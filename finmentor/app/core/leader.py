"""Which replica runs the scheduled jobs.

`ENABLE_SCHEDULER` is a per-process switch, so two replicas with it on are two
copies of every job: two market refreshes per interval against a free-tier
provider, and two retention passes over the same rows. Nothing in the
application noticed, because duplicating a refresh is not an error — it is
just twice the traffic, which is exactly the kind of cost that shows up on a
bill rather than in a log.

The lease here is the smallest thing that fixes it. Before running a job, a
process asks Redis for a short-lived key with `SET ... NX EX`: whoever gets it
runs, everyone else skips this tick and tries again on the next one. The
holder does not renew or hand over; the lease simply expires, and the next
tick is a fresh election. That means no shutdown path to get wrong, and a
process that dies mid-job costs one skipped interval rather than a stuck lock.

**Without Redis, every process runs.** That is deliberate and it is the safer
default for this project: the deployment it actually ships is a single API
container, and a lease that failed closed would silently stop refreshing the
cache the moment Redis blinked. Duplicated work is a cost; no work at all is
an outage. The same reasoning the rate limiter uses for `ask`.
"""
from __future__ import annotations

import logging
import os
import socket

from app.core.config import settings

log = logging.getLogger("finmentor.leader")

#: Distinct enough to tell two containers apart in a log, cheap enough to
#: compute on every tick.
IDENTITY = f"{socket.gethostname()}:{os.getpid()}"


def _key(job: str) -> str:
    return f"finmentor:lease:{job}"


def hold_lease(job: str, *, seconds: int | None = None) -> bool:
    """May this process run `job` on this tick?

    True when the lease was taken, or when Redis cannot be reached at all —
    see the module docstring for why that direction.
    """
    ttl = settings.scheduler_lease_seconds if seconds is None else seconds
    try:
        from app.core import limits

        client = limits._redis()                      # the shared, pooled client
        # NX so only the first caller in this window wins; EX so it expires
        # on its own and there is no release path to get wrong.
        taken = client.set(_key(job), IDENTITY, nx=True, ex=ttl)
        if not taken:
            log.debug("%s: another replica holds the lease", job)
        return bool(taken)
    except Exception as exc:  # noqa: BLE001 - unreachable, missing, misconfigured
        log.warning(
            "no lease store for %s, running anyway (%s). With more than one "
            "replica this means duplicated work.", job, exc,
        )
        return True


def run_if_leader(job: str, work) -> None:
    """Run `work` only if this process holds the lease for `job`."""
    if hold_lease(job):
        work()
