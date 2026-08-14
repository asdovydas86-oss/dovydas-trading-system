"""The price snapshot service — the one place a venue is named for a mark.

    fmis.providers.binance.fetch_klines   public candles -> CandleSeries
    fmis.marks.build_price_snapshot       candles        -> PriceSnapshot

**No price is computed here.** This module chooses what to fetch, isolates each
symbol's failure, and hands the result to `fmis.marks`, which owns the selection
rule. A test asserts the module contains no arithmetic operator of its own — the
same guarantee `fmis.pipeline.market_analysis` already holds for the analysis
pipeline, and for the same reason: a number produced at the composition layer is
a number no engine can be held to.

**Per-symbol failure isolation, and only for the failures a provider can have.**
Four named exception families become a `PriceUnavailable` entry; anything else
propagates, because a `KeyError` from inside FMITS rendered as *"this market
could not be priced"* teaches the owner to ignore both. This is the identical
discipline the daily-workflow runner applies to a symbol whose analysis fails —
named in prose rather than by module path, because this repository's guard tests
scan raw text for an import and a mention would weaken one.

**Two candles are requested, not one.** A window of one candle can consist
entirely of the forming bar, which would make every symbol unpriceable at the
top of an interval. Two is the smallest window that always contains a closed bar
in a live market, and `PriceReading.closed_count` reports what was actually
found.

**The interval is a stated policy, not an implicit one.** `MARK_INTERVAL` is
`1h`: fine enough that a valuation is at most one hour behind the market, coarse
enough that every market this system watches has a real closed hourly bar. It is
a default the caller overrides, and the chosen value travels on every reading.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Callable

from fmis.data import CandleSeries
from fmis.ingest import IngestError
from fmis.marks import PriceSnapshot, build_price_snapshot, empty_price_snapshot
from fmis.pipeline.structural_facts import BINANCE_SPOT
from fmis.providers.binance import BinanceError, Transport, fetch_klines

__all__ = [
    "MARK_INTERVAL",
    "MARK_CANDLE_LIMIT",
    "MARK_SOURCE",
    "NO_SOURCE_CONSULTED",
    "fetch_price_snapshot",
]

#: The timeframe a mark is read from unless the caller names another. See the
#: module docstring for why an hour: a stated policy, printed with every figure
#: it produces, never a number buried in a call site.
MARK_INTERVAL = "1h"

#: How many candles to request per symbol. Two, because a one-candle window can
#: be entirely the forming bar.
MARK_CANDLE_LIMIT = 2

#: The provenance label carried onto every reading. `BINANCE_SPOT` is reused
#: rather than re-spelled, so a fact sheet and a mark taken from the same
#: endpoint cannot claim two different sources.
MARK_SOURCE = BINANCE_SPOT

#: The `source` of a snapshot that deliberately priced nothing.
NO_SOURCE_CONSULTED = "no price source was consulted"


def fetch_price_snapshot(
    symbols: Sequence[str],
    *,
    taken_at: datetime,
    interval: str = MARK_INTERVAL,
    limit: int = MARK_CANDLE_LIMIT,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> PriceSnapshot:
    """Fetch one price per symbol and freeze them into a snapshot.

    Args:
        symbols: exact provider symbols. Duplicates are collapsed, preserving
            first-seen order, because one market has one price and asking twice
            would produce a snapshot the domain refuses to build.
        taken_at: the instant the snapshot describes. Supplied rather than read,
            so a run is reproducible.
        interval: the timeframe a price is read from.
        limit: candles requested per symbol.
        transport, clock, base_url: the provider's own injection points,
            forwarded unchanged so a caller can run this network-free.

    Returns:
        A `PriceSnapshot`. An empty ``symbols`` produces an empty snapshot
        rather than a failure — a portfolio holding nothing needs no price, and
        that is a legitimate morning.

    Raises:
        Anything other than a provider, ingestion or argument failure. Those six
        families become `PriceUnavailable` rows; an internal defect propagates.
    """
    wanted: list[str] = []
    for symbol in symbols:
        if symbol not in wanted:
            wanted.append(symbol)
    if not wanted:
        return empty_price_snapshot(taken_at=taken_at, source=NO_SOURCE_CONSULTED)

    fetched: list[CandleSeries] = []
    failures: dict[str, str] = {}
    for symbol in wanted:
        try:
            fetched.append(
                fetch_klines(
                    symbol,
                    interval,
                    limit=limit,
                    transport=transport,
                    clock=clock,
                    **({} if base_url is None else {"base_url": base_url}),
                )
            )
        except (BinanceError, IngestError, ValueError, TypeError) as error:
            failures[symbol] = (
                f"{symbol} {interval}: {type(error).__name__}: {error}"
            )
    return build_price_snapshot(
        fetched,
        taken_at=taken_at,
        source=MARK_SOURCE,
        unreadable=failures,
    )
