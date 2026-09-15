"""Router registry.

`auth` first so its routes are matched before anything guarded, and `me` before
the `{user_id}` routes it aliases.
"""
from app.api.routes import (
    ai, auth, finance, goals, health, learn, market, market_live, market_public, me,
    oauth, simulations, users,
)

ALL_ROUTERS = [
    auth.router, oauth.router, me.router, users.router, finance.router, goals.router,
    health.router, simulations.router, market.router, market_live.router,
    market_public.router, learn.router, ai.router,
]
