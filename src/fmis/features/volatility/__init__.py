"""Volatility — how much price is moving, and the regime it implies (Tier 2).

Single responsibility: interpret volatility primitives into volatility features.
Category: ``FeatureCategory.VOLATILITY``. Labels use
``fmis.features.types.VolatilityRegime``.

Planned features (NOT implemented yet):
    TODO: volatility regime (low / normal / high / extreme)
    TODO: ATR-based normalized volatility
    TODO: Bollinger Band width / squeeze detection
Consumes ``indicators`` results (ATR, Bollinger Bands); performs no math yet.
"""

from __future__ import annotations

__all__: list[str] = []
