"""market routes (GET /api/market/assets[/{symbol}], /api/market/watchlist/{user_id}).
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["market"])

# TODO(phase-4): implement endpoints listed in docs/SPEC.md section 22.
