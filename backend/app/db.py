from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    # Keep engine global for reuse across requests/tools.
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )


async def test_db_connection(timeout_s: float = 2.0) -> tuple[bool, Optional[str]]:
    settings = get_settings()
    if not settings.database_url:
        return False, "DATABASE_URL is empty"

    engine: Optional[AsyncEngine] = None
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=timeout_s)
        return True, None
    except Exception as e:
        return False, str(e)

