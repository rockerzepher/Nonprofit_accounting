"""Transaction classification service — keyword/pattern matching with learning."""

import re
from sqlalchemy.orm import Session

from backend.models.accounting import Transaction, Account, ClassificationRule, Fund


# Built-in keyword map: pattern → (account_sub_type, transaction_type)
_DEFAULT_PATTERNS: list[tuple[str, str, str]] = [
    # Expenses
    (r"electric|power|energy|utility|utilit|gas\b|water\b|sewage|pge|con edison|duke energy",
     "utilities", "expense"),
    (r"rent|lease|mortgage|property",
     "occupancy", "expense"),
    (r"insurance|premium|coverage",
     "insurance", "expense"),
    (r"office\s*supply|staples|office\s*depot|paper|toner",
     "supplies", "expense"),
    (r"salary|payroll|wage|adp|gusto|paychex",
     "payroll", "expense"),
    (r"travel|airline|hotel|uber|lyft|taxi|airbnb|flight",
     "travel", "expense"),
    (r"attorney|lawyer|legal|accounting|cpa|audit|consult",
     "professional", "expense"),
    (r"software|subscription|saas|cloud|aws|azure|google cloud|microsoft|adobe|zoom|slack",
     "technology", "expense"),
    (r"bank\s*fee|service\s*charge|overdraft|nsf|monthly\s*fee|maintenance\s*fee|atm\s*fee",
     "bank_fees", "expense"),
    (r"depreciation|amortization",
     "depreciation", "expense"),
    # Revenue
    (r"donation|donat|gift|contribution|tithe|offering|pledge",
     "donations", "income"),
    (r"grant|foundation|award",
     "grants", "income"),
    (r"interest\s*(income|earned|payment)|dividend",
     "interest", "income"),
    (r"tuition|enrollment|registration\s*fee",
     "program", "income"),
    (r"fundrais|gala|benefit|auction|raffle",
     "fundraising", "income"),
    (r"dues|membership",
     "program", "income"),
    (r"sponsor",
     "donations", "income"),
]


def classify_transactions(db: Session, org_id: int, transaction_ids: list[int] | None = None):
    """Classify unclassified transactions for an organization.

    First tries org-specific learned rules, then falls back to built-in patterns.
    """
    query = db.query(Transaction).filter(
        Transaction.organization_id == org_id,
        Transaction.account_id.is_(None),
    )
    if transaction_ids:
        query = query.filter(Transaction.id.in_(transaction_ids))
    txns = query.all()

    if not txns:
        return

    # Load org accounts and rules
    accounts = db.query(Account).filter(Account.organization_id == org_id).all()
    acct_by_sub = {}
    for a in accounts:
        if a.sub_type not in acct_by_sub:
            acct_by_sub[a.sub_type] = a

    learned_rules = db.query(ClassificationRule).filter(
        ClassificationRule.organization_id == org_id
    ).order_by(ClassificationRule.confidence.desc()).all()

    # Default fund = General
    general_fund = db.query(Fund).filter(
        Fund.organization_id == org_id, Fund.code == "GEN"
    ).first()

    for txn in txns:
        desc = txn.description.lower() if txn.description else ""

        # 1) Try learned rules first
        matched = False
        for rule in learned_rules:
            if re.search(rule.pattern, desc, re.IGNORECASE):
                txn.account_id = rule.account_id
                txn.fund_id = rule.fund_id or (general_fund.id if general_fund else None)
                txn.transaction_type = rule.transaction_type or txn.transaction_type
                txn.ai_classified = True
                txn.ai_confidence = min(rule.confidence, 1.0)
                rule.times_applied += 1
                matched = True
                break

        if matched:
            continue

        # 2) Try built-in patterns
        for pattern, sub_type, txn_type in _DEFAULT_PATTERNS:
            if re.search(pattern, desc, re.IGNORECASE):
                acct = acct_by_sub.get(sub_type)
                if acct:
                    txn.account_id = acct.id
                    txn.fund_id = general_fund.id if general_fund else None
                    txn.transaction_type = txn_type
                    txn.ai_classified = True
                    txn.ai_confidence = 0.6
                    break

    db.commit()


def confirm_classification(db: Session, txn_id: int, account_id: int,
                           fund_id: int | None = None):
    """User confirms or corrects a classification. Learn from it."""
    txn = db.get(Transaction, txn_id)
    if not txn:
        return

    old_account_id = txn.account_id
    txn.account_id = account_id
    if fund_id is not None:
        txn.fund_id = fund_id
    txn.classification_confirmed = True

    # Learn: upsert a classification rule from the confirmed description
    desc_pattern = _make_pattern(txn.description)
    if desc_pattern:
        existing = db.query(ClassificationRule).filter(
            ClassificationRule.organization_id == txn.organization_id,
            ClassificationRule.pattern == desc_pattern,
        ).first()

        if existing:
            existing.account_id = account_id
            existing.fund_id = fund_id or existing.fund_id
            existing.transaction_type = txn.transaction_type
            existing.times_confirmed += 1
            existing.confidence = min(0.5 + existing.times_confirmed * 0.1, 1.0)
        else:
            rule = ClassificationRule(
                organization_id=txn.organization_id,
                pattern=desc_pattern,
                account_id=account_id,
                fund_id=fund_id,
                transaction_type=txn.transaction_type,
                confidence=0.6,
                times_applied=0,
                times_confirmed=1,
            )
            db.add(rule)

    db.commit()


def _make_pattern(description: str) -> str | None:
    """Extract key words from a description to build a reusable pattern."""
    if not description:
        return None
    # Remove numbers, special chars, common filler words
    words = re.sub(r"[^a-zA-Z\s]", "", description.lower()).split()
    stop = {"the", "a", "an", "of", "for", "to", "in", "on", "at", "by", "and", "or",
            "from", "with", "is", "was", "payment", "pos", "debit", "credit", "check"}
    keywords = [w for w in words if w not in stop and len(w) > 2]
    if not keywords:
        return None
    # Use the first 3 meaningful words as pattern
    return r".*".join(keywords[:3])
