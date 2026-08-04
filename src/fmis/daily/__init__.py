"""Deterministic Daily Workflow — the same analysis, across a daily universe.

    run_daily(symbols, reference_time=...)  ──►  DailyRun
                                                   └─ one SymbolResult per symbol
    render_daily_run(run)  ──►  compact readiness index

**One command, many symbols, nothing lost.** Every requested symbol produces
exactly one result in the order it was requested. A symbol whose provider failed
carries its failure and the run continues, because one instrument's outage is not
a reason to discard the rest.

**A readiness index, not a ranking.** Rows are never reordered by any property of
the analysis. `fmis.decision_context` decides whether an analysis rests on enough
data, and that is all a row says: `SUFFICIENT` is not an opportunity, and a list
sorted by it would read as a list of picks however it were labelled. No score, no
direction, no recommendation — asserted over every public name and every string
this package can produce.

**It adds no engine.** Each symbol goes through `workspace_for_symbol`, the same
root `fmits swing` uses, so a daily row and a full page are produced by identical
code.

**The model is not the page.** `DailyRun` is a first-class object; the terminal
renderer is one consumer, and a future Telegram, JSON or persistence consumer
reads the same instance without any of them re-deriving anything.
"""

from __future__ import annotations

from fmis.daily.models import (
    DAILY_SCHEMA_VERSION,
    MAXIMUM_SYMBOLS,
    DailyRun,
    DailyRunError,
    FailureKind,
    ResultCategory,
    SymbolFailure,
    SymbolResult,
    require_symbols,
)
from fmis.daily.render import CATEGORY_GLYPH, render_daily_run
from fmis.daily.runner import DAILY_LIMITATIONS, analyse_symbol, run_daily

__all__ = [
    "run_daily",
    "analyse_symbol",
    "render_daily_run",
    "DailyRun",
    "SymbolResult",
    "SymbolFailure",
    "ResultCategory",
    "FailureKind",
    "require_symbols",
    "CATEGORY_GLYPH",
    "DAILY_LIMITATIONS",
    "DAILY_SCHEMA_VERSION",
    "MAXIMUM_SYMBOLS",
    "DailyRunError",
]
