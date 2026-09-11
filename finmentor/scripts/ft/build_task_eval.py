"""Build data/ft/task_eval.jsonl — the held-out task-adherence slice.

    python scripts/ft/build_task_eval.py [--people 12]

Held out properly: the people here are drawn from a *different seed offset*
than `build_dataset.py` uses, so nothing in this file appears in train or val.
A slice sampled from the same population would measure memorisation.

What it measures is deliberately narrow. `probes.py` already asks whether an
answer is correct — right verdicts, right sides, no invented numbers, no
advice. This asks only whether it is the right *kind* of answer, because that
is the check `finmentor-3b` needed and did not have: it scored 38/39 on
verdicts while answering an EXPLAIN question in CHAT shape.

Each row carries the prompt the model will be sent, the task it must perform,
and the subject its answer has to name. It carries no gold answer — there is no
single right wording, only a right shape.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ai.prompts import TASK_CHAT, TASK_EXPLAIN  # noqa: E402
from app.schemas.simulation import WhatIfParams  # noqa: E402
from app.services.decision_simulator import evaluate_purchase  # noqa: E402
from app.services.education_engine import get_topic  # noqa: E402
from app.services.simulation_engine import run_what_if  # noqa: E402
from scripts.ft.build_dataset import SEED, chat_payload, explain_payload  # noqa: E402
from scripts.ft.people import (  # noqa: E402
    TOPIC_KEYS, build_population, chat_snapshot, health_context, twin_for,
)

#: A different seed to the training population. Same generator, same buckets,
#: people the model has never been shown.
HELD_OUT_SEED = SEED + 7919


def rows_for(person, index: int) -> list[dict]:
    out: list[dict] = []

    def add(task, question, payload, *, subject="", onboarded=True):
        out.append({
            "task": task, "question": question, "payload": payload,
            "subject": subject, "onboarded": onboarded,
            "person": person.key, "bucket": person.bucket,
        })

    snapshot = chat_snapshot(person)

    # --- CHAT: must stay a reply -----------------------------------------
    for message in ("how am I doing?", "hey", "what should I focus on first?"):
        add(TASK_CHAT, message, chat_payload(message, snapshot, []),
            onboarded=person.onboarded)

    # A second turn, because history is where a model most often slips into
    # summarising instead of continuing a conversation.
    history = [{"question": "how am I doing?", "answer": "You are doing fine so far."}]
    add(TASK_CHAT, "and what about my savings?",
        chat_payload("and what about my savings?", snapshot, history),
        onboarded=person.onboarded)

    if not person.onboarded:
        return out

    # --- EXPLAIN: must name what was asked about --------------------------
    health = health_context(person)
    add(TASK_EXPLAIN, "why is my financial health score what it is?",
        explain_payload("why is my financial health score what it is?", health),
        subject="score")
    add(TASK_EXPLAIN, "what is my score out of 100?",
        explain_payload("what is my score out of 100?", health), subject="score")

    twin = twin_for(person)
    delta = round(max(twin.monthly_savings * 0.25, 1_000_000), -5)
    what_if = run_what_if(twin, WhatIfParams(monthly_savings_delta=delta)
                          ).model_dump(mode="json")
    question = f"what if I save {int(delta // 1_000_000)}m more each month?"
    add(TASK_EXPLAIN, question, explain_payload(question, what_if), subject="what_if")

    price = round(max(twin.current_savings * 0.7, 5_000_000), -5)
    decision = evaluate_purchase(twin, price).model_dump(mode="json")
    question = f"what happens if I spend {int(price // 1_000_000)}m on a laptop?"
    add(TASK_EXPLAIN, question, explain_payload(question, decision), subject="purchase")

    topic = get_topic(TOPIC_KEYS[index % len(TOPIC_KEYS)])
    question = f"what does {topic['title'].lower()} mean?"
    add(TASK_EXPLAIN, question, explain_payload(question, topic), subject="topic")

    add(TASK_EXPLAIN, "how are my goals going?",
        explain_payload("how are my goals going?", health), subject="goal")

    missing = {"unavailable": "your watchlist is empty, and I did not recognise a symbol."}
    add(TASK_EXPLAIN, "how is the market doing?",
        explain_payload("how is the market doing?", missing), subject="unavailable")

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=int, default=12)
    parser.add_argument("--out", default="data/ft/task_eval.jsonl")
    args = parser.parse_args()

    population = build_population(args.people, seed=HELD_OUT_SEED, tag="ho")
    rows = [row for index, person in enumerate(population)
            for row in rows_for(person, index)]

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"{path}: {len(rows)} rows from {len(population)} held-out people "
          f"(seed {HELD_OUT_SEED})")

    by_task = collections.Counter(row["task"] for row in rows)
    print("\ntask                 rows")
    for task, count in sorted(by_task.items()):
        print(f"  {task:18} {count:4}")

    print("\nEXPLAIN subjects")
    for subject, count in sorted(collections.Counter(
            row["subject"] for row in rows if row["task"] == TASK_EXPLAIN).items()):
        print(f"  {subject:18} {count:4}")

    print("\nbuckets")
    for bucket, count in sorted(collections.Counter(row["bucket"] for row in rows).items()):
        print(f"  {bucket:18} {count:4}")

    # The guarantee that makes this a held-out slice rather than a sample.
    train_people = {p.key for p in build_population(40)}
    overlap = {row["person"] for row in rows} & train_people
    print(f"\noverlap with the training population: {len(overlap)} "
          f"({'held out' if not overlap else 'LEAKED: ' + str(sorted(overlap))})")


if __name__ == "__main__":
    main()
