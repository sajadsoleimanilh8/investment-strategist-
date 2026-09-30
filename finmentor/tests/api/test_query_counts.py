"""Work that must not grow with the size of the data.

A response can be correct and still be wrong: `GET /api/goals/{user_id}`
returned exactly the right figures while issuing a query count that grew as
the square of the number of goals. `_to_out` built a Financial Twin per goal,
and `load_twin` lists the user's goals itself, so ten goals cost about forty
queries for one screen.

Nothing in the existing suite could see it. Every assertion was about the
body, and the body was right.

So this file counts. It asserts the *shape* of the cost — constant rather than
linear, linear rather than quadratic — and deliberately not an exact number,
which would fail on every unrelated refactor and teach people to update the
constant without reading it.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import event

PROFILE = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000},
    "current_savings": 45_000_000,
    "emergency_fund": 30_000_000,
}


@contextmanager
def counting(db):
    """Count SELECTs issued on this session's connection."""
    counter = {"n": 0}
    engine = db.get_bind()

    def before_cursor_execute(conn, cursor, statement, params, context, executemany):
        if statement.lstrip()[:6].upper() == "SELECT":
            counter["n"] += 1

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


@pytest.fixture
def user_id(client) -> int:
    user_id = client.post("/api/users", json={"telegram_id": 701_001}).json()["id"]
    client.put(f"/api/financial-profile/{user_id}", json=PROFILE)
    return user_id


def add_goals(client, user_id: int, how_many: int) -> None:
    for index in range(how_many):
        response = client.post("/api/goals", json={
            "user_id": user_id, "name": f"Goal {index}",
            "target_amount": 10_000_000 + index, "current_amount": 1_000_000,
            "priority": (index % 5) + 1,
        })
        assert response.status_code == 201, response.text


def queries_for(client, db, user_id: int, goals: int) -> int:
    add_goals(client, user_id, goals)
    with counting(db) as counter:
        assert client.get(f"/api/goals/{user_id}").status_code == 200
    return counter["n"]


def test_listing_goals_does_not_cost_more_per_goal(client, db, user_id):
    """The N+1, stated as the property rather than as a number.

    One goal and twelve goals must cost the same number of queries: the twin
    is built once for the list, so nothing in this route scales with the
    number of rows it returns.
    """
    one = queries_for(client, db, user_id, 1)
    twelve = queries_for(client, db, user_id, 11)   # 1 + 11 = 12

    assert twelve == one, (
        f"listing 12 goals cost {twelve} queries and listing 1 cost {one}; "
        "the per-goal work is back"
    )


def test_the_cost_of_listing_goals_is_small(client, db, user_id):
    """A guard on the absolute number, loose enough not to be brittle.

    The route needs the user, the profile, this month's expenses and the
    goals. A handful. The bound is there to catch a new query being added to
    a loop, not to pin the exact plan.
    """
    add_goals(client, user_id, 8)

    with counting(db) as counter:
        client.get(f"/api/goals/{user_id}")

    assert counter["n"] <= 8, f"{counter['n']} queries to list 8 goals"


def test_the_summary_does_not_cost_more_per_goal(client, db, user_id):
    """`/api/me/summary` already passed the saving rate down rather than
    refetching it. Asserted so it stays that way, since it is the one screen
    that renders goals, health and the watchlist together."""
    add_goals(client, user_id, 2)
    with counting(db) as counter:
        client.get("/api/me/summary")
    few = counter["n"]

    add_goals(client, user_id, 10)
    with counting(db) as counter:
        client.get("/api/me/summary")
    many = counter["n"]

    assert many == few, f"summary cost {few} queries for 2 goals and {many} for 12"


def test_the_figures_survive_the_optimisation(client, db, user_id):
    """Fewer queries must not mean different numbers.

    A cheaper route that returns a different ETA has not been optimised, it
    has been broken, and the count assertions above would not notice.
    """
    add_goals(client, user_id, 3)

    goals = client.get(f"/api/goals/{user_id}").json()

    assert len(goals) == 3
    for goal in goals:
        assert goal["progress_pct"] > 0
        # Every goal shares one saving rate, so every ETA is a real date.
        assert goal["estimated_completion"] is not None


def test_a_user_with_no_profile_still_lists_goals(client, db):
    """The saving rate is resolved once, so "no profile" is resolved once too.

    The old code discovered it per goal by catching an HTTPException inside
    the loop; this asserts the behaviour is unchanged now that it is decided
    before the loop.
    """
    user_id = client.post("/api/users", json={"telegram_id": 701_002}).json()["id"]
    add_goals(client, user_id, 2)

    goals = client.get(f"/api/goals/{user_id}").json()

    assert len(goals) == 2
    for goal in goals:
        assert goal["estimated_completion"] is None
        assert goal["progress_pct"] > 0
