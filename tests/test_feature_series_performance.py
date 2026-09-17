"""TA Slice 5A — `compute_series()` scaling, measured rather than assumed.

`compute_series()` exists partly so a future replay does not have to recompute a
whole indicator per bar. A series implementation that is itself quadratic would
defeat that **silently**: it is invisible at a 500-bar production window and
fatal at ten thousand. Report 0047 §10.3 found exactly that shape already living
in `derive_level_crossings`, so the hazard is not hypothetical in this
repository.

**How this is measured, and why it is measured this way.** Counting operations
was tried first and does not fit: every one of these features starts by calling
``series.closed()``, which rebuilds a plain tuple, and the shared math helpers
read their inputs by slice and by iteration rather than by index — so an
instrumented sequence counts a handful of calls whatever the input size. Timing
is what actually distinguishes the shapes here.

**Timing is used for the shape, never for a threshold.** No wall-clock budget is
asserted, because a duration bound in a test suite fails on a loaded machine
rather than on a defect. What is asserted is the **growth ratio** across a
ten-fold increase in input, where linear and quadratic differ by an order of
magnitude and no plausible amount of scheduler noise can close the gap. Each
measurement is the best of several repeats, which removes the one-sided noise a
shared machine contributes.

Expected complexity, per ADR-0031:

    EMA · ATR · RSI · MACD          O(n)              one pass, recursive
    RelativeVolume · AverageVolume  O(n · lookback)   a fixed window per bar,
                                                      and lookback is a parameter
                                                      rather than a function of n
"""

from __future__ import annotations

import time

import pytest

from fmis.features.types import FeatureContext
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.macd import MovingAverageConvergenceDivergence
from fmis.features.indicators.rsi import RelativeStrengthIndex
from fmis.features.volume.statistics import AverageVolume, RelativeVolume

from tests.feature_series_helpers import series

#: The sizes the milestone brief names. 500 is the production window; 2,000 is
#: four times it, which is where a quadratic first becomes unmissable.
SIZES = (200, 500, 1000, 2000)

#: Best-of, to drop scheduler noise. Noise on a shared machine is one-sided —
#: it only ever makes a run slower — so the minimum is the closest thing to the
#: work actually performed.
REPEATS = 7

FEATURES = (
    ExponentialMovingAverage(20),
    ExponentialMovingAverage(200),
    AverageTrueRange(14),
    RelativeStrengthIndex(14),
    MovingAverageConvergenceDivergence(),
    RelativeVolume(20),
    AverageVolume(20),
)
_IDS = [feature.name for feature in FEATURES]

#: Linear growth over a 10x input is ~10x; quadratic is ~100x. Thirty sits an
#: order of magnitude clear of the quadratic and three times clear of the
#: linear, so neither a slow machine nor a fast one decides the outcome.
MAX_GROWTH_OVER_TENFOLD = 30.0


def _best_seconds(feature, size: int) -> float:
    """The fastest of ``REPEATS`` runs of ``compute_series`` over ``size`` candles.

    The series is built once and reused, so what is timed is the computation and
    not the fixture.
    """
    context = FeatureContext(primary=series(size))
    feature.compute_series(context)  # warm the interpreter, never timed
    best = float("inf")
    for _ in range(REPEATS):
        started = time.perf_counter()
        feature.compute_series(context)
        best = min(best, time.perf_counter() - started)
    return best


def _points_at(feature, size: int) -> int:
    """How many points ``feature`` emits over ``size`` candles."""
    return len(feature.compute_series(FeatureContext(primary=series(size))).points)


def _measurable_sizes(feature) -> tuple[int, ...]:
    """The sizes at which this feature is warmed up enough to time meaningfully.

    **EMA(200) is the reason this exists.** At 200 candles it emits exactly one
    point, so almost all of that run is `closed()` and price extraction and none
    of it is the recursion — and a growth ratio taken from it measures the
    warm-up, not the algorithm. A size counts as measurable once the feature has
    produced a hundred points, which is well past the fixed cost and far short of
    where any of these sizes sit.
    """
    return tuple(size for size in SIZES if _points_at(feature, size) >= 100)


@pytest.mark.parametrize("feature", FEATURES, ids=_IDS)
def test_the_cost_per_emitted_point_stays_flat_as_the_input_grows(feature) -> None:
    """**O(n), stated exactly, and the assertion that catches a quadratic.**

    A linear implementation costs the same per point whatever the input size. A
    quadratic one costs proportionally more per point as the input grows — from
    the smallest measurable size to the largest here that is a **four-fold**
    rise, against a bound of two and a half.

    Per point rather than per candle, because a feature's warm-up is a fixed cost
    that no growth rate should be charged for.
    """
    sizes = _measurable_sizes(feature)
    assert len(sizes) >= 2, (feature.name, sizes)

    per_point = {
        size: _best_seconds(feature, size) / _points_at(feature, size)
        for size in sizes
    }
    smallest = per_point[sizes[0]]
    largest = per_point[sizes[-1]]

    assert largest < 2.5 * smallest, (
        feature.name,
        {size: f"{value * 1e9:.1f} ns/point" for size, value in per_point.items()},
    )


@pytest.mark.parametrize("feature", FEATURES, ids=_IDS)
def test_the_whole_measured_range_stays_far_from_quadratic(feature) -> None:
    """End to end, over whatever range this feature is measurable across.

    Linear growth costs the input ratio; quadratic costs its square. The bound is
    three times the ratio, which sits clear of the first and below the second for
    every span these sizes produce.
    """
    sizes = _measurable_sizes(feature)
    ratio = sizes[-1] / sizes[0]
    small = _best_seconds(feature, sizes[0])
    large = _best_seconds(feature, sizes[-1])
    growth = large / small

    assert growth < 3.0 * ratio, (
        feature.name,
        f"{growth:.2f}x over {ratio:.1f}x input",
        f"{small * 1e6:.1f} us at {sizes[0]}",
        f"{large * 1e6:.1f} us at {sizes[-1]}",
    )
    assert growth < MAX_GROWTH_OVER_TENFOLD, feature.name


@pytest.mark.parametrize("feature", FEATURES, ids=_IDS)
def test_the_history_costs_about_what_the_latest_value_costs(feature) -> None:
    """Publishing the whole history is not a different algorithm.

    Every one of these features already computed its full series internally and
    kept ``[-1]``; ADR-0031 §6 makes that literal rather than incidental. So the
    series path costs the same traversal plus the points it builds, never a
    second traversal per bar — which is what the ratio here would expose.
    """
    context = FeatureContext(primary=series(SIZES[-1]))
    feature.compute(context)
    feature.compute_series(context)

    latest = float("inf")
    whole = float("inf")
    for _ in range(REPEATS):
        started = time.perf_counter()
        feature.compute(context)
        latest = min(latest, time.perf_counter() - started)
        started = time.perf_counter()
        feature.compute_series(context)
        whole = min(whole, time.perf_counter() - started)

    assert whole < 20.0 * latest, (
        feature.name,
        f"latest {latest * 1e6:.1f} us",
        f"series {whole * 1e6:.1f} us",
    )


def test_a_wider_window_costs_its_window_and_not_the_whole_history() -> None:
    """The windowed features are O(n · lookback), with lookback a parameter.

    Doubling the lookback roughly doubles the per-bar window work; it does not
    turn the traversal into a quadratic, because the window never grows with the
    input.
    """
    for narrow in (RelativeVolume(20), AverageVolume(20)):
        wide = type(narrow)(lookback=narrow.lookback * 2)
        assert _best_seconds(wide, 1000) < 6.0 * _best_seconds(narrow, 1000), (
            narrow.name
        )


def test_the_measured_timings_are_reported() -> None:
    """A wall-clock table, **reported so the milestone report can quote it**.

    The only duration asserted anywhere in this file, and it is deliberately
    loose: every series-capable feature over 2,000 closed candles, in under a
    second. A 20-symbol scan fetches three timeframes per symbol over a network,
    which is four orders of magnitude slower — so this bound can only be reached
    by an algorithmic regression, never by a slow afternoon.
    """
    lines = ["", f"compute_series over {len(FEATURES)} features:"]
    for size in SIZES:
        context = FeatureContext(primary=series(size))
        for feature in FEATURES:
            feature.compute_series(context)
        started = time.perf_counter()
        for feature in FEATURES:
            feature.compute_series(context)
        elapsed = time.perf_counter() - started
        lines.append(f"  {size:>5} closed candles: {elapsed * 1000:8.2f} ms")
    print("\n".join(lines))

    context = FeatureContext(primary=series(SIZES[-1]))
    started = time.perf_counter()
    for feature in FEATURES:
        feature.compute_series(context)
    assert time.perf_counter() - started < 1.0
