"""Deterministic comparison between consecutive swings of the same kind.

Two functions. `compare_swings` compares one pair; `compare_swing_sequence`
walks an ordered run of swing points and compares each against the previous
point **of its own type**. Both are pure: no state, no side effects, no candles,
and no call to `detect_swings` — this layer consumes `SwingPoint` objects and
nothing else.

**Same-type only.** A swing high is compared to the previous swing high, a low
to the previous low. Comparing a high to a low would mix two different
measurements — one is where price stopped rising, the other where it stopped
falling — and the number it produced would mean nothing.

**Numeric, not directional.** A relation says one price is the larger number.
Turning `SwingType.HIGH` plus `SwingRelation.HIGHER` into "higher high", or into
any statement about trend, is a later layer's decision; the two facts are kept
separate here precisely so that naming stays deliberate.

**Ordering is validated, never repaired.** Input must already be ordered. A
caller handing over unsorted points has a bug, and silently sorting would hide
it while producing comparisons between the wrong pairs.

Ordering contract, which is exactly what `detect_swings` produces:

  * indices are **non-decreasing** across the whole input;
  * within each `SwingType`, indices and timestamps are **strictly** increasing;
  * points sharing an index must share a timestamp.

Global strictness is deliberately *not* required, because a single outside
candle legitimately yields two points at one index — one HIGH and one LOW — and
rejecting that would make this function unable to consume `detect_swings`
output, which is its entire purpose. Per-type strictness is what actually
matters: it is what guarantees each comparison links two distinct candles.
"""

from __future__ import annotations

from collections.abc import Iterable

from fmis.market_structure.models import (
    SwingComparison,
    SwingPoint,
    SwingType,
    _relation_for,
    _validate_key_order,
)

__all__ = ["compare_swings", "compare_swing_sequence"]


def compare_swings(previous: SwingPoint, current: SwingPoint) -> SwingComparison:
    """Compare two swing points of the same type, in the order given.

    Args:
        previous: the earlier swing.
        current: the later swing, at a strictly greater index and timestamp.

    Returns:
        An immutable `SwingComparison` whose ``relation`` is derived from the
        two prices by exact comparison.

    Raises:
        TypeError: either argument is not a `SwingPoint`.
        ValueError: the two points have different `SwingType`, or ``current``
            does not strictly follow ``previous`` in both index and timestamp.

    The arguments are never reordered: passing them the wrong way round raises
    rather than quietly producing the inverse relation.
    """
    return SwingComparison(
        previous=previous,
        current=current,
        relation=_relation_for(previous, current),
    )


def compare_swing_sequence(
    points: Iterable[SwingPoint],
) -> tuple[SwingComparison, ...]:
    """Compare each swing against the previous swing of its own type.

    Args:
        points: swing points already ordered as `detect_swings` returns them.
            Both types may be interleaved in any pattern.

    Returns:
        An immutable tuple of comparisons ordered by ``current.index``. The
        first point of each type produces nothing, so the result holds
        ``max(highs - 1, 0) + max(lows - 1, 0)`` comparisons. Empty input, and
        any input with fewer than two points of either type, yields ``()``.

        **Tie-break:** two comparisons can share a ``current.index`` when one
        candle produced both a HIGH and a LOW. Their order is the order those
        points appeared in the **input** — the walk emits as it encounters — and
        not enum declaration order or any dictionary iteration order. For
        `detect_swings` output that means HIGH before LOW, because that is the
        order the detector emits them.

    Raises:
        TypeError: ``points`` is not iterable, or an element is not a
            `SwingPoint`.
        ValueError: the input is not ordered — a decreasing index or timestamp,
            a repeated index for the same type, or two points sharing an index
            but not a timestamp.

    Pure and deterministic: the input is not mutated, no candle is inspected, and
    detection is never re-run. Appending later points cannot change a comparison
    already produced, because each depends only on two points that were already
    present.
    """
    if isinstance(points, (str, bytes)) or not isinstance(points, Iterable):
        raise TypeError(
            f"points must be an iterable of SwingPoint, got {type(points).__name__}"
        )
    ordered = tuple(points)

    for position, point in enumerate(ordered):
        if not isinstance(point, SwingPoint):
            raise TypeError(
                f"points[{position}] must be a SwingPoint, "
                f"got {type(point).__name__}"
            )

    # Ordering is checked in full before any comparison is built, so an unordered
    # run never yields a partial result. The rule itself lives in
    # `models._validate_key_order`; this call is the point-level projection onto
    # it, and the noun arguments reproduce this layer's original wording exactly.
    _validate_key_order(
        [(point.index, point.timestamp, point.type) for point in ordered],
        subject="points",
        index_noun="index",
        timestamp_noun="timestamp",
        element_noun="point",
    )

    comparisons: list[SwingComparison] = []
    latest: dict[SwingType, SwingPoint] = {}

    for point in ordered:
        previous = latest.get(point.type)
        if previous is not None:
            comparisons.append(compare_swings(previous, point))
        latest[point.type] = point

    return tuple(comparisons)
