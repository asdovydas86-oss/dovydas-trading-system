"""Deterministic classification rules — the vocabulary of the evidence report.

Every rule here is a pure function over plain values, with no knowledge of
snapshots, features, or candles, so each can be read and tested in isolation.
They classify; they never interpret.

Vocabulary note: `Alignment.UPWARD` / `DOWNWARD` state the **sign of a measured
relationship** — "this value sits above that one" — and carry no market view. A
price above its moving average is an arithmetic fact; whether that is good news
is a judgement this layer does not make and has no vocabulary for.

Two rules exist specifically to prevent a familiar mistake:

  * An RSI zone is `NOT_DIRECTIONAL`. "Overbought" is a description of where a
    bounded oscillator sits, not evidence that price will fall — treating it as
    directional is the oversold-equals-buy fallacy, so the zone is reported and
    then structurally excluded from directional grouping.
  * ATR percent is `NOT_DIRECTIONAL` for the same structural reason: magnitude
    of movement says nothing about its sign.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Comparison",
    "RsiZone",
    "Sign",
    "Alignment",
    "classify_comparison",
    "classify_rsi_zone",
    "classify_sign",
    "alignment_of_comparison",
    "alignment_of_sign",
    "RSI_ZONE_BOUNDS",
]


class Comparison(str, Enum):
    """How one value stands relative to another."""

    ABOVE = "above"
    BELOW = "below"
    EQUAL = "equal"
    UNAVAILABLE = "unavailable"


class RsiZone(str, Enum):
    """Which bounded band an RSI reading falls in. Descriptive only."""

    OVERSOLD_ZONE = "oversold_zone"
    LOWER_NEUTRAL = "lower_neutral"
    NEUTRAL = "neutral"
    UPPER_NEUTRAL = "upper_neutral"
    OVERBOUGHT_ZONE = "overbought_zone"
    UNAVAILABLE = "unavailable"


class Sign(str, Enum):
    """The sign of a signed quantity (e.g. a MACD histogram)."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    ZERO = "zero"
    UNAVAILABLE = "unavailable"


class Alignment(str, Enum):
    """Which way an observation leans, for agreement grouping only.

    `NOT_DIRECTIONAL` marks an observation that is reported but never counted as
    directional evidence. `NEUTRAL` means the comparison was exactly equal.
    """

    UPWARD = "upward"
    DOWNWARD = "downward"
    NEUTRAL = "neutral"
    NOT_DIRECTIONAL = "not_directional"
    UNAVAILABLE = "unavailable"


#: RSI band edges. Written out as named thresholds rather than a lookup table so
#: each boundary's inclusivity is visible at the point it is applied.
RSI_OVERSOLD_EDGE = 30.0
RSI_NEUTRAL_LOWER_EDGE = 45.0
RSI_NEUTRAL_UPPER_EDGE = 55.0
RSI_OVERBOUGHT_EDGE = 70.0

#: The bands in ascending order, for documentation and exhaustiveness checks.
RSI_ZONE_BOUNDS: tuple[tuple[float, RsiZone], ...] = (
    (RSI_OVERSOLD_EDGE, RsiZone.OVERSOLD_ZONE),        # rsi <  30
    (RSI_NEUTRAL_LOWER_EDGE, RsiZone.LOWER_NEUTRAL),   # 30 <= rsi <  45
    (RSI_NEUTRAL_UPPER_EDGE, RsiZone.NEUTRAL),         # 45 <= rsi <= 55
    (RSI_OVERBOUGHT_EDGE, RsiZone.UPPER_NEUTRAL),      # 55 <  rsi <= 70
)


def classify_comparison(left: float | None, right: float | None) -> Comparison:
    """Compare two values exactly.

    No epsilon or tolerance is applied: inventing one would be an undocumented
    judgement about what counts as "the same price", and `EQUAL` on floats is
    rare enough that hiding it would be worse than reporting it.
    """
    if left is None or right is None:
        return Comparison.UNAVAILABLE
    if left > right:
        return Comparison.ABOVE
    if left < right:
        return Comparison.BELOW
    return Comparison.EQUAL


def classify_rsi_zone(rsi: float | None) -> RsiZone:
    """Place an RSI reading in its band.

    The extreme bands are strict — 30 and 70 fall *outside* them — matching the
    usual reading of "below 30" and "above 70". The two inner edges (55 and 70)
    are inclusive so that every reading lands in exactly one band:

        rsi <  30            OVERSOLD_ZONE
        30 <= rsi <  45      LOWER_NEUTRAL
        45 <= rsi <= 55      NEUTRAL
        55 <  rsi <= 70      UPPER_NEUTRAL
        rsi >  70            OVERBOUGHT_ZONE
    """
    if rsi is None:
        return RsiZone.UNAVAILABLE
    if rsi < RSI_OVERSOLD_EDGE:
        return RsiZone.OVERSOLD_ZONE
    if rsi < RSI_NEUTRAL_LOWER_EDGE:
        return RsiZone.LOWER_NEUTRAL
    if rsi <= RSI_NEUTRAL_UPPER_EDGE:
        return RsiZone.NEUTRAL
    if rsi <= RSI_OVERBOUGHT_EDGE:
        return RsiZone.UPPER_NEUTRAL
    return RsiZone.OVERBOUGHT_ZONE


def classify_sign(value: float | None) -> Sign:
    """Classify the sign of a signed quantity."""
    if value is None:
        return Sign.UNAVAILABLE
    if value > 0:
        return Sign.POSITIVE
    if value < 0:
        return Sign.NEGATIVE
    return Sign.ZERO


def alignment_of_comparison(comparison: Comparison) -> Alignment:
    """Map a comparison onto the alignment used for agreement grouping."""
    return {
        Comparison.ABOVE: Alignment.UPWARD,
        Comparison.BELOW: Alignment.DOWNWARD,
        Comparison.EQUAL: Alignment.NEUTRAL,
        Comparison.UNAVAILABLE: Alignment.UNAVAILABLE,
    }[comparison]


def alignment_of_sign(sign: Sign) -> Alignment:
    """Map a sign onto the alignment used for agreement grouping."""
    return {
        Sign.POSITIVE: Alignment.UPWARD,
        Sign.NEGATIVE: Alignment.DOWNWARD,
        Sign.ZERO: Alignment.NEUTRAL,
        Sign.UNAVAILABLE: Alignment.UNAVAILABLE,
    }[sign]
