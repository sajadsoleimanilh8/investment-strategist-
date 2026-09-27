"""simulations routes (spec section 22): POST /api/simulations,
GET /api/simulations/{user_id}.

The route resolves the user's twin, hands it to the deterministic engine, and
persists what came back. It performs no arithmetic of its own — every number in
the response was produced by `app/services`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import (
    CurrentUser, DbSession, OwnedUserId, assert_owns, load_twin, load_user,
    require_user, simulation_rate_limit,
)
from app.repositories import goals as goals_repo
from app.repositories import simulations as simulations_repo
from app.schemas.finance import FINITE, MONEY_CEILING
from app.schemas.simulation import MAX_HORIZON_MONTHS, WhatIfParams
from app.services.decision_simulator import evaluate_purchase
from app.services.simulation_engine import run_what_if
from app.services.time_machine import compare_paths

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["simulations"],
                   dependencies=[Depends(require_user)])

DEFAULT_TIME_MACHINE_HORIZON = 36


class SimulationIn(BaseModel):
    user_id: int = Field(gt=0)
    kind: Literal["what_if", "time_machine", "decision"]
    #: shape depends on `kind`; validated per-kind below so the error names the field
    params: dict[str, Any] = Field(default_factory=dict)


class TimeMachineParams(BaseModel):
    """The only lever a time machine has.

    A model rather than two `isinstance` calls, so the bound lives with the
    field and matches `WhatIfParams.horizon_months` exactly — the two run the
    same straight-line projection, so a horizon one accepts and the other
    rejects would be a bug on its own.
    """

    model_config = FINITE

    horizon_months: int = Field(default=DEFAULT_TIME_MACHINE_HORIZON,
                                ge=1, le=MAX_HORIZON_MONTHS)


class DecisionParams(BaseModel):
    """A purchase to evaluate. Positive, finite, and inside the money bounds."""

    model_config = FINITE

    price: float = Field(gt=0, le=MONEY_CEILING)


class SimulationRecord(BaseModel):
    id: int
    user_id: int
    kind: str
    params: dict[str, Any]
    result: Any
    created_at: datetime


def _bad_params(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)   # literal: see errors.py


def _run(db, payload: SimulationIn) -> Any:
    """Dispatch to the engine. Raises 422 for params the engine cannot accept."""
    twin = load_twin(db, payload.user_id)

    if payload.kind == "what_if":
        try:
            params = WhatIfParams(**payload.params)
        except ValidationError as exc:
            raise _bad_params(f"invalid what_if params: {exc.errors()}") from exc
        goal = None
        if params.goal_id is not None:
            stored = goals_repo.get(db, params.goal_id)
            if stored is None or stored.user_id != payload.user_id:
                raise _bad_params("goal_id does not belong to this user")
            goal = goals_repo.to_goal_in(stored)
        return run_what_if(twin, params, goal=goal)

    if payload.kind == "time_machine":
        # Validated by the schema rather than by hand. The hand-written
        # version checked `isinstance(int)` and `> 0` and stopped there, so an
        # arbitrary-precision integer passed it and raised OverflowError deep
        # in the engine. `TimeMachineParams` carries the same bound as
        # `WhatIfParams`, because it is the same projection.
        try:
            params = TimeMachineParams(**payload.params)
        except ValidationError as exc:
            raise _bad_params(f"invalid time_machine params: {exc.errors()}") from exc
        return compare_paths(twin, params.horizon_months)

    try:
        decision = DecisionParams(**payload.params)
    except ValidationError as exc:
        raise _bad_params(f"invalid decision params: {exc.errors()}") from exc
    return evaluate_purchase(twin, decision.price)


def _as_jsonable(result: Any) -> Any:
    if isinstance(result, list):
        return [item.model_dump(mode="json") for item in result]
    return result.model_dump(mode="json")


@router.post("/simulations", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(simulation_rate_limit)])
def create_simulation(payload: SimulationIn, db: DbSession,
                      current_user: CurrentUser) -> Any:
    """Run a scenario and persist both the params and the deterministic result."""
    assert_owns(current_user, payload.user_id)
    result = _run(db, payload)
    simulations_repo.create(
        db, payload.user_id, kind=payload.kind, params=payload.params,
        result=_as_jsonable(result),
    )
    db.commit()
    return result


@router.get("/simulations/{user_id}", response_model=list[SimulationRecord])
def list_simulations(
    user_id: OwnedUserId,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[SimulationRecord]:
    """The user's saved runs, newest first."""
    load_user(db, user_id)
    rows = simulations_repo.list_for_user(db, user_id, limit=limit, offset=offset)
    return [SimulationRecord(**simulations_repo.decode(row)) for row in rows]
