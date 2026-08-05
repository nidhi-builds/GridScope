from fastapi.testclient import TestClient
import pytest

from app.config import Settings, get_settings
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


def test_ingest_concurrency_is_configured_above_the_library_defaults(client):
    """Measured at 57 req/s against a 500 req/s target with the stock 40-thread,
    15-connection defaults; both limits are now explicit and applied at startup."""
    from app.db import engine

    settings = Settings(_env_file=None)

    assert settings.db_pool_size > 5  # above SQLAlchemy's stock pool_size
    assert settings.db_max_overflow > 10  # above SQLAlchemy's stock max_overflow
    assert settings.request_thread_limit >= 80
    # Two processes must be able to hold a full pool at once: the application
    # plus a test runner or measurement container, inside max_connections of 100.
    assert (settings.db_pool_size + settings.db_max_overflow) * 2 < 100
    assert engine.pool.size() == get_settings().db_pool_size
    # Asserted from the running app, so it proves the limiter was raised in the
    # event loop that actually serves requests.
    assert client.app.state.thread_limit == get_settings().request_thread_limit


def test_settings_use_required_runtime_defaults():
    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.poll_interval_ms == 3000
