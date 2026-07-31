"""Deterministic crossing derivation over closed candles and price levels.

Two public functions. `crossing_kind` answers *how one candle stands against one
level*; `derive_level_crossings` replays a whole candle series against a whole
level set and returns every interaction, in one explicit order.

Semantics, stated in full because every one of them is a decision:

**Closed candles only.** Derivation runs on ``series.closed()``. A forming
candle's high, low and close can still move, and a crossing that can change is
not a fact. Indices in the returned events are positions in that *closed*
sequence, matching `SwingPoint.index` exactly.

**One canonical crossing policy, not a configurable one.** Touch, wick breach and
close breach are three *facts on the event*, not three settings. A configurable
rule would make every historical event non-reproducible without its setting — the
argument the market-structure review §9 uses to keep tolerance out of comparison.
A consumer that only trusts closes filters on `CrossingKind.CLOSE_BREACH`.

**Exact equality is a touch, never a breach.** No epsilon, tick size, rounding or
`Decimal`, inheriting ADR-0013 §4.

**No future candle is ever consulted.** An event at candle ``i`` is a function of
candle ``i``, candle ``i - 1``, and the level set. Nothing reads forward, there is
no confirmation delay, and the result is therefore **exactly prefix-stable**:
deriving over a prefix gives precisely the events of the full derivation whose
index falls inside that prefix, in the same order.

**A candle already beyond a level, whose predecessor was also beyond it, emits
nothing.** Nothing happened; price was already there. Without that rule a level
breached once would re-emit on every later candle.

**Nothing has a lifecycle.** No level is active, spent, protected or invalidated,
and no candle is skipped for preceding a level's origin. Derivation is a pure
geometric predicate over (candles, levels) with no notion of a level being born.
That is deliberate: activation is a policy decision — does a level exist at its
pivot bar, or only once that pivot is *confirmed*? — belonging to the future
Break-of-Structure layer, which can apply it by filtering
``event.index >= event.level.origin.index`` on facts it already holds, without
re-reading a candle. See ADR-0019 §I, deferred question D1.

**Empty input is not an error.** No candles, or no levels, yields an empty tuple.
"No crossing occurred" is a true answer to a well-formed question.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.data import Candle, CandleSeries
from fmis.level_crossing.models import (
    CrossingKind,
    CrossingMechanism,
    DuplicateLevelError,
    LevelCrossingEvent,
    PriceLevel,
    _crossing_kind,
    _is_wholly_beyond,
    _level_key,
)

__all__ = ["crossing_kind", "derive_level_crossings"]


def crossing_kind(candle: Candle, level: PriceLevel) -> CrossingKind | None:
    """How far ``candle`` went against ``level``, or ``None`` if it never reached it.

    Args:
        candle: the bar to test. Its ``high`` faces an `LevelSide.UPPER` level and
            its ``low`` faces a `LevelSide.LOWER` one; ``close`` decides between a
            wick and a close breach. ``open`` is never consulted.
        level: the level to test against.

    Returns:
        `CrossingKind.TOUCH` when the facing extreme equals the level's price
        exactly, `CrossingKind.WICK_BREACH` when the extreme went strictly beyond
        but the close did not, `CrossingKind.CLOSE_BREACH` when the close went
        strictly beyond, and ``None`` when the extreme never reached the level.

    Raises:
        TypeError: ``candle`` is not a `Candle`, or ``level`` is not a
            `PriceLevel`.

    This is **the** authoritative predicate. `derive_level_crossings` calls the
    same rule rather than re-deriving it, and `LevelCrossingEvent` validates
    itself against it, so an event can never claim a kind the derivation would
    not have produced.

    Note the deliberate seam with `derive_level_crossings`: this function answers
    the question for **any** candle in isolation, while the batch additionally
    suppresses a candle whose predecessor already lay wholly beyond the level
    (module docstring). A non-``None`` result here is therefore necessary but not
    sufficient for an event.

    Pure: no state, no cache, no clock, no randomness.
    """
    if not isinstance(candle, Candle):
        raise TypeError(f"candle must be a Candle, got {type(candle).__name__}")
    if not isinstance(level, PriceLevel):
        raise TypeError(f"level must be a PriceLevel, got {type(level).__name__}")
    return _crossing_kind(candle, level)


def _require_distinct(levels: Sequence[PriceLevel]) -> tuple[PriceLevel, ...]:
    """Levels in canonical order, with exact duplicates rejected.

    Sorting by `_level_key` puts equal levels adjacent, so one linear scan finds
    every duplicate. Two levels sharing a price but differing in provenance sort
    adjacently too and are **not** duplicates — the comparison is on the whole
    object, not on the key, precisely so that different-provenance levels at one
    price survive.

    Rejection rather than deduplication follows the repository's
    validate-never-repair rule. `sorted` is stable, but stability is not relied
    on: the key is total over distinct levels, so the order does not depend on it.

    Deliberately **private**: it is an argument check plus the canonical order,
    and a public version would let a caller sort levels by hand and grow a second
    ordering contract.
    """
    ordered = sorted(levels, key=_level_key)
    for position in range(1, len(ordered)):
        if ordered[position] == ordered[position - 1]:
            raise DuplicateLevelError(
                f"levels contains a duplicate level ({ordered[position].side.value} "
                f"{ordered[position].price}); levels must be distinct"
            )
    return tuple(ordered)


def _mechanism_for(
    candle: Candle, previous: Candle | None, level: PriceLevel
) -> CrossingMechanism | None:
    """How the candle came to stand against the level, or ``None`` to emit nothing.

    Three outcomes and one suppression:

      * the level lies within ``[low, high]`` -> `WITHIN_RANGE`;
      * the candle is wholly beyond and there is **no** predecessor ->
        `ALREADY_BEYOND` (the series simply starts there, so no arrival can be
        claimed);
      * the candle is wholly beyond and the predecessor was **not** ->
        `GAPPED_BEYOND`;
      * the candle is wholly beyond and the predecessor was **too** -> ``None``,
        because nothing happened.

    Reads candle ``i`` and candle ``i - 1`` only, which is what makes the whole
    derivation exactly prefix-stable.

    Deliberately **private**: the suppression rule is meaningless without the
    replay that supplies ``previous``, and a public version would invite a caller
    to pass the wrong neighbour.
    """
    if not _is_wholly_beyond(candle, level):
        return CrossingMechanism.WITHIN_RANGE
    if previous is None:
        return CrossingMechanism.ALREADY_BEYOND
    if _is_wholly_beyond(previous, level):
        return None
    return CrossingMechanism.GAPPED_BEYOND


def derive_level_crossings(
    series: CandleSeries, levels: Sequence[PriceLevel]
) -> tuple[LevelCrossingEvent, ...]:
    """Every interaction between ``series``' closed candles and ``levels``.

    Args:
        series: candles to replay. Only closed candles participate; indices in
            the result are positions in ``series.closed().candles``.
        levels: the levels to test against, in any order. Input order is **not**
            part of the contract — the output is canonically ordered — and exact
            duplicates are rejected.

    Returns:
        An immutable tuple of `LevelCrossingEvent`, ordered by

            (crossing candle index, level side, level price, level origin,
             level origin label)

        with `LevelSide.UPPER` before `LevelSide.LOWER`, from explicit rank
        mappings rather than enum or hash order. Timestamp need not appear in the
        key because `CandleSeries` guarantees timestamps increase strictly with
        index, so index order *is* timestamp order; kind and mechanism need not
        appear because at most one event exists per (candle, level) pair.

        Empty when there are no closed candles, no levels, or no interaction.

    Raises:
        TypeError: ``series`` is not a `CandleSeries`, ``levels`` is not a
            non-string sequence, or an element is not a `PriceLevel`.
        DuplicateLevelError: two levels are equal in every field.

    The result is a pure function of the closed candles and the level set: the
    same inputs always give the same output, permuting the levels changes
    nothing, and extending the series with later candles never alters an event
    already returned.

    A single candle may produce any number of events — one per level it reaches —
    including one `UPPER` and one `LOWER` event from a single outside bar. Those
    two share an index and a timestamp, and **their relative order is the level
    ordering, not a claim about which happened first**; OHLC data cannot prove
    that. See `LevelCrossingEvent`.

    Pure: no state, no cache, no clock, no randomness, no global registry.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    if isinstance(levels, (str, bytes)) or not isinstance(levels, Sequence):
        raise TypeError(
            f"levels must be a sequence of PriceLevel, got {type(levels).__name__}"
        )
    for position, level in enumerate(levels):
        if not isinstance(level, PriceLevel):
            raise TypeError(
                f"levels[{position}] must be a PriceLevel, got "
                f"{type(level).__name__}"
            )

    # Validate before deriving, so a failure is deterministic and no partial
    # result is ever built.
    ordered = _require_distinct(levels)

    # Closed candles only — idempotent even if the caller already closed them.
    candles = series.closed().candles

    found: list[LevelCrossingEvent] = []
    # Candle-major, level-minor, both in canonical order, which *is* the stated
    # ordering contract. `_validate_event_order` then checks the result rather
    # than trusting the loops, so a future refactor that reorders them fails the
    # suite instead of silently changing a contract.
    for index, candle in enumerate(candles):
        previous = candles[index - 1] if index > 0 else None
        for level in ordered:
            kind = _crossing_kind(candle, level)
            if kind is None:
                continue
            mechanism = _mechanism_for(candle, previous, level)
            if mechanism is None:
                continue
            found.append(
                LevelCrossingEvent(
                    level=level,
                    candle=candle,
                    index=index,
                    kind=kind,
                    mechanism=mechanism,
                )
            )

    _validate_event_order(found)
    return tuple(found)


def _event_key(event: LevelCrossingEvent) -> tuple[int, tuple[int, float, int, int, float, int]]:
    """The one authoritative ordering key for an event.

    ``(crossing candle index, level key)``. The level key is `_level_key`, reused
    rather than restated so the two orderings cannot drift.

    Deliberately **private**, for the same reason `_level_key` is.
    """
    return (event.index, _level_key(event.level))


def _validate_event_order(events: Sequence[LevelCrossingEvent]) -> None:
    """The derived run must be in canonical order — checked, not assumed.

    Strictly increasing, because at most one event exists per (candle, level) pair
    and the key is total over distinct levels. A non-strict check would accept a
    duplicated event, which is precisely one of the failures worth catching.

    This validates this module's **own output**, which is unusual and deliberate:
    the ordering contract is public and mutation-tested, and an internal check
    means a refactor that reorders the loops fails loudly rather than shipping a
    different contract. It is not an input check — inputs are validated before
    derivation begins.

    Raises:
        AssertionError-free by design: it raises `ValueError`, matching the
        repository's ordering-validation convention.
    """
    for position in range(1, len(events)):
        if _event_key(events[position]) <= _event_key(events[position - 1]):
            raise ValueError(
                f"events must be in canonical order; events[{position}] "
                f"repeats or precedes events[{position - 1}]"
            )
