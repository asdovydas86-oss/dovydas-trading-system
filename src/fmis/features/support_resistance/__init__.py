"""Support & resistance — significant horizontal price levels (Tier 2).

Single responsibility: identify and score S/R levels from structure. Category:
``FeatureCategory.SUPPORT_RESISTANCE``.

Planned features (NOT implemented yet):
    TODO: support / resistance level candidates (from swing points)
    TODO: level strength / touch count
    TODO: proximity of current price to nearest level
    TODO: role-flip detection (old resistance -> support and vice versa)
Consumes ``market_structure`` results; performs no math in this milestone.
"""

from __future__ import annotations

__all__: list[str] = []
