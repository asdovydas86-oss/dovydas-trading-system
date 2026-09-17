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

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.market_pulse import (
    FreshnessState,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
)
from fmis.risk_policy import ENTRY_CAVEAT, PLANNING_LIMITATIONS
from fmis.swing_setup import BlockerKind, DevelopingEvidenceState
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
    BlockerRow,
    DevelopingEvidenceRow,
    EvidenceItemRow,
    FactorRow,
    ScanChangeView,
    SwingSnapshot,
    SwingView,
    SymbolChangeRow,
    SymbolDecisionRow,
    CrossingEventRow,
    FeatureReadingRow,
    StructuralLevelRow,
    StructureEventRow,
    TechnicalContextRow,
    TradeRiskPlanRow,
    TransitionRow,
    TimeframeRow,
    UnreadableRow,
    WarningRow,
    ValidationCriterionRow,
    ValidationSampleRow,
    ValidationCellRow,
    ValidationPolicyRow,
    ValidationPlateauPointRow,
    ValidationPlateauRow,
    ValidationWindowRow,
    ValidationCohortRow,
    ValidationDecompositionRow,
    ValidationView,
)

__all__ = [
    "counts_from",
    "pulse_view",
    "macro_view",
    "swing_view",
    "symbol_decision_rows",
    "technical_context_rows",
    "swing_snapshot",
    "scan_change_view",
    "portfolio_view",
    "paper_view",
    "performance_views",
    "health_view",
    "warning_rows",
    "lab_view",
    "geometry_view",
    "validation_view",
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


def _evidence_items(items: Any) -> tuple[EvidenceItemRow, ...]:
    """One evidence group, item for item. Nothing counted, nothing dropped."""
    return tuple(
        EvidenceItemRow(
            key=item.key,
            status=item.status,
            statement=item.statement,
            observed=item.observed,
            source=item.source,
            families=tuple(item.families),
            scope=item.scope,
            as_of=item.as_of,
            correlated_with=tuple(item.correlated_with),
            independence_note=item.independence_note,
        )
        for item in items
    )


def _developing_row(value: Any) -> DevelopingEvidenceRow | None:
    """The developing-evidence summary, translated field for field.

    ``state`` and ``lean`` are the enums' own values, read at runtime — this
    package never names a side, on ADR-0028's boundary.
    """
    if value is None:
        return None
    return DevelopingEvidenceRow(
        state=value.state.value,
        lean=None if value.lean is None else value.lean.value,
        agreeing=tuple(value.agreeing),
        opposing=tuple(value.opposing),
        non_voting=tuple(value.non_voting),
    )


def _blocker_row(value: Any) -> BlockerRow | None:
    """The named blocking condition, translated field for field."""
    if value is None:
        return None
    return BlockerRow(
        kind=value.kind.value,
        statement=value.statement,
        requirement=value.requirement,
        observed=value.observed,
        source=value.source,
    )


def _amount_or_reason(value: Any) -> tuple[str | None, str | None]:
    """Split a `Money`/`Quantity`/`Decimal` or `Absent` into text and a reason.

    **This function performs no arithmetic.** `Money.text` and `Quantity.text`
    are the domain's own canonical spelling of an amount it already computed;
    the asset is appended so a figure on the page always names what it is
    denominated in. A bare number beside a size would be an amount with no
    asset, which does not exist in this domain.
    """
    if value is None:
        return None, None
    reason = getattr(value, "reason", None)
    if reason is not None:
        return None, str(reason)
    text = getattr(value, "text", None)
    asset = getattr(value, "asset", None)
    if text is not None:
        return (f"{text} {asset}" if asset is not None else str(text)), None
    return str(value), None


def _trade_plan_row(plan: Any) -> TradeRiskPlanRow | None:
    """One `fmis.risk_policy.TradeRiskPlan`, translated field for field.

    `None` in, `None` out: a decision assembled with no declared risk policy has
    no planning row, and the Swing view's own note says why rather than leaving
    a reader to infer it from a missing panel.

    **Nothing is computed and nothing is defaulted.** Every value is the plan's
    own; every absence carries the plan's own reason.
    """
    if plan is None:
        return None
    direction, direction_reason = _amount_or_reason(plan.direction)
    entry, _ = _amount_or_reason(plan.entry)
    invalidation, _ = _amount_or_reason(plan.invalidation)
    risk_per_unit, risk_per_unit_reason = _amount_or_reason(plan.risk_per_unit)
    equity, equity_reason = _amount_or_reason(plan.equity)
    fraction, fraction_reason = _text_or_reason(plan.fraction_text)
    money_at_risk, money_at_risk_reason = _amount_or_reason(plan.money_at_risk)
    quantity, quantity_reason = _amount_or_reason(plan.quantity)
    notional, notional_reason = _amount_or_reason(plan.notional)
    reward_risk, reward_risk_reason = _text_or_reason(plan.reward_risk)
    return TradeRiskPlanRow(
        symbol=plan.symbol,
        status=plan.status.value,
        missing=tuple(plan.missing),
        reason=plan.reason,
        direction=direction,
        direction_reason=direction_reason or "",
        entry=entry,
        entry_caveat=ENTRY_CAVEAT if entry is not None else "",
        invalidation=invalidation,
        risk_per_unit=risk_per_unit,
        risk_per_unit_reason=risk_per_unit_reason or "",
        equity=equity,
        equity_reason=equity_reason or "",
        declared_at=(
            None
            if getattr(plan.declared_at, "reason", None) is not None
            else plan.declared_at.isoformat()
        ),
        contract_version=plan.contract_version,
        risk_fraction=fraction,
        risk_fraction_reason=fraction_reason or "",
        money_at_risk=money_at_risk,
        money_at_risk_reason=money_at_risk_reason or "",
        quantity=quantity,
        quantity_reason=quantity_reason or "",
        notional=notional,
        notional_reason=notional_reason or "",
        reward_risk=reward_risk,
        reward_risk_reason=reward_risk_reason or "",
        ceiling=plan.ceiling_text,
        ceiling_source=plan.ceiling_source,
        basis=plan.basis,
        caps=tuple(plan.caps),
        notes=tuple(plan.notes),
        portfolio_impact_reason=plan.portfolio_impact.reason,
        limitations=PLANNING_LIMITATIONS,
    )


#: The engine's own metadata key for *not enough history yet*. Carried as the
#: reason token rather than reworded here, on the `PlanningStatus` pattern: the
#: model holds the producer's word and `render` supplies a reader's.
WARMING_UP_REASON = "insufficient_data"

#: The engine's own metadata key for *warmed up and still undefined*, whose value
#: names which undefined case it was.
UNDEFINED_REASON = "undefined_reason"


def _level_row(level: Any) -> StructuralLevelRow | None:
    """One `PriceLevel`, translated field for field. `None` stays `None`.

    The side is the engine's own, and no role is derived from it. A level above
    the last close is a level above the last close.
    """
    if level is None:
        return None
    origin = level.origin
    return StructuralLevelRow(
        price=level.price,
        side=level.side.value,
        origin_label=None if origin is None else origin.label.value,
        origin_timestamp=None if origin is None else origin.timestamp,
        origin_index=None if origin is None else origin.index,
    )


def _crossing_row(event: Any) -> CrossingEventRow | None:
    """One `LevelCrossingEvent`, translated field for field. `None` stays `None`.

    ``kind`` and ``mechanism`` are the engine's nine-way classification, carried
    verbatim and never collapsed into a word this repository has not defined.
    """
    if event is None:
        return None
    return CrossingEventRow(
        kind=event.kind.value,
        mechanism=event.mechanism.value,
        side=event.level.side.value,
        level_price=event.level.price,
        as_of=event.timestamp,
        index=event.index,
    )


def _break_row(event: Any) -> StructureEventRow | None:
    """One `StructureBreak`, translated field for field. `None` stays `None`."""
    if event is None:
        return None
    return StructureEventRow(
        side=event.side.value,
        level_price=event.level.price,
        as_of=event.timestamp,
        index=event.index,
        origin_label=event.label.value,
    )


def _character_change_row(change: Any) -> StructureEventRow | None:
    """One `ChangeOfCharacter`, as its subject break plus the one it changed from.

    Both sides are carried because the pair is what makes the statement
    auditable — a reader sees that character did change, and from what. Neither
    side is named a direction and neither is called a reversal.
    """
    if change is None:
        return None
    return StructureEventRow(
        side=change.subject.side.value,
        level_price=change.subject.level.price,
        as_of=change.subject.timestamp,
        index=change.subject.index,
        origin_label=change.subject.label.value,
        previous_side=change.previous.side.value,
        previous_as_of=change.previous.timestamp,
    )


def _feature_rows(features: Any) -> tuple[FeatureReadingRow, ...]:
    """A `FeatureSet`'s results, in the engine's own order and under its own names.

    Three outcomes, kept apart because they are three different facts: a value;
    *not enough history yet*; and *enough history and still undefined*. The last
    one is real — a baseline window that traded nothing has no denominator — and
    a surface that showed it as a blank would be saying the first thing.

    A structured value's parts are carried in the producing mapping's own order.
    Nothing here is compared, combined or labelled.
    """
    rows: list[FeatureReadingRow] = []
    for name, result in features.features.items():
        value = result.value
        metadata = result.metadata
        if value is None:
            reason = metadata.get(UNDEFINED_REASON)
            if reason is None and metadata.get(WARMING_UP_REASON):
                reason = WARMING_UP_REASON
            rows.append(
                FeatureReadingRow(name=name, available=False, unavailable_reason=reason)
            )
            continue
        if isinstance(value, Mapping):
            rows.append(
                FeatureReadingRow(
                    name=name,
                    available=True,
                    components=tuple(value.items()),
                )
            )
            continue
        rows.append(FeatureReadingRow(name=name, available=True, value=value))
    return tuple(rows)


def technical_context_rows(technical: Any) -> tuple[TechnicalContextRow, ...]:
    """The recovered per-role technical context, translated field for field.

    **In the order the roles arrive**, which `fmis.pipeline` fixes as context,
    setup, execution — the gating role first, and the order the policy applies
    them in. This function does not reorder, merge or compare the roles, and
    derives nothing from their combination.

    Every value read here was produced by an engine and carried across the seam
    by `fmis.pipeline.technical_context` (ADR-0032). **The bounded selections —
    which crossing, which break, which character change a page prints — were
    made there, beside the full histories they were selected from.** Making one
    here would be this layer choosing which market event matters, which is the
    line between a window and an engine.

    `None` — a decision assembled without a context — yields an empty tuple, and
    the surface states the absence.
    """
    if technical is None:
        return ()
    rows: list[TechnicalContextRow] = []
    for view in technical.views:
        crossings = view.crossings
        rows.append(
            TechnicalContextRow(
                role=view.role,
                interval=view.interval,
                as_of=view.as_of,
                closed_count=view.closed_count,
                last_close=view.last_close,
                structural_trend=view.structural_trend.value,
                regime_structure=view.regime_structure.value,
                regime_volatility=view.regime_volatility.value,
                regime_participation=view.regime_participation.value,
                nearest_above=_level_row(view.nearest_above),
                nearest_below=_level_row(view.nearest_below),
                level_count=len(view.levels),
                upper_level_count=view.upper_level_count,
                lower_level_count=view.lower_level_count,
                crossing_count=crossings.count,
                latest_crossing=_crossing_row(crossings.latest),
                latest_close_breach=_crossing_row(crossings.latest_close_breach),
                break_count=len(view.breaks),
                latest_break=_break_row(view.latest_break),
                character_change_count=len(view.changes),
                latest_character_change=_character_change_row(view.latest_change),
                features=_feature_rows(view.features),
                warming_up=tuple(view.warming_up),
            )
        )
    return tuple(rows)


def symbol_decision_rows(decisions: Any) -> tuple[SymbolDecisionRow, ...]:
    """The workspace's per-symbol decisions, translated field for field.

    **In the order they arrive, which is scan order.** This function does not
    sort, filter, group or score; reordering here would invent the ranking
    `fmis.swing_workspace` deliberately refused to produce for this section.
    """
    return tuple(
        SymbolDecisionRow(
            symbol=decision.symbol,
            state=decision.state,
            classification=decision.classification,
            reason=decision.reason,
            sufficiency=decision.sufficiency,
            as_of=decision.as_of,
            direction=decision.direction,
            thesis=tuple(decision.thesis),
            regime_context=tuple(decision.regime_context),
            confirmation=tuple(decision.confirmation),
            invalidation=tuple(decision.invalidation),
            factors=tuple(
                FactorRow(
                    family=factor.family,
                    lean=factor.lean,
                    observed=factor.observed,
                    source=factor.source,
                )
                for factor in decision.factors
            ),
            supporting=_evidence_items(decision.supporting),
            conflicting=_evidence_items(decision.conflicting),
            missing=_evidence_items(decision.missing),
            unavailable=_evidence_items(decision.unavailable),
            agreeing_families=tuple(decision.agreeing_families),
            conflicting_families=tuple(decision.conflicting_families),
            independence_established=decision.independence_established,
            independence_caveats=tuple(decision.independence_caveats),
            evidence_warnings=tuple(decision.evidence_warnings),
            open_questions=tuple(decision.open_questions),
            decision_ready=decision.decision_ready,
            decision_ready_reason=decision.decision_ready_reason,
            evidence_reason=decision.evidence_reason,
            developing=_developing_row(decision.developing),
            blocker=_blocker_row(decision.blocker),
            timeframes=tuple(
                TimeframeRow(
                    role=line.role,
                    interval=line.interval,
                    as_of=line.as_of,
                    closed_count=line.closed_count,
                    age=line.age,
                    structural_trend=line.structural_trend,
                )
                for line in decision.timeframes
            ),
            plan=_trade_plan_row(decision.plan),
            technical=technical_context_rows(getattr(decision, "technical", None)),
        )
        for decision in decisions
    )


#: `SetupState`'s three values. Compared as strings rather than imported as enum
#: members, exactly as `fmis.swing_workspace.sections` compares the same three
#: for the same reason: a presentation layer that imports a domain vocabulary
#: becomes a second place that vocabulary lives.
_CONFIRMED = "confirmed"
_CANDIDATE = "candidate"
_WAITING = "wait"

#: The order the snapshot lists blocker kinds and developing states in: each
#: enum's own declaration order. **Not** frequency order — a distribution sorted
#: by size reads as a ranking of importance, and these are neither ranked nor
#: comparable. Read at import time from the enums themselves, so a member added
#: below appears here without an edit and cannot be silently omitted.
_BLOCKER_ORDER: tuple[str, ...] = tuple(kind.value for kind in BlockerKind)
_DEVELOPING_ORDER: tuple[str, ...] = tuple(
    state.value for state in DevelopingEvidenceState
)


def swing_snapshot(view_decisions: Any, *, unreadable: int) -> SwingSnapshot:
    """Tally the scan over the engine's own named conditions. **A count, never a verdict.**

    Counting is the one arithmetic this layer performs, and it performs it with
    `Counter` rather than `sum` — the aggregation guard forbids the builtins
    that turn a presentation layer into an engine, and a tally of named states
    is not an aggregation over financial values.

    Categories are the enums' own members, in the enums' own order. Nothing here
    invents a category, merges two, or orders by size.
    """
    states: Counter[str] = Counter(row.state for row in view_decisions)
    blockers: Counter[str] = Counter(
        row.blocker.kind for row in view_decisions if row.blocker is not None
    )
    developing: Counter[str] = Counter(
        row.developing.state for row in view_decisions if row.developing is not None
    )
    return SwingSnapshot(
        scanned=len(view_decisions),
        confirmed=states[_CONFIRMED],
        candidates=states[_CANDIDATE],
        waiting=states[_WAITING],
        unreadable=unreadable,
        blockers=tuple(
            (kind, blockers[kind]) for kind in _BLOCKER_ORDER if blockers[kind]
        ),
        developing=tuple(
            (state, developing[state])
            for state in _DEVELOPING_ORDER
            if developing[state]
        ),
    )


def _note_text(value: Any) -> str:
    """A `str | NotAvailable | None` note as the one sentence a page prints.

    `None` — a workspace built before this field existed — falls through to
    `SwingView`'s own default, which states the pre-declaration answer rather
    than nothing.
    """
    if value is None:
        return SwingView.__dataclass_fields__["risk_note"].default
    reason = getattr(value, "reason", None)
    return str(value) if reason is None else str(reason)


def swing_view(workspace: Any) -> SwingView:
    """The workspace's groups, each mapped in the order it arrived, plus the tally.

    The snapshot is built from the rows this function just built, rather than
    from the workspace a second time: one traversal, and the tiles at the top of
    the page cannot disagree with the table under them.
    """
    decisions = symbol_decision_rows(workspace.decisions)
    unreadable = tuple(
        UnreadableRow(symbol=entry.symbol, detail=entry.detail)
        for entry in workspace.unanalysed
    )
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
        unreadable=unreadable,
        ranking_rule=workspace.ranking_rule,
        scanned=workspace.summary.scanned,
        regime_note=workspace.summary.regime_note,
        decisions=decisions,
        snapshot=swing_snapshot(decisions, unreadable=len(unreadable)),
        breadth=tuple(workspace.summary.breadth),
        # The workspace has always produced this note and this layer has always
        # dropped it: `workspace.metadata` was read nowhere, so the dashboard
        # could not say whether a size had been computed or why not. Carried now,
        # with the pre-declaration default kept when the metadata has no entry.
        risk_note=_note_text(workspace.metadata.get("risk_note")),
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


# --------------------------------------------------------------- validation ---


def _validation_cell(entry: Any, *, deciding: str) -> "ValidationCellRow":
    """One (sample, cost) cell. Every figure arrived reduced; nothing is computed.

    The stored metrics payload is read directly rather than recomputed from the
    trades, because the artifact stores metrics per scenario and re-deriving them
    here would let the page disagree with the artifact it is displaying.
    """
    metrics = entry["metrics"]
    expectancy = metrics["expectancy_r"]
    return ValidationCellRow(
        sample=entry["sample"],
        cost_policy_id=entry["cost_policy_id"],
        is_deciding=entry["cost_policy_id"] == deciding,
        trades=metrics["trades"],
        measurable=metrics["measurable_trades"],
        ambiguous=metrics["ambiguous_trades"],
        refused=entry["refused"],
        win_rate=metrics["win_rate"]["value"],
        expectancy=expectancy["value"],
        expectancy_reason=expectancy["reason"],
        profit_factor=metrics["profit_factor"]["value"],
        total_r=metrics["total_r"],
        max_drawdown=metrics["max_drawdown_r"],
        largest_symbol_share=entry["largest_symbol_share"],
    )


def _validation_plateau(entry: Any) -> "ValidationPlateauRow | None":
    if entry is None:
        return None
    return ValidationPlateauRow(
        classification=entry["classification"],
        statement=entry["statement"],
        detail=entry["detail"],
        points=tuple(
            ValidationPlateauPointRow(
                axis=point["axis"],
                threshold=f"{point['threshold']:g}",
                is_primary=point["is_primary"],
                measurable=point["measurable_trades"],
                expectancy=point["expectancy_r"],
            )
            for point in entry["points"]
        ),
    )


def validation_view(
    artifact: Any, *, digest_verified: bool, seal_matches: bool
) -> ValidationView:
    """Adapt one validation artifact into the page's read model. A copy, never a measure.

    Policy order is the artifact's own, which is **pre-registration order** —
    deliberately not an order by result, because a table sorted by expectancy is
    a table that has chosen a winner.

    ``seal_matches`` is supplied rather than derived here for the same reason
    ``digest_verified`` is: verifying a digest is work, this layer performs none,
    and a contract guard asserts it.
    """
    manifest = artifact.manifest
    deciding = manifest["deciding_cost_policy_id"]
    membership = manifest["sample_membership"]

    policies: list[ValidationPolicyRow] = []
    for policy_id in artifact.policy_ids:
        entry = artifact.policy(policy_id)
        assessment = entry["assessment"]
        policies.append(
            ValidationPolicyRow(
                hypothesis_id=entry["hypothesis_id"],
                policy_id=policy_id,
                role=entry["role"],
                family=entry["family"],
                title=entry["title"],
                hypothesis=entry["hypothesis"],
                prediction=entry["prediction"],
                refuted_by=entry["refuted_by"],
                is_structural=entry["is_structural"],
                verdict=assessment["verdict"],
                verdict_statement=assessment["statement"],
                cells=tuple(
                    _validation_cell(cell, deciding=deciding)
                    for cell in entry["measurements"]
                ),
                criteria=tuple(
                    ValidationCriterionRow(
                        name=item["name"],
                        requirement=item["requirement"],
                        passed=item["passed"],
                        observed=item["observed"],
                    )
                    for item in assessment["criteria"]
                ),
                blocking_criteria=tuple(
                    item["name"]
                    for item in assessment["criteria"]
                    if item["passed"] is not True
                ),
                plateau=_validation_plateau(assessment["plateau"]),
            )
        )

    return ValidationView(
        experiment_id=manifest["experiment_id"],
        preregistration_id=manifest["preregistration_id"],
        preregistration_digest=manifest["preregistration_digest"],
        seal_matches=seal_matches,
        deciding_cost_policy_id=deciding,
        cost_policy_ids=tuple(manifest["cost_policy_ids"]),
        holdout_opened=manifest["holdout_candidate_count"] > 0,
        no_lookahead_proven=manifest["no_lookahead_proven"],
        result_digest=manifest["result_digest"],
        digest_verified=digest_verified,
        samples=tuple(
            ValidationSampleRow(
                name=spec["name"],
                role=spec["role"],
                symbols=tuple(spec["symbols"]),
                signal_start=spec["signal_start"],
                signal_end=spec["signal_end"],
                contamination=spec["contamination"],
                candidates=membership.get(spec["name"], 0),
            )
            for spec in manifest["samples"]
        ),
        unclaimed_candidates=membership.get("unclaimed", 0),
        policies=tuple(policies),
        walk_forward_policy_id=artifact.payload["walk_forward_policy_id"],
        walk_forward=tuple(
            ValidationWindowRow(
                label=window["label"],
                trades=window["trades"],
                measurable=window["measurable_trades"],
                win_rate=window["win_rate"],
                expectancy=window["expectancy_r"],
                profit_factor=window["profit_factor"],
                total_r=window["total_r"],
                max_drawdown=window["max_drawdown_r"],
            )
            for window in artifact.payload["walk_forward"]
        ),
        decompositions=tuple(
            ValidationDecompositionRow(
                name=cut["name"],
                question=cut["question"],
                agrees_on_sign=cut["agrees_on_sign"],
                cohorts=tuple(
                    ValidationCohortRow(
                        label=cohort["label"].split(":")[-1],
                        measurable=cohort["measurable_trades"],
                        expectancy=cohort["expectancy_r"]["value"],
                        expectancy_reason=cohort["expectancy_r"]["reason"],
                        total_r=cohort["total_r"],
                    )
                    for cohort in cut["cohorts"]
                ),
            )
            for cut in artifact.payload["decompositions"]
        ),
        limitations=tuple(manifest["limitations"]),
        candidate_policy_ids=artifact.candidate_policy_ids,
    )


# ---------------------------------------------------------------------------
# What changed since the previous comparable scan
# ---------------------------------------------------------------------------


def scan_change_view(comparison: Any) -> ScanChangeView:
    """One `fmis.scan_memory.ScanComparison`, translated field for field.

    **A translation and nothing else.** No dimension is added, dropped, merged
    or reordered here, and no symbol is filtered: the comparator decided what
    changed and this function carries that decision across the seam. Reordering
    the changed symbols would invent an attention ranking the engine
    deliberately refused to produce, so the tuple arrives in the scan's own
    universe order and leaves in it.

    The enum members are read at runtime for their own values, exactly as
    `_developing_row` and `_blocker_row` read theirs — this package names no
    dimension vocabulary of its own.
    """
    return ScanChangeView(
        status=comparison.status.value,
        current_scan_at=comparison.current_scan_at,
        previous_scan_at=comparison.previous_scan_at,
        reason=comparison.reason,
        changed=tuple(
            SymbolChangeRow(
                symbol=change.symbol,
                state=change.state,
                previous_state=change.previous_state,
                transitions=tuple(
                    TransitionRow(
                        dimension=transition.dimension.value,
                        previous=transition.previous,
                        current=transition.current,
                    )
                    for transition in change.transitions
                ),
            )
            for change in comparison.changes
        ),
        unchanged=tuple(comparison.unchanged),
        recorded=comparison.recorded,
        recording_note=comparison.recording_note,
    )
