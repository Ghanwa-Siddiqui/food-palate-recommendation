"""Server-side dish profile embedding without browser-supplied vectors."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import get_settings
from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.dish import PartnerDishWrite
from app.services.data_core.embeddings import (
    SentenceTransformerEmbeddingProvider,
    build_dish_embedding_text,
)


class DishEmbeddingService(Protocol):
    def generate(self, profile: PartnerDishWrite) -> list[float]: ...


class SentenceTransformerDishEmbeddingService:
    """Real semantic dish embedding - the same local Sentence Transformers
    model (and build_dish_embedding_text composition) already used for the
    base catalog seed and review embeddings, so a partner-submitted dish
    lands in the same embedding space as everything it's ranked against."""

    def __init__(self, model_name: str | None = None) -> None:
        self._provider = SentenceTransformerEmbeddingProvider(
            model_name or get_settings().embedding_model
        )

    def generate(self, profile: PartnerDishWrite) -> list[float]:
        text = build_dish_embedding_text(
            name=profile.name,
            description=profile.description,
            cuisine=profile.cuisine,
            ingredients=profile.ingredients,
            spice_level=profile.spice_level,
            oiliness=profile.oiliness,
            sweetness=profile.sweetness,
            sourness=profile.sourness,
            saltiness=profile.saltiness,
            smokiness=profile.smokiness,
            richness=profile.richness,
            texture_tags=profile.texture_tags,
            dietary_tags=profile.dietary_tags,
            allergens=profile.allergens,
            preparation_style=profile.preparation_style,
            availability=profile.availability,
        )
        return self._provider.embed(text)


class DeterministicDishEmbeddingService:
    """Hash-based placeholder, kept for tests that want a fast, dependency-
    free stand-in. Not used by get_dish_embedding_service's default (the
    real endpoint needs a real embedding) - inject it explicitly via
    app.dependency_overrides in tests that don't need semantic meaning."""

    def generate(self, profile: PartnerDishWrite) -> list[float]:
        terms = [
            profile.name,
            profile.cuisine,
            *profile.ingredients,
            *profile.dietary_tags,
            *profile.texture_tags,
            profile.preparation_style,
            *(f"{field}:{getattr(profile, field)}" for field in _TASTE_FIELDS),
        ]
        seed = "|".join(term.strip().casefold() for term in terms if term.strip()).encode()
        values: list[float] = []
        counter = 0
        while len(values) < EMBEDDING_DIMENSION:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend((byte - 127.5) / 127.5 for byte in digest)
            counter += 1
        values = values[:EMBEDDING_DIMENSION]
        magnitude = math.sqrt(sum(value * value for value in values))
        return [value / magnitude for value in values]


_TASTE_FIELDS = (
    "spice_level",
    "sweetness",
    "sourness",
    "saltiness",
    "oiliness",
    "richness",
    "smokiness",
)


def get_dish_embedding_service() -> DishEmbeddingService:
    return SentenceTransformerDishEmbeddingService()
