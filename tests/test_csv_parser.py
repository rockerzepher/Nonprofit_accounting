"""Tests for CSV parser service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.models.accounting import Transaction
from backend.services.csv_parser import parse_csv, parse_date


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Create a test org
    org = Organization(name="Test Org", org_type="general_nonprofit")
    session.add(org)
    session.commit()
    yield session
    session.close()


def test_parse_date_formats():
    from datetime import date
    assert parse_date("01/15/2026") == date(2026, 1, 15)
    assert parse_date("2026-01-15") == date(2026, 1, 15)
    assert parse_date("01-15-2026") == date(2026, 1, 15)


def test_parse_basic_csv(db):
    csv_content = b"Date,Description,Amount\n01/15/2026,Donation from John,500.00\n01/16/2026,Office Supplies,-45.00\n"
    txns = parse_csv(csv_content, 1, db)
    assert len(txns) == 2
    assert txns[0].amount == 500.00
    assert txns[0].transaction_type == "income"
    assert txns[1].amount == -45.00
    assert txns[1].transaction_type == "expense"


def test_parse_debit_credit_csv(db):
    csv_content = b"Date,Description,Debit,Credit\n01/15/2026,Donation,,500.00\n01/16/2026,Rent,2200.00,\n"
    txns = parse_csv(csv_content, 1, db)
    assert len(txns) == 2
    assert txns[0].amount == 500.00
    assert txns[1].amount == -2200.00


def test_parse_csv_with_bom(db):
    csv_content = b"\xef\xbb\xbfDate,Description,Amount\n01/15/2026,Test,100.00\n"
    txns = parse_csv(csv_content, 1, db)
    assert len(txns) == 1


def test_skip_blank_rows(db):
    csv_content = b"Date,Description,Amount\n01/15/2026,Test,100.00\n,,\n01/16/2026,Test2,200.00\n"
    txns = parse_csv(csv_content, 1, db)
    assert len(txns) == 2
