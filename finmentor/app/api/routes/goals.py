"""goals routes (spec section 22): GET /api/goals/{user_id}, POST /api/goals,
PUT /api/goals/{goal_id}, DELETE /api/goals/{goal_id}.

Progress and ETA come from `services.goal_engine`; the route never does goal
maths of its own.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, OwnedUserId, assert_owns, load_twin, load_user, require_user
from app.models.goal import FinancialGoal
from app.repositories import goals as goals_repo
from app.schemas.finance import GoalCreate, GoalIn, GoalOut, GoalUpdate
from app.services import goal_engine

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["goals"],
                   dependencies=[Depends(require_user)])


def _monthly_savings(db, user_id: int) -> float | None:
    """What this user currently saves each month, or None if we cannot say.

    The ETA on a goal assumes the saving rate holds. With no profile there is
    no rate to assume, and None is the honest answer rather than zero — zero
    would render as "never reachable", which is a claim about the user rather
    than about what we know.
    """
    try:
        return load_twin(db, user_id).monthly_savings
    except HTTPException:
        return None


def _to_out(goal: FinancialGoal, monthly_savings: float | None) -> GoalOut:
    """A stored goal plus its deterministic figures. No database access.

    The saving rate arrives as an argument rather than being fetched here, and
    that is the whole fix for the N+1 below: a function that loads what it
    needs is a function that loads it once per call, however many times the
    caller calls it.
    """
    out = GoalOut.model_validate(goal)
    goal_in = goals_repo.to_goal_in(goal)
    out.progress_pct = goal_engine.progress_pct(goal_in)
    if monthly_savings is not None:
        out.estimated_completion = goal_engine.estimated_completion(
            goal_in, monthly_savings)
    return out


@router.get("/goals/{user_id}", response_model=list[GoalOut])
def list_goals(user_id: OwnedUserId, db: DbSession, active_only: bool = True):
    """Every goal, each with its progress and ETA.

    The twin is built once for the whole list. It used to be built inside
    `_to_out`, so listing N goals built N twins — and `load_twin` lists the
    user's goals itself, so the work grew as the square of the number of
    goals. Somebody with ten goals paid about forty queries for one screen.
    """
    load_user(db, user_id)
    monthly_savings = _monthly_savings(db, user_id)
    return [
        _to_out(goal, monthly_savings)
        for goal in goals_repo.list_for_user(db, user_id, active_only=active_only)
    ]


@router.post("/goals", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, db: DbSession, current_user: CurrentUser):
    assert_owns(current_user, payload.user_id)
    load_user(db, payload.user_id)
    goal = goals_repo.create(db, payload.user_id, GoalIn(**payload.model_dump(exclude={"user_id"})))
    db.commit()
    return _to_out(goal, _monthly_savings(db, payload.user_id))


def _own_goal(db, goal_id: int, current_user) -> FinancialGoal:
    """A goal the caller owns, or the right refusal.

    The path carries a `{goal_id}`, not a `{user_id}`, so `owned_user_id`
    cannot reach it — the owner is a property of the row, not of the URL. The
    row has to be loaded before the question can even be asked, which is why
    this is `assert_owns` in the body rather than a dependency.

    404 before 403 on purpose: a goal id that does not exist is not somebody
    else's goal, and answering 403 for it would turn these routes into a way
    to count the rows in the table.

    One helper rather than three copies, because "every goal mutation checks
    ownership" should be something you can see rather than something you have
    to audit — `PUT` shipped without it once already.
    """
    goal = goals_repo.get(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="goal not found")
    assert_owns(current_user, goal.user_id)
    return goal


@router.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, payload: GoalUpdate, db: DbSession, current_user: CurrentUser):
    """Replace a goal the caller owns, and optionally archive or restore it."""
    goal = _own_goal(db, goal_id, current_user)
    goals_repo.update(db, goal, payload)
    db.commit()
    return _to_out(goal, _monthly_savings(db, goal.user_id))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response)
def delete_goal(goal_id: int, db: DbSession, current_user: CurrentUser) -> Response:
    """Remove a goal for good.

    Separate from archiving (`is_active: false` on the PUT above), which is
    what a finished goal wants. This is for one that should not exist, and it
    is the only irreversible thing a user can do here, which is why the client
    asks first.
    """
    goal = _own_goal(db, goal_id, current_user)
    goals_repo.delete(db, goal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
