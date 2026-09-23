# Research workflow and provider contract

EventTrader uses the LiteLLM Python SDK directly. The implementation follows the
official [LiteLLM documentation](https://docs.litellm.ai/): model identifiers are
configuration, completion responses expose OpenAI-style choices and usage tokens,
provider failures use normalized exceptions, and provider credentials come from
environment variables. The project deliberately does not use the LiteLLM proxy or
its budget service; small deterministic Python gates and PostgreSQL usage rows are
enough for this MVP.

`MODEL_MODE=disabled` returns `RESEARCH_UNAVAILABLE` without contacting a model.
`MODEL_MODE=mock` produces deterministic schema-valid development responses without
a key. `MODEL_MODE=litellm` calls the configured role model. The optional fallback
model is called once only after provider failure. Invalid output is persisted as a
failed attempt and causes abstention.

Every call records graph run, report, role, provider, model, input/output tokens,
latency, estimated cost, success, error code, and UTC timestamp. Failed primary and
successful fallback attempts are separate rows. Expected role costs are checked
before calls. Daily cost is the UTC-day sum of successful usage rows.

Evidence can be fetched from an application-supplied public HTTP(S) URL or added as
explicit low-trust development context. Fetching rejects non-public addresses,
redirects, unsupported content types, empty content, and oversized responses. HTML
scripts, styles, templates, and noscript content are removed. Evidence retains URL,
publisher, title, published/retrieved timestamps, SHA-256 content hash, source type,
trust level, and extracted text. Missing publication time is accepted only for
explicit low-trust manual context.

The graph never exposes tools for execution, credentials, wallets, signing, or order
submission. Its final statuses are decision records only.
