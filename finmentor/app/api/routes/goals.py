"""goals routes (spec section 22): GET /api/goals/{user_id}, POST /api/goals,
PUT /api/goals/{goal_id}.

Progress and ETA come from `services.goal_engine`; the route never does goal
maths of its own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, load_twin, load_user, require_user
from app.models.goal import FinancialGoal
from app.repositories import goals as goals_repo
from app.schemas.finance import GoalCreate, GoalIn, GoalOut
from app.services import goal_engine

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["goals"],
                   dependencies=[Depends(require_user)])


def _to_out(db, goal: FinancialGoal) -> GoalOut:
    """A stored goal plus its deterministic figures.

    The ETA assumes the user keeps saving at their current monthly rate; with
    no profile yet there is no rate to assume, so the ETA stays null.
    """
    out = GoalOut.model_validate(goal)
    goal_in = goals_repo.to_goal_in(goal)
    out.progress_pct = goal_engine.progress_pct(goal_in)
    try:
        monthly_savings = load_twin(db, goal.user_id).monthly_savings
    except HTTPException:
        return out
    out.estimated_completion = goal_engine.estimated_completion(goal_in, monthly_savings)
    return out


@router.get("/goals/{user_id}", response_model=list[GoalOut])
def list_goals(user_id: int, db: DbSession, active_only: bool = True):
    load_user(db, user_id)
    return [_to_out(db, goal) for goal in goals_repo.list_for_user(db, user_id, active_only=active_only)]


@router.post("/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, db: DbSession):
    load_user(db, payload.user_id)
    goal = goals_repo.create(db, payload.user_id, GoalIn(**payload.model_dump(exclude={"user_id"})))
    db.commit()
    return _to_out(db, goal)


@router.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, payload: GoalIn, db: DbSession):
    goal = goals_repo.get(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="goal not found")
    goals_repo.update(db, goal, payload)
    db.commit()
    return _to_out(db, goal)
