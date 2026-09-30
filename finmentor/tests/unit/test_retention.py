"""Three tables that grew on a timer and were never pruned.

None of them is bounded by anything a user does: the refresh job writes a
market snapshot per symbol per interval, a reset row outlives the link it
represents, and a simulation row is written per request to a rate-limited but
otherwise unlimited endpoint. Nothing deleted any of it.

The three are treated differently on purpose, and the tests say which is
which: two are maintenance, and the third is the user's own data.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.auth import PasswordReset
from app.models.market import MarketSnapshot
from app.models.simulation import Simulation
from scripts.prune_records import (
    _as_utc, prune, prune_market_snapshots, prune_password_resets,
    prune_simulations,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def snapshot(db, symbol: str, *, minutes_ago: int) -> MarketSnapshot:
    row = MarketSnapshot(
        symbol=symbol,
        as_of=NOW - timedelta(minutes=minutes_ago),
        points_json=json.dumps([{"date": "2026-09-01", "close": 100.0, "volume": None}]),
    )
    db.add(row)
    db.flush()
    return row


# --- market_snapshots: a cache -------------------------------------------

def test_only_the_newest_snapshots_per_symbol_survive(db):
    for minutes in range(10):
        snapshot(db, "BTC", minutes_ago=minutes)

    removed = prune_market_snapshots(db, keep_per_symbol=3)
    db.commit()

    assert removed == 7
    kept = db.query(MarketSnapshot).all()
    assert len(kept) == 3


def test_the_newest_snapshot_is_never_the_one_removed(db):
    """`latest_snapshot` is the only read, so losing it would empty the cache."""
    for minutes in range(6):
        snapshot(db, "BTC", minutes_ago=minutes)

    prune_market_snapshots(db, keep_per_symbol=2)
    db.commit()

    # Through `_as_utc`, because SQLite hands the column back naive and
    # Postgres does not — the same normalisation the cache does on read.
    newest = max(db.query(MarketSnapshot).all(), key=lambda row: row.as_of)
    assert _as_utc(newest.as_of) == NOW


def test_symbols_are_pruned_independently(db):
    """One busy symbol must not evict another's only snapshot."""
    for minutes in range(8):
        snapshot(db, "BTC", minutes_ago=minutes)
    snapshot(db, "ETH", minutes_ago=1)

    prune_market_snapshots(db, keep_per_symbol=2)
    db.commit()

    by_symbol = {}
    for row in db.query(MarketSnapshot).all():
        by_symbol.setdefault(row.symbol, []).append(row)
    assert len(by_symbol["BTC"]) == 2
    assert len(by_symbol["ETH"]) == 1


def test_a_keep_of_zero_disables_snapshot_pruning(db):
    """Off means off, not "delete everything" — the difference is the cache."""
    snapshot(db, "BTC", minutes_ago=1)

    assert prune_market_snapshots(db, keep_per_symbol=0) == 0
    assert db.query(MarketSnapshot).count() == 1


# --- password_resets: spent credentials ----------------------------------

def test_long_expired_resets_are_removed(db, current_user):
    db.add(PasswordReset(user_id=current_user.id, token_hash="a" * 64,
                         expires_at=NOW - timedelta(days=30)))
    db.commit()

    removed = prune_password_resets(db, older_than_days=7, now=NOW)
    db.commit()

    assert removed == 1
    assert db.query(PasswordReset).count() == 0


def test_a_recently_expired_reset_is_kept(db, current_user):
    """The row is what refuses a second use of a spent link as "no longer
    valid" rather than "no such token". That distinction is worth keeping
    while the link might still be sitting in somebody's inbox."""
    db.add(PasswordReset(user_id=current_user.id, token_hash="b" * 64,
                         expires_at=NOW - timedelta(hours=2)))
    db.commit()

    assert prune_password_resets(db, older_than_days=7, now=NOW) == 0
    assert db.query(PasswordReset).count() == 1


def test_an_outstanding_reset_is_never_touched(db, current_user):
    """Deleting a live one would break a link somebody is about to click."""
    db.add(PasswordReset(user_id=current_user.id, token_hash="c" * 64,
                         expires_at=NOW + timedelta(minutes=30)))
    db.commit()

    assert prune_password_resets(db, older_than_days=7, now=NOW) == 0
    assert db.query(PasswordReset).count() == 1


# --- simulations: the user's own data ------------------------------------

def make_simulations(db, user_id: int, how_many: int) -> None:
    for index in range(how_many):
        db.add(Simulation(user_id=user_id, kind="decision",
                          params_json=json.dumps({"price": index}),
                          result_json=json.dumps({"affordable": True})))
    db.flush()


def test_simulations_are_capped_per_user(db, current_user):
    make_simulations(db, current_user.id, 12)
    db.commit()

    removed = prune_simulations(db, keep_per_user=5)
    db.commit()

    assert removed == 7
    assert db.query(Simulation).count() == 5


def test_the_default_cap_is_far_beyond_what_the_product_can_reach(db, current_user):
    """This is a runaway guard, not a retention policy.

    The list endpoint pages at 100 and a person runs a handful. A default that
    could delete a real history would be a product decision, and deleting a
    user's own saved runs is not a decision this job gets to make.
    """
    make_simulations(db, current_user.id, 30)
    db.commit()

    assert prune_simulations(db) == 0
    assert settings.retention_simulations_per_user >= 500


def test_one_users_runs_do_not_evict_anothers(db, current_user):
    from app.repositories import users as users_repo

    other = users_repo.create(db, telegram_id=990_101)
    db.flush()
    make_simulations(db, current_user.id, 9)
    make_simulations(db, other.id, 2)
    db.commit()

    prune_simulations(db, keep_per_user=3)
    db.commit()

    counts = {}
    for row in db.query(Simulation).all():
        counts[row.user_id] = counts.get(row.user_id, 0) + 1
    assert counts[current_user.id] == 3
    assert counts[other.id] == 2


# --- the job as a whole --------------------------------------------------

def test_the_job_reports_what_it_removed(db, current_user):
    for minutes in range(10):
        snapshot(db, "BTC", minutes_ago=minutes)
    db.commit()

    counts = prune(db)

    assert set(counts) == {"market_snapshots", "password_resets", "simulations"}
    assert counts["market_snapshots"] > 0


def test_one_failing_table_does_not_abort_the_run(db, monkeypatch, current_user):
    """A job that stops at the first problem leaves the rest undone forever."""
    import scripts.prune_records as job

    for minutes in range(10):
        snapshot(db, "BTC", minutes_ago=minutes)
    db.commit()

    def explode(*args, **kwargs):
        raise RuntimeError("that table is having a bad day")

    monkeypatch.setattr(job, "prune_password_resets", explode)

    counts = job.prune(db)

    assert counts["password_resets"] == 0
    assert counts["market_snapshots"] > 0, "a later rule was skipped"


def test_the_job_runs_on_an_empty_database(db):
    """The first night of a new deployment."""
    assert prune(db) == {
        "market_snapshots": 0, "password_resets": 0, "simulations": 0,
    }
