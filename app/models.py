"""Shared Pydantic contracts.

UserTaste and its onboarding-answer fields mirror Ganva's published
docs/contracts/v1/user-taste.schema.json ("onboarding handoff v1... for
Manahil's onboarding and personalization module") field-for-field, so the
Personalization Engine's public surface validates against that schema.
Interaction mirrors interaction.schema.json.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InteractionAction = Literal["click", "save", "order"]

# 0-5 scale per Ganva's dish.schema.json / user-taste.schema.json (spice_level,
# oiliness, sweetness, sourness, saltiness on dishes; *_preference on users).
TASTE_LEVEL_MIN = 0
TASTE_LEVEL_MAX = 5


class OnboardingAnswers(BaseModel):
    preferred_cuisines: list[str] = Field(default_factory=list, description="e.g. ['Pakistani','Italian']")
    favourite_dishes: list[str] = Field(default_factory=list, description="Free-text favorite dishes")
    spice_preference: int = Field(default=2, ge=TASTE_LEVEL_MIN, le=TASTE_LEVEL_MAX)
    sweetness_preference: int = Field(default=2, ge=TASTE_LEVEL_MIN, le=TASTE_LEVEL_MAX)
    sourness_preference: int = Field(default=2, ge=TASTE_LEVEL_MIN, le=TASTE_LEVEL_MAX)
    saltiness_preference: int = Field(default=2, ge=TASTE_LEVEL_MIN, le=TASTE_LEVEL_MAX)
    oiliness_preference: int = Field(default=2, ge=TASTE_LEVEL_MIN, le=TASTE_LEVEL_MAX)
    preferred_textures: list[str] = Field(default_factory=list, description="e.g. ['crispy','tender']")
    budget_min: float = Field(default=0, ge=0)
    budget_max: float = Field(default=1500, ge=0)
    dietary_requirements: list[str] = Field(default_factory=list, description="e.g. ['halal','vegetarian']")
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)

    @field_validator(
        "preferred_cuisines", "favourite_dishes", "preferred_textures",
        "dietary_requirements", "allergies", "disliked_ingredients",
        mode="before",
    )
    @classmethod
    def _strip_empties(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",")]
        return [str(item).strip() for item in v if str(item).strip()]

    @model_validator(mode="after")
    def _budget_range_valid(self):
        if self.budget_max < self.budget_min:
            self.budget_min, self.budget_max = self.budget_max, self.budget_min
        return self


class UserTaste(BaseModel):
    user_id: str
    preferred_cuisines: list[str]
    favourite_dishes: list[str]
    spice_preference: int
    sweetness_preference: int
    sourness_preference: int
    saltiness_preference: int
    oiliness_preference: int
    preferred_textures: list[str]
    budget_min: float
    budget_max: float
    dietary_requirements: list[str]
    allergies: list[str]
    disliked_ingredients: list[str]
    taste_vector: list[float]
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
