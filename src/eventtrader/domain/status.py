from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    service: Literal["EventTrader"] = "EventTrader"
    trading_mode: Literal["PAPER"] = "PAPER"
    live_trading_enabled: Literal[False] = False


class ReadinessStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    graph: Literal["ok", "unavailable"]
