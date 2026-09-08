"""The alembic revision must describe exactly what the models declare.

Needs a real Postgres — the migration relies on Postgres server defaults — so
these are skipped unless FINMENTOR_TEST_DATABASE_URL points at one:

    FINMENTOR_TEST_DATABASE_URL=postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test pytest
"""
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.db.base import Base
from tests.conftest import database_url_for_tests

ROOT = Path(__file__).resolve().parents[2]

postgres_only = pytest.mark.skipif(
    not database_url_for_tests().startswith("postgresql"),
    reason="needs FINMENTOR_TEST_DATABASE_URL pointing at Postgres",
)


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def _wipe(engine) -> None:
    """A truly empty database — no model tables, no alembic bookkeeping."""
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def migration_engine():
    """Own engine, deliberately not the `db_engine` one: alembic creates the schema here."""
    engine = create_engine(database_url_for_tests(), future=True)
    _wipe(engine)
    try:
        yield engine
    finally:
        _wipe(engine)
        engine.dispose()


def test_there_is_exactly_one_head():
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) == 1, f"branched migration history: {heads}"


@postgres_only
def test_upgrade_head_produces_the_model_schema(migration_engine):
    config = alembic_config()
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names())

        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        assert diff == [], f"migration drifted from the models: {diff}"


@postgres_only
def test_downgrade_removes_every_table(migration_engine):
    config = alembic_config()
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.downgrade(config, "base")

        remaining = set(inspect(connection).get_table_names()) & set(Base.metadata.tables)
        assert remaining == set()
