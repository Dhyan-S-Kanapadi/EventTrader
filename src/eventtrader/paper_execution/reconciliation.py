"""Read-only Polymarket resolution reconciliation for paper positions."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eventtrader.domain.paper import ReconciliationResult, SettlementInstruction
from eventtrader.market_data.polymarket import PolymarketReadOnlyClient
from eventtrader.persistence.models import PaperPositionRow
from eventtrader.persistence.paper_repository import PaperRepository
from eventtrader.settings import Settings


class ResolutionProvider(Protocol):
    async def get_resolution(
        self, condition_id: str, outcome_count: int
    ) -> SettlementInstruction | None: ...


class ReconciliationService:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings

    async def reconcile(
        self,
        *,
        provider: ResolutionProvider | None = None,
        manual: Sequence[SettlementInstruction] = (),
    ) -> ReconciliationResult:
        with Session(self.engine) as session:
            repo = PaperRepository(session)
            positions = list(
                session.scalars(select(PaperPositionRow).where(PaperPositionRow.status == "OPEN"))
            )
            candidates: list[tuple[UUID, str | None, int | None, int]] = []
            for position_row in positions:
                market_row = repo.market(position_row.market_id)
                outcome_identity = repo.outcome_index(
                    position_row.market_id, position_row.outcome_token_id
                )
                candidates.append(
                    (
                        position_row.id,
                        market_row.condition_id if market_row else None,
                        outcome_identity[0] if outcome_identity else None,
                        outcome_identity[1] if outcome_identity else 0,
                    )
                )

        instructions = {item.condition_id: item for item in manual}
        missing = {
            condition_id: outcome_count
            for _, condition_id, _, outcome_count in candidates
            if condition_id and condition_id not in instructions
        }
        if provider is not None:
            for condition_id, outcome_count in missing.items():
                result = await provider.get_resolution(condition_id, outcome_count)
                if result is not None:
                    instructions[condition_id] = result
        elif missing:
            async with PolymarketReadOnlyClient(self.settings) as public_provider:
                for condition_id, outcome_count in missing.items():
                    result = await public_provider.get_resolution(condition_id, outcome_count)
                    if result is not None:
                        instructions[condition_id] = result

        settled: list[UUID] = []
        warnings: list[str] = []
        with Session(self.engine) as session, session.begin():
            repo = PaperRepository(session)
            repo.initialize_capital(self.settings.starting_capital_usd)
            for position_id, candidate_condition_id, candidate_outcome_index, _ in candidates:
                locked_position = session.get(PaperPositionRow, position_id, with_for_update=True)
                if locked_position is None or locked_position.status != "OPEN":
                    continue
                instruction = instructions.get(candidate_condition_id or "")
                if instruction is None or candidate_outcome_index is None:
                    warning = f"{locked_position.market_id}:RESOLUTION_UNAVAILABLE"
                    warnings.append(warning)
                    if not repo.event_exists(
                        "RECONCILIATION_WARNING", "paper_position", locked_position.id
                    ):
                        repo.record_event(
                            event_type="RECONCILIATION_WARNING",
                            reference_type="paper_position",
                            reference_id=locked_position.id,
                            amount_usd=Decimal("0"),
                            metadata={"mode": "PAPER", "warning": warning},
                        )
                    continue
                payout_per_share = instruction.payouts[candidate_outcome_index]
                held_shares = locked_position.quantity_shares
                payout = held_shares * payout_per_share
                realized_delta = payout - locked_position.cost_basis_usd
                locked_position.realized_pnl_usd += realized_delta
                locked_position.unrealized_pnl_usd = Decimal("0")
                locked_position.current_mark_price = payout_per_share
                locked_position.quantity_shares = Decimal("0")
                locked_position.status = "SETTLED"
                locked_position.closed_at = instruction.resolved_at
                if not repo.event_exists("PAPER_SETTLEMENT", "paper_position", locked_position.id):
                    repo.record_event(
                        event_type="PAPER_SETTLEMENT",
                        reference_type="paper_position",
                        reference_id=locked_position.id,
                        amount_usd=payout,
                        metadata={
                            "mode": "PAPER",
                            "condition_id": instruction.condition_id,
                            "payout_per_share": str(payout_per_share),
                            "shares": str(held_shares),
                            "source": instruction.source,
                            "realized_pnl_delta_usd": str(realized_delta),
                        },
                    )
                settled.append(locked_position.id)
        return ReconciliationResult(
            settled_position_ids=settled,
            warnings=warnings,
        )
