"""Deterministic mock embedding.

Day-1 stand-in for a real embedding model. Same input text always yields the
same unit-length vector, so the rest of the pipeline (cosine similarity, EMA
updates, nearest-neighbor) behaves stably in tests and dev.

Swap this module out for sentence-transformers or an API call later; nothing
else in the codebase should need to change.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence

import numpy as np

from .config import VECTOR_DIM


def _seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def embed_text(text: str, dim: int = VECTOR_DIM) -> list[float]:
    if not text:
        return [0.0] * dim
    rng = np.random.default_rng(_seed_from_text(text.lower().strip()))
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0.0:
        return [0.0] * dim
    return (vec / norm).tolist()


def embed_terms(terms: Iterable[str], dim: int = VECTOR_DIM) -> list[float]:
    """Average-embed a bag of terms into one unit vector."""
    terms = [t for t in terms if t]
    if not terms:
        return [0.0] * dim
    stacked = np.stack([np.array(embed_text(t, dim), dtype=np.float32) for t in terms])
    mean = stacked.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0.0:
        return [0.0] * dim
    return (mean / norm).tolist()


def embed_dish(
    name: str, cuisine: str, ingredients: Sequence[str], dim: int = VECTOR_DIM
) -> list[float]:
    """Compose a dish vector from name + cuisine + ingredients."""
    terms = [name, cuisine, *ingredients]
    return embed_terms(terms, dim)
