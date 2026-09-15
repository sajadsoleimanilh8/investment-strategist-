"""Turning a provider identity into a FinMentor user."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import UserIdentity
from app.models.user import User
from app.repositories import users as users_repo


def get(db: Session, provider: str, subject: str) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.subject == subject
        )
    )


def link(db: Session, *, user_id: int, provider: str, subject: str,
         email: str | None) -> UserIdentity:
    identity = UserIdentity(
        user_id=user_id, provider=provider, subject=subject,
        email=users_repo.normalise_email(email) if email else None,
    )
    db.add(identity)
    db.flush()
    return identity


def resolve(db: Session, *, provider: str, subject: str,
            email: str | None) -> tuple[User, bool]:
    """The user behind a provider sign-in, creating one if this is the first.

    Returns `(user, created)`.

    Three cases, in order:

    1. **This provider account is known.** Sign that user in. The subject is
       the provider's immutable id, so this keeps working after someone
       changes the address on their Google account.

    2. **The verified address matches an existing account.** Link the two.
       This is the case that makes "sign in with Google" work for someone who
       originally signed up with a password, and it is only safe because the
       address is verified by the provider — the callers in `app/oauth` refuse
       an unverified one, and without that check this branch would be an
       account takeover by anyone who can type an address into a profile.

    3. **Neither.** A new account, with no password. They can add one later
       through the reset flow, which is exactly what that flow is for.
    """
    existing = get(db, provider, subject)
    if existing is not None:
        return existing.user, False

    if email:
        by_email = users_repo.get_by_email(db, email)
        if by_email is not None:
            link(db, user_id=by_email.id, provider=provider, subject=subject, email=email)
            return by_email, False

    if not email:
        # Every provider this app supports returns a verified address, so this
        # is a provider that answered oddly rather than a case to design for.
        # Refusing beats inventing a placeholder address that then collides.
        raise NoAddressError(provider)

    user = User(email=users_repo.normalise_email(email))
    db.add(user)
    db.flush()
    link(db, user_id=user.id, provider=provider, subject=subject, email=email)
    return user, True


class NoAddressError(Exception):
    """The provider signed someone in without giving us a verified address."""
