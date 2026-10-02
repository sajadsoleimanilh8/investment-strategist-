"""Submitting a quiz: the shared pipeline both surfaces call.

It lives here, next to `ask.py`, for the reason that one does. The HTTP route
recorded progress and the bot did not: tapping through a quiz in Telegram
scored it on screen and wrote nothing, so a bot-only user's
`financial_knowledge` band never moved, while the bot cheerfully read
`count_completed` to display it. That is the same shape of defect as `/ask`
being rate limited while the bot calling the same pipeline was not
(decision 6), and the same fix: one function, both callers.

The engine still does the marking. This adds the transaction and the
refusals, which is delivery-layer work.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import education as education_repo
from app.services.education_engine import get_topic, score_quiz


class QuizRefused(Exception):
    """The submission will not be scored, and the caller should say why.

    Carries a status because one of the two surfaces speaks HTTP; the bot
    shows `message` and ignores the number. Same shape as `AskRefused`.
    """

    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoSuchTopic(QuizRefused):
    status_code = 404


@dataclass(frozen=True)
class QuizResult:
    """What the attempt scored, and why each answer was right or wrong."""

    topic: dict
    #: Per question, in the order they were asked.
    marks: list[bool]
    score: int
    #: Always True. A quiz here is a comprehension check rather than an exam:
    #: being shown why you were wrong is the lesson, and this is the field
    #: Financial DNA counts, so a wrong answer still advances the band.
    completed: bool = True

    @property
    def correct_count(self) -> int:
        return sum(self.marks)

    @property
    def total(self) -> int:
        return len(self.marks)


def submit(db: Session, *, user_id: int, key: str, answers: list[int]) -> QuizResult:
    """Mark a set of answers, record the progress, and report what happened.

    Validates before scoring, because a submission with the wrong number of
    answers is a client bug and scoring it would record a number the user
    never earned: treating the missing ones as wrong invents a failure, and
    scoring only what arrived would make a single answer worth 100%.
    """
    topic = get_topic(key)
    if topic is None:
        raise NoSuchTopic("no lesson on that topic")

    questions = topic["questions"]
    if len(answers) != len(questions):
        raise QuizRefused(
            f"this quiz has {len(questions)} questions and "
            f"{len(answers)} answers were sent"
        )
    for index, (answer, question) in enumerate(zip(answers, questions)):
        if not 0 <= answer < len(question["options"]):
            raise QuizRefused(f"question {index + 1} has no option {answer}")

    score, marks = score_quiz(topic, answers)
    education_repo.record_quiz(db, user_id, key, score=score, completed=True)
    db.commit()
    return QuizResult(topic=topic, marks=marks, score=score)
