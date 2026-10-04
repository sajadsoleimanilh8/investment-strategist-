"""Rate limiting, with no web framework in sight.

It used to live in `app/api/deps.py` as a private helper behind three FastAPI
dependencies, which put it on the HTTP surface rather than on the thing it
protects. That mattered: `/ai/ask` was rate limited and the Telegram bot,
which calls the same pipeline in-process, was not. A guard attached to one
door is not a guard.

So the counting lives here, framework-free, and both surfaces reach it through
the pipeline that actually spends the resource. `app/api/deps.py` still
exposes the FastAPI dependencies for the routes whose budget is genuinely an
HTTP concern (signup and login are per-address, and an address is an HTTP
notion).

Two deliberate properties.

**One client, not one per request.** `redis.Redis.from_url` builds a new
connection pool every time it is called, and the old code called it on every
signup, login, ask and simulation. The client here is module-level and
lazy: built on first use, reused after that, and rebuilt if it breaks.

**Fail open, except where failing open is the hole.** If Redis is unreachable
the limiter lets the request through, because a cache outage taking the whole
API with it is a worse failure than the one the limiter prevents. That is the
right trade for `/ask`, where the cost of an outage is a model bill. It is the
wrong trade for authentication, where failing open removes brute-force
protection altogether and silently. So `auth` gets an in-process fallback
counter: weaker than Redis (it is per-process and resets on restart) but not
nothing, which is what it replaced.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

from app.core.config import settings
from app.core.security import rate_limit_key

log = logging.getLogger("finmentor.limits")

#: Buckets that must not simply wave requests through when Redis is down.
#: Authentication is the one place where an unlimited retry loop is the whole
#: attack rather than a cost.
FAIL_CLOSED_BUCKETS = frozenset({"auth"})

_client = None
#: The `redis_url` the cached client was built from, so `reset` can tell a
#: changed address from an unchanged one.
_client_url: str | None = None
_client_lock = threading.Lock()


def _redis():
    """The shared client, built once. None when redis is unusable."""
    global _client, _client_url
    if _client is not None:
        if _client_url == settings.redis_url:
            return _client
        # The address changed under us. Checked here rather than in `reset`
        # because a caller can repoint `redis_url` at any moment -- a test
        # pointing it at a dead address to watch the fallback does exactly
        # that, after `reset` has already run -- and handing back a client
        # built for the old address would quietly ignore them.
        _drop_client()
    with _client_lock:
        if _client is None:
            import redis

            _client_url = settings.redis_url
            _client = redis.Redis.from_url(
                settings.redis_url,
                socket_timeout=settings.redis_command_timeout_seconds,
                socket_connect_timeout=settings.redis_connect_timeout_seconds,
                health_check_interval=30,
            )
    return _client


#: Prefix every counter key shares. Exposed so a test fixture can clear the
#: counters without reaching for `flushdb` -- this instance also holds the
#: market cache, which a test has no business dropping.
KEY_PREFIX = "rl:"


def reset() -> None:
    """Forget the shared client and every in-process count.

    For tests: the client is cached across calls by design, so a suite that
    points `redis_url` somewhere new mid-run would otherwise keep talking to
    the old one. Cheap enough to call per test, and deliberately **does not
    connect** -- connecting here would cache a client built from whatever
    `redis_url` says at reset time, which is exactly what a test that then
    points `redis_url` at a dead address is trying to avoid.

    Counts already stored in Redis are not this function's business either.
    `tests/conftest.py` clears those with its own short-lived client, because
    the key prefix is public and a test fixture is where test isolation
    belongs.
    """
    # The client is deliberately *not* dropped here. It used to be, so that a
    # suite repointing `redis_url` mid-run could not keep talking to the old
    # address -- but `_redis` now notices a changed address itself, which
    # covers that case at the moment it matters rather than once per test.
    #
    # Dropping it unconditionally was also the source of a real flake: every
    # test reconnected, and a connect slower than
    # `redis_connect_timeout_seconds` sends that one call to the in-process
    # counter while the rest go to Redis. The count splits and a limit lets an
    # extra request through, which showed up as a different test in
    # `tests/api/test_rate_limit.py` failing on each run.
    _local.__init__()


def _drop_client() -> None:
    """Forget a client that failed, so the next call builds a fresh one."""
    global _client, _client_url
    with _client_lock:
        _client = None
        _client_url = None


class _LocalCounter:
    """A per-process fallback for the buckets that must not fail open.

    Deliberately simple: a fixed window per minute, the same shape as the
    Redis counter, kept in memory. Across several replicas it permits N times
    the intended rate, which is the price of not needing Redis to be up. That
    is still a bound, and a bound is what brute forcing needs to not have.
    """

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = defaultdict(int)
        self._lock = threading.Lock()

    def hit(self, key: str, per_minute: int) -> bool:
        window = int(time.time() // 60)
        with self._lock:
            # Drop everything from an earlier window rather than growing a
            # dict keyed on every minute the process has been alive.
            stale = [k for k in self._counts if k[1] != window]
            for k in stale:
                del self._counts[k]
            self._counts[(key, window)] += 1
            return self._counts[(key, window)] <= per_minute


_local = _LocalCounter()


def allow(bucket: str, identity: str, per_minute: int) -> bool:
    """Has `identity` any budget left in `bucket` this minute?

    `per_minute <= 0` disables the limit, which is what the test suite uses.
    """
    if per_minute <= 0:
        return True

    key = rate_limit_key(identity, bucket)
    try:
        client = _redis()
        used = client.incr(key)
        if used == 1:
            client.expire(key, 60)
        return used <= per_minute
    except Exception as exc:                  # unreachable, missing, misconfigured
        _drop_client()
        if bucket in FAIL_CLOSED_BUCKETS:
            log.warning("rate limiter unavailable, falling back in-process: %s", exc)
            return _local.hit(key, per_minute)
        log.warning("rate limiter unavailable, allowing the request: %s", exc)
        return True
