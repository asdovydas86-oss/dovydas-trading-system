# ADR-0005 — Ingestion boundary: strict decoding, no repair

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** how untrusted external records become canonical models (Milestone O)
**Implemented by:** `feat(ingest): add strict candle ingestion boundary`
**Relates to:** [ADR-0001](ADR-0001-canonical-utc-timestamps.md) (UTC contract, enforced by `Candle`, not
re-implemented here); [ADR-0003](ADR-0003-availability-time-boundary.md) (why observation-series ingestion
is excluded); `ARCHITECTURE_AND_ROADMAP_V1.md` §4.1 (provider adapters, deferred) and §4.2 (validation
and normalization, `partial`)

---

## Context

Every canonical object in FMITS is currently built by hand — in tests, or by ad-hoc `json.loads` +
`Candle(...)` loops duplicated across `tests/test_data_models.py` and `tests/test_ema.py`. Architecture
limitation §2.9(4) records the consequence: nothing can populate a `CandleSeries` from outside the
process, so no amount of downstream capability (indicators, alignment, RVE) can be pointed at real data.

The gap must be closed without building the deferred provider-adapter layer (§4.1), which needs transport,
credentials, retries and provider quirks that would drag non-determinism and dependencies into the core.

## Decisions

### 1. A decoder, not a provider adapter
`fmis.ingest` converts *already-fetched* records into canonical models. It has no transport, network,
credentials, retries, pagination, rate limiting, or provider-specific field names, and adds no
dependencies. A future adapter fetches, renames its payload to the canonical field names, and calls this
decoder. Provider quirks therefore stay in the adapter and never reach the canonical layer — preserving
the property §2.7 calls a current strength ("no provider type has leaked into the domain model").

### 2. The canonical record shape is exactly the `Candle` field names
`CANDLE_FIELDS` is the nine `Candle` fields, no more and no fewer. **Missing fields and unexpected fields
are both errors.** Rejecting extras is the deliberately hostile choice: a payload carrying both `close`
and `adj_close` must not be silently decoded on the wrong one. A test asserts `CANDLE_FIELDS` equals
`Candle.__dataclass_fields__`, so the two cannot drift apart.

### 3. Strict types; nothing is coerced, repaired, or inferred
- `timestamp` — a `datetime`, or an ISO-8601 `str` (including a `Z` suffix). No other format.
- prices/volume — `int` or `float` (an `int` widens to `float`). **Numeric strings are rejected**:
  silently parsing `"1e3"` or `"1,000"` is exactly the repair this layer exists to prevent. `bool` is
  rejected explicitly, since it subclasses `int`.
- `is_closed` — `bool` only; `0`/`1` are rejected, because a forming bar misread as closed silently
  corrupts every downstream signal and violates the closed-candle rule the engine depends on.
- Records are never sorted, deduplicated, filtered, forward-filled, or regrouped. Out-of-order or
  duplicate timestamps raise; filtering by `is_closed` remains `CandleSeries.closed()`'s job.

### 4. The canonical models remain the single authority on invariants
The decoder validates *shape* (field presence and type) and then constructs `Candle`/`CandleSeries`,
which enforce the domain invariants — UTC contract (ADR-0001), OHLC ordering, non-negativity,
finiteness, strictly increasing timestamps, homogeneous identity. Those rules are **not** re-implemented,
so they cannot drift. Model errors are caught and re-raised as `RecordDecodeError` carrying the record
index, with the original exception preserved as `__cause__`. A test asserts the package never imports
`fmis.data._timeutils`.

### 5. Errors are positional
Every failure names the record index, and the field where one is attributable, so a bad row in a
thousand-row payload is findable. `IngestError` is the base; `RecordDecodeError` and `SeriesDecodeError`
also subclass `ValueError`, matching the RVE's error-hierarchy convention.

### 6. Series identity is declared or inferred, never regrouped
`decode_candle_series(records, symbol=..., timeframe=...)` treats a disagreeing record as an error. With
both omitted, identity comes from the first record and every later record must match. An empty payload
therefore requires explicit identity, having no record to take it from.

### 7. v1 scope is OHLCV candles only
`ObservationSeries` ingestion is deliberately excluded. The observation model's real sources are
macroeconomic, fundamental, revised and vintage series, which ADR-0003 gates behind an availability-time
model that does not yet exist. Candle ingestion carries no such hazard. `candle_series_to_observations`
already bridges candles into the observation world, so nothing is blocked by this exclusion.

## Alternatives considered

- **Accept numeric strings and `0`/`1` booleans.** Rejected: every real exchange payload sends strings,
  which makes tolerance feel pragmatic — but coercion at the canonical boundary is unauditable, and the
  correct home for it is the provider adapter that knows the payload's actual conventions.
- **Ignore unexpected fields.** Rejected: silently discarding `adj_close`, `quote_volume`, or a renamed
  field hides real schema mismatches until they surface as wrong numbers.
- **Sort records before validating.** Rejected: consistent with the project-wide rule that no layer
  silently reorders or repairs data; out-of-order input is a provider or caller defect worth surfacing.
- **Put the decoder in `fmis.data`.** Rejected: `fmis.data` is the canonical model kernel and imports
  nothing internal. Decoding untrusted input is a service/policy concern, so it gets its own package —
  the same reasoning that moved alignment out of `fmis.data` in ADR-0002.
- **Define a `MarketDataSource` Protocol now.** Rejected as speculative: there is no implementation to
  satisfy it, and the interface should be derived from a real adapter rather than guessed before one.
- **Also decode `ObservationSeries` now.** Rejected: see §7 — blocked on ADR-0003.

## Consequences

- Real data can enter the system for the first time; `tests/fixtures/btcusdt_4h.json` becomes a
  first-class validated payload rather than something each test re-parses by hand.
- Strictness means most real provider payloads will **not** decode without a mapping step. That is the
  intended cost: it forces provider quirks into an adapter instead of the canonical layer.
- The existing hand-rolled parsing in `tests/test_data_models.py` and `tests/test_ema.py` is left in
  place (those tests exercise the models directly); a test asserts the decoder produces a series equal to
  the hand-built one, so the two paths are proven equivalent rather than merely coexisting.
- A future provider adapter, `ObservationSeries` decoding, streaming/incremental decoding, and any
  caching are additive future work, each its own decision.
