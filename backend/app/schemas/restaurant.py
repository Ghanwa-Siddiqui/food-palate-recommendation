import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.schemas.common import ORMModel, Page

HalalStatus = Literal["verified", "claimed", "not_halal", "unknown"]
HalalVerificationStatus = Literal["unverified", "pending", "verified", "rejected"]


class PartnerRestaurantWrite(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    address: str = Field(min_length=3, max_length=300)
    city: str = Field(min_length=2, max_length=100)
    cuisine_types: list[str] = Field(min_length=1, max_length=8)
    contact_phone: str | None = Field(default=None, max_length=40)
    halal_status: HalalStatus = "unknown"
    halal_verification_status: HalalVerificationStatus = "unverified"
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lng: Decimal | None = Field(default=None, ge=-180, le=180)
    opening_information: str | None = Field(default=None, max_length=500)
    available: bool = True
    image_path: str | None = Field(default=None, max_length=300)
    price_range: str = Field(default="moderate", min_length=1, max_length=20)

    @field_validator("cuisine_types")
    @classmethod
    def clean_cuisines(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not cleaned:
            raise ValueError("at least one cuisine is required")
        return cleaned

    @field_validator("image_path")
    @classmethod
    def local_image_only(cls, value: str | None) -> str | None:
        if value and (not value.startswith("/static/images/") or ".." in value):
            raise ValueError("image_path must be a local static image")
        return value

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must both be populated or both be null")
        return self


class PartnerRestaurantCreate(PartnerRestaurantWrite):
    pass


class PartnerRestaurantUpdate(PartnerRestaurantWrite):
    pass


class RestaurantRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    cuisine_types: list[str]
    address: str
    city: str
    lat: Decimal | None = Field(validation_alias=AliasChoices("lat", "latitude"), ge=-90, le=90)
    lng: Decimal | None = Field(validation_alias=AliasChoices("lng", "longitude"), ge=-180, le=180)
    location_verified: bool
    coordinates_source_url: str | None
    coordinates_verified_at: datetime | None
    price_range: str
    halal_status: HalalStatus
    owner_id: uuid.UUID | None = None
    contact_phone: str | None = None
    halal_verification_status: HalalVerificationStatus = "unverified"
    opening_information: str | None = None
    available: bool = True
    image_path: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("lat", "lng", when_used="json")
    def serialize_coordinates(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None

    @model_validator(mode="after")
    def validate_location(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must both be populated or both be null")
        if self.location_verified and self.lat is None:
            raise ValueError("verified locations require coordinates")
        return self


class RestaurantPage(Page[RestaurantRead]):
    items: list[RestaurantRead] = Field(default_factory=list)
