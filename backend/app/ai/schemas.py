from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class IncidentExplanationFacts:
    incident_id: str
    fault_class: str
    location_class: str
    affected_count: int
    confidence: str
    status: str
    asset_ids: tuple[str, ...]
    boundary_ids: tuple[str, ...]
    confidence_reasons: tuple[str, ...]
    unknowns: tuple[str, ...]
    navigation: tuple[float, float]
    pin_code: str

    @property
    def protected(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "fault_class": self.fault_class,
            "location_class": self.location_class,
            "affected_count": self.affected_count,
            "confidence": self.confidence,
            "status": self.status,
            "asset_ids": list(self.asset_ids),
            "boundary_ids": list(self.boundary_ids),
            "navigation": list(self.navigation),
        }


@dataclass(frozen=True)
class Explanation:
    english: str
    kannada: str

    def as_dict(self) -> dict[str, str]:
        return {"english": self.english, "kannada": self.kannada}


@dataclass(frozen=True)
class ExplanationResult:
    explanation: Explanation
    used_fallback: bool
    model: str | None
    usage: dict[str, int]
    latency_ms: int
    fallback_reason: str | None = None


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    english: str = Field(min_length=1, max_length=600)
    kannada: str = Field(min_length=1, max_length=600)
    protected: dict[str, Any]
    usage: dict[str, int] = Field(default_factory=dict)
