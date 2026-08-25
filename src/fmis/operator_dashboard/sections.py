"""Engine output → read model. The only module that knows both vocabularies.

**Every function here is a translation, and translation is the whole job.** A
field is renamed, an enum becomes its own `.value`, a `Money` becomes its
canonical text, a `NotAvailable` splits into a `None` and the reason that
explains it. Nothing is added up, divided, compared for magnitude, sorted by a
property of the analysis, or classified. If a value is not already on the object
being read, it does not appear on the object being written.

**The `_or_reason` pair is the spine of the module.** Three engine vocabularies
express *"there is no value, and here is why"* — `NotAvailable` from
`fmis.today`, `Absent` from `fmis.provenance`, and the ``value``/
``unavailable_reason`` pairing `fmis.market_pulse` uses. All three collapse to
one shape here: ``(value | None, reason | None)``, exactly one of which is set.
That is the invariant the render layer relies on to keep *zero* and *absent*
visually distinct, and it is why a bare `None` is never written without its
reason travelling beside it.

**Ordering is inherited, never produced.** `ranked_setups` arrive in the order
`fmis.swing_workspace` placed them and are mapped index-for-index. There is no
`sorted()` call anywhere in this module, and a guard asserts it: re-sorting rows
by risk/reward or evidence count would be this dashboard inventing the ranking
four engines below it deliberately refused to make.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.market_pulse import (
    FreshnessState,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
)
from fmis.operator_dashboard.models import (
    BenchmarkRow,
    BookRow,
    DataHealthView,
    EquityStep,
    EvidenceView,
    GeometryCriterionRow,
    GeometryFindingRow,
    GeometryPolicyRow,
    GeometrySampleRow,
    GeometrySensitivityRow,
    GeometryShareRow,
    GeometryView,
    LabGateRow,
    LabVariantRow,
    LabView,
    LimitRow,
    MacroRow,
    MacroView,
    MoveCell,
    NoTradeRow,
    OverviewCounts,
    PaperRow,
    PaperView,
    PerformanceView,
    PortfolioView,
    PositionRow,
    PulseView,
    RelationshipRow,
    SetupRow,
    SourceHealth,
    SourceState,
    SwingView,
    UnreadableRow,
    WarningRow,
)

__all__ = [
    "counts_from",
    "pulse_view",
    "macro_view",
    "swing_view",
    "portfolio_view",
    "paper_view",
    "performance_views",
    "health_view",
    "warning_rows",
    "lab_view",
    "geometry_view",
]


# ---------------------------------------------------------------------------
# The absence vocabularies, reduced to one shape
# ---------------------------------------------------------------------------


def _text_or_reason(value: Any) -> tuple[str | None, str | None]:
    """Split a `str | NotAvailable` into a value and a reason.

    `fmis.today.NotAvailable` carries three fields — the reason, the layer that
    owns the gap, and the inference the gap forbids. Only the reason is carried
    forward: the other two are an audit trail for the engine that produced it,
    and putting them on a dashboard row would bury the fact under its footnotes.
    """
    if value is None:
        return None, None
    reason = getattr(value, "reason", None)
    if reason is not None and not isinstance(value, str):
        return None, str(reason)
    return str(value), None


def _money_or_reason(value: Any) -> tuple[str | None, str | None]:
    """Split a `Money | Absent` into canonical text and a reason.

    ``Money.text`` rather than `str(amount)`: it is the exact spelling the store
    holds and the digest covers, so a figure on screen and the same figure in a
    record are the same characters. Rounding here would make them differ.
    """
    if value is None:
        return None, None
    reason = getattr(value, "reason", None)
    if reason is not None:
        return None, str(reason)
    text = getattr(value, "text", None)
    if text is not None:
        return str(text), None
    return str(value), None


def _decimal_or_reason(value: Any) -> tuple[str | None, str | None]:
    """Split a `Decimal | Absent`. The exact decimal, never a float."""
    if value is None:
        return None, None
    reason = getattr(value, "reason", None)
    if reason is not None:
        return None, str(reason)
    if isinstance(value, Decimal):
        return format(value, "f"), None
    return str(value), None


def _enum_value(value: Any) -> str:
    """An enum's own `.value`, or the string it already is."""
    inner = getattr(value, "value", None)
    return str(inner) if inner is not None else str(value)


# ---------------------------------------------------------------------------
# Overview counts
# ---------------------------------------------------------------------------


def counts_from(workspace: Any) -> OverviewCounts:
    """The first page's tallies, every one already counted by the workspace."""
    summary = workspace.summary
    return OverviewCounts(
        scanned=summary.scanned,
        confirmed=summary.confirmed,
        candidates=summary.candidates,
        waiting=summary.waiting,
        unreadable=summary.unanalysed,
        open_positions=summary.open_positions,
        paper_positions=summary.paper_positions,
    )


# ---------------------------------------------------------------------------
# Markets — pulse
# ---------------------------------------------------------------------------


def _move_cells(moves: Any, horizons: dict[str, str]) -> tuple[MoveCell, ...]:
    return tuple(
        MoveCell(
            horizon_id=move.horizon_id,
            label=horizons.get(move.horizon_id, move.horizon_id),
            bars=move.bars,
            value=move.value,
            unavailable_reason=move.unavailable_reason,
            metric=move.metric,
        )
        for move in moves
    )


def _reading_state(reading: MarketReading, as_of: datetime) -> SourceState:
    """A reading's state, decided by the reading's own freshness verdict.

    Three `FreshnessState` members map one-for-one onto three `SourceState`
    members. The mapping is total and holds no threshold of its own — the
    policy that decides *behind schedule* is a property of the series, declared
    in `fmis.market_pulse`, and this only carries its answer across the seam.
    """
    state = reading.freshness_at(as_of)
    if state is FreshnessState.BEHIND_SCHEDULE:
        return SourceState.BEHIND_SCHEDULE
    if state is FreshnessState.ON_SCHEDULE:
        return SourceState.AVAILABLE
    return SourceState.SCHEDULE_UNKNOWN


def _unavailable_state(entry: MarketUnavailable) -> SourceState:
    """A market a provider was asked for and did not deliver.

    **Always `UNAVAILABLE`, and there is no second branch on purpose.**
    Unsupported and unavailable are different facts — *"there is no provider for
    the dollar index in this build"* is permanent, while *"Binance did not
    answer"* is this afternoon — but the engine already keeps them apart at
    construction: `MarketUnavailable` refuses a benchmark with no provider
    instrument, because *"a market with no provider is unsupported, which is a
    different fact"*. Unsupported markets arrive from `universe.unsupported`
    instead, and `_unsupported_benchmarks` reads them.

    A defensive `if entry.benchmark.unsupported_reason` here would be a branch
    that can never be taken, which reads as a distinction this function makes
    rather than one made below it.
    """
    return SourceState.UNAVAILABLE


def _unsupported_benchmarks(universe: Any) -> tuple[Any, ...]:
    """The markets no provider was ever asked for.

    **These are not in `unavailable`, and reading only that tuple loses them.**
    The engines draw a three-way distinction — read, *asked for and not
    delivered*, and *never asked for because no provider is configured*. The
    third lives on the universe rather than on the report, because it is a
    property of the build rather than of the run. DXY and XAU are the live
    cases, and a page that silently omitted them would be answering *"what can
    this system not tell me?"* with silence.
    """
    return tuple(getattr(universe, "unsupported", ()) or ())


def pulse_view(pulse: MarketPulse) -> PulseView:
    """The pulse, re-sectioned. Every market appears exactly once, as it does
    in the report — a reading or a stated failure, never both and never neither.
    """
    horizons = {horizon.horizon_id: horizon.description for horizon in pulse.horizons}
    co_movements = {
        movement.subject_id: movement for movement in pulse.co_movements
    }
    rows: list[BenchmarkRow] = []
    for reading in pulse.readings:
        benchmark = reading.benchmark
        movement = co_movements.get(benchmark.benchmark_id)
        rows.append(
            BenchmarkRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                category=_enum_value(benchmark.category),
                quote_unit=benchmark.quote_unit,
                state=_reading_state(reading, pulse.as_of),
                moves=_move_cells(reading.moves, horizons),
                volatility=reading.volatility.value,
                volatility_reason=reading.volatility.unavailable_reason,
                volatility_metric=reading.volatility.metric,
                last_bar_open=reading.last_bar_open,
                age=reading.age_at(pulse.as_of),
                source=reading.source,
                interval=reading.interval,
                co_movement=None if movement is None else movement.value,
                co_movement_reason=(
                    None if movement is None else movement.unavailable_reason
                ),
                co_movement_reference=(
                    None if movement is None else movement.reference_id
                ),
            )
        )
    for entry in pulse.unavailable:
        benchmark = entry.benchmark
        rows.append(
            BenchmarkRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                category=_enum_value(benchmark.category),
                quote_unit=benchmark.quote_unit,
                state=_unavailable_state(entry),
                unavailable_reason=entry.reason,
            )
        )
    for benchmark in _unsupported_benchmarks(pulse.universe):
        rows.append(
            BenchmarkRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                category=_enum_value(benchmark.category),
                quote_unit=benchmark.quote_unit,
                state=SourceState.UNSUPPORTED,
                unavailable_reason=benchmark.unsupported_reason,
            )
        )
    return PulseView(
        as_of=pulse.as_of,
        universe=pulse.universe.name,
        rows=tuple(rows),
        horizons=tuple(
            (horizon.horizon_id, horizon.description) for horizon in pulse.horizons
        ),
        read_count=pulse.read_count,
        requested_count=pulse.requested_count,
        unsupported_count=pulse.unsupported_count,
        co_movement_reference=pulse.co_movement_reference,
    )


# ---------------------------------------------------------------------------
# Markets — macro
# ---------------------------------------------------------------------------


def _rate_cells(fact: Any, horizons: dict[str, str]) -> tuple[MoveCell, ...]:
    """A yield's moves, carried in basis points because that is what they are.

    `fmis.macro` produces a `RateChange` holding the same move at three scales.
    Basis points is the one carried: a yield that went from 4.10 to 4.35 moved
    25 basis points, and calling that a 6.1% return would be describing a
    different quantity in a unit that invites comparison with an equity move.
    """
    cells = [
        MoveCell(
            horizon_id=window,
            label=horizons.get(window, window),
            bars=0,
            value=change.basis_points,
            metric="basis points",
        )
        for window, change in fact.changes
    ]
    cells.extend(
        MoveCell(
            horizon_id=window,
            label=horizons.get(window, window),
            bars=0,
            value=None,
            unavailable_reason=reason,
            metric="basis points",
        )
        for window, reason in fact.unavailable_horizons
    )
    return tuple(cells)


def macro_view(report: Any) -> MacroView:
    """The macro report, re-sectioned. Levels, moves, relationships, absences."""
    horizons = {horizon.horizon_id: horizon.description for horizon in report.horizons}
    levels = {level.benchmark_id: level for level in report.levels}
    rates = {fact.benchmark_id: fact for fact in report.rate_facts}
    rows: list[MacroRow] = []
    for reading in report.readings:
        benchmark = reading.benchmark
        level = levels.get(benchmark.benchmark_id)
        fact = rates.get(benchmark.benchmark_id)
        rows.append(
            MacroRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                state=_reading_state(reading, report.as_of),
                level=None if level is None else level.value,
                unit="" if level is None else level.unit,
                quantity_kind=_enum_value(benchmark.quantity_kind),
                observed_at=None if level is None else level.observed_at,
                source=reading.source if level is None else level.source,
                age=reading.age_at(report.as_of),
                moves=(
                    _rate_cells(fact, horizons)
                    if fact is not None
                    else _move_cells(reading.moves, horizons)
                ),
                change_unit="basis points" if fact is not None else "percent",
                volatility=reading.volatility.value,
                volatility_reason=reading.volatility.unavailable_reason,
            )
        )
    for entry in report.unavailable:
        benchmark = entry.benchmark
        rows.append(
            MacroRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                state=_unavailable_state(entry),
                unavailable_reason=entry.reason,
            )
        )
    for benchmark in _unsupported_benchmarks(report.universe):
        rows.append(
            MacroRow(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                state=SourceState.UNSUPPORTED,
                unavailable_reason=benchmark.unsupported_reason,
            )
        )
    relationships = tuple(
        RelationshipRow(
            subject_id=relationship.subject_id,
            reference_id=relationship.reference_id,
            metric=relationship.metric,
            value=relationship.value,
            unavailable_reason=relationship.unavailable_reason,
            observation_count=relationship.observation_count,
            aligned_count=relationship.aligned_count,
            comparability=(
                ""
                if relationship.comparability is None
                else _enum_value(relationship.comparability)
            ),
            detail=relationship.not_comparable_detail or "",
        )
        for relationship in report.relationships
    )
    return MacroView(
        as_of=report.as_of,
        rows=tuple(rows),
        relationships=relationships,
        relationship_reference=report.relationship_reference,
        horizons=tuple(
            (horizon.horizon_id, horizon.description) for horizon in report.horizons
        ),
    )


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------


def _evidence_view(value: Any) -> tuple[EvidenceView | None, str | None]:
    """A digest, or the reason there is none. Counts are carried, never summed."""
    if value is None:
        return None, None
    reason = getattr(value, "reason", None)
    if reason is not None:
        return None, str(reason)
    return (
        EvidenceView(
            supporting=value.supporting,
            conflicting=value.conflicting,
            missing=value.missing,
            unavailable=value.unavailable,
            agreeing_families=tuple(value.agreeing_families),
            conflicting_families=tuple(value.conflicting_families),
            independence_established=value.independence_established,
            decision_ready=value.decision_ready,
            decision_ready_reason=value.decision_ready_reason,
            caveats=tuple(value.caveats),
        ),
        None,
    )


def _setup_row(ranked: Any) -> SetupRow:
    """One workspace row, translated field for field. Its position is carried."""
    line = ranked.opportunity
    evidence, evidence_reason = _evidence_view(ranked.evidence)
    identity, identity_reason = _text_or_reason(ranked.identity)
    paper_status, _ = _text_or_reason(ranked.paper_status)
    held, _ = _text_or_reason(ranked.held)
    return SetupRow(
        symbol=line.symbol,
        state=line.state,
        sufficiency=line.sufficiency,
        position=ranked.position,
        direction=line.direction,
        approval_status=line.approval_status,
        risk_reward=line.risk_reward,
        stop=line.stop,
        target=line.target,
        recommended_size=line.recommended_size,
        open_risk_after=line.open_risk_after,
        thesis=tuple(line.thesis),
        confirmation=tuple(line.confirmation),
        invalidation=tuple(line.invalidation),
        blocking_reasons=tuple(line.blocking_reasons),
        approval_warnings=tuple(line.approval_warnings),
        evidence=evidence,
        evidence_reason=evidence_reason,
        identity=identity,
        identity_reason=identity_reason,
        paper_status=paper_status,
        held=held,
        rank_components=tuple(
            (component.name, component.value) for component in ranked.key.components
        ),
    )


def swing_view(workspace: Any) -> SwingView:
    """The workspace's four groups, each mapped in the order it arrived."""
    return SwingView(
        reference_time=workspace.reference_time,
        opportunities=tuple(_setup_row(row) for row in workspace.opportunities),
        wait_list=tuple(_setup_row(row) for row in workspace.wait_list),
        no_trade=tuple(
            NoTradeRow(
                reason=group.reason,
                classification=group.classification,
                symbols=tuple(group.symbols),
            )
            for group in workspace.no_trade
        ),
        unreadable=tuple(
            UnreadableRow(symbol=entry.symbol, detail=entry.detail)
            for entry in workspace.unanalysed
        ),
        ranking_rule=workspace.ranking_rule,
        scanned=workspace.summary.scanned,
        regime_note=workspace.summary.regime_note,
        breadth=tuple(workspace.summary.breadth),
    )


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def portfolio_view(workspace: Any) -> PortfolioView:
    """The recorded book only. No paper field is read anywhere in this function."""
    overview = workspace.portfolio
    cash, cash_reason = _text_or_reason(overview.cash)
    exposure, exposure_reason = _text_or_reason(overview.exposure)
    value, value_reason = _text_or_reason(overview.market_value)
    unrealized, unrealized_reason = _text_or_reason(overview.unrealized_pnl)
    committed, committed_reason = _text_or_reason(overview.committed_risk)
    available, available_reason = _text_or_reason(overview.available_risk)
    budget, _ = _text_or_reason(overview.budget_note)
    marks, _ = _text_or_reason(overview.marks_note)
    books: list[BookRow] = []
    for book in workspace.books:
        book_value, book_reason = _text_or_reason(book.market_value)
        books.append(
            BookRow(
                label=book.label,
                open_positions=book.open_positions,
                market_value=book_value,
                market_value_reason=book_reason,
            )
        )
    limits: list[LimitRow] = []
    for limit in overview.limits:
        current, current_reason = _text_or_reason(limit.current)
        status, status_reason = _text_or_reason(limit.status)
        limits.append(
            LimitRow(
                limit_id=limit.limit_id,
                scope=limit.scope,
                stated_limit=limit.stated_limit,
                severity=limit.severity,
                current=current,
                current_reason=current_reason,
                status=status,
                status_reason=status_reason,
            )
        )
    return PortfolioView(
        store_root=overview.store_root,
        store_present=overview.store_present,
        positions=tuple(
            PositionRow(
                market=position.market,
                book=position.book,
                direction=position.direction,
                quantity=position.quantity,
                average_entry=position.average_entry,
                opened_at=position.opened_at,
                trade_count=position.trade_count,
                mark=position.mark,
                market_value=position.market_value,
                unrealized_pnl=position.unrealized_pnl,
            )
            for position in overview.open_positions
        ),
        limits=tuple(limits),
        books=tuple(books),
        cash=cash,
        cash_reason=cash_reason,
        exposure=exposure,
        exposure_reason=exposure_reason,
        market_value=value,
        market_value_reason=value_reason,
        unrealized_pnl=unrealized,
        unrealized_pnl_reason=unrealized_reason,
        committed_risk=committed,
        committed_risk_reason=committed_reason,
        available_risk=available,
        available_risk_reason=available_reason,
        budget_note=budget,
        marks_note=marks,
        snapshot_as_of=overview.snapshot_as_of,
    )


# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------


def paper_view(workspace: Any) -> PaperView:
    """The simulator's trades. Never merged into the portfolio view."""
    rows: list[PaperRow] = []
    for trade in workspace.paper:
        entry, entry_reason = _text_or_reason(trade.entry)
        risk, risk_reason = _text_or_reason(trade.initial_risk)
        total_r, total_r_reason = _text_or_reason(trade.total_r)
        mfe, mfe_reason = _text_or_reason(trade.max_favourable_r)
        mae, mae_reason = _text_or_reason(trade.max_adverse_r)
        rows.append(
            PaperRow(
                activation_id=trade.activation_id,
                market=trade.market,
                state=trade.state,
                open_size=trade.open_size,
                bars_in_trade=trade.bars_in_trade,
                stop_widenings=trade.stop_widenings,
                entry=entry,
                entry_reason=entry_reason,
                stop=trade.stop,
                initial_stop=trade.initial_stop,
                initial_risk=risk,
                initial_risk_reason=risk_reason,
                total_r=total_r,
                total_r_reason=total_r_reason,
                max_favourable_r=mfe,
                max_favourable_r_reason=mfe_reason,
                max_adverse_r=mae,
                max_adverse_r_reason=mae_reason,
            )
        )
    note, _ = _text_or_reason(workspace.paper_note)
    return PaperView(rows=tuple(rows), note=note)


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def performance_views(report: Any) -> tuple[PerformanceView, ...]:
    """One view per quote asset. **Figures are never summed across assets.**

    `fmis.statistics` keeps a separate report per asset because adding a profit
    in USDT to one in BTC produces a number that is not money. That separation
    survives the seam: this returns a tuple, and the page shows a section each.
    """
    views: list[PerformanceView] = []
    for asset in report.assets:
        performance = asset.performance
        drawdown = asset.drawdown
        net, net_reason = _money_or_reason(performance.net_profit)
        expectancy, expectancy_reason = _money_or_reason(performance.expectancy)
        win_rate, win_rate_reason = _decimal_or_reason(performance.win_rate)
        factor, factor_reason = _decimal_or_reason(performance.profit_factor)
        average_r, average_r_reason = _decimal_or_reason(performance.average_r)
        maximum, maximum_reason = _money_or_reason(drawdown.maximum)
        steps: list[EquityStep] = []
        for point in asset.equity.points:
            equity, _ = _money_or_reason(point.equity)
            steps.append(
                EquityStep(
                    at=point.at,
                    trade_ref=point.trade_ref,
                    delta=point.delta.text,
                    cumulative=point.cumulative.text,
                    equity=equity,
                )
            )
        views.append(
            PerformanceView(
                quote_asset=str(asset.quote_asset.code),
                trades=asset.general.total,
                open_trades=asset.general.open_trades.count,
                resolved=performance.resolved.count
                if hasattr(performance.resolved, "count")
                else len(performance.resolved.values),
                sample_floor=report.policy.minimum_sample,
                floor_note=report.policy.basis,
                net=net,
                net_reason=net_reason,
                expectancy=expectancy,
                expectancy_reason=expectancy_reason,
                win_rate=win_rate,
                win_rate_reason=win_rate_reason,
                profit_factor=factor,
                profit_factor_reason=factor_reason,
                average_r=average_r,
                average_r_reason=average_r_reason,
                max_drawdown=maximum,
                max_drawdown_reason=maximum_reason,
                equity=tuple(steps),
                equity_basis=asset.equity.basis,
                equity_excluded=tuple(asset.equity.excluded),
            )
        )
    return tuple(views)


# ---------------------------------------------------------------------------
# Data health
# ---------------------------------------------------------------------------


def _market_sources(view: Any, as_of: datetime, prefix: str) -> list[SourceHealth]:
    """One health row per market, carrying the state its own reading decided."""
    sources: list[SourceHealth] = []
    for row in view.rows:
        # Every state gets a sentence. An available source left blank renders as
        # an absence, and *"unavailable: no detail was stated"* against a market
        # that was read perfectly well is exactly the misleading cell this
        # section exists to prevent.
        detail = row.unavailable_reason or ""
        if not detail:
            detail = {
                SourceState.AVAILABLE: (
                    "read, and no older than this source's own publication "
                    "schedule explains"
                ),
                SourceState.BEHIND_SCHEDULE: (
                    "older than this source's own publication schedule accounts "
                    "for — late, not necessarily wrong"
                ),
                SourceState.SCHEDULE_UNKNOWN: (
                    "read; no publication schedule is established for this "
                    "series, so no verdict on its age is offered"
                ),
            }.get(row.state, "")
        sources.append(
            SourceHealth(
                source_id=f"{prefix}:{row.benchmark_id}",
                label=row.display_name,
                state=row.state,
                detail=detail,
                last_observation=getattr(row, "last_bar_open", None)
                or getattr(row, "observed_at", None),
                age=row.age,
                provider=row.source,
            )
        )
    return sources


def health_view(
    *,
    pulse: PulseView | None,
    macro: MacroView | None,
    portfolio: PortfolioView | None,
    paper: PaperView | None,
    pulse_failure: str | None = None,
    macro_failure: str | None = None,
    store_failure: str | None = None,
) -> DataHealthView:
    """Every source the refresh touched, with the state its own engine decided.

    **A section that failed appears here as an unavailable source, not as a
    missing row.** A page that simply omitted the macro sources when FRED was
    down would look exactly like a page where FRED was fine, which is the
    precise failure mode this section exists to prevent.
    """
    sources: list[SourceHealth] = []
    if pulse is not None:
        sources.extend(_market_sources(pulse, pulse.as_of, "pulse"))
    elif pulse_failure:
        sources.append(
            SourceHealth(
                source_id="pulse",
                label="Global market pulse",
                state=SourceState.UNAVAILABLE,
                detail=pulse_failure,
            )
        )
    if macro is not None:
        sources.extend(_market_sources(macro, macro.as_of, "macro"))
    elif macro_failure:
        sources.append(
            SourceHealth(
                source_id="macro",
                label="Macro & cross-asset context",
                state=SourceState.UNAVAILABLE,
                detail=macro_failure,
            )
        )
    if portfolio is not None:
        sources.append(
            SourceHealth(
                source_id="store",
                label="Durable store",
                state=(
                    SourceState.AVAILABLE
                    if portfolio.store_present
                    else SourceState.ABSENT
                ),
                detail=(
                    portfolio.store_root
                    if portfolio.store_present
                    else f"no store at {portfolio.store_root}"
                ),
                last_observation=portfolio.snapshot_as_of,
            )
        )
    elif store_failure:
        sources.append(
            SourceHealth(
                source_id="store",
                label="Durable store",
                state=SourceState.UNAVAILABLE,
                detail=store_failure,
            )
        )
    if paper is not None:
        sources.append(
            SourceHealth(
                source_id="paper",
                label="Paper trade simulator",
                state=SourceState.AVAILABLE,
                detail=paper.note or f"{len(paper.rows)} trade(s) read",
            )
        )
    return DataHealthView(sources=tuple(sources))


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


def warning_rows(workspace: Any) -> tuple[WarningRow, ...]:
    """The workspace's own aggregated warnings, in its own order."""
    return tuple(
        WarningRow(
            code=warning.code,
            kind=_enum_value(warning.kind),
            severity=_enum_value(warning.severity),
            statement=warning.statement,
            evidence=warning.evidence,
            subjects=tuple(warning.subjects),
            detail=tuple(warning.detail),
        )
        for warning in workspace.warnings
    )


# ---------------------------------------------------------------------------
# Swing Lab
# ---------------------------------------------------------------------------


#: How many decimal places a lab figure is carried at. An expectancy is a
#: quotient of two exact decimals and arrives with ~28 significant digits; a
#: page showing all of them states a precision the sample cannot support and is
#: simply unreadable. Four places is a **stated presentation precision**, not a
#: rounding of a measurement — the artifact keeps every digit, and this layer
#: neither computes nor re-derives the value it is displaying.
_LAB_PLACES = Decimal("0.0001")


def _measure(measure: Any) -> tuple[str | None, str | None]:
    """A `Measure` split into canonical text and the reason it is absent.

    The sample count is not dropped here: it is folded into the reason when a
    figure is missing, so a page can never show a blank cell without saying how
    many trades produced it. `quantize` states a display precision; it performs
    no arithmetic on the engine's value and cannot change which side of zero it
    falls on.
    """
    if measure is None:
        return None, "not measured"
    if measure.value is None:
        return None, measure.reason
    return format(measure.value.quantize(_LAB_PLACES), "f"), None


def lab_view(artifact: Any, *, digest_verified: bool) -> LabView:
    """Adapt one lab artifact into the page's read model. A copy, never a measure.

    Every figure here was reduced by `fmis.swing_lab.metrics` before this
    function saw it. Nothing is totalled, ranked or re-derived: variant order is
    the artifact's own, which is the study's own, which is the order the
    variants were pre-specified in.
    """
    manifest = artifact.manifest
    gate = artifact.gate
    rows = []
    for variant_id in artifact.variant_ids:
        spec = artifact.variant(variant_id)
        metrics = artifact.metrics(variant_id)
        verdict = artifact.verdict(variant_id)
        win_rate, win_rate_reason = _measure(metrics.win_rate)
        expectancy, expectancy_reason = _measure(metrics.expectancy_r)
        median, median_reason = _measure(metrics.median_r)
        profit_factor, profit_factor_reason = _measure(metrics.profit_factor)
        rows.append(
            LabVariantRow(
                variant_id=variant_id,
                title=spec["title"],
                hypothesis=spec["hypothesis"],
                policy_id=spec["policy_id"],
                is_baseline=spec["is_production_baseline"],
                trades=metrics.trades,
                measurable=metrics.measurable_trades,
                ambiguous=metrics.ambiguous_trades,
                wins=metrics.wins,
                losses=metrics.losses,
                win_rate=win_rate,
                win_rate_reason=win_rate_reason,
                expectancy=expectancy,
                expectancy_reason=expectancy_reason,
                median_r=median,
                median_r_reason=median_reason,
                profit_factor=profit_factor,
                profit_factor_reason=profit_factor_reason,
                total_r=format(metrics.total_r.quantize(_LAB_PLACES), "f"),
                max_drawdown=format(
                    metrics.max_drawdown.max_drawdown_r.quantize(_LAB_PLACES), "f"
                ),
                sample_note=(
                    f"{metrics.measurable_trades} measurable of {metrics.trades}"
                ),
                verdict=verdict.value,
                verdict_statement=verdict.statement,
            )
        )
    return LabView(
        experiment_id=manifest["experiment_id"],
        symbols=tuple(manifest["symbols"]),
        measurement_start=manifest["measurement_start"],
        measurement_end=manifest["measurement_end"],
        interval_groups=tuple("/".join(group) for group in manifest["interval_groups"]),
        cost_policy=manifest["cost_policy"]["policy_id"],
        result_digest=manifest["result_digest"],
        digest_verified=digest_verified,
        variants=tuple(rows),
        gate=LabGateRow(
            instants=gate["instants"],
            not_reached=gate["not_reached"],
            allowed=gate["allowed"],
            blocked_without_effect=gate["blocked_without_effect"],
            blocked_candidate=gate["blocked_candidate"],
            blocked_confirmed=gate["blocked_confirmed"],
            blocked_long=gate["blocked_long"],
            blocked_short=gate["blocked_short"],
            counterfactual_note=gate["counterfactual_note"],
        ),
        limitations=tuple(manifest["limitations"]),
    )


def _geometry_sample(entry: Any, metrics: Any) -> GeometrySampleRow:
    """One sample's row. Every figure was reduced by `fmis.swing_lab.metrics`."""
    win_rate, win_rate_reason = _measure(metrics.win_rate)
    expectancy, expectancy_reason = _measure(metrics.expectancy_r)
    median, median_reason = _measure(metrics.median_r)
    profit_factor, profit_factor_reason = _measure(metrics.profit_factor)
    planned_rr = next(
        (
            item["median"]
            for item in entry["diagnosis"]["distributions"]
            if item["label"] == "planned_rr"
        ),
        None,
    )
    return GeometrySampleRow(
        sample=entry["sample"],
        trades=metrics.trades,
        measurable=metrics.measurable_trades,
        refused=entry["refused"],
        win_rate=win_rate,
        win_rate_reason=win_rate_reason,
        expectancy=expectancy,
        expectancy_reason=expectancy_reason,
        median_r=median,
        median_r_reason=median_reason,
        profit_factor=profit_factor,
        profit_factor_reason=profit_factor_reason,
        total_r=format(metrics.total_r.quantize(_LAB_PLACES), "f"),
        max_drawdown=format(
            metrics.max_drawdown.max_drawdown_r.quantize(_LAB_PLACES), "f"
        ),
        median_planned_rr=None if planned_rr is None else f"{planned_rr:.3f}",
        largest_symbol_share=entry["largest_symbol_share"],
    )


def geometry_view(artifact: Any, *, digest_verified: bool) -> GeometryView:
    """Adapt one geometry artifact into the page's read model. A copy, never a measure.

    Every figure arrived reduced; nothing here is totalled, ranked or
    re-derived. Policy order is the artifact's own, which is the order the
    geometries were **pre-declared** in — deliberately not an order by result,
    because a table sorted by expectancy is a table that has chosen a winner.
    """
    manifest = artifact.manifest
    rows: list[GeometryPolicyRow] = []
    for policy_id in artifact.policy_ids:
        entry = artifact.policy(policy_id)
        rows.append(
            GeometryPolicyRow(
                policy_id=policy_id,
                title=entry["title"],
                family=entry["family"],
                hypothesis=entry["hypothesis"],
                stop_rule=entry["stop_rule"],
                target_rule=entry["target_rule"],
                is_production_geometry=entry["is_production_geometry"],
                verdict=entry["verdict"],
                verdict_statement=entry["verdict_statement"],
                development=_geometry_sample(
                    entry["development"], artifact.metrics(policy_id, "development")
                ),
                holdout=_geometry_sample(
                    entry["holdout"], artifact.metrics(policy_id, "holdout")
                ),
                criteria=tuple(
                    GeometryCriterionRow(
                        name=item["name"],
                        requirement=item["requirement"],
                        passed=item["passed"],
                        observed=item["observed"],
                    )
                    for item in entry["criteria"]
                ),
                blocking_criteria=tuple(
                    item["name"]
                    for item in entry["criteria"]
                    if item["passed"] is not True
                ),
            )
        )

    sensitivity: list[GeometrySensitivityRow] = []
    plateau_notes: list[str] = []
    for curve in artifact.payload["sensitivity"]:
        plateau_notes.append(
            f"{curve['kind']}: "
            + {
                True: "plateau — every measurable point agrees in sign",
                False: "NOT a plateau — the sign changes across the grid",
                None: "not evaluable — fewer than three points cleared the floor",
            }[curve["is_plateau"]]
        )
        for point in curve["points"]:
            sensitivity.append(
                GeometrySensitivityRow(
                    kind=curve["kind"],
                    threshold=f"{point['threshold']:.2f}",
                    development_trades=point["development_trades"],
                    development_expectancy=point["development_expectancy_r"],
                    holdout_trades=point["holdout_trades"],
                    holdout_expectancy=point["holdout_expectancy_r"],
                )
            )

    baseline = artifact.payload["policies"][0]["development"]["diagnosis"]
    return GeometryView(
        experiment_id=manifest["experiment_id"],
        development_symbols=tuple(manifest["development_symbols"]),
        holdout_symbols=tuple(manifest["holdout_symbols"]),
        measurement_start=manifest["measurement_start"],
        measurement_end=manifest["measurement_end"],
        admission=manifest["admission_policy_id"],
        candidate_count=manifest["candidate_count"],
        cost_policy=manifest["cost_policy"]["policy_id"],
        result_digest=manifest["result_digest"],
        digest_verified=digest_verified,
        policies=tuple(rows),
        candidate_policy_ids=artifact.candidate_policy_ids,
        sensitivity=tuple(sensitivity),
        plateau_notes=tuple(plateau_notes),
        baseline_findings=tuple(
            GeometryFindingRow(
                question=item["question"],
                supported=item["supported"],
                evidence=item["evidence"],
                reading=item["reading"],
            )
            for item in baseline["findings"]
        ),
        # Carried as the three stored values, never combined into a rate here:
        # a percentage is arithmetic, `fmis.swing_lab.geometry_diagnosis.Share`
        # already decided whether one may be stated at all, and this layer must
        # not be able to state one it refused.
        baseline_shares=tuple(
            GeometryShareRow(
                label=label,
                numerator=baseline[key]["numerator"],
                denominator=baseline[key]["denominator"],
                fraction=baseline[key]["fraction"],
                text=baseline[key]["text"],
            )
            for label, key in (
                ("setups planning reward < risk", "reward_below_risk"),
                ("target exits under +1R", "target_exits_below_one_r"),
                ("stops inside one ATR(14)", "stops_inside_one_atr"),
                ("trades giving back a full R", "mfe_exceeds_realized_by_one_r"),
                ("stop-outs whose target came later", "stopped_then_reached_target"),
            )
        ),
        limitations=tuple(manifest["limitations"]),
    )
