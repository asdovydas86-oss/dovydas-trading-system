"""Data contract subpackage: normalized OHLCV primitives.

Re-exports the validated `Candle` and `CandleSeries` types so callers can use
`from fmis.data import Candle, CandleSeries`.
"""

from __future__ import annotations

from fmis.data.models import Candle, CandleSeries

__all__ = ["Candle", "CandleSeries"]
