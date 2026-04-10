from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db import get_engine
from app.models import Base

logger = logging.getLogger(__name__)


async def init_task_schema(engine: AsyncEngine | None = None) -> None:
    # M1: For now we use `create_all` so the project is runnable without migrations.
    # Later phases will replace with Alembic migrations as per PRD.
    if engine is None:
        engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("task_schema_initialized")

