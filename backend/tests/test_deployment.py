import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, validate_production_settings
from app.main import app as railway_app
from app.main import create_app


def _production_settings(**updates) -> Settings:
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://user:placeholder@db.example.test/chaska",
        "internal_api_key": "internal-placeholder",
        "expected_supabase_project_ref": "project-placeholder",
        "embedding_dimension": 384,
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def test_railway_asgi_health_and_start_command():
    assert TestClient(railway_app).get("/health").json() == {"status": "ok"}
    deployment = json.loads(
        (Path(__file__).resolve().parents[1] / "railway.json").read_text(encoding="utf-8")
    )
    assert deployment["deploy"]["startCommand"] == (
        "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    )
    assert deployment["deploy"]["healthcheckPath"] == "/health"


def test_production_configuration_requires_secrets_without_exposing_values():
    settings = _production_settings(internal_api_key=None)
    with pytest.raises(RuntimeError, match="CHASKA_INTERNAL_API_KEY") as error:
        validate_production_settings(settings)
    assert "placeholder@db" not in str(error.value)


def test_required_internal_key_uses_documented_environment_name(monkeypatch):
    monkeypatch.setenv("CHASKA_INTERNAL_API_KEY", "documented-placeholder")
    assert Settings(_env_file=None).internal_api_key == "documented-placeholder"


def test_production_backend_requires_shared_key_but_keeps_health_public(monkeypatch):
    settings = _production_settings()
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    application = create_app()
    client = TestClient(application)

    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 401
    assert (
        client.get(
            "/openapi.json",
            headers={"X-Chaska-Internal-Key": "internal-placeholder"},
        ).status_code
        == 200
    )
