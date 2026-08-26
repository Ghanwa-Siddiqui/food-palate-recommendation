"""Configuration values read from environment variables."""

import os

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "REVIEW_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
)
