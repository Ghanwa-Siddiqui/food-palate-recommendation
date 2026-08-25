"""Domain logic for building/updating user taste vectors.

Keeps the vector-composition rules in one place so tests can pin them down
and the API layer stays thin.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from .config import VECTOR_DIM
from .embedding import embed_terms, embed_text
from .models import OnboardingAnswers, UserTaste
from .vector_math import ema_update

# Relative weights when mixing signals into the initial taste vector.
# Cuisines and favorite foods carry the most personalization signal;
# spice/dietary are lighter hints because they're also used as hard filters
# downstream by Esha's candidate generator.
WEIGHT_CUISINES = 0.45
WEIGHT_FOODS = 0.40
WEIGHT_SPICE = 0.10
WEIGHT_DIETARY = 0.05

_SPICE_WORDS = {0: "mild", 1: "gentle", 2: "medium", 3: "spicy", 4: "very hot"}


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
    cuisine_vec = embed_terms(answers.cuisines)
    food_vec = embed_terms(answers.favorite_foods)
    spice_vec = embed_text(_SPICE_WORDS.get(answers.spice_pref, "medium"))
    dietary_vec = embed_terms(answers.dietary)
    return _weighted_sum([
        (cuisine_vec, WEIGHT_CUISINES),
        (food_vec, WEIGHT_FOODS),
        (spice_vec, WEIGHT_SPICE),
        (dietary_vec, WEIGHT_DIETARY),
    ])


def user_from_onboarding(user_id: str, answers: OnboardingAnswers) -> UserTaste:
    return UserTaste(
        user_id=user_id,
        taste_vector=build_taste_vector(answers),
        budget=answers.budget,
        dietary=answers.dietary,
        spice_pref=answers.spice_pref,
        last_updated=datetime.now(timezone.utc),
    )


def apply_interaction_update(user: UserTaste, dish_vector: list[float]) -> UserTaste:
    """Nudge the user's vector toward a dish they interacted with (EMA)."""
    return user.model_copy(update={
        "taste_vector": ema_update(user.taste_vector, dish_vector),
        "last_updated": datetime.now(timezone.utc),
    })
