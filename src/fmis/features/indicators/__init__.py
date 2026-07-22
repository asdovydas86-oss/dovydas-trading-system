"""Indicators — raw technical-analysis primitives (Tier 1).

Single responsibility: compute the raw numeric value(s) of classic indicators
from a price series, with no interpretation. Category: ``FeatureCategory.INDICATOR``.
Interpretation (trend/momentum/volatility regimes) lives in the sibling category
packages that consume these numbers.

Implemented:
    - ExponentialMovingAverage (EMA): configurable period + source, SMA-seeded.

Planned features (NOT implemented yet):
    TODO: EMA slope / distance helpers
    TODO: RSI (+ RSI moving average)
    TODO: MACD -> line / signal / histogram
    TODO: ATR
    TODO: ADX (+ DI+/DI-)
    TODO: Bollinger Bands -> upper / middle / lower / width
    TODO: VWAP
Each implements the fmis.features.types.Feature protocol and returns a
FeatureResult.
"""

from __future__ import annotations

from fmis.features.indicators.ema import ExponentialMovingAverage

__all__ = ["ExponentialMovingAverage"]
