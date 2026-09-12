"""The destructive-test-target guard (tests/conftest.py::guard_destructive_target).

Pure string/URL parsing, no database connection — these run even when nothing
is listening on 5432.
"""
import pytest

from tests.conftest import DESTRUCTIVE_OVERRIDE_ENV, guard_destructive_target


def test_sqlite_always_allowed():
    guard_destructive_target("sqlite+pysqlite:///:memory:")


def test_postgres_test_database_allowed():
    guard_destructive_target(
        "postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test"
    )


def test_postgres_test_database_allowed_case_insensitive():
    guard_destructive_target(
        "postgresql+psycopg://finmentor:finmentor@localhost:5432/FinMentor_TEST"
    )


def test_postgres_non_test_database_refused():
    with pytest.raises(RuntimeError, match="finmentor"):
        guard_destructive_target(
            "postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor"
        )


def test_override_env_bypasses_the_check(monkeypatch):
    monkeypatch.setenv(DESTRUCTIVE_OVERRIDE_ENV, "1")
    guard_destructive_target(
        "postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor"
    )


def test_override_env_wrong_value_does_not_bypass(monkeypatch):
    monkeypatch.setenv(DESTRUCTIVE_OVERRIDE_ENV, "true")  # only "1" counts
    with pytest.raises(RuntimeError):
        guard_destructive_target(
            "postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor"
        )
