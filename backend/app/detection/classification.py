from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from typing import Any

from app.detection.localization import BoundaryResult


@dataclass(frozen=True)
class FaultClassification:
    kind: str
    boundaries: tuple[BoundaryResult, ...] = ()
    transformer_id: object | None = None
    feeder_id: object | None = None
    reason: str | None = None


def classify(boundaries: list[BoundaryResult], coverage: Any) -> FaultClassification:
    """Classify only topology-supported scope; separate branches stay separate."""
    if _value(coverage, "device_issue", False):
        return FaultClassification("device_issue", tuple(boundaries), reason="live_descendant_or_isolated")
    feeder_dts = _value(coverage, "feeder_dts", {})
    for feeder_id, data in feeder_dts.items():
        qualifying = set(_value(data, "qualifying", ()))
        total = int(_value(data, "total", 0))
        if len(qualifying) >= max(2, ceil(total * 0.60)):
            return FaultClassification("feeder", tuple(boundaries), feeder_id=feeder_id, reason="dt_quorum")
    branches = _value(coverage, "dt_branches", {})
    for transformer_id, data in branches.items():
        dark, observable = set(_value(data, "dark", ())), set(_value(data, "observable", ()))
        live = set(_value(data, "live", ()))
        minimum = int(_value(data, "minimum_branches", _value(coverage, "minimum_branches", 2)))
        threshold = float(_value(data, "coverage_threshold", _value(coverage, "dt_coverage_threshold", 0.60)))
        required = max(minimum, ceil(len(observable) * threshold))
        if len(observable) >= minimum and not live and len(dark & observable) >= required:
            boundary = next((item for item in boundaries if item.transformer_id == transformer_id), None)
            return FaultClassification("dt", tuple(boundaries), transformer_id, boundary.feeder_id if boundary else None, "branch_coverage")
    if not boundaries:
        return FaultClassification("ambiguous", reason="no_supported_boundary")
    first = boundaries[0]
    return FaultClassification(first.kind, tuple(boundaries), first.transformer_id, first.feeder_id)


def _value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
