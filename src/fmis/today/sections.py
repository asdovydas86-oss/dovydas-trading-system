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

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from fmis.money import Money, canonical_decimal_text
from fmis.provenance import Absent
from fmis.statistics import (
    closed_between,
    duration_text,
    performance_statistics,
    recent_trades,
)
from fmis.trade_lifecycle import TradeLifecycleState
from fmis.today.models import (
    BookPerformance,
    PaperTradeLine,
    PaperTrading,
    PerformanceLine,
    PerformanceSummary,
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
    "paper_trading",
    "performance_summary",
    "PERFORMANCE_RECENT_LIMIT",
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

#: What a candidate the approval layer refused to build a proposal for shows as.
#: A word rather than a blank: a row whose approval column is empty reads as a
#: row nobody objected to, and this one had an objection so basic that no size
#: could be computed at all.
_NOT_SIZEABLE = "not sizeable"


def _state_of(assessment: Any) -> str:
    return assessment.state.value


def _line_from(assessment: Any, approval: Any = None) -> OpportunityLine:
    """One `SetupAssessment`, reduced to what this workspace shows.

    Values are copied, never recomputed. `risk_reward` is the engine's own
    ratio; `stop` and `target` are the prices of real detected `PriceLevel`
    objects it selected, or `None` where it selected none.

    ``approval`` is an `ApprovalResult` when one was computed for this symbol, an
    `Absent` when the approval layer was asked and refused this candidate, and
    `None` when it was never asked. All three are different facts and only the
    first produces a status.
    """
    status, size, open_risk, blocking, warnings = _approval_fields(approval)
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
        approval_status=status,
        recommended_size=size,
        open_risk_after=open_risk,
        blocking_reasons=blocking,
        approval_warnings=warnings,
    )


def _approval_fields(
    approval: Any,
) -> tuple[str | None, str | None, str | None, tuple[str, ...], tuple[str, ...]]:
    """An `ApprovalResult` reduced to five printable values, or five absences.

    Duck-typed like every other value this module reads. An `Absent` carries a
    `reason` and an `ApprovalResult` does not, and that is the whole of the
    distinction — reaching into `fmis.position_sizing` for an `isinstance` would
    give this package a second place that vocabulary lives, which the module
    docstring's own rule about `SetupState` already rejects for the same reason.

    A refusal from the approval layer becomes a **blocking reason** rather than a
    silent `None`: *"this candidate has no stop, so no size can be produced"* is
    the most useful sentence on the row, and dropping it would leave a candidate
    looking merely unchecked.
    """
    if approval is None:
        return None, None, None, (), ()
    reason = getattr(approval, "reason", None)
    if reason is not None:
        return (
            _NOT_SIZEABLE,
            f"unavailable — {reason}",
            f"unavailable — {reason}",
            (reason,),
            (),
        )
    return (
        approval.status.value,
        _quantity_text(approval.recommended_quantity),
        _amount_text(approval.open_risk_after),
        tuple(entry.statement for entry in approval.blocking),
        tuple(entry.statement for entry in approval.warnings),
    )


def _quantity_text(value: Any) -> str:
    reason = getattr(value, "reason", None)
    if reason is not None:
        return f"unavailable — {reason}"
    return f"{value.text} {value.asset}"


def _assessed(results: Sequence[Any]) -> tuple[Any, ...]:
    return tuple(
        result.assessment for result in results if result.assessment is not None
    )


def opportunities_from_results(
    results: Sequence[Any],
    approvals: Mapping[str, Any] | None = None,
    *,
    approval_note: Any = None,
) -> Opportunities:
    """Group one scan's results by the engine's own state.

    ``approvals`` maps a requested symbol to the `ApprovalResult` computed for
    it, or to an `Absent` naming why no candidate could be built from it. `None`
    means no approval was computed at all — the third case, and the one
    ``approval_note`` explains on the page.

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
    found = {} if approvals is None else dict(approvals)

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
        approval = found.get(result.requested_symbol)
        if state == _CONFIRMED:
            confirmed.append(_line_from(assessment, approval))
        elif state == _CANDIDATE:
            candidates.append(_line_from(assessment, approval))
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
        **(
            {}
            if approval_note is None
            else {"approval_note": approval_note}
        ),
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


def _amount_text(value: Any) -> str:
    """A money figure as text, or the reason there is none — never a blank.

    Duck-typed, like every other value this module reads. An `Absent` carries a
    `reason` and a `Money` does not, and that is the whole of the distinction —
    reaching into `fmis.money` for an `isinstance` would give this package a
    second place the domain's vocabulary lives, which the module docstring's own
    rule about `SetupState` already rejects for the same reason.
    """
    reason = getattr(value, "reason", None)
    if reason is not None:
        return f"unavailable — {reason}"
    return f"{value.text} {value.asset}"


def _age_text(value: Any) -> str:
    """A mark's age as text, or the reason there is none.

    Printed to whole seconds. A microsecond on a staleness figure is noise a
    reader has to look past, and it is the only thing on the line that changes
    between two runs a second apart — which made the page look less reproducible
    than it is. Truncating is a formatting decision; the figure itself is
    untouched, and this page still states how stale a mark is without deciding
    what "too stale" means, because a staleness threshold is a policy and this
    package sets none.
    """
    reason = getattr(value, "reason", None)
    if reason is not None:
        return f"unavailable — {reason}"
    seconds = int(value.total_seconds())
    return str(timedelta(seconds=seconds))


def _amount_or_absence(
    value: Any, *, owned_by: str, forbidden: str
) -> str | NotAvailable:
    """The same figure, as the model's own two-shape absence."""
    reason = getattr(value, "reason", None)
    if reason is not None:
        return NotAvailable(
            reason=reason, owned_by=owned_by, forbidden_inference=forbidden
        )
    return f"{value.text} {value.asset}"


def _position_line(position: Any, marked: Any | None = None) -> PositionLine:
    """One open position, optionally paired with the price it was valued at.

    ``marked`` is a `MarkedPosition` wrapping this same position. When it is
    `None` no price source was consulted and the three price fields stay `None`,
    which the model distinguishes from a price that was sought and not found.
    """
    return PositionLine(
        market=position.market.value,
        book=position.book.value,
        direction=position.direction.value,
        quantity=f"{position.net_quantity.text} {position.net_quantity.asset}",
        average_entry=position.average_entry.arithmetic,
        opened_at=position.opened_at,
        trade_count=position.trade_count,
        event_ids=position.event_ids,
        mark=(
            None
            if marked is None
            else (
                f"unavailable — {marked.mark.reason}"
                if getattr(marked.mark, "reason", None) is not None
                else (
                    f"{marked.mark.price} {marked.mark.quote_asset} "
                    f"as of {marked.mark.as_of.isoformat()} "
                    f"({marked.mark.source})"
                )
            )
        ),
        market_value=None if marked is None else _amount_text(marked.market_value),
        unrealized_pnl=(
            None if marked is None else _amount_text(marked.unrealized_pnl)
        ),
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
    valuation: Any | None = None,
) -> PortfolioOverview:
    """What is held, what it is worth and what is committed.

    ``budget`` is the `RiskBudget` in force, or `None` when none is. ``snapshot``
    is the latest `PortfolioSnapshot`, or `None` when none has been taken.
    ``valuation`` is a `PortfolioValuation` when a price source was consulted,
    and `None` when one was not. All three absences are rendered with their
    reason rather than collapsed into an empty section.

    **Every marked figure is read off the valuation, never recomputed.** Market
    value, exposure and open risk are `PortfolioValuation` properties, which are
    in turn `PortfolioState` properties; this function selects and formats.
    """
    unmeasurable = NotAvailable(
        reason=(
            "open risk needs a mark for every holding and a stop for every open "
            "position; no price source was consulted for this page"
            if valuation is None
            else "no figure was measured against this limit"
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
        # Named `unobserved` rather than `valuation`: the parameter above is a
        # `PortfolioValuation`, and a local sharing its name would shadow it —
        # which is exactly what happened the first time this section was widened.
        unobserved: str | NotAvailable = NotAvailable(
            reason="no portfolio snapshot has been taken",
            owned_by="the portfolio layer (roadmap C6)",
            forbidden_inference=(
                "Do not read an absent balance as a zero balance, or as a "
                "balance this system has checked."
            ),
        )
        cash: str | NotAvailable = unobserved
        exposure: str | NotAvailable = unobserved
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

    if valuation is None:
        unpriced = NotAvailable(
            reason="no price source was consulted for this page",
            owned_by="the valuation layer",
            forbidden_inference=(
                "Do not read an unvalued portfolio as a worthless one, or an "
                "unstated profit and loss as a flat one."
            ),
        )
        lines = tuple(_position_line(position) for position in positions)
        market_value: str | NotAvailable = unpriced
        unrealized: str | NotAvailable = unpriced
        marks_note: str | NotAvailable = unpriced
        committed = unmeasurable
        priced_exposure = exposure
    else:
        lines = tuple(
            _position_line(marked.position, marked) for marked in valuation.positions
        )
        market_value = _amount_or_absence(
            valuation.market_value,
            owned_by="the valuation layer",
            forbidden="Do not read an unvalued portfolio as a worthless one.",
        )
        unrealized = _amount_or_absence(
            valuation.unrealized_pnl,
            owned_by="the valuation layer",
            forbidden="Do not read an unstated profit and loss as a flat one.",
        )
        committed = _amount_or_absence(
            valuation.open_risk,
            owned_by="the risk layer",
            forbidden=(
                "Do not read this as risk being within budget. Nothing was "
                "measured."
            ),
        )
        priced_exposure = _amount_or_absence(
            valuation.gross_exposure,
            owned_by="the valuation layer",
            forbidden="Do not read an unstated exposure as no exposure.",
        )
        marks_note = (
            f"{valuation.marks.marked_count} of "
            f"{valuation.marks.requested_count} market(s) priced from "
            f"{valuation.prices.source} · oldest mark age "
            f"{_age_text(valuation.mark_age)}"
        )

    return PortfolioOverview(
        store_root=store_root,
        store_present=store_present,
        open_positions=lines,
        limits=limits,
        budget_note=budget_note,
        committed_risk=committed,
        available_risk=unmeasurable,
        cash=cash,
        exposure=priced_exposure,
        snapshot_as_of=snapshot_as_of,
        market_value=market_value,
        unrealized_pnl=unrealized,
        marks_note=marks_note,
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


# --------------------------------------------------------------------------
# The paper simulator's section.
# --------------------------------------------------------------------------


def _paper_line(view: Any) -> PaperTradeLine:
    """One simulated trade, reduced to strings. **Nothing is computed here.**

    Every figure comes off the `TradeMonitor` the simulator's own read path
    produced, so a number on this page and the same number under
    `fmits trade status` are the same value rendered twice — not two
    calculations that agree today.
    """
    monitor = view.monitor
    return PaperTradeLine(
        activation_id=view.activation_id,
        market=view.activation.market.pair_symbol,
        state=view.state.value,
        open_size=str(monitor.remaining),
        entry=_paper_decimal(monitor.entry_price),
        stop=_decimal_text(monitor.effective_stop),
        initial_stop=_decimal_text(monitor.initial_stop),
        total_r=_paper_decimal(monitor.total_r),
        holding=_paper_str(monitor.holding_time),
        bars_in_trade=monitor.bars_in_trade,
        stop_widenings=monitor.stop_widenings,
    )


def _decimal_text(value: Any) -> str:
    """One exact price or ratio, in the domain's single canonical spelling."""
    return canonical_decimal_text(value)


def _paper_decimal(value: Any) -> str | NotAvailable:
    """A domain `Decimal | Absent` becomes canonical text or a stated absence."""
    if isinstance(value, Absent):
        return _paper_absence(value)
    return _decimal_text(value)


def _paper_str(value: Any) -> str | NotAvailable:
    """A domain `T | Absent` whose value is not a price — a duration, a label.

    A second helper rather than one that branches on the type: this package
    holds no `decimal` import and gains none, so what is a price and what is not
    is decided by the **call site**, where the answer is known, rather than by an
    `isinstance` here, where it would be guessed.
    """
    if isinstance(value, Absent):
        return _paper_absence(value)
    return str(value)


def _paper_absence(value: Any) -> NotAvailable:
    """The simulator's own reason, carried through verbatim.

    Not paraphrased: the reason the simulator gave is more specific than
    anything this layer could invent, and a page that reworded it would be a
    second answer to the same question.
    """
    return NotAvailable(
        reason=value.reason,
        owned_by="fmis.paper",
        forbidden_inference=(
            "that the figure is zero, or that this trade never moved that way. "
            "It is a figure the simulator could not state"
        ),
    )


#: The states a trade is over in, in the order the section lists them. Named
#: here rather than derived from `TERMINAL_LIFECYCLE_STATES`, because that set
#: holds only `RESOLVED` — the fold's terminal state — and the owner's question
#: is *"which of these have finished"*, which four more states answer.
_FINISHED_STATES: tuple[str, ...] = (
    "closed",
    "resolved",
    "cancelled",
    "expired",
    "superseded",
)


def paper_trading(
    views: Sequence[Any], *, read: bool
) -> PaperTrading:
    """Group the simulator's trades by what the owner does next about each.

    `read=False` produces an empty section whose note says the store was not
    consulted — which is a different claim from *"there are no paper trades"*
    and must not render the same way. This is the identical discipline every
    other section on this page already follows for an unread store.
    """
    if not read:
        return PaperTrading(
            note=NotAvailable(
                reason=(
                    "the store was not read, so whether any paper trade is "
                    "running is unknown"
                ),
                owned_by="fmis.paper",
                forbidden_inference=(
                    "that no paper trade is running. This page did not look"
                ),
            )
        )
    buckets: dict[str, list[PaperTradeLine]] = {
        state.value: [] for state in TradeLifecycleState
    }
    for view in views:
        line = _paper_line(view)
        # Every member of the enum has a bucket by construction, so a state
        # added later lands somewhere visible rather than in a key nothing
        # reads. `PAPER_SECTION_GROUPS` below then decides which list it joins,
        # and a guard asserts the two cover the enum between them — the first
        # draft hard-coded six keys, and a finished trade folds to `RESOLVED`
        # rather than `CLOSED`, so *every* finished trade was invisible.
        buckets[line.state].append(line)
    return PaperTrading(
        pending=tuple(buckets["pending"]),
        triggered=tuple(buckets["triggered"]),
        # A halted trade sits with the open ones, because that is what it is: it
        # holds exposure and it is waiting for a decision. `PaperTradeLine.halted`
        # marks it out, so nothing has to remember to look in a sixth list.
        open_trades=tuple(buckets["open"] + buckets["ambiguous"]),
        partially_exited=tuple(buckets["partially_exited"]),
        # `CLOSED` and `RESOLVED` alike: the engine freezes an outcome the moment
        # a trade closes, so `CLOSED` is transient within one run and a finished
        # trade is almost always read as `RESOLVED`. `CANCELLED`, `EXPIRED` and
        # `SUPERSEDED` end a trade too, and a page that showed none of them would
        # answer *"what happened to the ones I activated"* with silence.
        recently_closed=tuple(
            line
            for state in _FINISHED_STATES
            for line in buckets[state]
        ),
        note=(
            "every activation this store holds was folded from its own event "
            "stream; no state is stored. This page reads no simulation candle, "
            "so an excursion and a bar count are absent here — `fmits trade "
            "status` fetches them"
        ),
    )


# ---------------------------------------------------------------------------
# 6. Performance — whether this is working (Milestone BP)
# ---------------------------------------------------------------------------

#: How many finished trades the day's page lists. Ten, because the brief names
#: ten and because a page that listed every trade would stop being a day's page
#: — `fmits trades summary` is where the whole corpus is read.
PERFORMANCE_RECENT_LIMIT = 10


#: What a reader must not conclude from a figure the sample floor withheld.
_FLOOR_FORBIDS = (
    "that the figure is zero, or that the trades behind it are too few to "
    "matter — the number exists and is simply not a rate yet"
)

#: What a reader must not conclude from a figure whose input is missing.
_MISSING_FORBIDS = "that the figure is zero"


def _floor_refusal(resolved: int, floor: int) -> NotAvailable:
    """The short form of a sample-floor refusal, built from its two numbers.

    **No prose is restated.** The floor's full justification is five sentences
    and belongs once per section — repeated against four figures it makes the
    day's page unreadable, which makes the guard easier to ignore rather than
    harder. So this is derived from `n` and the floor, and
    `PerformanceSummary.floor_note` carries the policy.

    A population of **zero** is reported as one rather than as *"below the
    floor"*: both are true, and *"no resolved trade"* is the one that tells the
    owner what to do about it.
    """
    reason = (
        "no resolved trade to state this from"
        if resolved == 0
        else f"refused: {resolved} resolved trade(s), below the floor of {floor}"
    )
    return NotAvailable(
        reason=reason,
        owned_by="fmis.statistics",
        forbidden_inference=_FLOOR_FORBIDS,
    )


def _performance_text(
    value: Any,
    *,
    forbids: str = _MISSING_FORBIDS,
    floored: tuple[int, int] | None = None,
) -> str | NotAvailable:
    """One rule for turning a statistic into what the page holds.

    `floored` is `(resolved, floor)` and is supplied **only for the figures the
    sample guard actually governs** — the rates. Supplying it for a mean would
    label an empty population as a floor refusal, and supplying it for a
    zero-denominator refusal would label that as one too; both are absences the
    guard did not produce, and calling them its work would misdirect the reader
    to the sample when the problem is elsewhere. Every other absence keeps its
    own reason verbatim, because those reasons are one line and are all
    different.
    """
    if isinstance(value, Absent):
        if floored is not None and floored[0] < floored[1]:
            return _floor_refusal(floored[0], floored[1])
        return NotAvailable(
            reason=value.reason,
            owned_by="fmis.statistics",
            forbidden_inference=forbids,
        )
    if isinstance(value, Money):
        return f"{value.text} {value.asset.code}"
    if isinstance(value, timedelta):
        return _duration_text(value)
    return canonical_decimal_text(value)


def _duration_text(span: timedelta) -> str:
    """Days and hours — `fmis.statistics.duration_text`, called.

    Not reimplemented, for two reasons that point the same way. This page's own
    magic-number guard forbids a rule module from typing `86400`, and it is
    right to: a unit constant here is a second place the unit is decided. And
    `fmits statistics` already formats durations, so a local copy would let the
    two pages disagree about what a holding time reads as.
    """
    return duration_text(span, minutes=False)


def _performance_line(stat: Any) -> PerformanceLine:
    return PerformanceLine(
        trade_ref=stat.trade_ref,
        market=stat.market.value,
        result=stat.result.value,
        closed_at=(
            "-" if isinstance(stat.closed_at, Absent) else stat.closed_at.isoformat()
        ),
        # No `floored` here: a single trade's R multiple and profit and loss are
        # facts about that trade, and the sample guard governs neither.
        r_multiple=_performance_text(stat.r_multiple),
        net=_performance_text(stat.realized_pnl_net),
    )


def _book_performance(
    label: str, trades: tuple[Any, ...], policy: Any, asset: Any
) -> BookPerformance:
    """One book's headline pair, folded through the engine rather than by hand.

    `performance_statistics` is called again over the narrowed population
    instead of the numbers being re-derived here, because the sample floor has
    to apply to a book's win rate exactly as it applies to the corpus's — and a
    second computation would be a second place it could be skipped.
    """
    reading = performance_statistics(trades, policy, quote_asset=asset)
    resolved = reading.resolved.size
    return BookPerformance(
        label=label,
        trades=len(trades),
        closed=resolved,
        # Expectancy is a mean and is not floored; its absence means the
        # population is empty, and it says so in its own words.
        expectancy=_performance_text(reading.expectancy),
        win_rate=_performance_text(
            reading.win_rate, floored=(resolved, policy.minimum_sample)
        ),
    )


def performance_summary(
    report: Any, *, at: datetime, limit: int = PERFORMANCE_RECENT_LIMIT
) -> PerformanceSummary:
    """The day's page's performance section, from one already-built report.

    **Takes a report rather than a store**, so this module keeps the property
    every other section here has: it adapts, and it performs no I/O. The report
    is built in `fmis.today.builder`, beside every other store read.

    `closed today` is the trades that closed inside the UTC day containing
    `at` — a half-open window, so a trade closing at midnight is counted on the
    day that is starting and never on both.
    """
    if not isinstance(at, datetime):
        raise TypeError(f"at must be a datetime, got {type(at).__name__}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise TodayError("limit must be a non-negative int")
    if report is None:
        return PerformanceSummary(
            note=NotAvailable(
                reason=(
                    "this run did not read the store, so no statistic was "
                    "computed over it"
                ),
                owned_by="fmis.statistics",
                forbidden_inference="that the owner has recorded no trade",
            )
        )

    asset_report = report.primary
    if isinstance(asset_report, Absent):
        return PerformanceSummary(
            sample_floor=report.policy.minimum_sample,
            note=asset_report.reason,
        )

    performance = asset_report.performance
    floor = report.policy.minimum_sample
    # Constructed rather than `at.replace(hour=0, ...)`. `fmis.today`'s
    # architecture guard forbids `.replace` anywhere in this package because it
    # is the store's write verb, and it matches on the name alone — correctly,
    # since a guard that had to know which object it was called on would be a
    # guard with an exception in it. Building the instant explicitly costs one
    # line and keeps the ban absolute.
    utc_moment = at.astimezone(timezone.utc)
    day_start = datetime(
        utc_moment.year, utc_moment.month, utc_moment.day, tzinfo=timezone.utc
    )
    closed_today = closed_between(
        asset_report.trades, start=day_start, end=day_start + timedelta(days=1)
    )
    paper = tuple(stat for stat in asset_report.trades if stat.is_paper)
    other = tuple(stat for stat in asset_report.trades if not stat.is_paper)

    return PerformanceSummary(
        trades=asset_report.size,
        open_trades=asset_report.general.open_trades.count,
        closed_today=len(closed_today),
        resolved=performance.resolved.size,
        sample_floor=report.policy.minimum_sample,
        quote_asset=asset_report.quote_asset.code,
        # Only the two **rates** are floored. Expectancy, expectancy in R and
        # average R are means over a stated `n` and are true descriptions of
        # the trades in hand at any sample.
        expectancy=_performance_text(performance.expectancy),
        expectancy_r=_performance_text(performance.expectancy_r),
        win_rate=_performance_text(
            performance.win_rate, floored=(performance.resolved.size, floor)
        ),
        profit_factor=_performance_text(
            performance.profit_factor, floored=(performance.resolved.size, floor)
        ),
        average_r=_performance_text(performance.average_r),
        average_holding_time=_performance_text(
            asset_report.general.average_holding_time
        ),
        current_equity=_performance_text(
            asset_report.equity.current_equity,
            forbids=(
                "that the account is empty. This system records the owner's "
                "opening capital nowhere"
            ),
        ),
        realized=_performance_text(asset_report.equity.realized),
        current_drawdown=_performance_text(asset_report.drawdown.current),
        floor_note=(
            f"rates are refused below {floor} resolved trades, and passing that "
            "floor establishes nothing. `fmits expectancy` prints the full basis"
        ),
        recent=tuple(
            _performance_line(stat)
            for stat in recent_trades(asset_report.trades, limit)
        ),
        # Two rows, always both, even when one is empty. A page that dropped the
        # empty book would let a store holding only paper trades read as a
        # statement about the owner's money.
        books=(
            _book_performance(
                "paper", paper, report.policy, asset_report.quote_asset
            ),
            _book_performance(
                "other books", other, report.policy, asset_report.quote_asset
            ),
        ),
        note=(
            f"every rate here is refused below {report.policy.minimum_sample} "
            "resolved trades and says so; counts are shown at any sample. "
            "Excursion figures and R multiples exist only for simulated trades. "
            "`fmits statistics` is the whole picture"
        ),
    )
