"""Paper-only execution and portfolio APIs."""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from eventtrader.domain.paper import (
    PaperExecutionResult,
    PaperOrderCreate,
    PaperOrderRead,
    PaperPortfolioRead,
    PaperPositionRead,
    ReconciliationResult,
)
from eventtrader.orchestration.paper_graph import build_paper_execution_graph
from eventtrader.paper_execution.reconciliation import ReconciliationService
from eventtrader.paper_execution.service import PaperExecutionError, PaperExecutionService

router = APIRouter(prefix="/paper", tags=["paper trading"])


def _service(request: Request) -> PaperExecutionService:
    return PaperExecutionService(request.app.state.engine, request.app.state.settings)


def _raise(error: PaperExecutionError) -> NoReturn:
    missing = error.code in {"PAPER_ORDER_NOT_FOUND", "APPROVED_PROPOSAL_NOT_FOUND"}
    raise HTTPException(404 if missing else 409, error.code)


@router.post("/orders", response_model=PaperExecutionResult)
def submit_order(order: PaperOrderCreate, request: Request) -> PaperExecutionResult:
    try:
        state = build_paper_execution_graph(_service(request)).invoke(
            {"request": order, "stages": []}
        )
        return PaperExecutionResult.model_validate(state["result"])
    except PaperExecutionError as exc:
        _raise(exc)


@router.get("/orders", response_model=list[PaperOrderRead])
def list_orders(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PaperOrderRead]:
    return _service(request).orders(limit=limit, offset=offset)


@router.get("/orders/{order_id}", response_model=PaperOrderRead)
def get_order(order_id: UUID, request: Request) -> PaperOrderRead:
    order = _service(request).order(order_id)
    if order is None:
        raise HTTPException(404, "PAPER_ORDER_NOT_FOUND")
    return order


@router.post("/orders/{order_id}/cancel", response_model=PaperOrderRead)
def cancel_order(order_id: UUID, request: Request) -> PaperOrderRead:
    try:
        return _service(request).cancel(order_id)
    except PaperExecutionError as exc:
        _raise(exc)


@router.get("/positions", response_model=list[PaperPositionRead])
def list_positions(request: Request) -> list[PaperPositionRead]:
    return _service(request).portfolio().positions


@router.get("/portfolio", response_model=PaperPortfolioRead)
def get_portfolio(request: Request) -> PaperPortfolioRead:
    return _service(request).portfolio()


@router.post("/portfolio/mark", response_model=PaperPortfolioRead)
def mark_portfolio(request: Request) -> PaperPortfolioRead:
    return _service(request).mark_to_market()


@router.post(
    "/portfolio/reconcile-resolutions",
    response_model=ReconciliationResult,
)
async def reconcile_portfolio(request: Request) -> ReconciliationResult:
    return await ReconciliationService(
        request.app.state.engine, request.app.state.settings
    ).reconcile()
