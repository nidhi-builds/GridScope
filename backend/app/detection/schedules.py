from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.detection.classification import FaultClassification


@dataclass(frozen=True)
class ScheduleDecision:
    status: str
    schedule_id: object | None = None
    confidence_reduced: bool = False


def match_schedule(classification: FaultClassification, schedules: Any, now: datetime) -> ScheduleDecision:
    """Schedules are soft evidence: only a current matching scope is planned."""
    snapshot = schedules if hasattr(schedules, "schedules") else None
    stale = bool(getattr(snapshot, "stale", False))
    for schedule in snapshot.schedules if snapshot else schedules:
        if not _scope_matches(classification, _value(schedule, "scope", {})):
            continue
        start, end = _value(schedule, "scheduled_start"), _value(schedule, "scheduled_end")
        if now < start:
            continue
        grace = timedelta(minutes=int(_value(schedule, "end_grace_minutes", 40)))
        if now <= end + grace:
            return ScheduleDecision("planned", _value(schedule, "id", _value(schedule, "external_id")), stale)
        return ScheduleDecision("overrun", _value(schedule, "id", _value(schedule, "external_id")), stale)
    return ScheduleDecision("unmatched")


def _scope_matches(classification: FaultClassification, scope: Any) -> bool:
    transformer_id = _value(scope, "transformer_id")
    feeder_id = _value(scope, "feeder_id")
    return (classification.kind == "dt" and transformer_id == classification.transformer_id) or (
        classification.kind == "feeder" and feeder_id == classification.feeder_id
    )


def _value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
