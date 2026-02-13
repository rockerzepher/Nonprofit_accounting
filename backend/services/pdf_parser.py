"""Bank statement PDF parser service.

Extracts transaction rows from PDF bank statements using pypdfium2.
Handles common bank statement layouts by looking for lines that start with a date.
"""

import re
from datetime import datetime, date
from typing import Optional

import pypdfium2
from sqlalchemy.orm import Session

from backend.models.accounting import Transaction
from backend.services.csv_parser import _parse_amount

# Month abbreviations for "Jan 15" / "January 15" style dates
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Pattern: MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD (with 2 or 4 digit year)
_DATE_SLASH_RE = re.compile(
    r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b"
)

# Pattern: MM/DD (no year, very common in bank statements)
_DATE_SHORT_RE = re.compile(
    r"^\s*(\d{1,2}/\d{1,2})\b(?!/)"  # MM/DD but not MM/DD/YY
)

# Pattern: "Jan 15" or "January 15" or "Jan 15, 2026"
_DATE_MONTH_RE = re.compile(
    r"^\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)\b",
    re.IGNORECASE,
)

# Pattern: monetary amount like $1,234.56 or (1,234.56) or -1234.56
_AMOUNT_RE = re.compile(
    r"[($-]*\$?\s*[\d,]+\.\d{2}\)?"
)

# Date formats to try for slash/dash dates
_DATE_FORMATS = [
    "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y",
    "%d/%m/%Y", "%d/%m/%y",
]


def _parse_date_str(raw: str, statement_year: Optional[int] = None) -> Optional[date]:
    """Parse a date string in various formats, return None if unparseable."""
    raw = raw.strip().rstrip(",")

    # Try slash/dash formats with year
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    # Try MM/DD without year
    try:
        dt = datetime.strptime(raw, "%m/%d")
        year = statement_year or datetime.now().year
        return dt.replace(year=year).date()
    except ValueError:
        pass

    # Try "Jan 15" or "January 15" or "Jan 15, 2026"
    m = re.match(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?",
        raw, re.IGNORECASE,
    )
    if m:
        month_str = m.group(1).lower()[:3]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else (statement_year or datetime.now().year)
        month = _MONTHS.get(month_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def _extract_amount(text: str) -> Optional[float]:
    """Find and parse the first monetary amount in a text fragment."""
    matches = _AMOUNT_RE.findall(text)
    if not matches:
        return None
    # If there are 2+ amounts, first is transaction amount, last is balance
    raw = matches[0] if len(matches) >= 2 else matches[-1]
    return _parse_amount(raw)


def _extract_description(text: str, date_str: str) -> str:
    """Extract the description portion from a transaction line."""
    # Remove the date from the beginning
    desc = text.replace(date_str, "", 1).strip()
    # Remove all dollar amounts
    desc = _AMOUNT_RE.sub("", desc).strip()
    # Clean up extra whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF using pypdfium2."""
    pdf = pypdfium2.PdfDocument(file_bytes)
    pages_text = []
    for page in pdf:
        textpage = page.get_textpage()
        pages_text.append(textpage.get_text_range())
        textpage.close()
        page.close()
    pdf.close()
    return "\n".join(pages_text)


def _detect_statement_year(text: str) -> Optional[int]:
    """Try to find the statement year from header text like 'Statement Period: 01/01/2026 - 01/31/2026'."""
    m = re.search(r"20\d{2}", text[:500])
    if m:
        return int(m.group())
    return None


def parse_pdf(file_bytes: bytes, org_id: int, db: Session) -> list[Transaction]:
    """Parse a bank statement PDF and create Transaction records.

    Strategy:
    1. Extract all text from the PDF
    2. Find lines that start with a date pattern (multiple formats)
    3. Extract description and amount from each such line
    4. Create Transaction records

    Returns a tuple of (transactions, debug_info) where debug_info
    contains extracted text for troubleshooting.
    """
    text = _extract_text_from_pdf(file_bytes)
    lines = text.split("\n")
    statement_year = _detect_statement_year(text)

    transactions: list[Transaction] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try each date pattern
        date_str = None
        txn_date = None

        # 1. Full date with year (MM/DD/YYYY etc.)
        m = _DATE_SLASH_RE.match(line)
        if m:
            date_str = m.group(1).strip()
            txn_date = _parse_date_str(date_str, statement_year)

        # 2. Short date MM/DD (no year)
        if not txn_date:
            m = _DATE_SHORT_RE.match(line)
            if m:
                date_str = m.group(1).strip()
                txn_date = _parse_date_str(date_str, statement_year)

        # 3. Month name format (Jan 15, January 15, etc.)
        if not txn_date:
            m = _DATE_MONTH_RE.match(line)
            if m:
                date_str = m.group(1).strip()
                txn_date = _parse_date_str(date_str, statement_year)

        if not txn_date or not date_str:
            continue

        # Extract amount(s) from the line
        amount_matches = _AMOUNT_RE.findall(line)
        if not amount_matches:
            continue

        # Heuristic: if multiple amounts, first is transaction amount, last is balance
        raw_amount = amount_matches[0] if len(amount_matches) >= 2 else amount_matches[-1]
        amount = _parse_amount(raw_amount)
        if amount is None or amount == 0:
            continue

        description = _extract_description(line, date_str)
        if not description:
            continue

        txn_type = "income" if amount >= 0 else "expense"

        txn = Transaction(
            organization_id=org_id,
            date=txn_date,
            description=description,
            amount=amount,
            transaction_type=txn_type,
            payee=description,
            source="pdf_import",
        )
        db.add(txn)
        transactions.append(txn)

    db.commit()
    for t in transactions:
        db.refresh(t)
    return transactions


def extract_pdf_debug_text(file_bytes: bytes) -> str:
    """Return the raw text extracted from a PDF, for debugging."""
    return _extract_text_from_pdf(file_bytes)
