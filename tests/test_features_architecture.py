"""Architecture tests for the Feature Engine skeleton.

These verify the *plumbing* (protocol conformance, registry, FeatureSet
accessors, engine wiring) using a trivial dummy feature. No indicator math is
implemented or tested here — that arrives in the Milestone C computation phase.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.features import (
    BaseFeature,
    Feature,
    FeatureCategory,
    FeatureContext,
    FeatureRegistry,
    FeatureResult,
    FeatureSet,
)
from fmis.features.feature_engine import FeatureEngine


class DummyFeature(BaseFeature):
    """Minimal feature used only to exercise the interfaces (returns a constant)."""

    name = "dummy"
    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def compute(self, context: FeatureContext) -> FeatureResult:
        return FeatureResult(name=self.name, category=self.category, value=1.0)


def _empty_series() -> CandleSeries:
    return CandleSeries(symbol="BTCUSDT", timeframe="4H", candles=())


def _result(name: str, category: FeatureCategory) -> FeatureResult:
    return FeatureResult(name=name, category=category, value=0.0)


# --- protocol / base ---------------------------------------------------------


def test_dummy_feature_satisfies_feature_protocol() -> None:
    assert isinstance(DummyFeature(), Feature)


def test_feature_category_is_technical_only() -> None:
    # Boundary guard: the Feature Engine owns deterministic technical categories
    # ONLY. Non-technical domains (macro/news/on-chain/derivatives/sentiment/AI)
    # are separate future engines and must never appear in this enum.
    members = {c.name for c in FeatureCategory}
    assert members == {
        "INDICATOR",
        "TREND",
        "MOMENTUM",
        "VOLATILITY",
        "VOLUME",
        "MARKET_STRUCTURE",
        "SUPPORT_RESISTANCE",
        "PATTERN",
    }
    for forbidden in ("MACRO", "NEWS", "ONCHAIN", "DERIVATIVES", "SENTIMENT", "AI"):
        assert forbidden not in members


def test_feature_result_is_immutable() -> None:
    result = _result("x", FeatureCategory.TREND)
    with pytest.raises(AttributeError):
        result.value = 5.0  # type: ignore[misc]


def test_feature_result_metadata_is_read_only() -> None:
    result = FeatureResult("x", FeatureCategory.INDICATOR, 1.0, {"period": 3})
    with pytest.raises(TypeError):
        result.metadata["period"] = 99  # type: ignore[index]


def test_feature_result_copies_metadata_defensively() -> None:
    original = {"period": 3}
    result = FeatureResult("x", FeatureCategory.INDICATOR, 1.0, original)
    original["period"] = 99  # mutating the source must not leak into the result
    assert result.metadata["period"] == 3


def test_feature_context_defaults_are_empty() -> None:
    ctx = FeatureContext(primary=_empty_series())
    assert ctx.computed == {}
    assert ctx.sources == {}


# --- FeatureSet accessors ----------------------------------------------------


def test_feature_set_get_has_and_by_category() -> None:
    results = {
        "ema": _result("ema", FeatureCategory.INDICATOR),
        "rsi": _result("rsi", FeatureCategory.INDICATOR),
        "trend": _result("trend", FeatureCategory.TREND),
    }
    fs = FeatureSet(
        symbol="BTCUSDT",
        timeframe="4H",
        as_of=datetime(2024, 1, 1, tzinfo=timezone.utc),
        features=results,
    )
    assert fs.has("ema")
    assert not fs.has("macd")
    assert fs.get("rsi") is results["rsi"]
    assert fs.get("missing") is None
    assert len(fs.by_category(FeatureCategory.INDICATOR)) == 2
    assert len(fs.by_category(FeatureCategory.VOLUME)) == 0


# --- registry ----------------------------------------------------------------


def test_registry_register_get_and_membership() -> None:
    registry = FeatureRegistry()
    feature = DummyFeature()
    registry.register(feature)
    assert "dummy" in registry
    assert len(registry) == 1
    assert registry.get("dummy") is feature
    assert registry.all() == (feature,)


def test_registry_rejects_duplicate_names() -> None:
    registry = FeatureRegistry()
    registry.register(DummyFeature())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyFeature())


def test_registry_by_category() -> None:
    registry = FeatureRegistry()
    registry.register(DummyFeature())
    assert len(registry.by_category(FeatureCategory.INDICATOR)) == 1
    assert len(registry.by_category(FeatureCategory.MOMENTUM)) == 0


# --- engine skeleton ---------------------------------------------------------


def test_engine_holds_its_registry() -> None:
    registry = FeatureRegistry()
    engine = FeatureEngine(registry)
    assert engine.registry is registry


def test_engine_compute_requires_closed_candles() -> None:
    # compute() is implemented as of the EMA vertical slice; with no closed
    # candles there is nothing to stamp a FeatureSet with, so it raises.
    engine = FeatureEngine(FeatureRegistry())
    with pytest.raises(ValueError, match="no closed candles"):
        engine.compute(_empty_series())
