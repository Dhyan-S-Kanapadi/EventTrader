"""Deterministic economics and risk authority. This module cannot execute orders."""

from decimal import Decimal

from eventtrader.domain.research import (
    DeterministicEvaluation,
    ResearchProposal,
    RiskState,
    TradeProposalInput,
)
from eventtrader.settings import Settings


def trading_cost(
    *,
    position: Decimal,
    ask: Decimal,
    spread: Decimal | None,
    fees_enabled: bool | None,
    fee_rate: Decimal | None,
    slippage_bps: Decimal,
) -> Decimal | None:
    if ask <= 0 or spread is None:
        return None
    if fees_enabled is not False and fee_rate is None:
        return None
    spread_cost = (position / ask) * spread
    fee_cost = position * (fee_rate or Decimal("0"))
    slippage_cost = position * slippage_bps / Decimal("10000")
    return spread_cost + fee_cost + slippage_cost


def evaluate_proposal(
    *,
    proposal: TradeProposalInput,
    ask: Decimal,
    spread: Decimal | None,
    fees_enabled: bool | None,
    fee_rate: Decimal | None,
    research_cost: Decimal,
    risk_state: RiskState,
    settings: Settings,
) -> tuple[ResearchProposal, DeterministicEvaluation]:
    position = proposal.proposed_position_usd
    gross = (position / ask) * (proposal.estimated_probability - ask) if ask > 0 else Decimal("-1")
    costs = trading_cost(
        position=position,
        ask=ask,
        spread=spread,
        fees_enabled=fees_enabled,
        fee_rate=fee_rate,
        slippage_bps=settings.research_slippage_bps,
    )
    trading = costs if costs is not None else position
    net = gross - trading - research_cost
    research_proposal = ResearchProposal(
        proposal=proposal,
        gross_expected_profit_usd=gross,
        estimated_trading_cost_usd=trading,
        total_research_cost_usd=research_cost,
        net_expected_profit_usd=net,
    )
    reasons: list[str] = []
    if proposal.recommendation != "BUY":
        reasons.append("MODEL_ABSTAIN")
    if proposal.maximum_entry_price < ask:
        reasons.append("ENTRY_PRICE_EXCEEDED")
    if costs is None:
        reasons.append("UNKNOWN_TRADING_COST")
    if proposal.estimated_probability <= ask or net <= 0:
        reasons.append("NON_POSITIVE_COST_ADJUSTED_EV")
    if position <= 0 or position > settings.max_single_position_usd:
        reasons.append("SINGLE_POSITION_LIMIT")
    if risk_state.total_exposure_usd + position > settings.max_total_exposure_usd:
        reasons.append("TOTAL_EXPOSURE_LIMIT")
    if risk_state.cash_usd - position < settings.min_cash_reserve_usd:
        reasons.append("CASH_RESERVE_LIMIT")
    if risk_state.daily_loss_usd >= settings.max_daily_loss_usd:
        reasons.append("DAILY_LOSS_LIMIT")
    if risk_state.weekly_loss_usd >= settings.max_weekly_loss_usd:
        reasons.append("WEEKLY_LOSS_LIMIT")
    if risk_state.drawdown_percent >= settings.max_drawdown_percent:
        reasons.append("DRAWDOWN_LIMIT")
    if risk_state.simultaneous_markets >= settings.max_simultaneous_markets:
        reasons.append("SIMULTANEOUS_MARKET_LIMIT")
    if risk_state.trades_today >= settings.max_trades_per_day:
        reasons.append("DAILY_TRADE_LIMIT")
    evaluation = DeterministicEvaluation(
        status="REJECTED" if reasons else "APPROVED_FOR_PAPER",
        reasons=reasons,
        gross_expected_profit_usd=gross,
        estimated_trading_cost_usd=trading,
        total_research_cost_usd=research_cost,
        net_expected_profit_usd=net,
    )
    return research_proposal, evaluation
