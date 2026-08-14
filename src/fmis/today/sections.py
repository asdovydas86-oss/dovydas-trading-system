"""Adapting what already exists into the workspace's seven sections.

**Nothing in this module computes a market quantity or a monetary one.** Every
value it produces is either read straight off a `SetupAssessment` that
`fmis.swing_setup` already composed, or off a domain record the store already
holds. Where a value would require a computation this product cannot perform —
open risk without marks, a portfolio total without a valuation — the section
carries an `NotAvailable` naming the missing input and the inference its absence
forbids, rather than a zero.

**The market half and the owner half are read separately and never mixed.** The
scan adapters below see no position and no balance; the store adapters see no
candle and no assessment. That separation is the repository's own rule — *"the
market half never reads the trading half, or the analysis becomes a function of
the position"* — and here it costs nothing to keep, because the two families
meet only in `TodayWorkspace` itself.

**Grouping, never reordering.** `waiting` groups symbols by the engine's own
verbatim `thesis[0]`, exactly as `fmis.swing_setup.scan_report` does; every
other tuple preserves scan order. The one `sorted()` call in this package
orders wait *groups* by how many symbols reached each reason — a distribution
over already-stated reasons, not a ranking of opportunities — and ties keep
scan order because `sorted` is stable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fmis.today.models import (
    AnalysisLine,
    AnalysisSummary,
    ClosedPositionLine,
    FailedSymbol,
    JournalLine,
    JournalSummary,
    LimitLine,
    MarketOverview,
    Opportunities,
    OpportunityLine,
    PortfolioOverview,
    PositionLine,
    TodayError,
    NotAvailable,
    WaitGroup,
)

__all__ = [
    "REGIME_NOTE",
    "RECENT_LIMIT",
    "opportunities_from_results",
    "market_overview_from_results",
    "portfolio_overview",
    "journal_summary",
    "analysis_summary",
]

#: Printed under the market section, where a Bull/Bear/Neutral headline would
#: otherwise sit. It is a sentence rather than a silence because a missing
#: headline reads as an oversight, and this one is a contract.
REGIME_NOTE = (
    "No single bull/bear/neutral label is produced. A regime here is an "
    "environment with three separate dimensions (structure, volatility, "
    "participation) and is never collapsed into a direction — ADR-0025. What is "
    "shown instead is the distribution of what the engine actually concluded, "
    "per symbol."
)

#: How many recent records each memory section shows. A page nobody scrolls is a
#: page whose later sections are never read; five is the count that fits beside
#: everything above it without pushing the priority queue off a terminal.
RECENT_LIMIT = 5

#: The engine's own state values, spelled once. Compared as strings rather than
#: imported as enum members, because `OpportunityLine` already carries
#: `SetupState.value` and reaching back into the engine for the enum would give
#: this package a second place the vocabulary lives.
_WAIT = "wait"
_CANDIDATE = "candidate"
_CONFIRMED = "confirmed"
_ERROR = "error"
_STATUS_ORDER = (_WAIT, _CANDIDATE, _CONFIRMED, _ERROR)

#: `ContextState.INSUFFICIENT.value` — the state that means the analysis was not
#: classifiable, as opposed to classified and declined.
_INSUFFICIENT = "insufficient"

#: The bucket a symbol falls in when the engine reached no directional verdict.
#: Named here so the breadth table has a label for it without this module ever
#: naming a side.
_ABSENT_DIRECTION = "no direction"


def _state_of(assessment: Any) -> str:
    return assessment.state.value


def _line_from(assessment: Any) -> OpportunityLine:
    """One `SetupAssessment`, reduced to what this workspace shows.

    Values are copied, never recomputed. `risk_reward` is the engine's own
    ratio; `stop` and `target` are the prices of real detected `PriceLevel`
    objects it selected, or `None` where it selected none.
    """
    return OpportunityLine(
        symbol=assessment.symbol,
        state=_state_of(assessment),
        sufficiency=assessment.sufficiency.value,
        direction=None if assessment.direction is None else assessment.direction.value,
        risk_reward=None
        if assessment.risk_reward is None
        else assessment.risk_reward.ratio,
        stop=None if assessment.stop is None else assessment.stop.price,
        target=None if not assessment.targets else assessment.targets[0].price,
        thesis=assessment.thesis,
        confirmation=assessment.confirmation,
        invalidation=assessment.invalidation,
    )


def _assessed(results: Sequence[Any]) -> tuple[Any, ...]:
    return tuple(
        result.assessment for result in results if result.assessment is not None
    )


def opportunities_from_results(results: Sequence[Any]) -> Opportunities:
    """Group one scan's results by the engine's own state.

    Raises:
        TodayError: ``results`` is empty. A workspace over no symbols is a
            caller error rather than a quiet market.
    """
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise TypeError("results must be a non-string sequence")
    if not results:
        raise TodayError(
            "at least one scan result is required; an empty universe is a caller "
            "error, not a morning with nothing in it"
        )

    confirmed: list[OpportunityLine] = []
    candidates: list[OpportunityLine] = []
    wait_groups: dict[str, list[str]] = {}
    failed: list[FailedSymbol] = []

    for result in results:
        assessment = result.assessment
        if assessment is None:
            # `SetupRunResult` guarantees a failure string whenever there is no
            # assessment, so the read is unconditional. What it does *not*
            # guarantee is that the string says anything: a provider message
            # that is present but blank passes every check upstream and then
            # fails `FailedSymbol`'s own non-empty check, taking the whole page
            # down over one symbol's unhelpful error text. The per-symbol
            # isolation this workspace inherits is worth nothing if a whitespace
            # string can defeat it.
            reported = result.failure.strip()
            failed.append(
                FailedSymbol(
                    symbol=result.requested_symbol,
                    detail=reported or "no reason was reported",
                )
            )
            continue
        state = _state_of(assessment)
        if state == _CONFIRMED:
            confirmed.append(_line_from(assessment))
        elif state == _CANDIDATE:
            candidates.append(_line_from(assessment))
        else:
            reason = (
                assessment.thesis[0] if assessment.thesis else "no reason stated"
            )
            wait_groups.setdefault(reason, []).append(result.requested_symbol)

    ordered_groups = sorted(
        wait_groups.items(), key=lambda item: len(item[1]), reverse=True
    )
    return Opportunities(
        confirmed=tuple(confirmed),
        candidates=tuple(candidates),
        waiting=tuple(
            WaitGroup(reason=reason, symbols=tuple(symbols))
            for reason, symbols in ordered_groups
        ),
        failed=tuple(failed),
    )


def _breadth(results: Sequence[Any]) -> tuple[tuple[str, int], ...]:
    """How many symbols the engine placed on each side, and how many on none.

    A count, never a verdict. The label for a side is the engine's own
    `Direction.value`, read at runtime — this module names no side of its own.
    """
    counts: dict[str, int] = {}
    for assessment in _assessed(results):
        key = (
            _ABSENT_DIRECTION
            if assessment.direction is None
            else assessment.direction.value
        )
        counts[key] = counts.get(key, 0) + 1
    return tuple(counts.items())


def market_overview_from_results(
    results: Sequence[Any], opportunities: Opportunities
) -> MarketOverview:
    """What the market is doing, entirely from facts the scan already produced.

    ``readable_declined`` and ``unreadable`` split the `WAIT` population on the
    engine's own sufficiency judgement: a symbol whose decision context was
    insufficient was not classified, and one whose context was sufficient or
    limited was read and declined. Shown as one number, a quiet system and a
    quiet market are indistinguishable.
    """
    if not isinstance(opportunities, Opportunities):
        raise TypeError("opportunities must be an Opportunities")

    declined: list[str] = []
    unreadable: list[str] = []
    for result in results:
        assessment = result.assessment
        if assessment is None or _state_of(assessment) != _WAIT:
            continue
        target = (
            unreadable if assessment.sufficiency.value == _INSUFFICIENT else declined
        )
        target.append(result.requested_symbol)

    assessments = _assessed(results)
    counts = {
        _WAIT: opportunities.waiting_count,
        _CANDIDATE: len(opportunities.candidates),
        _CONFIRMED: len(opportunities.confirmed),
        _ERROR: len(opportunities.failed),
    }

    observations: list[str] = []
    if not opportunities.actionable_count:
        observations.append(
            "No actionable setup exists anywhere in the scanned watchlist. "
            "WAIT is a successful result, not a failure."
        )
    if unreadable and not declined:
        observations.append(
            "Every symbol that reached WAIT did so because the engine could not "
            "classify it, not because it read it and declined."
        )
    if opportunities.failed:
        observations.append(
            f"{len(opportunities.failed)} symbol(s) produced no analysis at all "
            "and are absent from every count above except ERROR."
        )

    return MarketOverview(
        scanned=len(results),
        status_counts=tuple((label, counts[label]) for label in _STATUS_ORDER),
        breadth=_breadth(results),
        readable_declined=tuple(declined),
        unreadable=tuple(unreadable),
        observations=tuple(observations),
        regime_note=REGIME_NOTE,
        analysis_as_of=assessments[0].as_of if assessments else None,
    )


def _position_line(position: Any) -> PositionLine:
    return PositionLine(
        market=position.market.value,
        book=position.book.value,
        direction=position.direction.value,
        quantity=f"{position.net_quantity.text} {position.net_quantity.asset}",
        average_entry=position.average_entry.arithmetic,
        opened_at=position.opened_at,
        trade_count=position.trade_count,
        event_ids=position.event_ids,
    )


def _limit_line(limit: Any, unmeasurable: NotAvailable) -> LimitLine:
    """One configured limit, with nothing measured against it.

    Deriving open risk, concentration and cluster exposure needs positions,
    marks and a valued portfolio snapshot wired together, and no mark source
    exists. `NotAvailable` is used rather than a zero or a `WITHIN`, because
    *"indeterminate must be visually distinct from within"* and the cheapest way
    to keep it distinct is to make it a different type.
    """
    return LimitLine(
        limit_id=limit.limit_id,
        scope=limit.scope.value,
        stated_limit=f"{limit.value} {limit.unit.value}",
        severity=limit.severity.value,
        current=unmeasurable,
        status=unmeasurable,
    )


def portfolio_overview(
    *,
    store_root: str,
    store_present: bool,
    positions: Sequence[Any],
    budget: Any | None,
    snapshot: Any | None,
) -> PortfolioOverview:
    """What is held and what is committed, from the store and nowhere else.

    ``budget`` is the `RiskBudget` in force, or `None` when none is. ``snapshot``
    is the latest `PortfolioSnapshot`, or `None` when none has been taken. Both
    absences are rendered with their reason rather than collapsed into an empty
    section.
    """
    unmeasurable = NotAvailable(
        reason=(
            "open risk needs a mark for every holding and a stop for every open "
            "position; no mark source exists and no plan is recorded"
        ),
        owned_by="the risk layer (roadmap C4/C6)",
        forbidden_inference=(
            "Do not read this as risk being within budget. Nothing was measured."
        ),
    )

    if budget is None:
        budget_note: str | NotAvailable = NotAvailable(
            reason="no risk budget generation is in force at this instant",
            owned_by="the owner — every limit is a value the owner sets",
            forbidden_inference=(
                "Do not infer that no limit applies to you. It means no limit "
                "is recorded here."
            ),
        )
        limits: tuple[LimitLine, ...] = ()
    else:
        budget_note = (
            f"budget {budget.budget_id} · policy version "
            f"{budget.risk_policy_version} · in force from "
            f"{budget.effective_from.isoformat()}"
        )
        limits = tuple(_limit_line(limit, unmeasurable) for limit in budget.limits)

    if snapshot is None:
        valuation: str | NotAvailable = NotAvailable(
            reason="no portfolio snapshot has been taken",
            owned_by="the portfolio layer (roadmap C6)",
            forbidden_inference=(
                "Do not read an absent balance as a zero balance, or as a "
                "balance this system has checked."
            ),
        )
        cash: str | NotAvailable = valuation
        exposure: str | NotAvailable = valuation
        snapshot_as_of = None
    else:
        cash = " · ".join(
            f"{balance.amount.text} {balance.amount.asset}" for balance in snapshot.cash
        ) or "no cash balance recorded"
        exposure = (
            f"gross {snapshot.exposure.gross.text} "
            f"{snapshot.exposure.gross.asset} · net "
            f"{snapshot.exposure.net.text} {snapshot.exposure.net.asset}"
        )
        snapshot_as_of = snapshot.as_of

    return PortfolioOverview(
        store_root=store_root,
        store_present=store_present,
        open_positions=tuple(_position_line(position) for position in positions),
        limits=limits,
        budget_note=budget_note,
        committed_risk=unmeasurable,
        available_risk=unmeasurable,
        cash=cash,
        exposure=exposure,
        snapshot_as_of=snapshot_as_of,
    )


def _journal_line(entry: Any) -> JournalLine:
    title = entry.title if isinstance(entry.title, str) else "(no title)"
    return JournalLine(
        entry_id=entry.entry_id,
        kind=entry.kind.value,
        recorded_at=entry.recorded_at,
        author=entry.author,
        title=title,
        recollection=entry.recollection,
    )


def _closed_line(position: Any) -> ClosedPositionLine:
    return ClosedPositionLine(
        market=position.market.value,
        book=position.book.value,
        closed_at=position.closed_at,
        realized_net=(
            f"{position.realized_pnl_net.text} {position.realized_pnl_net.asset}"
        ),
        trade_count=position.trade_count,
    )


def journal_summary(
    *,
    entries: Sequence[Any],
    closed_positions: Sequence[Any],
    decisions: Sequence[str],
) -> JournalSummary:
    """Recent decisions, recently closed positions, and the latest notes.

    ``entries`` and ``closed_positions`` arrive oldest-first from the store and
    the fold; the most recent `RECENT_LIMIT` of each are kept, and the slice is
    taken from the end rather than sorted, so nothing here reorders records the
    store already ordered deterministically.
    """
    recent_entries = tuple(entries)[-RECENT_LIMIT:]
    recent_closed = tuple(closed_positions)[-RECENT_LIMIT:]
    note: str | NotAvailable
    if recent_entries or recent_closed or decisions:
        note = (
            f"{len(entries)} journal entr(ies) and {len(closed_positions)} closed "
            f"position(s) are recorded; the most recent {RECENT_LIMIT} of each "
            "are shown."
        )
    else:
        note = NotAvailable(
            reason="the store holds no journal entries and no closed positions",
            owned_by="the journal slice, and the owner writing in it",
            forbidden_inference=(
                "Do not read this as a quiet month. It means nothing was "
                "written down."
            ),
        )
    return JournalSummary(
        entries=tuple(_journal_line(entry) for entry in recent_entries),
        closed_positions=tuple(_closed_line(p) for p in recent_closed),
        decisions=tuple(decisions),
        note=note,
    )


def _archive_line(entry: Any) -> AnalysisLine:
    return AnalysisLine(
        record_id=entry.record_id,
        record_type=entry.record_type.value,
        subject=" ".join(entry.subject),
        analysis_as_of=entry.analysis_as_of,
    )


def _citation_line(record: Any) -> AnalysisLine:
    return AnalysisLine(
        record_id=record.record_id,
        record_type=record.record_type,
        subject=record.subject_label,
        analysis_as_of=record.analysis_as_of,
    )


def _snapshot_line(snapshot: Any) -> AnalysisLine:
    return AnalysisLine(
        record_id=snapshot.snapshot_id,
        record_type="market_snapshot",
        subject=snapshot.market.value,
        analysis_as_of=snapshot.built_at,
    )


def analysis_summary(
    *,
    archived: Sequence[Any],
    citations: Sequence[Any],
    snapshots: Sequence[Any],
) -> AnalysisSummary:
    """What FMITS has durably recorded about its own past analyses.

    Metadata only — no archived payload is opened here, which is the property
    that keeps this section cheap however large the archive becomes.

    ``change_note`` states what a comparison would need and does not perform
    one. Two archived pages differ in ways that require decoding both payloads
    and defining what a difference *is*; neither exists, and a page that claimed
    a comparison it had not run would be worse than one that says so.
    """
    recent_archived = tuple(archived)[-RECENT_LIMIT:]
    recent_citations = tuple(citations)[-RECENT_LIMIT:]
    recent_snapshots = tuple(snapshots)[-RECENT_LIMIT:]

    total = len(archived) + len(citations) + len(snapshots)
    change_note: str | NotAvailable
    if not total:
        change_note = NotAvailable(
            reason=(
                "no analysis has been archived, cited or captured, so there is "
                "nothing to compare today's scan against"
            ),
            owned_by="fmis.archive (run any analysis with --archive)",
            forbidden_inference=(
                "Do not read this as nothing having changed since yesterday."
            ),
        )
    elif total == 1:
        change_note = (
            "One durable analysis artifact exists. A change needs two "
            "observations of the same subject; there is one."
        )
    else:
        change_note = (
            f"{total} durable analysis artifact(s) exist. What changed between "
            "any two of them is not computed here: comparing two archived "
            "analyses requires decoding both payloads and defining what a "
            "difference is, and neither exists yet."
        )

    return AnalysisSummary(
        archived=tuple(_archive_line(entry) for entry in recent_archived),
        citations=tuple(_citation_line(record) for record in recent_citations),
        snapshots=tuple(_snapshot_line(snapshot) for snapshot in recent_snapshots),
        change_note=change_note,
    )
