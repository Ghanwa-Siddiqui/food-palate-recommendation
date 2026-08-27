"""Read-only accessor for the dish catalog fixture.

Ganva owns dishes; this module just consumes the JSON they publish. Day 1 it
reads data/mock_dishes.json (our own fixtures); Day 2 it will point at
Ganva's real seed file or the /dishes API.
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_dishes() -> list[dict]:
    path = config.DATA_DIR / "mock_dishes.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def get_dish(dish_id: str) -> dict | None:
    for d in load_dishes():
        if d.get("id") == dish_id:
            return d
    return None


def dish_vector(dish_id: str) -> list[float] | None:
    d = get_dish(dish_id)
    return d.get("vector") if d else None


def invalidate_cache() -> None:
    load_dishes.cache_clear()
