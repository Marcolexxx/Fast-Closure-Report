from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.tools.base import TaskContext, ToolResult

logger = logging.getLogger(__name__)

# PRD §7.3 R-01: 误差阈值
WARN_THRESHOLD = 0.10   # > 10% → block, Agent 必须向用户确认


async def validate_quantity(input: dict, context: TaskContext) -> ToolResult:
    """
    PRD §7.3 Tool 7: validate_quantity — 数量校验
    
    Rules:
    - R-01: 误差 ≤10% → pass (直接继续)
    - R-01: 误差 >10% → BUSINESS error; Agent MUST ask user to confirm before continuing
    - Only is_confirmed=true annotations count toward actual_qty
    - user_confirmed=true in input means user already approved override
    """
    items: List[Dict[str, Any]] = input.get("items") or []
    # actual_qty_map: {item_name: count_of_confirmed_annotations}
    actuals: Dict[str, int] = input.get("actual_qty_map") or input.get("actuals") or {}
    # If user already explicitly confirmed to override a previous block, allow continuation
    user_confirmed: bool = bool(input.get("user_confirmed", False))

    checks: List[Dict[str, Any]] = []
    overall = "pass"
    blocked_items: List[str] = []

    for it in items:
        name = it.get("name") or ""
        target = int(it.get("target_qty") or 0)
        # PRD R-01: AI候选框未经人工确认不计入数量
        actual = int(actuals.get(name, 0))
        
        if target == 0:
            status = "pass"
            delta_pct = 0.0
        else:
            delta_pct = (actual - target) / target
            if abs(delta_pct) > WARN_THRESHOLD:
                status = "block"
                overall = "block"
                blocked_items.append(name)
            else:
                status = "pass"

        checks.append({
            "item_name": name,
            "target_qty": target,
            "actual_qty": actual,
            "delta_pct": round(delta_pct * 100, 1),
            "status": status,
        })
        logger.info(
            "quantity_check",
            extra={"item": name, "target": target, "actual": actual, "status": status, "trace_id": context.trace_id},
        )

    if overall == "block" and not user_confirmed:
        # PRD R-01: Agent 必须提问 — 不能静默继续
        shortage_desc = "; ".join(
            f"[{c['item_name']}] 实际{c['actual_qty']}/目标{c['target_qty']} (差{c['delta_pct']}%)"
            for c in checks if c["status"] == "block"
        )
        return ToolResult(
            success=False,
            error_type="BUSINESS",
            error_code="QUANTITY_SHORTAGE",
            message=f"以下物料数量不足（偏差>10%），财务可能拒审：{shortage_desc}",
            data={
                "checks": checks,
                "overall": overall,
                "blocked_items": blocked_items,
                "needs_confirmation": True,
                "question": (
                    f"以下物料标注数量不足，偏差超过10%，财务可能拒审：\n{shortage_desc}\n\n"
                    f"是否仍然继续生成结案报告？（回复「是」则携带 user_confirmed=true 重新调用本工具）"
                ),
            },
            summary=f"数量校验：{len(blocked_items)} 个物料数量不足，需要您确认是否继续",
        )

    return ToolResult(
        success=True,
        data={"checks": checks, "overall": overall, "user_confirmed": user_confirmed},
        summary=(
            f"数量校验通过：共 {len(checks)} 项，全部在10%误差内"
            if overall == "pass"
            else f"数量校验：用户已确认继续，{len(blocked_items)} 个物料数量不足"
        ),
    )

