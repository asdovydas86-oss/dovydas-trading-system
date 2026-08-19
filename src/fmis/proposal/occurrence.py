"""`SetupOccurrence` — the read-time grouping that makes one idea one thing.

§9.4. **The measured problem this closes.** A `SetupAssessment` is recomputed from
scratch on every run and has no identity across time. `AV` derived one from a
window-relative bar index, which changed every bar, and produced **549 "unique
setups" from 552 directional observations** — a 1:1 ratio **[E]** report 0012 §7.
Without continuity, one idea that persists for a week becomes forty setups, forty
rows on the morning page, and forty denominators in every statistic.

An occurrence groups consecutive observations that share an `anchor_identity`. It
is a **pure function** of the observation series and one named policy parameter —
give it the same observations and the same parameter and it returns the same
occurrences, every time, on any machine.

**A projection, and nothing frozen may point at one.** Write authority is *none*;
deletion is *free*; the grouping is recomputed. §23.1's rule — *a derived key may
never be referenced from a captured artifact* — is what makes it safe to bump
`SETUP_IDENTITY_VERSION` and re-derive every occurrence in the repository. The
deduplication that protects captured artifacts is a different mechanism in a
different place: creation rule 4 in `lifecycle.admit`, keyed on the same
`MEASURED` anchor. Both now agree by construction, because both call
`anchors_match`.

**The one policy parameter, named and deliberately not chosen.**
``occurrence_gap_bars`` — how many consecutive non-directional observations may
fall between two directional ones before the occurrence is considered *ended*
rather than *interrupted*. The data model declines to choose a value and this
module declines too: the parameter is **required**, with no default. A default
here would be a trading policy chosen by a library author, and `BD` §6.7 already
found that the existing hardcoded parameters *"are load-bearing and have never
been varied or validated."* The measurement that would choose it exists — `BC`'s
corrected research harness replays 380 usable days and can report the
occurrence-count curve against the parameter directly.

**Ordering is by observation instant, and ties are rejected rather than guessed.**
Two readings of one market at the same instant are a caller error — a replay that
emitted the same bar twice — and silently keeping one would make the occurrence
count depend on dict ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fmis.accounts import Book, MarketId
from fmis.provenance import Absent
from fmis.records import DomainValidationError, TradeDomainError, require_int
from fmis.snapshotting import Anchor, TradeDirection

from fmis.proposal.observation import SetupObservation

__all__ = ["CONFIRMED_STATE", "OccurrenceError", "SetupOccurrence", "group_occurrences"]

#: The reading state that counts as a confirmation. `SetupReading.state` is a
#: free-form `str` on the domain side — the domain must stay describable without
#: importing the engine's enum — so the composition root passes
#: `SetupState.CONFIRMED.value`, and this constant is the one place the spelling
#: is asserted. A test pins it against the engine's own member.
CONFIRMED_STATE = "confirmed"


class OccurrenceError(TradeDomainError):
    """Base class for every occurrence failure."""


@dataclass(frozen=True, slots=True)
class SetupOccurrence:
    """One idea, across every bar it was observed on."""

    identity: str
    market: MarketId
    book: Book
    direction: TradeDirection
    anchor: Anchor
    observations: tuple[SetupObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity:
            raise TypeError("identity must be a non-empty str")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        if not isinstance(self.book, Book):
            raise TypeError("book must be a Book")
        if not isinstance(self.direction, TradeDirection):
            raise TypeError("direction must be a TradeDirection")
        if not isinstance(self.anchor, Anchor):
            raise TypeError("anchor must be an Anchor")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be a tuple of SetupObservation")
        if not self.observations:
            raise DomainValidationError(
                "an occurrence with no observations is not an idea that was ever "
                "observed; it is an empty group that would still be counted as one"
            )
        for position, item in enumerate(self.observations):
            if not isinstance(item, SetupObservation):
                raise TypeError(
                    f"observations[{position}] must be a SetupObservation, got "
                    f"{type(item).__name__}"
                )

    @property
    def began_at(self) -> datetime:
        """The instant this idea was first observed — stable for its whole life."""
        return self.observations[0].as_of

    @property
    def last_seen_at(self) -> datetime:
        return self.observations[-1].as_of

    @property
    def observation_count(self) -> int:
        """How many bars this one idea was observed on.

        **This is the number `AV` reported as a setup count.** Keeping it as a
        property of the occurrence rather than as a row in a total is what makes
        *"one idea seen forty times"* say so, instead of reading as forty ideas.
        """
        return len(self.observations)

    @property
    def ever_confirmed(self) -> bool:
        return any(item.reading.state == CONFIRMED_STATE for item in self.observations)

    @property
    def first_confirmed_at(self) -> datetime | Absent:
        """When this idea first reached `CONFIRMED`, once per occurrence.

        The flag `AV`'s index-based identity could not deliver: it fired on
        essentially every confirmed bar, so one idea was outcome-evaluated many
        times and every rate computed over those outcomes had an inflated
        denominator.
        """
        for item in self.observations:
            if item.reading.state == CONFIRMED_STATE:
                return item.as_of
        return Absent("this occurrence never reached CONFIRMED")


def group_occurrences(
    observations: tuple[SetupObservation, ...],
    *,
    occurrence_gap_bars: int,
) -> tuple[SetupOccurrence, ...]:
    """Group one market's chronological observations into distinct ideas.

    ``occurrence_gap_bars`` is required and has no default; see the module
    docstring. Zero is legal and means *any* non-directional observation ends the
    occurrence — the strictest reading, and the one `research_identity` uses
    today.

    Observations must be for a single market and book and strictly increasing in
    ``as_of``. Both are checked rather than assumed: a mixed-market series would
    silently interleave two markets' ideas into one occurrence, and an unordered
    one would make ``began_at`` meaningless.
    """
    if not isinstance(observations, tuple):
        raise TypeError(
            f"observations must be a tuple, got {type(observations).__name__}"
        )
    require_int(occurrence_gap_bars, "occurrence_gap_bars", minimum=0)
    for position, item in enumerate(observations):
        if not isinstance(item, SetupObservation):
            raise TypeError(
                f"observations[{position}] must be a SetupObservation, got "
                f"{type(item).__name__}"
            )
    if not observations:
        return ()

    market = observations[0].market
    book = observations[0].book
    previous: datetime | None = None
    for item in observations:
        if item.market != market:
            raise DomainValidationError(
                f"observations span two markets ({market.value} and "
                f"{item.market.value}); an occurrence is never compared across "
                "markets, so the caller must group by market first"
            )
        if item.book is not book:
            raise DomainValidationError(
                f"observations span two books ({book.value} and {item.book.value})"
            )
        if previous is not None and item.as_of <= previous:
            raise DomainValidationError(
                f"observations must be strictly increasing in as_of; "
                f"{item.as_of.isoformat()} does not follow {previous.isoformat()}"
            )
        previous = item.as_of

    completed: list[SetupOccurrence] = []
    open_identity: str | None = None
    open_items: list[SetupObservation] = []
    gap_run = 0

    def close() -> None:
        nonlocal open_identity, open_items, gap_run
        if open_items:
            first = open_items[0]
            anchor = first.anchor
            assert isinstance(anchor, Anchor)  # a grouped item is always directional
            completed.append(
                SetupOccurrence(
                    identity=open_identity or "",
                    market=first.market,
                    book=first.book,
                    direction=first.direction,
                    anchor=anchor,
                    observations=tuple(open_items),
                )
            )
        open_identity = None
        open_items = []
        gap_run = 0

    for item in observations:
        identity = item.identity
        if isinstance(identity, Absent):
            # A non-directional reading never joins an occurrence. It either
            # interrupts the open one or, once the tolerance is exhausted, ends it.
            if open_identity is not None:
                gap_run += 1
                if gap_run > occurrence_gap_bars:
                    close()
            continue
        if open_identity is not None and identity != open_identity:
            # A different idea — a new anchor, or a direction flip — ends the
            # open one immediately. Tolerance covers silence, never disagreement.
            close()
        if open_identity is None:
            open_identity = identity
        open_items.append(item)
        gap_run = 0

    close()
    return tuple(completed)
