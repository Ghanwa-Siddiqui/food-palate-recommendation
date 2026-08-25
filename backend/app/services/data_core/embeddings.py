from collections.abc import Sequence
from typing import Protocol

from app.core.constants import EMBEDDING_DIMENSION


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddingProvider:
    """Lazy local provider; importing this module never downloads or loads a model."""

    dimension = EMBEDDING_DIMENSION

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        vector = self._get_model().encode(text, normalize_embeddings=True)
        values = [float(value) for value in vector]
        if len(values) != self.dimension:
            raise ValueError(f"expected {self.dimension} dimensions, got {len(values)}")
        return values


class DeterministicFakeEmbeddingProvider:
    dimension = EMBEDDING_DIMENSION

    def embed(self, text: str) -> list[float]:
        seed = sum((index + 1) * ord(character) for index, character in enumerate(text))
        return [((seed + index * 31) % 1000) / 1000 for index in range(self.dimension)]


def build_dish_embedding_text(
    *,
    name: str,
    description: str | None,
    cuisine: str,
    ingredients: Sequence[str],
    spice_level: int,
    oiliness: int,
    sweetness: int,
    sourness: int,
    saltiness: int,
    smokiness: int,
    richness: int,
    texture_tags: Sequence[str],
    dietary_tags: Sequence[str],
    allergens: Sequence[str],
    preparation_style: str,
    availability: bool,
) -> str:
    return " | ".join(
        (
            f"name: {name}",
            f"description: {description or ''}",
            f"cuisine: {cuisine}",
            f"ingredients: {', '.join(ingredients)}",
            f"taste: spice {spice_level}/5, oiliness {oiliness}/5, sweetness "
            f"{sweetness}/5, sourness {sourness}/5, saltiness {saltiness}/5",
            f"smokiness: {smokiness}/5 | richness: {richness}/5",
            f"textures: {', '.join(texture_tags)}",
            f"dietary: {', '.join(dietary_tags)}",
            f"allergens: {', '.join(allergens)}",
            f"preparation: {preparation_style}",
            f"available: {availability}",
        )
    )
