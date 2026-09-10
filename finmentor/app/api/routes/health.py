"""health routes (spec section 22): GET /api/health/{user_id}.

The Financial DNA lives at its own path rather than as a flag on the score,
so each endpoint has one response shape:

    GET /api/health/{user_id}       -> HealthScoreOut  (5 components, total)
    GET /api/health/{user_id}/dna   -> FinancialDNAOut (Strong/Moderate/Weak bands)

Both are pure deterministic engine calls — no LLM anywhere on this path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, OwnedUserId, load_twin, require_user
from app.repositories import education as education_repo
from app.schemas.health import FinancialDNAOut, HealthScoreOut
from app.services.financial_dna import build_dna
from app.services.health_score import compute_health_score

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["health"],
                   dependencies=[Depends(require_user)])


@router.get("/health/{user_id}", response_model=HealthScoreOut)
def get_health_score(user_id: OwnedUserId, db: DbSession) -> HealthScoreOut:
    return compute_health_score(load_twin(db, user_id))


@router.get("/health/{user_id}/dna", response_model=FinancialDNAOut)
def get_financial_dna(user_id: OwnedUserId, db: DbSession) -> FinancialDNAOut:
    twin = load_twin(db, user_id)
    return build_dna(twin, completed_topics=education_repo.count_completed(db, user_id))
