from datetime import UTC, datetime
from math import cos, hypot, radians
from pathlib import Path
from uuid import UUID, uuid5

from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import engine
from app.db.models.assets import Device, DeviceAssignment, Feeder, Pole, Substation, TopologyEdge, Transformer
from app.domain.types import SeedSummary
from app.simulator.generator import generate_network

_STARTUP_LOCK_ID = 724_202_608_03
_DEFAULT_SEED = 20260803
_NAMESPACE = UUID("7375372c-f178-44f2-b344-17b8f24df10c")


def _id(seed: int, kind: str, value: str) -> UUID:
    return uuid5(_NAMESPACE, f"{seed}:{kind}:{value}")


def _counts(session: Session) -> SeedSummary:
    return SeedSummary(
        *(session.scalar(select(func.count()).select_from(model)) or 0 for model in (
            Substation,
            Feeder,
            Transformer,
            Pole,
            Device,
        ))
    )


def _distance_m(parent, child) -> float:
    latitude_m = (child.latitude - parent.latitude) * 111_320
    longitude_m = (
        (child.longitude - parent.longitude)
        * 111_320
        * cos(radians((child.latitude + parent.latitude) / 2))
    )
    return round(hypot(latitude_m, longitude_m), 2)


def _alembic_config_path() -> Path:
    for candidate in (
        Path.cwd() / "backend" / "alembic.ini",
        Path.cwd() / "alembic.ini",
        Path(__file__).resolve().parents[1] / "alembic.ini",
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("alembic.ini not found")


def seed_if_empty(session: Session, seed: int) -> SeedSummary:
    if session.scalar(select(func.count()).select_from(Substation)):
        return _counts(session)

    network = generate_network(seed)
    session.execute(
        insert(Substation),
        [
            {"id": item.id, "code": item.code, "latitude": item.latitude, "longitude": item.longitude}
            for item in network.substations
        ],
    )
    session.execute(
        insert(Feeder),
        [{"id": item.id, "substation_id": item.substation_id, "code": item.code} for item in network.feeders],
    )
    session.execute(
        insert(Transformer),
        [
            {
                "id": item.id,
                "feeder_id": item.feeder_id,
                "code": item.code,
                "latitude": item.latitude,
                "longitude": item.longitude,
            }
            for item in network.transformers
        ],
    )

    pole_ids = {pole.id for pole in network.hidden_poles}
    exported_by_id = {pole.id: pole for pole in network.exported_poles}
    hidden_by_id = {pole.id: pole for pole in network.hidden_poles}
    session.execute(
        insert(Pole),
        [
            {
                "id": pole.id,
                "transformer_id": pole.transformer_id,
                "code": pole.code,
                "latitude": pole.latitude,
                "longitude": pole.longitude,
                "pin_code": pole.pin_code,
                "parent_pole_id": pole.parent_id if pole.parent_id in pole_ids else None,
                "branch_index": pole.branch_index,
                "seq_on_line": pole.seq_on_line,
            }
            for pole in network.exported_poles
        ],
    )
    edges = []
    for child in network.hidden_poles:
        if child.parent_id not in pole_ids:
            continue
        visible = exported_by_id[child.id].parent_id is not None
        edges.append(
            {
                "id": _id(seed, "edge", str(child.id)),
                "transformer_id": child.transformer_id,
                "parent_pole_id": child.parent_id,
                "child_pole_id": child.id,
                "source": "registry" if visible else "hidden_truth",
                "version": 1,
                "distance_m": _distance_m(hidden_by_id[child.parent_id], child),
                "ambiguity_score": 0.0,
                "calibration_bucket": "seeded-truth",
                "is_visible": visible,
            }
        )
    session.execute(insert(TopologyEdge), edges)

    session.execute(
        insert(Device),
        [
            {
                "id": device.id,
                "serial_number": device.serial_number,
                "firmware": device.firmware,
                "battery_pct": device.battery_pct,
                "rssi_dbm": device.rssi_dbm,
                "is_online": device.is_online,
                "heartbeat_interval_seconds": device.heartbeat_interval_seconds,
                "next_heartbeat_offset_seconds": device.next_heartbeat_offset_seconds,
            }
            for device in network.devices
        ],
    )
    effective_from = datetime(2026, 8, 3, tzinfo=UTC)
    session.execute(
        insert(DeviceAssignment),
        [
            {
                "id": _id(seed, "assignment", str(device.id)),
                "device_id": device.id,
                "pole_id": device.pole_id,
                "effective_from": effective_from,
                "effective_to": None,
            }
            for device in network.devices
        ],
    )
    session.flush()
    return _counts(session)


def migrate_and_seed() -> SeedSummary | None:
    settings = get_settings()
    with engine.connect() as connection:
        connection.execute(text("select pg_advisory_lock(:lock_id)"), {"lock_id": _STARTUP_LOCK_ID})
        connection.commit()
        try:
            alembic_config = Config(str(_alembic_config_path()))
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")
            connection.commit()
            if not settings.seed:
                return None
            with Session(bind=connection) as session:
                summary = seed_if_empty(session, _DEFAULT_SEED)
                session.commit()
                return summary
        finally:
            connection.execute(text("select pg_advisory_unlock(:lock_id)"), {"lock_id": _STARTUP_LOCK_ID})
            connection.commit()


if __name__ == "__main__":
    summary = migrate_and_seed()
    print(f"GridScope database ready: {summary}")
