"""Validated research, evidence, model-usage, and deterministic proposal schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field

from eventtrader.domain.markets import Amount, Price


class ResearchModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)


class EvidenceDocument(ResearchModel):
    id: UUID
    market_id: UUID
    source_url: str
    publisher: str | None = None
    title: str | None = None
    published_at: AwareDatetime | None = None
    retrieved_at: AwareDatetime
    content_hash: str
    extracted_text: str
    source_type: Literal["webpage", "rss", "manual_context"]
    trust_level: Literal["low", "standard", "high"]
    created_at: AwareDatetime


class EvidenceCreate(ResearchModel):
    source_url: AnyUrl
    publisher: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=500)
    published_at: AwareDatetime | None = None
    extracted_text: str | None = Field(default=None, min_length=1, max_length=200_000)
    source_type: Literal["webpage", "rss", "manual_context"] = "webpage"
    trust_level: Literal["low", "standard", "high"] = "standard"


class EvidenceCollectionResult(ResearchModel):
    documents: list[EvidenceDocument]
    rejected_sources: list[str] = Field(default_factory=list)


class ExtractionResult(ResearchModel):
    key_facts: list[str]
    evidence_ids: list[UUID]
    conflicting_evidence: bool = False


class ResearchAnalysis(ResearchModel):
    chosen_outcome_token_id: str
    estimated_probability: Price
    confidence: Price
    maximum_entry_price: Price
    recommendation: Literal["BUY", "ABSTAIN"]
    counterarguments: list[str]
    resolution_interpretation: str
    evidence_ids: list[UUID]
    analysis_expires_at: AwareDatetime


class CritiqueResult(ResearchModel):
    refutes_proposal: bool
    concerns: list[str]
    evidence_ids: list[UUID]
    confidence: Price


class TradeProposalInput(ResearchModel):
    market_id: UUID
    chosen_outcome_token_id: str
    side: Literal["BUY"] = "BUY"
    estimated_probability: Price
    confidence: Price
    maximum_entry_price: Price
    proposed_position_usd: Amount
    evidence_ids: list[UUID]
    key_facts: list[str]
    counterarguments: list[str]
    resolution_interpretation: str
    expires_at: AwareDatetime
    recommendation: Literal["BUY", "ABSTAIN"]


class ResearchProposal(ResearchModel):
    proposal: TradeProposalInput
    gross_expected_profit_usd: Decimal
    estimated_trading_cost_usd: Decimal
    total_research_cost_usd: Decimal
    net_expected_profit_usd: Decimal


class RiskState(ResearchModel):
    cash_usd: Amount
    total_exposure_usd: Amount = Decimal("0")
    daily_loss_usd: Amount = Decimal("0")
    weekly_loss_usd: Amount = Decimal("0")
    drawdown_percent: Amount = Decimal("0")
    simultaneous_markets: int = Field(default=0, ge=0)
    trades_today: int = Field(default=0, ge=0)


class DeterministicEvaluation(ResearchModel):
    status: Literal["APPROVED_FOR_PAPER", "REJECTED"]
    reasons: list[str]
    gross_expected_profit_usd: Decimal
    estimated_trading_cost_usd: Decimal
    total_research_cost_usd: Decimal
    net_expected_profit_usd: Decimal


class LLMUsageRead(ResearchModel):
    id: UUID
    graph_run_id: UUID
    research_report_id: UUID | None
    model_role: str
    provider: str
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost_usd: Decimal
    success: bool
    error_code: str | None
    created_at: datetime


class ResearchReportRead(ResearchModel):
    id: UUID
    market_id: UUID
    graph_run_id: UUID
    model_role: str
    model_name: str
    prompt_version: str
    estimated_probability: Decimal | None
    confidence: Decimal | None
    maximum_entry_price: Decimal | None
    recommendation: str
    counterarguments: list[str]
    resolution_interpretation: str | None
    analysis_expires_at: datetime | None
    total_research_cost_usd: Decimal
    status: str
    reason_codes: list[str]
    graph_stages: list[dict[str, object]]
    result_payload: dict[str, object] | None
    created_at: datetime


class ResearchRunResult(ResearchModel):
    graph_run_id: UUID
    market_id: UUID
    status: Literal["APPROVED_FOR_PAPER", "REJECTED", "RESEARCH_UNAVAILABLE"]
    reason_codes: list[str]
    stages: list[dict[str, object]]
    proposal: ResearchProposal | None = None
    usage: list[LLMUsageRead] = Field(default_factory=list)
