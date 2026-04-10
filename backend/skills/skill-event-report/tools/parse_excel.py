from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.security.path_validator import PathValidator
from app.tools.base import TaskContext, ToolResult
from app.shared.excel import parse_spreadsheet, ColumnAmbiguityError

logger = logging.getLogger(__name__)

async def parse_excel(input: dict, context: TaskContext) -> ToolResult:
    """
    Parse an Excel material list into normalized items.
    PRD §7.3: Levenshtein-based column mapping; ambiguous columns trigger
    BUSINESS error with needs_clarification payload for Agent to ask user.
    """

    if input.get("items"):
        items = input["items"]
        return ToolResult(success=True, data={"items": items}, summary=f"解析完成：共 {len(items)} 个预置物料")

    excel_path = input.get("excel_path")
    if not excel_path:
        return ToolResult(success=False, error_type="BUSINESS", error_code="MISSING_EXCEL", message="excel_path is required", summary="缺少 excel_path")

    pv = PathValidator(root_dir=input.get("storage_root") or "/data")
    ok, safe_path = pv.validate(excel_path)
    if not ok:
        return ToolResult(success=False, error_type="BUSINESS", error_code="INVALID_PATH", message="invalid excel_path", summary="excel_path 非法")

    sheet_name = input.get("sheet_name")

    try:
        items = parse_spreadsheet(safe_path, sheet_name)
    except ColumnAmbiguityError as e:
        # PRD §7.3: ambiguous column detected → Agent must ask user to choose
        logger.warning(f"Column ambiguity detected: {e}")
        return ToolResult(
            success=False,
            error_type="BUSINESS",
            error_code="COLUMN_AMBIGUITY",
            message=str(e),
            data={
                "needs_clarification": True,
                "ambiguous_hint": e.hint,
                "candidates": e.candidates,
                "question": (
                    f"Excel 表中存在多个列名与「{e.hint}」相似，请告知哪一列是正确的物料名称列？"
                    f"候选列：{[c['column'] for c in e.candidates]}"
                ),
            },
            summary=f"列名歧义：发现 {len(e.candidates)} 个候选列，需要您确认",
        )
    except ValueError as e:
        logger.error(f"Spreadsheet parsing error: {e}")
        return ToolResult(
            success=False,
            error_type="BUSINESS",
            error_code="EXCEL_PARSE_ERROR",
            message=str(e),
            summary=f"Excel 解析失败: {e}",
        )
    except Exception as e:
        logger.exception("Unexpected error in Excel parser")
        return ToolResult(
            success=False,
            error_type="SYSTEM",
            error_code="INTERNAL_ERROR",
            message="Internal server error during parsing",
            summary="内部解析错误",
        )

    return ToolResult(
        success=True,
        data={"items": items},
        summary=f"Excel 智能提取完成：共提取 {len(items)} 个有效物料行",
    )

