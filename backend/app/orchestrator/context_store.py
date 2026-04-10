from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import TaskContext


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def load_task_context(task_id: str) -> dict[str, Any]:
    async with get_session_maker()() as session:
        row = (await session.execute(select(TaskContext).where(TaskContext.task_id == task_id))).scalars().first()
        if not row or not row.context_json:
            return {}
        try:
            return json.loads(row.context_json.decode("utf-8"))
        except Exception:
            return {}


async def save_task_context(task_id: str, data: dict[str, Any], schema_version: int = 1) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    async with get_session_maker()() as session:
        row = (await session.execute(select(TaskContext).where(TaskContext.task_id == task_id))).scalars().first()
        if not row:
            row = TaskContext(task_id=task_id, context_json=payload, schema_version=schema_version)
            session.add(row)
        else:
            row.context_json = payload
            row.schema_version = schema_version
        await session.commit()

