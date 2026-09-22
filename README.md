# EventTrader

Controlled Polymarket research in **paper mode only**. Milestone 2 adds PostgreSQL
market, outcome, and snapshot persistence; public GET-only ingestion; a bounded
manual LangGraph sync; read-only APIs; and a Streamlit Market Scanner. No LLMs,
scheduler, wallets, private keys, order calls, or paper execution exist.

## Docker startup and manual sync

Requires Docker with its engine running and Docker Compose v2. In PowerShell, from
the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
# On first setup, replace POSTGRES_PASSWORD with a local development password.
docker compose up -d postgres
docker compose build api dashboard
docker compose run --rm api python -m alembic upgrade head
docker compose up -d api dashboard
docker compose run --rm api python -m eventtrader.cli sync --limit 10
```

Dashboard: http://localhost:8501 — select **Market Scanner** in the sidebar.
API docs: http://localhost:8000/docs

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod 'http://localhost:8000/markets?limit=10'
# Use a local UUID returned above:
Invoke-RestMethod 'http://localhost:8000/markets/<market_uuid>'
Invoke-RestMethod 'http://localhost:8000/markets/<market_uuid>/snapshots?limit=20'
docker compose logs -f api dashboard
docker compose down
```

PostgreSQL data persists in a named volume. Set the password before the first start;
editing `.env` does not change an existing database user's password. Published ports
bind to localhost. Migrations are explicit and are not run during API startup.
`/health` checks liveness. `/ready` checks database connectivity and the foundation
status graph, not schema version, provider availability, or trading readiness.

## Local Python startup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Keep `POSTGRES_HOST=localhost` in `.env`.
If port 5432 is unavailable, set both `POSTGRES_PORT` and `POSTGRES_HOST_PORT`
to the same available local port. Containers still use PostgreSQL's internal 5432.

```powershell
uv sync --frozen
docker compose up -d postgres
uv run --frozen python -m alembic upgrade head
uv run --frozen python -m eventtrader.cli sync --limit 10
uv run --frozen python -m uvicorn eventtrader.api.main:app --reload --no-access-log
```

In a second terminal:

```powershell
uv run --frozen python -m streamlit run src/eventtrader/dashboard/app.py --browser.gatherUsageStats=false
```

This workspace also has uv at `.tools/bin/uv.exe`; use that path if uv is not on
`PATH`. Dependencies are locked in `uv.lock`.

## Tests and checks

```powershell
uv run --frozen python -m pytest
# Requires local PostgreSQL and .env; creates and drops random test schemas only:
uv run --frozen python -m pytest --postgres
# If the local PostgreSQL host port differs from .env:
uv run --frozen python -m pytest --postgres --postgres-port 15432
uv run --frozen python -m alembic check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
```

Default tests have no provider or network dependency; PostgreSQL tests are opt-in.
HTTP fixtures are documented examples rather than successful live recordings because
direct provider access timed out during implementation. A sync failure exits nonzero
with a safe error code and must not be interpreted as an empty market list.

`--limit` bounds discovery to 1-1000 markets. Synced markets are upserted and each
outcome gets its own append-only snapshot. The scanner searches stored questions and
pages through 50 markets at a time. It never triggers provider calls. Missing values
remain unknown; timestamps and outcome labels stay visible. HTTP pagination supports
`limit` and `offset`, with optional `q` on `/markets`.

Settings load from `.env` with environment overrides. LIVE mode is rejected.
Database passwords are excluded from settings serialization; the dashboard container
receives only public configuration. Never log settings, raw exceptions, response
bodies, or secrets. Do not enable external graph tracing. Public ingestion requires
no provider authentication.

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) for architecture and milestone scope,
and [the Polymarket data contract](docs/POLYMARKET_DATA.md) for official sources,
field mappings, fee semantics, snapshot limitations, and failure behavior.
