"""Tokens that may be spent exactly once.

`app/models/auth.py` already states the principle for password resets: "single
use means the server has to remember whether it was spent — which a stateless
token cannot do". The OAuth handoff token is the same kind of credential and
did not have the same property. It is a signed JWT with a sixty-second
lifetime, and `exchange` cleared the *cookie* on use while the *token* stayed
valid: anything that captured it — a shared machine, a proxy log, a browser
extension — could trade it for a full access and refresh pair until it
expired.

A reset gets a table because it lives for an hour and has to survive a
restart. A handoff lives for sixty seconds, so Redis is the right size of
memory for it, and the key expires on its own rather than needing a sweep.

**An unreachable Redis lets the token through.** The same direction the rate
limiter takes for `ask`, and for the same reason: failing closed here would
mean every third-party sign-in stops working whenever Redis blinks, which is
an outage of a core flow in exchange for closing a window that requires an
attacker to already hold a sixty-second credential. It is also strictly no
worse than the behaviour it replaces, where nothing was burned at all.

If Redis-independence ever matters more than that, the answer is a table with
the shape `password_resets` already has, not a cleverer stateless token.
"""
from __future__ import annotations

import logging

log = logging.getLogger("finmentor.nonce")

#: Prefix so a spent nonce is distinguishable from a rate-limit counter in
#: the same Redis.
_PREFIX = "finmentor:spent:"


def spend(nonce: str, *, ttl_seconds: int) -> bool:
    """Claim `nonce`. True the first time, False every time after.

    `ttl_seconds` should match the token's own lifetime: once the token has
    expired its signature check fails anyway, so remembering it any longer
    buys nothing and costs memory.

    Returns True when the store cannot be reached — see the module docstring.
    """
    if not nonce:
        # A token minted before this existed, or one that lost its claim.
        # Treated as spendable so an old cookie in a jar still works during a
        # deploy; they expire within the minute either way.
        return True
    try:
        from app.core import limits

        client = limits._redis()                      # the shared, pooled client
        # NX: the first caller creates the key and wins. EX so it cleans up
        # after itself, which is the whole reason this is not a table.
        claimed = client.set(f"{_PREFIX}{nonce}", "1", nx=True, ex=ttl_seconds)
        if not claimed:
            log.warning("refused a replayed single-use token")
        return bool(claimed)
    except Exception as exc:  # noqa: BLE001 - unreachable, missing, misconfigured
        log.warning(
            "no store to burn a single-use token, allowing it (%s). A captured "
            "token is replayable until it expires while this is the case.", exc,
        )
        return True
