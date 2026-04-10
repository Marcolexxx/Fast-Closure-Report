from __future__ import annotations

from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult


async def request_receipt_confirm(input: dict, context: TaskContext) -> ToolResult:
    """
    HIL (ReceiptMatcher).
    MVP: expose match table for human confirmation.
    """

    matches: List[Dict[str, Any]] = input.get("matches") or []
    unmatched: List[Dict[str, Any]] = input.get("unmatched") or []

    hil = {
        "ui_component": "ReceiptMatcher",
        "prefill_data": {"matches": matches, "unmatched": unmatched},
        "reasoning_summary": f"已完成初步配对：matches={len(matches)}, unmatched={len(unmatched)}，请确认/补充（MVP）。",
    }

    return ToolResult(
        success=True,
        data={"hil": hil, "confirmed_matches": matches, "unmatched": unmatched},
        summary="凭据确认请求已准备（MVP）",
    )

