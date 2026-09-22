"""A deterministic status graph, with no network calls or model clients."""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class StatusState(TypedDict, total=False):
    status: Literal["ok"]
    trading_mode: Literal["PAPER"]
    live_trading_enabled: Literal[False]


def health_status(state: StatusState) -> StatusState:
    return {"status": "ok", "trading_mode": "PAPER", "live_trading_enabled": False}


def build_status_graph() -> CompiledStateGraph[StatusState, None, StatusState, StatusState]:
    builder = StateGraph(StatusState)
    builder.add_node("health_status", health_status)
    builder.add_edge(START, "health_status")
    builder.add_edge("health_status", END)
    return builder.compile()
