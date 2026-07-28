"""`SwingType` and `SwingPoint` — the vocabulary of deterministic swing detection.

A `SwingPoint` is a **located fact**: at this candle, this extreme price was a
local high or low relative to its neighbours. It is not a judgement. It carries
no direction, no trend, no strength, no confidence, and no relationship to any
other swing — comparing swings to each other is what produces higher-high /
lower-low classification, break of structure, and support levels, and all of
that is deliberately a later milestone's work.

``index`` is a position into the **closed** candles of the series it was derived
from (`CandleSeries.closed().candles`), not into the raw series. Detection
operates on closed candles only, so any forming candle is absent before indices
are assigned; a raw index would silently mean something different depending on
whether the last bar had closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = ["SwingType", "SwingPoint"]


class SwingType(str, Enum):
    """Which extreme a swing point marks.

    Two members and no third: a swing is a high or a low. Anything that would
    need a `NEUTRAL`, `BOTH`, or `UNCONFIRMED` member is a different concept —
    an unconfirmed swing is simply not emitted, and a candle that is both a
    swing high and a swing low produces two separate points.
    """

    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """One confirmed local extreme: where it is, when, at what price, which kind.

    Frozen, slotted and hashable, so a detected swing cannot drift, cannot grow
    an attribute it was never given, and can be put in a set or used as a dict
    key when a later layer compares runs.

    Fields, and nothing else:
      * ``index`` — position in the closed-candle sequence it was detected from.
      * ``timestamp`` — that candle's timestamp, carried so a point stays
        meaningful once separated from the series.
      * ``price`` — the candle's ``high`` for a `SwingType.HIGH`, its ``low``
        for a `SwingType.LOW`. The extreme itself, never a midpoint or average.
      * ``type`` — `SwingType.HIGH` or `SwingType.LOW`.

    Deliberately absent: direction, trend, strength, confidence, rank, and any
    reference to a neighbouring swing. Each of those is an interpretation, and
    a field for one would invite filling it before anything can compute it.
    """

    index: int
    timestamp: datetime
    price: float
    type: SwingType

    def __post_init__(self) -> None:
        # bool is an int subclass; an index of True is a programming error.
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError(f"index must be an int, got {type(self.index).__name__}")
        if self.index < 0:
            raise ValueError(f"index cannot be negative, got {self.index}")
        if not isinstance(self.timestamp, datetime):
            raise TypeError(
                f"timestamp must be a datetime, got {type(self.timestamp).__name__}"
            )
        if isinstance(self.price, bool) or not isinstance(self.price, (int, float)):
            raise TypeError(f"price must be a number, got {type(self.price).__name__}")
        if not math.isfinite(self.price):
            raise ValueError("price must be a finite number")
        if not isinstance(self.type, SwingType):
            raise TypeError(f"type must be a SwingType, got {type(self.type).__name__}")
