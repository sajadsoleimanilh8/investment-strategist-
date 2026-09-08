"""financial_profiles, income_records, expense_records."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User

INCOME_TYPES = ("fixed", "variable", "mixed")
EXPENSE_CATEGORIES = (
    "housing", "food", "transportation", "education",
    "bills", "entertainment", "shopping", "other",
)


class FinancialProfile(Base, TimestampMixin):
    """1:1 with a user. The raw inputs the Financial Twin is recomputed from."""

    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint(
            "income_type IN ('fixed', 'variable', 'mixed')",
            name="ck_financial_profiles_income_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    monthly_income: Mapped[float] = mapped_column(Float, default=0.0)
    income_type: Mapped[str] = mapped_column(String(16), default="fixed")
    current_savings: Mapped[float] = mapped_column(Float, default=0.0)
    debt: Mapped[float] = mapped_column(Float, default=0.0)
    monthly_debt_payment: Mapped[float] = mapped_column(Float, default=0.0)
    emergency_fund: Mapped[float] = mapped_column(Float, default=0.0)
    # Planned budget per category, json.dumps(dict[str, float]). The
    # planned-vs-actual baseline for the budget-stability metric (phase 2).
    planned_budget_json: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped[User] = relationship(back_populates="profile")


class IncomeRecord(Base, TimestampMixin):
    """Income history — the signal behind `income_type = variable`."""

    __tablename__ = "income_records"
    __table_args__ = (Index("ix_income_records_user_period", "user_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[str] = mapped_column(String(7), default="")  # e.g. "2026-09"
    source: Mapped[str | None] = mapped_column(String(32), default=None)  # salary|freelance|...

    user: Mapped[User] = relationship(back_populates="income_records")


class ExpenseRecord(Base, TimestampMixin):
    """One category total for one month. Unique per (user, period, category)."""

    __tablename__ = "expense_records"
    __table_args__ = (
        Index("ix_expense_records_user_period", "user_id", "period"),
        Index(
            "uq_expense_records_user_period_category",
            "user_id", "period", "category", unique=True,
        ),
        CheckConstraint(
            "category IN ('housing', 'food', 'transportation', 'education',"
            " 'bills', 'entertainment', 'shopping', 'other')",
            name="ck_expense_records_category",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(24), default="other")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[str] = mapped_column(String(7), default="")
    is_essential: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(back_populates="expense_records")
