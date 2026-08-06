import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.db.models.assets import Device, DeviceAssignment
from app.db.models.simulator import SimulatedFault
from app.db.models.telemetry import PoleEvidenceState
from app.detection.evidence import HEARTBEAT_TIMEOUT


def deenergized_poles(session: Session) -> set:
    """Poles a simulated fault has taken out and not yet repaired.

    A device with no power cannot send a heartbeat. This is the difference
    between a heartbeat generator and a lie: without it the sweep would keep
    reporting firmware-1.2 poles as live after they went dark, which is exactly
    the scenario the system is supposed to admit it cannot see.
    """
    out: set = set()
    for fault in session.scalars(select(SimulatedFault).where(SimulatedFault.repaired_at.is_(None))):
        out.update(fault.truth.get("deenergized", []) or [])
    return {str(pole_id) for pole_id in out}


def sweep_once(session: Session, now: datetime | None = None) -> int:
    """One round of routine heartbeats from every online, energised device.

    Only online devices report, so an offline device's pole correctly decays to
    `unknown_silent`. A pole that is confirmed dark is never overwritten here:
    darkness is cleared by a real `power_restored` event, not by the passage of
    time.
    """
    now = now or datetime.now(UTC)
    dark = deenergized_poles(session)
    rows = session.execute(
        select(DeviceAssignment.pole_id)
        .join(Device, Device.id == DeviceAssignment.device_id)
        .where(Device.is_online.is_(True), DeviceAssignment.effective_to.is_(None))
    ).all()
    reporting = [row.pole_id for row in rows if str(row.pole_id) not in dark]
    if not reporting:
        return 0

    statement = pg_insert(PoleEvidenceState).values([
        {
            "pole_id": pole_id,
            "evidence_class": "confirmed_live",
            "device_health": "healthy",
            "fresh_until": now + HEARTBEAT_TIMEOUT,
            "evidence": {"origin": "heartbeat_sweep", "observed_at": now.isoformat()},
        }
        for pole_id in reporting
    ])
    session.execute(statement.on_conflict_do_update(
        index_elements=[PoleEvidenceState.pole_id],
        set_={
            "evidence_class": "confirmed_live",
            "device_health": "healthy",
            "fresh_until": statement.excluded.fresh_until,
            "evidence": statement.excluded.evidence,
        },
        # Never resurrect a dark pole. Only a real restoration event may do that.
        where=PoleEvidenceState.evidence_class != "confirmed_dark",
    ))
    return len(reporting)


def _sweep() -> int:
    with SessionLocal.begin() as session:
        return sweep_once(session)


async def run_heartbeats(stop: asyncio.Event) -> None:
    """Routine telemetry, so the console opens on a live network.

    Real devices heartbeat on an interval; nothing in this system generated that
    traffic, so every pole sat at `unknown_silent` until a scenario touched it and
    any seeded live state expired after fifteen minutes. This closes the loop:
    live in steady state, dark during a fault, live again after repair.
    """
    settings = get_settings()
    if not settings.heartbeat_sweep_seconds:
        return
    interval = timedelta(seconds=settings.heartbeat_sweep_seconds).total_seconds()
    while not stop.is_set():
        try:
            await asyncio.to_thread(_sweep)
        except Exception:  # noqa: BLE001 - a demo heartbeat must never stop the app
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
