"""Tests for transaction classifier."""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.models.accounting import Transaction, Account, Fund, ClassificationRule
from backend.services.onboarding import create_organization
from backend.services.classifier import classify_transactions, confirm_classification


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def org_with_txns(db):
    org = create_organization(db, name="Test Church", org_type="church")

    txns = [
        Transaction(organization_id=org.id, date=date(2026, 1, 10),
                     description="Duke Energy - Electric", amount=-342.50,
                     transaction_type="expense", source="csv_import"),
        Transaction(organization_id=org.id, date=date(2026, 1, 15),
                     description="Donation - John Smith", amount=500.00,
                     transaction_type="income", source="csv_import"),
        Transaction(organization_id=org.id, date=date(2026, 1, 20),
                     description="ADP Payroll", amount=-4500.00,
                     transaction_type="expense", source="csv_import"),
        Transaction(organization_id=org.id, date=date(2026, 1, 25),
                     description="Bank Monthly Service Charge", amount=-12.00,
                     transaction_type="expense", source="csv_import"),
    ]
    for t in txns:
        db.add(t)
    db.commit()
    return org


def test_classify_transactions(db, org_with_txns):
    org = org_with_txns
    classify_transactions(db, org.id)

    txns = db.query(Transaction).filter(
        Transaction.organization_id == org.id).all()

    classified = [t for t in txns if t.account_id is not None]
    assert len(classified) >= 3  # at least utilities, donation, payroll should match

    # Check specific classifications
    electric = [t for t in txns if "Duke Energy" in t.description][0]
    assert electric.account is not None
    assert electric.account.sub_type == "utilities"

    donation = [t for t in txns if "Donation" in t.description][0]
    assert donation.account is not None
    assert donation.account.sub_type == "donations"


def test_confirm_creates_rule(db, org_with_txns):
    org = org_with_txns
    classify_transactions(db, org.id)

    txn = db.query(Transaction).filter(
        Transaction.organization_id == org.id).first()
    acct = db.query(Account).filter(
        Account.organization_id == org.id).first()

    confirm_classification(db, txn.id, acct.id)

    assert txn.classification_confirmed is True
    rules = db.query(ClassificationRule).filter(
        ClassificationRule.organization_id == org.id).all()
    assert len(rules) >= 1
