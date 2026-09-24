"""Deterministic paper-only LangGraph tools. No provider trading API is imported."""

from uuid import UUID

from eventtrader.domain.paper import (
    PaperExecutionResult,
    PaperOrderCreate,
    PaperOrderRead,
    PaperPortfolioRead,
    ReconciliationResult,
)
from eventtrader.paper_execution.reconciliation import (
    ReconciliationService,
    ResolutionProvider,
)
from eventtrader.paper_execution.service import PaperExecutionService


def create_paper_order(
    service: PaperExecutionService, request: PaperOrderCreate
) -> PaperExecutionResult:
    # The service deliberately creates, fills, and accounts in one DB transaction.
    return service.submit(request)


def simulate_paper_fill(result: PaperExecutionResult) -> PaperExecutionResult:
    return result


def update_paper_portfolio(result: PaperExecutionResult) -> PaperExecutionResult:
    return result


def record_portfolio_event(result: PaperExecutionResult) -> PaperExecutionResult:
    return result


def mark_positions_to_market(
    service: PaperExecutionService,
) -> PaperPortfolioRead:
    return service.mark_to_market()


async def reconcile_resolved_positions(
    service: ReconciliationService,
    provider: ResolutionProvider | None = None,
) -> ReconciliationResult:
    return await service.reconcile(provider=provider)


def cancel_paper_order(service: PaperExecutionService, order_id: UUID) -> PaperOrderRead:
    return service.cancel(order_id)
