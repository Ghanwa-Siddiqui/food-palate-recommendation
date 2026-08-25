import uuid
from copy import deepcopy

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dish import Dish
from app.models.restaurant import Restaurant
from scripts.correct_bbq_cuisine import (
    BBQ_RESTAURANT_NAMES,
    CORRECTION_CONFIRMATION,
    authorize_correction,
    correct_bbq_cuisine,
)
from scripts.seed import SeedSafetyError, seed

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"


def _create_legacy_records(session: Session) -> None:
    seed(session)
    restaurants = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES))
    ).all()
    for restaurant in restaurants:
        restaurant.cuisine_types = ["BBQ"]
        for dish in restaurant.dishes:
            dish.cuisine = "BBQ"
            dish.preparation_style = "grilled"
    session.commit()


def test_correction_updates_exact_records_and_is_idempotent(session: Session):
    _create_legacy_records(session)
    dishes = session.scalars(
        select(Dish).join(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES))
    ).all()
    before = {dish.id: (dish.restaurant_id, dish.price) for dish in dishes}
    session.rollback()

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        result = correct_bbq_cuisine(correction_session)
    assert result.status == "corrected"
    assert (result.restaurants_updated, result.dishes_updated) == (4, 12)

    session.expire_all()
    corrected = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES))
    ).all()
    corrected_dishes = [dish for restaurant in corrected for dish in restaurant.dishes]
    assert all(restaurant.cuisine_types == ["Pakistani"] for restaurant in corrected)
    assert len(corrected_dishes) == 12
    assert all(dish.cuisine == "Pakistani" for dish in corrected_dishes)
    assert all(dish.preparation_style == "BBQ" for dish in corrected_dishes)
    assert all(dish.smokiness == 3 for dish in corrected_dishes)
    assert {dish.id: (dish.restaurant_id, dish.price) for dish in corrected_dishes} == before
    session.rollback()

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        repeated = correct_bbq_cuisine(correction_session)
    assert repeated.status == "already_corrected"
    assert (repeated.restaurants_updated, repeated.dishes_updated) == (0, 0)


@pytest.mark.parametrize("failure", ["missing_restaurant", "wrong_id", "missing_dish"])
def test_correction_aborts_when_identity_preflight_fails(session: Session, failure: str):
    _create_legacy_records(session)
    restaurant = session.scalar(
        select(Restaurant).where(Restaurant.name == BBQ_RESTAURANT_NAMES[0])
    )
    if failure == "missing_restaurant":
        session.delete(restaurant)
    elif failure == "wrong_id":
        restaurant.id = uuid.uuid4()
    else:
        session.delete(restaurant.dishes[0])
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError):
            with correction_session.begin():
                correct_bbq_cuisine(correction_session)

    unchanged = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES))
    ).all()
    assert all(restaurant.cuisine_types == ["BBQ"] for restaurant in unchanged)


def test_correction_rejects_partial_state_without_more_changes(session: Session):
    _create_legacy_records(session)
    restaurant = session.scalar(
        select(Restaurant).where(Restaurant.name == BBQ_RESTAURANT_NAMES[0])
    )
    restaurant.cuisine_types = ["Pakistani"]
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="unexpected or partial state"):
            with correction_session.begin():
                correct_bbq_cuisine(correction_session)

    remaining = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(BBQ_RESTAURANT_NAMES[1:]))
    ).all()
    assert all(restaurant.cuisine_types == ["BBQ"] for restaurant in remaining)


def _authorization_values():
    return {
        "database_url": REMOTE_URL,
        "app_env": "development",
        "confirmation": CORRECTION_CONFIRMATION,
        "expected_project_ref": "projectref",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "production"),
        ("confirmation", None),
        ("confirmation", "wrong"),
        ("expected_project_ref", None),
        ("expected_project_ref", "differentref"),
    ],
)
def test_correction_requires_every_authorization_gate(field: str, value: str | None):
    values = deepcopy(_authorization_values())
    values[field] = value
    with pytest.raises(SeedSafetyError):
        authorize_correction(**values)


def test_correction_rejects_non_supabase_database():
    values = _authorization_values()
    values["database_url"] = "postgresql://user:secret@localhost/chaska"
    with pytest.raises(SeedSafetyError, match="Supabase PostgreSQL"):
        authorize_correction(**values)


def test_correction_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
