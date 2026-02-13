"""Bank statement PDF parser service.

Extracts transaction rows from PDF bank statements using pypdfium2.
Handles common bank statement layouts by looking for lines that contain a date.
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
# Matches anywhere in the line (not just start)
_DATE_SLASH_RE = re.compile(
    r"(?:^|\s)(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b"
)

# Pattern: MM/DD (no year, very common in bank statements)
_DATE_SHORT_RE = re.compile(
    r"(?:^|\s)(\d{1,2}/\d{1,2})\b(?!/)"  # MM/DD but not MM/DD/YY
)

# Pattern: "Jan 15" or "January 15" or "Jan 15, 2026"
_DATE_MONTH_RE = re.compile(
    r"(?:^|\s)((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?)\b",
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

# Lines that are likely headers/footers, not transactions
_SKIP_PATTERNS = re.compile(
    r"(?i)(?:page\s+\d|continued|balance\s+forward|opening\s+balance|"
    r"closing\s+balance|statement\s+period|account\s+number|"
    r"total\s+(?:debits?|credits?|deposits?|withdrawals?)|"
    r"beginning\s+balance|ending\s+balance|account\s+summary)",
)


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


def _find_date_in_line(line: str, statement_year: Optional[int] = None) -> tuple[Optional[date], Optional[str]]:
    """Find a date anywhere in the line (not just at the start).

    Returns (parsed_date, raw_date_string) or (None, None).
    """
    # 1. Full date with year (MM/DD/YYYY etc.)
    m = _DATE_SLASH_RE.search(line)
    if m:
        date_str = m.group(1).strip()
        txn_date = _parse_date_str(date_str, statement_year)
        if txn_date:
            return txn_date, date_str

    # 2. Month name format (Jan 15, January 15, etc.)
    m = _DATE_MONTH_RE.search(line)
    if m:
        date_str = m.group(1).strip()
        txn_date = _parse_date_str(date_str, statement_year)
        if txn_date:
            return txn_date, date_str

    # 3. Short date MM/DD (no year) — try last to avoid false positives
    m = _DATE_SHORT_RE.search(line)
    if m:
        date_str = m.group(1).strip()
        txn_date = _parse_date_str(date_str, statement_year)
        if txn_date:
            return txn_date, date_str

    return None, None


def _extract_description(text: str, date_str: str) -> str:
    """Extract the description portion from a transaction line."""
    # Remove the date from the line
    desc = text.replace(date_str, "", 1).strip()
    # Remove all dollar amounts
    desc = _AMOUNT_RE.sub("", desc).strip()
    # Clean up extra whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    # Remove leading/trailing punctuation artifacts
    desc = desc.strip("-–—:;,.")
    return desc.strip()


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
    """Try to find the statement year from header text."""
    # Look for year in statement period, date range, etc.
    m = re.search(r"20\d{2}", text[:1000])
    if m:
        return int(m.group())
    return None


def parse_pdf(file_bytes: bytes, org_id: int, db: Session) -> list[Transaction]:
    """Parse a bank statement PDF and create Transaction records.

    Strategy:
    1. Extract all text from the PDF
    2. Find lines that contain a date pattern (multiple formats, anywhere in line)
    3. Extract description and amount from each such line
    4. Handle continuation lines (description on next line with no date)
    5. Create Transaction records
    """
    text = _extract_text_from_pdf(file_bytes)
    lines = text.split("\n")
    statement_year = _detect_statement_year(text)

    transactions: list[Transaction] = []
    pending_txn = None  # for multi-line transaction handling

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip header/footer lines
        if _SKIP_PATTERNS.search(line):
            continue

        # Try to find a date in this line
        txn_date, date_str = _find_date_in_line(line, statement_year)

        if txn_date and date_str:
            # If we had a pending transaction without an amount, discard it
            # and start fresh with this line
            if pending_txn:
                _finalize_transaction(pending_txn, transactions, org_id, db)
                pending_txn = None

            # Extract amount(s) from the line
            amount_matches = _AMOUNT_RE.findall(line)
            description = _extract_description(line, date_str)

            if amount_matches:
                # Heuristic: if multiple amounts, first is transaction amount, last is balance
                raw_amount = amount_matches[0] if len(amount_matches) >= 2 else amount_matches[-1]
                amount = _parse_amount(raw_amount)
                if amount is not None and amount != 0 and description:
                    pending_txn = {
                        "date": txn_date,
                        "description": description,
                        "amount": amount,
                    }
            elif description:
                # Date found but no amount yet — might be on the next line
                pending_txn = {
                    "date": txn_date,
                    "description": description,
                    "amount": None,
                }
        elif pending_txn and pending_txn["amount"] is None:
            # Continuation line — check if it has an amount
            amount_matches = _AMOUNT_RE.findall(line)
            if amount_matches:
                raw_amount = amount_matches[0] if len(amount_matches) >= 2 else amount_matches[-1]
                amount = _parse_amount(raw_amount)
                if amount is not None and amount != 0:
                    pending_txn["amount"] = amount
                    # Also append any extra description text
                    extra_desc = _AMOUNT_RE.sub("", line).strip()
                    if extra_desc:
                        pending_txn["description"] += " " + extra_desc
            else:
                # Continuation of description
                clean = line.strip()
                if clean and len(clean) > 2:
                    pending_txn["description"] += " " + clean

    # Finalize any remaining pending transaction
    if pending_txn:
        _finalize_transaction(pending_txn, transactions, org_id, db)

    db.commit()
    for t in transactions:
        db.refresh(t)
    return transactions


def _finalize_transaction(
    txn_data: dict,
    transactions: list[Transaction],
    org_id: int,
    db: Session,
) -> None:
    """Create a Transaction record from parsed data if valid."""
    if txn_data["amount"] is None or txn_data["amount"] == 0:
        return
    if not txn_data["description"]:
        return

    # Clean up description
    desc = re.sub(r"\s+", " ", txn_data["description"]).strip()
    amount = txn_data["amount"]
    txn_type = "income" if amount >= 0 else "expense"

    txn = Transaction(
        organization_id=org_id,
        date=txn_data["date"],
        description=desc,
        amount=amount,
        transaction_type=txn_type,
        payee=desc,
        source="pdf_import",
    )
    db.add(txn)
    transactions.append(txn)


def extract_pdf_debug_text(file_bytes: bytes) -> str:
    """Return the raw text extracted from a PDF, for debugging."""
    return _extract_text_from_pdf(file_bytes)
