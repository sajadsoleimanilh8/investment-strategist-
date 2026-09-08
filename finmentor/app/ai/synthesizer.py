"""Response synthesizer (spec section 15).

Pipeline: deterministic result -> local draft -> (optional) remote draft ->
merge via local model -> safety.enforce -> user.
Ported/expanded from legacy ai/combiner.py.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

import json

from app.ai import remote_llm, safety
from app.ai.local_llm import LocalLLMUnavailable, get_local_provider
from app.ai.prompts import EXPLAIN_TEMPLATE, SYNTHESIS_TEMPLATE


def explain(question: str, context: dict, *, market_context: bool = False) -> dict:
    """context = the deterministic values (and ONLY those) the LLM may use."""
    ctx_json = json.dumps(context, ensure_ascii=False, default=str)
    local = get_local_provider()

    try:
        draft_a = local.generate(EXPLAIN_TEMPLATE.format(question=question, context_json=ctx_json))
    except LocalLLMUnavailable:
        # Graceful degradation: hand back the deterministic context verbatim.
        return {
            "text": safety.enforce(
                "The local model is unavailable, so here is the calculated "
                "result on its own:\n"
                + ctx_json,
                market_context=market_context,
            ),
            "source": "deterministic",
            "used_context": context,
            "disclaimer_applied": True,
        }

    draft_b = remote_llm.generate(
        EXPLAIN_TEMPLATE.format(question=question, context_json=ctx_json)
    )
    if not draft_b:
        return {"text": safety.enforce(draft_a, market_context=market_context),
                "source": "local", "used_context": context, "disclaimer_applied": True}

    try:
        merged = local.generate(SYNTHESIS_TEMPLATE.format(
            question=question, context_json=ctx_json, draft_a=draft_a, draft_b=draft_b))
    except LocalLLMUnavailable:
        merged = draft_b
    return {"text": safety.enforce(merged, market_context=market_context),
            "source": "hybrid", "used_context": context, "disclaimer_applied": True}
