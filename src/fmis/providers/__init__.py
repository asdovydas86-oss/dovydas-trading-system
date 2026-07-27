"""Provider adapters — the only layer allowed to know an external API's shape.

An adapter fetches raw data from one concrete provider and renames/parses it into
the canonical record shape (`fmis.ingest.CANDLE_FIELDS`), then calls the
ingestion boundary to decode it. Everything provider-specific — base URLs, query
parameters, field order, string-encoded numbers, error payloads, rate limits —
stops here. Nothing downstream ever sees a provider type.

    provider REST API
      -> fmis.providers.<provider>      transport + provider→canonical mapping
      -> fmis.ingest                    strict, provider-agnostic decoding
      -> fmis.data                      canonical Candle / CandleSeries

Implemented: `binance` (public spot klines, no API key).

Rules for any adapter added here:
  * **Import direction is one-way.** An adapter may import `fmis.ingest` and
    `fmis.data`. It must never import `fmis.features`, `fmis.alignment`, or
    `fmis.relative_value`, and nothing in those packages may import an adapter.
  * **No canonical validation.** Invariants belong to `Candle`/`CandleSeries`,
    reached through `fmis.ingest`. An adapter never constructs a canonical model
    directly and never re-implements a domain rule.
  * **Parsing here, not at the boundary.** `fmis.ingest` deliberately rejects
    numeric strings (ADR-0005 §3); converting a provider's `"42000.10"` into a
    float is the adapter's job, because only the adapter knows the payload's
    conventions.
  * **Injectable transport.** HTTP access goes through a `Transport` callable so
    the test suite never touches the network.
  * **No silent emptiness.** A provider error is raised, never turned into an
    empty series. An empty series means the provider genuinely returned no rows.

There is deliberately **no** generic provider Protocol: one concrete adapter
exists, and an interface guessed before a second one would be speculative
(ADR-0005 rejected the same idea for a `MarketDataSource`).
"""

from __future__ import annotations

__all__: list[str] = []
