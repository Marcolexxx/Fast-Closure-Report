from __future__ import annotations

import asyncio
import jwt
from functools import lru_cache
from typing import Any, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_engine
from app.models import AgentTask, TaskHilState, TaskStatus, User, UserRole
from app.redis_lock import get_redis_client
from app.security.auth import decode_token

router = APIRouter(prefix="")


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _load_task(session: AsyncSession, task_id: str) -> Optional[AgentTask]:
    return await session.get(AgentTask, task_id)


async def _load_user(session: AsyncSession, user_id: str) -> Optional[User]:
    return await session.get(User, user_id)


def _decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return {}
    if payload.get("type") != "access":
        return {}
    return payload


@router.websocket("/ws/task/{task_id}")
async def ws_task(websocket: WebSocket, task_id: str) -> None:
    settings = get_settings()
    trace_id = websocket.headers.get(settings.trace_header_name, "-")
    progress_channel = f"task:{task_id}:progress"

    await websocket.accept()

    async with get_session_maker()() as session:
        token = websocket.query_params.get("token", "")
        payload = _decode_access_token(token)
        user_id = str(payload.get("sub", ""))
        if not user_id:
            await websocket.send_json({"type": "error", "task_id": task_id, "message": "Unauthorized"})
            await websocket.close(code=1008)
            return
        user = await _load_user(session, user_id)
        if not user or not user.is_active:
            await websocket.send_json({"type": "error", "task_id": task_id, "message": "Unauthorized"})
            await websocket.close(code=1008)
            return

        task = await _load_task(session, task_id)
        if not task:
            await websocket.send_json(
                {"type": "error", "task_id": task_id, "message": "Task not found"}
            )
            await websocket.close(code=1008)
            return
        # IDOR protection: only task owner or admin can subscribe.
        if user.role != UserRole.ADMIN.value and str(task.user_id or "") != str(user.id):
            await websocket.send_json({"type": "error", "task_id": task_id, "message": "Forbidden"})
            await websocket.close(code=1008)
            return

        last_state: Tuple[str, int] = (str(task.status), int(task.current_step))
        hil = None
        if str(task.status) == TaskStatus.WAITING_HUMAN.value:
            row = (
                await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))
            ).scalars().first()
            if row:
                hil = {"ui_component": row.ui_component, "reasoning_summary": row.reasoning_summary}

        await websocket.send_json(
            {
                "type": "hydration",
                "task_id": task_id,
                "status": str(task.status),
                "current_step": task.current_step,
                "max_steps": task.max_steps,
                "trace_id": task.trace_id or trace_id,
                "ui_component": (hil or {}).get("ui_component"),
                "reasoning_summary": (hil or {}).get("reasoning_summary"),
            }
        )

    # Lightweight polling loop (MVP). Later phases will replace with Redis Pub/Sub.
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()
    
    try:
        # Subscribe Redis progress channel.
        await pubsub.subscribe(progress_channel)

        # Non-blocking event loop using pubsub.listen()
        async for message in pubsub.listen():
            if message and message.get("type") == "message":
                data = message.get("data")
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8", errors="ignore")
                
                payload = json_safe_loads(data)
                msg_type = payload.get("type", "progress")
                
                if msg_type == "progress":
                    await websocket.send_json(
                        {"type": "progress", "task_id": task_id, "payload": payload}
                    )
                elif msg_type == "state_change":
                    async with get_session_maker()() as session:
                        task = await _load_task(session, task_id)
                        if not task:
                            await websocket.send_json({"type": "error", "task_id": task_id, "message": "Task not found"})
                            await websocket.close(code=1008)
                            return

                        state = (str(task.status), int(task.current_step))
                        if state != last_state:
                            last_state = state
                            hil = None
                            if str(task.status) == TaskStatus.WAITING_HUMAN.value:
                                row = (
                                    await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))
                                ).scalars().first()
                                if row:
                                    hil = {"ui_component": row.ui_component, "reasoning_summary": row.reasoning_summary}
                            await websocket.send_json(
                                {
                                    "type": "task_update",
                                    "task_id": task_id,
                                    "status": str(task.status),
                                    "current_step": task.current_step,
                                    "trace_id": task.trace_id or trace_id,
                                    "ui_component": (hil or {}).get("ui_component"),
                                    "reasoning_summary": (hil or {}).get("reasoning_summary"),
                                }
                            )

            # Allow client-side ping/pong or future extension.
            # We don't block on receive here to avoid backpressure complexity.
    except WebSocketDisconnect:
        return
    finally:
        try:
            await pubsub.unsubscribe(progress_channel)
            await pubsub.close()
        except Exception:
            pass


def json_safe_loads(s: Any) -> Any:
    # Local helper to avoid importing json at module top for minor startup cost.
    import json

    try:
        return json.loads(s) if isinstance(s, str) else s
    except Exception:
        return s

