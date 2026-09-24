# Read-only Polymarket contract

Official sources reviewed through 2026-09-24:

- [REST APIs and authentication](https://docs.polymarket.com/getting-started/api)
- [Current Python SDK](https://docs.polymarket.com/getting-started/python)
- [Keyset market listing](https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination)
- [Market by Gamma ID](https://docs.polymarket.com/api-reference/markets/get-market-by-id)
- [Discovery and slug lookup](https://docs.polymarket.com/market-data/discover-markets)
- [Market details and fee schedule](https://docs.polymarket.com/market-data/market-details)
- [Order-book API](https://docs.polymarket.com/api-reference/market-data/get-order-book)
- [Book structure and outcome tokens](https://docs.polymarket.com/market-data/prices-order-books)
- [Resolution state](https://docs.polymarket.com/api-reference/markets/get-resolution-state)
- [Trading fees](https://help.polymarket.com/en/articles/13364478-trading-fees)

The official Python distribution is `polymarket-client`, importing `polymarket`.
This milestone uses the existing `httpx` dependency directly instead of installing
an SDK that includes account and trading surfaces. Only public GET requests are
made, without authentication headers, wallet code, redirects, or provider secrets.

| Operation | Source |
| --- | --- |
| Discovery | `GET https://gamma-api.polymarket.com/markets/keyset`, with `closed=false`, `limit`, and `after_cursor` |
| Detail by ID | `GET https://gamma-api.polymarket.com/markets/{id}` |
| Detail by slug | `GET https://gamma-api.polymarket.com/markets/slug/{slug}` |
| Outcome book | `GET https://clob.polymarket.com/book?token_id={token_id}` |
| Resolution | `GET https://data-api.polymarket.com/v2/resolutions?condition={condition_id}` |

Discovery follows `next_cursor` until exhausted or the requested limit is reached.
Repeated cursors and pages without progress fail explicitly. Each invocation is
bounded to 1-1000 markets, with pages of at most 100. The wire models validate the
documented fields used by this integration and ignore unrelated future fields.

## Mapping and limits

- Gamma `id` is the external market ID, distinct from the local UUID and
  `conditionId`. `outcomes` and `clobTokenIds` may be JSON-encoded arrays. They are
  paired by index and checked for matching lengths and unique numeric token IDs.
- `description` supplies resolution rules and `resolutionSource` supplies the source.
  `endDate` is the scheduled close time. `closedTime` does not prove resolution, so
  `resolved_at` remains null. `created_at` and `updated_at` are local database times.
- Status retains active, closed, archived, inactive, or unknown. Accepting-orders
  and order-book-enabled flags are separate. Only active outcomes with both flags
  explicitly true are read for snapshots. This is an availability screen, not
  economic eligibility, freshness approval, or permission to trade.
- Snapshots include `outcome_id`; market-level prices alone would mix YES and NO.
  A composite foreign key enforces outcome ownership. Changes to an existing token
  at an outcome index are rejected instead of rewriting snapshot history.
- Best bid is the maximum positive-size bid; best ask is the minimum positive-size
  ask. Array order is not trusted. Spread and midpoint require both sides. Empty
  sides remain null; crossed books and invalid prices fail validation.
- `min_order_size` and `tick_size` come from the token's CLOB book. Normalized
  positive bid and ask levels are persisted by snapshot for deterministic paper fills.
- Gamma `feeSchedule.rate` is a fee-curve parameter, not a flat percentage. The
  exponent, taker-only flag, rebate fraction, and `feesEnabled` are retained.
  Missing schedules remain unknown; only explicit `feesEnabled=false` yields zero.
  Paper taker fills use `shares * fee_rate * price * (1 - price)` per consumed level
  and round the aggregate fee to five decimal places.
- Liquidity and total volume come from Gamma and are market-wide. They repeat on
  each outcome snapshot and must not be summed across outcomes. Open interest is
  null because the selected endpoints do not supply it. Categories are not guessed.
- `captured_at` is local book receipt time, `provider_timestamp` is the book's
  timestamp, and `metadata_captured_at` is Gamma receipt time. These are not an
  atomic venue snapshot, and a book timestamp does not guarantee executability.
- Raw provider responses are not persisted. `raw_payload_hash` combines canonical
  payload hashes. Response headers, secrets, clients, and settings never enter graph
  state.

## Failure behavior

Rate limits and transport or 5xx failures receive bounded exponential retries.
`Retry-After` seconds and HTTP dates are honored within the configured maximum wait;
a longer wait terminates rather than retrying early. Missing resources and invalid
responses are not retried. Logs include a local correlation ID, status code, and
attempt, without raw response bodies or exception text.

Market and outcome upserts form one transaction. Each successful outcome snapshot
commits separately. Provider failures leave prior snapshots intact and appear in
CLI output. Exit code 2 means partial capture, 1 means run failure, and 0 means the
bounded run completed. No scheduler or automatic whole-run retry exists.

## Verification evidence

PostgreSQL tests apply the real migration in isolated temporary schemas and exercise
uniqueness, upserts, rollback, numeric precision, snapshot history, partial graph
failures, and read-only APIs. HTTP and dashboard tests use safe fixtures and mocks.
See `tests/fixtures/README.md` for fixture provenance.

Direct Polymarket requests timed out from both the host and Docker during this
implementation. The fixtures are official documentation examples, not live response
recordings. Mock success must not be represented as live interoperability. Rerun a
limited manual sync when provider connectivity is available; no credentials are
needed. These checks make no production-readiness or profitability claim.
