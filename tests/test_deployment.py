import json
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from api.index import app as vercel_app
from app import config
from app import main as ui_main


def _valid_production_config(monkeypatch) -> None:
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://project.example.test")
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "public-placeholder")
    monkeypatch.setattr(config, "SESSION_SECRET", "s" * 32)
    monkeypatch.setattr(config, "CHASKA_INTERNAL_API_KEY", "internal-placeholder")
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", True)


def test_vercel_asgi_health_and_static_assets():
    client = TestClient(vercel_app)
    assert client.get("/health").json() == {"status": "ok"}
    static = client.get("/static/favicon.svg")
    assert static.status_code == 200
    assert "image/svg+xml" in static.headers["content-type"]

    deployment = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    assert deployment["functions"]["api/index.py"]["includeFiles"] == "app/**"
    assert deployment["rewrites"][0]["destination"] == "/api/index"


def test_production_rejects_localhost_backend_and_missing_secrets(monkeypatch):
    _valid_production_config(monkeypatch)
    monkeypatch.setattr(config, "BACKEND_API_BASE_URL", "http://127.0.0.1:8000")
    with pytest.raises(RuntimeError, match="public HTTPS URL"):
        config.validate_production_config()

    monkeypatch.setattr(config, "BACKEND_API_BASE_URL", "https://api.example.test")
    monkeypatch.setattr(config, "SESSION_SECRET", "")
    with pytest.raises(RuntimeError, match="SESSION_SECRET") as error:
        config.validate_production_config()
    assert "public-placeholder" not in str(error.value)
    assert "internal-placeholder" not in str(error.value)


def test_production_session_cookie_is_secure_and_http_only(monkeypatch):
    monkeypatch.setattr(ui_main, "validate_production_config", lambda: None)
    monkeypatch.setattr(ui_main, "SESSION_SECRET", "s" * 32)
    monkeypatch.setattr(ui_main, "SESSION_COOKIE_SECURE", True)
    application = ui_main.create_app()

    @application.get("/_deployment/session")
    def set_session(request: Request):
        request.scope["session"]["deployment"] = "ok"
        return {"status": "ok"}

    response = TestClient(application).get("/_deployment/session")
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
