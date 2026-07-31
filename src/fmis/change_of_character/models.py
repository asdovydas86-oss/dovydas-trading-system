"""The change-of-character value type and its errors.

A `ChangeOfCharacter` is a **located fact about two closed bars**: structure broke
one way at a bar, and at a strictly later bar it broke the other way, with no
break-bearing bar in between. It is not a signal, not a reversal call, not a
trend, and not a claim that the change will persist.

**Exactly two stored fields.** ``subject`` is the break that changed character;
``previous`` is the break it changed *from*. Both are needed and neither is
redundant: without ``previous`` the claim would be an assertion whose
justification lived only in the derivation that produced it, and the point of
storing it is that a consumer holding this object alone can check the claim.

Everything else is one attribute away on ``subject`` or ``previous`` — the level,
its price, its provenance, its label, the crossing, the mechanism, the
eligibility bar. A stored copy of any of them is somewhere for one fact to
disagree with itself (ADR-0016 §4), so there are **three projections only**:
``index``, ``timestamp`` and ``side``, the three join keys every layer in this
chain already exposes.

Deliberately absent: ``previous_side`` (fully determined by ``side``, since
validation guarantees the two are opposite and there are two sides),
``bars_since``, ``direction``, ``confirmed``, ``strength``, ``confidence``,
``invalidated``, ``failed``, and any character-state enum. The reasons are
recorded one by one in `docs/design/CHOCH_FOUNDATION_V1.md` §3.5.

Also deliberately absent: any direction enum. `side` projects the subject
break's side, which already carries the only sense this layer knows — ADR-0019
§D, unchanged through three layers. `UPPER` is not "bullish".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fmis.level_crossing import LevelSide
from fmis.structure_break import StructureBreak

__all__ = [
    "ChangeOfCharacter",
    "ChangeOfCharacterError",
    "ChangeOfCharacterInputError",
]


class ChangeOfCharacterError(Exception):
    """Base class for every change-of-character failure.

    Follows the established package-error convention — `IngestError`,
    `RelativeValueError`, `SeriesContextError`, `LevelCrossingError`,
    `StructureBreakError` — so a caller can catch this layer's failures as a
    group.

    Identity mismatch deliberately does **not** subclass this: it is raised by
    `require_same_identity` as `SeriesIdentityMismatchError`, and wrapping it
    here would let this package's error be caught without catching the
    contract's.
    """


class ChangeOfCharacterInputError(ChangeOfCharacterError, ValueError):
    """The supplied breaks cannot be read as one unambiguous break sequence.

    Also a `ValueError`, matching `SeriesIdentityMismatchError`,
    `DuplicateLevelError` and `StructureBreakInputError`, so existing callers
    catching `ValueError` at a boundary keep working.

    One cause, with one exact message:

      * two **distinct** breaks share a bar index and a side, so "the break at
        that bar on that side" — which the previous-character rule reads — is
        ambiguous.

    It is **rejected, never repaired**. Picking one of the two would change the
    character at every later bar without saying so, which is the failure mode
    hardest to notice and impossible to debug from the output. Two *equal*
    breaks are not this error: duplicated facts are one fact and collapse
    silently, exactly as duplicated crossings do one layer down (ADR-0020 §3.8).

    `derive_structure_breaks` cannot produce a conflicting pair — it emits at
    most one break per (bar, side). A hand-built run can, which is precisely why
    guessing here would be inventing behaviour.
    """


@dataclass(frozen=True, slots=True)
class ChangeOfCharacter:
    """One break that changed character, and the break it changed from.

    ``subject``
        The `StructureBreak` that changed character, **by reference**. It carries
        the crossing, the level, its provenance and label, the bar index, the
        timestamp, the side and the eligibility bar — so nothing about the break
        needs restating here, and nothing is re-derived.

    ``previous``
        The `StructureBreak` that established the character being changed —
        **by reference**, on a **strictly earlier bar**, on the **opposite
        side**. Stored rather than projected because it is what makes the claim
        auditable: a consumer holding only this object can verify that character
        did change, and from what.

    **The change validates itself against its own two breaks.** The sides must
    differ, and ``previous.index`` must be **strictly** less than
    ``subject.index``. A `ChangeOfCharacter` claiming a same-side change, or a
    change from a break at the same bar or a later one, **cannot be
    constructed**. That is `SwingComparison`'s rule and `StructureBreak`'s rule,
    applied here.

    The strict index inequality is the load-bearing one. Two breaks may share a
    bar — one upper, one lower — and ADR-0019 §2.6 and ADR-0020 §3.5 both state
    that **their order is the level ordering, not a claim about which happened
    first**. A change of character derived from such a pair would be a claim
    about intrabar sequence that OHLC data cannot support. This model refuses to
    represent one.

    **What it does not claim.** Not that the change will hold. Not that a trend
    reversed. Not that anything should be traded. Not that the market is now
    bullish or bearish. And not that the previous break "failed" — a break is a
    fact about a closed bar, and nothing later revises it (ADR-0020 §3.7).

    Frozen, slotted and hashable, so a change cannot drift and a run of changes
    can go in a set when a later layer diffs two derivations.
    """

    subject: StructureBreak
    previous: StructureBreak

    def __post_init__(self) -> None:
        if not isinstance(self.subject, StructureBreak):
            raise TypeError(
                "subject must be a StructureBreak, got "
                f"{type(self.subject).__name__}"
            )
        if not isinstance(self.previous, StructureBreak):
            raise TypeError(
                "previous must be a StructureBreak, got "
                f"{type(self.previous).__name__}"
            )
        if self.previous.side is self.subject.side:
            raise ValueError(
                f"previous break is on the same side ({self.subject.side.value}); "
                "character did not change"
            )
        if self.previous.index >= self.subject.index:
            raise ValueError(
                f"previous break index ({self.previous.index}) does not precede "
                f"the subject's ({self.subject.index}); two breaks at one bar "
                "carry no order in time"
            )

    @property
    def index(self) -> int:
        """The changing bar's position in the closed-candle sequence.

        A **projection** of ``subject.index``, not a stored field. Matches
        `SwingPoint.index`, `LevelCrossingEvent.index` and `StructureBreak.index`,
        so a later layer joins on it without a translation table.

        Deliberately the **subject's** bar, not the previous break's: the change
        happened when the opposing break closed. ``previous.index`` is one
        attribute away for anyone who needs it.
        """
        return self.subject.index

    @property
    def timestamp(self) -> datetime:
        """The changing bar's timestamp — a projection of ``subject.timestamp``.

        The **changing** bar's time, not the previous break's and not the origin
        swing's. The market-structure review §15 named conflating a pivot's time
        with a later event's as fact #5, and this layer is two events removed
        from that pivot.
        """
        return self.subject.timestamp

    @property
    def side(self) -> LevelSide:
        """The side structure broke on at the change — a projection of ``subject.side``.

        `LevelSide.UPPER` means the subject break closed **above** its level. It
        does not mean bullish, long, a reversal to the upside, or a reason to
        buy; naming it that way would be the interpretation this layer exists not
        to make.

        There is deliberately no ``previous_side``: validation guarantees the two
        sides differ and there are exactly two, so it is fully determined by this
        one. A consumer that wants it explicitly writes ``change.previous.side``.
        """
        return self.subject.side
