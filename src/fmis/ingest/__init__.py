"""Ingestion boundary — untrusted external records into canonical models.

This is the one place where data that FMITS did not construct itself becomes a
canonical `fmis.data` object. Everything upstream of it (a file, an exchange
payload, a TradingView export, a hand-written fixture) is *untrusted*; everything
downstream of it is a validated `CandleSeries`.

v1 decodes OHLCV candle records only (`decode_candle`, `decode_candle_series`,
`decode_candle_series_from_json`). See ADR-0005.

Scope boundary — this package is a **decoder**, not a provider adapter. It has no
transport, no network, no credentials, no retries, no pagination, no rate limits,
and no provider-specific field names. A future provider adapter (§4.1, deferred)
is expected to fetch and rename its own payload into the canonical field names,
then call this decoder; provider quirks stay in the adapter and never leak into
the canonical layer.

Hard rules:
  * **Strict, never repairing.** Missing field, unknown field, wrong type, or an
    invariant violation raises. Nothing is coerced from a string, defaulted,
    dropped, reordered, deduplicated, or filled.
  * **Positional errors.** Every failure names the record index and the field, so
    a bad row in a thousand-row payload is findable.
  * **The canonical models remain the single authority on invariants.** This
    package checks *shape* (presence and type of each field) and then hands the
    values to `Candle`/`CandleSeries`, which enforce the domain invariants
    (UTC contract, OHLC ordering, non-negativity, strictly increasing timestamps).
    Those rules are not re-implemented here.

Dependency boundary: imports only `fmis.data` and the standard library. It does
not import `fmis.features`, `fmis.alignment`, or `fmis.relative_value`.
"""

from __future__ import annotations

from fmis.ingest.candles import (
    CANDLE_FIELDS,
    IngestError,
    RecordDecodeError,
    SeriesDecodeError,
    decode_candle,
    decode_candle_series,
    decode_candle_series_from_json,
)

__all__ = [
    "decode_candle",
    "decode_candle_series",
    "decode_candle_series_from_json",
    "CANDLE_FIELDS",
    "IngestError",
    "RecordDecodeError",
    "SeriesDecodeError",
]
