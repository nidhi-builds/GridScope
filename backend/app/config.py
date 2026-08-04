from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://gridscope:gridscope@db:5432/gridscope"
    app_env: str = "development"
    log_level: str = "INFO"
    seed: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    worker_batch_size: int = 100
    poll_interval_ms: int = 3000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
