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
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    Horizon,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    build_market_pulse,
    horizons_for,
    measure_from_observations,
)
from fmis.pipeline.market_data import (
    DATA_SOURCE_ERRORS,
    MarketDataSources,
    observations_for_benchmark,
)
from fmis.providers.binance import Transport

__all__ = ["run_market_pulse"]


def _declared_horizons(universe: MarketUniverse) -> tuple[Horizon, ...]:
    """Every horizon any market in ``universe`` is measured over, in first-seen order.

    The page declares the union rather than one family, because Milestone BU made
    the universe span two cadences and a market measured over a horizon the page
    did not declare would produce an ordering nobody could reconstruct. Order is
    the universe's, so the declared set is a function of the configuration rather
    than of a set's iteration order.
    """
    declared: list[Horizon] = []
    seen: set[str] = set()
    for benchmark in universe.supported:
        family, _, _ = horizons_for(benchmark)
        for horizon in family:
            if horizon.horizon_id not in seen:
                seen.add(horizon.horizon_id)
                declared.append(horizon)
    return tuple(declared)


#: Distinguishes *"the caller said nothing"* from *"the caller said `None`"*.
#: `co_movement_horizon=None` is a request to omit the cross-asset section, and
#: omitting the argument is a request to pick the window from the reference
#: market's own cadence — two different instructions that `None` alone cannot
#: tell apart.
_UNSET: object = object()


def run_market_pulse(
    *,
    as_of: datetime,
    universe: MarketUniverse = DEFAULT_PULSE_UNIVERSE,
    horizons: Sequence[Horizon] | None = None,
    volatility_horizon: Horizon | None = None,
    co_movement_horizon: Horizon | None | object = _UNSET,
    limit: int | None = None,
    sources: MarketDataSources | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> MarketPulse:
    """Fetch every supported market in ``universe`` and assemble one pulse.

    **Each market is measured over the horizons its own cadence names.** An
    hourly crypto series and a daily macro series are measured over different
    windows with different ids, chosen by `fmis.market_pulse.horizons_for`, so
    the page can hold both without ever putting a week and eight months under one
    label. The pulse declares the union of the families present.

    Args:
        as_of: the instant the page describes. Supplied rather than read, so a
            run is reproducible; the CLI is where the clock lives.
        universe: the stated scope. Its unsupported members are reported without
            being fetched.
        horizons: override the per-market horizon families with one set applied
            to every market. Omitted, each market is measured over the family its
            own cadence names, which is the production path. Supplying one is for
            a caller that wants a specific window from every market and accepts
            that a shared label then spans different durations.
        volatility_horizon: likewise, for the volatility window.
        co_movement_horizon: the window co-movement is measured over. Omitted, it
            is the reference market's own cadence's window; `None` omits the
            cross-asset section entirely rather than filling it with absences.
        limit: candles requested per crypto market. Omitted, `CANDLE_LIMIT`.
        sources: the adapters' injection points, as one record. Defaults to real
            transports for every provider.
        transport, clock, base_url: Milestone BT's Binance-only injection points,
            kept so every existing caller and test continues to work unchanged.
            They are folded into ``sources``; supplying both a populated
            ``sources`` and one of these is refused rather than silently
            resolved, because which one won would be invisible in the output.

    Returns:
        A `MarketPulse` in which every supported benchmark appears exactly once,
        as a reading or as a stated failure.

    Raises:
        ValueError: both ``sources`` and a legacy injection point were supplied.
        Anything outside `DATA_SOURCE_ERRORS`. Those families become
        `MarketUnavailable` rows; an internal defect propagates.
    """
    legacy = (transport, clock, base_url)
    if sources is not None and any(entry is not None for entry in legacy):
        raise ValueError(
            "run_market_pulse was given both a MarketDataSources and one of the "
            "individual transport/clock/base_url arguments; supply one or the "
            "other, because which of the two won would not be visible in the "
            "page that came out"
        )
    if sources is None:
        sources = MarketDataSources(
            binance_transport=transport,
            binance_base_url=base_url,
            clock=clock,
            candle_limit=limit,
        )

    readings: list[MarketReading] = []
    failures: list[MarketUnavailable] = []
    observations: dict[str, ObservationSeries] = {}
    declared: list[Horizon] = []
    seen: set[str] = set()
    for benchmark in universe.supported:
        instrument = benchmark.instrument
        try:
            family, volatility, _ = horizons_for(benchmark)
            if horizons is not None:
                family = tuple(horizons)
            if volatility_horizon is not None:
                volatility = volatility_horizon
            # Read once, here, and handed to both the reading and the
            # co-movement step. Two reads would be two requests for one fact,
            # and two places a window could be selected differently.
            reduced = observations_for_benchmark(
                benchmark, as_of=as_of, sources=sources
            )
            reading = measure_from_observations(
                benchmark,
                reduced,
                source=instrument.provider,
                horizons=family,
                volatility_horizon=volatility,
            )
        except DATA_SOURCE_ERRORS as error:
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
        for horizon in family:
            if horizon.horizon_id not in seen:
                seen.add(horizon.horizon_id)
                declared.append(horizon)

    window: Horizon | None
    if co_movement_horizon is _UNSET:
        # The reference is the first market read, and the co-movement window is
        # the one *its* cadence names — the section compares like with like, and
        # `build_market_pulse` keeps other cadences out of it.
        window = horizons_for(readings[0].benchmark)[2] if readings else None
    else:
        window = co_movement_horizon
    return build_market_pulse(
        as_of=as_of,
        universe=universe,
        readings=readings,
        unavailable=failures,
        horizons=tuple(declared) if declared else _declared_horizons(universe),
        observations=None if window is None else observations,
        co_movement_horizon=window,
    )
