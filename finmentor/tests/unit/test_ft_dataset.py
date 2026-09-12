"""The fine-tuning dataset's contract with the running app.

Training data is worthless if it teaches a prompt shape the model will never
see. These tests pin the two places that can silently drift apart:

* the user turn a row carries vs. the payload `synthesizer` actually sends
* the contexts `scripts/ft/people.py` builds vs. the ones `app/api/deps.py`
  builds from the database

Neither the training scripts nor this file are imported by `app/`. They import
`app`, never the reverse.
"""
import json

import pytest

from app.ai.prompts import CHAT_TEMPLATE, EXPLAIN_TEMPLATE, SYSTEM_PROMPT
from app.ai.rendering import render_sides
from scripts.ft import gold
from scripts.ft.build_dataset import chat_payload, explain_payload, to_record, vet
from scripts.ft.people import build_population, chat_snapshot, health_context

PERIOD = "2026-09"


@pytest.fixture(scope="module")
def population():
    return build_population(8)


# --- the payload must match what the model will actually be sent ---------

def test_the_explain_payload_is_what_the_synthesizer_sends(monkeypatch, population):
    """Capture the real prompt and compare it to the dataset's."""
    sent = []
    from app.ai import synthesizer
    from app.ai.local_llm import FakeLocalProvider

    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: sent.append(prompt) or "ok",
    )

    context = health_context(next(p for p in population if p.onboarded))
    question = "why is my financial health score what it is?"
    synthesizer.explain(question, context)

    assert explain_payload(question, context) == sent[0]


def test_the_chat_payload_is_what_the_synthesizer_sends(monkeypatch, population):
    sent = []
    from app.ai import synthesizer
    from app.ai.local_llm import FakeLocalProvider

    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: sent.append(prompt) or "ok",
    )

    snapshot = chat_snapshot(next(p for p in population if p.onboarded))
    history = [{"question": "hey", "answer": "hello"}]
    synthesizer.chat("how am I doing?", snapshot, history)

    assert chat_payload("how am I doing?", snapshot, history) == sent[0]


def test_a_two_sided_context_carries_its_labelled_block(population):
    from app.schemas.simulation import WhatIfParams
    from app.services.simulation_engine import run_what_if
    from scripts.ft.people import twin_for

    person = next(p for p in population if p.onboarded)
    context = run_what_if(twin_for(person), WhatIfParams(monthly_savings_delta=1_000_000)
                          ).model_dump(mode="json")
    payload = explain_payload("what if I save 1m more?", context)

    assert render_sides(context) in payload
    assert payload.index("BEFORE") < payload.index("Figures (")


def test_a_one_sided_context_leaves_no_hole(population):
    payload = explain_payload("why?", health_context(
        next(p for p in population if p.onboarded)))

    assert "BEFORE" not in payload
    assert "\n\n\n" not in payload


# --- the record shape ----------------------------------------------------

def test_a_record_splits_the_prompt_from_the_completion():
    """The split is what makes TRL mask the prompt. Flattened into one
    `messages` list, loss is computed over ~1200 characters of JSON context as
    well as the answer — and the model learns to emit contexts. The first
    training run did exactly that."""
    record = to_record({"payload": "user turn", "answer": "assistant turn"})

    assert [m["role"] for m in record["prompt"]] == ["system", "user"]
    assert [m["role"] for m in record["completion"]] == ["assistant"]
    assert record["prompt"][0]["content"] == SYSTEM_PROMPT
    assert record["prompt"][1]["content"] == "user turn"
    assert record["completion"][0]["content"] == "assistant turn"
    assert json.loads(json.dumps(record)) == record          # serialisable as-is


def test_the_completion_is_far_shorter_than_the_prompt():
    """The reason the split matters, asserted rather than assumed."""
    from scripts.ft.build_dataset import chat_rows
    import random

    rng = random.Random(3)
    rows = chat_rows(build_population(4)[1], rng)
    record = to_record(rows[0])

    prompt_chars = sum(len(m["content"]) for m in record["prompt"])
    completion_chars = len(record["completion"][0]["content"])
    assert prompt_chars > completion_chars * 3


# --- the synthetic contexts must match the database-backed ones ----------

def test_the_chat_snapshot_matches_the_one_deps_builds(db, monkeypatch):
    """`people.chat_snapshot` duplicates `deps.build_chat_snapshot` so training
    needs no database. Same keys, same component shape — or the model is tuned
    on a context the product does not send."""
    from app.api.deps import build_chat_snapshot
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    live = build_chat_snapshot(db, seed_demo_user(db, period=PERIOD))
    synthetic = chat_snapshot(next(p for p in build_population(8) if p.onboarded))

    assert set(live) == set(synthetic)
    assert set(live["components"][0]) == set(synthetic["components"][0])
    assert set(live["active_goals"][0]) == set(synthetic["active_goals"][0])


def test_the_health_context_matches_the_one_deps_builds(db, monkeypatch):
    from app.ai.intent import parse
    from app.api.deps import build_ai_context
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    user_id = seed_demo_user(db, period=PERIOD)
    live, _ = build_ai_context(db, user_id, parse("why is my health score what it is?"))
    synthetic = health_context(next(p for p in build_population(8) if p.onboarded))

    assert set(live) == set(synthetic)
    assert set(live["components"][0]) == set(synthetic["components"][0])


# --- every shipped row is clean -----------------------------------------

def test_every_composed_answer_passes_the_grader_and_safety(population):
    """The dataset's own quality gate, run over a slice of the population.

    A row that safety would downgrade teaches the model to write something
    that gets thrown away, so the builder drops it. This asserts the composer
    is good enough that dropping is rare, not routine.
    """
    from scripts.ft.build_dataset import chat_rows, explain_rows
    import random

    rng = random.Random(7)
    rows = []
    for person in population:
        rows += chat_rows(person, rng) + explain_rows(person, rng)

    verdicts = [vet(row) for row in rows]
    accepted = sum(ok for ok, _ in verdicts)

    assert accepted / len(rows) > 0.95, [
        f for ok, fs in verdicts if not ok for f in fs
    ][:5]


def test_no_composed_answer_ever_gives_advice(population):
    from app.ai.safety import _BUY_SELL_RE
    from scripts.ft.build_dataset import chat_rows
    import random

    rng = random.Random(7)
    for person in population:
        for row in chat_rows(person, rng):
            assert not _BUY_SELL_RE.search(row["answer"]), row["answer"]


def test_the_redirect_answers_name_nothing_to_buy(population):
    from scripts.ft.build_dataset import chat_rows
    import random

    rng = random.Random(7)
    for person in population:
        for row in chat_rows(person, rng):
            if not row["forbid_any"]:
                continue
            lowered = row["answer"].lower()
            assert not [t for t in row["forbid_any"] if t in lowered.split()], row["answer"]


def test_a_person_without_a_profile_is_always_pointed_at_start(population):
    import random

    rng = random.Random(7)
    for person in population:
        if person.onboarded:
            continue
        answer = gold.chat_answer(chat_snapshot(person), "how am I doing?", rng)
        assert "/start" in answer
