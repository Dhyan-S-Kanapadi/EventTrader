from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from eventtrader.domain.markets import Market
from eventtrader.market_data.provider import PredictionMarketDataProvider, ProviderError
from eventtrader.orchestration.market_tools import discover_polymarket_markets, sync_market_snapshot
from eventtrader.persistence.repository import MarketRepository


class SyncState(TypedDict, total=False):
    limit: int
    markets: list[Market]
    market_ids: list[UUID]
    snapshots: int
    skipped: int
    failures: list[dict[str, str]]


def build_sync_graph(
    provider: PredictionMarketDataProvider,
    engine: Engine,
) -> CompiledStateGraph[SyncState, None, SyncState, SyncState]:
    # Clients, engine, and settings live in closures, never in graph state.
    async def discover_markets(state: SyncState) -> SyncState:
        return {"markets": await discover_polymarket_markets(provider, state["limit"])}

    def persist_markets(state: SyncState) -> SyncState:
        with Session(engine) as session, session.begin():
            repository = MarketRepository(session)
            return {"market_ids": [repository.upsert_market(market) for market in state["markets"]]}

    async def capture_snapshots(state: SyncState) -> SyncState:
        captured, skipped = 0, 0
        failures: list[dict[str, str]] = []
        for market_id, market in zip(state["market_ids"], state["markets"], strict=True):
            for outcome in market.outcomes:
                if (
                    not outcome.active
                    or not outcome.token_id
                    or market.enable_order_book is not True
                    or market.accepting_orders is not True
                ):
                    skipped += 1
                    continue
                try:
                    await sync_market_snapshot(
                        provider, engine, market_id, market, outcome.token_id
                    )
                    captured += 1
                except ProviderError as exc:
                    failures.append(
                        {
                            "market_id": str(market_id),
                            "token_id": outcome.token_id,
                            "code": exc.code,
                            "correlation_id": exc.correlation_id,
                        }
                    )
        return {"snapshots": captured, "skipped": skipped, "failures": failures}

    builder = StateGraph(SyncState)
    builder.add_node("discover_markets", discover_markets)
    builder.add_node("persist_markets", persist_markets)
    builder.add_node("capture_snapshots", capture_snapshots)
    builder.add_edge(START, "discover_markets")
    builder.add_edge("discover_markets", "persist_markets")
    builder.add_edge("persist_markets", "capture_snapshots")
    builder.add_edge("capture_snapshots", END)
    return builder.compile()
