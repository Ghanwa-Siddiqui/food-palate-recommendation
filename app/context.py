"""Context-aware signal: meal-period preference from interaction timestamps.

Third leg of the flow diagram's Personalization Engine (content-based +
collaborative + context-aware). We don't have location/weather data, so the
only context we can honestly derive from what this module owns is *when*
a user tends to interact — useful as a tiebreaker/boost in the ranking
engine, not a hard filter.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .models import Interaction

# (period, start_hour_inclusive, end_hour_exclusive). late_night wraps midnight.
MEAL_PERIODS: list[tuple[str, int, int]] = [
    ("breakfast", 5, 11),
    ("lunch", 11, 16),
    ("dinner", 16, 22),
    ("late_night", 22, 5),
]


def meal_period(ts: datetime) -> str:
    hour = ts.hour
    for name, start, end in MEAL_PERIODS:
        if start < end:
            if start <= hour < end:
                return name
        elif hour >= start or hour < end:  # wraps midnight
            return name
    return "dinner"  # unreachable: periods above cover all 24 hours


def current_period(now: datetime | None = None) -> str:
    return meal_period(now or datetime.now(timezone.utc))


def period_preferences(interactions: list[Interaction]) -> dict[str, float]:
    """Fraction of past interactions that fell in each meal period."""
    if not interactions:
        return {}
    counts = Counter(meal_period(i.ts) for i in interactions)
    total = sum(counts.values())
    return {period: round(count / total, 3) for period, count in counts.items()}


def context_signal(interactions: list[Interaction], now: datetime | None = None) -> dict:
    prefs = period_preferences(interactions)
    now_period = current_period(now)
    preferred = max(prefs, key=prefs.get) if prefs else None
    return {
        "current_period": now_period,
        "preferred_period": preferred,
        "period_weights": prefs,
        "context_match": (preferred == now_period) if preferred else None,
    }
