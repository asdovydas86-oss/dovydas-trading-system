"""Command-line entry point — the repository's first product surface.

    fmits facts BTCUSDT
    fmits facts ETHUSDT --interval 1d --limit 300
    python -m fmis.pipeline facts BTCUSDT

One subcommand, ``facts``, which fetches candles and prints a
`StructuralFactSheet`. It exists so the deterministic engines can be *read* by a
human, which until now nothing allowed.

**The CLI holds no logic.** It parses arguments, calls one composition root,
renders the result, and maps failures to exit codes. Every number it prints was
produced by an engine; adding a calculation here would put market logic in the
one layer with no tests over market behaviour.

**This is where the clock lives.** Everything beneath is a pure function of its
inputs, so `structural_facts_for_symbol` never reads the time. Data *age* needs a
reference instant, and this — the outermost edge — is the only correct place to
take one. The ``--reference-time`` flag makes even that injectable, so the
rendered output can be pinned in a test.

Exit codes: ``0`` success · ``1`` a data or provider failure the user can act on
· ``2`` bad usage (argparse's own convention).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Sequence

from fmis.market_structure import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from fmis.pipeline.market_analysis import PipelineError
from fmis.pipeline.render import render_fact_sheet
from fmis.pipeline.structural_facts import (
    DetectionSettings,
    structural_facts_for_symbol,
)
from fmis.providers.binance import BinanceError

__all__ = ["main", "build_parser"]

_DEFAULT_INTERVAL = "4h"

#: Exit codes. Kept as names so the tests assert intent rather than integers.
EXIT_OK = 0
EXIT_FAILURE = 1


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

    facts = subcommands.add_parser(
        "facts",
        help="print the deterministic fact sheet for one symbol",
        description=(
            "Fetch public candles for SYMBOL and print every deterministic fact "
            "the system can compute: indicators, market structure, levels, "
            "breaks, changes of character, warm-up status and limitations."
        ),
    )
    facts.add_argument("symbol", help="exact provider symbol, e.g. BTCUSDT")
    facts.add_argument(
        "-i",
        "--interval",
        default=_DEFAULT_INTERVAL,
        help=f"candle interval (default: {_DEFAULT_INTERVAL})",
    )
    facts.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="number of candles to request (default: provider default)",
    )
    facts.add_argument(
        "--left-bars",
        type=int,
        default=DEFAULT_LEFT_BARS,
        help=f"swing detection left neighbours (default: {DEFAULT_LEFT_BARS})",
    )
    facts.add_argument(
        "--right-bars",
        type=int,
        default=DEFAULT_RIGHT_BARS,
        help=(
            f"swing detection right neighbours (default: {DEFAULT_RIGHT_BARS}). "
            "Also used as the break-confirmation delay — one value, both uses, "
            "so they cannot disagree (ADR-0020 D1)."
        ),
    )
    facts.add_argument(
        "--reference-time",
        default=None,
        metavar="ISO8601",
        help=(
            "instant to measure data age against (default: now). Supply it to "
            "make the rendered output reproducible."
        ),
    )
    facts.add_argument(
        "--no-age",
        action="store_true",
        help="omit the data-age line entirely",
    )
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

    try:
        reference = _reference_time(args.reference_time, omit=args.no_age)
        sheet = structural_facts_for_symbol(
            args.symbol,
            args.interval,
            limit=args.limit,
            detection=DetectionSettings(
                left_bars=args.left_bars, right_bars=args.right_bars
            ),
        )
    except (PipelineError, BinanceError, ValueError, TypeError) as error:
        # Precise messages already; re-wrapping would hide which stage failed.
        print(f"fmits: {type(error).__name__}: {error}")
        return EXIT_FAILURE

    print(render_fact_sheet(sheet, reference_time=reference))
    return EXIT_OK
