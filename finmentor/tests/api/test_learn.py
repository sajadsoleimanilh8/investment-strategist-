"""/api/learn — the 12 curated topics, their quizzes, and the progress they write.

The content is static and human-written; the only moving part is progress, and
the only reason it matters is that completing topics raises the
`financial_knowledge` band in Financial DNA. That link is what these assert.
"""
import pytest

from app.services.education_engine import get_topic, list_topics


@pytest.fixture
def user_id(client, current_user) -> int:
    """Progress is keyed on the *signed-in* user, not a path parameter."""
    return current_user.id


def test_every_topic_is_listed(client, user_id):
    body = client.get("/api/learn").json()

    assert len(body["items"]) == len(list_topics()) == 12
    assert body["completed_count"] == 0
    assert all(item["title"] and item["key"] for item in body["items"])


def test_the_listing_never_leaks_a_quiz_answer(client, user_id):
    """The list is safe to fetch eagerly, so it must not spoil anything."""
    body = client.get("/api/learn").text

    assert "answer_idx" not in body


def test_a_topic_returns_its_full_content(client, user_id):
    body = client.get("/api/learn/diversification").json()
    topic = get_topic("diversification")

    assert body["explanation"] == topic["explanation"]
    assert body["example"] == topic["example"]
    assert body["common_mistake"] == topic["common_mistake"]
    assert body["quiz"]["question"] == topic["quiz"]["question"]
    assert body["quiz"]["options"] == topic["quiz"]["options"]


def test_a_single_topic_also_withholds_the_answer(client, user_id):
    assert "answer_idx" not in client.get("/api/learn/diversification").text


def test_an_unknown_topic_is_404(client, user_id):
    assert client.get("/api/learn/how-to-get-rich-quick").status_code == 404


@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_every_topic_is_readable(client, user_id, topic):
    assert client.get(f"/api/learn/{topic['key']}").status_code == 200


# --- the quiz ------------------------------------------------------------

def test_a_correct_answer_scores_100(client, user_id):
    topic = get_topic("budgeting")
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answer_idx": topic["quiz"]["answer_idx"]}).json()

    assert body["correct"] is True
    assert body["score"] == 100
    assert body["completed"] is True


def test_a_wrong_answer_still_marks_the_topic_read(client, user_id):
    """A one-question quiz is a comprehension check, not an exam. Being shown
    the answer is the lesson, so it counts as completed either way."""
    topic = get_topic("budgeting")
    wrong = (topic["quiz"]["answer_idx"] + 1) % len(topic["quiz"]["options"])

    body = client.post("/api/learn/budgeting/quiz", json={"answer_idx": wrong}).json()

    assert body["correct"] is False
    assert body["score"] == 0
    assert body["completed"] is True
    assert body["correct_idx"] == topic["quiz"]["answer_idx"]


def test_the_result_explains_rather_than_just_marking(client, user_id):
    body = client.post("/api/learn/budgeting/quiz", json={"answer_idx": 0}).json()

    assert body["explanation"] == get_topic("budgeting")["common_mistake"]


def test_an_option_that_does_not_exist_is_422(client, user_id):
    assert client.post("/api/learn/budgeting/quiz",
                       json={"answer_idx": 9}).status_code == 422


def test_a_quiz_on_an_unknown_topic_is_404(client, user_id):
    assert client.post("/api/learn/nonsense/quiz",
                       json={"answer_idx": 0}).status_code == 404


# --- progress ------------------------------------------------------------

def test_progress_shows_up_in_the_listing(client, user_id):
    topic = get_topic("budgeting")
    client.post("/api/learn/budgeting/quiz",
                json={"answer_idx": topic["quiz"]["answer_idx"]})

    body = client.get("/api/learn").json()
    entry = next(item for item in body["items"] if item["key"] == "budgeting")

    assert entry["completed"] is True
    assert entry["quiz_score"] == 100
    assert body["completed_count"] == 1


def test_a_retake_keeps_the_better_score(client, user_id):
    """A lesson learned is not unlearned by a careless second attempt."""
    topic = get_topic("budgeting")
    client.post("/api/learn/budgeting/quiz",
                json={"answer_idx": topic["quiz"]["answer_idx"]})
    client.post("/api/learn/budgeting/quiz",
                json={"answer_idx": (topic["quiz"]["answer_idx"] + 1) % 3})

    entry = next(item for item in client.get("/api/learn").json()["items"]
                 if item["key"] == "budgeting")
    assert entry["quiz_score"] == 100


def test_a_retake_does_not_create_a_second_row(client, db, user_id):
    from app.repositories import education as education_repo

    for _ in range(3):
        client.post("/api/learn/budgeting/quiz", json={"answer_idx": 0})

    assert len(education_repo.list_for_user(db, user_id)) == 1


def test_completing_topics_raises_the_knowledge_band(client, db, user_id, monkeypatch):
    """The whole reason progress is persisted: Financial DNA reads it."""
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    demo_id = seed_demo_user(db, period="2026-09")

    before = client.get(f"/api/health/{demo_id}/dna").json()["financial_knowledge"]
    assert before == "Beginner"

    from app.repositories import education as education_repo
    for topic in list_topics()[:4]:
        education_repo.record_quiz(db, demo_id, topic["key"], score=100, completed=True)
    db.commit()

    after = client.get(f"/api/health/{demo_id}/dna").json()["financial_knowledge"]
    assert after == "Intermediate"


# --- no model on this path ----------------------------------------------

def test_reading_a_topic_never_calls_the_model(client, user_id, monkeypatch):
    """Curated content, verbatim. An explanation of compound interest that
    drifts is worse than no explanation."""
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("the learn path reached the LLM")

    monkeypatch.setattr("app.ai.synthesizer.explain", explode)
    monkeypatch.setattr("app.ai.synthesizer.chat", explode)

    assert client.get("/api/learn/diversification").status_code == 200
    assert client.get("/api/learn").status_code == 200
