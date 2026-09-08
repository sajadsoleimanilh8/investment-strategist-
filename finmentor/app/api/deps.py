"""Shared FastAPI dependencies and the glue that turns DB rows into engine input.

The assembly lives here, in the delivery layer: `app/services` stays free of
persistence (see docs/ARCHITECTURE.md) and the routes stay free of duplicated
loading code.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db  # noqa: F401  re-exported for routes
from app.models.finance import FinancialProfile
from app.models.user import User
from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.finance import FinancialTwinOut
from app.services.financial_twin import build_twin

DbSession = Annotated[Session, Depends(get_db)]


def load_user(db: Session, user_id: int) -> User:
    user = users_repo.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def load_profile(db: Session, user_id: int) -> FinancialProfile:
    load_user(db, user_id)
    profile = profiles_repo.get_by_user(db, user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no financial profile for this user yet",
        )
    return profile


def load_twin(db: Session, user_id: int, *, period: str | None = None) -> FinancialTwinOut:
    """Profile + this period's expenses + active goals -> the Financial Twin."""
    profile = load_profile(db, user_id)
    return build_twin(
        profiles_repo.to_profile_in(db, profile, period=period),
        [goals_repo.to_goal_in(goal) for goal in goals_repo.list_for_user(db, user_id)],
    )
