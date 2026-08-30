import os
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent

APP_ENV = os.getenv("APP_ENV", "development").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
VECTOR_DIM = int(
    os.getenv("VECTOR_DIM", "384")
)  # matches Ganva's contracts/v1 dish-vector.schema.json
EMA_ALPHA = float(os.getenv("EMA_ALPHA", "0.15"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
BACKEND_API_BASE_URL = os.getenv(
    "BACKEND_API_BASE_URL", "http://127.0.0.1:8000"
).rstrip("/")
BACKEND_API_TIMEOUT_SECONDS = float(os.getenv("BACKEND_API_TIMEOUT_SECONDS", "5"))
CHASKA_INTERNAL_API_KEY = os.getenv("CHASKA_INTERNAL_API_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", SUPABASE_KEY)
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"


def validate_production_config() -> None:
    """Fail closed on unsafe production UI configuration without exposing values."""
    if APP_ENV != "production":
        return

    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_PUBLISHABLE_KEY:
        missing.append("SUPABASE_PUBLISHABLE_KEY")
    if len(SESSION_SECRET) < 32:
        missing.append("SESSION_SECRET")
    if not CHASKA_INTERNAL_API_KEY:
        missing.append("CHASKA_INTERNAL_API_KEY")
    if missing:
        raise RuntimeError(
            "Production UI configuration is incomplete: " + ", ".join(missing)
        )

    backend_url = urlparse(BACKEND_API_BASE_URL)
    if (
        backend_url.scheme != "https"
        or not backend_url.hostname
        or backend_url.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise RuntimeError(
            "BACKEND_API_BASE_URL must be a public HTTPS URL in production"
        )
    if not SESSION_COOKIE_SECURE:
        raise RuntimeError("SESSION_COOKIE_SECURE must be true in production")
