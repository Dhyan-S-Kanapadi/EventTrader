# EventTrader project context

## Mission and current scope

EventTrader is a one-week MVP for controlled Polymarket research and paper trading.
The implemented loop is:

Polymarket data -> deterministic filters -> evidence -> cost gate -> research ->
critique -> deterministic economics and risk -> paper execution -> reconciliation ->
Streamlit.

Milestones 1 through 5 are complete. Paper execution is an internal simulation over
durable public order-book snapshots. Research approval never executes automatically;
a caller must explicitly submit a paper order.

## Architecture

- Python 3.12, Pydantic v2, FastAPI, Streamlit, and Plotly.
- LangGraph and LangChain Core for bounded orchestration.
- LiteLLM for configurable research model routing; disabled by default.
- SQLAlchemy 2, Alembic, and PostgreSQL for durable records.
- httpx for public, unauthenticated Polymarket and evidence retrieval.
- Docker Compose and pytest for local operation.

The research graph ends with a persisted `APPROVED_FOR_PAPER`, `REJECTED`, or
`RESEARCH_UNAVAILABLE` decision. The separately invoked paper graph is:

`START -> create_paper_order -> simulate_paper_fill -> update_paper_portfolio ->
record_portfolio_event -> END`.

The paper service owns one atomic database transaction for order creation, fill
simulation, position accounting, and ledger events. BUY limits consume asks and SELL
limits consume bids from the latest stored book. It supports full, partial, open,
rejected, cancelled, expired, and filled orders; duplicate proposals and idempotency
keys cannot create duplicate fills. Marks use the latest stored best bid. Resolution
reconciliation uses the public Polymarket resolution endpoint and abstains unless one
outcome has payout 1, all others have payout 0, and a resolution timestamp exists.

## Hard constraints

1. Polymarket is the only venue.
2. PAPER is the default and only enabled mode.
3. No wallet or private key is requested or stored.
4. No provider order placement, modification, cancellation, signing, or live adapter exists.
5. Models research and propose; deterministic Python owns economics, risk, and fills.
6. Secrets never belong in source, logs, database rows, graph state, prompts, or Streamlit.
7. Insufficient evidence, freshness, liquidity, cost data, or EV means abstain or reject.
8. Every model attempt, including failed primary and fallback calls, is cost-metered.
9. No profitability claims.
10. Changes stay focused, typed, tested, and documented.

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

The paper ledger rechecks these limits against persistent cash, exposure, positions,
trade count, realized daily and weekly loss, and drawdown before each BUY.

## Cost and accounting policy

- Market scanning is deterministic and makes no model calls.
- Extraction precedes research and has per-call and daily budget checks.
- Research runs only when plausible gross value covers expected research and trading costs.
- Actual model usage remains stored separately from fills and trading cash.
- Position cost basis and net P&L include allocated successful research cost and estimated fees.
- Spread and depth slippage remain separate visible metrics.
- Fee-bearing taker fills use the current documented Polymarket fee curve at each book level.
- Research and execution are manual and bounded; no scheduler continuously calls models.

## Milestones

1. **Foundation - complete.**
2. **Read-only Polymarket ingestion - complete.**
3. **Evidence provenance and cost gates - complete.**
4. **Metered research, critique, and deterministic proposal evaluation - complete.**
5. **Paper execution, portfolio accounting, and resolution reconciliation - complete.**
6. **Next: bounded scheduling and restart hardening.** Schedule deterministic scanning and
   tightly budgeted research only after adding single-run locks, stale-run recovery, and
   operator-visible scheduler state. Keep paper execution explicitly invoked.
