"""The dashboard's read models — the seam between FMITS and any user interface.

**These types are the whole contract.** Everything above them (HTML, CSS, a
future React app, a future terminal UI) may be replaced without touching
anything below them, and everything below them — every engine in this
repository — may be rearranged without touching the UI, provided these shapes
survive. That is the entire reason the layer exists.

**Nothing here computes.** Not one type in this module holds a method that
adds, divides, compares magnitudes or classifies a market. Every field is a
value an engine already produced, carried forward. When a field looks like a
number it is either a primitive the engine returned (`float`, `int`) or the
engine's own canonical text (`Money.text`, a `str | NotAvailable` the workspace
already folded). Formatting those for display is presentation and happens in
`fmis.operator_dashboard.render`; producing them is an engine's job and happens
nowhere near here.

**Absence is a value, not a gap.** `None` in a payload means *the engine said
this is unavailable and told us why*, and the reason travels beside it. A
section that failed operationally is `DashboardSectionStatus.UNAVAILABLE` carrying its
reason, never an empty section that reads as a calm one. The distinction
between *zero* and *absent* is the one this dashboard exists to preserve: a
portfolio with no risk and a portfolio whose risk could not be measured look
nothing alike here, and must look nothing alike on screen.

**No `STALE`.** `fmis.market_pulse` refuses the word deliberately — *"stale"* is
a judgement about whether a number is still usable, and that depends on what the
reader is doing with it. What can be stated objectively is narrower: whether a
reading is older than its own source's publication schedule explains. So
`SourceState` carries `BEHIND_SCHEDULE`, which is `FreshnessState`'s word, and
this layer invents no threshold of its own.

**No composite health score.** `DataHealthView` is a list of sources with their
states and reasons. Collapsing six sources into one green light would be exactly
the invented judgement every engine below refuses to make, and it would be the
one field on the page most likely to be believed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Generic, Mapping, TypeVar

__all__ = [
    "DASHBOARD_SCHEMA_VERSION",
    "DashboardError",
    "DashboardSectionStatus",
    "SourceState",
    "DashboardSection",
    "SourceHealth",
    "DataHealthView",
    "BenchmarkRow",
    "MoveCell",
    "PulseView",
    "MacroRow",
    "RelationshipRow",
    "MacroView",
    "EvidenceView",
    "SetupRow",
    "FactorRow",
    "EvidenceItemRow",
    "SymbolDecisionRow",
    "TimeframeRow",
    "DevelopingEvidenceRow",
    "BlockerRow",
    "NoTradeRow",
    "UnreadableRow",
    "SwingSnapshot",
    "SwingView",
    "TransitionRow",
    "SymbolChangeRow",
    "ScanChangeView",
    "PositionRow",
    "LimitRow",
    "BookRow",
    "PortfolioView",
    "PaperRow",
    "PaperView",
    "EquityStep",
    "PerformanceView",
    "WarningRow",
    "OverviewCounts",
    "LabVariantRow",
    "LabGateRow",
    "LabView",
    "GeometryCriterionRow",
    "GeometrySampleRow",
    "GeometryPolicyRow",
    "GeometrySensitivityRow",
    "GeometryShareRow",
    "GeometryFindingRow",
    "GeometryView",
    "ValidationCriterionRow",
    "ValidationSampleRow",
    "ValidationCellRow",
    "ValidationPolicyRow",
    "ValidationPlateauPointRow",
    "ValidationPlateauRow",
    "ValidationWindowRow",
    "ValidationCohortRow",
    "ValidationDecompositionRow",
    "ValidationView",
    "OperatorDashboardSnapshot",
]

#: Bumped when a field is removed or its meaning changes. A UI pinned to a
#: version can then refuse to render a snapshot it would misread, rather than
#: silently showing a field that now means something else.
DASHBOARD_SCHEMA_VERSION = 1


class DashboardError(Exception):
    """Something the dashboard layer itself refused.

    Deliberately narrow. A provider outage is not this — it is a section's
    stated unavailability. This is raised when the dashboard is asked for
    something it cannot honestly assemble at all.
    """


class DashboardSectionStatus(Enum):
    """Whether a section's own read succeeded.

    Three states and no fourth, because the fourth anybody reaches for —
    *degraded* — is a judgement about severity that this layer has no basis to
    make. A section either holds what it read, holds nothing because there was
    nothing, or could not read at all and says why.
    """

    #: The read succeeded. The payload may still contain absences; those are the
    #: engines' own, stated on the fields that carry them.
    AVAILABLE = "available"
    #: The read succeeded and there was genuinely nothing to report. An empty
    #: store is not a failure, and an owner who has never traded has not
    #: suffered an outage.
    EMPTY = "empty"
    #: The read failed operationally. ``unavailable_reason`` says why. This is
    #: never used for a programming defect — those propagate.
    UNAVAILABLE = "unavailable"


class SourceState(Enum):
    """What one data source is doing, in the vocabulary the engines already use.

    Every member below is a restatement of a distinction some engine already
    draws, never a new one. `UNSUPPORTED` is `Benchmark.unsupported_reason`;
    `BEHIND_SCHEDULE` is `FreshnessState.BEHIND_SCHEDULE`; `UNAVAILABLE` is a
    `MarketUnavailable` row. Inventing a fifth would mean inventing a judgement.
    """

    #: Read, and no older than its own source's schedule explains.
    AVAILABLE = "available"
    #: Read, but older than its source's publication schedule accounts for.
    #: **Not** an accusation that the number is wrong: a source can be late.
    BEHIND_SCHEDULE = "behind_schedule"
    #: Read, but no publication schedule is established for the series, so no
    #: verdict on its age is offered. The age itself is still stated.
    SCHEDULE_UNKNOWN = "schedule_unknown"
    #: There is no provider for this market in this build. A permanent property
    #: of the system, not a transient outage — DXY and XAU are the live cases.
    UNSUPPORTED = "unsupported"
    #: A supported source that could not be read on this run, with its reason.
    UNAVAILABLE = "unavailable"
    #: A local store that is not present. Distinct from unavailable: nothing
    #: failed, there is simply nothing there yet.
    ABSENT = "absent"


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DashboardSection(Generic[T]):
    """One dashboard section, its payload, and everything qualifying it.

    **Why every section carries `as_of` and `source` separately.** The page has
    one refresh instant but several data instants, and they are not the same
    fact. A macro series published daily and a crypto series published hourly,
    read in the same refresh, describe two different moments; showing one
    timestamp for the page would make the older half look as recent as the
    newer. So the refresh instant lives on the snapshot and the *data* instant
    lives here, per section.
    """

    name: str
    status: DashboardSectionStatus
    #: The instant the section's data describes — not when the page was built.
    #: `None` only when the section holds nothing that has an instant.
    as_of: datetime | None = None
    #: Where the payload came from, in prose: an engine name, a store path, a
    #: provider. Rendered so provenance is readable without opening code.
    source: str = ""
    data: T | None = None
    #: Set exactly when ``status`` is `DashboardSectionStatus.UNAVAILABLE`.
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise DashboardError("a section must be named")
        if not isinstance(self.status, DashboardSectionStatus):
            raise DashboardError("status must be a DashboardSectionStatus")
        if self.status is DashboardSectionStatus.UNAVAILABLE:
            if not self.unavailable_reason:
                raise DashboardError(
                    f"section {self.name!r} is unavailable and must say why; an "
                    "unexplained absence reads as an empty section, which reads "
                    "as a calm one"
                )
            if self.data is not None:
                raise DashboardError(
                    f"section {self.name!r} is unavailable but carries data; a "
                    "half-failed section would render as a whole one"
                )
        elif self.unavailable_reason is not None:
            raise DashboardError(
                f"section {self.name!r} states a reason but is not unavailable"
            )
        if self.as_of is not None:
            if not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None:
                raise DashboardError(
                    f"section {self.name!r} as_of must be timezone-aware; a naive "
                    "instant compared against a UTC one is a silently wrong age"
                )

    @property
    def is_available(self) -> bool:
        return self.status is DashboardSectionStatus.AVAILABLE

    @property
    def failed(self) -> bool:
        return self.status is DashboardSectionStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# Data health
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceHealth:
    """One source, what state it is in, and the evidence for saying so."""

    source_id: str
    label: str
    state: SourceState
    #: Free text from the engine that decided the state. Never composed here.
    detail: str = ""
    #: The instant of the last observation this source produced, if any.
    last_observation: datetime | None = None
    #: The engine's own age for that observation. Carried, not subtracted here.
    age: timedelta | None = None
    provider: str = ""


@dataclass(frozen=True, slots=True)
class DataHealthView:
    """Every source the refresh touched. No score, no colour-coded aggregate."""

    sources: tuple[SourceHealth, ...] = ()

    def with_state(self, state: SourceState) -> tuple[SourceHealth, ...]:
        return tuple(source for source in self.sources if source.state is state)


# ---------------------------------------------------------------------------
# Markets — pulse
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MoveCell:
    """One market's move over one named window.

    ``value`` is the engine's fraction; ``unavailable_reason`` is set exactly
    when it is `None`. ``bars`` is a count of closed bars and not a duration,
    because this build holds no trading calendar and a window here is a number
    of observations rather than an elapsed time.
    """

    horizon_id: str
    label: str
    bars: int
    value: float | None
    unavailable_reason: str | None = None
    metric: str = ""


@dataclass(frozen=True, slots=True)
class BenchmarkRow:
    """One market on the pulse page, or one market that could not be read."""

    benchmark_id: str
    display_name: str
    category: str
    quote_unit: str
    state: SourceState
    moves: tuple[MoveCell, ...] = ()
    volatility: float | None = None
    volatility_reason: str | None = None
    volatility_metric: str = ""
    last_bar_open: datetime | None = None
    age: timedelta | None = None
    source: str = ""
    interval: str = ""
    #: Why this market has no reading. Set for UNSUPPORTED and UNAVAILABLE.
    unavailable_reason: str | None = None
    co_movement: float | None = None
    co_movement_reason: str | None = None
    co_movement_reference: str | None = None


@dataclass(frozen=True, slots=True)
class PulseView:
    """The global pulse, re-sectioned for a screen. Same figures, same order."""

    as_of: datetime
    universe: str
    rows: tuple[BenchmarkRow, ...] = ()
    horizons: tuple[tuple[str, str], ...] = ()
    read_count: int = 0
    requested_count: int = 0
    unsupported_count: int = 0
    co_movement_reference: str | None = None


# ---------------------------------------------------------------------------
# Markets — macro
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MacroRow:
    """One macro market: its level with its unit, its moves, its provenance.

    **Yields are carried as basis points, prices as fractions, and the two are
    never mixed.** `fmis.macro` decides which a market is via its
    `QuantityKind`; ``change_unit`` carries that decision forward so the page
    cannot label a rate move as a percentage return.
    """

    benchmark_id: str
    display_name: str
    state: SourceState
    level: float | None = None
    unit: str = ""
    quantity_kind: str = ""
    observed_at: datetime | None = None
    source: str = ""
    age: timedelta | None = None
    moves: tuple[MoveCell, ...] = ()
    change_unit: str = ""
    volatility: float | None = None
    volatility_reason: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RelationshipRow:
    """One cross-asset relationship, with the alignment it required.

    ``aligned_count`` and ``observation_count`` are both carried because a
    correlation over four aligned points out of ninety is a different claim from
    one over ninety, and a page that showed only the number would hide that.
    """

    subject_id: str
    reference_id: str
    metric: str
    value: float | None
    unavailable_reason: str | None = None
    observation_count: int = 0
    aligned_count: int = 0
    comparability: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MacroView:
    as_of: datetime
    rows: tuple[MacroRow, ...] = ()
    relationships: tuple[RelationshipRow, ...] = ()
    relationship_reference: str | None = None
    horizons: tuple[tuple[str, str], ...] = ()


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """One setup's evidence digest, exactly as `fmis.setup_evidence` folded it."""

    supporting: int
    conflicting: int
    missing: int
    unavailable: int
    agreeing_families: tuple[str, ...] = ()
    conflicting_families: tuple[str, ...] = ()
    independence_established: bool = False
    decision_ready: bool = False
    decision_ready_reason: str = ""
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SetupRow:
    """One actionable setup, in the order `fmis.swing_workspace` placed it.

    **`position` is an index, not a rank.** It is where the row sits in the
    workspace's own ordering, carried so a UI can display the sequence without
    re-deriving it. This layer sorts nothing; reordering these rows anywhere
    above this model would be inventing a ranking the engines refused to make.

    **`held` and `paper_status` are separate fields on purpose.** A symbol the
    owner holds and a symbol the simulator is running are two different facts,
    and one field carrying either would let the page imply real exposure where
    there is only a paper trade.
    """

    symbol: str
    state: str
    sufficiency: str
    position: int
    direction: str | None = None
    approval_status: str | None = None
    risk_reward: float | None = None
    stop: float | None = None
    target: float | None = None
    recommended_size: str | None = None
    open_risk_after: str | None = None
    thesis: tuple[str, ...] = ()
    confirmation: tuple[str, ...] = ()
    invalidation: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    approval_warnings: tuple[str, ...] = ()
    evidence: EvidenceView | None = None
    evidence_reason: str | None = None
    identity: str | None = None
    identity_reason: str | None = None
    paper_status: str | None = None
    held: str | None = None
    #: The workspace's ordering key, component by component, so the reason one
    #: row sits above another is readable on the row itself.
    rank_components: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FactorRow:
    """One directional family, its lean, and what produced it. Carried, not judged."""

    family: str
    lean: str
    observed: str
    source: str


@dataclass(frozen=True, slots=True)
class EvidenceItemRow:
    """One evidence item as the projection produced it — not a count of items.

    `EvidenceView` answers *how many*; this answers *which*, which is the half
    that tells two `WAIT` symbols apart. ``correlated_with`` and
    ``independence_note`` travel with the item so a renderer can mark it as a
    non-independent reading; dropping them here would let the page display one
    fact seen three ways as three-fold confirmation.
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


@dataclass(frozen=True, slots=True)
class TimeframeRow:
    """One timeframe role: when it was read, how old that is, how many bars.

    **No freshness verdict, and no field to hold one.** See
    `fmis.swing_workspace.TimeframeLine`, whose omission this inherits: no
    validated staleness bound exists for any role in this repository, and a cell
    painted green would be an invented policy wearing a fact's clothes.
    """

    role: str
    interval: str
    as_of: datetime
    closed_count: int
    age: timedelta | None = None
    #: This role's structural trend, as the engine reported it.
    structural_trend: str | None = None


@dataclass(frozen=True, slots=True)
class DevelopingEvidenceRow:
    """Which way the readable families point. **Never what the policy decided.**

    ``state`` is `DevelopingEvidenceState`'s own value and ``lean`` is
    `Direction`'s, both read at runtime — this package names neither side, on
    the ADR-0028 boundary every other module here observes.

    `SymbolDecisionRow` holds this **beside** the policy's own ``state``, and a
    guard asserts no renderer shows one without the other. *"Evidence leaning"*
    with the word `WAIT` removed is a signal the policy refused to give.
    """

    state: str
    lean: str | None = None
    agreeing: tuple[str, ...] = ()
    opposing: tuple[str, ...] = ()
    non_voting: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BlockerRow:
    """The named condition holding this reading, and what the gate demands.

    ``requirement`` restates a condition the policy already states. It is never
    a price, a date or a prediction — see
    `fmis.swing_setup.decision_summary.Blocker`, which builds it.
    """

    kind: str
    statement: str
    requirement: str
    observed: str
    source: str


@dataclass(frozen=True, slots=True)
class TradeRiskPlanRow:
    """One symbol's trade-planning figures, or exactly why there are none.

    Carries `fmis.risk_policy.TradeRiskPlan` field for field, with every amount
    already rendered as the text the domain itself produced. **This layer
    computes nothing**: `money_at_risk` is `Money.text` plus its asset, not a
    multiplication, and a guard asserts the renderer holds no arithmetic.

    **Every figure is `None` unless it was produced, and `None` prints its
    reason rather than a blank.** A blank where a size belongs reads as a size
    of nothing, and `AP` §14.3 is the whole discipline: *"a zero makes the total
    look plausible and survives for years."*

    ``portfolio_impact_reason`` is always populated and there is deliberately no
    ``portfolio_impact`` beside it. No portfolio is read for these figures, so
    total open risk, concentration and correlation are **not evaluated** — which
    is a different fact from their being zero, and a page silent about portfolio
    risk reads as a page reporting none.

    ``status`` is `PlanningStatus`'s own value. `no_trade_plan` — the state of
    most of the watchlist — carries no figures at all: not a zero size, not an
    empty one. A waiting symbol with a quantity beside it reads as almost a
    trade, and that is the single rendering this row exists to prevent.
    """

    symbol: str
    status: str
    #: What the owner has not declared, one entry per input. Never a default.
    missing: tuple[str, ...] = ()
    #: The engine's own sentence for why there is no number, verbatim.
    reason: str = ""
    direction: str | None = None
    direction_reason: str = ""
    entry: str | None = None
    entry_caveat: str = ""
    invalidation: str | None = None
    risk_per_unit: str | None = None
    risk_per_unit_reason: str = ""
    equity: str | None = None
    equity_reason: str = ""
    declared_at: str | None = None
    #: The risk-policy contract these figures were computed under, so a reader —
    #: or a future archived decision — can ask *which policy produced this*.
    contract_version: int = 0
    risk_fraction: str | None = None
    risk_fraction_reason: str = ""
    money_at_risk: str | None = None
    money_at_risk_reason: str = ""
    quantity: str | None = None
    quantity_reason: str = ""
    notional: str | None = None
    notional_reason: str = ""
    reward_risk: str | None = None
    reward_risk_reason: str = ""
    #: The specification's hard maximum, printed whatever the owner declared.
    ceiling: str = ""
    ceiling_source: str = ""
    #: Why `risk_fraction` is the number it is. A fraction with no stated
    #: provenance is a number something chose on the owner's behalf.
    basis: str = ""
    #: The ceilings that actually reduced the size, in the order applied.
    caps: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    portfolio_impact_reason: str = ""
    #: What these figures are not — `fmis.risk_policy.PLANNING_LIMITATIONS`,
    #: carried as `(title, detail)` pairs. On the row rather than reached for by
    #: the renderer, which imports no domain package: a limitation belongs beside
    #: the number, and the layer that owns the number owns the caveat.
    limitations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SymbolDecisionRow:
    """One scanned symbol's decision, whatever state it reached.

    Carries `fmis.swing_workspace.SymbolDecision` field for field. Its reason for
    existing is the population `SetupRow` does not cover: a `WAIT` symbol has no
    `SetupRow`, so before this row a request for ``/swing/BTCUSDT`` on a waiting
    BTC could only answer *"not an actionable or waiting setup on this
    refresh"* — while the engine had in fact produced a full assessment, three
    directional factors, a regime reading and a complete evidence report for it.

    **No score, no rank, no position.** Deliberately absent, and a guard test
    asserts no field name here matches a ranking vocabulary. Rows are held in
    scan order and this layer sorts nothing.
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
    factors: tuple[FactorRow, ...] = ()
    supporting: tuple[EvidenceItemRow, ...] = ()
    conflicting: tuple[EvidenceItemRow, ...] = ()
    missing: tuple[EvidenceItemRow, ...] = ()
    unavailable: tuple[EvidenceItemRow, ...] = ()
    agreeing_families: tuple[str, ...] = ()
    conflicting_families: tuple[str, ...] = ()
    independence_established: bool = False
    independence_caveats: tuple[str, ...] = ()
    evidence_warnings: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    decision_ready: bool = False
    decision_ready_reason: str = ""
    evidence_reason: str | None = None
    #: The operator decision layer. `None` on a row assembled without it — a
    #: page missing the summary, never a page that invents one.
    developing: DevelopingEvidenceRow | None = None
    blocker: BlockerRow | None = None
    #: One row per timeframe role that was read, in role order: context, then
    #: setup, then execution. Empty when the result carried no readings.
    timeframes: tuple[TimeframeRow, ...] = ()
    #: This symbol's trade-planning figures. `None` on a page built with no
    #: declared risk policy — a page with no planning section, never a page that
    #: invents one, and never a page that shows a zero where a size belongs.
    plan: TradeRiskPlanRow | None = None


@dataclass(frozen=True, slots=True)
class NoTradeRow:
    """A conclusion, not a failure. Rendered as a legitimate outcome."""

    reason: str
    classification: str
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnreadableRow:
    """A symbol whose analysis could not be produced, and the reason given."""

    symbol: str
    detail: str


@dataclass(frozen=True, slots=True)
class SwingSnapshot:
    """**A tally of the scan, and nothing else.** Descriptive, never predictive.

    Every number is a count of symbols that reached a *named deterministic
    condition* the engine itself produced — the three `SetupState` members and
    the blocker kinds `fmis.swing_setup.decision_summary` names. No category was
    invented for this page, and there is none that could not be derived from the
    decisions the workspace already carries.

    **Deliberately absent: any market verdict.** No bullish count, no bearish
    count, no breadth figure, no risk-on reading, no *"conditions are
    improving"*. This repository measures no breadth and has validated no
    directional edge, so a summary that leaned would be leaning on nothing.
    ``blockers`` is a distribution over already-stated conditions, ordered by
    the fixed order the engine's own enum declares — **not** by size, so the
    first row is never the most important one.
    """

    scanned: int = 0
    confirmed: int = 0
    candidates: int = 0
    waiting: int = 0
    unreadable: int = 0
    #: `(blocker kind, count)`, in the enum's own declaration order.
    blockers: tuple[tuple[str, int], ...] = ()
    #: `(developing-evidence state, count)`, likewise in enum order.
    developing: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class SwingView:
    """The swing workspace, split into the groups a screen shows separately."""

    reference_time: datetime
    opportunities: tuple[SetupRow, ...] = ()
    wait_list: tuple[SetupRow, ...] = ()
    no_trade: tuple[NoTradeRow, ...] = ()
    unreadable: tuple[UnreadableRow, ...] = ()
    ranking_rule: str = ""
    scanned: int = 0
    regime_note: str = ""
    breadth: tuple[tuple[str, int], ...] = ()
    #: One row per scanned symbol that produced an assessment, in scan order.
    #: Spans the three decision sections rather than partitioning them.
    decisions: tuple[SymbolDecisionRow, ...] = ()
    #: The scan's own tallies. Defaulted so a view built without it renders the
    #: page without the snapshot rather than failing to render at all.
    snapshot: SwingSnapshot = field(default_factory=lambda: SwingSnapshot())
    #: Whether trade-planning figures were produced for this page and, when they
    #: were not, which input is missing. **Defaulted to the honest
    #: pre-declaration answer**, so a view built without one states an absence
    #: rather than rendering a silent page — the failure this field exists to
    #: prevent is the one the audit found: the workspace already produced this
    #: note and the dashboard dropped it, so the surface said nothing at all
    #: about why no size was ever shown.
    risk_note: str = (
        "No risk policy is declared, so no trade-planning figure was produced "
        "for any symbol. Nothing is assumed in its place — not a capital "
        "figure, and above all not a risk fraction. Do not read a symbol with "
        "no planning figures as one that carries no risk."
    )
    #: The default above is the pre-declaration answer and is deliberately the
    #: *default* rather than something a caller must remember to pass: a view
    #: built without this field states the absence instead of rendering a page
    #: that is silent about why no size appears.

    def row_for(self, symbol: str) -> SetupRow | None:
        """The actionable or waiting row for one symbol, if there is one.

        Lookup, not search-and-rank: the first match in the workspace's own
        order. A symbol appears in at most one of the two groups.
        """
        for row in self.opportunities + self.wait_list:
            if row.symbol == symbol:
                return row
        return None

    def decision_for(self, symbol: str) -> SymbolDecisionRow | None:
        """One symbol's decision row, whatever state it reached.

        A lookup by name, never a nearest match. `None` means the symbol
        produced no assessment on this refresh — which the *could not be read*
        section states — and never that the symbol has no decision.
        """
        for row in self.decisions:
            if row.symbol == symbol:
                return row
        return None


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# What changed since the previous comparable scan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransitionRow:
    """One dimension that differs, and the two values it differs between.

    ``dimension`` is `fmis.scan_memory.ChangeDimension`'s own value; the
    operator's wording for it lives beside the other label tables in the
    renderer, so a second UI supplies its own. ``previous`` and ``current`` are
    the engines' own values, carried at runtime — this package names no side and
    invents no vocabulary, on the ADR-0028 boundary every module here observes.

    **No severity, no weight, no arrow beyond the two ends.** There is no field
    here that could say whether the change was good, and none that could rank it
    against another symbol's.
    """

    dimension: str
    previous: str
    current: str


@dataclass(frozen=True, slots=True)
class SymbolChangeRow:
    """One symbol's differences, **with its current state named first.**

    ``state`` is what the symbol is *now*. Everything else on this row qualifies
    that; nothing replaces it, and a guard asserts no renderer shows a transition
    without the current state beside it. A page that showed only *BTCUSDT
    changed* would have told the operator nothing he could act on.
    """

    symbol: str
    state: str
    previous_state: str
    transitions: tuple[TransitionRow, ...] = ()


@dataclass(frozen=True, slots=True)
class ScanChangeView:
    """This scan beside the previous comparable completed one — or why there is none.

    **Four statuses, and *unchanged* is only ever one of them.** ``compared`` is
    the only one under which ``changed`` and ``unchanged`` mean anything; the
    other three carry a ``reason`` and no per-symbol result at all, because
    *"nothing changed"* and *"there was nothing to compare against"* are
    different facts and an operator acts differently on them.

    ``recorded`` is `False` when this scan's analysis succeeded and remembering
    it did not. The page still shows the analysis and says plainly that the scan
    was not recorded; it never claims change tracking succeeded.

    **No score, no rank, no ordering of its own.** ``changed`` arrives in the
    scan's own universe order and this layer does not sort it.
    """

    status: str
    current_scan_at: datetime
    previous_scan_at: datetime | None = None
    reason: str = ""
    changed: tuple[SymbolChangeRow, ...] = ()
    unchanged: tuple[str, ...] = ()
    recorded: bool = True
    recording_note: str = ""

    @property
    def compared(self) -> bool:
        return self.status == "compared"

    def change_for(self, symbol: str) -> SymbolChangeRow | None:
        """One symbol's differences, by name. **A lookup, never a nearest match.**

        `None` means *this symbol did not change* only when `compared` is true.
        Under every other status it means there was no comparison at all, and
        the surfaces say which.
        """
        for row in self.changed:
            if row.symbol == symbol:
                return row
        return None


@dataclass(frozen=True, slots=True)
class PositionRow:
    market: str
    book: str
    direction: str
    quantity: str
    average_entry: str
    opened_at: datetime
    trade_count: int = 0
    mark: str | None = None
    market_value: str | None = None
    unrealized_pnl: str | None = None


@dataclass(frozen=True, slots=True)
class LimitRow:
    limit_id: str
    scope: str
    stated_limit: str
    severity: str
    current: str | None = None
    current_reason: str | None = None
    status: str | None = None
    status_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BookRow:
    label: str
    open_positions: int
    market_value: str | None = None
    market_value_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PortfolioView:
    """The recorded book. **Paper never appears here** — it has its own view.

    Aggregating a simulated position into a real exposure figure is the single
    most dangerous thing this dashboard could do, so the two are separate types
    assembled from separate fields of the workspace, and no field on this type
    can hold a paper number.
    """

    store_root: str
    store_present: bool
    positions: tuple[PositionRow, ...] = ()
    limits: tuple[LimitRow, ...] = ()
    books: tuple[BookRow, ...] = ()
    cash: str | None = None
    cash_reason: str | None = None
    exposure: str | None = None
    exposure_reason: str | None = None
    market_value: str | None = None
    market_value_reason: str | None = None
    unrealized_pnl: str | None = None
    unrealized_pnl_reason: str | None = None
    committed_risk: str | None = None
    committed_risk_reason: str | None = None
    available_risk: str | None = None
    available_risk_reason: str | None = None
    budget_note: str | None = None
    marks_note: str | None = None
    snapshot_as_of: datetime | None = None


# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PaperRow:
    """One simulated trade. Every metric is the lifecycle engine's own."""

    activation_id: str
    market: str
    state: str
    open_size: str
    bars_in_trade: int = 0
    stop_widenings: int = 0
    entry: str | None = None
    entry_reason: str | None = None
    stop: str = ""
    initial_stop: str = ""
    initial_risk: str | None = None
    initial_risk_reason: str | None = None
    total_r: str | None = None
    total_r_reason: str | None = None
    max_favourable_r: str | None = None
    max_favourable_r_reason: str | None = None
    max_adverse_r: str | None = None
    max_adverse_r_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PaperView:
    rows: tuple[PaperRow, ...] = ()
    note: str | None = None


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EquityStep:
    """One closed trade's step on the curve.

    **Nothing sits between two steps.** `fmis.statistics` interpolates nothing,
    and a chart that draws a straight line between these points is drawing
    pixels, not claiming observations. That distinction is stated on the page.
    """

    at: datetime
    trade_ref: str
    delta: str
    cumulative: str
    equity: str | None = None


@dataclass(frozen=True, slots=True)
class PerformanceView:
    """Statistics for one quote asset. Figures are never summed across assets.

    Each rate carries its own absence reason, because the sample floor refuses
    rates below a stated number of observations and a blank cell would read as
    a zero win rate rather than as a refusal to state one.
    """

    quote_asset: str
    trades: int = 0
    open_trades: int = 0
    resolved: int = 0
    sample_floor: int = 0
    floor_note: str = ""
    net: str | None = None
    net_reason: str | None = None
    expectancy: str | None = None
    expectancy_reason: str | None = None
    win_rate: str | None = None
    win_rate_reason: str | None = None
    profit_factor: str | None = None
    profit_factor_reason: str | None = None
    average_r: str | None = None
    average_r_reason: str | None = None
    max_drawdown: str | None = None
    max_drawdown_reason: str | None = None
    equity: tuple[EquityStep, ...] = ()
    equity_basis: str = ""
    equity_excluded: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# The snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WarningRow:
    code: str
    kind: str
    severity: str
    statement: str
    evidence: str = ""
    subjects: tuple[str, ...] = ()
    detail: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OverviewCounts:
    """The counts the first page shows. Every one is an engine's own tally."""

    scanned: int = 0
    confirmed: int = 0
    candidates: int = 0
    waiting: int = 0
    unreadable: int = 0
    open_positions: int = 0
    paper_positions: int = 0


@dataclass(frozen=True, slots=True)
class LabVariantRow:
    """One policy variant's measured result, as text this layer never computes.

    Every figure arrives already reduced by `fmis.swing_lab.metrics` and is
    carried across as canonical text beside its own sample count. `*_reason`
    holds why a figure is absent — a thin cohort and an empty one look identical
    in a blank cell, and this page must not let them.
    """

    variant_id: str
    title: str
    hypothesis: str
    policy_id: str
    is_baseline: bool
    trades: int = 0
    measurable: int = 0
    ambiguous: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: str | None = None
    win_rate_reason: str | None = None
    expectancy: str | None = None
    expectancy_reason: str | None = None
    median_r: str | None = None
    median_r_reason: str | None = None
    profit_factor: str | None = None
    profit_factor_reason: str | None = None
    total_r: str = ""
    max_drawdown: str = ""
    sample_note: str = ""
    #: The verdict `fmis.swing_lab.metrics.classify` derived from this result,
    #: carried as its own value and its own sentence. This layer never decides
    #: it — a page that computed a verdict would be a second research engine.
    verdict: str = ""
    verdict_statement: str = ""


@dataclass(frozen=True, slots=True)
class LabGateRow:
    """What the context-role gate did, with the two block counts kept apart.

    The raw block count and the count that actually removed a setup are
    different facts, and a page showing only the first would suggest the gate
    discarded thousands of trades it never had.
    """

    instants: int = 0
    not_reached: int = 0
    allowed: int = 0
    blocked_without_effect: int = 0
    blocked_candidate: int = 0
    blocked_confirmed: int = 0
    blocked_long: int = 0
    blocked_short: int = 0
    counterfactual_note: str = ""


@dataclass(frozen=True, slots=True)
class LabView:
    """One completed experiment, read from an artifact the caller supplied.

    **Not a live engine read.** A lab study replays years of history and takes
    minutes; this page therefore shows a *record* of one, and says so. When no
    artifact was supplied the page states that plainly rather than rendering an
    empty table that reads as "no edge found".
    """

    experiment_id: str = ""
    symbols: tuple[str, ...] = ()
    measurement_start: str = ""
    measurement_end: str = ""
    interval_groups: tuple[str, ...] = ()
    cost_policy: str = ""
    result_digest: str = ""
    digest_verified: bool = False
    variants: tuple[LabVariantRow, ...] = ()
    gate: LabGateRow | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GeometryCriterionRow:
    """One requirement a geometry had to meet, and the measurement that decided it.

    ``passed`` is tri-state for the reason `fmis.swing_lab.geometry_verdict`
    makes it so: a criterion that could not be evaluated is not a failure, and a
    page that rendered both as a red mark would report a policy nobody measured
    as one that lost money.
    """

    name: str
    requirement: str
    passed: bool | None
    observed: str


@dataclass(frozen=True, slots=True)
class GeometrySampleRow:
    """One geometry's result on one sample. Text, already reduced upstream.

    ``refused`` sits beside ``trades`` deliberately. A rule that traded six times
    because it refused ninety candidates and a rule that traded six times because
    six setups formed are different findings, and a trade count alone cannot tell
    them apart.
    """

    sample: str
    trades: int = 0
    measurable: int = 0
    refused: int = 0
    win_rate: str | None = None
    win_rate_reason: str | None = None
    expectancy: str | None = None
    expectancy_reason: str | None = None
    median_r: str | None = None
    median_r_reason: str | None = None
    profit_factor: str | None = None
    profit_factor_reason: str | None = None
    total_r: str = ""
    max_drawdown: str = ""
    median_planned_rr: str | None = None
    largest_symbol_share: str | None = None


@dataclass(frozen=True, slots=True)
class GeometryFindingRow:
    """One diagnostic question, its evidence and its reading, kept apart.

    Evidence and interpretation are separate fields because the milestone brief
    asks them to be: a reader may disagree with the reading without having to
    doubt the count it was read from.
    """

    question: str
    supported: bool | None
    evidence: str
    reading: str


@dataclass(frozen=True, slots=True)
class GeometryShareRow:
    """A count out of a total, and the rate — if the engine allowed one.

    The three values are carried separately and are **never** combined here.
    `fmis.swing_lab.geometry_diagnosis.Share` already decided whether a rate may
    be stated for this denominator; computing one on this page would let the
    dashboard state a rate the engine refused.
    """

    label: str
    numerator: int
    denominator: int
    fraction: str | None
    #: The engine's own canonical rendering, e.g. ``45/85 (52.9%)``. Carried so
    #: no surface has to round a `Decimal` itself.
    text: str = ""


@dataclass(frozen=True, slots=True)
class GeometryPolicyRow:
    """One pre-declared geometry: what it is, what it measured, what blocked it."""

    policy_id: str
    title: str
    family: str
    hypothesis: str
    stop_rule: str
    target_rule: str
    is_production_geometry: bool
    verdict: str
    verdict_statement: str
    development: GeometrySampleRow
    holdout: GeometrySampleRow
    criteria: tuple[GeometryCriterionRow, ...] = ()
    #: The names of every criterion this policy did not meet, in declaration
    #: order. A **field** rather than a property: selecting rows is the kind of
    #: work this layer exists not to do, and `fmis.swing_lab.geometry_verdict`
    #: already decided which criteria blocked.
    blocking_criteria: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GeometrySensitivityRow:
    """One threshold on one sensitivity grid, both samples side by side."""

    kind: str
    threshold: str
    development_trades: int
    development_expectancy: str | None
    holdout_trades: int
    holdout_expectancy: str | None


@dataclass(frozen=True, slots=True)
class GeometryView:
    """One completed geometry experiment, read from an artifact the caller supplied.

    **Not a live engine read**, for the reason `LabView` states: a geometry study
    replays years of history and takes tens of minutes. With no artifact loaded
    the page says so plainly rather than rendering an empty table, which on this
    page would read as *"no geometry works"* rather than *"nothing was measured"*.
    """

    experiment_id: str = ""
    development_symbols: tuple[str, ...] = ()
    holdout_symbols: tuple[str, ...] = ()
    measurement_start: str = ""
    measurement_end: str = ""
    admission: str = ""
    candidate_count: int = 0
    cost_policy: str = ""
    result_digest: str = ""
    digest_verified: bool = False
    policies: tuple[GeometryPolicyRow, ...] = ()
    sensitivity: tuple[GeometrySensitivityRow, ...] = ()
    plateau_notes: tuple[str, ...] = ()
    baseline_findings: tuple[GeometryFindingRow, ...] = ()
    baseline_shares: tuple[GeometryShareRow, ...] = ()
    limitations: tuple[str, ...] = ()
    #: Every policy the STUDY judged worth forward testing. Usually empty, and
    #: that is a result rather than a missing measurement. A field, not a
    #: filter — see `GeometryPolicyRow.blocking_criteria`.
    candidate_policy_ids: tuple[str, ...] = ()
    #: Always ``False``, carried as data so the contract itself states it. No
    #: page in this repository approves trading, and there is no code path here
    #: that could set it to anything else.
    is_approved_for_trading: bool = False


# --------------------------------------------------------------- validation ---
#
# Milestone BY. The page shows a SEALED pre-registration and what it measured,
# and the read models below exist so it can show two things BX's page could not:
# **which pre-registration a number was judged under**, and **which cost
# scenario decided it**. Both travel as data rather than as page copy, because a
# figure whose basis is written in prose beside it is a figure that can be
# quoted without its basis.


@dataclass(frozen=True, slots=True)
class ValidationCriterionRow:
    """One sealed requirement, and the measurement that decided it.

    ``passed`` is tri-state for `fmis.swing_lab.validation`'s reason: a criterion
    that could not be evaluated is not a failure, and a page rendering both as a
    red mark would report a policy nobody measured as one that lost money.
    """

    name: str
    requirement: str
    passed: bool | None
    observed: str


@dataclass(frozen=True, slots=True)
class ValidationSampleRow:
    """One sample's identity and its contamination, carried together.

    The contamination sentence is a **required field on the sample**, not page
    copy beside a table. Milestone BX had to spend a report paragraph explaining
    that its holdout was a low-liquidity symbol split; here the caveat cannot be
    separated from the row it qualifies.
    """

    name: str
    role: str
    symbols: tuple[str, ...]
    signal_start: str
    signal_end: str
    contamination: str
    candidates: int = 0


@dataclass(frozen=True, slots=True)
class ValidationCellRow:
    """One policy on one sample under one cost scenario. Text, reduced upstream."""

    sample: str
    cost_policy_id: str
    is_deciding: bool
    trades: int = 0
    measurable: int = 0
    ambiguous: int = 0
    refused: int = 0
    win_rate: str | None = None
    expectancy: str | None = None
    expectancy_reason: str | None = None
    profit_factor: str | None = None
    total_r: str = ""
    max_drawdown: str = ""
    largest_symbol_share: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationPlateauPointRow:
    """One neighbourhood point. **Failing neighbours are rows like any other.**"""

    axis: str
    threshold: str
    is_primary: bool
    measurable: int
    expectancy: str | None


@dataclass(frozen=True, slots=True)
class ValidationPlateauRow:
    """A policy's neighbourhood, its classification and the rule that produced it."""

    classification: str
    statement: str
    detail: str
    points: tuple[ValidationPlateauPointRow, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationPolicyRow:
    """One sealed hypothesis: what it claims, what it measured, what blocked it."""

    hypothesis_id: str
    policy_id: str
    role: str
    family: str
    title: str
    hypothesis: str
    prediction: str
    refuted_by: str
    is_structural: bool
    verdict: str
    verdict_statement: str
    cells: tuple[ValidationCellRow, ...] = ()
    criteria: tuple[ValidationCriterionRow, ...] = ()
    #: A **field**, not a filter. Selecting rows is the work this layer exists
    #: not to do, and `fmis.swing_lab.validation` already decided which blocked.
    blocking_criteria: tuple[str, ...] = ()
    plateau: ValidationPlateauRow | None = None


@dataclass(frozen=True, slots=True)
class ValidationWindowRow:
    """One chronological window of the frozen policy. Empty windows are rows too."""

    label: str
    trades: int
    measurable: int
    win_rate: str | None
    expectancy: str | None
    profit_factor: str | None
    total_r: str
    max_drawdown: str


@dataclass(frozen=True, slots=True)
class ValidationCohortRow:
    """One cohort of one decomposition, with its absence reason when it has one."""

    label: str
    measurable: int
    expectancy: str | None
    expectancy_reason: str | None
    total_r: str


@dataclass(frozen=True, slots=True)
class ValidationDecompositionRow:
    """One way of cutting the primary policy's trades, and what it showed."""

    name: str
    question: str
    agrees_on_sign: bool | None
    cohorts: tuple[ValidationCohortRow, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationView:
    """One completed pre-registered validation, read from a supplied artifact.

    **Not a live engine read**, for `LabView`'s reason: the study replays years
    of history across two universes and takes over an hour. With no artifact
    loaded the page says so plainly rather than rendering an empty table, which
    here would read as *"nothing works"* rather than *"nothing was measured"*.
    """

    experiment_id: str = ""
    preregistration_id: str = ""
    preregistration_digest: str = ""
    #: Whether the sealed rules in the repository still match the ones these
    #: numbers were judged against. Carried as data because a mismatch does not
    #: make the numbers wrong — it makes the CRITERIA different — and only the
    #: page can say that in words a reader will act on.
    seal_matches: bool = False
    deciding_cost_policy_id: str = ""
    cost_policy_ids: tuple[str, ...] = ()
    holdout_opened: bool = False
    no_lookahead_proven: bool = False
    result_digest: str = ""
    digest_verified: bool = False
    samples: tuple[ValidationSampleRow, ...] = ()
    unclaimed_candidates: int = 0
    policies: tuple[ValidationPolicyRow, ...] = ()
    walk_forward_policy_id: str = ""
    walk_forward: tuple[ValidationWindowRow, ...] = ()
    decompositions: tuple[ValidationDecompositionRow, ...] = ()
    limitations: tuple[str, ...] = ()
    #: Every policy the STUDY judged worth forward testing. Usually empty, and
    #: that is a result rather than a missing measurement.
    candidate_policy_ids: tuple[str, ...] = ()
    #: Always ``False``, carried as data so the contract itself states it.
    is_approved_for_trading: bool = False


@dataclass(frozen=True, slots=True)
class OperatorDashboardSnapshot:
    """Everything one refresh produced. The root of the presentation contract.

    **Deterministic for identical injected inputs.** The only clock reading is
    ``refreshed_at``, supplied by the caller rather than taken here, so two
    composes over the same engine outputs and the same instant are equal.

    **No write method exists on this type or anything it holds.** Every field is
    a frozen dataclass or a tuple of them. There is nothing here to call that
    could reach a store.
    """

    refreshed_at: datetime
    reference_time: datetime
    counts: OverviewCounts
    pulse: DashboardSection[PulseView]
    macro: DashboardSection[MacroView]
    swing: DashboardSection[SwingView]
    portfolio: DashboardSection[PortfolioView]
    paper: DashboardSection[PaperView]
    performance: DashboardSection[tuple[PerformanceView, ...]]
    health: DashboardSection[DataHealthView]
    lab: DashboardSection[LabView] | None = None
    geometry: DashboardSection[GeometryView] | None = None
    validation: DashboardSection[ValidationView] | None = None
    warnings: tuple[WarningRow, ...] = ()
    #: What changed since the previous comparable completed scan. `None` on a
    #: snapshot composed without scan memory — a page missing the temporal
    #: section, never a page that invents one. Supplied already computed by the
    #: layer that owns the history store, because **this package writes nothing**
    #: and a guard asserts it.
    scan_change: ScanChangeView | None = None
    limitations: tuple[tuple[str, str], ...] = ()
    schema_version: int = DASHBOARD_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("refreshed_at", "reference_time"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise DashboardError(
                    f"{name} must be a timezone-aware datetime; the page states "
                    "an age, and a naive instant makes that age silently wrong"
                )

    @property
    def sections(self) -> tuple[DashboardSection[Any], ...]:
        """Every section, in the order the navigation shows them."""
        return (
            self.pulse,
            self.macro,
            self.swing,
            self.portfolio,
            self.paper,
            self.performance,
            self.health,
        )

    @property
    def failed_sections(self) -> tuple[DashboardSection[Any], ...]:
        return tuple(section for section in self.sections if section.failed)
