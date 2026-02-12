"""Transaction management API routes — upload, list, classify, confirm."""

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.accounting import Transaction, Account, Fund
from backend.models.organization import Organization
from backend.services.csv_parser import parse_csv
from backend.services.classifier import classify_transactions, confirm_classification

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/{org_id}", response_class=HTMLResponse)
def list_transactions(org_id: int, request: Request,
                      filter: str = "all",
                      db: Session = Depends(get_db)):
    """List transactions for an org with optional filter."""
    org = db.get(Organization, org_id)
    if not org:
        return RedirectResponse(url="/", status_code=302)

    query = db.query(Transaction).filter(Transaction.organization_id == org_id)
    if filter == "unclassified":
        query = query.filter(Transaction.account_id.is_(None))
    elif filter == "classified":
        query = query.filter(Transaction.account_id.isnot(None))

    txns = query.order_by(Transaction.date.desc()).all()
    accounts = db.query(Account).filter(
        Account.organization_id == org_id).order_by(Account.code).all()
    funds = db.query(Fund).filter(
        Fund.organization_id == org_id).all()

    return templates.TemplateResponse("transactions.html", {
        "request": request,
        "org": org,
        "transactions": txns,
        "accounts": accounts,
        "funds": funds,
        "current_filter": filter,
    })


@router.get("/{org_id}/upload", response_class=HTMLResponse)
def upload_form(org_id: int, request: Request, db: Session = Depends(get_db)):
    """Show CSV upload form."""
    org = db.get(Organization, org_id)
    return templates.TemplateResponse("upload.html", {
        "request": request, "org": org,
    })


@router.post("/{org_id}/upload")
async def upload_csv(org_id: int, request: Request,
                     file: UploadFile = File(...),
                     db: Session = Depends(get_db)):
    """Upload and parse a bank statement CSV."""
    contents = await file.read()
    txns = parse_csv(contents, org_id, db)

    # Auto-classify the imported transactions
    txn_ids = [t.id for t in txns]
    classify_transactions(db, org_id, txn_ids)

    return RedirectResponse(
        url=f"/transactions/{org_id}?uploaded={len(txns)}",
        status_code=302,
    )


@router.post("/{org_id}/classify-all")
def classify_all(org_id: int, db: Session = Depends(get_db)):
    """Run classifier on all unclassified transactions."""
    classify_transactions(db, org_id)
    return RedirectResponse(url=f"/transactions/{org_id}", status_code=302)


@router.post("/{org_id}/confirm/{txn_id}")
def confirm_txn(org_id: int, txn_id: int,
                account_id: int = Form(...),
                fund_id: int = Form(None),
                db: Session = Depends(get_db)):
    """Confirm or correct a transaction's classification."""
    confirm_classification(db, txn_id, account_id, fund_id)
    return RedirectResponse(url=f"/transactions/{org_id}", status_code=302)
