"""The structural sequence state at every candle that changed it.

One function. `derive_structural_sequence_state_history` folds an ordered run of
`StructuralSwing` objects into one immutable snapshot per candle at which
structure changed. It is pure: no state, no side effects, **no candles**, and no
call to `detect_swings`, `compare_swings`, `compare_swing_sequence`,
`label_swing_sequence` or `derive_structural_sequence_state` — this layer
consumes `StructuralSwing` objects and delegates every classification rule.

**Why this exists.** `derive_structural_sequence_state` answers "what is the
structure now?" and its answer is superseded as newer swings confirm
(ADR-0015 §8). That makes it unsuitable as the input to anything defined over a
*sequence*. Without this layer every later consumer — trend, break of structure,
change of character — would derive its own sequencing from the label run, which
is the duplication ADR-0013 §6, ADR-0014 §6 and ADR-0015 §9 each refused. See
ADR-0016.

**Recording is not interpreting.** A snapshot says: at this candle, the latest
HIGH-side and LOW-side facts stood thus. It does not say the structure improved,
weakened, broke, continued or reversed, and a run of snapshots is not a trend.
There is deliberately no transition type, no "changed" flag, no direction and no
magnitude — a consumer comparing two adjacent snapshots' states has every fact
such a reading would need, and the reading itself belongs to a layer that can
state its own conditions.

**Outside bars resolve atomically.** One candle can produce both a HIGH-side and
a LOW-side `StructuralSwing`. Both are applied before that candle's snapshot is
emitted, so no half-applied state is ever exposed — the policy ADR-0015 §7 set
for the single state, carried into the history. Either input order gives the same
snapshot.

**Insufficient structure is recorded, not suppressed.** Until both sides exist
the state is `INSUFFICIENT_STRUCTURE`, and those snapshots are emitted like any
other. "At this candle structure was not yet determinable" is a fact, and
dropping it would make the history silently non-total.

**Prefix stability — the exact guarantee.** The history is prefix-stable under
**candle-series extension** and under **complete structural-group extension**:
appending later candles, or later whole same-candle groups, never alters a
snapshot already produced.

It is **not** stable under an arbitrary cut inside a same-candle HIGH/LOW group.
Taking the HIGH of an outside bar without its LOW yields a different — and
correct — state for that candle, because it is a different input. This cannot
arise from candle growth, since a candle produces both swings of an outside bar
or neither, and it is not detectable either: a HIGH with no matching LOW is a
perfectly legal run, as most candles are not outside bars. The narrower true
claim is documented rather than the broader false one.

Ordering is validated, never repaired, by the same
`models._validate_current_point_order` the labelling layer uses, so this layer
cannot drift into a conflicting policy.
"""

from __future__ import annotations

from collections.abc import Iterable

from fmis.market_structure.models import (
    StructuralSequenceState,
    StructuralSequenceStateSnapshot,
    StructuralSwing,
    SwingType,
    _sequence_state_for,
    _validate_current_point_order,
)

__all__ = ["derive_structural_sequence_state_history"]


def derive_structural_sequence_state_history(
    structures: Iterable[StructuralSwing],
) -> tuple[StructuralSequenceStateSnapshot, ...]:
    """The structural sequence state at every candle that changed it.

    Args:
        structures: `StructuralSwing` objects already ordered as
            `label_swing_sequence` returns them. Both sides may be interleaved,
            and either may be absent entirely.

    Returns:
        An immutable tuple with one `StructuralSequenceStateSnapshot` per distinct
        ``current`` index in the input, in input order. Empty input yields ``()``.
        A candle that produced both a HIGH and a LOW yields **one** snapshot
        holding both as triggers.

    Raises:
        TypeError: ``structures`` is not iterable, or an element is not a
            `StructuralSwing`.
        ValueError: the run is not ordered — a decreasing ``current`` index or
            timestamp, a repeated ``current`` point for one swing type (which
            also catches a duplicated object), or two entries sharing a
            ``current`` index without sharing its timestamp.

    Ordering is validated in full before any snapshot is built, so an unordered
    run yields no partial history.

    A side not confirmed at a candle is **carried forward by identity** from the
    previous snapshot: the same object, never a copy. Only the triggers differ.

    Pure and deterministic: the input is not mutated or sorted, no candle is
    inspected, and neither detection, comparison, labelling nor state
    classification is re-implemented — `models._sequence_state_for` remains the
    one authority for what a pair of sides means.
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

    snapshots: list[StructuralSequenceStateSnapshot] = []
    latest: dict[SwingType, StructuralSwing] = {}
    group: list[StructuralSwing] = []

    def close_group() -> None:
        # Every swing of the candle has been applied before the state is read, so
        # an outside bar never exposes a half-applied intermediate.
        latest_high = latest.get(SwingType.HIGH)
        latest_low = latest.get(SwingType.LOW)
        snapshots.append(
            StructuralSequenceStateSnapshot(
                state=StructuralSequenceState(
                    latest_high=latest_high,
                    latest_low=latest_low,
                    state=_sequence_state_for(latest_high, latest_low),
                ),
                triggers=tuple(group),
            )
        )

    for structure in ordered:
        current = structure.comparison.current
        if group and current.index != group[0].comparison.current.index:
            close_group()
            group = []
        group.append(structure)
        latest[current.type] = structure

    if group:
        close_group()

    return tuple(snapshots)
