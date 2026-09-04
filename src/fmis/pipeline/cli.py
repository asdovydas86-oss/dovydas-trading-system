"""Command-line entry point — the repository's product surface.

    fmits facts BTCUSDT
    fmits facts ETHUSDT --interval 1d --limit 300
    fmits mtf   BTCUSDT
    fmits mtf   BTCUSDT --context 1w --setup 1d --execution 4h
    python -m fmis.pipeline mtf BTCUSDT

Two subcommands. ``facts`` prints one timeframe's `StructuralFactSheet`; ``mtf``
prints several role-labelled timeframes side by side. They exist so the
deterministic engines can be *read* by a human, which until Milestone AF nothing
allowed.

**The CLI holds no logic.** It parses arguments, calls one composition root,
renders the result, and maps failures to exit codes. Every number it prints was
produced by an engine; adding a calculation here would put market logic in the
one layer with no tests over market behaviour.

**Commands are declared, not dispatched by hand.** Each is a `Command` record
carrying its own argument configuration and runner, and `COMMANDS` is the single
registry `build_parser` and `main` both read. The alternative — an ``if/elif``
chain in `main` — makes the parser and the dispatcher two places to keep in sync,
and the third command is where that starts going wrong.

**This is where the clock lives.** Everything beneath is a pure function of its
inputs, so no composition root reads the time. Data *age* needs a reference
instant, and this — the outermost edge — is the only correct place to take one.
``--reference-time`` makes even that injectable, so rendered output can be pinned
in a test.

Exit codes: ``0`` success · ``1`` a data or provider failure the user can act on
· ``2`` bad usage (argparse's own convention).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

import fmis
from fmis.archive import (
    ArchiveError,
    ArchiveStore,
    RecordNotFoundError,
    default_archive_root,
    render_archive_verification,
    render_manifest,
    render_record_verification,
)
from fmis.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from fmis.operator_dashboard import (
    DEFAULT_HOST as DASHBOARD_DEFAULT_HOST,
    DEFAULT_PORT as DASHBOARD_DEFAULT_PORT,
    SnapshotHolder,
    serve as serve_dashboard,
)
from fmis.pipeline.market_analysis import PipelineError
from fmis.daily import DailyRun, DailyRunError, render_daily_run, run_daily
from fmis.market_regime import RegimePolicy
from fmis.swing_lab import (
    CONSERVATIVE_COSTS,
    FRICTIONLESS_COSTS,
    PRE_SPECIFIED_VARIANTS,
    SwingLabError,
    measure_robustness,
    run_lab_study,
    variant_by_id,
    write_study,
)
from fmis.swing_lab import read_artifact, verify_digest
from fmis.swing_lab.geometry_artifact import (
    read_geometry_artifact,
    verify_geometry_digest,
    write_geometry_study,
)
from fmis.swing_lab.geometry_render import render_geometry_study
from fmis.swing_lab.validation_artifact import (
    read_validation_artifact,
    verify_preregistration_seal,
    verify_result_digest,
    write_validation_study,
)
from fmis.swing_lab.admission_artifact import (
    encode_admission_study,
    write_admission_study,
)
from fmis.paired_dependence import (
    PairedDependenceError,
    dependence_rows_of,
    encode_dependence_study,
    read_dependence_study,
    render_dependence_study,
    study_from_capture as dependence_study_from_capture,
    study_from_rows as dependence_study_from_rows,
    verify_dependence_study_digest,
    write_dependence_study,
)
from fmis.universe import (
    CC_PREREGISTRATION_DIGEST,
    SeriesCache,
    UniverseError,
    encode_universe_study,
    render_universe_study,
    run_universe_study,
    write_universe_artifact,
)
from fmis.swing_lab.admission_power import (
    CA_DESIGN_CURVE_CORRELATIONS,
    CA_LIMITATIONS as CA_DESIGN_LIMITATIONS,
    ca_design_assessment,
    ca_design_curve,
    ca_post_hoc,
    ca_reproduction,
)
from fmis.swing_lab.admission_render import render_admission_study
from fmis.swing_lab.admission_study import study_from_capture
from fmis.research_design import (
    GrowthPath,
    ResearchDesignError,
    encode_design_assessment,
    render_design_assessment,
    verify_design_assessment_digest,
)
from fmis.research_design.render import rule, wrap_text
from fmis.swing_lab.persistence_artifact import (
    read_persistence_capture,
    verify_capture_digest,
)
from fmis.swing_lab.persistence_preregistration import BZ_PREREGISTRATION_DIGEST
from fmis.swing_lab.persistence_render import render_persistence_study
from fmis.swing_lab.persistence_study import (
    run_persistence_experiment,
    study_from_captures,
)
from fmis.swing_lab.validation_render import render_validation_study
from fmis.swing_lab.validation_study import run_validation_experiment
from fmis.swing_lab.geometry_study import run_geometry_experiment
from fmis.swing_lab.render import render_robustness, render_study
from fmis.operator_dashboard.sections import geometry_view, lab_view, validation_view
from fmis.swing_setup import (
    BacktestError,
    DEFAULT_BACKTEST_DAYS,
    DEFAULT_BACKTEST_LIMIT,
    DEFAULT_BACKTEST_SYMBOLS,
    DEFAULT_EVALUATION_WINDOW_BARS,
    DEFAULT_VARIANT_MAX_AGES,
    SCAN_UNIVERSE,
    SetupRunResult,
    compare_variant,
    compute_metrics,
    post_filter_comparison,
    render_availability_report,
    render_backtest_report,
    render_research_report,
    render_scan,
    render_scan_report,
    render_setup,
    run_backtest,
    run_market_scan,
    run_research_study,
    run_setup_for_symbols,
)
from fmis.pipeline.prices import MARK_INTERVAL
from fmis.position_sizing import (
    APPROVAL_ERRORS,
    DEFAULT_BOOK,
    DEFAULT_OWNER_TIMEZONE,
    DEFAULT_SIZING_POLICY_ID,
    price_from_text,
    proposal_for_plan,
    scope_from_text,
    proposal_from_text,
    render_approval,
    resolve_account,
    run_approval,
    sizing_policy_from_text,
)
from fmis.paper import (
    AMENDMENT_REASON_SUGGESTIONS,
    ENTRY_TYPE_CHOICES,
    LIFECYCLE_STATE_CHOICES,
    PAPER_DUST_POLICY,
    PAPER_ERRORS,
    activate_request_from_text,
    activate_trade,
    amend_request_from_text,
    amend_stop,
    bars_from_series,
    cancel_activation,
    cancel_request_from_text,
    list_paper_trades,
    load_paper_trade,
    render_activation,
    render_history,
    render_lifecycle,
    render_simulation,
    render_status,
    run_simulation,
    states_from_text,
)
from fmis.pipeline.candles import (
    SIMULATION_CANDLE_LIMIT,
    SIMULATION_INTERVAL,
    fetch_simulation_candles,
)
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    MarketPulseError,
    render_market_pulse,
    universe_subset,
)
from fmis.pipeline.pulse import run_market_pulse
from fmis.macro import MacroError, render_macro_context
from fmis.pipeline.macro import macro_universe, run_macro_context
from fmis.today import TodayError, render_today, run_today
from fmis.swing_workspace import (
    SwingWorkspaceError,
    render_swing_workspace,
    run_swing_workspace,
)
from fmis.valuation import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_ID,
    ValuationError,
    render_valuation,
    run_valuation,
)
from fmis.trade_capture import (
    BOOK_CHOICES,
    CAPTURE_DUST_POLICY,
    CAPTURE_ERRORS,
    DEFAULT_MARKET_MODE,
    DEFAULT_QUOTE_ASSET,
    DEFAULT_VENUE,
    DIRECTION_CHOICES,
    MARKET_MODE_CHOICES,
    STATUS_CHOICES,
    append_note,
    capture_store_root,
    close_request_from_text,
    close_trade,
    filters_from_text,
    list_trades,
    load_trade,
    market_from_symbol,
    note_request_from_text,
    open_store,
    plan_request_from_text,
    record_plan,
    record_request_from_text,
    record_trade,
    render_listing,
    render_outcome,
    render_trade,
)
from fmis.setup_evidence import (
    SetupEvidenceError,
    SetupIdentityRef,
    project_setup_evidence,
    render_setup_evidence,
)
from fmis.setup_observation import observe_setup_series, render_setup_identity
from fmis.statistics import (
    DIMENSION_NAMES,
    NO_EQUITY_BASIS,
    NO_STARTING_EQUITY,
    STATISTICS_ERRORS,
    DEFAULT_REGIME_DIMENSION,
    as_of_from_text,
    baseline_from_text,
    policy_from_text,
    render_equity,
    render_expectancy,
    render_performance,
    render_statistics,
    render_trades_summary,
    report_for_store,
    statistics_store_root,
)
from fmis.workspace import Workspace, render_workspace, workspace_for_symbol
from fmis.pipeline.regime import (
    REGIME_LIMITATIONS,
    multi_timeframe_regime_for_symbol,
    regime_for_symbol,
)
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.render import (
    render_fact_sheet,
    render_multi_timeframe_regime,
    render_multi_timeframe_sheet,
    render_regime_sheet,
)
from fmis.pipeline.structural_facts import (
    DetectionSettings,
    structural_facts_for_symbol,
)
from fmis.providers.binance import BinanceError

__all__ = ["main", "build_parser", "Command", "COMMANDS"]

_DEFAULT_INTERVAL = "4h"

#: Exit codes. Kept as names so the tests assert intent rather than integers.
EXIT_OK = 0
EXIT_FAILURE = 1


@dataclass(frozen=True, slots=True)
class Command:
    """One subcommand: its name, its help, how to configure it, how to run it.

    ``configure`` receives the subparser and adds this command's arguments;
    ``run`` receives the parsed namespace and returns an exit code. Holding both
    on one record means a command cannot be registered without a runner, or
    given a runner the parser never reaches.
    """

    name: str
    help: str
    description: str
    configure: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Arguments every analysis command shares, defined once."""
    parser.add_argument("symbol", help="exact provider symbol, e.g. BTCUSDT")
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="number of candles to request (default: provider default)",
    )
    parser.add_argument(
        "--left-bars",
        type=int,
        default=DEFAULT_LEFT_BARS,
        help=f"swing detection left neighbours (default: {DEFAULT_LEFT_BARS})",
    )
    parser.add_argument(
        "--right-bars",
        type=int,
        default=DEFAULT_RIGHT_BARS,
        help=(
            f"swing detection right neighbours (default: {DEFAULT_RIGHT_BARS}). "
            "Also used as the break-confirmation delay — one value, both uses, "
            "so they cannot disagree (ADR-0020 D1)."
        ),
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        metavar="ISO8601",
        help=(
            "instant to measure data age against (default: now). Supply it to "
            "make the rendered output reproducible."
        ),
    )
    parser.add_argument(
        "--no-age",
        action="store_true",
        help="omit the data-age line entirely",
    )


def _configure_facts(parser: argparse.ArgumentParser) -> None:
    _add_common_arguments(parser)
    parser.add_argument(
        "-i",
        "--interval",
        default=_DEFAULT_INTERVAL,
        help=f"candle interval (default: {_DEFAULT_INTERVAL})",
    )


def _configure_mtf(parser: argparse.ArgumentParser) -> None:
    _add_common_arguments(parser)
    for role in (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION):
        default = DEFAULT_TIMEFRAMES[role]
        parser.add_argument(
            f"--{role.value}",
            default=default,
            metavar="INTERVAL",
            help=f"interval playing the {role.value} role (default: {default})",
        )


def _detection_from(args: argparse.Namespace) -> DetectionSettings:
    return DetectionSettings(left_bars=args.left_bars, right_bars=args.right_bars)


def _run_facts(args: argparse.Namespace) -> int:
    reference = _reference_time(args.reference_time, omit=args.no_age)
    sheet = structural_facts_for_symbol(
        args.symbol,
        args.interval,
        limit=args.limit,
        detection=_detection_from(args),
    )
    print(render_fact_sheet(sheet, reference_time=reference))
    return EXIT_OK


def _run_mtf(args: argparse.Namespace) -> int:
    reference = _reference_time(args.reference_time, omit=args.no_age)
    sheet = multi_timeframe_facts_for_symbol(
        args.symbol,
        timeframes={
            TimeframeRole.CONTEXT: args.context,
            TimeframeRole.SETUP: args.setup,
            TimeframeRole.EXECUTION: args.execution,
        },
        limit=args.limit,
        detection=_detection_from(args),
    )
    print(render_multi_timeframe_sheet(sheet, reference_time=reference))
    return EXIT_OK


def _configure_regime(parser: argparse.ArgumentParser) -> None:
    _add_common_arguments(parser)
    parser.add_argument(
        "-i",
        "--interval",
        default=_DEFAULT_INTERVAL,
        help=f"candle interval (default: {_DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--multi",
        action="store_true",
        help=(
            "classify each of the three roles instead of one interval. Each view "
            "is classified alone; nothing is derived from their combination."
        ),
    )
    for role in (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION):
        default = DEFAULT_TIMEFRAMES[role]
        parser.add_argument(
            f"--{role.value}",
            default=default,
            metavar="INTERVAL",
            help=(
                f"interval playing the {role.value} role under --multi "
                f"(default: {default})"
            ),
        )
    parser.add_argument(
        "--band",
        type=float,
        default=None,
        metavar="FRACTION",
        help=(
            "policy band for volatility and participation (default: "
            f"{RegimePolicy().volatility_band}). One number producing two "
            "mirrored edges, so an asymmetric gate cannot be expressed."
        ),
    )
    parser.add_argument(
        "--transition-lookback",
        type=int,
        default=None,
        metavar="BARS",
        help=(
            "how recent a change of character must be for structure to read as "
            f"transitioning (default: {RegimePolicy().transition_lookback_bars})"
        ),
    )


def _policy_from(args: argparse.Namespace) -> RegimePolicy:
    """Build the policy from the flags, falling back to each stated default.

    The band reaches both dimensions from **one** flag. Two flags would let a
    caller skew volatility against participation, which is the shape of gate
    `docs/analysis-notes.md` blames for the v2 bias, expressed at the CLI.
    """
    default = RegimePolicy()
    custom = args.band is not None or args.transition_lookback is not None
    return RegimePolicy(
        policy_id=f"{default.policy_id}-custom" if custom else default.policy_id,
        volatility_band=(
            default.volatility_band if args.band is None else args.band
        ),
        participation_band=(
            default.participation_band if args.band is None else args.band
        ),
        transition_lookback_bars=(
            default.transition_lookback_bars
            if args.transition_lookback is None
            else args.transition_lookback
        ),
    )


def _run_regime(args: argparse.Namespace) -> int:
    policy = _policy_from(args)
    if args.multi:
        _, regimes = multi_timeframe_regime_for_symbol(
            args.symbol,
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=policy,
            detection=_detection_from(args),
        )
        print(render_multi_timeframe_regime(regimes))
        return EXIT_OK
    _, regime = regime_for_symbol(
        args.symbol,
        args.interval,
        limit=args.limit,
        policy=policy,
        detection=_detection_from(args),
    )
    print(render_regime_sheet(regime, limitations=REGIME_LIMITATIONS))
    return EXIT_OK


REGIME_COMMAND = Command(
    name="regime",
    help="classify the market environment for one symbol",
    description=(
        "Fetch public candles for SYMBOL and classify three environments — "
        "structure, volatility and participation — each with the evidence "
        "behind it, the evidence against it, what was unavailable, and the exact "
        "policy that produced the result. A regime is not a direction and not a "
        "recommendation."
    ),
    configure=_configure_regime,
    run=_run_regime,
)


def _add_archive_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--archive-root",
        default=None,
        metavar="PATH",
        help=f"archive root (default: {default_archive_root()})",
    )


def _add_archive_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--archive",
        action="store_true",
        help="also archive the result durably (Memory & Decision Archive)",
    )
    _add_archive_root_argument(parser)


def _archive_root_from(args: argparse.Namespace) -> Path:
    return Path(args.archive_root) if args.archive_root else default_archive_root()


def _configure_swing(parser: argparse.ArgumentParser) -> None:
    _add_common_arguments(parser)
    _add_archive_arguments(parser)
    for role in (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION):
        default = DEFAULT_TIMEFRAMES[role]
        parser.add_argument(
            f"--{role.value}",
            default=default,
            metavar="INTERVAL",
            help=f"interval playing the {role.value} role (default: {default})",
        )
    parser.add_argument(
        "--band",
        type=float,
        default=None,
        metavar="FRACTION",
        help=(
            "regime policy band for volatility and participation (default: "
            f"{RegimePolicy().volatility_band})"
        ),
    )
    parser.add_argument(
        "--transition-lookback",
        type=int,
        default=None,
        metavar="BARS",
        help=(
            "how recent a change of character must be for structure to read as "
            f"transitioning (default: {RegimePolicy().transition_lookback_bars})"
        ),
    )


def _maybe_archive(args: argparse.Namespace, artifact: Workspace | DailyRun, *, label: str) -> int:
    """Archive `artifact` if `--archive` was requested; report failure distinctly.

    An archive failure is a **different fact** from an analysis failure: the
    analysis already printed successfully above this call, so a non-zero exit
    here must never read as "the analysis failed" (design doc §3.6).
    """
    if not args.archive:
        return EXIT_OK
    store = ArchiveStore(_archive_root_from(args))
    try:
        record = store.archive_workspace(artifact) if isinstance(artifact, Workspace) else store.archive_daily_run(artifact)
    except ArchiveError as error:
        print(f"fmits {label}: archive failed: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(f"archived: {record.record_id} -> {record.relative_path}")
    return EXIT_OK


def _run_swing(args: argparse.Namespace) -> int:
    _, workspace = workspace_for_symbol(
        args.symbol,
        timeframes={
            TimeframeRole.CONTEXT: args.context,
            TimeframeRole.SETUP: args.setup,
            TimeframeRole.EXECUTION: args.execution,
        },
        limit=args.limit,
        policy=_policy_from(args),
        detection=_detection_from(args),
    )
    print(render_workspace(workspace))
    return _maybe_archive(args, workspace, label="swing")


SWING_COMMAND = Command(
    name="swing",
    help="the complete swing workspace for one symbol",
    description=(
        "Fetch every timeframe once and compose the full swing workspace: data "
        "quality, market regime, structure by role, levels, evidence by family, "
        "conflicts and limitations. Risk, portfolio, trade plan and AI "
        "interpretation render as explicitly unavailable. Nothing here is a "
        "trade recommendation and no direction is expressed or implied."
    ),
    configure=_configure_swing,
    run=_run_swing,
)


def _add_setup_style_arguments(parser: argparse.ArgumentParser) -> None:
    """Arguments `setup` and `scan` share — everything but the symbol list.

    `setup` takes its symbols from the command line; `scan` takes them from
    `SCAN_UNIVERSE`. Every other option — candle limit, detection window,
    timeframe roles, regime policy — applies identically to both.
    """
    parser.add_argument(
        "-n", "--limit", type=int, default=None,
        help="candles to request per timeframe, applied to every symbol",
    )
    parser.add_argument(
        "--left-bars", type=int, default=DEFAULT_LEFT_BARS,
        help=f"swing detection left neighbours (default: {DEFAULT_LEFT_BARS})",
    )
    parser.add_argument(
        "--right-bars", type=int, default=DEFAULT_RIGHT_BARS,
        help=f"swing detection right neighbours (default: {DEFAULT_RIGHT_BARS})",
    )
    for role in (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION):
        default = DEFAULT_TIMEFRAMES[role]
        parser.add_argument(
            f"--{role.value}", default=default, metavar="INTERVAL",
            help=f"interval playing the {role.value} role (default: {default})",
        )
    parser.add_argument(
        "--band", type=float, default=None, metavar="FRACTION",
        help="regime policy band, applied identically to every symbol",
    )
    parser.add_argument(
        "--transition-lookback", type=int, default=None, metavar="BARS",
        help="regime transition lookback, applied identically to every symbol",
    )


def _configure_setup(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="+",
        metavar="SYMBOL",
        help="one or more symbols, assessed in the order given",
    )
    _add_setup_style_arguments(parser)


def _exit_code_for(results: Sequence[SetupRunResult]) -> int:
    """`EXIT_OK` unless every result failed — "at least one true report"."""
    return EXIT_OK if any(r.assessment is not None for r in results) else EXIT_FAILURE


def _run_setup(args: argparse.Namespace) -> int:
    """Print one full setup page per symbol, in requested order.

    A symbol whose analysis failed prints a failure block and does not stop the
    remaining symbols (design record §14) — the same isolation `fmits daily`
    applies, without depending on it. The command exits non-zero only when
    every requested symbol failed, matching `fmits daily`'s own "at least one
    result is a true report" contract.
    """
    results = run_setup_for_symbols(
        args.symbols,
        timeframes={
            TimeframeRole.CONTEXT: args.context,
            TimeframeRole.SETUP: args.setup,
            TimeframeRole.EXECUTION: args.execution,
        },
        limit=args.limit,
        policy=_policy_from(args),
        detection=_detection_from(args),
    )
    for position, result in enumerate(results):
        if position:
            print()
        if result.assessment is not None:
            print(render_setup(result.assessment))
            identity = _setup_identity_block(result)
            if identity is not None:
                print(identity)
        else:
            print(f"fmits setup: {result.requested_symbol}: {result.failure}", file=sys.stderr)
    return _exit_code_for(results)


#: The gap tolerance `fmits setup` groups under. **Zero, and the value cannot
#: matter here**: one invocation observes one bar, so there is no gap for a
#: tolerance to span. It is named rather than inlined so the choice is visible —
#: a surface that one day passes a *series* has to revisit it, and the data model
#: is explicit that no value for this parameter has been validated.
SETUP_IDENTITY_GAP_BARS = 0


def _setup_identity_block(result: SetupRunResult) -> str | None:
    """The stable-identity block for one assessed symbol, or `None`.

    **Appended to the page; nothing above it changes.** `render_setup` produces
    exactly the bytes it always did, and this block is printed after it.

    `None` is returned when the symbol cannot be resolved to a market. That is
    not a failure of the analysis: `market_from_symbol` refuses to guess where
    `BTCUSDT` divides into base and quote, and a symbol quoted in something other
    than the default is a real, legitimate case. Suppressing one *extra* block is
    the proportionate response — printing a fabricated market to keep the section
    would put an invented fact under a heading whose entire purpose is identity.

    Nothing here is written anywhere. `SetupObservation` and `SetupOccurrence` are
    rebuildable projections and the store refuses both.
    """
    assessment = result.assessment
    if assessment is None:  # pragma: no cover - guarded by the caller
        return None
    try:
        market = market_from_symbol(assessment.symbol)
    except (*CAPTURE_ERRORS, TypeError, ValueError):
        return None
    run = observe_setup_series(
        [assessment],
        market=market,
        code_version=fmis.__version__,
        occurrence_gap_bars=SETUP_IDENTITY_GAP_BARS,
    )
    return render_setup_identity(run)


SETUP_COMMAND = Command(
    name="setup",
    help="a deterministic swing-trade setup assessment for one or more symbols",
    description=(
        "Fetch every timeframe once per symbol and compose an explicit, "
        "testable swing-trade setup assessment: state (WAIT/CANDIDATE/"
        "CONFIRMED), direction when a candidate exists, the independent "
        "evidence families behind it, confirmation, invalidation, stop, "
        "target(s), risk/reward when computable, and every limitation that "
        "applies. WAIT is a successful result, not a failure. No position "
        "size and no calibrated probability are ever produced."
    ),
    configure=_configure_setup,
    run=_run_setup,
)


def _configure_evidence(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="+",
        metavar="SYMBOL",
        help="one or more symbols, explained in the order given",
    )
    _add_setup_style_arguments(parser)


def _identity_ref_for(result: SetupRunResult) -> SetupIdentityRef | None:
    """The stable identity of the assessed setup, or `None` when it has none.

    **Reuses the identity `fmits setup` already prints**, through the same
    `observe_setup_series` call, so the two surfaces can never disagree about
    what a setup is called. `fmis.setup_evidence` derives no identity of its
    own — `fmis.proposal.setup_identity` owns that rule.

    `None` is returned for a symbol that cannot be resolved to a market, and for
    a `WAIT` reading, which produces no occurrence because there is no
    directional idea to name. Both are ordinary outcomes, not failures.
    """
    assessment = result.assessment
    if assessment is None:  # pragma: no cover - guarded by the caller
        return None
    try:
        market = market_from_symbol(assessment.symbol)
    except (*CAPTURE_ERRORS, TypeError, ValueError):
        return None
    run = observe_setup_series(
        [assessment],
        market=market,
        code_version=fmis.__version__,
        occurrence_gap_bars=SETUP_IDENTITY_GAP_BARS,
    )
    if not run.occurrences:
        return None
    return SetupIdentityRef(setup_id=run.occurrences[-1].identity)


def _run_evidence(args: argparse.Namespace) -> int:
    """Print one evidence page per symbol, in requested order.

    Runs exactly the live `fmits setup` path and explains what it produced —
    the assessment is never recomputed under different arguments, so the page
    always explains a setup the owner could have seen on `fmits setup`.

    A symbol whose analysis failed prints a failure block and does not stop the
    remaining symbols, matching `fmits setup`'s own isolation contract.

    **Projection failure is isolated the same way.** An assessment can be
    produced and still not be projectable, and letting that abort the loop threw
    away the valid pages of every symbol queued behind it. Only
    `SetupEvidenceError` is caught, and only around the projection of one
    symbol: that is the error the package raises for a report it refuses to
    build. Anything else — a `TypeError`, an `AttributeError`, a bug in this
    file — is a programmer error and still propagates, because a surface that
    swallows those reports a clean page over broken code.
    """
    results = run_setup_for_symbols(
        args.symbols,
        timeframes={
            TimeframeRole.CONTEXT: args.context,
            TimeframeRole.SETUP: args.setup,
            TimeframeRole.EXECUTION: args.execution,
        },
        limit=args.limit,
        policy=_policy_from(args),
        detection=_detection_from(args),
    )
    rendered = 0
    for position, result in enumerate(results):
        if position:
            print()
        if result.assessment is None:
            print(
                f"fmits evidence: {result.requested_symbol}: {result.failure}",
                file=sys.stderr,
            )
            continue
        try:
            report = project_setup_evidence(
                result.assessment, setup_identity=_identity_ref_for(result)
            )
            page = render_setup_evidence(report)
        except SetupEvidenceError as failure:
            # Rendered inside the guard too, so a half-written page is never
            # printed above the error explaining that it could not be built.
            print(
                f"fmits evidence: {result.requested_symbol}: "
                f"evidence could not be projected: {failure}",
                file=sys.stderr,
            )
            continue
        print(page)
        rendered += 1
    return EXIT_OK if rendered else EXIT_FAILURE


EVIDENCE_COMMAND = Command(
    name="evidence",
    help="explain why a swing setup exists, and what argues against it",
    description=(
        "Project the deterministic swing-setup assessment into structured "
        "evidence: why the setup exists, what currently supports it, what "
        "conflicts with it, what confirmation is still outstanding, what could "
        "not be read, and whether enough deterministic information exists to "
        "decide. Family confluence reports agreement across evidence families "
        "and states plainly when correlated readings are not independent "
        "corroboration. WAIT is a successful result. Nothing here is a "
        "recommendation to trade, and no score, weight or calibrated "
        "probability is produced."
    ),
    configure=_configure_evidence,
    run=_run_evidence,
)


def _configure_scan(parser: argparse.ArgumentParser) -> None:
    _add_setup_style_arguments(parser)
    parser.add_argument(
        "--table", action="store_true",
        help=(
            "print the old compact one-row-per-symbol table instead of the "
            "market intelligence report"
        ),
    )


def _run_scan(args: argparse.Namespace) -> int:
    """Scan the fixed watchlist and print a market intelligence report.

    Reuses `run_market_scan` — itself `run_setup_for_symbols` over
    `SCAN_UNIVERSE` — so a scan row and a `fmits setup` page for the same
    symbol are produced by identical code and cannot disagree. A symbol whose
    analysis failed is isolated exactly as `setup` isolates it; the scan never
    stops early.

    Prints `render_scan_report` (Milestone AU) by default — a readable
    summary, market overview, actionable setups and grouped WAIT reasons over
    the exact same results. `--table` prints the original compact table
    (Milestone AT) instead, unchanged, for scripting or a narrower terminal.
    """
    results = run_market_scan(
        timeframes={
            TimeframeRole.CONTEXT: args.context,
            TimeframeRole.SETUP: args.setup,
            TimeframeRole.EXECUTION: args.execution,
        },
        limit=args.limit,
        policy=_policy_from(args),
        detection=_detection_from(args),
    )
    print(render_scan(results) if args.table else render_scan_report(results))
    return _exit_code_for(results)


SCAN_COMMAND = Command(
    name="scan",
    help="scan a fixed watchlist of major crypto pairs for a swing setup",
    description=(
        "Run the same deterministic swing-setup assessment `fmits setup` "
        "produces across a fixed, hardcoded watchlist of major crypto pairs, "
        "and print a readable market intelligence report: scan summary, "
        "market overview, actionable CONFIRMED/CANDIDATE setups with their "
        "stated reasons, and WAIT results grouped by reason. A symbol whose "
        "analysis fails is reported as ERROR and does not stop the scan. "
        "Symbols stay in the fixed list order within every section — this is "
        "not a ranking, and no score or probability is computed. `--table` "
        "prints the original compact one-row-per-symbol table instead."
    ),
    configure=_configure_scan,
    run=_run_scan,
)


def _configure_backtest(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="*",
        default=list(DEFAULT_BACKTEST_SYMBOLS),
        metavar="SYMBOL",
        help=(
            f"symbols to backtest (default: the {len(DEFAULT_BACKTEST_SYMBOLS)}-symbol "
            "v1 set)"
        ),
    )
    parser.add_argument(
        "--start", default=None, metavar="ISO8601",
        help=(
            "start of the historical window (default: --end minus "
            f"{DEFAULT_BACKTEST_DAYS} days)"
        ),
    )
    parser.add_argument(
        "--end", default=None, metavar="ISO8601",
        help="end of the historical window (default: now)",
    )
    parser.add_argument(
        "--window", type=int, default=DEFAULT_EVALUATION_WINDOW_BARS, metavar="BARS",
        help=(
            "execution-role bars to evaluate a confirmed setup's outcome over "
            f"(default: {DEFAULT_EVALUATION_WINDOW_BARS}); a measurement policy, "
            "not a tuned value"
        ),
    )
    parser.add_argument(
        "--research", action="store_true",
        help=(
            "run the corrected research harness (Milestone BC): --start/--end "
            "then mean the MEASUREMENT window, warm-up history is fetched "
            "before it, and outcome-tail candles are read after it. Without "
            "this flag the command behaves exactly as it always has"
        ),
    )
    parser.add_argument(
        "--max-confirmation-age", type=int, action="append", default=None,
        metavar="BARS", dest="max_confirmation_age",
        help=(
            "RESEARCH ONLY, repeatable: replay a counterfactual confirmation-"
            "staleness bound alongside the production baseline. Requires "
            "--research; it can never change live setup behaviour. Omitted "
            f"under --research, the brief's own set is used: "
            f"{', '.join(str(age) for age in DEFAULT_VARIANT_MAX_AGES)}"
        ),
    )
    _add_setup_style_arguments(parser)


def _backtest_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    end = _reference_time(args.end, omit=False)
    start = (
        datetime.fromisoformat(args.start)
        if args.start is not None
        else end - timedelta(days=DEFAULT_BACKTEST_DAYS)
    )
    if start.tzinfo is None:
        raise ValueError("--start must be timezone-aware, e.g. 2026-01-01T00:00:00+00:00")
    return start, end


def _run_research_backtest(args: argparse.Namespace) -> int:
    """Run the corrected research harness and print the study.

    ``--start``/``--end`` mean the **measurement** window here. Warm-up history
    is derived and fetched before it, outcome-tail candles are read after it,
    and every counterfactual staleness bound is replayed through the production
    composition path rather than filtered out of the baseline's results.

    A window the provider cannot supply enough history for is reported as an
    availability failure and exits non-zero — never quietly shortened.
    """
    start, end = _backtest_window(args)
    ages = (
        tuple(DEFAULT_VARIANT_MAX_AGES)
        if args.max_confirmation_age is None
        else tuple(args.max_confirmation_age)
    )
    try:
        study = run_research_study(
            args.symbols,
            measurement_start=start,
            measurement_end=end,
            run_at=datetime.now(timezone.utc),
            variant_max_ages=ages,
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=_policy_from(args),
            detection=_detection_from(args),
            evaluation_window_bars=args.window,
        )
    except BacktestError as error:
        print(f"fmits backtest --research: {error}", file=sys.stderr)
        return EXIT_FAILURE
    comparisons = tuple(compare_variant(study.baseline, run) for run in study.variants)
    post_filters = tuple(
        post_filter_comparison(study.baseline, run) for run in study.variants
    )
    print(render_availability_report(study.availability))
    print(render_research_report(study.runs, comparisons, post_filters))
    return EXIT_OK


def _run_backtest(args: argparse.Namespace) -> int:
    """Run the historical Swing Setup backtest and print its report.

    Reuses the unmodified production composition path over a replay
    transport — see `fmis.swing_setup.backtest_harness` for the no-lookahead
    argument in full. Not a portfolio backtest and not a claim of
    profitability; every limitation prints on the report itself.
    """
    if args.max_confirmation_age is not None and not args.research:
        print(
            "fmits backtest: --max-confirmation-age is a research-only override "
            "and requires --research. It is deliberately unreachable from any "
            "production command.",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if args.research:
        return _run_research_backtest(args)
    start, end = _backtest_window(args)
    try:
        run = run_backtest(
            args.symbols,
            start_time=start,
            end_time=end,
            run_at=datetime.now(timezone.utc),
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=_policy_from(args),
            detection=_detection_from(args),
            evaluation_window_bars=args.window,
        )
    except BacktestError as error:
        print(f"fmits backtest: {error}", file=sys.stderr)
        return EXIT_FAILURE
    metrics = compute_metrics(run)
    print(render_backtest_report(run, metrics))
    return EXIT_OK


BACKTEST_COMMAND = Command(
    name="backtest",
    help="replay the Swing Setup v1 policy over real historical candles",
    description=(
        "Replay the exact, unmodified Swing Setup v1 policy across a "
        "historical window of real closed candles, one simulated instant at "
        "a time, using only candles already closed at that instant. Records "
        "every WAIT/CANDIDATE/CONFIRMED observation, classifies what "
        "happened after each confirmed setup (TARGET_FIRST / STOP_FIRST / "
        "AMBIGUOUS_SAME_BAR / NEITHER_WITHIN_WINDOW), and prints deterministic "
        "aggregate measurements. This measures the current policy; it does "
        "not change it, rank it, or claim realized profitability. "
        "--research switches to the corrected harness (Milestone BC): "
        "--start/--end then name the MEASUREMENT window, warm-up history is "
        "derived and fetched before it, outcome-tail candles are read after "
        "it, and counterfactual confirmation-staleness bounds are replayed "
        "rather than filtered out of the baseline. The research override is "
        "unreachable without --research and never changes live behaviour."
    ),
    configure=_configure_backtest,
    run=_run_backtest,
)


def _configure_daily(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="+",
        metavar="SYMBOL",
        help=(
            "the daily universe, in the order it should be reported. A universe "
            "kept in a file is supplied by the shell: fmits daily $(cat list.txt)"
        ),
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=None,
        help="candles to request per timeframe, applied to every symbol",
    )
    parser.add_argument(
        "--left-bars", type=int, default=DEFAULT_LEFT_BARS,
        help=f"swing detection left neighbours (default: {DEFAULT_LEFT_BARS})",
    )
    parser.add_argument(
        "--right-bars", type=int, default=DEFAULT_RIGHT_BARS,
        help=f"swing detection right neighbours (default: {DEFAULT_RIGHT_BARS})",
    )
    for role in (TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION):
        default = DEFAULT_TIMEFRAMES[role]
        parser.add_argument(
            f"--{role.value}", default=default, metavar="INTERVAL",
            help=f"interval playing the {role.value} role (default: {default})",
        )
    parser.add_argument(
        "--band", type=float, default=None, metavar="FRACTION",
        help="regime policy band, applied identically to every symbol",
    )
    parser.add_argument(
        "--transition-lookback", type=int, default=None, metavar="BARS",
        help="regime transition lookback, applied identically to every symbol",
    )
    parser.add_argument(
        "--reference-time", default=None, metavar="ISO8601",
        help=(
            "instant the run is stamped with (default: now). Supply it to make "
            "the rendered index reproducible."
        ),
    )
    _add_archive_arguments(parser)


def _run_daily_command(args: argparse.Namespace) -> int:
    """Run the universe and print the index.

    An invalid universe is a caller error and is reported as one, with a
    non-zero exit code and no partial page. A symbol that failed is *not* a
    caller error: it appears as a row, and the run still exits zero, because the
    other symbols succeeded and the report is true.
    """
    reference = _reference_time(args.reference_time, omit=False)
    try:
        run = run_daily(
            args.symbols,
            reference_time=reference,
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=_policy_from(args),
            detection=_detection_from(args),
        )
    except DailyRunError as error:
        print(f"fmits daily: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_daily_run(run))
    return _maybe_archive(args, run, label="daily")


DAILY_COMMAND = Command(
    name="daily",
    help="run the swing analysis across a daily universe",
    description=(
        "Analyse every requested symbol through the same Swing Workspace one at "
        "a time, and print a compact readiness index: one row per symbol, in the "
        "order requested, with the decision-context state and the regime beside "
        "it. A symbol that fails reports why and does not stop the run. This is "
        "a readiness index, not a ranking: no score, no direction and no "
        "recommendation is produced."
    ),
    configure=_configure_daily,
    run=_run_daily_command,
)


def _configure_today(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="*",
        default=list(SCAN_UNIVERSE),
        metavar="SYMBOL",
        help=(
            f"the watchlist to scan (default: the {len(SCAN_UNIVERSE)}-symbol "
            "list `fmits scan` uses)"
        ),
    )
    _add_setup_style_arguments(parser)
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="PATH",
        help=(
            "the durable store to read positions, capital, decisions and "
            "journal entries from (default: the owner's store). Read-only: this "
            "command writes nothing"
        ),
    )
    _add_archive_root_argument(parser)
    parser.add_argument(
        "--no-records",
        action="store_true",
        help=(
            "do not read the durable store at all. The page still renders and "
            "says that it did not look"
        ),
    )
    parser.add_argument(
        "--no-marks",
        action="store_true",
        help=(
            "read the store but fetch no price. Positions are still listed, "
            "and every figure that needed a price says so with its reason"
        ),
    )
    parser.add_argument(
        "--mark-interval",
        default=MARK_INTERVAL,
        metavar="INTERVAL",
        help=(
            f"the timeframe a holding's price is read from (default: "
            f"{MARK_INTERVAL}); the close of its last closed candle"
        ),
    )
    parser.add_argument(
        "--account",
        default=None,
        metavar="ID",
        help=(
            "which account every candidate on this page is sized against "
            "(default: the only account the store records fills in). With "
            "several accounts and no flag, no approval is computed and the page "
            "says so — books never share capacity across accounts"
        ),
    )
    parser.add_argument(
        "--book",
        default=DEFAULT_BOOK.value,
        choices=BOOK_CHOICES,
        help=(
            f"which capacity pool a candidate would consume (default: "
            f"{DEFAULT_BOOK.value})"
        ),
    )
    parser.add_argument(
        "--risk-fraction",
        default=None,
        metavar="FRACTION",
        help=(
            "the fraction of equity to size each candidate at, e.g. 0.01 for "
            "1 %%. Omit it and the default the owner set below their per-trade "
            "ceiling is used; with neither, no size is produced and each row "
            "says so — a ceiling is not a target"
        ),
    )
    parser.add_argument(
        "--min-risk-reward",
        default=None,
        metavar="RATIO",
        help="warn when a candidate's planned reward-to-risk ratio is below this",
    )
    parser.add_argument(
        "--max-equity-age",
        default=None,
        metavar="DURATION",
        help="block sizing when the recorded equity is older than this, e.g. 7d",
    )
    parser.add_argument(
        "--max-mark-age",
        default=None,
        metavar="DURATION",
        help="block sizing when the oldest price is older than this, e.g. 36h",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_OWNER_TIMEZONE,
        metavar="ZONE",
        help=(
            f"the owner's calendar, for periodic limit boundaries (default: "
            f"{DEFAULT_OWNER_TIMEZONE}). A locale, never a threshold"
        ),
    )
    parser.add_argument(
        "--reference-time", default=None, metavar="ISO8601",
        help=(
            "instant the workspace is stamped with (default: now). Supply it to "
            "make the rendered page reproducible."
        ),
    )


def _run_today_command(args: argparse.Namespace) -> int:
    """Assemble and print the daily trading workspace.

    Reads the store; never writes to it. A symbol whose analysis failed appears
    as an ERROR row and does not stop the run, exactly as it does in `scan` and
    `daily`, and the command exits non-zero only when every symbol failed —
    matching the "at least one result is a true report" contract those two
    commands already hold.
    """
    reference = _reference_time(args.reference_time, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    scope = scope_from_text(account=args.account, book=args.book)
    try:
        workspace = run_today(
            args.symbols,
            reference_time=reference,
            store_root=args.store_root,
            archive_root=args.archive_root,
            read_records=not args.no_records,
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=_policy_from(args),
            detection=_detection_from(args),
            read_marks=not args.no_marks,
            mark_interval=args.mark_interval,
            sizing=sizing_policy_from_text(
                policy_id=DEFAULT_SIZING_POLICY_ID,
                risk_fraction=args.risk_fraction,
                max_equity_age=args.max_equity_age,
                max_mark_age=args.max_mark_age,
                minimum_risk_reward=args.min_risk_reward,
            ),
            account=scope[0],
            book=scope[1],
            timezone=args.timezone,
        )
    except (TodayError, *APPROVAL_ERRORS) as error:
        print(f"fmits today: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_today(workspace))
    return (
        EXIT_FAILURE
        if workspace.market.scanned == len(workspace.opportunities.failed)
        else EXIT_OK
    )


TODAY_COMMAND = Command(
    name="today",
    help="the daily trading workspace: market, capital, opportunities, warnings",
    description=(
        "Assemble one page from everything FMITS already knows: what the market "
        "is doing, what positions and capital are recorded, which setups are "
        "actionable, which deserve attention and which this system refuses to "
        "produce a number for, what has been decided and written down, and what "
        "has been durably archived. Reads the durable store and never writes to "
        "it. Nothing is ranked by desirability, no position size is computed, "
        "no probability is calibrated, and every value the workspace cannot "
        "produce is printed with its reason and the inference its absence "
        "forbids. This command executes nothing and places no orders."
    ),
    configure=_configure_today,
    run=_run_today_command,
)


def _run_workspace_command(args: argparse.Namespace) -> int:
    """Assemble and print the swing decision workspace.

    **The same flags, the same fetch, the same store read as `fmits today`.**
    `_configure_today` configures this command too, rather than a second copy of
    twelve arguments that could drift from it, and `run_swing_workspace` forwards
    every one of them to the identical composition root. The two commands
    therefore cannot disagree about what the market did or what the store holds;
    they disagree only about how the same facts are arranged.

    Reads the store; never writes to it. A symbol whose analysis failed appears
    under *could not be read* and does not stop the run, and the command exits
    non-zero only when every symbol failed — the "at least one result is a true
    report" contract `scan`, `daily` and `today` already hold.
    """
    reference = _reference_time(args.reference_time, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    scope = scope_from_text(account=args.account, book=args.book)
    try:
        workspace = run_swing_workspace(
            args.symbols,
            reference_time=reference,
            store_root=args.store_root,
            archive_root=args.archive_root,
            read_records=not args.no_records,
            timeframes={
                TimeframeRole.CONTEXT: args.context,
                TimeframeRole.SETUP: args.setup,
                TimeframeRole.EXECUTION: args.execution,
            },
            limit=args.limit,
            policy=_policy_from(args),
            detection=_detection_from(args),
            read_marks=not args.no_marks,
            mark_interval=args.mark_interval,
            sizing=sizing_policy_from_text(
                policy_id=DEFAULT_SIZING_POLICY_ID,
                risk_fraction=args.risk_fraction,
                max_equity_age=args.max_equity_age,
                max_mark_age=args.max_mark_age,
                minimum_risk_reward=args.min_risk_reward,
            ),
            account=scope[0],
            book=scope[1],
            timezone=args.timezone,
        )
    except (SwingWorkspaceError, TodayError, *APPROVAL_ERRORS) as error:
        print(f"fmits workspace: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_swing_workspace(workspace))
    return (
        EXIT_FAILURE
        if workspace.summary.scanned == workspace.summary.unanalysed
        else EXIT_OK
    )


WORKSPACE_COMMAND = Command(
    name="workspace",
    help="the swing decision workspace: one page, ordered for one decision",
    description=(
        "Assemble the operator's page from everything FMITS already knows, and "
        "order the actionable setups by a stated key rather than leaving them "
        "in scan order: readiness, then approval, then decision-context "
        "sufficiency, then watchlist position. Every component of that key is "
        "printed on the row it placed, so the reason one setup sits above "
        "another can be reconstructed without reading any code. Risk/reward, "
        "position size and evidence counts order nothing. Sections: global "
        "market summary, top opportunities, wait list, no trade, active paper "
        "trades, portfolio summary, statistics snapshot and warnings. Reads the "
        "durable store and never writes to it; computes no market quantity, no "
        "monetary quantity and no statistic. This command executes nothing and "
        "places no orders."
    ),
    configure=_configure_today,
    run=_run_workspace_command,
)


def _configure_pulse(parser: argparse.ArgumentParser) -> None:
    """Four arguments, and the default is the useful one.

    `fmits pulse` with no argument is the command the owner actually runs. Every
    flag below earns its place by answering a question the default cannot: which
    markets (a subset), which instant (replay), how old is too old (the owner's
    own bound), and where from (a test's fake endpoint).
    """
    parser.add_argument(
        "benchmarks",
        nargs="*",
        metavar="BENCHMARK",
        help=(
            "benchmark ids to read, in the order given (default: the whole "
            "configured universe). Ids, not provider symbols — e.g. BTC, not "
            "BTCUSDT"
        ),
    )
    parser.add_argument(
        "--as-of",
        default=None,
        metavar="ISO8601",
        help=(
            "the instant to describe (default: now). Bars opening after it are "
            "excluded, so supplying it makes the page reproducible"
        ),
    )
    parser.add_argument(
        "--max-age",
        default=None,
        metavar="HOURS",
        type=float,
        help=(
            "your staleness bound, in hours. With no bound every age is stated "
            "and nothing is called stale: a bound this system chose for you "
            "would be a threshold it invented"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help=argparse.SUPPRESS,
    )


def _run_pulse(args: argparse.Namespace) -> int:
    """Fetch the configured universe and print the orientation page.

    **One unavailable market never costs the page.** `run_market_pulse` isolates
    each market's provider failure onto its own row, so the exit code reflects
    whether *anything* could be read rather than whether *everything* could —
    the "at least one result is a true report" contract `scan`, `daily`, `today`
    and `workspace` already hold.
    """
    reference = _reference_time(args.as_of, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    if args.max_age is not None and args.max_age <= 0:
        print(
            "fmits pulse: --max-age must be positive; a non-positive bound "
            "marks every reading stale, including one taken this second",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    max_age = (
        None if args.max_age is None else timedelta(hours=args.max_age)
    )
    try:
        universe = (
            DEFAULT_PULSE_UNIVERSE
            if not args.benchmarks
            else universe_subset(
                DEFAULT_PULSE_UNIVERSE, tuple(args.benchmarks), name="selected"
            )
        )
        pulse = run_market_pulse(
            as_of=reference, universe=universe, base_url=args.base_url
        )
    except MarketPulseError as error:
        print(f"fmits pulse: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_market_pulse(pulse, max_age=max_age))
    return EXIT_FAILURE if pulse.is_empty else EXIT_OK


PULSE_COMMAND = Command(
    name="pulse",
    help="global market pulse: what the tracked markets are doing right now",
    description=(
        "One deterministic orientation across the configured market universe, "
        "for the question that comes before choosing an asset to study: what "
        "are these markets doing, and what can this system not tell me? Prints "
        "each market's move over named horizons, the same moves ordered by one "
        "stated quantity, measured volatility, co-movement against one named "
        "reference, every market that could not be read with its reason, and "
        "the age and provenance of every figure. Horizons are counts of closed "
        "bars, not durations, because this build holds no trading calendar. "
        "Volatility is measured and deliberately not classified. Nothing here "
        "is a view, a signal or a suggested action; no setup, plan, position "
        "or approval is read, and none is changed. This command executes "
        "nothing and places no orders."
    ),
    configure=_configure_pulse,
    run=_run_pulse,
)


def _configure_macro(parser: argparse.ArgumentParser) -> None:
    """Three arguments, and the default is the useful one.

    `fmits macro` with no argument is the command the owner actually runs. Each
    flag answers a question the default cannot: which markets (a subset), which
    instant (replay), and whether to spend the extra request the cross-asset
    section costs.
    """
    parser.add_argument(
        "benchmarks",
        nargs="*",
        metavar="BENCHMARK",
        help=(
            "benchmark ids to report, in the order given (default: every macro "
            "market). Ids, not source series — e.g. US10Y, not DGS10"
        ),
    )
    parser.add_argument(
        "--as-of",
        default=None,
        metavar="ISO8601",
        help=(
            "the instant to describe (default: now). Observations dated after "
            "it are excluded, so supplying it makes the page reproducible"
        ),
    )
    parser.add_argument(
        "--no-relationships",
        action="store_true",
        help=(
            "omit the cross-asset section. It costs one extra request for the "
            "reference market; this skips both the section and the request"
        ),
    )


def _run_macro(args: argparse.Namespace) -> int:
    """Read the macro universe and print the context page.

    **One unavailable market never costs the page.** `run_macro_context`
    isolates each market's source failure onto its own row, so the exit code
    reflects whether *anything* could be read rather than whether *everything*
    could — the same contract `pulse`, `scan`, `daily` and `workspace` hold.
    """
    reference = _reference_time(args.as_of, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    try:
        universe = (
            macro_universe()
            if not args.benchmarks
            else universe_subset(
                DEFAULT_PULSE_UNIVERSE, tuple(args.benchmarks), name="selected"
            )
        )
        report = run_macro_context(
            as_of=reference,
            universe=universe,
            with_relationships=not args.no_relationships,
        )
    except (MacroError, MarketPulseError) as error:
        print(f"fmits macro: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_macro_context(report))
    return EXIT_FAILURE if report.is_empty else EXIT_OK


MACRO_COMMAND = Command(
    name="macro",
    help="macro & cross-asset context: what the non-crypto markets are doing",
    description=(
        "One deterministic page of macro and cross-asset facts, for the "
        "question that sits behind every other one: what are equities, the "
        "dollar, yields and volatility doing, and what can this system not tell "
        "me? Prints each market's level with its unit, its move over named "
        "windows, yields as basis-point differences rather than percentage "
        "returns, measured volatility, correlations against one named reference "
        "with the alignment they required, every market that could not be read "
        "with its reason, and the age and source of every figure. Windows are "
        "counts of completed observations, not durations, because this build "
        "holds no trading calendar. Volatility is measured and deliberately not "
        "classified. Nothing here is interpretation: there is no regime, no "
        "risk-on or risk-off, no causal claim and no view. No setup, plan, "
        "position or approval is read, and none is changed. This command "
        "executes nothing and places no orders."
    ),
    configure=_configure_macro,
    run=_run_macro,
)


def _configure_portfolio(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="PATH",
        help=(
            "the durable store to read positions, plans and capital from "
            "(default: the owner's store). Read-only: this command writes "
            "nothing"
        ),
    )
    parser.add_argument(
        "--portfolio-id",
        default=DEFAULT_PORTFOLIO_ID,
        metavar="ID",
        help=(
            f"which portfolio's snapshot supplies cash and equity "
            f"(default: {DEFAULT_PORTFOLIO_ID})"
        ),
    )
    parser.add_argument(
        "--base-currency",
        default=DEFAULT_BASE_CURRENCY,
        metavar="ASSET",
        help=(
            f"what every figure is stated in (default: {DEFAULT_BASE_CURRENCY}). "
            "A holding quoted in anything else is reported as unvalued rather "
            "than converted, because this system holds no exchange rate"
        ),
    )
    parser.add_argument(
        "--mark-interval",
        default=MARK_INTERVAL,
        metavar="INTERVAL",
        help=(
            f"the timeframe a price is read from (default: {MARK_INTERVAL}). "
            "Every price is the close of the last closed candle on it; a "
            "forming bar is never read"
        ),
    )
    parser.add_argument(
        "--no-marks",
        action="store_true",
        help=(
            "do not fetch any price. The page still renders, and every figure "
            "that needed one says so with the reason"
        ),
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        metavar="ISO8601",
        help=(
            "the instant this reading describes (default: now). Supply it to "
            "make a valuation reproducible."
        ),
    )


def _run_portfolio_command(args: argparse.Namespace) -> int:
    """Value the recorded portfolio at current marks and print it.

    Reads the store; never writes to it. A market whose price could not be
    fetched leaves its position unmarked and every total that depended on it
    unavailable-with-a-reason — the run does not fail, because a portfolio page
    that vanishes when one symbol is unreachable is a page the owner learns not
    to rely on.
    """
    reference = _reference_time(args.reference_time, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    try:
        valuation = run_valuation(
            args.store_root,
            as_of=reference,
            portfolio_id=args.portfolio_id,
            base_currency=args.base_currency,
            read_marks=not args.no_marks,
            interval=args.mark_interval,
        )
    except ValuationError as error:
        print(f"fmits portfolio: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_valuation(valuation))
    return EXIT_OK


PORTFOLIO_COMMAND = Command(
    name="portfolio",
    help="value the recorded portfolio at current marks",
    description=(
        "What the recorded positions are worth right now, what they cost, what "
        "is unrealized, what is exposed and what is at risk — each figure "
        "computed from the close of the last closed candle on a stated "
        "timeframe, with the price source, the selection rule and the age of "
        "every mark printed beside it. A market with no price leaves its "
        "position unmarked and every total that depended on it unavailable "
        "with the reason, never a smaller number that looks complete. Reads "
        "the durable store and never writes to it. Nothing is stored, nothing "
        "is ranked, no position size is proposed and no order is placed."
    ),
    configure=_configure_portfolio,
    run=_run_portfolio_command,
)


def _configure_approve(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbol",
        nargs="?",
        default=None,
        metavar="SYMBOL",
        help=(
            "the market to evaluate, e.g. BTCUSDT. Omit it and pass --plan to "
            "size a commitment already recorded with `fmits trade record`"
        ),
    )
    parser.add_argument(
        "--plan",
        default=None,
        metavar="PLAN_ID",
        help=(
            "size a recorded commitment instead of a typed one. The market, "
            "book, side, stop and targets are read from it and cannot be "
            "overridden — a plan's stop is the field it exists to keep immutable"
        ),
    )
    parser.add_argument(
        "--direction",
        default=None,
        choices=DIRECTION_CHOICES,
        help="which side the candidate is on (required unless --plan is used)",
    )
    parser.add_argument(
        "--entry",
        required=True,
        metavar="PRICE",
        help=(
            "the price the owner intends to transact at. Not an order: nothing "
            "here is placed, and the setup engine fabricates no exact entry"
        ),
    )
    parser.add_argument(
        "--stop",
        default=None,
        metavar="PRICE",
        help=(
            "the level that ends the trade (required unless --plan is used). "
            "There is no size without one: no stop means no risk denominator"
        ),
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        metavar="PRICE",
        dest="targets",
        help="a target, nearest first. Repeat for a ladder. Optional",
    )
    parser.add_argument(
        "--account",
        default=None,
        metavar="ID",
        help=(
            "which account this candidate consumes capacity in (default: the "
            "only account the store records fills in, refused when there are "
            "several — books never share capacity across accounts)"
        ),
    )
    parser.add_argument(
        "--book",
        default=DEFAULT_BOOK.value,
        choices=BOOK_CHOICES,
        help=f"which capacity pool this candidate belongs to (default: {DEFAULT_BOOK.value})",
    )
    parser.add_argument(
        "--risk-fraction",
        default=None,
        metavar="FRACTION",
        help=(
            "the fraction of equity to risk on this trade, e.g. 0.01 for 1 %%. "
            "Omit it and the default the owner set below their per-trade ceiling "
            "is used; with neither, no size is produced and the page says so — "
            "a ceiling is not a target and is never used as one"
        ),
    )
    parser.add_argument(
        "--min-risk-reward",
        default=None,
        metavar="RATIO",
        help=(
            "warn when the planned reward-to-risk ratio is below this. A "
            "warning and never a block: the size comes from the risk rule and "
            "the stop distance, never from the quality of the idea"
        ),
    )
    parser.add_argument(
        "--max-equity-age",
        default=None,
        metavar="DURATION",
        help=(
            "block when the recorded equity is older than this, e.g. 7d. With "
            "no bound the age is reported and not judged — a staleness bound is "
            "a policy and this system sets none on the owner's behalf"
        ),
    )
    parser.add_argument(
        "--max-mark-age",
        default=None,
        metavar="DURATION",
        help="block when the oldest price behind the exposure figures is older than this, e.g. 36h",
    )
    parser.add_argument(
        "--venue", default=DEFAULT_VENUE, metavar="NAME",
        help=f"which venue the market trades at (default: {DEFAULT_VENUE})",
    )
    parser.add_argument(
        "--quote", default=DEFAULT_QUOTE_ASSET, metavar="ASSET",
        help=(
            f"the quote asset the symbol ends in (default: {DEFAULT_QUOTE_ASSET}). "
            "FMITS holds no asset registry and will not guess the split"
        ),
    )
    parser.add_argument(
        "--mode", default=DEFAULT_MARKET_MODE, choices=MARKET_MODE_CHOICES,
        help=f"the market's mode (default: {DEFAULT_MARKET_MODE})",
    )
    parser.add_argument(
        "--store-root", default=None, metavar="PATH",
        help=(
            "the durable store to read positions, plans, capital and limits "
            "from (default: the owner's store). Read-only: this command writes "
            "nothing and places nothing"
        ),
    )
    parser.add_argument(
        "--portfolio-id", default=DEFAULT_PORTFOLIO_ID, metavar="ID",
        help=f"which portfolio's snapshot supplies cash and equity (default: {DEFAULT_PORTFOLIO_ID})",
    )
    parser.add_argument(
        "--base-currency", default=DEFAULT_BASE_CURRENCY, metavar="ASSET",
        help=f"what every figure is stated in (default: {DEFAULT_BASE_CURRENCY})",
    )
    parser.add_argument(
        "--timezone", default=DEFAULT_OWNER_TIMEZONE, metavar="ZONE",
        help=(
            f"the owner's calendar, for periodic limit boundaries (default: "
            f"{DEFAULT_OWNER_TIMEZONE}). A locale, never a threshold"
        ),
    )
    parser.add_argument(
        "--mark-interval", default=MARK_INTERVAL, metavar="INTERVAL",
        help=f"the timeframe a holding's price is read from (default: {MARK_INTERVAL})",
    )
    parser.add_argument(
        "--no-marks", action="store_true",
        help=(
            "fetch no price. The evaluation still runs and comes back "
            "INDETERMINATE, naming every position that could not be priced"
        ),
    )
    parser.add_argument(
        "--reference-time", default=None, metavar="ISO8601",
        help=(
            "the instant this evaluation describes (default: now). Supply it to "
            "make an approval reproducible."
        ),
    )


def _proposal_from(args: argparse.Namespace) -> object:
    """The candidate, typed or read from a recorded commitment.

    Every conversion happens behind `fmis.position_sizing.inputs`; this function
    only decides which of the two doors to knock on, so the CLI still constructs
    no domain value of its own.
    """
    account = resolve_account(args.store_root, stated=args.account)
    if args.plan is not None:
        if args.symbol is not None or args.direction is not None or args.stop is not None:
            raise ValueError(
                "--plan reads the market, the side and the stop from the recorded "
                "commitment; passing them again would let a sizing call restate a "
                "stop the plan exists to keep immutable"
            )
        return proposal_for_plan(
            args.store_root,
            plan_id=args.plan,
            account=account,
            entry=price_from_text(args.entry, "--entry"),
        )
    missing = [
        name
        for name, value in (
            ("SYMBOL", args.symbol),
            ("--direction", args.direction),
            ("--stop", args.stop),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"{', '.join(missing)} is required unless --plan names a recorded "
            "commitment to read them from"
        )
    return proposal_from_text(
        symbol=args.symbol,
        direction=args.direction,
        account=account.value,
        book=args.book,
        entry=args.entry,
        stop=args.stop,
        targets=args.targets,
        venue=args.venue,
        quote=args.quote,
        mode=args.mode,
    )


def _run_approve(args: argparse.Namespace) -> int:
    """Size a candidate and check it against the owner's own limits.

    Reads the store; never writes to it, and never places anything. A `BLOCKED`
    result exits **0**: the evaluation succeeded and its answer was no, which is
    a first-class successful outcome in this product exactly as `WAIT` is. A
    non-zero code means the evaluation could not be produced at all.
    """
    reference = _reference_time(args.reference_time, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    try:
        result = run_approval(
            args.store_root,
            proposal=_proposal_from(args),  # type: ignore[arg-type]
            as_of=reference,
            policy=sizing_policy_from_text(
                policy_id=DEFAULT_SIZING_POLICY_ID,
                risk_fraction=args.risk_fraction,
                max_equity_age=args.max_equity_age,
                max_mark_age=args.max_mark_age,
                minimum_risk_reward=args.min_risk_reward,
            ),
            portfolio_id=args.portfolio_id,
            base_currency=args.base_currency,
            timezone=args.timezone,
            read_marks=not args.no_marks,
            interval=args.mark_interval,
        )
    except (*APPROVAL_ERRORS, ValuationError) as error:
        print(f"fmits approve: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_approval(result))
    return EXIT_OK


APPROVE_COMMAND = Command(
    name="approve",
    help="how large this position may be, and whether your own limits permit it",
    description=(
        "Answers 'can I take this trade' — never 'is this setup good'. Computes "
        "the largest position whose capital at risk stays inside the fraction of "
        "equity the owner chose and every ceiling they set, then evaluates the "
        "portfolio as it would be with that position open: total open risk, "
        "instrument, asset, account and group concentration, leverage, "
        "concurrent positions and reserve. Returns APPROVED, BLOCKED or "
        "INDETERMINATE with every reason named, and never a recommendation to "
        "take or skip anything — that is the owner's conclusion. Every threshold "
        "is one the owner set; this command invents none. Reads the durable "
        "store and never writes to it. Nothing is stored, nothing is ranked, no "
        "probability is calibrated, no order is placed and no venue is reached "
        "for execution. A BLOCKED answer exits 0: the evaluation succeeded."
    ),
    configure=_configure_approve,
    run=_run_approve,
)


def _add_store_arguments(parser: argparse.ArgumentParser) -> None:
    """The store root and the filing instant — every `trade` subcommand takes both."""
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="PATH",
        help=f"the durable store to use (default: {capture_store_root()})",
    )
    parser.add_argument(
        "--author",
        default="owner",
        metavar="NAME",
        help=(
            "who asserts this. FMITS has exactly one owner, so this defaults to "
            "'owner'; a record with no author is unattributable"
        ),
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        metavar="ISO8601",
        help=(
            "the instant the write is filed at (default: now). Supply it to make "
            "a capture reproducible."
        ),
    )


def _add_fill_arguments(parser: argparse.ArgumentParser, *, price_flag: str) -> None:
    """The fields a fill needs. Shared by `record` and `close`, defined once.

    The FX arguments are **required** and that is not an oversight. `AP` §22.2
    item 10 — the rate to the tax currency at the transaction instant — is
    unrecoverable retroactively, so a trade recorded without it is permanently
    untaxable. The domain refuses to build one; this asks for it up front rather
    than failing after the owner has typed everything else.
    """
    parser.add_argument(price_flag, required=True, metavar="PRICE", help="the fill price")
    parser.add_argument(
        "--fee", required=True, metavar="AMOUNT", help="the fee paid on this fill"
    )
    parser.add_argument(
        "--fee-asset",
        default=None,
        metavar="ASSET",
        help="the asset the fee was paid in (default: the market's quote asset)",
    )
    parser.add_argument(
        "--fee-fx-rate",
        default=None,
        metavar="RATE",
        help=(
            "rate to the tax currency for a fee paid in a third asset. Required "
            "only then: such a fee is its own disposal"
        ),
    )
    parser.add_argument(
        "--fx-rate",
        required=True,
        metavar="RATE",
        help=(
            "rate from the quote asset to the tax currency at the fill instant. "
            "Required, and unrecoverable later — a trade without it is "
            "permanently untaxable"
        ),
    )
    parser.add_argument(
        "--fx-source", required=True, metavar="NAME", help="where the rate came from"
    )
    parser.add_argument(
        "--fx-timestamp",
        default=None,
        metavar="ISO8601",
        help="when the rate was read (default: the fill's own instant)",
    )
    parser.add_argument(
        "--occurred-at",
        default=None,
        metavar="ISO8601",
        help="when the fill happened (default: the reference time)",
    )


def _configure_trade(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="trade_command", required=True)

    record = subcommands.add_parser(
        "record",
        help="record a swing trade: the commitment, the entry fill and the thesis",
        description=(
            "Record one swing trade the owner has already entered. Writes three "
            "records through the durable store: a TradePlan holding the stop, the "
            "targets and the stated confidence; a Trade holding the entry fill; "
            "and, when a thesis is given, a JournalEntry holding it. Nothing is "
            "executed, no order is placed and no exchange is contacted. Every "
            "value is validated before anything is written, nothing is silently "
            "corrected, and re-running the identical command records nothing "
            "twice."
        ),
    )
    record.add_argument("symbol", metavar="SYMBOL", help="the pair, e.g. BTCUSDT")
    record.add_argument(
        "--direction",
        required=True,
        choices=DIRECTION_CHOICES,
        help="which side the commitment came down on",
    )
    record.add_argument(
        "--account",
        required=True,
        metavar="ID",
        help="the account the fill sits in. Never inferred",
    )
    record.add_argument(
        "--book",
        required=True,
        choices=BOOK_CHOICES,
        help=(
            "which discipline this belongs to. Books never share capacity and a "
            "book is never inferred, so there is no default"
        ),
    )
    record.add_argument(
        "--stop",
        required=True,
        metavar="PRICE",
        help=(
            "the initial invalidation. Required: a plan with no stop cannot be "
            "sized, and this value can never change afterwards"
        ),
    )
    record.add_argument(
        "--target",
        action="append",
        default=None,
        metavar="PRICE",
        dest="targets",
        help="repeatable, stated nearest first",
    )
    record.add_argument(
        "--size", required=True, metavar="QUANTITY", help="the base-asset quantity filled"
    )
    record.add_argument(
        "--confidence",
        required=True,
        metavar="LABEL",
        help=(
            "the owner's own word for how sure they are. A numeric-looking label "
            "is refused: confidence is not a probability"
        ),
    )
    _add_fill_arguments(record, price_flag="--entry")
    record.add_argument(
        "--setup", default=None, metavar="TERM", help="the originating setup type"
    )
    record.add_argument(
        "--proposal", default=None, metavar="RECORD_ID", help="the proposal this came from"
    )
    record.add_argument(
        "--snapshot", default=None, metavar="RECORD_ID", help="the MarketSnapshot it rests on"
    )
    record.add_argument(
        "--analysis",
        action="append",
        default=None,
        metavar="RECORD_ID",
        help="repeatable: an archived analysis page this decision read",
    )
    record.add_argument(
        "--committed-at",
        default=None,
        metavar="ISO8601",
        help="when the commitment was made (default: the fill's instant)",
    )
    record.add_argument(
        "--expires", default=None, metavar="ISO8601", help="when the commitment lapses"
    )
    record.add_argument("--thesis", default=None, metavar="TEXT", help="why this trade")
    record.add_argument(
        "--note", default=None, metavar="TEXT", help="an annotation on the commitment"
    )
    record.add_argument(
        "--venue", default=DEFAULT_VENUE, metavar="NAME", help=f"(default: {DEFAULT_VENUE})"
    )
    record.add_argument(
        "--quote",
        default=DEFAULT_QUOTE_ASSET,
        metavar="ASSET",
        help=(
            f"the quote asset of SYMBOL (default: {DEFAULT_QUOTE_ASSET}). FMITS "
            "holds no asset registry and will not guess where the base ends"
        ),
    )
    record.add_argument(
        "--mode",
        default=DEFAULT_MARKET_MODE,
        choices=MARKET_MODE_CHOICES,
        help=f"(default: {DEFAULT_MARKET_MODE})",
    )
    _add_store_arguments(record)

    show = subcommands.add_parser(
        "show",
        help="show one recorded trade: commitment, fills, position, journal",
        description=(
            "Assemble one recorded swing trade from the commitment, the resolved "
            "ledger and the journal, and print it. Reads the store and writes "
            "nothing. Capital at risk and risk/reward are arithmetic over the "
            "records and are shown with the arithmetic that produced them."
        ),
    )
    show.add_argument("plan_id", metavar="TRADE_ID")
    _add_store_arguments(show)

    listing = subcommands.add_parser(
        "list",
        help="list recorded trades, with filters",
        description=(
            "One row per recorded commitment, ordered by when it was made. Not a "
            "ranking: nothing is sorted by size, profit or quality. The filters "
            "applied and the number of rows excluded by them are printed with the "
            "listing, so a filtered page can never read as the whole store."
        ),
    )
    listing.add_argument("--status", default=None, choices=STATUS_CHOICES)
    listing.add_argument("--symbol", default=None, metavar="SYMBOL")
    listing.add_argument("--account", default=None, metavar="ID")
    listing.add_argument("--direction", default=None, choices=DIRECTION_CHOICES)
    listing.add_argument(
        "--since", default=None, metavar="ISO8601", help="commitments made at or after"
    )
    listing.add_argument(
        "--until", default=None, metavar="ISO8601", help="commitments made at or before"
    )
    _add_store_arguments(listing)

    note = subcommands.add_parser(
        "note",
        help="append a note to a recorded trade",
        description=(
            "Append one journal entry to a recorded trade. Append-only: there is "
            "no edit path and there never will be. What the owner first wrote is "
            "frequently the more interesting record, and a store that let a "
            "second note overwrite the first would destroy the only evidence of "
            "which it was."
        ),
    )
    note.add_argument("plan_id", metavar="TRADE_ID")
    note.add_argument("--body", required=True, metavar="TEXT")
    note.add_argument("--title", default=None, metavar="TEXT")
    note.add_argument(
        "--recorded-at",
        default=None,
        metavar="ISO8601",
        help="when the note was written (default: the reference time)",
    )
    _add_store_arguments(note)

    close = subcommands.add_parser(
        "close",
        help="record an exit against a recorded trade",
        description=(
            "Append an exit fill and the reason for it. Nothing already stored "
            "changes: the entry, the commitment and every note stay byte-"
            "identical, and 'closing' is one more Trade in the other direction — "
            "which is what actually happened, and why the realized profit or loss "
            "printed afterwards is a fold rather than a figure anyone typed. A "
            "reason from the owner's exit vocabulary is required."
        ),
    )
    close.add_argument("plan_id", metavar="TRADE_ID")
    close.add_argument(
        "--reason",
        required=True,
        metavar="TERM",
        help=(
            "why the trade was exited, from the owner's own vocabulary. Required: "
            "the reason is the field that makes exits analysable"
        ),
    )
    close.add_argument(
        "--size",
        default=None,
        metavar="QUANTITY",
        help="how much was closed (default: the whole open position)",
    )
    close.add_argument(
        "--account",
        default=None,
        metavar="ID",
        help="required only when the fills sit in more than one account",
    )
    close.add_argument("--note", default=None, metavar="TEXT")
    _add_fill_arguments(close, price_flag="--price")
    _add_store_arguments(close)

    plan = subcommands.add_parser(
        "plan",
        help="record a commitment with no fill — a stop, targets and confidence",
        description=(
            "Record what the owner intends before they act: a market, a side, a "
            "stop, an optional target ladder and a stated confidence. Writes one "
            "TradePlan and, when a thesis is given, one JournalEntry. No fill, no "
            "position and no money — this is the commitment `fmits trade "
            "activate` hands to the paper simulator."
        ),
    )
    plan.add_argument("symbol", metavar="SYMBOL", help="the pair, e.g. BTCUSDT")
    plan.add_argument("--direction", required=True, choices=DIRECTION_CHOICES)
    plan.add_argument("--book", required=True, choices=BOOK_CHOICES)
    plan.add_argument("--stop", required=True, metavar="PRICE")
    plan.add_argument(
        "--target", dest="targets", action="append", default=None, metavar="PRICE",
        help="stated nearest first; repeatable",
    )
    plan.add_argument(
        "--confidence", required=True, metavar="LABEL",
        help="the owner's own scale. Explicitly not a probability",
    )
    plan.add_argument("--committed-at", default=None, metavar="ISO8601")
    plan.add_argument("--expires", default=None, metavar="ISO8601")
    plan.add_argument("--setup", default=None, metavar="TERM")
    plan.add_argument("--proposal", default=None, metavar="ID")
    plan.add_argument("--snapshot", default=None, metavar="ID")
    plan.add_argument("--analysis", action="append", default=None, metavar="ID")
    plan.add_argument("--thesis", default=None, metavar="TEXT")
    plan.add_argument("--note", default=None, metavar="TEXT")
    plan.add_argument("--venue", default=DEFAULT_VENUE, metavar="NAME")
    plan.add_argument("--quote", default=DEFAULT_QUOTE_ASSET, metavar="ASSET")
    plan.add_argument(
        "--mode", default=DEFAULT_MARKET_MODE, choices=MARKET_MODE_CHOICES
    )
    _add_store_arguments(plan)

    activate = subcommands.add_parser(
        "activate",
        help="hand a recorded commitment to the paper simulator",
        description=(
            "Create a TradeActivation: the size, the entry type, the exit ladder "
            "and the stop rules the simulator will run this commitment under. "
            "Writes one activation and one journal entry. Nothing is executed, no "
            "order is placed and no exchange is contacted — `fmits simulate` "
            "advances it over closed candles."
        ),
    )
    activate.add_argument("plan_id", metavar="TRADE_ID")
    activate.add_argument("--size", required=True, metavar="QTY")
    activate.add_argument(
        "--entry-type", required=True, choices=ENTRY_TYPE_CHOICES,
        help="market fills at the next bar's open; the other two wait for a level",
    )
    activate.add_argument(
        "--entry", default=None, metavar="PRICE",
        help="required for a limit or stop-entry, and refused for a market entry",
    )
    activate.add_argument(
        "--share", dest="fractions", action="append", default=None, metavar="FRACTION",
        help=(
            "the share of the activated size taken at each target, nearest first. "
            "Repeatable. When none is given the whole position exits at the first "
            "target and the page says so"
        ),
    )
    activate.add_argument(
        "--account", default=None, metavar="ID",
        help="which account the simulated fills sit in (default: paper)",
    )
    activate.add_argument(
        "--interval", default=SIMULATION_INTERVAL, metavar="TF",
        help=f"the timeframe the simulation advances on (default: {SIMULATION_INTERVAL})",
    )
    activate.add_argument("--break-even-r", default=None, metavar="R")
    activate.add_argument("--break-even-offset-r", default=None, metavar="R")
    activate.add_argument("--trail-r", default=None, metavar="R")
    activate.add_argument("--trail-start-r", default=None, metavar="R")
    activate.add_argument("--expires", default=None, metavar="ISO8601")
    activate.add_argument("--activated-at", default=None, metavar="ISO8601")
    activate.add_argument("--note", default=None, metavar="TEXT")
    activate.add_argument("--quote", default=DEFAULT_QUOTE_ASSET, metavar="ASSET")
    _add_store_arguments(activate)

    stop = subcommands.add_parser(
        "stop",
        help="move a simulated trade's stop, append-only, with a reason",
        description=(
            "Append a StopAmendment. The TradePlan is never touched: "
            "initial_invalidation stays what was committed to forever, and what "
            "moves is the fold. A widening is recorded as a widening and counted "
            "as one, which is why a reason is required rather than optional."
        ),
    )
    stop.add_argument("activation_id", metavar="ACTIVATION_ID")
    stop.add_argument("--to", dest="new_stop", required=True, metavar="PRICE")
    stop.add_argument(
        "--reason", required=True, metavar="TERM",
        help=(
            "the owner's own term. Suggested: "
            + ", ".join(AMENDMENT_REASON_SUGGESTIONS)
        ),
    )
    stop.add_argument("--occurred-at", default=None, metavar="ISO8601")
    stop.add_argument("--note", default=None, metavar="TEXT")
    _add_store_arguments(stop)

    cancel = subcommands.add_parser(
        "cancel",
        help="withdraw an activation before anything has filled",
        description=(
            "Append a CANCELLED lifecycle event. Legal only while nothing has "
            "filled: the lifecycle table decides that, so cancelling an open "
            "position raises rather than quietly abandoning a fill the ledger "
            "already holds."
        ),
    )
    cancel.add_argument("activation_id", metavar="ACTIVATION_ID")
    cancel.add_argument("--reason", required=True, metavar="TERM")
    cancel.add_argument("--occurred-at", default=None, metavar="ISO8601")
    cancel.add_argument("--note", default=None, metavar="TEXT")
    _add_store_arguments(cancel)

    status = subcommands.add_parser(
        "status",
        help="every simulated trade still running, with its monitoring block",
        description=(
            "Pending, triggered, open and partially exited paper trades, each with "
            "remaining size, realized and unrealized R, distance to stop and "
            "target, holding time and the stop's own history. Reads the store and "
            "writes nothing."
        ),
    )
    status.add_argument("--symbol", default=None, metavar="SYMBOL")
    status.add_argument(
        "--offline",
        action="store_true",
        help=(
            "read the store only. Every excursion, mark and bar count then "
            "comes back absent with its reason, because each one needs a candle"
        ),
    )
    _add_store_arguments(status)

    history = subcommands.add_parser(
        "history",
        help="every finished simulated trade, with its frozen outcome",
        description=(
            "One block per finished trade: the exit reason, the entry and exit, "
            "the profit and loss, the final R, the excursions and the holding "
            "time. The excursions were frozen when the trade ended, because kline "
            "history is not permanent."
        ),
    )
    history.add_argument("--symbol", default=None, metavar="SYMBOL")
    _add_store_arguments(history)

    lifecycle = subcommands.add_parser(
        "lifecycle",
        help="one simulated trade's complete event stream and stop history",
        description=(
            "Every lifecycle event, every stop move with who made it and why, "
            "every fill, the monitoring block and the outcome. The state is folded "
            "from the stream on every read and is stored nowhere."
        ),
    )
    lifecycle.add_argument("activation_id", metavar="ACTIVATION_ID")
    lifecycle.add_argument(
        "--offline",
        action="store_true",
        help="read the store only; see `fmits trade status --offline`",
    )
    _add_store_arguments(lifecycle)


def _record_request(args: argparse.Namespace, *, filed_at: datetime) -> object:
    """Hand every string straight to the capture layer, converting nothing here.

    `fmis.pipeline` is a market-half package and may not reach the trading domain
    or the store — Milestone BJ's rule, enforced by a guard test, and this
    milestone keeps it. So the CLI never builds an `AccountId`, never parses an
    amount and never opens a store: `fmis.trade_capture.inputs` does all three,
    where they can be tested without a parser.
    """
    return record_request_from_text(
        symbol=args.symbol,
        direction=args.direction,
        account=args.account,
        book=args.book,
        entry=args.entry,
        stop=args.stop,
        size=args.size,
        fee=args.fee,
        fx_rate=args.fx_rate,
        fx_source=args.fx_source,
        confidence=args.confidence,
        author=args.author,
        filed_at=filed_at,
        targets=args.targets,
        fee_asset=args.fee_asset,
        fee_fx_rate=args.fee_fx_rate,
        fx_timestamp=args.fx_timestamp,
        occurred_at=args.occurred_at,
        committed_at=args.committed_at,
        expires=args.expires,
        setup=args.setup,
        proposal=args.proposal,
        snapshot=args.snapshot,
        analysis=args.analysis,
        thesis=args.thesis,
        note=args.note,
        venue=args.venue,
        quote=args.quote,
        mode=args.mode,
    )


#: The lifecycle states `fmits trade status` shows. Named here rather than
#: derived from `LIVE_LIFECYCLE_STATES`, because the page's question is *"what is
#: still running"* and a halted trade belongs on it — it is waiting for the owner
#: rather than for a bar, which is exactly what the page exists to surface.
_LIVE_STATE_NAMES: tuple[str, ...] = (
    "pending",
    "triggered",
    "open",
    "partially_exited",
    "ambiguous",
)


def _market_of(store: object, activation_id: str) -> str:
    """The provider symbol one activation trades, for the fetch below."""
    return store.activations.load(activation_id).market.pair_symbol


def _monitoring_bars(
    store: object, args: argparse.Namespace
) -> dict[str, tuple[object, ...]]:
    """Closed candles for every market with a live paper trade, or none.

    **The monitoring block is the reason this fetch exists.** The milestone
    brief asks a position monitor for maximum favourable and adverse excursion,
    bars in trade and distance to stop, and every one of them needs a candle:
    without one the page can only say *"no bar has been observed"*, which is
    honest and useless. `--offline` keeps the store-only reading for a run with
    no network, and the page then says so figure by figure.

    A fetch failure is **not** an error here. The page still renders from the
    store, with the excursions absent and their reason printed — the same
    degradation `fmits today` already applies when no mark source answers.
    """
    if getattr(args, "offline", False):
        return {}
    markets = sorted(
        {
            activation.market.pair_symbol
            for activation, _ in store.activations.live_activations()
        }
    )
    if not markets:
        return {}
    fetched = fetch_simulation_candles(markets, interval=SIMULATION_INTERVAL)
    return {
        symbol: bars_from_series(series)
        for symbol, series in fetched.series.items()
    }


def _dispatch_trade(args: argparse.Namespace, *, filed_at: datetime) -> str:
    """Run one `trade` subcommand and return the page it produced.

    Returning the text rather than printing it keeps the failure boundary in one
    place: every refusal below raises, and `_run_trade` is the only thing that
    decides an exit code.
    """
    store = open_store(args.store_root)
    if args.trade_command == "record":
        return render_outcome(
            record_trade(store, _record_request(args, filed_at=filed_at))
        )
    if args.trade_command == "show":
        return render_trade(
            load_trade(store, args.plan_id, dust=CAPTURE_DUST_POLICY, at=filed_at)
        )
    if args.trade_command == "list":
        return render_listing(
            list_trades(
                store,
                dust=CAPTURE_DUST_POLICY,
                at=filed_at,
                filters=filters_from_text(
                    status=args.status,
                    symbol=args.symbol,
                    account=args.account,
                    direction=args.direction,
                    since=args.since,
                    until=args.until,
                ),
            )
        )
    if args.trade_command == "note":
        return render_outcome(
            append_note(
                store,
                note_request_from_text(
                    plan_id=args.plan_id,
                    body=args.body,
                    author=args.author,
                    filed_at=filed_at,
                    title=args.title,
                    recorded_at=args.recorded_at,
                ),
            )
        )
    if args.trade_command == "close":
        return render_outcome(
            close_trade(
                store,
                close_request_from_text(
                    store,
                    plan_id=args.plan_id,
                    price=args.price,
                    fee=args.fee,
                    fx_rate=args.fx_rate,
                    fx_source=args.fx_source,
                    reason=args.reason,
                    author=args.author,
                    filed_at=filed_at,
                    size=args.size,
                    account=args.account,
                    fee_asset=args.fee_asset,
                    fee_fx_rate=args.fee_fx_rate,
                    fx_timestamp=args.fx_timestamp,
                    occurred_at=args.occurred_at,
                    note=args.note,
                ),
            )
        )
    if args.trade_command == "plan":
        return render_outcome(
            record_plan(
                store,
                plan_request_from_text(
                    symbol=args.symbol,
                    direction=args.direction,
                    book=args.book,
                    stop=args.stop,
                    confidence=args.confidence,
                    author=args.author,
                    filed_at=filed_at,
                    targets=args.targets,
                    committed_at=args.committed_at,
                    expires=args.expires,
                    setup=args.setup,
                    proposal=args.proposal,
                    snapshot=args.snapshot,
                    analysis=args.analysis,
                    thesis=args.thesis,
                    note=args.note,
                    venue=args.venue,
                    quote=args.quote,
                    mode=args.mode,
                ),
            )
        )
    if args.trade_command == "activate":
        return render_activation(
            activate_trade(
                store,
                activate_request_from_text(
                    store,
                    plan_id=args.plan_id,
                    size=args.size,
                    entry_type=args.entry_type,
                    interval=args.interval,
                    filed_at=filed_at,
                    account=args.account,
                    entry=args.entry,
                    fractions=args.fractions,
                    break_even_r=args.break_even_r,
                    break_even_offset_r=args.break_even_offset_r,
                    trail_r=args.trail_r,
                    trail_start_r=args.trail_start_r,
                    expires=args.expires,
                    activated_at=args.activated_at,
                    note=args.note,
                ),
            )
        )
    if args.trade_command == "stop":
        return render_activation(
            amend_stop(
                store,
                amend_request_from_text(
                    activation_id=args.activation_id,
                    new_stop=args.new_stop,
                    reason=args.reason,
                    author=args.author,
                    filed_at=filed_at,
                    occurred_at=args.occurred_at,
                    note=args.note,
                ),
            )
        )
    if args.trade_command == "cancel":
        return render_activation(
            cancel_activation(
                store,
                cancel_request_from_text(
                    activation_id=args.activation_id,
                    reason=args.reason,
                    author=args.author,
                    filed_at=filed_at,
                    occurred_at=args.occurred_at,
                    note=args.note,
                ),
            )
        )
    if args.trade_command == "status":
        return render_status(
            list_paper_trades(
                store,
                dust=PAPER_DUST_POLICY,
                at=filed_at,
                states=states_from_text(_LIVE_STATE_NAMES),
                market=args.symbol,
                bars_by_symbol=_monitoring_bars(store, args),
            )
        )
    if args.trade_command == "history":
        return render_history(
            list_paper_trades(
                store,
                dust=PAPER_DUST_POLICY,
                at=filed_at,
                states=states_from_text(("resolved",)),
                market=args.symbol,
            )
        )
    if args.trade_command == "lifecycle":
        return render_lifecycle(
            load_paper_trade(
                store,
                args.activation_id,
                dust=PAPER_DUST_POLICY,
                at=filed_at,
                bars=_monitoring_bars(store, args).get(
                    _market_of(store, args.activation_id), ()
                ),
            )
        )
    raise AssertionError(f"unreachable trade_command {args.trade_command!r}")


def _run_trade(args: argparse.Namespace) -> int:
    """Capture or read one recorded trade.

    A refusal is not a crash and is reported as neither: `CaptureRefusedError`
    names the two values that disagree and exits non-zero, so a script can tell
    "FMITS would not record that" from "FMITS broke".
    """
    filed_at = _reference_time(args.reference_time, omit=False)
    assert filed_at is not None  # `omit=False` always yields an instant
    try:
        print(_dispatch_trade(args, filed_at=filed_at))
    except CAPTURE_ERRORS as error:
        print(f"fmits trade: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK


TRADE_COMMAND = Command(
    name="trade",
    help="record, read and close the owner's own swing trades",
    description=(
        "The system of record for what the owner decided and did. `record` "
        "captures a commitment — direction, stop, targets, size, confidence, the "
        "setup and the analysis it came from — together with the entry fill and "
        "the thesis behind it. `show` and `list` read them back. `note` appends "
        "to a trade's journal and `close` appends an exit with its reason. "
        "Everything is append-only: nothing already recorded is ever edited or "
        "deleted, a mistake is corrected by a later record that supersedes the "
        "first, and both stay readable forever. FMITS places no order, contacts "
        "no exchange and executes nothing; the owner remains the trader."
    ),
    configure=_configure_trade,
    run=_run_trade,
)


def _configure_simulate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "symbols",
        nargs="*",
        metavar="SYMBOL",
        help=(
            "the markets to advance. With none and without --all, every market "
            "holding a live activation is advanced"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "advance every live activation. The default already does this; the "
            "flag exists so a script can say so explicitly and so naming symbols "
            "and asking for all at once is a usage error rather than a silent "
            "preference"
        ),
    )
    parser.add_argument(
        "--interval",
        default=SIMULATION_INTERVAL,
        metavar="TF",
        help=f"the timeframe to advance on (default: {SIMULATION_INTERVAL})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=SIMULATION_CANDLE_LIMIT,
        metavar="N",
        help=f"closed candles to request per market (default: {SIMULATION_CANDLE_LIMIT})",
    )
    _add_store_arguments(parser)


def _run_simulate(args: argparse.Namespace) -> int:
    """Advance every live paper trade over the closed candles fetched for it.

    The fetch is isolated per symbol and the simulation is not: a market the
    provider could not serve becomes a row on the page, and a defect inside FMITS
    propagates rather than being reported as *"this market could not be
    simulated"*.
    """
    if args.symbols and args.all:
        print(
            "fmits simulate: name markets or pass --all, not both. Asking for "
            "specific markets and for everything at once has no reading",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    filed_at = _reference_time(args.reference_time, omit=False)
    assert filed_at is not None  # `omit=False` always yields an instant
    try:
        store = open_store(args.store_root)
        wanted = tuple(symbol.upper() for symbol in args.symbols)
        markets = sorted(
            {
                activation.market.pair_symbol
                for activation, _ in store.activations.live_activations()
                if not wanted or activation.market.pair_symbol.upper() in wanted
            }
        )
        fetched = fetch_simulation_candles(
            markets, interval=args.interval, limit=args.limit
        )
        print(
            render_simulation(
                run_simulation(
                    store,
                    ran_at=filed_at,
                    code_version=fmis.__version__,
                    interval=args.interval,
                    bars_by_symbol={
                        symbol: bars_from_series(series)
                        for symbol, series in fetched.series.items()
                    },
                    failures=dict(fetched.failures),
                    markets=wanted,
                )
            )
        )
    except PAPER_ERRORS as error:
        print(f"fmits simulate: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    return EXIT_OK


SIMULATE_COMMAND = Command(
    name="simulate",
    help="advance every paper trade over newly closed candles",
    description=(
        "The paper execution engine. Replays each live activation from the "
        "moment it was activated, one closed candle at a time, and records what "
        "happened: the entry trigger and its fill, every partial exit, every stop "
        "the owner's rules moved, the close, and the outcome frozen at the "
        "instant it ended. Deterministic — no randomness, no model, no "
        "prediction, and no exchange is contacted. Re-running over the same "
        "candles writes nothing, because every record's id is a digest of its own "
        "content."
    ),
    configure=_configure_simulate,
    run=_run_simulate,
)


# ---------------------------------------------------------------------------
# Statistics — five read-only pages over the durable store (Milestone BP)
# ---------------------------------------------------------------------------


def _configure_statistics_common(parser: argparse.ArgumentParser) -> None:
    """The flags every statistics page shares.

    One function rather than five copies: the sample floor and the two equity
    baselines change what the numbers *mean*, and a page that accepted a
    different set of them would be a page whose figures were not comparable
    with its siblings'.
    """
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="PATH",
        help=(
            "the durable store to read trades from (default: the owner's "
            "store). Read-only: these commands write nothing at all"
        ),
    )
    parser.add_argument(
        "--minimum-sample",
        default=None,
        metavar="N",
        help=(
            "the number of observations below which a rate is refused rather "
            "than printed (default: 30). Counts and totals are never withheld; "
            "only rates, expectancies and ratios are"
        ),
    )
    parser.add_argument(
        "--starting-equity",
        default=None,
        metavar="AMOUNT",
        help=(
            "what the account began with. Without it the curve is cumulative "
            "realized profit and loss and every percentage is reported as "
            "unavailable, because this system records the opening capital nowhere"
        ),
    )
    parser.add_argument(
        "--equity-basis",
        default=None,
        metavar="AMOUNT",
        help=(
            "the equity a risk percentage is a percentage of. One basis for the "
            "whole corpus, because the equity at the time of each trade is not "
            "recorded"
        ),
    )
    parser.add_argument(
        "--base-currency",
        default=DEFAULT_BASE_CURRENCY,
        metavar="ASSET",
        help=(
            f"the asset the supplied baselines are stated in (default: "
            f"{DEFAULT_BASE_CURRENCY}). Figures are never summed across quote "
            "assets; each gets its own set"
        ),
    )
    parser.add_argument(
        "--as-of",
        default=None,
        metavar="ISO8601",
        help=(
            "compute the figures as they stood at a past instant. Trades "
            "committed after it, and trades that closed after it, are excluded "
            "— so the page states what was knowable then rather than what is "
            "known now"
        ),
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        metavar="ISO8601",
        help=(
            "instant the reading is taken at (default: now). Supply it to make "
            "the rendered output reproducible."
        ),
    )


def _statistics_report(args: argparse.Namespace, *, regime: str | None = None):
    """Build one report from the shared flags. The only place they are read.

    Every string becomes a domain value in `fmis.statistics.inputs`, never
    here: this layer parses argv and prints, and a `Absent` constructed in a CLI
    would put a domain reason in the one module with no tests over the domain.
    """
    reference = _reference_time(args.reference_time, omit=False)
    assert reference is not None  # `omit=False` always yields an instant
    return report_for_store(
        statistics_store_root(args.store_root),
        at=reference,
        policy=policy_from_text(args.minimum_sample),
        starting_equity=baseline_from_text(
            args.starting_equity,
            asset=args.base_currency,
            flag="--starting-equity",
            absent=NO_STARTING_EQUITY,
        ),
        equity_basis=baseline_from_text(
            args.equity_basis,
            asset=args.base_currency,
            flag="--equity-basis",
            absent=NO_EQUITY_BASIS,
        ),
        as_of=as_of_from_text(args.as_of),
        regime_dimension=regime or DEFAULT_REGIME_DIMENSION,
    )


def _run_statistics_page(args: argparse.Namespace, name: str, render, **extra) -> int:
    """Build, render, print. Every statistics command's whole body.

    A store that does not exist is an empty corpus and renders a page; a store
    that exists and cannot be read is a failure and says so. Collapsing the two
    would report that an owner with a corrupt store has never traded.
    """
    try:
        report = _statistics_report(args, regime=getattr(args, "regime", None))
        rendered = render(report, **extra)
    except STATISTICS_ERRORS as error:
        print(f"fmits {name}: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(rendered)
    return EXIT_OK


def _configure_statistics(parser: argparse.ArgumentParser) -> None:
    _configure_statistics_common(parser)
    parser.add_argument(
        "--regime",
        default=DEFAULT_REGIME_DIMENSION,
        metavar="DIMENSION",
        help=(
            f"which regime dimension the per-regime breakdown groups on "
            f"(default: {DEFAULT_REGIME_DIMENSION}). A snapshot records several "
            "and this engine picks none for you"
        ),
    )


def _run_statistics(args: argparse.Namespace) -> int:
    return _run_statistics_page(args, "statistics", render_statistics)


STATISTICS_COMMAND = Command(
    name="statistics",
    help="every measured statistic over the recorded trades",
    description=(
        "Does this system have an edge. Counts, performance, risk, excursion "
        "quality, the equity and drawdown curves, and every breakdown — all "
        "computed from recorded history alone. Every rate carries the number of "
        "trades it rests on and is refused below a stated floor; every count is "
        "shown at any sample, because a count is a fact and a rate is a claim. "
        "Nothing is estimated, inferred, predicted or calibrated, no candle is "
        "fetched and no record is written. Statistics are recomputed on every "
        "run and stored nowhere."
    ),
    configure=_configure_statistics,
    run=_run_statistics,
)


def _run_performance(args: argparse.Namespace) -> int:
    return _run_statistics_page(args, "performance", render_performance)


PERFORMANCE_COMMAND = Command(
    name="performance",
    help="what the trades made and how they behaved",
    description=(
        "Gross and net profit, average and largest win and loss, profit factor, "
        "payoff ratio, expectancy in money and in R, and the excursion figures "
        "that say how much movement each trade sat through. Excursions exist "
        "only for simulated trades, and every figure states how many of the "
        "corpus actually contributed."
    ),
    configure=_configure_statistics_common,
    run=_run_performance,
)


def _run_expectancy(args: argparse.Namespace) -> int:
    return _run_statistics_page(args, "expectancy", render_expectancy)


EXPECTANCY_COMMAND = Command(
    name="expectancy",
    help="what the average trade did, and how many trades that rests on",
    description=(
        "The narrowest page and the one most easily over-read, so the sample "
        "floor and the population come before the numbers. Expectancy in money "
        "and in R, win and loss rate, profit factor and payoff ratio — each "
        "refused outright below the floor rather than printed with a caveat, "
        "because a caveat beside a number is read as a number."
    ),
    configure=_configure_statistics_common,
    run=_run_expectancy,
)


def _configure_equity(parser: argparse.ArgumentParser) -> None:
    _configure_statistics_common(parser)
    parser.add_argument(
        "--points",
        type=int,
        default=20,
        metavar="N",
        help=(
            "how many of the most recent closed-trade steps to list (default: "
            "20). Every step is in the figures whether or not it is listed"
        ),
    )


def _run_equity(args: argparse.Namespace) -> int:
    return _run_statistics_page(args, "equity", render_equity, points=args.points)


EQUITY_COMMAND = Command(
    name="equity",
    help="the deterministic equity and drawdown curves",
    description=(
        "One step per closed trade and nothing between them. Nothing is "
        "interpolated, open positions are tracked separately and excluded, and "
        "no mark-to-market value is included — this system retains no mark "
        "history to reconstruct one from. Drawdown is measured from each "
        "high-water mark to the recovery of that mark, and a decline that has "
        "not recovered is reported as ongoing rather than as a finished episode."
    ),
    configure=_configure_equity,
    run=_run_equity,
)


def _configure_trades(parser: argparse.ArgumentParser) -> None:
    subcommands = parser.add_subparsers(dest="trades_command", required=True)
    summary = subcommands.add_parser(
        "summary",
        help="the counts, and the most recent closed trades one per line",
        description=(
            "How many trades there are, of what kind, in what state, and how "
            "the last of them ended. A companion to `fmits trade list`, which "
            "shows commitments; this shows what happened to them."
        ),
    )
    _configure_statistics_common(summary)
    summary.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="how many recent closed trades to list (default: 10)",
    )


def _run_trades(args: argparse.Namespace) -> int:
    return _run_statistics_page(
        args, "trades summary", render_trades_summary, limit=args.limit
    )


TRADES_COMMAND = Command(
    name="trades",
    help="summaries over the recorded trades",
    description=(
        "Read-only summaries over every trade in the store. Distinct from "
        "`fmits trade`, which records and inspects one commitment at a time."
    ),
    configure=_configure_trades,
    run=_run_trades,
)


def _configure_archive(parser: argparse.ArgumentParser) -> None:
    # `--archive-root` is defined on every subcommand, not the shared parent:
    # argparse requires a parent optional to precede the subcommand token
    # (`fmits archive --archive-root X list`), which reads worse than the
    # natural `fmits archive list --archive-root X` every sibling command
    # already supports.
    subcommands = parser.add_subparsers(dest="archive_command", required=True)

    list_parser = subcommands.add_parser("list", help="list archived records, metadata only")
    _add_archive_root_argument(list_parser)

    show_parser = subcommands.add_parser(
        "show", help="render one archived record, from storage only — no network access"
    )
    show_parser.add_argument("record_id", metavar="RECORD_ID")
    _add_archive_root_argument(show_parser)

    verify_parser = subcommands.add_parser(
        "verify",
        help="verify integrity; omit RECORD_ID to verify the whole archive",
    )
    verify_parser.add_argument("record_id", nargs="?", default=None, metavar="RECORD_ID")
    _add_archive_root_argument(verify_parser)


def _run_archive(args: argparse.Namespace) -> int:
    store = ArchiveStore(_archive_root_from(args))
    try:
        if args.archive_command == "list":
            print(render_manifest(store.list()))
            return EXIT_OK
        if args.archive_command == "show":
            record = store.load(args.record_id)
            print(render_workspace(record) if isinstance(record, Workspace) else render_daily_run(record))
            return EXIT_OK
        if args.archive_command == "verify":
            if args.record_id is None:
                result = store.verify_archive()
                print(render_archive_verification(result))
                return EXIT_OK if result.ok else EXIT_FAILURE
            record_result = store.verify_record(args.record_id)
            print(render_record_verification(record_result))
            return EXIT_OK if record_result.ok else EXIT_FAILURE
    except ArchiveError as error:
        kind = "not found" if isinstance(error, RecordNotFoundError) else type(error).__name__
        print(f"fmits archive: {kind}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    raise AssertionError(f"unreachable archive_command {args.archive_command!r}")


ARCHIVE_COMMAND = Command(
    name="archive",
    help="list, show and verify durably archived Workspace and DailyRun records",
    description=(
        "The Memory & Decision Archive: list archived records without reading "
        "full payloads, show one record by its stable ID with no network "
        "access, and verify integrity — detecting corruption and unsupported "
        "schema versions. Nothing here is recomputed and nothing is replayed "
        "from raw inputs; a shown record is exactly what was archived."
    ),
    configure=_configure_archive,
    run=_run_archive,
)


FACTS_COMMAND = Command(
    name="facts",
    help="print the deterministic fact sheet for one symbol on one timeframe",
    description=(
        "Fetch public candles for SYMBOL and print every deterministic fact the "
        "system can compute: indicators, market structure, levels, breaks, "
        "changes of character, warm-up status and limitations."
    ),
    configure=_configure_facts,
    run=_run_facts,
)

MTF_COMMAND = Command(
    name="mtf",
    help="print role-labelled fact sheets across several timeframes",
    description=(
        "Fetch public candles for SYMBOL across several timeframes and print each "
        "one's deterministic facts, labelled by the role it plays: context, setup "
        "and execution. The views are reported side by side; nothing is derived "
        "from their combination."
    ),
    configure=_configure_mtf,
    run=_run_mtf,
)

def _configure_dashboard(parser: argparse.ArgumentParser) -> None:
    """Five arguments, and `fmits dashboard` with none of them is the useful one."""
    parser.add_argument(
        "symbols",
        nargs="*",
        metavar="SYMBOL",
        help=(
            f"the watchlist to scan (default: the {len(SCAN_UNIVERSE)}-symbol "
            "list `fmits scan` uses)"
        ),
    )
    parser.add_argument(
        "--host",
        default=DASHBOARD_DEFAULT_HOST,
        metavar="ADDRESS",
        help=(
            f"the interface to bind (default: {DASHBOARD_DEFAULT_HOST}). Any "
            "other address additionally requires --allow-public, because this "
            "page states your positions, open risk and account figures"
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DASHBOARD_DEFAULT_PORT,
        metavar="N",
        help=(
            f"the port to listen on (default: {DASHBOARD_DEFAULT_PORT}). Pass 0 "
            "to let the operating system choose a free one"
        ),
    )
    parser.add_argument(
        "--allow-public",
        action="store_true",
        help=(
            "permit binding an address other than loopback. Publishing this "
            "page to a network publishes what you hold and what you risk"
        ),
    )
    parser.add_argument(
        "--store-root",
        default=None,
        metavar="PATH",
        help=(
            "the durable store to read positions, plans, paper trades and "
            "closed trades from (default: the owner's store). Read-only: this "
            "command writes nothing"
        ),
    )
    parser.add_argument(
        "--lab-artifact",
        default=None,
        metavar="PATH",
        dest="lab_artifact",
        help=(
            "show a saved Swing Lab experiment on the /lab page. The file is "
            "read HERE and handed to the dashboard already decoded, so the "
            "dashboard package still opens nothing. Omitted, /lab says no "
            "experiment is loaded"
        ),
    )
    parser.add_argument(
        "--validation-artifact",
        default=None,
        metavar="PATH",
        dest="validation_artifact",
        help=(
            "show a saved pre-registered Validation study on the /validation "
            "page. Read and decoded by this command, never by the dashboard, "
            "on the same footing as --lab-artifact and --geometry-artifact. "
            "Omitted, /validation says no study is loaded"
        ),
    )
    parser.add_argument(
        "--geometry-artifact",
        default=None,
        metavar="PATH",
        dest="geometry_artifact",
        help=(
            "show a saved Trade Geometry experiment on the /geometry page. Read "
            "HERE and handed to the dashboard already decoded, on the same terms "
            "as --lab-artifact. Omitted, /geometry says no experiment is loaded"
        ),
    )
    parser.add_argument(
        "--no-relationships",
        action="store_true",
        help=(
            "omit the macro cross-asset section. It costs one extra request "
            "per refresh; this skips both the section and the request"
        ),
    )


def _run_dashboard(args: argparse.Namespace) -> int:
    """Serve the operator dashboard until interrupted.

    **The only command in this CLI that does not print a page and exit.** It
    binds a socket and blocks, so the usual "render, print, map to an exit code"
    shape does not apply: the exit code reports whether the server ran, not
    whether any market could be read. A provider outage is a section on the page
    saying so, exactly as it is for every other surface.

    **The first refresh happens on the first request, not here.** Starting the
    server does not fetch, so the command comes up immediately and the owner
    sees the page assemble rather than watching a silent terminal.
    """
    lab = None
    if args.lab_artifact is not None:
        # Decoded HERE, deliberately. The dashboard package opens nothing, and
        # a guard asserts it: handing it an already-parsed view is what keeps
        # that true while still putting research on a page.
        try:
            artifact = read_artifact(args.lab_artifact)
            lab = lab_view(artifact, digest_verified=verify_digest(artifact))
        except SwingLabError as error:
            print(f"fmits dashboard: {error}", file=sys.stderr)
            return EXIT_FAILURE

    validation = None
    if args.validation_artifact is not None:
        try:
            record = read_validation_artifact(args.validation_artifact)
            validation = validation_view(
                record,
                digest_verified=verify_result_digest(record),
                seal_matches=verify_preregistration_seal(record),
            )
        except SwingLabError as error:
            print(f"fmits dashboard: {error}", file=sys.stderr)
            return EXIT_FAILURE
    geometry = None
    if args.geometry_artifact is not None:
        try:
            record = read_geometry_artifact(args.geometry_artifact)
            geometry = geometry_view(
                record, digest_verified=verify_geometry_digest(record)
            )
        except SwingLabError as error:
            print(f"fmits dashboard: {error}", file=sys.stderr)
            return EXIT_FAILURE

    def announce(url: str, _server: object) -> None:
        # Flushed explicitly: piped or redirected, this banner is block-buffered
        # and the owner would stare at an empty terminal while the socket sat
        # listening. The URL is the whole point of the command's output.
        print("FMITS Operator Dashboard — read only", flush=True)
        print(f"  open   {url}", flush=True)
        print("  stop   Ctrl-C", flush=True)
        print(
            "  This surface reads. It places no order, records no trade and "
            "changes no stored value.",
            flush=True,
        )

    try:
        serve_dashboard(
            host=args.host,
            port=args.port,
            holder=SnapshotHolder(
                symbols=tuple(args.symbols) or None,
                store_root=args.store_root,
                with_relationships=not args.no_relationships,
                lab=lab,
                geometry=geometry,
                validation=validation,
            ),
            allow_public=args.allow_public,
            quiet=True,
            announce=announce,
        )
    except (ValueError, OSError) as error:
        print(f"fmits dashboard: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print("fmits dashboard: stopped", file=sys.stderr)
    return EXIT_OK


def _configure_research(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "area",
        choices=(
            "swing", "geometry", "validation", "persistence", "admission",
            "design", "universe", "dependence",
        ),
        help=(
            "which research question to run. 'swing' is the Swing Strategy "
            "Laboratory's timeframe-policy comparison (Milestone BW); "
            "'geometry' is the Swing Trade Geometry Laboratory's stop/target "
            "comparison (Milestone BX), which needs --development and --holdout "
            "instead of a positional universe; 'validation' runs Milestone BY's "
            "SEALED pre-registration and takes no universe, no window and no "
            "threshold at all — every one of them is part of what was frozen, "
            "and a study whose symbols could be renamed at a shell prompt would "
            "not be a pre-registered study; 'persistence' runs Milestone BZ's "
            "SEALED post-entry study — what happens to a thesis AFTER entry, and "
            "whether a causal exit policy generalises — and takes no universe, "
            "no window and no threshold either; 'admission' runs Milestone CA's "
            "SEALED null-model study — whether the admission engine selects "
            "instants and directions better than MATCHED entries it did not "
            "select — which is measured entirely from a saved BZ capture and "
            "therefore REQUIRES --from-capture and touches no network at all; "
            "'design' runs Milestone CB's research-design assessment of the CA "
            "study — whether that experiment could ever have resolved the effect "
            "it declared — which reads no market data of any kind, opens no "
            "capture and says nothing about whether an edge exists; "
            "'universe' runs Milestone CC's SEALED universe-feasibility study — "
            "whether a research universe large and INDEPENDENT enough to resolve "
            "CA's +0.10 ATR effect can be built at all from this repository's "
            "provider. It discovers instruments from the public read-only "
            "exchangeInfo endpoint, stages a funnel down to eligible economic "
            "assets, measures co-movement between them and reports a feasibility "
            "verdict that approves NOTHING; "
            "'dependence' runs Milestone CD's SEALED paired-effect dependence "
            "measurement — how dependent the actual admission-versus-control "
            "paired differences are WITHIN one economic asset and BETWEEN assets "
            "observed in the same period, and what that does to Milestone CB's "
            "information requirement. It is measured over a Milestone BZ capture "
            "and therefore REQUIRES --from-capture, or replays a persisted CD "
            "artifact with --from-study. It approves NOTHING and measures no edge"
        ),
    )
    parser.add_argument(
        "symbols", nargs="*", metavar="SYMBOL",
        help=(
            "the universe to replay, in report order. Required for 'swing'; "
            "'geometry' refuses it and asks for --development/--holdout, "
            "because a geometry study that could not say which symbols were "
            "held back would have no holdout at all"
        ),
    )
    parser.add_argument(
        "--development", nargs="+", default=None, metavar="SYMBOL",
        help=(
            "geometry only: the symbols variants may be judged on. These are "
            "NOT out-of-sample — Milestone BW already measured them"
        ),
    )
    parser.add_argument(
        "--holdout", nargs="+", default=None, metavar="SYMBOL",
        help=(
            "geometry only: symbols held back, measured over the SAME window. "
            "Must be disjoint from --development"
        ),
    )
    parser.add_argument(
        "--no-sensitivity", action="store_true",
        help="geometry only: skip the parameter-sensitivity grids (faster)",
    )
    parser.add_argument(
        "--with-mechanics", action="store_true",
        help=(
            "validation only: also run the entry, exit and intrabar-ambiguity "
            "studies (Milestone BY §7-§9). Costs a second fetch of ~400k 1H "
            "rows. Omitted, the report says those sections were NOT MEASURED "
            "rather than printing an empty table"
        ),
    )
    parser.add_argument(
        "--save-capture", default=None, metavar="PATH", dest="save_capture",
        help=(
            "persistence only: write the replay's CAPTURE — candidates, bars and "
            "the structural timeline — to PATH as a deterministic, digested "
            "artifact. Market data is mutable at source, so a study that "
            "refetches is not reproducible even with frozen code; this is what "
            "makes a later re-run a pure function of the file"
        ),
    )
    parser.add_argument(
        "--from-capture", default=None, metavar="PATH", dest="from_capture",
        help=(
            "persistence and admission: re-measure from a saved capture instead "
            "of replaying. NO NETWORK IS TOUCHED. Refuses a corrupted digest, a "
            "foreign schema version, a study artifact, or a capture missing any "
            "data it references — it never completes a gap from the provider. "
            "REQUIRED for 'admission', which has no live path at all"
        ),
    )
    parser.add_argument(
        "--save-study", default=None, metavar="PATH", dest="save_study",
        help=(
            "admission only: write the completed study as a deterministic, "
            "digested artifact carrying both the pre-registration digest it was "
            "measured under and the capture digest it was measured over, so a "
            "later disagreement can be attributed to the code, the rules or the "
            "data rather than argued about. Refuses to overwrite"
        ),
    )
    parser.add_argument(
        "--save-universe", default=None, metavar="PATH", dest="save_universe",
        help=(
            "universe only: write the derived feasibility study as a "
            "deterministic, digested artifact. It carries the funnel, every "
            "eligibility decision with its reason, the dependence and density "
            "summaries, the growth curve and the verdict, plus the SHA-256 of "
            "every series it was computed from — but not the bars themselves. "
            "Pair it with --save-capture for reproduction from raw inputs. "
            "Refuses to overwrite"
        ),
    )
    parser.add_argument(
        "--from-study", default=None, metavar="PATH", dest="from_study",
        help=(
            "dependence only: re-measure Milestone CD from a persisted CD "
            "artifact instead of replaying a capture. NO NETWORK AND NO CAPTURE "
            "IS TOUCHED — every figure is re-derived from the observation rows "
            "the artifact carries, which is what makes offline reproduction real "
            "rather than claimed. Refuses a corrupted digest, a foreign schema "
            "version, a foreign seal or a missing provenance field"
        ),
    )
    parser.add_argument(
        "--save-dependence", default=None, metavar="PATH", dest="save_dependence",
        help=(
            "dependence only: write the completed measurement as a "
            "deterministic, digested artifact carrying EVERY observation-level "
            "paired difference with the provenance to audit it offline, plus the "
            "CD seal it was measured under and the capture digest it was measured "
            "over. Refuses to overwrite"
        ),
    )
    parser.add_argument(
        "--causal-proven", action="store_true", dest="causal_proven",
        help=(
            "admission only: assert that the milestone's no-lookahead suite "
            "passed WITH its non-vacuity controls in this build. Off by default "
            "and deliberately so — a run cannot verify the repository's own test "
            "suite from inside itself, so the causal criterion blocks unless a "
            "human states it, and a blocked criterion cannot promote"
        ),
    )
    parser.add_argument(
        "--open-holdout", action="store_true",
        help=(
            "validation only: also replay the held-back symbols. Omitted, the "
            "holdout is NOT EVEN FETCHED, every holdout criterion reports as "
            "unevaluable and no policy can reach candidate status. That is the "
            "development pass, and it is the default so the holdout cannot be "
            "inspected by habit"
        ),
    )
    parser.add_argument(
        "--start", default=None, metavar="ISO8601",
        help=(
            "start of the MEASUREMENT window. Warm-up history is derived and "
            "fetched before it; a window the provider cannot warm is refused "
            "with the shortfall rather than quietly shortened"
        ),
    )
    parser.add_argument(
        "--end", default=None, metavar="ISO8601",
        help="end of the measurement window (default: now)",
    )
    parser.add_argument(
        "--variant", action="append", default=None, metavar="ID", dest="variant",
        help=(
            "repeatable: run only these pre-specified variants. Omitted, every "
            "variant in the study is run. Variants are DEFINED IN CODE and "
            "cannot be described on the command line — a policy invented at a "
            "shell prompt is a policy nobody pre-specified. Available: "
            + ", ".join(item.variant_id for item in PRE_SPECIFIED_VARIANTS)
        ),
    )
    parser.add_argument(
        "--window", type=int, default=DEFAULT_EVALUATION_WINDOW_BARS, metavar="BARS",
        help=(
            "execution-role bars to evaluate a trade over (default: "
            f"{DEFAULT_EVALUATION_WINDOW_BARS}); a measurement policy, not a "
            "tuned value"
        ),
    )
    parser.add_argument(
        "--costs", choices=("frictionless", "conservative"), default="frictionless",
        help=(
            "cost scenario (default: frictionless). 'conservative' charges 10 "
            "basis points on the entry and the exit notional and is "
            "deliberately pessimistic"
        ),
    )
    parser.add_argument(
        "--robustness", action="store_true",
        help="also print the chronological, walk-forward, symbol and direction splits",
    )
    parser.add_argument(
        "--save", default=None, metavar="PATH",
        help=(
            "write the completed experiment as a JSON research artifact, "
            "carrying its manifest and every trade so the run can be reviewed "
            "and rebuilt. Refuses to overwrite an existing file. This is a "
            "research record, not part of the trading store"
        ),
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=None, metavar="CANDLES",
        help="candles requested per role (default: the harness default)",
    )


def _run_research(args: argparse.Namespace) -> int:
    """Run one Swing Lab experiment and print its report.

    **Read-only research.** This command replays history, measures policy
    variants and prints a comparison. It writes nothing, changes no production
    strategy and promotes nothing: a variant that measures well here is a
    candidate for forward testing, which is a later, explicit owner decision.
    """
    if args.area == "design":
        for name in ("symbols", "development", "holdout", "variant"):
            value = getattr(args, name, None)
            if value:
                print(
                    f"fmits research design: {name} is not accepted. This area "
                    "reads no market data at all — it assesses a study's DESIGN "
                    "from published sample metadata and uncertainty",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        for name in ("start", "end", "from_capture", "save_capture"):
            if getattr(args, name, None) is not None:
                print(
                    f"fmits research design: --{name.replace('_', '-')} is not "
                    "accepted. The samples assessed are the sealed ones and no "
                    "capture is read",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_design_research(args)
    if args.area == "universe":
        for name in ("symbols", "development", "holdout", "variant"):
            if getattr(args, name, None):
                print(
                    f"fmits research universe: {name} is not accepted. The "
                    "universe is DISCOVERED from the provider, never supplied — a "
                    "hand-written list is exactly what this study exists to "
                    "replace",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        for name in ("start", "end", "save_study"):
            if getattr(args, name, None) is not None:
                print(
                    f"fmits research universe: --{name.replace('_', '-')} is not "
                    "accepted. The measurement window and every threshold are "
                    "part of what the CC pre-registration sealed",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_universe_research(args)
    if args.area == "dependence":
        for name in ("symbols", "development", "holdout", "variant"):
            value = getattr(args, name, None)
            if value:
                print(
                    f"fmits research dependence: {name} is not accepted. The "
                    "universe, the samples, the horizon, the estimator and every "
                    "threshold are part of the sealed pre-registration",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        for name in ("start", "end"):
            if getattr(args, name, None) is not None:
                print(
                    f"fmits research dependence: --{name} is not accepted. The "
                    "measurement windows are Milestone BY's, sealed; moving one "
                    "would make this a different study under the same digest",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_dependence_research(args)
    if args.area == "admission":
        for name in ("symbols", "development", "holdout", "variant"):
            value = getattr(args, name, None)
            if value:
                print(
                    f"fmits research admission: {name} is not accepted. Every "
                    "symbol, window, horizon, matching rule, seed and threshold "
                    "is sealed in the pre-registration",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        for name in ("start", "end"):
            if getattr(args, name, None) is not None:
                print(
                    f"fmits research admission: --{name} is not accepted. The "
                    "measurement windows are part of the sealed "
                    "pre-registration",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_admission_research(args)
    if args.area == "persistence":
        for name in ("symbols", "development", "holdout", "variant"):
            value = getattr(args, name, None)
            if value:
                print(
                    f"fmits research persistence: {name} is not accepted. Every "
                    "symbol, window, checkpoint and threshold is sealed in the "
                    "pre-registration",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_persistence_research(args)
    if args.area == "validation":
        # Dispatched BEFORE the window is read, because this study HAS no window
        # argument: its dates are sealed. Parsing --start here would let a
        # caller believe they had moved a boundary that the pre-registration
        # fixed, which is worse than the flag simply not existing.
        for name, value in (("start", args.start), ("end", args.end)):
            if value is not None:
                print(
                    f"fmits research validation: --{name} is not accepted. The "
                    "measurement windows are part of the sealed "
                    "pre-registration; moving one would make this a different "
                    "experiment measured under the same digest",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
        return _run_validation_research(args)
    if args.start is None:
        print(
            "fmits research: --start is required for this area",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    end = _reference_time(args.end, omit=False)
    start = datetime.fromisoformat(args.start)
    if start.tzinfo is None:
        print(
            "fmits research: --start must be timezone-aware, e.g. "
            "2024-01-01T00:00:00+00:00",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if args.area == "geometry":
        return _run_geometry_research(args, start=start, end=end)
    if not args.symbols:
        print(
            "fmits research swing: at least one SYMBOL is required",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    for name in ("development", "holdout"):
        if getattr(args, name) is not None:
            print(
                f"fmits research swing: --{name} belongs to 'geometry'; the "
                "swing study replays one universe and holds nothing back",
                file=sys.stderr,
            )
            return EXIT_FAILURE
    try:
        chosen = (
            PRE_SPECIFIED_VARIANTS
            if args.variant is None
            else tuple(variant_by_id(item) for item in args.variant)
        )
        study = run_lab_study(
            args.symbols,
            measurement_start=start,
            measurement_end=end,
            run_at=datetime.now(timezone.utc),
            experiment_id=f"cli-{start.date()}-{end.date()}",
            variants=chosen,
            costs=(
                CONSERVATIVE_COSTS if args.costs == "conservative" else FRICTIONLESS_COSTS
            ),
            evaluation_window_bars=args.window,
            limit=DEFAULT_BACKTEST_LIMIT if args.limit is None else args.limit,
        )
    except SwingLabError as error:
        print(f"fmits research {args.area}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_study(study))
    if args.save is not None:
        try:
            written = write_study(study, args.save)
        except SwingLabError as error:
            print(f"fmits research {args.area}: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nResearch artifact written to {written}")
    if args.robustness:
        for result in study.results:
            print()
            print(
                render_robustness(
                    measure_robustness(
                        result.trades,
                        variant_id=result.variant.variant_id,
                        measurement_start=start,
                        measurement_end=end,
                    )
                )
            )
    return EXIT_OK


def _run_geometry_research(
    args: argparse.Namespace, *, start: datetime, end: datetime
) -> int:
    """Run one Swing Trade Geometry experiment and print its report.

    **Read-only research.** Replays history once, measures pre-declared geometry
    policies against a development sample and a held-back one, and prints what
    each concluded. It writes no trading record, changes no production strategy
    and promotes nothing: the strongest verdict it can produce means *worth
    testing forward*, which is a later, explicit owner decision.

    Geometries are **defined in code** and cannot be described on this command
    line — a stop rule invented at a shell prompt is a rule nobody pre-declared.
    """
    if args.symbols:
        print(
            "fmits research geometry: name symbols with --development and "
            "--holdout, not positionally. A geometry study that could not say "
            "which symbols were held back would have no holdout at all",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if not args.development or not args.holdout:
        print(
            "fmits research geometry: both --development and --holdout are "
            "required. Measuring a policy without holding symbols back is "
            "exactly the mistake this study exists to avoid",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    try:
        study = run_geometry_experiment(
            development_symbols=args.development,
            holdout_symbols=args.holdout,
            measurement_start=start,
            measurement_end=end,
            run_at=datetime.now(timezone.utc),
            experiment_id=f"geometry-{start.date()}-{end.date()}",
            costs=(
                CONSERVATIVE_COSTS if args.costs == "conservative" else FRICTIONLESS_COSTS
            ),
            evaluation_window_bars=args.window,
            limit=DEFAULT_BACKTEST_LIMIT if args.limit is None else args.limit,
            with_sensitivity=not args.no_sensitivity,
        )
    except SwingLabError as error:
        print(f"fmits research geometry: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_geometry_study(study))
    if args.save is not None:
        try:
            written = write_geometry_study(study, args.save)
        except SwingLabError as error:
            print(f"fmits research geometry: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nResearch artifact written to {written}")
    return EXIT_OK


def _run_universe_research(args: argparse.Namespace) -> int:
    """Run Milestone CC's SEALED universe-feasibility study. **Approves nothing.**

    Two read-only, unauthenticated public endpoints are used — `exchangeInfo` to
    discover what exists and `klines` to measure how much history it has. Nothing
    signs a request, reads a credential or touches an order path, and there is no
    production execution path reachable from this command.

    ``--from-capture`` re-measures from a persisted series capture with fetching
    disabled, so a re-run is a pure function of the file. ``--save-capture``
    writes the series this run read, and ``--save-study`` writes the derived
    feasibility artifact carrying the digest of every series behind it.

    The verdict answers whether the +0.10 ATR question can be ASKED. It says
    nothing about whether an admission edge exists — Milestone CA's NO_EDGE
    stands — and it is not permission to trade, to paper trade or to promote.
    """
    cache = SeriesCache()
    allow_fetch = True
    if args.from_capture is not None:
        try:
            cache = SeriesCache.read(args.from_capture)
        except (UniverseError, OSError, ValueError) as error:
            print(f"fmits research universe: {error}", file=sys.stderr)
            return EXIT_FAILURE
        allow_fetch = False
    try:
        study = run_universe_study(cache=cache, allow_fetch=allow_fetch)
    except (UniverseError, SwingLabError, ResearchDesignError) as error:
        print(f"fmits research universe: {error}", file=sys.stderr)
        return EXIT_FAILURE

    print(render_universe_study(study))

    if study.horizon is not None:
        print()
        print(rule())
        print("POST-HOC ROBUSTNESS — THE PROVIDER'S CEILING (NOT PRE-REGISTERED)")
        print(rule())
        ceiling = study.horizon
        print(f"  economic assets ever qualifying   {ceiling.qualifying_assets:>10,}")
        print(f"  total usable asset-years          {ceiling.total_asset_years:>10,.1f}")
        print(f"  projected admissions              {ceiling.projected_admissions:>10,}")
        print(f"  required admissions               {ceiling.required_admissions:>10,}")
        print(f"  required clusters                 {ceiling.required_clusters:>10,}")
        print(f"  reaches the requirement           {str(ceiling.reaches_requirement):>10}")
        print()
        for line in wrap_text(ceiling.note):
            print(line)

    if args.save_capture is not None:
        try:
            written = cache.write(args.save_capture)
        except OSError as error:
            print(f"fmits research universe: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nCAPTURE WRITTEN to {written} ({len(cache)} series)")

    if getattr(args, "save_universe", None) is not None:
        payload = encode_universe_study(
            study,
            manifest={
                "written_at": datetime.now(timezone.utc).isoformat(),
                "preregistration_digest": study.preregistration_digest,
                "capture_series": len(cache),
            },
        )
        try:
            written = write_universe_artifact(payload, args.save_universe)
        except (UniverseError, OSError) as error:
            print(f"fmits research universe: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nSTUDY WRITTEN to {written}")
        print(f"  content digest {payload['manifest']['content_digest']}")

    if args.from_capture is not None:
        print(
            f"\nRE-MEASURED OFFLINE from {args.from_capture}\n"
            f"  series in capture {len(cache)}\n"
            f"  seal in build     {CC_PREREGISTRATION_DIGEST}\n"
            f"  seal recomputed   {study.preregistration_digest}\n"
            f"  seals agree       "
            f"{study.preregistration_digest == CC_PREREGISTRATION_DIGEST}\n"
            "  NO CANDLE WAS REFETCHED."
        )
    return EXIT_OK


def _run_design_research(args: argparse.Namespace) -> int:
    """Print Milestone CB's design assessment of the CA study. **Reads nothing.**

    No network, no capture, no store and no file. Every input is published sample
    metadata and a published interval, so this command is a pure function of the
    build — which is what makes it safe to run before a study rather than after.

    It answers one question and refuses every other: *could that experiment have
    resolved the effect it declared?* It says nothing about whether an admission
    edge exists, and there is no code path here that could.
    """
    try:
        assessment = ca_design_assessment()
        reproduction = ca_reproduction()
    except (SwingLabError, ResearchDesignError) as error:
        print(f"fmits research design: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_design_assessment(assessment))

    print(rule())
    print("REPRODUCING MILESTONE CA'S PUBLISHED REQUIREMENT")
    print(rule())
    print(f"  published claim         ~{reproduction.published_claim:,} admissions per sample")
    print(f"  published half-width     {reproduction.published_half_width}")
    print(f"  half-width from bounds   {reproduction.derived_half_width}")
    print(f"  recomputed (published h) {reproduction.recomputed_from_published_half_width:,}")
    print(f"  recomputed (bounds h)    {reproduction.recomputed_from_interval_bounds:,}")
    print(f"  disposition              {reproduction.disposition.upper()}")
    print()
    for line in wrap_text(reproduction.reasoning):
        print(line)
    print()

    print(rule())
    print("POST-HOC RESOLUTION, EVERY SAMPLE")
    print(rule())
    print("  sample          obs  clusters  half-width  smallest resolvable  resolves")
    for name in ("development", "validation", "holdout"):
        reading = ca_post_hoc(name)
        print(
            f"  {name:<13} {reading.observations:>4} {reading.clusters:>9} "
            f"{reading.observed_half_width:>11.4f} "
            f"{reading.smallest_resolvable_effect:>20.4f} "
            f"{str(reading.resolves_meaningful_effect):>9}"
        )
    print()
    print(rule())
    print("DESIGN CURVE — MODELLED, AND EXTRAPOLATED BEYOND 155 ADMISSIONS")
    print(rule())
    for path in (
        GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
        GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
    ):
        for correlation in CA_DESIGN_CURVE_CORRELATIONS:
            print(f"  {path.value} @ rho={correlation}")
            print("      admissions  clusters  half-width  resolves  extrapolated")
            for point in ca_design_curve(path, correlation):
                print(
                    f"      {point.observations:>10,} {point.clusters:>9,} "
                    f"{point.half_width:>11.4f} {str(point.resolves):>9} "
                    f"{str(point.extrapolated):>13}"
                )
            print()
    print(rule())
    print("WHAT THIS ASSESSMENT CANNOT DO")
    print(rule())
    for item in CA_DESIGN_LIMITATIONS:
        for line in wrap_text(f"- {item}"):
            print(line)
    print()

    if getattr(args, "save_study", None):
        target = Path(args.save_study)
        if target.exists():
            print(
                f"fmits research design: {target} already exists; an assessment is "
                "never overwritten",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        payload = encode_design_assessment(assessment, writer="fmits research design")
        if not verify_design_assessment_digest(payload):  # pragma: no cover - defensive
            print(
                "fmits research design: the assessment did not verify against its "
                "own digest and was not written",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        target.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nwrote {target}", file=sys.stderr)
    return EXIT_OK


def _run_admission_research(args: argparse.Namespace) -> int:
    """Run Milestone CA's sealed null-model study. **Offline, always.**

    There is deliberately no live path: CA is measured over a Milestone BZ
    capture, so `--from-capture` is required rather than optional. A live variant
    would refetch mutable market data and the study would stop being a pure
    function of a file — which is the exact failure BZ recorded as BZ-D2 and the
    reason the capture exists.
    """
    if not args.from_capture:
        print(
            "fmits research admission: --from-capture is REQUIRED. Milestone CA "
            "is measured over a saved Milestone BZ capture and has no live path: "
            "a study that refetched mutable market data would not be "
            "reproducible even with frozen code",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if args.save_capture:
        print(
            "fmits research admission: --save-capture belongs to 'persistence'; "
            "CA reads a capture and never writes one. Use --save-study",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    target = None
    if args.save_study:
        target = Path(args.save_study)
        if target.exists():
            print(
                f"fmits research admission: {target} already exists; a study is "
                "never overwritten",
                file=sys.stderr,
            )
            return EXIT_FAILURE
    try:
        artifact = read_persistence_capture(args.from_capture)
    except SwingLabError as error:
        print(f"fmits research admission: {error}", file=sys.stderr)
        return EXIT_FAILURE
    if not verify_capture_digest(artifact):
        print(
            f"fmits research admission: capture {args.from_capture} does not "
            "match its own content digest; it has been edited or truncated",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    # Reported rather than resolved: a capture can be perfectly intact and still
    # describe a different experiment, and merging those two failures would
    # report a foreign experiment as a corrupt file.
    if artifact.preregistration_digest != BZ_PREREGISTRATION_DIGEST:
        print(
            "fmits research admission: NOTE — this capture was taken under "
            f"pre-registration {artifact.preregistration_digest}, and this build "
            f"seals {BZ_PREREGISTRATION_DIGEST}. The capture is intact; it "
            "describes a different Milestone BZ experiment.",
            file=sys.stderr,
        )
    missing = [
        name for name in ("primary", "holdout") if name not in artifact.universe_names
    ]
    if missing:
        print(
            f"fmits research admission: this capture holds no {', '.join(missing)} "
            f"universe; it holds {', '.join(artifact.universe_names)}. CA needs "
            "both, and the holdout is not optional because a study that could "
            "not open it would report every holdout criterion as unevaluable",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    try:
        study = study_from_capture(
            artifact,
            universe_for_sample={
                "development": "primary",
                "validation": "primary",
                "holdout": "holdout",
            },
            run_at=datetime.now(timezone.utc),
            causal_proven=bool(args.causal_proven),
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except SwingLabError as error:
        print(f"fmits research admission: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_admission_study(study))
    if target is not None:
        written = write_admission_study(
            encode_admission_study(study, writer="fmits research admission"), target
        )
        print(f"\nwrote {written}", file=sys.stderr)
    return EXIT_OK


def _run_dependence_research(args: argparse.Namespace) -> int:
    """Run Milestone CD's sealed paired-effect dependence measurement.

    **Offline, always.** There is no live path: CD measures the dependence of
    Milestone CA's paired differences, CA is a pure function of a saved Milestone
    BZ capture, and a study that refetched mutable market data would not be
    reproducible even with frozen code. Either ``--from-capture`` (replay CA over
    a capture and measure its output) or ``--from-study`` (re-derive every figure
    from a persisted CD artifact) is required, and they are mutually exclusive.

    The report separates OBSERVATION, MEASUREMENT, UNCERTAINTY, DESIGN
    IMPLICATION and LIMITATIONS, and prints no recommendation of any kind. The
    verdict says how well a dependence was identified. It is not permission to
    trade, to paper trade, to shadow trade or to promote a setup, and Milestone
    CA's NO_EDGE stands whatever it says.
    """
    if bool(args.from_capture) == bool(args.from_study):
        print(
            "fmits research dependence: exactly one of --from-capture and "
            "--from-study is required. --from-capture replays Milestone CA over "
            "a BZ capture and measures its paired differences; --from-study "
            "re-derives every figure from a persisted CD artifact. There is no "
            "live path, because a study that refetched mutable market data would "
            "not be reproducible even with frozen code",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    target = None
    if args.save_dependence:
        target = Path(args.save_dependence)
        if target.exists():
            print(
                f"fmits research dependence: {target} already exists; a research "
                "artifact is never overwritten",
                file=sys.stderr,
            )
            return EXIT_FAILURE

    def say(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        if args.from_capture:
            artifact = read_persistence_capture(args.from_capture)
            if not verify_capture_digest(artifact):
                print(
                    f"fmits research dependence: capture {args.from_capture} does "
                    "not match its own content digest; it has been edited or "
                    "truncated and no number measured over it can be trusted",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
            missing = [
                name
                for name in ("primary", "holdout")
                if name not in artifact.universe_names
            ]
            if missing:
                print(
                    f"fmits research dependence: this capture holds no "
                    f"{', '.join(missing)} universe; it holds "
                    f"{', '.join(artifact.universe_names)}. CD needs both, "
                    "because a dependence measured on fifteen assets and one "
                    "measured on thirty-six are different measurements",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
            study = dependence_study_from_capture(
                artifact, run_at=datetime.now(timezone.utc), progress=say
            )
        else:
            saved = read_dependence_study(args.from_study)
            if not verify_dependence_study_digest(saved):
                print(
                    f"fmits research dependence: study {args.from_study} does not "
                    "match its own content digest; it has been edited since it "
                    "was written",
                    file=sys.stderr,
                )
                return EXIT_FAILURE
            saved.require_seal()
            study = dependence_study_from_rows(
                dependence_rows_of(saved),
                manifest=saved.manifest,
                reconstruction=saved.payload["reconstruction"],
                progress=say,
            )
    except (PairedDependenceError, SwingLabError, ResearchDesignError) as error:
        print(f"fmits research dependence: {error}", file=sys.stderr)
        return EXIT_FAILURE

    print(render_dependence_study(study))

    if target is not None:
        payload = encode_dependence_study(study, writer="fmits research dependence")
        try:
            written = write_dependence_study(payload, target)
        except (PairedDependenceError, OSError) as error:
            print(f"fmits research dependence: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nSTUDY WRITTEN to {written}", file=sys.stderr)
        print(
            f"  content digest {payload['manifest']['content_digest']}",
            file=sys.stderr,
        )
        print(f"  observations   {len(payload['observations']):,}", file=sys.stderr)
    return EXIT_OK


def _run_persistence_research(args: argparse.Namespace) -> int:
    """Run Milestone BZ's SEALED post-entry study and print what it concluded.

    **Read-only research.** Replays history once per universe, collects the
    structural timeline from that same walk, observes every position's causal
    post-entry path, measures the sealed exit families against their own control
    and prints the verdict. It writes no trading record, changes no production
    strategy and promotes nothing.

    The holdout is **not fetched** unless `--open-holdout` is given, so a
    development pass cannot inspect it by accident.
    """
    if args.from_capture is not None:
        if args.save_capture is not None:
            print(
                "fmits research persistence: --from-capture and --save-capture "
                "are mutually exclusive; re-writing a capture from itself would "
                "claim a fresh replay that never happened",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        return _run_persistence_from_capture(args)
    try:
        study = run_persistence_experiment(
            run_at=datetime.now(timezone.utc),
            open_holdout=args.open_holdout,
            # The no-lookahead suite is a repository-level fact this command
            # cannot verify from inside a run, so it is reported as UNPROVEN
            # here and the criterion blocks. A promotion therefore needs the
            # milestone's own verification, never a bare CLI invocation.
            causal_proven=False,
            limit=None if args.limit is None else args.limit,
        )
    except SwingLabError as error:
        print(f"fmits research persistence: {error}", file=sys.stderr)
        return EXIT_FAILURE
    if args.save_capture is not None:
        print(
            "fmits research persistence: --save-capture needs the capture the "
            "run produced; use the milestone's own runner, which writes it. The "
            "command declines rather than writing a partial artifact.",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    print(render_persistence_study(study))
    if not args.open_holdout:
        print(
            "\nNOTE: the holdout was NOT opened. Every holdout criterion is "
            "unevaluable and no family can reach candidate status. Re-run with "
            "--open-holdout once, and only once, when development is finished."
        )
    return EXIT_OK


def _run_persistence_from_capture(args: argparse.Namespace) -> int:
    """Re-measure Milestone BZ from a persisted capture. **No network, ever.**

    The point of the flag is reproducibility: given the same file and the same
    code this prints the same study, so a disagreement between two runs is a
    code change rather than a data change. The capture's own pre-registration
    digest is compared against this build's seal and a mismatch is **reported
    rather than resolved** — a capture can be perfectly intact and still describe
    a different experiment, and the two failures must not be merged.
    """
    try:
        artifact = read_persistence_capture(args.from_capture)
        if not verify_capture_digest(artifact):
            print(
                f"fmits research persistence: capture {args.from_capture} "
                "fails its own content digest; it has been edited since it was "
                "written and no number in it can be trusted",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        names = artifact.universe_names
        if "primary" not in names:
            print(
                "fmits research persistence: this capture holds no 'primary' "
                f"universe; it holds {', '.join(names)}",
                file=sys.stderr,
            )
            return EXIT_FAILURE
        primary = artifact.universe("primary")
        holdout = artifact.universe("holdout") if "holdout" in names else None
        study = study_from_captures(
            primary=primary.capture,
            primary_timelines=primary.timelines,
            holdout=None if holdout is None else holdout.capture,
            holdout_timelines={} if holdout is None else holdout.timelines,
            causal_proven=False,
            evaluation_window_bars=artifact.manifest["evaluation_window_bars"],
        )
    except SwingLabError as error:
        print(f"fmits research persistence: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_persistence_study(study))
    print(
        f"\nRE-MEASURED OFFLINE from {args.from_capture}\n"
        f"  captured at    {artifact.manifest['captured_at']}\n"
        f"  content digest {artifact.content_digest}\n"
        f"  seal in file   {artifact.preregistration_digest}\n"
        f"  seal in build  {BZ_PREREGISTRATION_DIGEST}\n"
        f"  seals agree    {artifact.preregistration_digest == BZ_PREREGISTRATION_DIGEST}\n"
        "  NO NETWORK WAS CONTACTED."
    )
    return EXIT_OK


def _run_validation_research(args: argparse.Namespace) -> int:
    """Run Milestone BY's SEALED pre-registered validation and print its report.

    **Read-only research.** Replays history, measures the sealed hypotheses on
    the sealed samples under the sealed cost scenarios, and prints what each
    concluded. It writes no trading record, changes no production strategy and
    promotes nothing: the strongest verdict it can produce means *worth testing
    forward*, which is a later, explicit owner decision.

    The holdout is **not fetched** unless `--open-holdout` is given, so a
    development pass cannot inspect it by accident.
    """
    for name in ("development", "holdout", "symbols", "variant"):
        value = getattr(args, name, None)
        if value:
            print(
                f"fmits research validation: {name} is not accepted. Every "
                "symbol, window and threshold is sealed in the "
                "pre-registration",
                file=sys.stderr,
            )
            return EXIT_FAILURE
    try:
        study, mechanics = run_validation_experiment(
            run_at=datetime.now(timezone.utc),
            experiment_id="by-validation",
            open_holdout=args.open_holdout,
            with_mechanics=args.with_mechanics,
            # The suite is a repository-level fact this command cannot verify
            # from inside a run, so it is reported as UNPROVEN here and the
            # criterion blocks. A promotion therefore needs the milestone's own
            # verification, never a bare CLI invocation.
            no_lookahead_proven=False,
            limit=DEFAULT_BACKTEST_LIMIT if args.limit is None else args.limit,
        )
    except SwingLabError as error:
        print(f"fmits research validation: {error}", file=sys.stderr)
        return EXIT_FAILURE
    print(render_validation_study(study, mechanics))
    if not args.open_holdout:
        print(
            "\nNOTE: the holdout was NOT opened. Every holdout criterion is "
            "unevaluable and no policy can reach candidate status. Re-run with "
            "--open-holdout once, and only once, when development is finished."
        )
    if args.save is not None:
        try:
            written = write_validation_study(study, args.save)
        except SwingLabError as error:
            print(f"fmits research validation: {error}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"\nResearch artifact written to {written}")
    return EXIT_OK


RESEARCH_COMMAND = Command(
    name="research",
    help="replay policy variants over real history and compare them (read-only)",
    description=(
        "Three read-only laboratories. 'validation' (Milestone BY) runs a SEALED "
        "pre-registration: every hypothesis, threshold, symbol, window, cost "
        "scenario and promotion criterion was fixed and digested before any "
        "result was read, so the command takes no universe, no window and no "
        "threshold, and nothing outside the seal can be promoted whatever it "
        "measures. 'geometry' (Milestone BX) replays history "
        "once and compares pre-declared stop/target rules against a development "
        "sample and a held-back one, reporting expectancy, planned reward-to-"
        "risk, volatility-normalised stop distance, parameter sensitivity and a "
        "named verdict per rule. "
        "'swing' (Milestone BW) replays the current production swing policy "
        "over a historical measurement window and, over the SAME facts at the "
        "same instants, replays pre-specified alternative policies beside it — "
        "chiefly variants of what the CONTEXT-role timeframe (1w under the "
        "production mapping) is allowed to do — reporting setups, trades, "
        "expectancy in R, profit factor, drawdown and what the weekly gate "
        "actually blocked. "
        "Every variant and every geometry is defined in code and fixed before "
        "any result is seen; none can be described on this command line. This "
        "command changes no production strategy, writes no trading record, and "
        "promotes nothing."
    ),
    configure=_configure_research,
    run=_run_research,
)


DASHBOARD_COMMAND = Command(
    name="dashboard",
    help="serve the read-only operator dashboard on this machine",
    description=(
        "Serve a local, read-only web page over everything FMITS already knows: "
        "the global market pulse, macro and cross-asset context, the swing "
        "decision workspace in its own order, the recorded portfolio, the "
        "simulator's paper trades, the deterministic statistics with the equity "
        "curve, and the state of every data source the refresh touched. "
        "Computes nothing: every figure was produced by an engine and is "
        "carried to the page unchanged, with its instant, its source and — "
        "where there is no figure — the reason there is none. Binds loopback "
        "and refuses any other address without --allow-public. Answers GET and "
        "HEAD only; it exposes no method that could place an order, record a "
        "trade, activate a paper trade or change any stored value. Reads the "
        "durable store and never writes to it. Runs until interrupted."
    ),
    configure=_configure_dashboard,
    run=_run_dashboard,
)


#: The single registry. `build_parser` and `main` both read it, so a command
#: cannot exist in the parser without a runner, or vice versa.
COMMANDS: tuple[Command, ...] = (
    FACTS_COMMAND,
    MTF_COMMAND,
    REGIME_COMMAND,
    SWING_COMMAND,
    SETUP_COMMAND,
    EVIDENCE_COMMAND,
    SCAN_COMMAND,
    BACKTEST_COMMAND,
    DAILY_COMMAND,
    TODAY_COMMAND,
    WORKSPACE_COMMAND,
    PULSE_COMMAND,
    MACRO_COMMAND,
    PORTFOLIO_COMMAND,
    APPROVE_COMMAND,
    TRADE_COMMAND,
    SIMULATE_COMMAND,
    STATISTICS_COMMAND,
    PERFORMANCE_COMMAND,
    EXPECTANCY_COMMAND,
    EQUITY_COMMAND,
    TRADES_COMMAND,
    # The last of the read surfaces, and deliberately not after `archive`:
    # three guards pin `archive` as the final entry, and the dashboard is a
    # window over every command above it rather than a step that follows them.
    RESEARCH_COMMAND,
    DASHBOARD_COMMAND,
    ARCHIVE_COMMAND,
)


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, built separately so tests can exercise parsing alone."""
    parser = argparse.ArgumentParser(
        prog="fmits",
        description=(
            "Financial Market Intelligence & Trading System — deterministic "
            "market facts. Measurements only; no direction, ranking or advice."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = subcommands.add_parser(
            command.name, help=command.help, description=command.description
        )
        command.configure(subparser)
    return parser


def _reference_time(raw: str | None, *, omit: bool) -> datetime | None:
    """Resolve the age reference: explicit, omitted, or the wall clock."""
    if omit:
        return None
    if raw is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(
            "--reference-time must be timezone-aware, e.g. "
            "2026-08-01T09:00:00+00:00"
        )
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code rather than calling ``exit``.

    Returning instead of exiting keeps `main` testable: a test asserts the code
    and captures the output without a `SystemExit` to catch.
    """
    args = build_parser().parse_args(argv)
    runners = {command.name: command.run for command in COMMANDS}

    try:
        return runners[args.command](args)
    except (PipelineError, BinanceError, ValueError, TypeError) as error:
        # Precise messages already; re-wrapping would hide which stage failed.
        print(f"fmits: {type(error).__name__}: {error}")
        return EXIT_FAILURE
