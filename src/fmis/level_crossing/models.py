"""Value types for deterministic level crossing.

A `PriceLevel` is a **number with a side**: a price, and which way "beyond" means.
It is not support, resistance, a protected level, or a reason to trade. Its
optional `origin` records *where it came from* and nothing more.

A `LevelCrossingEvent` is a **located fact**: at this candle, this level was
touched, strictly breached by an extreme, or breached by a close — and it says
whether price demonstrably reached the level or arrived on the far side without
trading at it. It is not a break of structure, a change of character, a signal,
or a direction to trade.

``index`` is a position into the **closed** candles of the series the event was
derived from (`CandleSeries.closed().candles`), matching `SwingPoint.index`
exactly, so a later layer can join a crossing to a swing without a translation
table.

**Four different things are called "direction" in trading and none of them is the
same as another.** This module names one and only one: `LevelSide`, which says
whether "beyond" means above or below. It is not candle direction
(``close > open``), not trade direction, and not trend direction. There is
deliberately no `direction` field anywhere here, because `LevelSide` already
carries the only sense this layer knows — see ADR-0019 §D.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType

from fmis.data import Candle
from fmis.market_structure import StructuralSwingLabel

__all__ = [
    "LevelSide",
    "CrossingKind",
    "CrossingMechanism",
    "LevelOrigin",
    "PriceLevel",
    "LevelCrossingEvent",
    "LevelCrossingError",
    "DuplicateLevelError",
]


class LevelCrossingError(Exception):
    """Base class for every level-crossing failure.

    Follows the established package-error convention — `IngestError`,
    `RelativeValueError`, `SeriesContextError` — so a caller can catch this
    layer's failures as a group.

    Identity mismatch deliberately does **not** subclass this: it is raised by
    `require_same_identity` as `SeriesIdentityMismatchError`, and wrapping it
    here would let this package's error be caught without catching the contract's.
    """


class DuplicateLevelError(LevelCrossingError, ValueError):
    """Two supplied levels are equal in every field.

    Also a `ValueError`, matching `SeriesIdentityMismatchError(SeriesContextError,
    ValueError)` and `SeriesDecodeError(IngestError, ValueError)`, so existing
    callers catching `ValueError` at a boundary keep working.

    Raised rather than silently deduplicated, following the repository's
    validate-never-repair rule. An exact duplicate cannot come out of
    `structural_levels` — two swing-derived levels always differ by origin index —
    so it is always caller error, and collapsing it would hide the bug while
    quietly changing the event count.

    Two levels at the same price with **different** provenance are **not**
    duplicates and are never collapsed.
    """


class LevelSide(str, Enum):
    """Which way "beyond" means for one level.

    Two members and no third. `UPPER` is breached by price going above, `LOWER`
    by price going below.

    Deliberately absent: BOTH, NEUTRAL, ANY. A level has one side; a caller
    wanting a price watched from both directions supplies two levels, which keeps
    every event unambiguous about which fact it reports.

    Also deliberately absent: any member naming a *movement*. This enum describes
    the level, never the candle, the trade or the trend.
    """

    UPPER = "upper"
    LOWER = "lower"


class CrossingKind(str, Enum):
    """How far a candle went against one level.

    Three members, **mutually exclusive and exhaustive** over "an interaction
    occurred". For an `UPPER` level at price ``L``:

        high <  L                  -> no event at all
        high == L                  -> TOUCH
        high >  L and close <= L   -> WICK_BREACH
        high >  L and close >  L   -> CLOSE_BREACH

    Mirrored on ``low`` for a `LOWER` level. `CLOSE_BREACH` implies the extreme
    was also beyond, because ``high >= close``, so the kinds nest correctly and
    no candle can close beyond a level it never reached.

    **Exact equality is a `TOUCH`, never a breach.** A breach requires strict
    ``>`` / ``<``. Comparison is exact on stored floats — no epsilon, tick size,
    rounding or `Decimal` — inheriting ADR-0013 §4 and the market-structure
    review §9, which record that tolerance belongs at ingestion behind a
    tick-size model that does not exist.

    Deliberately absent: BOS, CHOCH, BREAK, SWEEP, REJECTION, FAKEOUT,
    CONFIRMED, INVALID, STRONG, WEAK. Each is a reading of the fact rather than
    the fact. A consumer that only trusts closes filters on `CLOSE_BREACH` and
    gets a stronger guarantee than a configuration setting would have given it —
    which is why there is exactly one crossing policy and it is not
    configurable (ADR-0019 §B).
    """

    TOUCH = "touch"
    WICK_BREACH = "wick_breach"
    CLOSE_BREACH = "close_breach"


class CrossingMechanism(str, Enum):
    """How the candle came to stand against the level. Orthogonal to `CrossingKind`.

    `WITHIN_RANGE`
        ``low <= L <= high``. Price **demonstrably reached** the level during
        this candle.

    `GAPPED_BEYOND`
        This candle lies **wholly** beyond the level (``low > L`` for `UPPER`,
        ``high < L`` for `LOWER`) and the previous candle did not. Price arrived
        on the far side **without trading at the level**.

    `ALREADY_BEYOND`
        The **first** candle of the series lies wholly beyond the level. There is
        no predecessor, so no arrival can be claimed: this is a state
        observation, honestly labelled, not a crossing.

    `GAPPED_BEYOND` and `ALREADY_BEYOND` always carry `CrossingKind.CLOSE_BREACH`,
    because a candle wholly beyond a level necessarily closed beyond it. That is
    an **enforced invariant**, not a coincidence.

    A candle wholly beyond a level whose predecessor was **also** wholly beyond
    emits **nothing** — nothing happened, price was already there. Without that
    rule a level breached once would re-emit on every later candle.

    ``open`` is **never consulted.** "Previous close below, next open above" is a
    description of a gap, not a definition: an open above the level whose low came
    back below it *did* trade at the level, and is `WITHIN_RANGE`. The
    ``low``/``high`` test is the one that is actually true.

    **No time gap is inferred.** `CandleSeries` permits arbitrary timestamp
    spacing and nothing in the repository detects a missing bar. A gap here is a
    gap in *price coverage between adjacent candles*, whatever their spacing.

    Deliberately absent: any member naming an intrabar path. See
    `LevelCrossingEvent`.
    """

    WITHIN_RANGE = "within_range"
    GAPPED_BEYOND = "gapped_beyond"
    ALREADY_BEYOND = "already_beyond"


#: The one authoritative side for each structural swing label. Explicit rather
#: than derived from the label's spelling, so a renamed member cannot silently
#: re-point a level's side. Exhaustive over `StructuralSwingLabel`.
_SIDE_BY_LABEL: Mapping[StructuralSwingLabel, LevelSide] = MappingProxyType(
    {
        StructuralSwingLabel.HIGHER_HIGH: LevelSide.UPPER,
        StructuralSwingLabel.LOWER_HIGH: LevelSide.UPPER,
        StructuralSwingLabel.EQUAL_HIGH: LevelSide.UPPER,
        StructuralSwingLabel.HIGHER_LOW: LevelSide.LOWER,
        StructuralSwingLabel.LOWER_LOW: LevelSide.LOWER,
        StructuralSwingLabel.EQUAL_LOW: LevelSide.LOWER,
    }
)

#: Explicit ordering ranks. **Never** enum definition order, ``.value`` string
#: order, or hash order — an ordering contract that depended on any of those
#: would change silently when a member was renamed or reordered.
_SIDE_RANK: Mapping[LevelSide, int] = MappingProxyType(
    {LevelSide.UPPER: 0, LevelSide.LOWER: 1}
)

_LABEL_RANK: Mapping[StructuralSwingLabel, int] = MappingProxyType(
    {
        StructuralSwingLabel.HIGHER_HIGH: 0,
        StructuralSwingLabel.LOWER_HIGH: 1,
        StructuralSwingLabel.EQUAL_HIGH: 2,
        StructuralSwingLabel.HIGHER_LOW: 3,
        StructuralSwingLabel.LOWER_LOW: 4,
        StructuralSwingLabel.EQUAL_LOW: 5,
    }
)


@dataclass(frozen=True, slots=True)
class LevelOrigin:
    """Where a level came from. Provenance, never policy.

    Exactly three fields, all copied from the swing unchanged:

      * ``index`` — the pivot's position in the closed-candle sequence.
      * ``timestamp`` — the **pivot candle's** timestamp, matching
        `SwingPoint.timestamp`. Not a confirmation time, not an emission time.
        Must be **timezone-aware**; see below.
      * ``label`` — the swing's own `StructuralSwingLabel`, carried verbatim.

    Nothing here marks the level protected, active, spent, or BOS-relevant, and
    nothing in this package reads an origin except the ordering key. An
    `EQUAL_HIGH`-derived level stays an `EQUAL_HIGH`-derived level; this package
    never renames a swing.

    **The timestamp must be timezone-aware, and this is deliberately stricter than
    `SwingPoint`**, which accepts any `datetime`. The reason is that this
    timestamp is an **ordering key**: `_level_key` sorts levels by it, and the
    event ordering is a public, mutation-tested contract. Two naive datetimes
    cannot be compared against an aware one at all, and any projection that made
    them comparable — notably `datetime.timestamp()`, which interprets a naive
    value in the **host's local time zone** — would make the published order
    depend on the machine that computed it. This package promises no
    environment-dependent output, so the stricter rule is what keeps that promise.

    Being stricter costs nothing reachable: `structural_levels` builds every
    origin from `SwingPoint.timestamp`, which comes from `Candle.timestamp`,
    which `fmis.data` has already validated as canonical UTC. No level derived
    from real candles can be rejected here. Only a hand-built naive origin is,
    and that one has no correct ordering to give it.

    Awareness is required; UTC specifically is **not**. A `+05:00` origin sorts
    chronologically and unambiguously, and demanding UTC would restate
    `fmis.data`'s contract in a second place.

    Frozen, slotted and hashable, so provenance cannot drift and a level stays
    usable as a dict key.
    """

    index: int
    timestamp: datetime
    label: StructuralSwingLabel

    def __post_init__(self) -> None:
        # bool is an int subclass; an index of True is a programming error.
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError(f"index must be an int, got {type(self.index).__name__}")
        if self.index < 0:
            raise ValueError(f"index cannot be negative, got {self.index}")
        if not isinstance(self.timestamp, datetime):
            raise TypeError(
                f"timestamp must be a datetime, got {type(self.timestamp).__name__}"
            )
        if self.timestamp.utcoffset() is None:
            raise ValueError(
                "timestamp must be timezone-aware; a naive origin timestamp has "
                "no machine-independent ordering"
            )
        if not isinstance(self.label, StructuralSwingLabel):
            raise TypeError(
                "label must be a StructuralSwingLabel, got "
                f"{type(self.label).__name__}"
            )


@dataclass(frozen=True, slots=True)
class PriceLevel:
    """A price, which way "beyond" means, and optionally where it came from.

    ``origin`` is **optional on purpose**. A hand-written level in a test, or a
    future level from a source that is not a swing, must be representable without
    fabricating a pivot — a level model that demanded provenance would make every
    such level a lie.

    ``side`` is **intrinsic**. A swing high yields an `UPPER` level. Evaluating
    one level "both ways" would need a caller decision this package must not make.

    **Equality is structural and exact.** Two levels at the same price with
    different origins are **two levels**, never collapsed: a retest of a price
    that two separate pivots established is two facts, and losing one is exactly
    the information a later layer wants. Two levels equal in *every* field are
    rejected by `derive_level_crossings`, not deduplicated.

    ``side`` is **validated against ``origin.label``**: a level claiming `UPPER`
    while carrying an `EQUAL_LOW` provenance cannot be constructed. That is
    `SwingComparison`'s rule — a model may not contradict its own fields —
    applied here.

    Frozen, slotted and hashable, so a level can be shared by reference across a
    whole derivation without any copy, and can key a dict.

    Deliberately absent: active/inactive state, invalidation, protection,
    strength, confidence, touch count, and any BOS relevance. Each is a lifecycle
    or interpretation decision belonging to a later layer (ADR-0019 §I).
    """

    price: float
    side: LevelSide
    origin: LevelOrigin | None = None

    def __post_init__(self) -> None:
        if isinstance(self.price, bool) or not isinstance(self.price, (int, float)):
            raise TypeError(f"price must be a number, got {type(self.price).__name__}")
        if not math.isfinite(self.price):
            raise ValueError("price must be a finite number")
        if not isinstance(self.side, LevelSide):
            raise TypeError(f"side must be a LevelSide, got {type(self.side).__name__}")
        if self.origin is not None and not isinstance(self.origin, LevelOrigin):
            raise TypeError(
                "origin must be a LevelOrigin or None, got "
                f"{type(self.origin).__name__}"
            )
        if self.origin is not None:
            expected = _SIDE_BY_LABEL[self.origin.label]
            if self.side is not expected:
                raise ValueError(
                    f"side {self.side.value!r} does not match the origin label "
                    f"({self.origin.label.value}); expected {expected.value!r}"
                )


#: Sorts before every real `LevelOrigin.timestamp`. Placed in the key only where
#: the preceding ``has-origin`` element has already made it unreachable, so it
#: cannot collide with a real value however early that value is.
_NO_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)


def _level_key(level: PriceLevel) -> tuple[int, float, int, int, datetime, int]:
    """The one authoritative canonical order for levels.

    A **total** key derived entirely from level content, so input order is not
    part of the contract and permuting a level set cannot change the output.

        (side rank, price, has-origin, origin index, origin timestamp, label rank)

    ``side`` and ``label`` use explicit rank mappings, never enum definition
    order, ``.value`` string order or hash order: an ordering contract resting on
    any of those would change silently when a member was renamed.

    A level without an origin sorts before one with an origin (``has-origin`` 0
    before 1), which makes the key total across the optional field without a
    sentinel value that could collide with real data. The two placeholder numbers
    after it are unreachable for an origin-less level, because ``has-origin``
    has already separated it.

    The timestamp enters the key **as a `datetime`, never as a POSIX float**. An
    earlier draft projected it with `datetime.timestamp()`, which has two defects
    the independent review measured. It interprets a *naive* value in the host's
    **local time zone**, so the published order changed with `TZ` — an
    environment-dependent output this package forbids. And it loses resolution as
    the epoch offset grows: two origins one microsecond apart in the year 3000
    projected to the **same** float, making the key non-total and the order
    dependent on input order after all. `LevelOrigin` now requires an aware
    timestamp, which makes direct `datetime` comparison total, exact and
    chronological, and both defects unrepresentable.

    Deliberately **private**, following the market-structure package's
    `_relation_for` and `_label_for`. A public key function would invite a caller
    to sort levels by hand and grow a second, conflicting ordering contract.
    """
    origin = level.origin
    if origin is None:
        return (_SIDE_RANK[level.side], level.price, 0, 0, _NO_TIMESTAMP, 0)
    return (
        _SIDE_RANK[level.side],
        level.price,
        1,
        origin.index,
        origin.timestamp,
        _LABEL_RANK[origin.label],
    )


def _extreme_for(candle: Candle, side: LevelSide) -> float:
    """The candle extreme that faces one level side — the one authoritative choice.

    ``high`` faces an `UPPER` level, ``low`` faces a `LOWER` one. Defined once and
    used by both the crossing predicate and the range test, so the two cannot
    disagree about which field a side reads.
    """
    return candle.high if side is LevelSide.UPPER else candle.low


def _is_wholly_beyond(candle: Candle, level: PriceLevel) -> bool:
    """Does this candle lie entirely on the far side of the level?

    ``low > price`` for an `UPPER` level, ``high < price`` for a `LOWER` one:
    strictly beyond with no part of the range touching. This is the negation of
    "the level lies within ``[low, high]``", and both the mechanism rule and the
    event's self-validation read it from here so there is one definition.
    """
    if level.side is LevelSide.UPPER:
        return candle.low > level.price
    return candle.high < level.price


@dataclass(frozen=True, slots=True)
class LevelCrossingEvent:
    """One candle standing against one level: where, when, how far, and how.

    Fields, and nothing else:

      * ``level`` — the `PriceLevel` **by reference**, carrying its provenance.
      * ``candle`` — the crossing `Candle` **by reference**.
      * ``index`` — that candle's position in the closed-candle sequence,
        matching `SwingPoint.index`.
      * ``kind`` — `TOUCH`, `WICK_BREACH` or `CLOSE_BREACH`.
      * ``mechanism`` — `WITHIN_RANGE`, `GAPPED_BEYOND` or `ALREADY_BEYOND`.

    ``timestamp`` is a **property projecting ``candle.timestamp``**, not a stored
    field, following ADR-0016 §4: a stored copy of a value one attribute away is
    somewhere for it to drift.

    **The event validates itself against its own fields.** ``kind`` must equal
    what the candle and level actually imply, and ``mechanism`` must be
    consistent with whether the candle lies wholly beyond the level. An event
    claiming `CLOSE_BREACH` for a candle that closed inside, or `WITHIN_RANGE`
    for a candle wholly beyond, **cannot be constructed**. That is
    `SwingComparison`'s rule applied here.

    The one distinction the event **cannot** self-check is `GAPPED_BEYOND` versus
    `ALREADY_BEYOND`: it depends on the *previous* candle, which the event does
    not carry. Both are validated as far as the fields allow — each requires the
    candle to be wholly beyond — and the residue is documented rather than
    pretended away.

    **No intrabar path is claimed, ever.** An outside bar breaching an upper and a
    lower level produces two events sharing one ``index`` and one ``timestamp``,
    and **their relative order in the output is the level ordering, not a claim
    about time**. OHLC data does not record whether the high or the low came
    first. There is deliberately no path field and no "order unknown" flag:
    intrabar order is never known, for every event, so a flag that is always the
    same value carries no information and would imply that its absence means
    "known". The honest encoding is a model that cannot express a path at all.

    **This is not a break of structure.** A crossing is a comparison of a price to
    a number at a bar. Break of Structure additionally needs a decision about
    which level was protected, when protection ends, and whether a `TOUCH` or a
    `WICK_BREACH` counts — none of which this layer makes. Change of Character is
    a further reading over the sequence of *those* decisions. See ADR-0019 §1.

    ``candle`` is carried by reference so a consumer *may* look and so the model
    can validate itself; the guarantee is that a future BOS layer does not *need*
    to, because level, provenance, index, timestamp, kind and mechanism are all
    already here.

    Frozen, slotted and hashable, so an event cannot drift and a run of events can
    go in a set when a later layer diffs two derivations.
    """

    level: PriceLevel
    candle: Candle
    index: int
    kind: CrossingKind
    mechanism: CrossingMechanism

    def __post_init__(self) -> None:
        if not isinstance(self.level, PriceLevel):
            raise TypeError(
                f"level must be a PriceLevel, got {type(self.level).__name__}"
            )
        if not isinstance(self.candle, Candle):
            raise TypeError(
                f"candle must be a Candle, got {type(self.candle).__name__}"
            )
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise TypeError(f"index must be an int, got {type(self.index).__name__}")
        if self.index < 0:
            raise ValueError(f"index cannot be negative, got {self.index}")
        if not isinstance(self.kind, CrossingKind):
            raise TypeError(
                f"kind must be a CrossingKind, got {type(self.kind).__name__}"
            )
        if not isinstance(self.mechanism, CrossingMechanism):
            raise TypeError(
                "mechanism must be a CrossingMechanism, got "
                f"{type(self.mechanism).__name__}"
            )

        expected = _crossing_kind(self.candle, self.level)
        if expected is None:
            raise ValueError(
                f"candle does not reach the level ({self.level.side.value} "
                f"{self.level.price}); no crossing to record"
            )
        if self.kind is not expected:
            raise ValueError(
                f"kind {self.kind.value!r} does not match the candle against the "
                f"level ({self.level.side.value} {self.level.price}); "
                f"expected {expected.value!r}"
            )

        beyond = _is_wholly_beyond(self.candle, self.level)
        if beyond and self.mechanism is CrossingMechanism.WITHIN_RANGE:
            raise ValueError(
                "mechanism 'within_range' does not match the candle, which lies "
                f"wholly beyond the level ({self.level.side.value} "
                f"{self.level.price})"
            )
        if not beyond and self.mechanism is not CrossingMechanism.WITHIN_RANGE:
            raise ValueError(
                f"mechanism {self.mechanism.value!r} does not match the candle, "
                f"which reaches the level ({self.level.side.value} "
                f"{self.level.price}) within its range; expected 'within_range'"
            )

    @property
    def timestamp(self) -> datetime:
        """The crossing candle's timestamp — a **projection, not a stored field**.

        Read from ``candle.timestamp`` on access, following ADR-0016 §4, so there
        is exactly one place an event's time comes from and no synchronization
        problem can exist.

        This is the **crossing** candle's time. It is deliberately not the level's
        origin timestamp, which is one attribute away on ``level.origin`` and
        means something else entirely: a swing carries its *pivot's* time, and a
        crossing happens at a different bar. Conflating the two is the mistake the
        market-structure review §15 named as fact #5.
        """
        return self.candle.timestamp


def _crossing_kind(candle: Candle, level: PriceLevel) -> CrossingKind | None:
    """The kind implied by one candle and one level — the one authoritative rule.

    For an `UPPER` level at ``L``:

        high <  L                  -> None
        high == L                  -> TOUCH
        high >  L and close <= L   -> WICK_BREACH
        high >  L and close >  L   -> CLOSE_BREACH

    Mirrored on ``low`` for a `LOWER` level. Comparison is **exact** on the stored
    floats — no epsilon, tolerance, percentage band, ATR scaling, rounding or
    `Decimal` conversion — matching `models._relation_for` in
    `fmis.market_structure` and, through it, ADR-0013 §4.

    Defined here in `models` and re-exported publicly as `crossing_kind` from
    `fmis.level_crossing.crossing`, so `LevelCrossingEvent.__post_init__` and the
    batch derivation share one implementation. If they did not, an event could
    validate against a rule the derivation no longer used.

    Returns:
        The kind, or ``None`` when the candle's facing extreme never reached the
        level.
    """
    price = level.price
    extreme = _extreme_for(candle, level.side)
    if level.side is LevelSide.UPPER:
        if extreme < price:
            return None
        if extreme == price:
            return CrossingKind.TOUCH
        return (
            CrossingKind.CLOSE_BREACH
            if candle.close > price
            else CrossingKind.WICK_BREACH
        )
    if extreme > price:
        return None
    if extreme == price:
        return CrossingKind.TOUCH
    return (
        CrossingKind.CLOSE_BREACH if candle.close < price else CrossingKind.WICK_BREACH
    )
