"""learn routes (spec section 17): the 12 curated topics and their quizzes.

Content is static and human-written, never model-generated — an explanation of
compound interest that drifts is worse than no explanation. No LLM is imported
on this path, and a test asserts it.

The quiz write is the only reason these routes need a user: completing a topic
raises the `financial_knowledge` band in Financial DNA, so the score has to
know about it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_user
from app.repositories import education as education_repo
from app.schemas.education import (
    QuizIn, QuizQuestion, QuizResultOut, TopicListOut, TopicOut, TopicSummary,
)
from app.services.education_engine import get_topic, list_topics

router = APIRouter(prefix="/api", tags=["learn"],
                   dependencies=[Depends(require_user)])


def _load_topic(key: str) -> dict:
    topic = get_topic(key)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no lesson on that topic")
    return topic


@router.get("/learn", response_model=TopicListOut)
def list_learn_topics(user: CurrentUser, db: DbSession) -> TopicListOut:
    """Every topic, with this user's progress folded in."""
    progress = {row.topic_key: row for row in education_repo.list_for_user(db, user.id)}
    items = [
        TopicSummary(
            key=topic["key"], title=topic["title"],
            completed=bool(progress.get(topic["key"]) and progress[topic["key"]].completed),
            quiz_score=progress[topic["key"]].quiz_score if topic["key"] in progress else None,
        )
        for topic in list_topics()
    ]
    return TopicListOut(items=items,
                        completed_count=sum(item.completed for item in items))


@router.get("/learn/{key}", response_model=TopicOut)
def read_topic(key: str, user: CurrentUser, db: DbSession) -> TopicOut:
    topic = _load_topic(key)
    row = education_repo.get(db, user.id, key)
    return TopicOut(
        key=key, title=topic["title"], explanation=topic["explanation"],
        example=topic["example"], common_mistake=topic["common_mistake"],
        quiz=QuizQuestion(question=topic["quiz"]["question"],
                          options=topic["quiz"]["options"]),
        completed=bool(row and row.completed),
        quiz_score=row.quiz_score if row else None,
    )


@router.post("/learn/{key}/quiz", response_model=QuizResultOut)
def submit_quiz(key: str, payload: QuizIn, user: CurrentUser, db: DbSession) -> QuizResultOut:
    """Mark the answer and record progress. Wrong answers still count as read.

    A one-question quiz is a comprehension check, not an exam: getting it wrong
    and being shown the answer is the lesson. `completed` is what Financial DNA
    counts, and it is set either way — `quiz_score` is what distinguishes them.
    """
    topic = _load_topic(key)
    quiz = topic["quiz"]
    if payload.answer_idx >= len(quiz["options"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "that option does not exist")

    correct = payload.answer_idx == quiz["answer_idx"]
    score = 100 if correct else 0
    education_repo.record_quiz(db, user.id, key, score=score, completed=True)
    db.commit()

    return QuizResultOut(
        correct=correct, correct_idx=quiz["answer_idx"],
        explanation=topic["common_mistake"], score=score, completed=True,
    )
