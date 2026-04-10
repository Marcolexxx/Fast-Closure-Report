from __future__ import annotations

import logging
import os
import shutil
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

from werkzeug.utils import secure_filename

from app.security.path_validator import PathValidator
from app.tools.base import TaskContext, ToolResult
from app.shared.vision_adapter import get_vision_adapter
from app.shared.ocr import extract_structured_fields

logger = logging.getLogger(__name__)

# Fields compared between the two extraction paths
_COMPARABLE_FIELDS = ("amount", "date", "merchant", "invoice_no")


def _parse_amount(raw: Any) -> Optional[Decimal]:
    """Parse amount string to Decimal; supports negative (冲红) amounts."""
    if raw is None:
        return None
    try:
        s = str(raw).replace("¥", "").replace("￥", "").replace(",", "").strip()
        return Decimal(s)
    except InvalidOperation:
        return None


def _cross_validate(
    pdf_result: Dict[str, Any],
    vision_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    PRD §7.3 Tool 8: compare two extraction paths field by field.
    Returns merged result with low_confidence_fields marking any disagreements.
    """
    merged: Dict[str, Any] = {}
    low_confidence: Dict[str, str] = {}

    for field in _COMPARABLE_FIELDS:
        v_pdf = pdf_result.get(field)
        v_vis = vision_result.get(field)

        if v_pdf is not None and v_vis is not None:
            # Normalize amounts for comparison
            if field == "amount":
                d_pdf = _parse_amount(v_pdf)
                d_vis = _parse_amount(v_vis)
                if d_pdf != d_vis:
                    low_confidence[field] = f"pdf={v_pdf} vision={v_vis}"
                merged[field] = str(d_pdf) if d_pdf is not None else v_pdf
            else:
                if str(v_pdf).strip() != str(v_vis).strip():
                    low_confidence[field] = f"pdf={v_pdf} vision={v_vis}"
                # Prefer pdf path (usually more accurate for text) 
                merged[field] = v_pdf
        elif v_pdf is not None:
            merged[field] = v_pdf
        elif v_vis is not None:
            merged[field] = v_vis
            low_confidence[field] = "pdf_path_missing"
        else:
            merged[field] = None
            low_confidence[field] = "both_paths_missing"

    # Confidence: lower if any field is disagreed
    confidence = 0.5 if low_confidence else 0.95
    merged["ocr_confidence"] = confidence
    merged["low_confidence_fields"] = low_confidence
    return merged


async def ocr_receipt(input: dict, context: TaskContext) -> ToolResult:
    """
    PRD §7.3 Tool 8: ocr_receipt — 凭据 OCR 识别（双路交叉验证）
    
    - PDF → pdfplumber 文字提取 + 正则匹配（精确路径）
    - 图片 → 本地 LLM Vision（图片不出内网）
    - 两路交叉验证：不一致字段标 low_confidence_fields
    - 支持负数/冲红发票（amount 允许 Decimal 负值）
    - 金额一律使用 Decimal，禁止 float
    """
    if input.get("receipts") or input.get("ocr_results"):
        receipts = input.get("receipts") or input.get("ocr_results") or []
        return ToolResult(success=True, data={"receipts": receipts}, summary=f"OCR 凭据结构化完成：{len(receipts)} 条")

    files = input.get("receipt_files") or []
    if not isinstance(files, list) or not files:
        return ToolResult(
            success=False,
            error_type="BUSINESS",
            error_code="MISSING_RECEIPT_FILES",
            message="receipt_files is required",
            summary="缺少 receipt_files",
        )

    pv = PathValidator(root_dir=input.get("storage_root") or "/data")
    vision = await get_vision_adapter()
    receipts: List[Dict[str, Any]] = []
    low_confidence_count = 0

    for f in files[:100]:   # PRD §7.2: 最多 100 份
        # --- Security: sanitize filename to prevent path traversal ---
        raw_name = Path(str(f)).name
        clean_name = secure_filename(raw_name)
        if not clean_name:
            logger.warning(f"Filename rejected after sanitization: {f}", extra={"trace_id": context.trace_id})
            continue

        # Reconstruct path using sanitized name under the same parent dir
        sanitized_f = str(Path(str(f)).parent / clean_name)

        ok, safe_path = pv.validate(sanitized_f)
        if not ok:
            logger.warning(f"Invalid path skipped after sanitization: {f}", extra={"trace_id": context.trace_id})
            continue
        p = Path(safe_path)

        # Track any temp files created during this iteration for cleanup
        _temp_files: List[str] = []
        try:
            if p.suffix.lower() == ".pdf":
                # PRIMARY: pdfplumber text extraction + regex
                pdf_result = extract_structured_fields(p)

                # SECONDARY: optionally run vision path for cross-validation if pdf_result has missing fields
                missing = [k for k in _COMPARABLE_FIELDS if pdf_result.get(k) is None]
                if missing:
                    try:
                        vision_result = await vision.extract_receipt_fields(str(safe_path))
                    except Exception:
                        vision_result = {}
                    receipt = _cross_validate(pdf_result, vision_result)
                else:
                    # PDF path was complete — mark high confidence directly
                    receipt = {**pdf_result, "ocr_confidence": 0.95, "low_confidence_fields": {}}
            else:
                # Image path → Local LLM Vision only (图片不出内网)
                vision_result = await vision.extract_receipt_fields(str(safe_path))
                receipt = {
                    "amount": str(_parse_amount(vision_result.get("amount"))) if vision_result.get("amount") else None,
                    "date": vision_result.get("date"),
                    "merchant": vision_result.get("merchant"),
                    "invoice_no": vision_result.get("invoice_no"),
                    "ocr_confidence": float(vision_result.get("confidence", 0.8)),
                    "low_confidence_fields": {},
                }

            # Detect low-confidence fields
            if receipt.get("low_confidence_fields"):
                low_confidence_count += 1

            # PRD R-04: support negative amounts (冲红发票)
            amount_dec = _parse_amount(receipt.get("amount"))
            receipt["amount"] = str(amount_dec) if amount_dec is not None else None
            receipt["is_void"] = (amount_dec is not None and amount_dec < 0)
            receipt["type"] = "invoice" if p.suffix.lower() == ".pdf" else "payment"
            receipt["source_path"] = str(safe_path)

            receipts.append(receipt)
            logger.info(
                "ocr_receipt_done",
                extra={
                    "path": str(safe_path),
                    "confidence": receipt.get("ocr_confidence"),
                    "low_conf_fields": list(receipt.get("low_confidence_fields", {}).keys()),
                    "trace_id": context.trace_id,
                },
            )
        except Exception as e:
            logger.error(f"OCR failed for {safe_path}: {e}", extra={"trace_id": context.trace_id})
            receipts.append({
                "type": "receipt",
                "amount": None,
                "date": None,
                "merchant": None,
                "invoice_no": None,
                "ocr_confidence": 0.0,
                "low_confidence_fields": {"all": "parse_failed"},
                "is_void": False,
                "source_path": str(safe_path),
            })
            low_confidence_count += 1
        finally:
            # Guarantee cleanup of any intermediate temp files created during this iteration
            for tmp in _temp_files:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError as cleanup_err:
                    logger.warning(f"Temp file cleanup failed: {tmp} — {cleanup_err}")

    return ToolResult(
        success=True,
        data={"receipts": receipts, "low_confidence_count": low_confidence_count},
        summary=(
            f"OCR 凭据识别完成：共 {len(receipts)} 条，"
            f"其中 {low_confidence_count} 条存在低置信字段需人工确认"
            if low_confidence_count
            else f"OCR 凭据识别完成：共 {len(receipts)} 条（全部高置信）"
        ),
    )


