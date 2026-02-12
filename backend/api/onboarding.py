"""Onboarding API routes."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend._paths import TEMPLATES_DIR
from backend.database import get_db
from backend.services.onboarding import create_organization

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
def onboarding_form(request: Request):
    """Show onboarding form."""
    return templates.TemplateResponse("onboarding.html", {"request": request})


@router.post("/", response_class=HTMLResponse)
def onboarding_submit(
    request: Request,
    name: str = Form(...),
    org_type: str = Form(...),
    description: str = Form(""),
    fiscal_year_start: int = Form(1),
    db: Session = Depends(get_db),
):
    """Process onboarding form and create organization."""
    org = create_organization(db, name=name, org_type=org_type,
                              description=description,
                              fiscal_year_start=fiscal_year_start)
    return RedirectResponse(url=f"/dashboard/{org.id}", status_code=302)
