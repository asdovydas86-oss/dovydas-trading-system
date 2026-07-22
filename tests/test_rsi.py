"""Tests for the Wilder RSI feature and an EMA+ATR+RSI engine integration test.

Expected values are independently hand-calculated from the gain/loss series —
never by calling the RSI implementation or reproducing its full algorithm.

Primary worked example (period=3, closes = [10, 11, 10, 12, 11, 13]):
    changes = [+1, -1, +2, -1, +2]
    gains   = [ 1,  0,  2,  0,  2]
    losses  = [ 0,  1,  0,  1,  0]
    seed avg_gain = SMA(1,0,2) = 1.0 ;  seed avg_loss = SMA(0,1,0) = 1/3
    smooth i=3: ag=(1.0*2+0)/3=2/3      ; al=(1/3*2+1)/3 = 5/9
    smooth i=4: ag=(2/3*2+2)/3=10/9     ; al=(5/9*2+0)/3 = 10/27
    RS = (10/9)/(10/27) = 3.0 ;  RSI = 100 - 100/(1+3) = 75.0
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
    RelativeStrengthIndex,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
_HAND_CLOSES = [10, 11, 10, 12, 11, 13]


def series_from_closes(
    closes: list[float],
    *,
    closed_flags: list[bool] | None = None,
    symbol: str = "TEST",
    timeframe: str = "4H",
) -> CandleSeries:
    """Flat candles (O=H=L=C=close)."""
    flags = closed_flags if closed_flags is not None else [True] * len(closes)
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol=symbol,
            timeframe=timeframe,
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1.0,
            is_closed=flag,
        )
        for i, (c, flag) in enumerate(zip(closes, flags))
    )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)


def rsi_result(closes, period, **kwargs):
    feature = RelativeStrengthIndex(period, **kwargs)
    return feature.compute(FeatureContext(primary=series_from_closes(closes)))


# --- core RSI math -----------------------------------------------------------


def test_hand_calculated_rsi_with_gains_and_losses() -> None:
    result = rsi_result(_HAND_CLOSES, 3)
    assert result.value == pytest.approx(75.0)
    assert result.metadata["insufficient_data"] is False


def test_all_gains_gives_100() -> None:
    result = rsi_result([1, 2, 3, 4, 5, 6], 3)
    assert result.value == pytest.approx(100.0)


def test_all_losses_gives_0() -> None:
    result = rsi_result([6, 5, 4, 3, 2, 1], 3)
    assert result.value == pytest.approx(0.0)


def test_constant_prices_gives_50() -> None:
    result = rsi_result([5, 5, 5, 5, 5], 3)
    assert result.value == pytest.approx(50.0)


def test_exactly_period_plus_one_candles() -> None:
    # 4 closes -> 3 changes; period 3 = seed only, no smoothing.
    # changes [+1,-1,+2]: seed ag=1.0, al=1/3 -> RS=3 -> RSI 75.0
    result = rsi_result([10, 11, 10, 12], 3)
    assert result.value == pytest.approx(75.0)


def test_wilder_smoothing_period_2() -> None:
    # period=2 over the 6-close series exercises 3 smoothing steps.
    # Hand result: RS = 1.3125/0.3125 = 4.2 ; RSI = 100 - 100/5.2 = 1050/13
    result = rsi_result(_HAND_CLOSES, 2)
    assert result.value == pytest.approx(1050 / 13)


def test_different_period_5() -> None:
    # period=5 over the 6-close series -> seed only.
    # gains [1,0,2,0,2] avg=1.0 ; losses [0,1,0,1,0] avg=0.4 ; RS=2.5 -> 500/7
    result = rsi_result(_HAND_CLOSES, 5)
    assert result.value == pytest.approx(500 / 7)


# --- source handling ---------------------------------------------------------


def test_source_selection_changes_result() -> None:
    # open varies like the hand series; close is constant at 100.
    opens = [10, 11, 10, 12]
    rows = [(o, max(o, 100), min(o, 100), 100) for o in opens]
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol="TEST",
            timeframe="4H",
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1.0,
            is_closed=True,
        )
        for i, (o, h, low, c) in enumerate(rows)
    )
    series = CandleSeries(symbol="TEST", timeframe="4H", candles=candles)

    open_result = RelativeStrengthIndex(3, source="open").compute(
        FeatureContext(primary=series)
    )
    close_result = RelativeStrengthIndex(3, source="close").compute(
        FeatureContext(primary=series)
    )
    assert open_result.name == "rsi_open_3"
    assert open_result.value == pytest.approx(75.0)  # from the open pattern
    assert close_result.value == pytest.approx(50.0)  # constant close -> 50


# --- closed-candle discipline & determinism ----------------------------------


def test_open_candle_is_excluded() -> None:
    closes = [*_HAND_CLOSES, 9999]
    flags = [True] * 6 + [False]
    feature = RelativeStrengthIndex(3)
    result = feature.compute(
        FeatureContext(primary=series_from_closes(closes, closed_flags=flags))
    )
    assert result.value == pytest.approx(75.0)
    assert result.metadata["closed_candles_available"] == 6


def test_deterministic_repeatability() -> None:
    first = rsi_result(_HAND_CLOSES, 3)
    second = rsi_result(_HAND_CLOSES, 3)
    assert first.value == second.value
    assert first.metadata == second.metadata


def test_period_one_uses_last_change() -> None:
    # period=1 -> avg reduces to the last gain/loss. Last change of [10,12,11]
    # is -1 (a loss), so RSI = 0.
    result = rsi_result([10, 12, 11], 1)
    assert result.value == pytest.approx(0.0)


# --- insufficient data -------------------------------------------------------


def test_insufficient_candles() -> None:
    # period 3 needs >= 4 candles (>= 3 changes); give 3 candles (2 changes).
    result = rsi_result([10, 11, 10], 3)
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert result.metadata["required_candles"] == 4
    assert result.metadata["changes_available"] == 2


# --- identity / validation ---------------------------------------------------


def test_default_name_category_and_metadata_shape() -> None:
    feature = RelativeStrengthIndex()
    assert feature.name == "rsi_close_14"
    assert feature.period == 14
    assert feature.source == "close"

    result = rsi_result(_HAND_CLOSES, 3)
    assert result.name == "rsi_close_3"
    assert result.category is FeatureCategory.INDICATOR
    for key in (
        "period",
        "source",
        "method",
        "closed_candles_available",
        "changes_available",
        "warmup_candles",
        "initialization",
        "zero_gain_zero_loss_policy",
        "provenance",
    ):
        assert key in result.metadata
    assert result.metadata["method"] == "wilder"


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_period_value_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        RelativeStrengthIndex(bad)


@pytest.mark.parametrize("bad", [2.5, "14", None, True])
def test_invalid_period_type_rejected(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        RelativeStrengthIndex(bad)  # type: ignore[arg-type]


def test_invalid_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be one of"):
        RelativeStrengthIndex(14, source="typical")


def test_ema_and_rsi_share_source_vocabulary() -> None:
    # EMA and RSI validate against one shared vocabulary, not each other.
    from fmis.features.indicators.sources import VALID_SOURCES

    assert VALID_SOURCES == ("open", "high", "low", "close")
    for src in VALID_SOURCES:
        assert ExponentialMovingAverage(3, source=src).source == src
        assert RelativeStrengthIndex(3, source=src).source == src
    for bad in ("typical", "hlc3"):
        with pytest.raises(ValueError, match="source must be one of"):
            ExponentialMovingAverage(3, source=bad)
        with pytest.raises(ValueError, match="source must be one of"):
            RelativeStrengthIndex(3, source=bad)


# --- integration: EMA + ATR + RSI through FeatureEngine ----------------------


def test_engine_computes_ema_atr_rsi_together() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(3))
    registry.register(AverageTrueRange(3))
    registry.register(RelativeStrengthIndex(3))
    engine = FeatureEngine(registry)

    # Duplicate RSI request must be deduplicated; order follows requested order.
    fs = engine.compute(
        series_from_closes(_HAND_CLOSES),
        ["rsi_close_3", "ema_3", "atr_3", "rsi_close_3"],
    )

    assert list(fs.features.keys()) == ["rsi_close_3", "ema_3", "atr_3"]
    assert fs.has("ema_3") and fs.has("atr_3") and fs.has("rsi_close_3")
    # No collisions: three distinct names, three distinct results.
    assert len({"rsi_close_3", "ema_3", "atr_3"}) == 3
    assert fs.get("rsi_close_3").value == pytest.approx(75.0)
    assert fs.get("ema_3").value is not None
    assert fs.get("atr_3").value is not None
