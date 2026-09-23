# EventTrader

EventTrader is a controlled Polymarket research system in **paper mode only**.
It persists public market data and evidence, runs a bounded LangGraph research
workflow, meters every model attempt, and sends structured proposals through
deterministic cost and risk checks. It cannot create an order: there is no wallet,
signing key, order route, or execution adapter.

## Start locally with Docker

Requires Docker Compose v2. Run these commands in PowerShell from the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
# Replace POSTGRES_PASSWORD with a local development password.
# Leave MODEL_MODE=disabled, or use MODEL_MODE=mock for the no-key research demo.
$env:POSTGRES_HOST_PORT='15432' # omit if local port 5432 is available
docker compose up -d postgres
docker compose build api dashboard
docker compose run --rm api python -m alembic upgrade head
docker compose up -d api dashboard
docker compose run --rm api python -m eventtrader.cli sync --limit 10
```

Dashboard: http://localhost:8501
API docs: http://localhost:8000/docs

To run one deterministic development research flow, first set `MODEL_MODE=mock`
in `.env`, restart the API, and use a market UUID returned by `/markets`:

```powershell
docker compose up -d --force-recreate api
$markets = Invoke-RestMethod 'http://localhost:8000/markets?limit=1'
$marketId = $markets[0].id
$body = @{
  source_url = 'https://example.org/development-context'
  extracted_text = 'Low-trust development context for exercising the research graph.'
  source_type = 'manual_context'
  trust_level = 'low'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType 'application/json' -Body $body "http://localhost:8000/markets/$marketId/evidence"
Invoke-RestMethod -Method Post "http://localhost:8000/markets/$marketId/research"
Invoke-RestMethod 'http://localhost:8000/research-runs'
Invoke-RestMethod 'http://localhost:8000/llm-usage'
```

The mock result is a workflow demonstration, not a market claim. Research can return
`APPROVED_FOR_PAPER`, `REJECTED`, or `RESEARCH_UNAVAILABLE`; none creates an
order.

## Local Python startup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

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

## Configuration and model routing

Research defaults to `MODEL_MODE=disabled`. `MODEL_MODE=mock` is deterministic and
requires no key. `MODEL_MODE=litellm` uses the configured `EXTRACTION_MODEL`,
`RESEARCH_MODEL`, `CRITIC_MODEL`, and optional `FALLBACK_MODEL`. Provider
credentials remain process environment variables consumed by LiteLLM; EventTrader
does not load them into settings, graph state, prompts, logs, or database rows.

Expected per-role costs support pre-call gates. `RESEARCH_PER_CALL_BUDGET_USD` and
`RESEARCH_DAILY_BUDGET_USD` are hard limits. Actual provider response cost is used
when LiteLLM supplies it; otherwise the configured expected cost is persisted.
Fallback runs only after provider failure, and each attempt gets its own usage row.
Malformed output does not trigger fallback.

## Tests and checks

```powershell
uv run --frozen python -m pytest
uv run --frozen python -m pytest --postgres --postgres-port 15432
uv run --frozen python -m alembic check
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
```

PostgreSQL tests create and drop isolated random schemas. Migrations are explicit and
are never run by API startup. Public evidence is treated as untrusted data, bounded by
size and timeout, sanitized before model use, and retained with URL, timestamps, and
content hash. Inline development evidence must be explicitly marked low-trust.

See [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md),
[docs/POLYMARKET_DATA.md](docs/POLYMARKET_DATA.md), and
[docs/RESEARCH.md](docs/RESEARCH.md).
