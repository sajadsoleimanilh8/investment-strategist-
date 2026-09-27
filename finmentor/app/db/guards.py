"""The last check before a number becomes a row.

`app/schemas/finance.py` refuses `Infinity` and `NaN` at the HTTP edge, and
that is where the check belongs: it produces a 422 naming the field, which is
something a client can act on. This module is the second line, and it exists
because the HTTP edge is not the only way a row gets written.

The bot opens its own sessions and calls the repositories directly. So do
`scripts/seed_demo_user.py`, `scripts/fetch_market_snapshots.py` and the
fine-tune data generator. A repository function takes floats, not a validated
schema, so none of those paths passes through Pydantic at all. One of them
storing a non-finite float would leave an account that reads back as `null`
on every figure and cannot be repaired through the API, because the API's own
validation would then reject the corrected value's neighbours in the same row.

So the guard is attached to the session's flush rather than to any one caller.
Whatever writes, whichever surface it came from, a non-finite float raises
before it reaches the database.

Cost: one pass over the objects already being flushed, checking only the
columns that are actually floats. That is a handful of attribute reads on a
set SQLAlchemy has just built for its own use.
"""
from __future__ import annotations

import math

from sqlalchemy import Float, event, inspect
from sqlalchemy.orm import Session


class NonFiniteValueError(ValueError):
    """A float column was about to receive Infinity, -Infinity or NaN."""


def _float_columns(obj) -> list[str]:
    """The float-typed column attributes on this mapped object."""
    return [
        column.key
        for column in inspect(type(obj)).columns
        if isinstance(column.type, Float)
    ]


def assert_finite(obj) -> None:
    """Raise if any float column on `obj` holds a non-finite value."""
    for name in _float_columns(obj):
        value = getattr(obj, name, None)
        if isinstance(value, float) and not math.isfinite(value):
            raise NonFiniteValueError(
                f"{type(obj).__name__}.{name} is {value!r}, which is not a "
                "finite number. Money and rates must be real figures; see "
                "app/schemas/finance.py for the bounds the API enforces."
            )


def _check_pending(session: Session, _flush_context, _instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        assert_finite(obj)


def install() -> None:
    """Attach the guard to every session this application opens.

    Registered against the `Session` *class*, not against a `sessionmaker`,
    and that distinction is not cosmetic. SQLAlchemy's event registry is keyed
    on `id()` of the target, and a `sessionmaker` that goes out of scope frees
    its address for the next allocation. A fresh factory landing on a recycled
    address then answers True to `event.contains`, the registration is skipped
    as a duplicate, and the guard is silently absent.

    That is not hypothetical: it is what this function used to do. In
    production it happened to work, because `SessionLocal` is module-level and
    never collected. In the test suite, which builds a factory per test, the
    guard was off for roughly half of them — so the suite was quietly not
    running the rules production runs, which is the exact gap this module
    exists to close.

    The class is the right scope regardless. "No session in this application
    writes a non-finite float" is a property of every session, whichever
    factory made it: the API's, the bot's, a script's, a test's.

    Idempotent, and safe to call more than once: `Session` is a module-level
    class, so its identity is stable for the life of the process.
    """
    if not event.contains(Session, "before_flush", _check_pending):
        event.listen(Session, "before_flush", _check_pending)


#: Installed on import. A guard you have to remember to switch on is a guard
#: that is off wherever somebody forgot, and the only thing this needs in
#: order to work is for the module to be imported at all.
install()
