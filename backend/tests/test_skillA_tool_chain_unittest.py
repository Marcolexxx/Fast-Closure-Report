from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

# Ensure `backend/` is on sys.path so `import app.*` works when running from repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class SkillAToolChainTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # Use sqlite for tests to avoid depending on docker mysql.
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_e2e.db"
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # not used in this test
        os.environ["SKILLS_DIR"] = str(BACKEND_DIR / "skills")

        # Late imports after env set
        from app.db_init import init_task_schema
        from app.skills.registry import get_skill_registry_service
        from app.tools.registry import get_tool_registry

        await init_task_schema()
        await get_skill_registry_service().load_all()

        tools = get_tool_registry().list_tools()
        # Ensure skill A tools are registered
        self.assertIn("skill-event-report::parse_excel", tools)
        self.assertIn("skill-event-report::submit_review", tools)

        # Prepare a task row needed by ToolCallLog foreign key.
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from app.db import get_engine
        from app.models import AgentTask

        engine = get_engine()
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with Session() as s:
            t = await s.get(AgentTask, "e2e_t1")
            if not t:
                s.add(AgentTask(id="e2e_t1", status="CREATED", trace_id="test-trace"))
                await s.commit()

    async def test_full_skillA_chain_logs_tool_calls(self) -> None:
        from app.tools.base import TaskContext
        from app.tools.runner import execute_tool
        from sqlalchemy import select, func
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from app.db import get_engine
        from app.models import ToolCallLog

        ctx = TaskContext(task_id="e2e_t1", user_id=None, trace_id="test-trace")

        # 1 parse_excel
        r1 = await execute_tool("skill-event-report::parse_excel", {}, ctx)
        self.assertTrue(r1.success)
        items = r1.data.get("items") or []

        # 2 classify_assets
        r2 = await execute_tool("skill-event-report::classify_assets", {"assets": []}, ctx)
        self.assertTrue(r2.success)

        # 3 fetch_cloud_album
        r3 = await execute_tool("skill-event-report::fetch_cloud_album", {"url": "demo", "max_images": 2}, ctx)
        self.assertTrue(r3.success)
        assets = r3.data.get("assets") or []

        # 4 run_ai_detection (sync tool; celery tested separately)
        r4 = await execute_tool(
            "skill-event-report::run_ai_detection",
            {"assets": assets, "item_names": [it.get("name") for it in items]},
            ctx,
        )
        self.assertTrue(r4.success)

        # 5 bind_design_images (HIL tool; still returns success with hil payload)
        r5 = await execute_tool(
            "skill-event-report::bind_design_images",
            {"items": items, "design_images": []},
            ctx,
        )
        self.assertTrue(r5.success)

        # 6 request_annotation (HIL tool)
        r6 = await execute_tool("skill-event-report::request_annotation", {"detections": r4.data.get("detections")}, ctx)
        self.assertTrue(r6.success)

        # 7 validate_quantity
        r7 = await execute_tool("skill-event-report::validate_quantity", {"items": items, "actuals": {}}, ctx)
        self.assertTrue(r7.success)

        # 8 ocr_receipt
        r8 = await execute_tool("skill-event-report::ocr_receipt", {}, ctx)
        self.assertTrue(r8.success)

        # 9 match_receipts
        r9 = await execute_tool("skill-event-report::match_receipts", {"receipts": r8.data.get("receipts")}, ctx)
        self.assertTrue(r9.success)

        # 10 request_receipt_confirm (HIL)
        r10 = await execute_tool(
            "skill-event-report::request_receipt_confirm",
            {"matches": r9.data.get("matches"), "unmatched": r9.data.get("unmatched")},
            ctx,
        )
        self.assertTrue(r10.success)

        # 11 generate_ppt
        r11 = await execute_tool(
            "skill-event-report::generate_ppt",
            {"template_id": "default", "items": items, "receipts": r8.data.get("receipts")},
            ctx,
        )
        self.assertTrue(r11.success)

        # 12 submit_review
        r12 = await execute_tool(
            "skill-event-report::submit_review",
            {"pptx_path": r11.data.get("pptx_path"), "comment": "ok"},
            ctx,
        )
        self.assertTrue(r12.success)

        engine = get_engine()
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with Session() as s:
            count = (await s.execute(select(func.count()).select_from(ToolCallLog).where(ToolCallLog.task_id == "e2e_t1"))).scalar_one()
        self.assertGreaterEqual(count, 12)


if __name__ == "__main__":
    unittest.main()

