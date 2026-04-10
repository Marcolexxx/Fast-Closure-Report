from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult
from app.shared.vision_adapter import get_vision_adapter

logger = logging.getLogger(__name__)

async def run_ai_detection(input: dict, context: TaskContext) -> ToolResult:
    """
    Call local inference server or Vision API for object detection.
    """

    image_assets: List[Dict[str, Any]] = input.get("assets") or input.get("images") or []
    item_names: List[str] = input.get("item_names") or []
    image_paths = [a.get("local_path", "") for a in image_assets if a.get("local_path")]

    vision = await get_vision_adapter()
    try:
        detections = await vision.detect_objects(image_paths, item_names)
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        return ToolResult(
            success=False,
            error_type="SYSTEM",
            error_code="INFERENCE_ERROR",
            message=str(e),
            summary="推理服务调用失败",
        )

    return ToolResult(
        success=True,
        data={"detections": detections},
        summary=f"AI 预标注候选生成完成：{len(detections)} 组",
    )

