from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    app_name: str = "Chaska API"
    app_env: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:password@localhost:5432/chaska",
        description="Supabase pooler-compatible SQLAlchemy connection URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 5
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    expected_supabase_project_ref: str | None = None
    internal_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CHASKA_INTERNAL_API_KEY", "INTERNAL_API_KEY"),
    )
    collaborative_min_similarity: float = Field(default=0.65, ge=0, le=1)
    collaborative_min_evidence: float = Field(default=0.45, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_settings(settings: Settings) -> None:
    """Reject incomplete production configuration without including secret values."""
    if settings.app_env.lower() != "production":
        return

    missing = []
    if not settings.internal_api_key:
        missing.append("CHASKA_INTERNAL_API_KEY")
    if not settings.expected_supabase_project_ref:
        missing.append("EXPECTED_SUPABASE_PROJECT_REF")
    if not settings.database_url or "localhost" in settings.database_url.lower():
        missing.append("DATABASE_URL")
    if missing:
        raise RuntimeError("Production backend configuration is incomplete: " + ", ".join(missing))
    if settings.embedding_dimension != 384:
        raise RuntimeError("EMBEDDING_DIMENSION must be 384")
