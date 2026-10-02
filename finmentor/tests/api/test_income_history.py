"""Recording income per period, and reading it back.

`income_records` was declared in the initial schema, with a docstring calling
it "the signal behind `income_type = variable`", and nothing ever wrote a row
to it. These cover the write that was missing, the read, and the one thing
this feature must not do: change what the user told us.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.finance import IncomeRecord
from app.repositories import profiles as profiles_repo
from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn

BLANK = ExpenseBreakdown()


def profile_payload(income: float, income_type: str = "fixed") -> FinancialProfileIn:
    return FinancialProfileIn(
        monthly_income=income, income_type=income_type, current_savings=0.0,
        debt=0.0, monthly_debt_payment=0.0, emergency_fund=0.0, expenses=BLANK,
    )


def save(client, income: float, income_type: str = "fixed", period: str | None = None):
    payload = profile_payload(income, income_type).model_dump()
    url = "/api/financial-profile/1"
    if period:
        url += f"?period={period}"
    return client.put(url, json=payload)


# --- the write that never existed ----------------------------------------

def test_saving_a_profile_records_the_income_for_the_period(client, current_user, db):
    save(client, 3000.0, period="2026-01")

    rows = db.query(IncomeRecord).filter_by(user_id=current_user.id).all()
    assert [(r.period, r.amount) for r in rows] == [("2026-01", 3000.0)]


def test_re_saving_corrects_the_period_rather_than_appending(client, current_user, db):
    """The invariant the whole measure rests on.

    A row per save would make the variation a function of how often somebody
    edited their profile, which is not a property of their income.
    """
    save(client, 3000.0, period="2026-01")
    save(client, 3200.0, period="2026-01")
    save(client, 3100.0, period="2026-01")

    rows = db.query(IncomeRecord).filter_by(user_id=current_user.id).all()
    assert len(rows) == 1
    assert rows[0].amount == 3100.0, "the newest figure wins"


def test_each_period_gets_its_own_row(client, current_user, db):
    save(client, 3000.0, period="2026-01")
    save(client, 2500.0, period="2026-02")

    rows = db.query(IncomeRecord).filter_by(user_id=current_user.id).all()
    assert sorted((r.period, r.amount) for r in rows) == [
        ("2026-01", 3000.0), ("2026-02", 2500.0),
    ]


def test_a_history_accumulates_without_anyone_maintaining_it(client, current_user, db):
    """Exactly how six months of expenses came to exist before anything read
    them: one row per period, rewritten on save, never appended to."""
    for month, amount in enumerate([3000.0, 3100.0, 2900.0, 3050.0], start=1):
        save(client, amount, period=f"2026-{month:02d}")

    rows = profiles_repo.income_history(db, current_user.id, months=24,
                                        today=date(2026, 4, 30))
    assert rows == [("2026-01", 3000.0), ("2026-02", 3100.0),
                    ("2026-03", 2900.0), ("2026-04", 3050.0)]


# --- the read ------------------------------------------------------------

def test_history_is_oldest_first(client, current_user, db):
    for period in ("2026-03", "2026-01", "2026-02"):
        save(client, 3000.0, period=period)

    body = client.get("/api/me/income/history?months=24").json()

    assert [row["period"] for row in body["periods"]] == [
        "2026-01", "2026-02", "2026-03",
    ]


def test_a_month_with_no_record_is_absent_rather_than_zero(client, current_user, db):
    """Zero income is a claim. No record is not."""
    save(client, 3000.0, period="2026-01")
    save(client, 3000.0, period="2026-03")

    body = client.get("/api/me/income/history?months=24").json()

    assert [row["period"] for row in body["periods"]] == ["2026-01", "2026-03"]


def test_nothing_recorded_is_an_empty_list(client):
    body = client.get("/api/me/income/history").json()

    assert body["periods"] == []
    assert body["months"] == 12


def test_no_profile_means_no_signal_rather_than_a_404(client):
    """There is nothing to compare a signal against without a profile."""
    response = client.get("/api/me/income/history")

    assert response.status_code == 200
    assert response.json()["signal"] is None


@pytest.mark.parametrize("months", [0, -1, 25])
def test_the_window_is_bounded(client, months):
    assert client.get(f"/api/me/income/history?months={months}").status_code == 422


def test_history_is_scoped_to_the_caller(client, current_user, db):
    from app.repositories import users as users_repo

    other = users_repo.create_web_user(db, email="other-income@example.com",
                                       password_hash="x")
    db.flush()
    db.add(IncomeRecord(user_id=other.id, period="2026-01", amount=99_000.0))
    db.flush()
    save(client, 3000.0, period="2026-01")

    body = client.get("/api/me/income/history?months=24").json()

    assert [row["amount"] for row in body["periods"]] == [3000.0]


def test_the_query_count_does_not_grow_with_the_history(client, current_user, db):
    from sqlalchemy import event

    for month in range(1, 13):
        save(client, 3000.0 + month, period=f"2026-{month:02d}")

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        rows = profiles_repo.income_history(db, current_user.id, months=24,
                                            today=date(2026, 12, 31))
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(rows) == 12
    assert len(statements) == 1


# --- the observation, not the correction ---------------------------------

def test_the_signal_reports_the_declared_value_untouched(client, current_user, db):
    save(client, 3000.0, income_type="fixed", period="2026-01")
    save(client, 1000.0, income_type="fixed", period="2026-02")
    save(client, 5000.0, income_type="fixed", period="2026-03")

    signal = client.get("/api/me/income/history?months=24").json()["signal"]

    assert signal["declared"] == "fixed", "what the user said"
    assert signal["suggested"] == "variable", "what the records say"
    assert signal["disagrees"] is True


def test_reading_the_history_never_rewrites_the_profile(client, current_user, db):
    """The decision this feature turns on.

    Nothing reads `income_type` today, so deriving it would be a write with no
    effect. The moment something does read it, a silent derivation would move
    every existing user's figures without them asking for it.
    """
    save(client, 3000.0, income_type="fixed", period="2026-01")
    save(client, 1000.0, income_type="fixed", period="2026-02")
    save(client, 5000.0, income_type="fixed", period="2026-03")

    client.get("/api/me/income/history?months=24")
    db.expire_all()

    assert profiles_repo.get_by_user(db, current_user.id).income_type == "fixed"


def test_agreement_is_not_reported_as_disagreement(client, current_user, db):
    save(client, 3000.0, income_type="fixed", period="2026-01")
    save(client, 3000.0, income_type="fixed", period="2026-02")
    save(client, 3000.0, income_type="fixed", period="2026-03")

    signal = client.get("/api/me/income/history?months=24").json()["signal"]

    assert signal["suggested"] == "fixed"
    assert signal["disagrees"] is False


def test_too_few_periods_says_so_rather_than_guessing(client, current_user, db):
    save(client, 3000.0, period="2026-01")
    save(client, 1000.0, period="2026-02")

    signal = client.get("/api/me/income/history?months=24").json()["signal"]

    assert signal["periods"] == 2
    assert signal["insufficient"] is True
    assert signal["suggested"] is None
    assert signal["disagrees"] is False


def test_the_signal_carries_the_range_it_was_computed_from(client, current_user, db):
    save(client, 2000.0, period="2026-01")
    save(client, 4000.0, period="2026-02")
    save(client, 3000.0, period="2026-03")

    signal = client.get("/api/me/income/history?months=24").json()["signal"]

    assert signal["low"] == 2000.0
    assert signal["high"] == 4000.0
    assert signal["mean"] == 3000.0
    assert signal["variation"] == pytest.approx(0.2721655, rel=1e-4)


def test_the_signal_only_sees_the_window(client, current_user, db):
    """A figure described as "your income" must come from the months shown."""
    save(client, 3000.0, period="2026-01")
    save(client, 3000.0, period="2026-02")
    save(client, 3000.0, period="2026-03")

    narrow = client.get("/api/me/income/history?months=1").json()

    assert narrow["signal"]["periods"] == len(narrow["periods"])
