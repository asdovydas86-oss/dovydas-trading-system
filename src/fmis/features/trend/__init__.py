"""Trend — direction and strength of the prevailing move (Tier 2).

Single responsibility: interpret indicator/structure primitives into trend
features. Category: ``FeatureCategory.TREND``. Outputs use
``fmis.features.types.TrendDirection`` where a label is appropriate.

Planned features (NOT implemented yet):
    TODO: trend direction (up / down / sideways)
    TODO: trend strength (e.g. ADX-derived)
    TODO: distance to EMA (price displacement from a moving average)
    TODO: EMA alignment / stacking across periods
Consumes results from ``indicators`` via FeatureContext.computed; performs no
math in this milestone.
"""

from __future__ import annotations

__all__: list[str] = []
