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
from app.ai.local_llm import LocalLLMUnavailable, get_local_provider
from app.ai.prompts import EXPLAIN_TEMPLATE, SYNTHESIS_TEMPLATE
from app.ai.rendering import render_context

log = logging.getLogger("finmentor.ai")

DETERMINISTIC_PREAMBLE = (
    "The explanation model is unavailable, so here are your figures exactly as "
    "they were calculated:"
)


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
    explain_prompt = EXPLAIN_TEMPLATE.format(question=question, context_json=context_json)
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
