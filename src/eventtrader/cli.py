"""Manual, bounded ingestion. No scheduler, credentials, or execution adapter."""

import argparse
import asyncio
import json

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from eventtrader.logging import configure_logging
from eventtrader.market_data.polymarket import PolymarketReadOnlyClient
from eventtrader.market_data.provider import ProviderError
from eventtrader.orchestration.sync_graph import build_sync_graph
from eventtrader.persistence.database import create_database_engine
from eventtrader.settings import Settings


async def sync(limit: int) -> int:
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    try:
        async with PolymarketReadOnlyClient(settings) as provider:
            result = await build_sync_graph(provider, engine).ainvoke({"limit": limit})
        print(
            json.dumps(
                {
                    "mode": "READ-ONLY / PAPER",
                    "markets": len(result["market_ids"]),
                    "snapshots": result["snapshots"],
                    "skipped": result["skipped"],
                    "failures": result["failures"],
                }
            )
        )
        return 2 if result["failures"] else 0
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="EventTrader read-only market ingestion")
    parser.add_argument("command", choices=["sync"])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    try:
        code = asyncio.run(sync(args.limit))
    except ProviderError as exc:
        print(json.dumps({"error": exc.code, "correlation_id": exc.correlation_id}))
        code = 1
    except (SQLAlchemyError, ValidationError, ValueError):
        print(
            json.dumps(
                {
                    "error": "database_or_configuration_error",
                    "hint": "Check settings and run alembic upgrade head",
                }
            )
        )
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
