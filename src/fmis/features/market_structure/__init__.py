"""Market structure — swing points and the shape of price action (Tier 2).

Single responsibility: derive structural features from price. Category:
``FeatureCategory.MARKET_STRUCTURE``.

Swing *detection* is not here: it lives in `fmis.market_structure`, because a
tuple of `SwingPoint` objects is not a `FeatureValue` and so cannot be a
`FeatureResult`. This package is for structural features that *interpret* those
points and can be expressed as a FeatureValue (see ADR-0012).

Planned features (NOT implemented yet):
    TODO: higher-high / higher-low / lower-high / lower-low classification
    TODO: break of structure (BOS) / change of character (CHoCH)
    TODO: consolidation vs. expansion state
Performs no math in this milestone.
"""

from __future__ import annotations

__all__: list[str] = []
