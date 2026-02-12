"""Dashboard route — landing page / org selector."""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.organization import Organization

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Landing page: show list of orgs or redirect to onboarding."""
    orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
    if not orgs:
        return RedirectResponse(url="/onboarding/", status_code=302)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "orgs": orgs,
    })


@router.get("/dashboard/{org_id}", response_class=HTMLResponse)
def org_dashboard(org_id: int, request: Request, db: Session = Depends(get_db)):
    """Dashboard for a specific organization."""
    from backend.models.accounting import Transaction, Account, Fund
    from sqlalchemy import func
    from datetime import date, timedelta

    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)

    total_txns = db.query(func.count(Transaction.id)).filter(
        Transaction.organization_id == org_id).scalar() or 0
    classified = db.query(func.count(Transaction.id)).filter(
        Transaction.organization_id == org_id,
        Transaction.account_id.isnot(None)).scalar() or 0
    unclassified = total_txns - classified

    total_income = db.query(func.sum(Transaction.amount)).filter(
        Transaction.organization_id == org_id,
        Transaction.transaction_type == "income").scalar() or 0
    total_expenses = db.query(func.sum(Transaction.amount)).filter(
        Transaction.organization_id == org_id,
        Transaction.transaction_type == "expense").scalar() or 0

    return templates.TemplateResponse("org_dashboard.html", {
        "request": request,
        "org": org,
        "total_txns": total_txns,
        "classified": classified,
        "unclassified": unclassified,
        "total_income": abs(total_income),
        "total_expenses": abs(total_expenses),
        "net": abs(total_income) - abs(total_expenses),
    })
