from sqlalchemy import func, select

from app.models.deal import Deal
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.user import User
from scripts.seed import ALLOWED_SEED_CUISINES, seed, stable_id


def test_seed_is_complete_and_idempotent(session):
    assert seed(session) == (30, 90, 30)
    assert seed(session) == (0, 0, 0)
    assert session.scalar(select(func.count()).select_from(Restaurant)) == 30
    assert session.scalar(select(func.count()).select_from(Dish)) == 90
    assert session.scalar(select(func.count()).select_from(Deal)) == 30
    assert session.scalar(select(func.count()).select_from(User)) == 0
    assert session.scalar(select(func.count()).select_from(Review)) == 0
    assert session.scalar(select(func.count()).select_from(Interaction)) == 0
    assert (
        session.scalar(select(func.count()).select_from(Dish).where(Dish.embedding.is_not(None)))
        == 0
    )


def test_seed_uses_only_authoritative_regional_cuisines(session):
    seed(session)

    restaurants = session.scalars(select(Restaurant)).all()
    dishes = session.scalars(select(Dish)).all()
    allowed = set(ALLOWED_SEED_CUISINES)

    assert allowed == {
        "Pakistani",
        "Chinese",
        "Italian",
        "Turkish",
        "Fast Food",
        "Continental",
    }
    assert "BBQ" not in allowed
    assert all(set(restaurant.cuisine_types) <= allowed for restaurant in restaurants)
    assert all("BBQ" not in restaurant.cuisine_types for restaurant in restaurants)
    assert all(dish.cuisine in allowed for dish in dishes)
    assert all(dish.cuisine != "BBQ" for dish in dishes)


def test_bbq_menu_records_use_pakistani_cuisine_and_preserve_ids(session):
    seed(session)

    expected_restaurant_names = {
        "Chaska Sample BBQ Kitchen 06",
        "Chaska Sample BBQ Kitchen 13",
        "Chaska Sample BBQ Kitchen 20",
        "Chaska Sample BBQ Kitchen 27",
    }
    restaurants = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(expected_restaurant_names))
    ).all()

    assert {restaurant.name for restaurant in restaurants} == expected_restaurant_names
    for restaurant in restaurants:
        assert restaurant.id == stable_id("restaurant", restaurant.name)
        assert restaurant.cuisine_types == ["Pakistani"]
        assert {dish.name for dish in restaurant.dishes} == {
            "Chicken Tikka",
            "Seekh Kebab",
            "Grilled Fish",
        }
        for dish in restaurant.dishes:
            assert dish.id == stable_id("dish", f"{restaurant.name}:{dish.name}")
            assert dish.cuisine == "Pakistani"
            assert dish.preparation_style == "BBQ"
            assert dish.smokiness == 3
