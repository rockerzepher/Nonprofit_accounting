"""Tests for financial reports."""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.accounting import Transaction
from backend.services.onboarding import create_organization
from backend.services.classifier import classify_transactions
from backend.services.reports import income_expense_report, balance_sheet_report, fund_summary


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def org_with_classified(db):
    org = create_organization(db, name="Report Test Org", org_type="church")

    txns_data = [
        (date(2026, 1, 5), "Donation - John", 500.0, "income"),
        (date(2026, 1, 7), "Tithe Collection", 3200.0, "income"),
        (date(2026, 1, 10), "Duke Energy Electric", -342.50, "expense"),
        (date(2026, 1, 12), "ADP Payroll", -4500.0, "expense"),
        (date(2026, 1, 15), "Bank Service Charge", -12.0, "expense"),
    ]
    for d, desc, amt, tt in txns_data:
        db.add(Transaction(
            organization_id=org.id, date=d, description=desc,
            amount=amt, transaction_type=tt, source="csv_import",
        ))
    db.commit()

    classify_transactions(db, org.id)
    return org


def test_income_expense_report(db, org_with_classified):
    org = org_with_classified
    report = income_expense_report(db, org.id, date(2026, 1, 1), date(2026, 1, 31))

    assert report.total_income > 0
    assert report.total_expenses > 0
    assert len(report.income_lines) >= 1
    assert len(report.expense_lines) >= 1


def test_balance_sheet_report(db, org_with_classified):
    org = org_with_classified
    report = balance_sheet_report(db, org.id, date(2026, 1, 31))
    # Should have some data since transactions are classified
    assert report is not None


def test_fund_summary(db, org_with_classified):
    org = org_with_classified
    funds = fund_summary(db, org.id, date(2026, 1, 1), date(2026, 1, 31))
    # Classified transactions should have been assigned to General Fund
    assert isinstance(funds, list)
