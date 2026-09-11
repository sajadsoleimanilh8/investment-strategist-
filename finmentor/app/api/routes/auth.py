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
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.auth import LoginIn, MeOut, RefreshIn, SignupIn, TokenPair

router = APIRouter(prefix="/api/auth", tags=["auth"])

#: One message for "no such email" and "wrong password". Telling them apart
#: hands an attacker a free account-existence oracle.
BAD_CREDENTIALS = "email or password is incorrect"


def _pair(user_id: int) -> TokenPair:
    return TokenPair(
        access_token=security.create_access_token(user_id),
        refresh_token=security.create_refresh_token(user_id),
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
    return _pair(user.id)


@router.post("/login", response_model=TokenPair,
             dependencies=[Depends(auth_rate_limit)])
def login(payload: LoginIn, db: DbSession) -> TokenPair:
    user = users_repo.get_by_email(db, payload.email)
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS)

    if security.needs_rehash(user.password_hash):
        users_repo.set_password(db, user, security.hash_password(payload.password))
        db.commit()
    return _pair(user.id)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshIn, db: DbSession) -> TokenPair:
    try:
        user_id = security.decode_token(payload.refresh_token, expect=security.REFRESH)
    except security.TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    if users_repo.get(db, user_id) is None:      # deleted since the token was issued
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token is not valid")
    return _pair(user_id)


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
