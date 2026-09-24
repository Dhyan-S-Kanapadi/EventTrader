"""Typed deterministic callables used by LangGraph; no LLM tool selection."""

import hashlib
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from eventtrader.domain.markets import Market, OrderBook, SnapshotValues
from eventtrader.market_data.provider import PredictionMarketDataProvider
from eventtrader.persistence.repository import MarketRepository


async def discover_polymarket_markets(
    provider: PredictionMarketDataProvider, limit: int
) -> list[Market]:
    return await provider.discover_markets(limit)


async def get_polymarket_market_details(
    provider: PredictionMarketDataProvider,
    identifier: str,
    *,
    by_slug: bool = False,
) -> Market:
    return await provider.get_market_details(identifier, by_slug=by_slug)


async def get_polymarket_orderbook(
    provider: PredictionMarketDataProvider, token_id: str
) -> OrderBook:
    return await provider.get_orderbook(token_id)


async def sync_market_snapshot(
    provider: PredictionMarketDataProvider,
    engine: Engine,
    market_id: UUID,
    market: Market,
    token_id: str,
) -> UUID:
    book = await get_polymarket_orderbook(provider, token_id)
    constraints = await provider.get_market_constraints(market, book)
    bid, ask = book.best_bid, book.best_ask
    fee = constraints.fee_schedule
    snapshot = SnapshotValues(
        captured_at=book.captured_at,
        metadata_captured_at=market.observed_at,
        provider_timestamp=book.provider_timestamp,
        best_bid=bid,
        best_ask=ask,
        midpoint=(bid + ask) / 2 if bid is not None and ask is not None else None,
        spread=ask - bid if bid is not None and ask is not None else None,
        last_trade_price=book.last_trade_price,
        liquidity=market.liquidity,
        volume=market.volume,
        # Open interest is not supplied by the chosen market/book endpoints.
        open_interest=None,
        minimum_order_size=constraints.minimum_order_size,
        tick_size=constraints.tick_size,
        fees_enabled=constraints.fees_enabled,
        fee_rate=Decimal(0) if constraints.fees_enabled is False else fee.rate if fee else None,
        fee_exponent=fee.exponent if fee else None,
        fee_taker_only=fee.taker_only if fee else None,
        fee_rebate_rate=fee.rebate_rate if fee else None,
        raw_payload_hash=hashlib.sha256(
            (market.raw_payload_hash + book.raw_payload_hash).encode()
        ).hexdigest(),
    )
    with Session(engine) as session, session.begin():
        return MarketRepository(session).add_snapshot(
            market_id, token_id, snapshot, bids=book.bids, asks=book.asks
        )
