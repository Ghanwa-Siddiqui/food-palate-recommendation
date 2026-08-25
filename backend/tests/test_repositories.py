from decimal import Decimal

from app.repositories.dishes import DishRepository
from app.repositories.restaurants import RestaurantRepository
from tests.factories import dish, restaurant


def test_restaurant_repository_filters_and_paginates(session):
    session.add_all(
        [
            restaurant(name="A", city="Karachi", halal_status="claimed"),
            restaurant(name="B", city="Lahore", halal_status="unknown"),
            restaurant(name="C", city="Karachi", halal_status="claimed"),
        ]
    )
    session.commit()
    items, total = RestaurantRepository(session).list(
        city="karachi", cuisine="pakistani", halal_status="claimed", limit=1, offset=1
    )
    assert total == 2
    assert len(items) == 1
    assert items[0].name == "C"


def test_dish_repository_combines_filters(session):
    owner = restaurant()
    other = restaurant(name="Other")
    session.add_all([owner, other])
    session.flush()
    session.add_all(
        [
            dish(owner.id, name="Chicken Karahi", price=Decimal("900")),
            dish(owner.id, name="Beef Karahi", price=Decimal("1200")),
            dish(other.id, name="Chicken Karahi", price=Decimal("900")),
        ]
    )
    session.commit()
    items, total = DishRepository(session).list(
        restaurant_id=owner.id,
        cuisine="Pakistani",
        name="chicken",
        min_price=Decimal("800"),
        max_price=Decimal("1000"),
        limit=20,
        offset=0,
    )
    assert total == 1
    assert [item.name for item in items] == ["Chicken Karahi"]
