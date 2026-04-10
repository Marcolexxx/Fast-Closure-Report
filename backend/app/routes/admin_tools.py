"""
Admin: Tools Management API
Read-only endpoints to introspect registered tools and their runtime stats.

This is designed to support the Admin console "Tools 管理" tab.
All endpoints require admin role.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import ToolCallLog, User
from app.security.deps import require_admin
from app.tools.registry import get_tool_registry

router = APIRouter(prefix="/admin/tools", tags=["admin-tools"])


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


def _split_tool_id(tool_id: str) -> tuple[Optional[str], str]:
    if "::" not in tool_id:
        return None, tool_id
    skill_id, name = tool_id.split("::", 1)
    return skill_id or None, name


class ToolListItem(BaseModel):
    tool_id: str
    skill_id: Optional[str] = None
    name: str
    total_calls: int = 0
    failed_calls: int = 0
    error_rate: float = 0.0
    last_used_at: Optional[str] = None


@router.get("")
async def list_tools(
    skill_id: Optional[str] = None,
    q: Optional[str] = None,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Return all registered tool IDs plus aggregated runtime stats from ToolCallLog.

    - skill_id: filter tools by skill prefix (e.g. 'skill-event-report')
    - q: substring filter on tool_id
    """
    tool_ids = get_tool_registry().list_tools()
    if skill_id:
        prefix = f"{skill_id}::"
        tool_ids = [t for t in tool_ids if t.startswith(prefix)]
    if q:
        q2 = q.lower().strip()
        tool_ids = [t for t in tool_ids if q2 in t.lower()]

    # Aggregate stats by tool_name (stored as full tool_id)
    async with _sm()() as s:
        rows = (
            await s.execute(
                select(
                    ToolCallLog.tool_name.label("tool_id"),
                    func.count(ToolCallLog.id).label("total_calls"),
                    func.sum(case((ToolCallLog.status == "FAILED", 1), else_=0)).label("failed_calls"),
                    func.max(ToolCallLog.created_at).label("last_used_at"),
                )
                .where(ToolCallLog.tool_name.in_(tool_ids) if tool_ids else False)
                .group_by(ToolCallLog.tool_name)
            )
        ).all()

    stats_map: dict[str, dict[str, Any]] = {}
    for tool_id_val, total_calls, failed_calls, last_used_at in rows:
        total = int(total_calls or 0)
        failed = int(failed_calls or 0)
        stats_map[str(tool_id_val)] = {
            "total_calls": total,
            "failed_calls": failed,
            "last_used_at": last_used_at.isoformat() if isinstance(last_used_at, datetime) else None,
        }

    items: list[ToolListItem] = []
    for tid in tool_ids:
        s2 = stats_map.get(tid, {})
        total = int(s2.get("total_calls", 0) or 0)
        failed = int(s2.get("failed_calls", 0) or 0)
        rate = (failed / total) if total > 0 else 0.0
        sid, name = _split_tool_id(tid)
        items.append(
            ToolListItem(
                tool_id=tid,
                skill_id=sid,
                name=name,
                total_calls=total,
                failed_calls=failed,
                error_rate=rate,
                last_used_at=s2.get("last_used_at"),
            )
        )

    # Sort by: skill_id, name
    items.sort(key=lambda x: (x.skill_id or "", x.name))
    return {"items": [i.model_dump() for i in items], "total": len(items)}


@router.get("/calls")
async def list_tool_calls(
    tool_id: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Return recent ToolCallLog entries, optionally filtered by tool_id."""
    limit = max(1, min(int(limit), 200))
    async with _sm()() as s:
        q = select(ToolCallLog).order_by(desc(ToolCallLog.created_at)).limit(limit)
        if tool_id:
            q = select(ToolCallLog).where(ToolCallLog.tool_name == tool_id).order_by(desc(ToolCallLog.created_at)).limit(limit)
        rows = (await s.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "task_id": r.task_id,
                "tool_name": r.tool_name,
                "status": r.status,
                "error_type": r.error_type,
                "duration_ms": r.duration_ms,
                "trace_id": r.trace_id,
                "input_summary": r.input_summary,
                "output_summary": r.output_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }

