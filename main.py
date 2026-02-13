"""Nonprofit Accounting MVP — main application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend._paths import STATIC_DIR
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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle 405 Method Not Allowed by redirecting to home."""
    if exc.status_code == 405:
        return RedirectResponse(url="/", status_code=303)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Debug endpoint — shows what Vercel is actually sending
@app.get("/debug")
def debug_request(request: Request):
    return {
        "path": request.url.path,
        "method": request.method,
        "base_url": str(request.base_url),
        "url": str(request.url),
        "headers": dict(request.headers),
    }


# Static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Routers
app.include_router(dashboard_router)
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
app.include_router(transactions_router, prefix="/transactions", tags=["transactions"])
app.include_router(reports_router, prefix="/reports", tags=["reports"])
