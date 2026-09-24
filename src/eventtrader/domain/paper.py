"""Paper-only execution and portfolio schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from eventtrader.domain.markets import Amount, Price

PaperSide = Literal["BUY", "SELL"]
PaperOrderStatus = Literal[
    "CREATED",
    "PARTIALLY_FILLED",
    "FILLED",
    "OPEN",
    "CANCELLED",
    "REJECTED",
    "EXPIRED",
]


class PaperModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class PaperOrderCreate(PaperModel):
    trade_proposal_id: UUID
    side: PaperSide
    limit_price: Price
    requested_size_usd: Amount | None = None
    requested_shares: Amount | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_size(self) -> "PaperOrderCreate":
        if self.side == "BUY" and (self.requested_size_usd is None or self.requested_size_usd <= 0):
            raise ValueError("BUY requires positive requested_size_usd")
        if self.side == "SELL" and (self.requested_shares is None or self.requested_shares <= 0):
            raise ValueError("SELL requires positive requested_shares")
        return self


class PaperFillRead(PaperModel):
    id: UUID
    paper_order_id: UUID
    fill_price: Decimal
    filled_shares: Decimal
    filled_notional_usd: Decimal
    estimated_fee_usd: Decimal
    estimated_spread_cost_usd: Decimal
    estimated_slippage_usd: Decimal
    filled_at: datetime


class PaperOrderRead(PaperModel):
    id: UUID
    trade_proposal_id: UUID
    market_id: UUID
    outcome_token_id: str
    side: str
    order_type: str
    limit_price: Decimal
    requested_size_usd: Decimal
    requested_shares: Decimal
    status: str
    idempotency_key: str
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    fills: list[PaperFillRead] = Field(default_factory=list)


class PaperPositionRead(PaperModel):
    id: UUID
    market_id: UUID
    outcome_token_id: str
    side: str
    quantity_shares: Decimal
    average_entry_price: Decimal
    cost_basis_usd: Decimal
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    allocated_research_cost_usd: Decimal
    current_mark_price: Decimal | None
    trade_proposal_id: UUID
    status: str
    opened_at: datetime
    closed_at: datetime | None


class PortfolioEventRead(PaperModel):
    id: UUID
    event_type: str
    reference_type: str
    reference_id: UUID
    amount_usd: Decimal
    balance_after_usd: Decimal
    event_metadata: dict[str, object]
    created_at: datetime


class PaperPortfolioRead(PaperModel):
    mode: Literal["PAPER"] = "PAPER"
    starting_capital_usd: Decimal
    cash_balance_usd: Decimal
    reserved_cash_usd: Decimal
    available_cash_usd: Decimal
    open_exposure_usd: Decimal
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    total_net_pnl_usd: Decimal
    total_fees_usd: Decimal
    total_spread_cost_usd: Decimal
    total_slippage_usd: Decimal
    total_research_cost_usd: Decimal
    positions: list[PaperPositionRead]
    events: list[PortfolioEventRead]


class PaperExecutionResult(PaperModel):
    order: PaperOrderRead
    portfolio: PaperPortfolioRead


class SettlementInstruction(PaperModel):
    condition_id: str
    payouts: list[Decimal]
    resolved_at: AwareDatetime
    source: str


class ReconciliationResult(PaperModel):
    settled_position_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OrderBookLevelRead(PaperModel):
    id: UUID
    market_snapshot_id: UUID
    side: str
    price: Decimal
    size: Decimal
    level_index: int
