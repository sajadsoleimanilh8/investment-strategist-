"""Reads over `education_progress` — the observable input to Financial DNA's
knowledge level. The /learn write path lands in phase 6 with the bot.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.simulation import EducationProgress


def count_completed(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(EducationProgress)
        .where(
            EducationProgress.user_id == user_id,
            EducationProgress.completed.is_(True),
        )
    ) or 0
