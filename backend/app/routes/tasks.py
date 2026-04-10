from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import AgentTask, TaskCheckpoint, TaskStatus, User, UserRole
from app.orchestrator.runner import run_task
from app.redis_lock import acquire_lock
from app.security.deps import get_current_user

router = APIRouter(prefix="", tags=["tasks"])


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _ensure_task_access(task: AgentTask, current_user: User) -> None:
    # PRD IDOR baseline: task creator or admin only.
    if current_user.role == UserRole.ADMIN.value:
        return
    if str(task.user_id or "") != str(current_user.id):
        raise HTTPException(status_code=403, detail="No permission to resume this task")


async def _resume_task_impl(task_id: str) -> dict[str, Any]:
    # PRD: use Redis distributed lock (SETNX, TTL=60s) to avoid duplicate resume.
    lock_key = f"task:{task_id}:resume_lock"
    lock_ok = await acquire_lock(key=lock_key, value="1", ttl_s=60)
    if not lock_ok:
        raise HTTPException(status_code=409, detail="Resume already in progress")

    session_maker = get_session_maker()
    async with session_maker() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        current_status = str(task.status)
        if current_status == TaskStatus.RUNNING.value:
            return {"task_id": task_id, "status": TaskStatus.RUNNING.value}

        latest_checkpoint_stmt = (
            select(TaskCheckpoint)
            .where(TaskCheckpoint.task_id == task_id)
            .order_by(desc(TaskCheckpoint.step_index))
            .limit(1)
        )
        latest_checkpoint = (await session.execute(latest_checkpoint_stmt)).scalars().first()

        # Allow resume from WAITING_HUMAN and also recover from ERROR/CREATED
        # as long as caller provides the latest human input in later phases.
        task.status = TaskStatus.RUNNING.value
        if latest_checkpoint:
            task.current_step = latest_checkpoint.step_index

        await session.commit()

        resumed_from: Optional[dict[str, Any]] = None
        if latest_checkpoint:
            resumed_from = {
                "step_index": latest_checkpoint.step_index,
                "step_name": latest_checkpoint.step_name,
                "tool_name": latest_checkpoint.tool_name,
            }

        # Fire-and-forget orchestrator continuation (best-effort).
        asyncio.create_task(run_task(task_id))

        return {
            "task_id": task_id,
            "status": TaskStatus.RUNNING.value,
            "resumed_from": resumed_from,
        }


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Authorization: task owner or admin.
    session_maker = get_session_maker()
    async with session_maker() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        _ensure_task_access(task, current_user)

    return await _resume_task_impl(task_id)


@router.get("/tasks/{task_id}/status")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Fallback polling endpoint for client resilience when WS drops."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        _ensure_task_access(task, current_user)
        
        hil_data = {}
        if str(task.status) == TaskStatus.WAITING_HUMAN.value:
            from app.models import TaskHilState
            row = (
                await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))
            ).scalars().first()
            if row:
                hil_data = {"ui_component": row.ui_component, "reasoning_summary": row.reasoning_summary}

        return {
            "task_id": task_id,
            "status": str(task.status),
            "current_step": task.current_step,
            "max_steps": task.max_steps,
            "trace_id": task.trace_id,
            "ui_component": hil_data.get("ui_component"),
            "reasoning_summary": hil_data.get("reasoning_summary"),
        }

