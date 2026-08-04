"""Rendering a `DailyRun` as a compact terminal index.

**This module only renders.** It computes no market quantity, makes no policy
decision, reorders nothing, and hides nothing. A test asserts it calls no runner
and no engine and imports only the model.

**Compact by design.** A full workspace is ~270 lines; twenty of them is four
thousand lines nobody reads, which is the alert fatigue `reports/0005` Phase 4
names as this milestone's principal risk. The index is one row per symbol, and
the footer says exactly how to open any single page in full.

**No colour is required.** Every state carries a word and a glyph, so the page
survives a pipe, a log file and a reader who cannot distinguish the colours a
terminal would use.
"""

from __future__ import annotations

import textwrap
from collections.abc import Mapping
from types import MappingProxyType

from fmis.daily.models import (
    DailyRun,
    DailyRunError,
    ResultCategory,
    SymbolResult,
)

__all__ = ["render_daily_run", "CATEGORY_GLYPH"]

#: Page width, matching the workspace's own contract so the two paste together.
_WIDTH = 78

_ABSENT = "—"

#: Column widths. The row is built from these rather than from literals, so the
#: header and the rows cannot drift apart, and every value is clipped to fit
#: before the page-width guard is ever reached.
_SYMBOL_WIDTH = 12
_REGIME_WIDTH = 30

#: Reporting order for the **summary counts only**. The rows themselves never
#: use it: they stay in the order the caller requested, because sorting a list
#: by readiness reads as sorting it by attractiveness however it is labelled.
_COUNT_ORDER: tuple[ResultCategory, ...] = (
    ResultCategory.SUFFICIENT,
    ResultCategory.LIMITED,
    ResultCategory.INSUFFICIENT,
    ResultCategory.FAILED,
)

#: A glyph **and** a word for every category, so nothing depends on colour.
CATEGORY_GLYPH: Mapping[ResultCategory, str] = MappingProxyType({
    ResultCategory.SUFFICIENT: "✓",
    ResultCategory.LIMITED: "◐",
    ResultCategory.INSUFFICIENT: "⧗",
    ResultCategory.FAILED: "✗",
})


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _row(label: str, value: str, note: str = "") -> str:
    left = f" {label}"
    pad = max(1, 30 - len(left) - len(value))
    line = f"{left}{' ' * pad}{value}"
    return f"{line}   {note}" if note else line


def _clip(value: str, width: int) -> str:
    """Fit a value to its column, marking the cut rather than hiding it.

    A value that silently overflows its column pushes every later column right
    and the row is then truncated at the page edge — which cuts a *later* value
    mid-character and leaves no sign that anything was lost. Clipping here means
    at most one value is shortened, and the ellipsis says which.
    """
    return value if len(value) <= width else value[: width - 1] + "…"


def _regime_summary(result: SymbolResult) -> str:
    """The regime string the composition root already reduced, or an absence."""
    return result.regime_summary or _ABSENT


def _as_of(result: SymbolResult) -> str:
    """The analysis instant, to the minute.

    Formatted rather than sliced: `isoformat()[:16]` would print a timestamp
    that *looks* whole while depending on the offset's length, and a time
    reading `08:0` is a value a reader parses as something it is not.
    """
    workspace = result.workspace
    return _ABSENT if workspace is None else workspace.as_of.strftime("%Y-%m-%d %H:%M")


def render_daily_run(run: DailyRun) -> str:
    """Render one daily run as a compact plain-text index.

    Every requested symbol appears, in the order it was requested, whatever
    happened to it. A failed symbol shows its reason on the row beneath it.

    Raises:
        TypeError: ``run`` is not a `DailyRun`.
        DailyRunError: a rendered line exceeded the page width. Rows are
            truncated and prose is wrapped, so this is a defect in this module
            rather than an unusual input, and it is raised rather than printed.
    """
    if not isinstance(run, DailyRun):
        raise TypeError(f"run must be a DailyRun, got {type(run).__name__}")

    lines: list[str] = [_rule("═")]
    lines.append(" FMITS DAILY WORKFLOW — readiness index · not a ranking")
    lines.append(_rule("═"))
    lines.append(_row("Reference time", run.reference_time.isoformat()))
    lines.append(_row("Objective", run.objective, run.source))
    lines.append(
        _row(
            "Symbols",
            str(run.requested_count),
            f"{run.completed_count} analysed · {run.failed_count} failed",
        )
    )
    counts = " · ".join(
        f"{category.value} {run.count_of(category)}" for category in _COUNT_ORDER
    )
    lines.extend(
        textwrap.wrap(
            counts,
            width=_WIDTH,
            initial_indent=" By readiness".ljust(30),
            subsequent_indent=" " * 30,
        )
    )

    lines.append("")
    lines.append(_rule())
    lines.append(
        f"   {'SYMBOL':<{_SYMBOL_WIDTH}} {'READINESS':<13} "
        f"{'REGIME':<{_REGIME_WIDTH}} AS OF"
    )
    lines.append(_rule())

    for result in run.results:
        glyph = CATEGORY_GLYPH[result.category]
        symbol = _clip(result.requested_symbol, _SYMBOL_WIDTH)
        regime = _clip(_regime_summary(result), _REGIME_WIDTH)
        row = (
            f" {glyph} {symbol:<{_SYMBOL_WIDTH}} "
            f"{result.category.value:<13} {regime:<{_REGIME_WIDTH}} {_as_of(result)}"
        )
        lines.append(row.rstrip())
        if result.failure is not None:
            lines.extend(
                textwrap.wrap(
                    f"{result.failure.kind.value}: {result.failure.detail}",
                    width=_WIDTH,
                    initial_indent="     ",
                    subsequent_indent="       ",
                )
            )

    lines.append(_rule())
    lines.append("")
    lines.append(" To read any symbol in full:")
    lines.append("     fmits swing SYMBOL")
    lines.append("")
    lines.append(_rule())
    lines.append(" LIMITATIONS")
    for code, text in run.limitations:
        head = f" [{code}] "
        lines.extend(
            textwrap.wrap(
                text, width=_WIDTH, initial_indent=head, subsequent_indent=" " * len(head)
            )
        )
    lines.append("")
    lines.append(_rule("═"))
    lines.append(" Readiness describes the analysis, not the instrument. No ranking,")
    lines.append(" direction or recommendation is expressed or implied.")
    lines.append(_rule("═"))

    # A terminal that wraps a row mid-value produces something a reader parses
    # as a different value. Rows are truncated and prose is wrapped above, so an
    # over-wide line here is a defect in this module rather than an odd input,
    # and it is raised rather than printed. Same guard, same reason, as the
    # workspace renderer's table check.
    for line in lines:
        if len(line) > _WIDTH:
            raise DailyRunError(
                f"rendered line of {len(line)} exceeds the {_WIDTH}-column page: "
                f"{line!r}"
            )
    return "\n".join(lines)
