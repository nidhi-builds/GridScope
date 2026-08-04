import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.db.models.assets import Pole
from app.db.models.incidents import Incident


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
def seeded_incident(session):
    pole = session.scalar(select(Pole).order_by(Pole.code))
    incident = Incident(
        correlation_key=f"ai:{pole.id}", fault_class="span", status="detected", location_class="span",
        transformer_id=pole.transformer_id, pole_id=pole.id, pin_code=pole.pin_code or "estimated",
        pin_source="registry", affected_count=3, confidence="high", confidence_reasons=["direct dark evidence"],
        navigation_latitude=pole.latitude, navigation_longitude=pole.longitude,
    )
    session.add(incident)
    session.flush()
    return incident
