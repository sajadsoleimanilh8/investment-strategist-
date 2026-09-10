"""Build data/ft/{train,val}.jsonl — supervised pairs for the local model.

    python scripts/ft/build_dataset.py [--people 40] [--out data/ft]

Two things make this a training set rather than a pile of text:

1. **The user turn is byte-identical to inference.** Each row's user content is
   produced by the same `EXPLAIN_TEMPLATE` / `CHAT_TEMPLATE` formatting that
   `synthesizer.explain` and `.chat` use, including the labelled before/after
   block and the same JSON serialisation. A model tuned on a prompt shape it
   will never see is a model tuned on nothing.

2. **Nothing ships ungraded.** Every composed answer goes through
   `probes.score_answer` (seven checks) and `safety.enforce`. A row that is not
   clean on all seven, or that safety would downgrade, is dropped and counted —
   it is never "fixed up" and shipped, because a near-miss is exactly the
   behaviour being trained away.

The split is 90/10, stratified by task and by synthetic-person bucket, so the
validation set contains the hard shapes rather than whichever rows fell last.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ai import safety  # noqa: E402
from app.ai.prompts import CHAT_TEMPLATE, EXPLAIN_TEMPLATE, SYSTEM_PROMPT  # noqa: E402
from app.ai.rendering import render_sides  # noqa: E402
from app.ai.synthesizer import render_history  # noqa: E402
from app.schemas.simulation import WhatIfParams  # noqa: E402
from app.services.decision_simulator import evaluate_purchase  # noqa: E402
from app.services.education_engine import get_topic  # noqa: E402
from app.services.simulation_engine import run_what_if  # noqa: E402
from scripts.ft import gold  # noqa: E402
from scripts.ft.people import (  # noqa: E402
    TOPIC_KEYS, Person, build_population, chat_snapshot, health_context, twin_for,
)
from scripts.ft.probes import Probe, score_answer  # noqa: E402

SEED = 20260909
NAMED_ASSETS = ("bitcoin", "btc", "ethereum", "eth", "nvidia", "nvda", "apple",
                "aapl", "tesla", "tsla", "s&p", "etf", "index fund", "crypto")


# --- the exact inference-time payloads -----------------------------------

def explain_payload(question: str, context: dict) -> str:
    sides = render_sides(context)
    return EXPLAIN_TEMPLATE.format(
        question=question,
        sides=f"\n{sides}\n" if sides else "",
        context_json=json.dumps(context, ensure_ascii=False, default=str),
    )


def chat_payload(message: str, snapshot: dict, history: list[dict]) -> str:
    return CHAT_TEMPLATE.format(
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=str),
        history=render_history(history),
        question=message,
    )


# --- rows ----------------------------------------------------------------

def chat_rows(person: Person, rng: random.Random) -> list[dict]:
    """Free conversation. Half carry a previous turn, so history is learned."""
    snapshot = chat_snapshot(person)
    rows = []

    openers = [
        ("how am I doing?", gold.chat_answer),
        ("hey there", gold.chat_answer),
        ("i want to save for a car", gold.chat_answer),
        ("what should I focus on first?", lambda s, m, r: gold.chat_focus_answer(s, r)),
        ("how are my goals looking?", lambda s, m, r: gold.chat_goal_answer(s, r)),
        ("thanks, that helps", gold.chat_answer),
        ("what should I buy right now?", gold.chat_answer),
        ("my friend says a stock is about to explode, should I put money in?",
         gold.chat_answer),
    ]

    for index, (message, composer) in enumerate(openers):
        history: list[dict] = []
        if index % 2 == 1 and rows:                    # every other row sees a turn
            history = [{"question": rows[-1]["question"], "answer": rows[-1]["answer"]}]

        answer = composer(snapshot, message, rng)
        forbid = NAMED_ASSETS if ("buy" in message or "stock" in message) else ()
        rows.append({
            "task": "chat", "bucket": person.bucket, "person": person.key,
            "question": message, "answer": answer,
            "payload": chat_payload(message, snapshot, history),
            "context": snapshot, "forbid_any": forbid,
            "expect_any": (),
        })
    return rows


def explain_rows(person: Person, rng: random.Random) -> list[dict]:
    """The precise paths: health, what-if, purchase, education, missing data."""
    rows = []

    def add(question, context, answer, *, expect=(), market=False):
        rows.append({
            "task": "explain", "bucket": person.bucket, "person": person.key,
            "question": question, "answer": answer,
            "payload": explain_payload(question, context),
            "context": context, "expect_any": expect, "forbid_any": (),
            "market_context": market,
        })

    if person.onboarded:
        context = health_context(person)
        add("why is my financial health score what it is?", context,
            gold.health_answer(context, rng), expect=("score",))
        add("how am I doing overall?", context,
            gold.health_answer(context, rng), expect=("score",))

        if not person.goals:
            add("how are my goals going?", context,
                gold.no_goals_answer(context, rng), expect=("goal",))

        twin = twin_for(person)
        delta = round(twin.monthly_savings * 0.3 + 500_000, -5) or 1_000_000
        what_if = run_what_if(twin, WhatIfParams(monthly_savings_delta=delta)
                              ).model_dump(mode="json")
        add(f"what if I save {int(delta // 1_000_000)}m more each month?", what_if,
            gold.sides_answer(what_if, rng), expect=("saving", "projected"))

        price = round(max(twin.current_savings * 0.8, 5_000_000), -5)
        decision = evaluate_purchase(twin, price).model_dump(mode="json")
        add(f"what happens if I spend {int(price // 1_000_000)}m on a laptop?",
            decision, gold.sides_answer(decision, rng, purchase=True),
            expect=("saving", "emergency"))

    for key in rng.sample(TOPIC_KEYS, 2):
        topic = get_topic(key)
        add(f"what does {topic['title'].lower()} mean?", topic,
            gold.topic_answer(topic, rng), expect=(key.split("_")[0][:6],))

    add("how is the market doing?",
        {"unavailable": "your watchlist is empty, and I did not recognise a symbol."},
        gold.unavailable_answer(
            {"unavailable": "your watchlist is empty, and I did not recognise a symbol."},
            rng),
        expect=("watchlist", "empty"), market=True)

    return rows


# --- grading -------------------------------------------------------------

def vet(row: dict) -> tuple[bool, list[str]]:
    """Every check the eval harness applies, plus safety's own verdict.

    A row that safety would downgrade is a row teaching the model to write
    something that gets thrown away, so it is rejected here.
    """
    probe = Probe(
        key=row["person"], task=row["task"], question=row["question"],
        context=row["context"], market_context=row.get("market_context", False),
        expect_any=row.get("expect_any", ()), forbid_any=row.get("forbid_any", ()),
    )
    score = score_answer(row["answer"], probe)
    _, report = safety.enforce(
        row["answer"], context=row["context"],
        market_context=row.get("market_context", False),
    )

    failures = list(score.failures)
    if report["downgraded"]:
        failures.append(f"safety would downgrade: {report['ungrounded_numbers']}")
    if report["buy_sell_scrubbed"]:
        failures.append("safety would scrub a sentence")
    return (score.passed and not report["downgraded"]
            and not report["buy_sell_scrubbed"]), failures


def to_record(row: dict) -> dict:
    """A prompt/completion pair, not a flat `messages` list.

    This split is load-bearing. With one `messages` array TRL trains on the
    whole sequence, and these prompts are ~1200 characters of JSON against a
    47-word answer — so the gradient is dominated by the context, and the model
    learns to *emit* JSON contexts instead of replying to them. That is not
    hypothetical: the first run produced exactly that, and every answer was
    discarded by the safety layer.

    Split into `prompt` and `completion`, TRL masks the prompt and computes loss
    on the assistant turn only, which is the thing being taught.
    """
    return {
        "prompt": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": row["payload"]},
        ],
        "completion": [{"role": "assistant", "content": row["answer"]}],
    }


def stratified_split(rows: list[dict], val_fraction: float, seed: int):
    """90/10 within every (task, bucket) cell, so val holds the hard shapes."""
    rng = random.Random(seed)
    cells = collections.defaultdict(list)
    for row in rows:
        cells[(row["task"], row["bucket"])].append(row)

    train, val = [], []
    for cell in sorted(cells):
        group = cells[cell][:]
        rng.shuffle(group)
        cut = max(1, round(len(group) * val_fraction))
        val.extend(group[:cut])
        train.extend(group[cut:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=int, default=40)
    parser.add_argument("--out", default="data/ft")
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--show-rejects", type=int, default=5)
    args = parser.parse_args()

    rng = random.Random(SEED)
    population = build_population(args.people)

    rows, rejected = [], []
    for person in population:
        person_rows = chat_rows(person, rng)
        if True:
            person_rows += explain_rows(person, rng)
        for row in person_rows:
            ok, failures = vet(row)
            (rows if ok else rejected).append(
                row if ok else {**row, "why": failures}
            )

    train, val = stratified_split(rows, args.val_fraction, SEED)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, split in (("train", train), ("val", val)):
        path = out / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in split:
                handle.write(json.dumps(to_record(row), ensure_ascii=False) + "\n")
        print(f"{path}: {len(split)} rows")

    print(f"\naccepted {len(rows)}, rejected {len(rejected)} "
          f"({len(rejected) / max(1, len(rows) + len(rejected)) * 100:.1f}%)")

    print("\ntask x bucket histogram (train | val)")
    tr = collections.Counter((r["task"], r["bucket"]) for r in train)
    va = collections.Counter((r["task"], r["bucket"]) for r in val)
    for cell in sorted(set(tr) | set(va)):
        print(f"  {cell[0]:8} {cell[1]:14} {tr[cell]:4} | {va[cell]:3}")
    print(f"  {'TOTAL':8} {'':14} {sum(tr.values()):4} | {sum(va.values()):3}")

    lengths = [len(r["answer"].split()) for r in rows]
    print(f"\nanswer length: min {min(lengths)}, mean {sum(lengths) // len(lengths)}, "
          f"max {max(lengths)} words")
    payloads = [len(r["payload"]) for r in rows]
    print(f"payload chars: mean {sum(payloads) // len(payloads)}, max {max(payloads)}")

    if rejected and args.show_rejects:
        print(f"\nfirst {args.show_rejects} rejects:")
        for row in rejected[:args.show_rejects]:
            print(f"  [{row['task']}/{row['bucket']}] {row['question'][:40]!r}")
            print(f"     {'; '.join(row['why'])[:110]}")
            print(f"     {row['answer'][:110]}")


if __name__ == "__main__":
    main()
