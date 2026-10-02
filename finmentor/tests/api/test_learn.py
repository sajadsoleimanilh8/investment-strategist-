"""/api/learn — the 12 curated topics, their quizzes, and the progress they write.

The content is static and human-written; the only moving part is progress, and
the only reason it matters is that completing topics raises the
`financial_knowledge` band in Financial DNA. That link is what these assert.
"""
import pytest

from app.services.education_engine import get_topic, list_topics


def right(key: str) -> list[int]:
    """Every answer correct, in order."""
    return [q["answer_idx"] for q in get_topic(key)["questions"]]


def all_wrong(key: str) -> list[int]:
    return [(q["answer_idx"] + 1) % len(q["options"])
            for q in get_topic(key)["questions"]]


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
    assert [q["question"] for q in body["questions"]] ==         [q["question"] for q in topic["questions"]]
    assert [q["options"] for q in body["questions"]] ==         [q["options"] for q in topic["questions"]]


def test_a_single_topic_also_withholds_the_answer(client, user_id):
    assert "answer_idx" not in client.get("/api/learn/diversification").text


def test_a_topic_never_leaks_an_explanation_before_it_is_answered(client, user_id):
    """`why` is the giveaway: it names the right option in prose.

    The one-question version had nothing to leak here, because the only
    explanation was the topic's `common_mistake`, which is safe to show. A
    per-question `why` is not, and it travels in the result instead.
    """
    body = client.get("/api/learn/diversification").text
    for question in get_topic("diversification")["questions"]:
        assert question["why"] not in body
    assert "why" not in client.get("/api/learn/diversification").json()["questions"][0]


def test_an_unknown_topic_is_404(client, user_id):
    assert client.get("/api/learn/how-to-get-rich-quick").status_code == 404


@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_every_topic_is_readable(client, user_id, topic):
    assert client.get(f"/api/learn/{topic['key']}").status_code == 200


# --- the quiz ------------------------------------------------------------

def test_every_answer_right_scores_100(client, user_id):
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answers": right("budgeting")}).json()

    assert body["score"] == 100
    assert body["correct_count"] == body["total"] == 3
    assert all(answer["correct"] for answer in body["answers"])
    assert body["completed"] is True


def test_every_answer_wrong_still_marks_the_topic_read(client, user_id):
    """A quiz here is a comprehension check, not an exam. Being shown why is
    the lesson, so it counts as completed either way -- the decision the
    one-question version made, kept."""
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answers": all_wrong("budgeting")}).json()

    assert body["score"] == 0
    assert body["correct_count"] == 0
    assert body["completed"] is True
    assert not any(answer["correct"] for answer in body["answers"])


def test_a_partly_right_quiz_scores_in_between(client, user_id):
    """What a score means changed: it is the percentage, not 0 or 100."""
    answers = right("budgeting")
    answers[1] = (answers[1] + 1) % 3

    body = client.post("/api/learn/budgeting/quiz", json={"answers": answers}).json()

    assert body["score"] == 67
    assert body["correct_count"] == 2
    assert [a["correct"] for a in body["answers"]] == [True, False, True]


def test_the_result_names_the_right_option_for_each_question(client, user_id):
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answers": all_wrong("budgeting")}).json()

    expected = [q["answer_idx"] for q in get_topic("budgeting")["questions"]]
    assert [answer["correct_idx"] for answer in body["answers"]] == expected


def test_each_question_explains_itself(client, user_id):
    """The old result returned the topic's `common_mistake` whatever you got
    wrong, which is a sentence about the topic and not about the question."""
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answers": all_wrong("budgeting")}).json()

    whys = [answer["why"] for answer in body["answers"]]
    assert whys == [q["why"] for q in get_topic("budgeting")["questions"]]
    assert len(set(whys)) == 3, "three questions, three different explanations"


def test_the_topic_note_still_comes_back(client, user_id):
    body = client.post("/api/learn/budgeting/quiz",
                       json={"answers": right("budgeting")}).json()

    assert body["common_mistake"] == get_topic("budgeting")["common_mistake"]


def test_an_option_that_does_not_exist_is_422(client, user_id):
    answers = right("budgeting")
    answers[0] = 9

    response = client.post("/api/learn/budgeting/quiz", json={"answers": answers})

    assert response.status_code == 422
    assert "question 1" in response.text


@pytest.mark.parametrize("answers", [
    pytest.param([0], id="too few"),
    pytest.param([0, 0, 0, 0], id="too many"),
])
def test_the_wrong_number_of_answers_is_refused(client, user_id, answers):
    """Scoring a partial submission would record a number nobody earned:
    padding the gaps invents a failure, and scoring only what arrived would
    make one answer worth 100%."""
    response = client.post("/api/learn/budgeting/quiz", json={"answers": answers})

    assert response.status_code == 422
    assert "3 questions" in response.text


def test_an_empty_submission_is_refused(client, user_id):
    assert client.post("/api/learn/budgeting/quiz",
                       json={"answers": []}).status_code == 422


def test_a_quiz_on_an_unknown_topic_is_404(client, user_id):
    assert client.post("/api/learn/nonsense/quiz",
                       json={"answers": [0, 0, 0]}).status_code == 404


@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_every_topic_can_be_completed(client, user_id, topic):
    """Every one of the twelve, end to end, scoring full marks."""
    body = client.post(f"/api/learn/{topic['key']}/quiz",
                       json={"answers": right(topic["key"])}).json()

    assert body["score"] == 100, topic["key"]


# --- progress ------------------------------------------------------------

def test_progress_shows_up_in_the_listing(client, user_id):
    client.post("/api/learn/budgeting/quiz", json={"answers": right("budgeting")})

    body = client.get("/api/learn").json()
    entry = next(item for item in body["items"] if item["key"] == "budgeting")

    assert entry["completed"] is True
    assert entry["quiz_score"] == 100
    assert body["completed_count"] == 1


def test_a_retake_keeps_the_better_score(client, user_id):
    """A lesson learned is not unlearned by a careless second attempt."""
    client.post("/api/learn/budgeting/quiz", json={"answers": right("budgeting")})
    client.post("/api/learn/budgeting/quiz", json={"answers": all_wrong("budgeting")})

    entry = next(item for item in client.get("/api/learn").json()["items"]
                 if item["key"] == "budgeting")
    assert entry["quiz_score"] == 100


def test_a_retake_does_not_create_a_second_row(client, db, user_id):
    from app.repositories import education as education_repo

    for _ in range(3):
        client.post("/api/learn/budgeting/quiz", json={"answers": [0, 0, 0]})

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
