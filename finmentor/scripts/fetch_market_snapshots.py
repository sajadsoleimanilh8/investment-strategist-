"""Scheduled market refresh job (spec section 24). Run by APScheduler or cron.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.core.config import settings


def main() -> None:
    # TODO(phase-4): for each configured watchlist symbol -> market_engine.get_series
    #   -> market.cache.store_series
    print("would refresh:", settings.stock_watchlist, settings.crypto_watchlist)


if __name__ == "__main__":
    main()
