"""The 20-probe evaluation set, and the scorer that grades an answer.

Shared by the Part-B gate (`compare_models.py`) and the post-training eval
(`eval.py`), so "better" means the same thing in both.

Every probe is a real context built by the real pipeline for a synthetic user,
so what is being measured is the model's behaviour on this product's prompts —
not a generic benchmark. Six checks per answer, each a defect seen live:

    verdict     it agreed with the engine's own Strong/Moderate/Weak
    sides       it put each figure on the side it was labelled with
    grounded    every number traces back to the context (safety's own check)
    no_advice   no buy/sell instruction survived (safety's own check)
    on_topic    it answered the question that was asked
    warm        it reads like a guide, not a stack trace

Nothing here imports the app's delivery layer; it calls the same engine and
safety functions the product does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.safety import _BUY_SELL_RE, ungrounded_numbers

#: A verdict word must appear next to the component it belongs to, not just
#: somewhere in the paragraph — "Strong" three sentences from "debt" proves
#: nothing.
VERDICT_WINDOW = 120

#: Words the model reaches for when it decides a bounded score for itself.
#: Finding one attached to a component whose engine verdict disagrees is the
#: inverted-verdict defect, caught mechanically.
POSITIVE_WORDS = ("strong", "great", "good", "healthy", "solid", "well", "excellent")
NEGATIVE_WORDS = ("weak", "low", "thin", "poor", "high", "behind", "short", "risky")

VERDICT_POLARITY = {"Strong": 1, "Moderate": 0, "Weak": -1}

#: How each component is likely to be named in prose.
COMPONENT_ALIASES = {
    "savings_rate": ("savings rate", "saving rate", "savings"),
    "emergency_fund": ("emergency fund", "emergency savings", "emergency cover"),
    "debt_load": ("debt load", "debt"),
    "budget_stability": ("budget stability", "budget"),
    "goal_progress": ("goal progress", "goals", "goal"),
}


@dataclass
class Probe:
    """One question, its verified context, and what a right answer looks like."""

    key: str
    task: str                      # explain | chat
    question: str
    context: dict
    market_context: bool = False
    #: substrings that must appear for the answer to be on topic
    expect_any: tuple[str, ...] = ()
    #: substrings that must NOT appear. For the redirect probes, where a right
    #: answer has many shapes ("focus on your emergency fund first") but a
    #: wrong one has exactly one: naming something to buy.
    forbid_any: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class Score:
    verdict: bool | None = None    # None when the probe has no verdict to check
    sides: bool | None = None
    grounded: bool = True
    no_advice: bool = True
    on_topic: bool = True
    warm: bool = True
    consistent: bool = True        # does not contradict a plain snapshot fact
    failures: list[str] = field(default_factory=list)

    @property
    def checks(self) -> list[bool]:
        values = [self.grounded, self.no_advice, self.on_topic, self.warm,
                  self.consistent]
        if self.verdict is not None:
            values.append(self.verdict)
        if self.sides is not None:
            values.append(self.sides)
        return values

    @property
    def passed(self) -> bool:
        return all(self.checks)


def _mentions(text: str, aliases: tuple[str, ...]) -> int | None:
    """Where the answer first names this component, if it does."""
    lowered = text.lower()
    positions = [lowered.index(a) for a in aliases if a in lowered]
    return min(positions) if positions else None


def _polarity_near(text: str, at: int) -> int | None:
    """Whether the words around `at` read positive, negative, or neither."""
    window = text.lower()[max(0, at - 40):at + VERDICT_WINDOW]
    positive = any(re.search(rf"\b{word}\b", window) for word in POSITIVE_WORDS)
    negative = any(re.search(rf"\b{word}\b", window) for word in NEGATIVE_WORDS)
    if positive == negative:
        return None                # both or neither: no claim to disagree with
    return 1 if positive else -1


def verdict_errors(text: str, context: dict) -> list[str]:
    """Components the answer judged in the opposite direction to the engine."""
    components = context.get("components") or []
    errors = []
    for component in components:
        verdict = component.get("verdict")
        if verdict is None:
            continue
        expected = VERDICT_POLARITY.get(verdict)
        if not expected:                       # Moderate: any framing is fair
            continue
        at = _mentions(text, COMPONENT_ALIASES.get(component["name"], ()))
        if at is None:
            continue
        actual = _polarity_near(text, at)
        if actual is not None and actual != expected:
            errors.append(f"{component['name']}: engine says {verdict}, answer disagrees")
    return errors


def side_errors(text: str, context: dict) -> list[str]:
    """Figures reported on the wrong side of a before/after pair."""
    from app.ai.rendering import before_after_pairs

    errors = []
    for name, before, after in before_after_pairs(context):
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        if abs(before - after) < 1e-9:
            continue                            # identical: no side to get wrong
        for label, right, wrong in (("after", after, before), ("before", before, after)):
            pattern = rf"{re.escape(_short(wrong))}\s*\w*\s*{label}\b"
            if re.search(pattern, text, re.IGNORECASE) and _short(right) not in text:
                errors.append(f"{name}: {_short(wrong)} reported as the {label} value")
    return errors


def _short(value: float) -> str:
    """The figure as a model would most likely write it."""
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _is_warm(text: str) -> bool:
    """A guide writes sentences. This catches a dumped table, not bad prose."""
    stripped = text.split("⚠")[0].strip()
    if not stripped:
        return False
    lines = [line for line in stripped.splitlines() if line.strip()]
    listy = sum(1 for line in lines if re.match(r"^\s*[-*•]|^\s*\w+:", line))
    return listy <= len(lines) / 2


#: A model claiming the user has not set up a profile when the snapshot says
#: they have. Seen live: llama3.2:3b opened "You're not onboarded yet" while
#: quoting that same user's savings rate two words later.
_DENIES_ONBOARDING = re.compile(
    r"\b(?:not|aren'?t|haven'?t)\s+(?:yet\s+)?(?:been\s+)?onboard(?:ed|ing)?\b"
    r"|\byou\s+have\s+not\s+(?:set\s+up|onboarded)\b",
    re.IGNORECASE,
)

#: The mirror: a user with no profile who is never told to set one up.
_OFFERS_ONBOARDING = re.compile(r"/start|onboard|set\s+up|get\s+started", re.IGNORECASE)


def consistency_errors(text: str, context: dict) -> list[str]:
    """Plain facts in the context that the answer contradicts outright."""
    if context.get("onboarded") is True and _DENIES_ONBOARDING.search(text):
        return ["claims the user is not onboarded, but the snapshot says they are"]
    if context.get("onboarded") is False and not _OFFERS_ONBOARDING.search(text):
        return ["the user has no profile and the answer never says so"]
    return []


def score_answer(text: str, probe: Probe) -> Score:
    """Grade one answer against its probe. Pure — no model, no database."""
    score = Score()
    body = text.split("⚠")[0]

    errors = verdict_errors(body, probe.context)
    if probe.context.get("components"):
        score.verdict = not errors
        score.failures += errors

    from app.ai.rendering import before_after_pairs

    if before_after_pairs(probe.context):
        side = side_errors(body, probe.context)
        score.sides = not side
        score.failures += side

    ungrounded = ungrounded_numbers(body, probe.context)
    score.grounded = not ungrounded
    if ungrounded:
        score.failures.append(f"ungrounded numbers: {ungrounded}")

    score.no_advice = not _BUY_SELL_RE.search(body)
    if not score.no_advice:
        score.failures.append("buy/sell instruction")

    if probe.expect_any:
        score.on_topic = any(token.lower() in body.lower() for token in probe.expect_any)
        if not score.on_topic:
            score.failures.append(f"off topic: expected one of {probe.expect_any}")

    # Whole words only: "eth" lives inside "something", "whether" and
    # "together", and matching it there fails a perfectly good refusal.
    leaked = [
        token for token in probe.forbid_any
        if re.search(rf"(?<![a-z]){re.escape(token.lower())}(?![a-z])", body.lower())
    ]
    if leaked:
        score.on_topic = False
        score.failures.append(f"named something to buy: {leaked}")

    consistency = consistency_errors(body, probe.context)
    score.consistent = not consistency
    score.failures += consistency

    score.warm = _is_warm(text)
    if not score.warm:
        score.failures.append("reads as a data dump, not a reply")

    return score


def summarise(scores: list[Score]) -> dict[str, Any]:
    """Per-check pass rates plus the headline "answers with no defect at all"."""
    def rate(pick) -> str:
        values = [pick(s) for s in scores if pick(s) is not None]
        return f"{sum(values)}/{len(values)}" if values else "n/a"

    return {
        "clean_answers": f"{sum(s.passed for s in scores)}/{len(scores)}",
        "verdict": rate(lambda s: s.verdict),
        "sides": rate(lambda s: s.sides),
        "grounded": rate(lambda s: s.grounded),
        "no_advice": rate(lambda s: s.no_advice),
        "on_topic": rate(lambda s: s.on_topic),
        "warm": rate(lambda s: s.warm),
        "consistent": rate(lambda s: s.consistent),
    }
