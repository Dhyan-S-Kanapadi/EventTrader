import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from eventtrader.api.markets import router as markets_router
from eventtrader.api.paper import router as paper_router
from eventtrader.api.research import router as research_router
from eventtrader.domain.status import HealthStatus, ReadinessStatus
from eventtrader.logging import configure_logging
from eventtrader.orchestration.graph import build_status_graph
from eventtrader.persistence.database import check_database, create_database_engine
from eventtrader.settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    configure_logging(settings.log_level)
    app.state.graph_ready = build_status_graph().invoke({})["status"] == "ok"
    app.state.settings = settings
    app.state.engine = create_database_engine(settings)
    logger.info("application_started")
    try:
        yield
    finally:
        app.state.engine.dispose()
        logger.info("application_stopped")


app = FastAPI(title="EventTrader", version="0.1.0", lifespan=lifespan)
app.include_router(markets_router)
app.include_router(paper_router)
app.include_router(research_router)


@app.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    return HealthStatus()


@app.get("/ready", response_model=ReadinessStatus, responses={503: {"model": ReadinessStatus}})
def ready(request: Request, response: Response) -> ReadinessStatus:
    database_ok = check_database(request.app.state.engine)
    graph_ok = request.app.state.graph_ready
    is_ready = database_ok and graph_ok
    response.status_code = 200 if is_ready else 503
    return ReadinessStatus(
        status="ready" if is_ready else "not_ready",
        database="ok" if database_ok else "unavailable",
        graph="ok" if graph_ok else "unavailable",
    )
