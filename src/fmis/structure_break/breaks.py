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

**Eligibility begins at the level's confirmation bar**, ``origin.index +
confirmation_bars`` — the earliest bar at which the level was knowable at all. A
pivot at bar ``o`` is confirmed only once ``confirmation_bars`` further candles
have closed, so treating it as the reference before then would let a prefix
report a break the full run does not. That is measured, not theorised: 30
violating prefixes across 40 seeded fixtures under pivot-bar eligibility, and 0
under this rule. See ADR-0020 §2.4.

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


def _require_confirmation_bars(value: object) -> int:
    """A non-negative int. ``bool`` is rejected explicitly, being an int subclass.

    Zero is permitted and means "a level is eligible at its own pivot bar". That
    is only correct for levels whose provenance did not come from a confirmation
    window, so it is allowed rather than blessed — and the module docstring says
    what it costs.

    There is deliberately **no default**. The caller already chose ``right_bars``
    when detecting swings, and a default would silently bind this layer to
    `DEFAULT_RIGHT_BARS` and be wrong for anyone who chose otherwise — the exact
    failure a default is supposed to prevent. Making it required makes the
    coupling visible at every call site.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"confirmation_bars must be an int, got {type(value).__name__}"
        )
    if value < 0:
        raise ValueError(f"confirmation_bars cannot be negative, got {value}")
    return value


def _levels_by_side(
    levels: Sequence[PriceLevel], confirmation_bars: int
) -> dict[LevelSide, list[tuple[int, PriceLevel]]]:
    """Levels grouped by side and ordered by the bar each became eligible.

    Returns ``{side: [(eligible_from, level), …]}`` sorted ascending, which is what
    makes reference lookup a scan rather than a search over the whole set.

    **This is the one place the eligibility arithmetic lives.**
    ``eligible_from = origin.index + confirmation_bars`` is computed here and
    nowhere else, so `derive_structure_breaks` never restates it: the reference
    test already implies it (see there). Because two levels on one side may not
    share an origin index, eligibility values are **strictly increasing** within a
    side, which is what makes that implication exact.

    Validates, never repairs:

      * a level without provenance cannot be placed in time — rejected;
      * two levels on one side sharing an origin index make "the most recent
        level" ambiguous — rejected.

    `structural_levels` can produce neither: it always attaches an origin, and
    `fmis.market_structure`'s ordering rule already forces per-type strictly
    increasing indices. Both failures therefore mean a hand-built set, where
    guessing would be inventing behaviour.

    Deliberately **private**: it is the reference-ranking rule, and a public
    version would let a caller rank levels by hand and grow a second contract.
    """
    grouped: dict[LevelSide, list[tuple[int, PriceLevel]]] = {
        LevelSide.UPPER: [],
        LevelSide.LOWER: [],
    }
    seen: dict[tuple[LevelSide, int], PriceLevel] = {}

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
        key = (level.side, origin.index)
        if key in seen:
            raise StructureBreakInputError(
                f"levels[{position}] shares origin index {origin.index} with "
                f"another {level.side.value} level; the reference level at that "
                "point would be ambiguous"
            )
        seen[key] = level
        grouped[level.side].append((origin.index + confirmation_bars, level))

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
    *,
    confirmation_bars: int,
) -> tuple[StructureBreak, ...]:
    """Every break of structure implied by ``levels`` and ``crossings``.

    Args:
        levels: the structural level set, as `structural_levels` returns. Order is
            **not** part of the contract. Every level must carry provenance, and
            no two levels on one side may share an origin index.
        crossings: the crossing history, as `derive_level_crossings` returns.
            Order is **not** part of the contract, and duplicated events collapse.
            Every crossing's level must be present in ``levels``.
        confirmation_bars: the confirmation delay used when the underlying swings
            were detected — the same ``right_bars`` passed to `detect_swings`.
            **Required, with no default**, because it lives on none of the inputs
            (ADR-0020 deferred question D1) and a default would silently be wrong
            for any caller who chose a different lookback.

    Returns:
        An immutable tuple of `StructureBreak`, ordered by

            (breaking candle index, level side)

        with `LevelSide.UPPER` before `LevelSide.LOWER`, from an explicit rank
        mapping rather than enum or hash order. That key is total, because there
        is at most one break per (bar, side). Empty when nothing broke.

    Raises:
        TypeError: an argument is not a non-string sequence, an element has the
            wrong type, or ``confirmation_bars`` is not an ``int``.
        ValueError: ``confirmation_bars`` is negative.
        StructureBreakInputError: a level carries no provenance, two levels on one
            side share an origin index, or a crossing references a level absent
            from ``levels``.

    The result is a pure function of the two inputs and the confirmation delay:
    the same inputs always give the same output, permuting either input changes
    nothing, duplicated crossings change nothing, and extending the underlying
    series never alters a break already returned.

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
    bars = _require_confirmation_bars(confirmation_bars)

    # Validate and rank before deriving, so a failure is deterministic and no
    # partial result is ever built.
    ranked = _levels_by_side(levels, bars)
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
        # origin index are rejected above), so `_reference(...) is level` already
        # implies `level.origin.index + bars <= crossing.index`. A separate
        # eligibility check would be unreachable code that no test could
        # distinguish — an equivalent mutant by construction. The arithmetic it
        # would restate lives once, in `_levels_by_side`.
        if _reference(ranked[level.side], crossing.index) is not level:
            continue
        key = id(level)
        previous = earliest.get(key)
        if previous is None or crossing.index < previous.index:
            earliest[key] = crossing

    found = [
        StructureBreak(
            crossing=crossing,
            eligible_from=crossing.level.origin.index + bars,
        )
        for crossing in earliest.values()
    ]
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
