"""Tests for PDF parser service."""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.services.pdf_parser import (
    _extract_description, _extract_amount, _parse_date_str,
    _DATE_SLASH_RE, _DATE_SHORT_RE, _DATE_MONTH_RE,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    org = Organization(name="Test Org", org_type="general_nonprofit")
    session.add(org)
    session.commit()
    yield session
    session.close()


def test_date_line_regex_full():
    """Test that full date formats (with year) are detected."""
    assert _DATE_SLASH_RE.match("01/15/2026  Donation from John  $500.00  $1,500.00")
    assert _DATE_SLASH_RE.match("2026-01-15  Electric Bill  -$342.50")
    assert _DATE_SLASH_RE.match("01-15-2026  Payroll  $4,500.00")
    assert not _DATE_SLASH_RE.match("Account Summary")
    assert not _DATE_SLASH_RE.match("Total Deposits: $5,000.00")


def test_date_short_regex():
    """Test that MM/DD (no year) dates are detected."""
    assert _DATE_SHORT_RE.match("01/15  Donation  $500.00")
    assert _DATE_SHORT_RE.match("1/5  ATM  $40.00")
    # Should NOT match if there's a third slash segment (that's a full date)
    assert not _DATE_SHORT_RE.match("01/15/2026  Full date")


def test_date_month_name_regex():
    """Test that month name dates are detected."""
    assert _DATE_MONTH_RE.match("Jan 15  Donation  $500.00")
    assert _DATE_MONTH_RE.match("January 15  Donation  $500.00")
    assert _DATE_MONTH_RE.match("Feb 3, 2026  Payment  $100.00")
    assert not _DATE_MONTH_RE.match("Account Summary")


def test_parse_date_str():
    """Test date string parsing across formats."""
    assert _parse_date_str("01/15/2026") == date(2026, 1, 15)
    assert _parse_date_str("2026-01-15") == date(2026, 1, 15)
    assert _parse_date_str("01/15", statement_year=2026) == date(2026, 1, 15)
    assert _parse_date_str("Jan 15", statement_year=2026) == date(2026, 1, 15)
    assert _parse_date_str("January 15, 2026") == date(2026, 1, 15)
    assert _parse_date_str("not a date") is None


def test_extract_amount():
    assert _extract_amount("$500.00") == 500.00
    assert _extract_amount("($342.50)") == -342.50
    assert _extract_amount("1,234.56") == 1234.56
    assert _extract_amount("-$45.00") == -45.00
    assert _extract_amount("") is None


def test_extract_description():
    line = "01/15/2026  Donation from John Smith  $500.00  $1,500.00"
    desc = _extract_description(line, "01/15/2026")
    assert "Donation from John Smith" in desc
    assert "$" not in desc
