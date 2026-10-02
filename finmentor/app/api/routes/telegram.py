"""`/api/me/telegram` — connecting and disconnecting a Telegram account.

Only the web side is here. Redeeming a code happens inside Telegram and goes
through `app/api/telegram_link.py`, which both surfaces share.
"""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_user
from app.core import limits, security
from app.core.config import settings
from app.repositories import telegram_links as links_repo
from app.schemas.telegram import LinkCodeOut, TelegramStatusOut

router = APIRouter(prefix="/api/me/telegram", tags=["telegram"],
                   dependencies=[Depends(require_user)])


def _link_rate_limit(current_user: CurrentUser) -> None:
    """Per-user, on issuing a code.

    Each request writes a row and retires the previous one, so spamming this
    cannot produce a pile of live grants — but it can produce a pile of dead
    ones, and a table that grows without a ceiling is the same defect as
    `/simulations` had.
    """
    if not limits.allow("auth", f"tgcode:{current_user.id}",
                        settings.telegram_link_attempts_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many codes at once — wait a minute and try again",
        )


@router.get("", response_model=TelegramStatusOut)
def telegram_status(user: CurrentUser) -> TelegramStatusOut:
    return TelegramStatusOut(linked=user.telegram_id is not None,
                             telegram_id=user.telegram_id)


@router.post("/code", response_model=LinkCodeOut,
             dependencies=[Depends(_link_rate_limit)])
def create_code(user: CurrentUser, db: DbSession) -> LinkCodeOut:
    """Issue a code, retiring any this account already has.

    Refused when the account is already linked, because a code that cannot be
    redeemed is worse than no code: the user would type it into Telegram and
    get a refusal with no idea which of the two accounts was the problem.
    """
    if user.telegram_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this account already has a Telegram account connected",
        )

    links_repo.invalidate_outstanding(db, user.id)
    code, code_hash = security.new_link_code()
    link = links_repo.create(db, user_id=user.id, code_hash=code_hash)
    # `get_db` does not commit, so every write route owns its transaction.
    # Without this the code is handed to the user and then rolled back, and
    # the only symptom is that every code is refused.
    db.commit()

    deep_link = None
    if settings.telegram_bot_username:
        bare = security.normalise_link_code(code)
        deep_link = f"https://t.me/{settings.telegram_bot_username}?start=link_{bare}"

    expires_at = link.expires_at
    if expires_at.tzinfo is None:  # SQLite drops the offset
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return LinkCodeOut(code=code, expires_at=expires_at,
                       ttl_minutes=settings.telegram_link_ttl_minutes,
                       deep_link=deep_link)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def unlink(user: CurrentUser, db: DbSession) -> None:
    """Detach the Telegram account. The data stays on this account.

    There is no merge to undo: linking moved the bot's rows onto this account
    and deleted the row they came from, so unlinking is only the id. Anyone
    expecting their bot history to leave with it would be wrong, which is why
    the web copy says so before they click.

    Refused without an email, which cannot happen through this route — a
    caller holding an access token has one — but the check is here rather
    than relying on that, because `ck_users_has_an_identity` is the thing
    standing between this and a row nobody can sign in to.
    """
    if user.email is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this account has no other way to sign in",
        )
    if user.telegram_id is None:
        return
    links_repo.invalidate_outstanding(db, user.id)
    user.telegram_id = None
    db.commit()
