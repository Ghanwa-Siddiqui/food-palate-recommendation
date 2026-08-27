import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _safe_text(value: str) -> str:
    value = value.strip()
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError("Review contains unsupported control characters")
    if "<script" in value.casefold():
        raise ValueError("Review contains unsupported markup")
    return value


class ReviewCreate(BaseModel):
    dish_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=10, max_length=2000)
    tried_confirmation: bool
    show_display_name: bool = False
    submission_key: str = Field(min_length=8, max_length=64)
    _clean = field_validator("text")(_safe_text)


class ReviewUpdate(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=10, max_length=2000)
    show_display_name: bool = False
    _clean = field_validator("text")(_safe_text)


class PublicReviewRead(BaseModel):
    id: uuid.UUID
    dish_id: uuid.UUID
    rating: int
    text: str
    reviewer_name: str
    created_at: datetime
    updated_at: datetime


class ReviewRead(ORMModel):
    """Internal compatibility model; never used by public review endpoints."""

    id: uuid.UUID
    user_id: uuid.UUID
    dish_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    text: str | None
    created_at: datetime


class OwnReviewRead(PublicReviewRead):
    processing_status: str


class ReviewSummary(BaseModel):
    dish_id: uuid.UUID
    review_count: int = Field(ge=0)
    average_rating: float | None = Field(default=None, ge=1, le=5)
    avg_sentiment: float | None = Field(default=None, ge=0, le=1)
    spice_level: float | None = Field(default=None, ge=0, le=1)
    oiliness: float | None = Field(default=None, ge=0, le=1)
    flavor_tags: list[str]
