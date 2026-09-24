"""PostgreSQL operations. Callers own the transaction boundary."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from eventtrader.domain.markets import (
    BookLevel,
    Market,
    MarketRead,
    OutcomeRead,
    SnapshotRead,
    SnapshotValues,
)
from eventtrader.persistence.models import (
    MarketRow,
    OrderBookLevelRow,
    OutcomeRow,
    SnapshotRow,
)


class MarketRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_market(self, market: Market) -> UUID:
        values = market.model_dump(
            include={
                "provider",
                "external_market_id",
                "slug",
                "question",
                "category",
                "condition_id",
                "status",
                "resolution_rules",
                "resolution_source",
                "close_time",
                "resolved_at",
                "accepting_orders",
                "enable_order_book",
            }
        )
        statement = insert(MarketRow).values(**values)
        # ON CONFLICT also serializes concurrent updates to this market and its outcomes.
        market_id = self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_market_provider_external",
                set_={**values, "updated_at": datetime.now(UTC)},
            ).returning(MarketRow.id)
        ).scalar_one()
        existing = {
            row.outcome_index: row
            for row in self.session.scalars(
                select(OutcomeRow).where(OutcomeRow.market_id == market_id)
            )
        }
        self.session.execute(
            update(OutcomeRow).where(OutcomeRow.market_id == market_id).values(active=False)
        )
        for outcome in market.outcomes:
            old = existing.get(outcome.outcome_index)
            if old and old.token_id is not None and old.token_id != outcome.token_id:
                raise ValueError(
                    "Outcome token identity changed; refusing to rewrite snapshot history"
                )
            statement_outcome = insert(OutcomeRow).values(
                market_id=market_id, **outcome.model_dump()
            )
            self.session.execute(
                statement_outcome.on_conflict_do_update(
                    constraint="uq_outcome_market_index",
                    set_=outcome.model_dump(),
                )
            )
        return market_id

    def add_snapshot(
        self,
        market_id: UUID,
        token_id: str,
        snapshot: SnapshotValues,
        *,
        bids: list[BookLevel] | None = None,
        asks: list[BookLevel] | None = None,
    ) -> UUID:
        outcome_id = self.session.execute(
            select(OutcomeRow.id).where(
                OutcomeRow.market_id == market_id,
                OutcomeRow.token_id == token_id,
            )
        ).scalar_one()
        row = SnapshotRow(market_id=market_id, outcome_id=outcome_id, **snapshot.model_dump())
        self.session.add(row)
        self.session.flush()
        for side, levels in (("BID", bids or []), ("ASK", asks or [])):
            self.session.add_all(
                OrderBookLevelRow(
                    market_snapshot_id=row.id,
                    side=side,
                    price=level.price,
                    size=level.size,
                    level_index=index,
                )
                for index, level in enumerate(levels)
                if level.size > 0
            )
        return row.id

    def get_market(self, market_id: UUID) -> MarketRead | None:
        row = self.session.get(MarketRow, market_id)
        return self._read(row) if row else None

    def list_markets(
        self, *, query: str = "", limit: int = 50, offset: int = 0
    ) -> list[MarketRead]:
        statement = select(MarketRow)
        if query:
            statement = statement.where(MarketRow.question.icontains(query, autoescape=True))
        rows = self.session.scalars(
            statement.order_by(MarketRow.created_at.desc(), MarketRow.id)
            .limit(limit)
            .offset(offset)
        )
        # Bounded manual scanner (<=100 rows); optimize batch loading if profiling warrants it.
        return [self._read(row) for row in rows]

    def snapshots(
        self, market_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[SnapshotRead]:
        rows = self.session.scalars(
            select(SnapshotRow)
            .where(SnapshotRow.market_id == market_id)
            .order_by(SnapshotRow.captured_at.desc(), SnapshotRow.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [SnapshotRead.model_validate(row) for row in rows]

    def _read(self, row: MarketRow) -> MarketRead:
        outcomes = [
            OutcomeRead.model_validate(outcome)
            for outcome in self.session.scalars(
                select(OutcomeRow)
                .where(OutcomeRow.market_id == row.id)
                .order_by(OutcomeRow.outcome_index)
            )
        ]
        latest = self.session.scalars(
            select(SnapshotRow)
            .where(SnapshotRow.market_id == row.id)
            .distinct(SnapshotRow.outcome_id)
            .order_by(SnapshotRow.outcome_id, SnapshotRow.captured_at.desc(), SnapshotRow.id.desc())
        )
        values = {column.name: getattr(row, column.name) for column in MarketRow.__table__.columns}
        return MarketRead(
            **values,
            outcomes=outcomes,
            latest_snapshots=[SnapshotRead.model_validate(item) for item in latest],
        )
