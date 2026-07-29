"""The state of the latest HIGH-side and LOW-side structural facts.

One function. `derive_structural_sequence_state` takes an ordered run of
`StructuralSwing` objects, finds the last one of each side, and reports how the
two stand together. It is pure: no state, no side effects, **no candles**, and no
call to `detect_swings`, `compare_swings`, `compare_swing_sequence` or
`label_swing_sequence` — this layer consumes `StructuralSwing` objects and
nothing else.

**Describing is not interpreting.** `SHIFTED_HIGHER` says both structural sides
sit at higher prices than the swings they were each compared against. It does not
say the market is trending up, that it is bullish, that continuation or reversal
is likely, that structure broke, or that anything should be traded.
`CONTRACTED` is not consolidation, `EXPANDED` is not a breakout, and `UNCHANGED`
is not a double top, support, resistance or liquidity. Trend, BOS, CHoCH,
support/resistance and liquidity each need decisions this layer does not make,
and each is a later milestone.

**Both source facts are kept.** The state groups the nine complete label
combinations into five, which is lossy on purpose — so the two `StructuralSwing`
objects that produced it stay on the result. A consumer needing the exact pair
reads ``latest_high.label`` and ``latest_low.label``.

**One side is never enough.** With no labelled HIGH, or no labelled LOW, the
result is `INSUFFICIENT_STRUCTURE` and the side that does exist is still
attached. Deriving a two-sided statement from one side would be fabricating the
other half.

**Outside bars resolve atomically.** One candle can produce both a HIGH-side and
a LOW-side `StructuralSwing` at the same index. The whole supplied run is
evaluated and a single final state derived from both latest sides, so no
intermediate state is ever exposed in which only one half of that candle had
been applied. Exposing one would give artificial meaning to an ordering that is
an artefact of how the pair was emitted.

**The aggregate state is expected to change; that is not repainting.** Every
`StructuralSwing` in the input is settled and prefix-stable — appending later
swings never alters one already produced. The *aggregate* is different by
construction: it is a statement about the latest pair, so a newer confirmed swing
on either side legitimately supersedes it. A new result is a new fact about newer
data, not a revision of an old one. See ADR-0015.

Ordering is validated, never repaired, using the same
`models._validate_current_point_order` rule the labelling layer applies, so this
layer cannot drift into a conflicting policy.
"""

from __future__ import annotations

from collections.abc import Iterable

from fmis.market_structure.models import (
    StructuralSequenceState,
    StructuralSwing,
    SwingType,
    _sequence_state_for,
    _validate_current_point_order,
)

__all__ = ["derive_structural_sequence_state"]


def derive_structural_sequence_state(
    structures: Iterable[StructuralSwing],
) -> StructuralSequenceState:
    """Derive the state of the latest HIGH-side and LOW-side structural facts.

    Args:
        structures: `StructuralSwing` objects already ordered as
            `label_swing_sequence` returns them. Both sides may be interleaved,
            and either may be absent entirely.

    Returns:
        One immutable `StructuralSequenceState` holding the last HIGH-side swing,
        the last LOW-side swing (either may be ``None``), and the state those two
        imply. Empty input yields both sides ``None`` and
        `StructuralSequenceStateType.INSUFFICIENT_STRUCTURE`.

    Raises:
        TypeError: ``structures`` is not iterable, or an element is not a
            `StructuralSwing`.
        ValueError: the run is not ordered — a decreasing ``current`` index or
            timestamp, a repeated ``current`` point for one swing type (which
            also catches a duplicated object), or two entries sharing a
            ``current`` index without sharing its timestamp.

    "Latest" is **position in the supplied run**, not the largest index: the run
    is validated as ordered first, so the two agree, and using position keeps the
    input's own order authoritative rather than re-deriving one.

    The two sides are selected independently and need not share an index, a
    timestamp, or a candle — the latest high and the latest low are usually from
    different bars, and requiring otherwise would discard almost every real pair.

    Pure and deterministic: the input is not mutated or sorted, no candle is
    inspected, and neither detection, comparison nor labelling is re-run.
    """
    if isinstance(structures, (str, bytes)) or not isinstance(structures, Iterable):
        raise TypeError(
            "structures must be an iterable of StructuralSwing, "
            f"got {type(structures).__name__}"
        )
    ordered = tuple(structures)

    for position, structure in enumerate(ordered):
        if not isinstance(structure, StructuralSwing):
            raise TypeError(
                f"structures[{position}] must be a StructuralSwing, "
                f"got {type(structure).__name__}"
            )

    _validate_current_point_order(
        tuple(structure.comparison for structure in ordered), "structures"
    )

    latest: dict[SwingType, StructuralSwing] = {}
    for structure in ordered:
        latest[structure.comparison.current.type] = structure

    latest_high = latest.get(SwingType.HIGH)
    latest_low = latest.get(SwingType.LOW)

    return StructuralSequenceState(
        latest_high=latest_high,
        latest_low=latest_low,
        state=_sequence_state_for(latest_high, latest_low),
    )
