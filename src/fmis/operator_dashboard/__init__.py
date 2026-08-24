"""The FMITS Operator Dashboard — a window into FMITS, not a second FMITS.

    fmits dashboard

**What it is.** The first visual surface of this system: seven read-only pages
over the engines that already exist, served locally, showing what the market is
doing, what has confirmed, what is held, what the simulator is running, whether
any of it has worked, and which sources could not be read.

**What it must never become.** A place where a market or monetary quantity is
computed. Every figure on every page was produced by an engine below this
package and carried across one seam unchanged. This package holds no indicator,
no market structure, no setup state, no evidence rule, no ranking, no return, no
risk figure, no position size and no statistic — and four architecture guards
assert exactly that, by scanning this package's own source for the vocabulary of
each.

**The four layers, and why the split is worth its cost:**

  * `models` — the presentation contract. Frozen dataclasses, no methods that
    compute. Everything above may be replaced without touching anything below.
  * `sections` — engine output → read model. Translation only.
  * `compose` — the composition root. Four engine reads per refresh, each
    isolated, named in `REFRESH_READS` so the count is a contract.
  * `render` + `theme` + `server` — HTML, appearance, and a standard-library
    socket. Replaceable in their entirety.

**The redesign seam is `theme` plus `render`.** The brief that produced this
surface said the visual design will change. Deleting both modules and writing a
different UI against `models` is the intended path, and it requires touching
nothing in `sections` or `compose`.

**Read-only is enforced, not promised.** The server answers `GET` and `HEAD` and
refuses every other method by name; it binds loopback and refuses to bind
elsewhere without an explicit argument; it serves no file from any path; and a
guard asserts no module in this package names a store write verb, an execution
verb, or opens a path for writing.
"""

from __future__ import annotations

from fmis.operator_dashboard.compose import (
    DASHBOARD_LIMITATIONS,
    REFRESH_READS,
    WORKSPACE_ERRORS,
    build_snapshot,
    refresh,
)
from fmis.operator_dashboard.models import (
    DASHBOARD_SCHEMA_VERSION,
    BenchmarkRow,
    BookRow,
    DashboardError,
    DataHealthView,
    EquityStep,
    EvidenceView,
    LimitRow,
    MacroRow,
    MacroView,
    MoveCell,
    NoTradeRow,
    OperatorDashboardSnapshot,
    OverviewCounts,
    PaperRow,
    PaperView,
    PerformanceView,
    PortfolioView,
    PositionRow,
    PulseView,
    RelationshipRow,
    DashboardSection,
    DashboardSectionStatus,
    SetupRow,
    SourceHealth,
    SourceState,
    SwingView,
    UnreadableRow,
    WarningRow,
)
from fmis.operator_dashboard.render import PAGES, page_titles, render_page
from fmis.operator_dashboard.sections import (
    counts_from,
    health_view,
    macro_view,
    paper_view,
    performance_views,
    portfolio_view,
    pulse_view,
    swing_view,
    warning_rows,
)
from fmis.operator_dashboard.server import (
    ALLOWED_METHODS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DashboardServer,
    SnapshotHolder,
    build_server,
    resolve_route,
    serve,
)
from fmis.operator_dashboard.theme import STYLESHEET

__all__ = [
    # the contract
    "DASHBOARD_SCHEMA_VERSION",
    "DashboardError",
    "DashboardSectionStatus",
    "SourceState",
    "DashboardSection",
    "OperatorDashboardSnapshot",
    "OverviewCounts",
    "SourceHealth",
    "DataHealthView",
    "MoveCell",
    "BenchmarkRow",
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
    # translation
    "counts_from",
    "pulse_view",
    "macro_view",
    "swing_view",
    "portfolio_view",
    "paper_view",
    "performance_views",
    "health_view",
    "warning_rows",
    # composition
    "REFRESH_READS",
    "DASHBOARD_LIMITATIONS",
    "WORKSPACE_ERRORS",
    "build_snapshot",
    "refresh",
    # presentation
    "PAGES",
    "page_titles",
    "render_page",
    "STYLESHEET",
    # the local server
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ALLOWED_METHODS",
    "SnapshotHolder",
    "DashboardServer",
    "build_server",
    "resolve_route",
    "serve",
]
