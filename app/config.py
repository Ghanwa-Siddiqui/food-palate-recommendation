import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "json").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
VECTOR_DIM = int(os.getenv("VECTOR_DIM", "128"))
EMA_ALPHA = float(os.getenv("EMA_ALPHA", "0.15"))
