"""Test fixtures.

Database choice: tests run against an in-memory SQLite database by default, so
`pytest` needs no infrastructure and stays fast. Foreign keys are enforced via
`PRAGMA foreign_keys=ON`, which is what makes the FK/cascade assertions real.

To run the same suite against a real Postgres (recommended before a release,
and what CI should do for the migration test), point it at one:

    FINMENTOR_TEST_DATABASE_URL=postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test pytest

Nothing here touches the app's own engine (`app.db.session.engine`); the API
fixture overrides the `get_db` dependency instead.
"""
import os

os.environ.setdefault("DEMO_MODE", "true")
# the background market refresh must never run under pytest — it would fetch
# on a timer against whatever database the app engine points at
os.environ.setdefault("ENABLE_SCHEDULER", "false")
# no live model in the test environment: `fake` is the deterministic double in
# app/ai/local_llm.py. Remote stays disabled; tests that want the hybrid tier
# monkeypatch `app.ai.remote_llm.generate` / `is_enabled`.
os.environ.setdefault("LOCAL_LLM_PROVIDER", "fake")
# The rate limiters are real infrastructure and every test arrives from the
# same client address, so a suite that exercises login twenty times would trip
# a limit meant for a human. 0 disables them; `test_rate_limit.py` turns one
# back on and asserts it works.
os.environ.setdefault("AUTH_RATE_LIMIT_PER_MINUTE", "0")
os.environ.setdefault("ASK_RATE_LIMIT_PER_MINUTE", "0")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registers every table on Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

DEFAULT_TEST_DB_URL = "sqlite+pysqlite:///:memory:"

#: Escape hatch for a real test database that, for whatever reason, cannot be
#: named with "test" in it. Set to "1" to bypass the name check below.
DESTRUCTIVE_OVERRIDE_ENV = "FINMENTOR_ALLOW_DESTRUCTIVE_TESTS"


def database_url_for_tests() -> str:
    return os.getenv("FINMENTOR_TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


def guard_destructive_target(url: str) -> None:
    """Refuse to run the suite against anything that isn't obviously a test DB.

    `db_engine` below calls `Base.metadata.drop_all` on whatever this URL
    points at, twice per test. SQLite is always a private in-memory database,
    so it's always safe. Postgres is a real, possibly-shared server — pointed
    at the running demo stack by mistake (a copy-paste of `DATABASE_URL`
    instead of `FINMENTOR_TEST_DATABASE_URL`, say), that isn't a test failure,
    it's a wiped database. It happened once, mid–Phase 8. So: the database
    name must contain "test", or you say so explicitly.
    """
    if url.startswith("sqlite"):
        return
    db_name = make_url(url).database or ""
    if "test" in db_name.lower():
        return
    if os.getenv(DESTRUCTIVE_OVERRIDE_ENV) == "1":
        return
    raise RuntimeError(
        f"Refusing to run the test suite against database {db_name!r}: its "
        "name doesn't contain 'test', and this suite drops every table it "
        "manages, twice per test. Point FINMENTOR_TEST_DATABASE_URL at a "
        f"database named e.g. 'finmentor_test', or set "
        f"{DESTRUCTIVE_OVERRIDE_ENV}=1 if you are certain."
    )


@pytest.fixture
def db_engine():
    url = database_url_for_tests()
    guard_destructive_target(url)
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    engine = create_engine(url, future=True, **kwargs)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db(db_engine) -> Session:
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def bot_db(db_engine, monkeypatch):
    """Point `app.bot.context.session()` at the test database.

    The bot opens its own sessions (it is not a FastAPI request, so there is no
    dependency to override), which is exactly the thing to redirect here.
    """
    import app.bot.context as bot_context

    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(bot_context, "SessionLocal", factory)
    return factory


@pytest.fixture
def current_user(db):
    """A real `users` row standing in for whoever is signed in.

    A real row, not a stand-in object: routes that write rows keyed on the
    caller (`education_progress`, `chat_sessions`) need a foreign key that
    resolves, and an id of 0 fails that at the database rather than in the code
    under test.
    """
    from app.repositories import users as users_repo

    user = users_repo.create_web_user(
        db, email="tests@finmentor.local", password_hash="x"
    )
    db.commit()
    return user


@pytest.fixture
def client(db, current_user, monkeypatch) -> TestClient:
    """API client authenticated as `current_user`, with ownership waived.

    The suite predates web auth and is about business logic, not about who is
    allowed to call what. Rather than thread a token through two hundred
    assertions, `require_user` and the ownership guard are overridden here — so
    these tests keep testing what they were written to test.

    The guard itself is tested for real in `tests/api/test_auth.py`, which uses
    `raw_client`, mints real tokens, and asserts the 401s and cross-user 403s.
    """
    from app.api import deps

    fastapi_app.dependency_overrides[get_db] = lambda: db
    fastapi_app.dependency_overrides[deps.require_user] = lambda: current_user
    # Annotated, not a bare lambda: FastAPI coerces a path parameter using the
    # dependency's own signature, so an unannotated override hands the route a
    # *string*. SQLite tolerates that and Postgres does not, which makes it the
    # kind of bug that only appears in CI.
    def owns_anything(user_id: int) -> int:
        return user_id

    fastapi_app.dependency_overrides[deps.owned_user_id] = owns_anything

    # `assert_owns` guards the routes that carry a user id in the *body*
    # (`POST /goals`, `/simulations`, `/ai/ask`). It is a plain call inside the
    # handler, not a dependency, so it cannot be overridden — it has to be
    # patched where each module bound the name at import.
    for module in ("goals", "simulations", "ai"):
        monkeypatch.setattr(f"app.api.routes.{module}.assert_owns",
                            lambda user, user_id: user_id)
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def raw_client(db) -> TestClient:
    """The API exactly as a browser meets it: no overrides, real guards."""
    fastapi_app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()


def error_message(response) -> str:
    """The human-readable half of the API's error envelope.

    Phase 8 replaced FastAPI's bare `{"detail": ...}` with a stable shape
    (`app/api/errors.py`), so assertions go through here rather than reaching
    into the body — one place to change if the envelope ever moves again.
    """
    body = response.json()["error"]
    fields = body.get("fields")
    return body["message"] + ("; " + "; ".join(
        f"{f['field']}: {f['message']}" for f in fields) if fields else "")
