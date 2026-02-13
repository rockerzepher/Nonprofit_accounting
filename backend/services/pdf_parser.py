"""Bank statement PDF parser service.

Extracts transaction rows from PDF bank statements using pypdfium2.
Handles common bank statement layouts by looking for lines that start with a date.
"""

import re
from typing import Optional

import pypdfium2
from sqlalchemy.orm import Session

from backend.models.accounting import Transaction
from backend.services.csv_parser import parse_date, _parse_amount


# Pattern: line starts with a date like 01/15/2026, 2026-01-15, 01-15-2026, etc.
_DATE_LINE_RE = re.compile(
    r"^\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\s+"
)

# Pattern: monetary amount like $1,234.56 or (1,234.56) or -1234.56
_AMOUNT_RE = re.compile(
    r"[($-]*\$?\s*[\d,]+\.\d{2}\)?"
)


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


def parse_pdf(file_bytes: bytes, org_id: int, db: Session) -> list[Transaction]:
    """Parse a bank statement PDF and create Transaction records.

    Strategy:
    1. Extract all text from the PDF
    2. Find lines that start with a date pattern
    3. Extract description and amount from each such line
    4. Create Transaction records
    """
    text = _extract_text_from_pdf(file_bytes)
    lines = text.split("\n")

    transactions: list[Transaction] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = _DATE_LINE_RE.match(line)
        if not match:
            continue

        date_str = match.group(1).strip()

        try:
            txn_date = parse_date(date_str)
        except ValueError:
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
