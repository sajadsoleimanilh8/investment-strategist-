"""The auth and /ask rate limiters, exercised for real.

These are disabled for the rest of the suite (`AUTH_RATE_LIMIT_PER_MINUTE=0` in
conftest) because nine hundred tests arrive from one client address and would
trip a limit meant for a human. So this file is where they are actually
verified: the limits are turned back on per-test, the counters are cleared
either side, and nothing here changes the global configuration.

Two properties matter, and the second is the one that would hurt in production:

* over the limit is a 429
* **Redis being down is not an outage.** The limiter logs and allows the
  request. A cache failure taking the whole API with it would be a worse
  incident than the brute-force it exists to slow down.
"""
import pytest

from app.core import security
from app.core.config import settings
from tests.conftest import error_message

LIMIT = 3
#: What `request.client.host` is under TestClient. The limiter keys on it, so
#: the tests have to clear exactly the key the app will write.
TEST_CLIENT_IP = "testclient"

EMAIL = "limiter@example.com"
PASSWORD = "a-long-enough-password"


def redis_client():
    """A live Redis, or None. The limiter's own import, from its own URL."""
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5)
        client.ping()
        return client
    except Exception:
        return None


@pytest.fixture
def limiter(monkeypatch):
    """Turn the limits on for one test, and leave no counter behind.

    Skips rather than fails without Redis: with no counter store the limiter is
    *designed* to allow everything, so asserting a 429 would be asserting the
    opposite of the intended behaviour.
    """
    client = redis_client()
    if client is None:
        pytest.skip("no Redis; the limiter fails open by design and cannot be observed")

    keys = [
        security.rate_limit_key(TEST_CLIENT_IP, "auth"),
        *[security.rate_limit_key(str(user_id), "ask") for user_id in range(1, 20)],
    ]
    client.delete(*keys)

    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", LIMIT)
    monkeypatch.setattr(settings, "ask_rate_limit_per_minute", LIMIT)
    try:
        yield client
    finally:
        client.delete(*keys)


def signup(client, index: int):
    return client.post("/api/auth/signup",
                       json={"email": f"user{index}@example.com", "password": PASSWORD})


# --- the limit bites -----------------------------------------------------

def test_requests_up_to_the_limit_are_served(raw_client, limiter):
    for index in range(LIMIT):
        assert signup(raw_client, index).status_code == 201, f"request {index + 1} refused"


def test_the_request_after_the_limit_is_429(raw_client, limiter):
    for index in range(LIMIT):
        signup(raw_client, index)

    refused = signup(raw_client, LIMIT)

    assert refused.status_code == 429
    assert "too many attempts" in error_message(refused)


def test_it_stays_refused_rather_than_letting_the_next_one_through(raw_client, limiter):
    """An off-by-one that resets the counter would make the limit decorative."""
    for index in range(LIMIT + 3):
        signup(raw_client, index)

    assert signup(raw_client, 99).status_code == 429


def test_login_and_signup_share_one_budget(raw_client, limiter):
    """Both are guessing surfaces for the same attacker from the same address,
    so they draw on one counter rather than one each."""
    signup(raw_client, 0)
    signup(raw_client, 1)

    assert raw_client.post("/api/auth/login",
                           json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    refused = raw_client.post("/api/auth/login",
                              json={"email": EMAIL, "password": PASSWORD})

    assert refused.status_code == 429


def test_a_refused_request_never_reaches_the_database(raw_client, limiter, db):
    """429 before the handler: the point is to stop the work, not report it."""
    from app.repositories import users as users_repo

    for index in range(LIMIT):
        signup(raw_client, index)
    signup(raw_client, 777)

    assert users_repo.get_by_email(db, "user777@example.com") is None


def test_the_counter_carries_an_expiry_so_the_lockout_is_temporary(raw_client, limiter):
    """Without a TTL the first burst would lock that address out permanently."""
    signup(raw_client, 0)

    ttl = limiter.ttl(security.rate_limit_key(TEST_CLIENT_IP, "auth"))

    assert 0 < ttl <= 60


# --- the /ask limiter is per user, not per address -----------------------

def test_ask_is_limited_per_user(raw_client, limiter, db, monkeypatch):
    from app.repositories import users as users_repo
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    tokens = signup(raw_client, 0).json()
    user_id = security.decode_token(tokens["access_token"])
    seed_demo_user(db, user=users_repo.get(db, user_id), period="2026-09")
    db.commit()

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    payload = {"user_id": user_id, "question": "how am I doing?"}

    codes = [raw_client.post("/api/ai/ask", json=payload, headers=headers).status_code
             for _ in range(LIMIT + 1)]

    assert codes[-1] == 429
    assert codes[:LIMIT] == [200] * LIMIT


def test_the_ask_refusal_is_worded_for_a_person(raw_client, limiter, db, monkeypatch):
    from app.repositories import users as users_repo
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    tokens = signup(raw_client, 0).json()
    user_id = security.decode_token(tokens["access_token"])
    seed_demo_user(db, user=users_repo.get(db, user_id), period="2026-09")
    db.commit()

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    payload = {"user_id": user_id, "question": "how am I doing?"}
    for _ in range(LIMIT + 1):
        response = raw_client.post("/api/ai/ask", json=payload, headers=headers)

    assert response.status_code == 429
    assert "give it a moment" in error_message(response)


# --- failure modes -------------------------------------------------------

def test_a_limit_of_zero_disables_the_limiter(raw_client, monkeypatch):
    """What the rest of the suite relies on."""
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 0)

    codes = [signup(raw_client, index).status_code for index in range(6)]

    assert 429 not in codes


def test_an_unreachable_redis_allows_the_request(raw_client, monkeypatch, caplog):
    """The behaviour that matters most. A cache outage must not become an API
    outage — losing the limiter is a smaller problem than losing signup."""
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")

    codes = [signup(raw_client, index).status_code for index in range(4)]

    assert 429 not in codes
    assert any("rate limiter unavailable" in record.message for record in caplog.records)


def test_the_limiter_never_leaks_a_credential_into_its_key():
    """The key is an address or a user id — never an email, never a password."""
    key = security.rate_limit_key("198.51.100.4", "auth")

    assert key == "rl:auth:198.51.100.4"
    assert "@" not in key
