# Paper trading and reconciliation

EventTrader's execution surface is internal and PAPER-only. `POST /paper/orders`
accepts a previously persisted `APPROVED_FOR_PAPER` report. The service rechecks the
proposal limit, snapshot freshness, fee data, market constraints, held shares, cash,
exposure, loss, drawdown, market-count, and trade-count limits before writing anything.

A market sync persists every positive normalized bid and ask level beside its snapshot.
A marketable BUY consumes asks from lowest price upward; a SELL consumes bids from
highest price downward. No eligible depth leaves the order open. An empty relevant
book rejects it. Limited depth produces one partial aggregate fill and reserves the
unfilled BUY notional. Every accepted fill updates cash, position, costs, and the audit
ledger in one PostgreSQL transaction guarded by a portfolio advisory lock.

Immediate simulated fills are taker fills. Fee-bearing fills use the current Polymarket
formula per consumed level: `shares * fee_rate * price * (1 - price)`, rounded to five
decimal places. Spread cost is measured from midpoint to the best relevant touch;
slippage is measured from that touch to the depth-weighted average fill. Successful
research cost is allocated to position cost basis and remains separately visible.

`POST /paper/portfolio/mark` marks open positions to the latest stored best bid.
`POST /paper/portfolio/reconcile-resolutions` reads the public Polymarket Data API. A
position settles only when the response uniquely matches its condition, has a timestamp,
and supplies a binary payout vector with exactly one winner. Missing or ambiguous data
creates an idempotent warning and leaves the position open.

The API routes are:

- `POST /paper/orders`
- `GET /paper/orders`
- `GET /paper/orders/{order_id}`
- `POST /paper/orders/{order_id}/cancel`
- `GET /paper/positions`
- `GET /paper/portfolio`
- `POST /paper/portfolio/mark`
- `POST /paper/portfolio/reconcile-resolutions`

No class in the paper execution package accepts a wallet, private key, signer, or
provider trading client. The only provider call in reconciliation is an unauthenticated
HTTP GET for published resolution data.
