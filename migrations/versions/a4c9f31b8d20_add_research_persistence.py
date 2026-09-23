"""Add evidence-grounded research persistence.

Revision ID: a4c9f31b8d20
Revises: 7fe0b5c4acb3
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4c9f31b8d20"
down_revision: str | None = "7fe0b5c4acb3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "content_hash", name="uq_evidence_market_hash"),
    )
    op.create_index(
        "ix_evidence_market_retrieved",
        "evidence_documents",
        ["market_id", "retrieved_at"],
    )
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("graph_run_id", sa.Uuid(), nullable=False),
        sa.Column("model_role", sa.String(32), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("estimated_probability", sa.Numeric(38, 18), nullable=True),
        sa.Column("confidence", sa.Numeric(38, 18), nullable=True),
        sa.Column("maximum_entry_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("recommendation", sa.String(16), nullable=False),
        sa.Column("counterarguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolution_interpretation", sa.Text(), nullable=True),
        sa.Column("analysis_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_research_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("graph_stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_run_id", name="uq_research_report_graph_run"),
    )
    op.create_index(
        "ix_research_report_market_created", "research_reports", ["market_id", "created_at"]
    )
    op.create_index("ix_research_reports_status", "research_reports", ["status"])
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("graph_run_id", sa.Uuid(), nullable=False),
        sa.Column("research_report_id", sa.Uuid(), nullable=True),
        sa.Column("model_role", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["research_report_id"], ["research_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_graph_run", "llm_usage", ["graph_run_id"])
    op.create_index("ix_llm_usage_created", "llm_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_usage_created", table_name="llm_usage")
    op.drop_index("ix_llm_usage_graph_run", table_name="llm_usage")
    op.drop_table("llm_usage")
    op.drop_index("ix_research_reports_status", table_name="research_reports")
    op.drop_index("ix_research_report_market_created", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_index("ix_evidence_market_retrieved", table_name="evidence_documents")
    op.drop_table("evidence_documents")
