"""All 12 /learn topics must be complete — no silent gaps in curated content."""
import pytest

from app.services.education_engine import (
    QUESTIONS_PER_TOPIC, QUIZ_FIELDS, REQUIRED_FIELDS, TOPICS, get_topic,
    list_topics, score_quiz,
)

SPEC_TOPIC_KEYS = {
    "budgeting", "emergency_fund", "savings_rate", "inflation", "risk", "volatility",
    "diversification", "compound_growth", "time_horizon", "debt", "opportunity_cost",
    "investment_basics",
}
PROSE_FIELDS = ("title", "explanation", "example", "common_mistake")
#: titles are a couple of words; the prose fields must actually explain something
MIN_LENGTH = {"title": 3, "explanation": 120, "example": 80, "common_mistake": 60}
#: English typography, not another script — em dashes and smart quotes are fine
ALLOWED_NON_ASCII = set("—–’‘“”…")


def is_english_text(text: str) -> bool:
    return all(ch.isascii() or ch in ALLOWED_NON_ASCII for ch in text)


def test_the_twelve_spec_topics_are_present():
    assert set(TOPICS) == SPEC_TOPIC_KEYS
    assert len(TOPICS) == 12


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_every_topic_has_every_required_field(key):
    topic = TOPICS[key]
    missing = [field for field in REQUIRED_FIELDS if not topic.get(field)]
    assert missing == [], f"{key} is missing {missing}"


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_prose_is_real_english_content(key):
    topic = TOPICS[key]
    for field in PROSE_FIELDS:
        text = topic[field]
        assert len(text) >= MIN_LENGTH[field], f"{key}.{field} is too short to be real content"
        assert is_english_text(text), f"{key}.{field} contains non-English characters"
        assert "TODO" not in text


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_no_legacy_localised_fields_remain(key):
    assert not [field for field in TOPICS[key] if field.endswith(("_fa", "_en"))]


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_every_quiz_has_the_same_number_of_questions(key):
    """A fixed count is what makes a percentage mean the same thing on every
    topic, and what stops a topic quietly going back to one question."""
    assert len(TOPICS[key]["questions"]) == QUESTIONS_PER_TOPIC


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_every_question_is_answerable(key):
    for index, question in enumerate(TOPICS[key]["questions"]):
        where = f"{key}[{index}]"
        assert all(field in question for field in QUIZ_FIELDS), where
        assert question["question"].endswith("?"), where
        assert len(question["options"]) >= 3, where
        assert len(set(question["options"])) == len(question["options"]),             f"duplicate options in {where}"
        assert 0 <= question["answer_idx"] < len(question["options"]), where
        assert all(is_english_text(option) for option in question["options"]), where
        assert is_english_text(question["question"]), where


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_every_question_explains_itself(key):
    """`why` is per question, not per topic.

    The result used to return the topic's `common_mistake` whatever the user
    got wrong, which is a sentence about the topic rather than about the
    question they just missed.
    """
    for index, question in enumerate(TOPICS[key]["questions"]):
        why = question["why"]
        assert why and why.strip() == why, f"{key}[{index}]"
        assert len(why) > 40, f"{key}[{index}]: too short to explain anything"
        assert is_english_text(why), f"{key}[{index}]"


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_no_question_is_repeated_within_a_topic(key):
    prompts = [q["question"] for q in TOPICS[key]["questions"]]
    assert len(set(prompts)) == len(prompts)


def test_no_question_is_repeated_across_topics():
    prompts = [q["question"] for topic in TOPICS.values()
               for q in topic["questions"]]
    assert len(set(prompts)) == len(prompts)


@pytest.mark.parametrize("key", sorted(SPEC_TOPIC_KEYS))
def test_the_answer_is_not_always_in_the_same_position(key):
    """Three questions all answered "b" is a quiz you can pass without reading.

    Asserted per topic rather than globally, because a user sees one topic at
    a time and that is where the pattern would be learnable.
    """
    positions = [q["answer_idx"] for q in TOPICS[key]["questions"]]
    assert len(set(positions)) > 1, f"{key}: every answer is option {positions[0]}"


def test_list_topics_carries_the_key_and_full_content():
    topics = list_topics()
    assert len(topics) == 12
    assert {t["key"] for t in topics} == SPEC_TOPIC_KEYS
    assert all(all(t.get(field) for field in REQUIRED_FIELDS) for t in topics)


def test_get_topic_round_trip_and_miss():
    topic = get_topic("compound_growth")
    assert topic["key"] == "compound_growth"
    assert topic["title"] == "Compound Growth"
    assert get_topic("nope") is None


def test_education_content_pulls_in_no_ai_module():
    """The content is curated, not generated — the module imports no AI layer.

    Checked statically: a `sys.modules` probe would only pass while no other
    test had already imported `app.ai`, which makes it a test-order accident
    rather than an invariant.
    """
    import ast
    import pathlib

    module = pathlib.Path(app_education_engine_path())
    tree = ast.parse(module.read_text(encoding="utf-8"))

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [name for name in imported if name.startswith("app.ai")]


def app_education_engine_path() -> str:
    import app.services.education_engine as engine

    return engine.__file__
