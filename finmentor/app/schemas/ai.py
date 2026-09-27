"""AI mentor request/response contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field

#: A question, not a document. The cap is about what the question *becomes*:
#: it is interpolated into the model prompt and appended verbatim to the
#: user's transcript, which is re-read and re-serialised on every later turn.
#: Unbounded, one request buys unbounded generation cost and permanent
#: storage growth, and the per-minute rate limit does not touch either
#: because it counts requests rather than bytes. Two thousand characters is
#: several paragraphs, which is past the length any real question reaches.
MAX_QUESTION_LENGTH = 2000


class AskRequest(BaseModel):
    user_id: int = Field(gt=0)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)


class AskResponse(BaseModel):
    text: str
    source: str            # local | hybrid | deterministic
    used_context: dict     # exactly the deterministic values handed to the LLM
    disclaimer_applied: bool
