"""Schemas for Telegram account linking."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TelegramStatusOut(BaseModel):
    """Whether this account has a Telegram account attached."""

    linked: bool
    #: The user's own Telegram id, which is theirs to see. Null when unlinked.
    telegram_id: int | None = None


class LinkCodeOut(BaseModel):
    """A fresh code, and the two ways to use it."""

    #: Grouped for reading: `ABCD-EFGH-JKMN`. The hyphens are decoration and
    #: the bot accepts the code with or without them.
    code: str = Field(description="the code to send to the bot")
    expires_at: datetime
    ttl_minutes: int
    #: `https://t.me/<bot>?start=link_<code>`, or null when the deployment has
    #: not been told the bot's username. A null here is a missing setting, not
    #: an error: the code still works, it just has to be typed.
    deep_link: str | None = None
