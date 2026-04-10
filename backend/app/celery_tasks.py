from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

import redis
from app.celery_app import celery_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import AgentTask
from app.tools.base import TaskContext
from app.tools.runner import execute_tool
from app.skills.registry import get_skill_registry_service
from app.orchestrator.context_store import load_task_context, save_task_context


_SKILL_REGISTRY_LOADED = False


def _ensure_skill_registry_loaded() -> None:
    global _SKILL_REGISTRY_LOADED
    if _SKILL_REGISTRY_LOADED:
        return
    import asyncio

    service = get_skill_registry_service()
    asyncio.run(service.load_all())
    _SKILL_REGISTRY_LOADED = True


def _get_redis_sync_client() -> redis.Redis:
    # Worker is a sync context; use redis-py sync client.
    # Fall back to env var.
    import os

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.Redis.from_url(redis_url)


def _progress_channel(task_id: str) -> str:
    return f"task:{task_id}:progress"


def _session_maker() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@celery_app.task(name="run_ai_detection_async")
def run_ai_detection_async(task_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    MVP:
    - Load AgentTask to get trace_id/user_id
    - Execute tool `skill-event-report::run_ai_detection` via ToolRunner.
    - Advance Task check point.
    - Publish progress explicitly.
    - Recall run_task!
    """
    redis_client = _get_redis_sync_client()
    payload_base = {"task_id": task_id, "tool_name": "run_ai_detection", "timestamp": datetime.utcnow().isoformat()}
    redis_client.publish(_progress_channel(task_id), json.dumps({**payload_base, "type": "progress", "current": 0, "total": 100, "step_desc": "queued"}))

    _ensure_skill_registry_loaded()

    async def _run() -> Dict[str, Any]:
        session_maker = _session_maker()
        async with session_maker() as session:
            task = await session.get(AgentTask, task_id)
            trace_id = task.trace_id if task else "-"
            user_id = getattr(task, "user_id", None) if task else None
            ctx = TaskContext(task_id=task_id, user_id=user_id, trace_id=trace_id, storage=None, logger=None)
            tool_result = await execute_tool("skill-event-report::run_ai_detection", input_data, ctx)
            
            # Post-processing: advance state machine and continue
            if tool_result.success and isinstance(tool_result.data, dict) and tool_result.data.get("detections"):
                task_ctx = await load_task_context(task_id)
                task_ctx["detections"] = tool_result.data["detections"]
                await save_task_context(task_id, task_ctx)
                
            if task and tool_result.success:
                task.current_step += 1
                await session.commit()
                
            redis_client.publish(
                _progress_channel(task_id),
                json.dumps({"type": "state_change", "task_id": task_id, "timestamp": datetime.utcnow().isoformat()})
            )
            
            if tool_result.success:
                # Fire the runner again from the worker
                from app.orchestrator.runner import run_task
                await run_task(task_id)

            return {
                "success": tool_result.success,
                "summary": tool_result.summary,
                "data": tool_result.data,
            }

    # Run async tool runner in this sync Celery task.
    import asyncio
    result = asyncio.run(_run())

    redis_client.publish(
        _progress_channel(task_id),
        json.dumps(
            {
                **payload_base,
                "type": "progress",
                "current": 100,
                "total": 100,
                "step_desc": "completed",
                "success": result.get("success"),
                "summary": result.get("summary"),
            }
        ),
    )

    return result


@celery_app.task(name="resource_gc_task")
def resource_gc_task() -> Dict[str, Any]:
    """
    Cleans up soft-deleted and >24h obsolete image assets.
    """
    import os
    import asyncio
    from datetime import datetime, timedelta
    from sqlalchemy import select

    async def _run_gc() -> Dict[str, Any]:
        session_maker = _session_maker()
        deleted_count = 0
        async with session_maker() as session:
            from app.models import AssetImage
            
            cutoff = datetime.utcnow() - timedelta(days=7)
            q = select(AssetImage).where(AssetImage.is_deleted == True, AssetImage.deleted_at < cutoff)
            rows = (await session.execute(q)).scalars().all()
            for asset in rows:
                if asset.original_path and os.path.exists(asset.original_path):
                    try:
                        os.remove(asset.original_path)
                    except OSError:
                        pass
                if asset.thumbnail_path and os.path.exists(asset.thumbnail_path):
                    try:
                        os.remove(asset.thumbnail_path)
                    except OSError:
                        pass
                await session.delete(asset)
                deleted_count += 1
            await session.commit()
        return {"deleted_assets": deleted_count}

    import asyncio
    result = asyncio.run(_run_gc())
    return result


@celery_app.task(name="pattern_miner_task")
def pattern_miner_task() -> Dict[str, Any]:
    """
    PRD §8.2 PatternMiner: 累积 ≥50 条 FeedbackEvent 后自动分析，生成 PatternReport。
    """
    import asyncio
    from collections import Counter
    from sqlalchemy import select, func

    FEEDBACK_THRESHOLD = 50

    async def _run_miner() -> Dict[str, Any]:
        session_maker = _session_maker()
        reports_created = 0

        async with session_maker() as session:
            from app.models import FeedbackEvent, PatternReport

            count_q = (
                select(FeedbackEvent.skill_id, func.count(FeedbackEvent.id).label("cnt"))
                .where(FeedbackEvent.skill_id.isnot(None))
                .group_by(FeedbackEvent.skill_id)
            )
            skill_counts = (await session.execute(count_q)).all()

            for skill_id, total_cnt in skill_counts:
                if total_cnt < FEEDBACK_THRESHOLD:
                    continue

                events_q = (
                    select(FeedbackEvent)
                    .where(FeedbackEvent.skill_id == skill_id)
                    .order_by(FeedbackEvent.created_at.desc())
                    .limit(500)
                )
                events = (await session.execute(events_q)).scalars().all()

                type_counter: Counter = Counter()
                for ev in events:
                    type_counter[ev.event_type] += 1

                top_issues = type_counter.most_common(10)
                summary_lines = [
                    f"[{i+1}] {etype}: {cnt} 次 ({cnt*100//len(events)}%)"
                    for i, (etype, cnt) in enumerate(top_issues)
                ]
                summary = (
                    f"分析 {len(events)} 条用户修正记录，高频问题：\n"
                    + "\n".join(summary_lines)
                )

                suggestions = {
                    "top_error_types": [
                        {"event_type": et, "count": c, "pct": round(c * 100 / len(events), 1)}
                        for et, c in top_issues
                    ],
                    "recommendation": (
                        "建议重点检查以下场景的 Agent Prompt 或工具参数设置：\n"
                        + ", ".join(et for et, _ in top_issues[:3])
                    ),
                }

                report = PatternReport(
                    skill_id=skill_id,
                    analysis_type="auto_feedback_pattern",
                    summary=summary,
                    sample_count=len(events),
                    suggestions_json=suggestions,
                )
                session.add(report)
                reports_created += 1

            await session.commit()

        return {"reports_created": reports_created}

    result = asyncio.run(_run_miner())
    return result



@celery_app.task(name="extract_librarian_experience_task")
def extract_librarian_experience_task(feedback_id: str) -> Dict[str, Any]:
    """
    Librarian Agent -- Experience Distillation.
    Triggered after every HIL correction to distill a FeedbackEvent into
    a LibrarianKnowledge leaf entry (keywords + intent_tags JSONB).
    """
    import asyncio

    async def _run_extract() -> Dict[str, Any]:
        session_maker = _session_maker()
        async with session_maker() as session:
            from app.models import FeedbackEvent, LibrarianKnowledge

            ev = await session.get(FeedbackEvent, feedback_id)
            if not ev:
                return {"status": "skipped", "reason": "FeedbackEvent not found"}

            payload_bytes = ev.payload_json or b"{}"
            payload: Dict[str, Any] = json.loads(
                payload_bytes.decode("utf-8", errors="ignore")
                if isinstance(payload_bytes, bytes)
                else payload_bytes
            )

            skill_id = ev.skill_id or "unknown"
            event_type = ev.event_type or ""
            keyword_parts = [event_type, skill_id]
            for v in payload.values():
                if isinstance(v, str) and len(v) < 128:
                    keyword_parts.append(v.strip())
            keywords = " ".join(filter(None, keyword_parts))
            summary = (
                f"HIL correction: event_type={event_type}, skill={skill_id}, "
                f"details={json.dumps(payload, ensure_ascii=False)[:200]}"
            )
            intent_tags = {
                "event_type": event_type,
                "source": "hil_correction",
                "payload_keys": list(payload.keys()),
            }
            knowledge = LibrarianKnowledge(
                skill_id=skill_id,
                parent_id=None,
                summary=summary,
                keywords=keywords,
                intent_tags=intent_tags,
                knowledge_json=payload,
                is_active=True,
            )
            session.add(knowledge)
            await session.commit()
            return {"status": "ok", "knowledge_id": knowledge.id}

    return asyncio.run(_run_extract())


@celery_app.task(name="librarian_nightly_patrol")
def librarian_nightly_patrol() -> Dict[str, Any]:
    """
    Librarian Agent -- Hierarchical Knowledge Tree Builder (nightly Beat).
    Clusters orphan leaf LibrarianKnowledge nodes under the same skill_id
    that share common keywords, creates or links them to parent summary
    nodes -- building the knowledge tree bottom-up.

    Leaf nodes  : parent_id IS NULL, knowledge_json NOT NULL
    Parent nodes: parent_id IS NULL, knowledge_json IS NULL (summary only)
    """
    import asyncio
    from collections import defaultdict
    from sqlalchemy import select

    async def _run_patrol() -> Dict[str, Any]:
        session_maker = _session_maker()
        nodes_created = 0
        nodes_linked = 0

        async with session_maker() as session:
            from app.models import LibrarianKnowledge

            leaf_q = (
                select(LibrarianKnowledge)
                .where(
                    LibrarianKnowledge.parent_id.is_(None),
                    LibrarianKnowledge.is_active == True,
                    LibrarianKnowledge.knowledge_json.isnot(None),
                )
                .order_by(LibrarianKnowledge.skill_id, LibrarianKnowledge.created_at)
            )
            leaves = (await session.execute(leaf_q)).scalars().all()

            by_skill: Dict[str, list] = defaultdict(list)
            for leaf in leaves:
                by_skill[leaf.skill_id].append(leaf)

            for skill_id, skill_leaves in by_skill.items():
                if len(skill_leaves) < 3:
                    continue

                cluster_map: Dict[str, list] = defaultdict(list)
                for leaf in skill_leaves:
                    tokens = [t for t in (leaf.keywords or "").split() if len(t) > 2]
                    cluster_key = tokens[0].lower() if tokens else "general"
                    cluster_map[cluster_key].append(leaf)

                for cluster_key, cluster_leaves in cluster_map.items():
                    if len(cluster_leaves) < 2:
                        continue

                    parent_q = select(LibrarianKnowledge).where(
                        LibrarianKnowledge.skill_id == skill_id,
                        LibrarianKnowledge.parent_id.is_(None),
                        LibrarianKnowledge.knowledge_json.is_(None),
                        LibrarianKnowledge.keywords.contains(cluster_key),
                    )
                    existing_parent = (await session.execute(parent_q)).scalars().first()

                    if not existing_parent:
                        summaries = "; ".join(l.summary[:80] for l in cluster_leaves[:5])
                        parent_node = LibrarianKnowledge(
                            skill_id=skill_id,
                            parent_id=None,
                            summary=f"[Cluster] {cluster_key}@{skill_id}: {summaries}",
                            keywords=f"{cluster_key} {skill_id}",
                            intent_tags={"cluster_key": cluster_key, "leaf_count": len(cluster_leaves)},
                            knowledge_json=None,
                            is_active=True,
                        )
                        session.add(parent_node)
                        await session.flush()
                        nodes_created += 1
                        parent_id = parent_node.id
                    else:
                        parent_id = existing_parent.id
                        tags = existing_parent.intent_tags or {}
                        tags["leaf_count"] = len(cluster_leaves)
                        existing_parent.intent_tags = tags

                    for leaf in cluster_leaves:
                        if leaf.parent_id is None:
                            leaf.parent_id = parent_id
                            nodes_linked += 1

            await session.commit()

        return {"nodes_created": nodes_created, "nodes_linked": nodes_linked}

    return asyncio.run(_run_patrol())


@celery_app.task(name="task_guardian_patrol")
def task_guardian_patrol() -> Dict[str, Any]:
    """
    DLQ / Guardian mechanism:
    Scans for AgentTasks that have been RUNNING for too long (>1h) without progress.
    Marks them as ERROR to prevent pipeline deadlocks caused by Worker OOM/crashes.
    """
    import asyncio
    from datetime import datetime, timedelta
    from sqlalchemy import select

    async def _run_guardian() -> Dict[str, Any]:
        session_maker = _session_maker()
        rescued_count = 0

        async with session_maker() as session:
            from app.models import AgentTask, TaskStatus, TaskCheckpoint
            
            cutoff = datetime.utcnow() - timedelta(hours=1)
            q = select(AgentTask).where(
                AgentTask.status == TaskStatus.RUNNING.value,
                AgentTask.updated_at < cutoff
            )
            zombie_tasks = (await session.execute(q)).scalars().all()
            
            for task in zombie_tasks:
                task.status = TaskStatus.ERROR.value
                
                # Add checkpoint explaining the dead-letter
                checkpoint = TaskCheckpoint(
                    task_id=task.id,
                    step_index=task.current_step,
                    step_name="system_guardian",
                    tool_name="task_guardian_patrol",
                    output_summary="Task automatically failed by DLQ Guardian due to > 1 hour inactivity. Possible worker crash or OOM.",
                    next_step="ABORT",
                )
                session.add(checkpoint)
                rescued_count += 1
            
            if rescued_count > 0:
                await session.commit()
                
        return {"rescued_zombies": rescued_count}

    return asyncio.run(_run_guardian())
