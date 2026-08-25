import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, Field, field_serializer, model_validator

from app.schemas.common import ORMModel, Page

HalalStatus = Literal["verified", "claimed", "not_halal", "unknown"]


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
