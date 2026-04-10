from __future__ import annotations

from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult


async def request_annotation(input: dict, context: TaskContext) -> ToolResult:
    """
    HIL (AnnotationCanvas).
    MVP: package AI candidate boxes into a prefill structure for UI rendering.
    """

    detections: List[Dict[str, Any]] = input.get("detections") or []
    candidates = []
    for d in detections:
        candidates.append(
            {
                "image_id": d.get("image_id"),
                "item_name": d.get("item_name"),
                "candidate_boxes": d.get("candidates") or [],
            }
        )

    hil = {
        "ui_component": "AnnotationCanvas",
        "prefill_data": {"candidates": candidates},
        "reasoning_summary": f"已生成 {len(candidates)} 组候选框，需要您确认/调整标注（MVP）。",
    }

    return ToolResult(
        success=True,
        data={"hil": hil, "candidates": candidates},
        summary="标注画板请求已准备（MVP）",
    )

