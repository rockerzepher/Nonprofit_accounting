"""Bank statement CSV parser service."""

import csv
import io
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.accounting import Transaction


# Common date formats found in bank CSVs
_DATE_FORMATS = [
    "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y",
    "%m.%d.%Y", "%d.%m.%Y", "%Y.%m.%d",
    "%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y",
]


def parse_date(raw: str) -> date:
    """Try common date formats and return a date object."""
    raw = raw.strip().strip('"').strip("'")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {raw}")


def _detect_delimiter(text: str) -> str:
    """Auto-detect CSV delimiter by checking first few lines."""
    first_lines = text.split("\n", 5)[:5]
    for delim in [",", "\t", ";", "|"]:
        counts = [line.count(delim) for line in first_lines if line.strip()]
        if counts and min(counts) >= 1 and max(counts) - min(counts) <= 2:
            return delim
    return ","


def _find_header_row(text: str, delimiter: str) -> tuple[int, list[str]]:
    """Find the actual header row, skipping preamble lines.

    Many bank CSVs have bank name, account info, date range etc.
    before the actual column headers. We look for the first row that
    contains date-like and amount-like column names.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    date_keywords = {"date", "posted", "post_date", "transaction_date",
                     "posting_date", "trans_date", "effective_date", "process_date"}
    amount_keywords = {"amount", "transaction_amount", "debit", "credit",
                       "withdrawal", "deposit", "withdrawals", "deposits",
                       "debit_amount", "credit_amount", "money_in", "money_out"}

    for row_idx, row in enumerate(reader):
        normalised = [h.strip().lower().replace(" ", "_") for h in row]
        has_date = any(any(k in col for k in date_keywords) for col in normalised)
        has_amount = any(any(k in col for k in amount_keywords) for col in normalised)
        if has_date and has_amount:
            return row_idx, row
        # Also detect if a row has "date" anywhere — some CSVs just have Date + Description
        if has_date and len(row) >= 2:
            return row_idx, row

    # Fallback: use first non-empty row as headers
    return 0, []


def _detect_columns(headers: list[str]) -> dict:
    """Map CSV headers to our expected fields using fuzzy matching."""
    mapping = {}
    normalised = [h.strip().lower().replace(" ", "_") for h in headers]

    date_keywords = ["date", "posted", "post_date", "transaction_date",
                     "posting_date", "trans_date", "effective_date", "process_date"]
    desc_keywords = ["description", "memo", "details", "narrative",
                     "transaction_description", "payee", "name", "particulars"]
    amount_keywords = ["amount", "transaction_amount", "sum", "value"]
    debit_keywords = ["debit", "withdrawal", "withdrawals", "debit_amount",
                      "money_out", "payments", "charges"]
    credit_keywords = ["credit", "deposit", "deposits", "credit_amount",
                       "money_in", "receipts"]
    ref_keywords = ["reference", "ref", "check_number", "check_no", "check#",
                    "reference_number", "cheque", "serial"]
    # balance column — we want to detect this so we DON'T confuse it with amount
    balance_keywords = ["balance", "running_balance", "available_balance", "ledger_balance"]

    balance_cols = set()
    for i, col in enumerate(normalised):
        if any(k in col for k in balance_keywords):
            balance_cols.add(i)

    for i, col in enumerate(normalised):
        if i in balance_cols:
            continue
        if not mapping.get("date") and any(k in col for k in date_keywords):
            mapping["date"] = i
        elif not mapping.get("description") and any(k in col for k in desc_keywords):
            mapping["description"] = i
        elif not mapping.get("amount") and any(k in col for k in amount_keywords):
            mapping["amount"] = i
        elif not mapping.get("debit") and any(k in col for k in debit_keywords):
            mapping["debit"] = i
        elif not mapping.get("credit") and any(k in col for k in credit_keywords):
            mapping["credit"] = i
        elif not mapping.get("reference") and any(k in col for k in ref_keywords):
            mapping["reference"] = i

    # If we still don't have a description column, use the column right after date
    if "description" not in mapping and "date" in mapping:
        date_idx = mapping["date"]
        for i in range(len(normalised)):
            if i != date_idx and i not in balance_cols and i not in mapping.values():
                # Check it's not a numeric-looking column name
                if not any(k in normalised[i] for k in amount_keywords + debit_keywords + credit_keywords):
                    mapping["description"] = i
                    break

    if "date" not in mapping:
        raise ValueError("Could not find a date column in the CSV. "
                         "Expected columns like: Date, Posted, Transaction Date")
    if "description" not in mapping:
        raise ValueError("Could not find a description column in the CSV. "
                         "Expected columns like: Description, Memo, Details, Payee")
    if "amount" not in mapping and "debit" not in mapping:
        raise ValueError("Could not find an amount, debit, or credit column. "
                         "Expected columns like: Amount, Debit, Credit, Withdrawal, Deposit")

    return mapping


def _parse_amount(raw: str) -> Optional[float]:
    """Parse a monetary amount string, return None if empty."""
    raw = raw.strip().replace("$", "").replace(",", "")
    # Handle parenthetical negatives: (123.45) -> -123.45
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    raw = raw.strip()
    if not raw or raw == "-" or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_csv(file_bytes: bytes, org_id: int, db: Session) -> list[Transaction]:
    """Parse a bank statement CSV and create Transaction records.

    Convention: positive amount = money IN (income), negative = money OUT (expense).
    Handles various delimiters, preamble rows, and column naming conventions.
    """
    # Try utf-8 with BOM, fall back to latin-1
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    delimiter = _detect_delimiter(text)
    header_row_idx, header_row = _find_header_row(text, delimiter)

    # Re-read from the header row onwards
    lines = text.split("\n")
    remaining_text = "\n".join(lines[header_row_idx:])
    reader = csv.reader(io.StringIO(remaining_text), delimiter=delimiter)

    # First row of remaining_text is the headers
    headers = next(reader)
    col_map = _detect_columns(headers)

    transactions: list[Transaction] = []

    for row_num, row in enumerate(reader, start=header_row_idx + 2):
        if not any(cell.strip() for cell in row):
            continue  # skip blank rows

        try:
            txn_date = parse_date(row[col_map["date"]])
        except (ValueError, IndexError):
            continue

        desc_idx = col_map.get("description")
        description = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) else ""

        # Determine amount
        if "amount" in col_map:
            raw_amount = _parse_amount(row[col_map["amount"]]) if col_map["amount"] < len(row) else None
            if raw_amount is None:
                # If single amount column is empty, try debit/credit as fallback
                if "debit" in col_map or "credit" in col_map:
                    raw_amount = _get_debit_credit_amount(row, col_map)
                if raw_amount is None:
                    continue
            amount = raw_amount
        else:
            amount = _get_debit_credit_amount(row, col_map)
            if amount is None:
                continue

        txn_type = "income" if amount >= 0 else "expense"
        reference = (row[col_map["reference"]].strip()
                     if "reference" in col_map and col_map["reference"] < len(row)
                     else None)

        txn = Transaction(
            organization_id=org_id,
            date=txn_date,
            description=description,
            amount=amount,
            transaction_type=txn_type,
            reference=reference,
            payee=description,
            source="csv_import",
        )
        db.add(txn)
        transactions.append(txn)

    db.commit()
    for t in transactions:
        db.refresh(t)
    return transactions


def _get_debit_credit_amount(row: list[str], col_map: dict) -> Optional[float]:
    """Calculate amount from separate debit/credit columns."""
    debit = (_parse_amount(row[col_map["debit"]])
             if "debit" in col_map and col_map["debit"] < len(row) else None)
    credit = (_parse_amount(row[col_map["credit"]])
              if "credit" in col_map and col_map["credit"] < len(row) else None)
    if debit and debit > 0:
        return -abs(debit)  # money out
    elif credit and credit > 0:
        return abs(credit)  # money in
    elif debit and debit < 0:
        return debit  # already negative
    elif credit and credit < 0:
        return abs(credit)  # negative credit = money in
    return None
