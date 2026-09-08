"""AI mentor request/response contracts."""
from __future__ import annotations

from pydantic import BaseModel


class AskRequest(BaseModel):
    user_id: int
    question: str


class AskResponse(BaseModel):
    text: str
    source: str            # local | hybrid | deterministic
    used_context: dict     # exactly the deterministic values handed to the LLM
    disclaimer_applied: bool
