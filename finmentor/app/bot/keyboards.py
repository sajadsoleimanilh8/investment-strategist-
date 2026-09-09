"""Inline keyboards (spec section 19). Users tap, they don't type commands.

Every `callback_data` follows one convention:

    "<area>:<action>"            e.g. "menu:health"
    "<area>:<action>:<arg>"      e.g. "learn:topic:risk", "wl:add:BTC"

`parse_cb` is the only place that convention is decoded, and the callback
router in `handlers.py` is the only caller — so adding a button is adding a
branch there, not inventing a new string format. Telegram caps callback_data at
64 bytes, which is why arguments are keys and symbols, never labels.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.education_engine import list_topics

CB_SEPARATOR = ":"
#: Telegram's hard limit on callback_data.
MAX_CALLBACK_BYTES = 64
#: Topics per page in the /learn menu, two to a row.
TOPICS_PER_PAGE = 6


def cb(area: str, action: str, arg: str | None = None) -> str:
    data = CB_SEPARATOR.join([area, action] + ([arg] if arg is not None else []))
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError(f"callback_data too long for Telegram: {data!r}")
    return data


def parse_cb(data: str) -> tuple[str, str, str | None]:
    """"learn:topic:risk" -> ("learn", "topic", "risk"). Never raises on junk.

    An unknown or malformed payload comes back as ("", "", None) so the router
    can shrug it off — old buttons survive a redeploy.
    """
    parts = (data or "").split(CB_SEPARATOR, 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return "", "", None
    return parts[0], parts[1], parts[2] if len(parts) == 3 else None


def _back() -> InlineKeyboardButton:
    return InlineKeyboardButton("◀️ Back", callback_data=cb("menu", "home"))


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_back()]])


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 My Finances", callback_data=cb("menu", "finances")),
         InlineKeyboardButton("❤️ Financial Health", callback_data=cb("menu", "health"))],
        [InlineKeyboardButton("🎯 Goals", callback_data=cb("menu", "goals")),
         InlineKeyboardButton("🔮 Simulate", callback_data=cb("menu", "simulate"))],
        [InlineKeyboardButton("📈 Market", callback_data=cb("menu", "market")),
         InlineKeyboardButton("🧠 Learn", callback_data=cb("menu", "learn"))],
        [InlineKeyboardButton("💬 Ask AI", callback_data=cb("menu", "ask"))],
    ]
    return InlineKeyboardMarkup(rows)


def onboarding_prompt() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Set up my profile", callback_data=cb("onboard", "start"))]]
    )


def goals_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add a goal", callback_data=cb("goal", "add"))],
        [_back()],
    ])


def goal_priority_picker() -> InlineKeyboardMarkup:
    """1 is highest — the health score weighs a priority-1 goal five times."""
    labels = {1: "1 · highest", 2: "2", 3: "3 · normal", 4: "4", 5: "5 · lowest"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(labels[level], callback_data=cb("goal", "priority", str(level)))
         for level in (1, 2, 3)],
        [InlineKeyboardButton(labels[level], callback_data=cb("goal", "priority", str(level)))
         for level in (4, 5)],
    ])


def simulate_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔮 What-if", callback_data=cb("sim", "whatif"))],
        [InlineKeyboardButton("🛒 Evaluate a purchase", callback_data=cb("sim", "purchase"))],
        [InlineKeyboardButton("⏳ Time machine", callback_data=cb("sim", "timemachine"))],
        [_back()],
    ])


def market_menu(symbols: list[str], watched: set[str]) -> InlineKeyboardMarkup:
    """One toggle row per known asset: add if unwatched, remove if watched."""
    rows = []
    for symbol in symbols:
        if symbol in watched:
            rows.append([InlineKeyboardButton(
                f"➖ Remove {symbol}", callback_data=cb("wl", "remove", symbol))])
        else:
            rows.append([InlineKeyboardButton(
                f"➕ Add {symbol}", callback_data=cb("wl", "add", symbol))])
    rows.append([_back()])
    return InlineKeyboardMarkup(rows)


def learn_menu(page: int = 0) -> InlineKeyboardMarkup:
    """The 12 topics, two per row, six per page."""
    topics = list_topics()
    pages = max(1, -(-len(topics) // TOPICS_PER_PAGE))
    page = max(0, min(page, pages - 1))
    window = topics[page * TOPICS_PER_PAGE:(page + 1) * TOPICS_PER_PAGE]

    rows = [
        [InlineKeyboardButton(topic["title"], callback_data=cb("learn", "topic", topic["key"]))
         for topic in window[index:index + 2]]
        for index in range(0, len(window), 2)
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=cb("learn", "page", str(page - 1))))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=cb("learn", "page", str(page + 1))))
    if nav:
        rows.append(nav)
    rows.append([_back()])
    return InlineKeyboardMarkup(rows)


def topic_menu(topic_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❓ Quiz me", callback_data=cb("learn", "quiz", topic_key))],
        [InlineKeyboardButton("◀️ Topics", callback_data=cb("learn", "page", "0"))],
    ])


def quiz_options(topic_key: str, topic: dict) -> InlineKeyboardMarkup:
    """Options are answered by index — the text would blow the 64-byte budget."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(option, callback_data=cb("quiz", topic_key, str(index)))]
        for index, option in enumerate(topic["quiz"]["options"])
    ] + [[InlineKeyboardButton("◀️ Topics", callback_data=cb("learn", "page", "0"))]])


def confirm_cancel(area: str, action: str, arg: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirm", callback_data=cb(area, action, arg)),
        InlineKeyboardButton("✖️ Cancel", callback_data=cb(area, "cancel")),
    ]])


def skip_keyboard(area: str = "onboard") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Skip", callback_data=cb(area, "skip"))]]
    )


def income_type_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Fixed", callback_data=cb("onboard", "income_type", "fixed")),
        InlineKeyboardButton("Variable", callback_data=cb("onboard", "income_type", "variable")),
        InlineKeyboardButton("Mixed", callback_data=cb("onboard", "income_type", "mixed")),
    ]])


def risk_question_options(question_idx: int, options: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            option, callback_data=cb("risk", str(question_idx), str(index)))]
        for index, option in enumerate(options)
    ])


def redo_profile() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Redo my profile", callback_data=cb("onboard", "start"))],
        [_back()],
    ])
