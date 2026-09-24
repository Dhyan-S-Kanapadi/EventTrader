"""Transactional paper-execution persistence. Callers own transaction boundaries."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from eventtrader.domain.paper import (
    OrderBookLevelRead,
    PaperFillRead,
    PaperOrderRead,
    PaperPositionRead,
    PortfolioEventRead,
)
from eventtrader.persistence.models import (
    LLMUsageRow,
    MarketRow,
    OrderBookLevelRow,
    OutcomeRow,
    PaperFillRow,
    PaperOrderRow,
    PaperPositionRow,
    PortfolioEventRow,
    ResearchReportRow,
    SnapshotRow,
)

INITIAL_CAPITAL_REFERENCE = UUID("00000000-0000-0000-0000-000000000001")
PORTFOLIO_LOCK = 5_738_291


class PaperRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_portfolio(self) -> None:
        self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": PORTFOLIO_LOCK})

    def initialize_capital(self, amount: Decimal) -> None:
        self.lock_portfolio()
        self.session.execute(
            insert(PortfolioEventRow)
            .values(
                event_type="INITIAL_CAPITAL",
                reference_type="portfolio",
                reference_id=INITIAL_CAPITAL_REFERENCE,
                amount_usd=amount,
                balance_after_usd=amount,
                event_metadata={"mode": "PAPER"},
            )
            .on_conflict_do_nothing(constraint="uq_portfolio_event_reference")
        )

    def cash_balance(self) -> Decimal:
        value = self.session.scalar(
            select(func.coalesce(func.sum(PortfolioEventRow.amount_usd), 0))
        )
        return Decimal(value or 0)

    def realized_pnl_since(self, since: datetime) -> Decimal:
        rows = self.session.scalars(
            select(PortfolioEventRow).where(PortfolioEventRow.created_at >= since)
        )
        total = Decimal("0")
        for row in rows:
            value = row.event_metadata.get("realized_pnl_delta_usd")
            if value is not None:
                total += Decimal(str(value))
        return total

    def event_exists(self, event_type: str, reference_type: str, reference_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(PortfolioEventRow.id).where(
                    PortfolioEventRow.event_type == event_type,
                    PortfolioEventRow.reference_type == reference_type,
                    PortfolioEventRow.reference_id == reference_id,
                )
            )
            is not None
        )

    def record_event(
        self,
        *,
        event_type: str,
        reference_type: str,
        reference_id: UUID,
        amount_usd: Decimal,
        metadata: dict[str, object],
    ) -> PortfolioEventRow:
        self.lock_portfolio()
        balance = self.cash_balance() + amount_usd
        row = PortfolioEventRow(
            event_type=event_type,
            reference_type=reference_type,
            reference_id=reference_id,
            amount_usd=amount_usd,
            balance_after_usd=balance,
            event_metadata=metadata,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def report(self, report_id: UUID) -> ResearchReportRow | None:
        return self.session.get(ResearchReportRow, report_id)

    def report_research_cost(self, report_id: UUID) -> Decimal:
        value = self.session.scalar(
            select(func.coalesce(func.sum(LLMUsageRow.estimated_cost_usd), 0)).where(
                LLMUsageRow.research_report_id == report_id,
                LLMUsageRow.success.is_(True),
            )
        )
        return Decimal(value or 0)

    def latest_snapshot(
        self, market_id: UUID, token_id: str
    ) -> tuple[SnapshotRow, list[OrderBookLevelRead]] | None:
        snapshot = self.session.scalar(
            select(SnapshotRow)
            .join(OutcomeRow, OutcomeRow.id == SnapshotRow.outcome_id)
            .where(
                SnapshotRow.market_id == market_id,
                OutcomeRow.token_id == token_id,
            )
            .order_by(SnapshotRow.captured_at.desc(), SnapshotRow.id.desc())
            .limit(1)
        )
        if snapshot is None:
            return None
        levels = self.session.scalars(
            select(OrderBookLevelRow)
            .where(OrderBookLevelRow.market_snapshot_id == snapshot.id)
            .order_by(OrderBookLevelRow.side, OrderBookLevelRow.level_index)
        )
        return snapshot, [OrderBookLevelRead.model_validate(item) for item in levels]

    def order_by_idempotency(self, key: str) -> PaperOrderRow | None:
        return self.session.scalar(
            select(PaperOrderRow).where(PaperOrderRow.idempotency_key == key)
        )

    def order(self, order_id: UUID) -> PaperOrderRow | None:
        return self.session.get(PaperOrderRow, order_id)

    def order_for_proposal(self, report_id: UUID, side: str) -> PaperOrderRow | None:
        return self.session.scalar(
            select(PaperOrderRow).where(
                PaperOrderRow.trade_proposal_id == report_id,
                PaperOrderRow.side == side,
            )
        )

    def orders(self, *, limit: int = 100, offset: int = 0) -> list[PaperOrderRead]:
        rows = self.session.scalars(
            select(PaperOrderRow)
            .order_by(PaperOrderRow.created_at.desc(), PaperOrderRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self.order_read(row) for row in rows]

    def fills(self, order_id: UUID) -> list[PaperFillRead]:
        rows = self.session.scalars(
            select(PaperFillRow)
            .where(PaperFillRow.paper_order_id == order_id)
            .order_by(PaperFillRow.filled_at, PaperFillRow.id)
        )
        return [PaperFillRead.model_validate(row) for row in rows]

    def order_read(self, row: PaperOrderRow) -> PaperOrderRead:
        values = {
            column.name: getattr(row, column.name) for column in PaperOrderRow.__table__.columns
        }
        return PaperOrderRead(**values, fills=self.fills(row.id))

    def positions(self, *, open_only: bool = False) -> list[PaperPositionRead]:
        statement = select(PaperPositionRow)
        if open_only:
            statement = statement.where(PaperPositionRow.status == "OPEN")
        rows = self.session.scalars(
            statement.order_by(PaperPositionRow.opened_at, PaperPositionRow.id)
        )
        return [PaperPositionRead.model_validate(row) for row in rows]

    def position(
        self, market_id: UUID, token_id: str, side: str = "LONG"
    ) -> PaperPositionRow | None:
        return self.session.scalar(
            select(PaperPositionRow).where(
                PaperPositionRow.market_id == market_id,
                PaperPositionRow.outcome_token_id == token_id,
                PaperPositionRow.side == side,
            )
        )

    def events(self, *, limit: int = 500) -> list[PortfolioEventRead]:
        rows = self.session.scalars(
            select(PortfolioEventRow)
            .order_by(PortfolioEventRow.created_at, PortfolioEventRow.id)
            .limit(limit)
        )
        return [PortfolioEventRead.model_validate(row) for row in rows]

    def open_buy_reserve(self) -> Decimal:
        value = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        (
                            PaperOrderRow.requested_shares
                            - func.coalesce(
                                select(func.sum(PaperFillRow.filled_shares))
                                .where(PaperFillRow.paper_order_id == PaperOrderRow.id)
                                .correlate(PaperOrderRow)
                                .scalar_subquery(),
                                0,
                            )
                        )
                        * PaperOrderRow.limit_price
                    ),
                    0,
                )
            ).where(
                PaperOrderRow.side == "BUY",
                PaperOrderRow.status.in_(["CREATED", "OPEN", "PARTIALLY_FILLED"]),
            )
        )
        return max(Decimal(value or 0), Decimal("0"))

    def market(self, market_id: UUID) -> MarketRow | None:
        return self.session.get(MarketRow, market_id)

    def outcome_index(self, market_id: UUID, token_id: str) -> tuple[int, int] | None:
        outcome = self.session.scalar(
            select(OutcomeRow).where(
                OutcomeRow.market_id == market_id,
                OutcomeRow.token_id == token_id,
            )
        )
        if outcome is None:
            return None
        count = self.session.scalar(
            select(func.count(OutcomeRow.id)).where(OutcomeRow.market_id == market_id)
        )
        return outcome.outcome_index, int(count or 0)

    def expire_orders(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        rows = self.session.scalars(
            select(PaperOrderRow).where(
                PaperOrderRow.status.in_(["CREATED", "OPEN", "PARTIALLY_FILLED"]),
                PaperOrderRow.expires_at <= current,
            )
        )
        for row in rows:
            row.status = "EXPIRED"
            row.updated_at = current
