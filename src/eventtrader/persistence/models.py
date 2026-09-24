from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MarketRow(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("provider", "external_market_id", name="uq_market_provider_external"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(32))
    external_market_id: Mapped[str] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    condition_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    resolution_rules: Mapped[str | None] = mapped_column(Text)
    resolution_source: Mapped[str | None] = mapped_column(Text)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepting_orders: Mapped[bool | None] = mapped_column(Boolean)
    enable_order_book: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutcomeRow(Base):
    __tablename__ = "market_outcomes"
    __table_args__ = (
        UniqueConstraint("market_id", "outcome_index", name="uq_outcome_market_index"),
        UniqueConstraint("market_id", "token_id", name="uq_outcome_market_token"),
        UniqueConstraint("market_id", "id", name="uq_outcome_market_id"),
        CheckConstraint("outcome_index >= 0", name="ck_outcome_index"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    outcome_name: Mapped[str] = mapped_column(Text)
    token_id: Mapped[str | None] = mapped_column(Text)
    outcome_index: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)


class SnapshotRow(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["market_id", "outcome_id"], ["market_outcomes.market_id", "market_outcomes.id"]
        ),
        Index("ix_snapshot_market_captured", "market_id", "captured_at"),
        Index("ix_snapshot_outcome_captured", "outcome_id", "captured_at"),
        CheckConstraint("best_bid IS NULL OR best_bid BETWEEN 0 AND 1", name="ck_snapshot_bid"),
        CheckConstraint("best_ask IS NULL OR best_ask BETWEEN 0 AND 1", name="ck_snapshot_ask"),
        CheckConstraint("spread IS NULL OR spread >= 0", name="ck_snapshot_spread"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    outcome_id: Mapped[UUID]
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    best_bid: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    best_ask: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    midpoint: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    spread: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    last_trade_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    liquidity: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    minimum_order_size: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fee_rate: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fees_enabled: Mapped[bool | None] = mapped_column(Boolean)
    fee_exponent: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    fee_taker_only: Mapped[bool | None] = mapped_column(Boolean)
    fee_rebate_rate: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    raw_payload_hash: Mapped[str] = mapped_column(String(64))


class EvidenceRow(Base):
    __tablename__ = "evidence_documents"
    __table_args__ = (
        UniqueConstraint("market_id", "content_hash", name="uq_evidence_market_hash"),
        Index("ix_evidence_market_retrieved", "market_id", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    source_url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    extracted_text: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    trust_level: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchReportRow(Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        UniqueConstraint("graph_run_id", name="uq_research_report_graph_run"),
        Index("ix_research_report_market_created", "market_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    graph_run_id: Mapped[UUID] = mapped_column(default=uuid4)
    model_role: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(32))
    estimated_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    maximum_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    recommendation: Mapped[str] = mapped_column(String(16))
    counterarguments: Mapped[list[str]] = mapped_column(JSONB, default=list)
    resolution_interpretation: Mapped[str | None] = mapped_column(Text)
    analysis_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_research_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    graph_stages: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    result_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMUsageRow(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (
        Index("ix_llm_usage_graph_run", "graph_run_id"),
        Index("ix_llm_usage_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    graph_run_id: Mapped[UUID]
    research_report_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_reports.id"))
    model_role: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    success: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderBookLevelRow(Base):
    __tablename__ = "orderbook_levels"
    __table_args__ = (
        UniqueConstraint(
            "market_snapshot_id", "side", "level_index", name="uq_orderbook_snapshot_side_level"
        ),
        Index("ix_orderbook_snapshot_side", "market_snapshot_id", "side", "level_index"),
        CheckConstraint("price BETWEEN 0 AND 1", name="ck_orderbook_level_price"),
        CheckConstraint("size > 0", name="ck_orderbook_level_size"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("market_snapshots.id"))
    side: Mapped[str] = mapped_column(String(8))
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    size: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    level_index: Mapped[int] = mapped_column(Integer)


class PaperOrderRow(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_paper_order_idempotency"),
        UniqueConstraint("trade_proposal_id", "side", name="uq_paper_order_proposal_side"),
        Index("ix_paper_order_market_created", "market_id", "created_at"),
        Index("ix_paper_order_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trade_proposal_id: Mapped[UUID] = mapped_column(ForeignKey("research_reports.id"))
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    outcome_token_id: Mapped[str] = mapped_column(Text)
    side: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    limit_price: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    requested_size_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    requested_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    status: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperFillRow(Base):
    __tablename__ = "paper_fills"
    __table_args__ = (Index("ix_paper_fill_order_filled", "paper_order_id", "filled_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_order_id: Mapped[UUID] = mapped_column(ForeignKey("paper_orders.id"))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    filled_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    filled_notional_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    estimated_fee_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    estimated_spread_cost_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    estimated_slippage_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperPositionRow(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint(
            "market_id", "outcome_token_id", "side", name="uq_paper_position_market_token_side"
        ),
        Index("ix_paper_position_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"))
    outcome_token_id: Mapped[str] = mapped_column(Text)
    side: Mapped[str] = mapped_column(String(8))
    quantity_shares: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    cost_basis_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    realized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    unrealized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    allocated_research_cost_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    current_mark_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    trade_proposal_id: Mapped[UUID] = mapped_column(ForeignKey("research_reports.id"))
    status: Mapped[str] = mapped_column(String(16))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortfolioEventRow(Base):
    __tablename__ = "portfolio_events"
    __table_args__ = (
        UniqueConstraint(
            "event_type", "reference_type", "reference_id", name="uq_portfolio_event_reference"
        ),
        Index("ix_portfolio_event_created", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(32))
    reference_type: Mapped[str] = mapped_column(String(32))
    reference_id: Mapped[UUID]
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    balance_after_usd: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
