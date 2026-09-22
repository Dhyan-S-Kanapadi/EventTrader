from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from eventtrader.api.main import app


def test_market_database_error_is_safe_503():
    error = OperationalError("secret-sentinel", {}, Exception("secret-sentinel"))
    with patch("eventtrader.api.markets.MarketRepository.list_markets", side_effect=error):
        with TestClient(app) as client:
            response = client.get("/markets")
    assert response.status_code == 503
    assert "secret-sentinel" not in response.text


def test_health_is_independent_of_database():
    with patch("eventtrader.api.main.check_database") as check, TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "EventTrader",
        "trading_mode": "PAPER",
        "live_trading_enabled": False,
    }
    check.assert_not_called()


def test_ready_when_database_and_graph_are_healthy():
    with patch("eventtrader.api.main.check_database", return_value=True):
        with TestClient(app) as client:
            response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "graph": "ok"}


def test_ready_returns_503_when_database_is_unavailable():
    with patch("eventtrader.api.main.check_database", return_value=False):
        with TestClient(app) as client:
            response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable", "graph": "ok"}


def test_ready_requires_graph_status():
    with patch("eventtrader.api.main.check_database", return_value=True):
        with TestClient(app) as client:
            app.state.graph_ready = False
            response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["graph"] == "unavailable"


def test_shutdown_disposes_engine():
    with patch("eventtrader.api.main.create_database_engine") as create:
        with TestClient(app):
            pass
    create.return_value.dispose.assert_called_once()
