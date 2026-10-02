"""Education contracts (spec section 17).

The listing deliberately omits the quiz answers. A client that can see
`answer_idx` before the user answers is a client that can spoil the quiz, and
the whole point of the topic list is that it is safe to fetch eagerly. That
holds for three questions exactly as it held for one: `QuizQuestion` carries
the prompt and the options and nothing else, and `why` travels only in the
result, after the answer has been given.
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
    questions: list[QuizQuestion]
    completed: bool = False
    quiz_score: int | None = None


class TopicListOut(BaseModel):
    items: list[TopicSummary]
    completed_count: int


class QuizIn(BaseModel):
    """One chosen option index per question, in order.

    Bounded on both axes. `max_length` is the ceiling on questions a topic can
    ever have rather than the number it has, because the route checks the
    exact count against the topic and can say so; the schema bound is here to
    stop a thousand-element list being parsed at all.
    """

    answers: list[int] = Field(min_length=1, max_length=20)


class QuizAnswerOut(BaseModel):
    """How one question went, returned only after it was answered."""

    correct: bool
    correct_idx: int
    #: Why that option is the right one. Specific to this question, not the
    #: topic: the old result returned the topic's `common_mistake` whatever
    #: the user got wrong.
    why: str


class QuizResultOut(BaseModel):
    """The whole attempt. `answers` is in the order the questions were asked."""

    answers: list[QuizAnswerOut]
    correct_count: int
    total: int
    #: Percentage, rounded. Three questions give 0, 33, 67 or 100, which fits
    #: the 0..100 the progress table already enforces.
    score: int
    #: True whatever the score. A quiz here is a comprehension check, not an
    #: exam: getting one wrong and being shown why is the lesson. This is also
    #: what Financial DNA counts, so a richer quiz does not move anybody's
    #: existing band.
    completed: bool
    #: The topic's own note, still returned because it is worth reading after
    #: the quiz whether or not any single answer was wrong.
    common_mistake: str
