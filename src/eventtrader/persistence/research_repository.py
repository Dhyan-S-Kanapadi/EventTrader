"""Typed persistence for evidence, reports, and model usage."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from eventtrader.domain.research import (
    EvidenceDocument,
    LLMUsageRead,
    ResearchReportRead,
)
from eventtrader.persistence.models import EvidenceRow, LLMUsageRow, ResearchReportRow


class ResearchRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_evidence(
        self,
        *,
        market_id: UUID,
        source_url: str,
        publisher: str | None,
        title: str | None,
        published_at: datetime | None,
        extracted_text: str,
        source_type: str,
        trust_level: str,
        content_hash: str,
        retrieved_at: datetime | None = None,
    ) -> EvidenceDocument:
        values = {
            "market_id": market_id,
            "source_url": source_url,
            "publisher": publisher,
            "title": title,
            "published_at": published_at,
            "retrieved_at": retrieved_at or datetime.now(UTC),
            "content_hash": content_hash,
            "extracted_text": extracted_text,
            "source_type": source_type,
            "trust_level": trust_level,
        }
        row = self.session.execute(
            insert(EvidenceRow)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_evidence_market_hash",
                set_={
                    "retrieved_at": values["retrieved_at"],
                    "source_url": source_url,
                    "publisher": publisher,
                    "title": title,
                    "published_at": published_at,
                    "trust_level": trust_level,
                },
            )
            .returning(EvidenceRow)
        ).scalar_one()
        return EvidenceDocument.model_validate(row)

    def evidence(self, market_id: UUID) -> list[EvidenceDocument]:
        rows = self.session.scalars(
            select(EvidenceRow)
            .where(EvidenceRow.market_id == market_id)
            .order_by(EvidenceRow.retrieved_at.desc())
        )
        return [EvidenceDocument.model_validate(row) for row in rows]

    def daily_cost(self) -> Decimal:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        value = self.session.scalar(
            select(func.coalesce(func.sum(LLMUsageRow.estimated_cost_usd), 0)).where(
                LLMUsageRow.created_at >= start,
                LLMUsageRow.success.is_(True),
            )
        )
        return Decimal(value or 0)

    def persist_report(
        self,
        *,
        values: dict[str, object],
        usage: list[dict[str, object]],
    ) -> ResearchReportRead:
        row = ResearchReportRow(**values)
        self.session.add(row)
        self.session.flush()
        for item in usage:
            self.session.add(LLMUsageRow(research_report_id=row.id, **item))
        self.session.flush()
        return ResearchReportRead.model_validate(row)

    def reports(self, *, limit: int = 50, offset: int = 0) -> list[ResearchReportRead]:
        rows = self.session.scalars(
            select(ResearchReportRow)
            .order_by(ResearchReportRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [ResearchReportRead.model_validate(row) for row in rows]

    def report(self, graph_run_id: UUID) -> ResearchReportRead | None:
        row = self.session.scalar(
            select(ResearchReportRow).where(ResearchReportRow.graph_run_id == graph_run_id)
        )
        return ResearchReportRead.model_validate(row) if row else None

    def usage(self, *, limit: int = 100, offset: int = 0) -> list[LLMUsageRead]:
        rows = self.session.scalars(
            select(LLMUsageRow).order_by(LLMUsageRow.created_at.desc()).limit(limit).offset(offset)
        )
        return [LLMUsageRead.model_validate(row) for row in rows]

    def has_recent_evidence(self, market_id: UUID, hours: int) -> bool:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        return (
            self.session.scalar(
                select(func.count(EvidenceRow.id)).where(
                    EvidenceRow.market_id == market_id,
                    EvidenceRow.retrieved_at >= cutoff,
                )
            )
            or 0
        ) > 0
