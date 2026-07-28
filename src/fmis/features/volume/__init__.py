"""Volume — participation behind price moves (Tier 2).

Single responsibility: deterministic volume **measurements**. Category:
``FeatureCategory.VOLUME``.

Implemented (v1a — the volume foundation):
    AverageVolume    mean volume over the `lookback` candles preceding the latest
    RelativeVolume   latest candle volume / that preceding average
    trailing_mean    the shared kernel both use — the single source of truth

Still planned, deliberately not here yet: VWAP and anchored VWAP, OBV,
accumulation/distribution, money-flow measures, volume profile, and any
volume-confirmation flag. Each needs its own milestone.

**Measurements, not conclusions.** Nothing here emits a label, threshold,
direction, or judgement — no "high volume", no "strong", no "confirmed
breakout". Classifying a ratio is a later Volume Evidence milestone's job, and
keeping calculation separate from interpretation is what lets one number serve
markets that read it very differently.

**Shared calculation does not mean identical interpretation.** A relative volume
of 3.0 is computed identically for a 24/7 crypto perpetual, an HKEX share with a
lunch break and a closing auction, a Shanghai listing with price limits, a thinly
traded mining company, and a mega-cap AI stock. What that 3.0 *means* differs
completely across them — session structure, auction mechanics, venue
fragmentation, and reported-volume conventions all differ. The core measures;
market-aware reasoning interprets. See ADR-0010.

Volume validity is inherited from the canonical ``Candle`` contract, which
already rejects negative and non-finite volume and permits zero. This package
does not re-validate it.
"""

from __future__ import annotations

from fmis.features.volume.statistics import AverageVolume, RelativeVolume
from fmis.features.volume.volume_math import required_values, trailing_mean

__all__ = ["AverageVolume", "RelativeVolume", "trailing_mean", "required_values"]
