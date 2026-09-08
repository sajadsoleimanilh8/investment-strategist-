"""Education content (spec section 17). Static, curated, NOT AI-generated so
explanations stay accurate. The AI may rephrase a topic on request.

Twelve topics, each with a plain-English explanation, a concrete example with
round numbers, the mistake beginners actually make, and a one-question quiz.
Written for a 16-25 year old with no finance background: no jargon without a
translation, no formula the reader cannot do in their head.

Example amounts are written with the default `$` symbol. They are illustrative
figures inside prose, not computed values — anything the engine calculates is
rendered through `app.bot.formatting.money`.
"""
from __future__ import annotations

#: Every topic must carry all of these — `list_topics` is what /learn renders.
REQUIRED_FIELDS = ("title", "explanation", "example", "common_mistake", "quiz")
QUIZ_FIELDS = ("question", "options", "answer_idx")

# key -> {title, explanation, example, common_mistake,
#         quiz: {question, options, answer_idx}}
TOPICS: dict[str, dict] = {
    "budgeting": {
        "title": "Budgeting",
        "explanation": (
            "Budgeting means deciding where your money goes before you spend it. You split "
            "your monthly income across a few categories — housing, food, transport, savings "
            "— and then try to stay inside those limits. A budget isn't a restriction; it's a "
            "plan."
        ),
        "example": (
            "Income $30,000. Using the 50/30/20 guideline: $15,000 for needs, $9,000 for "
            "wants, $6,000 for savings. If your rent is heavier than that, change the shares "
            "yourself — these numbers are a guideline, not a rule."
        ),
        "common_mistake": (
            "Writing an ideal budget you never actually follow. A budget far from what you "
            "really spent last month gets abandoned within two weeks."
        ),
        "quiz": {
            "question": "What is the best starting point for building a budget?",
            "options": [
                "Copying someone else's budget",
                "Looking at what you actually spent over the past few months",
                "Cutting out all fun spending entirely",
            ],
            "answer_idx": 1,
        },
    },
    "emergency_fund": {
        "title": "Emergency Fund",
        "explanation": (
            "An emergency fund is money set aside only for the unexpected: losing your job, a "
            "broken phone, a medical bill. The usual target is three to six times one month of "
            "essential expenses, and it has to be quick to reach."
        ),
        "example": (
            "If your essential expenses are $16,000 a month, a three-month fund is $48,000. "
            "Saving $4,000 a month, you get there in a year."
        ),
        "common_mistake": (
            "Spending the emergency fund on something that was merely a good deal. A discount "
            "on a new phone is not an emergency."
        ),
        "quiz": {
            "question": "How much of your essential expenses should an emergency fund usually cover?",
            "options": ["One week", "Three to six months", "Five years"],
            "answer_idx": 1,
        },
    },
    "savings_rate": {
        "title": "Savings Rate",
        "explanation": (
            "Your savings rate is what share of your income you keep, not how much money you "
            "have. The formula is simple: monthly savings divided by monthly income. It is the "
            "best number for comparing one of your own months against another."
        ),
        "example": (
            "Income $30,000, spending $18,000, debt payment $1,500. That leaves $10,500 saved "
            "— a savings rate of 35%."
        ),
        "common_mistake": (
            "Comparing your savings amount with other people instead of comparing your "
            "percentage with your own previous month."
        ),
        "quiz": {
            "question": "How is the savings rate calculated?",
            "options": [
                "Monthly savings divided by monthly income",
                "Total account balance divided by your age",
                "Income minus rent",
            ],
            "answer_idx": 0,
        },
    },
    "inflation": {
        "title": "Inflation",
        "explanation": (
            "Inflation means the same amount of money buys less as time passes. Money sitting "
            "still without growing loses a little purchasing power every year, even when the "
            "number itself never changes."
        ),
        "example": (
            "If a bag costs $10,000 this year and inflation is 40%, the same bag costs about "
            "$14,000 next year — your $10,000 is no longer enough to buy it."
        ),
        "common_mistake": (
            "Watching only the number in your account and forgetting what that number can "
            "actually buy."
        ),
        "quiz": {
            "question": "What does inflation do to money that is sitting idle?",
            "options": [
                "It reduces its purchasing power",
                "It increases the number automatically",
                "It has no effect at all",
            ],
            "answer_idx": 0,
        },
    },
    "risk": {
        "title": "Risk",
        "explanation": (
            "Risk means the outcome is not certain and you could lose part of your money. More "
            "risk usually comes with a higher possible return — but 'possible' is the important "
            "word: nothing is guaranteed."
        ),
        "example": (
            "A bank deposit pays a small but near-certain return. A volatile asset might rise "
            "50% in a year or fall 50%."
        ),
        "common_mistake": (
            "Taking on more risk than you can handle just because past returns looked good."
        ),
        "quiz": {
            "question": "Higher risk usually means what?",
            "options": [
                "A larger guaranteed profit",
                "A wider range of possible outcomes, both up and down",
                "More safety",
            ],
            "answer_idx": 1,
        },
    },
    "volatility": {
        "title": "Volatility",
        "explanation": (
            "Volatility is how much an asset's price jumps around. High volatility isn't "
            "automatically bad, but it means the value of your money can change very fast in "
            "the short term."
        ),
        "example": (
            "Asset A moves between 98 and 102 over a month; asset B moves between 70 and 130 in "
            "the same month. Asset B is far more volatile."
        ),
        "common_mistake": (
            "Selling in fear at the bottom of an ordinary swing, turning a temporary dip into a "
            "real loss."
        ),
        "quiz": {
            "question": "What does volatility measure?",
            "options": [
                "How much the price moves up and down",
                "That the price will definitely go up",
                "The guaranteed annual return",
            ],
            "answer_idx": 0,
        },
    },
    "diversification": {
        "title": "Diversification",
        "explanation": (
            "Diversification means not putting all your money in one place. When your holdings "
            "are different from each other, one of them going badly does not wipe out "
            "everything you have."
        ),
        "example": (
            "If all your savings are in one asset and it drops 40%, you have lost 40% of "
            "everything. If that asset is a quarter of your holdings, the effect is about 10%."
        ),
        "common_mistake": (
            "Buying several things that look different but all rise and fall together — that "
            "is not real diversification."
        ),
        "quiz": {
            "question": "What is the main purpose of diversification?",
            "options": [
                "Guaranteeing a profit",
                "Reducing the effect of one bad event on everything you own",
                "Making money grow faster",
            ],
            "answer_idx": 1,
        },
    },
    "compound_growth": {
        "title": "Compound Growth",
        "explanation": (
            "Compound growth means the returns you earn start earning returns of their own. In "
            "the first years the difference looks small, but the longer it runs, the bigger the "
            "effect gets."
        ),
        "example": (
            "$10,000 growing 20% a year: $12,000 after one year, $14,400 after two, about "
            "$17,300 after three. Each year's growth is larger than the last."
        ),
        "common_mistake": (
            "Withdrawing early and often — that breaks the chain the growth depends on."
        ),
        "quiz": {
            "question": "What makes compound growth powerful?",
            "options": ["Time", "Luck", "A very large starting amount"],
            "answer_idx": 0,
        },
    },
    "time_horizon": {
        "title": "Time Horizon",
        "explanation": (
            "Your time horizon is how long you have before you need the money. Money you need "
            "next year and money you need in ten years should not be kept the same way."
        ),
        "example": (
            "Rent for the next three months belongs somewhere safe and instantly reachable; "
            "money set aside for ten years from now can tolerate more ups and downs."
        ),
        "common_mistake": (
            "Putting short-term money somewhere volatile and being forced to sell at the worst "
            "possible time."
        ),
        "quiz": {
            "question": "Where is money you need within six months best kept?",
            "options": [
                "Somewhere safe and quick to access",
                "In the most volatile asset available",
                "Somewhere locked up for five years",
            ],
            "answer_idx": 0,
        },
    },
    "debt": {
        "title": "Debt",
        "explanation": (
            "Debt means using your future money today. Not all debt is bad, but every payment "
            "has already spent part of the income of the months ahead. The number that matters "
            "is what share of your monthly income the payments take."
        ),
        "example": (
            "Income $30,000 with a $1,500 monthly payment is a debt burden of 5% — light. If "
            "payments reach $12,000, then 40% of your income is spent before it arrives."
        ),
        "common_mistake": (
            "Paying only the minimum on each instalment: the principal barely moves and the "
            "repayment drags on for years."
        ),
        "quiz": {
            "question": "How is debt burden usually measured?",
            "options": [
                "Monthly payment as a share of monthly income",
                "The number of loans you have",
                "Your age",
            ],
            "answer_idx": 0,
        },
    },
    "opportunity_cost": {
        "title": "Opportunity Cost",
        "explanation": (
            "Opportunity cost is what you give up by choosing one option over another. Every "
            "unit of money you spend is money that cannot be working somewhere else."
        ),
        "example": (
            "You spend $20,000 on a trip. The opportunity cost is that the same $20,000 was a "
            "third of your $60,000 laptop goal."
        ),
        "common_mistake": (
            "Seeing the price of a purchase but not seeing which goal that money pushes back."
        ),
        "quiz": {
            "question": "What is the opportunity cost of a purchase?",
            "options": [
                "The tax on it",
                "The best thing you could have done with the same money",
                "Its price next year",
            ],
            "answer_idx": 1,
        },
    },
    "investment_basics": {
        "title": "Investment Basics",
        "explanation": (
            "Investing means putting money somewhere it has a chance to grow over time. The "
            "sensible order is: budget first, then an emergency fund, then heavy debt, and only "
            "then investing — with money you do not need soon."
        ),
        "example": (
            "Someone with $45,000 saved but a thin emergency fund is better off filling the "
            "fund first and investing after that."
        ),
        "common_mistake": (
            "Investing money you need next month, or investing only because someone else "
            "recommended it."
        ),
        "quiz": {
            "question": "What should usually be in place before you start investing?",
            "options": [
                "An emergency fund",
                "A new phone",
                "A market price prediction",
            ],
            "answer_idx": 0,
        },
    },
}


def list_topics() -> list[dict]:
    return [{"key": k, **v} for k, v in TOPICS.items()]


def get_topic(key: str) -> dict | None:
    t = TOPICS.get(key)
    return {"key": key, **t} if t else None
