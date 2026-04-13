from __future__ import annotations

import asyncio
import hashlib
import json
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine, get_session_maker
from app.models import AgentTask, TaskContext, TaskStatus, Project, User, UserRole
from app.orchestrator.runner import run_task
from app.security.deps import get_current_user

router = APIRouter(prefix="", tags=["tasks"])


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TaskCreateRequest(BaseModel):
    task_id: Optional[str] = None
    skill_id: str
    user_id: Optional[str] = None
    idempotency_key: Optional[str] = None

    # Initial context: files/urls/params. Keep flexible for PRD evolution.
    context: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = 1


@router.post("/tasks")
async def create_task(
    body: TaskCreateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Security: user_id must come from auth context, not request body.
    user_id = current_user.id

    idem = body.idempotency_key
    if not idem:
        idem = _stable_hash(
            {
                "skill_id": body.skill_id,
                "user_id": user_id,
                "context": body.context,
            }
        )

    async with get_session_maker()() as session:
        existing = (await session.execute(select(AgentTask).where(AgentTask.idempotency_key == idem))).scalars().first()
        if existing:
            return {"task_id": existing.id, "status": existing.status, "idempotency_key": existing.idempotency_key, "reused": True}

        task = AgentTask(
            id=body.task_id or None,
            skill_id=body.skill_id,
            user_id=user_id,
            idempotency_key=idem,
            status=TaskStatus.CREATED.value,
            current_step=0,
            max_steps=50,
        )
        session.add(task)
        await session.flush()

        ctx_payload = json.dumps(body.context or {}, ensure_ascii=False).encode("utf-8")
        session.add(TaskContext(task_id=task.id, context_json=ctx_payload, schema_version=body.schema_version))
        
        # Closing the loop: Link Project -> Task
        project_id = body.context.get("project_id")
        if project_id:
            project = await session.get(Project, project_id)
            if project:
                # Row-level isolation: non-admin users can only bind their own department project.
                if current_user.role != UserRole.ADMIN.value:
                    if project.department_id and project.department_id != current_user.department_id:
                        raise HTTPException(status_code=403, detail="Project access denied")
                project.task_id = task.id
                # FIX M1: Don't change project status to TaskStatus 'RUNNING'
                # The orchestrator will update project.status when task completes
                
        await session.commit()

    # Fire-and-forget: start orchestrator.
    asyncio.create_task(run_task(task.id))

    return {"task_id": task.id, "status": task.status, "idempotency_key": idem, "reused": False}

