"""Provider registry. Order matters: first match wins, mock is always last."""
from app.core.config import settings
from app.market.alpha_vantage import AlphaVantageProvider
from app.market.base import MarketDataProvider, PricePoint  # noqa: F401
from app.market.coingecko import CoinGeckoProvider
from app.market.mock_provider import MockMarketProvider


def build_providers() -> list[MarketDataProvider]:
    if settings.demo_mode:
        return [MockMarketProvider()]
    return [AlphaVantageProvider(), CoinGeckoProvider(), MockMarketProvider()]
