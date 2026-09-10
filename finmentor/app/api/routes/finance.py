"""finance routes (spec section 22): GET/PUT /api/financial-profile/{user_id}.

Both return the rebuilt Financial Twin — the profile is an input, the twin is
what the rest of the product reads.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, OwnedUserId, load_twin, load_user, require_user
from app.repositories import profiles as profiles_repo
from app.schemas.finance import FinancialProfileIn, FinancialTwinOut

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["finance"],
                   dependencies=[Depends(require_user)])

PeriodQuery = Query(
    default=None,
    pattern=r"^\d{4}-\d{2}$",
    description="expense period, YYYY-MM (defaults to the current month)",
)


@router.get("/financial-profile/{user_id}", response_model=FinancialTwinOut)
def get_financial_profile(user_id: OwnedUserId, db: DbSession, period: str | None = PeriodQuery):
    return load_twin(db, user_id, period=period)


@router.put("/financial-profile/{user_id}", response_model=FinancialTwinOut)
def put_financial_profile(
    user_id: OwnedUserId,
    payload: FinancialProfileIn,
    db: DbSession,
    period: str | None = PeriodQuery,
):
    """Create or replace the profile (and this period's expense records)."""
    user = load_user(db, user_id)
    profiles_repo.upsert(db, user, payload, period=period)
    db.commit()
    return load_twin(db, user_id, period=period)
