"""Tests for the Wilder ATR feature.

Expected values are hand-calculated from the true-range series — never the ATR
implementation copied into the test.

Primary worked example (period=3). Candles chosen so each close sits inside the
next candle's range, making TR = high - low for every bar:

    candle:  (o,  h,  l,  c)     TR (vs previous close)
    0        ( 9, 10,  8,  9)    —   (no previous close)
    1        (10, 11,  9, 10)    2
    2        (11, 13, 10, 12)    3
    3        (12, 14, 10, 11)    4
    4        (12, 16, 11, 15)    5
    5        (15, 18, 12, 13)    6

    true ranges = [2, 3, 4, 5, 6]
    period=3 seed = SMA(2,3,4) = 3.0
    Wilder:  (3.0*2 + 5)/3 = 11/3 ; (11/3*2 + 6)/3 = 40/9  -> ATR = 40/9
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.features import FeatureCategory, FeatureContext
from fmis.features.indicators.atr import AverageTrueRange

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)

# (open, high, low, close) rows producing true ranges [2, 3, 4, 5, 6].
_HAND_ROWS = [
    (9, 10, 8, 9),
    (10, 11, 9, 10),
    (11, 13, 10, 12),
    (12, 14, 10, 11),
    (12, 16, 11, 15),
    (15, 18, 12, 13),
]


def series_from_rows(
    rows: list[tuple[float, float, float, float]],
    *,
    closed_flags: list[bool] | None = None,
    symbol: str = "TEST",
    timeframe: str = "4H",
) -> CandleSeries:
    flags = closed_flags if closed_flags is not None else [True] * len(rows)
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol=symbol,
            timeframe=timeframe,
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1.0,
            is_closed=flag,
        )
        for i, ((o, h, low, c), flag) in enumerate(zip(rows, flags))
    )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)


def atr_result(rows, period, **kwargs):
    feature = AverageTrueRange(period, **kwargs)
    return feature.compute(FeatureContext(primary=series_from_rows(rows)))


# --- core ATR math -----------------------------------------------------------


def test_hand_calculated_atr() -> None:
    result = atr_result(_HAND_ROWS, 3)
    assert result.value == pytest.approx(40 / 9)
    assert result.metadata["insufficient_data"] is False


def test_period_equal_to_true_range_count_is_sma() -> None:
    # 5 true ranges, period 5 -> ATR = SMA(2,3,4,5,6) = 4.0 (independent reference).
    result = atr_result(_HAND_ROWS, 5)
    assert result.value == pytest.approx(4.0)


def test_different_period_smaller() -> None:
    # period=2: seed SMA(2,3)=2.5; (2.5+4)/2=3.25; (3.25+5)/2=4.125;
    #           (4.125+6)/2 = 5.0625
    result = atr_result(_HAND_ROWS, 2)
    assert result.value == pytest.approx(5.0625)


# --- edge / behavioural cases ------------------------------------------------


def test_insufficient_candles() -> None:
    # period 3 needs >= 4 candles (>= 3 true ranges); give 3 candles (2 TRs).
    result = atr_result(_HAND_ROWS[:3], 3)
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert result.metadata["required_candles"] == 4
    assert result.metadata["true_ranges_available"] == 2


def test_constant_price_candles_give_zero_atr() -> None:
    rows = [(100, 100, 100, 100)] * 6
    result = atr_result(rows, 3)
    assert result.value == pytest.approx(0.0)


def test_high_volatility_with_gaps() -> None:
    # Gaps make TR pick the close-relative components, not high-low:
    #   TR1: prev_close 100, (o125,h130,l120,c128) -> max(10, 30, 20) = 30
    #   TR2: prev_close 128, (o85, h90, l80, c82)  -> max(10, 38, 48) = 48
    #   TR3: prev_close 82,  (o88, h95, l85, c90)  -> max(10, 13,  3) = 13
    # period 3 -> ATR = SMA(30,48,13) = 91/3
    rows = [
        (100, 100, 100, 100),
        (125, 130, 120, 128),
        (85, 90, 80, 82),
        (88, 95, 85, 90),
    ]
    result = atr_result(rows, 3)
    assert result.value == pytest.approx(91 / 3)


def test_open_candle_is_excluded() -> None:
    # A still-forming 7th candle with wild values must not change ATR (40/9).
    rows = [*_HAND_ROWS, (13, 9999, 1, 5000)]
    flags = [True] * 6 + [False]
    feature = AverageTrueRange(3)
    result = feature.compute(
        FeatureContext(primary=series_from_rows(rows, closed_flags=flags))
    )
    assert result.value == pytest.approx(40 / 9)
    assert result.metadata["closed_candles_available"] == 6


def test_deterministic_repeatability() -> None:
    first = atr_result(_HAND_ROWS, 3)
    second = atr_result(_HAND_ROWS, 3)
    assert first.value == second.value
    assert first.metadata == second.metadata


# --- identity / validation ---------------------------------------------------


def test_default_period_and_result_shape() -> None:
    feature = AverageTrueRange()
    assert feature.name == "atr_14"
    assert feature.period == 14
    result = atr_result(_HAND_ROWS, 3)
    assert result.name == "atr_3"
    assert result.category is FeatureCategory.INDICATOR
    assert result.metadata["method"] == "wilder"
    assert "true_range_formula" in result.metadata
    assert "initialization" in result.metadata


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_period_value_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        AverageTrueRange(bad)


@pytest.mark.parametrize("bad", [2.5, "14", None, True])
def test_invalid_period_type_rejected(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        AverageTrueRange(bad)  # type: ignore[arg-type]
