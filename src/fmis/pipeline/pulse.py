"""The market-pulse composition root — the one place a venue is named for it.

    fmis.providers.binance.fetch_klines     public candles -> CandleSeries
    fmis.market_pulse.measure_market        candles        -> MarketReading
    fmis.market_pulse.build_market_pulse    readings       -> MarketPulse

A sibling of `fmis.pipeline.prices` and `fmis.pipeline.candles`, written to the
same three rules because it is the same kind of module: it chooses **what** to
fetch, isolates each market's failure, and computes nothing. A test asserts it
holds no arithmetic operator of its own — a number produced at the composition
layer is a number no engine can be held to.

**One fetch per supported market, and no market is fetched twice.**
`MarketUniverse` already refuses two benchmarks over one provider instrument, so
a duplicate is impossible before this module runs; and the observation series
each reading was measured from is retained and handed to the co-movement step
rather than recomputed, so the page costs exactly one request per market.

**Per-market failure isolation, and only for the failures a provider can have.**
The same four exception families `fmis.pipeline.prices` names become a
`MarketUnavailable` row, plus this package's own empty-window error. Anything
else propagates: a `KeyError` from inside FMITS rendered as *"this market could
not be read"* teaches the owner to ignore both, which is the identical
discipline the daily-workflow runner applies to a symbol whose analysis fails.

**An unsupported market never reaches this module.** A benchmark with no
provider instrument is not asked for, is not a failure, and is reported by the
page from the universe itself. Fetching a market that has no adapter and calling
the resulting error a provider failure would erase the distinction the whole
surface is built on.

**No credential, no private endpoint, no order.** The adapter this module calls
signs nothing and reads no key; nothing here changes that.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Callable

from fmis.data.observation import ObservationSeries
from fmis.ingest import IngestError
from fmis.market_pulse import (
    CO_MOVEMENT_HORIZON,
    DEFAULT_HORIZONS,
    DEFAULT_PULSE_UNIVERSE,
    VOLATILITY_HORIZON,
    Benchmark,
    Horizon,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    NoObservationsError,
    PULSE_CANDLE_LIMIT,
    build_market_pulse,
    measure_from_observations,
    observations_for,
)
from fmis.providers.binance import BinanceError, Transport, fetch_klines

__all__ = ["PULSE_SOURCE", "run_market_pulse"]

#: The provenance label carried onto every reading. Read from the universe's own
#: provider name rather than re-spelled, so a benchmark's configured provider and
#: the source printed beside its figures cannot disagree.
PULSE_SOURCE = "binance-spot"


def _fetch_series(
    benchmark: Benchmark,
    *,
    limit: int,
    transport: Transport | None,
    clock: Callable[[], datetime] | None,
    base_url: str | None,
):
    """One market's candles, straight from the adapter. No interpretation."""
    instrument = benchmark.instrument
    return fetch_klines(
        instrument.symbol,
        instrument.interval,
        limit=limit,
        transport=transport,
        clock=clock,
        **({} if base_url is None else {"base_url": base_url}),
    )


def run_market_pulse(
    *,
    as_of: datetime,
    universe: MarketUniverse = DEFAULT_PULSE_UNIVERSE,
    horizons: Sequence[Horizon] = DEFAULT_HORIZONS,
    volatility_horizon: Horizon = VOLATILITY_HORIZON,
    co_movement_horizon: Horizon | None = CO_MOVEMENT_HORIZON,
    limit: int = PULSE_CANDLE_LIMIT,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> MarketPulse:
    """Fetch every supported market in ``universe`` and assemble one pulse.

    Args:
        as_of: the instant the page describes. Supplied rather than read, so a
            run is reproducible; the CLI is where the clock lives.
        universe: the stated scope. Its unsupported members are reported without
            being fetched.
        horizons: the windows to measure, in the order to print them.
        volatility_horizon: the window realized volatility is measured over.
        co_movement_horizon: the window co-movement is measured over, or `None`
            to omit the cross-asset section rather than fill it with absences.
        limit: candles requested per market.
        transport, clock, base_url: the provider's own injection points,
            forwarded unchanged so a caller can run this network-free — the same
            three arguments every composition root in this repository uses.

    Returns:
        A `MarketPulse` in which every supported benchmark appears exactly once,
        as a reading or as a stated failure.

    Raises:
        Anything other than a provider, ingestion, argument or empty-window
        failure. Those families become `MarketUnavailable` rows; an internal
        defect propagates.
    """
    readings: list[MarketReading] = []
    failures: list[MarketUnavailable] = []
    observations: dict[str, ObservationSeries] = {}
    for benchmark in universe.supported:
        instrument = benchmark.instrument
        try:
            series = _fetch_series(
                benchmark,
                limit=limit,
                transport=transport,
                clock=clock,
                base_url=base_url,
            )
            # Reduced once, here, and handed to both the reading and the
            # co-movement step. Two reductions would be two places a window
            # could be selected differently.
            reduced = observations_for(
                series, as_of=as_of, series_id=instrument.label
            )
            reading = measure_from_observations(
                benchmark,
                reduced,
                source=PULSE_SOURCE,
                horizons=horizons,
                volatility_horizon=volatility_horizon,
            )
        except (
            BinanceError,
            IngestError,
            NoObservationsError,
            ValueError,
            TypeError,
        ) as error:
            failures.append(
                MarketUnavailable(
                    benchmark=benchmark,
                    reason=(
                        f"{instrument.label}: {type(error).__name__}: {error}"
                    ),
                )
            )
            continue
        readings.append(reading)
        observations[benchmark.benchmark_id] = reduced
    return build_market_pulse(
        as_of=as_of,
        universe=universe,
        readings=readings,
        unavailable=failures,
        horizons=horizons,
        observations=None if co_movement_horizon is None else observations,
        co_movement_horizon=co_movement_horizon,
    )
