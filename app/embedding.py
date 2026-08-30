"""Real local Sentence Transformers embeddings for taste vectors and dish text.

Same model family the backend already uses for review embeddings
(`sentence-transformers/all-MiniLM-L6-v2`, 384-dim), so a user's taste
vector and a dish's embedding live in the same semantic space and cosine
similarity between them means something - unlike the old hash-based mock
this replaces, where two unrelated strings just landed on unrelated random
vectors regardless of what they actually meant.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

import numpy as np

from .config import EMBEDDING_MODEL, VECTOR_DIM


class EmbeddingError(RuntimeError):
    pass


class _Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: object) -> object: ...


_model: _Encoder | None = None


def _load_model() -> _Encoder:
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(EMBEDDING_MODEL)
        except Exception as exc:  # dependency/model downloads can fail in many ways
            raise EmbeddingError(
                f"Could not load embedding model `{EMBEDDING_MODEL}`. Install "
                "sentence-transformers and ensure the model can be downloaded or is "
                "cached locally."
            ) from exc
    return _model


def embed_terms(terms: Iterable[str], dim: int = VECTOR_DIM) -> list[float]:
    """Average-embed a bag of terms into one unit vector."""
    cleaned = [t.strip() for t in terms if t and t.strip()]
    if not cleaned:
        return [0.0] * dim
    vectors = _load_model().encode(cleaned, normalize_embeddings=True)
    values = np.asarray(vectors, dtype=np.float32)
    if values.shape[-1] != dim:
        raise EmbeddingError(f"expected {dim} dimensions, got {values.shape[-1]}")
    mean = values.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0.0:
        return mean.tolist()
    return (mean / norm).tolist()


def embed_text(text: str, dim: int = VECTOR_DIM) -> list[float]:
    return embed_terms([text], dim)


def embed_dish(
    name: str, cuisine: str, ingredients: Sequence[str], dim: int = VECTOR_DIM
) -> list[float]:
    """Compose a dish vector from name + cuisine + ingredients."""
    terms = [name, cuisine, *ingredients]
    return embed_terms(terms, dim)
