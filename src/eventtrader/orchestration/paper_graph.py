"""Explicitly invoked paper execution graph. Research never invokes it automatically."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from eventtrader.domain.paper import PaperExecutionResult, PaperOrderCreate
from eventtrader.paper_execution.service import PaperExecutionService
from eventtrader.paper_execution.tools import (
    create_paper_order,
    record_portfolio_event,
    simulate_paper_fill,
    update_paper_portfolio,
)


class PaperExecutionState(TypedDict, total=False):
    request: PaperOrderCreate
    result: PaperExecutionResult
    stages: list[str]


def build_paper_execution_graph(
    service: PaperExecutionService,
) -> CompiledStateGraph[PaperExecutionState, None, PaperExecutionState, PaperExecutionState]:
    def create(state: PaperExecutionState) -> PaperExecutionState:
        return {
            "result": create_paper_order(service, state["request"]),
            "stages": [*state.get("stages", []), "create_paper_order"],
        }

    def simulate(state: PaperExecutionState) -> PaperExecutionState:
        return {
            "result": simulate_paper_fill(state["result"]),
            "stages": [*state["stages"], "simulate_paper_fill"],
        }

    def update(state: PaperExecutionState) -> PaperExecutionState:
        return {
            "result": update_paper_portfolio(state["result"]),
            "stages": [*state["stages"], "update_paper_portfolio"],
        }

    def record(state: PaperExecutionState) -> PaperExecutionState:
        return {
            "result": record_portfolio_event(state["result"]),
            "stages": [*state["stages"], "record_portfolio_event"],
        }

    builder = StateGraph(PaperExecutionState)
    builder.add_node("create_paper_order", create)
    builder.add_node("simulate_paper_fill", simulate)
    builder.add_node("update_paper_portfolio", update)
    builder.add_node("record_portfolio_event", record)
    builder.add_edge(START, "create_paper_order")
    builder.add_edge("create_paper_order", "simulate_paper_fill")
    builder.add_edge("simulate_paper_fill", "update_paper_portfolio")
    builder.add_edge("update_paper_portfolio", "record_portfolio_event")
    builder.add_edge("record_portfolio_event", END)
    return builder.compile()
