from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://gridscope:gridscope@db:5432/gridscope"
    app_env: str = "development"
    log_level: str = "INFO"
    seed: bool = True
    # Give every online device a baseline "last reported energised" state at seed
    # time, so a fresh install opens on a live network instead of a grey one.
    # Off by default: it changes the starting evidence every detection test is
    # written against. Enabled in the deployed demo.
    seed_baseline_live: bool = False
    # Routine heartbeats from online devices, in seconds. Real devices report on
    # an interval; nothing else in this system generates that traffic, so without
    # it every pole sits at `unknown_silent`. 0 disables it, which is the default
    # for the test suites.
    heartbeat_sweep_seconds: int = 0
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    worker_batch_size: int = 100
    poll_interval_ms: int = 3000
    # Ingest concurrency. Sized so the application and a second process (test
    # runner, measurement container, psql session) can both hold a full pool
    # inside PostgreSQL's default max_connections of 100.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    request_thread_limit: int = 80

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Hosted PostgreSQL hands out postgres:// URLs; SQLAlchemy needs the driver."""
        for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
            if value.startswith(prefix):
                return value
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return f"postgresql+psycopg://{value[len(prefix):]}"
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
