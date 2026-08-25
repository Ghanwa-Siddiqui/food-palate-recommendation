"""FastAPI entrypoint for the Personalization Engine.

Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routers import onboarding, user

app = FastAPI(
    title="Taste Engine — Personalization",
    version="0.1.0",
    description="User taste vectors, onboarding, interaction feedback loop.",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(onboarding.router)
app.include_router(user.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/onboarding")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
