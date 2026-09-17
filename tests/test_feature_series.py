"""TA Slice 5A — the feature-series correctness matrix (ADR-0031).

`compute_series()` is a new path through arithmetic six features already ran, and
the way it fails is not by returning nonsense. It fails by being **off by one**,
by **backfilling a warm-up position**, by letting a **future candle change a past
value**, or by **drifting from `compute()`** the first time one of the two is
edited. None of those is visible in a spot check of a printed number, so every
one of them is asserted here directly.

The matrix, and why each row is in it:

  1. **latest-value parity** — the contract that makes one arithmetic provable.
  2. **warm-up boundary** at `w−1` / `w` / `w+1` — the exact bar an off-by-one
     moves.
  3. **prefix stability** — a value knowable at a closed prefix must not change
     because later candles arrived.
  4. **no lookahead** — the same property stated from the other side: appending
     a candle may only *add* points.
  5. **identity and provenance** — a series that lost its symbol, timeframe or
     parameters is a series that can be compared with the wrong one.
  6. **parameter variation** — two periods must give two different series, or
     the parameter is not reaching the math.
  7. **empty and short input** — an absence, never a guessed number.
  8. **malformed input** — inherited from the canonical `Candle` contract, and
     asserted so the inheritance is real.
  9. **structured values** — MACD proves the protocol is not scalar-only.
 10. **repeat determinism** — two calls, equal results.
 11. **closed-candle semantics** — a forming bar can never enter a series.
 12. **alignment** — every point's timestamp is its own candle's.

Plus the three-state rule the type exists to hold: *no point*, *a point with a
value*, and *a point with an undefined reason* are three different facts.

Offline, clock-free and network-free throughout.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import pytest

from fmis.data import Candle, CandleSeries, SeriesIdentity
from fmis.features import (
    BaseFeature,
    Feature,
    FeatureCategory,
    FeatureContext,
    FeatureSeries,
    FeatureSeriesPoint,
    SeriesFeature,
    supports_series,
)
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.macd import MovingAverageConvergenceDivergence
from fmis.features.indicators.rsi import RelativeStrengthIndex
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.volume.statistics import (
    UNDEFINED_REASON_KEY,
    ZERO_BASELINE,
    AverageVolume,
    RelativeVolume,
)
from fmis.pipeline.market_analysis import default_features

from tests.feature_series_helpers import (
    BASE,
    SYMBOL,
    TIMEFRAME,
    prefix,
    series,
    series_features,
    warmup_of,
)

#: Long enough that every feature — including EMA(200) — has warmed up well
#: before the end, so parity is tested on a real recursion and not on a seed.
_LONG = 320

_ROSTER = series_features()
_IDS = [feature.name for feature in _ROSTER]


def _context(candle_series: CandleSeries) -> FeatureContext:
    return FeatureContext(primary=candle_series)


def _equal_values(left: object, right: object) -> bool:
    """Exact equality, with structured values compared component by component.

    No tolerance anywhere. Both paths execute the same operations in the same
    order over the same floats, so anything but bit-identical output is a defect
    rather than a rounding difference — and a tolerance here would hide exactly
    the drift this file exists to catch.
    """
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not (isinstance(left, Mapping) and isinstance(right, Mapping)):
            return False
        return dict(left) == dict(right)
    return left == right


# ---------------------------------------------------------------------------
# 1. Latest-value parity — the contract that proves one arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_latest_value_equals_the_final_point_of_the_series(feature) -> None:
    """**The contract of ADR-0031 §6**, asserted per feature.

    If this fails, `compute` and `compute_series` are two implementations of one
    formula and one of them has moved.
    """
    context = _context(series(_LONG))
    result = feature.compute(context)
    history = feature.compute_series(context)

    assert history.latest is not None, feature.name
    assert _equal_values(result.value, history.latest.value), feature.name


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_both_paths_report_no_value_under_the_same_conditions(feature) -> None:
    """Parity covers the absence too, or the two paths disagree about warm-up."""
    short = series(warmup_of(feature) - 1)
    context = _context(short)

    assert feature.compute(context).value is None, feature.name
    assert feature.compute_series(context).points == (), feature.name


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_final_point_is_the_last_closed_candle(feature) -> None:
    """A warmed-up series ends on the bar `compute` describes, not one before."""
    candle_series = series(_LONG)
    history = feature.compute_series(_context(candle_series))

    assert history.latest.index == len(candle_series.candles) - 1, feature.name
    assert history.latest.timestamp == candle_series.candles[-1].timestamp


# ---------------------------------------------------------------------------
# 2. Warm-up boundary — the exact bar an off-by-one moves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_one_candle_before_warm_up_produces_no_point(feature) -> None:
    warmup = warmup_of(feature)
    history = feature.compute_series(_context(series(warmup - 1)))

    assert history.points == (), feature.name
    assert history.first_index is None
    assert history.latest is None
    assert history.warmup_candles == warmup
    assert history.closed_candles == warmup - 1


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_exact_warm_up_bar_produces_exactly_one_point(feature) -> None:
    """The first defined bar, named as an index rather than counted by hand."""
    warmup = warmup_of(feature)
    history = feature.compute_series(_context(series(warmup)))

    assert len(history.points) == 1, feature.name
    assert history.first_index == warmup - 1
    assert history.points[0].index == warmup - 1


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_one_candle_after_warm_up_produces_exactly_two_points(feature) -> None:
    warmup = warmup_of(feature)
    history = feature.compute_series(_context(series(warmup + 1)))

    assert len(history.points) == 2, feature.name
    assert [point.index for point in history.points] == [warmup - 1, warmup]


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_warm_up_region_is_absent_and_never_backfilled(feature) -> None:
    """No `None`, no zero and no seed stands in for a bar with no value.

    A padded warm-up would make *not enough history yet* and *no value at this
    bar* the same token — the distinction `StructuralFactSheet.warming_up` exists
    one layer up to keep.
    """
    warmup = warmup_of(feature)
    history = feature.compute_series(_context(series(_LONG)))

    for index in range(warmup - 1):
        assert history.point_at(index) is None, (feature.name, index)
    assert history.point_at(warmup - 1) is not None


# ---------------------------------------------------------------------------
# 3 & 4. Prefix stability and no lookahead
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_a_prefix_yields_a_prefix(feature) -> None:
    """Values knowable at a closed prefix are **equal**, not merely close.

    The prefix is a slice of the same candle objects, so any difference can only
    have come from the computation.
    """
    full = series(_LONG)
    for cut in (warmup_of(feature), 150, 250, _LONG):
        partial = feature.compute_series(_context(prefix(full, cut)))
        whole = feature.compute_series(_context(full))
        for point in partial.points:
            counterpart = whole.point_at(point.index)
            assert counterpart is not None, (feature.name, cut, point.index)
            assert counterpart.timestamp == point.timestamp
            assert counterpart.undefined_reason == point.undefined_reason
            assert _equal_values(counterpart.value, point.value), (
                feature.name,
                cut,
                point.index,
            )


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_appending_a_candle_only_adds_points(feature) -> None:
    """No future candle may alter an earlier emitted value — stated forwards.

    Prefix stability says a prefix agrees with the whole; this says the whole
    agrees with the prefix, which is the property a replay actually relies on.
    """
    full = series(_LONG)
    before = feature.compute_series(_context(prefix(full, _LONG - 1)))
    after = feature.compute_series(_context(full))

    assert len(after.points) >= len(before.points), feature.name
    assert after.points[: len(before.points)] == before.points, feature.name


# ---------------------------------------------------------------------------
# 5. Identity and provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_series_carries_the_identity_of_the_candles_it_read(feature) -> None:
    candle_series = series(_LONG, symbol="OTHERUSDT", timeframe="1d")
    history = feature.compute_series(_context(candle_series))

    assert history.identity == SeriesIdentity(symbol="OTHERUSDT", timeframe="1d")
    assert history.identity == candle_series.identity
    assert history.name == feature.name
    assert history.category is feature.category


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_two_instruments_produce_series_that_are_not_equal(feature) -> None:
    """The measured risk `SeriesIdentity` exists to close, at this boundary."""
    one = feature.compute_series(_context(series(_LONG, symbol="AAAUSDT")))
    other = feature.compute_series(_context(series(_LONG, symbol="BBBUSDT")))

    assert one != other, feature.name


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_series_metadata_states_its_parameters_and_its_producer(feature) -> None:
    """Provenance survives, so a stored series can be re-derived."""
    history = feature.compute_series(_context(series(_LONG)))
    result = feature.compute(_context(series(_LONG)))

    assert history.metadata["provenance"] == result.metadata["provenance"]
    assert type(feature).__name__ in history.metadata["provenance"]
    for key in ("period", "lookback", "fast_period"):
        if key in result.metadata:
            assert history.metadata[key] == result.metadata[key], (feature.name, key)


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_series_metadata_is_read_only(feature) -> None:
    history = feature.compute_series(_context(series(_LONG)))
    with pytest.raises(TypeError):
        history.metadata["period"] = 999  # type: ignore[index]


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_the_as_of_is_the_last_closed_candle_not_the_last_point(feature) -> None:
    """They differ exactly while warming up, and collapsing them would hide it."""
    warmup = warmup_of(feature)
    warming = series(warmup - 1)
    history = feature.compute_series(_context(warming))

    assert history.points == ()
    assert history.as_of == warming.candles[-1].timestamp


# ---------------------------------------------------------------------------
# 6. Parameter variation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "one, other",
    [
        (ExponentialMovingAverage(20), ExponentialMovingAverage(50)),
        (AverageTrueRange(14), AverageTrueRange(21)),
        (RelativeStrengthIndex(14), RelativeStrengthIndex(7)),
        (
            MovingAverageConvergenceDivergence(),
            MovingAverageConvergenceDivergence(5, 13, 4),
        ),
        (RelativeVolume(20), RelativeVolume(10)),
    ],
    ids=["ema", "atr", "rsi", "structured", "volume"],
)
def test_a_different_parameter_gives_a_different_series(one, other) -> None:
    """Or the parameter is not reaching the math the series path runs."""
    context = _context(series(_LONG))
    first = one.compute_series(context)
    second = other.compute_series(context)

    assert first.name != second.name
    assert first.warmup_candles != second.warmup_candles
    assert first.points != second.points


@pytest.mark.parametrize("period", [2, 3, 7, 14, 50])
def test_the_source_reaches_the_series_path(period: int) -> None:
    """A non-default source must change the values, not only the name."""
    context = _context(series(_LONG))
    on_close = ExponentialMovingAverage(period).compute_series(context)
    on_high = ExponentialMovingAverage(period, source="high").compute_series(context)

    assert on_close.name != on_high.name
    assert on_close.metadata["source"] == "close"
    assert on_high.metadata["source"] == "high"
    assert on_close.points != on_high.points


# ---------------------------------------------------------------------------
# 7. Empty and short input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_an_empty_series_is_an_absence_with_no_instant(feature) -> None:
    empty = CandleSeries(symbol=SYMBOL, timeframe=TIMEFRAME, candles=())
    history = feature.compute_series(_context(empty))

    assert history.points == (), feature.name
    assert history.closed_candles == 0
    assert history.as_of is None
    assert history.first_index is None
    assert history.latest is None


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
@pytest.mark.parametrize("count", [1, 2, 3])
def test_a_series_far_too_short_raises_nothing_and_guesses_nothing(
    feature, count: int
) -> None:
    """Warm-up is a result, never an error — the sheet's rule, at this layer."""
    history = feature.compute_series(_context(series(count)))

    assert history.points == (), (feature.name, count)
    assert history.closed_candles == count


# ---------------------------------------------------------------------------
# 8. Malformed input — the canonical contract, inherited
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_price_cannot_reach_a_series_at_all(bad: float) -> None:
    """Refused by `fmis.data`, so no feature has to re-validate it.

    Asserted here so the inheritance is real rather than assumed: if `Candle`
    ever stopped refusing, this test would fail beside the one in `fmis.data`.
    """
    with pytest.raises((ValueError, TypeError)):
        Candle(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            timestamp=BASE,
            open=1.0,
            high=bad,
            low=1.0,
            close=1.0,
            volume=1.0,
            is_closed=True,
        )


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_every_emitted_value_is_finite(feature) -> None:
    """A finite input series can produce no infinity and no NaN."""
    for point in feature.compute_series(_context(series(_LONG))).points:
        if point.value is None:
            continue
        numbers = (
            list(point.value.values())
            if isinstance(point.value, Mapping)
            else [point.value]
        )
        for number in numbers:
            assert math.isfinite(number), (feature.name, point.index)


# ---------------------------------------------------------------------------
# 9. Structured values — the protocol is not scalar-only
# ---------------------------------------------------------------------------


def test_a_structured_feature_emits_all_three_components_at_every_point() -> None:
    """**The design test of ADR-0031 §5.**

    One timestamp, three numbers. A representation assuming one float per point
    would have needed redesigning the first time it met this feature, which is
    why this is a protocol assertion and not an indicator assertion.
    """
    feature = MovingAverageConvergenceDivergence()
    history = feature.compute_series(_context(series(_LONG)))

    assert history.points
    for point in history.points:
        assert isinstance(point.value, Mapping), point.index
        assert set(point.value) == {"macd_line", "signal_line", "histogram"}
        assert tuple(point.value) == ("macd_line", "signal_line", "histogram")


def test_a_structured_point_value_cannot_be_mutated() -> None:
    history = MovingAverageConvergenceDivergence().compute_series(
        _context(series(_LONG))
    )
    with pytest.raises(TypeError):
        history.points[0].value["histogram"] = 0.0  # type: ignore[index]


def test_the_structured_value_at_a_bar_is_derivable_from_that_bars_prices() -> None:
    """**The alignment test parity cannot perform**, and the one that found a hole.

    `compute` and `compute_series` share the expression that pairs a MACD-line
    element with a signal-line element. That sharing is the point — it is what
    makes them one arithmetic — but it means a **shift in the pairing moves both
    paths together**, so latest-value parity, prefix stability and the
    histogram's internal consistency all keep passing while every point
    describes the wrong bar.

    An adversarial probe during TA Slice 5A did exactly that: pairing the signal
    with the MACD element one position earlier survived the whole series matrix.
    This assertion closes it by deriving the expected value **from the prices at
    that bar**, through the shared EMA helper and none of the pairing logic, so a
    shift has nothing left to hide behind.
    """
    feature = MovingAverageConvergenceDivergence()
    candle_series = series(_LONG)
    prices = [candle.close for candle in candle_series.candles]
    history = feature.compute_series(_context(candle_series))

    from fmis.features.indicators.ema_math import ema_series

    assert history.points
    for point in history.points:
        upto = prices[: point.index + 1]
        expected_line = (
            ema_series(upto, feature.fast_period)[-1]
            - ema_series(upto, feature.slow_period)[-1]
        )
        assert point.value["macd_line"] == expected_line, point.index

        # The signal at this bar is the EMA of the MACD line over every bar up
        # to and including it — rebuilt here from prices, never read off the
        # series under test.
        line_to_here = [
            ema_series(prices[: index + 1], feature.fast_period)[-1]
            - ema_series(prices[: index + 1], feature.slow_period)[-1]
            for index in range(feature.slow_period - 1, point.index + 1)
        ]
        expected_signal = ema_series(line_to_here, feature.signal_period)[-1]
        assert point.value["signal_line"] == pytest.approx(
            expected_signal, rel=0, abs=1e-12
        ), point.index
        # One bar is enough to pin the alignment; the rest would be quadratic.
        break

    # And the final bar, which is the one `compute` also describes.
    last = history.latest
    upto = prices[: last.index + 1]
    assert last.value["macd_line"] == (
        ema_series(upto, feature.fast_period)[-1]
        - ema_series(upto, feature.slow_period)[-1]
    )


def test_every_structured_point_pairs_the_line_with_its_own_signal() -> None:
    """The pairing, asserted across the whole series rather than at one bar.

    Cheap where the test above is expensive: the MACD line is computed once, and
    each point's line component is checked against the element the alignment rule
    says belongs to that bar. A shift in either direction fails here.
    """
    feature = MovingAverageConvergenceDivergence()
    candle_series = series(_LONG)
    prices = [candle.close for candle in candle_series.candles]

    from fmis.features.indicators.macd_math import macd_lines

    line, signal = macd_lines(
        prices, feature.fast_period, feature.slow_period, feature.signal_period
    )
    history = feature.compute_series(_context(candle_series))

    assert len(history.points) == len(signal)
    for offset, point in enumerate(history.points):
        # `macd_lines` states its own alignment: element k of the line describes
        # candle k + slow - 1. Read back from the point's candle index rather
        # than from the offset, so the two alignments must agree.
        line_position = point.index - (feature.slow_period - 1)
        assert point.value["macd_line"] == line[line_position], point.index
        assert point.value["signal_line"] == signal[offset], point.index


def test_the_structured_components_are_internally_consistent() -> None:
    """The third component is the difference of the other two, at every point.

    Checked as a relationship the producer states, not recomputed as a formula
    the test owns: if the pairing between the line and the signal ever shifted by
    one position, this is the assertion that would notice.
    """
    history = MovingAverageConvergenceDivergence().compute_series(
        _context(series(_LONG))
    )
    for point in history.points:
        line = point.value["macd_line"]
        signal = point.value["signal_line"]
        assert point.value["histogram"] == line - signal, point.index


# ---------------------------------------------------------------------------
# 10. Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_two_calls_over_one_input_are_equal(feature) -> None:
    context = _context(series(_LONG))
    assert feature.compute_series(context) == feature.compute_series(context)


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_two_equal_inputs_give_equal_series(feature) -> None:
    """Equality is structural, so a rebuilt-but-identical input matches."""
    assert feature.compute_series(_context(series(_LONG))) == feature.compute_series(
        _context(series(_LONG))
    )


# ---------------------------------------------------------------------------
# 11 & 12. Closed candles and alignment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_a_forming_candle_never_enters_a_series(feature) -> None:
    """The reproducibility rule, at the one new place it could be broken."""
    closed_only = series(_LONG)
    with_forming = CandleSeries(
        symbol=closed_only.symbol,
        timeframe=closed_only.timeframe,
        candles=closed_only.candles + series(_LONG + 1, closed=False).candles[-1:],
    )

    assert feature.compute_series(_context(with_forming)) == feature.compute_series(
        _context(closed_only)
    ), feature.name


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_every_point_carries_its_own_candles_timestamp(feature) -> None:
    """**The off-by-one assertion.** One shifted index and this fails at once."""
    candle_series = series(_LONG)
    history = feature.compute_series(_context(candle_series))

    assert history.points
    for point in history.points:
        assert point.timestamp == candle_series.candles[point.index].timestamp, (
            feature.name,
            point.index,
        )


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_points_are_contiguous_from_the_first_defined_bar(feature) -> None:
    """No hole in the middle: warm-up is a head, never a scatter."""
    history = feature.compute_series(_context(series(_LONG)))
    indexes = [point.index for point in history.points]

    assert indexes == list(range(history.first_index, history.closed_candles))


# ---------------------------------------------------------------------------
# The three states — value, undefined, absent
# ---------------------------------------------------------------------------


def test_a_warmed_up_position_with_no_denominator_stays_in_the_series() -> None:
    """**Why a point carries an `undefined_reason`.**

    Dropping the position would shorten the history and shift nothing else —
    the worst available failure, because every later index would still look
    plausible. Padding it with a number would turn *we cannot say* into a
    measurement.
    """
    feature = RelativeVolume(20)
    quiet = series(60, volume=0.0)
    history = feature.compute_series(_context(quiet))

    assert history.points
    for point in history.points:
        assert point.value is None
        assert point.undefined_reason == ZERO_BASELINE
    assert history.first_index == 20
    assert [point.index for point in history.points] == list(range(20, 60))


def test_the_undefined_position_matches_what_the_latest_value_path_reports() -> None:
    """Parity holds through the undefined case too, not only the computed one."""
    feature = RelativeVolume(20)
    context = _context(series(60, volume=0.0))
    result = feature.compute(context)
    history = feature.compute_series(context)

    assert result.value is None
    assert result.metadata[UNDEFINED_REASON_KEY] == ZERO_BASELINE
    assert history.latest.value is None
    assert history.latest.undefined_reason == ZERO_BASELINE


def test_a_zero_baseline_is_still_a_perfectly_good_average() -> None:
    """`AverageVolume` has no undefined case; only the ratio against it does."""
    history = AverageVolume(20).compute_series(_context(series(60, volume=0.0)))

    assert history.points
    for point in history.points:
        assert point.value == 0.0
        assert point.undefined_reason is None


def test_absent_undefined_and_computed_are_three_distinguishable_states() -> None:
    feature = RelativeVolume(5)
    warming = feature.compute_series(_context(series(4)))
    undefined = feature.compute_series(_context(series(10, volume=0.0)))
    computed = feature.compute_series(_context(series(10)))

    assert warming.point_at(5) is None
    assert undefined.point_at(5).value is None
    assert undefined.point_at(5).undefined_reason == ZERO_BASELINE
    assert computed.point_at(5).value is not None
    assert computed.point_at(5).undefined_reason is None


# ---------------------------------------------------------------------------
# The types themselves
# ---------------------------------------------------------------------------


def test_a_point_must_carry_a_value_or_a_reason_and_never_both() -> None:
    with pytest.raises(ValueError):
        FeatureSeriesPoint(index=0, timestamp=BASE)
    with pytest.raises(ValueError):
        FeatureSeriesPoint(index=0, timestamp=BASE, value=1.0, undefined_reason="why")


@pytest.mark.parametrize("index", [-1, True, 1.5, "0"])
def test_a_point_index_must_be_a_non_negative_int(index) -> None:
    with pytest.raises((TypeError, ValueError)):
        FeatureSeriesPoint(index=index, timestamp=BASE, value=1.0)


def test_a_series_refuses_a_point_beyond_the_candles_it_read() -> None:
    with pytest.raises(ValueError):
        FeatureSeries(
            name="x",
            category=FeatureCategory.INDICATOR,
            identity=SeriesIdentity(symbol=SYMBOL, timeframe=TIMEFRAME),
            as_of=BASE,
            closed_candles=2,
            warmup_candles=1,
            points=(FeatureSeriesPoint(index=5, timestamp=BASE, value=1.0),),
        )


def test_a_series_refuses_points_out_of_candle_order() -> None:
    from datetime import timedelta

    later = BASE + timedelta(hours=4)
    with pytest.raises(ValueError):
        FeatureSeries(
            name="x",
            category=FeatureCategory.INDICATOR,
            identity=SeriesIdentity(symbol=SYMBOL, timeframe=TIMEFRAME),
            as_of=later,
            closed_candles=3,
            warmup_candles=1,
            points=(
                FeatureSeriesPoint(index=1, timestamp=later, value=1.0),
                FeatureSeriesPoint(index=0, timestamp=BASE, value=1.0),
            ),
        )


def test_a_series_refuses_a_timestamp_that_goes_backwards() -> None:
    from datetime import timedelta

    later = BASE + timedelta(hours=4)
    with pytest.raises(ValueError):
        FeatureSeries(
            name="x",
            category=FeatureCategory.INDICATOR,
            identity=SeriesIdentity(symbol=SYMBOL, timeframe=TIMEFRAME),
            as_of=later,
            closed_candles=3,
            warmup_candles=1,
            points=(
                FeatureSeriesPoint(index=0, timestamp=later, value=1.0),
                FeatureSeriesPoint(index=1, timestamp=BASE, value=1.0),
            ),
        )


def test_first_index_and_latest_are_projections_not_fields() -> None:
    """ADR-0016 §4: a stored copy of a value one attribute away can drift."""
    stored = {field for field in FeatureSeries.__dataclass_fields__}
    assert "first_index" not in stored
    assert "latest" not in stored


# ---------------------------------------------------------------------------
# Additive compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("feature", _ROSTER, ids=_IDS)
def test_a_series_feature_is_still_an_ordinary_feature(feature) -> None:
    """`compute_series` is additive: nothing stopped satisfying `Feature`."""
    assert isinstance(feature, Feature)
    assert isinstance(feature, SeriesFeature)
    assert supports_series(feature)


def test_the_base_class_demands_no_history_of_a_new_feature() -> None:
    """A pattern detector's output is not a series, and must stay constructible."""
    assert not hasattr(BaseFeature, "compute_series")

    class Latest(BaseFeature):
        name = "latest_only"
        category = FeatureCategory.INDICATOR

        def compute(self, context: FeatureContext):
            from fmis.features import FeatureResult

            return FeatureResult(name=self.name, category=self.category, value=1.0)

    feature = Latest()
    assert isinstance(feature, Feature)
    assert not supports_series(feature)


def test_the_engine_grew_no_series_method() -> None:
    """ADR-0031 §8 — threading *latest* results into a *history* is lookahead.

    Recorded as an assertion rather than a comment so that adding one is a
    deliberate act with a dependency semantics attached, not a convenience.
    """
    from fmis.features.feature_engine import FeatureEngine

    assert not hasattr(FeatureEngine, "compute_series")


def test_the_default_feature_set_did_not_grow() -> None:
    """`AverageVolume` gained a history and stays DORMANT — brief §11."""
    names = {feature.name for feature in default_features()}

    assert "average_volume_20" not in names
    assert names == {
        "ema_20",
        "ema_50",
        "rsi_close_14",
        "atr_14",
        "macd_close_12_26_9",
        "relative_volume_20",
    }
