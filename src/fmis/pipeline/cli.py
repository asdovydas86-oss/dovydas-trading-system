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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from fmis.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from fmis.pipeline.market_analysis import PipelineError
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.render import render_fact_sheet, render_multi_timeframe_sheet
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
COMMANDS: tuple[Command, ...] = (FACTS_COMMAND, MTF_COMMAND)


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
