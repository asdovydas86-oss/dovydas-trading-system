"""Momentum — speed and acceleration of price change (Tier 2).

Single responsibility: interpret momentum primitives into momentum features.
Category: ``FeatureCategory.MOMENTUM``. Labels use
``fmis.features.types.MomentumRegime``.

Planned features (NOT implemented yet):
    TODO: momentum regime (accelerating / steady / decelerating)
    TODO: MACD histogram slope & rate-of-change
    TODO: RSI slope / recovery-from-extreme
    TODO: momentum divergence flags (price vs. RSI/MACD)
Consumes ``indicators`` results; performs no math in this milestone.
"""

from __future__ import annotations

__all__: list[str] = []
