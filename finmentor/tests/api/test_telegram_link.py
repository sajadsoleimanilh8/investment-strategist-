"""Issuing, redeeming and revoking a Telegram link code.

The merge itself is `tests/unit/test_account_link.py`. This file is about the
credential: who can get one, how long it lives, how many times it works, and
what each refusal says.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.api import telegram_link as link_pipeline
from app.core import limits, security
from app.core.config import settings
from app.models.auth import TelegramLink
from app.repositories import telegram_links as links_repo
from app.repositories import users as users_repo
from tests.conftest import error_message


@pytest.fixture
def frozen_window(monkeypatch):
    """Stop the limiter's window rolling underneath a counting test.

    `limits._LocalCounter.hit` buckets by `int(time.time() // 60)`, a fixed
    wall-clock minute rather than a rolling one. Three requests that straddle
    a `:00` land in two buckets and the third is allowed, so any test that
    counts up to a limit fails whenever it happens to run across a minute
    boundary. Rare per run, certain over enough runs, and exactly the kind of
    intermittent failure lesson 2 in PROJECT_STATE is about.
    """
    monkeypatch.setattr(limits.time, "time", lambda: 1_800_000_000.0)


@pytest.fixture
def bot_user(db):
    user = users_repo.create(db, telegram_id=55_501)
    db.flush()
    return user


def issue(db, user) -> str:
    """A live code for `user`, as the route would have made it."""
    code, code_hash = security.new_link_code()
    links_repo.create(db, user_id=user.id, code_hash=code_hash)
    return code


# --- issuing -------------------------------------------------------------

def test_a_code_is_issued_and_round_trips(client, current_user, db):
    response = client.post("/api/me/telegram/code")

    assert response.status_code == 200
    body = response.json()
    assert body["ttl_minutes"] == settings.telegram_link_ttl_minutes
    assert links_repo.usable(db, security.hash_link_code(body["code"])) is not None


def test_the_code_is_never_stored_in_the_clear(client, db):
    code = client.post("/api/me/telegram/code").json()["code"]

    stored = db.query(TelegramLink).one().code_hash
    assert code not in stored
    assert security.normalise_link_code(code) not in stored
    assert stored == security.hash_link_code(code)


def test_issuing_again_retires_the_previous_code(client, db):
    first = client.post("/api/me/telegram/code").json()["code"]
    second = client.post("/api/me/telegram/code").json()["code"]

    assert first != second
    assert links_repo.usable(db, security.hash_link_code(first)) is None
    assert links_repo.usable(db, security.hash_link_code(second)) is not None


def test_the_deep_link_carries_the_bare_code(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_username", "FinMentorBot")

    body = client.post("/api/me/telegram/code").json()

    bare = security.normalise_link_code(body["code"])
    assert body["deep_link"] == f"https://t.me/FinMentorBot?start=link_{bare}"
    assert "-" not in body["deep_link"].split("link_")[1]


def test_no_bot_username_means_no_deep_link_rather_than_a_broken_one(client, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_username", "")

    body = client.post("/api/me/telegram/code").json()

    assert body["deep_link"] is None
    assert body["code"], "the code still works, it just has to be typed"


def test_an_already_linked_account_cannot_issue_a_code(client, current_user, db):
    current_user.telegram_id = 777
    db.flush()

    response = client.post("/api/me/telegram/code")

    assert response.status_code == 409


def test_issuing_needs_a_token(raw_client):
    assert raw_client.post("/api/me/telegram/code").status_code == 401
    assert raw_client.get("/api/me/telegram").status_code == 401
    assert raw_client.delete("/api/me/telegram").status_code == 401


def test_issuing_is_rate_limited(client, monkeypatch, frozen_window):
    monkeypatch.setattr(settings, "telegram_link_attempts_per_minute", 2)

    codes = [client.post("/api/me/telegram/code").status_code for _ in range(3)]

    assert codes == [200, 200, 429]


# --- status and unlinking ------------------------------------------------

def test_status_reports_both_states(client, current_user, db):
    assert client.get("/api/me/telegram").json() == {"linked": False,
                                                     "telegram_id": None}

    current_user.telegram_id = 4242
    db.flush()

    assert client.get("/api/me/telegram").json() == {"linked": True,
                                                     "telegram_id": 4242}


def test_unlinking_detaches_the_id_and_keeps_the_data(client, current_user, db):
    current_user.telegram_id = 4242
    db.flush()

    assert client.delete("/api/me/telegram").status_code == 204
    db.refresh(current_user)
    assert current_user.telegram_id is None
    assert users_repo.get(db, current_user.id) is not None


def test_unlinking_retires_outstanding_codes(client, current_user, db):
    code = issue(db, current_user)
    current_user.telegram_id = 4242
    db.flush()

    client.delete("/api/me/telegram")

    assert links_repo.usable(db, security.hash_link_code(code)) is None


def test_unlinking_when_not_linked_is_not_an_error(client):
    assert client.delete("/api/me/telegram").status_code == 204


# --- redeeming -----------------------------------------------------------

def test_redeeming_links_the_two_accounts(db, current_user):
    code = issue(db, current_user)

    user, report = link_pipeline.redeem(db, code=code, telegram_id=55_999)

    assert user.id == current_user.id
    assert current_user.telegram_id == 55_999
    assert report.moved_anything is False


@pytest.mark.parametrize("typed", [
    pytest.param(lambda code: code, id="as shown"),
    pytest.param(lambda code: code.lower(), id="lower case"),
    pytest.param(lambda code: code.replace("-", ""), id="no hyphens"),
    pytest.param(lambda code: code.replace("-", " "), id="spaces instead"),
    pytest.param(lambda code: f"  {code}\n", id="pasted with whitespace"),
])
def test_a_code_is_accepted_however_a_person_retypes_it(db, current_user, typed):
    code = issue(db, current_user)

    user, _ = link_pipeline.redeem(db, code=typed(code), telegram_id=55_999)

    assert user.id == current_user.id


def test_a_code_works_once(db, current_user):
    code = issue(db, current_user)
    link_pipeline.redeem(db, code=code, telegram_id=55_999)
    current_user.telegram_id = None  # isolate single use from already-linked
    db.flush()

    with pytest.raises(link_pipeline.CodeNotUsable):
        link_pipeline.redeem(db, code=code, telegram_id=55_999)


def test_an_expired_code_is_refused(db, current_user):
    code, code_hash = security.new_link_code()
    link = links_repo.create(db, user_id=current_user.id, code_hash=code_hash)
    link.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()

    with pytest.raises(link_pipeline.CodeNotUsable):
        link_pipeline.redeem(db, code=code, telegram_id=55_999)


def test_an_unknown_code_is_refused(db):
    with pytest.raises(link_pipeline.CodeNotUsable):
        link_pipeline.redeem(db, code="ZZZZ-ZZZZ-ZZZZ", telegram_id=55_999)


def test_every_bad_code_gets_the_same_sentence(db, current_user):
    """Expired, spent and unknown are one refusal on purpose.

    The person holding a bad code cannot act on the difference, and telling
    someone guessing that a code existed but expired is telling them their
    guess was right.
    """
    spent = issue(db, current_user)
    links_repo.spend(db, links_repo.usable(db, security.hash_link_code(spent)))

    messages = set()
    for code in (spent, "ZZZZ-ZZZZ-ZZZZ"):
        with pytest.raises(link_pipeline.CodeNotUsable) as raised:
            link_pipeline.redeem(db, code=code, telegram_id=55_999)
        messages.add(raised.value.message)

    assert len(messages) == 1


def test_a_refusal_never_repeats_the_code_back(db, current_user):
    """The reply lands in a chat log that outlives the code's ten minutes."""
    code = issue(db, current_user)
    links_repo.spend(db, links_repo.usable(db, security.hash_link_code(code)))

    with pytest.raises(link_pipeline.LinkRefused) as raised:
        link_pipeline.redeem(db, code=code, telegram_id=55_999)

    assert security.normalise_link_code(code) not in raised.value.message
    assert code not in raised.value.message


def test_redeeming_the_same_code_twice_from_the_same_chat_is_idempotent(db, current_user):
    """A user who taps the deep link twice should not see a failure."""
    code = issue(db, current_user)
    link_pipeline.redeem(db, code=code, telegram_id=55_999)

    second = issue(db, current_user)
    user, report = link_pipeline.redeem(db, code=second, telegram_id=55_999)

    assert user.id == current_user.id
    assert report.moved_anything is False


def test_a_code_for_an_account_linked_elsewhere_is_refused(db, current_user):
    current_user.telegram_id = 111
    db.flush()
    code = issue(db, current_user)

    with pytest.raises(link_pipeline.AlreadyLinked) as raised:
        link_pipeline.redeem(db, code=code, telegram_id=222)

    assert current_user.telegram_id == 111, "the existing link is untouched"
    assert "Disconnect" in raised.value.message


def test_a_telegram_account_on_another_web_account_is_refused_not_merged(db, current_user):
    """Two web accounts is a different operation with a different consent.

    Merging them would have to pick which email survives, and that is not a
    guess worth making on someone's behalf.
    """
    other = users_repo.create_web_user(db, email="other@finmentor.local",
                                       password_hash="x")
    other.telegram_id = 333
    db.flush()
    code = issue(db, current_user)

    with pytest.raises(link_pipeline.AlreadyLinked):
        link_pipeline.redeem(db, code=code, telegram_id=333)

    assert users_repo.get(db, other.id) is not None
    assert current_user.telegram_id is None


def test_a_bot_only_row_is_merged(db, current_user, bot_user):
    """The normal case: the bot row has no email, so it is not an account."""
    code = issue(db, current_user)

    user, _ = link_pipeline.redeem(db, code=code,
                                   telegram_id=bot_user.telegram_id)

    assert user.id == current_user.id
    assert users_repo.get(db, bot_user.id) is None


def test_a_refused_link_still_spends_the_code(db, current_user):
    """A refusal about the accounts is not a reason to leave the code live.

    Otherwise the same wrong attempt can be retried forever and the limiter
    never sees it as a repeat.
    """
    current_user.telegram_id = 111
    db.flush()
    code = issue(db, current_user)

    with pytest.raises(link_pipeline.AlreadyLinked):
        link_pipeline.redeem(db, code=code, telegram_id=222)

    assert links_repo.usable(db, security.hash_link_code(code)) is None


def test_redeeming_is_rate_limited_per_telegram_account(db, current_user,
                                                       monkeypatch, frozen_window):
    monkeypatch.setattr(settings, "telegram_link_attempts_per_minute", 3)

    for _ in range(3):
        with pytest.raises(link_pipeline.CodeNotUsable):
            link_pipeline.redeem(db, code="ZZZZ-ZZZZ-ZZZZ", telegram_id=55_999)

    with pytest.raises(link_pipeline.RedeemingTooFast):
        link_pipeline.redeem(db, code="ZZZZ-ZZZZ-ZZZZ", telegram_id=55_999)


def test_the_limit_is_per_account_not_global(db, current_user, monkeypatch,
                                            frozen_window):
    """One person guessing must not lock everybody else out."""
    monkeypatch.setattr(settings, "telegram_link_attempts_per_minute", 2)
    for _ in range(2):
        with pytest.raises(link_pipeline.CodeNotUsable):
            link_pipeline.redeem(db, code="ZZZZ-ZZZZ-ZZZZ", telegram_id=1)

    code = issue(db, current_user)
    user, _ = link_pipeline.redeem(db, code=code, telegram_id=2)

    assert user.id == current_user.id


def test_redemption_uses_the_bucket_that_fails_closed(db, current_user, monkeypatch):
    """Attaching an account is an authentication boundary, not a cost centre.

    Decision 7: `ask` fails open because losing the limiter costs money, and
    `auth` fails closed because losing it *is* the attack. Linking belongs on
    the second side of that line, so this asserts the bucket name rather than
    trusting the call site to keep using it.
    """
    seen = []
    monkeypatch.setattr(limits, "allow",
                        lambda bucket, key, limit: seen.append(bucket) or True)
    monkeypatch.setattr(link_pipeline.limits, "allow", limits.allow)

    with pytest.raises(link_pipeline.CodeNotUsable):
        link_pipeline.redeem(db, code="ZZZZ-ZZZZ-ZZZZ", telegram_id=55_999)

    assert seen == ["auth"]


# --- the code itself -----------------------------------------------------

def test_the_alphabet_excludes_every_confusable_character():
    """O/0, I/1/L and U/V are the pairs people mistype off a screen."""
    for character in "01OILUV":
        assert character not in security.LINK_CODE_ALPHABET


def test_the_log_scrubber_covers_the_whole_alphabet():
    """A code must not survive in a log line because the alphabet grew.

    `_LINK_CODE` is a hand-written character class. If a symbol is added to
    `LINK_CODE_ALPHABET` and not to the pattern, codes containing it stop
    being redacted — silently, and only sometimes.
    """
    from app.core.logging import SECRET_MASK, scrub_text

    for character in security.LINK_CODE_ALPHABET:
        code = security.format_link_code(character * security.LINK_CODE_LENGTH)
        assert scrub_text(code) == SECRET_MASK, f"{character} is not covered"


def test_an_issued_code_is_redacted_in_both_forms(client):
    from app.core.logging import SECRET_MASK, scrub_text

    body = client.post("/api/me/telegram/code").json()
    bare = security.normalise_link_code(body["code"])

    assert scrub_text(f"/link {body['code']} failed") == f"/link {SECRET_MASK} failed"
    assert scrub_text(f"start payload link_{bare}") == f"start payload {SECRET_MASK}"
