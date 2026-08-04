from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_is_live(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database(client):
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["database"] == "ready"


def test_settings_use_required_runtime_defaults():
    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.poll_interval_ms == 3000
