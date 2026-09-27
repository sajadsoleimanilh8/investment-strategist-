"""Every route that touches somebody's data proves it checks whose data it is.

Why this file exists
--------------------
`PUT /api/goals/{goal_id}` shipped with no ownership check at all, and the
whole suite stayed green. Three things conspired:

* the `client` fixture overrides `require_user` and `owned_user_id` and
  monkeypatches `assert_owns` to a no-op, because most of the suite is about
  business logic and threading tokens through two hundred assertions would
  drown it. So the guard is absent from almost every test by design.
* `test_auth.py::CROSS_USER` is a hand-written list, and a list nobody adds a
  route to keeps passing forever.
* that list is templated on `{user_id}`, so it structurally cannot reach a
  route keyed on `{goal_id}`. Adding the route to the list was not an option
  anybody forgot; it was not possible.

So this file does not check a list. It walks the router tree, works out which
routes touch a user-owned resource, and demands that each one be accounted
for. A new route that takes a resource id and is not accounted for fails here
on the day it is written.

How ownership is enforced in this codebase
------------------------------------------
Two mechanisms, and a route uses exactly one:

`PATH_DEPENDENCY`
    The user id is in the path, so `OwnedUserId` (which depends on
    `owned_user_id`) compares it to the token and raises 403. This is the
    normal case and it is verified *structurally*: the dependency is either in
    the route's dependant tree or it is not.

`ASSERTS_OWNERSHIP`
    The owner is not in the URL — it is in the request body, or it is a
    property of the row the route has to load first. A dependency cannot reach
    either, so the handler calls `assert_owns(current_user, owner_id)`. This
    is verified *behaviourally*: the route is driven with two real users and
    two real tokens, and has to answer 403. Declaring a route here without
    implementing the guard fails the test, which is what stops the registry
    from becoming decoration.

`NOT_USER_SCOPED`
    The route takes an identifier that is not a user's: a market symbol, a
    lesson key, a provider name. Each entry carries a reason.

Adding a route
--------------
If your new route takes a `{something_id}` path parameter or a body field
ending in `_id`, `test_every_resource_route_is_accounted_for` will fail until
you add it to `OWNERSHIP` below. Pick the mechanism, and if it is
`ASSERTS_OWNERSHIP` add an attack to `CROSS_USER_ATTACKS` so the guard is
proved rather than promised.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.api.deps import owned_user_id
from app.api.routes import ALL_ROUTERS
from app.core import security

# --- how each route is guarded ------------------------------------------

PATH_DEPENDENCY = "path dependency (OwnedUserId)"
ASSERTS_OWNERSHIP = "assert_owns in the handler"
NOT_USER_SCOPED = "identifier is not a user's"

#: Every route the discovery below flags, and how it is guarded. Keyed by
#: "METHOD /path" exactly as the router registers it.
OWNERSHIP: dict[str, tuple[str, str]] = {
    # The owner is in the body, so no dependency can see it.
    "POST /api/goals": (
        ASSERTS_OWNERSHIP, "GoalCreate.user_id names the owner"),
    "POST /api/simulations": (
        ASSERTS_OWNERSHIP, "SimulationIn.user_id names the owner"),
    "POST /api/ai/ask": (
        ASSERTS_OWNERSHIP, "AskRequest.user_id names the owner"),
    # The owner is a property of the row, which has to be loaded to find out.
    # Both go through `_own_goal`, which is the single place that asks.
    "PUT /api/goals/{goal_id}": (
        ASSERTS_OWNERSHIP, "the goal's user_id is only known after loading it"),
    "DELETE /api/goals/{goal_id}": (
        ASSERTS_OWNERSHIP, "the goal's user_id is only known after loading it"),
    # Creates a user rather than reading one; there is no owner to compare
    # against yet. Guarded by `require_user` like everything else on the
    # router, and no client calls it — see the audit note on this route.
    "POST /api/users": (
        NOT_USER_SCOPED, "telegram_id identifies a new user, not an existing owner"),
}


def _route_key(route: APIRoute) -> str:
    method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
    return f"{method} {route.path}"


def _api_routes() -> list[APIRoute]:
    return [
        route
        for router in ALL_ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
    ]


def _has_owned_dependency(route: APIRoute) -> bool:
    """Is `owned_user_id` anywhere in this route's dependency tree?

    Structural, not textual: it reads the dependant FastAPI actually built, so
    a route that imports the name without depending on it does not pass.
    """
    seen, stack = set(), [route.dependant]
    while stack:
        dependant = stack.pop()
        for sub in dependant.dependencies:
            if sub.call is owned_user_id:
                return True
            if id(sub) not in seen:
                seen.add(id(sub))
                stack.append(sub)
    return False


def _body_fields(route: APIRoute) -> list[str]:
    if route.body_field is None:
        return []
    annotation = getattr(route.body_field.field_info, "annotation", None)
    return list(getattr(annotation, "model_fields", {}) or {})


def _takes_a_resource_identifier(route: APIRoute) -> bool:
    """Does this route name a specific record, in the path or the body?

    Deliberately broad: anything ending in `_id`. A future `{profile_id}` or a
    body carrying `account_id` is caught by the same rule that caught
    `{goal_id}`, without anyone having to think of it in advance.
    """
    path_params = {param.name for param in route.dependant.path_params}
    return (
        any(name.endswith("_id") for name in path_params)
        or any(name.endswith("_id") for name in _body_fields(route))
    )


# --- the structural guard ------------------------------------------------

def test_every_resource_route_is_accounted_for():
    """A route naming a record must be guarded, or declared and explained.

    This is the test that would have caught the goal IDOR. It does not know
    what routes exist; it asks the application.
    """
    undeclared = []
    for route in _api_routes():
        if _has_owned_dependency(route):
            continue                       # guarded by the path dependency
        if not _takes_a_resource_identifier(route):
            continue                       # names no particular record
        if _route_key(route) not in OWNERSHIP:
            undeclared.append(_route_key(route))

    assert undeclared == [], (
        f"{undeclared} take a resource identifier, do not depend on "
        "owned_user_id, and are not declared in OWNERSHIP. Either guard them "
        "with OwnedUserId, or declare how they check ownership and add a "
        "cross-user attack to CROSS_USER_ATTACKS. See this module's docstring."
    )


def test_the_registry_has_no_entries_for_routes_that_are_gone():
    """A stale declaration is a claim nobody is checking any more."""
    live = {_route_key(route) for route in _api_routes()}

    assert set(OWNERSHIP) <= live, f"{set(OWNERSHIP) - live} no longer exist"


def test_path_user_id_routes_are_guarded_by_the_dependency():
    """`{user_id}` in a path must mean `OwnedUserId`, never a bare `int`.

    The one way to reintroduce the whole class of bug at once is to declare
    the parameter as `user_id: int` and let it through.
    """
    unguarded = [
        _route_key(route)
        for route in _api_routes()
        if "{user_id}" in route.path and not _has_owned_dependency(route)
    ]

    assert unguarded == [], f"{unguarded} take a path user_id without OwnedUserId"


def test_every_asserting_route_has_an_attack_proving_it():
    """A declaration is a promise; the attack below is the proof.

    Without this, `OWNERSHIP` could say a route asserts ownership when it does
    not, and nothing would notice — which is exactly the failure mode that
    made the hand-maintained CROSS_USER list useless.
    """
    declared = {key for key, (how, _) in OWNERSHIP.items() if how == ASSERTS_OWNERSHIP}
    proved = {attack[0] for attack in CROSS_USER_ATTACKS}

    assert declared == proved, (
        f"{declared ^ proved} is declared as asserting ownership without an "
        "attack proving it, or has an attack without a declaration."
    )


# --- the behavioural proof ----------------------------------------------
#
# Each entry is (route key, method, path builder, body builder). The path and
# body builders receive the *victim's* id, so every request is a genuine
# attempt by one signed-in person to act on another's record.

CROSS_USER_ATTACKS = [
    (
        "POST /api/goals", "POST",
        lambda victim: "/api/goals",
        lambda victim: {"user_id": victim, "name": "Theirs", "target_amount": 1_000_000},
    ),
    (
        "POST /api/simulations", "POST",
        lambda victim: "/api/simulations",
        lambda victim: {"user_id": victim, "kind": "decision",
                        "params": {"price": 1_000_000}},
    ),
    (
        "POST /api/ai/ask", "POST",
        lambda victim: "/api/ai/ask",
        lambda victim: {"user_id": victim, "question": "how am I doing?"},
    ),
    (
        "PUT /api/goals/{goal_id}", "PUT",
        lambda victim: f"/api/goals/{victim}",       # a goal id, substituted below
        lambda victim: {"name": "Mine now", "target_amount": 1,
                        "current_amount": 0, "priority": 1},
    ),
    (
        "DELETE /api/goals/{goal_id}", "DELETE",
        lambda victim: f"/api/goals/{victim}",       # a goal id, substituted below
        lambda victim: None,
    ),
]


@pytest.fixture
def attacker_and_victim(raw_client):
    """Two real accounts with real tokens, and a goal belonging to the victim."""
    attacker = raw_client.post("/api/auth/signup", json={
        "email": "attacker@example.com", "password": "a-long-enough-password"}).json()
    victim = raw_client.post("/api/auth/signup", json={
        "email": "victim@example.com", "password": "a-long-enough-password"}).json()
    victim_id = security.decode_token(victim["access_token"])

    goal = raw_client.post(
        "/api/goals",
        headers={"Authorization": f"Bearer {victim['access_token']}"},
        json={"user_id": victim_id, "name": "Victim's laptop",
              "target_amount": 60_000_000, "current_amount": 20_000_000, "priority": 2},
    )
    assert goal.status_code == 201, goal.text

    return {
        "attacker_token": attacker["access_token"],
        "victim_id": victim_id,
        "victim_token": victim["access_token"],
        "victim_goal_id": goal.json()["id"],
    }


@pytest.mark.parametrize("key,method,path_for,body_for", CROSS_USER_ATTACKS,
                         ids=[attack[0] for attack in CROSS_USER_ATTACKS])
def test_acting_on_another_users_resource_is_403(
    raw_client, attacker_and_victim, key, method, path_for, body_for
):
    people = attacker_and_victim
    # Routes keyed on a goal id get the victim's goal; the rest get their user id.
    target = people["victim_goal_id"] if "{goal_id}" in key else people["victim_id"]

    response = raw_client.request(
        method, path_for(target),
        headers={"Authorization": f"Bearer {people['attacker_token']}"},
        json=body_for(people["victim_id"]),
    )

    assert response.status_code == 403, (
        f"{key} answered {response.status_code} to a cross-user request: "
        f"{response.text[:200]}"
    )


def test_the_victim_can_still_use_their_own_resources(raw_client, attacker_and_victim):
    """The guards must refuse the stranger without refusing the owner.

    A guard that answers 403 to everybody passes every test above and breaks
    the product, so the owner's path is asserted in the same place.
    """
    people = attacker_and_victim
    headers = {"Authorization": f"Bearer {people['victim_token']}"}

    own_goal = raw_client.put(
        f"/api/goals/{people['victim_goal_id']}", headers=headers,
        json={"name": "Victim's laptop", "target_amount": 60_000_000,
              "current_amount": 25_000_000, "priority": 2},
    )
    assert own_goal.status_code == 200, own_goal.text
    assert own_goal.json()["current_amount"] == 25_000_000

    own_list = raw_client.get(f"/api/goals/{people['victim_id']}", headers=headers)
    assert own_list.status_code == 200
