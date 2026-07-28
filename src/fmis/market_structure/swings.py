"""Deterministic swing-point detection over closed candles.

One function, `detect_swings`. It reports where a candle's high was a local
maximum, or its low a local minimum, relative to a fixed number of neighbours on
each side. It classifies nothing beyond that.

Semantics, stated in full because every one of them is a decision:

**Closed candles only.** Detection runs on ``series.closed()``. A forming candle
has a high and low that can still move, so including it would let a reported
swing change on the next tick. Indices in the returned points are positions in
that *closed* sequence.

**A swing needs neighbours on both sides.** Index ``i`` is a candidate only when
``i - left_bars >= 0`` and ``i + right_bars <= n - 1``. The first ``left_bars``
and last ``right_bars`` closed candles therefore never produce a swing.

**Confirmation delay is the point, not a limitation.** A swing at ``i`` is
knowable only once ``right_bars`` further candles have closed. In any finite
series snapshot the newest ``right_bars`` closed candles therefore cannot *yet*
be classified; they become eligible once additional closed candles arrive, so
the confirmation frontier advances with the data. What never changes is a point
already emitted: everything it depends on had closed when it was emitted, which
is what makes detection non-repainting.

**No future candle is ever consulted.** The window is exactly
``[i - left_bars, i + right_bars]``, entirely inside the supplied closed series.
Nothing is extrapolated, and nothing outside that window affects the result.

**Comparison rule — strictly greater on the left, greater-or-equal on the
right** (mirrored for lows):

    swing high at i  <=>  high[i] >  high[j]  for j in [i-left, i-1]
                     and  high[i] >= high[j]  for j in [i+1, i+right]

This asymmetry is what makes **plateaus** (runs of equal highs) resolve to
exactly one point instead of none or several:

  * ``[1, 5, 5, 1]`` with left=right=1 → one swing high, at index 1. Index 2
    fails the strict left test against index 1.
  * Requiring strict on both sides would report *no* swing here at all, silently
    discarding a real structural level; repeated prices are common, not exotic.
  * Requiring ``>=`` on both sides would report every bar of the plateau.

The **first** bar of a plateau wins, which also means the swing confirms as
early as the information allows — index 1 above is settled at index 2, not at
the end of the run.

**Equal highs / equal lows that are separated** are a different thing from a
plateau and both are reported: ``[1, 5, 1, 5, 1]`` with left=right=1 yields two
swing highs, at indices 1 and 3. They are two distinct local maxima that happen
to share a price, and collapsing them would destroy exactly the structure a
later layer wants.

**A candle can be both.** An outside bar whose high exceeds its neighbours and
whose low undercuts them produces two points at the same index, one of each
type.

**Insufficient history is not an error.** Fewer than ``left_bars + 1 +
right_bars`` closed candles yields an empty result, as does an empty series.
"No swing could be confirmed" is a true answer to a well-formed question.
"""

from __future__ import annotations

from fmis.data import CandleSeries
from fmis.market_structure.models import SwingPoint, SwingType

__all__ = ["detect_swings", "required_candles", "DEFAULT_LEFT_BARS",
           "DEFAULT_RIGHT_BARS"]

#: Neighbour counts used when a caller does not choose. Two bars each side is a
#: common, deliberately unremarkable default; it encodes no market opinion, and
#: any lookback is available by passing it explicitly.
DEFAULT_LEFT_BARS = 2
DEFAULT_RIGHT_BARS = 2


def required_candles(left_bars: int, right_bars: int) -> int:
    """Closed candles needed before any swing can be confirmed.

    The candidate itself plus its neighbours on both sides. Exposed so callers,
    docs and tests quote one number rather than each repeating the arithmetic.
    """
    return _require_bars(left_bars, "left_bars") + _require_bars(
        right_bars, "right_bars"
    ) + 1


def _require_bars(value: object, field: str) -> int:
    """A positive int. ``bool`` is rejected explicitly, being an int subclass."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{field} must be at least 1, got {value}")
    return value


def _is_swing_high(highs: list[float], i: int, left: int, right: int) -> bool:
    """Strictly above every left neighbour, at or above every right neighbour."""
    pivot = highs[i]
    if any(pivot <= highs[j] for j in range(i - left, i)):
        return False
    return all(pivot >= highs[j] for j in range(i + 1, i + right + 1))


def _is_swing_low(lows: list[float], i: int, left: int, right: int) -> bool:
    """Strictly below every left neighbour, at or below every right neighbour."""
    pivot = lows[i]
    if any(pivot >= lows[j] for j in range(i - left, i)):
        return False
    return all(pivot <= lows[j] for j in range(i + 1, i + right + 1))


def detect_swings(
    series: CandleSeries,
    *,
    left_bars: int = DEFAULT_LEFT_BARS,
    right_bars: int = DEFAULT_RIGHT_BARS,
) -> tuple[SwingPoint, ...]:
    """Confirmed swing highs and lows in ``series``, ordered by candle index.

    Args:
        series: candles to scan. Only closed candles participate; indices in the
            result are positions in ``series.closed().candles``.
        left_bars: neighbours required strictly beyond the pivot on the left.
        right_bars: neighbours required at-or-beyond the pivot on the right, and
            therefore the confirmation delay in candles.

    Returns:
        An immutable tuple sorted by ``(index, type)``, with `SwingType.HIGH`
        before `SwingType.LOW` when a single candle is both. Empty when fewer
        than `required_candles` closed candles are available.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`, or a bar count is not an
            ``int``.
        ValueError: a bar count is below 1.

    The result is a pure function of the closed candles and the two bar counts:
    the same inputs always give the same output, and extending the series with
    later candles never alters a point already returned.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(
            f"series must be a CandleSeries, got {type(series).__name__}"
        )
    left = _require_bars(left_bars, "left_bars")
    right = _require_bars(right_bars, "right_bars")

    # Closed candles only — idempotent even if the caller already closed them.
    candles = series.closed().candles
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]

    found: list[SwingPoint] = []
    # Candidates are exactly the indices with enough neighbours on both sides,
    # so the window never reaches outside the closed series.
    for index in range(left, len(candles) - right):
        candle = candles[index]
        if _is_swing_high(highs, index, left, right):
            found.append(
                SwingPoint(
                    index=index,
                    timestamp=candle.timestamp,
                    price=candle.high,
                    type=SwingType.HIGH,
                )
            )
        if _is_swing_low(lows, index, left, right):
            found.append(
                SwingPoint(
                    index=index,
                    timestamp=candle.timestamp,
                    price=candle.low,
                    type=SwingType.LOW,
                )
            )

    # Already in this order by construction; sorting states the guarantee
    # explicitly rather than leaving it to depend on the loop above.
    return tuple(sorted(found, key=lambda point: (point.index, point.type.value)))
