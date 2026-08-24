"""Candles in, one market's reading out. Pure, and it computes nothing itself.

    fmis.data.reduction.candle_series_to_observations   candles -> observations
    fmis.relative_value.period_return                   observations -> a move
    fmis.relative_value.realized_volatility             observations -> a number
    fmis.relative_value.pearson_correlation             two series -> one number

**Every number on the page comes from the Relative Value Engine.** This module
selects a window, hands it to a metric, and turns the result into a record. It
holds no return formula, no standard deviation and no correlation of its own —
a guard test asserts it contains no arithmetic operator at all — because a
number produced here would be a number no engine's tests could be held to.

**No second volatility engine is created.** `fmis.features.indicators.atr`
exists and is deliberately not used: ATR is an absolute range in a market's own
quote currency, so BTC's and DOGE's are not comparable, and comparability is the
only reason this page prints volatility beside other markets' at all. RVE's
`realized_volatility` — the sample standard deviation of simple returns — is
unitless and is the right primitive here. Nothing in this package reimplements
either.

**The window is taken from the end and is exact.** A horizon of `N` bars reads
the last `N + 1` closed prices. Fewer than that is reported as insufficient
rather than measured over what happened to arrive, because a *"7-day move"*
computed from four days is a different measurement wearing the same label.

**No lookahead, enforced twice.** `candle_series_to_observations` runs over
`series.closed()`, so a forming bar cannot enter; and this module then drops any
bar whose open is after the instant being described. The redundancy is
deliberate and matches `fmis.pipeline.candles`: the guarantee survives a bug in
either mechanism alone.

**Nothing here fetches, and nothing here reads a clock.** The caller supplies
the candles and the instant, which is what keeps every provider name and every
transport error on the far side of this package.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from fmis.data import CandleSeries
from fmis.data.reduction import CandleField, candle_series_to_observations
from fmis.data.observation import ObservationSeries
from fmis.market_pulse.models import (
    Benchmark,
    CoMovement,
    Horizon,
    HorizonMove,
    MarketReading,
    QuantityKind,
    VolatilityReading,
)
from fmis.relative_value import (
    MetricStatus,
    RelativeValueResult,
    pearson_correlation,
    period_return,
    realized_volatility,
)

__all__ = [
    "MOVE_METRIC",
    "VOLATILITY_METRIC",
    "CO_MOVEMENT_METRIC",
    "MOVE_MINIMUM_OBSERVATIONS",
    "VOLATILITY_MINIMUM_OBSERVATIONS",
    "CO_MOVEMENT_MINIMUM_OBSERVATIONS",
    "RATE_LIKE_MEASURE_REASON",
    "NoObservationsError",
    "observations_for",
    "measure_move",
    "measure_volatility",
    "measure_from_observations",
    "measure_market",
    "measure_co_movement",
]

#: The engine function behind every move on the page. Carried onto each record
#: so a figure traces to a tested engine rather than to this module.
MOVE_METRIC = "period_return"

#: The engine function behind every volatility figure.
VOLATILITY_METRIC = "realized_volatility"

#: The engine function behind every co-movement figure.
CO_MOVEMENT_METRIC = "pearson_correlation"

#: Why a rate-like market produces no percentage move and no realized volatility.
#:
#: **Added by Milestone BU, and it makes the milestone's central error
#: unrepresentable rather than merely unrendered.** A yield's `period_return` is
#: arithmetically computable — 4.65% to 4.69% is +0.86% — and it is the wrong
#: answer to *"what did the ten-year do"*, which is +4 basis points. BU's first
#: fix excluded yields from the orderings, and a live run showed the figure still
#: reaching the page on the market's own row, unlabelled, where a reader would
#: read it as the move. The number is therefore not produced at all: a rate-like
#: market's moves carry this reason instead of a value, so no consumer of a
#: `MarketReading` can print one by accident.
#:
#: **Realized volatility is refused for the same reason and not by extension.**
#: It is the sample standard deviation of *simple returns* — the identical ratio
#: construction — so a yield's volatility figure would be the dispersion of
#: ratios of rates, which is not the dispersion of the yield.
#:
#: `fmis.macro` states what a yield actually did, in basis points.
RATE_LIKE_MEASURE_REASON = (
    "this market is a rate, not a price: a percentage return of a yield is the "
    "ratio between two rates rather than the move a reader means, so it is not "
    "computed here. `fmits macro` states this market's move in basis points"
)

#: The Relative Value Engine's own minimum observation counts, restated here so
#: a horizon too short for a metric is caught **before** the engine is called.
#:
#: **Why restated rather than caught.** The engine raises
#: `InsufficientObservationsError` for a request that is structurally ill-formed,
#: and that is the correct behaviour: it is a caller mistake, not a fact about a
#: market. Catching it here would turn a misconfigured horizon into a row reading
#: *"unavailable"* on every market forever, which looks exactly like a data
#: outage. So the condition is detected first and reported as what it is — a
#: configuration error naming both numbers. A guard test asserts these constants
#: still match the engine's own requirements, so the two cannot drift.
MOVE_MINIMUM_OBSERVATIONS = 2
VOLATILITY_MINIMUM_OBSERVATIONS = 3
CO_MOVEMENT_MINIMUM_OBSERVATIONS = 3


class NoObservationsError(ValueError):
    """A series held no closed bar at or before the instant being described.

    A distinct type rather than a bare `ValueError` because the caller's correct
    response is specific: record the market as unavailable with this reason and
    carry on measuring every other one. A page that stopped because one market
    returned an empty window would be hostage to its least liquid member — the
    identical rule `fmis.marks.PriceUnreadableError` states one layer over.
    """


def observations_for(
    series: CandleSeries, *, as_of: datetime, series_id: str
) -> ObservationSeries:
    """The closed closes of ``series`` at or before ``as_of``, as observations.

    Args:
        series: candles for one market on one interval, forming bar included —
            it is dropped here rather than by the caller, so the exclusion has
            one implementation.
        as_of: the instant being described. A bar whose **open** is after it is
            excluded, following `fmis.marks.build_price_snapshot`'s rule for the
            identical situation: asking what the market did last Tuesday fetches
            candles that closed since, and a bar from after a moment is not that
            moment's bar.
        series_id: the identity carried onto the observations, and into every
            metric's own metadata.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`.
        NoObservationsError: nothing survived both filters. An empty window is
            not a market that did not move.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    closed = series.closed()
    kept = tuple(
        candle for candle in closed.candles if candle.timestamp <= as_of
    )
    if not kept:
        raise NoObservationsError(
            f"{series.symbol} {series.timeframe}: no closed bar at or before "
            f"{as_of.isoformat()} in a window of {len(series.candles)} bar(s); "
            "an unread market has no move rather than a move of zero"
        )
    return candle_series_to_observations(
        CandleSeries(
            symbol=closed.symbol, timeframe=closed.timeframe, candles=kept
        ),
        CandleField.CLOSE,
        series_id=series_id,
    )


def _tail(series: ObservationSeries, count: int) -> ObservationSeries:
    """The last ``count`` observations, as their own series. Never pads."""
    return ObservationSeries(
        series_id=series.series_id,
        unit=series.unit,
        frequency=series.frequency,
        timestamps=series.timestamps[-count:],
        values=series.values[-count:],
    )


def _undefined_reason(result: RelativeValueResult) -> str:
    """The engine's own undefined reason, spelled for a reader.

    The `UndefinedReason` member's value is carried verbatim so the sentence a
    page prints and the state an engine returned cannot drift apart.
    """
    return (
        f"{result.name} is mathematically undefined over this window "
        f"({result.reason.value}); this is not a reading of zero"
    )


def _short_window(
    horizon: Horizon, available: int, *, subject: str
) -> str:
    return (
        f"{subject} needs {horizon.required_observations} closed bars and this "
        f"market supplied {available}; a shorter window is a different "
        "measurement, not a smaller one"
    )


def _too_short_a_horizon(
    horizon: Horizon, minimum: int, *, subject: str, metric: str
) -> str:
    """A horizon shorter than the metric itself requires. A configuration fault.

    Worded so it cannot be mistaken for a market outage: it names the metric,
    the minimum it requires and the horizon that was configured, and says
    explicitly that no market can satisfy it.
    """
    return (
        f"{subject} cannot be measured over the {horizon.horizon_id} horizon: "
        f"{metric} requires at least {minimum} observations and that horizon "
        f"names {horizon.required_observations}. This is a configuration fault "
        "rather than a missing reading — no market could satisfy it"
    )


def measure_move(
    observations: ObservationSeries, horizon: Horizon
) -> HorizonMove:
    """One market's move over one horizon, or the stated reason there is none.

    Never raises for a short window: an insufficient history is an ordinary
    outcome for a newly listed market and is reported on the record. A structural
    failure inside the engine still propagates — it would be a defect here, not
    a fact about the market.
    """
    if not isinstance(horizon, Horizon):
        raise TypeError(f"horizon must be a Horizon, got {type(horizon).__name__}")
    available = len(observations.values)
    needed = horizon.required_observations
    if needed < MOVE_MINIMUM_OBSERVATIONS:  # pragma: no cover - unreachable
        # `Horizon` refuses fewer than one bar, so `required_observations` is
        # always at least two. Kept symmetric with the other two metrics so a
        # future horizon rule cannot make this the one path with no guard.
        return HorizonMove(
            horizon_id=horizon.horizon_id,
            bars=horizon.bars,
            value=None,
            unavailable_reason=_too_short_a_horizon(
                horizon,
                MOVE_MINIMUM_OBSERVATIONS,
                subject="the move",
                metric=MOVE_METRIC,
            ),
            metric=MOVE_METRIC,
            observation_count=available,
        )
    if available < needed:
        return HorizonMove(
            horizon_id=horizon.horizon_id,
            bars=horizon.bars,
            value=None,
            unavailable_reason=_short_window(
                horizon, available, subject=f"the {horizon.description} move"
            ),
            metric=MOVE_METRIC,
            observation_count=available,
        )
    window = _tail(observations, needed)
    result = period_return(window)
    if result.status is not MetricStatus.OK:
        return HorizonMove(
            horizon_id=horizon.horizon_id,
            bars=horizon.bars,
            value=None,
            unavailable_reason=_undefined_reason(result),
            metric=MOVE_METRIC,
            observation_count=needed,
        )
    return HorizonMove(
        horizon_id=horizon.horizon_id,
        bars=horizon.bars,
        value=result.value,
        unavailable_reason=None,
        metric=MOVE_METRIC,
        observation_count=needed,
        window_start=window.timestamps[0],
        window_end=window.timestamps[-1],
    )


def measure_volatility(
    observations: ObservationSeries, horizon: Horizon
) -> VolatilityReading:
    """Realized volatility over one horizon, or the stated reason there is none.

    The number is a sample standard deviation of simple returns and is
    **unannualized and unclassified**. `VOLATILITY_CLASSIFICATION_NOTE` is what
    the page prints instead of an adjective, and this function deliberately
    returns nothing that could be mistaken for one.
    """
    if not isinstance(horizon, Horizon):
        raise TypeError(f"horizon must be a Horizon, got {type(horizon).__name__}")
    available = len(observations.values)
    needed = horizon.required_observations
    if needed < VOLATILITY_MINIMUM_OBSERVATIONS:
        return VolatilityReading(
            value=None,
            unavailable_reason=_too_short_a_horizon(
                horizon,
                VOLATILITY_MINIMUM_OBSERVATIONS,
                subject="realized volatility",
                metric=VOLATILITY_METRIC,
            ),
            metric=VOLATILITY_METRIC,
            observation_count=available,
        )
    if available < needed:
        return VolatilityReading(
            value=None,
            unavailable_reason=_short_window(
                horizon, available, subject="realized volatility"
            ),
            metric=VOLATILITY_METRIC,
            observation_count=available,
        )
    window = _tail(observations, needed)
    result = realized_volatility(window)
    if result.status is not MetricStatus.OK:
        return VolatilityReading(
            value=None,
            unavailable_reason=_undefined_reason(result),
            metric=VOLATILITY_METRIC,
            observation_count=needed,
        )
    return VolatilityReading(
        value=result.value,
        unavailable_reason=None,
        metric=VOLATILITY_METRIC,
        observation_count=needed,
        window_start=window.timestamps[0],
        window_end=window.timestamps[-1],
    )


def _refused_move(horizon: Horizon, available: int) -> HorizonMove:
    """One horizon's move for a rate-like market: the reason, never a number."""
    return HorizonMove(
        horizon_id=horizon.horizon_id,
        bars=horizon.bars,
        value=None,
        unavailable_reason=RATE_LIKE_MEASURE_REASON,
        metric=MOVE_METRIC,
        observation_count=available,
    )


def _refused_volatility(available: int) -> VolatilityReading:
    """Realized volatility for a rate-like market: the reason, never a number."""
    return VolatilityReading(
        value=None,
        unavailable_reason=RATE_LIKE_MEASURE_REASON,
        metric=VOLATILITY_METRIC,
        observation_count=available,
    )


def measure_from_observations(
    benchmark: Benchmark,
    observations: ObservationSeries,
    *,
    source: str,
    horizons: Sequence[Horizon],
    volatility_horizon: Horizon,
) -> MarketReading:
    """One market's complete reading from an already-reduced series.

    Split out from `measure_market` so a caller that needs the observations for
    something else — the co-movement step does — can reduce the candles **once**
    and pass the result to both. Reducing twice would be correct and wasteful;
    worse, it would be two places a window could be selected differently.

    Raises:
        TypeError: ``benchmark`` is not a `Benchmark`.
        ValueError: ``benchmark`` carries no provider instrument, or the series
            is empty. An empty series here is a caller error rather than a fact
            about a market — `observations_for` is what turns an empty window
            into `NoObservationsError`, and it runs first.
    """
    if not isinstance(benchmark, Benchmark):
        raise TypeError(
            f"benchmark must be a Benchmark, got {type(benchmark).__name__}"
        )
    if benchmark.instrument is None:
        raise ValueError(
            f"{benchmark.benchmark_id} carries no provider instrument, so no "
            "candles can belong to it"
        )
    if not observations.values:
        raise ValueError(
            f"{benchmark.benchmark_id} was handed an empty observation series; "
            "an empty window is produced by observations_for as "
            "NoObservationsError and never reaches this function"
        )
    rate_like = benchmark.quantity_kind is QuantityKind.RATE_LIKE
    return MarketReading(
        benchmark=benchmark,
        source=source,
        interval=benchmark.instrument.interval,
        last_bar_open=observations.timestamps[-1],
        closed_bar_count=len(observations.values),
        moves=tuple(
            _refused_move(horizon, len(observations.values))
            if rate_like
            else measure_move(observations, horizon)
            for horizon in horizons
        ),
        volatility=(
            _refused_volatility(len(observations.values))
            if rate_like
            else measure_volatility(observations, volatility_horizon)
        ),
    )


def measure_market(
    benchmark: Benchmark,
    series: CandleSeries,
    *,
    as_of: datetime,
    source: str,
    horizons: Sequence[Horizon],
    volatility_horizon: Horizon,
) -> MarketReading:
    """One market's complete reading, straight from its candles.

    The convenience path: reduce, then measure. A caller that also needs the
    reduced series should call `observations_for` and
    `measure_from_observations` itself rather than reduce twice.

    Args:
        benchmark: the market being read. Must carry a provider instrument —
            an unsupported market has no reading by construction.
        series: that market's candles, forming bar included.
        as_of: the instant being described; bars opening after it are excluded.
        source: the provenance label carried onto the reading.
        horizons: the windows to measure, in the order they should be printed.
        volatility_horizon: the window volatility is measured over.

    Raises:
        NoObservationsError: the series held no usable closed bar.
        TypeError, ValueError: as `measure_from_observations`.
    """
    if not isinstance(benchmark, Benchmark):
        raise TypeError(
            f"benchmark must be a Benchmark, got {type(benchmark).__name__}"
        )
    if benchmark.instrument is None:
        raise ValueError(
            f"{benchmark.benchmark_id} carries no provider instrument, so no "
            "candles can belong to it"
        )
    return measure_from_observations(
        benchmark,
        observations_for(
            series, as_of=as_of, series_id=benchmark.instrument.label
        ),
        source=source,
        horizons=horizons,
        volatility_horizon=volatility_horizon,
    )


def measure_co_movement(
    subject_id: str,
    subject: ObservationSeries,
    reference_id: str,
    reference: ObservationSeries,
    horizon: Horizon,
) -> CoMovement:
    """How two markets' returns moved together over one window of closed bars.

    **The two windows must line up exactly.** The Relative Value Engine never
    aligns, and this function does not align for it: a pair whose bar opens
    differ is reported unavailable with that reason rather than intersected,
    because an intersection is a *different* window than the one the page names
    and would be printed under the wrong label.

    Never raises for a short or misaligned window — both are ordinary facts
    about a pair of markets. A structural failure from the engine over inputs
    this function already validated would be a defect here, and propagates.
    """
    if not isinstance(horizon, Horizon):
        raise TypeError(f"horizon must be a Horizon, got {type(horizon).__name__}")
    needed = horizon.required_observations
    shortest = min(len(subject.values), len(reference.values))
    if needed < CO_MOVEMENT_MINIMUM_OBSERVATIONS:
        return CoMovement(
            subject_id=subject_id,
            reference_id=reference_id,
            value=None,
            unavailable_reason=_too_short_a_horizon(
                horizon,
                CO_MOVEMENT_MINIMUM_OBSERVATIONS,
                subject="co-movement",
                metric=CO_MOVEMENT_METRIC,
            ),
            metric=CO_MOVEMENT_METRIC,
            observation_count=shortest,
        )
    if shortest < needed:
        return CoMovement(
            subject_id=subject_id,
            reference_id=reference_id,
            value=None,
            unavailable_reason=_short_window(
                horizon, shortest, subject="co-movement"
            ),
            metric=CO_MOVEMENT_METRIC,
            observation_count=shortest,
        )
    left = _tail(subject, needed)
    right = _tail(reference, needed)
    if left.timestamps != right.timestamps:
        return CoMovement(
            subject_id=subject_id,
            reference_id=reference_id,
            value=None,
            unavailable_reason=(
                "the two markets' most recent "
                f"{needed} closed bars do not cover the same instants, so they "
                "cannot be correlated; this build never intersects two windows "
                "to force a comparison, because the result would be labelled "
                "with a window it was not measured over"
            ),
            metric=CO_MOVEMENT_METRIC,
            observation_count=needed,
        )
    result = pearson_correlation(left, right)
    if result.status is not MetricStatus.OK:
        return CoMovement(
            subject_id=subject_id,
            reference_id=reference_id,
            value=None,
            unavailable_reason=_undefined_reason(result),
            metric=CO_MOVEMENT_METRIC,
            observation_count=needed,
        )
    return CoMovement(
        subject_id=subject_id,
        reference_id=reference_id,
        value=result.value,
        unavailable_reason=None,
        metric=CO_MOVEMENT_METRIC,
        observation_count=needed,
        window_start=left.timestamps[0],
        window_end=left.timestamps[-1],
    )
