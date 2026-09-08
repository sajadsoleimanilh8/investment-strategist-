"""Auth / rate-limiting primitives.

Phase 1 ships without user auth (Telegram user id is the identity). This
module is the seam for API keys / JWT if a web client is added later.
# >>> finmentor-stub <<<
"""
from __future__ import annotations


def rate_limit_key(user_id: str, bucket: str) -> str:
    return f"rl:{bucket}:{user_id}"


# TODO(phase-7): token hashing, per-user request quotas backed by Redis.
