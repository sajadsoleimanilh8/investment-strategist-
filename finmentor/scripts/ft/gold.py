"""Deterministic gold answers, composed from the context.

Why templates and not a teacher model: FinMentor answers are formulaic by
design — open with what is going well, name the weak part, quote the engine's
own figures, nudge. That is a shape a composer can hit exactly and a 3B teacher
cannot hit reliably. A weak teacher would poison the set with the very defects
the fine-tune exists to remove, and no teacher larger than 3B can be pulled on
this machine.

The rules the composer obeys, which are the rules the model is being taught:

* Every figure is copied verbatim out of the context. Nothing is computed here,
  not even a rounding — the `plain` strings and the labelled before/after
  values are quoted as they arrive.
* A component's verdict is the engine's word. The composer never decides
  whether a number is good.
* Before/after figures are written next to their label, in that order.
* No buy/sell, ever, including in the redirect answers.

Every row is then graded by `probes.score_answer` and pushed through
`safety.enforce`; anything short of clean is dropped rather than shipped.
Lexical variation is seeded per row so the model learns the shape, not one
sentence.
"""
from __future__ import annotations

import random

from app.ai.rendering import before_after_pairs, format_value

#: Strongest first, weakest last — the order the opening line reads them in.
VERDICT_RANK = {"Strong": 0, "Moderate": 1, "Weak": 2}

COMPONENT_LABEL = {
    "savings_rate": "savings rate",
    "emergency_fund": "emergency fund",
    "debt_load": "debt load",
    "budget_stability": "budget stability",
    "goal_progress": "goal progress",
}

OPENERS = (
    "Here is where you stand.",
    "Let's look at where you are.",
    "Here's the picture from your numbers.",
    "This is what your figures say.",
)

CHAT_OPENERS = (
    "Good question.",
    "Happy to walk through it.",
    "Let's take a look.",
    "Sure — here's what your numbers show.",
)

STRONG_FRAMES = (
    "Your {label} is {verdict} — {plain}.",
    "{Plain_cap} — that puts your {label} at {verdict}.",
    "On the {label} you are {verdict}: {plain}.",
)

WEAK_FRAMES = (
    "The thinner part is your {label}, which is {verdict} — {plain}.",
    "Your {label} is the weaker spot at {verdict}: {plain}.",
    "Where there is room to move is your {label} — {verdict}, {plain}.",
)

NUDGES = (
    "Small, steady changes move this more than big ones.",
    "One step at a time is enough here.",
    "Nothing here needs fixing today — it is just worth knowing.",
    "That is a reasonable place to put your next effort.",
)

REDIRECTS = (
    "I do not tell people what to buy or sell — that is not something I can "
    "judge for you.",
    "Picking what to buy is not something I do; I explain what your own "
    "numbers are doing.",
    "I cannot tell you what to put money into. What I can do is show you what "
    "your figures look like.",
)


def _sorted_components(context: dict) -> list[dict]:
    components = [c for c in context.get("components", []) if c.get("verdict")]
    return sorted(components, key=lambda c: VERDICT_RANK.get(c["verdict"], 1))


def _frame(rng: random.Random, frames: tuple[str, ...], component: dict) -> str:
    plain = component["plain"].rstrip(".")
    return rng.choice(frames).format(
        label=COMPONENT_LABEL.get(component["name"], component["name"].replace("_", " ")),
        verdict=component["verdict"], plain=plain,
        Plain_cap=plain[0].upper() + plain[1:] if plain else "",
    )


# --- chat ----------------------------------------------------------------

def chat_answer(snapshot: dict, message: str, rng: random.Random) -> str:
    """A warm 2-4 sentence reply built from a chat snapshot."""
    if snapshot.get("onboarded") is False:
        return (
            f"{rng.choice(CHAT_OPENERS)} I do not have your numbers yet, so there "
            "is nothing I can tell you about them. Send /start and we can set up "
            "your profile in a couple of minutes."
        )

    components = _sorted_components(snapshot)
    strongest, weakest = components[0], components[-1]
    sentences = [rng.choice(CHAT_OPENERS)]

    if "buy" in message.lower() or "invest" in message.lower() or "stock" in message.lower():
        sentences = [rng.choice(REDIRECTS)]

    sentences.append(_frame(rng, STRONG_FRAMES, strongest))
    if weakest["name"] != strongest["name"]:
        sentences.append(_frame(rng, WEAK_FRAMES, weakest))
    sentences.append(rng.choice(NUDGES))
    return " ".join(sentences)


def chat_focus_answer(snapshot: dict, rng: random.Random) -> str:
    """"What should I focus on?" — name the weak part, in the engine's word."""
    if snapshot.get("onboarded") is False:
        return chat_answer(snapshot, "", rng)

    components = _sorted_components(snapshot)
    weakest, strongest = components[-1], components[0]
    return " ".join([
        _frame(rng, WEAK_FRAMES, weakest),
        _frame(rng, STRONG_FRAMES, strongest),
        rng.choice(NUDGES),
    ])


def chat_goal_answer(snapshot: dict, rng: random.Random) -> str:
    """Goal progress. The engine's verdict leads, so the closing line cannot
    read as praise over a Weak goal."""
    if snapshot.get("onboarded") is False:
        return chat_answer(snapshot, "", rng)

    goals = snapshot.get("active_goals") or []
    if not goals:
        return (
            f"{rng.choice(CHAT_OPENERS)} You do not have a goal set yet, so there "
            "is nothing for me to track. Adding one gives me a date to work "
            "towards with you."
        )

    verdict = next(
        (c["verdict"] for c in snapshot.get("components", [])
         if c["name"] == "goal_progress"), "Moderate",
    )
    goal = goals[0]
    return (
        f"{rng.choice(CHAT_OPENERS)} Your goal progress is {verdict}. "
        f"{goal['name']} is at {format_value('progress_pct', goal['progress_pct'])}%, "
        f"{format_value('current', goal['current'])} of "
        f"{format_value('target', goal['target'])}. "
        f"{rng.choice(NUDGES)}"
    )


# --- explain -------------------------------------------------------------

def health_answer(context: dict, rng: random.Random) -> str:
    """The precise path: the score, its strongest and weakest parts."""
    components = sorted(
        context.get("components", []),
        key=lambda c: c.get("points", 0), reverse=True,
    )
    best, worst = components[0], components[-1]
    score = context["financial_health_score"]

    def line(component: dict, lead: str) -> str:
        label = COMPONENT_LABEL.get(component["name"], component["name"].replace("_", " "))
        detail = component.get("detail", "").rstrip(".")
        return (f"{lead} your {label}, at "
                f"{format_value('points', component['points'])} out of "
                f"{format_value('points', component['max_points'])}"
                + (f" — {detail}." if detail else "."))

    return " ".join([
        f"{rng.choice(OPENERS)} Your financial health score is "
        f"{format_value('score', score)} out of 100.",
        line(best, "The strongest part is"),
        line(worst, "The one with the most room is"),
        rng.choice(NUDGES),
    ])


def sides_answer(context: dict, rng: random.Random, *, purchase: bool = False) -> str:
    """A what-if or a purchase: each figure written next to its own label."""
    pairs = [
        (name, before, after) for name, before, after in before_after_pairs(context)
        if isinstance(before, (int, float)) and isinstance(after, (int, float))
    ]
    named = {
        "monthly_savings": "what you save each month",
        "projected_savings_end": "your projected savings",
        "emergency_months": "your emergency cover",
        "health_score": "your health score",
        "savings": "your savings",
        "goal_completion_pct": "your goal progress",
    }

    lines = []
    for name, before, after in pairs[:3]:
        label = named.get(name, name.replace("_", " "))
        lines.append(
            f"{label.capitalize()} goes from {format_value(name, before)} "
            f"before to {format_value(name, after)} after."
        )

    head = (
        "Here is what that purchase does to your numbers."
        if purchase else
        f"{rng.choice(OPENERS)} Here is the same picture before and after that change."
    )
    tail = (
        "Those are the consequences from your own figures — the decision is yours."
        if purchase else
        "This is a straight-line projection from your own figures, not a forecast."
    )
    return " ".join([head, *lines, tail])


def topic_answer(context: dict, rng: random.Random) -> str:
    """Education: the curated topic, tightened. Nothing invented."""
    explanation = context["explanation"].split(". ")
    return " ".join([
        f"{explanation[0]}.",
        (explanation[1] + ".") if len(explanation) > 1 else "",
        f"The mistake to avoid: {context['common_mistake'][0].lower()}"
        f"{context['common_mistake'][1:]}",
    ]).replace("  ", " ").strip()


def unavailable_answer(context: dict, rng: random.Random) -> str:
    reason = context["unavailable"].rstrip(".")
    return (
        f"I do not have that for you: {reason}. "
        "Once that is in place I can walk you through it."
    )


def no_goals_answer(context: dict, rng: random.Random) -> str:
    return (
        "You do not have any active goals yet, so there is no progress for me "
        "to report. Adding one gives me a target and a date to track against. "
        f"{rng.choice(NUDGES)}"
    )
