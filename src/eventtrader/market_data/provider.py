from typing import Protocol

from eventtrader.domain.markets import Market, MarketConstraints, OrderBook


class ProviderError(Exception):
    """Safe error code and locally generated correlation ID; no response bodies."""

    def __init__(self, code: str, correlation_id: str):
        self.code = code
        self.correlation_id = correlation_id
        super().__init__(f"{code} (request {correlation_id})")


class RateLimited(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class InvalidResponse(ProviderError):
    pass


class MarketNotFound(ProviderError):
    pass


class PredictionMarketDataProvider(Protocol):
    async def discover_markets(self, limit: int = 10) -> list[Market]: ...

    async def get_market_details(self, identifier: str, *, by_slug: bool = False) -> Market: ...

    async def get_orderbook(self, token_id: str) -> OrderBook: ...

    async def get_market_constraints(
        self, market: Market, book: OrderBook
    ) -> MarketConstraints: ...
