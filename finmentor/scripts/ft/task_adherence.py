"""Did the answer do the task it was asked to do?

A separate axis from `probes.py`. That file asks whether an answer is *correct*
— right verdicts, right sides, no invented numbers, no advice. This one asks
whether it is the right *kind* of answer, which is a question the existing
checks cannot fail on.

The defect it exists for: `finmentor-3b` scored 38/39 on verdicts and 15/15 on
sides while answering "why is my financial health score what it is?" with a
warm verdict list that never said the word "score". Every tone and grounding
check passed. It was still the wrong answer, because it was a CHAT answer to an
EXPLAIN question.

Two tasks, and the failure runs in both directions:

    EXPLAIN  a precise answer about one thing that was asked about
    CHAT     a short warm reply to a person

so an EXPLAIN answer that reads like a chat is a failure, and a CHAT answer
that reads like a report is equally one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ai.prompts import TASK_CHAT, TASK_EXPLAIN

#: A question's subject, and the words that count as naming it. The model does
#: not have to echo the question, but it does have to be *about* the thing.
SUBJECT_TERMS: dict[str, tuple[str, ...]] = {
    "score": ("score", "out of 100", "/100"),
    "what_if": ("before", "after", "would", "goes from", "instead"),
    "purchase": ("before", "after", "savings", "left"),
    "topic": ("means", "is when", "is a", "refers to"),
    "goal": ("goal", "target", "progress"),
    "unavailable": ("unavailable", "do not have", "empty", "not set"),
}

#: A CHAT answer stays inside this; an EXPLAIN answer is allowed to be longer.
CHAT_MAX_SENTENCES = 6
CHAT_MAX_WORDS = 110
EXPLAIN_MIN_SENTENCES = 2
EXPLAIN_MAX_SENTENCES = 8

#: Openers that only ever belong to a conversation.
CONVERSATIONAL_OPENERS = (
    "good question", "happy to", "let's", "lets ", "sure", "here's what",
    "here is what", "of course", "nice", "great question", "glad",
)

#: Shapes that mean "report", not "reply".
REPORT_MARKERS = (
    "components:", "name:", "points:", "max points:", "detail:",
    "here are your figures", "straight from the calculation",
)


@dataclass
class TaskScore:
    task: str
    passed: bool
    failures: list[str] = field(default_factory=list)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def _is_bulleted(text: str) -> bool:
    """More than a couple of `label: value` lines is a table, whatever the
    formatting. That is the shape a downgraded answer takes, and the shape a
    chat reply must never take."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    labelled = [line for line in lines if re.match(r"^[-*•]?\s*[A-Za-z][\w \-]{,28}:", line)]
    return len(labelled) >= 3


def _names_the_subject(text: str, subject: str) -> bool:
    terms = SUBJECT_TERMS.get(subject, ())
    lowered = (text or "").lower()
    return not terms or any(term in lowered for term in terms)


def score_explain(answer: str, *, subject: str) -> TaskScore:
    """An EXPLAIN answer names what was asked about and stays a short answer."""
    failures: list[str] = []
    body = (answer or "").strip()
    lines = sentences(body)

    if not body:
        return TaskScore(TASK_EXPLAIN, False, ["empty"])
    if not _names_the_subject(body, subject):
        failures.append(f"never names the subject ({subject}): "
                        f"expected one of {SUBJECT_TERMS.get(subject, ())}")
    if len(lines) < EXPLAIN_MIN_SENTENCES:
        failures.append(f"too short for an explanation ({len(lines)} sentences)")
    if len(lines) > EXPLAIN_MAX_SENTENCES:
        failures.append(f"too long for an explanation ({len(lines)} sentences)")
    if _is_bulleted(body):
        failures.append("answered with a table instead of prose")
    if any(marker in body.lower() for marker in REPORT_MARKERS):
        failures.append("reads as a raw context dump")

    return TaskScore(TASK_EXPLAIN, not failures, failures)


def score_chat(answer: str, *, onboarded: bool = True) -> TaskScore:
    """A CHAT answer is short, addressed to a person, and not a report."""
    failures: list[str] = []
    body = (answer or "").strip()
    lines = sentences(body)

    if not body:
        return TaskScore(TASK_CHAT, False, ["empty"])
    if len(lines) > CHAT_MAX_SENTENCES:
        failures.append(f"too long for a reply ({len(lines)} sentences)")
    if len(body.split()) > CHAT_MAX_WORDS:
        failures.append(f"too wordy for a reply ({len(body.split())} words)")
    if _is_bulleted(body):
        failures.append("replied with a table instead of a sentence")
    if any(marker in body.lower() for marker in REPORT_MARKERS):
        failures.append("replied with a raw context dump")
    if "you" not in body.lower():
        failures.append("never addresses the person it is replying to")
    if not onboarded and "/start" not in body:
        failures.append("no profile, and the reply never points at /start")

    return TaskScore(TASK_CHAT, not failures, failures)


def score(answer: str, *, task: str, subject: str = "", onboarded: bool = True) -> TaskScore:
    if task == TASK_EXPLAIN:
        return score_explain(answer, subject=subject)
    if task == TASK_CHAT:
        return score_chat(answer, onboarded=onboarded)
    raise ValueError(f"unknown task: {task!r}")


def looks_conversational(text: str) -> bool:
    """Only used to describe an answer, never to fail one — a good EXPLAIN
    answer may open warmly, and a good CHAT answer need not."""
    return (text or "").strip().lower().startswith(CONVERSATIONAL_OPENERS)
