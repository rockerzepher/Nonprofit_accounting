"""Tests for PDF parser service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.services.pdf_parser import _extract_description, _extract_amount, _DATE_LINE_RE


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


def test_date_line_regex():
    """Test that common bank statement date formats are detected."""
    assert _DATE_LINE_RE.match("01/15/2026  Donation from John  $500.00  $1,500.00")
    assert _DATE_LINE_RE.match("2026-01-15  Electric Bill  -$342.50")
    assert _DATE_LINE_RE.match("01-15-2026  Payroll  $4,500.00")
    assert not _DATE_LINE_RE.match("Account Summary")
    assert not _DATE_LINE_RE.match("Total Deposits: $5,000.00")


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
