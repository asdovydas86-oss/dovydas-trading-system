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
from datetime import datetime, timezone
from typing import Callable, Sequence

from fmis.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from fmis.pipeline.market_analysis import PipelineError
from fmis.daily import DailyRunError, render_daily_run, run_daily
from fmis.market_regime import RegimePolicy
from fmis.workspace import render_workspace, workspace_for_symbol
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


def _configure_swing(parser: argparse.ArgumentParser) -> None:
    _add_common_arguments(parser)
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
    return EXIT_OK


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
    return EXIT_OK


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
    DAILY_COMMAND,
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
