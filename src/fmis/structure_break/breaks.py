"""Deterministic break-of-structure derivation over levels and crossing events.

One public function, `derive_structure_breaks`. It consumes the two facts that
already exist — the structural level set and the level-crossing history — and
reports where structure broke.

**No candle is ever read.** This module cannot read one: the package does not
import `fmis.data`, so `Candle` is not a name it can reach. The crossing history
already answers every question a break needs, which is what
`fmis.level_crossing` was built to guarantee.

Semantics, stated in full because every one of them is a decision:

**A break is the first close beyond the reference level for its side, at a bar
where that level was already knowable.** Five conjuncts, each independently
decided in ADR-0020: the crossing is a `CLOSE_BREACH`; its mechanism is not
`ALREADY_BEYOND`; the level carries provenance and the bar is at or after the
level's confirmation bar; the level **is the reference** for its side at that
bar; and it is the **first** such crossing for that level.

**Only a close breaks structure.** A `TOUCH` reached the level without passing
it, and a `WICK_BREACH` passed it and closed back inside — a rejection, not a
break. A wick-based rule also cannot be non-repainting on a forming bar, which
the market-structure review §15 identified as the deciding property. There is
exactly one qualifying kind and it is **not configurable**: a setting would make
every historical break non-reproducible without it.

**The reference is the most recent eligible level on that side**, not the most
extreme. "Most extreme unbroken" is protected-level and liquidity logic, and is
out of scope.

**Eligibility begins at the level's confirmation bar**, ``origin.knowable_from``
— the earliest bar at which the level was knowable at all. A pivot at bar ``o``
is confirmed only once its confirmation window of further candles has closed, so
treating it as the reference before then would let a prefix report a break the
full run does not. That is measured, not theorised: 30 violating prefixes across
40 seeded fixtures under pivot-bar eligibility, and 0 under this rule. See
ADR-0020 §2.4.

**The delay is read off the level, never supplied** (ADR-0024). Each origin
records the window its pivot was confirmed under, so this module cannot be given
a delay that disagrees with detection — the ADR-0020 D1 hazard is not warned
about here, it is unrepresentable. One level set must agree on that window;
mixing two is rejected, because "the most recent eligible level" would stop being
well defined.

**Structure breaks once.** At most one break per level, ever — the earliest
qualifying crossing. A second close beyond an already-broken level is not a
second break, and once the reference is broken with no newer level on that side,
there is simply no further break on that side until a new swing forms.

**Nothing is invalidated.** A break is a fact about a closed bar; nothing later
revises it.

**Order-invariant on both inputs.** Levels and crossings may arrive in any order,
and duplicated crossing events collapse, because the earliest qualifying crossing
per level is selected rather than assumed. Re-validating the crossing run's
canonical order would be a second implementation of a rule `fmis.level_crossing`
already owns.

**Empty input is not an error.** No levels, or no crossings, yields an empty
tuple. "Structure did not break" is a true answer to a well-formed question.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from fmis.level_crossing import (
    CrossingKind,
    CrossingMechanism,
    LevelCrossingEvent,
    LevelSide,
    PriceLevel,
)
from fmis.structure_break.models import StructureBreak, StructureBreakInputError

__all__ = ["derive_structure_breaks"]

#: Explicit ordering rank. **Never** enum definition order, ``.value`` string
#: order or hash order — an ordering contract resting on any of those would
#: change silently when a member was renamed. Matches `fmis.level_crossing`'s own
#: convention without reaching into its private key, which stays private.
_SIDE_RANK: Mapping[LevelSide, int] = MappingProxyType(
    {LevelSide.UPPER: 0, LevelSide.LOWER: 1}
)


def _levels_by_side(
    levels: Sequence[PriceLevel],
) -> dict[LevelSide, list[tuple[int, PriceLevel]]]:
    """Levels grouped by side and ordered by the bar each became eligible.

    Returns ``{side: [(eligible_from, level), …]}`` sorted ascending, which is what
    makes reference lookup a scan rather than a search over the whole set.

    **This is the one place the eligibility rule lives.** Eligibility begins at
    the level's own ``origin.knowable_from`` — the bar at which the pivot became
    knowable — and that value is read from the level, never supplied. The
    arithmetic behind it belongs to `LevelOrigin.knowable_from` and is not
    restated here, so this module holds the *decision* that eligibility starts
    there while `fmis.level_crossing` holds the number.

    Validates, never repairs:

      * a level without provenance cannot be placed in time — rejected;
      * two levels on one side sharing an origin index make "the most recent
        level" ambiguous — rejected;
      * levels whose origins disagree about the confirmation window did not come
        from one detection run — rejected.

    **Why one window is required across the set.** ``eligible_from`` must be
    *strictly increasing* within a side for `_reference`'s binary search to find
    what a linear scan would, and for the reference test to imply eligibility
    without restating it. With one shared window that follows from strictly
    increasing origin indices, which the duplicate check above already forces.
    With mixed windows it does not: a later pivot detected under a shorter window
    can become knowable *before* an earlier one, and "the most recent eligible
    level" stops being well defined. Mixing windows also means mixing detection
    runs over one index space, which no producer in this repository can do.
    Rejecting it keeps a proven property proven instead of silently weakening it.

    `structural_levels` can produce none of the three: it always attaches an
    origin, `fmis.market_structure`'s ordering rule already forces per-type
    strictly increasing indices, and every origin in one run copies the same
    ``right_bars``. All three failures therefore mean a hand-built set, where
    guessing would be inventing behaviour.

    Deliberately **private**: it is the reference-ranking rule, and a public
    version would let a caller rank levels by hand and grow a second contract.
    """
    grouped: dict[LevelSide, list[tuple[int, PriceLevel]]] = {
        LevelSide.UPPER: [],
        LevelSide.LOWER: [],
    }
    seen: dict[tuple[LevelSide, int], PriceLevel] = {}
    window: int | None = None
    window_position = 0

    for position, level in enumerate(levels):
        if not isinstance(level, PriceLevel):
            raise TypeError(
                f"levels[{position}] must be a PriceLevel, got "
                f"{type(level).__name__}"
            )
        origin = level.origin
        if origin is None:
            raise StructureBreakInputError(
                f"levels[{position}] carries no origin ({level.side.value} "
                f"{level.price}); a break needs provenance to place the level "
                "in time"
            )
        if window is None:
            window = origin.confirmation_bars
            window_position = position
        elif origin.confirmation_bars != window:
            raise StructureBreakInputError(
                f"levels[{position}] was confirmed under "
                f"{origin.confirmation_bars} bars but levels[{window_position}] "
                f"under {window}; one level set cannot mix confirmation windows, "
                "because the most recent eligible level would be ambiguous"
            )
        key = (level.side, origin.index)
        if key in seen:
            raise StructureBreakInputError(
                f"levels[{position}] shares origin index {origin.index} with "
                f"another {level.side.value} level; the reference level at that "
                "point would be ambiguous"
            )
        seen[key] = level
        grouped[level.side].append((origin.knowable_from, level))

    for side in grouped:
        grouped[side].sort(key=lambda pair: pair[0])
    return grouped


def _reference(
    ranked: list[tuple[int, PriceLevel]], index: int
) -> PriceLevel | None:
    """The level on one side that is the reference at candle ``index``.

    The **most recent** level whose eligibility has begun — the last entry whose
    ``eligible_from <= index`` in a list already sorted by that key. ``None`` when
    no level on this side is eligible yet, which is the honest answer for the
    start of a series and after a side's only level is still unconfirmed.

    Not the most *extreme* level. That choice is recorded in ADR-0020 §3.4:
    "most extreme unbroken" is protected-level logic and belongs to a layer that
    does not exist.

    **Binary search, not a scan.** An earlier version walked the list, making the
    derivation O(crossings x levels-per-side) — 125 million inner iterations at
    5,000 levels and 50,000 crossings, which the independent review measured. The
    list is sorted by ``eligible_from`` and those values are **strictly
    increasing** within a side (two levels sharing an origin index are rejected by
    `_levels_by_side`), so `bisect_right` finds the same element the scan did,
    exactly, in O(log n). The equivalence is not merely argued: a test compares
    this against a reference linear implementation over an exhaustive small space.

    Deliberately **private**, for the same reason `_levels_by_side` is.
    """
    position = bisect_right(ranked, index, key=lambda pair: pair[0])
    if position == 0:
        return None
    return ranked[position - 1][1]


def derive_structure_breaks(
    levels: Sequence[PriceLevel],
    crossings: Sequence[LevelCrossingEvent],
) -> tuple[StructureBreak, ...]:
    """Every break of structure implied by ``levels`` and ``crossings``.

    Args:
        levels: the structural level set, as `structural_levels` returns. Order is
            **not** part of the contract. Every level must carry provenance, no
            two levels on one side may share an origin index, and every origin
            must record the **same** confirmation window.
        crossings: the crossing history, as `derive_level_crossings` returns.
            Order is **not** part of the contract, and duplicated events collapse.
            Every crossing's level must be present in ``levels``.

    **There is no ``confirmation_bars`` argument, and its absence is the point**
    (ADR-0024). Each level states the window it was confirmed under, on
    ``origin.confirmation_bars``, so this function reads the delay off the data
    that earned it. Until Milestone AH the delay was a required keyword argument
    that lived on none of the inputs (ADR-0020 D1): supplying one that disagreed
    with the ``right_bars`` used for detection silently changed which level was
    the reference at every bar, and so which breaks and which changes of
    character existed, **while raising no error** — 36.1 % of 300 seeded series
    produced materially different breaks under a wrong value, none detected. A
    caller can no longer express that mistake.

    Returns:
        An immutable tuple of `StructureBreak`, ordered by

            (breaking candle index, level side)

        with `LevelSide.UPPER` before `LevelSide.LOWER`, from an explicit rank
        mapping rather than enum or hash order. That key is total, because there
        is at most one break per (bar, side). Empty when nothing broke.

    Raises:
        TypeError: an argument is not a non-string sequence, or an element has
            the wrong type.
        StructureBreakInputError: a level carries no provenance, two levels on one
            side share an origin index, two levels disagree about the confirmation
            window, or a crossing references a level absent from ``levels``.

    The result is a pure function of the two inputs: the same inputs always give
    the same output, permuting either input changes nothing, duplicated crossings
    change nothing, and extending the underlying series never alters a break
    already returned.

    A single bar may produce **two** breaks — one upper, one lower. They share an
    index and a timestamp, and **their order is the level ordering, not a claim
    about which happened first**; OHLC data cannot prove that, and this layer
    inherits ADR-0019 §2.6's refusal to pretend otherwise.

    Pure: no state, no cache, no clock, no randomness, no global registry — and
    no candle.
    """
    if isinstance(levels, (str, bytes)) or not isinstance(levels, Sequence):
        raise TypeError(
            f"levels must be a sequence of PriceLevel, got {type(levels).__name__}"
        )
    if isinstance(crossings, (str, bytes)) or not isinstance(crossings, Sequence):
        raise TypeError(
            "crossings must be a sequence of LevelCrossingEvent, got "
            f"{type(crossings).__name__}"
        )
    # Validate and rank before deriving, so a failure is deterministic and no
    # partial result is ever built.
    ranked = _levels_by_side(levels)
    known = {id(level) for level in levels}

    # The earliest qualifying crossing per level. Keyed by object identity rather
    # than value: two equal-valued levels are already rejected as ambiguous
    # above, so identity is exact here, and it keeps the *supplied* level object
    # attached to the break rather than an equal substitute.
    earliest: dict[int, LevelCrossingEvent] = {}

    for position, crossing in enumerate(crossings):
        if not isinstance(crossing, LevelCrossingEvent):
            raise TypeError(
                f"crossings[{position}] must be a LevelCrossingEvent, got "
                f"{type(crossing).__name__}"
            )
        level = crossing.level
        if id(level) not in known:
            raise StructureBreakInputError(
                f"crossings[{position}] references a level absent from levels "
                f"({level.side.value} {level.price})"
            )
        # Only a close beyond the level breaks structure.
        if crossing.kind is not CrossingKind.CLOSE_BREACH:
            continue
        # A series that began beyond the level records no arrival, so it breaks
        # nothing. Doubly excluded: it can only occur at bar 0, where no
        # structural level is eligible.
        if crossing.mechanism is CrossingMechanism.ALREADY_BEYOND:
            continue
        # Eligibility and recency are **one** test, not two. `_reference`
        # returns the last level whose `eligible_from <= index`, and eligibility
        # values are strictly increasing within a side (two levels sharing an
        # origin index are rejected above, and a mixed confirmation window is
        # rejected with them), so `_reference(...) is level` already implies
        # `level.origin.knowable_from <= crossing.index`. A separate eligibility
        # check would be unreachable code that no test could distinguish — an
        # equivalent mutant by construction.
        if _reference(ranked[level.side], crossing.index) is not level:
            continue
        key = id(level)
        previous = earliest.get(key)
        if previous is None or crossing.index < previous.index:
            earliest[key] = crossing

    found = [StructureBreak(crossing=crossing) for crossing in earliest.values()]
    found.sort(key=_break_key)
    return tuple(found)


def _break_key(subject: StructureBreak) -> tuple[int, int]:
    """The one authoritative ordering key for a break.

    ``(breaking candle index, level side rank)``. Total, because at most one break
    exists per (bar, side): each side has exactly one reference level at a given
    bar, and `fmis.level_crossing` emits at most one event per (candle, level).

    The full level ordering key is deliberately **not** restated here. It is
    private to `fmis.level_crossing` precisely so a second implementation cannot
    drift from it, and this layer does not need it.

    Deliberately **private**, following `_relation_for`, `_label_for` and
    `_level_key` in the packages below.
    """
    return (subject.index, _SIDE_RANK[subject.side])
