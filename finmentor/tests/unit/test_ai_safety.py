"""The safety layer (spec section 16): scrub advice, reject invented numbers,
disclaim exactly once.

This is the last thing between a 3B model and a user, so the cases here are the
ones that would actually cause harm: a trade instruction, and a number the
engine never produced.
"""
import pytest

from app.ai.safety import (
    FINANCE_DISCLAIMER, add_disclaimer, enforce, is_grounded, numbers_in_context,
    numbers_in_text, scrub_directives, ungrounded_numbers,
)
from app.schemas.market import MARKET_DISCLAIMER

CONTEXT = {
    "financial_health_score": 62.3,
    "savings_rate": 0.35,
    "monthly_savings": 10_500_000.0,
    "emergency_months": 1.82,
    "components": [
        {"name": "debt_load", "points": 17.5, "detail": "debt payments are 5.0% of income"},
    ],
}


# --- buy/sell scrubbing -------------------------------------------------

@pytest.mark.parametrize(
    "directive",
    [
        "It is not advisable to buy the laptop.",
        "It would be a good idea to buy now.",
        "I would not recommend that.",
        "Do not buy it.",
        "You shouldn't buy that.",
        "You should buy Bitcoin.",
        "You should sell your position.",
        "You should invest in tech stocks.",
        "I recommend buying gold now.",
        "Put all your money into crypto.",
        "Now is the time to buy.",
        "This is a guaranteed return.",
        "It is a risk-free profit.",
        "Buy now before it goes up.",
    ],
)
def test_trade_instructions_are_removed(directive):
    text = f"Your savings rate is 35%. {directive} Keep tracking it."
    clean, report = enforce(text, context=CONTEXT)

    assert report["buy_sell_scrubbed"] is True
    assert directive.rstrip(".").lower() not in clean.lower()
    assert "Your savings rate is 35%." in clean          # the rest survives
    assert "Keep tracking it." in clean


def test_educational_text_about_buying_survives():
    text = (
        "Buying only one asset is risky, which is why diversification matters. "
        "Many beginners sell in a panic when prices fall."
    )
    clean, report = enforce(text, context=CONTEXT)

    assert report["buy_sell_scrubbed"] is False
    assert "diversification matters" in clean
    assert "sell in a panic" in clean


def test_a_message_that_is_only_advice_becomes_a_refusal():
    clean, report = enforce("You should buy Bitcoin now.", context=CONTEXT)

    assert report["buy_sell_scrubbed"] is True
    assert "do not give buy or sell advice" in clean


def test_scrubbing_reports_whether_it_changed_anything():
    assert scrub_directives("Your score is fine.") == ("Your score is fine.", False)
    cleaned, changed = scrub_directives("Nice. You should sell everything.")
    assert changed is True
    assert cleaned == "Nice."


# --- number grounding ---------------------------------------------------

def test_numbers_that_all_trace_to_the_context_pass_through():
    text = (
        "Your score is 62.3 out of 100. You save 35% of your income, about "
        "$10.5M a month, and hold 1.8 months of expenses. Debt load scores 17.5."
    )
    clean, report = enforce(text, context=CONTEXT)

    assert report["ungrounded_numbers"] == []
    assert report["downgraded"] is False
    assert "62.3" in clean


def test_an_invented_number_downgrades_to_the_verified_figures():
    text = "Your score is 62.3 and will reach 88.4 next quarter."
    clean, report = enforce(text, context=CONTEXT)

    assert report["downgraded"] is True
    assert 88.4 in report["ungrounded_numbers"]
    assert "88.4" not in clean                       # the invention never ships
    assert "62.3" in clean                           # the real figure does
    assert "straight from the calculation" in clean


def test_a_hallucinated_amount_never_reaches_the_user():
    text = "You have $99,000,000 saved."
    clean, report = enforce(text, context=CONTEXT)

    assert report["downgraded"] is True
    assert "99,000,000" not in clean


def test_rounding_a_context_number_is_not_an_invention():
    # 1.82 months written as 1.8; 0.35 written as 35%
    clean, report = enforce(
        "You hold 1.8 months of expenses and save 35% of income.", context=CONTEXT
    )
    assert report["downgraded"] is False
    assert "1.8 months" in clean


def test_a_year_needs_no_grounding():
    clean, report = enforce("You stay on track through 2027.", context=CONTEXT)
    assert report["downgraded"] is False


def test_a_small_integer_is_not_waved_through():
    """The hole a live 3B found: claiming a component was "worth 0 points"
    when the context said 12. Counts the model may legitimately quote are in
    the context already, so nothing is exempt just for being small."""
    _, report = enforce("Budget stability is worth 0 points.", context=CONTEXT)

    assert report["downgraded"] is True
    assert 0.0 in report["ungrounded_numbers"]


def test_a_count_that_is_in_the_context_still_passes():
    context = {"active_goals": 2, "detail": "1 active goal(s), priority-weighted"}
    _, report = enforce("You have 2 goals and 1 is a priority.", context=context)

    assert report["downgraded"] is False


def test_magnitude_suffixes_are_read_not_confused_with_words():
    """"1.8 months" is not 1.8 million, and "62.3 but" is not 62.3 billion."""
    assert numbers_in_text("1.8 months") == [1.8]
    assert numbers_in_text("62.3 but soon") == [62.3]
    assert numbers_in_text("$10.5M") == [10_500_000.0]
    assert numbers_in_text("750k") == [750_000.0]


def test_percentages_are_read_both_ways():
    assert numbers_in_text("35%") == [35.0, 0.35]


def test_context_numbers_are_mined_from_nested_values_and_strings():
    found = numbers_in_context(CONTEXT)

    assert 62.3 in found
    assert 10_500_000.0 in found
    assert 17.5 in found
    assert 5.0 in found              # from the component detail string


def test_grounding_tolerates_one_percent():
    assert is_grounded(100.5, [100.0])
    assert not is_grounded(105.0, [100.0])


def test_ungrounded_numbers_lists_only_the_offenders():
    assert ungrounded_numbers("62.3 and 88.4", CONTEXT) == [88.4]


# --- disclaimer ---------------------------------------------------------

def test_the_finance_disclaimer_is_added_once():
    clean, report = enforce("Your score is 62.3.", context=CONTEXT)

    assert report["disclaimer_added"] is True
    assert clean.count(FINANCE_DISCLAIMER) == 1


def test_an_existing_disclaimer_is_not_doubled():
    already = f"Your score is 62.3.\n\n⚠️ {FINANCE_DISCLAIMER}"
    clean, report = enforce(already, context=CONTEXT)

    assert report["disclaimer_added"] is False
    assert clean.count(FINANCE_DISCLAIMER) == 1


def test_market_context_gets_the_market_disclaimer():
    clean, _ = enforce("BTC rose 4.37%.", context={"change_7d_pct": 4.37},
                       market_context=True)

    assert MARKET_DISCLAIMER in clean
    assert FINANCE_DISCLAIMER not in clean


def test_non_market_context_gets_the_finance_disclaimer():
    clean, _ = enforce("Your score is 62.3.", context=CONTEXT)

    assert FINANCE_DISCLAIMER in clean
    assert MARKET_DISCLAIMER not in clean


def test_add_disclaimer_is_idempotent():
    once, added_first = add_disclaimer("Your score is 62.3.", market_context=False)
    twice, added_again = add_disclaimer(once, market_context=False)

    assert added_first is True
    assert added_again is False
    assert once == twice


def test_a_reply_with_no_financial_claim_gets_no_disclaimer():
    """A greeting or 'you're welcome!' has nothing to disclaim. Stamping the
    same boilerplate onto every message in a conversation is what made the
    guide read as a form letter — see docs/ROADMAP.md, 2026-09-12."""
    text, added = add_disclaimer("Hey! Good to see you again.", market_context=False)

    assert added is False
    assert text == "Hey! Good to see you again."
    assert FINANCE_DISCLAIMER not in text


def test_market_context_always_gets_the_disclaimer_even_with_no_numbers():
    """The market disclaimer is about the topic, not any one figure — unlike
    the finance disclaimer, it doesn't wait for a number to appear."""
    text, added = add_disclaimer("Markets can be unpredictable.", market_context=True)

    assert added is True
    assert MARKET_DISCLAIMER in text


# --- the report ---------------------------------------------------------

def test_the_report_always_has_the_same_shape():
    _, report = enforce("Your score is 62.3.", context=CONTEXT)

    assert set(report) == {
        "buy_sell_scrubbed", "ungrounded_numbers", "disclaimer_added", "downgraded",
    }


def test_empty_model_output_still_returns_a_disclaimer():
    clean, report = enforce("", context=CONTEXT)

    assert FINANCE_DISCLAIMER in clean
    assert report["downgraded"] is False


def test_scrubbing_and_downgrading_can_both_happen():
    text = "You should buy now. Your balance is $77,000,000."
    clean, report = enforce(text, context=CONTEXT)

    assert report["buy_sell_scrubbed"] is True
    assert report["downgraded"] is True
    assert "77,000,000" not in clean


# --- the before/after block ---------------------------------------------

def test_before_after_pairs_reads_a_two_scenario_context():
    from app.ai.rendering import before_after_pairs

    pairs = before_after_pairs({
        "current": {"monthly_savings": 10.0, "emergency_months": 1.8},
        "scenario": {"monthly_savings": 15.0, "emergency_months": 1.8},
        "deltas": {"monthly_savings": 5.0},
    })

    assert ("monthly_savings", 10.0, 15.0) in pairs
    assert not [p for p in pairs if p[0] == "deltas"], "nested values are not a side"


def test_before_after_pairs_reads_suffixed_fields():
    from app.ai.rendering import before_after_pairs

    pairs = before_after_pairs({
        "purchase_price": 60.0, "savings_before": 45.0, "savings_after": 0.0,
    })

    assert pairs == [("savings", 45.0, 0.0)]
    assert not [p for p in pairs if p[0] == "purchase_price"]


def test_a_one_sided_context_renders_no_block():
    from app.ai.rendering import render_sides

    assert render_sides({"financial_health_score": 62.3}) == ""
    assert render_sides({}) == ""


def test_the_block_puts_each_figure_next_to_its_label():
    from app.ai.rendering import render_sides

    block = render_sides({"savings_before": 45_000_000.0, "savings_after": 0.0})

    assert "BEFORE savings: $45,000,000" in block
    assert "AFTER savings: $0" in block


# --- negative figures ----------------------------------------------------

def test_a_negative_context_figure_is_grounded_when_quoted():
    """`numbers_in_text` reads no sign, so "$-36,000,000" comes back as
    36,000,000. Grounding is about the magnitude: a purchase that overdraws
    someone used to flag its own deterministic rendering as invented."""
    context = {"savings_after": -36_000_000.0}

    assert ungrounded_numbers("You would be $-36,000,000 short.", context) == []
    assert ungrounded_numbers("You would be $36,000,000 short.", context) == []


def test_the_rendered_context_never_trips_the_grounding_check():
    from app.ai.rendering import render_context

    context = {
        "purchase_price": 40_000_000.0, "savings_before": 3_000_000.0,
        "savings_after": -36_000_000.0, "emergency_months_after": 0.0,
        "health_score_before": 12.9, "health_score_after": 12.7,
    }

    assert ungrounded_numbers(render_context(context), context) == []


def test_a_magnitude_that_is_in_no_context_field_is_still_caught():
    assert ungrounded_numbers("You have $99,000,000.", {"savings_after": -36_000_000.0})


def test_a_context_percentage_is_grounded_when_written_with_a_sign():
    """`numbers_in_text` reads "5%" as both 5 and 0.05. A context that already
    stores a percentage has to ground the fraction, or quoting its own figure
    back reads as invented."""
    assert ungrounded_numbers("Your goal is at 5%.", {"progress_pct": 5.0}) == []
    assert ungrounded_numbers("You save 35% of income.", {"savings_rate": 0.35}) == []


def test_a_percentage_in_no_context_field_is_still_caught():
    assert ungrounded_numbers("Your goal is at 88%.", {"progress_pct": 5.0})


def test_rounding_may_not_manufacture_a_zero():
    """`round(0.0182, 0)` is 0.0. Without a guard, "worth 0 points" is grounded
    by any small number in the context — the hole the ordinal exemption was
    removed to close, reopened through the rounding rule."""
    assert ungrounded_numbers("It is worth 0 points.", {"emergency_months": 1.82})
    assert ungrounded_numbers("You have 0 saved.", {"savings_rate": 0.35})


def test_a_real_zero_in_the_context_still_grounds_a_zero():
    assert ungrounded_numbers("Your debt is $0.", {"debt": 0.0}) == []
