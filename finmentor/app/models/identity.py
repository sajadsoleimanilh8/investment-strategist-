"""Third-party sign-in identities.

A row says "this provider's account number X is this FinMentor user". It is
not a copy of the person: no name, no picture, no access token. The provider's
token is used once, during the callback, to learn who signed in, and is then
discarded — this app does not call Google or GitHub on the user's behalf and
has no business holding a credential that would let it.

`email` is stored because it is what links a provider sign-in to an account
someone already has, and because it is the only contact detail this app uses.
It is a snapshot from the moment of linking, not a live copy: people change the
address on their Google account without telling us.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User

#: The providers this app knows how to talk to. A string column rather than an
#: enum type: adding a provider should be a deploy, not a migration.
PROVIDERS = ("google", "github", "apple")


class UserIdentity(Base, TimestampMixin):
    __tablename__ = "user_identities"
    __table_args__ = (
        # One provider account signs in to exactly one user. Without this a
        # second row could quietly point the same Google account at a
        # different FinMentor account, and which one you landed in would
        # depend on row order.
        UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    #: The provider's own immutable id for the account (`sub` in OIDC). Never
    #: the email: people change those, and providers reissue them.
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), default=None)

    user: Mapped[User] = relationship(back_populates="identities")
