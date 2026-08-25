"""Shared Pydantic contracts.

Mirrors the sprint's shared JSON shapes so all four modules can serialize/
deserialize the same objects. Fields here are the source of truth for the
Personalization Engine's public surface (see docs/contracts.md).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


InteractionAction = Literal["click", "save", "order"]


class OnboardingAnswers(BaseModel):
    cuisines: list[str] = Field(default_factory=list, description="Preferred cuisines, e.g. ['Pakistani','Italian']")
    favorite_foods: list[str] = Field(default_factory=list, description="Free-text favorite dishes/foods")
    dietary: list[str] = Field(default_factory=list, description="e.g. ['halal','vegetarian','no-beef']")
    spice_pref: int = Field(default=2, ge=0, le=4, description="0=none, 4=very hot")
    budget: int = Field(default=1000, ge=0, description="Per-meal ceiling, local currency")

    @field_validator("cuisines", "favorite_foods", "dietary", mode="before")
    @classmethod
    def _strip_empties(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",")]
        return [str(item).strip() for item in v if str(item).strip()]


class UserTaste(BaseModel):
    user_id: str
    taste_vector: list[float]
    budget: int
    dietary: list[str]
    spice_pref: int
    last_updated: datetime


class Interaction(BaseModel):
    user_id: str
    dish_id: str
    action: InteractionAction
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SimilarUser(BaseModel):
    user_id: str
    score: float


class ContextSignal(BaseModel):
    user_id: str
    current_period: str
    preferred_period: str | None
    period_weights: dict[str, float]
    context_match: bool | None


class PopularityEntry(BaseModel):
    dish_id: str
    score: float
