"""The macro composition root — the one place the macro page's sources are chosen.

    fmis.pipeline.market_data           benchmark    -> observations
    fmis.market_pulse.measure           observations -> a reading
    fmis.macro.context                  observations -> levels, rates, relations
    fmis.macro.build_macro_context      facts        -> one frozen report

A sibling of `fmis.pipeline.pulse`, written to the same three rules because it is
the same kind of module: it chooses **what** to read, isolates each market's
failure, and computes nothing itself.

**One read per market, and no market is read twice.** The observation series each
reading was measured from is retained and handed to the level, the rate fact and
the relationship step, so the page costs exactly one request per market plus one
for the cross-asset reference. Reading a market again for each metric would be
correct and wasteful; worse, it would be three places a window could be selected
differently.

**The cross-asset reference is fetched at the macro cadence, on purpose.** The
question *"how does Bitcoin compare with these markets"* cannot be answered from
an hourly series: an hourly bar and a daily observation share no instants, and a
correlation between them is not a number this build will produce. So the
reference is read as **daily** candles and correlated against daily macro
observations on the dates both of them have — which is a real comparison, stated
with the alignment it required. That is one additional request, and it buys the
only genuinely cross-asset section on the page.

**Per-market failure isolation, and only for the failures a source can have.**
The families in `DATA_SOURCE_ERRORS` become an unavailable row. Anything else
propagates: a `KeyError` from inside FMITS rendered as *"this market could not be
read"* teaches the owner to ignore both.

**An unsupported market never reaches a source.** A benchmark with no instrument
is not asked for, is not a failure, and is reported by the page from the registry
itself.
"""

from __future__ import annotations

from datetime import datetime

from fmis.data.observation import ObservationSeries
from fmis.macro import (
    RELATIONSHIP_METRIC,
    CrossAssetRelationship,
    MacroContextReport,
    MacroLevel,
    RateFact,
    build_macro_context,
    build_rate_fact,
    comparability_key,
    macro_level,
    relate_markets,
)
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    MACRO_BENCHMARK_IDS,
    MACRO_INTERVAL,
    Benchmark,
    Horizon,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    ProviderInstrument,
    QuantityKind,
    horizons_for,
    measure_from_observations,
    universe_subset,
)
from fmis.pipeline.market_data import (
    DATA_SOURCE_ERRORS,
    MarketDataSources,
    observations_for_benchmark,
)

__all__ = [
    "MACRO_UNIVERSE_NAME",
    "CROSS_ASSET_REFERENCE_ID",
    "macro_universe",
    "run_macro_context",
]

#: The name the macro page prints as its stated scope.
MACRO_UNIVERSE_NAME = "macro"

#: The market every relationship on the page is measured against.
#:
#: **A stated choice, printed on the page, never inferred from the data.** It is
#: Bitcoin because the owner's other surfaces are crypto-first and *"how does
#: this move with what I actually hold"* is the question the section exists to
#: answer. It is read at the macro cadence rather than reused from the pulse: see
#: this module's docstring for why an hourly series cannot answer it.
CROSS_ASSET_REFERENCE_ID = "BTC"


def macro_universe(
    universe: MarketUniverse = DEFAULT_PULSE_UNIVERSE,
) -> MarketUniverse:
    """The macro markets, in registry order, as their own stated scope.

    A projection of the one registry rather than a second list of markets, so a
    market added there appears here with no second edit — and the dark ones come
    with it, because *"which of these can this system not tell me about"* is one
    of the questions this page answers.
    """
    return universe_subset(
        universe, MACRO_BENCHMARK_IDS, name=MACRO_UNIVERSE_NAME
    )


def _reference_benchmark(universe: MarketUniverse) -> Benchmark | None:
    """The cross-asset reference, re-declared at the macro cadence.

    Built from the registry's own entry so its display name, quote unit and
    quantity kind stay in one place, with the interval and horizon family
    swapped for the macro ones. Returns `None` when the registry holds no such
    market, which makes the relationships section absent rather than fatal.
    """
    entry = universe.benchmark_for(CROSS_ASSET_REFERENCE_ID)
    if entry is None or entry.instrument is None:
        return None
    return Benchmark(
        benchmark_id=entry.benchmark_id,
        display_name=entry.display_name,
        category=entry.category,
        schedule=entry.schedule,
        quote_unit=entry.quote_unit,
        instrument=ProviderInstrument(
            provider=entry.instrument.provider,
            symbol=entry.instrument.symbol,
            interval=MACRO_INTERVAL,
        ),
        quantity_kind=entry.quantity_kind,
        freshness_policy=entry.freshness_policy,
    )


def run_macro_context(
    *,
    as_of: datetime,
    universe: MarketUniverse | None = None,
    reference_universe: MarketUniverse = DEFAULT_PULSE_UNIVERSE,
    sources: MarketDataSources | None = None,
    with_relationships: bool = True,
) -> MacroContextReport:
    """Read every supported macro market and assemble one context report.

    Args:
        as_of: the instant the page describes. Supplied rather than read, so a
            run is reproducible; the CLI is where the clock lives.
        universe: the stated scope. Defaults to the macro projection of the
            registry. Its unsupported members are reported without being read.
        reference_universe: where the cross-asset reference is looked up. Kept
            separate because the reference is deliberately **not** a member of
            the macro scope — it is the thing the macro markets are compared
            against, and putting it in the scope would make it a macro market.
        sources: the adapters' injection points. Defaults to real transports.
        with_relationships: whether to measure the cross-asset section at all.
            `False` omits it, and omits the reference's request with it.

    Returns:
        A `MacroContextReport` in which every supported benchmark appears exactly
        once, as a reading or as a stated failure.

    Raises:
        Anything outside `DATA_SOURCE_ERRORS`. Those families become unavailable
        rows; an internal defect propagates.
    """
    scope = macro_universe() if universe is None else universe
    if sources is None:
        sources = MarketDataSources()

    readings: list[MarketReading] = []
    failures: list[MarketUnavailable] = []
    levels: list[MacroLevel] = []
    rate_facts: list[RateFact] = []
    observations: dict[str, ObservationSeries] = {}
    declared: list[Horizon] = []
    seen_horizons: set[str] = set()

    for benchmark in scope.supported:
        instrument = benchmark.instrument
        try:
            family, volatility_horizon, _ = horizons_for(benchmark)
            reduced = observations_for_benchmark(
                benchmark, as_of=as_of, sources=sources
            )
            reading = measure_from_observations(
                benchmark,
                reduced,
                source=instrument.provider,
                horizons=family,
                volatility_horizon=volatility_horizon,
            )
            level = macro_level(benchmark, reduced, source=instrument.label)
            fact = (
                build_rate_fact(
                    benchmark, reduced, horizons=family, source=instrument.label
                )
                if benchmark.quantity_kind is QuantityKind.RATE_LIKE
                else None
            )
        except DATA_SOURCE_ERRORS as error:
            failures.append(
                MarketUnavailable(
                    benchmark=benchmark,
                    reason=f"{instrument.label}: {type(error).__name__}: {error}",
                )
            )
            continue
        readings.append(reading)
        levels.append(level)
        if fact is not None:
            rate_facts.append(fact)
        observations[benchmark.benchmark_id] = reduced
        for horizon in family:
            if horizon.horizon_id not in seen_horizons:
                seen_horizons.add(horizon.horizon_id)
                declared.append(horizon)

    relationships: list[CrossAssetRelationship] = []
    reference_id: str | None = None
    if with_relationships and readings:
        reference = _reference_benchmark(reference_universe)
        if reference is not None:
            try:
                reference_series = observations_for_benchmark(
                    reference, as_of=as_of, sources=sources
                )
            except DATA_SOURCE_ERRORS:
                # The reference failed. The section is omitted rather than
                # filled with one identical failure per market — the same fact
                # repeated five times is not five facts, and the markets
                # themselves were read successfully.
                reference_series = None
            if reference_series is not None:
                reference_id = reference.benchmark_id
                _, _, relationship_horizon = horizons_for(reference)
                reference_key = comparability_key(
                    reference, relationship_horizon, metric=RELATIONSHIP_METRIC
                )
                for reading in readings:
                    benchmark = reading.benchmark
                    relationships.append(
                        relate_markets(
                            benchmark.benchmark_id,
                            observations[benchmark.benchmark_id],
                            comparability_key(
                                benchmark,
                                relationship_horizon,
                                metric=RELATIONSHIP_METRIC,
                            ),
                            reference_id,
                            reference_series,
                            reference_key,
                            relationship_horizon,
                        )
                    )

    return build_macro_context(
        as_of=as_of,
        universe=scope,
        readings=readings,
        unavailable=failures,
        levels=levels,
        rate_facts=rate_facts,
        horizons=tuple(declared),
        relationships=tuple(relationships),
        relationship_reference=reference_id,
    )
