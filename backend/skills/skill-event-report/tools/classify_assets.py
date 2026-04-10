from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult
from app.shared.vision_adapter import get_vision_adapter

logger = logging.getLogger(__name__)

async def classify_assets(input: dict, context: TaskContext) -> ToolResult:
    """
    Classifies uploaded assets using VisionAdapter (Local Inference / API).
    """

    if "classified" in input:
        classified = input["classified"]
    else:
        assets: List[Dict[str, Any]] = input.get("assets") or []
        classified = {"design_render": [], "field_photo": [], "receipt": []}
        
        vision = await get_vision_adapter()
        
        for a in assets:
            at = a.get("asset_type")
            if at in classified:
                classified[at].append(a)
            else:
                try:
                    res = await vision.classify_image(a.get("local_path", ""))
                    cat = res.get("category", "field_photo")
                    a["asset_type"] = cat
                    a["confidence"] = res.get("confidence", 1.0)
                    if cat in classified:
                        classified[cat].append(a)
                    else:
                        classified["field_photo"].append(a)
                except Exception as e:
                    logger.error(f"Classification failed for {a}: {e}")
                    classified["field_photo"].append(a)

    return ToolResult(
        success=True,
        data=classified,
        summary="资产智能分类完成",
    )

