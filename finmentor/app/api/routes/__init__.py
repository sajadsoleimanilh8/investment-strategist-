"""Router registry."""
from app.api.routes import ai, finance, goals, health, market, simulations, users

ALL_ROUTERS = [
    users.router, finance.router, goals.router, health.router,
    simulations.router, market.router, ai.router,
]
