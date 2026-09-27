"""CRUD for `financial_goals`."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import FinancialGoal
from app.schemas.finance import GoalIn, GoalUpdate


def get(db: Session, goal_id: int) -> FinancialGoal | None:
    return db.get(FinancialGoal, goal_id)


def list_for_user(db: Session, user_id: int, *, active_only: bool = True) -> list[FinancialGoal]:
    stmt = select(FinancialGoal).where(FinancialGoal.user_id == user_id)
    if active_only:
        stmt = stmt.where(FinancialGoal.is_active.is_(True))
    return list(db.scalars(stmt.order_by(FinancialGoal.priority, FinancialGoal.id)))


def create(db: Session, user_id: int, data: GoalIn) -> FinancialGoal:
    goal = FinancialGoal(
        user_id=user_id,
        name=data.name,
        target_amount=data.target_amount,
        current_amount=data.current_amount,
        deadline=data.deadline,
        priority=data.priority,
    )
    db.add(goal)
    db.flush()
    return goal


def update(db: Session, goal: FinancialGoal, data: GoalIn | GoalUpdate) -> FinancialGoal:
    """Replace a goal's fields. `is_active` only moves when it is sent."""
    goal.name = data.name
    goal.target_amount = data.target_amount
    goal.current_amount = data.current_amount
    goal.deadline = data.deadline
    goal.priority = data.priority
    active = getattr(data, "is_active", None)
    if active is not None:
        goal.is_active = active
    db.flush()
    return goal


def delete(db: Session, goal: FinancialGoal) -> None:
    """Remove a goal outright.

    Distinct from archiving, and both are offered because they answer
    different questions. Archiving keeps a goal that was real and is over;
    deleting removes one that should never have existed. Only archiving is
    reversible, which is why the client confirms a delete and not an archive.
    """
    db.delete(goal)
    db.flush()


def to_goal_in(goal: FinancialGoal) -> GoalIn:
    return GoalIn(
        name=goal.name,
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        deadline=goal.deadline,
        priority=goal.priority,
    )
