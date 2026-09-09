"""Response synthesizer (spec section 15).

Pipeline: deterministic result -> local draft -> (optional) remote draft ->
merge via the local model -> safety.enforce -> user.

Three tiers, in descending preference:

    hybrid        local draft + remote draft, merged by the local model
    local         local draft only (remote disabled, or it failed)
    deterministic no model text at all — the verified context, rendered

The tiers exist so an outage degrades the prose, never the numbers: the figures
are identical on all three paths because they were computed before any model
was involved. Every path returns through `safety.enforce`, and there is no
`return` in this module that does not.

This module never touches the database and never calls the engine — it is handed
a finished context by `app.api.deps.build_ai_context`.
"""
from __future__ import annotations

import json
import logging

from app.ai import remote_llm, safety
from app.core.config import settings
from app.ai.local_llm import LocalLLMUnavailable, get_local_provider
from app.ai.prompts import (
    CHAT_SYNTHESIS_TEMPLATE, CHAT_TEMPLATE, EXPLAIN_TEMPLATE, SYNTHESIS_TEMPLATE,
)
from app.ai.rendering import render_context, render_sides

log = logging.getLogger("finmentor.ai")

DETERMINISTIC_PREAMBLE = (
    "The explanation model is unavailable, so here are your figures exactly as "
    "they were calculated:"
)

#: Ceiling on the rendered history, so a long-running chat cannot crowd the
#: figures out of a 3B's context window. Turns are dropped oldest-first.
HISTORY_CHAR_BUDGET = 1500
NO_HISTORY = "(this is the start of the conversation)"


def _finish(text: str, *, source: str, context: dict, market_context: bool) -> dict:
    """The one exit point. Everything user-facing leaves through safety.enforce."""
    clean, report = safety.enforce(text, context=context, market_context=market_context)
    if report["downgraded"]:
        log.warning("ai answer downgraded: ungrounded numbers %s", report["ungrounded_numbers"])
        source = "deterministic"
    return {
        "text": clean,
        "source": source,
        "used_context": context,
        "disclaimer_applied": report["disclaimer_added"],
        "safety_report": report,
    }


def explain(question: str, context: dict, *, market_context: bool = False) -> dict:
    """Turn a verified context into prose. `context` is the ONLY source of numbers."""
    context_json = json.dumps(context, ensure_ascii=False, default=str)
    sides = render_sides(context)
    explain_prompt = EXPLAIN_TEMPLATE.format(
        question=question,
        # blank for a one-sided context, so the template does not grow a hole
        sides=f"\n{sides}\n" if sides else "",
        context_json=context_json,
    )
    local = get_local_provider()

    try:
        local_draft = local.generate(explain_prompt)
    except LocalLLMUnavailable as exc:
        log.info("local model unavailable, serving the deterministic context: %s", exc)
        return _finish(
            render_context(context, preamble=DETERMINISTIC_PREAMBLE),
            source="deterministic", context=context, market_context=market_context,
        )

    remote_draft = remote_llm.generate(explain_prompt) if remote_llm.is_enabled() else None
    if not remote_draft:
        return _finish(local_draft, source="local", context=context,
                       market_context=market_context)

    try:
        merged = local.generate(SYNTHESIS_TEMPLATE.format(
            question=question, context_json=context_json,
            draft_a=local_draft, draft_b=remote_draft,
        ))
    except LocalLLMUnavailable:
        # The local model died between the draft and the merge: the remote draft
        # is already written and still has to pass safety, so use it.
        merged = remote_draft

    return _finish(merged, source="hybrid", context=context, market_context=market_context)


# --- free conversation ---------------------------------------------------
#
# The chat path is the one place the assistant sees history, and the one place
# it is not answering a precise question. It still gets figures the engine
# already computed — a snapshot, never rows — and still leaves through
# `_finish`, so a warm reply is held to exactly the same grounding rule as a
# health explanation.


def render_history(turns: list[dict], limit: int | None = None) -> str:
    """The last few exchanges as plain text, oldest first, newest last.

    Truncated from the front: the most recent turn is the one that makes a
    reply feel like a conversation, so it is the last thing to go.
    """
    limit = settings.ai_chat_history_turns if limit is None else limit
    recent = turns[-limit:] if limit > 0 else []
    if not recent:
        return NO_HISTORY

    lines = []
    for turn in recent:
        lines.append(f"You: {turn.get('question', '')}".strip())
        lines.append(f"Guide: {turn.get('answer', '')}".strip())

    rendered = "\n".join(lines)
    while len(rendered) > HISTORY_CHAR_BUDGET and len(lines) > 2:
        lines = lines[2:]                      # drop the oldest exchange whole
        rendered = "\n".join(lines)
    return rendered[-HISTORY_CHAR_BUDGET:]


def chat(message: str, snapshot: dict, history: list[dict]) -> dict:
    """Reply warmly to a message that is not a precise question.

    Raises `LocalLLMUnavailable` rather than swallowing it: with no model there
    is no conversation to have, and the caller's canned capabilities answer is
    a better floor than prose we would have to invent.
    """
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, default=str)
    prompt = CHAT_TEMPLATE.format(
        snapshot_json=snapshot_json,
        history=render_history(history),
        question=message,
    )
    local = get_local_provider()
    local_draft = local.generate(prompt)

    remote_draft = remote_llm.generate(prompt) if remote_llm.is_enabled() else None
    if not remote_draft:
        return _finish(local_draft, source="local", context=snapshot,
                       market_context=False)

    try:
        merged = local.generate(CHAT_SYNTHESIS_TEMPLATE.format(
            question=message, snapshot_json=snapshot_json,
            draft_a=local_draft, draft_b=remote_draft,
        ))
    except LocalLLMUnavailable:
        merged = remote_draft

    return _finish(merged, source="hybrid", context=snapshot, market_context=False)
