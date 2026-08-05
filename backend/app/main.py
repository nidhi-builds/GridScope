from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

import asyncio

from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.network import router as network_router
from app.api.operations import router as operations_router
from app.api.simulator import router as simulator_router
from app.api.telemetry import router as telemetry_router
from app.db import engine
from app.schedules.feed import DatabaseScheduleFeed, ScheduleCache, poll_schedule_feed
from app.telemetry.worker import run_worker


class SpaStaticFiles(StaticFiles):
    """Serve the built SPA for browser routes without masking missing API paths."""

    async def get_response(self, path: str, scope: dict):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code == 404 and path != "api" and not path.startswith("api/") and "." not in Path(path).name:
                return await super().get_response("index.html", scope)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = engine
    stop_worker = asyncio.Event()
    stop_schedules = asyncio.Event()
    app.state.schedule_cache = ScheduleCache()
    worker = asyncio.create_task(run_worker(stop_worker, app.state.schedule_cache))
    app.state.worker = worker
    schedules = asyncio.create_task(poll_schedule_feed(DatabaseScheduleFeed(), app.state.schedule_cache, stop_schedules))
    try:
        yield
    finally:
        stop_worker.set()
        stop_schedules.set()
        await worker
        await schedules
        engine.dispose()


app = FastAPI(title="GridScope", lifespan=lifespan)
app.include_router(health_router)
app.include_router(telemetry_router)
app.include_router(incidents_router)
app.include_router(network_router)
app.include_router(operations_router)
app.include_router(simulator_router)

static_directory = Path("/app/static")
if static_directory.is_dir():
    app.mount("/", SpaStaticFiles(directory=static_directory, html=True), name="frontend")
