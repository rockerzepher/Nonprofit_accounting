"""Financial reports API routes."""

from datetime import date

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend._paths import TEMPLATES_DIR
from backend.database import get_db
from backend.models.organization import Organization
from backend.services.reports import (
    income_expense_report, balance_sheet_report, fund_summary,
)

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _default_period(org: Organization) -> tuple[date, date]:
    """Return the current fiscal year start and today."""
    today = date.today()
    fy_month = org.fiscal_year_start or 1
    if today.month >= fy_month:
        start = date(today.year, fy_month, 1)
    else:
        start = date(today.year - 1, fy_month, 1)
    return start, today


@router.get("/{org_id}", response_class=HTMLResponse)
def reports_index(org_id: int, request: Request, db: Session = Depends(get_db)):
    """Reports landing page."""
    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("reports_index.html", {
        "request": request, "org": org,
    })


@router.get("/{org_id}/income-expense", response_class=HTMLResponse)
def income_expense(org_id: int, request: Request,
                   start: str = Query(None), end: str = Query(None),
                   db: Session = Depends(get_db)):
    """Income & Expense report."""
    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)

    if start and end:
        period_start = date.fromisoformat(start)
        period_end = date.fromisoformat(end)
    else:
        period_start, period_end = _default_period(org)

    report = income_expense_report(db, org_id, period_start, period_end)
    return templates.TemplateResponse("report_income_expense.html", {
        "request": request, "org": org, "report": report,
        "start": period_start.isoformat(), "end": period_end.isoformat(),
    })


@router.get("/{org_id}/balance-sheet", response_class=HTMLResponse)
def balance_sheet(org_id: int, request: Request,
                  as_of: str = Query(None),
                  db: Session = Depends(get_db)):
    """Balance Sheet report."""
    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)

    report_date = date.fromisoformat(as_of) if as_of else date.today()
    report = balance_sheet_report(db, org_id, report_date)
    return templates.TemplateResponse("report_balance_sheet.html", {
        "request": request, "org": org, "report": report,
        "as_of": report_date.isoformat(),
    })


@router.get("/{org_id}/fund-summary", response_class=HTMLResponse)
def fund_report(org_id: int, request: Request,
                start: str = Query(None), end: str = Query(None),
                db: Session = Depends(get_db)):
    """Fund summary report."""
    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)

    if start and end:
        period_start = date.fromisoformat(start)
        period_end = date.fromisoformat(end)
    else:
        period_start, period_end = _default_period(org)

    funds = fund_summary(db, org_id, period_start, period_end)
    return templates.TemplateResponse("report_fund_summary.html", {
        "request": request, "org": org, "funds": funds,
        "start": period_start.isoformat(), "end": period_end.isoformat(),
    })
