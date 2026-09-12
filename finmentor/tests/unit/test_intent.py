"""Fixture-driven parser tests: free text -> intent + structured params.

Phase 3 is rule-only, so every expectation here is exact — no LLM, no
tolerance. Anything the rules cannot read must come back `unparsed`, never
guessed.
"""
import pytest

from app.ai import intent as intent_module
from app.ai.intent import INTENTS, ParsedIntent, parse, parse_amount, parse_percent
from app.schemas.simulation import WhatIfParams

# (text, expected intent, expected WhatIfParams | None, expected price, expected topic)
FIXTURES = [
    # --- what-if: the canonical flow -----------------------------------
    ("what if I save $5M more each month?", "what_if",
     WhatIfParams(monthly_savings_delta=5_000_000), None, None),
    ("what if my income goes up 20%?", "what_if",
     WhatIfParams(income_pct_delta=0.20), None, None),
    ("what if expenses increase 15%?", "what_if",
     WhatIfParams(expense_pct_delta=0.15), None, None),
    ("what if my salary drops 10%?", "what_if",
     WhatIfParams(income_pct_delta=-0.10), None, None),
    ("what if I spend $900K less on entertainment?", "what_if",
     WhatIfParams(expense_category_delta={"entertainment": -900_000}), None, None),
    ("what if I save 2 million more a month", "what_if",
     WhatIfParams(monthly_savings_delta=2_000_000), None, None),
    ("what if I save 750,000 more each month", "what_if",
     WhatIfParams(monthly_savings_delta=750_000), None, None),
    ("suppose I earn 25 percent more", "what_if",
     WhatIfParams(income_pct_delta=0.25), None, None),
    # --- decision ------------------------------------------------------
    ("should I buy a $40M laptop?", "decision", None, 40_000_000, None),
    ("can I afford a 12,000,000 phone?", "decision", None, 12_000_000, None),
    ("should I buy a 3.5M bike", "decision", None, 3_500_000, None),
    # --- education -----------------------------------------------------
    ("what does volatility mean?", "education", None, None, "volatility"),
    ("explain compound growth", "education", None, None, "compound_growth"),
    ("what is an emergency fund?", "education", None, None, "emergency_fund"),
    # --- health / market ----------------------------------------------
    ("why did my score drop?", "health", None, None, None),
    ("how is my financial health?", "health", None, None, None),
    ("what is the price of bitcoin?", "market", None, None, None),
    ("how is btc doing", "market", None, None, None),
    # --- a definitional question with no curated topic must NOT become a
    # market lookup just because it names an asset (live bug: "what is
    # bitcoin?" returned a raw BTC price/trend dump instead of an answer) —
    # it goes to the guide instead, same as any other unparsed message.
    ("what is bitcoin?", "smalltalk", None, None, None),
    ("what does crypto mean?", "smalltalk", None, None, None),
    ("what is ethereum?", "smalltalk", None, None, None),
    # --- ambiguous / garbage: must come back unparsed ------------------
    ("asdkjhasd", "smalltalk", None, None, None),
    ("hello there", "smalltalk", None, None, None),
    ("what if I save a bit more", "smalltalk", None, None, None),
    ("", "smalltalk", None, None, None),
]


@pytest.mark.parametrize(("text", "expected_intent", "params", "price", "topic"), FIXTURES)
def test_fixtures(text, expected_intent, params, price, topic):
    result = parse(text)

    assert result.intent == expected_intent, f"{text!r} routed to {result.intent}"
    assert result.what_if == params
    assert result.purchase_price == price
    assert result.topic_key == topic
    assert result.raw == text


@pytest.mark.parametrize(("text", "expected_intent", "_p", "_pr", "_t"), FIXTURES)
def test_unparsed_flag_matches_the_routing(text, expected_intent, _p, _pr, _t):
    result = parse(text)

    if expected_intent == "smalltalk":
        assert result.unparsed is True
        assert result.confidence <= 0.1
    else:
        assert result.unparsed is False
        assert result.confidence >= 0.5


def test_every_route_returns_a_known_intent():
    assert all(parse(text).intent in INTENTS for text, *_ in FIXTURES)


# --- number parsing -----------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$5M", 5_000_000), ("5 million", 5_000_000), ("5,000,000", 5_000_000),
        ("40k", 40_000), ("40 thousand", 40_000), ("2.5m", 2_500_000),
        ("1b", 1_000_000_000), ("3 billion", 3_000_000_000),
        ("$ 900K", 900_000), ("12,000,000", 12_000_000), ("7", 7),
        ("no digits here", None),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("15%", 0.15), ("15 percent", 0.15), ("15 pct", 0.15), ("7.5%", 0.075),
     ("20%?", 0.20), ("no percent sign", None), ("100", None)],
)
def test_parse_percent(text, expected):
    assert parse_percent(text) == expected


# --- routing details ----------------------------------------------------

def test_case_and_whitespace_do_not_matter():
    result = parse("   WHAT IF I SAVE $5M MORE EACH MONTH?  ")
    assert result.intent == "what_if"
    assert result.what_if == WhatIfParams(monthly_savings_delta=5_000_000)


def test_a_decision_without_a_price_is_unparsed_not_a_guess():
    result = parse("should I buy a laptop?")

    assert result.unparsed is True
    assert result.purchase_price is None


def test_matched_rules_are_reported_for_debugging():
    assert "monthly_savings_delta" in parse("what if I save $5M more?").matched
    assert parse("asdkjhasd").matched == []


def test_the_llm_fallback_is_a_stub_that_parses_nothing():
    result = intent_module.llm_fallback("anything at all")

    assert isinstance(result, ParsedIntent)
    assert result.unparsed is True
    assert result.what_if is None


def test_the_parser_imports_no_llm_client():
    """Phase 3 rule: intent.py may not reach a model. Proven by its imports."""
    import inspect

    source = inspect.getsource(intent_module)
    for forbidden in ("local_llm", "remote_llm", "httpx", "requests", "openai", "ollama"):
        assert forbidden not in source, f"intent.py must not import {forbidden} in phase 3"


def test_education_topics_come_from_the_education_engine():
    from app.services.education_engine import TOPICS

    for key in TOPICS:
        result = parse(f"explain {key.replace('_', ' ')}")
        assert result.intent == "education"
        assert result.topic_key == key
