"""Value types for the Swing Decision Workspace.

A `SwingWorkspace` is a **first-class object**, not terminal text — the same
contract `Workspace` (AK), `DailyRun` (AN) and `TodayWorkspace` (BJ) already
hold. The renderer reads this model and nothing else.

**Almost nothing here is a new type.** `NotAvailable`, `WorkspaceWarning`,
`OpportunityLine`, `MarketOverview`, `PortfolioOverview` and `PerformanceSummary`
are `fmis.today`'s own and are imported rather than redeclared. A second
`OpportunityLine` with the same eight fields would be a second place a candidate
is described, and the two would drift the first time one gained a column. What
this module adds is only what composition needs and nothing below produces: an
explicit ordering key, the per-setup digests that hang off one row, and the
page's own container.

**The ordering is a key, not a score.** `RankComponent` carries the *name* of the
key, the *value* it took, the integer that value sorts as, and the *source* that
produced the value. A reader looking at two adjacent rows can therefore
reconstruct exactly why one is above the other, component by component, without
consulting this source. There is no weight, no total, no composite and no field
in which one could be recorded — a rank position is the index of a row in a
tuple, never a number this package computed about a setup.

**Readiness is not desirability, and the object says so.** `RANKING_RULE` travels
on the workspace itself rather than being printed by the renderer alone, so a
future JSON or notification consumer inherits the sentence with the data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any

from fmis.today import (
    MarketOverview,
    NotAvailable,
    OpportunityLine,
    PerformanceSummary,
    PortfolioOverview,
    WorkspaceWarning,
)

__all__ = [
    "SWING_WORKSPACE_SCHEMA_VERSION",
    "SwingWorkspaceError",
    "RankComponent",
    "RankKey",
    "EvidenceDigest",
    "EvidenceLine",
    "FactorLine",
    "TimeframeLine",
    "SymbolDecision",
    "RankedSetup",
    "NoTradeGroup",
    "UnanalysedSymbol",
    "PaperPosition",
    "BookExposure",
    "GlobalSummary",
    "SwingWorkspace",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
#: `1` for Milestone BS — the first version of this page.
SWING_WORKSPACE_SCHEMA_VERSION = 1


class SwingWorkspaceError(Exception):
    """Base class for every Swing Decision Workspace failure.

    Follows the package-error convention `TodayError`, `WorkspaceError`,
    `SwingSetupError` and `SetupEvidenceError` established elsewhere, so a caller
    can catch this layer's failures as a group.
    """


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SwingWorkspaceError(f"{name} must be a non-empty str")
    return value


def _strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple of str")
    for position, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise SwingWorkspaceError(f"{name}[{position}] must be a non-empty str")
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


def _count(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int")
    if value < 0:
        raise SwingWorkspaceError(f"{name} cannot be negative")
    return value


@dataclass(frozen=True, slots=True)
class RankComponent:
    """One key in the ordering, with everything needed to check it by hand.

    ``name`` is the key; ``value`` is what this setup's value *was*, in the
    vocabulary the engine that produced it uses; ``rank`` is the integer that
    value sorts as, ascending; ``source`` names the engine or the input the value
    was read from.

    **``rank`` is an ordinal over a stated, finite vocabulary — never a measure.**
    Every component in this package maps a *named state* onto a position in a
    documented list, or carries the position of a symbol in the requested
    watchlist. Nothing is divided, added, weighted or scaled, and there is no
    field here in which a magnitude could be recorded even by accident.
    """

    name: str
    value: str
    rank: int
    source: str

    def __post_init__(self) -> None:
        for name in ("name", "value", "source"):
            _text(getattr(self, name), name)
        _count(self.rank, "rank")


@dataclass(frozen=True, slots=True)
class RankKey:
    """The complete ordering key for one row, in comparison order.

    ``components`` is read left to right: the first component on which two rows
    differ decides their order, and later components are never consulted. That is
    the whole algorithm, and it is a property of this object rather than of the
    function that built it, so a consumer can re-sort a page's rows itself and
    obtain the identical order.

    ``ordinals`` is the tuple actually compared. Derived rather than stored twice
    — two fields that could disagree about what was compared is precisely the
    hidden-weighting failure this type exists to prevent.
    """

    components: tuple[RankComponent, ...]

    def __post_init__(self) -> None:
        _tuple_of(self.components, RankComponent, "components")
        if not self.components:
            raise SwingWorkspaceError(
                "a ranking key with no components would order rows by nothing "
                "stated; every ordering in this package names its keys"
            )
        seen = [component.name for component in self.components]
        if len(set(seen)) != len(seen):
            raise SwingWorkspaceError(
                f"a key names the same component twice: {sorted(seen)}"
            )

    @property
    def ordinals(self) -> tuple[int, ...]:
        """What is compared, and the only thing that is."""
        return tuple(component.rank for component in self.components)

    def explain(self) -> str:
        """The key as one line: `name=value(rank)`, in comparison order."""
        return " · ".join(
            f"{component.name}={component.value}({component.rank})"
            for component in self.components
        )


@dataclass(frozen=True, slots=True)
class EvidenceDigest:
    """`fmis.setup_evidence`'s report for one setup, reduced to counts.

    **Counts and two booleans, all of them projected.** Nothing here is computed:
    every field is `len()` of a group the evidence projection already produced, or
    a flag it already set. A digest carries no total and no strength, because
    `fmis.setup_evidence` deliberately publishes neither — a monotone ordinal with
    no deterministic rule per level is a score in an enum's clothing.

    ``independence_established`` is the field that matters. Three items that all
    restate one upstream fact look exactly like three-fold agreement on a page,
    and the projection's whole purpose is to say when they are not independent.
    ``caveats`` carries, verbatim, the correlations that made it `False`.

    **This digest is never a ranking key.** `RANK_KEYS` names the four keys the
    ordering uses and this is not one of them; a guard test asserts that planting
    a setup with a richer digest cannot move it up the page.
    """

    supporting: int
    conflicting: int
    missing: int
    unavailable: int
    agreeing_families: tuple[str, ...]
    conflicting_families: tuple[str, ...]
    independence_established: bool
    decision_ready: bool
    decision_ready_reason: str
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("supporting", "conflicting", "missing", "unavailable"):
            _count(getattr(self, name), name)
        for name in ("agreeing_families", "conflicting_families", "caveats"):
            _strings(getattr(self, name), name)
        for name in ("independence_established", "decision_ready"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        _text(self.decision_ready_reason, "decision_ready_reason")
        if self.independence_established and self.caveats:
            raise SwingWorkspaceError(
                "independence was established and correlation caveats were "
                "reported at the same time; the caveats are the reasons it was "
                "not, and a report holding both says two different things"
            )


@dataclass(frozen=True, slots=True)
class FactorLine:
    """One `DirectionalFactor`, carried verbatim. Four strings, no fifth.

    The policy tallies *families*, and a page that shows only the conclusion
    ("no directional candidate") hides the shape of the disagreement that
    produced it. Two symbols can both be `WAIT` because one never reached the
    tally and the other reached it and split — and the split is visible here and
    nowhere else on the page.

    ``lean`` is `Lean`'s own value, including its two non-voting members. A
    family that conflicts with itself and one that could not be read are
    different facts, and both are different from a vote.

    **No weight and no field to hold one.** The policy counts agreeing families
    and requires none opposing; it does not add them up, and neither does this.
    """

    family: str
    lean: str
    observed: str
    source: str

    def __post_init__(self) -> None:
        for name in ("family", "lean", "observed", "source"):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class EvidenceLine:
    """One `EvidenceItem`, carried verbatim rather than counted.

    `EvidenceDigest` reduces a whole report to four integers, which answers *how
    many* and never *which*. This carries the item itself, so the owner reads the
    statement the engine wrote, the value it observed, the engine that produced
    it and the timeframe it read — the facts that make one `WAIT` different from
    another.

    ``correlated_with`` and ``independence_note`` are the two fields that must
    never be dropped. They name the items this one is **not** independent of, and
    a surface that prints three correlated observations without them is showing
    one fact three times and calling it corroboration. `SymbolDecision` validates
    that they survive.

    ``as_of`` is `fmis.setup_evidence`'s own value for the item and is carried
    because it is already on the object — **not** a freshness verdict. Nothing in
    this package compares it to a clock, and no field here says fresh or stale.

    **No strength, no weight, no score, no rank** — the omission
    `fmis.setup_evidence.models` makes for the reason its own docstring gives,
    inherited here rather than quietly re-opened one layer up.
    """

    key: str
    status: str
    statement: str
    observed: str
    source: str
    families: tuple[str, ...] = ()
    scope: str | None = None
    as_of: datetime | None = None
    correlated_with: tuple[str, ...] = ()
    independence_note: str | None = None

    def __post_init__(self) -> None:
        for name in ("key", "status", "statement", "observed", "source"):
            _text(getattr(self, name), name)
        _strings(self.families, "families")
        _strings(self.correlated_with, "correlated_with")
        for name in ("scope", "independence_note"):
            value = getattr(self, name)
            if value is not None:
                _text(value, name)
        if self.as_of is not None and not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime or None, got {type(self.as_of).__name__}"
            )


@dataclass(frozen=True, slots=True)
class TimeframeLine:
    """One timeframe role's reading instant and how old it is on this page.

    **The age is not computed here.** ``age`` is a `timedelta` this package was
    *handed*, produced by `TimeframeReading.age_at` beside the instant it
    measures — the same arrangement `fmis.market_pulse` uses for the same
    reason, and the reason a guard forbids this package from subtracting
    anything at all.

    **There is no freshness verdict, and no field to hold one.** No `fresh`, no
    `stale`, no threshold, no colour. This repository has no validated staleness
    bound for any of the three roles, and one invented so a cell could be
    painted green would be an unvalidated policy presented as a fact. The reader
    gets the instant, the age and the bar count, and decides.

    ``age`` is `None` exactly when no reference instant was available to measure
    against — a stated absence, never a zero.
    """

    role: str
    interval: str
    as_of: datetime
    closed_count: int
    age: timedelta | None = None
    #: This role's structural trend, as the engine reported it — a **value**,
    #: read off `SetupReadings.structural_trend_for`, never recovered by
    #: matching an interval out of a provenance string. `None` is a stated gap.
    structural_trend: str | None = None

    def __post_init__(self) -> None:
        for name in ("role", "interval"):
            _text(getattr(self, name), name)
        if self.structural_trend is not None:
            _text(self.structural_trend, "structural_trend")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        _count(self.closed_count, "closed_count")
        if self.age is not None and not isinstance(self.age, timedelta):
            raise TypeError(
                f"age must be a timedelta or None, got {type(self.age).__name__}"
            )


@dataclass(frozen=True, slots=True)
class SymbolDecision:
    """**One scanned symbol's own decision record.** One per symbol, every state.

    The section that exists because the other four do not cover the population.
    `opportunities` and `wait_list` carry a row per *actionable* symbol;
    `no_trade` carries a row per *reason*, with the symbols that reached it
    listed inside — so a `WAIT` symbol has no row of its own anywhere, and
    everything the engine concluded about it beyond one shared sentence is
    dropped at this seam. This is that row.

    **Nothing here is computed and nothing is new.** ``state``, ``direction``,
    ``sufficiency``, ``thesis``, ``regime_context``, ``confirmation`` and
    ``invalidation`` are `SetupAssessment`'s own fields; ``factors`` are its own
    `DirectionalFactor` list; the four evidence groups, the family lists, the
    independence flag and its caveats are `fmis.setup_evidence`'s own report,
    carried item by item rather than reduced to counts. ``classification`` is the
    identical `read and declined` / `could not be classified` split
    `no_trade_groups` already applies, and ``reason`` is the identical verbatim
    first thesis line that function already groups on — so the per-symbol row and
    the grouped one cannot disagree about why a symbol is where it is.

    **This object carries no ordering and cannot acquire one.** There is no
    score, no closeness, no confidence, no rank and no position field. The
    sequence of `SwingWorkspace.decisions` is scan order — the order the owner
    asked for the symbols in — and a guard test asserts that no field name here
    matches a ranking vocabulary, so a later change cannot turn this projection
    into the unvalidated opportunity ranking the research record forbids.

    ``evidence_reason`` is set exactly when the evidence projection declined, and
    the four groups are then empty. Empty groups with no reason mean *the
    projection ran and found nothing in that group*; empty groups with a reason
    mean *the projection refused*, and those are different facts.
    """

    symbol: str
    state: str
    classification: str
    reason: str
    sufficiency: str
    as_of: datetime
    direction: str | None = None
    thesis: tuple[str, ...] = ()
    regime_context: tuple[str, ...] = ()
    confirmation: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    factors: tuple[FactorLine, ...] = ()
    supporting: tuple[EvidenceLine, ...] = ()
    conflicting: tuple[EvidenceLine, ...] = ()
    missing: tuple[EvidenceLine, ...] = ()
    unavailable: tuple[EvidenceLine, ...] = ()
    agreeing_families: tuple[str, ...] = ()
    conflicting_families: tuple[str, ...] = ()
    independence_established: bool = False
    independence_caveats: tuple[str, ...] = ()
    evidence_warnings: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    decision_ready: bool = False
    decision_ready_reason: str = ""
    evidence_reason: str | None = None
    #: The operator decision layer, projected by `fmis.swing_setup`. Carried by
    #: reference rather than flattened into strings here: `DevelopingEvidence`
    #: names a **side**, and ADR-0028 makes `fmis.swing_setup` the one package
    #: permitted to spell one. Reproducing its vocabulary in this package would
    #: put the word in a second place; carrying the object keeps it in one.
    #:
    #: `None` on a decision assembled without it — a page missing the operator
    #: summary, never a page that invents it.
    developing: Any | None = None
    blocker: Any | None = None
    #: One entry per timeframe role that was read, in the sheet's own order:
    #: context, then setup, then execution. Empty when the result carried no
    #: readings, which the surfaces state rather than paper over.
    timeframes: tuple[TimeframeLine, ...] = ()
    #: The deterministic trade-planning arithmetic for this symbol, projected by
    #: `fmis.risk_policy`. Carried by reference for the reason `developing` and
    #: `blocker` are: `TradeRiskPlan` states a **direction** and a **size**, and
    #: reproducing either vocabulary here would put it in a second place.
    #:
    #: `None` on a decision assembled without a declared risk policy — a page
    #: with no planning section, never a page that invents one. It is never a
    #: zero size, and a `TradeRiskPlan` for a `WAIT` symbol carries no figures at
    #: all: a waiting symbol with a quantity beside it reads as almost a trade.
    #:
    #: **Nothing here reaches the decision.** The plan is computed from the
    #: assessment; the assessment is never computed from the plan, and no field
    #: on this record changes because a size could or could not be produced.
    plan: Any | None = None

    def __post_init__(self) -> None:
        for name in ("symbol", "state", "classification", "reason", "sufficiency"):
            _text(getattr(self, name), name)
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if self.direction is not None:
            _text(self.direction, "direction")
        for name in (
            "thesis",
            "regime_context",
            "confirmation",
            "invalidation",
            "agreeing_families",
            "conflicting_families",
            "independence_caveats",
            "evidence_warnings",
            "open_questions",
        ):
            _strings(getattr(self, name), name)
        _tuple_of(self.factors, FactorLine, "factors")
        _tuple_of(self.timeframes, TimeframeLine, "timeframes")
        roles = [line.role for line in self.timeframes]
        if len(set(roles)) != len(roles):
            raise SwingWorkspaceError(
                f"each timeframe role may appear once; got {roles}. Two "
                "readings for one role is two answers to when that timeframe "
                "was last seen"
            )
        for name in ("supporting", "conflicting", "missing", "unavailable"):
            _tuple_of(getattr(self, name), EvidenceLine, name)
        for name in ("independence_established", "decision_ready"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        if self.evidence_reason is not None:
            _text(self.evidence_reason, "evidence_reason")
            if self.groups_are_populated:
                raise SwingWorkspaceError(
                    "the evidence projection was reported as having refused and "
                    "evidence items were carried anyway; a stated refusal beside "
                    "the evidence it refused to produce says two different things"
                )
        else:
            _text(self.decision_ready_reason, "decision_ready_reason")
        if self.independence_established and self.independence_caveats:
            raise SwingWorkspaceError(
                "independence was established and correlation caveats were "
                "reported at the same time; the caveats are the reasons it was "
                "not, and a decision holding both says two different things"
            )

    @property
    def groups_are_populated(self) -> bool:
        """Whether any evidence item at all was carried, in any group."""
        return bool(
            self.supporting or self.conflicting or self.missing or self.unavailable
        )

    @property
    def evidence_available(self) -> bool:
        """Whether the projection ran. **Never whether the evidence is good.**"""
        return self.evidence_reason is None

    @property
    def correlated_keys(self) -> frozenset[str]:
        """Every item key some carried item declares it is not independent of.

        A lookup over what the projection already stated, so a renderer marks the
        non-independent items without re-deriving which they are — and so a test
        can assert the disclosure survived this seam.
        """
        return frozenset(
            key
            for group in (
                self.supporting,
                self.conflicting,
                self.missing,
                self.unavailable,
            )
            for item in group
            for key in item.correlated_with
        )


@dataclass(frozen=True, slots=True)
class RankedSetup:
    """One setup on the page: the engine's line, its key, and what hangs off it.

    ``position`` is 1-based and is **the index of this row in its own section**,
    nothing more. It is stored so a renderer and a notification agree about what
    "first" means without either re-deriving it, and it is deliberately not a
    field anything may compare across sections.

    The three attachments are each `NotAvailable` rather than `None` when they
    could not be produced, carrying the reason and the inference the absence
    forbids. A blank evidence digest reads as *"no evidence"*; a stated one reads
    as *"the projection refused, and here is why"*, and those are different facts.
    """

    opportunity: OpportunityLine
    key: RankKey
    position: int
    evidence: EvidenceDigest | NotAvailable
    identity: str | NotAvailable
    paper_status: str | NotAvailable
    #: Whether the owner already **holds** this market, in any book, according to
    #: the recorded positions this page is already showing.
    #:
    #: A second field rather than a widening of ``paper_status``, and the reason
    #: is the hostile case that produced it: a row reading *"paper: none"* beside
    #: a real open position answers *"am I already in this?"* with the wrong half
    #: of the truth. Simulated exposure and recorded exposure are different facts
    #: about different money — `AP` §5.5 makes the book the economic
    #: classification — and one field holding both would have to choose which one
    #: to state.
    held: str | NotAvailable = field(
        default_factory=lambda: NotAvailable(
            reason="no recorded position was checked for this market",
            owned_by="the durable store",
            forbidden_inference=(
                "Do not read this as holding nothing here. Nothing was checked."
            ),
        )
    )

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, OpportunityLine):
            raise TypeError(
                f"opportunity must be an OpportunityLine, got "
                f"{type(self.opportunity).__name__}"
            )
        if not isinstance(self.key, RankKey):
            raise TypeError(f"key must be a RankKey, got {type(self.key).__name__}")
        if not isinstance(self.position, int) or isinstance(self.position, bool):
            raise TypeError("position must be an int")
        if self.position < 1:
            raise SwingWorkspaceError(
                "position is 1-based; a row at position 0 would print as the "
                "row before the first one"
            )
        if not isinstance(self.evidence, (EvidenceDigest, NotAvailable)):
            raise TypeError("evidence must be an EvidenceDigest or a NotAvailable")
        for name in ("identity", "paper_status", "held"):
            value = getattr(self, name)
            if isinstance(value, NotAvailable):
                continue
            _text(value, name)

    @property
    def symbol(self) -> str:
        return self.opportunity.symbol


@dataclass(frozen=True, slots=True)
class NoTradeGroup:
    """Symbols the engine read and reached no directional candidate on.

    Grouped on the engine's own verbatim wording, exactly as
    `fmis.swing_setup.scan_report` and `fmis.today.sections` group them, so no two
    surfaces in this repository can disagree about what a reason is.

    ``classification`` separates *"the engine read this and declined"* from
    *"the engine could not classify it at all"* — `fmis.today.MarketOverview`
    already splits the same population on the same judgement, and shown as one
    number a quiet system and a quiet market are indistinguishable.
    """

    reason: str
    classification: str
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.reason, "reason")
        _text(self.classification, "classification")
        _strings(self.symbols, "symbols")
        if not self.symbols:
            raise SwingWorkspaceError("a no-trade group with no symbols is not a group")


@dataclass(frozen=True, slots=True)
class UnanalysedSymbol:
    """A symbol that produced no analysis at all.

    **Never a no-trade result.** A provider outage and a market with no setup are
    the same blank on a page that merges them, and only one of the two is a
    statement about the market.
    """

    symbol: str
    detail: str

    def __post_init__(self) -> None:
        _text(self.symbol, "symbol")
        _text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class PaperPosition:
    """One simulated trade, with the seven figures the brief names.

    Every one of them is read off the `TradeMonitor` the paper package's own read
    path produced — entry, risk, R, MFE, MAE, bars and state. **Nothing here is
    computed**, so a figure on this page and the same figure under
    `fmits trade status` are one calculation rendered twice rather than two that
    happen to agree today.

    The excursions are `NotAvailable` far more often than they are numbers, and
    that is correct rather than a gap: this page reads no simulation candle, so an
    unfinished trade has observed no excursion. A page that printed a zero there
    would make every open trade look like one that never went against the owner.
    """

    activation_id: str
    market: str
    state: str
    open_size: str
    bars_in_trade: int
    stop_widenings: int
    entry: str | NotAvailable
    initial_risk: str | NotAvailable
    total_r: str | NotAvailable
    max_favourable_r: str | NotAvailable
    max_adverse_r: str | NotAvailable
    stop: str
    initial_stop: str

    def __post_init__(self) -> None:
        for name in (
            "activation_id",
            "market",
            "state",
            "open_size",
            "stop",
            "initial_stop",
        ):
            _text(getattr(self, name), name)
        for name in ("bars_in_trade", "stop_widenings"):
            _count(getattr(self, name), name)
        for name in (
            "entry",
            "initial_risk",
            "total_r",
            "max_favourable_r",
            "max_adverse_r",
        ):
            value = getattr(self, name)
            if isinstance(value, NotAvailable):
                continue
            _text(value, name)

    @property
    def halted(self) -> bool:
        """Derived, never stored: one fact, one place.

        `fmis.today.PaperTradeLine` derives the same property from the same
        folded state string, and the two must agree by construction rather than
        by two copies of one comparison staying in step.
        """
        return self.state == "ambiguous"

    @property
    def stop_moved(self) -> bool:
        return self.stop != self.initial_stop


@dataclass(frozen=True, slots=True)
class BookExposure:
    """How many open positions one book holds, and what they are worth.

    Two of these rather than one set of totals, for the reason `AP` §5.5 gives:
    the book is the economic classification, and a page that added a simulated
    position to a real one would put play money into a statement about the
    owner's capital.

    ``market_value`` is `NotAvailable` when no price source was consulted. There
    is no arithmetic in this type; the figures are selected and formatted by the
    section that builds it, from values the valuation layer already produced.
    """

    label: str
    open_positions: int
    market_value: str | NotAvailable

    def __post_init__(self) -> None:
        _text(self.label, "label")
        _count(self.open_positions, "open_positions")
        if not isinstance(self.market_value, NotAvailable):
            _text(self.market_value, "market_value")


@dataclass(frozen=True, slots=True)
class GlobalSummary:
    """The eight facts the owner reads before anything else on the page.

    **Every field is a count of something already established, or a value another
    layer already produced.** There is no summary judgement here and no field one
    could be written into: *"3 confirmed setups"* removes work from the sections
    below, while *"a good morning"* would invent information the engines never
    produced.

    ``risk_state`` is a **description of what is recorded and what was measured
    against it**, never a traffic light. No layer in this repository measures a
    limit yet — `fmis.today` renders every one of them as indeterminate with its
    reason — so a green/amber/red headline here would be an invention. When that
    changes, this field carries the fact and still not the colour.
    """

    scanned: int
    confirmed: int
    candidates: int
    waiting: int
    unanalysed: int
    open_positions: int
    paper_positions: int
    breadth: tuple[tuple[str, int], ...]
    regime_note: str
    risk_state: str | NotAvailable
    open_exposure: str | NotAvailable
    analysis_as_of: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "scanned",
            "confirmed",
            "candidates",
            "waiting",
            "unanalysed",
            "open_positions",
            "paper_positions",
        ):
            _count(getattr(self, name), name)
        if not isinstance(self.breadth, tuple):
            raise TypeError("breadth must be a tuple of (label, count) pairs")
        for position, pair in enumerate(self.breadth):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError(f"breadth[{position}] must be a 2-tuple")
            _text(pair[0], f"breadth[{position}] label")
            _count(pair[1], f"breadth[{position}] count")
        _text(self.regime_note, "regime_note")
        for name in ("risk_state", "open_exposure"):
            value = getattr(self, name)
            if isinstance(value, NotAvailable):
                continue
            _text(value, name)
        if self.analysis_as_of is not None and not isinstance(
            self.analysis_as_of, datetime
        ):
            raise TypeError("analysis_as_of must be a datetime or None")

    @property
    def actionable(self) -> int:
        return self.confirmed + self.candidates


@dataclass(frozen=True, slots=True)
class SwingWorkspace:
    """One operator page: nine sections, in a fixed order.

    The order is the design decision and it is inherited from `TodayWorkspace`
    unchanged: what the market is doing and what the owner already holds come
    before what could be taken. A dashboard that opens with opportunities is a
    dashboard that produces trades.

    ``reference_time`` is supplied by the outer boundary. Nothing in this package
    reads a clock, so two runs over the same inputs produce byte-identical pages.

    **A setup appears in exactly one section.** `opportunities`, `wait_list` and
    `no_trade` partition the scan on the engine's own three states, and a
    validation here rejects a workspace in which one symbol reached two of them —
    a duplicated row is the defect a reader is least able to detect and most
    likely to act on twice.
    """

    reference_time: datetime
    objective: str
    source: str
    summary: GlobalSummary
    market: MarketOverview
    opportunities: tuple[RankedSetup, ...]
    wait_list: tuple[RankedSetup, ...]
    no_trade: tuple[NoTradeGroup, ...]
    unanalysed: tuple[UnanalysedSymbol, ...]
    paper: tuple[PaperPosition, ...]
    paper_note: str | NotAvailable
    portfolio: PortfolioOverview
    books: tuple[BookExposure, ...]
    statistics: PerformanceSummary
    warnings: tuple[WorkspaceWarning, ...]
    ranking_rule: str
    limitations: tuple[tuple[str, str], ...]
    #: One row per scanned symbol that produced an assessment, in **scan order**.
    #:
    #: Spans the three decision sections rather than partitioning them: a symbol
    #: with a row in `opportunities` also has one here, and a `WAIT` symbol
    #: — which has no row of its own in any other section — has one here only.
    #: The section-exclusivity check deliberately does not consult this tuple,
    #: because overlapping with the other sections is what it is for.
    #:
    #: Defaulted to empty so that every existing construction of this object
    #: stays valid and a page assembled without decisions is a page missing a
    #: section, never a page that fails to build.
    decisions: tuple[SymbolDecision, ...] = ()
    schema_version: int = SWING_WORKSPACE_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.reference_time, datetime):
            raise TypeError(
                f"reference_time must be a datetime, got "
                f"{type(self.reference_time).__name__}"
            )
        for name in ("objective", "source", "ranking_rule"):
            _text(getattr(self, name), name)
        for name, kind in (
            ("summary", GlobalSummary),
            ("market", MarketOverview),
            ("portfolio", PortfolioOverview),
            ("statistics", PerformanceSummary),
        ):
            value = getattr(self, name)
            if not isinstance(value, kind):
                raise TypeError(
                    f"{name} must be a {kind.__name__}, got {type(value).__name__}"
                )
        _tuple_of(self.opportunities, RankedSetup, "opportunities")
        _tuple_of(self.wait_list, RankedSetup, "wait_list")
        _tuple_of(self.no_trade, NoTradeGroup, "no_trade")
        _tuple_of(self.unanalysed, UnanalysedSymbol, "unanalysed")
        _tuple_of(self.decisions, SymbolDecision, "decisions")
        self._require_one_decision_per_symbol()
        _tuple_of(self.paper, PaperPosition, "paper")
        _tuple_of(self.books, BookExposure, "books")
        _tuple_of(self.warnings, WorkspaceWarning, "warnings")
        if not isinstance(self.paper_note, NotAvailable):
            _text(self.paper_note, "paper_note")

        self._require_one_section_per_symbol()

        if not isinstance(self.limitations, tuple):
            raise TypeError("limitations must be a tuple of (code, text) pairs")
        for position, pair in enumerate(self.limitations):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError(f"limitations[{position}] must be a 2-tuple")
            _text(pair[0], f"limitations[{position}] code")
            _text(pair[1], f"limitations[{position}] text")
        if not self.limitations:
            raise SwingWorkspaceError(
                "a workspace must state its limitations; a page of results with "
                "no caveats is the excessive confidence SPEC section 7 warns "
                "against"
            )
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise TypeError("schema_version must be an int")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def _require_one_decision_per_symbol(self) -> None:
        """No symbol may carry two decision records.

        Unlike the section rule below, repetition is **not** permitted here even
        for a symbol requested twice: two records for one market are two answers
        to *"what is the current decision on this?"*, and the detail surface
        looks a symbol up by name and would silently show whichever came first.
        The scan's own results are keyed by symbol upstream, so this rejects a
        defect rather than a legitimate duplicate request.
        """
        seen: set[str] = set()
        for decision in self.decisions:
            if decision.symbol in seen:
                raise SwingWorkspaceError(
                    f"{decision.symbol!r} carries two decision records; one "
                    "symbol has one current decision, and a page holding two "
                    "cannot say which is shown"
                )
            seen.add(decision.symbol)

    def _require_one_section_per_symbol(self) -> None:
        """No symbol may occupy two **different** decision sections.

        Checked on the object rather than in the builder, so that a second
        composition root — a notification, a web page, a test fixture — cannot
        assemble the contradiction the builder is careful not to produce. A
        symbol confirmed *and* waiting is two irreconcilable claims about one
        market, and it is the defect a reader is least able to detect.

        **Repetition inside one section is permitted, and the distinction is not
        a loosening.** `fmits workspace BTCUSDT BTCUSDT` asks about one symbol
        twice; the scan answers twice, and two identical rows are the honest
        rendering of what was requested. An earlier draft rejected that too and
        lost the entire page over a repeated command-line argument — found by
        attacking the surface rather than by a test, which is why the two cases
        are now told apart.
        """
        placed: dict[str, str] = {}
        groups: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("opportunities", tuple(row.symbol for row in self.opportunities)),
            ("wait_list", tuple(row.symbol for row in self.wait_list)),
            (
                "no_trade",
                tuple(
                    symbol for group in self.no_trade for symbol in group.symbols
                ),
            ),
            ("unanalysed", tuple(entry.symbol for entry in self.unanalysed)),
        )
        for section, symbols in groups:
            for symbol in symbols:
                if placed.get(symbol, section) != section:
                    raise SwingWorkspaceError(
                        f"{symbol!r} appears in {placed[symbol]} and in {section}; "
                        "a symbol reaches exactly one of the engine's three "
                        "states, and a page claiming two of them at once cannot "
                        "both be right"
                    )
                placed[symbol] = section

        for name in ("opportunities", "wait_list"):
            rows = getattr(self, name)
            for index, row in enumerate(rows):
                if row.position != index + 1:
                    raise SwingWorkspaceError(
                        f"{name}[{index}] is stamped position {row.position}; a "
                        "stamped position that disagrees with the row's place on "
                        "the page is a ranking nobody can reconstruct"
                    )

    @property
    def is_empty(self) -> bool:
        """Whether the page holds nothing actionable. **Never a market verdict.**"""
        return not self.opportunities and not self.wait_list

    def row(self, symbol: str) -> RankedSetup | None:
        """One ranked row by symbol, from either actionable section."""
        wanted = _text(symbol, "symbol")
        for row in self.opportunities + self.wait_list:
            if row.symbol == wanted:
                return row
        return None

    def decision(self, symbol: str) -> SymbolDecision | None:
        """One symbol's decision record, whatever state it reached.

        A lookup by name over a tuple with at most one entry per symbol — never
        a search that ranks or a nearest match. `None` means the symbol produced
        no assessment on this run (it failed, or was not scanned), which the
        `unanalysed` section states; it never means the symbol has no decision.
        """
        wanted = _text(symbol, "symbol")
        for decision in self.decisions:
            if decision.symbol == wanted:
                return decision
        return None
