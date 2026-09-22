from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from streamlit.testing.v1 import AppTest

import eventtrader

SCANNER = Path(eventtrader.__file__).parent / "dashboard/pages/1_Market_Scanner.py"


def test_scanner_empty_and_unavailable():
    response = httpx.Response(
        200, json=[], request=httpx.Request("GET", "http://localhost/markets")
    )
    with patch("httpx.get", return_value=response):
        app = AppTest.from_file(str(SCANNER)).run(timeout=10)
        assert not app.exception
        assert "READ-ONLY / PAPER MODE" in app.info[0].value
        assert "No synced markets" in app.info[1].value
    with patch("httpx.get", side_effect=httpx.ConnectError("secret-sentinel")):
        app = AppTest.from_file(str(SCANNER)).run(timeout=10)
        assert not app.exception
        assert "Market data unavailable" in app.error[0].value
        assert "secret-sentinel" not in app.error[0].value


def test_scanner_populated_search_and_outcomes():
    market_id, outcome_id = str(uuid4()), str(uuid4())
    timestamp = datetime.now(UTC).isoformat()
    payload = [
        {
            "id": market_id,
            "provider": "polymarket",
            "external_market_id": "1",
            "slug": "example",
            "question": "Example question?",
            "category": None,
            "condition_id": None,
            "status": "active",
            "resolution_rules": None,
            "resolution_source": None,
            "close_time": None,
            "resolved_at": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "accepting_orders": True,
            "enable_order_book": True,
            "outcomes": [
                {
                    "id": outcome_id,
                    "market_id": market_id,
                    "outcome_name": "Yes",
                    "token_id": "123",
                    "outcome_index": 0,
                    "active": True,
                }
            ],
            "latest_snapshots": [
                {
                    "id": str(uuid4()),
                    "market_id": market_id,
                    "outcome_id": outcome_id,
                    "captured_at": timestamp,
                    "metadata_captured_at": timestamp,
                    "raw_payload_hash": "a" * 64,
                    "best_bid": "0.40",
                    "best_ask": "0.45",
                    "spread": "0.05",
                }
            ],
        }
    ]
    response = httpx.Response(
        200, json=payload, request=httpx.Request("GET", "http://localhost/markets")
    )
    with patch("httpx.get", return_value=response) as get:
        app = AppTest.from_file(str(SCANNER)).run(timeout=10)
        assert not app.exception
        assert app.dataframe[0].value.iloc[0]["Outcome"] == "Yes"
        assert app.dataframe[0].value.iloc[0]["Bid"] == "0.40"
        assert app.subheader[0].value == "Example question?"
        assert get.call_args.kwargs["params"]["q"] == ""
