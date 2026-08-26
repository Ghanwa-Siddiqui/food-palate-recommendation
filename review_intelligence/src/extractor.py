"""Ollama-backed extraction of structured facts from an individual review."""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from . import config
from .models import ReviewFeatures, ValidationError


class ExtractionError(RuntimeError):
    """A review could not be extracted into valid structured data."""


class OllamaUnavailableError(ExtractionError):
    """Ollama is not reachable or is not serving the selected model."""


PROMPT = """You extract factual food-review signals. Return ONLY one valid JSON object,
with no Markdown, prose, code fence, or additional keys:
{"sentiment": number, "spice_level": number, "oiliness": number, "flavor_tags": [string]}

SCORING
- sentiment: 0.0 very negative, 0.5 genuinely mixed/neutral, 1.0 very positive.
  Infer it from the overall review language. "amazing", "delicious", "rich",
  "tender", and "warming" are positive; "bland", "dry", "cold", "tough",
  "too salty", "too oily", "ruined", and "did not enjoy" are negative. A clear
  negative phrase must not receive a positive score. Do NOT output 0.5 for clearly
  positive or negative text. If a rating is supplied in review context, treat 1 as
  strongly negative, 2 negative, 3 neutral, 4 positive, and 5 strongly positive.
- spice_level: 0.0 means explicitly mild/not spicy OR no spice information is stated;
  0.5 means the review explicitly says medium/moderate/balanced spice; 1.0 means
  extremely/very spicy. Never use 0.5 merely because spice was not mentioned.
- oiliness: 0.0 means explicitly not oily/not greasy/no grease/without excess oil OR
  no oil information is stated; 0.5 means explicitly moderately/slightly oily;
  1.0 means very/extremely oily or greasy. Never use 0.5 merely because oil was
  not mentioned.

NEGATION AND TAGS
- Understand negation: "not greasy", "not oily", "no excess oil", "without grease",
  "not spicy", and "not sweet" are NOT positive evidence for greasy, oily, spicy,
  or sweet tags. Never emit the negated characteristic.
- Include only characteristics explicitly stated or strongly implied. Do not invent.
- Use lowercase canonical tags only: spicy, mild, sweet, salty, sour, smoky, creamy,
  rich, rich gravy, tender, juicy, crispy, dry, oily, greasy, aromatic, savory,
  flavorful, bland, cold, tough, smooth, fluffy, fresh, delicious. Normalize variants
  such as "sweety" to "sweet" and "smokey" to "smoky". Return an empty array only
  when there are no supported tags.

Examples:
Review: "Amazing rich gravy but quite oily for my taste."
{"sentiment":0.85,"spice_level":0.0,"oiliness":0.7,"flavor_tags":["rich gravy","oily"]}
Review: "Mild flavor, but the kebabs were fresh and not greasy."
{"sentiment":0.75,"spice_level":0.0,"oiliness":0.0,"flavor_tags":["mild"]}

Review: """

CANONICAL_TAGS = {
    "spicy", "mild", "sweet", "salty", "sour", "smoky", "creamy", "rich",
    "rich gravy", "tender", "juicy", "crispy", "dry", "oily", "greasy",
    "aromatic", "savory", "flavorful", "bland", "cold", "tough", "smooth",
    "fluffy", "fresh", "delicious",
}
TAG_ALIASES = {
    "spice": "spicy", "hot": "spicy", "fiery": "spicy", "mildly spicy": "mild",
    "oil": "oily", "grease": "greasy", "greasy": "greasy", "sweety": "sweet",
    "sweetness": "sweet", "smoke": "smoky", "smokey": "smoky", "creaminess": "creamy",
    "richness": "rich", "tenderness": "tender", "juiciness": "juicy",
    "crunchy": "crispy", "crisp": "crispy", "dried": "dry", "savoury": "savory",
    "flavourful": "flavorful", "flavour": "flavorful", "delightful": "delicious",
}

TAG_EVIDENCE = {
    "spicy": ("spicy", "spice", "spiced", "hot", "fiery"),
    "mild": ("mild",), "sweet": ("sweet", "sweety"), "salty": ("salty",),
    "sour": ("sour",), "smoky": ("smoky", "smokey", "smoke"),
    "creamy": ("creamy",), "rich": ("rich",), "tender": ("tender",),
    "juicy": ("juicy",), "crispy": ("crispy", "crisp", "crunchy"),
    "dry": ("dry",), "oily": ("oily", "oil"), "greasy": ("greasy", "grease"),
    "aromatic": ("aromatic", "aroma"), "savory": ("savory", "savoury"),
    "flavorful": ("flavorful", "flavourful"), "bland": ("bland",),
    "cold": ("cold",), "tough": ("tough",), "smooth": ("smooth",),
    "fluffy": ("fluffy",), "fresh": ("fresh",), "delicious": ("delicious",),
}


def _mentioned(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) for term in terms)


def _negated(text: str, terms: tuple[str, ...]) -> bool:
    joined = "|".join(re.escape(term) for term in terms)
    return bool(re.search(rf"\b(?:not|no|without)\s+(?:very\s+|excess\s+)?(?:{joined})\b", text, re.IGNORECASE))


def _normalise_tags(tags: list[str], text: str) -> list[str]:
    """Constrain model tags to canonical, text-supported, non-negated food signals."""
    lower_text = text.lower()
    blocked: set[str] = set()
    if _negated(text, ("spicy", "spice", "hot")) or _mentioned(text, ("mild",)):
        blocked.add("spicy")
    if _negated(text, ("oily", "oil", "greasy", "grease")):
        blocked.update({"oily", "greasy"})
    if _negated(text, ("sweet",)):
        blocked.add("sweet")

    normalised: list[str] = []
    for raw_tag in tags:
        tag = raw_tag.strip().lower()
        tag = TAG_ALIASES.get(tag, tag)
        if tag not in CANONICAL_TAGS or tag in blocked:
            continue
        # Require evidence in the source review, allowing a canonical tag's aliases.
        evidence = TAG_EVIDENCE.get(tag, (tag,))
        if tag == "rich gravy":
            supported = "rich" in lower_text and "gravy" in lower_text
        else:
            supported = _mentioned(text, tuple(evidence))
        if supported and tag not in normalised:
            normalised.append(tag)
    # The model may omit plainly stated features. Add only direct source evidence.
    for tag in sorted(CANONICAL_TAGS):
        if tag in blocked or tag in normalised or tag == "rich gravy":
            continue
        if _mentioned(text, TAG_EVIDENCE.get(tag, (tag,))):
            normalised.append(tag)
    if "rich" in lower_text and "gravy" in lower_text:
        if "rich gravy" not in normalised:
            normalised.append("rich gravy")
    return normalised


def _rule_assisted_sentiment(model_score: float, text: str, rating: int | None = None) -> float:
    """Keep LLM sentiment, except where explicit wording/rating makes it implausible."""
    lower = text.lower()
    positive_terms = ("amazing", "delicious", "wonderful", "excellent", "tender", "rich", "warming", "fresh", "juicy", "perfectly")
    negative_terms = ("bland", "dry", "cold", "terrible", "too salty", "tough", "disappointing", "ruined", "did not enjoy", "too oily", "overly sweet", "soggy", "watery", "rubbery")
    positive = sum(term in lower for term in positive_terms)
    negative = sum(term in lower for term in negative_terms)
    rating_score = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.75, 5: 0.9}.get(rating)

    # Clear negative language takes precedence over a hallucinated positive score.
    if negative and not positive:
        text_score = 0.1 if negative >= 3 else 0.2
    elif positive and not negative:
        text_score = 0.9 if positive >= 3 else 0.85
    elif positive and negative:
        text_score = round(0.5 + 0.12 * (positive - negative), 2)
    else:
        text_score = model_score

    if rating_score is not None:
        # Rating is a strong signal, but explicit language remains visible in mixed reviews.
        return round(0.6 * rating_score + 0.4 * text_score, 3)
    if positive or negative:
        return text_score
    return model_score


def _spice_from_text(text: str) -> float:
    lower = text.lower()
    if _negated(text, ("spicy", "spice", "hot")) or _mentioned(text, ("mild",)):
        return 0.0
    if re.search(r"\b(?:very|extremely|too)\s+spicy\b", lower):
        return 0.9
    if _mentioned(text, ("medium", "moderate")) and _mentioned(text, ("spice", "spicy", "heat")):
        return 0.5
    if _mentioned(text, ("warmly spiced", "spiced")):
        return 0.5
    if _mentioned(text, ("spicy", "spice", "hot", "heat", "fiery")):
        return 0.75
    return 0.0


def _oiliness_from_text(text: str) -> float:
    lower = text.lower()
    oil_terms = ("oily", "oil", "greasy", "grease")
    if _negated(text, oil_terms):
        return 0.0
    if re.search(r"\b(?:very|extremely|too)\s+(?:oily|greasy)\b", lower):
        return 0.9
    if re.search(r"\b(?:slightly|a little|somewhat)\s+(?:oily|greasy)\b", lower):
        return 0.5
    if _mentioned(text, oil_terms):
        return 0.75
    return 0.0


def _apply_review_context(parsed: dict[str, Any], text: str, rating: int | None = None) -> dict[str, Any]:
    """Apply deterministic safeguards where a score/tag contradicts review wording."""
    value = dict(parsed)
    raw_tags = value.get("flavor_tags")
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
        return value  # Preserve schema error handling in ReviewFeatures.
    value["flavor_tags"] = _normalise_tags(raw_tags, text)
    value["spice_level"] = _spice_from_text(text)
    value["oiliness"] = _oiliness_from_text(text)
    try:
        value["sentiment"] = _rule_assisted_sentiment(float(value["sentiment"]), text, rating)
    except (KeyError, TypeError, ValueError):
        pass  # Preserve the validator's clear message for invalid model values.
    return value


class OllamaClient:
    def __init__(self, host: str = config.OLLAMA_HOST, model: str = config.OLLAMA_MODEL, timeout: float = config.OLLAMA_TIMEOUT_SECONDS):
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout

    def generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "format": "json", "stream": False},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OllamaUnavailableError(
                f"Cannot reach Ollama at {self.host}. Start it with `ollama serve` and pull "
                f"the configured model using `ollama pull {self.model}`."
            ) from exc
        if response.status_code >= 400:
            raise OllamaUnavailableError(
                f"Ollama returned HTTP {response.status_code}: {response.text}. Ensure model "
                f"`{self.model}` is available (`ollama pull {self.model}`)."
            )
        try:
            payload = response.json()
            return payload["response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExtractionError("Ollama returned a response without a generated text field") from exc


class ReviewExtractor:
    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    def extract(self, text: str, rating: int | None = None) -> ReviewFeatures:
        if not isinstance(text, str) or not text.strip():
            raise ExtractionError("Review text must be a non-empty string")
        if rating is not None and rating not in {1, 2, 3, 4, 5}:
            raise ExtractionError("Review rating must be an integer from 1 to 5 when provided")
        rating_context = f"\nRating context: {rating}/5" if rating is not None else ""
        raw = self.client.generate(PROMPT + text.strip() + rating_context)
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"Model returned malformed JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ExtractionError("Model JSON must be an object")
        try:
            return ReviewFeatures.from_mapping(_apply_review_context(parsed, text, rating))
        except ValidationError as exc:
            raise ExtractionError(f"Model JSON failed schema validation: {exc}") from exc
