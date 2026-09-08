"""Number / currency formatting helpers for bot copy.

Money is always rendered through `settings.currency_symbol` — no currency is
hard-coded anywhere in the codebase.
"""
from __future__ import annotations

from app.core.config import settings


def number(value: float, *, decimals: int = 0) -> str:
    """Plain thousands-separated number: 1234567 -> "1,234,567"."""
    return f"{value:,.{decimals}f}"


def money(value: float) -> str:
    """Full amount with the configured symbol: 1234567 -> "$1,234,567"."""
    return f"{settings.currency_symbol}{number(value)}"


def compact(value: float) -> str:
    """Short money for buttons and cards: 1_200_000 -> "$1.2M", 450_000 -> "$450K"."""
    symbol = settings.currency_symbol
    magnitude = abs(value)
    sign = "-" if value < 0 else ""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if magnitude >= threshold:
            scaled = magnitude / threshold
            trimmed = f"{scaled:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{symbol}{trimmed}{suffix}"
    return f"{sign}{symbol}{magnitude:,.0f}"


def percent(fraction: float, *, decimals: int = 1) -> str:
    """0.35 -> "35.0%"."""
    return f"{fraction * 100:.{decimals}f}%"
