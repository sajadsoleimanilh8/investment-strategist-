"""All prompt text lives here (spec section 32). Nothing else composes prompts.

Written for a 3B local model: short, imperative, one instruction per line.
Long prompts make small models drift, and drift here means an invented number.
"""
from __future__ import annotations

SYSTEM_PROMPT = """You are FinMentor, an educational financial assistant.
Every number you are given was calculated by a deterministic system.

Rules:
- Never output a number that is not in the context. Do not compute new numbers.
- Never tell the user to buy, sell, or invest in anything.
- If the context says a value is unavailable, say that plainly.
- Do not promise or predict future returns.
- Answer in clear, simple English for a young beginner."""

EXPLAIN_TEMPLATE = """Question: {question}

Context (the only numbers you may use):
{context_json}

Explain in 3-5 short sentences. Use ONLY the numbers above. If the context
marks something unavailable, say it is unavailable. No buy or sell advice."""

SYNTHESIS_TEMPLATE = """Merge the two drafts below into ONE clear answer.

Question: {question}
Context (the only numbers allowed): {context_json}
Draft A: {draft_a}
Draft B: {draft_b}

Keep only what the context supports. Drop repetition, predictions, and any
buy or sell advice. 3-5 short sentences."""
