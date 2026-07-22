"""Indicators — raw technical-analysis primitives (Tier 1).

Single responsibility: compute the raw numeric value(s) of classic indicators
from a price series, with no interpretation. Category: ``FeatureCategory.INDICATOR``.
Interpretation (trend/momentum/volatility regimes) lives in the sibling category
packages that consume these numbers.

Implemented:
    - ExponentialMovingAverage (EMA): configurable period + source, SMA-seeded.
    - AverageTrueRange (ATR): Wilder's method, configurable period (default 14).
    - RelativeStrengthIndex (RSI): Wilder's method, configurable period + source.
    - MovingAverageConvergenceDivergence (MACD): fast/slow/signal EMAs, structured
      {macd_line, signal_line, histogram} value.

Planned features (NOT implemented yet):
    TODO: EMA slope / distance helpers
    TODO: RSI moving average
    TODO: ADX (+ DI+/DI-)
    TODO: Bollinger Bands -> upper / middle / lower / width
    TODO: VWAP
Each implements the fmis.features.types.Feature protocol and returns a
FeatureResult.
"""

from __future__ import annotations

from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.macd import MovingAverageConvergenceDivergence
from fmis.features.indicators.rsi import RelativeStrengthIndex

__all__ = [
    "AverageTrueRange",
    "ExponentialMovingAverage",
    "MovingAverageConvergenceDivergence",
    "RelativeStrengthIndex",
]
