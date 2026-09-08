import pytest

from app.services.budget_engine import DEFAULT_SPLIT, months_to_goal, plan_budget


def test_default_split():
    p = plan_budget(1000)
    assert (p.needs, p.wants, p.savings) == (500, 300, 200)


def test_rejects_non_positive():
    with pytest.raises(ValueError):
        plan_budget(0)


def test_custom_split_must_sum_to_one():
    with pytest.raises(ValueError):
        plan_budget(1000, {"needs": 0.6, "wants": 0.2, "savings": 0.1})


def test_annual_savings():
    assert plan_budget(1000).annual_savings == 200 * 12


def test_months_to_goal():
    assert months_to_goal(200, 2000) == 10.0
    assert months_to_goal(0, 2000) is None
    assert months_to_goal(200, 2000, current=1000) == 5.0


def test_default_split_constant_unchanged():
    assert DEFAULT_SPLIT == {"needs": 0.5, "wants": 0.3, "savings": 0.2}
