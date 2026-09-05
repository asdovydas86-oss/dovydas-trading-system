"""What one completed Swing scan *is*, and what a difference between two of them is.

**The whole package in one sentence:** a scan is a set of named states, one per
symbol; a change is a pair of those states that differ on a declared dimension.

**Nothing here decides anything.** No type in this module is reachable from
`evaluate_setup`, `SetupAssessment`, the regime gates or the evidence tally — the
dependency arrow points *into* this package from the projection and never out of
it. Scan memory observes decisions; it does not participate in them, and
`tests/test_scan_memory_architecture.py` asserts, over twenty-six named
packages, that no module here is imported by anything that computes a trading
conclusion.

**Why the compared fields are a declared tuple rather than "every field".**
`CHANGE_DIMENSIONS` is the whole comparison surface, written out. Everything a
`SymbolState` carries that is *not* on that tuple — the per-symbol assessment
instant, the blocker's observed value — is provenance the surfaces print, never
something a difference is derived from. That split is what stops the *What
changed* surface filling with `age changed from 5h to 1h` every time the clock
advances: the comparator cannot see a timestamp, because none is a dimension.

**No score, no rank, no importance.** There is no field here that could hold one,
and a guard test asserts no field name in this package matches a ranking
vocabulary. A `WAIT → CANDIDATE` transition is a named factual transition and is
never weighted against another one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "SCAN_MEMORY_SCHEMA_VERSION",
    "NOT_STATED",
    "PRESENT",
    "ABSENT",
    "ScanMemoryError",
    "ScanHistoryFormatError",
    "ScanHistoryIOError",
    "ChangeDimension",
    "CHANGE_DIMENSIONS",
    "STRUCTURE_DIMENSIONS",
    "ComparisonStatus",
    "ScanIdentity",
    "SymbolState",
    "ScanRecord",
    "StateTransition",
    "SymbolChange",
    "ScanComparison",
]

#: The persisted format. Bumped whenever a stored field changes meaning or a
#: compared dimension is added, removed or redefined — because a record written
#: under one meaning and read under another is the silent-reinterpretation
#: failure this number exists to make impossible.
SCAN_MEMORY_SCHEMA_VERSION = 1

#: What a dimension shows when the value it names was not stated at all. A
#: stated absence, never a third state and never a zero.
#:
#: Spelled `NOT_STATED` rather than `UNSTATED` because `fmis.swing_workspace`
#: already exports the latter for the same idea, and a repository-wide guard
#: requires every public name to belong to exactly one package.
NOT_STATED = "not stated"

#: The two values of the presence dimension. A symbol that produced no
#: assessment on one of the two scans is *absent from that scan*, which is a
#: statement about the scan and never about the market.
PRESENT = "produced an assessment"
ABSENT = "produced no assessment"


class ScanMemoryError(Exception):
    """Anything this package refuses to do."""


class ScanHistoryFormatError(ScanMemoryError):
    """Persisted state that cannot be read under the schema this build knows.

    Corrupt bytes, a truncated file and a record written by a future schema all
    raise this. The caller's contract is the same for all three: **history is
    unavailable, and the current analysis is untouched.**
    """


class ScanHistoryIOError(ScanMemoryError):
    """The filesystem refused. Never a reason to falsify the current scan."""


class ChangeDimension(Enum):
    """The dimensions a difference may be reported on. **This tuple is the whole
    comparison surface.**

    Every member names structured state some engine already produced. Not one of
    them is derived from a rendered sentence, and there is no member for a
    timestamp, an age or a closed-bar count — those advance because time
    advanced, and reporting them as change is the noise this enum's smallness
    exists to prevent.

    Declaration order is display order. It is **not** an importance order: no
    member is more significant than another, and nothing in this package sorts
    by it or weights it.
    """

    PRESENCE = "presence"
    DECISION = "decision"
    POLICY_DIRECTION = "policy_direction"
    DECISION_CONTEXT = "decision_context"
    DEVELOPING_EVIDENCE = "developing_evidence"
    BLOCKER = "blocker"
    CONTEXT_STRUCTURE = "context_structure"
    SETUP_STRUCTURE = "setup_structure"
    EXECUTION_STRUCTURE = "execution_structure"
    EVIDENCE_INDEPENDENCE = "evidence_independence"
    EVIDENCE_AVAILABILITY = "evidence_availability"
    EVIDENCE_COMPOSITION = "evidence_composition"


#: Every dimension, in declaration order. Used by the comparator as its whole
#: field list and by the guard tests as the thing they check it against.
CHANGE_DIMENSIONS: tuple[ChangeDimension, ...] = tuple(ChangeDimension)

#: The three timeframe roles whose structural trend is a dimension, paired with
#: the dimension each one is reported on. Written out rather than derived from a
#: role name, so a renamed role fails loudly instead of silently dropping a
#: dimension.
STRUCTURE_DIMENSIONS: tuple[tuple[str, ChangeDimension], ...] = (
    ("context", ChangeDimension.CONTEXT_STRUCTURE),
    ("setup", ChangeDimension.SETUP_STRUCTURE),
    ("execution", ChangeDimension.EXECUTION_STRUCTURE),
)


class ComparisonStatus(Enum):
    """Whether a comparison happened, and if not, why not.

    **`NO_PREVIOUS_SCAN` is not an error and is never rendered as one.** The
    absence of history is a valid state of a product that has just started
    remembering, and the surfaces say so in those words rather than showing an
    empty *nothing changed*.
    """

    COMPARED = "compared"
    NO_PREVIOUS_SCAN = "no_previous_scan"
    NOT_COMPARABLE = "not_comparable"
    HISTORY_UNAVAILABLE = "history_unavailable"


def _require_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ScanMemoryError(
            f"{name} must be a timezone-aware datetime; a naive instant makes "
            "every comparison between two scans silently ambiguous"
        )
    return value


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScanMemoryError(f"{name} must be a non-empty str")
    return value


def _require_count(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ScanMemoryError(f"{name} must be a non-negative int")
    return value


@dataclass(frozen=True, slots=True)
class ScanIdentity:
    """What makes one scan *that* scan, and what makes two of them comparable.

    **Identity and comparability are deliberately different tuples.**
    ``scan_id`` includes the instant, so two refreshes are two scans;
    ``comparable_key`` excludes it, because a scan is comparable with the one
    before it precisely when everything *except* the instant matches.

    ``universe`` is the requested watchlist in scan order — the symbols the scan
    was asked for, not the symbols it managed to read. Coverage is a property of
    the record; the universe is a property of the request, and conflating them
    would make an outage look like a different experiment.
    """

    schema_version: int
    universe: tuple[str, ...]
    timeframes: tuple[tuple[str, str], ...]
    reference_time: datetime
    analysis_as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise ScanMemoryError("schema_version must be an int")
        if not isinstance(self.universe, tuple) or not self.universe:
            raise ScanMemoryError(
                "universe must be a non-empty tuple; a scan of nothing is not a "
                "baseline anything can be compared against"
            )
        for symbol in self.universe:
            _require_text(symbol, "universe entry")
        if len(set(self.universe)) != len(self.universe):
            raise ScanMemoryError(
                f"universe lists a symbol twice: {self.universe}. Two requests "
                "for one market is two answers to whether it was covered"
            )
        if not isinstance(self.timeframes, tuple):
            raise ScanMemoryError("timeframes must be a tuple of (role, interval)")
        for pair in self.timeframes:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ScanMemoryError("each timeframe must be a (role, interval) pair")
            _require_text(pair[0], "timeframe role")
            _require_text(pair[1], "timeframe interval")
        _require_utc(self.reference_time, "reference_time")
        if self.analysis_as_of is not None:
            _require_utc(self.analysis_as_of, "analysis_as_of")

    @property
    def scan_id(self) -> str:
        """A deterministic name for this scan. **Never a hash of its results.**

        Two scans that observed identical market state are still two scans, and
        a digest over the states would collapse them into one — which would stop
        the second from ever being recorded and make *"nothing changed"*
        indistinguishable from *"nothing ran"*. So the digest covers identity
        only, and recording the same completed scan twice is the idempotent
        no-op it should be.
        """
        canonical = "|".join(
            [
                str(self.schema_version),
                ",".join(self.universe),
                ",".join(f"{role}={interval}" for role, interval in self.timeframes),
                self.reference_time.isoformat(),
                "" if self.analysis_as_of is None else self.analysis_as_of.isoformat(),
            ]
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    @property
    def comparable_key(self) -> tuple[object, ...]:
        """Everything two scans must share to be compared. **No instant here.**"""
        return (self.schema_version, self.universe, self.timeframes)


@dataclass(frozen=True, slots=True)
class SymbolState:
    """One symbol's decision-relevant state on one scan.

    **Every field is a value an engine already produced.** Nothing here is
    computed, combined, weighted or scored; this is the narrowest projection
    that answers the operator's change questions, and it deliberately carries no
    evidence item, no thesis prose, no factor and no provider payload.

    ``as_of`` and ``blocker_observed`` are **provenance, not dimensions.** They
    are stored so a surface can print what the previous scan saw; the comparator
    never reads them, which is why the passage of time cannot manufacture a
    change.
    """

    symbol: str
    state: str
    classification: str
    sufficiency: str
    as_of: datetime
    direction: str | None = None
    developing_state: str | None = None
    developing_lean: str | None = None
    blocker_kind: str | None = None
    blocker_observed: str = ""
    structural_trends: tuple[tuple[str, str | None], ...] = ()
    independence_established: bool = False
    evidence_available: bool = True
    supporting: int = 0
    conflicting: int = 0
    missing: int = 0
    unavailable: int = 0

    def __post_init__(self) -> None:
        for name in ("symbol", "state", "classification", "sufficiency"):
            _require_text(getattr(self, name), name)
        _require_utc(self.as_of, "as_of")
        for name in (
            "direction",
            "developing_state",
            "developing_lean",
            "blocker_kind",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_text(value, name)
        if not isinstance(self.blocker_observed, str):
            raise ScanMemoryError("blocker_observed must be a str")
        if not isinstance(self.structural_trends, tuple):
            raise ScanMemoryError("structural_trends must be a tuple of pairs")
        roles = [pair[0] for pair in self.structural_trends]
        if len(set(roles)) != len(roles):
            raise ScanMemoryError(
                f"each timeframe role may appear once; got {roles}. Two trends "
                "for one role is two answers to what that timeframe showed"
            )
        for pair in self.structural_trends:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ScanMemoryError("each structural trend must be a (role, value) pair")
            _require_text(pair[0], "structural trend role")
            if pair[1] is not None:
                _require_text(pair[1], "structural trend value")
        for name in ("independence_established", "evidence_available"):
            if not isinstance(getattr(self, name), bool):
                raise ScanMemoryError(f"{name} must be a bool")
        for name in ("supporting", "conflicting", "missing", "unavailable"):
            _require_count(getattr(self, name), name)

    def trend_for(self, role: str) -> str | None:
        """One role's structural trend, or `None` for a role the scan did not read."""
        for name, value in self.structural_trends:
            if name == role:
                return value
        return None


@dataclass(frozen=True, slots=True)
class ScanRecord:
    """One completed Swing scan, as it will be remembered.

    ``complete`` is the whole of §20's protection and it is **coverage, not
    success**: a scan is complete when every symbol its universe asked for
    produced an assessment. A scan that lost a symbol to a provider outage is
    recorded — honestly, and with the symbol named — but it is never chosen as
    the baseline another scan is compared against, so one outage cannot silently
    become the thing *"what changed"* means.
    """

    identity: ScanIdentity
    recorded_at: datetime
    symbols: tuple[SymbolState, ...] = ()
    unreadable: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ScanIdentity):
            raise ScanMemoryError("identity must be a ScanIdentity")
        _require_utc(self.recorded_at, "recorded_at")
        if not isinstance(self.symbols, tuple):
            raise ScanMemoryError("symbols must be a tuple of SymbolState")
        for state in self.symbols:
            if not isinstance(state, SymbolState):
                raise ScanMemoryError("symbols must be a tuple of SymbolState")
        names = [state.symbol for state in self.symbols]
        if len(set(names)) != len(names):
            raise ScanMemoryError(
                f"a symbol carries two states on one scan: {names}. Two records "
                "for one market is two answers to what the decision was"
            )
        if not isinstance(self.unreadable, tuple):
            raise ScanMemoryError("unreadable must be a tuple of str")
        for symbol in self.unreadable:
            _require_text(symbol, "unreadable entry")
        overlap = set(names) & set(self.unreadable)
        if overlap:
            raise ScanMemoryError(
                f"{sorted(overlap)} is recorded as both assessed and unreadable; "
                "a symbol did one or the other"
            )

    @property
    def scan_id(self) -> str:
        return self.identity.scan_id

    @property
    def covered(self) -> tuple[str, ...]:
        return tuple(state.symbol for state in self.symbols)

    @property
    def complete(self) -> bool:
        """Every symbol the universe asked for produced an assessment."""
        return bool(self.symbols) and set(self.covered) == set(self.identity.universe)

    def state_for(self, symbol: str) -> SymbolState | None:
        """One symbol's state, by name. **A lookup, never a nearest match.**"""
        for state in self.symbols:
            if state.symbol == symbol:
                return state
        return None


@dataclass(frozen=True, slots=True)
class StateTransition:
    """One dimension that differs, and the two values it differs between.

    ``previous`` and ``current`` are the engines' own values, carried as text.
    The comparator only ever constructs this when the two differ, and an
    invariant test asserts no reported transition has equal ends — a row saying
    ``trending → trending`` would be exactly the false change this type exists
    to make unrepresentable in practice.
    """

    dimension: ChangeDimension
    previous: str
    current: str

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, ChangeDimension):
            raise ScanMemoryError("dimension must be a ChangeDimension")
        for name in ("previous", "current"):
            _require_text(getattr(self, name), name)
        if self.previous == self.current:
            raise ScanMemoryError(
                f"{self.dimension.value} was reported as changed from "
                f"{self.previous!r} to the same value; an unchanged dimension is "
                "not a transition"
            )


@dataclass(frozen=True, slots=True)
class SymbolChange:
    """One symbol's differences, with **its current state named first.**

    ``state`` is what the symbol is *now*. History qualifies the current
    decision; it never replaces it, and every surface that renders this shows
    the current state before any transition.
    """

    symbol: str
    state: str
    previous_state: str
    transitions: tuple[StateTransition, ...] = ()

    def __post_init__(self) -> None:
        for name in ("symbol", "state", "previous_state"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.transitions, tuple) or not self.transitions:
            raise ScanMemoryError(
                "a symbol change must carry at least one transition; a change "
                "with nothing that changed is the fake event this refuses"
            )
        for transition in self.transitions:
            if not isinstance(transition, StateTransition):
                raise ScanMemoryError("transitions must be StateTransition values")
        dimensions = [transition.dimension for transition in self.transitions]
        if len(set(dimensions)) != len(dimensions):
            raise ScanMemoryError(
                f"a dimension is reported twice for {self.symbol}: {dimensions}"
            )


@dataclass(frozen=True, slots=True)
class ScanComparison:
    """This scan beside the previous comparable completed one — or why there is none.

    **Four statuses, and *unchanged* is only ever one of them.** A comparison
    that could not happen says which of the three reasons applied and never
    reports zero changes, because *"nothing changed"* and *"there was nothing to
    compare against"* are different facts and the operator acts differently on
    them.

    ``recorded`` and ``recording_note`` are the honesty valve for §20: when the
    analysis succeeded and persisting it did not, the page still shows the
    analysis and states plainly that this scan was not remembered. It never
    claims change tracking succeeded.
    """

    status: ComparisonStatus
    current_scan_at: datetime
    previous_scan_at: datetime | None = None
    reason: str = ""
    changes: tuple[SymbolChange, ...] = ()
    unchanged: tuple[str, ...] = ()
    recorded: bool = True
    recording_note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, ComparisonStatus):
            raise ScanMemoryError("status must be a ComparisonStatus")
        _require_utc(self.current_scan_at, "current_scan_at")
        if self.previous_scan_at is not None:
            _require_utc(self.previous_scan_at, "previous_scan_at")
        if not isinstance(self.recorded, bool):
            raise ScanMemoryError("recorded must be a bool")
        for name in ("reason", "recording_note"):
            if not isinstance(getattr(self, name), str):
                raise ScanMemoryError(f"{name} must be a str")
        if not isinstance(self.changes, tuple):
            raise ScanMemoryError("changes must be a tuple of SymbolChange")
        for change in self.changes:
            if not isinstance(change, SymbolChange):
                raise ScanMemoryError("changes must be a tuple of SymbolChange")
        if not isinstance(self.unchanged, tuple):
            raise ScanMemoryError("unchanged must be a tuple of str")
        if self.status is not ComparisonStatus.COMPARED:
            if self.changes or self.unchanged:
                raise ScanMemoryError(
                    f"{self.status.value} carries per-symbol results; a "
                    "comparison that did not happen has no symbols to report, "
                    "and reporting them as unchanged would fabricate a baseline"
                )
            if self.previous_scan_at is not None:
                raise ScanMemoryError(
                    f"{self.status.value} names a previous scan instant; there "
                    "was no previous comparable scan to name"
                )
            _require_text(self.reason, "reason")
        else:
            if self.previous_scan_at is None:
                raise ScanMemoryError(
                    "a completed comparison must name the scan it compared "
                    "against"
                )
        changed = {change.symbol for change in self.changes}
        overlap = changed & set(self.unchanged)
        if overlap:
            raise ScanMemoryError(
                f"{sorted(overlap)} is reported as both changed and unchanged"
            )
        if not self.recorded:
            _require_text(self.recording_note, "recording_note")

    @property
    def compared(self) -> bool:
        return self.status is ComparisonStatus.COMPARED

    @property
    def changed_count(self) -> int:
        return len(self.changes)

    def change_for(self, symbol: str) -> SymbolChange | None:
        """One symbol's differences, by name. `None` means *not changed* only
        when `compared` is true; otherwise it means there was no comparison."""
        for change in self.changes:
            if change.symbol == symbol:
                return change
        return None
