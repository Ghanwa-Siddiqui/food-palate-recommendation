"""Domain logic for building/updating user taste vectors.

Keeps the vector-composition rules in one place so tests can pin them down
and the API layer stays thin.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from .config import VECTOR_DIM
from .embedding import embed_terms
from .models import OnboardingAnswers, UserTaste
from .vector_math import ema_update

# Relative weights when mixing signals into the initial taste vector.
# Cuisines and favorite dishes carry the most personalization signal; the
# five taste dimensions and textures are lighter hints because dietary/
# allergy fields are also used as hard filters downstream by Esha's
# candidate generator, not just soft vector signal.
WEIGHT_CUISINES = 0.35
WEIGHT_DISHES = 0.30
WEIGHT_TASTE_DIMS = 0.20
WEIGHT_TEXTURES = 0.10
WEIGHT_DIETARY = 0.05

# 0-5 scale, matching Ganva's dish.schema.json (spice_level, oiliness, etc.)
_LEVEL_WORDS = ["none", "very light", "light", "moderate", "strong", "very strong"]


def _level_phrase(dimension: str, level: int) -> str:
    word = _LEVEL_WORDS[max(0, min(5, level))]
    return f"{word} {dimension}"


def _weighted_sum(vectors_with_weights: list[tuple[list[float], float]]) -> list[float]:
    active = [(v, w) for v, w in vectors_with_weights if any(v)]
    if not active:
        return [0.0] * VECTOR_DIM
    total_w = sum(w for _, w in active)
    stacked = np.stack([np.array(v, dtype=np.float32) * (w / total_w) for v, w in active])
    summed = stacked.sum(axis=0)
    norm = np.linalg.norm(summed)
    if norm == 0.0:
        return summed.tolist()
    return (summed / norm).tolist()


def build_taste_vector(answers: OnboardingAnswers) -> list[float]:
    cuisine_vec = embed_terms(answers.preferred_cuisines)
    dish_vec = embed_terms(answers.favourite_dishes)
    taste_dims_vec = embed_terms([
        _level_phrase("spice", answers.spice_preference),
        _level_phrase("sweetness", answers.sweetness_preference),
        _level_phrase("sourness", answers.sourness_preference),
        _level_phrase("saltiness", answers.saltiness_preference),
        _level_phrase("oiliness", answers.oiliness_preference),
    ])
    texture_vec = embed_terms(answers.preferred_textures)
    dietary_vec = embed_terms(answers.dietary_requirements)
    return _weighted_sum([
        (cuisine_vec, WEIGHT_CUISINES),
        (dish_vec, WEIGHT_DISHES),
        (taste_dims_vec, WEIGHT_TASTE_DIMS),
        (texture_vec, WEIGHT_TEXTURES),
        (dietary_vec, WEIGHT_DIETARY),
    ])


def user_from_onboarding(user_id: str, answers: OnboardingAnswers) -> UserTaste:
    return UserTaste(
        user_id=user_id,
        preferred_cuisines=answers.preferred_cuisines,
        favourite_dishes=answers.favourite_dishes,
        spice_preference=answers.spice_preference,
        sweetness_preference=answers.sweetness_preference,
        sourness_preference=answers.sourness_preference,
        saltiness_preference=answers.saltiness_preference,
        oiliness_preference=answers.oiliness_preference,
        preferred_textures=answers.preferred_textures,
        budget_min=answers.budget_min,
        budget_max=answers.budget_max,
        dietary_requirements=answers.dietary_requirements,
        allergies=answers.allergies,
        disliked_ingredients=answers.disliked_ingredients,
        taste_vector=build_taste_vector(answers),
        last_updated=datetime.now(timezone.utc),
    )


def apply_interaction_update(user: UserTaste, dish_vector: list[float]) -> UserTaste:
    """Nudge the user's vector toward a dish they interacted with (EMA)."""
    return user.model_copy(update={
        "taste_vector": ema_update(user.taste_vector, dish_vector),
        "last_updated": datetime.now(timezone.utc),
    })
