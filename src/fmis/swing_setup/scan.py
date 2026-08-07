"""Market Scanner v1 — the fixed-universe orchestrator over `fmis.swing_setup`.

    run_market_scan(symbols=SCAN_UNIVERSE)  ──►  tuple[SetupRunResult, ...]
    render_scan(results)                    ──►  compact terminal table

**This module adds no engine, no policy and no ranking.** `run_market_scan` is
`run_setup_for_symbols` (Milestone AR) called with a default, hardcoded
universe — the same per-symbol failure isolation, the same composition root,
the same `SetupAssessment`. Nothing here is recomputed.

**Why a separate module from `compose.py`.** `run_setup_for_symbols` serves a
caller-supplied symbol list (`fmits setup SYMBOL...`); this module exists only
to name the fixed watchlist and to render it as a scan table rather than one
full page per symbol. Splitting it out keeps `compose.py` free of a hardcoded
symbol list that has nothing to do with the general multi-symbol contract.

**No ranking, no score, no probability.** Rows are printed in scan order —
the order `SCAN_UNIVERSE` lists them — never reordered by state, direction or
any other property of the result. `WAIT` is a successful result and is never
treated as, or counted with, `ERROR`.

This is one of the two locations ADR-0028 permits directional vocabulary
(`SIDE: LONG`/`SHORT`) to appear, because it is a direct child of
`fmis/swing_setup/`.
"""

from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

from fmis.decision_context import ContextPolicy
from fmis.market_regime import RegimePolicy
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport
from fmis.swing_setup.compose import SetupRunResult, run_setup_for_symbols
from fmis.swing_setup.models import SwingSetupError

__all__ = ["SCAN_UNIVERSE", "run_market_scan", "render_scan"]

#: A small, hardcoded list of major crypto pairs. Not fetched from Binance and
#: not configurable at the CLI: the scanner's whole point is one command over
#: one known watchlist, never a per-run symbol universe (that is `fmits setup`
#: / `fmits daily`, both of which already accept a caller-supplied list).
SCAN_UNIVERSE: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "DOTUSDT",
    "TRXUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "SUIUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "UNIUSDT",
    "LTCUSDT",
    "HBARUSDT",
)


def run_market_scan(
    symbols: Sequence[str] = SCAN_UNIVERSE,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
) -> tuple[SetupRunResult, ...]:
    """Assess every symbol in `symbols` (default: `SCAN_UNIVERSE`), isolated.

    A thin default-universe wrapper over `run_setup_for_symbols` — every
    isolation, ordering and error-propagation guarantee documented there
    applies unchanged. A symbol whose analysis fails produces a
    `SetupRunResult.failure` and does not stop the remaining symbols.

    Raises:
        TypeError: ``symbols`` is not a non-string sequence.
        ValueError: ``symbols`` is empty.
    """
    return run_setup_for_symbols(
        symbols,
        timeframes=timeframes,
        limit=limit,
        policy=policy,
        context_policy=context_policy,
        detection=detection,
        transport=transport,
        clock=clock,
        base_url=base_url,
    )


_WIDTH = 78
_ABSENT = "—"

_SYMBOL_WIDTH = 10
_STATUS_WIDTH = 10
_SIDE_WIDTH = 6
_RR_WIDTH = 6
_STOP_WIDTH = 13
_TARGET_WIDTH = 13


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _clip(value: str, width: int) -> str:
    """Fit a value to its column, marking the cut rather than hiding it.

    Same discipline the daily readiness index applies to its own columns: a
    value that silently overflows pushes every later column out of alignment.
    """
    return value if len(value) <= width else value[: width - 1] + "…"


def _price(value: float) -> str:
    """Format a price exactly as `fmis.swing_setup.render._number` does."""
    return f"{value:,.6g}"


def _status(result: SetupRunResult) -> str:
    if result.assessment is None:
        return "ERROR"
    return result.assessment.state.value.upper()


def _side(result: SetupRunResult) -> str:
    if result.assessment is None or result.assessment.direction is None:
        return _ABSENT
    return result.assessment.direction.value.upper()


def _risk_reward(result: SetupRunResult) -> str:
    if result.assessment is None or result.assessment.risk_reward is None:
        return _ABSENT
    return f"{result.assessment.risk_reward.ratio:,.2f}"


def _stop(result: SetupRunResult) -> str:
    if result.assessment is None or result.assessment.stop is None:
        return _ABSENT
    return _price(result.assessment.stop.price)


def _target(result: SetupRunResult) -> str:
    if result.assessment is None or not result.assessment.targets:
        return _ABSENT
    return _price(result.assessment.targets[0].price)


def _row(result: SetupRunResult) -> str:
    return (
        f" {_clip(result.requested_symbol, _SYMBOL_WIDTH):<{_SYMBOL_WIDTH}} "
        f"{_clip(_status(result), _STATUS_WIDTH):<{_STATUS_WIDTH}} "
        f"{_clip(_side(result), _SIDE_WIDTH):<{_SIDE_WIDTH}} "
        f"{_clip(_risk_reward(result), _RR_WIDTH):<{_RR_WIDTH}} "
        f"{_clip(_stop(result), _STOP_WIDTH):<{_STOP_WIDTH}} "
        f"{_clip(_target(result), _TARGET_WIDTH):<{_TARGET_WIDTH}}"
    ).rstrip()


def _header() -> list[str]:
    return [
        (
            f" {'SYMBOL':<{_SYMBOL_WIDTH}} {'STATUS':<{_STATUS_WIDTH}} "
            f"{'SIDE':<{_SIDE_WIDTH}} {'RR':<{_RR_WIDTH}} "
            f"{'STOP':<{_STOP_WIDTH}} {'TARGET':<{_TARGET_WIDTH}}"
        ).rstrip(),
        _rule(),
    ]


def render_scan(results: Sequence[SetupRunResult]) -> str:
    """Render a market scan as a compact plain-text table.

    Every requested symbol appears exactly once, in the order `results` lists
    them — never reordered by state, direction or any other property. A
    `TOP OPPORTUNITIES` section repeats, in the same order, only the rows
    whose state is `CANDIDATE` or `CONFIRMED`; it is omitted entirely when
    none exist.

    Raises:
        TypeError: ``results`` is not a sequence of `SetupRunResult`.
        ValueError: ``results`` is empty.
        SwingSetupError: a rendered line exceeded the page width — a defect in
            this module, raised rather than silently truncated further.
    """
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise TypeError(
            f"results must be a non-string sequence, got {type(results).__name__}"
        )
    for position, result in enumerate(results):
        if not isinstance(result, SetupRunResult):
            raise TypeError(
                f"results[{position}] must be a SetupRunResult, got "
                f"{type(result).__name__}"
            )
    if not results:
        raise ValueError("at least one result is required")

    counts: dict[str, int] = {"WAIT": 0, "CANDIDATE": 0, "CONFIRMED": 0, "ERROR": 0}
    for result in results:
        counts[_status(result)] += 1
    opportunities = [
        result for result in results if _status(result) in ("CANDIDATE", "CONFIRMED")
    ]

    lines: list[str] = [_rule("═")]
    lines.append(" FMITS MARKET SCANNER — fixed watchlist · not a ranking")
    lines.append(_rule("═"))
    lines.append(f" {len(results)} symbols scanned")
    lines.append("")
    lines.extend(_header())
    for result in results:
        lines.append(_row(result))
        if result.failure is not None:
            lines.extend(
                textwrap.wrap(
                    result.failure,
                    width=_WIDTH,
                    initial_indent="     ",
                    subsequent_indent="       ",
                )
            )
    lines.append(_rule())
    lines.append("")
    lines.append(
        f" {len(results)} scanned · {counts['WAIT']} WAIT · "
        f"{counts['CANDIDATE']} CANDIDATE · {counts['CONFIRMED']} CONFIRMED · "
        f"{counts['ERROR']} ERROR"
    )

    if opportunities:
        lines.append("")
        lines.append(_rule("═"))
        lines.append(" TOP OPPORTUNITIES")
        lines.append(_rule("═"))
        lines.extend(_header())
        for result in opportunities:
            lines.append(_row(result))
        lines.append(_rule())

    lines.append("")
    lines.append(" To read any symbol in full:")
    lines.append("     fmits setup SYMBOL")
    lines.append("")
    lines.append(_rule("═"))
    lines.append(" This is the fixed watchlist scanned in list order, not a ranking. No")
    lines.append(" score, probability or recommendation is computed. WAIT is a")
    lines.append(" successful result, not a failure. Position sizing is not computed.")
    lines.append(_rule("═"))

    for line in lines:
        if len(line) > _WIDTH:
            raise SwingSetupError(
                f"rendered line of {len(line)} exceeds the {_WIDTH}-column page: "
                f"{line!r}"
            )
    return "\n".join(lines)
