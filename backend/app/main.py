from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = engine
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="GridScope", lifespan=lifespan)
app.include_router(health_router)

static_directory = Path("/app/static")
if static_directory.is_dir():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
