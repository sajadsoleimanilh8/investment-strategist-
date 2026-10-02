"""telegram account linking

Revision ID: a1d4e77c90b2
Revises: 9c3f1a7b2e04
Create Date: 2026-10-02 09:30:00.000000

`users` has carried both `telegram_id` and `email` since the initial schema,
with a comment saying the same row holds both "once the two identities are
linked". Nothing ever linked them. This adds the table that does.

The shape is `password_resets`: a hashed single-use credential with an
expiry. The index on `user_id` is there because the common query is "retire
this user's outstanding codes", not "find a code".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1d4e77c90b2'
down_revision: Union[str, Sequence[str], None] = '9c3f1a7b2e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_links_user_id", "telegram_links", ["user_id"])
    op.create_index("ix_telegram_links_code_hash", "telegram_links",
                    ["code_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_telegram_links_code_hash", table_name="telegram_links")
    op.drop_index("ix_telegram_links_user_id", table_name="telegram_links")
    op.drop_table("telegram_links")
