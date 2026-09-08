from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn
from app.services.financial_twin import build_twin


def test_twin_basic_maths():
    profile = FinancialProfileIn(
        monthly_income=30_000_000,
        expenses=ExpenseBreakdown(housing=10_000_000, food=5_000_000, bills=3_000_000),
        emergency_fund=36_000_000,
        monthly_debt_payment=0,
    )
    twin = build_twin(profile)
    assert twin.monthly_expenses == 18_000_000
    assert twin.essential_monthly_expenses == 18_000_000
    assert twin.monthly_savings == 12_000_000
    assert twin.savings_rate == round(12_000_000 / 30_000_000, 4)
    assert twin.emergency_months == 2.0
