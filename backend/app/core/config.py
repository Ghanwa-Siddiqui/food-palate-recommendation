from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Chaska API"
    app_env: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:password@localhost:5432/chaska",
        description="Supabase pooler-compatible SQLAlchemy connection URL",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 5
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    expected_supabase_project_ref: str | None = None
    internal_api_key: str | None = None
    collaborative_min_similarity: float = Field(default=0.65, ge=0, le=1)
    collaborative_min_evidence: float = Field(default=0.45, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
