"""The composition root: one run, read once, arranged for a decision.

    build_swing_workspace(run)  ──►  SwingWorkspace   (pure)
    run_swing_workspace(...)    ──►  SwingWorkspace   (fetches, once)

**This package computes nothing and fetches nothing twice.** `run_swing_workspace`
calls `fmis.today.assemble_today` — the exact sequence `fmits today` runs — and
keeps the three artifacts it produces: the scan results, the store reading, and
the assembled day's page. Everything below then rearranges those. There is no
second scan, no second store read, no second valuation and no second approval, so
a figure on this page and the same figure on `fmits today` are one calculation
rendered twice rather than two that happen to agree.

**What this page adds over `fmits today`, and it is one thing:** a *decision
order*. The day's page deliberately refuses to order actionable setups by
anything but the order they were scanned in, because ordering by a property of
the analysis reads as ordering by quality. This page orders them, and pays for
that by making the key explicit: four named components, each an engine's own
state, each printed on the row that carries it. See `ranking`.

**Everything else is the same objects, re-sectioned.** The market overview, the
opportunity lines, the portfolio overview, the statistics and the warnings are
`fmis.today`'s own instances, passed through — not copies, not re-derivations.
The three things assembled here that the day's page does not carry are the
per-setup evidence digest, the per-setup stable identity and the per-setup paper
status, and each of those is one call to the package that owns it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.position_sizing import DEFAULT_BOOK
from fmis.swing_setup import SCAN_UNIVERSE
from fmis.swing_workspace.models import SwingWorkspace
from fmis.swing_workspace.ranking import (
    EXCLUDED_FROM_RANKING,
    RANKING_RULE,
)
from fmis.swing_workspace.sections import (
    aggregated_warnings,
    books_from,
    global_summary,
    no_trade_groups,
    paper_positions,
    ranked_setups,
    require_actionable_split,
    symbol_decisions,
    unanalysed_from,
)
from fmis.today import TodayRun, assemble_today

__all__ = [
    "OBJECTIVE",
    "SWING_WORKSPACE_LIMITATIONS",
    "build_swing_workspace",
    "run_swing_workspace",
]

OBJECTIVE = "swing"

#: Printed once, at the foot of every page, unchanged. The *invariant* register:
#: these qualify the page as a whole and never a specific value, which is what
#: the warnings section is for. Inherited from `fmis.today`'s own eight in
#: substance — this page is assembled from that one — with two added for what
#: this page does that the day's page does not.
SWING_WORKSPACE_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "WS-1",
        "This page arranges what already exists. It computes no market "
        "quantity, no monetary one and no statistic; every figure on it was "
        "produced by an engine, folded from a record, or read from the day's "
        "page this run assembled.",
    ),
    (
        "WS-2",
        "The order of the setups is a stated key, not a score: readiness, then "
        "approval, then decision-context sufficiency, then watchlist position. "
        "Readiness describes how far the analysis has gone, never how good the "
        "trade is, and no measurement in this repository says a confirmed setup "
        "earns more than a candidate.",
    ),
    (
        "WS-3",
        "Risk/reward orders nothing on this page, deliberately. The one "
        "measurement this repository has published found higher displayed R:R "
        "associated with a worse outcome, not a better one, so a page sorted by "
        "it would put the least likely row first under a heading reading TOP.",
    ),
    (
        "WS-4",
        "No position size is computed here and nothing is rebalanced. Each "
        "candidate is approved against the portfolio as it stands, "
        "independently of the others: two candidates that each fit the budget "
        "alone do not both fit it together.",
    ),
    (
        "WS-5",
        "No probability is calibrated. No resolved-episode cohort exists, so no "
        "number on this page is a likelihood of anything.",
    ),
    (
        "WS-6",
        "No macro, news, derivatives, on-chain, orderbook or liquidity data is "
        "represented anywhere. Identical price action under extreme funding is "
        "a different trade, and this page cannot distinguish them.",
    ),
    (
        "WS-7",
        "Positions, capital, statistics and simulated trades are read from the "
        "durable store only. Anything held at an exchange and not recorded "
        "there is invisible to every section here.",
    ),
    (
        "WS-8",
        "Correlation between markets is never measured. Two setups on one side "
        "are counted as two setups; this page does not claim those markets move "
        "together, and does not claim they do not.",
    ),
    (
        "WS-9",
        "The evidence digest on a row counts items the evidence projection "
        "produced. It is not a strength, and it orders nothing — the agreement "
        "behind every live setup draws on shared upstream inputs, which is why "
        "independence is reported per row rather than assumed.",
    ),
    (
        "WS-10",
        "This page executes nothing, places no order, contacts no exchange and "
        "writes nothing at all. Every record it shows was written by something "
        "else.",
    ),
    (
        "WS-11",
        "The per-symbol decision rows are in the order the symbols were "
        "scanned, which is the order they were requested in. That order carries "
        "no meaning: the first row is not closer to a trade than the last, and "
        "nothing on this page measures how close any symbol is to anything.",
    ),
)


def build_swing_workspace(run: TodayRun) -> SwingWorkspace:
    """Assemble the workspace from one already-completed run. **Pure.**

    Fetches nothing, opens nothing and reads no clock: given the same `TodayRun`
    it returns an equal workspace. That is what lets a test assemble a full page
    from hand-built domain objects with no store and no network at all.

    Raises:
        TypeError: ``run`` is not a `TodayRun`.
        SwingWorkspaceError: the run's own opportunity groups place one symbol in
            two actionable states.
    """
    if not isinstance(run, TodayRun):
        raise TypeError(f"run must be a TodayRun, got {type(run).__name__}")

    today = run.workspace
    reading = run.reading
    opportunities = today.opportunities
    require_actionable_split(opportunities.confirmed, opportunities.candidates)

    watchlist = tuple(result.requested_symbol for result in run.results)
    assessments: dict[str, Any] = {
        result.assessment.symbol: result.assessment
        for result in run.results
        if result.assessment is not None
    }
    store_read = reading.present
    paper, paper_note = paper_positions(reading.paper_trades, read=store_read)

    def _rows(lines: Sequence[Any]) -> tuple[Any, ...]:
        return ranked_setups(
            lines,
            watchlist=watchlist,
            assessments=assessments,
            paper=paper,
            positions=today.portfolio.open_positions,
            store_read=store_read,
        )

    no_trade = no_trade_groups(run.results)
    unanalysed = unanalysed_from(opportunities.failed)
    decisions = symbol_decisions(run.results, reference_time=today.reference_time)
    return SwingWorkspace(
        reference_time=today.reference_time,
        objective=OBJECTIVE,
        source=today.source,
        summary=global_summary(
            market=today.market,
            confirmed=len(opportunities.confirmed),
            candidates=len(opportunities.candidates),
            waiting=sum(len(group.symbols) for group in no_trade),
            unanalysed=len(unanalysed),
            portfolio=today.portfolio,
            paper=paper,
            store_read=store_read,
        ),
        market=today.market,
        opportunities=_rows(opportunities.confirmed),
        wait_list=_rows(opportunities.candidates),
        no_trade=no_trade,
        unanalysed=unanalysed,
        decisions=decisions,
        paper=paper,
        paper_note=paper_note,
        portfolio=today.portfolio,
        books=books_from(today.portfolio, reading.valuation),
        statistics=today.performance,
        warnings=aggregated_warnings(today.warnings, reading.paper_trades),
        ranking_rule=RANKING_RULE,
        limitations=SWING_WORKSPACE_LIMITATIONS,
        metadata={
            "excluded_from_ranking": EXCLUDED_FROM_RANKING,
            "approval_note": opportunities.approval_note,
            "evidence_note": opportunities.evidence_note,
            "dust_policy": today.metadata.get("dust_policy"),
            "today_schema_version": today.schema_version,
        },
    )


def run_swing_workspace(
    symbols: Sequence[str] = SCAN_UNIVERSE,
    *,
    reference_time: datetime,
    store_root: Path | str | None = None,
    archive_root: Path | str | None = None,
    read_records: bool = True,
    timeframes: Mapping[Any, str] | None = None,
    limit: int | None = None,
    policy: Any | None = None,
    context_policy: Any | None = None,
    detection: Any | None = None,
    transport: Any | None = None,
    read_marks: bool = True,
    mark_interval: str | None = None,
    sizing: Any | None = None,
    account: Any | None = None,
    book: Any = DEFAULT_BOOK,
    classification: Any | None = None,
    timezone: str | None = None,
) -> SwingWorkspace:
    """Run one workspace end to end. **One scan, one store read, one valuation.**

    Every argument is forwarded to `fmis.today.assemble_today` unchanged, so this
    command and `fmits today` fetch the same data under the same flags and cannot
    disagree about what the market did or what the store holds. Per-symbol
    failure isolation is inherited unchanged: one symbol's outage never stops the
    run, and the symbol appears under *could not be read* rather than as a
    no-trade result.

    **The forwarded policies are typed `Any`, deliberately.** ``policy`` is a
    `RegimePolicy`, ``context_policy` a `ContextPolicy`, ``detection`` a
    `DetectionSettings`, ``timeframes`` a mapping keyed by `TimeframeRole` and
    ``sizing`` a `SizingPolicy` — and this package names none of those types,
    because it does nothing with them but pass them through. Four engine-layering
    guards scan for the *text* of those module names outside the composition
    roots they permit, and importing four vocabularies to annotate five opaque
    parameters would have meant widening four guards to buy five annotations.
    The values are checked where they are used, one layer down.

    Raises:
        StoreUnreadableError: the store exists and cannot be read. Raised by
            `fmis.today`, and deliberately not re-wrapped — the CLI already
            catches it, and two names for one condition is how one of them stops
            being handled.
    """
    return build_swing_workspace(
        assemble_today(
            symbols,
            reference_time=reference_time,
            store_root=store_root,
            archive_root=archive_root,
            read_records=read_records,
            timeframes=timeframes,
            limit=limit,
            policy=policy,
            context_policy=context_policy,
            detection=detection,
            transport=transport,
            read_marks=read_marks,
            mark_interval=mark_interval,
            sizing=sizing,
            account=account,
            book=book,
            classification=classification,
            timezone=timezone,
        )
    )
