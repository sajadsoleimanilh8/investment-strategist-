"""Intent detection + scenario parsing (spec section 33).

User text -> {intent, structured params}. This is the ONLY place free text
becomes engine input, and it is the boundary the architecture rule protects:
everything downstream is deterministic arithmetic on the params produced here.

Phase 3 is rule-only — regex and keywords, no LLM, no network. `llm_fallback`
marks where the phase-5 parser will hook in; today it returns a low-confidence
unparsed result, so a sentence we cannot read is reported as unread rather than
guessed at.

Known coverage gaps (deliberate; each would need either more rules or the
phase-5 fallback):
- One lever per sentence. "save $2M more and cut expenses 10%" keeps the
  savings lever and drops the expense one.
- Category deltas only match the eight `ExpenseBreakdown` categories by their
  own name; "eating out" or "rent" are not mapped to food/housing.
- No dates or horizons are parsed: "over the next 2 years" does not set
  `horizon_months`, which keeps its schema default.
- Relative wording without a number ("save a bit more") is unparsed.
- Decision intent requires a price in the sentence; "should I buy a laptop?"
  has no number, so it comes back unparsed rather than as a decision with a
  missing price.
- Market intent is recognised but carries no symbol extraction yet (phase 4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.simulation import WhatIfParams
from app.services.education_engine import TOPICS

INTENTS = ("what_if", "decision", "market", "education", "health", "smalltalk")

#: Confidence a rule match reports. Rules either fire on a clear phrase or not
#: at all, so this is a coarse three-level signal, not a probability.
STRONG_MATCH = 0.9
WEAK_MATCH = 0.5
NO_MATCH = 0.1

_MAGNITUDES = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}

#: "$5M", "5 million", "5,000,000", "40k" -> the number and where it was found.
_AMOUNT_RE = re.compile(
    r"(?<![\w.])[$€£]?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(k|thousand|mm|m|million|b|billion)?\b",
    re.IGNORECASE,
)
# NB: the word boundary belongs to the spelled-out forms only. "%" is not a
# word character, so a trailing word-boundary escape would fail on "20%?".
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b|pct\b)", re.IGNORECASE)

_EXPENSE_CATEGORIES = (
    "housing", "food", "transportation", "education",
    "bills", "entertainment", "shopping", "other",
)

_DECISION_HINTS = ("should i buy", "can i afford", "buy a", "buy the", "worth buying")
_WHAT_IF_HINTS = ("what if", "what happens if", "if i ", "suppose i ", "imagine i ")
_WHAT_IF_LEVERS = ("save", "saving", "income", "salary", "earn", "expense", "spend", "spending")
_MARKET_HINTS = ("price of", "market", "trend", "stock", "crypto", "bitcoin", "ethereum",
                 "how is btc", "watchlist")
_HEALTH_HINTS = ("score", "financial health", "how am i doing", "my health")
_EDUCATION_HINTS = ("what does", "what is", "what's", "explain", "mean", "meaning of",
                    "teach me", "learn about")


@dataclass
class ParsedIntent:
    intent: str
    what_if: WhatIfParams | None = None
    purchase_price: float | None = None
    topic_key: str | None = None
    raw: str = ""
    confidence: float = NO_MATCH
    unparsed: bool = False
    #: which rules fired, for debugging and for the phase-5 prompt context
    matched: list[str] = field(default_factory=list)


def parse_amount(text: str) -> float | None:
    """First money-like amount in the text, magnitude suffix applied."""
    match = _AMOUNT_RE.search(text)
    if match is None:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    return number * _MAGNITUDES.get(suffix, 1)


def parse_percent(text: str) -> float | None:
    """"15%" / "15 percent" / "15 pct" -> 0.15."""
    match = _PERCENT_RE.search(text)
    return float(match.group(1)) / 100 if match else None


def _find_topic(lowered: str) -> str | None:
    """An education topic by key ("compound_growth"), spaced key, or title."""
    for key, topic in TOPICS.items():
        if key in lowered or key.replace("_", " ") in lowered:
            return key
        if topic["title"].lower() in lowered:
            return key
    return None


def _is_negative_direction(lowered: str) -> bool:
    return any(word in lowered for word in ("down", "drop", "fall", "cut", "less", "lower",
                                            "decrease", "reduce"))


def _what_if_params(lowered: str) -> tuple[WhatIfParams | None, list[str]]:
    """Fill the levers this sentence actually names. First strong lever wins."""
    percent = parse_percent(lowered)
    amount = parse_amount(lowered)
    negative = _is_negative_direction(lowered)

    # "spend $X less on entertainment" / "spend $X more on food"
    for category in _EXPENSE_CATEGORIES:
        if category in lowered and amount is not None:
            signed = -amount if negative else amount
            return WhatIfParams(expense_category_delta={category: signed}), [
                "expense_category_delta", category
            ]

    if percent is not None:
        if any(word in lowered for word in ("income", "salary", "earn", "raise")):
            return WhatIfParams(income_pct_delta=-percent if negative else percent), [
                "income_pct_delta"
            ]
        if any(word in lowered for word in ("expense", "spend", "spending", "cost")):
            return WhatIfParams(expense_pct_delta=-percent if negative else percent), [
                "expense_pct_delta"
            ]

    if amount is not None and any(word in lowered for word in ("save", "saving", "put aside")):
        return WhatIfParams(monthly_savings_delta=-amount if negative else amount), [
            "monthly_savings_delta"
        ]

    return None, []


def llm_fallback(text: str) -> ParsedIntent:
    """Phase-5 hook: an LLM parser constrained to the same schema.

    Until then this reports "I could not read that" rather than guessing — an
    unparsed result is a safe outcome, an invented scenario is not.
    """
    # TODO(phase-5): call the local model with a schema-constrained prompt and
    #   validate its output into WhatIfParams before returning it.
    return ParsedIntent(intent="smalltalk", raw=text, confidence=NO_MATCH, unparsed=True)


def parse(text: str) -> ParsedIntent:
    """Route free text to an intent and, where possible, structured params."""
    raw = text or ""
    lowered = raw.lower().strip()
    if not lowered:
        return llm_fallback(raw)

    # decision: needs a price to be actionable
    if any(hint in lowered for hint in _DECISION_HINTS):
        price = parse_amount(lowered)
        if price is not None:
            return ParsedIntent(intent="decision", purchase_price=price, raw=raw,
                                confidence=STRONG_MATCH, matched=["decision", "price"])
        return llm_fallback(raw)

    # what-if: a hypothetical phrase plus a lever we can quantify
    if any(hint in lowered for hint in _WHAT_IF_HINTS) and any(
        lever in lowered for lever in _WHAT_IF_LEVERS
    ):
        params, matched = _what_if_params(lowered)
        if params is not None:
            return ParsedIntent(intent="what_if", what_if=params, raw=raw,
                                confidence=STRONG_MATCH, matched=["what_if", *matched])
        return llm_fallback(raw)

    # education: an explain-style question about a topic we actually have
    topic = _find_topic(lowered)
    if topic is not None and any(hint in lowered for hint in _EDUCATION_HINTS):
        return ParsedIntent(intent="education", topic_key=topic, raw=raw,
                            confidence=STRONG_MATCH, matched=["education", topic])

    if any(hint in lowered for hint in _HEALTH_HINTS):
        return ParsedIntent(intent="health", raw=raw, confidence=STRONG_MATCH,
                            matched=["health"])

    if any(hint in lowered for hint in _MARKET_HINTS):
        return ParsedIntent(intent="market", raw=raw, confidence=WEAK_MATCH,
                            matched=["market"])

    # a bare topic mention with no question phrasing is a weak education hit
    if topic is not None:
        return ParsedIntent(intent="education", topic_key=topic, raw=raw,
                            confidence=WEAK_MATCH, matched=["education", topic])

    return llm_fallback(raw)
