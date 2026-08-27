"""Server-side dish profile embedding without browser-supplied vectors."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.dish import PartnerDishWrite


class DishEmbeddingService(Protocol):
    def generate(self, profile: PartnerDishWrite) -> list[float]: ...


class DeterministicDishEmbeddingService:
    """Stable local baseline; replaceable without changing partner contracts."""

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
    return DeterministicDishEmbeddingService()
