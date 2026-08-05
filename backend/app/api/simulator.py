from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.schemas import Page
from app.db import get_session
from app.db.models.incidents import Incident
from app.db.models.simulator import SimulatorRun
from app.db.models.telemetry import TelemetryEvent
from app.simulator.scenarios import SCENARIOS
from app.simulator.service import repair_run, reset_runs, start_run


router = APIRouter(prefix="/api/v1/simulator", tags=["simulator"])


class StartRun(BaseModel):
    scenario_key: str
    seed: int = 20260803
    overrides: dict = Field(default_factory=dict)


def _run(session: Session, run: SimulatorRun) -> dict:
    incident_ids = [str(value) for value in session.scalars(select(Incident.id).where(Incident.simulation_id == run.id).order_by(Incident.created_at))]
    return {"id": str(run.id), "scenario": run.scenario, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at, "truth": run.truth, "expected": run.expected_results, "actual": run.actual_results, "incident_ids": incident_ids}


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    return [{"key": item.key, "label": item.label, "expected_incident_count": item.expected_incident_count, "expected_classes": item.expected_classes, "boundary_kind": item.boundary_kind, "observability": item.observability} for item in SCENARIOS.values()]


@router.post("/runs", status_code=201)
def create_run(request: StartRun, session: Session = Depends(get_session)) -> dict:
    try:
        run = start_run(session, request.scenario_key, request.seed, request.overrides)
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _run(session, run)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, session: Session = Depends(get_session)) -> dict:
    run = session.get(SimulatorRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown simulator run")
    return _run(session, run)


@router.get("/runs/{run_id}/events", response_model=Page)
def run_events(
    run_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> Page:
    """Replay the run's own generated events with the delivery outcome ingest recorded."""
    run = session.get(SimulatorRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown simulator run")
    event_ids = [UUID(value) for value in run.truth.get("event_ids", ())]
    window = event_ids[(page - 1) * page_size:(page - 1) * page_size + page_size]
    rows = {event.id: event for event in session.scalars(select(TelemetryEvent).where(TelemetryEvent.id.in_(window)))} if window else {}
    items = [{
        "id": str(event.id), "device_id": str(event.device_id) if event.device_id else None,
        "pole_id": str(event.pole_id) if event.pole_id else None, "event_type": event.event_type,
        "device_time": event.device_time, "received_at": event.received_at,
        "processing_state": event.processing_state, "epoch_decision": event.epoch_decision,
    } for event in (rows[event_id] for event_id in window if event_id in rows)]
    return Page(items=items, page=page, page_size=page_size, total=len(event_ids))


@router.post("/runs/{run_id}/repair")
def repair(run_id: UUID, session: Session = Depends(get_session)) -> dict:
    try:
        result = repair_run(session, run_id)
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleDataError as error:
        # A concurrent reset removed the fault mid-repair. That is a vanished run,
        # not a server fault, so report it as one instead of a 500.
        session.rollback()
        raise HTTPException(status_code=404, detail="simulator run was reset during repair") from error
    return _run(session, result)


@router.post("/reset")
def reset(session: Session = Depends(get_session)) -> dict[str, str]:
    # The worker can commit a new ticket event for an incident between reset's
    # child delete and its parent delete, which fails the foreign key. The window
    # is small and the operation is idempotent, so a bounded retry clears it.
    for attempt in range(3):
        try:
            reset_runs(session)
            session.commit()
            return {"status": "cleared"}
        except IntegrityError:
            session.rollback()
            if attempt == 2:
                raise HTTPException(status_code=503, detail="simulator reset lost a race with the worker; retry") from None
    return {"status": "cleared"}
