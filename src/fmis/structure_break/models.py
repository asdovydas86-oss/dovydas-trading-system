"""The break-of-structure value type and its errors.

A `StructureBreak` is a **located fact**: at this bar, price closed beyond the
reference structural level for its side, at a bar where that level was already
knowable. It is not a signal, not a direction to trade, not a change of
character, and not a claim that the break will hold.

**Exactly two stored fields**, because everything else is one attribute away on
the crossing and a stored copy is somewhere for it to drift (ADR-0016 §4). The
level, the bar index, the timestamp, the side, the price, the provenance and its
label are all **projections**.

Deliberately absent: any `invalidated`, `failed`, `active`, `retested`,
`strength` or `confidence` field. A break is a fact about a bar that has closed;
"this break failed" is a later *reading* over the break sequence, and it is
change-of-character adjacent, which puts it two layers up.

Also deliberately absent: any direction enum. `level.side` already carries the
only sense this layer knows, exactly as ADR-0019 §D decided for crossings, and a
second field would be a second place for one fact to disagree with itself.
`UPPER` is not "bullish".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fmis.level_crossing import (
    CrossingKind,
    CrossingMechanism,
    LevelCrossingEvent,
    LevelOrigin,
    LevelSide,
    PriceLevel,
)
from fmis.market_structure import StructuralSwingLabel

__all__ = [
    "StructureBreak",
    "StructureBreakError",
    "StructureBreakInputError",
]


class StructureBreakError(Exception):
    """Base class for every break-of-structure failure.

    Follows the established package-error convention — `IngestError`,
    `RelativeValueError`, `SeriesContextError`, `LevelCrossingError` — so a caller
    can catch this layer's failures as a group.

    Identity mismatch deliberately does **not** subclass this: it is raised by
    `require_same_identity` as `SeriesIdentityMismatchError`, and wrapping it here
    would let this package's error be caught without catching the contract's.
    """


class StructureBreakInputError(StructureBreakError, ValueError):
    """The supplied levels and crossings cannot be ranked into references.

    Also a `ValueError`, matching `SeriesIdentityMismatchError` and
    `DuplicateLevelError`, so existing callers catching `ValueError` at a boundary
    keep working.

    Three distinct causes, each with its own exact message:

      * a level carries **no provenance**, so it cannot be placed in time;
      * two levels on **one side share an origin index**, so "the most recent
        level" is ambiguous;
      * a crossing references a level **absent from the level set**, so the
        reference computation and the crossing history disagree about what exists.

    Every one is **rejected, never repaired**. Silently dropping an unrankable
    level would change which level is the reference at every later bar without
    saying so — the failure mode hardest to notice and impossible to debug from
    the output.
    """


@dataclass(frozen=True, slots=True)
class StructureBreak:
    """One crossing that broke structure, and the bar from which it could.

    ``crossing``
        The `LevelCrossingEvent` **by reference**. It carries the level, its
        provenance and label, the bar index, the timestamp, the kind and the
        mechanism — so nothing about the break needs restating here.

    ``eligible_from`` is a **property, not a field** — see below.

    **The break validates itself against its own crossing.** ``kind`` must be
    `CrossingKind.CLOSE_BREACH`, ``mechanism`` must not be
    `CrossingMechanism.ALREADY_BEYOND`, the level must carry provenance, and the
    crossing bar must be at or after ``eligible_from``. A `StructureBreak`
    claiming a touch, a wick, or a break of a level that was not yet knowable
    **cannot be constructed**. That is `SwingComparison`'s rule, applied here.

    **``eligible_from`` stopped being a stored field in Milestone AH** (ADR-0024).
    It was stored because ``confirmation_bars`` was a caller-supplied number that
    lived nowhere on the inputs (ADR-0020 D1), so a consumer holding only this
    object could not otherwise recover it. It now lives on
    ``crossing.level.origin``, which makes the stored copy exactly what ADR-0016
    §4 forbids: a duplicate of a value one attribute away, with somewhere to
    drift. Worse, while it was a constructor argument it was a **second source of
    truth** — a break could be built claiming an eligibility its own level
    contradicted. Removing the argument removes that possibility rather than
    validating against it.

    **What it does not claim.** Not that the break will hold. Not that a trend
    exists. Not that anything should be traded. And for two breaks sharing a bar —
    one upper, one lower — **not** which happened first: OHLC data cannot prove
    that, and the ordering is the level ordering, inherited verbatim from
    ADR-0019 §2.6.

    Frozen, slotted and hashable, so a break cannot drift and a run of breaks can
    go in a set when a later layer diffs two derivations.
    """

    crossing: LevelCrossingEvent

    def __post_init__(self) -> None:
        if not isinstance(self.crossing, LevelCrossingEvent):
            raise TypeError(
                "crossing must be a LevelCrossingEvent, got "
                f"{type(self.crossing).__name__}"
            )
        if self.crossing.kind is not CrossingKind.CLOSE_BREACH:
            raise ValueError(
                f"crossing kind {self.crossing.kind.value!r} does not break "
                "structure; expected 'close_breach'"
            )
        if self.crossing.mechanism is CrossingMechanism.ALREADY_BEYOND:
            raise ValueError(
                "crossing mechanism 'already_beyond' does not break structure; "
                "the series began beyond the level, so no arrival can be claimed"
            )
        if self.crossing.level.origin is None:
            raise ValueError(
                "crossing level carries no origin; a break needs provenance to "
                "place the level in time"
            )
        if self.crossing.index < self.eligible_from:
            raise ValueError(
                f"crossing index ({self.crossing.index}) precedes eligible_from "
                f"({self.eligible_from}); the level was not yet knowable"
            )

    @property
    def eligible_from(self) -> int:
        """The candle index from which this level could first break structure.

        A **projection** of ``crossing.level.origin.knowable_from``, not a stored
        field, following ADR-0016 §4. The break and the level it broke can no
        longer disagree about when that level became knowable, because there is
        only one place the number exists.

        The check that ``eligible_from`` cannot precede the level's origin index
        is gone with the field: ``knowable_from`` is ``index + confirmation_bars``
        with a window of at least 1, so it is *always* after the origin. What was
        a validated invariant is now an arithmetic one.

        Reads through the `origin` property rather than the raw attribute, so the
        "never ``None``" argument lives in exactly one place.
        """
        return self.origin.knowable_from

    @property
    def index(self) -> int:
        """The breaking bar's position in the closed-candle sequence.

        A **projection** of ``crossing.index``, not a stored field. Matches
        `SwingPoint.index` and `LevelCrossingEvent.index`, so a later layer joins
        on it without a translation table.
        """
        return self.crossing.index

    @property
    def timestamp(self) -> datetime:
        """The breaking bar's timestamp — a projection of ``crossing.timestamp``.

        This is the **breaking** bar's time. It is deliberately not the level's
        origin timestamp, which is two attributes away on ``level.origin`` and
        means something else: a swing carries its *pivot's* time, and a break
        happens at a different bar. The market-structure review §15 named
        conflating the two as fact #5.
        """
        return self.crossing.timestamp

    @property
    def level(self) -> PriceLevel:
        """The level that broke — a projection of ``crossing.level``."""
        return self.crossing.level

    @property
    def side(self) -> LevelSide:
        """Which way the break went — a projection of ``level.side``.

        `LevelSide.UPPER` means price closed **above** the level. It does not mean
        bullish, long, or a reason to buy; naming it that way would be the
        interpretation this layer exists not to make.
        """
        return self.crossing.level.side

    @property
    def origin(self) -> LevelOrigin:
        """Where the broken level came from — a projection of ``level.origin``.

        Never ``None``: construction rejects a level without provenance, so a
        consumer need not re-check.
        """
        origin = self.crossing.level.origin
        assert origin is not None  # guaranteed by __post_init__
        return origin

    @property
    def label(self) -> StructuralSwingLabel:
        """The broken level's swing label — a projection of ``origin.label``.

        Carried through **unchanged and unfiltered**. An `EQUAL_HIGH`-derived
        level breaks when a close goes beyond its price, exactly as a
        `HIGHER_HIGH`-derived one does: the break test measures a close against a
        price, and the label does not change that arithmetic. Exposing it here is
        what lets a consumer weigh the two differently *in its own layer*, which
        is where that policy belongs.
        """
        return self.origin.label
