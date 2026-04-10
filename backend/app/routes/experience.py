from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_engine
from app.models import FeedbackEvent, User, UserRole
from app.security.deps import get_current_user

router = APIRouter(prefix="/experience", tags=["experience"])

def _sm() -> async_sessionmaker[AsyncSession]:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)

class FeedbackSubmit(BaseModel):
    task_id: str
    project_id: Optional[str] = None
    # FIX B1: skill_id is required by the model (was missing in route schema)
    skill_id: Optional[str] = None
    event_type: str
    payload_json: dict[str, Any]

@router.post("/feedback")
async def submit_feedback(
    body: FeedbackSubmit,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Submits HIL adjustments into the datalake acting as the 'Experience Layer',
    allowing the system to record differences between AI prediction and Human correction.
    """
    async with _sm()() as session:
        event = FeedbackEvent(
            idempotency_key=f"{body.task_id}_{body.event_type}",
            task_id=body.task_id,
            project_id=body.project_id,
            skill_id=body.skill_id,
            user_id=current_user.id,
            event_type=body.event_type,
            # FIX B2: encode string to bytes for LargeBinary column
            payload_json=json.dumps(body.payload_json, ensure_ascii=False).encode('utf-8')
        )
        session.add(event)
        try:
            await session.commit()
        except Exception:
            # Safely ignore duplicates on idempotency key constraint
            await session.rollback()

    return {"status": "ok", "message": "Feedback captured. Thank you!"}

from sqlalchemy import func

@router.get("/metrics")
async def get_feedback_metrics(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Admin endpoint to see where the agent is failing the most (PRD §8.2)."""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin only")
        
    async with _sm()() as session:
        # Aggregate by event type to find patterns
        query = (
            select(FeedbackEvent.event_type, func.count(FeedbackEvent.id))
            .group_by(FeedbackEvent.event_type)
            .order_by(func.count(FeedbackEvent.id).desc())
        )
        rows = (await session.execute(query)).all()
        
    stats = {row[0]: row[1] for row in rows}
    
    return {
        "status": "ok",
        "total_events": sum(stats.values()),
        "distribution": stats,
        "recommendation": "Engineers should check top events for prompt refinement."
    }
