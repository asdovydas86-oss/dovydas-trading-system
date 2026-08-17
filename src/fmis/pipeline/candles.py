"""Closed candles for a simulation run — the one place a venue is named for a replay.

    fmis.providers.binance.fetch_klines   public candles -> CandleSeries
    fmis.paper.bars.bars_from_series      candles        -> exact PriceBars

A sibling of `fmis.pipeline.prices` and written to the same three rules, because
it is the same kind of module: it chooses **what** to fetch, isolates each
symbol's failure, and computes nothing. A test asserts it holds no arithmetic
operator of its own — a number produced at the composition layer is a number no
engine can be held to.

**Only closed candles reach a simulation.** `CandleSeries.closed()` is applied
here as well as inside `fmis.paper.bars`, and the redundancy is deliberate: the
no-lookahead guarantee holds even if either mechanism alone had a bug, which is
the same two-independent-checks construction `AV`'s replay transport already uses
for its own boundary.

**A window that does not reach back to the activation is reported, never
silently truncated.** One request returns at most the provider's page of candles;
an activation older than that window would otherwise be replayed from the middle
of its own life, and every excursion it produced would be a measurement of a
shorter trade than the one that happened.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fmis.data import CandleSeries
from fmis.ingest import IngestError
from fmis.providers.binance import MAX_LIMIT, BinanceError, Transport, fetch_klines

__all__ = [
    "SIMULATION_INTERVAL",
    "SIMULATION_CANDLE_LIMIT",
    "CandleFetch",
    "fetch_simulation_candles",
]

#: The timeframe a simulation advances on unless the caller names another. An
#: hour: fine enough that a swing stop is tested against something like the path
#: price actually took, coarse enough that a multi-week trade fits inside one
#: provider page. A stated policy, carried onto every activation that uses it.
SIMULATION_INTERVAL = "1h"

#: How many candles to request per symbol. The provider's own documented maximum,
#: because a replay wants every bar since the activation and there is no cheaper
#: way to ask for "as far back as you will go".
SIMULATION_CANDLE_LIMIT = MAX_LIMIT


@dataclass(frozen=True, slots=True)
class CandleFetch:
    """What one fetch returned, and what it could not.

    Two mappings rather than one with `None` values: *"this symbol was not asked
    for"* and *"this symbol was asked for and failed"* are different facts about a
    simulation run, and a caller that cannot tell them apart will report a trade
    as unadvanced when it was actually unreachable.
    """

    series: Mapping[str, CandleSeries]
    failures: Mapping[str, str]

    @property
    def fetched_symbols(self) -> tuple[str, ...]:
        return tuple(self.series)

    @property
    def failed_symbols(self) -> tuple[str, ...]:
        return tuple(self.failures)

    def earliest_close_of(self, symbol: str) -> datetime | None:
        """The open time of the oldest closed bar fetched, or `None` if there is none.

        What a caller compares an activation's own instant against to decide
        whether the window reached back far enough to replay it honestly.
        """
        series = self.series.get(symbol)
        if series is None or not series.candles:
            return None
        return series.candles[0].timestamp


def fetch_simulation_candles(
    symbols: Sequence[str],
    *,
    interval: str = SIMULATION_INTERVAL,
    limit: int = SIMULATION_CANDLE_LIMIT,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> CandleFetch:
    """Fetch the closed candle history a replay needs, one symbol at a time.

    Args:
        symbols: exact provider symbols. Duplicates are collapsed, preserving
            first-seen order.
        interval: the timeframe the simulation advances on.
        limit: candles requested per symbol.
        transport, clock, base_url: the provider's own injection points,
            forwarded unchanged so a caller can run this network-free — the same
            two arguments every replay and every test in this repository already
            uses.

    Returns:
        A `CandleFetch`. An empty ``symbols`` returns an empty one rather than
        failing: a store with no live activation needs no candles, and that is an
        ordinary morning.

    Raises:
        Anything other than a provider, ingestion or argument failure. Those
        families become entries in `failures`; an internal defect propagates,
        because a `KeyError` from inside FMITS rendered as *"this market could
        not be fetched"* teaches the owner to ignore both.
    """
    wanted: list[str] = []
    for symbol in symbols:
        if symbol not in wanted:
            wanted.append(symbol)

    series: dict[str, CandleSeries] = {}
    failures: dict[str, str] = {}
    for symbol in wanted:
        try:
            fetched = fetch_klines(
                symbol,
                interval,
                limit=limit,
                transport=transport,
                clock=clock,
                **({} if base_url is None else {"base_url": base_url}),
            )
        except (BinanceError, IngestError, ValueError, TypeError) as error:
            failures[symbol] = f"{symbol} {interval}: {type(error).__name__}: {error}"
            continue
        series[symbol] = fetched.closed()
    return CandleFetch(series=series, failures=failures)
