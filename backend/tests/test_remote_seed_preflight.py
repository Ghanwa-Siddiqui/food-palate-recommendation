import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.deal import Deal
from scripts.seed import SeedSafetyError, get_migration_head, verify_seed_preconditions
from tests.factories import dish, restaurant


def add_alembic_version(session, version: str | None = None) -> None:
    session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
        {"version": version or get_migration_head()},
    )
    session.commit()


def test_preflight_accepts_current_head_complete_empty_catalog(session):
    add_alembic_version(session)

    verify_seed_preconditions(session, require_empty_catalog=True)


def test_preflight_rejects_missing_alembic_version_table(session):
    with pytest.raises(SeedSafetyError, match="Alembic version table"):
        verify_seed_preconditions(session, require_empty_catalog=True)


def test_preflight_rejects_database_not_at_head(session):
    add_alembic_version(session, "old_revision")

    with pytest.raises(SeedSafetyError, match="not at the current Alembic head"):
        verify_seed_preconditions(session, require_empty_catalog=True)


def test_preflight_rejects_missing_owned_table(session):
    add_alembic_version(session)
    Deal.__table__.drop(session.get_bind())

    with pytest.raises(SeedSafetyError, match="required Chaska tables"):
        verify_seed_preconditions(session, require_empty_catalog=True)


@pytest.mark.parametrize("catalog_table", ["restaurants", "dishes", "deals"])
def test_remote_preflight_rejects_each_nonempty_catalog_table(session, catalog_table):
    add_alembic_version(session)
    if catalog_table == "restaurants":
        session.add(restaurant())
    elif catalog_table == "dishes":
        session.add(dish(uuid.uuid4()))
    else:
        now = datetime.now(UTC)
        session.add(
            Deal(
                restaurant_id=uuid.uuid4(),
                title="Existing",
                description=None,
                discount_percentage=Decimal("10"),
                starts_at=now,
                ends_at=now + timedelta(days=1),
                is_active=True,
            )
        )
    session.commit()

    with pytest.raises(SeedSafetyError, match="catalog tables must be empty"):
        verify_seed_preconditions(session, require_empty_catalog=True)
