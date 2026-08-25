"""Running one geometry experiment: capture once, judge many, hold a sample back.

    fetch ──► capture (expensive, once) ──┬──► development sample ──► 13 policies
                                          │                          + 2 sensitivity grids
                                          └──► holdout sample    ──► the same, untouched

**The holdout is a symbol split, and it is the honest one available.** Milestone
BW already measured BTC, ETH, BNB, LTC, XRP and ADA, and its report diagnosed the
geometry defect on those symbols. They are therefore *contaminated by
construction*: no policy written after BW can be called out-of-sample on them,
whatever a date split would say. The holdout is instead a set of symbols this
repository has never measured at all, over the identical window — so the two
samples differ in the one dimension that matters and in no other.

A chronological split is still run **inside** the development sample, as one of
`fmis.swing_lab.robustness`' four splits. It answers a different question — is
this one period? — and is reported as such rather than as a holdout.

**Nothing here selects a policy.** `fmis.swing_lab.geometry_verdict` judges each
policy against every criterion independently; this module runs the measurements
and hands them over. There is no ranking, no "best variant" field and no
argmax — a study that named a winner would be choosing one, and the criteria
exist precisely so that choice is not a judgement call.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from fmis.decision_context import ContextPolicy
from fmis.market_regime import RegimePolicy
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport
from fmis.swing_lab.geometry import GeometryPolicy
from fmis.swing_lab.geometry_diagnosis import (
    GeometryDiagnosis,
    GeometryRecord,
    diagnose_geometry,
)
from fmis.swing_lab.geometry_outcome import measure_outcome
from fmis.swing_lab.geometry_replay import (
    GeometryCapture,
    PolicyOutcome,
    capture_geometry_candidates,
    trades_for_policy,
)
from fmis.swing_lab.geometry_variants import (
    MIN_RR_SENSITIVITY_GRID,
    MIN_STOP_ATR_SENSITIVITY_GRID,
    PRE_DECLARED_GEOMETRIES,
    neighbours_of,
    sensitivity_series,
)
from fmis.swing_lab.geometry_verdict import GeometryAssessment, assess_geometry
from fmis.swing_lab.metrics import SAMPLE_FLOOR, VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import LabTrade, LabVariant, SwingLabError
from fmis.swing_lab.replay import dataset_for_group
from fmis.swing_lab.robustness import RobustnessReading, concentration_of, measure_robustness
from fmis.swing_lab.study import LAB_LIMITATIONS
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.variants import BASELINE_VARIANT
from fmis.swing_setup.backtest_harness import (
    DEFAULT_BACKTEST_LIMIT,
    DEFAULT_EVALUATION_WINDOW_BARS,
)
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    build_segments,
)
from fmis.swing_setup.research_models import ResearchWindow, interval_duration
from fmis.swing_setup.research_warmup import (
    derive_warmup,
    probe_availability,
    required_from_by_interval,
)
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "GEOMETRY_LIMITATIONS",
    "GEOMETRY_SCHEMA_VERSION",
    "SampleResult",
    "PolicyResult",
    "SensitivityPoint",
    "SensitivityCurve",
    "GeometryManifest",
    "GeometryStudy",
    "canonical_trade",
    "plateau_from",
    "geometry_digest",
    "records_for",
    "run_geometry_study",
    "run_geometry_experiment",
]

#: Bumped whenever a persisted geometry artifact changes shape.
GEOMETRY_SCHEMA_VERSION: Final[int] = 1

#: BX's own limitations, carried inside every artifact and printed on every
#: report. Milestone BW's `LAB_LIMITATIONS` apply beneath these unchanged — the
#: trade simulator, the fill rules and the cost model are the same ones.
GEOMETRY_LIMITATIONS: Final[tuple[str, ...]] = (
    "BX-1: Every limitation Milestone BW carries (BW-1 to BW-7, and BC/AV "
    "beneath them) applies unchanged. This milestone changes which structural "
    "level becomes a stop or a target; it does not change the fill rules, the "
    "cost model, the identity rule or the absence of position sizing.",
    "BX-2: The development sample is NOT out-of-sample in any strict sense. "
    "Milestone BW measured those six symbols and this milestone's hypotheses "
    "were written after reading BW's diagnosis of them. Only the holdout "
    "symbols were never measured before, and only holdout figures carry "
    "out-of-sample weight.",
    "BX-3: The universe is survivorship-filtered. EOSUSDT and NULSUSDT met the "
    "history requirement but stopped trading inside the window and were "
    "dropped rather than measured over a truncated span. Symbols that failed "
    "during the period are therefore under-represented, which flatters every "
    "variant equally but flatters them all.",
    "BX-4: The holdout symbols are materially less liquid than the development "
    "symbols. Under a frictionless cost scenario this does not bias R, but it "
    "means the holdout is a test of whether a geometry rule generalises across "
    "structure, NOT of whether it would have been executable at size.",
    "BX-5: Admission is held fixed at the production swing policy for every "
    "geometry variant. This milestone measures geometry, not entry selection: a "
    "variant that trades less does so because a geometry rule refused it, never "
    "because a different setup was found.",
    "BX-6: Volatility is the Wilder ATR(14) the regime feature set already "
    "computes on each view. No volatility engine was added, and no other "
    "measure of 'ordinary noise' was tried — a different one could rank the "
    "volatility variants differently.",
    "BX-7: Sensitivity grids are reported as curves and are NOT candidates. The "
    "best point on a grid was chosen by looking at results and can never be "
    "described as pre-declared.",
    "BX-8: Trades under different geometries overlap heavily — they share "
    "admission instants and differ only in stop and target — so the variants "
    "are not independent experiments and a multiple-testing correction across "
    "them would be too conservative in one direction and too loose in the other.",
)


@dataclass(frozen=True, slots=True)
class SampleResult:
    """One policy measured over one sample (development or holdout)."""

    sample: str
    policy: GeometryPolicy
    outcome: PolicyOutcome
    metrics: VariantMetrics
    diagnosis: GeometryDiagnosis
    robustness: RobustnessReading | None
    largest_symbol_share: Decimal | None

    @property
    def trades(self) -> tuple[LabTrade, ...]:
        return self.outcome.trades


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """One geometry policy on both samples, and the verdict the pair supports."""

    policy: GeometryPolicy
    development: SampleResult
    holdout: SampleResult
    assessment: GeometryAssessment


@dataclass(frozen=True, slots=True)
class SensitivityPoint:
    """One grid value's result on both samples. §9's plateau, one point of it."""

    threshold: float
    policy_id: str
    development: VariantMetrics
    holdout: VariantMetrics


@dataclass(frozen=True, slots=True)
class SensitivityCurve:
    """One threshold swept across its pre-declared grid.

    ``is_plateau`` asks the question §9 actually poses — *is this a plateau or a
    spike* — and answers it only from points that cleared the sample floor. It
    is ``None`` when fewer than three such points exist, because two points
    cannot distinguish a plateau from a slope.
    """

    kind: str
    points: tuple[SensitivityPoint, ...]

    @property
    def measurable_points(self) -> tuple[SensitivityPoint, ...]:
        return tuple(
            point for point in self.points if point.development.expectancy_r.is_present
        )

    @property
    def is_plateau(self) -> bool | None:
        values = [
            point.development.expectancy_r.value
            for point in self.measurable_points
            if point.development.expectancy_r.value is not None
        ]
        if len(values) < 3:
            return None
        return all(value > 0 for value in values) or all(value <= 0 for value in values)


@dataclass(frozen=True, slots=True)
class GeometryManifest:
    """What was run, exactly — read off the run, never typed beside it."""

    experiment_id: str
    schema_version: int
    generated_at: datetime
    development_symbols: tuple[str, ...]
    holdout_symbols: tuple[str, ...]
    measurement_start: datetime
    measurement_end: datetime
    warmup_start: datetime
    admission_variant_id: str
    admission_policy_id: str
    policy_ids: tuple[str, ...]
    candle_limit: int
    evaluation_window_bars: int
    cost_policy: Mapping[str, Any]
    candidate_count: int
    capture_metadata: Mapping[str, Any]
    limitations: tuple[str, ...]
    result_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "development_symbols": list(self.development_symbols),
            "holdout_symbols": list(self.holdout_symbols),
            "measurement_start": self.measurement_start.isoformat(),
            "measurement_end": self.measurement_end.isoformat(),
            "warmup_start": self.warmup_start.isoformat(),
            "admission_variant_id": self.admission_variant_id,
            "admission_policy_id": self.admission_policy_id,
            "policy_ids": list(self.policy_ids),
            "candle_limit": self.candle_limit,
            "evaluation_window_bars": self.evaluation_window_bars,
            "cost_policy": dict(self.cost_policy),
            "candidate_count": self.candidate_count,
            "capture_metadata": dict(self.capture_metadata),
            "limitations": list(self.limitations),
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class GeometryStudy:
    """Everything one geometry experiment produced."""

    manifest: GeometryManifest
    results: tuple[PolicyResult, ...]
    sensitivity: tuple[SensitivityCurve, ...]
    baseline_diagnosis: GeometryDiagnosis

    def result_for(self, policy_id: str) -> PolicyResult:
        for item in self.results:
            if item.policy.policy_id == policy_id:
                return item
        raise SwingLabError(
            f"this study holds no geometry {policy_id!r}; it holds "
            f"{', '.join(r.policy.policy_id for r in self.results)}"
        )

    @property
    def candidates(self) -> tuple[PolicyResult, ...]:
        """Every policy that met every criterion. Usually empty, and that is a result."""
        from fmis.swing_lab.models import LabVerdict

        return tuple(
            item
            for item in self.results
            if item.assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST
        )


def records_for(
    outcome: PolicyOutcome, capture: GeometryCapture, *, evaluation_window_bars: int
) -> tuple[GeometryRecord, ...]:
    """Join each plan with its trade and its after-the-fact measurements.

    `trades_for_policy` appends a plan and its trade together, so the two
    sequences correspond positionally. That correspondence is **checked** rather
    than trusted: a silent misalignment would measure every trade against the
    next trade's geometry and would look entirely plausible in a table.

    Raises:
        SwingLabError: the plan and trade sequences do not correspond.
    """
    if len(outcome.plans) != len(outcome.trades):
        raise SwingLabError(
            f"{outcome.policy.policy_id} produced {len(outcome.plans)} plans and "
            f"{len(outcome.trades)} trades; they must correspond one to one"
        )
    return tuple(
        GeometryRecord(
            plan=plan,
            trade=trade,
            outcome=measure_outcome(
                plan,
                trade,
                capture.bars_by_symbol[trade.symbol],
                evaluation_window_bars=evaluation_window_bars,
            ),
        )
        for plan, trade in zip(outcome.plans, outcome.trades, strict=True)
    )


def _measure_sample(
    capture: GeometryCapture,
    policy: GeometryPolicy,
    *,
    sample: str,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
    measurement_start: datetime,
    measurement_end: datetime,
    with_robustness: bool,
) -> SampleResult:
    outcome = trades_for_policy(
        capture, policy, costs=costs, evaluation_window_bars=evaluation_window_bars
    )
    records = records_for(
        outcome, capture, evaluation_window_bars=evaluation_window_bars
    )
    return SampleResult(
        sample=sample,
        policy=policy,
        outcome=outcome,
        metrics=compute_lab_metrics(
            outcome.trades, label=f"{policy.policy_id}:{sample}"
        ),
        diagnosis=diagnose_geometry(
            records, outcome.skips, label=f"{policy.policy_id}:{sample}"
        ),
        robustness=(
            measure_robustness(
                outcome.trades,
                variant_id=policy.policy_id,
                measurement_start=measurement_start,
                measurement_end=measurement_end,
            )
            if with_robustness
            else None
        ),
        largest_symbol_share=concentration_of(outcome.trades, lambda t: t.symbol),
    )


def _plateau_for(
    policy: GeometryPolicy,
    development: GeometryCapture,
    *,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
) -> tuple[bool | None, str]:
    """§9 for one policy: do its one-step threshold neighbours behave the same way?

    Passing requires every neighbour that cleared the sample floor to agree in
    sign with a positive result. A policy whose neighbours all thin below the
    floor returns ``None`` — the test could not be run, which is not a pass.
    """
    neighbours = neighbours_of(policy)
    if not neighbours:
        return None, "policy has no numeric threshold, so it has no neighbours"
    readings: list[tuple[str, VariantMetrics]] = []
    for neighbour in neighbours:
        outcome = trades_for_policy(
            development,
            neighbour,
            costs=costs,
            evaluation_window_bars=evaluation_window_bars,
        )
        readings.append(
            (
                neighbour.policy_id,
                compute_lab_metrics(outcome.trades, label=neighbour.policy_id),
            )
        )
    return plateau_from(readings)


def plateau_from(
    readings: Sequence[tuple[str, VariantMetrics]],
) -> tuple[bool | None, str]:
    """§9's plateau rule, as a pure function over neighbour readings.

    Separated from the replay so the *decision* can be tested without a capture:
    it is the rule, not the measurement, that decides whether a result is a
    plateau or a spike, and a mutation probe showed the rule was going
    unconstrained while the measurement around it was well covered.

    **Every** measurable neighbour must be positive — ``all``, never ``any``. One
    positive neighbour standing beside a negative one is precisely the spike this
    test exists to reject, and an ``any`` would report it as a plateau.

    ``None`` when no neighbour cleared the sample floor: the test could not be
    run, which is not a pass.
    """
    measurable = [
        (name, metrics)
        for name, metrics in readings
        if metrics.expectancy_r.value is not None
    ]
    detail = "; ".join(
        f"{name} "
        + (
            f"{metrics.expectancy_r.value:+.4f}R (n={metrics.measurable_trades})"
            if metrics.expectancy_r.value is not None
            else f"— (n={metrics.measurable_trades}, below floor)"
        )
        for name, metrics in readings
    )
    if not measurable:
        return None, f"no neighbour cleared the {SAMPLE_FLOOR}-trade floor: {detail}"
    return (
        all(metrics.expectancy_r.value > 0 for _, metrics in measurable),
        detail,
    )


def _sensitivity_curve(
    kind: str,
    grid: Sequence[float],
    development: GeometryCapture,
    holdout: GeometryCapture,
    *,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
) -> SensitivityCurve:
    points: list[SensitivityPoint] = []
    for threshold, policy in zip(grid, sensitivity_series(kind), strict=True):
        dev = trades_for_policy(
            development, policy, costs=costs, evaluation_window_bars=evaluation_window_bars
        )
        hold = trades_for_policy(
            holdout, policy, costs=costs, evaluation_window_bars=evaluation_window_bars
        )
        points.append(
            SensitivityPoint(
                threshold=threshold,
                policy_id=policy.policy_id,
                development=compute_lab_metrics(
                    dev.trades, label=f"{policy.policy_id}:development"
                ),
                holdout=compute_lab_metrics(
                    hold.trades, label=f"{policy.policy_id}:holdout"
                ),
            )
        )
    return SensitivityCurve(kind=kind, points=tuple(points))


def canonical_trade(trade: LabTrade) -> list[Any]:
    def text(value: Decimal | None) -> str | None:
        return None if value is None else format(value.normalize(), "f")

    return [
        trade.variant_id, trade.symbol, trade.setup_id, trade.direction.value,
        trade.signal_at.isoformat(),
        None if trade.entry_at is None else trade.entry_at.isoformat(),
        text(trade.entry_price), text(trade.initial_stop), text(trade.target),
        None if trade.exit_at is None else trade.exit_at.isoformat(),
        text(trade.exit_price), trade.exit_reason.value, trade.bars_held,
        text(trade.net_r), text(trade.mfe_r), text(trade.mae_r), trade.cost_policy_id,
    ]


def geometry_digest(results: Sequence[PolicyResult]) -> str:
    """A stable digest over every trade in the study, both samples included.

    Sorted by the trade's own identity rather than by iteration order, so the
    digest is invariant to symbol ordering and to `PYTHONHASHSEED`. Any change to
    a geometry rule, a window, a cost or a fill rule changes it.
    """
    rows = sorted(
        (
            canonical_trade(trade)
            for result in results
            for sample in (result.development, result.holdout)
            for trade in sample.trades
        ),
        key=lambda row: (row[0], row[1], row[4], row[2]),
    )
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_geometry_study(
    capture: GeometryCapture,
    *,
    development_symbols: Sequence[str],
    holdout_symbols: Sequence[str],
    experiment_id: str,
    run_at: datetime,
    measurement_start: datetime,
    measurement_end: datetime,
    warmup_start: datetime,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
    candle_limit: int,
    policies: Sequence[GeometryPolicy] = PRE_DECLARED_GEOMETRIES,
    with_sensitivity: bool = True,
) -> GeometryStudy:
    """Measure every policy on both samples and judge each against every criterion.

    The two samples are **cut from one capture**, so they see byte-identical
    candidate facts; a separate replay per sample would re-derive them and any
    provider difference would surface as a sample difference.

    Raises:
        SwingLabError: the samples overlap, either is empty, or a symbol is
            absent from the capture.
    """
    development_symbols = tuple(development_symbols)
    holdout_symbols = tuple(holdout_symbols)
    if not development_symbols or not holdout_symbols:
        raise SwingLabError("both the development and the holdout sample must be non-empty")
    shared = set(development_symbols) & set(holdout_symbols)
    if shared:
        raise SwingLabError(
            "the development and holdout samples must be disjoint; both hold "
            f"{', '.join(sorted(shared))}"
        )
    if not policies:
        raise SwingLabError("policies must be a non-empty sequence")

    development = capture.for_symbols(development_symbols)
    holdout = capture.for_symbols(holdout_symbols)

    results: list[PolicyResult] = []
    for policy in policies:
        dev = _measure_sample(
            development, policy, sample="development", costs=costs,
            evaluation_window_bars=evaluation_window_bars,
            measurement_start=measurement_start, measurement_end=measurement_end,
            with_robustness=True,
        )
        hold = _measure_sample(
            holdout, policy, sample="holdout", costs=costs,
            evaluation_window_bars=evaluation_window_bars,
            measurement_start=measurement_start, measurement_end=measurement_end,
            with_robustness=True,
        )
        plateau, plateau_detail = _plateau_for(
            policy, development, costs=costs,
            evaluation_window_bars=evaluation_window_bars,
        )
        results.append(
            PolicyResult(
                policy=policy,
                development=dev,
                holdout=hold,
                assessment=assess_geometry(
                    policy_id=policy.policy_id,
                    # Every policy in `PRE_DECLARED_GEOMETRIES` was written down
                    # before results existed; anything else is post-hoc and says so.
                    pre_declared=policy in PRE_DECLARED_GEOMETRIES,
                    development=dev.metrics,
                    holdout=hold.metrics,
                    development_symbol_share=dev.largest_symbol_share,
                    plateau=plateau,
                    plateau_detail=plateau_detail,
                ),
            )
        )

    ordered = tuple(results)
    curves: tuple[SensitivityCurve, ...] = ()
    if with_sensitivity:
        curves = (
            _sensitivity_curve(
                "min_rr", MIN_RR_SENSITIVITY_GRID, development, holdout,
                costs=costs, evaluation_window_bars=evaluation_window_bars,
            ),
            _sensitivity_curve(
                "min_stop_atr", MIN_STOP_ATR_SENSITIVITY_GRID, development, holdout,
                costs=costs, evaluation_window_bars=evaluation_window_bars,
            ),
        )

    baseline = ordered[0].development.diagnosis
    manifest = GeometryManifest(
        experiment_id=experiment_id,
        schema_version=GEOMETRY_SCHEMA_VERSION,
        generated_at=run_at,
        development_symbols=development_symbols,
        holdout_symbols=holdout_symbols,
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        warmup_start=warmup_start,
        admission_variant_id=capture.admission_variant_id,
        admission_policy_id=capture.admission_policy_id,
        policy_ids=tuple(policy.policy_id for policy in policies),
        candle_limit=candle_limit,
        evaluation_window_bars=evaluation_window_bars,
        cost_policy=costs.to_payload(),
        candidate_count=len(capture.candidates),
        capture_metadata=dict(capture.metadata),
        limitations=GEOMETRY_LIMITATIONS + LAB_LIMITATIONS,
        result_digest=geometry_digest(ordered),
    )
    return GeometryStudy(
        manifest=manifest,
        results=ordered,
        sensitivity=curves,
        baseline_diagnosis=baseline,
    )


def run_geometry_experiment(
    *,
    development_symbols: Sequence[str],
    holdout_symbols: Sequence[str],
    measurement_start: datetime,
    measurement_end: datetime,
    run_at: datetime,
    experiment_id: str,
    admission: LabVariant = BASELINE_VARIANT,
    costs: PaperCostPolicy = FRICTIONLESS_COSTS,
    policies: Sequence[GeometryPolicy] = PRE_DECLARED_GEOMETRIES,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    base_url: str | None = None,
    require_availability: bool = True,
    with_sensitivity: bool = True,
) -> GeometryStudy:
    """Fetch, capture once, and judge every geometry on both samples.

    The window is derived exactly as Milestone BC derives it and Milestone BW
    reuses it: a warm-up prefix computed from the production dependencies, an
    identity-priming prefix, and an outcome tail. **Both samples are fetched and
    replayed together**, so they share one dataset and one capture and cannot
    diverge for a provider reason.

    Raises:
        SwingLabError: the samples overlap or are empty, or the window is not
            satisfiable for some symbol and ``require_availability`` is set.
    """
    development_symbols = tuple(development_symbols)
    holdout_symbols = tuple(holdout_symbols)
    overlap = set(development_symbols) & set(holdout_symbols)
    if overlap:
        raise SwingLabError(
            "the development and holdout samples must be disjoint; both hold "
            f"{', '.join(sorted(overlap))}"
        )
    symbols = development_symbols + holdout_symbols
    if not symbols:
        raise SwingLabError("at least one symbol must be requested")
    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise SwingLabError("run_at must be a timezone-aware datetime")
    if measurement_end <= measurement_start:
        raise SwingLabError("measurement_end must be after measurement_start")

    timeframes = dict(admission.timeframes)
    warmup = derive_warmup(timeframes, limit=limit, detection=detection, policy=policy)
    execution_interval = timeframes[TimeframeRole.EXECUTION]
    priming_prefix = identity_priming_bars * interval_duration(execution_interval)
    window = ResearchWindow(
        warmup_start=measurement_start - warmup.prefix - priming_prefix,
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        outcome_tail_end=measurement_end
        + evaluation_window_bars * interval_duration(execution_interval),
    )
    segments = build_segments(window)
    intervals = tuple(sorted(set(timeframes.values())))

    availability = probe_availability(
        symbols,
        intervals,
        required_from=required_from_by_interval(window, warmup, intervals),
        probed_at=run_at,
        transport=transport,
        base_url=base_url,
    )
    if require_availability and not availability.is_satisfiable:
        worst = availability.unsatisfied[0]
        raise SwingLabError(
            "the requested measurement window is not satisfiable: "
            f"{worst.symbol} {worst.interval} begins "
            f"{'never' if worst.earliest_open is None else worst.earliest_open.date()}, "
            f"{worst.required_from.date()} is required, short by {worst.shortfall}. "
            f"{len(availability.unsatisfied)} of {len(availability.series)} series "
            "are short. Move --start later, or drop the symbol."
        )

    dataset = dataset_for_group(
        symbols, intervals, window=window, warmup=warmup, fetched_at=run_at,
        transport=transport, base_url=base_url,
    )
    capture = capture_geometry_candidates(
        symbols, admission,
        window=window, segments=segments, dataset=dataset, limit=limit,
        identity_priming_bars=identity_priming_bars,
        policy=policy, context_policy=context_policy, detection=detection,
    )
    return run_geometry_study(
        capture,
        development_symbols=development_symbols,
        holdout_symbols=holdout_symbols,
        experiment_id=experiment_id,
        run_at=run_at,
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        warmup_start=window.warmup_start,
        costs=costs,
        evaluation_window_bars=evaluation_window_bars,
        candle_limit=limit,
        policies=policies,
        with_sensitivity=with_sensitivity,
    )
