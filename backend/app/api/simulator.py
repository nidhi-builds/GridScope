from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.db.models.simulator import SimulatorRun
from app.simulator.scenarios import SCENARIOS
from app.simulator.service import repair_run, reset_runs, start_run


router = APIRouter(prefix="/api/v1/simulator", tags=["simulator"])


class StartRun(BaseModel):
    scenario_key: str
    seed: int = 20260803
    overrides: dict = Field(default_factory=dict)


def _run(run: SimulatorRun) -> dict:
    return {"id": str(run.id), "scenario": run.scenario, "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at, "truth": run.truth, "expected": run.expected_results, "actual": run.actual_results}


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
    return _run(run)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, session: Session = Depends(get_session)) -> dict:
    run = session.get(SimulatorRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown simulator run")
    return _run(run)


@router.post("/runs/{run_id}/repair")
def repair(run_id: UUID, session: Session = Depends(get_session)) -> dict:
    try:
        result = repair_run(session, run_id)
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _run(result)


@router.post("/reset")
def reset(session: Session = Depends(get_session)) -> dict[str, str]:
    reset_runs(session)
    session.commit()
    return {"status": "cleared"}
