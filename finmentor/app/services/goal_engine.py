"""Goal maths (spec section 4/8): progress %, ETA at current savings rate.
Deterministic — no AI, no I/O.
"""
from __future__ import annotations

import calendar
import math
from datetime import date

from app.schemas.finance import GoalIn

#: Beyond this the honest answer is "not reachable at this rate", not a date in
#: the year 3335360 — `date` cannot represent one, and no user could read it.
MAX_HORIZON_MONTHS = 1200  # 100 years


def progress_pct(goal: GoalIn) -> float:
    """How much of the target is funded, 0..100 (never over 100)."""
    return round(min(1.0, goal.current_amount / goal.target_amount) * 100, 1)


def remaining_amount(goal: GoalIn) -> float:
    return max(0.0, goal.target_amount - goal.current_amount)


def months_remaining(goal: GoalIn, monthly_contribution: float) -> int | None:
    """Whole months needed at this contribution. 0 if already met, None if never."""
    remaining = remaining_amount(goal)
    if remaining <= 0:
        return 0
    if monthly_contribution <= 0:
        return None
    return math.ceil(remaining / monthly_contribution)


def add_months(start: date, months: int) -> date:
    """Calendar-month arithmetic, clamping to the end of a short month."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def estimated_completion(
    goal: GoalIn, monthly_contribution: float, start: date | None = None
) -> date | None:
    """When the goal is funded at this monthly contribution.

    `start` (today by default) plus ceil(remaining / contribution) months.
    Returns None when the contribution cannot close the gap within
    `MAX_HORIZON_MONTHS` — that is "unreachable at this rate", which the caller
    must say out loud rather than dressing up as a far-off date. A goal already
    met returns `start`.
    """
    start = start or date.today()
    months = months_remaining(goal, monthly_contribution)
    if months is None or months > MAX_HORIZON_MONTHS:
        return None
    return add_months(start, months)
