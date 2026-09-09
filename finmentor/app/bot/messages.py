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
