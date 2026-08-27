import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.common import ORMModel


class UserSync(BaseModel):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    role: Literal["customer", "restaurant_partner", "admin"] | None = None


class TasteProfileUpdate(BaseModel):
    city: str | None = Field(default=None, max_length=100)
    preferred_cuisines: list[str] = Field(default_factory=list)
    favourite_dishes: list[str] = Field(default_factory=list)
    spice_preference: int = Field(ge=0, le=5)
    sweetness_preference: int = Field(ge=0, le=5)
    sourness_preference: int = Field(ge=0, le=5)
    saltiness_preference: int = Field(ge=0, le=5)
    oiliness_preference: int = Field(ge=0, le=5)
    richness_preference: int = Field(ge=0, le=5)
    preferred_textures: list[str] = Field(default_factory=list)
    budget_min: float = Field(ge=0)
    budget_max: float = Field(gt=0)
    dietary_requirements: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    require_halal: bool = False
    taste_vector: Annotated[
        list[float], Field(min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION)
    ]

    @model_validator(mode="after")
    def validate_budget(self):
        if self.budget_min > self.budget_max:
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class UserRead(ORMModel):
    id: uuid.UUID
    name: str
    email: str
    role: Literal["customer", "restaurant_partner", "admin"] = "customer"
    onboarding_complete: bool = False
    city: str | None = None
    created_at: datetime
    updated_at: datetime


class TasteProfileRead(ORMModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID = Field(validation_alias="id")
    name: str
    email: str
    role: Literal["customer", "restaurant_partner", "admin"]
    onboarding_complete: bool
    city: str | None
    preferred_cuisines: list[str]
    favourite_dishes: list[str]
    spice_preference: int
    sweetness_preference: int
    sourness_preference: int
    saltiness_preference: int
    oiliness_preference: int
    richness_preference: int
    preferred_textures: list[str]
    budget_min: float
    budget_max: float
    dietary_requirements: list[str]
    allergies: list[str]
    disliked_ingredients: list[str]
    require_halal: bool
    taste_updated_at: datetime | None


class SimilarUserRead(BaseModel):
    user_id: uuid.UUID
    name: str
    score: float = Field(ge=-1, le=1)
