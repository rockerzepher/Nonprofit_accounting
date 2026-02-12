"""Bank statement CSV parser service."""

import csv
import io
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.accounting import Transaction


# Common date formats found in bank CSVs
_DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%m/%d/%y", "%d/%m/%Y"]


def parse_date(raw: str) -> date:
    """Try common date formats and return a date object."""
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {raw}")


def _detect_columns(headers: list[str]) -> dict:
    """Map CSV headers to our expected fields using fuzzy matching."""
    mapping = {}
    normalised = [h.strip().lower().replace(" ", "_") for h in headers]

    date_keywords = ["date", "posted", "post_date", "transaction_date", "posting_date"]
    desc_keywords = ["description", "memo", "details", "narrative", "transaction_description", "payee"]
    amount_keywords = ["amount", "transaction_amount"]
    debit_keywords = ["debit", "withdrawal", "withdrawals", "debit_amount"]
    credit_keywords = ["credit", "deposit", "deposits", "credit_amount"]
    ref_keywords = ["reference", "ref", "check_number", "check_no", "check#", "reference_number"]

    for i, col in enumerate(normalised):
        if not mapping.get("date") and any(k in col for k in date_keywords):
            mapping["date"] = i
        elif not mapping.get("description") and any(k in col for k in desc_keywords):
            mapping["description"] = i
        elif not mapping.get("amount") and any(k == col for k in amount_keywords):
            mapping["amount"] = i
        elif not mapping.get("debit") and any(k in col for k in debit_keywords):
            mapping["debit"] = i
        elif not mapping.get("credit") and any(k in col for k in credit_keywords):
            mapping["credit"] = i
        elif not mapping.get("reference") and any(k in col for k in ref_keywords):
            mapping["reference"] = i

    if "date" not in mapping:
        raise ValueError("Could not find a date column in the CSV.")
    if "description" not in mapping:
        raise ValueError("Could not find a description column in the CSV.")
    if "amount" not in mapping and "debit" not in mapping:
        raise ValueError("Could not find an amount, debit, or credit column.")

    return mapping


def _parse_amount(raw: str) -> Optional[float]:
    """Parse a monetary amount string, return None if empty."""
    raw = raw.strip().replace("$", "").replace(",", "").replace("(", "-").replace(")", "")
    if not raw or raw == "-":
        return None
    return float(raw)


def parse_csv(file_bytes: bytes, org_id: int, db: Session) -> list[Transaction]:
    """Parse a bank statement CSV and create Transaction records.

    Convention: positive amount = money IN (income), negative = money OUT (expense).
    """
    text = file_bytes.decode("utf-8-sig")  # handle BOM
    reader = csv.reader(io.StringIO(text))
    headers = next(reader)
    col_map = _detect_columns(headers)

    transactions: list[Transaction] = []

    for row_num, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue  # skip blank rows

        try:
            txn_date = parse_date(row[col_map["date"]])
        except (ValueError, IndexError):
            continue

        description = row[col_map["description"]].strip() if col_map.get("description") is not None else ""

        # Determine amount
        if "amount" in col_map:
            raw_amount = _parse_amount(row[col_map["amount"]])
            if raw_amount is None:
                continue
            amount = raw_amount
        else:
            debit = _parse_amount(row[col_map["debit"]]) if "debit" in col_map else None
            credit = _parse_amount(row[col_map["credit"]]) if "credit" in col_map else None
            if debit and debit > 0:
                amount = -abs(debit)  # money out
            elif credit and credit > 0:
                amount = abs(credit)  # money in
            else:
                continue

        txn_type = "income" if amount >= 0 else "expense"
        reference = row[col_map["reference"]].strip() if "reference" in col_map and col_map["reference"] < len(row) else None

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
