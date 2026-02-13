"""Database configuration and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Use DATABASE_URL env var for cloud PostgreSQL (Neon, Supabase, etc.)
# Falls back to local SQLite for development
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Neon/Supabase provide postgres:// URLs; SQLAlchemy 2.x needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    _db_dir = "/tmp" if os.environ.get("VERCEL") else "."
    DATABASE_URL = f"sqlite:///{_db_dir}/nonprofit_accounting.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Yield a database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed a demo org on Vercel (ephemeral DB)."""
    Base.metadata.create_all(bind=engine)
    _seed_vercel_demo()


def _seed_vercel_demo():
    """On Vercel, auto-create a demo org so the app is usable without onboarding.

    Each cold start gets a fresh SQLite at /tmp, so we need to re-seed.
    """
    if not os.environ.get("VERCEL"):
        return

    from backend.models.organization import Organization
    db = SessionLocal()
    try:
        existing = db.query(Organization).first()
        if not existing:
            from backend.services.onboarding import create_organization
            create_organization(
                db, name="My Organization",
                org_type="general_nonprofit",
                description="Auto-created for Vercel deployment",
                fiscal_year_start=1,
            )
    finally:
        db.close()
