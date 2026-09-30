"""When the background jobs run, and which process runs them.

Two defects, both invisible from inside a single process.

The market refresh was scheduled at exactly `market_cache_ttl_seconds`, the
same value `is_fresh` uses to decide a snapshot has expired. That is the one
interval guaranteed to leave a gap: the snapshot goes stale at the moment its
replacement is due, so every cycle had a stretch where requests fell through
to a provider — the thing SPEC section 24 says must not happen once warm.

And `ENABLE_SCHEDULER` is per process, so two replicas with it on were two
copies of every job: two refreshes per interval against a free-tier provider,
and two retention passes over the same rows. Nothing logged an error, because
doing the work twice is not an error. It is just twice the traffic.
"""
from __future__ import annotations

import pytest

from app.core import leader
from app.core.config import Settings, settings


# --- refresh before expiry, not at it ------------------------------------

def test_the_refresh_runs_before_the_cache_goes_stale():
    """The defect, as an inequality rather than a number."""
    assert settings.market_refresh_interval_seconds < settings.market_cache_ttl_seconds


def test_the_interval_is_a_fraction_of_the_ttl():
    config = Settings(market_cache_ttl_seconds=3600, market_refresh_fraction=0.5)

    assert config.market_refresh_interval_seconds == 1800


def test_a_tiny_ttl_cannot_produce_a_spinning_job():
    """A zero-second interval is a busy loop against a provider."""
    config = Settings(market_cache_ttl_seconds=1, market_refresh_fraction=0.1)

    assert config.market_refresh_interval_seconds >= 1


def test_the_scheduler_registers_both_jobs(monkeypatch):
    """Retention has to be scheduled, not merely written."""
    from app import main

    monkeypatch.setattr(settings, "enable_scheduler", True)
    scheduler = main._start_scheduler()
    try:
        ids = {job.id for job in scheduler.get_jobs()}
        assert ids == {"market_snapshots", "retention"}
    finally:
        scheduler.shutdown(wait=False)


def test_the_market_job_is_scheduled_at_the_derived_interval(monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "enable_scheduler", True)
    scheduler = main._start_scheduler()
    try:
        job = scheduler.get_job("market_snapshots")
        assert job.trigger.interval.total_seconds() == \
            settings.market_refresh_interval_seconds
    finally:
        scheduler.shutdown(wait=False)


# --- one replica does the work -------------------------------------------

class _FakeRedis:
    """Enough of the client for a lease: `set` with NX."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True


@pytest.fixture
def lease_store(monkeypatch):
    from app.core import limits

    store = _FakeRedis()
    monkeypatch.setattr(limits, "_redis", lambda: store)
    return store


def test_only_the_first_replica_takes_the_lease(lease_store):
    """Two containers, one tick, one run."""
    first = leader.hold_lease("market_snapshots")
    second = leader.hold_lease("market_snapshots")

    assert first is True
    assert second is False


def test_different_jobs_have_different_leases(lease_store):
    """Holding the refresh lease must not block retention."""
    assert leader.hold_lease("market_snapshots") is True
    assert leader.hold_lease("retention") is True


def test_the_leader_runs_the_work_and_the_others_skip_it(lease_store):
    runs = []

    leader.run_if_leader("market_snapshots", lambda: runs.append("first"))
    leader.run_if_leader("market_snapshots", lambda: runs.append("second"))

    assert runs == ["first"]


def test_without_a_lease_store_the_work_still_happens(monkeypatch, caplog):
    """Deliberate, and the direction matters.

    A lease that failed closed would stop refreshing the cache the moment
    Redis blinked. Duplicated work is a cost; no work at all is an outage.
    This project deploys one API container, where "run anyway" is simply
    correct.
    """
    from app.core import limits

    def no_redis():
        raise OSError("connection refused")

    monkeypatch.setattr(limits, "_redis", no_redis)
    runs = []

    leader.run_if_leader("market_snapshots", lambda: runs.append("ran"))

    assert runs == ["ran"]
    assert any("running anyway" in record.message for record in caplog.records)


def test_the_lease_names_the_holder(lease_store):
    """So a log can say which container is doing the work."""
    leader.hold_lease("market_snapshots")

    assert lease_store.keys["finmentor:lease:market_snapshots"] == leader.IDENTITY
