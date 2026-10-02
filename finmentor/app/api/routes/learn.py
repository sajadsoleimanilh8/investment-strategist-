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

from app.api import quiz as quiz_pipeline
from app.api.deps import CurrentUser, DbSession, require_user
from app.repositories import education as education_repo
from app.schemas.education import (
    QuizAnswerOut, QuizIn, QuizQuestion, QuizResultOut, TopicListOut, TopicOut,
    TopicSummary,
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
        questions=[QuizQuestion(question=question["question"],
                                options=question["options"])
                   for question in topic["questions"]],
        completed=bool(row and row.completed),
        quiz_score=row.quiz_score if row else None,
    )


@router.post("/learn/{key}/quiz", response_model=QuizResultOut)
def submit_quiz(key: str, payload: QuizIn, user: CurrentUser, db: DbSession) -> QuizResultOut:
    """Mark the answers and record progress. A wrong answer still counts as read.

    The marking, the validation and the write live in `app/api/quiz.py`,
    which the Telegram bot calls as well. They used to live here, and the bot
    scored its quiz on screen and recorded nothing -- so a bot-only user's
    `financial_knowledge` band never moved while the bot displayed it.

    What a score means did change with three questions: it is the percentage
    right, so 0, 33, 67 or 100. Scores recorded by the one-question version
    read as 0 or 100 and still mean what they meant. `completed` is what
    Financial DNA counts, and it is still set either way, so nobody's
    existing band moves.
    """
    try:
        result = quiz_pipeline.submit(db, user_id=user.id, key=key,
                                      answers=payload.answers)
    except quiz_pipeline.QuizRefused as refused:
        raise HTTPException(refused.status_code, refused.message)

    return QuizResultOut(
        answers=[
            QuizAnswerOut(correct=mark, correct_idx=question["answer_idx"],
                          why=question["why"])
            for mark, question in zip(result.marks, result.topic["questions"])
        ],
        correct_count=result.correct_count,
        total=result.total,
        score=result.score,
        completed=result.completed,
        common_mistake=result.topic["common_mistake"],
    )
