import logging
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from eventtrader.domain.markets import MarketRead, SnapshotRead
from eventtrader.persistence.repository import MarketRepository

router = APIRouter(prefix="/markets", tags=["read-only markets"])
logger = logging.getLogger(__name__)


def repository(request: Request) -> Iterator[MarketRepository]:
    try:
        with Session(request.app.state.engine) as session:
            yield MarketRepository(session)
    except SQLAlchemyError:
        logger.warning("market_database_unavailable")
        raise HTTPException(
            503, "Market database unavailable; check migrations and connectivity"
        ) from None


Repository = Annotated[MarketRepository, Depends(repository)]


@router.get("", response_model=list[MarketRead])
def list_markets(
    repo: Repository,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MarketRead]:
    return repo.list_markets(query=q, limit=limit, offset=offset)


@router.get("/{market_id}", response_model=MarketRead)
def get_market(market_id: UUID, repo: Repository) -> MarketRead:
    market = repo.get_market(market_id)
    if market is None:
        raise HTTPException(404, "Market not found")
    return market


@router.get("/{market_id}/snapshots", response_model=list[SnapshotRead])
def get_snapshots(
    market_id: UUID,
    repo: Repository,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SnapshotRead]:
    if repo.get_market(market_id) is None:
        raise HTTPException(404, "Market not found")
    return repo.snapshots(market_id, limit=limit, offset=offset)
