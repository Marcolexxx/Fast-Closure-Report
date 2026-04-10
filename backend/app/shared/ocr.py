import re
from pathlib import Path
from typing import Any, Dict

_AMOUNT_RE = re.compile(r"(?P<amount>\d+(?:\.\d{1,2})?)")
_DATE_RE = re.compile(r"(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2})")
_INV_RE = re.compile(r"(发票|票据|invoice)\s*[:：]?\s*(?P<inv>[A-Za-z0-9\-]{3,})", re.IGNORECASE)

def extract_structured_fields(path: Path) -> Dict[str, Any]:
    """
    Extracts structured fields from a PDF invoice using pdfplumber.
    """
    if path.suffix.lower() != ".pdf":
        raise ValueError("extract_structured_fields currently optimized for PDF invoices.")
        
    try:
        import pdfplumber  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing pdfplumber dependency for local PDF extraction") from e

    texts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages[:5]:
            txt = page.extract_text() or ""
            if txt:
                texts.append(txt)
    text = "\n".join(texts).strip()

    amount = None
    date = None
    invoice_no = None

    m = _DATE_RE.search(text)
    if m:
        date = m.group("date").replace("/", "-")
    m = _INV_RE.search(text)
    if m:
        invoice_no = m.group("inv")

    amounts = [float(x.group("amount")) for x in _AMOUNT_RE.finditer(text)]
    if amounts:
        amount = max(amounts) # naive but useful heuristic

    return {
        "type": "invoice",
        "amount": amount,
        "date": date,
        "merchant": None,
        "invoice_no": invoice_no,
        "confidence": 0.85
    }
