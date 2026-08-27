import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "json").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
VECTOR_DIM = int(
    os.getenv("VECTOR_DIM", "384")
)  # matches Ganva's contracts/v1 dish-vector.schema.json
EMA_ALPHA = float(os.getenv("EMA_ALPHA", "0.15"))
RANKING_API_BASE_URL = os.getenv(
    "RANKING_API_BASE_URL", "http://127.0.0.1:8001"
).rstrip("/")
RANKING_API_TIMEOUT_SECONDS = float(os.getenv("RANKING_API_TIMEOUT_SECONDS", "3"))
BACKEND_API_BASE_URL = os.getenv(
    "BACKEND_API_BASE_URL", "http://127.0.0.1:8000"
).rstrip("/")
BACKEND_API_TIMEOUT_SECONDS = float(os.getenv("BACKEND_API_TIMEOUT_SECONDS", "5"))
CHASKA_INTERNAL_API_KEY = os.getenv("CHASKA_INTERNAL_API_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", SUPABASE_KEY)
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
