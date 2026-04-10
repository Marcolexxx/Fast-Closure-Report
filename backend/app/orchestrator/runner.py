from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.db import get_engine
from app.models import AgentTask, ProjectStatus, TaskCheckpoint, TaskHilState, TaskStatus
from app.orchestrator.context_store import load_task_context, save_task_context
from app.skills.registry import get_skill_registry_service
from app.tools.base import TaskContext as ToolTaskContext
from app.tools.runner import execute_tool
from app.shared.librarian_agent import run_librarian_rescue
from app.redis_lock import get_redis_client


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _tool_ns(skill_id: str, tool_name: str) -> str:
    return f"{skill_id}::{tool_name}"


async def _write_checkpoint(
    task_id: str,
    step_index: int,
    step_name: str,
    tool_name: str,
    output_summary: str,
    next_step: str,
) -> None:
    async with get_session_maker()() as session:
        session.add(
            TaskCheckpoint(
                task_id=task_id,
                step_index=step_index,
                step_name=step_name,
                tool_name=tool_name,
                output_summary=output_summary or "",
                next_step=next_step or "",
            )
        )
        await session.commit()


async def _set_hil_state(
    task_id: str,
    ui_component: str,
    reasoning_summary: str,
    prefill: dict[str, Any],
) -> None:
    async with get_session_maker()() as session:
        row = (
            await session.execute(select(TaskHilState).where(TaskHilState.task_id == task_id))
        ).scalars().first()
        if not row:
            row = TaskHilState(task_id=task_id)
            session.add(row)
        row.ui_component = ui_component
        row.reasoning_summary = reasoning_summary or ""
        row.prefill_json = json.dumps(prefill or {}, ensure_ascii=False).encode("utf-8")

        task = await session.get(AgentTask, task_id)
        if task:
            task.status = TaskStatus.WAITING_HUMAN.value
        await session.commit()


async def _set_task_status(task_id: str, status: str, current_step: Optional[int] = None) -> None:
    async with get_session_maker()() as session:
        task = await session.get(AgentTask, task_id)
        if not task:
            return
        task.status = status
        if current_step is not None:
            task.current_step = current_step
        await session.commit()


async def _get_task(task_id: str) -> Optional[AgentTask]:
    async with get_session_maker()() as session:
        return await session.get(AgentTask, task_id)


def _skillA_inputs(tool_name: str, ctx: dict[str, Any]) -> dict[str, Any]:
    # Minimal wiring to make the chain runnable with current MVP tools.
    if tool_name == "parse_excel":
        return ctx.get("parse_excel_input", {})
    if tool_name == "classify_assets":
        return {"assets": ctx.get("assets", [])}
    if tool_name == "fetch_cloud_album":
        return ctx.get("fetch_cloud_album_input", {"url": ctx.get("cloud_album_url", "demo"), "max_images": 2})
    if tool_name == "run_ai_detection":
        return {"assets": ctx.get("assets", []), "item_names": [i.get("name") for i in ctx.get("items", [])]}
    if tool_name == "bind_design_images":
        return {"items": ctx.get("items", []), "design_images": ctx.get("design_images", [])}
    if tool_name == "request_annotation":
        return {"detections": ctx.get("detections", [])}
    if tool_name == "validate_quantity":
        return {"items": ctx.get("items", []), "actuals": ctx.get("actuals", {})}
    if tool_name == "ocr_receipt":
        return ctx.get("ocr_input", {})
    if tool_name == "match_receipts":
        return {"receipts": ctx.get("receipts", [])}
    if tool_name == "request_receipt_confirm":
        return {"matches": ctx.get("matches", []), "unmatched": ctx.get("unmatched", [])}
    if tool_name == "generate_ppt":
        return {"template_id": ctx.get("template_id", "default"), "items": ctx.get("items", []), "receipts": ctx.get("receipts", [])}
    if tool_name == "submit_review":
        return {"pptx_path": ctx.get("pptx_path", ""), "comment": ctx.get("review_comment", "")}
    return {}


    pass


async def run_task(task_id: str) -> None:
    task = await _get_task(task_id)
    if not task or not task.skill_id:
        return

    # If we're waiting for human, do not continue.
    if str(task.status) == TaskStatus.WAITING_HUMAN.value:
        return

    skill_id = task.skill_id
    service = get_skill_registry_service()
    skill = service.skills.get(skill_id)
    if not skill:
        await _set_task_status(task_id, TaskStatus.ERROR.value)
        return

    enabled = await service.get_enabled(skill_id)
    if not enabled:
        await _set_task_status(task_id, TaskStatus.CANCELLED.value)
        return

    ctx = await load_task_context(task_id)
    start_index = int(task.current_step or 0)

    await _set_task_status(task_id, TaskStatus.RUNNING.value, current_step=start_index)

    for idx in range(start_index, len(skill.tools)):
        tool_spec = skill.tools[idx]
        tool_name = tool_spec.name
        full_tool_name = _tool_ns(skill_id, tool_name)

        next_step = skill.tools[idx + 1].name if idx + 1 < len(skill.tools) else ""

        # HIL: pause and expose UI.
        if tool_spec.type == "human_in_loop":
            # Run the tool once to produce prefill payload (it returns success with hil data).
            input_data = _skillA_inputs(tool_name, ctx)
            tool_ctx = ToolTaskContext(task_id=task_id, user_id=task.user_id, trace_id=task.trace_id, logger=logger)
            result = await execute_tool(full_tool_name, input_data, tool_ctx)

            hil = (result.data or {}).get("hil") or {}
            ui = hil.get("ui_component") or tool_spec.ui or "AnnotationCanvas"
            reasoning = hil.get("reasoning_summary") or result.summary
            prefill = hil.get("prefill_data") or hil.get("prefill") or {}

            await _write_checkpoint(task_id, idx, tool_name, full_tool_name, result.summary, next_step)
            await _set_hil_state(task_id, ui_component=ui, reasoning_summary=reasoning, prefill=prefill)
            # Do not advance current_step; resume will restart from this idx (idempotent tool runner protects).
            await _set_task_status(task_id, TaskStatus.WAITING_HUMAN.value, current_step=idx)
            return

        # AUTO tools
        input_data = _skillA_inputs(tool_name, ctx)

        if tool_spec.async_ and tool_name == "run_ai_detection":
            try:
                # Dispatch entirely asynchronously and DO NOT wait
                celery_app.send_task("run_ai_detection_async", args=[task_id, input_data])
                await _write_checkpoint(task_id, idx, tool_name, full_tool_name, "async queued", next_step)
                await save_task_context(task_id, ctx)
                return # Release ASGI worker immediately!
            except Exception as e:
                logger.exception("async_tool_dispatch_failed", extra={"task_id": task_id, "tool": tool_name})
                await _set_task_status(task_id, TaskStatus.ERROR.value, current_step=idx)
                return

        tool_ctx = ToolTaskContext(task_id=task_id, user_id=task.user_id, trace_id=task.trace_id, logger=logger)
        result = await execute_tool(full_tool_name, input_data, tool_ctx)
        
        # Bypass Hook (Librarian Experience Rescue)
        needs_rescue = False
        failed_reason = ""
        if not result.success:
            needs_rescue = True
            failed_reason = result.message or "Execution failed"
        elif tool_name == "ocr_receipt":
            # Check for low confidence fields
            low_conf = result.data.get("low_confidence_count", 0) if isinstance(result.data, dict) else 0
            if low_conf > 0:
                needs_rescue = True
                failed_reason = f"OCR Low Confidence detected count: {low_conf}"
                
        if needs_rescue:
            logger.warning(f"Task {task_id} needs Librarian rescue: {failed_reason}")
            rescue_succeeded = await run_librarian_rescue(ctx, failed_reason, input_data)
            if rescue_succeeded:
                result.success = True
                result.summary = "Librarian bypass rescue succeeded."
                # If tool was OCR, we would overwrite result data here. Emulate it.
                if tool_name == "ocr_receipt" and isinstance(result.data, dict):
                    result.data["low_confidence_count"] = 0 
            else:
                if not result.success:
                    await _set_task_status(task_id, TaskStatus.ERROR.value, current_step=idx)
                    return
                # If it was a success but low confidence, let it fall through 
                # (it will probably hit HIL next step or we can force HIL here)

        await _write_checkpoint(task_id, idx, tool_name, full_tool_name, result.summary, next_step)

        if not result.success:
            await _set_task_status(task_id, TaskStatus.ERROR.value, current_step=idx)
            return

        # Store commonly used outputs for next steps
        if tool_name == "parse_excel":
            ctx["items"] = (result.data or {}).get("items", [])
        elif tool_name == "fetch_cloud_album":
            ctx["assets"] = (result.data or {}).get("assets", [])
        elif tool_name == "ocr_receipt":
            ctx["receipts"] = (result.data or {}).get("receipts", [])
        elif tool_name == "match_receipts":
            ctx["matches"] = (result.data or {}).get("matches", [])
            ctx["unmatched"] = (result.data or {}).get("unmatched", [])
        elif tool_name == "generate_ppt":
            ctx["pptx_path"] = (result.data or {}).get("pptx_path", "")

        await save_task_context(task_id, ctx)
        await _set_task_status(task_id, TaskStatus.RUNNING.value, current_step=idx + 1)

    await _set_task_status(task_id, TaskStatus.COMPLETED.value, current_step=len(skill.tools))

    # Close loop on Project if linked
    project_id = ctx.get("project_id")
    pptx_path = ctx.get("pptx_path")
    if project_id and pptx_path:
        async with get_session_maker()() as session:
            from app.models import Project
            project = await session.get(Project, project_id)
            if project:
                # FIX B4: Use enum value 'pending_review' not 'PENDING_REVIEW'
                project.status = ProjectStatus.PENDING_REVIEW.value
                project.pptx_path = pptx_path
                await session.commit()
