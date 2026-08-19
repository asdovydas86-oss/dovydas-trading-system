"""`SetupObservation` — one deterministic setup reading, given a home in the domain.

§9.3. One reading for one market at one instant. **This type adds no market
computation and recomputes nothing**: it composes the reading the engine already
produced, exactly the constraint `AT` held itself to.

**It composes `SetupReading` rather than copying its eighteen fields.** §9.3's
purpose line is *"the built `SetupAssessment`, given a home in the domain model
**without being copied**"*, and a second declaration of `state`, `stop`,
`targets`, `risk_reward` and the rest would be a duplicate vocabulary that must
then be kept in step by hand. The reading is the market's answer; this type adds
only what the market half has no reason to know — which market and book the
reading belongs to, the version set that produced it, and the owner's optional
classification of what *kind* of setup it is.

**A projection, and the type says so by what it lacks.** There is no record id,
no `RecordAudit`, no `to_payload` and no `from_payload`, because §9.3 gives it
write authority **none — it is recomputed** and durability `REBUILDABLE_PROJECTION`,
which `fmis.persistence.kinds` refuses to store at all. A reading is persisted
only by being frozen into a `MarketSnapshot` or archived as an `AnalysisRecord`,
and in both cases what is written is the `SetupReading` — which has had its own
codec since it was built. Adding an encoder here would create a second, competing
way to write the same facts.

**`SetupType` is a `VersionedTerm`, not a new class.** §9.2 makes it one term in
the closed `setup` vocabulary, which is the shape `TradePlan.setup_type` already
carries and `fmis.statistics.breakdown` already groups on. It is `Absent` by
default and stays that way unless the owner classifies the reading: the built
engine classifies readiness and direction, never setup *kind*, and inventing a
classifier here would be a new engine this milestone has no authority to design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fmis.accounts import Book, MarketId
from fmis.provenance import Absent, VersionedTerm
from fmis.records import DomainValidationError, TradeDomainError
from fmis.snapshotting import Anchor, SetupReading, TradeDirection
from fmis.versioning import VersionSet

from fmis.proposal.setup_identity import SETUP_VOCABULARY_ID, anchor_identity

__all__ = ["ObservationError", "SetupObservation"]


class ObservationError(TradeDomainError):
    """Base class for every observation failure."""


@dataclass(frozen=True, slots=True)
class SetupObservation:
    """One market's setup reading at one instant, with the identity it belongs to."""

    market: MarketId
    book: Book
    reading: SetupReading
    version_set: VersionSet
    setup_type: VersionedTerm | Absent = field(
        default_factory=lambda: Absent("the owner has not classified this setup's kind")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketId):
            raise TypeError(f"market must be a MarketId, got {type(self.market).__name__}")
        if not isinstance(self.book, Book):
            raise TypeError(f"book must be a Book, got {type(self.book).__name__}")
        if not isinstance(self.reading, SetupReading):
            raise TypeError(
                f"reading must be a SetupReading, got {type(self.reading).__name__}"
            )
        if not isinstance(self.version_set, VersionSet):
            raise TypeError(
                f"version_set must be a VersionSet, got {type(self.version_set).__name__}"
            )
        if not isinstance(self.setup_type, (VersionedTerm, Absent)):
            raise TypeError("setup_type must be a VersionedTerm or Absent")
        if isinstance(self.setup_type, VersionedTerm):
            if self.setup_type.vocabulary_id != SETUP_VOCABULARY_ID:
                raise DomainValidationError(
                    f"setup_type must be a term in the {SETUP_VOCABULARY_ID!r} "
                    f"vocabulary, got {self.setup_type.vocabulary_id!r}; a term "
                    "borrowed from another vocabulary would be counted under a "
                    "heading it was never defined for"
                )
        anchor = self.reading.anchor
        if isinstance(anchor, Anchor):
            if anchor.market != self.market:
                raise DomainValidationError(
                    f"anchor market {anchor.market.value} disagrees with the "
                    f"observation's own market {self.market.value}"
                )
            if anchor.book is not self.book:
                raise DomainValidationError(
                    f"anchor book {anchor.book.value} disagrees with the "
                    f"observation's own book {self.book.value}"
                )

    @property
    def as_of(self) -> datetime:
        """The instant the reading was taken."""
        return self.reading.as_of

    @property
    def direction(self) -> TradeDirection:
        return self.reading.direction

    @property
    def is_directional(self) -> bool:
        """Whether this reading came down on a side at all.

        A `NO_TRADE` reading carries no anchor and therefore has no identity: it
        cannot begin, continue or end an occurrence. It is not discarded — it is
        what *interrupts* one, and the gap tolerance in `occurrence.py` decides
        whether the interruption ended the idea or merely paused it.
        """
        return self.reading.direction.is_directional

    @property
    def anchor(self) -> Anchor | Absent:
        return self.reading.anchor

    @property
    def identity(self) -> str | Absent:
        """The stable key this observation groups on, or why it has none."""
        anchor = self.reading.anchor
        if isinstance(anchor, Absent):
            return anchor
        return anchor_identity(anchor)
