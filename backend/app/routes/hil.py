from __future__ import annotations

import json
import logging
import asyncio
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine, get_session_maker
from app.models import AgentTask, FeedbackEvent, TaskHilState, TaskStatus, User, UserRole
from app.orchestrator.context_store import load_task_context, save_task_context
from app.routes.tasks import _resume_task_impl
from app.security.deps import get_current_user

router = APIRouter(prefix="/tasks", tags=["hil"])
logger = logging.getLogger(__name__)


async def _auto_resume(task_id: str) -> None:
    try:
        await _resume_task_impl(task_id)
    except Exception:
        logger.exception("auto_resume_failed", extra={"task_id": task_id})


class HilSetRequest(BaseModel):
    ui_component: str
    reasoning_summary: str = ""
    prefill: dict[str, Any] = {}


class HilSubmitRequest(BaseModel):
    ui_component: str
    data: dict[str, Any] = {}


def _ensure_task_access(task: AgentTask, current_user: User) -> None:
    # PRD IDOR baseline for HIL endpoints: task owner or admin.
    if current_user.role == UserRole.ADMIN.value:
        return
    if str(task.user_id or "") != str(current_user.id):
        raise HTTPException(status_code=403, detail="No permission to access this task")


@router.post("/{task_id}/hil/set")
async def hil_set(
    task_id: str,
    body: HilSetRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with get_session_maker()() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        _ensure_task_access(task, current_user)

        row = (await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))).scalars().first()
        if not row:
            row = TaskHilState(task_id=task_id)
            session.add(row)

        row.ui_component = body.ui_component
        row.reasoning_summary = body.reasoning_summary
        row.prefill_json = json.dumps(body.prefill, ensure_ascii=False).encode("utf-8")

        task.status = TaskStatus.WAITING_HUMAN.value
        await session.commit()

        return {"ok": True, "task_id": task_id, "status": task.status, "ui_component": row.ui_component}


@router.post("/{task_id}/hil/submit")
async def hil_submit(
    task_id: str,
    body: HilSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.redis_lock import acquire_lock, release_lock
    lock_key = f"task:{task_id}:hil_submit_lock"
    lock_ok = await acquire_lock(key=lock_key, value="1", ttl_s=10)
    if not lock_ok:
        raise HTTPException(status_code=409, detail="HIL submit already in progress")

    try:
        async with get_session_maker()() as session:
            task = await session.get(AgentTask, task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            _ensure_task_access(task, current_user)

            if task.status != TaskStatus.WAITING_HUMAN.value:
                raise HTTPException(status_code=409, detail=f"Task is not waiting for human (status={task.status})")

            row = (await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))).scalars().first()
            if not row:
                raise HTTPException(status_code=409, detail="HIL state not set")

            row.submit_json = json.dumps(body.data, ensure_ascii=False).encode("utf-8")
            # Resume task after human submit (Orchestrator will pick it up later).
            task.status = TaskStatus.RUNNING.value
            await session.commit()

        # Merge human input into TaskContext (P-2: use keyed update, not append).
        ctx = await load_task_context(task_id)
        hil_bucket = ctx.get("hil") if isinstance(ctx.get("hil"), dict) else {}
        hil_bucket[body.ui_component] = body.data or {}
        ctx["hil"] = hil_bucket
        await save_task_context(task_id, ctx)

        # --- Experience Layer: record correction and dispatch Librarian distillation ---
        try:
            async with get_session_maker()() as fe_session:
                skill_id = task.skill_id or "unknown"
                ev = FeedbackEvent(
                    task_id=task_id,
                    skill_id=skill_id,
                    event_type="hil_correction",
                    payload_json=json.dumps(body.data, ensure_ascii=False).encode("utf-8"),
                    user_id=str(current_user.id),
                )
                fe_session.add(ev)
                await fe_session.commit()

                # Fire-and-forget: distill the HIL correction into LibrarianKnowledge
                from app.celery_app import celery_app as _celery_app
                _celery_app.send_task("extract_librarian_experience_task", args=[ev.id])
        except Exception:
            logger.exception("librarian_experience_dispatch_failed", extra={"task_id": task_id})

        # Best-effort: auto call resume (idempotent + redis lock protected).
        asyncio.create_task(_auto_resume(task_id))
    finally:
        await release_lock(key=lock_key, value="1")

    return {"ok": True, "task_id": task_id, "status": task.status, "resume_triggered": True}


@router.get("/{task_id}/hil/current")
async def hil_current(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with get_session_maker()() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        _ensure_task_access(task, current_user)

        row = (await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))).scalars().first()
        if not row:
            return {"task_id": task_id, "status": task.status, "hil": None}

        prefill = {}
        try:
            prefill = json.loads((row.prefill_json or b"{}").decode("utf-8"))
        except Exception:
            prefill = {}

        return {
            "task_id": task_id,
            "status": task.status,
            "hil": {
                "ui_component": row.ui_component,
                "reasoning_summary": row.reasoning_summary,
                "prefill": prefill,
            },
        }

