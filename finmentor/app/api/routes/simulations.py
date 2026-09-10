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

from app.api.deps import CurrentUser, DbSession, OwnedUserId, assert_owns, load_twin, load_user, require_user
from app.repositories import goals as goals_repo
from app.repositories import simulations as simulations_repo
from app.schemas.simulation import WhatIfParams
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


class SimulationRecord(BaseModel):
    id: int
    user_id: int
    kind: str
    params: dict[str, Any]
    result: Any
    created_at: datetime


def _bad_params(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


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
        horizon = payload.params.get("horizon_months", DEFAULT_TIME_MACHINE_HORIZON)
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
            raise _bad_params("horizon_months must be a positive integer")
        return compare_paths(twin, horizon)

    price = payload.params.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        raise _bad_params("decision params need a positive 'price'")
    return evaluate_purchase(twin, float(price))


def _as_jsonable(result: Any) -> Any:
    if isinstance(result, list):
        return [item.model_dump(mode="json") for item in result]
    return result.model_dump(mode="json")


@router.post("/simulations", status_code=status.HTTP_201_CREATED)
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
