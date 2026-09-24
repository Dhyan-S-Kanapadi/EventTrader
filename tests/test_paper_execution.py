import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eventtrader.domain.markets import BookLevel, SnapshotValues
from eventtrader.domain.paper import PaperOrderCreate, SettlementInstruction
from eventtrader.market_data.polymarket import normalize_market
from eventtrader.orchestration.paper_graph import build_paper_execution_graph
from eventtrader.paper_execution.reconciliation import ReconciliationService
from eventtrader.paper_execution.service import PaperExecutionError, PaperExecutionService
from eventtrader.persistence.models import (
    LLMUsageRow,
    OrderBookLevelRow,
    PaperFillRow,
    PaperOrderRow,
    PortfolioEventRow,
    ResearchReportRow,
)
from eventtrader.persistence.paper_repository import PaperRepository
from eventtrader.persistence.repository import MarketRepository
from eventtrader.settings import Settings

D = Decimal


def seed_trade(
    engine,
    gamma_payload,
    *,
    bids: list[tuple[str, str]] | None = None,
    asks: list[tuple[str, str]] | None = None,
    best_bid: str = "0.39",
    best_ask: str = "0.40",
    fee_rate: str = "0",
    research_cost: str = "0.10",
) -> tuple[UUID, UUID, str]:
    now = datetime.now(UTC)
    market = normalize_market(gamma_payload, "fixture").model_copy(
        update={
            "status": "active",
            "close_time": now + timedelta(days=7),
            "resolution_rules": "Resolves Yes if the event occurs.",
            "resolution_source": "https://example.org/rules",
        }
    )
    token_id = market.outcomes[0].token_id
    assert token_id is not None
    bid_levels = [BookLevel(price=D(price), size=D(size)) for price, size in bids or []]
    ask_levels = [BookLevel(price=D(price), size=D(size)) for price, size in asks or []]
    graph_run_id = uuid4()
    with Session(engine) as session, session.begin():
        repo = MarketRepository(session)
        market_id = repo.upsert_market(market)
        repo.add_snapshot(
            market_id,
            token_id,
            SnapshotValues(
                captured_at=now,
                metadata_captured_at=now,
                best_bid=D(best_bid),
                best_ask=D(best_ask),
                midpoint=(D(best_bid) + D(best_ask)) / 2,
                spread=D(best_ask) - D(best_bid),
                minimum_order_size=D("1"),
                tick_size=D("0.01"),
                fee_rate=D(fee_rate),
                fees_enabled=D(fee_rate) != 0,
                raw_payload_hash="a" * 64,
            ),
            bids=bid_levels,
            asks=ask_levels,
        )
        report = ResearchReportRow(
            market_id=market_id,
            graph_run_id=graph_run_id,
            model_role="research",
            model_name="mock",
            prompt_version="v1",
            estimated_probability=D("0.70"),
            confidence=D("0.60"),
            maximum_entry_price=D("0.60"),
            recommendation="BUY",
            counterarguments=["fixture"],
            resolution_interpretation="fixture",
            analysis_expires_at=now + timedelta(hours=2),
            total_research_cost_usd=D(research_cost),
            status="APPROVED_FOR_PAPER",
            reason_codes=[],
            graph_stages=[],
            result_payload={
                "proposal": {
                    "chosen_outcome_token_id": token_id,
                    "maximum_entry_price": "0.60",
                }
            },
        )
        session.add(report)
        session.flush()
        session.add(
            LLMUsageRow(
                graph_run_id=graph_run_id,
                research_report_id=report.id,
                model_role="research",
                provider="mock",
                model_name="mock",
                input_tokens=10,
                output_tokens=10,
                latency_ms=1,
                estimated_cost_usd=D(research_cost),
                success=True,
                error_code=None,
            )
        )
        report_id = report.id
    return market_id, report_id, token_id


def buy(
    report_id: UUID, *, size: str = "2.50", limit: str = "0.50", key: str = "buy-order-1"
) -> PaperOrderCreate:
    return PaperOrderCreate(
        trade_proposal_id=report_id,
        side="BUY",
        limit_price=D(limit),
        requested_size_usd=D(size),
        idempotency_key=key,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_full_fill_accounts_cash_costs_and_depth(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(
        pg_engine,
        gamma_payload,
        bids=[("0.39", "20")],
        asks=[("0.40", "20")],
        fee_rate="0.02",
    )
    result = PaperExecutionService(pg_engine, Settings()).submit(buy(report_id))

    assert result.order.status == "FILLED"
    fill = result.order.fills[0]
    assert fill.filled_shares == D("5")
    assert fill.filled_notional_usd == D("2.00")
    assert fill.estimated_fee_usd == D("0.024")
    assert result.portfolio.cash_balance_usd == D("47.976")
    assert result.portfolio.positions[0].cost_basis_usd == D("2.124")
    assert result.portfolio.total_research_cost_usd == D("0.10")
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(OrderBookLevelRow)) == 2


def test_multi_level_partial_fill_reserves_remainder_and_measures_slippage(
    pg_engine, gamma_payload
):
    _, report_id, _ = seed_trade(
        pg_engine,
        gamma_payload,
        asks=[("0.40", "2"), ("0.45", "1"), ("0.70", "50")],
    )
    result = PaperExecutionService(pg_engine, Settings()).submit(buy(report_id))

    assert result.order.status == "PARTIALLY_FILLED"
    fill = result.order.fills[0]
    assert fill.filled_shares == D("3")
    assert fill.filled_notional_usd == D("1.25")
    assert fill.fill_price == D("0.416666666666666667")
    assert fill.estimated_slippage_usd == D("0.05")
    assert result.portfolio.reserved_cash_usd == D("1.00")
    assert result.portfolio.available_cash_usd == D("47.75")


def test_empty_book_rejects_and_non_marketable_limit_opens(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload)
    service = PaperExecutionService(pg_engine, Settings())
    rejected = service.submit(buy(report_id))
    assert rejected.order.status == "REJECTED"
    assert rejected.order.rejection_reason == "INSUFFICIENT_LIQUIDITY"

    _, second_report_id, _ = seed_trade(
        pg_engine,
        {**gamma_payload, "id": "other", "slug": "other-market", "conditionId": "0xother"},
        asks=[("0.55", "20")],
    )
    opened = service.submit(buy(second_report_id, limit="0.50", key="buy-order-2"))
    assert opened.order.status == "OPEN"
    assert opened.portfolio.reserved_cash_usd == D("2.50")


def test_limit_risk_and_idempotency_guards(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload, asks=[("0.40", "20")])
    service = PaperExecutionService(pg_engine, Settings())
    with pytest.raises(PaperExecutionError, match="LIMIT_PRICE_EXCEEDS_PROPOSAL"):
        service.submit(buy(report_id, limit="0.61"))
    with pytest.raises(PaperExecutionError, match="SINGLE_POSITION_LIMIT"):
        service.submit(buy(report_id, size="3.00", key="too-large"))

    first = service.submit(buy(report_id, key="idempotent-order"))
    repeated = service.submit(buy(report_id, key="idempotent-order"))
    assert repeated.order.id == first.order.id
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(PaperOrderRow)) == 1
        assert session.scalar(select(func.count()).select_from(PaperFillRow)) == 1
        assert session.scalar(select(func.count()).select_from(PortfolioEventRow)) == 2


def test_mark_sell_and_sell_exceeds_position(pg_engine, gamma_payload):
    market_id, report_id, token_id = seed_trade(
        pg_engine,
        gamma_payload,
        bids=[("0.39", "20")],
        asks=[("0.40", "20")],
        research_cost="0",
    )
    service = PaperExecutionService(pg_engine, Settings())
    service.submit(buy(report_id))
    with pytest.raises(PaperExecutionError, match="SELL_EXCEEDS_POSITION"):
        service.submit(
            PaperOrderCreate(
                trade_proposal_id=report_id,
                side="SELL",
                limit_price=D("0.39"),
                requested_shares=D("6"),
                idempotency_key="oversell-order",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    with Session(pg_engine) as session, session.begin():
        MarketRepository(session).add_snapshot(
            market_id,
            token_id,
            SnapshotValues(
                captured_at=datetime.now(UTC) + timedelta(seconds=1),
                metadata_captured_at=datetime.now(UTC),
                best_bid=D("0.60"),
                best_ask=D("0.61"),
                midpoint=D("0.605"),
                spread=D("0.01"),
                minimum_order_size=D("1"),
                tick_size=D("0.01"),
                fees_enabled=False,
                raw_payload_hash="b" * 64,
            ),
            bids=[BookLevel(price=D("0.60"), size=D("20"))],
            asks=[BookLevel(price=D("0.61"), size=D("20"))],
        )
    marked = service.mark_to_market()
    assert marked.positions[0].current_mark_price == D("0.60")
    assert marked.positions[0].unrealized_pnl_usd == D("1.00")

    sold = service.submit(
        PaperOrderCreate(
            trade_proposal_id=report_id,
            side="SELL",
            limit_price=D("0.60"),
            requested_shares=D("5"),
            idempotency_key="sell-order-1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    assert sold.order.status == "FILLED"
    assert sold.portfolio.positions[0].status == "CLOSED"
    assert sold.portfolio.cash_balance_usd == D("51.00")
    assert sold.portfolio.realized_pnl_usd == D("1.00")


def test_realized_daily_loss_blocks_new_buy(pg_engine, gamma_payload):
    market_id, report_id, token_id = seed_trade(
        pg_engine,
        gamma_payload,
        bids=[("0.10", "20")],
        asks=[("0.40", "20")],
        best_bid="0.10",
        research_cost="0",
    )
    service = PaperExecutionService(pg_engine, Settings())
    service.submit(buy(report_id))
    service.submit(
        PaperOrderCreate(
            trade_proposal_id=report_id,
            side="SELL",
            limit_price=D("0.10"),
            requested_shares=D("5"),
            idempotency_key="loss-making-sell",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    _, next_report_id, _ = seed_trade(
        pg_engine,
        {
            **gamma_payload,
            "id": "after-loss",
            "slug": "after-loss-market",
            "conditionId": "0xafterloss",
        },
        asks=[("0.40", "20")],
    )
    assert market_id is not None and token_id
    guarded = PaperExecutionService(
        pg_engine,
        Settings(max_daily_loss_usd=D("1")),
    )
    with pytest.raises(PaperExecutionError, match="DAILY_LOSS_LIMIT"):
        guarded.submit(buy(next_report_id, key="blocked-after-loss"))


def test_resolution_settlement_and_unavailable_warning_are_idempotent(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload, asks=[("0.40", "20")])
    service = PaperExecutionService(pg_engine, Settings())
    bought = service.submit(buy(report_id))
    position_id = bought.portfolio.positions[0].id
    instruction = SettlementInstruction(
        condition_id=gamma_payload["conditionId"],
        payouts=[D("1"), D("0")],
        resolved_at=datetime.now(UTC),
        source="official-fixture",
    )
    reconciliation = ReconciliationService(pg_engine, Settings())
    first = asyncio.run(reconciliation.reconcile(manual=[instruction]))
    second = asyncio.run(reconciliation.reconcile(manual=[instruction]))
    assert first.settled_position_ids == [position_id]
    assert second.settled_position_ids == []
    settled = service.portfolio()
    assert settled.positions[0].status == "SETTLED"
    assert settled.cash_balance_usd == D("53.00")
    assert settled.realized_pnl_usd == D("2.90")

    _, other_report_id, _ = seed_trade(
        pg_engine,
        {**gamma_payload, "id": "warn", "slug": "warn-market", "conditionId": "0xwarn"},
        asks=[("0.40", "20")],
    )
    warning_position = service.submit(buy(other_report_id, key="warning-buy"))

    class NullResolutionProvider:
        async def get_resolution(self, condition_id: str, outcome_count: int):
            return None

    provider = NullResolutionProvider()
    warned = asyncio.run(reconciliation.reconcile(provider=provider, manual=[instruction]))
    assert str(warning_position.portfolio.positions[-1].market_id) in warned.warnings[0]
    again = asyncio.run(reconciliation.reconcile(provider=provider, manual=[instruction]))
    assert again.warnings == warned.warnings
    with Session(pg_engine) as session:
        warnings = session.scalar(
            select(func.count())
            .select_from(PortfolioEventRow)
            .where(PortfolioEventRow.event_type == "RECONCILIATION_WARNING")
        )
        assert warnings == 1


def test_explicit_graph_runs_all_paper_stages_and_has_no_live_route(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload, asks=[("0.40", "20")])
    state = build_paper_execution_graph(PaperExecutionService(pg_engine, Settings())).invoke(
        {"request": buy(report_id), "stages": []}
    )
    assert state["result"].order.status == "FILLED"
    assert state["stages"] == [
        "create_paper_order",
        "simulate_paper_fill",
        "update_paper_portfolio",
        "record_portfolio_event",
    ]
    from eventtrader.api.main import app

    paths = set(app.openapi()["paths"])
    assert "/paper/orders" in paths
    assert not any("live" in path or "wallet" in path for path in paths)


def test_paper_api_and_open_order_lifecycle(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload, asks=[("0.55", "20")])
    from eventtrader.api.main import app

    request = buy(report_id).model_dump(mode="json")
    with TestClient(app) as client:
        app.state.engine = pg_engine
        created = client.post("/paper/orders", json=request)
        assert created.status_code == 200
        order = created.json()["order"]
        assert order["status"] == "OPEN"
        assert client.get(f"/paper/orders/{order['id']}").status_code == 200
        assert len(client.get("/paper/orders").json()) == 1
        portfolio = client.get("/paper/portfolio").json()
        assert portfolio["mode"] == "PAPER"
        assert Decimal(portfolio["reserved_cash_usd"]) == D("2.50")
        cancelled = client.post(f"/paper/orders/{order['id']}/cancel")
        assert cancelled.json()["status"] == "CANCELLED"
        assert client.get("/paper/positions").json() == []


def test_open_order_expiry_releases_reserved_cash(pg_engine, gamma_payload):
    _, report_id, _ = seed_trade(pg_engine, gamma_payload, asks=[("0.55", "20")])
    service = PaperExecutionService(pg_engine, Settings())
    result = service.submit(buy(report_id))
    assert result.portfolio.reserved_cash_usd == D("2.50")
    with Session(pg_engine) as session, session.begin():
        repo = PaperRepository(session)
        repo.expire_orders(now=datetime.now(UTC) + timedelta(hours=2))
    expired = service.order(result.order.id)
    assert expired is not None and expired.status == "EXPIRED"
    assert service.portfolio().reserved_cash_usd == D("0")
