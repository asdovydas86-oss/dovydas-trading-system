"""Indicators — raw technical-analysis primitives (Tier 1).

Single responsibility: compute the raw numeric value(s) of classic indicators
from a price series, with no interpretation. Category: ``FeatureCategory.INDICATOR``.
Interpretation (trend/momentum/volatility regimes) lives in the sibling category
packages that consume these numbers.

Planned features (NOT implemented yet — no calculations in this milestone):
    TODO: EMA family (e.g. 20/50/200) -> value + slope
    TODO: RSI (+ RSI moving average)
    TODO: MACD -> line / signal / histogram
    TODO: ATR
    TODO: ADX (+ DI+/DI-)
    TODO: Bollinger Bands -> upper / middle / lower / width
    TODO: VWAP
Each will implement the fmis.features.types.Feature protocol and return a
FeatureResult; nothing here performs math yet.
"""

from __future__ import annotations

__all__: list[str] = []
