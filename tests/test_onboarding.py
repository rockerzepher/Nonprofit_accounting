"""Tests for onboarding service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.organization import Organization
from backend.models.accounting import Fund, Account
from backend.services.onboarding import create_organization


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_church_org(db):
    org = create_organization(db, name="Grace Church", org_type="church")
    assert org.id is not None
    assert org.name == "Grace Church"
    assert org.org_type == "church"
    assert org.onboarding_complete is True

    funds = db.query(Fund).filter(Fund.organization_id == org.id).all()
    assert len(funds) == 3
    fund_codes = {f.code for f in funds}
    assert "GEN" in fund_codes

    accounts = db.query(Account).filter(Account.organization_id == org.id).all()
    # Base accounts + church-specific accounts
    assert len(accounts) > 30
    acct_names = {a.name for a in accounts}
    assert "Tithes & Offerings" in acct_names
    assert "Checking Account" in acct_names


def test_create_school_org(db):
    org = create_organization(db, name="Hope Academy", org_type="school")
    accounts = db.query(Account).filter(Account.organization_id == org.id).all()
    acct_names = {a.name for a in accounts}
    assert "Tuition Revenue" in acct_names


def test_create_general_nonprofit(db):
    org = create_organization(db, name="Helper Foundation", org_type="general_nonprofit",
                              fiscal_year_start=7)
    assert org.fiscal_year_start == 7
    accounts = db.query(Account).filter(Account.organization_id == org.id).all()
    assert len(accounts) > 25
