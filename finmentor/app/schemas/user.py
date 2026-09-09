"""User contracts."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserIn(BaseModel):
    telegram_id: int = Field(gt=0)
    locale: str = Field(default="en", max_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    locale: str
    risk_profile: str | None = None
