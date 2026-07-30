"""The safe pipeline boundary: identity-preserving wrappers over existing functions.

Three functions, one per stage of the existing candle-derived pipeline. Each one
does exactly three things:

    1. take the identity from its input,
    2. call the **existing** context-free production function, unchanged,
    3. re-wrap the result under that same identity object.

**Nothing analytical happens here.** Swing detection, comparison, labelling,
sequence grouping, structural-state derivation, structural-trend derivation,
ordering validation, outside-bar handling and prefix stability all keep their single
implementation in `fmis.market_structure` and `fmis.structural_trend`. This module
performs no arithmetic, reads no candle field, names no state or trend member, and
re-implements no rule — all enforced by AST tests, so a future "small optimisation"
that inlines a step fails the suite rather than quietly creating a second source of
truth.

Because the payload is passed straight through, **adding context cannot change a
result**. That is proved rather than claimed: the equivalence tests compare these
wrappers' payloads against the bare functions' returns across every fixture class,
including empty, insufficient-structure, each trend outcome, each sequence state,
and outside-bar-derived structure.

**Identity is carried by reference, never rebuilt.** A wrapper that reconstructed an
equal identity would pass every `==` test while severing the link to the series the
payload came from, so propagation is by object identity and the tests assert `is`.

**There is no argument through which identity can be substituted.** None of these
functions takes an identity parameter: the only place identity can come from is the
input, which is what makes silent replacement unrepresentable rather than merely
discouraged.

Entry to the safe pipeline is `contextual_structural_swings`, which is also the only
function here that touches a `CandleSeries` — and it reads `symbol` and `timeframe`
only, never a price. A future candle-consuming sibling (Level-Crossing) joins the
same contract through `require_same_identity`, which accepts a `CandleSeries` and a
`ContextualSeries` interchangeably, and needs to import nothing from this module.
"""

from __future__ import annotations

from fmis.data import CandleSeries
from fmis.market_structure import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    StructuralSequenceStateSnapshot,
    StructuralSwing,
    compare_swing_sequence,
    derive_structural_sequence_state_history,
    detect_swings,
    label_swing_sequence,
)
from fmis.series_context.models import ContextualSeries, _carry
from fmis.structural_trend import (
    StructuralTrendSnapshot,
    derive_structural_trend_history,
)

__all__ = [
    "contextual_structural_swings",
    "contextual_structural_state_history",
    "contextual_structural_trend_history",
]


def contextual_structural_swings(
    series: CandleSeries,
    *,
    left_bars: int = DEFAULT_LEFT_BARS,
    right_bars: int = DEFAULT_RIGHT_BARS,
) -> ContextualSeries[StructuralSwing]:
    """Enter the safe pipeline: a `CandleSeries` in, labelled structure out, in context.

    Args:
        series: the candle series to derive structure from. Its `identity`
            projection becomes the result's identity.
        left_bars: forwarded verbatim to `detect_swings`.
        right_bars: forwarded verbatim to `detect_swings`.

    Returns:
        A `ContextualSeries` whose payload is exactly
        ``label_swing_sequence(compare_swing_sequence(detect_swings(...)))`` — the
        same tuple, in the same order, that the context-free composition returns.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`.
        ValueError: whatever `detect_swings` raises for its own parameters.

    Detection, comparison and labelling are **delegated in full**. This function
    composes three existing production calls and adds no rule of its own; the
    plateau policy, the confirmation window, the exact price comparison, the label
    mapping and the equal-index order convention are all unchanged and untouched.

    Identity is read from ``series.symbol`` and ``series.timeframe`` through the
    `CandleSeries.identity` projection — never inferred from prices, never inferred
    from timestamps, and never supplied by the caller.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(
            f"series must be a CandleSeries, got {type(series).__name__}"
        )
    return ContextualSeries(
        identity=series.identity,
        values=label_swing_sequence(
            compare_swing_sequence(
                detect_swings(series, left_bars=left_bars, right_bars=right_bars)
            )
        ),
    )


def contextual_structural_state_history(
    structures: ContextualSeries[StructuralSwing],
) -> ContextualSeries[StructuralSequenceStateSnapshot]:
    """The structural sequence state history, in context.

    Args:
        structures: a `ContextualSeries` of `StructuralSwing`, as
            `contextual_structural_swings` returns.

    Returns:
        A `ContextualSeries` under the **same identity object**, whose payload is
        exactly ``derive_structural_sequence_state_history(structures.values)``.

    Raises:
        TypeError: ``structures`` is not a `ContextualSeries`, or its payload is
            rejected by the delegate.
        ValueError: the run is not ordered — raised by the delegate, with its
            message unchanged.

    Grouping, atomic outside-bar resolution, `INSUFFICIENT_STRUCTURE` recording,
    ordering validation and prefix stability are **entirely the delegate's**. This
    wrapper adds no validation of its own beyond the envelope type, so an ordering
    error surfaces with the exact message and position the context-free function
    already produced.
    """
    _require_envelope(structures, name="structures")
    return _carry(
        structures, derive_structural_sequence_state_history(structures.values)
    )


def contextual_structural_trend_history(
    snapshots: ContextualSeries[StructuralSequenceStateSnapshot],
) -> ContextualSeries[StructuralTrendSnapshot]:
    """The structural trend history, in context.

    Args:
        snapshots: a `ContextualSeries` of `StructuralSequenceStateSnapshot`, as
            `contextual_structural_state_history` returns.

    Returns:
        A `ContextualSeries` under the **same identity object**, whose payload is
        exactly ``derive_structural_trend_history(snapshots.values)``.

    Raises:
        TypeError: ``snapshots`` is not a `ContextualSeries`, or its payload is
            rejected by the delegate.
        ValueError: the run is not ordered — raised by the delegate, unchanged.

    The trend policy — which states are directional, the sustained threshold,
    transparency of non-directional states, one-shift invalidation, and the
    `NEUTRAL`/`INDETERMINATE` distinction — lives entirely in
    `fmis.structural_trend` and is not restated, parameterised or second-guessed
    here.
    """
    _require_envelope(snapshots, name="snapshots")
    return _carry(snapshots, derive_structural_trend_history(snapshots.values))


def _require_envelope(subject: object, *, name: str) -> None:
    """Reject a bare payload passed where an envelope belongs.

    Without this, a caller could pass the context-free tuple straight in and get a
    `TypeError` from deep inside a delegate — or, worse, silently lose the identity
    the whole contract exists to carry. Validating the envelope **before** any
    analytical work also keeps failures deterministic and partial results
    impossible (design §5, principle 11).

    Deliberately **private**: it is an argument check, not a public predicate.
    """
    if not isinstance(subject, ContextualSeries):
        raise TypeError(
            f"{name} must be a ContextualSeries, got {type(subject).__name__}"
        )
