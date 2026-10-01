"""Small defects that cost nothing today and something later.

None of these broke anything when they were written. A deprecated call still
runs, an unbounded query parameter still answers, a duplicate operation id
still serves requests, and a missing constraint still stores rows. They are
here because each one has a date or a load at which it stops being free, and
because a test is cheaper than remembering.
"""
from __future__ import annotations

import pathlib

import pytest

from app.api.routes.market import MAX_DAYS
from app.market.alpha_vantage import AlphaVantageProvider

APP = pathlib.Path(__file__).resolve().parents[2] / "app"


# --- APIs with an expiry date --------------------------------------------

def _code_only(source: str) -> str:
    """The source with comments and docstrings removed.

    A scan that reads prose fails on its own explanation: the comment above
    each fixed call names the deprecated function in order to say why it is
    not being used. Tokenising is the honest way to ask "does this *call*
    it".
    """
    import io
    import tokenize

    kept = []
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    previous_type = tokenize.INDENT
    for token in tokens:
        if token.type == tokenize.COMMENT:
            continue
        # A string in statement position is a docstring, not a value.
        if token.type == tokenize.STRING and previous_type in (
            tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT,
        ):
            continue
        kept.append(token.string)
        if token.type not in (tokenize.NL, tokenize.COMMENT):
            previous_type = token.type
    return " ".join(kept)


@pytest.mark.parametrize("deprecated", ["utcnow", "utcfromtimestamp"])
def test_no_naive_utc_helper_survives(deprecated):
    """`utcnow` and `utcfromtimestamp` return a *naive* datetime claiming to
    be UTC, which is why they are deprecated. The runtime is 3.11 today, so
    this costs nothing until the image moves and then costs an upgrade."""
    offenders = [
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if deprecated in _code_only(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], f"{offenders} still call datetime.{deprecated}"


# --- a query parameter nobody bounded ------------------------------------

def test_the_market_days_parameter_is_bounded(client):
    """`days` was a bare `int`, so `?days=100000` was a valid request: one
    provider call and a very large JSON body, for free."""
    assert client.get(f"/api/market/assets/BTC?days={MAX_DAYS + 1}").status_code == 422
    assert client.get("/api/market/assets/BTC?days=0").status_code == 422


def test_the_watchlist_days_parameter_is_bounded(client):
    user_id = client.post("/api/users", json={"telegram_id": 702_001}).json()["id"]

    response = client.get(f"/api/market/watchlist/{user_id}?days={MAX_DAYS + 1}")

    assert response.status_code == 422


def test_adding_to_a_watchlist_still_returns_the_list(client, db):
    """`add_to_watchlist` answered by calling the `get_watchlist` *handler*.

    That works right up until a parameter grows a `Query` default, at which
    point the direct call passes the `Query` object where an int belongs. A
    route handler is only a plain function while FastAPI is not the one
    supplying its arguments.
    """
    from app.repositories import market as market_repo

    user_id = client.post("/api/users", json={"telegram_id": 702_002}).json()["id"]
    market_repo.upsert_asset(db, symbol="BTC", provider_id="bitcoin",
                             asset_class="crypto", display_name="Bitcoin")
    db.commit()

    response = client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "BTC"})

    assert response.status_code == 201, response.text
    assert [item["symbol"] for item in response.json()["items"]] == ["BTC"]


# --- a provider claiming symbols it cannot serve -------------------------

@pytest.mark.parametrize("symbol", ["BTC", "ETH", "SOL"])
def test_the_equities_provider_does_not_claim_crypto(symbol):
    """`supports` was "all letters, all upper case", which is true of BTC as
    well as AAPL. Providers are tried in order, so every crypto refresh spent
    an Alpha Vantage call — against a free tier measured in calls per day —
    before failing through to the provider that was always going to answer."""
    assert AlphaVantageProvider().supports(symbol) is False


@pytest.mark.parametrize("symbol", ["AAPL", "MSFT", "TSLA", "NVDA"])
def test_the_equities_provider_still_claims_equities(symbol):
    """A fix that refuses everything would pass the test above."""
    assert AlphaVantageProvider().supports(symbol) is True


# --- one schema, one name per operation ----------------------------------

def test_the_openapi_schema_has_no_duplicate_operation_ids():
    """A duplicate is a `UserWarning` on every build and a generated client
    with two functions of the same name, one of which silently wins."""
    from app.main import create_app

    schema = create_app().openapi()
    ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    duplicates = {name for name in ids if ids.count(name) > 1}
    assert duplicates == set(), f"duplicate operation ids: {duplicates}"


def test_building_the_schema_emits_no_warning(recwarn):
    from app.main import create_app

    create_app().openapi()

    assert [w for w in recwarn if "Duplicate Operation ID" in str(w.message)] == []


# --- one chat session per user -------------------------------------------

def test_a_user_cannot_have_two_chat_sessions(db, current_user):
    """`get_or_create` reads the newest and creates when there is none, so two
    concurrent `/ask` calls could both insert. The older row was then
    unreachable: every read took the newer one, and its turns were invisible.
    The `order_by` made that survivable instead of visible."""
    from sqlalchemy.exc import IntegrityError

    from app.models.simulation import ChatSession

    db.add(ChatSession(user_id=current_user.id, transcript_json="[]"))
    db.commit()

    db.add(ChatSession(user_id=current_user.id, transcript_json="[]"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_the_constraint_has_a_migration():
    """A model-only constraint exists in the test database and nowhere else."""
    versions = (APP.parent / "migrations" / "versions")
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in versions.glob("*.py")
    )

    assert "uq_chat_sessions_user" in sources


def test_the_migration_deduplicates_before_constraining():
    """A database that already has a pair cannot take the constraint, so the
    migration has to remove the unreachable rows first or it fails on exactly
    the deployments that needed it."""
    versions = (APP.parent / "migrations" / "versions")
    migration = next(
        path for path in versions.glob("*.py")
        if "uq_chat_sessions_user" in path.read_text(encoding="utf-8")
    )
    source = migration.read_text(encoding="utf-8")

    assert "DELETE FROM chat_sessions" in source
    assert source.index("DELETE FROM chat_sessions") < source.index(
        "create_unique_constraint")
