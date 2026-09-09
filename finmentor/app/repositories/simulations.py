"""CRUD for `simulations` — saved deterministic scenario runs.

`params_json` / `result_json` are `json.dumps` text (see docs/DATA_MODEL.md),
so this module owns the encode/decode and callers deal in plain dicts.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.simulation import Simulation

KINDS = ("what_if", "time_machine", "decision")


def create(db: Session, user_id: int, *, kind: str, params: dict[str, Any],
           result: Any) -> Simulation:
    simulation = Simulation(
        user_id=user_id,
        kind=kind,
        params_json=json.dumps(params, default=str),
        result_json=json.dumps(result, default=str),
    )
    db.add(simulation)
    db.flush()
    return simulation


def get(db: Session, simulation_id: int) -> Simulation | None:
    return db.get(Simulation, simulation_id)


def list_for_user(db: Session, user_id: int, *, limit: int = 20,
                  offset: int = 0) -> list[Simulation]:
    """Most recent first — the run a user just made is the one they want back."""
    stmt = (
        select(Simulation)
        .where(Simulation.user_id == user_id)
        .order_by(Simulation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def decode(simulation: Simulation) -> dict[str, Any]:
    """The stored row with its JSON columns parsed back into objects."""
    return {
        "id": simulation.id,
        "user_id": simulation.user_id,
        "kind": simulation.kind,
        "params": json.loads(simulation.params_json),
        "result": json.loads(simulation.result_json),
        "created_at": simulation.created_at,
    }
