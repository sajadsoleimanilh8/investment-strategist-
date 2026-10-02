"""Redeeming a Telegram link code: the shared pipeline both surfaces call.

The bot is the only caller today. It lives here anyway, next to `ask.py` and
for the same reason that one does: the limiter and the refusals belong with
the operation they protect, not on an HTTP route that happens to be one way in
(decision 6 in `docs/PROJECT_STATE.md`). `/ask` was rate limited while the bot
calling the same pipeline was not, and that is the mistake this placement
avoids repeating.

Creating a code is genuinely an HTTP notion — it needs an authenticated
browser session — so it stays in `app/api/routes/telegram.py`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import limits, security
from app.core.config import settings
from app.models.user import User
from app.repositories import account_link
from app.repositories import telegram_links as links_repo
from app.repositories import users as users_repo


class LinkRefused(Exception):
    """The code will not be redeemed, and the caller should say why.

    Carries a status for the same reason `AskRefused` does: one of the two
    surfaces speaks HTTP and the other shows `message` and drops the number.
    """

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CodeNotUsable(LinkRefused):
    status_code = 400


class AlreadyLinked(LinkRefused):
    status_code = 409


class RedeemingTooFast(LinkRefused):
    status_code = 429


#: One sentence for "no such code", "already used" and "expired". The person
#: holding a bad code cannot act on the difference, and spelling it out tells
#: someone guessing which guesses were close.
BAD_CODE = "That code is not valid any more. Generate a fresh one on the web and try again."
ALREADY_LINKED = (
    "This Telegram account is already connected to a FinMentor account. "
    "Disconnect it on the web first if you want to connect a different one."
)
TARGET_TAKEN = (
    "That web account is already connected to a different Telegram account. "
    "Disconnect it on the web first."
)
TOO_FAST = "That is a lot of attempts. Wait a minute and try again."


def redeem(db: Session, *, code: str, telegram_id: int) -> tuple[User, account_link.MergeReport]:
    """Attach `telegram_id` to the account the code names, merging the two rows.

    Returns the surviving user and what the merge did, so the caller can tell
    the person which of their things moved. Raises `LinkRefused` for every
    outcome that is not a link.

    Fails *closed* when the limiter is unavailable is not a choice available
    here: `limits.allow` already decides that per bucket, and this uses the
    `auth` bucket deliberately. Attaching an account is an authentication
    boundary, not a cost centre (decision 7).
    """
    if not limits.allow("auth", f"tglink:{telegram_id}",
                        settings.telegram_link_attempts_per_minute):
        raise RedeemingTooFast(TOO_FAST)

    link = links_repo.usable(db, security.hash_link_code(code))
    if link is None:
        raise CodeNotUsable(BAD_CODE)

    target = users_repo.get(db, link.user_id)
    if target is None:  # pragma: no cover - the FK cascade makes this unreachable
        raise CodeNotUsable(BAD_CODE)

    # The code is spent whatever happens next. A refusal below is about the
    # state of the two accounts, not about the code, and leaving it live would
    # let the same wrong attempt be retried without the limiter noticing it is
    # the same code.
    links_repo.spend(db, link)
    links_repo.invalidate_outstanding(db, target.id)

    if target.telegram_id is not None:
        if target.telegram_id == telegram_id:
            return target, account_link.MergeReport()
        raise AlreadyLinked(TARGET_TAKEN)

    existing = users_repo.get_by_telegram_id(db, telegram_id)
    if existing is not None and existing.id != target.id:
        if existing.email is not None:
            # Not a bot-only row: it is somebody's web account, possibly this
            # person's second one. Merging two web accounts is a different
            # operation with a different consent conversation, and guessing
            # which email survives is not a guess worth making.
            raise AlreadyLinked(ALREADY_LINKED)
        report = account_link.merge(db, into=target, source=existing)
        return target, report

    target.telegram_id = telegram_id
    db.flush()
    return target, account_link.MergeReport()
