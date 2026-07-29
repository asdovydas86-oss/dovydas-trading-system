"""The structural trend over a run of structural sequence state snapshots.

Two functions. `derive_structural_trend` answers "what is the trend now?" and
`derive_structural_trend_history` answers "what was it at every snapshot?". Both
are pure: no state, no side effects, **no candles**, and no call to
`detect_swings`, `compare_swings`, `compare_swing_sequence`, `label_swing`,
`label_swing_sequence`, `derive_structural_sequence_state` or
`derive_structural_sequence_state_history` — this layer consumes
`StructuralSequenceStateSnapshot` objects and nothing else.

**The policy, in one paragraph.** Exactly two of the six
`StructuralSequenceStateType` members say both structural sides moved the same way
in price: `SHIFTED_HIGHER` and `SHIFTED_LOWER` (ADR-0015 §2). Those are the only
directional evidence available, and this layer accumulates them. `EXPANDED`,
`CONTRACTED`, `UNCHANGED` and `INSUFFICIENT_STRUCTURE` are **transparent** — they
neither advance nor invalidate a run, because none of them is evidence *against* a
direction, and treating one as though it were would be a market claim. A run of
`MINIMUM_DIRECTIONAL_SHIFTS` same-direction shifts is sustained; a single opposing
shift invalidates it immediately and restarts the count in the new direction.

**Summarising is not forecasting.** `SUSTAINED_HIGHER` says the same two-sided
shift happened more than once with nothing reversing it in between. It does not
say the market is trending up, that it is bullish or strong, that continuation is
likely, that structure broke, or that anything should be traded. There is
deliberately no confidence, score, strength, rank, duration or probability — each
would be a reading of the run rather than the run, and each needs its own decision
record.

**Ambiguity is reported, never resolved.** A history whose shifts alternate never
reaches the minimum, and the result is `NEUTRAL` rather than the latest direction.
`NEUTRAL` (evidence exists on both sides and conflicts) and `INDETERMINATE`
(evidence is absent) are kept distinct, because folding them together would make a
choppy market indistinguishable from a quiet one.

**Persistence is unconditional, and the limitation is stated.** A sustained trend
survives any number of non-directional snapshots. The consequence is real: a trend
established once and followed by five hundred contracting snapshots still reads as
sustained. Every alternative needs an arbitrary decay constant this layer has no
basis for, and a wrong constant would be invisible; so the guarantee is kept
simple and the limitation is documented instead. A consumer that needs recency has
every snapshot's ``index`` and ``timestamp``.

**Prefix stability — the exact guarantee.** For any snapshot history ``h`` and any
``k``, ``derive_structural_trend_history(h[:k])`` equals
``derive_structural_trend_history(h)[:k]``. Composed with ADR-0016 §6, the trend
history is therefore prefix-stable under **candle-series extension** and under
**complete structural-group extension**.

It is **not** stable under an arbitrary cut inside a same-candle HIGH/LOW group —
inherited verbatim from ADR-0016 §7, neither weakened nor repaired here. Nor is
anything claimed across two different `detect_swings` parameterisations, or across
two different values of `MINIMUM_DIRECTIONAL_SHIFTS`. And prefix stability says an
already-emitted reading never changes; it does **not** say the trend keeps its
value, since a later opposing shift may invalidate it — that is the policy
working, not instability.

Ordering is validated, never repaired, by
`models._validate_snapshot_history_order`, whose docstring records why a snapshot
history's rule is genuinely stricter than the swing run's rather than a copy of it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fmis.market_structure import (
    StructuralSequenceStateSnapshot,
    StructuralSequenceStateType,
)
from fmis.structural_trend.models import (
    MINIMUM_DIRECTIONAL_SHIFTS,
    StructuralTrendSnapshot,
    StructuralTrendType,
    _is_directional_state,
    _trend_for_directional_state,
    _validate_snapshot_history_order,
)

__all__ = ["derive_structural_trend", "derive_structural_trend_history"]


@dataclass(frozen=True, slots=True)
class _Run:
    """The accumulator: the current run of same-direction shifts, and its history.

    ``state`` is the directional `StructuralSequenceStateType` the current run is
    made of, or ``None`` before any shift has been seen. The state member itself is
    carried rather than a separate direction enum, so this layer invents no third
    vocabulary for something ADR-0015 already named.

    ``length`` is how many shifts the current run contains. ``contested`` records
    whether any shift has ever opposed the run then current, and is **monotone** —
    once true it never returns to false, because `INDETERMINATE` means "not enough
    evidence yet" and that description becomes permanently false the moment
    conflicting evidence exists.

    Deliberately **private**, and deliberately absent from
    `StructuralTrendSnapshot`. ``length`` exposed publicly would be a strength
    score by another name, and ``contested`` is a fact about a whole prefix rather
    than about the one snapshot a public type describes.

    Frozen and slotted: the fold replaces the accumulator, never mutates it, so a
    partially-updated run cannot be observed.
    """

    state: StructuralSequenceStateType | None
    length: int
    contested: bool


_INITIAL_RUN = _Run(state=None, length=0, contested=False)


def _advance(run: _Run, state: StructuralSequenceStateType) -> _Run:
    """Fold one state into the run — the one authoritative step rule.

    Three directional cases and one transparent case:

      * no run yet — the run starts at this state, length 1;
      * same state as the run — the run extends by one;
      * the opposing state — the run is **invalidated**: it restarts at the new
        state with length 1, and the history becomes contested for good;
      * not directional — the run is returned unchanged, which is the persistence
        rule.

    Called by both public functions, so there is exactly one implementation of the
    policy rather than one per API shape.
    """
    if not _is_directional_state(state):
        return run
    if run.state is None:
        return _Run(state=state, length=1, contested=run.contested)
    if state is run.state:
        return _Run(state=state, length=run.length + 1, contested=run.contested)
    return _Run(state=state, length=1, contested=True)


def _classify(run: _Run) -> StructuralTrendType:
    """The trend implied by a run — the one authoritative classification.

    Ordered, and the order carries the policy:

      1. a run that reached `MINIMUM_DIRECTIONAL_SHIFTS` gives its sustained
         member — this is the only way a direction is ever reported;
      2. otherwise a contested history gives `NEUTRAL` — evidence exists on both
         sides and does not resolve;
      3. otherwise `INDETERMINATE` — evidence is absent, not contradictory.

    Exhaustive and disjoint, so there is no catch-all and no case where the
    function must guess.

    Called by both public functions, for the same reason `_advance` is.
    """
    if run.state is not None and run.length >= MINIMUM_DIRECTIONAL_SHIFTS:
        return _trend_for_directional_state(run.state)
    if run.contested:
        return StructuralTrendType.NEUTRAL
    return StructuralTrendType.INDETERMINATE


def _validated(
    snapshots: Iterable[StructuralSequenceStateSnapshot], subject: str
) -> tuple[StructuralSequenceStateSnapshot, ...]:
    """Materialise the input once, check every element, then check the order.

    Validation is complete **before** either public function builds anything, so an
    unordered or ill-typed run yields no partial result.

    The input is materialised into a tuple and otherwise left alone: not mutated,
    not sorted, not re-ordered.
    """
    if isinstance(snapshots, (str, bytes)) or not isinstance(snapshots, Iterable):
        raise TypeError(
            f"{subject} must be an iterable of StructuralSequenceStateSnapshot, "
            f"got {type(snapshots).__name__}"
        )
    ordered = tuple(snapshots)

    for position, snapshot in enumerate(ordered):
        if not isinstance(snapshot, StructuralSequenceStateSnapshot):
            raise TypeError(
                f"{subject}[{position}] must be a "
                "StructuralSequenceStateSnapshot, got "
                f"{type(snapshot).__name__}"
            )

    _validate_snapshot_history_order(ordered, subject)
    return ordered


def derive_structural_trend(
    snapshots: Iterable[StructuralSequenceStateSnapshot],
) -> StructuralTrendType:
    """The structural trend as at the end of a snapshot history.

    Args:
        snapshots: `StructuralSequenceStateSnapshot` objects already ordered as
            `derive_structural_sequence_state_history` returns them.

    Returns:
        One `StructuralTrendType`. Empty input yields
        `StructuralTrendType.INDETERMINATE` — no directional evidence has been
        seen, and none has conflicted.

    Raises:
        TypeError: ``snapshots`` is not iterable, or an element is not a
            `StructuralSequenceStateSnapshot`.
        ValueError: the run is not ordered — a repeated or decreasing ``index``, or
            a repeated or decreasing ``timestamp``.

    This is **not** implemented as ``derive_structural_trend_history(...)[-1]``:
    making the cheap "what is it now" query allocate an entire history is a real
    cost for the most common call (ADR-0016 §10). Both functions fold with the same
    private `_advance` and classify with the same private `_classify`, so there is
    one rule and not two implementations, and their agreement is an
    explicitly-tested equivalence contract rather than a hope.

    Pure and deterministic: the input is not mutated or sorted, no candle is
    inspected, and neither detection, comparison, labelling nor state
    classification is re-run.
    """
    run = _INITIAL_RUN
    for snapshot in _validated(snapshots, "snapshots"):
        run = _advance(run, snapshot.state.state)
    return _classify(run)


def derive_structural_trend_history(
    snapshots: Iterable[StructuralSequenceStateSnapshot],
) -> tuple[StructuralTrendSnapshot, ...]:
    """The structural trend as at every snapshot in a history.

    Args:
        snapshots: `StructuralSequenceStateSnapshot` objects already ordered as
            `derive_structural_sequence_state_history` returns them.

    Returns:
        An immutable tuple with **exactly one** `StructuralTrendSnapshot` per input
        snapshot, in input order. Empty input yields ``()``.

    Raises:
        TypeError: ``snapshots`` is not iterable, or an element is not a
            `StructuralSequenceStateSnapshot`.
        ValueError: the run is not ordered — a repeated or decreasing ``index``, or
            a repeated or decreasing ``timestamp``.

    Totality is deliberate: a snapshot whose trend is `INDETERMINATE` is emitted
    like any other, so the history never starts at an arbitrary point and "nothing
    conclusive yet" stays distinguishable from "no snapshot here" — the same
    reasoning ADR-0016 §5 used for `INSUFFICIENT_STRUCTURE`.

    Each result holds its source snapshot **by identity**, never a copy, so a
    consumer can recover every underlying fact — the state, both latest sides, the
    triggers, and through them every point, index, timestamp and price.

    Prefix-stable: element *j* depends only on ``snapshots[0..j]``. Results are
    rebuilt on every call, so they compare ``==`` across calls but are not
    ``is`` — assert equality, never identity, as ADR-0016 requires of snapshots.

    Pure and deterministic: the input is not mutated or sorted, no candle is
    inspected, and neither detection, comparison, labelling nor state
    classification is re-run.
    """
    ordered = _validated(snapshots, "snapshots")

    history: list[StructuralTrendSnapshot] = []
    run = _INITIAL_RUN
    for snapshot in ordered:
        run = _advance(run, snapshot.state.state)
        history.append(
            StructuralTrendSnapshot(
                trend=_classify(run),
                state_snapshot=snapshot,
            )
        )

    return tuple(history)
