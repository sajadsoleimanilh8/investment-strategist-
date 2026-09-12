"""AI safety layer (spec section 16). Runs on every LLM output before it
reaches the user — no exceptions, no path around it.

Three jobs, in order:

1. Scrub buy/sell imperatives. FinMentor explains situations; it never tells
   anyone to buy or sell. Only the offending *sentence* is dropped, so
   educational prose that merely mentions buying ("buying only one asset is
   risky") survives untouched.
2. Reject fabricated numbers. Every figure in the text must trace back to the
   deterministic context. If one does not, the model's text is discarded
   entirely and the verified context is rendered instead — a wrong number is
   worse than a plain answer, so this fails safe rather than trying to patch.
3. Add exactly one disclaimer, and only if it is not already there.

Pure function: no I/O, no network, no model call.
"""
from __future__ import annotations

import re
from typing import Any

from app.ai.rendering import render_context
from app.schemas.market import MARKET_DISCLAIMER

FINANCE_DISCLAIMER = (
    "This is educational information calculated from the numbers you entered — "
    "not personalised investment advice."
)

#: A number in the text is grounded if it lands within this fraction of a
#: context number. 1% absorbs the model restating $10,500,000 as $10.5M while
#: still catching an invented figure.
NUMBER_TOLERANCE = 0.01

#: A year is prose, not a financial claim: "by 2027" needs no grounding.
YEAR_RANGE = (2024, 2035)
#: Scale denominators the product itself defines — "62.3 out of 100", "17.5/20".
#: Quoting the scale is not inventing a figure.
SCALE_NUMBERS = frozenset({20, 100})

# Small integers are deliberately NOT exempt. An earlier version waved through
# anything from 0 to 12 as "just a count", and a live 3B used exactly that gap
# to report a component "worth 0 points" when the context said 12. Counts the
# model may legitimately quote ("1 active goal(s)") are in the context already,
# so the exemption bought nothing and cost a wrong number. The price is the
# occasional downgrade on innocuous prose, which is the safe direction.

#: Directive phrasing. Each matches a whole clause, and the sentence carrying
#: it is removed rather than reworded — a half-rewritten instruction is worse
#: than a missing sentence.
_BUY_SELL_PATTERNS = (
    r"\byou\s+should\s+(?:buy|sell|invest\s+in|purchase)\b",
    r"\byou\s+(?:must|need\s+to|have\s+to)\s+(?:buy|sell|invest)\b",
    r"\bi\s+(?:recommend|suggest|advise)\s+(?:buying|selling|investing)\b",
    r"\bput\s+(?:your|all\s+your)\s+money\s+(?:in|into)\b",
    r"\bnow\s+is\s+the\s+time\s+to\s+(?:buy|sell|invest)\b",
    r"\bguaranteed\s+(?:return|returns|profit|profits|gains?)\b",
    r"\brisk[-\s]free\s+(?:profit|return|returns|investment)\b",
    r"\b(?:buy|sell)\s+(?:now|immediately|today)\b",
    # verdicts, not imperatives: a live 3B closed a purchase answer with
    # "therefore, it is not advisable to buy the laptop"
    r"\b(?:not\s+)?advisable\s+to\s+(?:buy|sell|invest|purchase)\b",
    r"\b(?:a\s+)?(?:good|bad)\s+idea\s+to\s+(?:buy|sell|invest|purchase)\b",
    r"\byou\s+(?:should|shouldn't|should\s+not)\s+(?:buy|sell|invest|purchase)\b",
    r"\bi\s+would\s+(?:not\s+)?recommend\b",
    r"\b(?:do\s+not|don't)\s+(?:buy|sell|invest\s+in)\b",
    r"\bworth\s+(?:buying|selling)\b",
)
_BUY_SELL_RE = re.compile("|".join(_BUY_SELL_PATTERNS), re.IGNORECASE)

#: A number with optional currency, thousands separators, decimals, magnitude
#: suffix or percent sign. The suffix needs its own word boundary: without it
#: "1.8 months" reads as 1.8 million and "62.3 but" as 62.3 billion.
_NUMBER_RE = re.compile(
    r"[$€£]?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?:(k|thousand|m|mm|million|b|billion)(?![a-z]))?\s*(%)?",
    re.IGNORECASE,
)
_MAGNITUDES = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT_RE.split(text.strip()) if part]


def scrub_directives(text: str) -> tuple[str, bool]:
    """Drop any sentence that instructs the user to trade. Returns (text, changed)."""
    kept = [s for s in split_sentences(text) if not _BUY_SELL_RE.search(s)]
    cleaned = " ".join(kept).strip()
    changed = len(kept) != len(split_sentences(text))
    if changed and not cleaned:
        cleaned = "I can explain what your numbers mean, but I do not give buy or sell advice."
    return cleaned, changed


def numbers_in_text(text: str) -> list[float]:
    """Every figure a reader would see, with magnitude suffixes applied.

    A percentage yields both readings — "35%" may restate a stored rate of
    0.35 or a stored score of 35 — and grounding accepts either.
    """
    found: list[float] = []
    for raw, suffix, percent in _NUMBER_RE.findall(text):
        value = float(raw.replace(",", "")) * _MAGNITUDES.get(suffix.lower(), 1)
        found.append(value)
        if percent:
            found.append(value / 100)
    return found


def numbers_in_context(context: Any) -> list[float]:
    """Every number anywhere in the context, including inside strings.

    Details like "35.0% of income saved" carry figures the model will quote
    back, so the strings are mined too — otherwise a faithful quote would be
    flagged as invented.
    """
    numbers: list[float] = []
    if isinstance(context, dict):
        for value in context.values():
            numbers.extend(numbers_in_context(value))
    elif isinstance(context, (list, tuple)):
        for item in context:
            numbers.extend(numbers_in_context(item))
    elif isinstance(context, bool):
        pass
    elif isinstance(context, (int, float)):
        numbers.append(float(context))
        numbers.append(float(context) * 100)      # a stored rate quoted as a percent
        # ...and the mirror, but only for a value that could *be* a percentage.
        # `numbers_in_text` reads "5%" as both 5 and 0.05, so a context holding
        # `progress_pct: 5.0` must ground 0.05 or quoting its own figure looks
        # invented. Values at or below 1 are already fractions and need no
        # mirror — adding one would scatter near-zero numbers through the
        # grounding set and quietly make a claimed "0" acceptable.
        if abs(float(context)) > 1:
            numbers.append(float(context) / 100)
        # The magnitude, because `numbers_in_text` reads no sign: "$-36,000,000"
        # comes back as 36,000,000. Without this a purchase that overdraws
        # someone flags its own deterministic rendering as invented, and every
        # negative figure downgrades an otherwise correct answer. A sign is a
        # direction, and direction is what the labelled before/after block and
        # the verdict words are for — grounding is about the magnitude.
        numbers.append(abs(float(context)))
    elif isinstance(context, str):
        numbers.extend(numbers_in_text(context))
    return numbers


def _decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text else 0


def is_grounded(value: float, context_numbers: list[float]) -> bool:
    """Does this figure trace back to the context?

    Three ways to qualify: it is within tolerance of a context number, it is
    that number rounded to the precision the model chose to write ("1.8 months"
    for 1.82), or it is a year or a scale denominator, neither of which asserts
    anything about the user's money.
    """
    if float(value).is_integer():
        whole = int(value)
        if YEAR_RANGE[0] <= whole <= YEAR_RANGE[1] or whole in SCALE_NUMBERS:
            return True

    precision = _decimals(value)
    for candidate in context_numbers:
        if abs(value - candidate) <= NUMBER_TOLERANCE * max(abs(candidate), 1.0):
            return True
        # Rounding may not manufacture a zero. `round(0.0182, 0)` is 0.0, so
        # without this a model claiming a component is "worth 0" is grounded by
        # any small number anywhere in the context — which is the exact defect
        # the ordinal exemption was removed to catch.
        if round(candidate, precision) == value and (value != 0 or candidate == 0):
            return True
    return False


def ungrounded_numbers(text: str, context: Any) -> list[float]:
    context_numbers = numbers_in_context(context)
    return [
        value for value in numbers_in_text(text)
        if not is_grounded(value, context_numbers)
    ]


def add_disclaimer(text: str, *, market_context: bool) -> tuple[str, bool]:
    """Add the disclaimer — but only to a reply that actually makes a claim.

    Every market answer gets one; the market disclaimer is about the *topic*,
    not any specific figure. Off the market path, a disclaimer is only
    warranted when the reply cites a figure — a greeting or "you're welcome!"
    has nothing to disclaim, and stamping the same boilerplate onto every
    message in a conversation is what made the guide read as a form letter
    rather than a person. A real explanation almost always contains a number,
    so this doesn't change behaviour on the precise (explain) path at all.
    """
    disclaimer = MARKET_DISCLAIMER if market_context else FINANCE_DISCLAIMER
    if disclaimer in text:
        return text, False
    # An empty reply isn't "no claim" the way a greeting is — it's more likely
    # something went wrong upstream, so it keeps the disclaimer rather than
    # being treated as harmless small talk.
    if not market_context and text.strip() and not numbers_in_text(text):
        return text, False
    return f"{text.strip()}\n\n⚠️ {disclaimer}", True


def enforce(
    text: str, *, context: dict, market_context: bool = False
) -> tuple[str, dict]:
    """Make model text safe to show. Returns (clean_text, report).

    The report says what happened rather than hiding it, so the route can log
    a downgrade and tests can assert on the reason.
    """
    report = {
        "buy_sell_scrubbed": False,
        "ungrounded_numbers": [],
        "disclaimer_added": False,
        "downgraded": False,
    }

    cleaned, scrubbed = scrub_directives(text or "")
    report["buy_sell_scrubbed"] = scrubbed

    invented = ungrounded_numbers(cleaned, context)
    if invented:
        # Fail safe: show the verified figures instead of the model's text.
        report["ungrounded_numbers"] = invented
        report["downgraded"] = True
        cleaned = render_context(
            context,
            preamble="Here are your figures, straight from the calculation:",
        )

    cleaned, added = add_disclaimer(cleaned, market_context=market_context)
    report["disclaimer_added"] = added
    return cleaned, report
