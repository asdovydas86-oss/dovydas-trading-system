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
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

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
from fmis.pipeline.market_analysis import PipelineError
from fmis.daily import DailyRun, DailyRunError, render_daily_run, run_daily
from fmis.market_regime import RegimePolicy
from fmis.swing_setup import (
    BacktestError,
    DEFAULT_BACKTEST_DAYS,
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
from fmis.today import TodayError, render_today, run_today
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
    note_request_from_text,
    open_store,
    record_request_from_text,
    record_trade,
    render_listing,
    render_outcome,
    render_trade,
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
        else:
            print(f"fmits setup: {result.requested_symbol}: {result.failure}", file=sys.stderr)
    return _exit_code_for(results)


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
        )
    except TodayError as error:
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

#: The single registry. `build_parser` and `main` both read it, so a command
#: cannot exist in the parser without a runner, or vice versa.
COMMANDS: tuple[Command, ...] = (
    FACTS_COMMAND,
    MTF_COMMAND,
    REGIME_COMMAND,
    SWING_COMMAND,
    SETUP_COMMAND,
    SCAN_COMMAND,
    BACKTEST_COMMAND,
    DAILY_COMMAND,
    TODAY_COMMAND,
    PORTFOLIO_COMMAND,
    TRADE_COMMAND,
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
