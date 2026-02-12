"""Organization and onboarding models."""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import relationship

from backend.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    org_type = Column(String(50), nullable=False)  # church, school, community_group, general_nonprofit
    sub_type = Column(String(100), nullable=True)  # e.g., "multisite_church", "private_school"
    description = Column(Text, nullable=True)
    fiscal_year_start = Column(Integer, default=1)  # month (1-12)
    created_at = Column(DateTime, default=datetime.utcnow)
    onboarding_complete = Column(Boolean, default=False)

    # Relationships
    funds = relationship("Fund", back_populates="organization", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="organization", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="organization", cascade="all, delete-orphan")
    classification_rules = relationship("ClassificationRule", back_populates="organization", cascade="all, delete-orphan")
