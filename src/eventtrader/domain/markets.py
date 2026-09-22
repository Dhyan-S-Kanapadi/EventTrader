"""Provider-independent public data. Unknown values stay null, never invented."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Price = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
Amount = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class PublicModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class Outcome(PublicModel):
    outcome_name: str
    token_id: str | None
    outcome_index: int
    active: bool


class FeeSchedule(PublicModel):
    rate: Amount
    exponent: Amount
    taker_only: bool
    rebate_rate: Amount | None = None


class Market(PublicModel):
    provider: Literal["polymarket"] = "polymarket"
    external_market_id: str
    slug: str | None = None
    question: str
    category: str | None = None
    condition_id: str | None = None
    status: Literal["active", "closed", "archived", "inactive", "unknown"]
    resolution_rules: str | None = None
    resolution_source: str | None = None
    close_time: AwareDatetime | None = None
    resolved_at: AwareDatetime | None = None
    outcomes: list[Outcome]
    liquidity: Amount | None = None
    volume: Amount | None = None
    fees_enabled: bool | None = None
    fee_schedule: FeeSchedule | None = None
    accepting_orders: bool | None = None
    enable_order_book: bool | None = None
    observed_at: AwareDatetime
    raw_payload_hash: str


class BookLevel(PublicModel):
    price: Price
    size: Amount


class OrderBook(PublicModel):
    token_id: str
    condition_id: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    minimum_order_size: Amount | None = None
    tick_size: Annotated[Decimal, Field(gt=0, le=1)] | None = None
    last_trade_price: Price | None = None
    provider_timestamp: AwareDatetime | None = None
    captured_at: AwareDatetime
    raw_payload_hash: str

    @property
    def best_bid(self) -> Decimal | None:
        return max((x.price for x in self.bids if x.size > 0), default=None)

    @property
    def best_ask(self) -> Decimal | None:
        return min((x.price for x in self.asks if x.size > 0), default=None)


class MarketConstraints(PublicModel):
    minimum_order_size: Amount | None
    tick_size: Decimal | None
    fees_enabled: bool | None
    fee_schedule: FeeSchedule | None


class SnapshotValues(PublicModel):
    captured_at: AwareDatetime
    metadata_captured_at: AwareDatetime
    provider_timestamp: AwareDatetime | None = None
    best_bid: Price | None = None
    best_ask: Price | None = None
    midpoint: Price | None = None
    spread: Amount | None = None
    last_trade_price: Price | None = None
    liquidity: Amount | None = None
    volume: Amount | None = None
    open_interest: Amount | None = None
    minimum_order_size: Amount | None = None
    tick_size: Decimal | None = None
    fee_rate: Amount | None = None
    fees_enabled: bool | None = None
    fee_exponent: Amount | None = None
    fee_taker_only: bool | None = None
    fee_rebate_rate: Amount | None = None
    raw_payload_hash: str


class SnapshotRead(SnapshotValues):
    id: UUID
    market_id: UUID
    outcome_id: UUID


class OutcomeRead(Outcome):
    id: UUID
    market_id: UUID


class MarketRead(PublicModel):
    id: UUID
    provider: str
    external_market_id: str
    slug: str | None
    question: str
    category: str | None
    condition_id: str | None
    status: str
    resolution_rules: str | None
    resolution_source: str | None
    close_time: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    accepting_orders: bool | None
    enable_order_book: bool | None
    outcomes: list[OutcomeRead]
    latest_snapshots: list[SnapshotRead] = Field(default_factory=list)
