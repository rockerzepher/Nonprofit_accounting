"""Nonprofit Accounting MVP — main application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.api.onboarding import router as onboarding_router
from backend.api.transactions import router as transactions_router
from backend.api.reports import router as reports_router
from backend.api.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nonprofit Accounting", version="0.1.0", lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

# Routers
app.include_router(dashboard_router)
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
app.include_router(transactions_router, prefix="/transactions", tags=["transactions"])
app.include_router(reports_router, prefix="/reports", tags=["reports"])
