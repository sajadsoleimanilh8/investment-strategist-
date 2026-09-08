"""Inline keyboards (spec section 19). Users tap, they don't type commands."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 My Finances", callback_data="finances"),
         InlineKeyboardButton("❤️ Financial Health", callback_data="health")],
        [InlineKeyboardButton("🎯 Goals", callback_data="goals"),
         InlineKeyboardButton("🔮 Simulate", callback_data="simulate")],
        [InlineKeyboardButton("📈 Market", callback_data="market"),
         InlineKeyboardButton("🧠 Learn", callback_data="learn")],
        [InlineKeyboardButton("💬 Ask AI", callback_data="ask")],
    ]
    return InlineKeyboardMarkup(rows)
