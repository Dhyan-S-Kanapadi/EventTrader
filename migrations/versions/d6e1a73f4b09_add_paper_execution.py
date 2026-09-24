"""Add paper execution, portfolio accounting, and order-book depth.

Revision ID: d6e1a73f4b09
Revises: a4c9f31b8d20
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d6e1a73f4b09"
down_revision: str | None = "a4c9f31b8d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orderbook_levels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("price", sa.Numeric(38, 18), nullable=False),
        sa.Column("size", sa.Numeric(38, 18), nullable=False),
        sa.Column("level_index", sa.Integer(), nullable=False),
        sa.CheckConstraint("price BETWEEN 0 AND 1", name="ck_orderbook_level_price"),
        sa.CheckConstraint("size > 0", name="ck_orderbook_level_size"),
        sa.ForeignKeyConstraint(["market_snapshot_id"], ["market_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_snapshot_id", "side", "level_index", name="uq_orderbook_snapshot_side_level"
        ),
    )
    op.create_index(
        "ix_orderbook_snapshot_side",
        "orderbook_levels",
        ["market_snapshot_id", "side", "level_index"],
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trade_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_token_id", sa.Text(), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("limit_price", sa.Numeric(38, 18), nullable=False),
        sa.Column("requested_size_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("requested_shares", sa.Numeric(38, 18), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("rejection_reason", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["trade_proposal_id"], ["research_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_paper_order_idempotency"),
        sa.UniqueConstraint("trade_proposal_id", "side", name="uq_paper_order_proposal_side"),
    )
    op.create_index("ix_paper_order_market_created", "paper_orders", ["market_id", "created_at"])
    op.create_index("ix_paper_order_status", "paper_orders", ["status"])
    op.create_table(
        "paper_fills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_order_id", sa.Uuid(), nullable=False),
        sa.Column("fill_price", sa.Numeric(38, 18), nullable=False),
        sa.Column("filled_shares", sa.Numeric(38, 18), nullable=False),
        sa.Column("filled_notional_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("estimated_fee_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("estimated_spread_cost_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("estimated_slippage_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_order_id"], ["paper_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_fill_order_filled", "paper_fills", ["paper_order_id", "filled_at"])
    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_token_id", sa.Text(), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity_shares", sa.Numeric(38, 18), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(38, 18), nullable=False),
        sa.Column("cost_basis_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("realized_pnl_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("allocated_research_cost_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("current_mark_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("trade_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["trade_proposal_id"], ["research_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_id", "outcome_token_id", "side", name="uq_paper_position_market_token_side"
        ),
    )
    op.create_index("ix_paper_position_status", "paper_positions", ["status"])
    op.create_table(
        "portfolio_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("balance_after_usd", sa.Numeric(38, 18), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type", "reference_type", "reference_id", name="uq_portfolio_event_reference"
        ),
    )
    op.create_index("ix_portfolio_event_created", "portfolio_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_event_created", table_name="portfolio_events")
    op.drop_table("portfolio_events")
    op.drop_index("ix_paper_position_status", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_index("ix_paper_fill_order_filled", table_name="paper_fills")
    op.drop_table("paper_fills")
    op.drop_index("ix_paper_order_status", table_name="paper_orders")
    op.drop_index("ix_paper_order_market_created", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_index("ix_orderbook_snapshot_side", table_name="orderbook_levels")
    op.drop_table("orderbook_levels")
