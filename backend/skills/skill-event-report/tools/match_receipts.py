from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List
from itertools import combinations
from decimal import Decimal

from app.tools.base import TaskContext, ToolResult

logger = logging.getLogger(__name__)

def _parse_date(d_str: Any) -> datetime | None:
    if not d_str: return None
    try: return datetime.strptime(str(d_str), "%Y-%m-%d")
    except: return None

async def match_receipts(input: dict, context: TaskContext) -> ToolResult:
    """
    Advanced match receipts based on finance rules:
      - Phase 1: Exact matching
      - Phase 2: Subset sum matching (max 5 invoices per payment, 3000 node limit)
      - Amount difference <= 5.0
      - Date difference <= 60 days
      - Resolves negative amounts (冲红)
    """

    receipts: List[Dict[str, Any]] = input.get("receipts") or []
    payments = [r for r in receipts if r.get("type") in ("payment", "receipt")]
    invoices = [r for r in receipts if r.get("type") == "invoice"]

    matches: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []

    # Filter out voided negative invoices (冲红) - Simplified preprocessing
    valid_invoices = []
    inv_by_merchant = {}
    for inv in invoices:
        m = inv.get("merchant") or "unknown"
        if m not in inv_by_merchant:
            inv_by_merchant[m] = []
        inv_by_merchant[m].append(inv)
        
    for m, m_invs in inv_by_merchant.items():
        positive = [i for i in m_invs if Decimal(str(i.get("amount") or 0)) > 0]
        negative = [i for i in m_invs if Decimal(str(i.get("amount") or 0)) < 0]
        # Basic cancellation logic
        for neg in negative:
            neg_amt = abs(Decimal(str(neg.get("amount") or 0)))
            for pos in positive:
                if not pos.get("_void") and abs(Decimal(str(pos.get("amount") or 0)) - neg_amt) < Decimal("0.01"):
                    pos["_void"] = True
                    neg["_void"] = True
                    break
                    
    valid_invoices = [i for i in invoices if not i.get("_void")]
    inv_matched = set()

    for p in payments:
        p_amt = Decimal(str(p.get("amount") or 0))
        p_date = _parse_date(p.get("date"))
        
        best_inv_combo = None
        best_diff = Decimal("999999.0")
        best_inv_indices = []

        # Find available invoices
        avail_indices = [idx for idx, inv in enumerate(valid_invoices) if idx not in inv_matched]
        
        # Max search limits to prevent NP-Hard hang
        MAX_COMBINATIONS = 3000
        MAX_DEPTH = 5
        combo_count = 0

        # Try combinations length 1 to MAX_DEPTH
        for r in range(1, min(len(avail_indices), MAX_DEPTH) + 1):
            for combo_indices in combinations(avail_indices, r):
                combo_count += 1
                if combo_count > MAX_COMBINATIONS:
                    break
                    
                combo_amt = sum(Decimal(str(valid_invoices[i].get("amount") or 0)) for i in combo_indices)
                amt_diff = abs(p_amt - combo_amt)
                
                if amt_diff <= Decimal("5.00"):
                    # Check dates
                    date_valid = True
                    max_days_diff = 0
                    for i in combo_indices:
                        inv_date = _parse_date(valid_invoices[i].get("date"))
                        if p_date and inv_date:
                            days = abs((p_date - inv_date).days)
                            if days > max_days_diff: max_days_diff = days
                            if days > 60:
                                date_valid = False
                                break
                    
                    if date_valid and amt_diff < best_diff:
                        best_diff = amt_diff
                        best_inv_combo = [valid_invoices[i] for i in combo_indices]
                        best_inv_indices = list(combo_indices)
                        
            if combo_count > MAX_COMBINATIONS:
                logger.warning(f"Hit max combinations limit for payment {p.get('id')}")
                break

        if best_inv_combo:
            for i in best_inv_indices:
                inv_matched.add(i)
                
            matches.append({
                "payment": p,
                "invoices": best_inv_combo, # Schema change to support multiple
                "match_type": "auto_exact" if best_diff == Decimal("0.00") else "auto_subset",
                "amount_diff": float(best_diff),
                "date_diff_days": max_days_diff if best_inv_combo else 0,
                "confirmed_by": None,
            })
        else:
            unmatched.append(p)

    return ToolResult(
        success=True,
        data={"matches": matches, "unmatched": unmatched},
        summary=f"发票配对完成：成功匹配 {len(matches)} 组，未匹配 {len(unmatched)} 笔",
    )
