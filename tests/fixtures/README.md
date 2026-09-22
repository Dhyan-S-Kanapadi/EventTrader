# Fixture provenance

Captured from official documentation on 2026-09-21, not live API recordings:

- `gamma_market.json`: composed from the Gamma wire examples in
  https://docs.polymarket.com/market-data/discover-markets and
  https://docs.polymarket.com/market-data/market-details. Token IDs, ID, and question
  use the documented market. Status/timing/fee fields are documentation examples,
  not assertions about the current state or fees of that market.
- `clob_book.json`: API example from
  https://docs.polymarket.com/market-data/prices-order-books. The documentation's
  literal `"..."` entries are omitted, so this is a truncated book, not live depth.

These public-data fixtures contain no headers, credentials, or wallet data.
Tests mutate copies for malformed/error cases and generate synthetic second pages.
Tests do not require internet access. Live-response recordings, when obtainable,
must be separately labelled and must never include request credentials.
