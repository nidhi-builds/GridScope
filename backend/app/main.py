from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import asyncio

from app.api.health import router as health_router
from app.api.telemetry import router as telemetry_router
from app.db import engine
from app.telemetry.worker import run_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = engine
    stop_worker = asyncio.Event()
    worker = asyncio.create_task(run_worker(stop_worker))
    try:
        yield
    finally:
        stop_worker.set()
        await worker
        engine.dispose()


app = FastAPI(title="GridScope", lifespan=lifespan)
app.include_router(health_router)
app.include_router(telemetry_router)

static_directory = Path("/app/static")
if static_directory.is_dir():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
