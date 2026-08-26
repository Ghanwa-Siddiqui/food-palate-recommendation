import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_serializer

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.common import ORMModel, Page


class DishRead(ORMModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    description: str | None
    cuisine: str
    ingredients: list[str]
    price: Decimal = Field(ge=0)
    spice_level: int = Field(ge=0, le=5)
    oiliness: int = Field(ge=0, le=5)
    sweetness: int = Field(ge=0, le=5)
    sourness: int = Field(ge=0, le=5)
    saltiness: int = Field(ge=0, le=5)
    smokiness: int = Field(ge=0, le=5)
    richness: int = Field(ge=0, le=5)
    texture_tags: list[str]
    dietary_tags: list[str]
    allergens: list[str]
    preparation_style: str
    availability: bool
    created_at: datetime
    updated_at: datetime
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)

    @field_serializer("price", when_used="json")
    def serialize_price(self, value: Decimal) -> float:
        return float(value)

    @field_serializer("lat", "lng", when_used="json")
    def serialize_coordinates(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class DishVectorRead(ORMModel):
    id: uuid.UUID
    vector: list[float] = Field(min_length=EMBEDDING_DIMENSION, max_length=EMBEDDING_DIMENSION)


class DishPage(Page[DishRead]):
    items: list[DishRead] = Field(default_factory=list)
