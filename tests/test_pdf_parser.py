"""Tests for PDF parser service."""

import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.services.pdf_parser import (
    _extract_description, _find_date_in_line, _parse_date_str,
    _DATE_SLASH_RE, _DATE_SHORT_RE, _DATE_MONTH_RE,
)
from backend.services.csv_parser import _parse_amount


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
    assert _DATE_SLASH_RE.search("01/15/2026  Donation from John  $500.00  $1,500.00")
    assert _DATE_SLASH_RE.search("2026-01-15  Electric Bill  -$342.50")
    assert _DATE_SLASH_RE.search("01-15-2026  Payroll  $4,500.00")
    assert not _DATE_SLASH_RE.search("Account Summary")
    assert not _DATE_SLASH_RE.search("Total Deposits: $5,000.00")


def test_date_short_regex():
    """Test that MM/DD (no year) dates are detected."""
    assert _DATE_SHORT_RE.search("01/15  Donation  $500.00")
    assert _DATE_SHORT_RE.search("1/5  ATM  $40.00")
    # Should NOT match if there's a third slash segment (that's a full date)
    assert not _DATE_SHORT_RE.search("01/15/2026  Full date")


def test_date_month_name_regex():
    """Test that month name dates are detected."""
    assert _DATE_MONTH_RE.search("Jan 15  Donation  $500.00")
    assert _DATE_MONTH_RE.search("January 15  Donation  $500.00")
    assert _DATE_MONTH_RE.search("Feb 3, 2026  Payment  $100.00")
    assert not _DATE_MONTH_RE.search("Account Summary")


def test_parse_date_str():
    """Test date string parsing across formats."""
    assert _parse_date_str("01/15/2026") == date(2026, 1, 15)
    assert _parse_date_str("2026-01-15") == date(2026, 1, 15)
    assert _parse_date_str("01/15", statement_year=2026) == date(2026, 1, 15)
    assert _parse_date_str("Jan 15", statement_year=2026) == date(2026, 1, 15)
    assert _parse_date_str("January 15, 2026") == date(2026, 1, 15)
    assert _parse_date_str("not a date") is None


def test_find_date_in_line():
    """Test finding dates anywhere in a line."""
    d, s = _find_date_in_line("01/15/2026  Donation  $500.00", 2026)
    assert d == date(2026, 1, 15)
    assert s == "01/15/2026"

    d, s = _find_date_in_line("  Jan 15  Donation  $500.00", 2026)
    assert d == date(2026, 1, 15)

    d, s = _find_date_in_line("Account Summary", 2026)
    assert d is None


def test_parse_amount():
    assert _parse_amount("$500.00") == 500.00
    assert _parse_amount("($342.50)") == -342.50
    assert _parse_amount("1,234.56") == 1234.56
    assert _parse_amount("-45.00") == -45.00
    assert _parse_amount("") is None


def test_extract_description():
    line = "01/15/2026  Donation from John Smith  $500.00  $1,500.00"
    desc = _extract_description(line, "01/15/2026")
    assert "Donation from John Smith" in desc
    assert "$" not in desc
