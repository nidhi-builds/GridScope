from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine, get_session
from app.db.models.assets import Pole
from app.db.models.incidents import Incident, IncidentBoundary, TicketEvent
from app.db.models.telemetry import PoleEvidenceState, TelemetryEvent
from app.main import app


@pytest.fixture
def session():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection) as session:
                yield session
        finally:
            transaction.rollback()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_incident(session):
    pole = session.scalar(select(Pole).order_by(Pole.code))
    now = datetime.now(UTC)
    event = TelemetryEvent(
        device_id=None, pole_id=pole.id, fingerprint=f"api-{now.timestamp()}", event_type="power_lost",
        payload={"energized": False}, device_time=now, received_at=now, processing_state="processed",
    )
    incident = Incident(
        correlation_key=f"api:{pole.id}", fault_class="span", status="detected", location_class="span",
        feeder_id=None,
        transformer_id=pole.transformer_id, pole_id=pole.id, pin_code=pole.pin_code or "estimated",
        pin_source="registry", affected_count=3, confidence="high", confidence_reasons=["direct dark evidence"],
        navigation_latitude=pole.latitude, navigation_longitude=pole.longitude,
    )
    session.add_all([event, incident])
    session.flush()
    session.add_all([
        IncidentBoundary(
            incident_id=incident.id, boundary_type="span", downstream_pole_id=pole.id,
            geometry={"pole_path": [str(pole.id)]},
        ),
        TicketEvent(
            incident_id=incident.id, event_type="detected", from_status=None, to_status="detected",
            actor="system", reason="evidence promoted", evidence_ids=[str(event.id)], occurred_at=now,
        ),
        PoleEvidenceState(
            pole_id=pole.id, evidence_class="confirmed_dark", source_event_id=event.id,
            fresh_until=now, device_health="healthy", evidence={},
        ),
    ])
    session.flush()
    return incident
