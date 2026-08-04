from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class IncidentStatus(StrEnum):
    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    CREW_ASSIGNED = "crew_assigned"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    CLOSED = "closed"


class EvidenceClass(StrEnum):
    CONFIRMED_LIVE = "confirmed_live"
    CONFIRMED_DARK = "confirmed_dark"
    UNKNOWN_SILENT = "unknown_silent"
    UNINSTRUMENTED = "uninstrumented"
    DEVICE_SUSPECT = "device_suspect"


@dataclass(frozen=True, slots=True)
class SubstationAsset:
    id: UUID
    code: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class FeederAsset:
    id: UUID
    substation_id: UUID
    code: str


@dataclass(frozen=True, slots=True)
class TransformerAsset:
    id: UUID
    feeder_id: UUID
    code: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class PoleAsset:
    id: UUID
    transformer_id: UUID
    code: str
    latitude: float
    longitude: float
    pin_code: str | None
    parent_id: UUID | None
    branch_index: int
    seq_on_line: int | None


@dataclass(frozen=True, slots=True)
class DeviceAsset:
    id: UUID
    pole_id: UUID
    serial_number: str
    firmware: str
    battery_pct: float
    rssi_dbm: float
    is_online: bool
    heartbeat_interval_seconds: int
    next_heartbeat_offset_seconds: int | None


@dataclass(frozen=True, slots=True)
class BranchPolyline:
    transformer_id: UUID
    branch_index: int
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class GeneratedNetwork:
    substations: tuple[SubstationAsset, ...]
    feeders: tuple[FeederAsset, ...]
    transformers: tuple[TransformerAsset, ...]
    hidden_poles: tuple[PoleAsset, ...]
    exported_poles: tuple[PoleAsset, ...]
    devices: tuple[DeviceAsset, ...]
    branch_polylines: tuple[BranchPolyline, ...]
    masked_transformer_ids: tuple[UUID, ...]

    @property
    def poles(self) -> tuple[PoleAsset, ...]:
        return self.exported_poles

    @property
    def device_coverage(self) -> float:
        return len(self.devices) / len(self.exported_poles)

    @property
    def missing_topology_ratio(self) -> float:
        return len(self.masked_transformer_ids) / len(self.transformers)

    @property
    def offline_device_ratio(self) -> float:
        return sum(not device.is_online for device in self.devices) / len(self.devices)


@dataclass(frozen=True, slots=True)
class SeedSummary:
    substations: int
    feeders: int
    transformers: int
    poles: int
    devices: int
