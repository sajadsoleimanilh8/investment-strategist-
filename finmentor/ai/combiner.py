"""
The hybrid layer: queries the local model and the external API model for
the same question, then produces ONE merged answer.

Design (see README "Architecture" section for the diagram):
    1. Always ask the local model (it's the reliable core).
    2. Ask the external API model too, IF configured and reachable.
    3. If only local answered -> return it as-is.
    4. If both answered -> feed both drafts back into the local model and
       ask it to synthesize one clear answer. The local model acts as the
       final "judge/editor", so the system stays self-contained even
       though it borrowed a second opinion from the API.
    5. Every answer gets a short, fixed disclaimer appended — this is a
       product decision, not just a legal footnote: the bot explains
       trends, it does not give personalized investment advice.
"""
from ai import local_model, api_model

DISCLAIMER = (
    "\n\n⚠️ این تحلیل، آموزشی و بر اساس روند اخیر بازاره، نه پیش‌بینی تضمینی یا "
    "توصیه‌ی خرید/فروش. تصمیم سرمایه‌گذاری نهایی با خودته."
)

SYNTHESIS_TEMPLATE = """Two draft answers were produced for the same user question.
Combine them into ONE clear, accurate, non-redundant answer. Prefer the more
specific/correct claims, drop anything that contradicts known facts or sounds
like a guaranteed prediction, and keep the tone simple and educational.
Answer in the same language as the user's original question.

User question: {question}

Draft A (local model):
{draft_a}

Draft B (external model):
{draft_b}

Final combined answer:"""


def answer(question: str) -> dict:
    """Returns {"text": str, "source": "local" | "hybrid", "disclaimer": bool}."""
    local_draft = local_model.generate_safe(question)

    api_draft = None
    if api_model.is_configured():
        api_draft = api_model.generate(question)

    if not api_draft:
        return {"text": local_draft + DISCLAIMER, "source": "local"}

    synthesis_prompt = SYNTHESIS_TEMPLATE.format(
        question=question, draft_a=local_draft, draft_b=api_draft
    )
    try:
        merged = local_model.generate(synthesis_prompt)
    except local_model.LocalModelUnavailable:
        # Local model died mid-flow but we do have an API draft -> use that
        # rather than failing the whole request.
        merged = api_draft

    return {"text": merged + DISCLAIMER, "source": "hybrid"}
