from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from eventtrader.settings import Settings


def test_supplied_env_example_loads_with_paper_defaults(tmp_path):
    example = Path(__file__).resolve().parents[1] / ".env.example"
    (tmp_path / ".env").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    settings = Settings()
    assert settings.trading_mode == "PAPER"
    assert settings.live_trading_enabled is False
    assert settings.starting_capital_usd == Decimal("50")


def test_safe_defaults_and_risk_limits():
    settings = Settings()
    assert settings.trading_mode == "PAPER"
    assert settings.live_trading_enabled is False
    expected = {
        "starting_capital_usd": "50",
        "max_single_position_usd": "2.50",
        "max_total_exposure_usd": "30",
        "min_cash_reserve_usd": "20",
        "max_daily_loss_usd": "3",
        "max_weekly_loss_usd": "7.50",
        "max_drawdown_percent": "20",
    }
    for field, value in expected.items():
        assert getattr(settings, field) == Decimal(value)
    assert settings.max_simultaneous_markets == 3
    assert settings.max_trades_per_day == 5
    assert settings.research_slippage_bps == Decimal("50")


@pytest.mark.parametrize(
    "name,value",
    [
        ("TRADING_MODE", "LIVE"),
        ("LIVE_TRADING_ENABLED", "true"),
        ("STARTING_CAPITAL_USD", "-1"),
        ("STARTING_CAPITAL_USD", "NaN"),
        ("MAX_SINGLE_POSITION_USD", "31"),
        ("MAX_TOTAL_EXPOSURE_USD", "31"),
        ("MAX_DAILY_LOSS_USD", "8"),
        ("MAX_DRAWDOWN_PERCENT", "101"),
        ("MAX_TRADES_PER_DAY", "0"),
    ],
)
def test_unsafe_configuration_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_dotenv_loading_and_environment_precedence(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("STARTING_CAPITAL_USD=75\n", encoding="utf-8")
    assert Settings().starting_capital_usd == Decimal("75")
    monkeypatch.setenv("STARTING_CAPITAL_USD", "100")
    assert Settings().starting_capital_usd == Decimal("100")


def test_password_excluded_from_repr_and_serialization(monkeypatch):
    password = "sentinel-test-password"
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    settings = Settings()
    assert settings.postgres_password.get_secret_value() == password
    assert password not in repr(settings)
    assert "postgres_password" not in settings.model_dump()
    assert password not in settings.model_dump_json()
