"""Data contract subpackage: canonical market-data primitives.

Re-exports the validated OHLCV types (`Candle`, `CandleSeries`), the canonical
`ObservationSeries` (non-OHLC timestamped numeric observations), and the
strict-intersection alignment service for observation series.
"""

from __future__ import annotations

from fmis.data.alignment import (
    AlignmentReport,
    AlignmentResult,
    SeriesAlignmentStats,
    align_intersection,
)
from fmis.data.models import Candle, CandleSeries
from fmis.data.observation import ObservationSeries

__all__ = [
    "Candle",
    "CandleSeries",
    "ObservationSeries",
    "align_intersection",
    "AlignmentResult",
    "AlignmentReport",
    "SeriesAlignmentStats",
]
