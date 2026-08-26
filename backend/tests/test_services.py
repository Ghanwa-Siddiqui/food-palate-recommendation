from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.services.data_core.catalog import DishService, NotFoundError


def test_dish_service_validates_price_range_before_query():
    repository = Mock()
    with pytest.raises(ValueError, match="min_price"):
        DishService(repository).list(
            restaurant_id=None,
            cuisine=None,
            name=None,
            min_price=Decimal("20"),
            max_price=Decimal("10"),
            limit=20,
            offset=0,
        )
    repository.list.assert_not_called()


def test_dish_service_reports_missing_item():
    repository = Mock()
    repository.get.return_value = None
    with pytest.raises(NotFoundError):
        DishService(repository).get("missing")
