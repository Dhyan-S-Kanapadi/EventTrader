"""Validated configuration. Credentials stay outside graph and domain state."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    trading_mode: Literal["PAPER"] = "PAPER"
    live_trading_enabled: Literal[False] = False
    starting_capital_usd: Decimal = Field(default=Decimal("50"), gt=0)
    max_single_position_usd: Decimal = Field(default=Decimal("2.50"), gt=0)
    max_total_exposure_usd: Decimal = Field(default=Decimal("30"), gt=0)
    min_cash_reserve_usd: Decimal = Field(default=Decimal("20"), ge=0)
    max_daily_loss_usd: Decimal = Field(default=Decimal("3"), gt=0)
    max_weekly_loss_usd: Decimal = Field(default=Decimal("7.50"), gt=0)
    max_drawdown_percent: Decimal = Field(default=Decimal("20"), gt=0, le=100)
    max_simultaneous_markets: int = Field(default=3, gt=0)
    max_trades_per_day: int = Field(default=5, gt=0)

    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_user: str = "eventtrader"
    postgres_db: str = "eventtrader"
    postgres_password: SecretStr = Field(default=SecretStr(""), repr=False, exclude=True)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    provider_timeout_seconds: float = Field(default=10, gt=0, le=60)
    provider_max_retries: int = Field(default=2, ge=0, le=5)
    provider_backoff_seconds: float = Field(default=0.5, ge=0, le=10)
    provider_max_backoff_seconds: float = Field(default=10, gt=0, le=60)
    provider_page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("live_trading_enabled", mode="before")
    @classmethod
    def parse_disabled_flag(cls, value: object) -> object:
        # Environment variables are strings; preserve Literal[False]'s rejection of true.
        return False if isinstance(value, str) and value.lower() == "false" else value

    @model_validator(mode="after")
    def validate_risk_configuration(self) -> "Settings":
        if self.max_single_position_usd > self.max_total_exposure_usd:
            raise ValueError("Single-position limit must not exceed total exposure limit")
        if self.max_total_exposure_usd + self.min_cash_reserve_usd > self.starting_capital_usd:
            raise ValueError("Exposure limit plus cash reserve must not exceed initial capital")
        if self.max_daily_loss_usd > self.max_weekly_loss_usd:
            raise ValueError("Daily loss limit must not exceed weekly loss limit")
        return self
