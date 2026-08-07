"""Composition root for the Swing Setup Engine — the network edge and its pure adapters.

    multi_timeframe_facts_for_symbol   ──►  MultiTimeframeFactSheet   (fmis.pipeline)
            │                                        │
            │                                        ├──► regime_for_sheet (per view)
            │                                        └──► build_evidence_report (SETUP view)
            ▼
    build_setup_inputs  ──►  SetupInputs  ──►  evaluate_setup  ──►  SetupAssessment
                                  ▲
                         evaluate_context (fmis.decision_context)

**This module adds no engine and computes no market quantity.** It fetches once
per timeframe through the existing multi-timeframe root, adapts what came back,
and hands the result to `fmis.swing_setup.policy`. Every number on the result
was produced by a layer below.

**Two small adapters are duplicated from `fmis.workspace.builder`, on purpose.**
`snapshot_from_sheet` and the `ContextInput` adapter both already exist there in
an identical shape. `fmis.swing_setup` does not import `fmis.workspace` — see
[ADR-0028](../../../docs/adr/ADR-0028-directional-interpretation-boundary.md) §3
for why a new top-level package importing a sibling top-level package's
internals was judged worse than duplicating ~20 lines of pure plumbing.

**Multi-symbol isolation follows the Deterministic Daily Workflow's contract
(Milestone AN), without importing that package.** `run_setup_for_symbols`
catches exactly the failures `PipelineError` and `BinanceError` name —
insufficient data and provider failures — and converts each into a
`SetupRunResult` carrying the reason, in requested order, one per symbol.
Anything else propagates: a defect in this repository must not be rendered as
an ordinary market failure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fmis.decision_context import (
    ContextInput,
    ContextPolicy,
    DecisionContext,
    ViewAdequacy,
    evaluate_context,
)
from fmis.decision_support import EvidenceReport, OverallState, build_evidence_report
from fmis.market_regime import (
    MarketRegime,
    ParticipationState,
    RegimeDimensionName,
    RegimePolicy,
    StructureState,
    VolatilityState,
)
from fmis.market_structure import required_candles
from fmis.pipeline.market_analysis import AnalysisSnapshot, PipelineError
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    MultiTimeframeFactSheet,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.regime import REGIME_LIMITATIONS, regime_features, regime_for_sheet
from fmis.pipeline.structural_facts import DetectionSettings, Limitation, StructuralFactSheet
from fmis.providers.binance import BinanceError, Transport
from fmis.swing_setup.models import ExecutionBreakEvent, SetupAssessment, SetupInputs
from fmis.swing_setup.policy import evaluate_setup

__all__ = [
    "SETUP_LIMITATIONS",
    "SETUP_ROLE",
    "snapshot_from_sheet",
    "context_input_from_sheet",
    "build_setup_inputs",
    "setup_assessment_for_sheet",
    "setup_inputs_and_assessment_for_sheet",
    "setup_for_symbol",
    "SetupRunResult",
    "run_setup_for_symbols",
]

#: Which role's evidence and structural trend feed the "does a thesis exist"
#: family, mirroring `fmis.workspace.builder.PRIMARY_ROLE`. The same role also
#: supplies the target candidate — one timeframe out from execution, following
#: the same "the higher timeframe carries the more significant level"
#: reasoning `fmis.pipeline.multi_timeframe` documents for context.
SETUP_ROLE = TimeframeRole.SETUP
EXECUTION_ROLE = TimeframeRole.EXECUTION
CONTEXT_ROLE = TimeframeRole.CONTEXT

SETUP_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "AR-1",
        "Probability is not calibrated. No backtested statistical model exists "
        "in this repository yet; probability.status is always NOT_CALIBRATED.",
    ),
    Limitation(
        "AR-2",
        "No position size, portfolio risk or leverage is computed. The "
        "existing 2% portfolio-risk maximum is a rule this package does not "
        "apply.",
    ),
    Limitation(
        "AR-3",
        "Stops and targets are the nearest already-detected structural level "
        "on the required side. No price is projected beyond what has already "
        "occurred, and one may be absent.",
    ),
    Limitation(
        "AR-4",
        "The execution-timeframe level watched for confirmation is the "
        "nearest same-side level by price to the last close, which may "
        "differ from the internal reference level the break-of-structure "
        "engine itself would use.",
    ),
    Limitation(
        "AR-5",
        "This is the first explicit hypothesis under policy v1. It is not "
        "validated against history and carries no claim of profitability or "
        "win rate.",
    ),
    Limitation(
        "AR-6",
        "A confirming execution-timeframe break is only honoured within "
        "CONFIRMATION_LOOKBACK_BARS (10) bars of the last closed candle. An "
        "older break on the confirming side does not confirm a candidate; "
        "the candidate stays CANDIDATE and the age is stated.",
    ),
)

#: The regime states that mean a dimension had nothing to read — used to build
#: `ViewAdequacy.dimensions_insufficient`, matching
#: `fmis.workspace.builder._INSUFFICIENT_STATES` exactly.
_INSUFFICIENT_REGIME_STATES = (
    StructureState.INSUFFICIENT,
    VolatilityState.INSUFFICIENT,
    ParticipationState.INSUFFICIENT,
)


def snapshot_from_sheet(sheet: StructuralFactSheet) -> AnalysisSnapshot:
    """Adapt a structural fact sheet into the snapshot the evidence layer reads.

    A copy, never a computation — see the module docstring for why this is
    duplicated rather than imported from `fmis.workspace.builder`.
    """
    if not isinstance(sheet, StructuralFactSheet):
        raise TypeError(
            f"sheet must be a StructuralFactSheet, got {type(sheet).__name__}"
        )
    return AnalysisSnapshot(
        symbol=sheet.symbol,
        interval=sheet.interval,
        as_of=sheet.as_of,
        window=sheet.window,
        features=sheet.features,
        metadata={"source": sheet.source, "adapted_from": "StructuralFactSheet"},
    )


def context_input_from_sheet(
    sheet: MultiTimeframeFactSheet,
    regimes: Mapping[TimeframeRole, MarketRegime],
    evidence: EvidenceReport | None,
    *,
    primary_role: TimeframeRole,
) -> ContextInput:
    """Adapt composed facts into the decision engine's narrow input.

    ``conflict_count`` is always 0: `fmis.decision_context` excludes conflicts
    from the sufficiency verdict entirely by design (its own docs), and this
    package does not compute a `Conflict` list (see the module docstring), so
    reporting a real conflict count here would cost a dependency for a number
    that never changes the answer.
    """
    views = tuple(
        ViewAdequacy(
            role=view.role.value,
            interval=view.interval,
            closed_candles=view.sheet.window.closed_count,
            required_candles=required_candles(
                view.sheet.detection.left_bars, view.sheet.detection.right_bars
            ),
            warming_up=len(view.sheet.warming_up),
            level_count=len(view.sheet.structure.levels),
            dimensions_insufficient=sum(
                1
                for dimension in regimes[view.role].dimensions
                if dimension.state in _INSUFFICIENT_REGIME_STATES
            ),
        )
        for view in sheet.views
    )
    return ContextInput(
        symbol=sheet.symbol,
        as_of=sheet.newest_as_of,
        views=views,
        primary_role=primary_role.value,
        evidence_is_insufficient=(
            evidence is None or evidence.state is OverallState.INSUFFICIENT_DATA
        ),
        conflict_count=0,
        metadata={"source": sheet.source},
    )


def _evidence_for(sheet: StructuralFactSheet) -> EvidenceReport | None:
    if sheet.window.last_close is None:
        return None
    return build_evidence_report(snapshot_from_sheet(sheet))


def _requirement_statements(context: DecisionContext) -> tuple[str, ...]:
    return tuple(check.statement for check in context.unmet)


def build_setup_inputs(
    sheet: MultiTimeframeFactSheet,
    regimes: Mapping[TimeframeRole, MarketRegime],
    evidence: EvidenceReport | None,
    context: DecisionContext,
) -> SetupInputs:
    """Adapt already-computed facts into the policy's narrow input. Pure.

    Raises:
        ValueError: the sheet does not carry all three roles this policy needs,
            or two roles were fetched at the same interval.
    """
    by_role = sheet.by_role
    missing = [
        role.value for role in (CONTEXT_ROLE, SETUP_ROLE, EXECUTION_ROLE) if role not in by_role
    ]
    if missing:
        raise ValueError(
            f"the swing setup policy needs context, setup and execution views; "
            f"missing: {missing}"
        )

    intervals = {
        role: by_role[role].interval for role in (CONTEXT_ROLE, SETUP_ROLE, EXECUTION_ROLE)
    }
    if len(set(intervals.values())) != 3:
        # Two roles at one interval read the same underlying candles, which
        # would silently count one fact as two independent directional
        # families — exactly the guarantee this policy exists to hold. Found
        # by the independent review; caught here rather than left to a
        # careful caller never picking colliding intervals.
        raise ValueError(
            "context, setup and execution must each be a distinct interval; "
            f"got {intervals[CONTEXT_ROLE]!r}, {intervals[SETUP_ROLE]!r}, "
            f"{intervals[EXECUTION_ROLE]!r}"
        )

    context_view = by_role[CONTEXT_ROLE].sheet
    setup_view = by_role[SETUP_ROLE].sheet
    execution_view = by_role[EXECUTION_ROLE].sheet

    context_regime = regimes[CONTEXT_ROLE].by_dimension
    execution_close = execution_view.window.last_close

    return SetupInputs(
        symbol=sheet.symbol,
        as_of=sheet.newest_as_of,
        source=sheet.source,
        context_interval=intervals[CONTEXT_ROLE],
        setup_interval=intervals[SETUP_ROLE],
        execution_interval=intervals[EXECUTION_ROLE],
        context_structural_trend=context_view.structure.trend,
        setup_structural_trend=setup_view.structure.trend,
        execution_structural_trend=execution_view.structure.trend,
        context_regime_structure=context_regime[RegimeDimensionName.STRUCTURE].state,
        context_regime_volatility=context_regime[RegimeDimensionName.VOLATILITY].state,
        context_regime_participation=context_regime[RegimeDimensionName.PARTICIPATION].state,
        evidence_state=None if evidence is None else evidence.state,
        evidence_dominant_alignment=(
            None if evidence is None else evidence.groups.dominant_alignment
        ),
        decision_context_state=context.state,
        decision_context_statements=_requirement_statements(context),
        execution_close=execution_close,
        execution_closed_count=execution_view.window.closed_count,
        execution_levels=execution_view.structure.levels,
        execution_breaks=tuple(
            ExecutionBreakEvent(level=b.level, index=b.index)
            for b in execution_view.structure.breaks
        ),
        setup_levels=setup_view.structure.levels,
        inherited_limitations=tuple(
            f"{item.code}: {item.text}"
            for item in (*sheet.limitations, *REGIME_LIMITATIONS, *SETUP_LIMITATIONS)
        ),
    )


def setup_inputs_and_assessment_for_sheet(
    sheet: MultiTimeframeFactSheet,
    *,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
) -> tuple[SetupInputs, SetupAssessment]:
    """Compose the policy's own input alongside its assessment. Pure.

    Identical composition to `setup_assessment_for_sheet`, which is now a thin
    wrapper over this function — no behaviour changes for any existing caller.
    Exists for a reader (or a future measurement layer, e.g. a historical
    backtest) that needs the structured facts an assessment was reasoned from
    — regime state, evidence leans, decision-context state — without either
    recomputing them or parsing them back out of `SetupAssessment`'s rendered
    text fields.
    """
    if not isinstance(sheet, MultiTimeframeFactSheet):
        raise TypeError(
            f"sheet must be a MultiTimeframeFactSheet, got {type(sheet).__name__}"
        )
    regimes: dict[TimeframeRole, MarketRegime] = {
        view.role: regime_for_sheet(view.sheet, policy=policy) for view in sheet.views
    }
    evidence = _evidence_for(sheet.by_role[SETUP_ROLE].sheet)
    context = evaluate_context(
        context_input_from_sheet(sheet, regimes, evidence, primary_role=SETUP_ROLE),
        context_policy,
    )
    inputs = build_setup_inputs(sheet, regimes, evidence, context)
    return inputs, evaluate_setup(inputs)


def setup_assessment_for_sheet(
    sheet: MultiTimeframeFactSheet,
    *,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
) -> SetupAssessment:
    """Compose one setup assessment from an already-built multi-timeframe sheet.

    Pure — no network and no clock. Every input was fetched by the caller.
    """
    _, assessment = setup_inputs_and_assessment_for_sheet(
        sheet, policy=policy, context_policy=context_policy
    )
    return assessment


def setup_for_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
) -> tuple[MultiTimeframeFactSheet, SetupAssessment]:
    """Fetch every timeframe once and compose the setup assessment over them.

    Returns the fact sheet beside the assessment, matching every other
    composition root in this repository: a result a reader cannot check against
    the facts beneath it is the opaque output this system exists to replace.
    """
    sheet = multi_timeframe_facts_for_symbol(
        symbol,
        timeframes=timeframes or DEFAULT_TIMEFRAMES,
        limit=limit,
        features=regime_features(),
        detection=detection,
        transport=transport,
        clock=clock,
        base_url=base_url,
    )
    return sheet, setup_assessment_for_sheet(
        sheet, policy=policy, context_policy=context_policy
    )


@dataclass(frozen=True, slots=True)
class SetupRunResult:
    """One requested symbol's outcome: an assessment, or the reason it has none.

    Exactly one of ``assessment``/``failure`` is set, following the same
    either/or discipline the Deterministic Daily Workflow's own per-symbol
    result applies to its two outcome fields.
    """

    requested_symbol: str
    assessment: SetupAssessment | None = None
    failure: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requested_symbol, str) or not self.requested_symbol.strip():
            raise ValueError("requested_symbol must be a non-empty str")
        if (self.assessment is None) == (self.failure is None):
            raise ValueError(
                "exactly one of assessment or failure must be set; a result "
                "with both or neither is not representable"
            )
        if self.assessment is not None and not isinstance(self.assessment, SetupAssessment):
            raise TypeError("assessment must be a SetupAssessment or None")
        if self.failure is not None and not isinstance(self.failure, str):
            raise TypeError("failure must be a str or None")


def run_setup_for_symbols(
    symbols: Sequence[str],
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
    """Assess every requested symbol, in requested order, isolating failures.

    Sequential, deliberately, following the Deterministic Daily Workflow's own
    reasoning: this fetches three timeframes per symbol, and a report a human
    reads in one sitting does not need provider-side concurrency risk to save
    wall time.

    Only `PipelineError` (insufficient data) and `BinanceError` (provider
    failures) are converted to a `SetupRunResult.failure`. Anything else is a
    defect and propagates, so a bug in this repository is never rendered as an
    ordinary market outcome.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
        raise TypeError(f"symbols must be a non-string sequence, got {type(symbols).__name__}")
    if not symbols:
        raise ValueError("at least one symbol is required")

    results = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"every symbol must be a non-empty str, got {symbol!r}")
        try:
            _, assessment = setup_for_symbol(
                symbol,
                timeframes=timeframes,
                limit=limit,
                policy=policy,
                context_policy=context_policy,
                detection=detection,
                transport=transport,
                clock=clock,
                base_url=base_url,
            )
        except (PipelineError, BinanceError) as error:
            results.append(
                SetupRunResult(
                    requested_symbol=symbol,
                    failure=f"{type(error).__name__}: {error}",
                )
            )
            continue
        results.append(SetupRunResult(requested_symbol=symbol, assessment=assessment))
    return tuple(results)
