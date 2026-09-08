"""AI safety layer (spec section 16). Runs on every LLM output before it
reaches the user.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.schemas.market import MARKET_DISCLAIMER

FINANCE_DISCLAIMER = (
    "This is educational information calculated from the numbers you entered — "
    "not personalised investment advice."
)

_BANNED_HINTS = ("guaranteed return", "you should buy", "you should sell", "risk-free profit")


def enforce(text: str, *, market_context: bool = False) -> str:
    """Append the correct disclaimer; flag/scrub prediction-style claims."""
    # TODO(phase-5): detect fabricated numbers not present in the context,
    #   rewrite/deny buy/sell imperatives, add disclaimer once.
    disclaimer = MARKET_DISCLAIMER if market_context else FINANCE_DISCLAIMER
    return f"{text}\n\n⚠️ {disclaimer}"
