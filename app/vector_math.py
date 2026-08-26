"""Vector ops shared across personalization: cosine, EMA update, nearest-neighbor."""
from __future__ import annotations

from typing import Iterable

import numpy as np

from .config import EMA_ALPHA


def _as_array(v: Iterable[float]) -> np.ndarray:
    return np.asarray(list(v), dtype=np.float32)


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    va, vb = _as_array(a), _as_array(b)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def ema_update(
    current: Iterable[float],
    signal: Iterable[float],
    alpha: float = EMA_ALPHA,
) -> list[float]:
    """Exponential moving average: new = (1-a)*current + a*signal, then renormalize."""
    vc, vs = _as_array(current), _as_array(signal)
    updated = (1.0 - alpha) * vc + alpha * vs
    norm = np.linalg.norm(updated)
    if norm == 0.0:
        return updated.tolist()
    return (updated / norm).tolist()


def top_k_similar(
    query: Iterable[float],
    candidates: dict[str, Iterable[float]],
    k: int = 5,
    exclude: Iterable[str] = (),
) -> list[tuple[str, float]]:
    exclude_set = set(exclude)
    scored = [
        (cid, cosine_similarity(query, vec))
        for cid, vec in candidates.items()
        if cid not in exclude_set
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
