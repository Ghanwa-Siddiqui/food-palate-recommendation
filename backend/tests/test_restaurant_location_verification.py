from copy import deepcopy
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.restaurant import Restaurant
from scripts.mark_restaurants_location_verified import (
    CORRECTION_CONFIRMATION,
    RESTAURANT_NAMES,
    authorize_correction,
    mark_location_verified,
)
from scripts.seed import SeedSafetyError

REMOTE_URL = "postgresql://postgres.projectref:secret@pooler.supabase.com:6543/postgres"


def _create_legacy_records(session: Session) -> None:
    for index, name in enumerate(RESTAURANT_NAMES):
        session.add(
            Restaurant(
                name=name,
                address=f"{index} Demo Street",
                city="Lahore",
                price_range="mid",
                halal_status="unknown",
                latitude=Decimal("31.5204") + Decimal(index) / Decimal(1000),
                longitude=Decimal("74.3587") + Decimal(index) / Decimal(1000),
                location_verified=False,
            )
        )
    session.commit()


def test_correction_updates_exact_records_and_is_idempotent(session: Session):
    _create_legacy_records(session)

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        status, count = mark_location_verified(correction_session)
    assert (status, count) == ("corrected", len(RESTAURANT_NAMES))

    session.expire_all()
    corrected = session.scalars(
        select(Restaurant).where(Restaurant.name.in_(RESTAURANT_NAMES))
    ).all()
    assert len(corrected) == len(RESTAURANT_NAMES)
    assert all(r.location_verified is True for r in corrected)
    assert all(r.coordinates_verified_at is not None for r in corrected)
    assert all(r.latitude is not None and r.longitude is not None for r in corrected)

    with Session(session.get_bind()) as correction_session, correction_session.begin():
        repeated = mark_location_verified(correction_session)
    assert repeated == ("already_corrected", 0)


def test_correction_rejects_missing_restaurant(session: Session):
    _create_legacy_records(session)
    missing = session.scalar(select(Restaurant).where(Restaurant.name == RESTAURANT_NAMES[0]))
    session.delete(missing)
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="restaurant count"):
            with correction_session.begin():
                mark_location_verified(correction_session)


def test_correction_rejects_restaurant_missing_coordinates(session: Session):
    _create_legacy_records(session)
    incomplete = session.scalar(select(Restaurant).where(Restaurant.name == RESTAURANT_NAMES[0]))
    incomplete.latitude = None
    incomplete.longitude = None
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="missing coordinates"):
            with correction_session.begin():
                mark_location_verified(correction_session)


def test_correction_rejects_mixed_verification_state(session: Session):
    _create_legacy_records(session)
    partially_done = session.scalar(
        select(Restaurant).where(Restaurant.name == RESTAURANT_NAMES[0])
    )
    partially_done.location_verified = True
    session.commit()

    with Session(session.get_bind()) as correction_session:
        with pytest.raises(SeedSafetyError, match="mixed verification state"):
            with correction_session.begin():
                mark_location_verified(correction_session)


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


def test_correction_accepts_exact_development_authorization():
    authorize_correction(**_authorization_values())
