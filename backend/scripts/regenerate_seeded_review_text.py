"""Rewrite every seeded review's text with a real local LLM, in development
data, then score and embed it through the same real signals a genuine
review submission gets.

Both customer-taste-demo seed batches build review text by concatenating a
canned opening ("I tried the {dish}.") with one of a small pool of fixed
ending sentences per rating tier. At the ~800-review scale this reads as
obviously templated - many reviews across different dishes are close to
word-for-word identical. It also means the seeded reviews' sentiment/
spice/oiliness/embedding were computed by the seed script's rule-based
extractor and a deterministic fake embedder, not the real pipeline.

This machine runs Ollama on CPU only (no usable GPU), and a single
generation call was measured at ~50s - the app's real pipeline
(LiveReviewProcessor) does two Ollama round trips per review (extract,
then... no, one - but this script originally wrote text with one call and
extracted with a second), which would put ~800 reviews at 18-20 hours.
Instead of two calls, this asks Ollama to write the review AND self-score
it (sentiment/spice/oiliness/tags) in one JSON call, then runs the exact
same deterministic refinement pass `ReviewExtractor` itself applies
(`_apply_review_context`: rule-based spice/oiliness/sentiment adjustment
from the actual text, tag normalisation) before embedding the text with
the real local Sentence Transformers model. So the only thing skipped is
a second LLM round trip for something the first call already produced -
the text is still real, the scores are still real (LLM + the same
rule-based safeguards the live endpoint uses), the embedding is still
real.

Not idempotent by design - re-running regenerates fresh text each time
(LLM output isn't deterministic), which is fine since the point is
variety, not reproducibility. Committed in small batches rather than one
transaction, since even at one call per review this is a long-running job
against a cloud database.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.routes.reviews import _recompute
from app.core.config import get_settings
from app.db.session import get_engine
from app.models.dish import Dish
from app.models.review import Review
from scripts.seed import SeedSafetyError, extract_supabase_project_ref, verify_seed_preconditions
from scripts.seed_customer_taste_demo import BATCH as WAVE1_BATCH
from scripts.seed_customer_taste_demo_wave2 import BATCH as WAVE2_BATCH

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from review_intelligence.src import config as review_intelligence_config  # noqa: E402
from review_intelligence.src.embeddings import ReviewEmbedder  # noqa: E402
from review_intelligence.src.extractor import _apply_review_context  # noqa: E402
from review_intelligence.src.models import ReviewFeatures, ValidationError  # noqa: E402

CORRECTION_CONFIRMATION = "REGENERATE_CHASKA_SEEDED_REVIEW_TEXT"

SEED_BATCH_PREFIXES = (f"{WAVE1_BATCH}:review:", f"{WAVE2_BATCH}:review:")

# The two seed scripts only ever produce openings shaped like these (see
# seed_customer_taste_demo.py / seed_customer_taste_demo_wave2.py _OPENINGS).
# A review still starting with one of these is un-regenerated - LLM output
# essentially never reproduces one verbatim - so this doubles as a resume
# marker: on a rerun (this machine is slow enough that a multi-hour job can
# get interrupted), already-regenerated reviews are skipped instead of
# redone from scratch.
_ORIGINAL_TEMPLATE_PREFIXES = (
    "I tried the ",
    "Ordered the ",
    "Finally got to taste the ",
    "Picked up the ",
    "Gave the ",
)

# CPU-only local inference on this host has been observed anywhere from
# ~50s to a full timeout for one call, so retries need generous headroom
# and backoff rather than assuming a fixed, fast response time.
_TIMEOUT_BACKOFFS = [30, 90, 240]

_WRITE_AND_SCORE_PROMPT = """You are a real customer. Write a short, natural restaurant
review, then score your own review. Return ONLY one valid JSON object, no markdown, no
prose, no extra keys:
{{"review": string, "sentiment": number, "spice_level": number, "oiliness": number, "flavor_tags": [string]}}

"review": first person, 1 to 2 sentences, plain conversational language - not a marketing
blurb - for the dish and star rating below.

Score your own "review" text using these rules:
- sentiment: 0.0 very negative, 0.5 genuinely mixed/neutral, 1.0 very positive. A star
  rating of 1 is strongly negative, 2 negative, 3 neutral, 4 positive, 5 strongly positive -
  match that.
- spice_level: 0.0 if not spicy or spice isn't mentioned; 0.5 if moderately spicy; 1.0 if
  very spicy.
- oiliness: 0.0 if not oily or oil isn't mentioned; 0.5 if moderately oily; 1.0 if very oily.
- flavor_tags: lowercase canonical tags only, from: spicy, mild, sweet, salty, sour, smoky,
  creamy, rich, rich gravy, tender, juicy, crispy, dry, oily, greasy, aromatic, savory,
  flavorful, bland, cold, tough, smooth, fluffy, fresh, delicious. Only tags your review
  text actually supports.

Dish: {dish_name}
Cuisine: {cuisine}
Star rating: {rating}/5
"""


class ReviewWriteError(RuntimeError):
    pass


class OllamaReviewWriter:
    def __init__(
        self,
        host: str = review_intelligence_config.OLLAMA_HOST,
        model: str = review_intelligence_config.OLLAMA_MODEL,
        timeout: float = 240.0,
        on_retry=None,
    ) -> None:
        self.host, self.model, self.timeout = host.rstrip("/"), model, timeout
        self.on_retry = on_retry

    def write_and_score(self, *, dish_name: str, cuisine: str, rating: int) -> tuple[str, ReviewFeatures]:
        last_error: Exception | None = None
        for wait in [0, *_TIMEOUT_BACKOFFS]:
            if wait:
                if self.on_retry:
                    self.on_retry(wait)
                time.sleep(wait)
            try:
                return self._attempt(dish_name=dish_name, cuisine=cuisine, rating=rating)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
        raise ReviewWriteError(
            f"Ollama at {self.host} did not respond after {len(_TIMEOUT_BACKOFFS) + 1} attempts "
            f"(CPU-only generation on this host is slow and sometimes unreliable)."
        ) from last_error

    def _attempt(self, *, dish_name: str, cuisine: str, rating: int) -> tuple[str, ReviewFeatures]:
        prompt = _WRITE_AND_SCORE_PROMPT.format(
            dish_name=dish_name, cuisine=cuisine, rating=rating
        )
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "format": "json", "stream": False},
                timeout=self.timeout,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            raise  # let the retry loop in write_and_score handle these
        except requests.exceptions.RequestException as exc:
            raise ReviewWriteError(f"Ollama request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ReviewWriteError(f"Ollama returned HTTP {response.status_code}: {response.text}")
        try:
            raw = response.json()["response"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ReviewWriteError("Ollama returned a response without generated text") from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReviewWriteError(f"Ollama returned malformed JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("review"), str):
            raise ReviewWriteError("Ollama JSON is missing a 'review' string")
        text = parsed["review"].strip().strip('"')
        if not text:
            raise ReviewWriteError("Ollama returned empty review text")
        try:
            features = ReviewFeatures.from_mapping(
                _apply_review_context(parsed, text, rating)
            )
        except ValidationError as exc:
            raise ReviewWriteError(f"Ollama JSON failed schema validation: {exc}") from exc
        return text, features


def authorize_correction(
    *,
    database_url: str,
    app_env: str,
    confirmation: str | None,
    expected_project_ref: str | None,
) -> None:
    if app_env != "development":
        raise SeedSafetyError("development-data correction requires APP_ENV=development")
    if not secrets.compare_digest(confirmation or "", CORRECTION_CONFIRMATION):
        raise SeedSafetyError("development-data correction confirmation did not match")
    if not expected_project_ref:
        raise SeedSafetyError("EXPECTED_SUPABASE_PROJECT_REF is required")
    target_project_ref = extract_supabase_project_ref(database_url)
    if not secrets.compare_digest(target_project_ref, expected_project_ref):
        raise SeedSafetyError("Supabase project reference did not match the expected target")


def _seed_review_filter():
    return or_(*(Review.submission_key.like(f"{prefix}%") for prefix in SEED_BATCH_PREFIXES))


def regenerate_seeded_review_text(
    session: Session,
    *,
    writer: OllamaReviewWriter,
    embedder: ReviewEmbedder,
    on_progress=None,
    on_skip=None,
) -> int:
    all_reviews = list(
        session.scalars(select(Review).where(_seed_review_filter()).order_by(Review.id))
    )
    if not all_reviews:
        raise SeedSafetyError("no seeded reviews found to regenerate")
    reviews = [
        review
        for review in all_reviews
        if (review.text or "").startswith(_ORIGINAL_TEMPLATE_PREFIXES)
    ]
    if not reviews:
        return 0

    dishes = {
        dish.id: dish
        for dish in session.scalars(
            select(Dish).where(Dish.id.in_({review.dish_id for review in reviews}))
        )
    }
    touched_dish_ids: set = set()
    now = datetime.now(UTC)
    # Committed in small batches, not one transaction for the whole run: this
    # is a long-running job (one Ollama call per review, ~50s-plus on this
    # CPU-only host) against a cloud database - a single multi-hour
    # transaction risks a connection/pool timeout that would roll back
    # everything already done. Partial progress persisting on interruption
    # is the right tradeoff for one-off dev-data cleanup like this.
    regenerated = 0
    for index, review in enumerate(reviews):
        dish = dishes[review.dish_id]
        try:
            text, features = writer.write_and_score(
                dish_name=dish.name, cuisine=dish.cuisine, rating=review.rating
            )
        except ReviewWriteError as exc:
            # Leave this one's original templated text in place - it still
            # matches _ORIGINAL_TEMPLATE_PREFIXES, so a rerun will retry it -
            # and keep going rather than losing hours of progress on the
            # rest over one stubborn review.
            if on_skip:
                on_skip(index + 1, len(reviews), str(exc))
            continue
        review.text = text
        review.sentiment = features.sentiment
        review.spice_score = features.spice_level
        review.oiliness_score = features.oiliness
        review.flavor_tags = features.flavor_tags
        review.review_embedding = embedder.embed(text)
        review.processing_status = "complete"
        review.processing_error_code = None
        review.updated_at = now
        touched_dish_ids.add(dish.id)
        regenerated += 1
        if regenerated % 10 == 0:
            session.commit()
        if on_progress:
            on_progress(index + 1, len(reviews))
    session.commit()

    reviews_by_dish = defaultdict(list)
    for review in session.scalars(
        select(Review).where(Review.dish_id.in_(touched_dish_ids), Review.archived_at.is_(None))
    ):
        reviews_by_dish[review.dish_id].append(review)
    for dish_id in touched_dish_ids:
        _recompute(dishes[dish_id], reviews_by_dish[dish_id])
    session.commit()

    return regenerated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    settings = get_settings()

    def on_progress(done: int, total: int) -> None:
        print(f"  regenerated {done}/{total}", flush=True)

    def on_skip(done: int, total: int, reason: str) -> None:
        print(f"  skipped {done}/{total} (will retry on next run): {reason}", flush=True)

    def on_retry(wait: float) -> None:
        print(f"  slow/no response, retrying in {wait:.0f}s...", flush=True)

    try:
        authorize_correction(
            database_url=settings.database_url,
            app_env=settings.app_env,
            confirmation=args.confirmation,
            expected_project_ref=settings.expected_supabase_project_ref,
        )
        with Session(get_engine()) as session:
            with session.begin():
                verify_seed_preconditions(session, require_empty_catalog=False)
            count = regenerate_seeded_review_text(
                session,
                writer=OllamaReviewWriter(on_retry=on_retry),
                embedder=ReviewEmbedder(),
                on_progress=on_progress,
                on_skip=on_skip,
            )
    except SeedSafetyError as error:
        raise SystemExit(str(error)) from error
    except ReviewWriteError as error:
        raise SystemExit(str(error)) from error

    print(f"Regenerated text and reprocessed {count} seeded reviews")


if __name__ == "__main__":
    main()
