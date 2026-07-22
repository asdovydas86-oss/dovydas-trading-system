"""Tests for the MACD feature and an EMA+ATR+RSI+MACD engine integration test.

Expected values are independently hand-calculated with small periods
(fast=2, slow=3, signal=2) using exact fractions — never by calling the MACD
implementation or copying its full algorithm.

Worked example (fast=2, slow=3, signal=2, closes = [1, 2, 4, 8]):
    fast EMA (k=2/3): seed (1+2)/2=1.5 ; idx2 (4-1.5)*2/3+1.5=19/6 ;
                      idx3 (8-19/6)*2/3+19/6=115/18
    slow EMA (k=1/2): seed (1+2+4)/3=7/3 ; idx3 (8-7/3)/2+7/3=31/6
    overlap indices [2,3]: macd_line = [19/6-7/3, 115/18-31/6] = [5/6, 11/9]
    signal EMA(period 2) seed = (5/6+11/9)/2 = 37/36   (2 values -> seed only)
    -> macd_line = 11/9 ; signal = 37/36 ; histogram = 11/9 - 37/36 = 7/36
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.features import FeatureCategory, FeatureContext, FeatureRegistry
from fmis.features.feature_engine import FeatureEngine
from fmis.features.indicators import (
    AverageTrueRange,
    ExponentialMovingAverage,
    MovingAverageConvergenceDivergence,
    RelativeStrengthIndex,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
MACD = MovingAverageConvergenceDivergence


def series_from_closes(
    closes: list[float],
    *,
    closed_flags: list[bool] | None = None,
) -> CandleSeries:
    flags = closed_flags if closed_flags is not None else [True] * len(closes)
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol="TEST",
            timeframe="4H",
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1.0,
            is_closed=flag,
        )
        for i, (c, flag) in enumerate(zip(closes, flags))
    )
    return CandleSeries(symbol="TEST", timeframe="4H", candles=candles)


def macd_value(closes, fast=2, slow=3, signal=2, **kwargs):
    feature = MACD(fast, slow, signal, **kwargs)
    return feature.compute(FeatureContext(primary=series_from_closes(closes)))


# --- core MACD math (hand-calculated) ----------------------------------------


def test_hand_calculated_line_signal_histogram() -> None:
    result = macd_value([1, 2, 4, 8])  # exactly required (slow+signal-1 = 4)
    assert result.value["macd_line"] == pytest.approx(11 / 9)
    assert result.value["signal_line"] == pytest.approx(37 / 36)
    assert result.value["histogram"] == pytest.approx(7 / 36)
    assert result.metadata["insufficient_data"] is False


def test_additional_candles_exercise_recursive_signal_ema() -> None:
    # N=5 [1,2,4,8,16]: macd_line=[5/6, 11/9, 239/108]; signal EMA(2) now smooths:
    #   seed=(5/6+11/9)/2=37/36 ; step (239/108-37/36)*2/3+37/36 = 589/324
    #   macd_line=239/108 ; signal=589/324 ; histogram = 239/108-589/324 = 32/81
    result = macd_value([1, 2, 4, 8, 16])
    assert result.value["macd_line"] == pytest.approx(239 / 108)
    assert result.value["signal_line"] == pytest.approx(589 / 324)
    assert result.value["histogram"] == pytest.approx(32 / 81)


def test_period_one_where_valid() -> None:
    # fast=1, slow=2, signal=1 over [2,4,8]:
    #   fast(1)=[2,4,8]; slow(2): seed 3, idx2 (8-3)*2/3+3=19/3
    #   overlap [1,2]: macd_line=[4-3, 8-19/3]=[1, 5/3]; signal(1) -> last = 5/3
    result = macd_value([2, 4, 8], fast=1, slow=2, signal=1)
    assert result.value["macd_line"] == pytest.approx(5 / 3)
    assert result.value["signal_line"] == pytest.approx(5 / 3)
    assert result.value["histogram"] == pytest.approx(0.0)


def test_constant_prices_all_zero() -> None:
    result = macd_value([5, 5, 5, 5, 5])
    assert result.value["macd_line"] == pytest.approx(0.0)
    assert result.value["signal_line"] == pytest.approx(0.0)
    assert result.value["histogram"] == pytest.approx(0.0)


def test_steadily_rising_has_positive_macd_line() -> None:
    result = macd_value([1, 2, 3, 4, 5, 6])
    assert result.value["macd_line"] > 0


def test_falling_has_negative_macd_line() -> None:
    result = macd_value([6, 5, 4, 3, 2, 1])
    assert result.value["macd_line"] < 0


# --- warm-up boundary --------------------------------------------------------


def test_exactly_required_is_valid_one_below_is_insufficient() -> None:
    # fast=2, slow=3, signal=2 -> required = slow + signal - 1 = 4.
    below = macd_value([1, 2, 4])  # 3 candles
    assert below.value is None
    assert below.metadata["insufficient_data"] is True
    assert below.metadata["required_candles"] == 4
    assert below.metadata["closed_candles_available"] == 3
    assert below.metadata["macd_values_available"] == 1  # N - slow + 1 = 1

    exact = macd_value([1, 2, 4, 8])  # 4 candles
    assert exact.value is not None


def test_default_12_26_9_requires_exactly_34_candles() -> None:
    closes = [float(i) for i in range(1, 40)]  # ample, strictly increasing
    feature = MACD()  # 12/26/9 defaults
    at_33 = feature.compute(FeatureContext(primary=series_from_closes(closes[:33])))
    at_34 = feature.compute(FeatureContext(primary=series_from_closes(closes[:34])))
    assert at_33.value is None
    assert at_33.metadata["required_candles"] == 34
    assert at_34.value is not None


# --- sources / closed candles / determinism ----------------------------------


def test_source_selection_changes_result() -> None:
    # opens follow [1,2,4,8,16]; close constant 100 -> macd(close) is all zero.
    opens = [1, 2, 4, 8, 16]
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol="TEST",
            timeframe="4H",
            open=o,
            high=max(o, 100),
            low=min(o, 100),
            close=100,
            volume=1.0,
            is_closed=True,
        )
        for i, o in enumerate(opens)
    )
    series = CandleSeries(symbol="TEST", timeframe="4H", candles=candles)

    on_open = MACD(2, 3, 2, source="open").compute(FeatureContext(primary=series))
    on_close = MACD(2, 3, 2, source="close").compute(FeatureContext(primary=series))
    assert on_open.name == "macd_open_2_3_2"
    assert on_open.value["macd_line"] == pytest.approx(239 / 108)  # from open series
    assert on_close.value["macd_line"] == pytest.approx(0.0)  # constant close


def test_open_candle_is_excluded() -> None:
    closes = [1, 2, 4, 8, 9999]
    flags = [True, True, True, True, False]
    result = MACD(2, 3, 2).compute(
        FeatureContext(primary=series_from_closes(closes, closed_flags=flags))
    )
    assert result.value["macd_line"] == pytest.approx(11 / 9)  # same as 4 closed
    assert result.metadata["closed_candles_available"] == 4


def test_deterministic_repeatability() -> None:
    first = macd_value([1, 2, 4, 8, 16])
    second = macd_value([1, 2, 4, 8, 16])
    assert first.value == second.value
    assert first.metadata == second.metadata


# --- identity / metadata / immutability --------------------------------------


def test_default_name_category_and_metadata_shape() -> None:
    feature = MACD()
    assert feature.name == "macd_close_12_26_9"
    result = macd_value([1, 2, 4, 8])
    assert result.name == "macd_close_2_3_2"
    assert result.category is FeatureCategory.INDICATOR
    for key in (
        "source",
        "fast_period",
        "slow_period",
        "signal_period",
        "method",
        "ema_initialization",
        "closed_candles_available",
        "required_candles",
        "macd_values_available",
        "warmup_candles",
        "output_representation",
        "provenance",
    ):
        assert key in result.metadata
    assert result.metadata["method"] == "ema"
    assert result.metadata["ema_initialization"] == "sma_seed"


def test_value_and_metadata_are_immutable() -> None:
    result = macd_value([1, 2, 4, 8])
    with pytest.raises(TypeError):
        result.value["macd_line"] = 0.0  # type: ignore[index]
    with pytest.raises(TypeError):
        result.metadata["source"] = "high"  # type: ignore[index]


# --- validation --------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_period_value_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        MACD(fast_period=bad)
    with pytest.raises(ValueError, match="positive integer"):
        MACD(signal_period=bad)


@pytest.mark.parametrize("bad", [2.5, "12", None, True])
def test_invalid_period_type_rejected(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        MACD(fast_period=bad)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be an int"):
        MACD(slow_period=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("fast,slow", [(3, 3), (5, 2), (26, 12)])
def test_fast_must_be_less_than_slow(fast: int, slow: int) -> None:
    with pytest.raises(ValueError, match="must be < slow_period"):
        MACD(fast_period=fast, slow_period=slow)


def test_invalid_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be one of"):
        MACD(source="typical")


# --- integration: EMA + ATR + RSI + MACD through FeatureEngine ----------------


def test_engine_computes_ema_atr_rsi_macd_together() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(3))
    registry.register(AverageTrueRange(3))
    registry.register(RelativeStrengthIndex(3))
    registry.register(MACD(2, 3, 2))
    engine = FeatureEngine(registry)

    # Duplicate MACD request must be deduplicated; order follows requested order.
    fs = engine.compute(
        series_from_closes([1, 2, 4, 8, 16]),
        ["macd_close_2_3_2", "ema_3", "atr_3", "rsi_close_3", "macd_close_2_3_2"],
    )

    assert list(fs.features.keys()) == [
        "macd_close_2_3_2",
        "ema_3",
        "atr_3",
        "rsi_close_3",
    ]
    assert len(set(fs.features.keys())) == 4  # no collisions
    macd = fs.get("macd_close_2_3_2").value
    assert set(macd.keys()) == {"macd_line", "signal_line", "histogram"}
    assert fs.get("ema_3").value is not None
    assert fs.get("atr_3").value is not None
    assert fs.get("rsi_close_3").value is not None
