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
from app.db.models.telemetry import PoleEvidenceState
from app.detection.evidence import HEARTBEAT_TIMEOUT
from app.domain.types import SeedSummary
from app.simulator.generator import generate_network
from app.topology.importer import validate_registry_tree
from app.topology.inference import infer_tree

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


def _inferred_edge_rows(network, seed: int) -> list[dict]:
    pole_ids = {pole.id for pole in network.hidden_poles}
    hidden_by_id = {pole.id: pole for pole in network.hidden_poles}
    known_spans = [
        _distance_m(hidden_by_id[child.parent_id], child)
        for child in network.hidden_poles
        if child.parent_id in pole_ids and child.transformer_id not in network.masked_transformer_ids
    ]
    rows = []
    for transformer in network.transformers:
        if transformer.id not in network.masked_transformer_ids:
            continue
        poles = tuple(pole for pole in network.exported_poles if pole.transformer_id == transformer.id)
        for edge in infer_tree(transformer, poles, known_spans).edges:
            if edge.parent_id in pole_ids:
                rows.append({
                    "id": _id(seed, "inferred-edge", str(edge.child_id)),
                    "transformer_id": transformer.id,
                    "parent_pole_id": edge.parent_id,
                    "child_pole_id": edge.child_id,
                    "source": "inferred",
                    "version": 1,
                    "distance_m": edge.distance_m,
                    "ambiguity_score": edge.alternative_margin,
                    "calibration_bucket": edge.calibration_bucket,
                    "is_visible": True,
                })
    return rows


def _backfill_inferred_topology(session: Session, seed: int) -> None:
    """Upgrade only the deterministic demo seed created before inferred edges existed."""
    if session.scalar(select(TopologyEdge.id).where(TopologyEdge.source == "inferred")):
        return
    network = generate_network(seed)
    if session.get(Substation, network.substations[0].id) is None:
        return
    session.execute(insert(TopologyEdge), _inferred_edge_rows(network, seed))


def seed_if_empty(session: Session, seed: int) -> SeedSummary:
    if session.scalar(select(func.count()).select_from(Substation)):
        _backfill_inferred_topology(session, seed)
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
    masked_transformers = set(network.masked_transformer_ids)
    validations = {}
    for transformer in network.transformers:
        if transformer.id in masked_transformers:
            continue
        poles = tuple(pole for pole in network.exported_poles if pole.transformer_id == transformer.id)
        validations[transformer.id] = validate_registry_tree(
            poles,
            [(pole.parent_id, pole.id) for pole in poles if pole.parent_id is not None],
        )
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
        validation = validations.get(child.transformer_id)
        quarantined = validation is not None and not validation.valid
        visible = exported_by_id[child.id].parent_id is not None and not quarantined
        distance_m = _distance_m(hidden_by_id[child.parent_id], child)
        edges.append(
            {
                "id": _id(seed, "edge", str(child.id)),
                "transformer_id": child.transformer_id,
                "parent_pole_id": child.parent_id,
                "child_pole_id": child.id,
                "source": "registry" if visible else "hidden_truth",
                "version": 1,
                "distance_m": distance_m,
                "ambiguity_score": 0.0,
                "calibration_bucket": "registry_quarantined" if quarantined else "seeded-truth",
                "is_visible": visible,
            }
        )
    edges.extend(_inferred_edge_rows(network, seed))
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
    _seed_baseline_live(session, network, seed)
    session.flush()
    return _counts(session)


def _seed_baseline_live(session: Session, network, seed: int) -> None:
    """Record that every online device last reported energised.

    Without this the console opens on a grey map: no pole is green until it has
    actually reported, and nothing has reported on a fresh database. Grey is the
    honest answer, but it is indistinguishable from a broken map.

    This states the network's known starting condition — the grid was up before
    the demo began — rather than inventing a reading for a pole that has none.
    Offline devices and poles with no device are deliberately left alone: they
    stay `unknown_silent` and `uninstrumented` respectively, because the system
    genuinely does not know their state, and pretending otherwise would be the
    same error as treating silence as darkness.
    """
    if not get_settings().seed_baseline_live:
        return
    # Must be `now`, not the fixed seed date. The worker expires any live state
    # whose `fresh_until` has passed, so a baseline dated in the past would be
    # swept to `unknown_silent` on the worker's first pass three seconds later —
    # the map would flash green and immediately go grey again.
    observed_at = datetime.now(UTC)
    session.execute(
        insert(PoleEvidenceState),
        [
            {
                "id": _id(seed, "baseline-live", str(device.pole_id)),
                "pole_id": device.pole_id,
                "evidence_class": "confirmed_live",
                "source_event_id": None,
                "fresh_until": observed_at + HEARTBEAT_TIMEOUT,
                "device_health": "healthy",
                "evidence": {"origin": "seed_baseline", "observed_at": observed_at.isoformat()},
            }
            for device in network.devices if device.is_online
        ],
    )


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
