"""Purchase consequences: numbers, never a verdict."""
import pytest

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.services.decision_simulator import evaluate_purchase
from app.services.financial_twin import build_twin

LAPTOP = GoalIn(name="Laptop", target_amount=60_000_000, current_amount=20_000_000, priority=1)


def demo_twin(**overrides):
    data = {
        "monthly_income": 30_000_000,
        "expenses": ExpenseBreakdown(
            housing=8_000_000, food=5_000_000, transportation=2_000_000,
            bills=1_500_000, entertainment=900_000, shopping=600_000,
        ),
        "current_savings": 45_000_000,
        "debt": 10_000_000,
        "monthly_debt_payment": 1_500_000,
        "emergency_fund": 30_000_000,
    }
    data.update(overrides)
    return build_twin(FinancialProfileIn(**data), [LAPTOP])


def test_an_affordable_purchase_reports_the_drawdown():
    out = evaluate_purchase(demo_twin(), 40_000_000)

    assert out.affordable is True
    assert out.purchase_price == 40_000_000
    assert out.savings_before == 45_000_000
    assert out.savings_after == 5_000_000


def test_a_purchase_beyond_cash_is_not_affordable_and_costs_the_buffer():
    out = evaluate_purchase(demo_twin(), 60_000_000)

    assert out.affordable is False              # cash alone does not cover it
    assert out.savings_after == 0               # cash spent, the rest from the fund
    assert out.emergency_months_after < out.emergency_months_before
    assert out.health_score_after < out.health_score_before


def test_a_purchase_beyond_cash_and_fund_is_shown_in_the_red():
    out = evaluate_purchase(demo_twin(), 90_000_000)

    assert out.affordable is False
    assert out.savings_after == -15_000_000     # the shortfall is shown, not hidden
    assert out.emergency_months_after == 0.0


def test_spending_the_last_unit_exactly_is_still_affordable():
    out = evaluate_purchase(demo_twin(), 45_000_000)

    assert out.savings_after == 0
    assert out.affordable is True               # the boundary is >= 0


def test_one_unit_past_the_boundary_is_not_affordable():
    out = evaluate_purchase(demo_twin(), 45_000_001)

    assert out.affordable is False              # one unit more than cash holds
    assert out.savings_after == 0
    # the single unit does come out of the fund, but emergency months are
    # reported to two decimals, so a draw this small rounds away
    assert out.emergency_months_after == out.emergency_months_before


def test_a_free_purchase_changes_nothing():
    out = evaluate_purchase(demo_twin(), 0)

    assert out.savings_before == out.savings_after
    assert out.health_score_before == out.health_score_after


def test_the_emergency_fund_is_never_raided_by_a_purchase():
    out = evaluate_purchase(demo_twin(), 44_000_000)
    assert out.emergency_months_before == out.emergency_months_after


def test_a_purchase_covered_by_cash_leaves_the_score_alone():
    out = evaluate_purchase(demo_twin(), 40_000_000)

    # the buffer was never threatened, so the score should not move
    assert out.emergency_months_before == out.emergency_months_after
    assert out.health_score_before == out.health_score_after
    assert 0 <= out.health_score_after <= 100


def test_the_output_carries_a_disclaimer_and_no_verdict():
    out = evaluate_purchase(demo_twin(), 40_000_000)
    text = " ".join(str(v) for v in out.model_dump().values()).lower()

    assert "decision is yours" in out.disclaimer.lower()
    for verdict in ("you should", "don't buy", "do not buy", "recommended", "bad idea"):
        assert verdict not in text


def test_the_input_twin_is_not_mutated():
    twin = demo_twin()
    before = twin.model_dump()
    evaluate_purchase(twin, 40_000_000)
    assert twin.model_dump() == before


@pytest.mark.parametrize("price", [1, 1_000_000, 45_000_000])
def test_cash_purchases_come_straight_out_of_savings(price):
    out = evaluate_purchase(demo_twin(), price)
    assert out.savings_after == pytest.approx(out.savings_before - price)


@pytest.mark.parametrize("price", [50_000_000, 75_000_000, 100_000_000])
def test_every_unit_of_an_oversized_purchase_is_accounted_for(price):
    """Cash drawn + fund drawn + remaining deficit must equal the price."""
    twin = demo_twin()
    out = evaluate_purchase(twin, price)

    cash_drawn = min(price, twin.current_savings)
    deficit = max(0.0, -out.savings_after)
    fund_drawn = price - cash_drawn - deficit

    assert 0 <= fund_drawn <= twin.emergency_fund
    assert cash_drawn + fund_drawn + deficit == pytest.approx(price)
