import uuid
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.core.constants import EMBEDDING_DIMENSION


class FeedPreferences(BaseModel):
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, gt=0)
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    require_halal: bool = False
    user_lat: float | None = Field(default=None, ge=-90, le=90)
    user_lng: float | None = Field(default=None, ge=-180, le=180)
    max_distance_km: float | None = Field(default=None, gt=0)
    taste_vector: Annotated[
        list[float] | None,
        Field(default=None, min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION),
    ]
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_ranges(self):
        if (self.user_lat is None) != (self.user_lng is None):
            raise ValueError("user_lat and user_lng must be supplied together")
        if self.max_distance_km is not None and self.user_lat is None:
            raise ValueError("max_distance_km requires user coordinates")
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class SignalScores(BaseModel):
    taste: float = Field(ge=0, le=100)
    review: float = Field(ge=0, le=100)
    popularity: float = Field(ge=0, le=100)
    distance: float = Field(ge=0, le=100)
    price: float = Field(ge=0, le=100)
    context: float = Field(ge=0, le=100)
    collaborative: float = Field(ge=0, le=100)


class RankedDishItem(BaseModel):
    dish_id: uuid.UUID
    dish_name: str
    restaurant_id: uuid.UUID
    restaurant_name: str
    price: float = Field(gt=0)
    match_percentage: int = Field(ge=0, le=100)
    distance_km: float | None = Field(default=None, ge=0)
    signals: SignalScores


class FeedResponse(BaseModel):
    user_id: uuid.UUID
    total_candidates: int = Field(ge=0)
    items: list[RankedDishItem] = Field(default_factory=list)
    neutral_signals: list[str] = Field(default_factory=list)
