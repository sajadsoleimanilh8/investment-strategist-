"""Router registry.

`auth` first so its routes are matched before anything guarded, and `me` before
the `{user_id}` routes it aliases.
"""
from app.api.routes import (
    ai, auth, finance, goals, health, learn, market, me, simulations, users,
)

ALL_ROUTERS = [
    auth.router, me.router, users.router, finance.router, goals.router,
    health.router, simulations.router, market.router, learn.router, ai.router,
]
