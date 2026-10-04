"""All user-facing strings (spec section 31). Plain, friendly English.

Copy lives here so it can be reviewed as copy. Anything with a number in it is
built in `views.py` from engine output instead — a string in this file must
never carry a figure.
"""
from __future__ import annotations

WELCOME = (
    "Hi! I'm FinMentor — your financial twin. 👋\n"
    "Understand your money, simulate your future.\n\n"
    "Tap a button below or send /help."
)

MENU_PROMPT = "What would you like to do?"
DISCLAIMER_MARKET = (
    "⚠️ This describes recent or historical market behaviour — not a prediction "
    "or personalised investment recommendation."
)
NOT_ONBOARDED = (
    "I need a few numbers before I can help. It takes about two minutes and "
    "nothing leaves your account."
)
ALREADY_ONBOARDED = "You're all set up. Here's your menu."
SOMETHING_WENT_WRONG = "Something went wrong — try again."
CALCULATING = "Calculating…"
THINKING = "Thinking…"
CANCELLED = "Cancelled. Nothing was saved."

# --- onboarding ---------------------------------------------------------

ONBOARD_INTRO = (
    "Let's build your financial twin. I'll ask a few short questions — send "
    "\"skip\" or tap Skip on anything you'd rather not answer.\n\n"
    "You can stop at any time with /cancel."
)
ASK_INCOME = "How much do you earn in a month? (e.g. 30m, 30,000,000, 4500)"
ASK_INCOME_TYPE = "Is that income fixed, variable, or a mix?"
ASK_EXPENSE = "How much do you spend on *{category}* in a month?"
ASK_SAVINGS = "How much do you have saved in total right now?"
ASK_DEBT = "How much do you owe in total? (Send 0 if none.)"
ASK_DEBT_PAYMENT = "How much do you pay towards that debt each month?"
ASK_EMERGENCY = "How much of your savings is set aside for emergencies?"
ASK_GOAL_NAME = "What's one thing you're saving for? (e.g. \"Laptop\")"
ASK_GOAL_TARGET = "How much does *{name}* cost in total?"
ASK_GOAL_CURRENT = "How much have you put aside for it already?"
ASK_GOAL_DEADLINE = "When do you want it by? Send a date as YYYY-MM-DD, or skip."
ASK_GOAL_PRIORITY = "How important is this goal to you?"
RISK_INTRO = (
    "Last part — three quick questions so I know how to talk to you about "
    "risk. There are no wrong answers, and this is not financial advice."
)
ONBOARD_DONE = "That's everything. Here's your financial twin:"

NOT_A_NUMBER = "I couldn't read a number there. Try something like 30m or 4,500."
NEGATIVE_NUMBER = "That can't be negative — try again."
BAD_DATE = "I need a date like 2027-06-01, or tap Skip."
EMPTY_NAME = "Give the goal a short name, like \"Laptop\" or \"Emergency fund\"."

# --- free-text prompts --------------------------------------------------

ASK_PROMPT = (
    "Ask me anything about your money — \"why is my score what it is?\", "
    "\"what if I save 2m more a month?\", \"what does diversification mean?\""
)
WHATIF_PROMPT = (
    "Describe the change. For example: \"what if I save 5m more each month\" "
    "or \"what if my rent goes up 20%\"."
)
PURCHASE_PROMPT = "How much does it cost? I'll show you what it does to your numbers."
UNREADABLE_AMOUNT = "I couldn't read an amount there. Try something like 60m."
NO_GOALS_YET = "You have no goals yet — add one from the Goals menu."

# --- account linking ----------------------------------------------------
#
# A code is a credential, so none of this copy ever repeats one back: a
# refusal says the code was refused, never which code, because the reply sits
# in a chat log that outlives the ten minutes the code was good for.

LINK_HOW = (
    "To connect this chat to your FinMentor account on the web:\n\n"
    "1. Sign in at the website.\n"
    "2. Open Profile, then Connect Telegram.\n"
    "3. Send me the code you see, like this: /link ABCD-EFGH-JKMN\n\n"
    "The code is good for a few minutes and works once."
)
LINK_DONE = "Connected. This chat and your web account are now the same account."
LINK_ALREADY_YOURS = "This chat is already connected to that account. Nothing to do."


# --- the command list ---------------------------------------------------
#
# One table, three consumers: Telegram's own command menu (registered on
# startup, so typing "/" shows something), `views.help_view`, and a test that
# checks it against the handler table in `bot/main.py`.
#
# It used to be a hand-written block of prose in `help_view` and nothing
# registered with Telegram at all, so the bot had twelve commands and
# advertised none of them. Two lists would have drifted the first time one was
# added; this one cannot.
#
# Descriptions are lower case and under about sixty characters, which is what
# the Telegram client shows without truncating.

COMMAND_HELP: tuple[tuple[str, str], ...] = (
    ("start", "set up, or reopen the menu"),
    ("help", "what I can do"),
    ("profile", "your finances as I have them"),
    ("health", "your health score and financial DNA"),
    ("budget", "a suggested split of your income"),
    ("goals", "track and add goals"),
    ("simulate", "what-ifs, purchases, the time machine"),
    ("market", "your watchlist, ranked"),
    ("watchlist", "add or remove symbols"),
    ("learn", "twelve short lessons"),
    ("ask", "ask me anything about your numbers"),
    ("link", "connect this chat to your web account"),
)
