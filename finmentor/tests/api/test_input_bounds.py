"""Values that must never reach the engine, the model, or a column.

Three separate defects, one shape: a field with a floor and no ceiling, or no
validation at all, and a caller who supplies something the arithmetic below
cannot survive.

* `horizon_months` was an unbounded `int`. Python ints are arbitrary
  precision, so `monthly_savings * months` raised `OverflowError` and the
  route answered 500.
* Money fields carried `ge=0` and nothing else. `inf >= 0` is true, so
  `Infinity` validated, reached `derive_figures`, produced NaN, and was
  written to a float column — after which every read of that account came
  back `null` in fields the web client's types declare as numbers.
* `question` had no length at all, so one request could buy unbounded
  generation cost and permanent transcript growth.

Each test here fails against the code as it was.
"""
import math

import pytest

from app.db.guards import NonFiniteValueError
from app.models.finance import FinancialProfile
from app.models.goal import FinancialGoal
from app.schemas.ai import MAX_QUESTION_LENGTH
from app.schemas.simulation import MAX_HORIZON_MONTHS

PROFILE_BODY = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000},
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
}


@pytest.fixture
def user_id(client) -> int:
    user_id = client.post("/api/users", json={"telegram_id": 700_555}).json()["id"]
    client.put(f"/api/financial-profile/{user_id}", json=PROFILE_BODY)
    return user_id


# --- M1: the simulation horizon -----------------------------------------

@pytest.mark.parametrize("kind", ["what_if", "time_machine"])
def test_an_enormous_horizon_is_rejected_not_a_500(client, user_id, kind):
    """`10 ** 400` used to reach the engine and raise OverflowError."""
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": kind, "params": {"horizon_months": 10 ** 400},
    })

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("horizon", [0, -1, MAX_HORIZON_MONTHS + 1])
def test_a_horizon_outside_the_bounds_is_rejected(client, user_id, horizon):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if", "params": {"horizon_months": horizon},
    })

    assert response.status_code == 422, response.text


def test_the_largest_allowed_horizon_still_projects(client, user_id):
    """A ceiling that refuses the documented maximum is a different bug."""
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"horizon_months": MAX_HORIZON_MONTHS},
    })

    assert response.status_code == 201, response.text
    assert math.isfinite(response.json()["scenario"]["projected_savings_end"])


# --- M2: non-finite and oversized money ---------------------------------

NON_FINITE = ["Infinity", "-Infinity", "NaN"]


@pytest.mark.parametrize("literal", NON_FINITE)
def test_a_non_finite_income_is_rejected(client, user_id, literal):
    """`json.loads` accepts these literals; the schema must not."""
    response = client.put(
        f"/api/financial-profile/{user_id}",
        headers={"Content-Type": "application/json"},
        content=f'{{"monthly_income": {literal}, "expenses": {{"housing": 100}}}}',
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("literal", NON_FINITE)
def test_a_non_finite_expense_is_rejected(client, user_id, literal):
    response = client.put(
        f"/api/financial-profile/{user_id}",
        headers={"Content-Type": "application/json"},
        content=f'{{"monthly_income": 100, "expenses": {{"housing": {literal}}}}}',
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("field", [
    "monthly_income", "current_savings", "debt", "monthly_debt_payment", "emergency_fund",
])
def test_an_absurd_money_value_is_rejected(client, user_id, field):
    response = client.put(f"/api/financial-profile/{user_id}",
                          json={**PROFILE_BODY, field: 1e300})

    assert response.status_code == 422, response.text


def test_a_rejected_profile_is_not_persisted(client, user_id, db):
    """422 has to mean the row is untouched, not that the write was reported."""
    before = db.query(FinancialProfile).filter_by(user_id=user_id).one()
    original = before.monthly_income

    client.put(
        f"/api/financial-profile/{user_id}",
        headers={"Content-Type": "application/json"},
        content='{"monthly_income": Infinity, "expenses": {"housing": 100}}',
    )

    db.expire_all()
    after = db.query(FinancialProfile).filter_by(user_id=user_id).one()
    assert after.monthly_income == original
    assert math.isfinite(after.monthly_income)


@pytest.mark.parametrize("literal", NON_FINITE)
def test_a_non_finite_scenario_lever_is_rejected(client, user_id, literal):
    """`income_pct_delta: 1e308` used to answer 201 with nulls in the body.

    Sent as raw content, not through `json=`: Python's own encoder refuses to
    write these literals, which is a neat illustration of the asymmetry that
    caused the bug. `json.dumps` will not produce them; `json.loads` accepts
    them happily, and that is the direction requests travel.
    """
    response = client.post(
        "/api/simulations",
        headers={"Content-Type": "application/json"},
        content=f'{{"user_id": {user_id}, "kind": "what_if", '
                f'"params": {{"income_pct_delta": {literal}}}}}',
    )

    assert response.status_code == 422, response.text


def test_a_simulation_response_never_contains_a_null_figure(client, user_id):
    """The web client's types declare these as numbers. They have to be."""
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"income_pct_delta": 100, "horizon_months": MAX_HORIZON_MONTHS},
    })

    assert response.status_code == 201, response.text
    for side in ("current", "scenario"):
        figures = response.json()[side]
        assert figures["monthly_savings"] is not None
        assert figures["projected_savings_end"] is not None
        assert math.isfinite(figures["projected_savings_end"])


def test_a_non_finite_goal_amount_is_rejected(client, user_id):
    response = client.post(
        "/api/goals",
        headers={"Content-Type": "application/json"},
        content=f'{{"user_id": {user_id}, "name": "x", "target_amount": Infinity}}',
    )

    assert response.status_code == 422, response.text


# --- M2: the write-time guard, for the paths that skip Pydantic ---------
#
# The bot and the seed scripts call the repositories directly, so a schema is
# not in the way. The guard is on the session flush instead.

def test_the_session_refuses_a_non_finite_float(db, current_user):
    """No schema involved: this is what the bot and the scripts would do."""
    db.add(FinancialProfile(user_id=current_user.id, monthly_income=float("inf")))

    with pytest.raises(NonFiniteValueError, match="monthly_income"):
        db.flush()


def test_the_session_refuses_a_nan_on_an_update(db, current_user):
    """A dirty object counts too, not only a new one."""
    goal = FinancialGoal(user_id=current_user.id, name="Laptop",
                         target_amount=1_000.0, current_amount=0.0)
    db.add(goal)
    db.commit()

    goal.current_amount = float("nan")
    with pytest.raises(NonFiniteValueError, match="current_amount"):
        db.flush()


def test_the_session_accepts_ordinary_figures(db, current_user):
    """The guard must not cost anything a real write depends on."""
    db.add(FinancialGoal(user_id=current_user.id, name="Laptop",
                         target_amount=60_000_000.0, current_amount=20_000_000.0))
    db.flush()

    assert db.query(FinancialGoal).count() == 1


# --- M4: the question ---------------------------------------------------

@pytest.fixture
def model_must_not_run(monkeypatch):
    """Booby-trap the synthesizer.

    Asserting the status code alone would pass even if the model had already
    been called and the transcript already written, which is the cost the cap
    exists to avoid. This makes "rejected" mean "rejected before the expensive
    part", which is the actual requirement.
    """
    from app.ai import synthesizer

    def explode(*args, **kwargs):                       # pragma: no cover - must not run
        raise AssertionError("the model was called for a question that should "
                             "have been rejected")

    monkeypatch.setattr(synthesizer, "explain", explode)
    monkeypatch.setattr(synthesizer, "chat", explode)


def test_a_half_megabyte_question_never_reaches_the_model(
    client, user_id, model_must_not_run
):
    """Two layers catch this, and the outer one catches it first.

    413 rather than 422 because the body limit refuses the request before
    anything parses it — which is the point of having a body limit as well as
    a field cap. The field cap is asserted separately below, at a size that
    fits through the door.
    """
    response = client.post("/api/ai/ask", json={
        "user_id": user_id, "question": "x" * 500_000,
    })

    assert response.status_code == 413, response.text


def test_a_question_over_the_field_cap_never_reaches_the_model(
    client, user_id, model_must_not_run
):
    """Small enough to pass the body limit, too long for the field."""
    response = client.post("/api/ai/ask", json={
        "user_id": user_id, "question": "x" * (MAX_QUESTION_LENGTH + 1),
    })

    assert response.status_code == 422, response.text


def test_an_empty_question_is_rejected(client, user_id):
    response = client.post("/api/ai/ask", json={"user_id": user_id, "question": ""})

    assert response.status_code == 422


def test_a_question_at_the_limit_is_answered(client, user_id):
    """The cap has to sit above anything a person would actually type."""
    response = client.post("/api/ai/ask", json={
        "user_id": user_id, "question": "why is my score what it is? " .ljust(
            MAX_QUESTION_LENGTH, "."),
    })

    assert response.status_code == 200, response.text


# --- the parser must survive a number it cannot use ----------------------

@pytest.mark.parametrize("question", [
    "what if my income went up 999999 percent?",
    "what if I save 900000 billion more each month?",
    "what if my spending dropped 500000 percent?",
])
def test_an_unusable_number_in_a_question_is_not_a_500(client, user_id, question):
    """`WhatIfParams` now rejects levers it used to accept.

    That validation runs inside `intent.parse`, so an out-of-range number in
    a *question* would have escaped as a 500 rather than a 422 — the request
    body was perfectly valid. The parser reports "no scenario here" instead
    and the message goes to the conversational path.
    """
    response = client.post("/api/ai/ask", json={
        "user_id": user_id, "question": question,
    })

    assert response.status_code == 200, response.text
    assert response.json()["text"]


# --- the ceiling on the whole request ------------------------------------

def test_an_oversized_body_is_refused_before_it_is_parsed(client, user_id):
    """A field cap only applies after the body has been read and parsed.

    413 rather than 422: nothing was wrong with the *content*, there was just
    too much of it, and the client cannot fix a field it was never told about.
    """
    from app.main import MAX_BODY_BYTES

    response = client.post(
        "/api/ai/ask",
        headers={"Content-Type": "application/json"},
        content=b'{"user_id": 1, "question": "' + b"x" * (MAX_BODY_BYTES + 1) + b'"}',
    )

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "payload_too_large"


def test_an_ordinary_body_is_unaffected(client, user_id):
    response = client.put(f"/api/financial-profile/{user_id}", json=PROFILE_BODY)

    assert response.status_code == 200


def test_the_guard_is_attached_to_every_session_not_to_one_factory():
    """The guard has to survive factories being created and collected.

    It used to register on the `sessionmaker`. SQLAlchemy keys its event
    registry on `id()` of the target, and a factory that goes out of scope
    frees its address, so the next one allocated there answered True to
    `event.contains`, the registration was skipped as a duplicate, and the
    guard was silently gone.

    Production never noticed, because `SessionLocal` is module-level and never
    collected. The test suite builds a factory per test and the guard was
    absent from about half of it, which made "the suite runs the same rules as
    production" quietly untrue. A loop is the only way to see it: one factory
    always works.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401  registers the tables
    from app.db.base import Base
    from app.models.user import User

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    for index in range(25):
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as session:
            user = User(email=f"guard{index}@example.com")
            session.add(user)
            session.commit()
            session.add(FinancialProfile(user_id=user.id,
                                         monthly_income=float("inf")))
            with pytest.raises(NonFiniteValueError):
                session.flush()
            session.rollback()
