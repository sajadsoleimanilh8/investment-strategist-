"""Seed the demo user (spec section 29): income 30M, expenses 18M, savings 45M,
emergency 30M, debt 10M; goal Laptop target 60M / current 20M / 6 months.

Idempotent — rerunning it updates the same user instead of creating a second.

    python scripts/seed_demo_user.py
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as `python scripts/...`

from sqlalchemy.orm import Session

from app.core.logging import configure_logging, safe_json
from app.db.session import SessionLocal
from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.finance import FinancialProfileIn, GoalIn
from scripts.seed_market_assets import seed_demo_watchlist, seed_market_assets

log = logging.getLogger("finmentor.seed")

DEMO_TELEGRAM_ID = 100_000_001

DEMO_PROFILE = {
    "monthly_income": 30_000_000,
    "income_type": "mixed",
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                 "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
    "current_savings": 45_000_000,
    "debt": 10_000_000,
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
    "risk_profile": "moderate",
}
DEMO_GOALS = [
    {"name": "Laptop", "target_amount": 60_000_000, "current_amount": 20_000_000, "priority": 1},
]

GOAL_HORIZON_DAYS = 30 * 6  # "6 months" from spec section 29


def _goal_payloads(today: date | None = None) -> list[GoalIn]:
    deadline = (today or date.today()) + timedelta(days=GOAL_HORIZON_DAYS)
    return [GoalIn(deadline=deadline, **goal) for goal in DEMO_GOALS]


def seed_demo_user(db: Session, *, telegram_id: int = DEMO_TELEGRAM_ID,
                   period: str | None = None) -> int:
    """Write the demo profile + goals through the repositories. Returns user id."""
    user = users_repo.get_or_create(db, telegram_id=telegram_id, locale="fa")
    profiles_repo.upsert(db, user, FinancialProfileIn(**DEMO_PROFILE), period=period)

    existing = {goal.name: goal for goal in goals_repo.list_for_user(db, user.id)}
    for payload in _goal_payloads():
        current = existing.get(payload.name)
        if current is None:
            goals_repo.create(db, user.id, payload)
        else:
            goals_repo.update(db, current, payload)

    db.commit()
    return user.id


def main() -> int:
    configure_logging()
    with SessionLocal() as db:
        user_id = seed_demo_user(db)
        # market assets + a watchlist, so /market is demonstrable too
        assets = seed_market_assets(db)
        watched = seed_demo_watchlist(db, user_id)
        db.commit()

    log.info("seeded demo user id=%s profile=%s", user_id, safe_json(DEMO_PROFILE))
    print(f"demo user seeded: id={user_id}, telegram_id={DEMO_TELEGRAM_ID}")
    print(f"market seeded: {assets} assets, {watched} watchlist entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
