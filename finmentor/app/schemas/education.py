"""Education contracts (spec section 17).

The listing deliberately omits the quiz answer. A client that can see
`answer_idx` before the user answers is a client that can spoil the quiz, and
the whole point of the topic list is that it is safe to fetch eagerly.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TopicSummary(BaseModel):
    key: str
    title: str
    completed: bool = False
    quiz_score: int | None = None


class QuizQuestion(BaseModel):
    question: str
    options: list[str]


class TopicOut(BaseModel):
    key: str
    title: str
    explanation: str
    example: str
    common_mistake: str
    quiz: QuizQuestion
    completed: bool = False
    quiz_score: int | None = None


class TopicListOut(BaseModel):
    items: list[TopicSummary]
    completed_count: int


class QuizIn(BaseModel):
    answer_idx: int = Field(ge=0, le=10)


class QuizResultOut(BaseModel):
    correct: bool
    correct_idx: int
    explanation: str          # why that answer, drawn from the curated topic
    score: int                # 0 or 100 for a one-question quiz
    completed: bool
