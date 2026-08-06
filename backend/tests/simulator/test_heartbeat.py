from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.assets import Device, DeviceAssignment
from app.db.models.simulator import SimulatedFault, SimulatorRun
from app.db.models.telemetry import PoleEvidenceState
from app.simulator.heartbeat import deenergized_poles, sweep_once


def _online_pole(session):
    row = session.execute(
        select(DeviceAssignment.pole_id)
        .join(Device, Device.id == DeviceAssignment.device_id)
        .where(Device.is_online.is_(True), DeviceAssignment.effective_to.is_(None))
        .limit(1)
    ).one()
    return row.pole_id


def test_a_sweep_reports_online_devices_as_live(session):
    pole_id = _online_pole(session)

    assert sweep_once(session) > 0
    session.flush()

    state = session.scalars(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == pole_id)).one()
    assert state.evidence_class == "confirmed_live"
    assert state.evidence["origin"] == "heartbeat_sweep"


def test_a_sweep_never_resurrects_a_confirmed_dark_pole(session):
    """Darkness is cleared by a restoration event, never by the clock."""
    pole_id = _online_pole(session)
    session.add(PoleEvidenceState(pole_id=pole_id, evidence_class="confirmed_dark", device_health="healthy"))
    session.flush()

    sweep_once(session)
    session.flush()

    state = session.scalars(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == pole_id)).one()
    assert state.evidence_class == "confirmed_dark"


def test_a_de_energized_pole_never_sends_a_heartbeat(session):
    """A device with no power cannot report.

    Without this the sweep would keep publishing firmware-1.2 poles as live after
    they went dark and silent — turning the one scenario the system honestly
    admits it cannot observe into a false claim that everything is fine.
    """
    pole_id = _online_pole(session)
    now = datetime.now(UTC)
    run = SimulatorRun(seed=1, scenario="known_span", status="completed", started_at=now, truth={}, expected_results={}, actual_results={})
    session.add(run)
    session.flush()
    session.add(SimulatedFault(
        simulator_run_id=run.id, fault_class="span", target={}, occurred_at=now,
        repaired_at=None, truth={"deenergized": [str(pole_id)]},
    ))
    session.flush()

    assert str(pole_id) in deenergized_poles(session)

    sweep_once(session)
    session.flush()

    assert session.scalars(select(PoleEvidenceState).where(PoleEvidenceState.pole_id == pole_id)).one_or_none() is None
