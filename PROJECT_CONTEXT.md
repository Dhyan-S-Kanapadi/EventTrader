# EventTrader project context

## Mission and current scope

EventTrader is a one-week MVP for controlled Polymarket research and paper trading.
The target loop is:

Polymarket data -> deterministic filters -> evidence -> cost gate -> research ->
critique -> deterministic economics and risk -> paper execution -> reconciliation ->
Streamlit.

Milestones 1 through 4 are implemented through the deterministic proposal decision.
Milestone 4 combines the previously planned evidence/cost-gate and metered-research
work because the requested repository jumped from Milestone 2 to Milestone 4. It adds
evidence provenance, LiteLLM routing, deterministic mock mode, model-attempt metering,
adversarial critique, selected-outcome pricing, cost-adjusted EV, configured risk
checks, APIs, and the Research Lab. `APPROVED_FOR_PAPER` is only a decision label.
No paper order, position, fill, wallet, signing, or live-trading code exists.

## Architecture

- Python 3.12, Pydantic v2, FastAPI, Streamlit, Plotly.
- LangGraph and LangChain Core for bounded orchestration.
- LiteLLM for configurable model routing; disabled by default.
- SQLAlchemy 2, Alembic, and PostgreSQL for durable records.
- httpx for public provider and evidence retrieval.
- Docker Compose and pytest for local operation.

The research graph is:

`START -> load_market_context -> load_latest_market_snapshot ->
collect_or_load_evidence -> validate_evidence -> cheap_fact_extraction ->
pre_research_budget_gate -> research_analysis ->
post_research_expected_value_gate -> conditional_critic ->
resolution_rule_validation -> create_structured_trade_proposal ->
deterministic_risk_evaluation -> persist_run_and_results -> END`.

Evidence and market text are untrusted input. Models can only return validated
research schemas. Deterministic Python selects the matching outcome snapshot,
calculates spread, fee and configured slippage costs, computes expected value, and
applies risk limits. Any missing, stale, malformed, unsupported, conflicting, or
uneconomic input produces an abstention or rejection.

## Hard constraints

1. Polymarket is the only venue.
2. PAPER is the default and only enabled mode.
3. No wallet or private key is requested or stored.
4. No order placement, modification, cancellation, fill, or live adapter exists.
5. Models research and propose; deterministic Python owns economics and risk.
6. Secrets never belong in source, logs, database rows, graph state, prompts, or Streamlit.
7. Insufficient evidence, freshness, liquidity, cost data, or EV means abstain.
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

The research evaluator applies these limits to a zero-position development risk
state. Persistent cash, exposure, loss, drawdown, trade-count, and position ledgers
remain future paper-execution work.

## Research cost policy

- Market scanning is deterministic and makes no model calls.
- Extraction precedes research and has its own per-call and daily budget check.
- Research runs only when plausible gross value covers expected research and trading costs.
- Critique is separately rechecked before its call.
- Unknown fee or spread data and configured slippage are handled conservatively.
- Actual and expected model cost records are separate from future trading P&L.
- Research is manual and bounded; no scheduler continuously calls models.
- Provider fallback occurs only after a provider failure. Invalid JSON does not retry.

## Milestones

1. **Foundation — complete.**
2. **Read-only Polymarket ingestion — complete; limited live interoperability still requires operator verification.**
3. **Evidence provenance and cost gates — complete as part of the requested Milestone 4.**
4. **Metered research, critique, and deterministic proposal evaluation — complete.**
5. **Next: paper execution and reconciliation.** Add durable cash/position ledgers,
   conservative paper fills, idempotency, and resolution reconciliation. Keep all
   execution internal and PAPER-only.
6. **MVP hardening and visibility.** Add bounded scheduling only after manual runs,
   ledgers, and restart behavior are proven.
