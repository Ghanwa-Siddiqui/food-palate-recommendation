"""Dish popularity from interaction logs.

Ranking engine's weighted score (task 33) includes a 5% "popularity" term
but no task defines its source. Interactions are stored here, so we compute
it here: order/save/click weighted counts, normalized to [0,1] against the
current max so Esha can drop it straight into the weighted sum.
"""

from __future__ import annotations

from collections import defaultdict

from .repositories import get_repository

ACTION_WEIGHTS = {"click": 1.0, "save": 2.0, "order": 3.0}


def raw_dish_scores() -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for interaction in get_repository().all_interactions():
        scores[interaction.dish_id] += ACTION_WEIGHTS.get(interaction.action, 1.0)
    return dict(scores)


def normalized_dish_popularity() -> dict[str, float]:
    """Each dish's score divided by the current max score. Empty log -> {}."""
    raw = raw_dish_scores()
    if not raw:
        return {}
    max_score = max(raw.values())
    if max_score == 0:
        return {k: 0.0 for k in raw}
    return {k: round(v / max_score, 4) for k, v in raw.items()}
