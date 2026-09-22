# EventTrader project context

## Mission and scope

Build a controlled autonomous Polymarket research and paper-trading system in one
week. Demonstrate the full decision loop with transparent decisions, costs, and
risk checks in Streamlit. Prefer the smallest reliable implementation. No
profitability claims, enterprise platform, multi-venue support, or live execution.

**Milestones 1 and 2** are implemented. The original status graph is preserved.
The manual read-only ingestion graph is `START -> discover_markets ->
persist_markets -> capture_snapshots -> END`. PostgreSQL stores markets, outcomes,
and per-outcome snapshots through Alembic migrations. Public Gamma/CLOB GETs use
httpx; read-only APIs and Streamlit expose saved data. No LLM calls, scheduler,
wallets, orders, or execution exist. Initial capital is configuration, not a balance.
See `docs/POLYMARKET_DATA.md` for verified official sources and data semantics.
Live provider interoperability remains unverified because direct requests timed out.

## Target architecture

Polymarket market data -> deterministic market filters -> low-cost evidence
extraction -> research-cost gate -> LLM research -> adversarial critique ->
deterministic expected-value and risk checks -> paper execution -> position
reconciliation -> Streamlit dashboard.

LangGraph orchestrates bounded work. LLMs research and propose probabilities;
deterministic Python owns fee calculation, expected value, position sizing, risk
limits, and fills. Evidence and decisions must become inspectable records in later
milestones. Insufficient evidence, liquidity, or economics means ABSTAIN. Provider
assumptions must be verified from official documentation when implementing each
integration; never infer unsupported capabilities.

Technology decisions:

- Python 3.12; FastAPI for backend/health APIs; Streamlit + Plotly for visibility.
- LangGraph + LangChain Core for orchestration; LiteLLM for configurable model routing.
- Pydantic v2/settings for validation; SQLAlchemy 2 + Alembic for persistence.
- PostgreSQL in Docker Compose; APScheduler for bounded scheduled work.
- httpx and WebSockets for provider communication; pytest for tests.
- Docker/Compose for local development; uv lockfile, Ruff, and mypy for development.

LiteLLM, APScheduler, and WebSocket dependencies will be introduced when used.
No background scheduling, model clients, or speculative adapter interfaces in M1.
Plotly is declared but charts remain deferred. Alembic now manages the M2 schema.

Package responsibilities under `src/eventtrader/`: `api`, `dashboard`,
`orchestration`, `domain`, `persistence`, `market_data`, `research`, `strategy`,
`risk`, `paper_execution`. Tests mirror behavior rather than every placeholder.

## Hard constraints

1. Polymarket is the only venue. No stock brokers, NSE, crypto exchanges, or unrelated integrations.
2. PAPER is the default and only enabled mode throughout this MVP.
3. Never implement or request real wallets or private keys in this milestone.
4. No live order can be placed. A future milestone would require a separately guarded live adapter.
5. LLMs research and propose; deterministic Python alone calculates fees, EV, size, risk, and fills.
6. Never put secrets, credentials, or API keys in source, logs, DB records, graph state, or Streamlit.
7. Prefer ABSTAIN when evidence, liquidity, or economics are insufficient.
8. Every model call must be cost-metered when introduced. Never continuously call models.
9. Never make profitability claims.
10. Keep changes focused, readable, typed, testable, and documented.

## Initial paper risk configuration

| Setting | Value |
| --- | ---: |
| starting_capital_usd | 50 |
| max_single_position_usd | 2.50 |
| max_total_exposure_usd | 30 |
| min_cash_reserve_usd | 20 |
| max_daily_loss_usd | 3 |
| max_weekly_loss_usd | 7.50 |
| max_drawdown_percent | 20 |
| max_simultaneous_markets | 3 |
| max_trades_per_day | 5 |

These are validated configuration defaults in M1, not an active risk engine.
Define mark-to-market, realized/unrealized loss, UTC day/week boundaries, and
drawdown high-water marks explicitly before implementing risk enforcement.

## LLM cost policy

- Scanning is deterministic and makes no model calls.
- Cheap extraction precedes expensive research. Any model-assisted extraction
  must also be budgeted and metered from its first call.
- Expensive research requires plausible gross expected profit sufficient to cover
  all expected research and trading costs. Unknown cost/fee data means ABSTAIN.
- Include critique and bounded retries in research budgets; reserve budget before
  calling models and reconcile actual usage afterward.
- Store model costs separately from trading P&L. No model keys in state or records.
- Research is bounded per candidate and per run; scheduling must not create
  continuous model loops. Budgeting and metering precede the first LLM integration.

## Planned milestone order

1. **Foundation (complete):** package structure, safe settings, health/readiness,
   status graph, JSON application logs, dashboard banner, Compose, tests/docs.
2. **Read-only market ingestion (implemented; live provider validation pending):** verify official
   Polymarket documentation, define market/outcome/book snapshots, introduce the
   first SQLAlchemy models and Alembic migration, store public data, apply explicit
   market-availability flags and show snapshots. No LLMs or orders. The explicit M2
   scope defers economic/freshness eligibility rules to the evidence/cost-gate work.
3. **Evidence and cost gate:** collect public evidence with provenance, timestamps,
   low-cost extraction, deterministic candidate screening, and cost-budget ledger.
4. **Metered research and critique:** LiteLLM routing, structured probability and
   evidence outputs, adversarial review, call limits, retries, actual cost records,
   and bounded LangGraph branches; evidence is untrusted data, not instructions.
5. **Deterministic economics, risk, and paper execution:** verify fee assumptions,
   calculate cost-adjusted EV, enforce every configured risk limit, apply conservative
   paper fills, keep cash/exposure ledgers, and reconcile positions and outcomes.
6. **End-to-end MVP hardening and visibility:** bounded APScheduler jobs, duplicate
   protection/restart behavior, failure-path integration tests, Plotly views of
   decisions/costs/risk, and an operator demo of the full paper decision loop.

Each milestone remains scoped for the one-week MVP. Use HTTP snapshots first;
add WebSockets only if freshness requirements justify maintaining a live stream.
The single next milestone is **Milestone 3: evidence collection and the deterministic
research-cost gate**, after a successful limited live read-only sync is verified.
