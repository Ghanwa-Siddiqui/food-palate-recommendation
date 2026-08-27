import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.core.constants import EMBEDDING_DIMENSION
from app.schemas.common import ORMModel, Page


class PartnerDishWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    cuisine: str = Field(min_length=2, max_length=100)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    availability: bool = True
    ingredients: list[str] = Field(min_length=1, max_length=100)
    allergens: list[str] = Field(default_factory=list, max_length=50)
    dietary_tags: list[str] = Field(default_factory=list, max_length=50)
    preparation_style: str = Field(min_length=2, max_length=100)
    image_path: str | None = Field(default=None, max_length=300)
    spice_level: int = Field(ge=0, le=5)
    sweetness: int = Field(ge=0, le=5)
    sourness: int = Field(ge=0, le=5)
    saltiness: int = Field(ge=0, le=5)
    oiliness: int = Field(ge=0, le=5)
    richness: int = Field(ge=0, le=5)
    smokiness: int = Field(ge=0, le=5)
    texture_tags: list[str] = Field(min_length=1, max_length=50)

    @field_validator("ingredients", "allergens", "dietary_tags", "texture_tags")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("image_path")
    @classmethod
    def local_image_only(cls, value: str | None) -> str | None:
        if value and (not value.startswith("/static/images/") or ".." in value):
            raise ValueError("image_path must be a local static image")
        return value

    @model_validator(mode="after")
    def required_profile_lists(self):
        if not self.ingredients or not self.texture_tags:
            raise ValueError("ingredients and textures are required")
        return self


class PartnerDishCreate(PartnerDishWrite):
    restaurant_id: uuid.UUID


class PartnerDishUpdate(PartnerDishWrite):
    pass


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
    image_path: str | None = None
    archived_at: datetime | None = None
    embedding_updated_at: datetime | None = None
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
