"""`GET /api/me/expenses/history`.

The data was already there. `replace_expenses` has filed every save under a
`YYYY-MM` period since the product shipped and only ever rewrites that one
period, so a user who has been here six months has six months of records and
no way to see five of them. These are about the read path and, mostly, about
the two decisions in it: a month with no records is absent rather than zero,
and the window is bounded.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.finance import ExpenseRecord
from app.repositories import profiles as profiles_repo
from app.repositories.profiles import ESSENTIAL_CATEGORIES


def record(db, user_id, period, category="food", amount=100.0):
    db.add(ExpenseRecord(user_id=user_id, period=period, category=category,
                         amount=amount,
                         is_essential=category in ESSENTIAL_CATEGORIES))
    db.flush()


def periods_from(response) -> list[str]:
    return [row["period"] for row in response.json()["periods"]]


# --- the series ----------------------------------------------------------

def test_history_is_oldest_first(client, current_user, db):
    for period in ("2026-03", "2026-01", "2026-02"):
        record(db, current_user.id, period)

    response = client.get("/api/me/expenses/history?months=24")

    assert response.status_code == 200
    assert periods_from(response) == ["2026-01", "2026-02", "2026-03"]


def test_each_period_carries_its_own_breakdown(client, current_user, db):
    record(db, current_user.id, "2026-01", "housing", 900.0)
    record(db, current_user.id, "2026-01", "food", 300.0)
    record(db, current_user.id, "2026-02", "food", 250.0)

    rows = client.get("/api/me/expenses/history?months=24").json()["periods"]

    january = next(row for row in rows if row["period"] == "2026-01")
    february = next(row for row in rows if row["period"] == "2026-02")
    assert january["expenses"]["housing"] == 900.0
    assert january["expenses"]["food"] == 300.0
    assert january["total"] == 1200.0
    assert february["total"] == 250.0
    assert february["expenses"]["housing"] == 0.0, "a category with no row is zero"


def test_the_essential_total_is_the_runway_denominator(client, current_user, db):
    """Housing, food, transportation and bills; not entertainment."""
    record(db, current_user.id, "2026-01", "housing", 900.0)
    record(db, current_user.id, "2026-01", "food", 300.0)
    record(db, current_user.id, "2026-01", "entertainment", 150.0)

    row = client.get("/api/me/expenses/history?months=24").json()["periods"][0]

    assert row["total"] == 1350.0
    assert row["essential_total"] == 1200.0


# --- absence is not zero -------------------------------------------------

def test_a_month_with_no_records_is_absent_rather_than_zero(client, current_user, db):
    """Zeros would say the user spent nothing. We have no record, which is
    a different claim, and only one of the two is true."""
    record(db, current_user.id, "2026-01")
    record(db, current_user.id, "2026-03")

    assert periods_from(client.get("/api/me/expenses/history?months=24")) == [
        "2026-01", "2026-03",
    ]


def test_no_records_at_all_is_an_empty_list_not_an_error(client):
    response = client.get("/api/me/expenses/history")

    assert response.status_code == 200
    assert response.json() == {"months": 12, "periods": []}


def test_a_user_with_no_profile_gets_a_screen_not_a_404(client, current_user, db):
    """Matches `/summary`: not having started is not an error."""
    assert profiles_repo.get_by_user(db, current_user.id) is None

    assert client.get("/api/me/expenses/history").status_code == 200


def test_the_window_is_echoed_so_empty_can_be_told_apart(client, current_user, db):
    """"Nothing in the last 3 months" and "nothing ever" are different."""
    record(db, current_user.id, "2026-01")

    body = client.get("/api/me/expenses/history?months=3").json()

    assert body["months"] == 3


# --- the window ----------------------------------------------------------

def test_the_window_includes_the_current_month(client, current_user, db):
    record(db, current_user.id, profiles_repo.current_period())

    assert periods_from(client.get("/api/me/expenses/history?months=1")) == [
        profiles_repo.current_period(),
    ]


def test_the_window_excludes_what_falls_outside_it(db, current_user):
    """Driven through the repository so the period can be pinned to a date.

    A fixture that hardcodes a period against `date.today()` expires, which
    this project has already paid for once (lesson 5).
    """
    today = date(2026, 6, 15)
    for period in ("2026-02", "2026-04", "2026-05", "2026-06"):
        record(db, current_user.id, period)

    rows = profiles_repo.expense_history(db, current_user.id, months=3, today=today)

    assert [period for period, _, _ in rows] == ["2026-04", "2026-05", "2026-06"]


@pytest.mark.parametrize("months", [0, -1, 25, 1000])
def test_an_out_of_range_window_is_refused(client, months):
    """Bounded for the same reason every window here is: the body grows with
    it, and `?months=100000` was a valid request for the whole table."""
    assert client.get(f"/api/me/expenses/history?months={months}").status_code == 422


def test_a_non_numeric_window_is_refused(client):
    assert client.get("/api/me/expenses/history?months=all").status_code == 422


# --- isolation and cost --------------------------------------------------

def test_history_is_scoped_to_the_caller(client, current_user, db):
    from app.repositories import users as users_repo

    other = users_repo.create_web_user(db, email="other@example.com",
                                       password_hash="x")
    db.flush()
    record(db, other.id, "2026-01", "housing", 5000.0)
    record(db, current_user.id, "2026-01", "food", 10.0)

    rows = client.get("/api/me/expenses/history?months=24").json()["periods"]

    assert len(rows) == 1
    assert rows[0]["total"] == 10.0


def test_the_query_count_does_not_grow_with_the_history(db, current_user):
    """One statement, whatever the window holds.

    The obvious implementation is a query per month, which is fine at three
    and not at twenty-four. This project has a commit about work growing with
    the data; this is that shape of defect caught before it ships.
    """
    from sqlalchemy import event

    for month in range(1, 13):
        record(db, current_user.id, f"2026-{month:02d}", "food", float(month))

    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", count)
    try:
        rows = profiles_repo.expense_history(db, current_user.id, months=24,
                                             today=date(2026, 12, 31))
    finally:
        event.remove(db.bind, "before_cursor_execute", count)

    assert len(rows) == 12
    assert len(statements) == 1, f"{len(statements)} selects for 12 months"


# --- the month arithmetic ------------------------------------------------

@pytest.mark.parametrize("months, expected", [
    (1, "2026-03"),
    (2, "2026-02"),
    (3, "2026-01"),
    (4, "2025-12"),
    (12, "2025-04"),
    (24, "2024-04"),
])
def test_the_cutoff_crosses_a_year_boundary_correctly(months, expected):
    """`timedelta(days=30 * months)` lands on the wrong month a third of the
    year, which is why this is integer arithmetic on a month ordinal."""
    assert profiles_repo.period_months_ago(months, date(2026, 3, 15)) == expected


def test_a_window_of_one_is_this_month_not_last(client):
    """Off by one here would silently drop the month the user is living in."""
    assert profiles_repo.period_months_ago(1, date(2026, 3, 1)) == "2026-03"
