"""Read-only evidence and research APIs. Research produces proposals, never orders."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.orm import Session

from eventtrader.domain.research import (
    EvidenceCreate,
    EvidenceDocument,
    LLMUsageRead,
    ResearchReportRead,
    ResearchRunResult,
)
from eventtrader.orchestration.research_graph import ResearchWorkflow
from eventtrader.persistence.repository import MarketRepository
from eventtrader.persistence.research_repository import ResearchRepository
from eventtrader.research.evidence import EvidenceError, HttpEvidenceFetcher, content_hash
from eventtrader.settings import Settings

router = APIRouter(tags=["read-only research"])


@router.post("/markets/{market_id}/evidence", response_model=EvidenceDocument)
async def add_evidence(
    market_id: UUID, evidence: EvidenceCreate, request: Request
) -> EvidenceDocument:
    settings: Settings = request.app.state.settings
    with Session(request.app.state.engine) as session:
        if MarketRepository(session).get_market(market_id) is None:
            raise HTTPException(404, "Market not found")
    if evidence.extracted_text is None:
        try:
            evidence = await HttpEvidenceFetcher(
                timeout=settings.provider_timeout_seconds,
                max_bytes=settings.evidence_max_bytes,
            ).fetch(evidence)
        except EvidenceError as exc:
            raise HTTPException(422, str(exc)) from None
    elif evidence.source_type != "manual_context" or evidence.trust_level != "low":
        raise HTTPException(
            422, "Inline evidence is allowed only as explicitly low-trust manual_context"
        )
    text = evidence.extracted_text
    assert text is not None
    with Session(request.app.state.engine) as session, session.begin():
        return ResearchRepository(session).add_evidence(
            market_id=market_id,
            source_url=str(evidence.source_url),
            publisher=evidence.publisher,
            title=evidence.title,
            published_at=evidence.published_at,
            extracted_text=text,
            source_type=evidence.source_type,
            trust_level=evidence.trust_level,
            content_hash=content_hash(text),
        )


@router.get("/markets/{market_id}/evidence", response_model=list[EvidenceDocument])
def list_evidence(market_id: UUID, request: Request) -> list[EvidenceDocument]:
    with Session(request.app.state.engine) as session:
        if MarketRepository(session).get_market(market_id) is None:
            raise HTTPException(404, "Market not found")
        return ResearchRepository(session).evidence(market_id)


@router.post("/markets/{market_id}/research", response_model=ResearchRunResult)
async def run_research(market_id: UUID, request: Request) -> ResearchRunResult:
    workflow = ResearchWorkflow(
        engine=request.app.state.engine,
        settings=request.app.state.settings,
    )
    return await workflow.run(market_id)


@router.get("/research-runs", response_model=list[ResearchReportRead])
def list_research_runs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ResearchReportRead]:
    with Session(request.app.state.engine) as session:
        return ResearchRepository(session).reports(limit=limit, offset=offset)


@router.get("/research-runs/{run_id}", response_model=ResearchReportRead)
def get_research_run(run_id: UUID, request: Request) -> ResearchReportRead:
    with Session(request.app.state.engine) as session:
        report = ResearchRepository(session).report(run_id)
    if report is None:
        raise HTTPException(404, "Research run not found")
    return report


@router.get("/llm-usage", response_model=list[LLMUsageRead])
def list_llm_usage(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LLMUsageRead]:
    with Session(request.app.state.engine) as session:
        return ResearchRepository(session).usage(limit=limit, offset=offset)
