"""Observations in, one frozen macro context out.

    fmis.market_pulse.measure_from_observations   observations -> a reading
    fmis.macro.rates.rate_change                  two levels   -> a yield move
    fmis.alignment.align_intersection             two series   -> shared dates
    fmis.relative_value.pearson_correlation       two series   -> one number

**Every price-like number on this page is Milestone BT's, and every alignment is
`fmis.alignment`'s.** This module writes no return formula, no standard deviation
and no correlation of its own, and it does not intersect two series by hand: it
selects windows, calls engines that already had tests over their behaviour, and
turns the results into records. The only arithmetic it owns is index arithmetic
for selecting a window, and `fmis.macro.rates` owns the one genuinely new
quantity — a yield difference.

**No second measurement path exists for price-like markets.** A macro equity
index and a crypto pair are measured by the identical function over the identical
record types; what differs is the observation cadence they were sampled at and
the horizons named over them, both of which travel on the data. That is what
makes *"the S&P moved 0.4% over 5 observations"* and *"BTC moved 2.1% over 24
bars"* the same kind of statement, computed the same way, and comparable exactly
when `fmis.macro.comparability` says so.

**Nothing here fetches and nothing here reads a clock.** The caller supplies the
observations and the instant, which is what keeps every provider name and every
transport error on the far side of this package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from fmis.alignment import align_intersection
from fmis.data.observation import ObservationSeries
from fmis.macro.comparability import (
    ComparabilityKey,
    compare_for_correlation,
)
from fmis.macro.models import (
    CrossAssetRelationship,
    MacroContextReport,
    MacroLevel,
    MacroReportError,
    RateFact,
)
from fmis.macro.rates import RateChange, rate_change
from fmis.market_pulse import (
    Benchmark,
    Horizon,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    QuantityKind,
)
from fmis.relative_value import MetricStatus, pearson_correlation

__all__ = [
    "RELATIONSHIP_METRIC",
    "RATE_CHANGE_METRIC",
    "RELATIONSHIP_MINIMUM_OBSERVATIONS",
    "macro_level",
    "comparability_key",
    "build_rate_fact",
    "relate_markets",
    "build_macro_context",
    "observations_reference",
]

#: The engine function behind every relationship figure.
RELATIONSHIP_METRIC = "pearson_correlation"

#: The function behind every yield move. Named on the record for the reason BT
#: names its metrics: a figure traces to a tested engine rather than to a page.
RATE_CHANGE_METRIC = "rate_change"

#: The Relative Value Engine's own minimum for a correlation, restated so a
#: horizon too short for it is caught **before** the engine is called. The same
#: rule and the same reasoning as `fmis.market_pulse.measure`: the engine raises
#: for a structurally ill-formed request because that is a caller mistake, and
#: turning that into a permanently unavailable row would look like a data outage.
RELATIONSHIP_MINIMUM_OBSERVATIONS = 3


def _tail(series: ObservationSeries, count: int) -> ObservationSeries:
    """The last ``count`` observations, as their own series. Never pads."""
    return ObservationSeries(
        series_id=series.series_id,
        unit=series.unit,
        frequency=series.frequency,
        timestamps=series.timestamps[-count:],
        values=series.values[-count:],
    )


def macro_level(
    benchmark: Benchmark, observations: ObservationSeries, *, source: str
) -> MacroLevel:
    """Where one market currently is, from the last observation in its window.

    Raises:
        TypeError: ``benchmark`` is not a `Benchmark`.
        MacroReportError: the series holds no observation. An empty window is
            not a level of zero, and the caller must report the market as
            unavailable rather than print one.
    """
    if not isinstance(benchmark, Benchmark):
        raise TypeError(
            f"benchmark must be a Benchmark, got {type(benchmark).__name__}"
        )
    if not observations.values:
        raise MacroReportError(
            f"{benchmark.benchmark_id} was handed an empty observation series, "
            "so it has no level; an unread market has no level rather than a "
            "level of zero"
        )
    return MacroLevel(
        benchmark_id=benchmark.benchmark_id,
        display_name=benchmark.display_name,
        value=observations.values[-1],
        unit=benchmark.quote_unit,
        quantity_kind=benchmark.quantity_kind,
        observed_at=observations.timestamps[-1],
        source=source,
    )


def comparability_key(
    benchmark: Benchmark, horizon: Horizon, *, metric: str
) -> ComparabilityKey:
    """The key describing one measurement of one market over one horizon.

    The observation interval is taken from the benchmark's **provider
    instrument** rather than from a label chosen here, so a market's declared
    cadence and the cadence its comparability is judged on cannot diverge.

    Raises:
        MacroReportError: the benchmark carries no instrument. An unsupported
            market produced no measurement, so there is nothing to compare.
    """
    if benchmark.instrument is None:
        raise MacroReportError(
            f"{benchmark.benchmark_id} carries no provider instrument, so it "
            "has no observation interval and nothing to compare"
        )
    return ComparabilityKey(
        quantity_kind=benchmark.quantity_kind,
        quote_unit=benchmark.quote_unit,
        observation_interval=benchmark.instrument.interval,
        horizon_id=horizon.horizon_id,
        metric=metric,
    )


def build_rate_fact(
    benchmark: Benchmark,
    observations: ObservationSeries,
    *,
    horizons: Sequence[Horizon],
    source: str,
) -> RateFact:
    """One yield's level and its move over each horizon, in basis points.

    A horizon the series cannot fill is recorded in `unavailable_horizons` with
    its reason rather than measured over whatever arrived — a *"21-observation
    move"* computed from nine observations is a different measurement wearing the
    same label, which is the rule `fmis.market_pulse.measure` states for a price.

    Raises:
        MacroReportError: the benchmark is not rate-like, or its series is empty.
    """
    if benchmark.quantity_kind is not QuantityKind.RATE_LIKE:
        raise MacroReportError(
            f"{benchmark.benchmark_id} is {benchmark.quantity_kind.value}, so it "
            "has no basis-point change; a rate fact describes a rate"
        )
    level = macro_level(benchmark, observations, source=source)

    changes: list[tuple[str, RateChange]] = []
    unavailable: list[tuple[str, str]] = []
    available = len(observations.values)
    for horizon in horizons:
        needed = horizon.required_observations
        if available < needed:
            unavailable.append(
                (
                    horizon.horizon_id,
                    f"the {horizon.description} move needs {needed} completed "
                    f"observations and this series supplied {available}; a "
                    "shorter window is a different measurement, not a smaller one",
                )
            )
            continue
        window = _tail(observations, needed)
        changes.append(
            (
                horizon.horizon_id,
                rate_change(window.values[0], window.values[-1]),
            )
        )
    return RateFact(
        benchmark_id=benchmark.benchmark_id,
        display_name=benchmark.display_name,
        level=level,
        changes=tuple(changes),
        unavailable_horizons=tuple(unavailable),
    )


def relate_markets(
    subject_id: str,
    subject: ObservationSeries,
    subject_key: ComparabilityKey,
    reference_id: str,
    reference: ObservationSeries,
    reference_key: ComparabilityKey,
    horizon: Horizon,
) -> CrossAssetRelationship:
    """How two markets' returns moved together over their shared observations.

    **Comparability is decided before any arithmetic runs.** A pair that is not
    comparable produces a refusal naming the components that differ, and no
    number is computed for it at all — which is what stops a plausible figure
    existing anywhere that a later change could accidentally surface it.

    **Alignment is explicit, named and reported.** Unlike
    `fmis.market_pulse.measure_co_movement`, which refuses a misaligned pair
    outright, this function intersects on shared observation dates using
    `fmis.alignment.align_intersection` and states how many observations each
    side lost. That difference is deliberate: the pulse compares markets that
    share one venue's calendar, where a mismatch means something is wrong; the
    macro page compares a market that trades seven days a week with one that
    trades five, where a mismatch is the normal case and refusing it would refuse
    every cross-asset relationship there is. The intersection is honest because
    it is *named* — the window is reported as the shared dates it actually is.

    Never raises for a short or unmeasurable window: both are ordinary facts
    about a pair of markets.
    """
    if not isinstance(horizon, Horizon):
        raise TypeError(f"horizon must be a Horizon, got {type(horizon).__name__}")

    verdict = compare_for_correlation(subject_key, reference_key)
    if not verdict.is_comparable:
        return CrossAssetRelationship(
            subject_id=subject_id,
            reference_id=reference_id,
            metric=RELATIONSHIP_METRIC,
            value=None,
            unavailable_reason=(
                f"{subject_id} and {reference_id} were not compared: "
                f"{verdict.explain()}"
            ),
            observation_count=0,
            comparability=subject_key,
            not_comparable_detail=verdict.explain(),
        )

    needed = horizon.required_observations
    if needed < RELATIONSHIP_MINIMUM_OBSERVATIONS:
        return CrossAssetRelationship(
            subject_id=subject_id,
            reference_id=reference_id,
            metric=RELATIONSHIP_METRIC,
            value=None,
            unavailable_reason=(
                f"a relationship cannot be measured over the {horizon.horizon_id} "
                f"horizon: {RELATIONSHIP_METRIC} requires at least "
                f"{RELATIONSHIP_MINIMUM_OBSERVATIONS} observations and that "
                f"horizon names {needed}. This is a configuration fault rather "
                "than a missing reading — no pair of markets could satisfy it"
            ),
            observation_count=0,
            comparability=subject_key,
        )

    aligned = align_intersection((subject, reference))
    shared = aligned.report.aligned_observation_count
    if shared < needed:
        return CrossAssetRelationship(
            subject_id=subject_id,
            reference_id=reference_id,
            metric=RELATIONSHIP_METRIC,
            value=None,
            unavailable_reason=(
                f"{subject_id} and {reference_id} share {shared} observation "
                f"date(s) and this window needs {needed}; the two series are "
                "compared only on dates both of them observe, and there are not "
                "enough of them"
            ),
            observation_count=0,
            aligned_count=shared,
            comparability=subject_key,
            subject_dropped=aligned.report.series_stats[0].dropped_count,
            reference_dropped=aligned.report.series_stats[1].dropped_count,
        )

    left = _tail(aligned.series[0], needed)
    right = _tail(aligned.series[1], needed)
    result = pearson_correlation(left, right)
    if result.status is not MetricStatus.OK:
        return CrossAssetRelationship(
            subject_id=subject_id,
            reference_id=reference_id,
            metric=RELATIONSHIP_METRIC,
            value=None,
            unavailable_reason=(
                f"{RELATIONSHIP_METRIC} is mathematically undefined over this "
                f"window ({result.reason.value}); this is not a reading of zero"
            ),
            observation_count=needed,
            aligned_count=shared,
            comparability=subject_key,
            subject_dropped=aligned.report.series_stats[0].dropped_count,
            reference_dropped=aligned.report.series_stats[1].dropped_count,
        )
    return CrossAssetRelationship(
        subject_id=subject_id,
        reference_id=reference_id,
        metric=RELATIONSHIP_METRIC,
        value=result.value,
        unavailable_reason=None,
        observation_count=needed,
        aligned_count=shared,
        comparability=subject_key,
        window_start=left.timestamps[0],
        window_end=left.timestamps[-1],
        subject_dropped=aligned.report.series_stats[0].dropped_count,
        reference_dropped=aligned.report.series_stats[1].dropped_count,
    )


def build_macro_context(
    *,
    as_of: datetime,
    universe: MarketUniverse,
    readings: Sequence[MarketReading],
    unavailable: Sequence[MarketUnavailable],
    levels: Sequence[MacroLevel],
    rate_facts: Sequence[RateFact],
    horizons: Sequence[Horizon],
    relationships: Sequence[CrossAssetRelationship] = (),
    relationship_reference: str | None = None,
) -> MacroContextReport:
    """Assemble one immutable macro context from measured facts and stated failures.

    Adds no information: every number in the result was already on a record
    before this function ran. It exists so the report's invariants — every market
    accounted for exactly once, no reading from the future, no relationship
    without a named reference — are proven in one place.

    Raises:
        MacroReportError: the universe and the results disagree about which
            markets exist, or a relationship names a subject this report does not
            read.
    """
    read_ids = {reading.benchmark_id for reading in readings}
    for relationship in relationships:
        if relationship.subject_id not in read_ids:
            raise MacroReportError(
                f"a relationship names {relationship.subject_id!r} as its "
                "subject, and this report holds no reading for it; a "
                "correlation of a market the page did not read cannot be traced "
                "to anything"
            )
    return MacroContextReport(
        as_of=as_of,
        universe=universe,
        levels=tuple(levels),
        readings=tuple(readings),
        unavailable=tuple(unavailable),
        rate_facts=tuple(rate_facts),
        relationships=tuple(relationships),
        horizons=tuple(horizons),
        relationship_reference=relationship_reference,
    )


def observations_reference(
    observations: Mapping[str, ObservationSeries], order: Sequence[str]
) -> str | None:
    """The first market in ``order`` that has observations, or `None`.

    A stated choice rather than an emergent one, and the page prints it — the
    same rule `fmis.market_pulse.pulse` follows for its own reference.
    """
    for benchmark_id in order:
        if benchmark_id in observations:
            return benchmark_id
    return None
