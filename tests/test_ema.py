"""Tests for the EMA feature and the minimal FeatureEngine vertical slice.

Expected values are hand-calculated or use an independent reference (arithmetic
mean, or the last value) — never the EMA implementation copied into the test.

Worked hand example (period=3, closes = [1, 2, 3, 4, 5, 6]):
    seed = SMA(1, 2, 3) = 2.0 ;  k = 2 / (3 + 1) = 0.5
    step 4: (4 - 2.0) * 0.5 + 2.0 = 3.0
    step 5: (5 - 3.0) * 0.5 + 3.0 = 4.0
    step 6: (6 - 4.0) * 0.5 + 4.0 = 5.0   -> EMA = 5.0
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import pytest

from fmis.data import Candle, CandleSeries
from fmis.features import FeatureCategory, FeatureContext, FeatureRegistry
from fmis.features.feature_engine import FeatureEngine
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.types import BaseFeature, FeatureResult

FIXTURES = Path(__file__).parent / "fixtures"
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def series_from_prices(
    prices: list[float],
    *,
    closed_flags: list[bool] | None = None,
    symbol: str = "TEST",
    timeframe: str = "4H",
) -> CandleSeries:
    """Build a CandleSeries where O=H=L=C=price (a valid flat candle)."""
    flags = closed_flags if closed_flags is not None else [True] * len(prices)
    candles = tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * i),
            symbol=symbol,
            timeframe=timeframe,
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1.0,
            is_closed=flag,
        )
        for i, (p, flag) in enumerate(zip(prices, flags))
    )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)


def ema_value(prices: list[float], period: int, **kwargs: object) -> FeatureResult:
    feature = ExponentialMovingAverage(period, **kwargs)  # type: ignore[arg-type]
    return feature.compute(FeatureContext(primary=series_from_prices(prices)))


# --- core EMA math -----------------------------------------------------------


def test_known_hand_calculated_example() -> None:
    result = ema_value([1, 2, 3, 4, 5, 6], 3)
    assert result.value == pytest.approx(5.0)
    assert result.metadata["insufficient_data"] is False


def test_exact_period_equals_seed_sma() -> None:
    # Independent reference: with exactly `period` values, EMA == mean of them.
    result = ema_value([1, 2, 3], 3)
    assert result.value == pytest.approx(mean([1, 2, 3]))  # 2.0


def test_more_than_period_second_hand_example() -> None:
    # period=2, [2,4,6]: seed=(2+4)/2=3, k=2/3; (6-3)*2/3+3 = 5.0
    result = ema_value([2, 4, 6], 2)
    assert result.value == pytest.approx(5.0)


def test_period_one_returns_last_value() -> None:
    # Independent reference: EMA(period=1) reduces to the most recent value.
    result = ema_value([10, 20, 30, 99], 1)
    assert result.value == pytest.approx(99.0)


def test_insufficient_data_state() -> None:
    result = ema_value([1, 2], 3)
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert result.metadata["required"] == 3
    assert result.metadata["closed_candles_available"] == 2


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_invalid_period_value_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ExponentialMovingAverage(bad)


@pytest.mark.parametrize("bad", [2.5, "3", None, True])
def test_invalid_period_type_rejected(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        ExponentialMovingAverage(bad)  # type: ignore[arg-type]


def test_invalid_source_rejected() -> None:
    with pytest.raises(ValueError, match="source must be one of"):
        ExponentialMovingAverage(3, source="typical")


# --- closed-candle discipline & determinism ----------------------------------


def test_open_candle_is_excluded() -> None:
    # Six closed candles [1..6] give EMA 5.0; a 7th still-forming candle at 9999
    # must not change the result.
    prices = [1, 2, 3, 4, 5, 6, 9999]
    flags = [True, True, True, True, True, True, False]
    feature = ExponentialMovingAverage(3)
    result = feature.compute(
        FeatureContext(primary=series_from_prices(prices, closed_flags=flags))
    )
    assert result.value == pytest.approx(5.0)
    assert result.metadata["closed_candles_available"] == 6


def test_repeated_computation_is_deterministic() -> None:
    prices = [3, 1, 4, 1, 5, 9, 2, 6]
    first = ema_value(prices, 4)
    second = ema_value(prices, 4)
    assert first.value == second.value
    assert first.metadata == second.metadata


def test_result_shape_and_category() -> None:
    result = ema_value([1, 2, 3, 4], 2)
    assert result.name == "ema_2"
    assert result.category is FeatureCategory.INDICATOR
    assert result.metadata["source"] == "close"
    assert result.metadata["period"] == 2
    assert "formula" in result.metadata
    assert "initialization" in result.metadata


def test_non_default_source_changes_name() -> None:
    feature = ExponentialMovingAverage(5, source="high")
    assert feature.name == "ema_5_high"


# --- registry integration ----------------------------------------------------


def test_registry_integration() -> None:
    registry = FeatureRegistry()
    ema = ExponentialMovingAverage(3)
    registry.register(ema)
    assert "ema_3" in registry
    assert registry.get("ema_3") is ema
    assert ema in registry.by_category(FeatureCategory.INDICATOR)


# --- engine -> FeatureSet vertical flow ---------------------------------------


def test_engine_vertical_flow() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(3))
    engine = FeatureEngine(registry)

    fs = engine.compute(series_from_prices([1, 2, 3, 4, 5, 6]), ["ema_3"])

    assert fs.symbol == "TEST"
    assert fs.timeframe == "4H"
    assert fs.has("ema_3")
    assert fs.get("ema_3").value == pytest.approx(5.0)
    # as_of is the last (closed) candle's timestamp: index 5 -> +20h.
    assert fs.as_of == _BASE + timedelta(hours=20)


def test_engine_computes_multiple_emas_together() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(3))
    registry.register(ExponentialMovingAverage(2))
    engine = FeatureEngine(registry)

    fs = engine.compute(series_from_prices([2, 4, 6]), ["ema_3", "ema_2"])

    # ema_3 over [2,4,6] is exactly period -> seed SMA = mean = 4.0 (independent).
    assert fs.get("ema_3").value == pytest.approx(mean([2, 4, 6]))
    # ema_2 over [2,4,6] = 5.0 (hand-calculated above).
    assert fs.get("ema_2").value == pytest.approx(5.0)
    # Deterministic order follows the requested order.
    assert list(fs.features.keys()) == ["ema_3", "ema_2"]


def test_engine_deduplicates_requested_names() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(3))
    engine = FeatureEngine(registry)

    fs = engine.compute(series_from_prices([1, 2, 3, 4, 5, 6]), ["ema_3", "ema_3"])

    assert list(fs.features.keys()) == ["ema_3"]  # computed once, not twice
    assert fs.get("ema_3").value == pytest.approx(5.0)


def test_engine_includes_insufficient_result_in_feature_set() -> None:
    registry = FeatureRegistry()
    registry.register(ExponentialMovingAverage(5))
    engine = FeatureEngine(registry)

    # 3 closed candles, period 5 -> insufficient, but still a valid FeatureSet.
    fs = engine.compute(series_from_prices([1, 2, 3]), ["ema_5"])
    result = fs.get("ema_5")
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert fs.as_of == _BASE + timedelta(hours=8)  # last closed candle (index 2)


def test_engine_rejects_unknown_feature() -> None:
    engine = FeatureEngine(FeatureRegistry())
    with pytest.raises(ValueError, match="unknown feature"):
        engine.compute(series_from_prices([1, 2, 3]), ["ema_99"])


def test_engine_detects_missing_dependency() -> None:
    class NeedsGhost(BaseFeature):
        name = "needs_ghost"
        category = FeatureCategory.INDICATOR
        dependencies = ("ghost",)

        def compute(self, context: FeatureContext) -> FeatureResult:  # pragma: no cover
            return FeatureResult(self.name, self.category, 0.0)

    registry = FeatureRegistry()
    registry.register(NeedsGhost())
    engine = FeatureEngine(registry)
    with pytest.raises(ValueError, match="unknown feature 'ghost'"):
        engine.compute(series_from_prices([1, 2, 3]), ["needs_ghost"])


def test_engine_detects_cycle() -> None:
    class FeatA(BaseFeature):
        name = "a"
        category = FeatureCategory.INDICATOR
        dependencies = ("b",)

        def compute(self, context: FeatureContext) -> FeatureResult:  # pragma: no cover
            return FeatureResult(self.name, self.category, 0.0)

    class FeatB(BaseFeature):
        name = "b"
        category = FeatureCategory.INDICATOR
        dependencies = ("a",)

        def compute(self, context: FeatureContext) -> FeatureResult:  # pragma: no cover
            return FeatureResult(self.name, self.category, 0.0)

    registry = FeatureRegistry()
    registry.register(FeatA())
    registry.register(FeatB())
    engine = FeatureEngine(registry)
    with pytest.raises(ValueError, match="cycle detected"):
        engine.compute(series_from_prices([1, 2, 3]), ["a"])


# --- committed BTCUSDT 4H fixture --------------------------------------------


def _fixture_closes() -> list[float]:
    records = json.loads((FIXTURES / "btcusdt_4h.json").read_text())
    return [r["close"] for r in records]


def test_fixture_ema_period_equals_mean_when_period_is_full_length() -> None:
    # 20 closed candles, period 20 -> EMA seeds with the SMA and never smooths,
    # so it equals the arithmetic mean of the closes (independent reference).
    closes = _fixture_closes()
    assert len(closes) == 20
    result = ema_value(closes, 20)
    assert result.value == pytest.approx(mean(closes))
    assert result.value == pytest.approx(42624.5)


def test_fixture_ema_period_one_equals_last_close() -> None:
    closes = _fixture_closes()
    result = ema_value(closes, 1)
    assert result.value == pytest.approx(closes[-1])
    assert result.value == pytest.approx(43350.0)
