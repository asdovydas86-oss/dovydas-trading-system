"""The dashboard's composition root. **One refresh, four reads, and no more.**

**Why four and not fourteen.** The failure mode this module exists to prevent is
the one every widget-oriented dashboard falls into: a pulse card fetching the
market, a macro card fetching it again, a swing table re-scanning, a portfolio
panel re-reading the store. Four widgets, four copies of the world, four
different instants on one page — and the page would show them all under one
heading as though they described one moment.

So the reads are enumerated here, once, and every section is a projection of
one of them:

    run_swing_workspace()  →  swing · portfolio · paper · warnings · counts
    run_market_pulse()     →  pulse
    run_macro_context()    →  macro
    report_for_store()     →  performance

`REFRESH_READS` names them and `test_operator_dashboard_compose` asserts the
count, so adding a fifth is a decision somebody makes on purpose rather than one
that happens because a section needed a number and fetching was easy.

**Three sections share one read, and that is stated rather than hidden.** Swing,
portfolio and paper all come from the single workspace call — `fmits workspace`
already assembles them from one scan, one store read, one valuation and one
approval pass. When that call fails, all three sections fail together and each
carries the same reason. Pretending otherwise would mean either a second store
read (two instants, one page) or a portfolio section that rendered empty because
the *swing* scan failed.

**Failure isolation is deliberately narrow.** Each read catches exactly the
exception family its own CLI command catches — `MarketPulseError` for the pulse,
`MacroError` for macro, and so on. Those are the families that mean *a source
did not answer*. Everything else propagates, because a `KeyError` in a mapping
function is a defect, and a dashboard that renders a defect as a tidy amber
"section unavailable" panel is a dashboard that hides its own bugs. The `except`
clauses here name types; not one of them is `except Exception`.

**The clock is not read here.** ``refreshed_at`` and ``reference_time`` are
supplied by the caller, exactly as every other composition root in this
repository requires, so a snapshot is reproducible and two composes over the
same inputs are equal.

**Nothing in this module writes.** No store verb, no path is opened for writing,
and a guard asserts the whole package is free of both.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from fmis.macro import MacroError
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    MarketPulseError,
    universe_subset,
)
from fmis.operator_dashboard.models import (
    LabView,
    DASHBOARD_SCHEMA_VERSION,
    DataHealthView,
    MacroView,
    OperatorDashboardSnapshot,
    OverviewCounts,
    PaperView,
    PerformanceView,
    PortfolioView,
    PulseView,
    DashboardSection,
    DashboardSectionStatus,
    ScanChangeView,
    SwingView,
)
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
from fmis.pipeline.macro import macro_universe, run_macro_context
from fmis.pipeline.pulse import run_market_pulse
from fmis.position_sizing import APPROVAL_ERRORS
from fmis.provenance import Absent
from fmis.risk_policy import RiskPolicyError, RiskPolicyFileError, load_declaration
from fmis.statistics import STATISTICS_ERRORS, report_for_store, statistics_store_root
from fmis.swing_workspace import SwingWorkspaceError, run_swing_workspace
from fmis.today import TodayError

__all__ = [
    "REFRESH_READS",
    "DEFAULT_WORKSPACE_RUNNER",
    "DASHBOARD_LIMITATIONS",
    "WORKSPACE_ERRORS",
    "RISK_POLICY_ERRORS",
    "build_snapshot",
    "refresh",
]

#: The workspace read `refresh` performs unless a caller injects another.
#: **Named so a layer that must wrap it takes *this* default** rather than
#: importing `fmis.swing_workspace` a second time — two names for one default is
#: how the two drift, and `fmis.swing_workspace` is guarded to be imported from
#: exactly one module of `fmis.pipeline`.
DEFAULT_WORKSPACE_RUNNER = run_swing_workspace

#: Every engine read one refresh performs, named so the count is a contract
#: rather than an accident. A test asserts the composition root calls exactly
#: these, exactly once each.
REFRESH_READS = (
    "fmis.swing_workspace.run_swing_workspace",
    "fmis.pipeline.pulse.run_market_pulse",
    "fmis.pipeline.macro.run_macro_context",
    "fmis.statistics.report_for_store",
)

#: What this surface cannot do, printed on the page rather than left for the
#: owner to discover. Every entry is a property of the build, not a to-do.
DASHBOARD_LIMITATIONS = (
    (
        "read-only",
        "This surface reads. It cannot place, amend, cancel or record an order, "
        "activate or close a paper trade, or change any stored value. No such "
        "method is reachable from it.",
    ),
    (
        "not live",
        "The page shows what one refresh read. It does not stream, and it does "
        "not update itself. Every figure carries the instant it describes, and "
        "the header carries the instant the page was built.",
    ),
    (
        "no page-level freshness verdict",
        "Sources publish on different schedules, so the page states each "
        "reading's age and its own source's verdict rather than one judgement "
        "over all of them. There is no composite health score, deliberately.",
    ),
    (
        "no interpretation",
        "Nothing here is a view, a signal, a recommendation or a ranking of "
        "desirability. Setups appear in the order the swing workspace placed "
        "them, by a stated key printed on each row.",
    ),
)

#: The families that mean *the workspace's own read failed*. Mirrors exactly what
#: `fmits workspace` catches, so the dashboard and the CLI agree about what is a
#: data failure and what is a defect.
WORKSPACE_ERRORS: tuple[type[BaseException], ...] = (
    SwingWorkspaceError,
    TodayError,
    *APPROVAL_ERRORS,
)

#: The families that mean *the owner's declared risk policy could not be read*.
#: Separate from `WORKSPACE_ERRORS` because the remedy is different and the
#: page says so: a malformed declaration is a file the owner can fix, not a
#: market that could not be reached.
RISK_POLICY_ERRORS: tuple[type[BaseException], ...] = (
    RiskPolicyFileError,
    RiskPolicyError,
)


def _unavailable(name: str, error: BaseException) -> DashboardSection[Any]:
    """A failed section, carrying the error's type and message as its reason.

    The type name is included because *"HTTPError: 503"* tells the owner the
    provider answered and refused, while *"503"* alone could be anything.
    """
    return DashboardSection(
        name=name,
        status=DashboardSectionStatus.UNAVAILABLE,
        unavailable_reason=f"{type(error).__name__}: {error}",
    )


def _section(
    name: str,
    data: Any,
    *,
    as_of: datetime | None,
    source: str,
    empty: bool = False,
) -> DashboardSection[Any]:
    return DashboardSection(
        name=name,
        status=DashboardSectionStatus.EMPTY if empty else DashboardSectionStatus.AVAILABLE,
        as_of=as_of,
        source=source,
        data=data,
    )


def build_snapshot(
    *,
    refreshed_at: datetime,
    reference_time: datetime,
    workspace: Any | None = None,
    workspace_error: BaseException | None = None,
    pulse: Any | None = None,
    pulse_error: BaseException | None = None,
    macro: Any | None = None,
    macro_error: BaseException | None = None,
    statistics: Any | None = None,
    statistics_error: BaseException | None = None,
    lab: LabView | None = None,
    geometry: Any | None = None,
    validation: Any | None = None,
    scan_change: ScanChangeView | None = None,
) -> OperatorDashboardSnapshot:
    """Assemble one snapshot from engine outputs that have already been read.

    **Pure.** No provider, no store, no clock. `refresh` does the reading and
    calls this; a test injects outputs and calls it directly. That split is what
    makes every mapping assertion in the suite cheap and every one of them
    deterministic — the same inputs always produce an equal snapshot.

    Each domain is supplied either as its engine output *or* as the exception
    that stopped it being read. Supplying both is refused: a section that held
    data and a failure would render as whichever the UI checked first.
    """
    for name, value, error in (
        ("workspace", workspace, workspace_error),
        ("pulse", pulse, pulse_error),
        ("macro", macro, macro_error),
        ("statistics", statistics, statistics_error),
    ):
        if value is not None and error is not None:
            raise ValueError(
                f"{name} was supplied both an output and a failure; which one "
                "the page showed would depend on the order it checked them"
            )

    # --- the three sections that share the workspace's single read -----------
    if workspace is not None:
        swing = swing_view(workspace)
        portfolio = portfolio_view(workspace)
        paper = paper_view(workspace)
        counts = counts_from(workspace)
        warnings = warning_rows(workspace)
        analysis_as_of = workspace.summary.analysis_as_of or workspace.reference_time
        swing_section: DashboardSection[SwingView] = _section(
            "swing",
            swing,
            as_of=analysis_as_of,
            source="fmis.swing_workspace · one scan, one store read",
        )
        portfolio_section: DashboardSection[PortfolioView] = _section(
            "portfolio",
            portfolio,
            as_of=portfolio.snapshot_as_of or workspace.reference_time,
            source=f"durable store · {portfolio.store_root}",
            empty=not portfolio.store_present,
        )
        paper_section: DashboardSection[PaperView] = _section(
            "paper",
            paper,
            as_of=workspace.reference_time,
            source="fmis.paper · simulated trades only",
            empty=not paper.rows,
        )
    else:
        swing = portfolio = paper = None
        counts = OverviewCounts()
        warnings = ()
        error = workspace_error or RuntimeError("the workspace was not read")
        swing_section = _unavailable("swing", error)
        portfolio_section = _unavailable("portfolio", error)
        paper_section = _unavailable("paper", error)

    # --- markets -------------------------------------------------------------
    if pulse is not None:
        pulse_data: PulseView | None = pulse_view(pulse)
        pulse_section: DashboardSection[PulseView] = _section(
            "pulse",
            pulse_data,
            as_of=pulse_data.as_of,
            source=f"fmis.market_pulse · {pulse_data.universe}",
            empty=not pulse_data.rows,
        )
    else:
        pulse_data = None
        pulse_section = _unavailable(
            "pulse", pulse_error or RuntimeError("the pulse was not read")
        )

    if macro is not None:
        macro_data: MacroView | None = macro_view(macro)
        macro_section: DashboardSection[MacroView] = _section(
            "macro",
            macro_data,
            as_of=macro_data.as_of,
            source="fmis.macro · macro & cross-asset context",
            empty=not macro_data.rows,
        )
    else:
        macro_data = None
        macro_section = _unavailable(
            "macro", macro_error or RuntimeError("the macro context was not read")
        )

    # --- performance ---------------------------------------------------------
    if statistics is not None:
        views: tuple[PerformanceView, ...] | None = performance_views(statistics)
        performance_section: DashboardSection[tuple[PerformanceView, ...]] = _section(
            "performance",
            views,
            as_of=statistics.reference_time,
            source=f"fmis.statistics · {statistics.store_root}",
            empty=not views,
        )
    else:
        views = None
        performance_section = _unavailable(
            "performance",
            statistics_error or RuntimeError("the statistics corpus was not read"),
        )

    # --- health --------------------------------------------------------------
    health = health_view(
        pulse=pulse_data,
        macro=macro_data,
        portfolio=portfolio,
        paper=paper,
        pulse_failure=(
            f"{type(pulse_error).__name__}: {pulse_error}" if pulse_error else None
        ),
        macro_failure=(
            f"{type(macro_error).__name__}: {macro_error}" if macro_error else None
        ),
        store_failure=(
            f"{type(workspace_error).__name__}: {workspace_error}"
            if workspace_error
            else None
        ),
    )
    health_section: DashboardSection[DataHealthView] = _section(
        "health",
        health,
        as_of=refreshed_at,
        source="every source this refresh touched",
        empty=not health.sources,
    )

    # --- swing lab -----------------------------------------------------------
    # NOT a read. The artifact was decoded by the caller and handed in already
    # parsed, which is what keeps this package free of any filesystem access at
    # all — a guard asserts no module here opens anything.
    lab_section: DashboardSection[LabView] | None = (
        None
        if lab is None
        else _section(
            "lab",
            lab,
            as_of=None,
            source=f"saved research artifact · {lab.experiment_id}",
            empty=not lab.variants,
        )
    )

    # --- trade geometry ------------------------------------------------------
    # Same discipline as the lab section above: decoded by the caller, handed in
    # already parsed, so this package still opens nothing.
    geometry_section = (
        None
        if geometry is None
        else _section(
            "geometry",
            geometry,
            as_of=None,
            source=f"saved geometry artifact · {geometry.experiment_id}",
            empty=not geometry.policies,
        )
    )

    # --- pre-registered validation -------------------------------------------
    # Milestone BY, on the same footing: decoded by the caller, handed in already
    # parsed, so this package still opens nothing.
    validation_section = (
        None
        if validation is None
        else _section(
            "validation",
            validation,
            as_of=None,
            source=(
                f"saved validation artifact · {validation.experiment_id} · "
                f"seal {validation.preregistration_id}"
            ),
            empty=not validation.policies,
        )
    )

    return OperatorDashboardSnapshot(
        refreshed_at=refreshed_at,
        reference_time=reference_time,
        counts=counts,
        pulse=pulse_section,
        macro=macro_section,
        swing=swing_section,
        portfolio=portfolio_section,
        paper=paper_section,
        performance=performance_section,
        health=health_section,
        lab=lab_section,
        geometry=geometry_section,
        validation=validation_section,
        warnings=warnings,
        # NOT computed and NOT read here. The comparison against the previous
        # scan is produced by the layer that owns the history store, exactly as
        # the three research artifacts above are decoded by the caller — which
        # is what keeps this package free of every write and every open, and a
        # guard asserts both.
        scan_change=scan_change,
        limitations=DASHBOARD_LIMITATIONS,
        schema_version=DASHBOARD_SCHEMA_VERSION,
    )


def refresh(
    *,
    refreshed_at: datetime,
    reference_time: datetime | None = None,
    symbols: Sequence[str] | None = None,
    store_root: Path | str | None = None,
    benchmarks: Sequence[str] | None = None,
    with_relationships: bool = True,
    workspace_runner: Callable[..., Any] = DEFAULT_WORKSPACE_RUNNER,
    pulse_runner: Callable[..., Any] = run_market_pulse,
    macro_runner: Callable[..., Any] = run_macro_context,
    statistics_runner: Callable[..., Any] = report_for_store,
    lab: LabView | None = None,
    geometry: Any | None = None,
    validation: Any | None = None,
    risk_policy_path: Path | str | None = None,
) -> OperatorDashboardSnapshot:
    """Perform one refresh: four reads, each isolated, then one snapshot.

    **The four runners are injected.** Production passes the real composition
    roots by default; a test passes fakes and asserts both the call count and
    that one failing runner does not cost the other three their sections. That
    is the only injection seam this layer needs — the runners themselves already
    take every provider and store argument the CLI passes them.

    Args:
        refreshed_at: when this refresh happened. The header's *last refresh*.
        reference_time: the instant the analysis describes. Defaults to
            ``refreshed_at``; supplied separately so a replayed page can state a
            past market instant while honestly reporting when it was built.
        symbols: the watchlist to scan. Omitted, the workspace's own default.
        store_root: the durable store. Omitted, the owner's.
        benchmarks: a subset of the market universe. Omitted, the whole of it.
        with_relationships: whether macro measures its cross-asset section. It
            costs one extra request; `False` skips both it and the request.
    """
    at = reference_time or refreshed_at

    # The owner's declared risk policy, read before the scan so a malformed
    # declaration is reported as itself rather than as a workspace failure. A
    # missing file is `Absent` and is passed through as `None`: no policy
    # declared is the ordinary state, and every surface below states it.
    declaration: Any | None = None
    workspace_error: BaseException | None = None
    try:
        loaded = load_declaration(risk_policy_path)
        declaration = None if isinstance(loaded, Absent) else loaded
    except RISK_POLICY_ERRORS as error:
        # The page still renders. A typo in a capital figure must not cost the
        # owner every setup on the watchlist, and the planning section says what
        # happened where the figures would have been.
        workspace_error = error

    workspace: Any | None = None
    if workspace_error is None:
        try:
            workspace = (
                workspace_runner(
                    symbols,
                    reference_time=at,
                    store_root=store_root,
                    risk_declaration=declaration,
                )
                if symbols
                else workspace_runner(
                    reference_time=at,
                    store_root=store_root,
                    risk_declaration=declaration,
                )
            )
        except WORKSPACE_ERRORS as error:
            workspace_error = error

    pulse: Any | None = None
    pulse_error: BaseException | None = None
    try:
        universe = (
            DEFAULT_PULSE_UNIVERSE
            if not benchmarks
            else universe_subset(
                DEFAULT_PULSE_UNIVERSE, tuple(benchmarks), name="selected"
            )
        )
        pulse = pulse_runner(as_of=at, universe=universe)
    except MarketPulseError as error:
        pulse_error = error

    macro: Any | None = None
    macro_error: BaseException | None = None
    try:
        macro = macro_runner(
            as_of=at,
            universe=macro_universe(),
            with_relationships=with_relationships,
        )
    except (MacroError, MarketPulseError) as error:
        macro_error = error

    statistics: Any | None = None
    statistics_error: BaseException | None = None
    try:
        # `statistics_store_root` parses a flag's text, so a `Path` is spelled
        # back out rather than passed through. The alternative — a second way to
        # resolve the default store — is the one that drifts.
        statistics = statistics_runner(
            statistics_store_root(None if store_root is None else str(store_root)),
            at=at,
        )
    except STATISTICS_ERRORS as error:
        statistics_error = error

    return build_snapshot(
        refreshed_at=refreshed_at,
        reference_time=at,
        workspace=workspace,
        workspace_error=workspace_error,
        pulse=pulse,
        pulse_error=pulse_error,
        macro=macro,
        macro_error=macro_error,
        statistics=statistics,
        statistics_error=statistics_error,
        lab=lab,
        # `geometry` and `validation` are forwarded for the same reason `lab`
        # is. Omitting them made both `--geometry-artifact` and
        # `--validation-artifact` INERT: the CLI decoded the artifact, handed it
        # to the refresher, and the page still reported that nothing was loaded.
        # A parameter accepted and dropped is worse than one that does not
        # exist, because the caller has no way to tell.
        geometry=geometry,
        validation=validation,
    )
