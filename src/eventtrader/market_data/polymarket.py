"""Public GET-only Gamma/CLOB adapter. Wire fields follow official Polymarket docs."""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from eventtrader.domain.markets import (
    Amount,
    BookLevel,
    FeeSchedule,
    Market,
    MarketConstraints,
    OrderBook,
    Outcome,
    Price,
)
from eventtrader.market_data.provider import (
    InvalidResponse,
    MarketNotFound,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
)
from eventtrader.settings import Settings

logger = logging.getLogger(__name__)
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def payload_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class GammaFees(BaseModel):
    rate: Amount
    exponent: Amount
    takerOnly: bool
    rebateRate: Amount | None = None


class GammaMarket(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    slug: str | None = None
    category: str | None = None
    conditionId: str | None = None
    description: str | None = None
    resolutionSource: str | None = None
    endDate: datetime | None = None
    active: bool | None = None
    closed: bool | None = None
    archived: bool | None = None
    acceptingOrders: bool | None = None
    enableOrderBook: bool | None = None
    outcomes: list[str] = Field(default_factory=list)
    clobTokenIds: list[str] = Field(default_factory=list)
    liquidity: Amount | None = None
    volume: Amount | None = None
    feesEnabled: bool | None = None
    feeSchedule: GammaFees | None = None

    @field_validator("outcomes", "clobTokenIds", mode="before")
    @classmethod
    def decode_arrays(cls, value: object) -> object:
        if value is None:
            return []
        return json.loads(value) if isinstance(value, str) else value

    @field_validator("endDate")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Missing timestamp timezone")
            return value.astimezone(UTC)
        return None


class GammaPage(BaseModel):
    markets: list[dict[str, Any]]
    next_cursor: str | None = None


class ClobBook(BaseModel):
    market: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    bids: list[BookLevel]
    asks: list[BookLevel]
    timestamp: str | int | None = None
    min_order_size: Amount | None = None
    tick_size: Annotated[Decimal, Field(gt=0, le=1)] | None = None
    last_trade_price: Price | None = None


def normalize_market(payload: object, correlation_id: str) -> Market:
    try:
        wire = GammaMarket.model_validate(payload)
        if wire.clobTokenIds and len(wire.clobTokenIds) != len(wire.outcomes):
            raise ValueError("Unaligned outcomes and token IDs")
        if len(set(wire.clobTokenIds)) != len(wire.clobTokenIds):
            raise ValueError("Duplicate token IDs")
        if any(not token.isdecimal() for token in wire.clobTokenIds):
            raise ValueError("Invalid token ID")
        status: Literal["active", "closed", "archived", "inactive", "unknown"] = (
            "archived"
            if wire.archived
            else "closed"
            if wire.closed
            else "active"
            if wire.active is True and wire.closed is False
            else "inactive"
            if wire.active is False
            else "unknown"
        )
        return Market(
            external_market_id=wire.id,
            slug=wire.slug,
            question=wire.question,
            category=wire.category,
            condition_id=wire.conditionId,
            status=status,
            resolution_rules=wire.description,
            resolution_source=wire.resolutionSource,
            close_time=wire.endDate,
            # closedTime is NOT a verified resolution timestamp.
            resolved_at=None,
            outcomes=[
                Outcome(
                    outcome_name=name,
                    outcome_index=index,
                    token_id=wire.clobTokenIds[index] if wire.clobTokenIds else None,
                    active=status == "active" and bool(wire.clobTokenIds),
                )
                for index, name in enumerate(wire.outcomes)
            ],
            liquidity=wire.liquidity,
            volume=wire.volume,
            fees_enabled=wire.feesEnabled,
            fee_schedule=FeeSchedule(
                rate=wire.feeSchedule.rate,
                exponent=wire.feeSchedule.exponent,
                taker_only=wire.feeSchedule.takerOnly,
                rebate_rate=wire.feeSchedule.rebateRate,
            )
            if wire.feeSchedule
            else None,
            accepting_orders=wire.acceptingOrders,
            enable_order_book=wire.enableOrderBook,
            observed_at=datetime.now(UTC),
            raw_payload_hash=payload_hash(payload),
        )
    except (ValidationError, ValueError, TypeError):
        raise InvalidResponse("invalid_market_response", correlation_id) from None


class PolymarketReadOnlyClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.http = httpx.AsyncClient(
            timeout=settings.provider_timeout_seconds,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": "EventTrader/0.2 read-only"},
        )

    async def __aenter__(self) -> "PolymarketReadOnlyClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.http.aclose()

    async def _get(self, url: str, params: dict[str, str] | None = None) -> tuple[Any, str]:
        correlation_id = str(uuid4())
        for attempt in range(self.settings.provider_max_retries + 1):
            retry_after = 0.0
            try:
                response = await self.http.get(
                    url,
                    params=params,
                    headers={"X-Request-ID": correlation_id},
                )
                logger.info(
                    "provider_response",
                    extra={
                        "correlation_id": correlation_id,
                        "status_code": response.status_code,
                        "attempt": attempt + 1,
                    },
                )
                if response.status_code == 404:
                    raise MarketNotFound("market_or_book_not_found", correlation_id)
                if response.status_code == 429:
                    error: ProviderError = RateLimited("rate_limited", correlation_id)
                    header = response.headers.get("Retry-After", "0")
                    try:
                        retry_after = float(header)
                    except ValueError:
                        try:
                            retry_after = (
                                parsedate_to_datetime(header) - datetime.now(UTC)
                            ).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            retry_after = 0
                elif response.status_code >= 500:
                    error = ProviderUnavailable("provider_unavailable", correlation_id)
                elif response.status_code != 200:
                    raise InvalidResponse("unexpected_http_status", correlation_id)
                else:
                    try:
                        return response.json(), correlation_id
                    except ValueError:
                        raise InvalidResponse("invalid_json", correlation_id) from None
            except httpx.TransportError:
                error = ProviderUnavailable("provider_transport_error", correlation_id)
                logger.warning(
                    "provider_transport_error",
                    extra={
                        "correlation_id": correlation_id,
                        "attempt": attempt + 1,
                    },
                )
            if attempt == self.settings.provider_max_retries:
                raise error from None
            # Do not retry sooner than a long Retry-After; fail bounded and let the operator retry.
            if retry_after > self.settings.provider_max_backoff_seconds:
                raise error from None
            delay = min(
                self.settings.provider_max_backoff_seconds,
                self.settings.provider_backoff_seconds * 2**attempt,
            )
            await asyncio.sleep(max(delay, retry_after))
        raise AssertionError("unreachable")

    async def discover_markets(self, limit: int = 10) -> list[Market]:
        if not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000")
        markets: dict[str, Market] = {}
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while len(markets) < limit:
            params = {
                "closed": "false",
                "limit": str(min(self.settings.provider_page_size, limit - len(markets))),
            }
            if cursor:
                params["after_cursor"] = cursor
            payload, request_id = await self._get(f"{GAMMA}/markets/keyset", params)
            try:
                page = GammaPage.model_validate(payload)
            except ValidationError:
                raise InvalidResponse("invalid_discovery_page", request_id) from None
            if not page.markets:
                break
            previous_count = len(markets)
            for raw in page.markets:
                market = normalize_market(raw, request_id)
                markets[market.external_market_id] = market
            cursor = page.next_cursor
            if cursor and (cursor in seen_cursors or len(markets) == previous_count):
                raise InvalidResponse("pagination_not_advancing", request_id)
            if not cursor:
                break
            seen_cursors.add(cursor)
        return list(markets.values())[:limit]

    async def get_market_details(self, identifier: str, *, by_slug: bool = False) -> Market:
        if not identifier or (not by_slug and not identifier.isdecimal()):
            raise ValueError("Use a Gamma numeric ID or explicitly select by_slug")
        path = f"markets/slug/{quote(identifier, safe='')}" if by_slug else f"markets/{identifier}"
        payload, request_id = await self._get(f"{GAMMA}/{path}")
        market = normalize_market(payload, request_id)
        if (market.slug if by_slug else market.external_market_id) != identifier:
            raise InvalidResponse("market_identity_mismatch", request_id)
        return market

    async def get_orderbook(self, token_id: str) -> OrderBook:
        if not token_id.isdecimal():
            raise ValueError("Token ID must be numeric")
        payload, request_id = await self._get(f"{CLOB}/book", {"token_id": token_id})
        try:
            wire = ClobBook.model_validate(payload)
            if wire.asset_id != token_id:
                raise ValueError("Token mismatch")
            book = OrderBook(
                token_id=wire.asset_id,
                condition_id=wire.market,
                bids=wire.bids,
                asks=wire.asks,
                minimum_order_size=wire.min_order_size,
                tick_size=wire.tick_size,
                last_trade_price=wire.last_trade_price,
                provider_timestamp=datetime.fromtimestamp(int(wire.timestamp) / 1000, UTC)
                if wire.timestamp is not None
                else None,
                captured_at=datetime.now(UTC),
                raw_payload_hash=payload_hash(payload),
            )
            if (
                book.best_bid is not None
                and book.best_ask is not None
                and book.best_bid > book.best_ask
            ):
                raise ValueError("Crossed order book")
            return book
        except (ValidationError, ValueError, TypeError, OverflowError, OSError):
            raise InvalidResponse("invalid_orderbook_response", request_id) from None

    async def get_market_constraints(self, market: Market, book: OrderBook) -> MarketConstraints:
        if book.token_id not in {outcome.token_id for outcome in market.outcomes} or (
            market.condition_id is not None and book.condition_id != market.condition_id
        ):
            raise InvalidResponse("market_book_mismatch", str(uuid4()))
        return MarketConstraints(
            minimum_order_size=book.minimum_order_size,
            tick_size=book.tick_size,
            fees_enabled=market.fees_enabled,
            fee_schedule=market.fee_schedule,
        )
