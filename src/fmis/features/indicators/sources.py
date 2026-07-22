"""Shared price-source vocabulary for indicators.

The set of candle price fields an indicator may read as its ``source``. It lives
here — not inside any single indicator — so EMA, RSI, and future indicators
depend on one shared vocabulary rather than on each other.
"""

from __future__ import annotations

__all__ = ["VALID_SOURCES"]

# Candle price fields a feature may use as its `source`.
VALID_SOURCES: tuple[str, ...] = ("open", "high", "low", "close")
