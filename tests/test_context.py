from datetime import datetime, timezone

from app.context import context_signal, current_period, meal_period, period_preferences
from app.models import Interaction


def _ts(hour: int) -> datetime:
    return datetime(2026, 8, 25, hour, 0, tzinfo=timezone.utc)


def test_meal_period_boundaries():
    assert meal_period(_ts(5)) == "breakfast"
    assert meal_period(_ts(10)) == "breakfast"
    assert meal_period(_ts(11)) == "lunch"
    assert meal_period(_ts(15)) == "lunch"
    assert meal_period(_ts(16)) == "dinner"
    assert meal_period(_ts(21)) == "dinner"
    assert meal_period(_ts(22)) == "late_night"
    assert meal_period(_ts(2)) == "late_night"
    assert meal_period(_ts(4)) == "late_night"


def test_current_period_uses_now_by_default():
    assert current_period(_ts(12)) == "lunch"


def test_period_preferences_empty():
    assert period_preferences([]) == {}


def test_period_preferences_distribution():
    interactions = [
        Interaction(user_id="u1", dish_id="d1", action="click", ts=_ts(12)),
        Interaction(user_id="u1", dish_id="d2", action="click", ts=_ts(13)),
        Interaction(user_id="u1", dish_id="d3", action="order", ts=_ts(19)),
    ]
    prefs = period_preferences(interactions)
    assert prefs["lunch"] == round(2 / 3, 3)
    assert prefs["dinner"] == round(1 / 3, 3)


def test_context_signal_match_and_mismatch():
    interactions = [
        Interaction(user_id="u1", dish_id="d1", action="order", ts=_ts(19)),
        Interaction(user_id="u1", dish_id="d2", action="order", ts=_ts(20)),
    ]
    sig = context_signal(interactions, now=_ts(18))
    assert sig["preferred_period"] == "dinner"
    assert sig["current_period"] == "dinner"
    assert sig["context_match"] is True

    sig2 = context_signal(interactions, now=_ts(8))
    assert sig2["current_period"] == "breakfast"
    assert sig2["context_match"] is False
