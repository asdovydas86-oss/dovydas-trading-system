"""Data contract subpackage: canonical market-data primitives.

Re-exports the validated OHLCV types (`Candle`, `CandleSeries`), the canonical
`ObservationSeries` (non-OHLC timestamped numeric observations), and the pure
`candle_series_to_observations` reduction that turns one candle field into an
`ObservationSeries`.

Alignment is **not** here: it is a temporal-comparison *policy*, not a canonical
model, and lives in the sibling package `fmis.alignment` (see ADR-0002). Keeping
this package free of alignment preserves it as a pure canonical kernel and keeps
downstream layers (e.g. `fmis.features`) from importing alignment transitively.
"""

from __future__ import annotations

from fmis.data.models import Candle, CandleSeries
from fmis.data.observation import ObservationSeries
from fmis.data.reduction import CandleField, candle_series_to_observations

__all__ = [
    "Candle",
    "CandleSeries",
    "ObservationSeries",
    "CandleField",
    "candle_series_to_observations",
]
