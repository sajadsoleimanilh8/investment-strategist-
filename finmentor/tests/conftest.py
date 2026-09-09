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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registers every table on Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app

DEFAULT_TEST_DB_URL = "sqlite+pysqlite:///:memory:"


def database_url_for_tests() -> str:
    return os.getenv("FINMENTOR_TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


@pytest.fixture
def db_engine():
    url = database_url_for_tests()
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
def client(db) -> TestClient:
    """API client whose requests run against the test database."""
    fastapi_app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
