"""FastAPI/Jinja entrypoint for the Namak web application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import SESSION_COOKIE_SECURE, SESSION_SECRET
from .routers import web
from .session import SignedSessionMiddleware

app = FastAPI(title="Namak", version="1.0.0")
app.add_middleware(
    SignedSessionMiddleware,
    secret_key=SESSION_SECRET,
    cookie_name="namak_session",
    max_age=60 * 60 * 24 * 7,
    https_only=SESSION_COOKIE_SECURE,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(web.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
