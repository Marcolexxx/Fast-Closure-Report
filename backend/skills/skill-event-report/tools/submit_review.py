from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools.base import TaskContext, ToolResult


async def submit_review(input: dict, context: TaskContext) -> ToolResult:
    """
    MVP: create a review task stub and return a link-like token.
    """

    pptx_path = input.get("pptx_path") or input.get("ppt_path") or ""
    comment = input.get("comment") or ""

    review_token = f"review_{context.task_id}"

    return ToolResult(
        success=True,
        data={"review_token": review_token, "pptx_path": pptx_path, "comment": comment},
        summary="审核任务已创建（MVP）",
    )

