"""Transaction management API routes — upload, list, classify, confirm."""

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend._paths import TEMPLATES_DIR
from backend.database import get_db
from backend.models.accounting import Transaction, Account, Fund
from backend.models.organization import Organization
from backend.services.csv_parser import parse_csv
from backend.services.pdf_parser import parse_pdf, extract_pdf_debug_text
from backend.services.classifier import classify_transactions, confirm_classification

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
    if not org:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("upload.html", {
        "request": request, "org": org,
    })


@router.post("/{org_id}/upload", response_class=HTMLResponse)
async def upload_file(org_id: int, request: Request,
                      file: UploadFile = File(...),
                      db: Session = Depends(get_db)):
    """Upload and parse a bank statement (CSV or PDF).

    Renders the transaction list directly instead of redirecting,
    so data is visible even on serverless platforms with ephemeral storage.
    """
    org = db.get(Organization, org_id)
    if not org:
        return templates.TemplateResponse("upload.html", {
            "request": request,
            "org": type("Org", (), {"id": org_id, "name": "Unknown"})(),
            "upload_error": f"Organization {org_id} not found. On Vercel, data is lost between requests. Please start from the home page.",
        })

    contents = await file.read()
    filename = (file.filename or "").lower()
    is_pdf = filename.endswith(".pdf") or file.content_type == "application/pdf"
    debug_text = ""
    upload_error = ""

    try:
        if is_pdf:
            txns = parse_pdf(contents, org_id, db)
            if not txns:
                raw = extract_pdf_debug_text(contents)
                debug_text = raw[:2000] if raw else "(No text could be extracted — this may be a scanned/image PDF)"
        else:
            txns = parse_csv(contents, org_id, db)
    except Exception as e:
        txns = []
        upload_error = f"Error parsing file: {e}"

    # Auto-classify the imported transactions
    txn_ids = [t.id for t in txns]
    if txn_ids:
        try:
            classify_transactions(db, org_id, txn_ids)
        except Exception:
            pass  # classification failure shouldn't block showing results

    # Re-query all transactions for this org
    all_txns = db.query(Transaction).filter(
        Transaction.organization_id == org_id
    ).order_by(Transaction.date.desc()).all()
    accounts = db.query(Account).filter(
        Account.organization_id == org_id).order_by(Account.code).all()
    funds = db.query(Fund).filter(
        Fund.organization_id == org_id).all()

    return templates.TemplateResponse("transactions.html", {
        "request": request,
        "org": org,
        "transactions": all_txns,
        "accounts": accounts,
        "funds": funds,
        "current_filter": "all",
        "upload_count": len(txns),
        "upload_debug_text": debug_text,
        "upload_error": upload_error,
    })


@router.api_route("/{org_id}/classify-all", methods=["GET", "POST"])
def classify_all(org_id: int, db: Session = Depends(get_db)):
    """Run classifier on all unclassified transactions."""
    classify_transactions(db, org_id)
    return RedirectResponse(url=f"/transactions/{org_id}", status_code=303)


@router.api_route("/{org_id}/confirm/{txn_id}", methods=["GET", "POST"])
def confirm_txn(org_id: int, txn_id: int,
                account_id: int = Form(None),
                fund_id: int = Form(None),
                db: Session = Depends(get_db)):
    """Confirm or correct a transaction's classification."""
    if account_id is None:
        return RedirectResponse(url=f"/transactions/{org_id}", status_code=303)
    confirm_classification(db, txn_id, account_id, fund_id)
    return RedirectResponse(url=f"/transactions/{org_id}", status_code=303)
