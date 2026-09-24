"""Deterministic paper-only execution and portfolio accounting."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventtrader.domain.paper import (
    OrderBookLevelRead,
    PaperExecutionResult,
    PaperOrderCreate,
    PaperOrderRead,
    PaperPortfolioRead,
)
from eventtrader.persistence.models import (
    PaperFillRow,
    PaperOrderRow,
    PaperPositionRow,
    SnapshotRow,
)
from eventtrader.persistence.paper_repository import PaperRepository
from eventtrader.settings import Settings


class PaperExecutionError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class PaperExecutionService:
    """Simulates public-book fills. It has no provider trading client or credentials."""

    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings

    def submit(self, request: PaperOrderCreate) -> PaperExecutionResult:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            existing = repo.order_by_idempotency(request.idempotency_key)
            if existing is not None:
                return PaperExecutionResult(
                    order=repo.order_read(existing),
                    portfolio=self._portfolio(session, repo),
                )
            duplicate = repo.order_for_proposal(request.trade_proposal_id, request.side)
            if duplicate is not None:
                return PaperExecutionResult(
                    order=repo.order_read(duplicate),
                    portfolio=self._portfolio(session, repo),
                )
            report = repo.report(request.trade_proposal_id)
            if report is None:
                raise PaperExecutionError("APPROVED_PROPOSAL_NOT_FOUND")
            if report.status != "APPROVED_FOR_PAPER" or not report.result_payload:
                raise PaperExecutionError("PROPOSAL_NOT_APPROVED")
            proposal = report.result_payload.get("proposal")
            if not isinstance(proposal, dict):
                raise PaperExecutionError("INVALID_PROPOSAL_PAYLOAD")
            market_id = report.market_id
            token_id = proposal.get("chosen_outcome_token_id")
            if not isinstance(token_id, str) or not token_id:
                raise PaperExecutionError("INVALID_PROPOSAL_TOKEN")
            if request.expires_at <= datetime.now(UTC):
                raise PaperExecutionError("ORDER_ALREADY_EXPIRED")
            if request.limit_price <= 0:
                raise PaperExecutionError("INVALID_LIMIT_PRICE")
            maximum_entry = Decimal(str(proposal.get("maximum_entry_price", "0")))
            if request.side == "BUY" and request.limit_price > maximum_entry:
                raise PaperExecutionError("LIMIT_PRICE_EXCEEDS_PROPOSAL")
            snapshot_and_levels = repo.latest_snapshot(market_id, token_id)
            if snapshot_and_levels is None:
                raise PaperExecutionError("MISSING_ORDERBOOK_SNAPSHOT")
            snapshot, levels = snapshot_and_levels
            cutoff = datetime.now(UTC) - timedelta(minutes=self.settings.snapshot_max_age_minutes)
            if snapshot.captured_at < cutoff:
                raise PaperExecutionError("STALE_ORDERBOOK_SNAPSHOT")
            if snapshot.tick_size is None or snapshot.minimum_order_size is None:
                raise PaperExecutionError("MISSING_MARKET_CONSTRAINTS")
            if request.limit_price % snapshot.tick_size != 0:
                raise PaperExecutionError("INVALID_TICK_SIZE")
            if snapshot.fees_enabled is not False and snapshot.fee_rate is None:
                raise PaperExecutionError("UNKNOWN_FEE_COST")

            if request.side == "BUY":
                assert request.requested_size_usd is not None
                requested_size = request.requested_size_usd
                requested_shares = requested_size / request.limit_price
                self._validate_buy_risk(session, repo, requested_size, market_id)
            else:
                assert request.requested_shares is not None
                requested_shares = request.requested_shares
                requested_size = requested_shares * request.limit_price
                position = repo.position(market_id, token_id)
                if (
                    position is None
                    or position.status != "OPEN"
                    or position.quantity_shares < requested_shares
                ):
                    raise PaperExecutionError("SELL_EXCEEDS_POSITION")

            if requested_shares < snapshot.minimum_order_size:
                raise PaperExecutionError("BELOW_MINIMUM_ORDER_SIZE")

            order = PaperOrderRow(
                trade_proposal_id=report.id,
                market_id=market_id,
                outcome_token_id=token_id,
                side=request.side,
                order_type="LIMIT",
                limit_price=request.limit_price,
                requested_size_usd=requested_size,
                requested_shares=requested_shares,
                status="CREATED",
                idempotency_key=request.idempotency_key,
                expires_at=request.expires_at,
            )
            session.add(order)
            session.flush()
            self._simulate_and_account(session, repo, order, snapshot, levels)
            self._mark_positions(session, repo)
            session.flush()
            return PaperExecutionResult(
                order=repo.order_read(order),
                portfolio=self._portfolio(session, repo),
            )

    def cancel(self, order_id: UUID) -> PaperOrderRead:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            order = repo.order(order_id)
            if order is None:
                raise PaperExecutionError("PAPER_ORDER_NOT_FOUND")
            if order.status not in {"CREATED", "OPEN", "PARTIALLY_FILLED"}:
                raise PaperExecutionError("PAPER_ORDER_NOT_CANCELLABLE")
            order.status = "CANCELLED"
            order.updated_at = datetime.now(UTC)
            session.flush()
            return repo.order_read(order)

    def mark_to_market(self) -> PaperPortfolioRead:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            self._mark_positions(session, repo)
            return self._portfolio(session, repo)

    def portfolio(self) -> PaperPortfolioRead:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            return self._portfolio(session, repo)

    def orders(self, *, limit: int = 100, offset: int = 0) -> list[PaperOrderRead]:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            return repo.orders(limit=limit, offset=offset)

    def order(self, order_id: UUID) -> PaperOrderRead | None:
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            repo.expire_orders()
            row = repo.order(order_id)
            return repo.order_read(row) if row else None

    def _validate_buy_risk(
        self,
        session: Session,
        repo: PaperRepository,
        requested_size: Decimal,
        market_id: UUID,
    ) -> None:
        portfolio = self._portfolio(session, repo)
        if requested_size > self.settings.max_single_position_usd:
            raise PaperExecutionError("SINGLE_POSITION_LIMIT")
        if portfolio.open_exposure_usd + requested_size > self.settings.max_total_exposure_usd:
            raise PaperExecutionError("TOTAL_EXPOSURE_LIMIT")
        if portfolio.available_cash_usd - requested_size < self.settings.min_cash_reserve_usd:
            raise PaperExecutionError("CASH_RESERVE_LIMIT")
        open_markets = {item.market_id for item in portfolio.positions if item.status == "OPEN"}
        if (
            market_id not in open_markets
            and len(open_markets) >= self.settings.max_simultaneous_markets
        ):
            raise PaperExecutionError("SIMULTANEOUS_MARKET_LIMIT")
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = session.scalar(
            select(func.count(PaperOrderRow.id)).where(
                PaperOrderRow.created_at >= today,
                PaperOrderRow.status.in_(["FILLED", "PARTIALLY_FILLED"]),
            )
        )
        if int(trades_today or 0) >= self.settings.max_trades_per_day:
            raise PaperExecutionError("DAILY_TRADE_LIMIT")
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        if repo.realized_pnl_since(day_start) <= -self.settings.max_daily_loss_usd:
            raise PaperExecutionError("DAILY_LOSS_LIMIT")
        if repo.realized_pnl_since(week_start) <= -self.settings.max_weekly_loss_usd:
            raise PaperExecutionError("WEEKLY_LOSS_LIMIT")
        drawdown = max(
            Decimal("0"),
            -portfolio.total_net_pnl_usd / self.settings.starting_capital_usd * Decimal("100"),
        )
        if drawdown >= self.settings.max_drawdown_percent:
            raise PaperExecutionError("DRAWDOWN_LIMIT")

    def _simulate_and_account(
        self,
        session: Session,
        repo: PaperRepository,
        order: PaperOrderRow,
        snapshot: SnapshotRow,
        levels: list[OrderBookLevelRead],
    ) -> None:
        wanted_side = "ASK" if order.side == "BUY" else "BID"
        book = [item for item in levels if item.side == wanted_side]
        reverse = order.side == "SELL"
        book.sort(key=lambda item: item.price, reverse=reverse)
        eligible = [
            item
            for item in book
            if (
                item.price <= order.limit_price
                if order.side == "BUY"
                else item.price >= order.limit_price
            )
        ]
        if not book:
            order.status = "REJECTED"
            order.rejection_reason = "INSUFFICIENT_LIQUIDITY"
            order.updated_at = datetime.now(UTC)
            return
        if not eligible:
            order.status = "OPEN"
            order.updated_at = datetime.now(UTC)
            return

        remaining = order.requested_shares
        shares = Decimal("0")
        notional = Decimal("0")
        raw_fee = Decimal("0")
        fee_rate = snapshot.fee_rate or Decimal("0")
        for level in eligible:
            take = min(remaining, level.size)
            if take <= 0:
                continue
            shares += take
            notional += take * level.price
            raw_fee += take * fee_rate * level.price * (Decimal("1") - level.price)
            remaining -= take
            if remaining <= 0:
                break
        if shares <= 0:
            order.status = "REJECTED"
            order.rejection_reason = "INSUFFICIENT_LIQUIDITY"
            order.updated_at = datetime.now(UTC)
            return

        average = notional / shares
        fee = raw_fee.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        midpoint = snapshot.midpoint
        if midpoint is None and snapshot.best_bid is not None and snapshot.best_ask is not None:
            midpoint = (snapshot.best_bid + snapshot.best_ask) / 2
        spread_cost = Decimal("0")
        if midpoint is not None:
            touch = snapshot.best_ask if order.side == "BUY" else snapshot.best_bid
            if touch is not None:
                spread_cost = shares * abs(touch - midpoint)
        touch = snapshot.best_ask if order.side == "BUY" else snapshot.best_bid
        slippage = shares * abs(average - touch) if touch is not None else Decimal("0")
        fill = PaperFillRow(
            paper_order_id=order.id,
            fill_price=average,
            filled_shares=shares,
            filled_notional_usd=notional,
            estimated_fee_usd=fee,
            estimated_spread_cost_usd=spread_cost,
            estimated_slippage_usd=slippage,
            filled_at=datetime.now(UTC),
        )
        session.add(fill)
        session.flush()
        order.status = "FILLED" if remaining <= 0 else "PARTIALLY_FILLED"
        order.updated_at = datetime.now(UTC)
        self._apply_fill(session, repo, order, fill)

    def _apply_fill(
        self,
        session: Session,
        repo: PaperRepository,
        order: PaperOrderRow,
        fill: PaperFillRow,
    ) -> None:
        position = repo.position(order.market_id, order.outcome_token_id)
        if order.side == "BUY":
            research_total = repo.report_research_cost(order.trade_proposal_id)
            research_allocated = research_total * (fill.filled_shares / order.requested_shares)
            if position is None:
                position = PaperPositionRow(
                    market_id=order.market_id,
                    outcome_token_id=order.outcome_token_id,
                    side="LONG",
                    quantity_shares=Decimal("0"),
                    average_entry_price=Decimal("0"),
                    cost_basis_usd=Decimal("0"),
                    realized_pnl_usd=Decimal("0"),
                    unrealized_pnl_usd=Decimal("0"),
                    allocated_research_cost_usd=Decimal("0"),
                    current_mark_price=None,
                    trade_proposal_id=order.trade_proposal_id,
                    status="OPEN",
                    opened_at=fill.filled_at,
                    closed_at=None,
                )
                session.add(position)
                session.flush()
            old_notional = position.average_entry_price * position.quantity_shares
            position.quantity_shares += fill.filled_shares
            position.average_entry_price = (
                old_notional + fill.filled_notional_usd
            ) / position.quantity_shares
            position.cost_basis_usd += (
                fill.filled_notional_usd + fill.estimated_fee_usd + research_allocated
            )
            position.allocated_research_cost_usd += research_allocated
            position.trade_proposal_id = order.trade_proposal_id
            position.status = "OPEN"
            position.closed_at = None
            cash_amount = -(fill.filled_notional_usd + fill.estimated_fee_usd)
            realized_delta = Decimal("0")
        else:
            if position is None or position.quantity_shares < fill.filled_shares:
                raise PaperExecutionError("SELL_EXCEEDS_POSITION")
            basis_released = position.cost_basis_usd * fill.filled_shares / position.quantity_shares
            proceeds = fill.filled_notional_usd - fill.estimated_fee_usd
            realized_delta = proceeds - basis_released
            position.realized_pnl_usd += realized_delta
            position.quantity_shares -= fill.filled_shares
            position.cost_basis_usd -= basis_released
            if position.quantity_shares == 0:
                position.status = "CLOSED"
                position.closed_at = fill.filled_at
                position.unrealized_pnl_usd = Decimal("0")
                position.current_mark_price = fill.fill_price
            cash_amount = proceeds
        repo.record_event(
            event_type="PAPER_FILL",
            reference_type="paper_fill",
            reference_id=fill.id,
            amount_usd=cash_amount,
            metadata={
                "mode": "PAPER",
                "order_id": str(order.id),
                "side": order.side,
                "fee_usd": str(fill.estimated_fee_usd),
                "spread_cost_usd": str(fill.estimated_spread_cost_usd),
                "slippage_usd": str(fill.estimated_slippage_usd),
                "realized_pnl_delta_usd": str(realized_delta),
            },
        )

    def _mark_positions(self, session: Session, repo: PaperRepository) -> None:
        rows = session.scalars(select(PaperPositionRow).where(PaperPositionRow.status == "OPEN"))
        for position in rows:
            snapshot_and_levels = repo.latest_snapshot(
                position.market_id, position.outcome_token_id
            )
            if snapshot_and_levels is None:
                continue
            snapshot, _ = snapshot_and_levels
            mark = (
                snapshot.best_bid
                if snapshot.best_bid is not None
                else snapshot.last_trade_price
                if snapshot.last_trade_price is not None
                else snapshot.midpoint
            )
            if mark is None:
                continue
            position.current_mark_price = mark
            position.unrealized_pnl_usd = position.quantity_shares * mark - position.cost_basis_usd

    def _portfolio(self, session: Session, repo: PaperRepository) -> PaperPortfolioRead:
        positions = repo.positions()
        events = repo.events()
        cash = repo.cash_balance()
        reserved = repo.open_buy_reserve()
        fills = list(session.scalars(select(PaperFillRow)))
        realized = sum((item.realized_pnl_usd for item in positions), start=Decimal("0"))
        unrealized = sum((item.unrealized_pnl_usd for item in positions), start=Decimal("0"))
        exposure = sum(
            (item.cost_basis_usd for item in positions if item.status == "OPEN"),
            start=Decimal("0"),
        )
        return PaperPortfolioRead(
            starting_capital_usd=self.settings.starting_capital_usd,
            cash_balance_usd=cash,
            reserved_cash_usd=reserved,
            available_cash_usd=cash - reserved,
            open_exposure_usd=exposure,
            realized_pnl_usd=realized,
            unrealized_pnl_usd=unrealized,
            total_net_pnl_usd=realized + unrealized,
            total_fees_usd=sum((item.estimated_fee_usd for item in fills), start=Decimal("0")),
            total_spread_cost_usd=sum(
                (item.estimated_spread_cost_usd for item in fills),
                start=Decimal("0"),
            ),
            total_slippage_usd=sum(
                (item.estimated_slippage_usd for item in fills),
                start=Decimal("0"),
            ),
            total_research_cost_usd=sum(
                (item.allocated_research_cost_usd for item in positions),
                start=Decimal("0"),
            ),
            positions=positions,
            events=events,
        )
