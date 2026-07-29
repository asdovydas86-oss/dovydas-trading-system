"""Naming an established structural fact: `SwingType` + `SwingRelation`.

Two functions. `label_swing` names one comparison; `label_swing_sequence` names
an ordered run of them. Both are pure: no state, no side effects, no candles, no
call to `detect_swings` or `compare_swing_sequence` — this layer consumes
`SwingComparison` objects and nothing else.

**Naming is not interpreting.** `HIGHER_HIGH` says the current swing is a high
whose price is numerically above the previous high, and stops there. It does not
say the market is trending up, that a breakout or break of structure occurred,
that continuation is likely, or that anything should be bought — and
`LOWER_LOW` is not a short signal. Trend, BOS, CHoCH, regime, support,
resistance and liquidity each require decisions this layer does not make, and
each is a later milestone.

**Equal structure is first-class.** `EQUAL_HIGH` and `EQUAL_LOW` are never
folded into HIGHER or LOWER, and are never renamed "double top", "double
bottom", "consolidation", "support" or "liquidity". A retest at exactly the
previous level is its own fact; what it *means* is somebody else's decision.

Equality is inherited, not redefined: the relation was already fixed by
`SwingComparison` using exact stored-float comparison (ADR-0013 §4). No epsilon,
tick-size equivalence, rounding, ATR tolerance or percentage band is introduced
here — this layer never touches a price at all.

**Order is preserved, never repaired.** Input order is the output order. A
caller handing over an unordered run has a bug, and sorting it silently would
hide that while presenting the result as if it were sequential.

That includes **equal indices**: where two comparisons share a ``current.index``
their relative order is inherited from the input, and this layer never imposes
HIGH-before-LOW of its own. HIGH-before-LOW is a property of `detect_swings`,
not a rule here — `compare_swing_sequence` accepts a valid run in either order,
so a LOW-before-HIGH pair is legitimate input and is labelled in that order.

Ordering contract, mirroring what `compare_swing_sequence` produces, checked on
each comparison's ``current`` point by the shared `models._validate_current_point_order`
so that every layer consuming an ordered run inherits one rule rather than
growing a second, subtly different one:

  * ``current.index`` is **non-decreasing** across the whole input;
  * ``current.timestamp`` is non-decreasing with it;
  * comparisons sharing a ``current.index`` must share its timestamp;
  * within each `SwingType`, ``current.index`` and ``current.timestamp`` are
    **strictly** increasing.

Global strictness is deliberately not required: a single outside candle produces
a HIGH and a LOW at one index, so `compare_swing_sequence` legitimately emits two
comparisons sharing a ``current.index``. Rejecting that would break the very
composition this layer exists for. Per-type strictness is what matters, and it
is also what rejects a duplicated comparison.
"""

from __future__ import annotations

from collections.abc import Iterable

from fmis.market_structure.models import (
    StructuralSwing,
    SwingComparison,
    _label_for,
    _validate_current_point_order,
)

__all__ = ["label_swing", "label_swing_sequence"]


def label_swing(comparison: SwingComparison) -> StructuralSwing:
    """Name one comparison.

    Args:
        comparison: a validated `SwingComparison`. Its ``current.type`` and
            ``relation`` determine the label; the previous point's type is not
            consulted, because `SwingComparison` already guarantees both points
            share a type.

    Returns:
        An immutable `StructuralSwing` holding the comparison and its label.

    Raises:
        TypeError: ``comparison`` is not a `SwingComparison`.

    Pure: no state, no side effects, and nothing beyond the supplied comparison
    is read.
    """
    if not isinstance(comparison, SwingComparison):
        raise TypeError(
            f"comparison must be a SwingComparison, got {type(comparison).__name__}"
        )
    return StructuralSwing(comparison=comparison, label=_label_for(comparison))


def label_swing_sequence(
    comparisons: Iterable[SwingComparison],
) -> tuple[StructuralSwing, ...]:
    """Name an ordered run of comparisons, preserving their order exactly.

    Args:
        comparisons: comparisons already ordered as `compare_swing_sequence`
            returns them. Both swing types may be interleaved.

    Returns:
        An immutable tuple with one `StructuralSwing` per input comparison, in
        the **same order as the input** — including where two comparisons share
        a ``current.index`` because one candle produced both a HIGH and a LOW.
        Empty input yields ``()``.

    Raises:
        TypeError: ``comparisons`` is not iterable, or an element is not a
            `SwingComparison`.
        ValueError: the run is not ordered — a decreasing ``current.index`` or
            timestamp, a repeated ``current`` point for one swing type
            (which also catches a duplicated comparison), or two comparisons
            sharing a ``current.index`` without sharing its timestamp.

    Pure and deterministic: the input is not mutated, no candle is inspected,
    and neither detection nor comparison is re-run. Appending later comparisons
    cannot change a label already produced, because each depends only on the one
    comparison it names.
    """
    if isinstance(comparisons, (str, bytes)) or not isinstance(comparisons, Iterable):
        raise TypeError(
            "comparisons must be an iterable of SwingComparison, "
            f"got {type(comparisons).__name__}"
        )
    ordered = tuple(comparisons)

    for position, comparison in enumerate(ordered):
        if not isinstance(comparison, SwingComparison):
            raise TypeError(
                f"comparisons[{position}] must be a SwingComparison, "
                f"got {type(comparison).__name__}"
            )

    _validate_current_point_order(ordered, "comparisons")

    return tuple(label_swing(comparison) for comparison in ordered)
