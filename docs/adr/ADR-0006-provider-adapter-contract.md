# ADR-0006 — Provider adapter contract

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** where provider code lives, and the contract every adapter follows (Milestone P)
**Implemented by:** `feat(providers): add Binance public klines adapter`
**Relates to:** [ADR-0005](ADR-0005-ingestion-boundary-strictness.md) (the strict boundary an adapter
feeds, which named the adapter as the correct home for payload parsing);
[ADR-0001](ADR-0001-canonical-utc-timestamps.md) (canonical time);
`ARCHITECTURE_AND_ROADMAP_V1.md` §4.1 (Data Sources / Provider Adapters), `PROJECT_SPECIFICATION_V1.md`
§16 ("each external provider should have a replaceable adapter")

---

## Context

`fmis.ingest` can decode canonical records, but nothing fetches them: every `CandleSeries` still
originated inside the process. Closing that gap requires the first module allowed to hold transport and
provider-specific knowledge, and the rules for it must be fixed before a second adapter copies whatever
the first one did.

Binance public spot klines (`GET /api/v3/klines`) is the chosen first provider: no API key, documented
stable REST contract, crypto spot candles matching the project's focus, and reachable with `urllib` so
the zero-runtime-dependency invariant holds. `PROJECT_SPECIFICATION_V1.md` names no approved provider —
it requires only that providers be replaceable — so nothing in the specification points elsewhere.

## Decisions

### 1. Adapters live in `fmis.providers`, and the import direction is one-way
`fmis.providers.<provider>` may import `fmis.ingest` and `fmis.data`. It must never import
`fmis.features`, `fmis.alignment`, or `fmis.relative_value`, and none of those may import an adapter.
Adapters cannot live in `fmis.data` (a canonical kernel that imports nothing internal) — the same
reasoning that moved alignment out in ADR-0002.

### 2. The adapter parses; the boundary validates; the models own the invariants
Binance returns prices as strings, which `fmis.ingest` rejects by design (ADR-0005 §3). Converting them
is the adapter's job, because only the adapter knows they are plain decimal and never locale-formatted.
The adapter then calls `decode_candle_series` and **never constructs `Candle` directly** — a test asserts
`Candle` is not imported — so canonical validation cannot be bypassed. Domain-rule violations surface as
`fmis.ingest` errors, unwrapped: they are already precise and positional, and wrapping would hide the
record index.

### 3. `is_closed` is derived from an injectable clock, never guessed
REST klines carry no closed/forming flag (only the websocket stream does). A kline is treated as closed
when its close time has passed relative to `clock()`, defaulting to `datetime.now(timezone.utc)`.

The alternatives were worse: assuming only the last row is forming is wrong for a historical window that
ends in the past, and marking everything closed would silently corrupt the closed-candle rule that every
indicator depends on. **Consequence to live with:** a host clock skewed far from Binance's can mislabel a
boundary candle. That is why the clock is an injected parameter and not an implicit call — it is
overridable, and it makes the decision deterministic under test.

The forming candle is **returned, not dropped**. Filtering stays `CandleSeries.closed()`'s job, so the
adapter never decides what the caller may see.

### 4. Transport is an injected callable that does not raise on HTTP status
`Transport = Callable[[str], HttpResponse]` returns `(status, body)` for every response, including 4xx —
because Binance puts its error details (`{"code": -1121, "msg": "Invalid symbol."}`) in the body of a
4xx. Interpreting status and body together therefore belongs to the adapter, not the transport. A
transport raises only when the request could not be completed at all. This is what keeps the test suite
network-free: injecting a function is the whole mechanism, with no mocking framework involved.

### 5. Errors are explicit and never become an empty series
`BinanceError` is the base: `BinanceRequestError` (bad arguments, raised before any I/O),
`BinanceTransportError` (request could not be completed), `BinanceAPIError` (error status or error
payload; carries `status`, `code`, `message`), `BinanceResponseError` (2xx but malformed or ambiguous).
An error payload raises **even when the status is 200**, so a provider failure can never be mistaken for
data. An empty `CandleSeries` means only one thing: Binance genuinely returned no rows.

### 6. The interval is used verbatim as the canonical `timeframe`
Binance's `"4h"` is stored as `timeframe="4h"`, not rewritten to `"4H"` or any other casing. Inventing a
normalization now would require a canonical timeframe vocabulary that does not exist, and guessing one
before a second provider exists is the speculative infrastructure this project avoids. **Consequence:**
timeframe labels are provider-native, so two providers may label the same period differently. A canonical
timeframe vocabulary is future work, and it is the natural moment to revisit this.

### 7. Deliberate non-scope
No authentication, private/account/order endpoints, websockets, trading, caching, persistence,
scheduling, or retries. No auto-pagination: `limit` is validated against the endpoint's 1…1000 range, and
walking a longer history means calling again with an advanced `start_time`. No generic provider Protocol
— one concrete adapter exists, and an interface guessed before the second would be speculative, the same
reason ADR-0005 rejected a `MarketDataSource`.

## Alternatives considered

- **A `requests`/`httpx` dependency.** Rejected: `urllib` is sufficient for one GET, and zero runtime
  dependencies is a documented project invariant worth more than the ergonomics.
- **A transport that raises on non-2xx** (the natural `urllib` behaviour). Rejected: it discards the
  error body where Binance's actual reason lives, forcing the adapter to reach into exception internals.
- **Recording request metadata in a wrapper result object.** Rejected as unnecessary API surface: the
  factual metadata (symbol, timeframe, timestamps, `is_closed`) already lives on the canonical objects,
  and `build_klines_url` is public for anyone who needs the exact request.
- **Auto-pagination to satisfy arbitrary ranges.** Rejected for this milestone: it introduces loop,
  partial-failure, and rate-limit policy that deserve their own decision.
- **Dropping the forming candle.** Rejected: the adapter would be deciding what the caller may see, and
  the information is already exposed per candle.

## Consequences

- A real path exists for the first time: **public provider → adapter → strict ingestion → canonical
  `CandleSeries`**, with the full analytical stack downstream of it.
- The adapter is replaceable per `PROJECT_SPECIFICATION_V1.md` §16, and the rules above are what a second
  adapter must follow. If a second one arrives and the shapes genuinely converge, extracting a Protocol
  becomes an evidence-based decision instead of a guess.
- Test-enforced boundaries: no third-party imports, no `Candle` import, no private/authenticated
  endpoints or websocket references in code, and no analytical package loaded by importing the adapter.
- Known limitations recorded here rather than in code comments alone: clock-skew sensitivity (§3),
  provider-native timeframe labels (§6), and no pagination (§7).
