"""All 12 /learn topics must be complete — no silent gaps in curated content."""
import pytest

from app.services.education_engine import (
    QUIZ_FIELDS, REQUIRED_FIELDS, TOPICS, get_topic, list_topics,
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
def test_every_quiz_is_answerable(key):
    quiz = TOPICS[key]["quiz"]
    assert all(field in quiz for field in QUIZ_FIELDS)
    assert quiz["question"].endswith("?")
    assert len(quiz["options"]) >= 3
    assert len(set(quiz["options"])) == len(quiz["options"]), "duplicate options"
    assert 0 <= quiz["answer_idx"] < len(quiz["options"])
    assert all(is_english_text(option) for option in quiz["options"])
    assert is_english_text(quiz["question"])


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
