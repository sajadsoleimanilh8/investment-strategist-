"""web auth: email + password_hash, nullable telegram_id

The web is a second delivery surface over the same data, so it needs a second
way to identify someone. `telegram_id` becomes nullable because a web signup
has none, and a CHECK keeps the pair honest: every row must carry at least one
identity. Existing Telegram rows are untouched — they already satisfy it.

Revision ID: 0129e065904c
Revises: f588259774a8
Create Date: 2026-09-09 23:55:01.328965

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0129e065904c'
down_revision: Union[str, Sequence[str], None] = 'f588259774a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email', sa.String(length=320), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.alter_column('users', 'telegram_id',
               existing_type=sa.BIGINT(),
               nullable=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_check_constraint(
        'ck_users_has_an_identity', 'users',
        'telegram_id IS NOT NULL OR email IS NOT NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_users_has_an_identity', 'users', type_='check')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.alter_column('users', 'telegram_id',
               existing_type=sa.BIGINT(),
               nullable=False)
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'email')
