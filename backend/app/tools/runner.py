from __future__ import annotations

import hashlib
import json
import time
from functools import lru_cache
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import ToolCallLog, ToolCallLogStatus
from app.tools.base import TaskContext, ToolResult
from app.tools.errors import BusinessError
from app.tools.registry import get_tool_registry


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _digest_input(input_data: dict) -> str:
    payload = json.dumps(input_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _truncate(s: Any, n: int) -> str:
    text = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    return text[:n]


async def execute_tool(tool_name: str, input_data: dict, context: TaskContext) -> ToolResult:
    tool_fn = get_tool_registry().get(tool_name)

    input_digest = _digest_input(input_data)

    session_maker = get_session_maker()
    async with session_maker() as session:
        # Minimal idempotency: reuse previous SUCCESS for same input_digest.
        existing_stmt = (
            select(ToolCallLog)
            .where(
                ToolCallLog.task_id == context.task_id,
                ToolCallLog.tool_name == tool_name,
                ToolCallLog.input_digest == input_digest,
            )
            .order_by(desc(ToolCallLog.created_at))
            .limit(1)
        )
        existing = (await session.execute(existing_stmt)).scalars().first()
        if existing and existing.status == ToolCallLogStatus.SUCCESS.value:
            return ToolResult(
                success=True,
                data={},
                summary=(existing.output_summary or "")[:200],
            )

        start = time.time()
        result: ToolResult
        try:
            result = await tool_fn(input_data, context)
        except BusinessError as e:
            result = ToolResult(
                success=False,
                error_type="BUSINESS",
                error_code=e.error_code,
                message=e.message,
                summary=(e.message or "business error")[:200],
            )
        except Exception:
            # Let the Agent see only generic internal error strings.
            result = ToolResult(
                success=False,
                error_type="SYSTEM",
                error_code="SYSTEM_ERROR",
                message="Internal error",
                summary="System error (see ToolCallLog for details)",
            )
            # Still record the traceable error in stdout logs via middleware trace_id.
            if context.logger:
                context.logger.exception(
                    "tool_failed",
                    extra={"tool_name": tool_name, "trace_id": context.trace_id},
                )

        duration_ms = int((time.time() - start) * 1000)

        status = ToolCallLogStatus.SUCCESS.value if result.success else ToolCallLogStatus.FAILED.value
        stmt = ToolCallLog(
            task_id=context.task_id,
            tool_name=tool_name,
            input_digest=input_digest,
            input_summary=_truncate(input_data, 500),
            output_summary=_truncate(result.data or result.message or {}, 500),
            duration_ms=duration_ms,
            error_type=result.error_type,
            status=status,
            trace_id=context.trace_id,
        )
        session.add(stmt)
        await session.commit()

        # Enforce summary <= 200 chars
        if result.summary:
            result.summary = result.summary[:200]

        return result

