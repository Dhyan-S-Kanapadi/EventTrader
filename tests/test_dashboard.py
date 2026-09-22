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
