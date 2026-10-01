"""one chat session per user

Revision ID: 9c3f1a7b2e04
Revises: 248bfcf244af
Create Date: 2026-10-01 10:12:00.000000

`chat_repo.get_or_create` reads the *newest* session for a user
(`order_by(id.desc()).limit(1)`) and creates one when there is none. Two
concurrent `/ask` requests can therefore both find nothing and both insert,
and from then on the older row is unreachable: every read picks the newer
one, and the turns written to the older one are invisible to the product.

The `order_by` was what made that survivable rather than visible, which is
why nobody noticed. A unique constraint makes the second insert fail instead,
which is the correct outcome for a table whose reader only ever wants one row.

Deduplicating before adding it is not optional: a database that already has a
pair cannot take the constraint. The rows removed are the ones nothing has
been able to read since the moment they were created.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c3f1a7b2e04'
down_revision: Union[str, Sequence[str], None] = '248bfcf244af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep the newest row per user, which is the only one any read has ever
    # returned. Written as a correlated subquery rather than a window
    # function so it runs the same on Postgres and on the SQLite the test
    # suite uses.
    op.execute(
        """
        DELETE FROM chat_sessions
        WHERE id NOT IN (
            SELECT MAX(id) FROM chat_sessions GROUP BY user_id
        )
        """
    )
    op.create_unique_constraint(
        "uq_chat_sessions_user", "chat_sessions", ["user_id"]
    )


def downgrade() -> None:
    # The deduplication is not reversible; the rows it removed were already
    # unreachable. Only the constraint comes back off.
    op.drop_constraint("uq_chat_sessions_user", "chat_sessions", type_="unique")
