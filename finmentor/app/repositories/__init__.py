"""Thin CRUD helpers over the ORM models.

Plain functions taking an explicit ``Session``. They ``flush()`` so the caller
can keep working with the persisted row (ids populated), but they never
``commit()`` — the request handler or script owns the transaction boundary.
"""
from app.repositories import education, goals, profiles, users  # noqa: F401
