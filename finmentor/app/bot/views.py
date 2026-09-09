"""Message bodies. Data in, string out — no Telegram, no database, no engine.

Everything here is a rendering of numbers someone else computed, which is why
it is pure: the whole file is unit-testable without a bot token or a session,
and a view can never quietly become the place a figure gets calculated.

Telegram messages, not essays: short blocks, one idea per line.
"""
from __future__ import annotations

from app.ai.safety import FINANCE_DISCLAIMER
from app.bot.formatting import compact, money, number, percent
from app.schemas.finance import FinancialTwinOut, GoalOut
from app.schemas.health import FinancialDNAOut, HealthScoreOut
from app.schemas.market import MARKET_DISCLAIMER, TrendReportOut
from app.schemas.simulation import DecisionOut, ScenarioComparison, SimulationOut

FINANCE_NOTE = f"⚠️ {FINANCE_DISCLAIMER}"
MARKET_NOTE = f"⚠️ {MARKET_DISCLAIMER}"

#: Component key -> the label a human recognises.
COMPONENT_LABELS = {
    "savings_rate": "Savings rate",
    "emergency_fund": "Emergency fund",
    "debt_load": "Debt load",
    "budget_stability": "Budget stability",
    "goal_progress": "Goal progress",
}

_BAR_FULL, _BAR_EMPTY, _BAR_WIDTH = "█", "░", 10


def _bar(points: float, max_points: float) -> str:
    filled = 0 if max_points <= 0 else round(_BAR_WIDTH * points / max_points)
    filled = max(0, min(_BAR_WIDTH, filled))
    return _BAR_FULL * filled + _BAR_EMPTY * (_BAR_WIDTH - filled)


def _join(*blocks: str) -> str:
    return "\n\n".join(block for block in blocks if block)


# --- health -------------------------------------------------------------

def health_view(twin: FinancialTwinOut, score: HealthScoreOut, dna: FinancialDNAOut) -> str:
    lines = [f"❤️ *Financial Health: {number(score.total, decimals=1)}/100*", ""]
    for component in score.components:
        label = COMPONENT_LABELS.get(component.name, component.name.replace("_", " ").title())
        lines.append(
            f"{_bar(component.points, component.max_points)}  {label} "
            f"{number(component.points, decimals=1)}/{number(component.max_points)}"
        )
        if component.detail:
            lines.append(f"    ↳ {component.detail}")

    summary = (
        f"Saving {percent(twin.savings_rate)} of income "
        f"({money(twin.monthly_savings)}/month), "
        f"{number(twin.emergency_months, decimals=1)} months of cover."
    )
    return _join("\n".join(lines), summary, dna_view(dna), FINANCE_NOTE)


def dna_view(dna: FinancialDNAOut) -> str:
    rows = [
        ("Saving discipline", dna.saving_discipline),
        ("Emergency readiness", dna.emergency_readiness),
        ("Debt management", dna.debt_management),
        ("Goal discipline", dna.goal_discipline),
        ("Budget stability", dna.budget_stability),
        ("Financial knowledge", dna.financial_knowledge),
    ]
    return "🧬 *Financial DNA*\n" + "\n".join(f"• {label}: {value}" for label, value in rows)


def profile_view(twin: FinancialTwinOut) -> str:
    categories = "\n".join(
        f"• {name.title()}: {money(amount)}"
        for name, amount in twin.expenses.model_dump().items() if amount
    ) or "• No expenses recorded yet."

    return _join(
        "💰 *Your Finances*",
        f"Income: {money(twin.income)}/month",
        f"Expenses: {money(twin.monthly_expenses)}/month\n{categories}",
        (
            f"Savings: {money(twin.current_savings)}\n"
            f"Emergency fund: {money(twin.emergency_fund)} "
            f"({number(twin.emergency_months, decimals=1)} months)\n"
            f"Debt: {money(twin.debt)} ({money(twin.monthly_debt_payment)}/month)"
        ),
        f"Risk profile: {twin.risk_profile.title()}",
    )


# --- budget -------------------------------------------------------------

def budget_view(plan) -> str:
    """`plan` is a `services.budget_engine.BudgetPlan`."""
    shares = plan.split
    return _join(
        f"📊 *Suggested Budget* — {money(plan.income)}/month",
        (
            f"• Needs ({percent(shares['needs'], decimals=0)}): {money(plan.needs)}\n"
            f"• Wants ({percent(shares['wants'], decimals=0)}): {money(plan.wants)}\n"
            f"• Savings ({percent(shares['savings'], decimals=0)}): {money(plan.savings)}"
        ),
        f"That is {money(plan.annual_savings)} saved over a year.",
        "This split is a guideline, not a rule — if your rent is heavier than "
        "that, move the shares yourself.",
        FINANCE_NOTE,
    )


# --- goals --------------------------------------------------------------

def _goal_line(goal: GoalOut) -> str:
    eta = goal.estimated_completion.isoformat() if goal.estimated_completion else "no date yet"
    return (
        f"🎯 *{goal.name}* — priority {goal.priority}\n"
        f"{_bar(goal.progress_pct, 100)}  {number(goal.progress_pct, decimals=1)}%\n"
        f"{compact(goal.current_amount)} of {compact(goal.target_amount)} · ETA {eta}"
    )


def goals_view(goals: list[GoalOut]) -> str:
    if not goals:
        return _join(
            "🎯 *Your Goals*",
            "You have not set a goal yet. Add one and I will track the date you "
            "reach it.",
        )
    return _join("🎯 *Your Goals*", "\n\n".join(_goal_line(goal) for goal in goals), FINANCE_NOTE)


def goal_added_view(goal: GoalOut) -> str:
    return _join(f"Added *{goal.name}*.", _goal_line(goal), FINANCE_NOTE)


# --- simulation ---------------------------------------------------------

def _scenario_block(title: str, scenario: ScenarioComparison) -> str:
    lines = [
        f"*{title}*",
        f"• Saving {money(scenario.monthly_savings)}/month",
        f"• Projected savings: {money(scenario.projected_savings_end)}",
        f"• Emergency cover: {number(scenario.emergency_months, decimals=1)} months",
        f"• Health score: {number(scenario.health_score, decimals=1)}/100",
    ]
    if scenario.goal_completion_pct is not None:
        eta = scenario.estimated_goal_date or "no date yet"
        lines.append(
            f"• Goal: {number(scenario.goal_completion_pct, decimals=1)}% · reaches it {eta}"
        )
    return "\n".join(lines)


def _delta_line(label: str, value: float, *, as_money: bool = True) -> str:
    arrow = "▲" if value > 0 else ("▼" if value < 0 else "•")
    shown = money(abs(value)) if as_money else number(abs(value), decimals=1)
    return f"{arrow} {label}: {shown}"


def simulation_view(result: SimulationOut) -> str:
    deltas = result.deltas
    changes = [
        _delta_line("Monthly savings", deltas.get("monthly_savings", 0.0)),
        _delta_line("Projected savings", deltas.get("projected_savings_end", 0.0)),
        _delta_line("Emergency months", deltas.get("emergency_months", 0.0), as_money=False),
        _delta_line("Health score", deltas.get("health_score", 0.0), as_money=False),
    ]
    return _join(
        "🔮 *What-if*",
        _scenario_block("CURRENT", result.current),
        _scenario_block("SCENARIO", result.scenario),
        "*RESULT*\n" + "\n".join(changes),
        "Illustrative projection from your own numbers — straight-line, with no "
        "market returns assumed.",
        FINANCE_NOTE,
    )


def decision_view(decision: DecisionOut) -> str:
    """Consequences only. There is no verdict here, by design."""
    return _join(
        f"🛒 *Buying something for {money(decision.purchase_price)}*",
        (
            f"Savings: {money(decision.savings_before)} → "
            f"{money(decision.savings_after)}\n"
            f"Emergency cover: {number(decision.emergency_months_before, decimals=1)} → "
            f"{number(decision.emergency_months_after, decimals=1)} months\n"
            f"Health score: {number(decision.health_score_before, decimals=1)} → "
            f"{number(decision.health_score_after, decimals=1)}"
        ),
        decision.disclaimer,
        FINANCE_NOTE,
    )


def time_machine_view(paths: list[ScenarioComparison]) -> str:
    blocks = [
        (
            f"*{path.label}*\n"
            f"{money(path.monthly_savings)}/month → {money(path.projected_savings_end)} "
            f"· health {number(path.health_score, decimals=1)}"
            + (
                f" · goal {number(path.goal_completion_pct, decimals=1)}%"
                if path.goal_completion_pct is not None else ""
            )
        )
        for path in paths
    ]
    return _join(
        "⏳ *Time Machine* — the same you, four habits",
        "\n\n".join(blocks),
        "Illustrative projections, not forecasts.",
        FINANCE_NOTE,
    )


# --- market -------------------------------------------------------------

def _trend_icon(trend: str) -> str:
    return {"Upward": "📈", "Downward": "📉"}.get(trend, "➖")


def market_view(reports: list[TrendReportOut]) -> str:
    if not reports:
        return _join(
            "📈 *Market*",
            "Your watchlist is empty. Add a symbol and I will track it.",
            MARKET_NOTE,
        )
    lines = [
        (
            f"{index}. {_trend_icon(report.trend)} *{report.symbol}* "
            f"{compact(report.latest_price)}\n"
            f"    7d {number(report.change_7d_pct, decimals=2)}% · "
            f"30d {number(report.change_30d_pct, decimals=2)}% · "
            f"{report.trend} · {report.volatility_label} volatility"
        )
        for index, report in enumerate(reports, start=1)
    ]
    return _join("📈 *Market* — ranked by 7-day momentum", "\n".join(lines), MARKET_NOTE)


# --- education ----------------------------------------------------------

def topic_view(topic: dict) -> str:
    return _join(
        f"🧠 *{topic['title']}*",
        topic["explanation"],
        f"*Example*\n{topic['example']}",
        f"*Common mistake*\n{topic['common_mistake']}",
    )


def quiz_view(topic: dict) -> str:
    """Just the question — the options are buttons (see keyboards.quiz_options)."""
    return f"❓ *{topic['title']} — quick check*\n\n{topic['quiz']['question']}"


def quiz_result_view(topic: dict, chosen_idx: int) -> str:
    quiz = topic["quiz"]
    head = "✅ Correct." if chosen_idx == quiz["answer_idx"] else "❌ Not quite."
    return _join(head, f"The answer is: {quiz['options'][quiz['answer_idx']]}")


def topics_list_view(topics: list[dict]) -> str:
    return _join("🧠 *Learn*", f"{len(topics)} short lessons. Pick one:")


# --- misc ---------------------------------------------------------------

def help_view() -> str:
    return _join(
        "*FinMentor commands*",
        (
            "/start — set up or reopen the menu\n"
            "/profile — your finances as I have them\n"
            "/health — your health score and DNA\n"
            "/budget — a suggested split of your income\n"
            "/goals — track and add goals\n"
            "/simulate — what-ifs, purchases, the time machine\n"
            "/market — your watchlist, ranked\n"
            "/watchlist — add or remove symbols\n"
            "/learn — 12 short lessons\n"
            "/ask — ask me anything about your numbers"
        ),
        "Every figure I show is calculated from your data, not guessed. "
        "I explain; I never tell you what to buy or sell.",
    )
