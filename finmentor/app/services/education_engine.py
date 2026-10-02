"""Education content (spec section 17). Static, curated, NOT AI-generated so
explanations stay accurate. The AI may rephrase a topic on request.

Twelve topics, each with a plain-English explanation, a concrete example with
round numbers, the mistake beginners actually make, and a three-question quiz.

Each question carries its own `why`. The result used to return the topic's
`common_mistake` whatever the user got wrong, which is a sentence about the
topic rather than about the question they just missed.
Written for a 16-25 year old with no finance background: no jargon without a
translation, no formula the reader cannot do in their head.

Example amounts are written with the default `$` symbol. They are illustrative
figures inside prose, not computed values — anything the engine calculates is
rendered through `app.bot.formatting.money`.
"""
from __future__ import annotations

#: Every topic must carry all of these — `list_topics` is what /learn renders.
REQUIRED_FIELDS = ("title", "explanation", "example", "common_mistake", "questions")
QUIZ_FIELDS = ("question", "options", "answer_idx", "why")

#: Every topic has exactly this many. A fixed count is what lets a score be a
#: percentage that means the same thing on every topic, and what stops the
#: quiz quietly becoming one question again on a topic somebody edits.
QUESTIONS_PER_TOPIC = 3

# key -> {title, explanation, example, common_mistake,
#         questions: [{question, options, answer_idx, why}]}
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
        "questions": [
            {
                "question": "What is the best starting point for building a budget?",
                "options": [
                    "Copying someone else's budget",
                    "Looking at what you actually spent over the past few months",
                    "Cutting out all fun spending entirely",
                ],
                "answer_idx": 1,
                "why": (
                    "A budget built from what you actually spent is one you can keep. "
                    "One built from what you wish you spent gets abandoned."
                ),
            },
            {
                "question": (
                    "You set a food budget of $4,000 and spent $6,000. What is the most "
                    "useful next step?"
                ),
                "options": [
                    "Ignore it, one month does not matter",
                    "Look at why it went over, then change the habit or change the number",
                    "Set next month's food budget to $2,000 to make up for it",
                ],
                "answer_idx": 1,
                "why": (
                    "A budget is a plan you revise, not a punishment you serve. "
                    "Overcorrecting is the fastest way to abandon it."
                ),
            },
            {
                "question": "What does the 50/30/20 split refer to?",
                "options": [
                    "Needs, wants, savings",
                    "Housing, food, transport",
                    "Stocks, bonds, cash",
                ],
                "answer_idx": 0,
                "why": (
                    "50% needs, 30% wants, 20% savings. It is a starting guideline "
                    "rather than a rule, and heavy rent is a normal reason to change "
                    "the shares."
                ),
            },
        ],
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
        "questions": [
            {
                "question": (
                    "How much of your essential expenses should an emergency fund usually "
                    "cover?"
                ),
                "options": [
                    "One week",
                    "Three to six months",
                    "Five years",
                ],
                "answer_idx": 1,
                "why": (
                    "Three to six months of essential expenses is the usual target. It "
                    "covers the gap while you sort things out, not your whole "
                    "lifestyle."
                ),
            },
            {
                "question": "Where should an emergency fund be kept?",
                "options": [
                    "Somewhere safe that you can reach within a day or two",
                    "In whatever has the highest expected return",
                    "Locked away for five years so you are not tempted",
                ],
                "answer_idx": 0,
                "why": (
                    "A fund you cannot reach during an emergency is not an emergency "
                    "fund. Safety and speed matter more than return for this money."
                ),
            },
            {
                "question": (
                    "Your essential expenses are $16,000 a month and you have $20,000 "
                    "saved. Roughly how long is your runway?"
                ),
                "options": [
                    "About six months",
                    "About five weeks",
                    "About a year",
                ],
                "answer_idx": 1,
                "why": (
                    "$20,000 divided by $16,000 a month is about 1.25 months, so a "
                    "little over five weeks. Runway uses essential spending, not total "
                    "spending."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "How is the savings rate calculated?",
                "options": [
                    "Monthly savings divided by monthly income",
                    "Total account balance divided by your age",
                    "Income minus rent",
                ],
                "answer_idx": 0,
                "why": (
                    "Savings divided by income, as a percentage. Using income minus "
                    "rent would call someone with cheap rent a great saver even if they "
                    "spent everything else."
                ),
            },
            {
                "question": (
                    "Your income rises from $30,000 to $40,000 and your savings stay at "
                    "$6,000. What happened to your savings rate?"
                ),
                "options": [
                    "It went up",
                    "It went down",
                    "It stayed the same",
                ],
                "answer_idx": 1,
                "why": (
                    "$6,000 of $30,000 is 20%. The same $6,000 of $40,000 is 15%. A "
                    "raise only improves the rate if some of it is saved."
                ),
            },
            {
                "question": "Which pair of people has the same savings rate?",
                "options": [
                    "One saving $500 of $2,000 and one saving $1,000 of $4,000",
                    "One saving $500 of $2,000 and one saving $500 of $4,000",
                    "One saving $1,000 of $2,000 and one saving $1,000 of $5,000",
                ],
                "answer_idx": 0,
                "why": (
                    "Both save a quarter of what they earn. The rate is a share, which "
                    "is what lets it compare people on different incomes fairly."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What does inflation do to money that is sitting idle?",
                "options": [
                    "It reduces its purchasing power",
                    "It increases the number automatically",
                    "It has no effect at all",
                ],
                "answer_idx": 0,
                "why": "The number in the account does not change. What it buys does.",
            },
            {
                "question": (
                    "Inflation is 10% a year and your savings earn 4%. What is happening "
                    "to your buying power?"
                ),
                "options": [
                    "It is growing by 4%",
                    "It is falling by roughly 6%",
                    "It is staying flat",
                ],
                "answer_idx": 1,
                "why": (
                    "Earning 4% while prices rise 10% leaves you about 6% behind. The "
                    "figure that matters is the return after inflation, not the return."
                ),
            },
            {
                "question": "Which of these best keeps its purchasing power over twenty years?",
                "options": [
                    "Cash kept at home",
                    "Something whose value tends to rise along with prices",
                    "A fixed amount of money promised to you in twenty years",
                ],
                "answer_idx": 1,
                "why": (
                    "Cash and a fixed future amount both lose purchasing power as "
                    "prices rise. Something that rises with prices roughly keeps pace."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "Higher risk usually means what?",
                "options": [
                    "A larger guaranteed profit",
                    "A wider range of possible outcomes, both up and down",
                    "More safety",
                ],
                "answer_idx": 1,
                "why": (
                    "Risk is the width of the range of outcomes. It is not a hidden "
                    "promise of a bigger prize."
                ),
            },
            {
                "question": (
                    "Two investments have the same expected return, and one swings far "
                    "more than the other. Which is riskier?"
                ),
                "options": [
                    "The one that swings more",
                    "Neither, the expected return is the same",
                    "The one that swings less, because it has less room to grow",
                ],
                "answer_idx": 0,
                "why": (
                    "Same expected outcome, wider range of actual outcomes. Risk is the "
                    "spread around the expectation."
                ),
            },
            {
                "question": 'What does "higher risk, higher return" actually mean?',
                "options": [
                    "You will earn more if you wait long enough",
                    "You are paid for accepting a wider range of outcomes, including losses",
                    "Risky assets always beat safe ones eventually",
                ],
                "answer_idx": 1,
                "why": (
                    "It is a price, not a promise. The higher expected return is "
                    "payment for bearing outcomes you may not like."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What does volatility measure?",
                "options": [
                    "How much the price moves up and down",
                    "That the price will definitely go up",
                    "The guaranteed annual return",
                ],
                "answer_idx": 0,
                "why": (
                    "Volatility measures movement, in both directions. It says nothing "
                    "about which way."
                ),
            },
            {
                "question": "An asset fell 50% and then rose 50%. Where is it now?",
                "options": [
                    "Back where it started",
                    "25% below where it started",
                    "25% above where it started",
                ],
                "answer_idx": 1,
                "why": (
                    "100 falls to 50, then rises by half of 50 to 75. Percentage moves "
                    "are not symmetric, which is why big swings cost more than they "
                    "look."
                ),
            },
            {
                "question": "A fund reports high volatility. What have you learned?",
                "options": [
                    "That it is a bad investment",
                    "That its price moves a lot, which may suit a long horizon and not a short one",
                    "That it will lose money",
                ],
                "answer_idx": 1,
                "why": (
                    "Volatility is a fact about movement, not a verdict. Whether it "
                    "suits you depends on when you need the money."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What is the main purpose of diversification?",
                "options": [
                    "Guaranteeing a profit",
                    "Reducing the effect of one bad event on everything you own",
                    "Making money grow faster",
                ],
                "answer_idx": 1,
                "why": (
                    "Diversification spreads the damage of any single bad event. It "
                    "does not remove risk."
                ),
            },
            {
                "question": (
                    "You own shares in five technology companies. How diversified are "
                    "you?"
                ),
                "options": [
                    "Well diversified, those are five different companies",
                    "Less than it looks, because they tend to fall together",
                    "Fully diversified, five is the usual target",
                ],
                "answer_idx": 1,
                "why": (
                    "Diversification is about owning things that do not move together. "
                    "Five companies in one industry share most of the same risks."
                ),
            },
            {
                "question": "What does diversification not protect against?",
                "options": [
                    "A whole market falling at once",
                    "One company failing",
                    "One industry having a bad year",
                ],
                "answer_idx": 0,
                "why": (
                    "Spreading out helps when the parts move differently. When "
                    "everything falls together, spreading out inside it does not help."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What makes compound growth powerful?",
                "options": [
                    "Time",
                    "Luck",
                    "A very large starting amount",
                ],
                "answer_idx": 0,
                "why": (
                    "Each period's growth is earned on the previous period's total, so "
                    "the effect accelerates the longer it runs."
                ),
            },
            {
                "question": "At roughly 7% a year, about how long does money take to double?",
                "options": [
                    "About 3 years",
                    "About 10 years",
                    "About 25 years",
                ],
                "answer_idx": 1,
                "why": (
                    "Divide 72 by the rate for a rough estimate: 72 divided by 7 is "
                    "about 10 years. It is an approximation, not a figure to plan to "
                    "the month with."
                ),
            },
            {
                "question": "Why does starting earlier matter so much?",
                "options": [
                    "Early money has more periods to compound in",
                    "Returns are higher when you are young",
                    "It does not, only the total amount saved matters",
                ],
                "answer_idx": 0,
                "why": (
                    "The same amount left for longer passes through more doublings. "
                    "Time is the one input you cannot buy back later."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "Where is money you need within six months best kept?",
                "options": [
                    "Somewhere safe and quick to access",
                    "In the most volatile asset available",
                    "Somewhere locked up for five years",
                ],
                "answer_idx": 0,
                "why": (
                    "A short horizon means you may have to sell at a bad moment, so "
                    "safety and access matter more than return."
                ),
            },
            {
                "question": (
                    "You are saving for something you need in eight months. What matters "
                    "most?"
                ),
                "options": [
                    "The highest expected return",
                    "That the money is still there and reachable when you need it",
                    "Spreading it across as many assets as possible",
                ],
                "answer_idx": 1,
                "why": (
                    "With eight months there is no time to recover from a fall, so "
                    "being sure of the amount beats the chance of a bigger one."
                ),
            },
            {
                "question": "Why can a long horizon carry more volatility?",
                "options": [
                    "Volatile assets become safe over time",
                    "There is time to recover from a bad stretch before the money is needed",
                    "Long horizons have higher returns guaranteed",
                ],
                "answer_idx": 1,
                "why": (
                    "Time does not remove the risk. It removes the need to sell at the "
                    "worst moment."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "How is debt burden usually measured?",
                "options": [
                    "Monthly payment as a share of monthly income",
                    "The number of loans you have",
                    "Your age",
                ],
                "answer_idx": 0,
                "why": (
                    "What matters is what the payment takes out of each month's income, "
                    "not how many separate loans there are."
                ),
            },
            {
                "question": (
                    "You have one debt at 24% and one at 6%, and spare money for one of "
                    "them. Which first?"
                ),
                "options": [
                    "The 24% one",
                    "The 6% one, to clear it off faster",
                    "Split it evenly, it makes no difference",
                ],
                "answer_idx": 0,
                "why": (
                    "Paying down the expensive debt first saves the most interest. The "
                    "rate is what the debt costs you to keep."
                ),
            },
            {
                "question": (
                    "Your income is $30,000 a month and your debt payments are $9,000. "
                    "What is your debt burden?"
                ),
                "options": [
                    "9%",
                    "30%",
                    "It depends on the interest rate",
                ],
                "answer_idx": 1,
                "why": (
                    "$9,000 of $30,000 is 30%. Burden is the share of income the "
                    "payments take, which is why it compares across incomes."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What is the opportunity cost of a purchase?",
                "options": [
                    "The tax on it",
                    "The best thing you could have done with the same money",
                    "Its price next year",
                ],
                "answer_idx": 1,
                "why": (
                    "The cost of a choice is the best alternative you gave up, not the "
                    "price on the label."
                ),
            },
            {
                "question": "You spend $5,000 on a phone. What is the opportunity cost?",
                "options": [
                    "$5,000",
                    "Whatever the best other use of that $5,000 would have been",
                    "Nothing, because you wanted the phone",
                ],
                "answer_idx": 1,
                "why": (
                    "The $5,000 is the price. The opportunity cost is the next best "
                    "thing that money could have done, such as a few weeks of emergency "
                    "fund."
                ),
            },
            {
                "question": "Why does opportunity cost matter even when you can afford something?",
                "options": [
                    "Because money spent here is money not available for anything else",
                    "It does not, affordability is the only question",
                    "Because prices always rise",
                ],
                "answer_idx": 0,
                "why": (
                    "Affordability asks whether you have the money. Opportunity cost "
                    "asks whether this is the best use of it."
                ),
            },
        ],
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
        "questions": [
            {
                "question": "What should usually be in place before you start investing?",
                "options": [
                    "An emergency fund",
                    "A new phone",
                    "A market price prediction",
                ],
                "answer_idx": 0,
                "why": (
                    "Investing before you have a buffer means a surprise bill forces "
                    "you to sell at whatever price the market offers that day."
                ),
            },
            {
                "question": "What does owning a share in a company mean?",
                "options": [
                    "The company owes you a fixed payment",
                    "You own a small part of the business and its future results",
                    "Your money is guaranteed by the company",
                ],
                "answer_idx": 1,
                "why": (
                    "A share is ownership, not a loan. Its value follows how the "
                    "business does, which is why it can fall as well as rise."
                ),
            },
            {
                "question": "You cannot predict the market. What can you control?",
                "options": [
                    "How much you save, how long you leave it, and what you pay in fees",
                    "Next year's return",
                    "When the next fall happens",
                ],
                "answer_idx": 0,
                "why": (
                    "The inputs you choose are the amount, the time and the cost. The "
                    "return is not one of them."
                ),
            },
        ],
    },
}


def list_topics() -> list[dict]:
    return [{"key": k, **v} for k, v in TOPICS.items()]


def get_topic(key: str) -> dict | None:
    t = TOPICS.get(key)
    return {"key": key, **t} if t else None


def score_quiz(topic: dict, answers: list[int]) -> tuple[int, list[bool]]:
    """`(percentage, per-question correctness)` for one topic's answers.

    Rounded to the nearest whole percent, which keeps it inside the 0..100
    the `education_progress.quiz_score` check constraint already enforces, so
    a richer quiz needs no migration. Three questions give 0, 33, 67 or 100.

    Raises `ValueError` when the answer count does not match the question
    count. A partial submission scored as if the missing answers were wrong
    would record a number the user never earned, and scoring only what was
    sent would make a one-answer submission worth 100%.
    """
    questions = topic["questions"]
    if len(answers) != len(questions):
        raise ValueError(
            f"expected {len(questions)} answers, got {len(answers)}"
        )

    marks = [
        answer == question["answer_idx"]
        for answer, question in zip(answers, questions)
    ]
    return round(sum(marks) / len(marks) * 100), marks
