import json

import pytest
from pydantic import ValidationError

from app.core.constants import EMBEDDING_DIMENSION
from app.models.dish import Dish
from app.schemas.dish import DishVectorRead
from app.services.data_core.embeddings import (
    DeterministicFakeEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from scripts.seed import (
    REMOTE_DEVELOPMENT_CONFIRMATION,
    SeedSafetyError,
    assert_safe_seed_target,
    authorize_seed_target,
    extract_supabase_project_ref,
)
from tests.contract_validation import CONTRACTS


def test_embedding_dimension_is_consistent_across_all_layers():
    contract = json.loads((CONTRACTS / "dish-vector.schema.json").read_text(encoding="utf-8"))
    vector = contract["properties"]["vector"]

    assert EMBEDDING_DIMENSION == 384
    assert Dish.__table__.c.embedding.type.dim == EMBEDDING_DIMENSION
    assert SentenceTransformerEmbeddingProvider.dimension == EMBEDDING_DIMENSION
    assert DeterministicFakeEmbeddingProvider().dimension == EMBEDDING_DIMENSION
    assert vector["minItems"] == vector["maxItems"] == EMBEDDING_DIMENSION


def test_vector_schema_requires_exact_embedding_dimension():
    values = {"id": "00000000-0000-0000-0000-000000000001"}
    with pytest.raises(ValidationError):
        DishVectorRead(**values, vector=[0.0] * 383)
    with pytest.raises(ValidationError):
        DishVectorRead(**values, vector=[0.0] * 385)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://user:password@example.com/database",
        "postgresql+psycopg://user:password@db.example.supabase.co/database",
        "mysql://user:password@localhost/database",
    ],
)
def test_seed_safety_rejects_remote_or_unsupported_targets(database_url):
    with pytest.raises(SeedSafetyError):
        assert_safe_seed_target(database_url)


@pytest.mark.parametrize(
    "database_url",
    ["sqlite+pysqlite:///:memory:", "postgresql+psycopg://user:password@localhost/chaska"],
)
def test_seed_safety_allows_only_explicit_local_targets(database_url):
    assert_safe_seed_target(database_url)


REMOTE_URL = (
    "postgresql+psycopg://postgres.abcdefghijklmnopqrst:password@"
    "aws-0-region.pooler.supabase.com:6543/postgres?sslmode=require"
)
PROJECT_REF = "abcdefghijklmnopqrst"


def remote_authorization(**overrides):
    values = {
        "database_url": REMOTE_URL,
        "app_env": "development",
        "allow_remote_development": True,
        "remote_confirmation": REMOTE_DEVELOPMENT_CONFIRMATION,
        "expected_project_ref": PROJECT_REF,
        "with_embeddings": False,
    }
    values.update(overrides)
    return authorize_seed_target(**values)


def test_remote_seed_is_rejected_by_default():
    with pytest.raises(SeedSafetyError, match="disabled by default"):
        remote_authorization(allow_remote_development=False)


@pytest.mark.parametrize("app_env", ["production", "test", "staging"])
def test_remote_seed_requires_development_environment(app_env):
    with pytest.raises(SeedSafetyError, match="APP_ENV=development"):
        remote_authorization(app_env=app_env)


@pytest.mark.parametrize("confirmation", [None, "", "seed_chaska_development", "wrong"])
def test_remote_seed_requires_exact_confirmation(confirmation):
    with pytest.raises(SeedSafetyError, match="confirmation"):
        remote_authorization(remote_confirmation=confirmation)


def test_remote_seed_requires_expected_project_reference():
    with pytest.raises(SeedSafetyError, match="EXPECTED_SUPABASE_PROJECT_REF"):
        remote_authorization(expected_project_ref=None)
    with pytest.raises(SeedSafetyError, match="did not match"):
        remote_authorization(expected_project_ref="differentprojectref")


def test_remote_seed_rejects_non_supabase_target_even_with_all_flags():
    with pytest.raises(SeedSafetyError, match="Supabase PostgreSQL"):
        remote_authorization(
            database_url="postgresql+psycopg://postgres.projectref:password@example.com/db"
        )


def test_remote_seed_rejects_embedding_generation():
    with pytest.raises(SeedSafetyError, match="does not allow embedding"):
        remote_authorization(with_embeddings=True)


def test_remote_seed_authorization_accepts_exact_matching_development_target():
    assert remote_authorization() is True
    assert extract_supabase_project_ref(REMOTE_URL) == PROJECT_REF


def test_project_reference_can_be_verified_from_direct_supabase_host():
    direct_url = (
        "postgresql+psycopg://postgres:password@"
        f"db.{PROJECT_REF}.supabase.co:5432/postgres?sslmode=require"
    )

    assert extract_supabase_project_ref(direct_url) == PROJECT_REF
