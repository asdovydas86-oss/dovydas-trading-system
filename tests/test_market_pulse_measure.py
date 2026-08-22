"""Milestone BT — measurement: windows, no lookahead, and absence over zero.

Two claims are under test. **The engine does the arithmetic**: every figure here
is `fmis.relative_value`'s, asserted by recomputing it through the engine
directly and comparing. And **a window shorter than the horizon is a different
measurement**, reported rather than taken.

The no-lookahead assertions are the load-bearing ones. A forming bar and a bar
that opens after the instant being described are excluded by two independent
mechanisms, and each is tested with the other disabled.
"""

from __future__ import annotations

import pytest

from fmis.data import CandleSeries
from fmis.data.reduction import CandleField, candle_series_to_observations
from fmis.market_pulse import (
    CO_MOVEMENT_METRIC,
    HORIZON_24_BARS,
    HORIZON_LATEST_BAR,
    MOVE_METRIC,
    VOLATILITY_METRIC,
    Horizon,
    NoObservationsError,
    measure_co_movement,
    measure_from_observations,
    measure_market,
    measure_move,
    measure_volatility,
    observations_for,
)
from fmis.relative_value import (
    pearson_correlation,
    period_return,
    realized_volatility,
)
from tests.market_pulse_helpers import (
    candles,
    crypto_benchmark,
    dark_benchmark,
    instant,
    linear,
    observations,
)

ONE = Horizon(horizon_id="h1", bars=1, description="one bar")
THREE = Horizon(horizon_id="h3", bars=3, description="three bars")


# --------------------------------------------------------------------------
# Reduction: closed only, at or before the instant, never empty as zero
# --------------------------------------------------------------------------


def test_a_forming_bar_never_reaches_a_measurement() -> None:
    """The first of two independent no-lookahead mechanisms."""
    mixed = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        candles=(
            *candles([100.0, 110.0], closed=True).candles,
            *candles([999.0], closed=False, start_hour=2).candles,
        ),
    )
    series = observations_for(mixed, as_of=instant(99), series_id="s")
    assert series.values == (100.0, 110.0)


def test_a_bar_opening_after_the_instant_never_reaches_a_measurement() -> None:
    """The second mechanism, tested with the first satisfied: every bar here is
    closed, and the later ones are still excluded."""
    series = observations_for(
        candles([100.0, 110.0, 120.0, 130.0]), as_of=instant(1), series_id="s"
    )
    assert series.values == (100.0, 110.0)
    assert series.timestamps[-1] == instant(1)


def test_a_bar_opening_exactly_at_the_instant_is_included() -> None:
    """The boundary is inclusive and is asserted, not left to inference."""
    series = observations_for(
        candles([100.0, 110.0, 120.0]), as_of=instant(1), series_id="s"
    )
    assert series.values == (100.0, 110.0)


def test_an_empty_window_is_an_error_and_never_a_move_of_zero() -> None:
    with pytest.raises(NoObservationsError, match="rather than a move of zero"):
        observations_for(
            candles([100.0, 110.0]), as_of=instant(-5), series_id="s"
        )


def test_an_all_forming_window_is_an_error() -> None:
    with pytest.raises(NoObservationsError):
        observations_for(
            candles([100.0, 110.0], closed=False), as_of=instant(99), series_id="s"
        )


def test_reduction_refuses_a_non_series() -> None:
    with pytest.raises(TypeError, match="must be a CandleSeries"):
        observations_for(object(), as_of=instant(1), series_id="s")


# --------------------------------------------------------------------------
# Moves: sign, zero, boundary, absence
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values, expected",
    [
        ([100.0, 110.0], 0.1),
        ([100.0, 90.0], -0.1),
        ([100.0, 100.0], 0.0),
    ],
    ids=["positive", "negative", "zero"],
)
def test_a_move_carries_the_measured_sign(values, expected) -> None:
    measured = measure_move(observations(values), ONE)
    assert measured.is_measured
    assert measured.value == pytest.approx(expected)


def test_the_move_is_the_engine_s_own_number_and_not_a_second_formula() -> None:
    """*Every number on the page comes from the Relative Value Engine.*"""
    values = linear(100.0, 3.0, 5)
    series = observations(values)
    measured = measure_move(series, THREE)
    direct = period_return(observations(values[-4:], start_hour=1))
    assert measured.value == direct.value
    assert measured.metric == MOVE_METRIC == direct.name


def test_a_move_reads_the_end_of_the_window_not_the_start() -> None:
    """A wrong-baseline mutation is exactly what this catches: the 1-bar move
    over a rising series must use the last two closes, not the first two."""
    measured = measure_move(observations([1.0, 2.0, 4.0]), ONE)
    assert measured.value == pytest.approx(1.0)  # 4/2 - 1, not 2/1 - 1


def test_a_move_names_the_window_it_actually_spanned() -> None:
    measured = measure_move(observations([1.0, 2.0, 4.0, 8.0]), ONE)
    assert measured.window_start == instant(2)
    assert measured.window_end == instant(3)
    assert measured.observation_count == 2


def test_exactly_enough_observations_measures_and_one_fewer_does_not() -> None:
    """The boundary of the window rule, asserted from both sides."""
    assert measure_move(observations(linear(1.0, 1.0, 4)), THREE).is_measured
    short = measure_move(observations(linear(1.0, 1.0, 3)), THREE)
    assert not short.is_measured
    assert "needs 4 closed bars and this market supplied 3" in short.unavailable_reason


def test_a_missing_baseline_is_reported_rather_than_measured_over_less() -> None:
    """*A "7-day move" computed from four days is a different measurement
    wearing the same label.*"""
    short = measure_move(observations([100.0, 110.0]), HORIZON_24_BARS)
    assert not short.is_measured
    assert short.value is None
    assert "different measurement" in short.unavailable_reason


def test_a_zero_baseline_is_undefined_and_says_so_rather_than_printing_zero() -> None:
    undefined = measure_move(observations([0.0, 100.0]), ONE)
    assert not undefined.is_measured
    assert "zero_denominator" in undefined.unavailable_reason
    assert "not a reading of zero" in undefined.unavailable_reason


def test_a_move_refuses_a_non_horizon() -> None:
    with pytest.raises(TypeError, match="must be a Horizon"):
        measure_move(observations([1.0, 2.0]), "1h")


def test_an_extreme_move_is_measured_rather_than_clamped() -> None:
    """A market that went up a thousandfold is a fact, not an error."""
    measured = measure_move(observations([0.001, 1000.0]), ONE)
    assert measured.value == pytest.approx(999999.0)


def test_a_non_terminating_decimal_result_is_still_deterministic() -> None:
    """1/3 has no finite binary expansion; two computations must still agree."""
    first = measure_move(observations([3.0, 1.0]), ONE)
    second = measure_move(observations([3.0, 1.0]), ONE)
    assert first.value == second.value
    assert first == second


# --------------------------------------------------------------------------
# Volatility: reuse, absence, and the refusal to classify
# --------------------------------------------------------------------------


def test_volatility_is_the_engine_s_own_number() -> None:
    values = [100.0, 105.0, 99.0, 103.0, 101.0]
    measured = measure_volatility(observations(values), THREE)
    direct = realized_volatility(observations(values[-4:], start_hour=1))
    assert measured.value == direct.value
    assert measured.metric == VOLATILITY_METRIC == direct.name


def test_a_constant_series_has_a_volatility_of_zero_which_is_a_measurement() -> None:
    """Zero volatility and unmeasurable volatility are different facts."""
    measured = measure_volatility(observations([5.0, 5.0, 5.0, 5.0]), THREE)
    assert measured.is_measured and measured.value == 0.0


def test_a_short_window_leaves_volatility_unavailable_rather_than_zero() -> None:
    measured = measure_volatility(observations([1.0, 2.0]), HORIZON_24_BARS)
    assert not measured.is_measured and measured.value is None


def test_a_zero_price_makes_volatility_undefined_rather_than_zero() -> None:
    measured = measure_volatility(observations([0.0, 1.0, 2.0, 3.0]), THREE)
    assert not measured.is_measured
    assert "zero_denominator" in measured.unavailable_reason


def test_a_volatility_reading_carries_no_classification_field() -> None:
    """*Calling a reading elevated requires a baseline this build does not
    compute.* The absence of the field is the guarantee."""
    measured = measure_volatility(observations([1.0, 2.0, 3.0, 4.0]), THREE)
    banned = {"regime", "level", "classification", "elevated", "is_high", "label"}
    assert banned & set(dir(measured)) == set()


def test_volatility_refuses_a_non_horizon() -> None:
    with pytest.raises(TypeError, match="must be a Horizon"):
        measure_volatility(observations([1.0, 2.0, 3.0]), 3)


# --------------------------------------------------------------------------
# A whole market reading
# --------------------------------------------------------------------------


def test_a_reading_carries_every_horizon_in_the_order_requested() -> None:
    reading = measure_market(
        crypto_benchmark(),
        candles(linear(100.0, 1.0, 30)),
        as_of=instant(99),
        source="binance-spot",
        horizons=(HORIZON_LATEST_BAR, THREE, ONE),
        volatility_horizon=THREE,
    )
    assert [move.horizon_id for move in reading.moves] == ["latest_bar", "h3", "h1"]


def test_a_reading_records_the_last_bar_open_and_the_bar_count() -> None:
    reading = measure_market(
        crypto_benchmark(),
        candles(linear(100.0, 1.0, 10)),
        as_of=instant(99),
        source="binance-spot",
        horizons=(ONE,),
        volatility_horizon=THREE,
    )
    assert reading.last_bar_open == instant(9)
    assert reading.closed_bar_count == 10


def test_an_unsupported_market_cannot_be_measured() -> None:
    with pytest.raises(ValueError, match="no provider instrument"):
        measure_market(
            dark_benchmark(),
            candles([1.0, 2.0]),
            as_of=instant(99),
            source="s",
            horizons=(ONE,),
            volatility_horizon=THREE,
        )


def test_measuring_refuses_a_non_benchmark() -> None:
    with pytest.raises(TypeError, match="must be a Benchmark"):
        measure_market(
            "BTC",
            candles([1.0, 2.0]),
            as_of=instant(99),
            source="s",
            horizons=(ONE,),
            volatility_horizon=THREE,
        )


def test_the_split_measure_path_and_the_convenience_path_agree() -> None:
    """`measure_market` must be exactly `observations_for` then
    `measure_from_observations` — the composition root relies on it."""
    benchmark = crypto_benchmark()
    series = candles(linear(100.0, 1.0, 30))
    direct = measure_market(
        benchmark,
        series,
        as_of=instant(99),
        source="binance-spot",
        horizons=(ONE, THREE),
        volatility_horizon=THREE,
    )
    split = measure_from_observations(
        benchmark,
        observations_for(
            series, as_of=instant(99), series_id=benchmark.instrument.label
        ),
        source="binance-spot",
        horizons=(ONE, THREE),
        volatility_horizon=THREE,
    )
    assert direct == split


def test_an_empty_observation_series_is_a_caller_error_not_a_market_fact() -> None:
    with pytest.raises(ValueError, match="empty observation series"):
        measure_from_observations(
            crypto_benchmark(),
            observations([]),
            source="s",
            horizons=(ONE,),
            volatility_horizon=THREE,
        )


def test_a_series_id_carries_the_instrument_label_into_engine_metadata() -> None:
    """Provenance reaches the engine, so a metric's own metadata names the
    market it was computed for."""
    benchmark = crypto_benchmark()
    series = observations_for(
        candles(linear(1.0, 1.0, 5)),
        as_of=instant(99),
        series_id=benchmark.instrument.label,
    )
    assert series.series_id == "binance-spot BTCUSDT 1h"
    assert period_return(series).metadata["source_series_ids"] == (series.series_id,)


# --------------------------------------------------------------------------
# Co-movement: aligned or refused, never intersected
# --------------------------------------------------------------------------


def test_co_movement_is_the_engine_s_own_number() -> None:
    left = [1.0, 2.0, 3.0, 5.0]
    right = [10.0, 21.0, 29.0, 52.0]
    measured = measure_co_movement(
        "ETH", observations(left), "BTC", observations(right), THREE
    )
    direct = pearson_correlation(observations(left), observations(right))
    assert measured.value == direct.value
    assert measured.metric == CO_MOVEMENT_METRIC == direct.name


def test_misaligned_windows_are_refused_rather_than_intersected() -> None:
    """*An intersection is a different window than the one the page names.*"""
    measured = measure_co_movement(
        "ETH",
        observations([1.0, 2.0, 3.0, 4.0], start_hour=0),
        "BTC",
        observations([1.0, 2.0, 3.0, 4.0], start_hour=5),
        THREE,
    )
    assert not measured.is_measured
    assert "do not cover the same instants" in measured.unavailable_reason
    assert "never intersects" in measured.unavailable_reason


def test_a_short_window_leaves_co_movement_unavailable() -> None:
    measured = measure_co_movement(
        "ETH", observations([1.0, 2.0]), "BTC", observations([1.0, 2.0]), THREE
    )
    assert not measured.is_measured
    assert measured.observation_count == 2


def test_the_shorter_of_the_two_windows_decides_sufficiency() -> None:
    """A long reference cannot rescue a short subject."""
    measured = measure_co_movement(
        "ETH",
        observations([1.0, 2.0]),
        "BTC",
        observations(linear(1.0, 1.0, 50)),
        THREE,
    )
    assert not measured.is_measured and measured.observation_count == 2


def test_a_constant_series_makes_co_movement_undefined_rather_than_zero() -> None:
    measured = measure_co_movement(
        "ETH",
        observations([5.0, 5.0, 5.0, 5.0]),
        "BTC",
        observations([1.0, 2.0, 3.0, 4.0]),
        THREE,
    )
    assert not measured.is_measured
    assert "zero_variance" in measured.unavailable_reason


def test_co_movement_refuses_a_non_horizon() -> None:
    with pytest.raises(TypeError, match="must be a Horizon"):
        measure_co_movement(
            "ETH", observations([1.0, 2.0, 3.0]), "BTC",
            observations([1.0, 2.0, 3.0]), 3,
        )


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_history_measured_twice_is_identical() -> None:
    benchmark = crypto_benchmark()
    series = candles(linear(100.0, 1.7, 40))
    args = dict(
        as_of=instant(99),
        source="binance-spot",
        horizons=(ONE, THREE),
        volatility_horizon=THREE,
    )
    assert measure_market(benchmark, series, **args) == measure_market(
        benchmark, series, **args
    )


# --------------------------------------------------------------------------
# A horizon shorter than the metric itself needs — a configuration fault
# --------------------------------------------------------------------------


def test_the_restated_engine_minimums_match_the_engine_s_own() -> None:
    """The two must not drift. If the RVE raises its minimum, this fails here
    rather than as an unhandled traceback on a live page."""
    from fmis.market_pulse.measure import (
        CO_MOVEMENT_MINIMUM_OBSERVATIONS,
        MOVE_MINIMUM_OBSERVATIONS,
        VOLATILITY_MINIMUM_OBSERVATIONS,
    )
    from fmis.relative_value import InsufficientObservationsError

    def minimum_of(call) -> int:
        try:
            call()
        except InsufficientObservationsError as error:
            return error.required
        raise AssertionError("expected the engine to state its minimum")

    assert MOVE_MINIMUM_OBSERVATIONS == minimum_of(
        lambda: period_return(observations([1.0]))
    )
    assert VOLATILITY_MINIMUM_OBSERVATIONS == minimum_of(
        lambda: realized_volatility(observations([1.0, 2.0]))
    )
    assert CO_MOVEMENT_MINIMUM_OBSERVATIONS == minimum_of(
        lambda: pearson_correlation(
            observations([1.0, 2.0]), observations([1.0, 2.0])
        )
    )


def test_a_horizon_too_short_for_volatility_reports_a_configuration_fault() -> None:
    """*No market could satisfy it* — worded so it cannot read as an outage."""
    measured = measure_volatility(observations(linear(1.0, 1.0, 50)), ONE)
    assert not measured.is_measured
    assert "configuration fault" in measured.unavailable_reason
    assert "realized_volatility requires at least 3" in measured.unavailable_reason


def test_a_horizon_too_short_for_co_movement_reports_a_configuration_fault() -> None:
    measured = measure_co_movement(
        "ETH",
        observations(linear(1.0, 1.0, 50)),
        "BTC",
        observations(linear(2.0, 3.0, 50)),
        ONE,
    )
    assert not measured.is_measured
    assert "configuration fault" in measured.unavailable_reason


def test_the_configuration_fault_is_caught_before_the_engine_is_called() -> None:
    """The engine's `InsufficientObservationsError` must never escape to a page.

    A plentiful series with a one-bar horizon is exactly the shape that used to
    reach `pearson_correlation` and raise.
    """
    from fmis.relative_value import InsufficientObservationsError

    try:
        measure_co_movement(
            "ETH",
            observations(linear(1.0, 1.0, 100)),
            "BTC",
            observations(linear(5.0, 2.0, 100)),
            ONE,
        )
    except InsufficientObservationsError:  # pragma: no cover - the regression
        raise AssertionError("the engine's structural error escaped to the page")


def test_the_default_horizons_are_all_long_enough_for_every_metric() -> None:
    """The shipped configuration is proved sound rather than assumed."""
    from fmis.market_pulse import DEFAULT_HORIZONS, VOLATILITY_HORIZON
    from fmis.market_pulse.measure import (
        CO_MOVEMENT_MINIMUM_OBSERVATIONS,
        MOVE_MINIMUM_OBSERVATIONS,
        VOLATILITY_MINIMUM_OBSERVATIONS,
    )

    for horizon in DEFAULT_HORIZONS:
        assert horizon.required_observations >= MOVE_MINIMUM_OBSERVATIONS
    assert VOLATILITY_HORIZON.required_observations >= VOLATILITY_MINIMUM_OBSERVATIONS
    assert VOLATILITY_HORIZON.required_observations >= CO_MOVEMENT_MINIMUM_OBSERVATIONS


def test_reduction_reads_the_close_and_no_other_field() -> None:
    """A wrong-field mutation would silently measure highs; this pins it."""
    series = candles([100.0, 110.0])
    assert observations_for(series, as_of=instant(99), series_id="s").values == (
        candle_series_to_observations(series, CandleField.CLOSE).values
    )
