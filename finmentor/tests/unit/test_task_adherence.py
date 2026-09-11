"""Task-type markers, and the grader that checks the model obeyed them.

The defect being guarded: `finmentor-3b` scored 38/39 on verdicts and 15/15 on
sides while answering "why is my financial health score what it is?" with a
warm verdict list that never said the word "score". Every existing check
passed. It was still the wrong *kind* of answer.

So there are two things to pin. The marker has to reach the model — at training
and at inference, byte-identically, or a fine-tune learns a token it will never
see. And the grader has to fail the answer that started this.
"""
import json
import pathlib

import pytest

from app.ai.prompts import CHAT_TEMPLATE, EXPLAIN_TEMPLATE, TASK_CHAT, TASK_EXPLAIN
from scripts.ft import task_adherence as ta
from scripts.ft.build_dataset import chat_payload, explain_payload
from scripts.ft.people import build_population, chat_snapshot, health_context

#: The real answer `finmentor-3b` gave to an EXPLAIN question. Kept verbatim:
#: this is the regression, and if the grader ever passes it the grader is wrong.
THE_ACTUAL_FAILURE = (
    "Let's look at where you are. Your savings rate is 31.7% — strong. Your "
    "emergency fund is at 1.82 months of essential expenses — weak. Your debt "
    "management is strong. Your goal discipline is weak. Your budget stability "
    "is moderate. Your financial knowledge is beginner-level. That is a "
    "reasonable place to put your next effort."
)


# --- the marker reaches the model ---------------------------------------

def test_both_templates_carry_a_task_marker():
    assert "TASK: {task}" in EXPLAIN_TEMPLATE
    assert "TASK: {task}" in CHAT_TEMPLATE
    assert TASK_EXPLAIN != TASK_CHAT


def test_the_marker_is_the_first_thing_the_model_reads():
    """Buried in the middle it competes with the context; a 3B weights the top
    of a prompt most heavily."""
    person = next(p for p in build_population(8) if p.onboarded)

    explain = explain_payload("why?", health_context(person))
    chat = chat_payload("hey", chat_snapshot(person), [])

    assert explain.splitlines()[0] == f"TASK: {TASK_EXPLAIN}"
    assert chat.splitlines()[0] == f"TASK: {TASK_CHAT}"


def test_each_template_names_the_other_task_as_the_thing_not_to_do():
    """Telling it what this task *is* leaves the other shape available. The
    bleed went both ways, so both prompts have to close both doors."""
    assert "CHAT task" in EXPLAIN_TEMPLATE
    assert "EXPLAIN task" in CHAT_TEMPLATE


def test_the_marked_payload_is_still_what_the_synthesizer_sends(monkeypatch):
    """The property the whole dataset depends on, re-asserted after the change."""
    sent = []
    from app.ai import synthesizer
    from app.ai.local_llm import FakeLocalProvider

    monkeypatch.setattr(FakeLocalProvider, "generate",
                        lambda self, prompt, system=None: sent.append(prompt) or "ok")

    person = next(p for p in build_population(8) if p.onboarded)
    context = health_context(person)
    synthesizer.explain("why is my score what it is?", context)
    assert explain_payload("why is my score what it is?", context) == sent[0]

    sent.clear()
    snapshot = chat_snapshot(person)
    synthesizer.chat("how am I doing?", snapshot, [])
    assert chat_payload("how am I doing?", snapshot, []) == sent[0]


def test_every_training_row_carries_its_marker():
    path = pathlib.Path("data/ft/train.jsonl")
    if not path.exists():
        pytest.skip("run scripts/ft/build_dataset.py first")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    firsts = {row["prompt"][1]["content"].splitlines()[0] for row in rows}

    assert firsts == {f"TASK: {TASK_EXPLAIN}", f"TASK: {TASK_CHAT}"}


def test_both_tasks_are_represented_in_training_and_validation():
    """A split that lost one task would teach the marker to mean nothing."""
    for name in ("train", "val"):
        path = pathlib.Path(f"data/ft/{name}.jsonl")
        if not path.exists():
            pytest.skip("run scripts/ft/build_dataset.py first")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        markers = [row["prompt"][1]["content"].splitlines()[0] for row in rows]

        assert markers.count(f"TASK: {TASK_EXPLAIN}") > 10, name
        assert markers.count(f"TASK: {TASK_CHAT}") > 10, name


# --- the grader ----------------------------------------------------------

def test_the_answer_that_started_this_now_fails():
    result = ta.score(THE_ACTUAL_FAILURE, task=TASK_EXPLAIN, subject="score")

    assert result.passed is False
    assert any("never names the subject" in failure for failure in result.failures)


def test_the_same_answer_is_fine_as_a_chat_reply_apart_from_its_length():
    """It is not a bad answer. It is the wrong task — which is exactly the
    distinction the existing tone and grounding checks cannot draw."""
    result = ta.score(THE_ACTUAL_FAILURE, task=TASK_CHAT)

    assert all("never names the subject" not in f for f in result.failures)


def test_a_good_explain_answer_passes():
    answer = ("Your financial health score is 62.3 out of 100. The strongest "
              "part is your savings rate at 20 out of 20. The thinnest is your "
              "emergency fund at 6.1, which is 1.8 months of expenses.")

    assert ta.score(answer, task=TASK_EXPLAIN, subject="score").passed


def test_a_good_chat_reply_passes():
    answer = ("Good question. Your savings rate is Strong — you put aside a "
              "third of what comes in. Your emergency fund is the thinner part.")

    assert ta.score(answer, task=TASK_CHAT).passed


@pytest.mark.parametrize(
    "subject,answer",
    [
        ("score", "Your score is 62.3 out of 100. The savings rate carries most of it."),
        ("what_if", "Before, you saved 10m a month. After the change it would be 15m."),
        ("purchase", "Your savings go from 45m before to 0 after. That is the whole balance."),
        ("topic", "Diversification means not putting all your money in one place. "
                  "One thing going badly then costs you less."),
        ("unavailable", "I do not have that yet. Your watchlist is empty, so there is "
                        "nothing to report."),
    ],
)
def test_each_explain_subject_is_recognised(subject, answer):
    assert ta.score(answer, task=TASK_EXPLAIN, subject=subject).passed, subject


def test_a_table_fails_either_task():
    table = ("Financial health score: 62.3\n"
             "Savings rate: 20\nEmergency fund: 6.1\nDebt load: 17.5")

    assert not ta.score(table, task=TASK_EXPLAIN, subject="score").passed
    assert not ta.score(table, task=TASK_CHAT).passed


def test_a_downgraded_answer_fails_as_a_chat_reply():
    """Safety's rendering is correct and is not a conversation. A model that
    produces it verbatim is not chatting."""
    downgraded = ("Here are your figures, straight from the calculation:\n"
                  "Financial health score: 62.3\nSavings rate: 20")

    assert not ta.score(downgraded, task=TASK_CHAT).passed


def test_a_rambling_reply_fails_chat_but_not_explain():
    long_reply = " ".join(["You are doing well on this front." for _ in range(9)])

    assert not ta.score(long_reply, task=TASK_CHAT).passed


def test_a_one_line_explanation_is_too_short():
    assert not ta.score("62.3.", task=TASK_EXPLAIN, subject="score").passed


def test_a_reply_that_never_says_you_is_not_addressed_to_anyone():
    assert not ta.score("The savings rate is Strong. The fund is Weak.",
                        task=TASK_CHAT).passed


def test_an_unonboarded_reply_must_point_at_start():
    without = "I do not have your numbers yet, so there is nothing to tell you."
    with_it = without + " Send /start and we can set them up."

    assert not ta.score(without, task=TASK_CHAT, onboarded=False).passed
    assert ta.score(with_it, task=TASK_CHAT, onboarded=False).passed


def test_an_empty_answer_fails_both_tasks():
    assert not ta.score("", task=TASK_EXPLAIN, subject="score").passed
    assert not ta.score("   ", task=TASK_CHAT).passed


def test_an_unknown_task_is_an_error_not_a_pass():
    with pytest.raises(ValueError):
        ta.score("anything", task="SUMMARISE")


# --- the held-out slice --------------------------------------------------

def test_the_held_out_slice_shares_no_person_with_training():
    """Compared by profile, not by label: identical figures under a different
    name would still be leakage."""
    from scripts.ft.build_task_eval import HELD_OUT_SEED

    def fingerprint(person):
        if not person.onboarded:
            return ""          # no figures, nothing to leak
        return json.dumps({
            "profile": person.profile.model_dump(mode="json"),
            "goals": [g.model_dump(mode="json") for g in person.goals],
        }, sort_keys=True)

    trained = {fingerprint(p) for p in build_population(40)} - {""}
    held_out = build_population(12, seed=HELD_OUT_SEED, tag="ho")

    assert not [p.key for p in held_out
                if fingerprint(p) and fingerprint(p) in trained]


def test_a_tag_keeps_two_populations_distinguishable():
    """Without it both draws produce p00_broke, p01_debt_heavy, … and an
    overlap check compares labels that collide by construction."""
    from scripts.ft.build_task_eval import HELD_OUT_SEED

    trained = {p.key for p in build_population(8)}
    held_out = {p.key for p in build_population(8, seed=HELD_OUT_SEED, tag="ho")}

    assert not trained & held_out


def test_the_slice_covers_both_tasks_and_every_explain_subject():
    path = pathlib.Path("data/ft/task_eval.jsonl")
    if not path.exists():
        pytest.skip("run scripts/ft/build_task_eval.py first")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    tasks = {row["task"] for row in rows}
    subjects = {row["subject"] for row in rows if row["task"] == TASK_EXPLAIN}

    assert tasks == {TASK_EXPLAIN, TASK_CHAT}
    assert subjects == set(ta.SUBJECT_TERMS),         f"the grader knows subjects the slice never exercises: "         f"{set(ta.SUBJECT_TERMS) - subjects}"


def test_every_slice_row_carries_the_prompt_and_what_it_expects():
    path = pathlib.Path("data/ft/task_eval.jsonl")
    if not path.exists():
        pytest.skip("run scripts/ft/build_task_eval.py first")

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        assert row["payload"].startswith(f"TASK: {row['task']}")
        assert row["question"]
        if row["task"] == TASK_EXPLAIN:
            assert row["subject"] in ta.SUBJECT_TERMS


def test_the_slice_carries_no_gold_answers():
    """There is no single right wording, only a right shape. A gold answer here
    would quietly turn a shape check into a similarity check."""
    path = pathlib.Path("data/ft/task_eval.jsonl")
    if not path.exists():
        pytest.skip("run scripts/ft/build_task_eval.py first")

    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    assert "answer" not in row and "completion" not in row
