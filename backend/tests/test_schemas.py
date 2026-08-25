import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.deal import DealRead
from app.schemas.dish import DishRead


def test_dish_schema_rejects_invalid_taste_and_price():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        DishRead(
            id=uuid.uuid4(),
            restaurant_id=uuid.uuid4(),
            name="Bad",
            description=None,
            cuisine="Test",
            ingredients=[],
            price=Decimal("-1"),
            spice_level=6,
            oiliness=0,
            sweetness=0,
            sourness=0,
            saltiness=0,
            smokiness=0,
            richness=0,
            texture_tags=[],
            dietary_tags=[],
            allergens=[],
            preparation_style="test",
            availability=True,
            created_at=now,
            updated_at=now,
        )


def test_deal_schema_rejects_inverted_date_range():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        DealRead(
            id=uuid.uuid4(),
            restaurant_id=uuid.uuid4(),
            title="Bad",
            description=None,
            discount_percentage=10,
            starts_at=now,
            ends_at=now - timedelta(days=1),
            is_active=True,
        )
