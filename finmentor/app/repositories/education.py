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


def get(db: Session, user_id: int, topic_key: str) -> EducationProgress | None:
    return db.scalar(
        select(EducationProgress).where(
            EducationProgress.user_id == user_id,
            EducationProgress.topic_key == topic_key,
        )
    )


def list_for_user(db: Session, user_id: int) -> list[EducationProgress]:
    return list(db.scalars(
        select(EducationProgress)
        .where(EducationProgress.user_id == user_id)
        .order_by(EducationProgress.topic_key)
    ))


def record_quiz(
    db: Session, user_id: int, topic_key: str, *, score: int, completed: bool
) -> EducationProgress:
    """Upsert one topic's progress. The caller commits.

    A retake keeps the better score: a lesson learned is not unlearned by a
    careless second attempt, and Financial DNA reads `completed`, not attempts.
    """
    row = get(db, user_id, topic_key)
    if row is None:
        row = EducationProgress(user_id=user_id, topic_key=topic_key)
        db.add(row)

    row.quiz_score = max(score, row.quiz_score or 0)
    row.completed = row.completed or completed
    db.flush()
    return row
