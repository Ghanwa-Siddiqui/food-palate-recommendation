import copy
import uuid

import pytest
from sqlalchemy import func, select

from app.models.deal import Deal
from app.models.dish import Dish
from app.models.restaurant import Restaurant
from app.models.user import User
from scripts.replace_sample_catalog import (
    CONFIRMATION,
    authorize_target,
    load_manifest,
    replace_catalog,
    validate_manifest,
    verify_exact_sample_state,
)
from scripts.seed import SeedSafetyError, seed

SUPABASE_URL = (
    "postgresql+psycopg://postgres.expectedref:secret@"
    "aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
)


def test_safe_target_verification_requires_every_guard():
    assert (
        authorize_target(
            database_url=SUPABASE_URL,
            app_env="development",
            confirmation=CONFIRMATION,
            expected_project_ref="expectedref",
        )
        == "expectedref"
    )
    cases = [
        {"app_env": "production", "confirmation": CONFIRMATION, "ref": "expectedref"},
        {"app_env": "development", "confirmation": "wrong", "ref": "expectedref"},
        {"app_env": "development", "confirmation": CONFIRMATION, "ref": None},
        {"app_env": "development", "confirmation": CONFIRMATION, "ref": "anotherref"},
    ]
    for case in cases:
        with pytest.raises(SeedSafetyError):
            authorize_target(
                database_url=SUPABASE_URL,
                app_env=case["app_env"],
                confirmation=case["confirmation"],
                expected_project_ref=case["ref"],
            )


def test_manifest_validation_and_source_mapping():
    restaurants, dishes, sources = load_manifest()
    validate_manifest(restaurants, dishes, sources)
    assert len(restaurants) == 30
    assert len(dishes) == 90
    assert sources["metadata"]["deals_count"] == 0
    broken = copy.deepcopy(sources)
    broken["dishes"].pop()
    with pytest.raises(SeedSafetyError, match="source mappings"):
        validate_manifest(restaurants, dishes, broken)


def test_exact_sample_state_preflight_and_unexpected_data_rejection(session):
    seed(session)
    verify_exact_sample_state(session)
    session.add(
        Restaurant(
            id=uuid.uuid4(),
            name="Unexpected",
            description=None,
            cuisine_types=["Pakistani"],
            address="Unexpected",
            city="Lahore",
            latitude=None,
            longitude=None,
            location_verified=False,
            price_range="budget",
            halal_status="unknown",
        )
    )
    session.commit()
    with pytest.raises(SeedSafetyError, match="exact deterministic sample restaurants"):
        verify_exact_sample_state(session)


def test_preflight_rejects_user_activity(session):
    seed(session)
    session.add(User(email="owner@example.test", name="Owner"))
    session.commit()
    with pytest.raises(SeedSafetyError, match="must be empty"):
        verify_exact_sample_state(session)


def test_replacement_rolls_back_on_error(session):
    seed(session)
    restaurants, dishes, _ = load_manifest()
    with pytest.raises(RuntimeError, match="injected"):
        replace_catalog(
            session, restaurants, dishes, verify_structure=False, fail_after_delete=True
        )
    session.rollback()
    assert session.scalar(select(func.count()).select_from(Restaurant)) == 30
    assert session.scalar(select(func.count()).select_from(Dish)) == 90
    assert session.scalar(select(func.count()).select_from(Deal)) == 30
    verify_exact_sample_state(session)


def test_replacement_final_state_and_repeat_run_idempotency(session):
    seed(session)
    restaurants, dishes, _ = load_manifest()
    assert replace_catalog(session, restaurants, dishes, verify_structure=False) == "replaced"
    session.commit()
    assert session.scalar(select(func.count()).select_from(Restaurant)) == 30
    assert session.scalar(select(func.count()).select_from(Dish)) == 90
    assert session.scalar(select(func.count()).select_from(Deal)) == 0
    relationships = dict(session.execute(select(Dish.id, Dish.restaurant_id)).all())
    assert set(relationships.values()) == {uuid.UUID(row["id"]) for row in restaurants}
    assert all(
        count == 3 for count in __import__("collections").Counter(relationships.values()).values()
    )
    before = set(relationships)
    assert (
        replace_catalog(session, restaurants, dishes, verify_structure=False) == "already_installed"
    )
    session.commit()
    assert set(session.scalars(select(Dish.id))) == before
