"""Value types for the Daily Trading Workspace.

A `TodayWorkspace` is a **first-class object**, not terminal text — the same
contract `Workspace` (AK) and `DailyRun` (AN) already hold. The renderer reads
this model and nothing else, and every future consumer will read the same one.

**Absence is a value here, never an omission.** `NotAvailable` carries three
things and all three are required: why the value is missing, which slice owns
producing it, and *the inference its absence forbids*. That third field is the
one that matters. A portfolio section rendered as blank reads as "no exposure";
a portfolio section rendered as `NotAvailable("nothing is recorded ... do not
infer that you hold nothing")` cannot. The pattern is `fmis.workspace`'s own and
is adopted unchanged.

**Nothing here ranks by desirability.** `PriorityQueue` orders by *attention* —
the engine's own readiness state, then the order the watchlist was scanned in —
and its `ordering` field states that rule on the page. There is no score, no
probability, no composite and no member sorted by risk/reward anywhere in this
module; a test asserts the queue's order is unchanged when a high-R:R candidate
is planted ahead of a low-R:R confirmed setup.

**Every number that reaches a warning came from `fmis.today.evidence`**, which
holds the measured figures this repository published and the caveat each one
must be printed with.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "TODAY_SCHEMA_VERSION",
    "TodayError",
    "StoreUnreadableError",
    "NotAvailable",
    "WarningClass",
    "WarningSeverity",
    "WorkspaceWarning",
    "MarketOverview",
    "PositionLine",
    "LimitLine",
    "PortfolioOverview",
    "OpportunityLine",
    "WaitGroup",
    "FailedSymbol",
    "Opportunities",
    "QueueEntry",
    "PriorityQueue",
    "JournalLine",
    "ClosedPositionLine",
    "JournalSummary",
    "AnalysisLine",
    "AnalysisSummary",
    "TodayWorkspace",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
#: `2` for Milestone BN: `OpportunityLine` gained the five approval fields and
#: `Opportunities` gained the note that says whether an approval was computed at
#: all. A consumer reading a version-1 page would render every candidate as
#: unapproved, which is a different claim from *"this page did not check"*.
TODAY_SCHEMA_VERSION = 2


class TodayError(Exception):
    """Base class for every Daily Trading Workspace failure.

    Follows the package-error convention `WorkspaceError`, `DailyRunError` and
    `PersistenceError` established elsewhere, so a caller can catch this layer's
    failures as a group.
    """


class StoreUnreadableError(TodayError):
    """The durable store exists and could not be read.

    Distinct from an *empty* store, which is not a failure at all: a missing
    line file reads as emptiness, because that is what it means. This is raised
    only when a store that is there cannot be trusted — a broken hash chain, a
    corrupt index row, a payload that will not decode.

    It exists so the outermost edge can report a store failure without importing
    the store. `fmis.pipeline` is a market-half package and may not reach
    `fmis.persistence`; wrapping the failure here keeps that boundary intact
    without discarding the original, which is chained as ``__cause__`` and
    quoted in the message.
    """


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TodayError(f"{name} must be a non-empty str")
    return value


def _tuple_of(value: Any, kind: type, name: str) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")
    for position, item in enumerate(value):
        if not isinstance(item, kind):
            raise TypeError(
                f"{name}[{position}] must be a {kind.__name__}, got "
                f"{type(item).__name__}"
            )
    return value


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple of str")
    for position, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise TodayError(f"{name}[{position}] must be a non-empty str")
    return value


def _count(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise TodayError(f"{name} cannot be negative")
    return value


@dataclass(frozen=True, slots=True)
class NotAvailable:
    """A value the workspace cannot produce, stated rather than left blank.

    All three fields are required. ``forbidden_inference`` is the load-bearing
    one: it is what stops an empty section being read as a reassuring one, and
    it is why an unbuilt section is rendered rather than omitted.
    """

    reason: str
    owned_by: str
    forbidden_inference: str

    def __post_init__(self) -> None:
        for name in ("reason", "owned_by", "forbidden_inference"):
            _text(getattr(self, name), name)


class WarningClass(Enum):
    """Which of the brief's five categories a warning belongs to."""

    MISSING_DATA = "missing_data"
    INCOMPLETE_ANALYSIS = "incomplete_analysis"
    RISK = "risk"
    CORRELATION = "correlation"
    LIMITATION = "limitation"


class WarningSeverity(Enum):
    """The blueprint's three registers, kept apart because they behave apart.

    `BLOCK` — the system refuses to produce a number or a record (blueprint
    §7.2). It cannot prevent the owner from trading anyway, and does not claim
    to. `WARNING` — shown beside the value it qualifies, never a gate (§7.3).
    `INFORMATION` — never a warning and never a gate (§7.4); *an absent input is
    information, never reassurance.*
    """

    BLOCK = "block"
    WARNING = "warning"
    INFORMATION = "information"


@dataclass(frozen=True, slots=True)
class WorkspaceWarning:
    """One deterministic observation about this run, with its own provenance.

    ``evidence`` names where the rule comes from — a specification section, an
    ADR, a measured figure. A warning with no stated source is a judgement this
    package invented, and there are none.

    ``detail`` carries the measured figure's full form when one backs the rule:
    statement, `n`, and the caveat blueprint §7.6 requires be printed with it.
    """

    code: str
    kind: WarningClass
    severity: WarningSeverity
    statement: str
    evidence: str
    subjects: tuple[str, ...] = ()
    detail: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.code, "code")
        _text(self.statement, "statement")
        _text(self.evidence, "evidence")
        if not isinstance(self.kind, WarningClass):
            raise TypeError(
                f"kind must be a WarningClass, got {type(self.kind).__name__}"
            )
        if not isinstance(self.severity, WarningSeverity):
            raise TypeError(
                f"severity must be a WarningSeverity, got "
                f"{type(self.severity).__name__}"
            )
        _strings(self.subjects, "subjects")
        _strings(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class MarketOverview:
    """What the market is doing, from the scan the run already performed.

    **There is no single Bull / Bear / Neutral label, deliberately.** ADR-0025
    forbids collapsing a regime into a direction, and every downstream engine
    refuses to state one; `regime_note` carries that refusal onto the page in
    words rather than leaving a reader to wonder where the headline went.

    ``breadth`` is a count per directional bucket over the whole scanned
    watchlist — a distribution, not a verdict. ``readable_declined`` and
    ``unreadable`` are kept as two separate lists because a quiet system and a
    quiet market are indistinguishable when they are shown as one number.
    """

    scanned: int
    status_counts: tuple[tuple[str, int], ...]
    breadth: tuple[tuple[str, int], ...]
    readable_declined: tuple[str, ...]
    unreadable: tuple[str, ...]
    observations: tuple[str, ...]
    regime_note: str
    analysis_as_of: datetime | None = None

    def __post_init__(self) -> None:
        _count(self.scanned, "scanned")
        for name in ("status_counts", "breadth"):
            pairs = getattr(self, name)
            if not isinstance(pairs, tuple):
                raise TypeError(f"{name} must be a tuple of (label, count) pairs")
            for position, pair in enumerate(pairs):
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise TypeError(f"{name}[{position}] must be a 2-tuple")
                _text(pair[0], f"{name}[{position}] label")
                _count(pair[1], f"{name}[{position}] count")
        _strings(self.readable_declined, "readable_declined")
        _strings(self.unreadable, "unreadable")
        _strings(self.observations, "observations")
        _text(self.regime_note, "regime_note")
        if self.analysis_as_of is not None and not isinstance(
            self.analysis_as_of, datetime
        ):
            raise TypeError("analysis_as_of must be a datetime or None")


@dataclass(frozen=True, slots=True)
class PositionLine:
    """One open position, folded from the ledger and never stored.

    Every value here is already on `fmis.positions.Position` or on the
    `MarkedPosition` that paired it with a price. Nothing is recomputed and no
    quotient is derived.

    ``mark``, ``market_value`` and ``unrealized_pnl`` are `None` when no price
    source was consulted for this position, and carry a *reason* rather than a
    figure when one was consulted and produced nothing. `None` and a reason are
    different facts — *"this page did not look"* against *"this page looked and
    could not price it"* — and the same distinction `store_present` already
    makes one level up.
    """

    market: str
    book: str
    direction: str
    quantity: str
    average_entry: str
    opened_at: datetime
    trade_count: int
    event_ids: tuple[str, ...]
    mark: str | None = None
    market_value: str | None = None
    unrealized_pnl: str | None = None

    def __post_init__(self) -> None:
        for name in ("market", "book", "direction", "quantity", "average_entry"):
            _text(getattr(self, name), name)
        if not isinstance(self.opened_at, datetime):
            raise TypeError("opened_at must be a datetime")
        _count(self.trade_count, "trade_count")
        _strings(self.event_ids, "event_ids")
        for name in ("mark", "market_value", "unrealized_pnl"):
            value = getattr(self, name)
            if value is None:
                continue
            _text(value, name)


@dataclass(frozen=True, slots=True)
class LimitLine:
    """One configured risk limit, and whether anything could be measured against it.

    ``current`` is `NotAvailable` whenever the measurement needs an input the
    product does not have. `INDETERMINATE` is never rendered as `WITHIN` — the
    contract `AP` §15.5 property 2 states, held here by making the two different
    types rather than two spellings of one.
    """

    limit_id: str
    scope: str
    stated_limit: str
    severity: str
    current: str | NotAvailable
    status: str | NotAvailable

    def __post_init__(self) -> None:
        for name in ("limit_id", "scope", "stated_limit", "severity"):
            _text(getattr(self, name), name)
        for name in ("current", "status"):
            value = getattr(self, name)
            if isinstance(value, NotAvailable):
                continue
            _text(value, name)


@dataclass(frozen=True, slots=True)
class PortfolioOverview:
    """What is held and what is committed, read from the durable store.

    ``store_present`` distinguishes *"the store holds no positions"* from
    *"there is no store on this machine"*. They look identical on a page that
    prints a zero, and they are entirely different facts about whether the
    owner's records are somewhere else.
    """

    store_root: str
    store_present: bool
    open_positions: tuple[PositionLine, ...]
    limits: tuple[LimitLine, ...]
    budget_note: str | NotAvailable
    committed_risk: str | NotAvailable
    available_risk: str | NotAvailable
    cash: str | NotAvailable
    exposure: str | NotAvailable
    snapshot_as_of: datetime | None = None
    #: What the open positions are worth at this run's marks, or why that could
    #: not be stated. Defaulted to the pre-mark answer so a caller that supplies
    #: no valuation gets the honest one rather than a blank.
    market_value: str | NotAvailable = field(
        default_factory=lambda: NotAvailable(
            reason="no price source was consulted for this page",
            owned_by="the valuation layer",
            forbidden_inference=(
                "Do not read an unvalued portfolio as a worthless one."
            ),
        )
    )
    unrealized_pnl: str | NotAvailable = field(
        default_factory=lambda: NotAvailable(
            reason="no price source was consulted for this page",
            owned_by="the valuation layer",
            forbidden_inference=(
                "Do not read an unstated profit or loss as a flat one."
            ),
        )
    )
    #: Where the prices came from, how they were chosen and how old the oldest
    #: one is. Absent when nothing was priced.
    marks_note: str | NotAvailable = field(
        default_factory=lambda: NotAvailable(
            reason="no price source was consulted for this page",
            owned_by="the valuation layer",
            forbidden_inference=(
                "Do not read the absence of a price source as a fresh one."
            ),
        )
    )

    def __post_init__(self) -> None:
        _text(self.store_root, "store_root")
        if not isinstance(self.store_present, bool):
            raise TypeError("store_present must be a bool")
        _tuple_of(self.open_positions, PositionLine, "open_positions")
        _tuple_of(self.limits, LimitLine, "limits")
        for name in (
            "budget_note",
            "committed_risk",
            "available_risk",
            "cash",
            "exposure",
            "market_value",
            "unrealized_pnl",
            "marks_note",
        ):
            value = getattr(self, name)
            if isinstance(value, NotAvailable):
                continue
            _text(value, name)
        if self.snapshot_as_of is not None and not isinstance(
            self.snapshot_as_of, datetime
        ):
            raise TypeError("snapshot_as_of must be a datetime or None")

    @property
    def open_count(self) -> int:
        return len(self.open_positions)


@dataclass(frozen=True, slots=True)
class OpportunityLine:
    """One setup, carrying only values the engine already computed.

    ``direction`` is the assessment's own `Direction.value`, passed through
    untouched. This package never decides a side, never re-derives one, and
    contains no directional vocabulary of its own — ADR-0028's boundary, held by
    carrying the string the engine produced rather than naming a member.

    **The five approval fields are `None` when no approval was computed, and that
    is not the same as an approval that found nothing.** `--no-records` skips the
    store, a store with no risk budget has no limits to check against, and a
    watchlist symbol with no stop has no risk denominator — in all three cases
    this page did not check, and `Opportunities.approval_note` says which. A
    blank rendered as a clean bill of health is the single most expensive
    misreading this page can produce, so `None` prints as a stated absence rather
    than as nothing.

    **Every approval value is a string this package did not compute.**
    `approval_status` is `ApprovalStatus.value`, `recommended_size` and
    `open_risk_after` are already-formatted figures, and the two reason tuples
    are `ApprovalReason.statement` verbatim. `fmis.today` computes no monetary
    quantity — `TD-1`, unchanged.
    """

    symbol: str
    state: str
    sufficiency: str
    direction: str | None = None
    risk_reward: float | None = None
    stop: float | None = None
    target: float | None = None
    thesis: tuple[str, ...] = ()
    confirmation: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    approval_status: str | None = None
    recommended_size: str | None = None
    open_risk_after: str | None = None
    blocking_reasons: tuple[str, ...] = ()
    approval_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("symbol", "state", "sufficiency"):
            _text(getattr(self, name), name)
        if self.direction is not None:
            _text(self.direction, "direction")
        for name in ("risk_reward", "stop", "target"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number or None")
        for name in ("thesis", "confirmation", "invalidation"):
            _strings(getattr(self, name), name)
        for name in ("approval_status", "recommended_size", "open_risk_after"):
            value = getattr(self, name)
            if value is None:
                continue
            _text(value, name)
        for name in ("blocking_reasons", "approval_warnings"):
            _strings(getattr(self, name), name)
        if self.approval_status is None and (
            self.blocking_reasons or self.approval_warnings
        ):
            raise TodayError(
                "an opportunity carries approval reasons with no approval "
                "status; reasons produced by an evaluation that is not reported "
                "would read as objections nobody could trace to a verdict"
            )

    @property
    def was_approved_against_limits(self) -> bool:
        """Whether an approval was computed at all. **Not whether it passed.**

        Named at length on purpose. A shorter `is_approved` would be read as
        *"this trade is fine"* by exactly the reader this page exists to protect,
        and the status is a three-valued string precisely because a boolean
        cannot carry `INDETERMINATE`.
        """
        return self.approval_status is not None


@dataclass(frozen=True, slots=True)
class WaitGroup:
    """Symbols that reached `WAIT` through one policy branch, grouped by its text.

    Grouped on the engine's own verbatim wording, exactly as
    `fmis.swing_setup.scan_report` groups them, so the two surfaces cannot
    disagree about what a reason is.
    """

    reason: str
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.reason, "reason")
        _strings(self.symbols, "symbols")
        if not self.symbols:
            raise TodayError("a wait group with no symbols is not a group")


@dataclass(frozen=True, slots=True)
class FailedSymbol:
    """A symbol whose analysis did not happen. Never a `WAIT`, never a candidate."""

    symbol: str
    detail: str

    def __post_init__(self) -> None:
        _text(self.symbol, "symbol")
        _text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class Opportunities:
    """Today's setups, grouped by the engine's own state and nothing else.

    Order inside every group is scan order — the order the watchlist was
    requested in — preserved from the run. Sorting any of these tuples by a
    property of the analysis would make the top row read as the best idea
    whatever the header says.
    """

    confirmed: tuple[OpportunityLine, ...]
    candidates: tuple[OpportunityLine, ...]
    waiting: tuple[WaitGroup, ...]
    failed: tuple[FailedSymbol, ...]
    #: Whether an approval was computed for the actionable lines, and — when one
    #: was not — which input was missing. Defaulted to the honest pre-approval
    #: answer so a caller that supplies no approvals gets a stated absence rather
    #: than a blank.
    approval_note: str | NotAvailable = field(
        default_factory=lambda: NotAvailable(
            reason="no approval was computed for this page",
            owned_by="the position-sizing layer (fmits approve)",
            forbidden_inference=(
                "Do not read an unapproved candidate as one your limits permit. "
                "Nothing was measured against them."
            ),
        )
    )

    def __post_init__(self) -> None:
        _tuple_of(self.confirmed, OpportunityLine, "confirmed")
        _tuple_of(self.candidates, OpportunityLine, "candidates")
        _tuple_of(self.waiting, WaitGroup, "waiting")
        _tuple_of(self.failed, FailedSymbol, "failed")
        if not isinstance(self.approval_note, NotAvailable):
            _text(self.approval_note, "approval_note")

    @property
    def actionable_count(self) -> int:
        return len(self.confirmed) + len(self.candidates)

    @property
    def waiting_count(self) -> int:
        return sum(len(group.symbols) for group in self.waiting)


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One setup in the attention queue, with everything qualifying it attached.

    ``blocked_by`` holds `BLOCK`-severity warnings only. An entry that carries
    one is not a worse opportunity — it is one the system refuses to produce a
    number for, which is a different statement and is rendered in a different
    group.
    """

    opportunity: OpportunityLine
    warnings: tuple[WorkspaceWarning, ...] = ()
    blocked_by: tuple[WorkspaceWarning, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, OpportunityLine):
            raise TypeError("opportunity must be an OpportunityLine")
        _tuple_of(self.warnings, WorkspaceWarning, "warnings")
        _tuple_of(self.blocked_by, WorkspaceWarning, "blocked_by")
        for position, warning in enumerate(self.blocked_by):
            if warning.severity is not WarningSeverity.BLOCK:
                raise TodayError(
                    f"blocked_by[{position}] is {warning.severity.value}, not a "
                    "block; a warning is not a refusal and the page must not "
                    "render it as one"
                )
        for position, warning in enumerate(self.warnings):
            if warning.severity is WarningSeverity.BLOCK:
                raise TodayError(
                    f"warnings[{position}] is a block and belongs in blocked_by; "
                    "the two registers do not share a list"
                )

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_by)


@dataclass(frozen=True, slots=True)
class PriorityQueue:
    """What deserves attention, in attention order — never in desirability order.

    ``ordering`` states the rule in words and is printed on the page. It is a
    field rather than a constant in the renderer so that the object itself
    carries its own contract to every future consumer, including one that never
    renders text.

    ``needs_attention`` and ``blocked`` are two lists because they answer two
    different questions: *what should I look at* and *what will this system
    refuse to size*. A single list ordered by some combination of the two would
    be the composite score this repository has refused everywhere else.
    """

    needs_attention: tuple[QueueEntry, ...]
    blocked: tuple[QueueEntry, ...]
    ordering: str

    def __post_init__(self) -> None:
        _tuple_of(self.needs_attention, QueueEntry, "needs_attention")
        _tuple_of(self.blocked, QueueEntry, "blocked")
        _text(self.ordering, "ordering")
        for position, entry in enumerate(self.needs_attention):
            if entry.is_blocked:
                raise TodayError(
                    f"needs_attention[{position}] carries a block and belongs in "
                    "blocked"
                )
        for position, entry in enumerate(self.blocked):
            if not entry.is_blocked:
                raise TodayError(
                    f"blocked[{position}] carries no block; an entry in this list "
                    "must name what refused it"
                )

    @property
    def is_empty(self) -> bool:
        return not self.needs_attention and not self.blocked


@dataclass(frozen=True, slots=True)
class JournalLine:
    """One journal entry, reduced to what a summary shows.

    ``recollection`` is carried because an entry written after the decision it
    concerns resolved is excluded from cohort statistics by default, and a
    summary that hides which entries those are teaches the owner they are the
    same kind of record.
    """

    entry_id: str
    kind: str
    recorded_at: datetime
    author: str
    title: str
    recollection: bool

    def __post_init__(self) -> None:
        for name in ("entry_id", "kind", "author", "title"):
            _text(getattr(self, name), name)
        if not isinstance(self.recorded_at, datetime):
            raise TypeError("recorded_at must be a datetime")
        if not isinstance(self.recollection, bool):
            raise TypeError("recollection must be a bool")


@dataclass(frozen=True, slots=True)
class ClosedPositionLine:
    """One position that has crossed flat, with its realized result as recorded."""

    market: str
    book: str
    closed_at: datetime
    realized_net: str
    trade_count: int

    def __post_init__(self) -> None:
        for name in ("market", "book", "realized_net"):
            _text(getattr(self, name), name)
        if not isinstance(self.closed_at, datetime):
            raise TypeError("closed_at must be a datetime")
        _count(self.trade_count, "trade_count")


@dataclass(frozen=True, slots=True)
class JournalSummary:
    """Recent decisions, recently closed positions, and the latest notes."""

    entries: tuple[JournalLine, ...]
    closed_positions: tuple[ClosedPositionLine, ...]
    decisions: tuple[str, ...]
    note: str | NotAvailable

    def __post_init__(self) -> None:
        _tuple_of(self.entries, JournalLine, "entries")
        _tuple_of(self.closed_positions, ClosedPositionLine, "closed_positions")
        _strings(self.decisions, "decisions")
        if not isinstance(self.note, NotAvailable):
            _text(self.note, "note")


@dataclass(frozen=True, slots=True)
class AnalysisLine:
    """One durable analysis artifact, by its metadata only. No payload is opened."""

    record_id: str
    record_type: str
    subject: str
    analysis_as_of: datetime

    def __post_init__(self) -> None:
        for name in ("record_id", "record_type", "subject"):
            _text(getattr(self, name), name)
        if not isinstance(self.analysis_as_of, datetime):
            raise TypeError("analysis_as_of must be a datetime")


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    """What FMITS has durably recorded about its own past analyses.

    ``change_note`` is a statement, never a diff. Comparing two archived
    analyses requires decoding both payloads and defining what a difference is;
    neither exists, and claiming a comparison this package did not perform would
    be worse than saying so.
    """

    archived: tuple[AnalysisLine, ...]
    citations: tuple[AnalysisLine, ...]
    snapshots: tuple[AnalysisLine, ...]
    change_note: str | NotAvailable

    def __post_init__(self) -> None:
        for name in ("archived", "citations", "snapshots"):
            _tuple_of(getattr(self, name), AnalysisLine, name)
        if not isinstance(self.change_note, NotAvailable):
            _text(self.change_note, "change_note")


@dataclass(frozen=True, slots=True)
class TodayWorkspace:
    """One evening's complete workspace: seven sections in a fixed order.

    The order is the design decision. Health, capital and existing exposure come
    before opportunity, because the highest-probability way this product loses
    real money is not a bad signal — it is a new position taken while the owner
    is already at his limit, or three simultaneous same-direction setups on three
    correlated majors. A dashboard that opens with opportunities is a dashboard
    that produces trades.

    ``reference_time`` is supplied by the outer boundary. Nothing in this
    package reads a clock, so two runs over the same inputs are identical.
    """

    reference_time: datetime
    objective: str
    source: str
    market: MarketOverview
    portfolio: PortfolioOverview
    opportunities: Opportunities
    queue: PriorityQueue
    journal: JournalSummary
    analysis: AnalysisSummary
    warnings: tuple[WorkspaceWarning, ...]
    limitations: tuple[tuple[str, str], ...]
    schema_version: int = TODAY_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.reference_time, datetime):
            raise TypeError(
                f"reference_time must be a datetime, got "
                f"{type(self.reference_time).__name__}"
            )
        for name in ("objective", "source"):
            _text(getattr(self, name), name)
        pairs = (
            ("market", MarketOverview),
            ("portfolio", PortfolioOverview),
            ("opportunities", Opportunities),
            ("queue", PriorityQueue),
            ("journal", JournalSummary),
            ("analysis", AnalysisSummary),
        )
        for name, kind in pairs:
            value = getattr(self, name)
            if not isinstance(value, kind):
                raise TypeError(
                    f"{name} must be a {kind.__name__}, got {type(value).__name__}"
                )
        _tuple_of(self.warnings, WorkspaceWarning, "warnings")
        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple of (code, text) pairs")
        for position, pair in enumerate(self.limitations):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError(f"limitations[{position}] must be a 2-tuple")
            _text(pair[0], f"limitations[{position}] code")
            _text(pair[1], f"limitations[{position}] text")
        if not self.limitations:
            raise TodayError(
                "a workspace must state its limitations; a page of results with "
                "no caveats is the excessive confidence SPEC section 7 warns "
                "against"
            )
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise TypeError("schema_version must be an int")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def warnings_of(self, kind: WarningClass) -> tuple[WorkspaceWarning, ...]:
        """Every warning in one category, in the order they were raised."""
        if not isinstance(kind, WarningClass):
            raise TypeError(
                f"kind must be a WarningClass, got {type(kind).__name__}"
            )
        return tuple(warning for warning in self.warnings if warning.kind is kind)

    def warning(self, code: str) -> WorkspaceWarning | None:
        """One warning by its code, or `None` if this run did not raise it."""
        wanted = _text(code, "code")
        for warning in self.warnings:
            if warning.code == wanted:
                return warning
        return None

    @property
    def blocking_warnings(self) -> tuple[WorkspaceWarning, ...]:
        return tuple(
            warning
            for warning in self.warnings
            if warning.severity is WarningSeverity.BLOCK
        )
