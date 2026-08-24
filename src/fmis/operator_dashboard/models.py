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
    "NoTradeRow",
    "UnreadableRow",
    "SwingView",
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

    def row_for(self, symbol: str) -> SetupRow | None:
        """The actionable or waiting row for one symbol, if there is one.

        Lookup, not search-and-rank: the first match in the workspace's own
        order. A symbol appears in at most one of the two groups.
        """
        for row in self.opportunities + self.wait_list:
            if row.symbol == symbol:
                return row
        return None


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


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
    warnings: tuple[WarningRow, ...] = ()
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
