"""CRUD for `financial_profiles` and the `expense_records` that back them.

A profile plus one month of expense records is exactly what
``services.financial_twin.build_twin`` needs, so this module also converts
between the ORM rows and ``FinancialProfileIn``.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import ExpenseRecord, FinancialProfile
from app.models.user import User
from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn

ESSENTIAL_CATEGORIES = frozenset({"housing", "food", "transportation", "bills"})


def current_period(today: date | None = None) -> str:
    """The `YYYY-MM` bucket expense/income records are filed under."""
    return (today or date.today()).strftime("%Y-%m")


def get_by_user(db: Session, user_id: int) -> FinancialProfile | None:
    return db.scalar(select(FinancialProfile).where(FinancialProfile.user_id == user_id))


def upsert(
    db: Session,
    user: User,
    data: FinancialProfileIn,
    *,
    period: str | None = None,
) -> FinancialProfile:
    """Create or update the user's profile, its expense records, and risk profile."""
    profile = get_by_user(db, user.id)
    if profile is None:
        profile = FinancialProfile(user_id=user.id)
        db.add(profile)

    profile.monthly_income = data.monthly_income
    profile.income_type = data.income_type
    profile.current_savings = data.current_savings
    profile.debt = data.debt
    profile.monthly_debt_payment = data.monthly_debt_payment
    profile.emergency_fund = data.emergency_fund
    profile.planned_budget_json = (
        json.dumps(data.planned_budget.model_dump()) if data.planned_budget else None
    )
    user.risk_profile = data.risk_profile

    replace_expenses(db, user.id, data.expenses, period=period)
    db.flush()
    return profile


def replace_expenses(
    db: Session,
    user_id: int,
    expenses: ExpenseBreakdown,
    *,
    period: str | None = None,
) -> list[ExpenseRecord]:
    """Overwrite the user's expense records for `period` with this breakdown."""
    period = period or current_period()
    existing = {
        row.category: row
        for row in db.scalars(
            select(ExpenseRecord).where(
                ExpenseRecord.user_id == user_id, ExpenseRecord.period == period
            )
        )
    }
    records: list[ExpenseRecord] = []
    for category, amount in expenses.model_dump().items():
        row = existing.pop(category, None)
        if row is None:
            row = ExpenseRecord(user_id=user_id, category=category, period=period)
            db.add(row)
        row.amount = amount
        row.is_essential = category in ESSENTIAL_CATEGORIES
        records.append(row)
    for orphan in existing.values():
        db.delete(orphan)
    db.flush()
    return records


def expense_breakdown(
    db: Session, user_id: int, *, period: str | None = None
) -> ExpenseBreakdown:
    period = period or current_period()
    rows = db.scalars(
        select(ExpenseRecord).where(
            ExpenseRecord.user_id == user_id, ExpenseRecord.period == period
        )
    )
    fields = ExpenseBreakdown.model_fields
    return ExpenseBreakdown(**{r.category: r.amount for r in rows if r.category in fields})


def planned_budget(profile: FinancialProfile) -> ExpenseBreakdown | None:
    """The stored planned budget, or None if the user never set one."""
    if not profile.planned_budget_json:
        return None
    return ExpenseBreakdown(**json.loads(profile.planned_budget_json))


def to_profile_in(
    db: Session, profile: FinancialProfile, *, period: str | None = None
) -> FinancialProfileIn:
    """The engine's input contract, rebuilt from persisted rows."""
    return FinancialProfileIn(
        monthly_income=profile.monthly_income,
        income_type=profile.income_type,
        expenses=expense_breakdown(db, profile.user_id, period=period),
        current_savings=profile.current_savings,
        debt=profile.debt,
        monthly_debt_payment=profile.monthly_debt_payment,
        emergency_fund=profile.emergency_fund,
        risk_profile=profile.user.risk_profile or "moderate",
        planned_budget=planned_budget(profile),
    )
