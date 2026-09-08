import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from finance.budget_planner import plan_budget, plan_budget_for_goal


def test_plan_budget_splits_default_ratio():
    plan = plan_budget(1000)
    assert plan.needs == 500
    assert plan.wants == 300
    assert plan.savings == 200


def test_plan_budget_rejects_non_positive_income():
    with pytest.raises(ValueError):
        plan_budget(0)
    with pytest.raises(ValueError):
        plan_budget(-100)


def test_plan_budget_custom_split():
    plan = plan_budget(1000, custom_split={"needs": 0.6, "wants": 0.2, "savings": 0.2})
    assert plan.needs == 600
    assert plan.wants == 200
    assert plan.savings == 200


def test_plan_budget_annual_savings():
    plan = plan_budget(1000)
    assert plan.monthly_savings_in_a_year == plan.savings * 12


def test_plan_budget_for_goal_estimates_months():
    result = plan_budget_for_goal(1000, goal_amount=2000)
    assert result["estimated_months"] == 10  # 2000 / 200 savings per month
