"""Dish popularity — the source for the ranking engine's popularity weight."""
from __future__ import annotations

from fastapi import APIRouter

from ..models import PopularityEntry
from ..popularity import normalized_dish_popularity

router = APIRouter(prefix="/api", tags=["popularity"])


@router.get("/popularity", response_model=list[PopularityEntry])
def list_popularity() -> list[PopularityEntry]:
    scores = normalized_dish_popularity()
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [PopularityEntry(dish_id=dish_id, score=score) for dish_id, score in ranked]


@router.get("/popularity/{dish_id}", response_model=PopularityEntry)
def get_popularity(dish_id: str) -> PopularityEntry:
    scores = normalized_dish_popularity()
    return PopularityEntry(dish_id=dish_id, score=scores.get(dish_id, 0.0))
