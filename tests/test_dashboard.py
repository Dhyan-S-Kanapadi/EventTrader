from pathlib import Path

from streamlit.testing.v1 import AppTest

import eventtrader


def test_dashboard_shows_paper_only_foundation():
    path = Path(eventtrader.__file__).parent / "dashboard" / "app.py"
    app = AppTest.from_file(str(path)).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "EventTrader"
    assert app.info[0].value == "PAPER TRADING mode"
    assert app.metric[0].label == "Initial capital"
    assert app.metric[0].value == "$50.00"
    assert any(item.value == "Live trading: disabled" for item in app.markdown)


def test_paper_trading_page_is_clearly_simulated(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        return Response([])

    monkeypatch.setattr("httpx.get", fake_get)
    path = Path(eventtrader.__file__).parent / "dashboard" / "pages" / "3_Paper_Trading.py"
    page = AppTest.from_file(str(path)).run(timeout=20)
    assert not page.exception
    assert page.title[0].value == "Paper Trading"
    assert "NO REAL MONEY" in page.error[0].value


def test_portfolio_page_shows_cost_and_risk_metrics(monkeypatch):
    class Response:
        def json(self):
            return {
                "starting_capital_usd": "50",
                "available_cash_usd": "50",
                "reserved_cash_usd": "0",
                "open_exposure_usd": "0",
                "realized_pnl_usd": "0",
                "unrealized_pnl_usd": "0",
                "total_net_pnl_usd": "0",
                "total_fees_usd": "0",
                "total_spread_cost_usd": "0",
                "total_slippage_usd": "0",
                "total_research_cost_usd": "0",
                "positions": [],
                "events": [],
            }

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Response())
    path = Path(eventtrader.__file__).parent / "dashboard" / "pages" / "4_Portfolio.py"
    page = AppTest.from_file(str(path)).run(timeout=20)
    assert not page.exception
    assert page.title[0].value == "Paper Portfolio"
    assert any(metric.label == "Open exposure" for metric in page.metric)
    assert any(metric.label == "Total net P&L after recorded costs" for metric in page.metric)
