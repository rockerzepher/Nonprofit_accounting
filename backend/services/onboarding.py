"""Onboarding service — creates org, seeds chart of accounts and funds."""

from sqlalchemy.orm import Session

from backend.models.organization import Organization
from backend.models.accounting import Fund, Account


# Default chart of accounts per org type.
# Format: (code, name, account_type, sub_type)
_BASE_ACCOUNTS = [
    # Assets
    ("1000", "Checking Account", "asset", "cash"),
    ("1010", "Savings Account", "asset", "cash"),
    ("1100", "Accounts Receivable", "asset", "accounts_receivable"),
    ("1200", "Prepaid Expenses", "asset", "prepaid"),
    # Liabilities
    ("2000", "Accounts Payable", "liability", "accounts_payable"),
    ("2100", "Accrued Expenses", "liability", "accrued"),
    ("2200", "Payroll Liabilities", "liability", "payroll"),
    # Equity / Net Assets
    ("3000", "Unrestricted Net Assets", "equity", "net_assets"),
    ("3100", "Temporarily Restricted Net Assets", "equity", "net_assets"),
    ("3200", "Permanently Restricted Net Assets", "equity", "net_assets"),
    # Revenue
    ("4000", "Individual Donations", "revenue", "donations"),
    ("4100", "Grants", "revenue", "grants"),
    ("4200", "Fundraising Events", "revenue", "fundraising"),
    ("4300", "Program Service Revenue", "revenue", "program"),
    ("4400", "Interest Income", "revenue", "interest"),
    ("4500", "Other Income", "revenue", "other"),
    # Expenses
    ("5000", "Salaries & Wages", "expense", "payroll"),
    ("5100", "Employee Benefits", "expense", "payroll"),
    ("5200", "Payroll Taxes", "expense", "payroll"),
    ("5300", "Rent & Occupancy", "expense", "occupancy"),
    ("5400", "Utilities", "expense", "utilities"),
    ("5500", "Office Supplies", "expense", "supplies"),
    ("5600", "Insurance", "expense", "insurance"),
    ("5700", "Professional Fees", "expense", "professional"),
    ("5800", "Program Expenses", "expense", "program"),
    ("5900", "Travel & Transportation", "expense", "travel"),
    ("6000", "Depreciation", "expense", "depreciation"),
    ("6100", "Miscellaneous Expense", "expense", "other"),
    ("6200", "Bank Fees & Charges", "expense", "bank_fees"),
    ("6300", "Technology & Software", "expense", "technology"),
]

# Extra accounts per org type
_ORG_TYPE_ACCOUNTS = {
    "church": [
        ("4010", "Tithes & Offerings", "revenue", "donations"),
        ("4020", "Building Fund Donations", "revenue", "donations"),
        ("5810", "Mission & Outreach", "expense", "program"),
        ("5820", "Worship & Music", "expense", "program"),
        ("5830", "Youth Ministry", "expense", "program"),
        ("5840", "Pastoral Support", "expense", "program"),
    ],
    "school": [
        ("4010", "Tuition Revenue", "revenue", "program"),
        ("4020", "Financial Aid Grants", "revenue", "grants"),
        ("5810", "Instructional Materials", "expense", "program"),
        ("5820", "Student Services", "expense", "program"),
        ("5830", "Athletics", "expense", "program"),
    ],
    "community_group": [
        ("4010", "Membership Dues", "revenue", "program"),
        ("4020", "Community Event Revenue", "revenue", "fundraising"),
        ("5810", "Community Programs", "expense", "program"),
        ("5820", "Volunteer Coordination", "expense", "program"),
    ],
    "general_nonprofit": [
        ("4010", "Corporate Sponsorships", "revenue", "donations"),
        ("5810", "Program Delivery", "expense", "program"),
    ],
}


def create_organization(db: Session, name: str, org_type: str,
                        description: str = "", fiscal_year_start: int = 1) -> Organization:
    """Create a new organization and seed its chart of accounts and funds."""
    org = Organization(
        name=name,
        org_type=org_type,
        description=description,
        fiscal_year_start=fiscal_year_start,
    )
    db.add(org)
    db.flush()  # get org.id

    # Seed funds
    _seed_funds(db, org.id)

    # Seed chart of accounts
    _seed_accounts(db, org.id, org_type)

    org.onboarding_complete = True
    db.commit()
    db.refresh(org)
    return org


def _seed_funds(db: Session, org_id: int):
    defaults = [
        ("GEN", "General Fund", "unrestricted", "Primary operating fund"),
        ("REST", "Restricted Fund", "temporarily_restricted", "Temporarily restricted donations"),
        ("PERM", "Endowment", "permanently_restricted", "Permanently restricted assets"),
    ]
    for code, name, fund_type, desc in defaults:
        db.add(Fund(
            organization_id=org_id, code=code, name=name,
            fund_type=fund_type, description=desc,
        ))


def _seed_accounts(db: Session, org_id: int, org_type: str):
    all_accounts = _BASE_ACCOUNTS + _ORG_TYPE_ACCOUNTS.get(org_type, [])
    for code, name, acct_type, sub in all_accounts:
        db.add(Account(
            organization_id=org_id, code=code, name=name,
            account_type=acct_type, sub_type=sub,
        ))
