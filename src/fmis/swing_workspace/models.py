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
from datetime import datetime
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
