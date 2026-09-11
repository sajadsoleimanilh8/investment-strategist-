"""The Definition-of-Done flow, with everything external switched off.

    python scripts/demo_check.py [--keep]

SPEC section 36 end to end, against a real database, with:

  * no Ollama            (LOCAL_LLM_PROVIDER unset -> a dead host)
  * no market APIs       (DEMO_MODE -> the seeded mock provider)
  * no remote LLM        (disabled by default)

What it proves is the promise Phase 5 made: the numbers are computed before any
model is involved, so with the model gone the user still gets every figure —
they just get it as a rendered table instead of prose. A run where `/ask`
returns `source=deterministic` *and* the right score is the whole point; a run
where it returns prose means the model was reachable and the check was not
actually testing anything.

Exit code 0 means the flow works offline. Anything else is a failure worth
blocking a deploy on.

The web surface is checked by Playwright (`web/ npm run test:e2e`), which
drives the same flow through a browser. This covers the Telegram surface and
the API underneath both.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set before app import: settings are read once, at import time.
os.environ["DEMO_MODE"] = "true"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["REMOTE_LLM_ENABLED"] = "false"
#: A closed port, not the fake provider. The fake would *pass* this check while
#: proving nothing about what happens when a real model is unreachable.
os.environ["LOCAL_LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_HOST"] = "http://127.0.0.1:1"

from app.ai.intent import parse  # noqa: E402
from app.api import ask as ask_pipeline  # noqa: E402
from app.api.deps import build_ai_context, load_twin  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.market import cache as market_cache  # noqa: E402
from app.repositories import market as market_repo  # noqa: E402
from app.schemas.simulation import WhatIfParams  # noqa: E402
from app.services import market_engine  # noqa: E402
from app.services.decision_simulator import evaluate_purchase  # noqa: E402
from app.services.education_engine import get_topic, list_topics  # noqa: E402
from app.services.financial_dna import build_dna  # noqa: E402
from app.services.health_score import compute_health_score  # noqa: E402
from app.services.simulation_engine import run_what_if  # noqa: E402
from app.services.time_machine import compare_paths  # noqa: E402
from scripts.seed_demo_user import seed_demo_user  # noqa: E402
from scripts.seed_market_assets import seed_demo_watchlist, seed_market_assets  # noqa: E402

PERIOD = "2026-09"
failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"  ok   {label}" + (f"  [{detail}]" if detail else ""))
    else:
        print(f"  FAIL {label}" + (f"  [{detail}]" if detail else ""))
        failures.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true",
                        help="leave the demo user behind for inspection")
    args = parser.parse_args()

    print(f"DEMO_MODE={settings.demo_mode}  local_llm={settings.ollama_host} "
          f"(closed)  remote_llm={settings.remote_llm_enabled}\n")

    db = SessionLocal()
    try:
        # --- onboarding ---------------------------------------------------
        print("onboarding")
        user_id = seed_demo_user(db, period=PERIOD)
        seed_market_assets(db)
        seed_demo_watchlist(db, user_id)
        db.commit()
        check("a profile exists", user_id > 0, f"user {user_id}")

        twin = load_twin(db, user_id, period=PERIOD)
        check("the twin has income and expenses",
              twin.income > 0 and twin.monthly_expenses > 0)

        # --- health -------------------------------------------------------
        print("\nhealth")
        score = compute_health_score(twin)
        check("a score in range", 0 <= score.total <= 100, f"{score.total}/100")
        check("all five components", len(score.components) == 5,
              ", ".join(f"{c.name} {c.points}" for c in score.components))

        dna = build_dna(twin, completed_topics=0)
        check("the DNA reads in bands",
              all(getattr(dna, f) for f in type(dna).model_fields),
              f"saving={dna.saving_discipline}, emergency={dna.emergency_readiness}")

        # --- what-if ------------------------------------------------------
        print("\nwhat-if")
        parsed = parse("what if I save 5m more each month?")
        check("the parser reads it without a model", parsed.intent == "what_if",
              f"delta={parsed.what_if.monthly_savings_delta:,.0f}")

        sim = run_what_if(twin, parsed.what_if or WhatIfParams())
        check("saving more raises projected savings",
              sim.scenario.projected_savings_end > sim.current.projected_savings_end,
              f"{sim.current.projected_savings_end:,.0f} -> "
              f"{sim.scenario.projected_savings_end:,.0f}")

        # --- decision -----------------------------------------------------
        print("\ndecision")
        decision = evaluate_purchase(twin, twin.current_savings * 1.2)
        check("a purchase beyond savings shows the cost",
              decision.savings_after < decision.savings_before,
              f"{decision.savings_before:,.0f} -> {decision.savings_after:,.0f}")
        check("and draws down the emergency fund",
              decision.emergency_months_after < decision.emergency_months_before,
              f"{decision.emergency_months_before:.2f} -> "
              f"{decision.emergency_months_after:.2f} months")

        # --- time machine -------------------------------------------------
        paths = compare_paths(twin)
        check("the time machine compares four paths", len(paths) == 4,
              ", ".join(p.label for p in paths))

        # --- market, with no network --------------------------------------
        print("\nmarket (no external API)")
        watched = market_repo.list_watchlist(db, user_id)
        check("the watchlist has symbols", len(watched) > 0,
              ", ".join(item.symbol for item in watched))

        reports = [market_engine.analyze(item.symbol,
                                         market_cache.get_or_fetch(db, item.symbol))
                   for item in watched]
        check("every symbol analysed from seeded data", len(reports) == len(watched))
        check("each report carries its disclaimer",
              all(report.disclaimer for report in reports))

        ranked = market_engine.rank_by_momentum(reports)
        check("ranked by momentum",
              [r.symbol for r in ranked] == [r.symbol for r in
                                             sorted(reports, key=lambda r: -r.change_7d_pct)],
              " > ".join(f"{r.symbol} {r.change_7d_pct:+.2f}%" for r in ranked))

        # --- education ----------------------------------------------------
        print("\nlearn")
        topics = list_topics()
        check("twelve curated topics", len(topics) == 12)
        topic = get_topic("diversification")
        check("a topic has explanation, example and mistake",
              all(topic.get(k) for k in ("explanation", "example", "common_mistake")))

        # --- ask, with the model unreachable ------------------------------
        print("\nask (model unreachable — the Phase 5 guarantee)")
        answer = ask_pipeline.answer_question(
            db, user_id, "why is my financial health score what it is?")

        check("it answered at all", bool(answer.text.strip()))
        check("it degraded to deterministic rather than failing",
              answer.source == "deterministic", f"source={answer.source}")
        check("the real score is in the answer",
              f"{score.total}" in answer.text, f"looking for {score.total}")
        check("the disclaimer is attached", answer.disclaimer_applied)
        check("the context came from the engine",
              answer.used_context.get("financial_health_score") == score.total)

        context, _ = build_ai_context(db, user_id, parse("what if I save 5m more a month?"))
        check("a what-if question still gets engine figures",
              context["scenario"]["monthly_savings"] > context["current"]["monthly_savings"])

        chat = ask_pipeline.answer_question(db, user_id, "hey, how am I doing?")
        check("free chat degrades too, without inventing anything",
              chat.source == "deterministic" and bool(chat.text.strip()),
              f"source={chat.source}")

        # --- transcript ---------------------------------------------------
        turns = ask_pipeline.transcript(db, user_id)
        check("the exchange was recorded", len(turns) >= 2, f"{len(turns)} turns")

        if not args.keep:
            db.rollback()
    finally:
        db.close()

    print(f"\n{'=' * 70}")
    if failures:
        print(f"FAILED {len(failures)} of {checks} checks:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"All {checks} checks passed — the full flow works with no Ollama, "
          f"no market API and no remote LLM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
