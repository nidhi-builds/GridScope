from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID


HEARTBEAT_TIMEOUT = timedelta(minutes=15)


@dataclass(frozen=True)
class PoleEvidence:
    pole_id: UUID
    device_id: UUID | None
    evidence_class: str
    device_health: str
    observed_at: datetime
    source_event_id: UUID | None = None
    fresh_until: datetime | None = None
    pre_fault_live_at: datetime | None = None


@dataclass(frozen=True)
class EvidenceDecision:
    evidence: PoleEvidence
    can_trigger_outage: bool

    @property
    def evidence_class(self) -> str:
        return self.evidence.evidence_class

    @property
    def pre_fault_live_at(self) -> datetime | None:
        return self.evidence.pre_fault_live_at


def apply_event(previous: PoleEvidence | None, event: Any, now: datetime) -> EvidenceDecision:
    """Convert one already-current stream event into electrical evidence."""
    event_type = _value(event, "event_type")
    energized = _value(event, "energized")
    observed_at = _value(event, "received_at")
    if event_type == "power_lost" and energized is False:
        evidence_class = "confirmed_dark"
        pre_fault_live_at = previous.observed_at if previous and previous.evidence_class == "confirmed_live" else (
            previous.pre_fault_live_at if previous else None
        )
    elif event_type in {"heartbeat", "boot", "power_restored"} and energized is True:
        evidence_class = "confirmed_live"
        pre_fault_live_at = observed_at
    else:
        return EvidenceDecision(previous, False) if previous else EvidenceDecision(
            PoleEvidence(_value(event, "pole_id"), _value(event, "device_id"), "unknown_silent", "healthy", now), False
        )
    evidence = PoleEvidence(
        pole_id=_value(event, "pole_id"),
        device_id=_value(event, "device_id"),
        evidence_class=evidence_class,
        device_health="healthy",
        observed_at=observed_at,
        source_event_id=_value(event, "id"),
        fresh_until=observed_at + HEARTBEAT_TIMEOUT,
        pre_fault_live_at=pre_fault_live_at,
    )
    return EvidenceDecision(evidence, evidence_class == "confirmed_dark" and now <= evidence.fresh_until)


def expire_heartbeat(previous: PoleEvidence, now: datetime) -> EvidenceDecision:
    """Silence only weakens known state; it never becomes direct dark evidence."""
    fresh_until = previous.fresh_until or previous.observed_at + HEARTBEAT_TIMEOUT
    if now <= fresh_until:
        return EvidenceDecision(previous, previous.evidence_class == "confirmed_dark")
    return EvidenceDecision(
        PoleEvidence(
            previous.pole_id,
            previous.device_id,
            "unknown_silent",
            "silent",
            previous.observed_at,
            previous.source_event_id,
            fresh_until,
            previous.observed_at if previous.evidence_class == "confirmed_live" else previous.pre_fault_live_at,
        ),
        False,
    )


def _value(event: Any, name: str) -> Any:
    value = getattr(event, name, None)
    if value is not None:
        return value
    payload = getattr(event, "payload", {})
    return payload.get(name) if isinstance(payload, dict) else None
