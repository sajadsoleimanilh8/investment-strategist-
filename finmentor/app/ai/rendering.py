"""Plain-language rendering of a deterministic context.

Used on the two paths where no model text may be shown: the local-model-down
tier, and a safety downgrade. Both need the verified numbers in readable prose
rather than a raw JSON dump, and both must produce text whose every figure came
straight from the context.

Pure formatting — no I/O, no model, no engine call.
"""
from __future__ import annotations

from app.core.config import settings

#: keys whose values read as money rather than a bare count
_MONEY_KEYS = (
    "savings", "income", "expenses", "debt", "fund", "amount", "price", "balance",
    "target", "current_savings", "projected_savings_end",
)
_PERCENT_KEYS = ("rate", "pct", "percent")


def _looks_like(key: str, needles: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(needle in lowered for needle in needles)


def humanise_key(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def format_value(key: str, value: object) -> str:
    """Render one leaf. Money uses the configured currency symbol, never a literal."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if _looks_like(key, _PERCENT_KEYS) and abs(value) <= 1:
            return f"{value * 100:.1f}%"
        if _looks_like(key, _MONEY_KEYS):
            return f"{settings.currency_symbol}{value:,.0f}"
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _lines(context: dict, indent: str = "") -> list[str]:
    lines: list[str] = []
    for key, value in context.items():
        label = humanise_key(key)
        if isinstance(value, dict):
            lines.append(f"{indent}{label}:")
            lines.extend(_lines(value, indent + "  "))
        elif isinstance(value, list):
            if not value:
                lines.append(f"{indent}{label}: none")
            elif all(isinstance(item, dict) for item in value):
                lines.append(f"{indent}{label}:")
                for item in value:
                    lines.extend(_lines(item, indent + "  "))
            else:
                lines.append(f"{indent}{label}: " + ", ".join(str(item) for item in value))
        else:
            lines.append(f"{indent}{label}: {format_value(key, value)}")
    return lines


def render_context(context: dict, *, preamble: str = "") -> str:
    """The verified figures as a readable block.

    This is what the user sees when no model text can be trusted, so it has to
    stand on its own — it is the answer, not an error page.
    """
    if not context:
        return (preamble or "There is nothing to report yet.").strip()

    body = "\n".join(_lines(context))
    return f"{preamble}\n{body}".strip() if preamble else body
