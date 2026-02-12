"""Financial reporting service for nonprofits."""

from datetime import date
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.accounting import Transaction, Account, Fund
from backend.models.organization import Organization


@dataclass
class ReportLine:
    code: str
    name: str
    amount: float
    children: list["ReportLine"] = field(default_factory=list)


@dataclass
class IncomeExpenseReport:
    period_start: date
    period_end: date
    income_lines: list[ReportLine] = field(default_factory=list)
    expense_lines: list[ReportLine] = field(default_factory=list)
    total_income: float = 0.0
    total_expenses: float = 0.0
    net_income: float = 0.0


@dataclass
class BalanceSheetReport:
    as_of: date
    asset_lines: list[ReportLine] = field(default_factory=list)
    liability_lines: list[ReportLine] = field(default_factory=list)
    equity_lines: list[ReportLine] = field(default_factory=list)
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0


@dataclass
class FundSummaryLine:
    fund_name: str
    fund_type: str
    total_income: float = 0.0
    total_expenses: float = 0.0
    net: float = 0.0


def income_expense_report(db: Session, org_id: int,
                          start: date, end: date) -> IncomeExpenseReport:
    """Generate an income & expense (profit & loss) report."""
    report = IncomeExpenseReport(period_start=start, period_end=end)

    # Get all transactions in the period that have an account
    txns = (
        db.query(
            Account.code, Account.name, Account.account_type,
            func.sum(Transaction.amount).label("total")
        )
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.organization_id == org_id,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.account_id.isnot(None),
        )
        .group_by(Account.id)
        .all()
    )

    for code, name, acct_type, total in txns:
        line = ReportLine(code=code, name=name, amount=abs(total or 0))
        if acct_type == "revenue":
            report.income_lines.append(line)
            report.total_income += abs(total or 0)
        elif acct_type == "expense":
            report.expense_lines.append(line)
            report.total_expenses += abs(total or 0)

    report.income_lines.sort(key=lambda l: l.code)
    report.expense_lines.sort(key=lambda l: l.code)
    report.net_income = report.total_income - report.total_expenses
    return report


def balance_sheet_report(db: Session, org_id: int, as_of: date) -> BalanceSheetReport:
    """Generate a simple balance sheet as of a given date."""
    report = BalanceSheetReport(as_of=as_of)

    txns = (
        db.query(
            Account.code, Account.name, Account.account_type,
            func.sum(Transaction.amount).label("total")
        )
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.organization_id == org_id,
            Transaction.date <= as_of,
            Transaction.account_id.isnot(None),
        )
        .group_by(Account.id)
        .all()
    )

    for code, name, acct_type, total in txns:
        amount = total or 0
        line = ReportLine(code=code, name=name, amount=amount)
        if acct_type == "asset":
            report.asset_lines.append(line)
            report.total_assets += amount
        elif acct_type == "liability":
            report.liability_lines.append(line)
            report.total_liabilities += abs(amount)
        elif acct_type == "equity":
            report.equity_lines.append(line)
            report.total_equity += abs(amount)

    # Net income goes into equity
    net = report.total_assets - report.total_liabilities - report.total_equity
    if abs(net) > 0.01:
        report.equity_lines.append(ReportLine(code="", name="Retained Net Income", amount=net))
        report.total_equity += net

    report.asset_lines.sort(key=lambda l: l.code)
    report.liability_lines.sort(key=lambda l: l.code)
    report.equity_lines.sort(key=lambda l: l.code)
    return report


def fund_summary(db: Session, org_id: int,
                 start: date, end: date) -> list[FundSummaryLine]:
    """Summarize income/expenses by fund."""
    results = (
        db.query(
            Fund.name, Fund.fund_type,
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Fund, Transaction.fund_id == Fund.id)
        .filter(
            Transaction.organization_id == org_id,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.fund_id.isnot(None),
        )
        .group_by(Fund.id, Transaction.transaction_type)
        .all()
    )

    fund_map: dict[str, FundSummaryLine] = {}
    for fund_name, fund_type, txn_type, total in results:
        if fund_name not in fund_map:
            fund_map[fund_name] = FundSummaryLine(fund_name=fund_name, fund_type=fund_type)
        line = fund_map[fund_name]
        if txn_type == "income":
            line.total_income += abs(total or 0)
        elif txn_type == "expense":
            line.total_expenses += abs(total or 0)

    for line in fund_map.values():
        line.net = line.total_income - line.total_expenses

    return list(fund_map.values())
