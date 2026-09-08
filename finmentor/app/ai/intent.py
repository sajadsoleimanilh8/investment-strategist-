"""Intent detection + scenario parsing (spec section 33).

User text -> {intent, structured params}. This is the ONLY place free text
becomes engine input. Rule-first (regex/keywords); the LLM is a fallback
parser that must still emit the strict schema.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.simulation import WhatIfParams

INTENTS = ("what_if", "decision", "market", "education", "health", "smalltalk")


@dataclass
class ParsedIntent:
    intent: str
    what_if: WhatIfParams | None = None
    purchase_price: float | None = None
    topic_key: str | None = None
    raw: str = ""


def parse(text: str) -> ParsedIntent:
    # TODO(phase-3/5): English number parsing ("5M", "5 million", "15%"),
    #   keyword routing, then LLM-assisted extraction constrained to the schema.
    raise NotImplementedError("phase-3")
