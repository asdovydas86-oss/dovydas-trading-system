"""The one place a benchmark is turned into observations, whatever its provider.

    Benchmark -> (dispatch on provider) -> ObservationSeries

Milestone BU added a second market-data adapter, and with it the first real
question about where provider choice lives. Before BU there was one adapter and
`fmis.pipeline.pulse` could name it directly; with two, either every composition
root grows a chain of ``if provider ==`` branches, or the dispatch happens once.
This module is that once.

**Both surfaces read through it, so neither can fetch differently.** `fmits pulse`
and `fmits macro` ask for the same benchmark in the same way and get a series
built by the same rules — the same as-of filter, the same series identity, the
same error families. Two composition roots that each knew how to call two
adapters would be four places a window could be selected differently.

**Provider names stay data, not code paths.** A benchmark's provider is a string
in the registry (`fmis.market_pulse.universe`), and this module maps it to an
adapter. Adding a third source is a new entry here and a new benchmark there;
nothing downstream of this module learns a provider's name, and no engine, model
or renderer imports an adapter.

**Nothing here computes a market quantity.** It fetches, filters by an instant,
and hands the result on. The window a metric is measured over is still selected
by `fmis.market_pulse.measure` and `fmis.macro.context`, which is what keeps the
selection in one place per metric rather than one per provider.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fmis.data.observation import ObservationSeries
from fmis.ingest import IngestError
from fmis.market_pulse import (
    Benchmark,
    MACRO_PROVIDER,
    NoObservationsError,
    PULSE_PROVIDER,
    observations_for,
)
from fmis.providers.binance import BinanceError, Transport as BinanceTransport
from fmis.providers.binance import fetch_klines
from fmis.providers.fred import FredError, Transport as FredTransport
from fmis.providers.fred import fetch_observations

__all__ = [
    "MarketDataError",
    "UnknownProviderError",
    "MarketDataSources",
    "DATA_SOURCE_ERRORS",
    "CANDLE_LIMIT",
    "OBSERVATION_LIMIT",
    "observations_for_benchmark",
]


class MarketDataError(Exception):
    """Base class for every failure this dispatch layer raises itself."""


class UnknownProviderError(MarketDataError, ValueError):
    """A benchmark names a provider this build has no adapter for.

    **A configuration defect, and deliberately not a `MarketUnavailable`.** A
    market whose provider does not exist will never be readable, however long the
    owner waits; reporting it as a transient source failure would put it in the
    section a reader scans for things that might work next time. It is raised so
    a misconfigured registry fails loudly at the composition root rather than
    producing a page with a plausible excuse on it.
    """


#: The exception families a composition root turns into a stated per-market
#: failure. Every one is a **provider or data** condition: a venue refused, a
#: payload was malformed, a window was empty, an argument was rejected.
#:
#: **Anything not named here propagates**, which is the point. A `KeyError` from
#: inside FMITS rendered as *"this market could not be read"* teaches the owner
#: to ignore both that row and the real ones — the identical discipline
#: `fmis.pipeline.prices` and `fmis.pipeline.pulse` already apply.
DATA_SOURCE_ERRORS: tuple[type[Exception], ...] = (
    BinanceError,
    FredError,
    IngestError,
    NoObservationsError,
    ValueError,
    TypeError,
)

#: Candles requested per crypto market. Milestone BT's figure, unchanged: the
#: longest hourly horizon needs 169 closed bars and the margin absorbs the
#: forming bar and any bar the provider omits.
CANDLE_LIMIT = 200

#: Observations retained per macro series, counted from the most recent.
#:
#: **A trim, not a fetch limit.** The macro source's CSV endpoint takes no range
#: parameter — a request for the 10-year yield returns every observation since
#: 1962 — so the whole history arrives regardless and this is how much of it is
#: kept. Roughly one year of business days: comfortably more than the longest
#: macro horizon needs, and bounded so that the alignment diagnostics a
#: cross-asset relationship prints stay meaningful. Reporting *"dropped 16,000
#: observations"* because one side carried six decades of history would be a
#: true number that told a reader nothing.
OBSERVATION_LIMIT = 260


@dataclass(frozen=True, slots=True)
class MarketDataSources:
    """The injection points every adapter this build has, in one record.

    Passing one of these rather than eight keyword arguments is what keeps a
    composition root's signature stable when a third adapter is added, and what
    lets a test run the whole pipeline network-free by supplying two fakes.

    Every field is optional and `None` means *use the adapter's own default*,
    which for both adapters is a real HTTP transport. A test that supplies
    neither transport will reach the network, and that is deliberate: silence
    would be a worse default than a slow test.
    """

    binance_transport: BinanceTransport | None = None
    binance_base_url: str | None = None
    fred_transport: FredTransport | None = None
    fred_base_url: str | None = None
    clock: Callable[[], datetime] | None = None
    #: Overrides for how much history to ask each adapter for. `None` uses
    #: `CANDLE_LIMIT` / `OBSERVATION_LIMIT`. They exist so a test can build a
    #: forty-bar fixture without the adapter asking for two hundred, and so a
    #: caller measuring a short window need not pay for a long one.
    candle_limit: int | None = None
    observation_limit: int | None = None


def _tail(series: ObservationSeries, count: int) -> ObservationSeries:
    """The last ``count`` observations, as their own series. Never pads."""
    return ObservationSeries(
        series_id=series.series_id,
        unit=series.unit,
        frequency=series.frequency,
        timestamps=series.timestamps[-count:],
        values=series.values[-count:],
    )


def _from_binance(
    benchmark: Benchmark, *, as_of: datetime, sources: MarketDataSources
) -> ObservationSeries:
    """One crypto market's closed closes, via the candle path.

    Reduction and the as-of filter are `fmis.market_pulse.observations_for`'s,
    unchanged — this function chooses *what* to fetch and nothing about how the
    window is selected.
    """
    instrument = benchmark.instrument
    series = fetch_klines(
        instrument.symbol,
        instrument.interval,
        limit=CANDLE_LIMIT if sources.candle_limit is None else sources.candle_limit,
        transport=sources.binance_transport,
        clock=sources.clock,
        **(
            {}
            if sources.binance_base_url is None
            else {"base_url": sources.binance_base_url}
        ),
    )
    return observations_for(series, as_of=as_of, series_id=instrument.label)


def _from_fred(
    benchmark: Benchmark, *, as_of: datetime, sources: MarketDataSources
) -> ObservationSeries:
    """One macro series' published observations, filtered to ``as_of``.

    **The as-of filter is the same rule the candle path applies**, for the same
    reason: an observation dated after the instant being described is not that
    instant's observation, and asking what markets did last Tuesday must not
    return a print from Thursday. See `fmis.providers.fred` for the dating
    convention and the replay limitation it carries.

    Raises:
        NoObservationsError: nothing survived the filter. An empty window is not
            a market that did not move, and the caller reports it as such.
    """
    instrument = benchmark.instrument
    published = fetch_observations(
        instrument.symbol,
        unit=benchmark.quote_unit,
        frequency=instrument.interval,
        transport=sources.fred_transport,
        **(
            {}
            if sources.fred_base_url is None
            else {"base_url": sources.fred_base_url}
        ),
    )
    kept = [
        (timestamp, value)
        for timestamp, value in zip(published.timestamps, published.values)
        if timestamp <= as_of
    ]
    if not kept:
        raise NoObservationsError(
            f"{instrument.label}: no observation dated at or before "
            f"{as_of.isoformat()} in a series of {len(published.values)} "
            "observation(s); an unread market has no move rather than a move of "
            "zero"
        )
    # Rebuilt under the instrument's own label so a series' identity names the
    # provider and symbol it came from, exactly as the candle path's does.
    filtered = ObservationSeries(
        series_id=instrument.label,
        unit=published.unit,
        frequency=published.frequency,
        timestamps=tuple(timestamp for timestamp, _ in kept),
        values=tuple(value for _, value in kept),
    )
    return _tail(
        filtered,
        OBSERVATION_LIMIT
        if sources.observation_limit is None
        else sources.observation_limit,
    )


#: Provider name -> the function that reads it. A mapping rather than a chain of
#: conditionals, so a provider with no adapter is a missing key with a precise
#: error rather than a silently skipped branch.
_ADAPTERS: dict[str, Callable[..., ObservationSeries]] = {
    PULSE_PROVIDER: _from_binance,
    MACRO_PROVIDER: _from_fred,
}


def observations_for_benchmark(
    benchmark: Benchmark, *, as_of: datetime, sources: MarketDataSources
) -> ObservationSeries:
    """One benchmark's observation series, from whichever adapter serves it.

    Args:
        benchmark: the market to read. Must carry a provider instrument — an
            unsupported market is reported from the registry and never fetched.
        as_of: the instant being described. Observations after it are excluded.
        sources: the adapters' injection points.

    Returns:
        An `ObservationSeries` identified by the instrument's own label, holding
        every usable observation at or before ``as_of``.

    Raises:
        ValueError: ``benchmark`` carries no provider instrument.
        UnknownProviderError: its provider has no adapter in this build.
        Anything in `DATA_SOURCE_ERRORS`: an ordinary source failure, which the
            caller isolates onto that market's own row.
    """
    if not isinstance(benchmark, Benchmark):
        raise TypeError(
            f"benchmark must be a Benchmark, got {type(benchmark).__name__}"
        )
    if benchmark.instrument is None:
        raise ValueError(
            f"{benchmark.benchmark_id} carries no provider instrument, so no "
            "observations can belong to it; an unsupported market is reported "
            "from the registry and never fetched"
        )
    if not isinstance(sources, MarketDataSources):
        raise TypeError(
            f"sources must be a MarketDataSources, got {type(sources).__name__}"
        )
    provider = benchmark.instrument.provider
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        known = ", ".join(sorted(_ADAPTERS))
        raise UnknownProviderError(
            f"{benchmark.benchmark_id} names provider {provider!r}, which this "
            f"build has no adapter for; it knows {known}. This is a registry "
            "defect rather than a source outage — the market will not become "
            "readable by retrying"
        )
    return adapter(benchmark, as_of=as_of, sources=sources)
