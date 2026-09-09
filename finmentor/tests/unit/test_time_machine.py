"""The four named paths, their ordering, and their relationship to a plain projection."""
import pytest

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.services.financial_twin import build_twin
from app.services.simulation_engine import project
from app.services.time_machine import PRESETS, compare_paths

LAPTOP = GoalIn(name="Laptop", target_amount=60_000_000, current_amount=20_000_000, priority=1)


def demo_twin(goals=(LAPTOP,)):
    return build_twin(
        FinancialProfileIn(
            monthly_income=30_000_000,
            expenses=ExpenseBreakdown(
                housing=8_000_000, food=5_000_000, transportation=2_000_000,
                bills=1_500_000, entertainment=900_000, shopping=600_000,
            ),
            current_savings=45_000_000, debt=10_000_000,
            monthly_debt_payment=1_500_000, emergency_fund=30_000_000,
        ),
        list(goals),
    )


def test_all_four_presets_are_returned_in_a_stable_order():
    paths = compare_paths(demo_twin())

    assert [p.label for p in paths] == list(PRESETS)
    assert [p.label for p in paths] == [
        "current", "conservative", "improved_savings", "increased_expense"
    ]


def test_repeated_calls_are_identical():
    twin = demo_twin()
    assert compare_paths(twin) == compare_paths(twin)


def test_current_equals_a_plain_projection_of_the_untouched_twin():
    twin = demo_twin()
    current = next(p for p in compare_paths(twin, 36) if p.label == "current")

    assert current == project(twin, 36, label="current")


def test_conservative_is_worse_and_improved_savings_is_better():
    paths = {p.label: p for p in compare_paths(demo_twin(), 36)}
    baseline = paths["current"].monthly_savings

    assert paths["conservative"].monthly_savings < baseline
    assert paths["increased_expense"].monthly_savings < baseline
    assert paths["improved_savings"].monthly_savings > baseline


def test_improved_savings_reaches_the_goal_soonest():
    paths = {p.label: p for p in compare_paths(demo_twin(), 36)}
    dates = {label: p.estimated_goal_date for label, p in paths.items()}

    assert dates["improved_savings"] < dates["current"] < dates["conservative"]


def test_every_path_projects_from_the_same_starting_savings():
    paths = compare_paths(demo_twin(), 1)
    # after one month each path differs only by its own monthly saving
    for path in paths:
        assert path.projected_savings_end == pytest.approx(45_000_000 + path.monthly_savings)


def test_the_horizon_is_honoured():
    short = {p.label: p for p in compare_paths(demo_twin(), 1)}
    long = {p.label: p for p in compare_paths(demo_twin(), 24)}

    assert long["current"].projected_savings_end > short["current"].projected_savings_end


def test_all_paths_track_the_same_goal_so_percentages_compare():
    twin = demo_twin(goals=(LAPTOP, GoalIn(name="car", target_amount=1, priority=5)))
    paths = compare_paths(twin, 1)

    assert all(p.goal_completion_pct is not None for p in paths)
    # the priority-1 laptop drives all of them; the 1-unit car would read 100%
    assert all(p.goal_completion_pct < 100 for p in paths)


def test_a_twin_without_goals_still_produces_every_path():
    paths = compare_paths(demo_twin(goals=()), 12)

    assert len(paths) == 4
    assert all(p.goal_completion_pct is None for p in paths)
    assert all(p.estimated_goal_date is None for p in paths)


def test_compare_paths_does_not_mutate_the_twin():
    twin = demo_twin()
    before = twin.model_dump()
    compare_paths(twin)
    assert twin.model_dump() == before
