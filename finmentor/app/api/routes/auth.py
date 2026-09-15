"""Web authentication (spec section 7).

Signup, login, refresh, logout, me. The Telegram bot does not use any of this —
it resolves a user from the update and calls the pipeline in-process — so these
routes exist purely for the browser client.

Refresh tokens rotate: `/refresh` issues a new pair and the old refresh token
is simply no longer the one the client holds. That does not revoke it (there is
no token store yet), but it means a leaked token is only useful until the real
user refreshes, and it costs nothing.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, auth_rate_limit
from app.core import security
from app.core.config import settings
from app.core.mailer import Message, send_quietly
from app.repositories import password_resets as resets_repo
from app.repositories import profiles as profiles_repo
from app.models.user import User
from app.repositories import users as users_repo
from app.schemas.auth import (
    ForgotPasswordIn, LoginIn, MeOut, RefreshIn, ResetPasswordIn, SignupIn, TokenPair,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: One message for "no such email" and "wrong password". Telling them apart
#: hands an attacker a free account-existence oracle.
BAD_CREDENTIALS = "email or password is incorrect"

#: The same sentence whether or not the address is registered, for the same
#: reason. It is deliberately about the *address*, not the account.
RESET_SENT = "if that address has an account, a reset link is on its way"

#: One refusal for a token that never existed, one that was already spent, and
#: one that expired. The difference is not something the holder of a bad link
#: can act on, and each distinction is a thing worth learning by guessing.
BAD_RESET = "that reset link is no longer valid. Ask for a new one."


def _pair(user: User) -> TokenPair:
    """A fresh pair, stamped with the user's current token version.

    Takes the row rather than the id so the version cannot be forgotten: a
    pair minted without it would be born already invalid.
    """
    return TokenPair(
        access_token=security.create_access_token(user.id, user.token_version),
        refresh_token=security.create_refresh_token(user.id, user.token_version),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/signup", response_model=TokenPair,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(auth_rate_limit)])
def signup(payload: SignupIn, db: DbSession) -> TokenPair:
    email = users_repo.normalise_email(payload.email)
    if users_repo.get_by_email(db, email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "that email is already registered")

    user = users_repo.create_web_user(
        db, email=email, password_hash=security.hash_password(payload.password)
    )
    try:
        db.commit()
    except IntegrityError:                       # two signups raced for one email
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "that email is already registered")
    return _pair(user)


@router.post("/login", response_model=TokenPair,
             dependencies=[Depends(auth_rate_limit)])
def login(payload: LoginIn, db: DbSession) -> TokenPair:
    user = users_repo.get_by_email(db, payload.email)
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)

    if security.needs_rehash(user.password_hash):
        users_repo.set_password(db, user, security.hash_password(payload.password))
        db.commit()
    return _pair(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshIn, db: DbSession) -> TokenPair:
    try:
        claims = security.decode_claims(payload.refresh_token, expect=security.REFRESH)
    except security.TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    user = users_repo.get(db, claims.user_id)
    if user is None:                             # deleted since the token was issued
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token is not valid")
    # Checked here as well as in the guard: without it a refresh token from
    # before a password reset would mint a valid access token, and the reset
    # would have ended nothing.
    if claims.version != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "this session ended when the password was changed")
    return _pair(user)


# `response_class=Response` and no return annotation: FastAPI reads `-> None`
# as a response model, and a 204 may not have a body. Newer versions shrug at
# this; the pinned one asserts at import, so the container would not start.
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT,
             response_class=Response)
def logout():
    """Nothing to do server-side: the client drops its tokens.

    Kept as a route so the client has one place to call, and so adding a
    revocation list later does not change the frontend.
    """


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DbSession) -> MeOut:
    return MeOut(
        id=user.id, email=user.email, telegram_id=user.telegram_id,
        locale=user.locale, risk_profile=user.risk_profile,
        onboarded=profiles_repo.get_by_user(db, user.id) is not None,
    )


# --- forgotten passwords -------------------------------------------------

def _reset_email(link: str) -> str:
    """The whole email. Plain text: this is four sentences and a link, and
    an HTML part would only give a mail client more ways to mangle it."""
    return f"""Someone asked to reset the password on your FinMentor account.

{link}

The link works once and expires in {settings.password_reset_ttl_minutes} minutes.

If it was not you, nothing has changed and you can ignore this. Your password
only changes when the link is used."""


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(auth_rate_limit)])
def forgot_password(payload: ForgotPasswordIn, db: DbSession) -> dict[str, str]:
    """Send a reset link, and say the same thing either way.

    202 and one sentence whether or not the address is registered. Anything
    else — a 404, a different message, a measurably faster response — turns
    this into a way to find out who has an account here, which is worth more
    to an attacker than it sounds: it is the first half of credential
    stuffing, and it is a disclosure the person never agreed to.

    The send itself is best-effort (`send_quietly`). A mail outage must not
    become a 500 on one address and a 202 on another.
    """
    user = users_repo.get_by_email(db, payload.email)
    if user is not None and user.email:
        # Asking again retires the previous link rather than leaving two keys
        # to the same account in the same inbox.
        resets_repo.invalidate_outstanding(db, user.id)
        raw, hashed = security.new_reset_token()
        resets_repo.create(db, user_id=user.id, token_hash=hashed)
        db.commit()
        send_quietly(Message(
            to=user.email,
            subject="Reset your FinMentor password",
            body=_reset_email(f"{settings.web_base_url}/reset-password?token={raw}"),
        ))
    return {"message": RESET_SENT}


@router.post("/reset-password", response_model=TokenPair,
             dependencies=[Depends(auth_rate_limit)])
def reset_password(payload: ResetPasswordIn, db: DbSession) -> TokenPair:
    """Spend a reset link: set the new password, end every older session.

    The pair comes back because the person has just proved they hold the
    address and chosen a password; making them type it again on a login form
    proves nothing further. Every token older than this moment stops working,
    which is the point of the exercise — a reset that leaves the sessions the
    old password started running has not taken the account back.
    """
    reset = resets_repo.usable(db, security.hash_reset_token(payload.token))
    if reset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_RESET)

    user = users_repo.get(db, reset.user_id)
    if user is None:                              # deleted while the link sat in an inbox
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_RESET)

    users_repo.set_password(db, user, security.hash_password(payload.password))
    resets_repo.spend(db, reset)
    resets_repo.invalidate_outstanding(db, user.id)
    resets_repo.end_existing_sessions(db, user)
    db.commit()
    return _pair(user)
