import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eventtrader.api.main import app
from eventtrader.domain.markets import SnapshotValues
from eventtrader.market_data.polymarket import PolymarketReadOnlyClient, normalize_market
from eventtrader.orchestration.sync_graph import build_sync_graph
from eventtrader.persistence.models import MarketRow, OutcomeRow, SnapshotRow
from eventtrader.persistence.repository import MarketRepository
from eventtrader.settings import Settings


def test_upsert_preserves_ids_and_uniqueness(pg_engine, gamma_payload):
    market = normalize_market(gamma_payload, "test")
    with Session(pg_engine) as session, session.begin():
        repo = MarketRepository(session)
        first = repo.upsert_market(market)
        second = repo.upsert_market(market.model_copy(update={"question": "Updated question"}))
        assert first == second
        assert session.scalar(select(func.count()).select_from(MarketRow)) == 1
        assert session.scalar(select(func.count()).select_from(OutcomeRow)) == 2
        assert repo.get_market(first).question == "Updated question"
        assert repo.get_market(first).created_at.tzinfo is not None
    with pytest.raises(IntegrityError), Session(pg_engine) as session, session.begin():
        session.add(
            MarketRow(
                provider="polymarket",
                external_market_id=market.external_market_id,
                question="duplicate",
                status="active",
            )
        )
        session.flush()


def test_token_changes_rollback_metadata(pg_engine, gamma_payload):
    market = normalize_market(gamma_payload, "test")
    with Session(pg_engine) as session, session.begin():
        market_id = MarketRepository(session).upsert_market(market)
    changed = market.model_copy(
        update={
            "question": "bad update",
            "outcomes": [market.outcomes[0].model_copy(update={"token_id": "123"})],
        }
    )
    with pytest.raises(ValueError), Session(pg_engine) as session, session.begin():
        MarketRepository(session).upsert_market(changed)
    with Session(pg_engine) as session:
        assert MarketRepository(session).get_market(market_id).question == market.question


def test_snapshot_precision_and_history(pg_engine, gamma_payload):
    market = normalize_market(gamma_payload, "test")
    value = SnapshotValues(
        captured_at=datetime.now(UTC),
        metadata_captured_at=datetime.now(UTC),
        best_bid=Decimal("0.123456789"),
        raw_payload_hash="a" * 64,
    )
    with Session(pg_engine) as session, session.begin():
        repo = MarketRepository(session)
        market_id = repo.upsert_market(market)
        repo.add_snapshot(market_id, market.outcomes[0].token_id, value)
        repo.add_snapshot(market_id, market.outcomes[0].token_id, value)
        assert len(repo.snapshots(market_id)) == 2
        assert repo.snapshots(market_id)[0].best_bid == Decimal("0.123456789")
        assert len(repo.get_market(market_id).latest_snapshots) == 1
        assert repo.snapshots(market_id)[0].captured_at.tzinfo is not None


@pytest.mark.parametrize("partial", [False, True])
def test_sync_graph_and_read_only_api(pg_engine, gamma_payload, book_payload, partial):
    def handler(request):
        assert request.method == "GET"
        if request.url.path == "/markets/keyset":
            return httpx.Response(200, json={"markets": [gamma_payload]})
        token = request.url.params["token_id"]
        if partial and token != book_payload["asset_id"]:
            return httpx.Response(404)
        return httpx.Response(200, json={**book_payload, "asset_id": token})

    async def run():
        async with PolymarketReadOnlyClient(
            Settings(), transport=httpx.MockTransport(handler)
        ) as provider:
            graph = build_sync_graph(provider, pg_engine)
            return await graph.ainvoke({"limit": 1})

    result = asyncio.run(run())
    assert result["snapshots"] == (1 if partial else 2)
    assert len(result["failures"]) == (1 if partial else 0)
    with TestClient(app) as client:
        app.state.engine = pg_engine
        response = client.get("/markets", params={"q": "aliens"})
        assert response.status_code == 200
        assert len(response.json()) == 1
        market_id = response.json()[0]["id"]
        assert len(client.get(f"/markets/{market_id}").json()["outcomes"]) == 2
        assert len(client.get(f"/markets/{market_id}/snapshots").json()) == result["snapshots"]
        assert client.get(f"/markets/{uuid4()}").status_code == 404
        assert client.get("/markets/not-a-uuid").status_code == 422
        assert client.get("/markets?limit=101").status_code == 422
        assert client.post("/markets").status_code == 405
        assert client.get("/markets?q=%25").json() == []
    with Session(pg_engine) as session:
        snapshots = list(session.scalars(select(SnapshotRow)))
        assert snapshots[0].spread == Decimal("0.94")
        assert snapshots[0].fee_rate == Decimal("0.04")
        assert snapshots[0].open_interest is None


def test_migration_roundtrip(pg_engine):
    from pathlib import Path

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pg_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    with Session(pg_engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketRow)) == 0
