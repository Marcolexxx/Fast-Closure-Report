from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult
from app.shared.pptx_generator import generate_report_pptx

logger = logging.getLogger(__name__)


async def _resolve_template_path(template_id: str) -> str:
    """Look up PPTTemplate by ID or by is_default if 'default'."""
    if not template_id or template_id == "default":
        try:
            from sqlalchemy import select
            from app.db import get_session_maker
            from app.models import PPTTemplate
            async with get_session_maker()() as session:
                row = (
                    await session.execute(
                        select(PPTTemplate)
                        .where(PPTTemplate.is_default == True, PPTTemplate.is_active == True)
                    )
                ).scalars().first()
                if row:
                    return row.file_path
        except Exception:
            pass
        return ""
    
    try:
        from sqlalchemy import select
        from app.db import get_session_maker
        from app.models import PPTTemplate
        async with get_session_maker()() as session:
            row = await session.get(PPTTemplate, template_id)
            if row and row.is_active and row.file_path:
                return row.file_path
    except Exception:
        pass
    return ""


async def generate_ppt(input: dict, context: TaskContext) -> ToolResult:
    """
    Generate the final PPTX report for the project.
    Now leverages app.shared.pptx_generator with template support.
    """
    template_id = input.get("template_id") or "default"
    items = input.get("items") or []
    
    # Receipts can be either a straight list (old logic) or the new {matches, unmatched} dict
    receipt_data = input.get("receipts")
    if isinstance(receipt_data, list):
        receipt_data = {"matches": [], "unmatched": receipt_data}
    elif not receipt_data:
        receipt_data = {"matches": [], "unmatched": []}

    # Resolve template file path from DB
    template_path = await _resolve_template_path(template_id)

    try:
        pptx_path = generate_report_pptx(
            task_id=context.task_id,
            items=items,
            receipts=receipt_data,
            template_path=template_path
        )
    except Exception as e:
        logger.error(f"Failed to generate PPTX: {e}")
        return ToolResult(
            success=False,
            error_type="SYSTEM",
            error_code="PPT_GEN_FAILED",
            message=str(e),
            summary="PPT 结案报告生成失败",
        )

    receipts_count = len(receipt_data.get("matches", [])) + len(receipt_data.get("unmatched", []))

    return ToolResult(
        success=True,
        data={"pptx_path": pptx_path, "items_count": len(items), "receipts_count": receipts_count},
        summary=f"结案 PPT 智能排版完成：共嵌入 {len(items)} 项物料与 {receipts_count} 笔凭据 (template={template_path or 'blank'})",
    )

