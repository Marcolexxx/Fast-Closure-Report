from __future__ import annotations

from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult


async def bind_design_images(input: dict, context: TaskContext) -> ToolResult:
    """
    HIL (DesignBinder).
    MVP: return item->design_image binding using provided `bindings` or empty mapping.
    """

    items: List[Dict[str, Any]] = input.get("items") or []
    design_images: List[Dict[str, Any]] = input.get("design_images") or []

    bindings = input.get("bindings")  # optional user selections
    if bindings is None:
        # Default: bind none (wait for human).
        bindings = []

    hil = {
        "ui_component": "DesignBinder",
        "prefill_data": {
            "items": items,
            "design_images": design_images,
            "bindings": bindings,
        },
    }

    return ToolResult(
        success=True,
        data={"bindings": bindings, "hil": hil},
        summary="设计图绑定请求已准备（MVP）",
    )

