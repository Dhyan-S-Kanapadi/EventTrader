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
