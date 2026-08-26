from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.interaction import Interaction
from app.models.user import User
from tests.factories import dish, restaurant


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91, 0), (-91, 0), (0, 181), (0, -181)],
)
def test_database_rejects_out_of_range_coordinates(session, latitude, longitude):
    session.add(restaurant(latitude=latitude, longitude=longitude))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_accepts_missing_coordinate_pair(session):
    item = restaurant(latitude=None, longitude=None, location_verified=False)
    session.add(item)
    session.commit()
    assert item.latitude is None and item.longitude is None


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(None, Decimal("67.0")), (Decimal("24.0"), None)],
)
def test_database_rejects_partial_coordinate_pair(session, latitude, longitude):
    session.add(restaurant(latitude=latitude, longitude=longitude, location_verified=False))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_verified_location_without_coordinates(session):
    session.add(restaurant(latitude=None, longitude=None, location_verified=True))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_invalid_halal_status(session):
    session.add(restaurant(halal_status="halal"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_invalid_interaction_action(session):
    user = User(name="Test User", email="action@example.test")
    owner = restaurant()
    session.add_all([user, owner])
    session.flush()
    menu_item = dish(owner.id)
    session.add(menu_item)
    session.flush()
    session.add(Interaction(user_id=user.id, dish_id=menu_item.id, action="view"))

    with pytest.raises(IntegrityError):
        session.commit()
