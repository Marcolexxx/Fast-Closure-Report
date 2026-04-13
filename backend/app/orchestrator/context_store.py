from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.db import get_session_maker
from app.models import TaskContext


async def load_task_context(task_id: str) -> dict[str, Any]:
    async with get_session_maker()() as session:
        row = (await session.execute(select(TaskContext).where(TaskContext.task_id == task_id))).scalars().first()
        if not row or not row.context_json:
            return {}
        try:
            data = json.loads(row.context_json.decode("utf-8"))
            data["_schema_version"] = row.schema_version
            return data
        except Exception:
            return {}


async def save_task_context(task_id: str, data: dict[str, Any], schema_version: int = 1) -> None:
    expected_version = data.pop("_schema_version", None)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    
    from app.db import get_session_maker
    async with get_session_maker()() as session:
        row = (await session.execute(select(TaskContext).where(TaskContext.task_id == task_id))).scalars().first()
        if not row:
            row = TaskContext(task_id=task_id, context_json=payload, schema_version=1)
            session.add(row)
        else:
            if expected_version is not None and row.schema_version != expected_version:
                raise RuntimeError(f"Optimistic lock failed: expected {expected_version}, got {row.schema_version}")
            row.context_json = payload
            row.schema_version += 1
        await session.commit()

