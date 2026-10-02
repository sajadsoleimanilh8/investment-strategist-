"""Attaching a Telegram account to a web account, including the data merge.

`users` has always been able to hold a `telegram_id` and an `email` on one
row. What it could not do is get there from two rows that already exist, which
is the normal case: people use the bot first, because that is the product they
found, and sign up on the web later.

So linking is a merge, and a merge needs a rule for collisions. The rule is
one sentence:

    **The web account wins every collision; everything that does not collide
    moves across.**

That is a choice between two bad alternatives. Discarding the Telegram side
destroys the data the user most likely cares about, since it is the side they
have been using. Asking them to resolve it field by field is a screen nobody
would build and nobody would read. Keeping both, where the shape of the table
allows it, loses nothing: the worst case is a duplicate goal the user can
delete, which is visible and reversible, as against data that is silently
gone, which is neither.

Collisions are not a matter of opinion here — they are exactly the unique
constraints, listed in `MERGED` below. A table with no constraint cannot
collide, so all of its rows move. A table with one keeps the web row.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session, aliased

from app.models.finance import ExpenseRecord, FinancialProfile, IncomeRecord
from app.models.goal import FinancialGoal
from app.models.market import WatchlistItem
from app.models.simulation import ChatSession, EducationProgress, Simulation
from app.models.user import User

#: `(model, label, key)` per table a user owns. The label is singular;
#: `views._inventory` pluralises it when the count calls for it. `key` is the columns of that
#: table's uniqueness-per-user constraint, and an empty `key` means the table
#: has none, so nothing in it can collide.
#:
#: This list is the merge. It is also load-bearing in a way worth stating: a
#: new table hanging off `users` that is missing from here keeps pointing at
#: the row the merge deletes, and its rows go with it.
#: `tests/unit/test_account_link.py` walks the mapper registry and fails if a
#: user-owned table is absent, so forgetting is a failing test rather than
#: lost data.
MERGED: tuple[tuple[type, str, tuple[str, ...]], ...] = (
    (FinancialProfile, "profile", ("user_id",)),
    (ChatSession, "chat session", ("user_id",)),
    (ExpenseRecord, "expense record", ("period", "category")),
    (WatchlistItem, "watchlist symbol", ("symbol",)),
    (EducationProgress, "completed topic", ("topic_key",)),
    (IncomeRecord, "income record", ()),
    (FinancialGoal, "goal", ()),
    (Simulation, "saved simulation", ()),
)


@dataclass
class MergeReport:
    """What the merge actually did, so the bot can say it rather than guess.

    `moved` and `kept` are keyed by the labels in `MERGED`. `kept` counts rows
    that stayed on the web account because moving one would have broken a
    unique constraint — the collisions, in other words, which is the number a
    user would want to know about.
    """

    moved: dict[str, int] = field(default_factory=dict)
    kept: dict[str, int] = field(default_factory=dict)

    @property
    def moved_anything(self) -> bool:
        return any(self.moved.values())


def _count(db: Session, model: type, user_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    ) or 0


def merge(db: Session, *, into: User, source: User) -> MergeReport:
    """Move everything movable from `source` onto `into`, then delete `source`.

    Ordering is not incidental. `source` is deleted *before* `into` takes the
    telegram id, because that id is unique: assigning it while another row
    still holds it is a constraint violation, and in one transaction the only
    thing that separates the two is a flush.
    """
    report = MergeReport()

    for model, label, key in MERGED:
        before = _count(db, model, source.id)
        if not before:
            continue

        statement = update(model).where(model.user_id == source.id)
        if key:
            other = aliased(model)
            collision = select(other.id).where(
                other.user_id == into.id,
                *[getattr(other, column) == getattr(model, column)
                  for column in key if column != "user_id"],
            )
            statement = statement.where(~exists(collision))

        moved = db.execute(statement.values(user_id=into.id)).rowcount
        if moved:
            report.moved[label] = moved
        if before - moved:
            report.kept[label] = before - moved

    # Whatever did not move is still pointing at `source` and goes with it.
    # That is the cascade doing the deleting, not this function, which is why
    # every `ondelete="CASCADE"` on a user-owned table matters here.
    db.delete(source)
    db.flush()

    into.telegram_id = source.telegram_id
    db.flush()
    return report
