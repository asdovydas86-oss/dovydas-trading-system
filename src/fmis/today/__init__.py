"""The Daily Trading Workspace — one command, one page, seven sections.

`fmis.today` is the first place the two halves of FMITS meet. Every layer below
belongs to exactly one of them: the market half computes what price did and
refuses to know anything about the owner's money, and the owner half records
what the owner did and never reads a candle. Neither may import the other. This
package imports both, assembles one page, and adds no engine, no policy and no
computation of its own.

    fmits today

**What it is.** A human-operated swing-trading cockpit: what the market is
doing, what is already held and committed, what is actionable today, what
deserves attention, what has been decided and written down, what has been
durably recorded, and every limitation that qualifies the rest.

**What it is not, and cannot become without a new milestone.** It executes
nothing, connects to no exchange, places no order, sizes no position, sends no
notification and simulates no trade. It writes nothing at all: every record it
shows was written by something else, and every market fact it shows was computed
by an engine that already existed.

**Three properties are structural rather than disciplinary**, so they survive an
inattentive reader:

* **Absence is rendered, never omitted.** Every value the workspace cannot
  produce carries its reason, the slice that owns producing it, and the
  inference its absence forbids. A blank capital section reads as no exposure;
  this one cannot.
* **Nothing is ranked by desirability.** The priority queue orders by the
  engine's own readiness state and then by watchlist order — never by
  risk/reward, and the object itself carries that rule to every consumer.
* **No figure appears without its sample and its caveat.** The two measured
  numbers this package cites live in one module with their `n`, their source and
  what is wrong with the sample they came from, and the renderer has no short
  form that could drop any of the three.
"""

from __future__ import annotations

from fmis.today.attention import ORDERING_RULE, build_queue
from fmis.today.builder import (
    DUST_POLICY,
    TODAY_LIMITATIONS,
    OBJECTIVE,
    StoreReading,
    approvals_for,
    build_today,
    empty_reading,
    read_store,
    run_today,
)
from fmis.today.evidence import (
    MEASURED_FIGURES,
    RISK_REWARD_ASSOCIATION,
    RISK_REWARD_DISTRIBUTION,
    RISK_REWARD_ELEVATED,
    RISK_REWARD_P90,
    MeasuredFigure,
)
from fmis.today.models import (
    TODAY_SCHEMA_VERSION,
    AnalysisLine,
    AnalysisSummary,
    ClosedPositionLine,
    FailedSymbol,
    PaperTradeLine,
    PaperTrading,
    JournalLine,
    JournalSummary,
    LimitLine,
    MarketOverview,
    Opportunities,
    OpportunityLine,
    PortfolioOverview,
    PositionLine,
    PriorityQueue,
    QueueEntry,
    StoreUnreadableError,
    TodayError,
    TodayWorkspace,
    NotAvailable,
    WaitGroup,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
)
from fmis.today.render import render_today
from fmis.today.sections import (
    RECENT_LIMIT,
    REGIME_NOTE,
    analysis_summary,
    journal_summary,
    paper_trading,
    market_overview_from_results,
    opportunities_from_results,
    portfolio_overview,
)
from fmis.today.warnings import (
    CLUSTER_MINIMUM,
    CODES,
    warnings_for_opportunity,
    workspace_warnings,
)

__all__ = [
    # the model
    "TODAY_SCHEMA_VERSION",
    "TodayError",
    "StoreUnreadableError",
    "TodayWorkspace",
    "NotAvailable",
    "MarketOverview",
    "PortfolioOverview",
    "PositionLine",
    "LimitLine",
    "Opportunities",
    "OpportunityLine",
    "WaitGroup",
    "FailedSymbol",
    "PriorityQueue",
    "QueueEntry",
    "JournalSummary",
    "PaperTradeLine",
    "PaperTrading",
    "JournalLine",
    "ClosedPositionLine",
    "AnalysisSummary",
    "AnalysisLine",
    "WorkspaceWarning",
    "WarningClass",
    "WarningSeverity",
    # measured figures
    "MeasuredFigure",
    "MEASURED_FIGURES",
    "RISK_REWARD_P90",
    "RISK_REWARD_ELEVATED",
    "RISK_REWARD_DISTRIBUTION",
    "RISK_REWARD_ASSOCIATION",
    # rules
    "CODES",
    "CLUSTER_MINIMUM",
    "warnings_for_opportunity",
    "workspace_warnings",
    "ORDERING_RULE",
    "build_queue",
    # sections
    "REGIME_NOTE",
    "RECENT_LIMIT",
    "opportunities_from_results",
    "market_overview_from_results",
    "portfolio_overview",
    "journal_summary",
    "paper_trading",
    "analysis_summary",
    # composition and rendering
    "OBJECTIVE",
    "TODAY_LIMITATIONS",
    "DUST_POLICY",
    "StoreReading",
    "read_store",
    "empty_reading",
    "approvals_for",
    "build_today",
    "run_today",
    "render_today",
]
