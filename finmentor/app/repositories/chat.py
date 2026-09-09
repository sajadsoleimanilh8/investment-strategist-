"""CRUD for `chat_sessions` — the AI transcript.

One open session per user, with `transcript_json` holding a list of turns. The
transcript is history, not context: the assistant answers from the verified
figures assembled per request, never from what it said last time.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.simulation import ChatSession


def get_or_create(db: Session, user_id: int) -> ChatSession:
    session = db.scalar(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.id.desc())
        .limit(1)
    )
    if session is None:
        session = ChatSession(user_id=user_id, transcript_json="[]")
        db.add(session)
        db.flush()
    return session


def read_transcript(session: ChatSession) -> list[dict[str, Any]]:
    try:
        turns = json.loads(session.transcript_json or "[]")
    except json.JSONDecodeError:
        return []
    return turns if isinstance(turns, list) else []


def append_turn(
    db: Session,
    user_id: int,
    *,
    question: str,
    answer: str,
    intent: str,
    source: str,
) -> ChatSession:
    """Append one exchange to the user's transcript. The caller commits."""
    session = get_or_create(db, user_id)
    turns = read_transcript(session)
    turns.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "answer": answer,
        "intent": intent,
        "source": source,
    })
    session.transcript_json = json.dumps(turns, ensure_ascii=False)
    db.flush()
    return session
