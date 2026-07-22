"""Deterministic Feature Engine.

Turns validated market data (fmis.data) into a standardized ``FeatureSet`` of
objective, reproducible features that higher layers — strategy, risk, AI
interpretation, reporting — consume. Implements the middle of the project's
core pipeline:

    Data -> deterministic calculations -> structured features -> AI -> decision

Layout (single responsibility per package):

    types.py            core vocabulary: Feature protocol, FeatureResult,
                        FeatureContext, FeatureSet, category/regime enums
    registry.py         FeatureRegistry — discovery / open-closed extension
    feature_engine/     the orchestrator (FeatureEngine)

    indicators/         raw TA primitives (EMA, RSI, MACD, ATR, ADX, BB, VWAP)
    trend/              trend direction & strength, distance-to-EMA
    momentum/           momentum regime derived from momentum indicators
    volatility/         volatility regime (ATR/BB-width based)
    volume/             volume statistics, VWAP-based features
    market_structure/   swing points, HH/HL/LH/LL, break of structure
    support_resistance/ support & resistance levels
    pattern_detection/  candlestick & chart patterns

Two-tier design: ``indicators/`` computes raw numbers; the category packages
turn those numbers into interpreted, grouped features. No calculations exist
yet — this milestone defines only the architecture that will hold them.

Scope boundary: this engine covers deterministic technical-market features only.
Macro, news, on-chain, derivatives, sentiment, and AI-generated interpretation
are explicitly out of scope — each will be its own future engine, and a Context
/ Evidence Aggregation layer will later combine their outputs with this engine's
FeatureSet. Everything produced here is deterministic and reproducible.
"""

from __future__ import annotations

from fmis.features.registry import FeatureRegistry
from fmis.features.types import (
    BaseFeature,
    Feature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
    FeatureSet,
    MomentumRegime,
    TrendDirection,
    VolatilityRegime,
)

__all__ = [
    "FeatureRegistry",
    "BaseFeature",
    "Feature",
    "FeatureCategory",
    "FeatureContext",
    "FeatureResult",
    "FeatureSet",
    "MomentumRegime",
    "TrendDirection",
    "VolatilityRegime",
]
