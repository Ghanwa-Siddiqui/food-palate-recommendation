import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_serializer, model_validator

from app.schemas.common import ORMModel, Page


class DealRead(ORMModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    title: str
    description: str | None
    discount_percentage: Decimal = Field(ge=0, le=100)
    starts_at: datetime
    ends_at: datetime
    is_active: bool

    @field_serializer("discount_percentage", when_used="json")
    def serialize_discount_percentage(self, value: Decimal) -> float:
        return float(value)

    @model_validator(mode="after")
    def validate_date_range(self) -> "DealRead":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class DealPage(Page[DealRead]):
    items: list[DealRead] = Field(default_factory=list)
