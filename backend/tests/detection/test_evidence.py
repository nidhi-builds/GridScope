from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.detection.evidence import PoleEvidence, apply_event, expire_heartbeat


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Event:
    pole_id: object
    device_id: object
    event_type: str
    energized: bool
    received_at: datetime
    id: object


def test_silence_never_becomes_dark():
    # Break caught: a missed heartbeat creates electrical outage evidence.
    live = PoleEvidence(uuid4(), uuid4(), "confirmed_live", "healthy", NOW, uuid4())

    result = expire_heartbeat(live, now=NOW + timedelta(minutes=16))

    assert result.evidence_class == "unknown_silent"
    assert result.can_trigger_outage is False
    assert result.pre_fault_live_at == NOW


def test_current_power_lost_creates_direct_dark_with_provenance():
    # Break caught: electrical evidence is confused with device-stream health.
    event = Event(uuid4(), uuid4(), "power_lost", False, NOW, uuid4())

    result = apply_event(None, event, now=NOW)

    assert result.evidence.evidence_class == "confirmed_dark"
    assert result.evidence.source_event_id == event.id
    assert result.evidence.device_id == event.device_id
    assert result.can_trigger_outage is True
