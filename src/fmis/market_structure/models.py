"""Value types for deterministic swing detection and comparison.

A `SwingPoint` is a **located fact**: at this candle, this extreme price was a
local high or low relative to its neighbours. It is not a judgement. It carries
no direction, no trend, no strength, and no confidence.

A `SwingComparison` adds exactly one more fact — how one swing's price stands
against the previous swing *of the same kind* — expressed as a `SwingRelation`
of HIGHER, LOWER or EQUAL. That is arithmetic about two numbers, not a reading
of the market: break of structure, trend, and support levels all require further
decisions this layer deliberately does not make.

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

__all__ = ["SwingType", "SwingPoint", "SwingRelation", "SwingComparison"]


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


class SwingRelation(str, Enum):
    """How one swing's price stands against the previous swing of its own kind.

    Three members describing **numeric movement only**. `HIGHER` means the later
    price is the larger number — nothing more. It is not "bullish", and on a
    swing low it says only that the low sits at a higher price than the low
    before it.

    Deliberately absent: BULLISH, BEARISH, BREAK, REVERSAL, CONTINUATION, and
    anything carrying confidence or strength. Each of those is a reading of the
    fact rather than the fact, and each needs its own decision record.

    There is also no UNAVAILABLE member. Both swings always exist and always
    carry a finite price, so every comparison resolves — unlike
    `fmis.decision_support.Comparison`, which describes possibly-missing values
    in a different layer and must not be reused here.
    """

    HIGHER = "higher"
    LOWER = "lower"
    EQUAL = "equal"


def _relation_for(previous: SwingPoint, current: SwingPoint) -> SwingRelation:
    """The relation implied by two swings' prices — the one authoritative rule.

    Comparison is **exact** on the stored float values:

        current.price > previous.price  -> HIGHER
        current.price < previous.price  -> LOWER
        otherwise                       -> EQUAL

    No epsilon, tolerance, percentage band, ATR scaling, rounding, or `Decimal`
    conversion, matching `fmis.decision_support.classify_comparison`. The
    repository stores prices as plain validated floats with no tick-size or
    instrument-precision metadata anywhere, so any tolerance would be a locally
    invented judgement about what counts as "the same price". ADR-0013 §4 records
    the limitation that leaves.

    Deliberately **private**. It compares prices and nothing else — it does not
    check that the two swings share a type, or that ``current`` actually follows
    ``previous``. Exposing it publicly would offer a plausible-looking shortcut
    that silently bypasses every invariant `SwingComparison` exists to enforce.
    Callers use `compare_swings`, which validates. Defined once here and used by
    both `SwingComparison.__post_init__` and `compare_swings`, so the rule has
    exactly one implementation.
    """
    if current.price > previous.price:
        return SwingRelation.HIGHER
    if current.price < previous.price:
        return SwingRelation.LOWER
    return SwingRelation.EQUAL


@dataclass(frozen=True, slots=True)
class SwingComparison:
    """Two same-kind swings and how their prices compare. Nothing more.

    ``previous`` and ``current`` are the two `SwingPoint` objects, kept whole so
    a consumer can see index, timestamp and price without a lookup. ``relation``
    is the arithmetic result, and is **validated against the prices** rather than
    trusted: an object claiming HIGHER when the price fell cannot be constructed.

    Invariants, all enforced on construction:
      * both points are `SwingPoint` objects;
      * both have the **same** `SwingType` — a high is never compared to a low;
      * ``current.index > previous.index``;
      * ``current.timestamp > previous.timestamp``;
      * ``relation`` equals the exact price comparison (see `compare_swings`).

    The ordering checks reject reversed arguments rather than silently swapping
    them. "Previous" and "current" are the caller's claim about direction of
    time, and quietly reordering would turn a caller's mistake into a plausible
    but wrong answer.

    Frozen, slotted and hashable: a comparison is a fact about two fixed points
    and cannot drift, and it can be put in a set when a later layer diffs runs.

    Deliberately absent: any label combining type and relation. A swing high that
    is HIGHER than the previous swing high is commonly called a "higher high",
    but that name is an interpretation; this type keeps ``type`` and ``relation``
    as two separate facts so a later layer can name them deliberately.
    """

    previous: SwingPoint
    current: SwingPoint
    relation: SwingRelation

    def __post_init__(self) -> None:
        for name, value in (("previous", self.previous), ("current", self.current)):
            if not isinstance(value, SwingPoint):
                raise TypeError(
                    f"{name} must be a SwingPoint, got {type(value).__name__}"
                )
        if not isinstance(self.relation, SwingRelation):
            raise TypeError(
                f"relation must be a SwingRelation, got {type(self.relation).__name__}"
            )
        if self.previous.type is not self.current.type:
            raise ValueError(
                "previous and current must have the same SwingType, got "
                f"{self.previous.type.value!r} and {self.current.type.value!r}"
            )
        if self.current.index <= self.previous.index:
            raise ValueError(
                f"current.index ({self.current.index}) must be greater than "
                f"previous.index ({self.previous.index})"
            )
        if self.current.timestamp <= self.previous.timestamp:
            raise ValueError(
                f"current.timestamp ({self.current.timestamp.isoformat()}) must be "
                f"later than previous.timestamp ({self.previous.timestamp.isoformat()})"
            )
        expected = _relation_for(self.previous, self.current)
        if self.relation is not expected:
            raise ValueError(
                f"relation {self.relation.value!r} does not match the prices "
                f"({self.previous.price} -> {self.current.price}); "
                f"expected {expected.value!r}"
            )
