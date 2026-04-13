from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Core
    database_url: str = ""
    redis_url: str = "redis://redis:6379/0"
    file_storage_root: str = "/data/aicopilot"
    tz: str = "UTC"

    # Security (used in later phases)
    secret_key: str = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    access_token_expire_hours: int = 8
    refresh_token_expire_days: int = 30
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"]

    # Request tracing
    trace_header_name: str = "X-Trace-Id"

    # LLM adapter selection
    llm_adapter: str = "mock"
    llm_fallback: Optional[str] = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # FastAPI container already provides env vars via docker-compose.
    # `BaseSettings` will pull them from the environment.
    s = Settings()

    # If DATABASE_URL is not set via env, attempt to keep M0 defaults harmless.
    if not s.database_url:
        s.database_url = os.environ.get("DATABASE_URL", "")

    return s

