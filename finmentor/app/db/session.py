"""Engine + session factory. Import get_db in FastAPI routes as a dependency."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db import guards

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Attached to the Session class, not to a route and not to this factory: the
# bot and the scripts open their own sessions and never pass through Pydantic.
# `guards` installs on import; the call is here so the dependency is visible
# at the place sessions are made. See app/db/guards.py.
guards.install()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
