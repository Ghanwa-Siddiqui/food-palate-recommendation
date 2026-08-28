"""FastAPI/Jinja entrypoint for the Namak web application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import SESSION_COOKIE_SECURE, SESSION_SECRET, validate_production_config
from .routers import web
from .session import SignedSessionMiddleware

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    validate_production_config()
    application = FastAPI(title="Namak", version="1.0.0")
    application.add_middleware(
        SignedSessionMiddleware,
        secret_key=SESSION_SECRET,
        cookie_name="namak_session",
        max_age=60 * 60 * 24 * 7,
        https_only=SESSION_COOKIE_SECURE,
    )
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    application.include_router(web.router)

    @application.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
