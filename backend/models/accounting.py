"""Core accounting models: funds, accounts, transactions."""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Float,
    ForeignKey, Boolean, Date
)
from sqlalchemy.orm import relationship

from backend.database import Base


class Fund(Base):
    """A fund represents a pool of money with restrictions or purposes."""
    __tablename__ = "funds"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    code = Column(String(20), nullable=False)
    fund_type = Column(String(50), nullable=False)  # unrestricted, temporarily_restricted, permanently_restricted
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="funds")
    transactions = relationship("Transaction", back_populates="fund")


class Account(Base):
    """Chart of accounts entry."""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    code = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)  # asset, liability, equity, revenue, expense
    sub_type = Column(String(100), nullable=True)  # e.g., "cash", "accounts_receivable"
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="accounts")
    parent = relationship("Account", remote_side=[id])
    transactions = relationship("Transaction", back_populates="account")


class Transaction(Base):
    """Individual financial transaction."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    fund_id = Column(Integer, ForeignKey("funds.id"), nullable=True)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)  # positive = debit, negative = credit
    transaction_type = Column(String(20), nullable=False)  # income, expense, transfer
    reference = Column(String(255), nullable=True)  # check number, reference ID
    payee = Column(String(255), nullable=True)
    memo = Column(Text, nullable=True)
    is_reconciled = Column(Boolean, default=False)
    source = Column(String(50), default="manual")  # manual, pdf_import, excel_import
    ai_classified = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    classification_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    fund = relationship("Fund", back_populates="transactions")
    tags = relationship("TransactionTag", back_populates="transaction", cascade="all, delete-orphan")


class TransactionTag(Base):
    """Tags for flexible transaction categorization."""
    __tablename__ = "transaction_tags"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    tag_name = Column(String(100), nullable=False)
    tag_value = Column(String(255), nullable=True)

    transaction = relationship("Transaction", back_populates="tags")


class ClassificationRule(Base):
    """Learned rules for AI transaction classification."""
    __tablename__ = "classification_rules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    pattern = Column(String(500), nullable=False)  # keyword/regex pattern from description
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    fund_id = Column(Integer, ForeignKey("funds.id"), nullable=True)
    transaction_type = Column(String(20), nullable=True)
    confidence = Column(Float, default=0.5)
    times_applied = Column(Integer, default=0)
    times_confirmed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="classification_rules")
    account = relationship("Account")
    fund = relationship("Fund")
