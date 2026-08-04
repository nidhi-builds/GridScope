from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceResult:
    level: str
    reasons: tuple[str, ...]


def score_confidence(facts: Any) -> ConfidenceResult:
    """Categorical confidence with stable, operator-readable reason codes."""
    source = _value(facts, "topology_source", "registry")
    validation = _value(facts, "topology_validation", "valid" if source == "registry" else "unknown")
    ambiguity = float(_value(facts, "topology_ambiguity", 0))
    exact = _value(facts, "boundary_kind") == "span"
    calibrated = source == "registry" or float(_value(facts, "calibration_precision", 0)) >= 0.90
    direct = int(_value(facts, "direct_dark_count", 0))
    live = bool(_value(facts, "post_onset_live", False))
    contradiction = bool(_value(facts, "contradiction", False))
    schedule = bool(_value(facts, "schedule_overlap", False))
    coverage = float(_value(facts, "downstream_coverage", 1))
    silent = int(_value(facts, "silent_count", 0))
    uncertainty = int(_value(facts, "unknown_count", 0)) + int(_value(facts, "offline_count", 0)) + int(_value(facts, "uninstrumented_count", 0))
    reasons = [f"topology:{source}", f"topology-validation:{validation}", f"topology-ambiguity:{ambiguity:.2f}", f"boundary:{'exact' if exact else 'degraded'}", f"direct-dark:{direct}", f"downstream-coverage:{coverage:.2f}"]
    if silent:
        reasons.append(f"silent:{silent}")
    if not live:
        reasons.append("no-post-onset-live")
    if uncertainty:
        reasons.append(f"unknown-or-offline:{uncertainty}")
    if contradiction:
        reasons.append("live-contradiction")
    if schedule:
        reasons.append("schedule-overlap")
    if exact and validation == "valid" and calibrated and direct >= 2 and live and coverage >= 0.60 and not contradiction and not schedule and not uncertainty and not silent:
        return ConfidenceResult("high", tuple(reasons))
    if contradiction or uncertainty > 1 or silent or coverage < 0.60 or not exact:
        return ConfidenceResult("low", tuple(reasons))
    return ConfidenceResult("medium", tuple(reasons))


def _value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
