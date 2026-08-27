"""Running the sealed pre-registration. **Capture once, judge under three costs.**

    replay A (15 symbols, 2023-06 → 2026-08)      replay B (21 symbols, 2024-06 → 2026-08)
                    │                                            │
        ┌───────────┴───────────┐                                │
        ▼                       ▼                                ▼
    DEVELOPMENT             VALIDATION                        HOLDOUT
    2023-06 → 2025-06       2025-06 → 2026-08                 never measured before
        │                       │                                │
        └───────────────────────┴────────────────────────────────┘
                                │
                     11 sealed hypotheses × 3 cost scenarios
                                │
                    plateau · walk-forward · decompositions
                                │
                      fmis.swing_lab.validation.assess_candidate

**Two captures, and the second one exists to be untouched.** The development and
validation samples are cut from *one* replay by
`fmis.swing_lab.preregistration.SampleSpec.holds`, so they see byte-identical
candidates and differ only in date — a second replay would re-derive them and any
provider difference would surface as a period difference. The holdout is a
separate replay of symbols this repository has never looked at, and it is handed
in as its own argument so a study can be run *without* it: `run_validation_study`
accepts ``holdout=None`` and reports every holdout criterion as unevaluable,
which is what a development pass does before the holdout is opened.

**One simulation, three cost scenarios.** Every trade is simulated once under
`FRICTIONLESS_COSTS` and then re-priced by `fmis.swing_lab.trades.reprice`, which
changes what a fill *cost* and never where price went. That is what makes the
scenario comparison honest: the frictionless and costed tables describe the
identical trades, so any difference between them is the cost model and nothing
else. **The deciding scenario is the costed one**, and `run_validation_study`
asserts the metrics it hands to the verdict layer carry that policy's id rather
than documenting the intention.

**Nothing here selects a policy.** There is no ranking, no "best variant" field
and no argmax. Every hypothesis is judged independently against the sealed
criteria, and a study that named a winner would be choosing one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from fmis.decision_context import ContextPolicy
from fmis.market_regime import RegimePolicy
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport
from fmis.swing_lab.geometry import GeometryPolicy, PlansGeometry
from fmis.swing_lab.geometry_diagnosis import GeometryDiagnosis, diagnose_geometry
from fmis.swing_lab.geometry_replay import (
    GeometryCapture,
    PolicyOutcome,
    capture_geometry_candidates,
    trades_for_policy,
)
from fmis.swing_lab.geometry_study import GEOMETRY_LIMITATIONS, canonical_trade, records_for
from fmis.swing_lab.metrics import (
    SAMPLE_FLOOR,
    VariantMetrics,
    compute_lab_metrics,
    lab_breakdown_by,
)
from fmis.swing_lab.models import LabTrade, LabVariant, SwingLabError
from fmis.swing_lab.preregistration import (
    VALIDATION_COST_SCENARIOS,
    DECIDING_COST_POLICY_ID,
    PRE_REGISTRATION,
    PREREGISTRATION_DIGEST,
    PRIMARY_STOP_ATR,
    PRIMARY_TARGET_R,
    STOP_ATR_NEIGHBOURHOOD,
    TARGET_R_NEIGHBOURHOOD,
    FAMILY_PRIMARY,
    Hypothesis,
    Preregistration,
    SampleSpec,
    preregistration_digest,
    sample_membership,
    verify_preregistration,
)
from fmis.swing_lab.replay import dataset_for_group
from fmis.swing_lab.robustness import RobustnessReading, concentration_of, measure_robustness
from fmis.swing_lab.study import LAB_LIMITATIONS
from fmis.swing_lab.trades import FRICTIONLESS_COSTS, reprice
from fmis.swing_lab.variants import BASELINE_VARIANT
from fmis.swing_setup.backtest_harness import (
    DEFAULT_BACKTEST_LIMIT,
    DEFAULT_EVALUATION_WINDOW_BARS,
)
from fmis.swing_setup.research_harness import DEFAULT_IDENTITY_PRIMING_BARS, build_segments
from fmis.swing_setup.research_models import ResearchWindow, interval_duration
from fmis.swing_setup.research_warmup import (
    derive_warmup,
    probe_availability,
    required_from_by_interval,
)
from fmis.swing_lab.validation import (
    CandidateAssessment,
    NeighbourReading,
    PlateauClass,
    PlateauReading,
    assess_candidate,
    classify_plateau,
)
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "VALIDATION_SCHEMA_VERSION",
    "VALIDATION_LIMITATIONS",
    "WALK_FORWARD_MONTHS",
    "MAJOR_SYMBOLS",
    "SampleMeasurement",
    "PolicyValidation",
    "WalkForwardWindow",
    "Decomposition",
    "ValidationManifest",
    "ValidationStudy",
    "narrow_to_sample",
    "walk_forward",
    "walk_forward_boundaries",
    "decompose",
    "validation_digest",
    "run_validation_study",
    "run_validation_experiment",
    "capture_for_window",
]

#: Bumped whenever a persisted validation artifact changes shape.
VALIDATION_SCHEMA_VERSION: Final[int] = 1

#: The rung below the execution timeframe, used to order two events inside one
#: bar. Declared here rather than passed in: a study that could be asked for a
#: different refinement interval could be asked for a coarser one.
REFINEMENT_INTERVAL: Final[str] = "1h"

#: Rolling walk-forward window length. Six months on a 3.2-year span gives six
#: windows, which is enough to see whether a frozen policy behaves consistently
#: and few enough that each window can still clear the sample floor. Declared
#: here rather than swept: a window length chosen to make a curve look smoother
#: is a parameter of the presentation, not of the strategy.
WALK_FORWARD_MONTHS: Final[int] = 6

#: The liquid subset of the development universe, for §11's symbol-class split.
#: Chosen by market standing rather than by result — these are the six symbols
#: Milestone BW measured and the majors of the fifteen — and fixed before the
#: split was run.
MAJOR_SYMBOLS: Final[frozenset[str]] = frozenset(
    {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LTCUSDT"}
)

VALIDATION_LIMITATIONS: Final[tuple[str, ...]] = (
    "BY-1: Every limitation Milestones BW and BX carry applies unchanged. This "
    "milestone changes which structural level becomes a stop or a target, when "
    "a position is opened and how it is managed; it does not change the "
    "admission policy, the identity rule or the absence of position sizing.",
    "BY-2: The development sample is CONTAMINATED BY CONSTRUCTION. Milestone BX "
    "measured all fifteen of its symbols and BY's primary hypothesis is BX's "
    "own post-hoc finding. A positive development figure is a necessary "
    "condition for a candidate, never evidence for one. Only the validation "
    "period and the holdout symbols carry out-of-sample weight.",
    "BY-3: The holdout window opens 2024-06-01 rather than 2023-06-01 because "
    "those symbols' weekly history cannot reach the production warm-up start "
    "any earlier. Holdout and development therefore cover overlapping but not "
    "identical market periods, and a difference between them confounds symbol "
    "with period to that extent.",
    "BY-4: The holdout symbols are materially less liquid than the development "
    "set — median 24h quote volume ~0.7M USDT against ~18.8M, measured at the "
    "study's run date and not over its window. Under a frictionless scenario "
    "this does not bias R; under any cost scenario it means the holdout tests "
    "whether a rule generalises across STRUCTURE, not whether it would have "
    "been executable at size.",
    "BY-5: The universe is survivorship-filtered. Only currently-tradable USDT "
    "spot pairs were probed, so every symbol that was delisted inside the "
    "window is absent by construction. This flatters every variant equally, "
    "and it flatters them all.",
    "BY-6: The slippage sensitivity scenario is a FRICTION PROXY, not a spread "
    "model. It raises the fee rate to 15 bp per side rather than moving the "
    "fill price, so it understates slippage's effect on R for the tightest "
    "stops — where a price move of a few basis points is a large fraction of "
    "the risk denominator.",
    "BY-7: The pre-registered hypotheses overlap heavily — they share admission "
    "instants and differ only in stop and target — so they are not independent "
    "experiments and a multiple-testing correction across them would be too "
    "conservative in one direction and too loose in the other.",
    "BY-8: Lower-timeframe candles resolve OUTCOME ORDERING only. They never "
    "reach a planning decision, and an architecture guard asserts it. Where the "
    "finest available resolution still contains two levels in one bar, the "
    "trade stays AMBIGUOUS and is excluded from expectancy rather than guessed.",
    "BY-9: Exit mechanics arm from the bar AFTER the bar that triggered them, "
    "at whatever resolution resolved the trigger. A break-even stop is "
    "therefore not tested against the same bar's adverse extreme, because four "
    "prices cannot order a high against a low.",
)


def narrow_to_sample(capture: GeometryCapture, spec: SampleSpec) -> GeometryCapture:
    """One sample's slice of a capture. **Selection by symbol AND date, never both alone.**

    The candidates are the **same objects** the capture holds, so two samples cut
    from one replay cannot see different facts. ``bars_by_symbol`` is narrowed to
    the sample's symbols but never truncated in time: a trade opened on the last
    day of a sample must still resolve over the bars that follow it, and cutting
    the bars at the sample boundary would silently turn every such trade into a
    time stop.
    """
    if not isinstance(capture, GeometryCapture):
        raise TypeError("capture must be a GeometryCapture")
    if not isinstance(spec, SampleSpec):
        raise TypeError("spec must be a SampleSpec")
    return GeometryCapture(
        admission_variant_id=capture.admission_variant_id,
        admission_policy_id=capture.admission_policy_id,
        candidates=tuple(
            candidate
            for candidate in capture.candidates
            if spec.holds(candidate.symbol, candidate.signal_at)
        ),
        bars_by_symbol={
            symbol: bars
            for symbol, bars in capture.bars_by_symbol.items()
            if symbol in spec.symbols
        },
        metadata={**dict(capture.metadata), "sample": spec.name},
    )


@dataclass(frozen=True, slots=True)
class SampleMeasurement:
    """One policy, on one sample, under one cost scenario."""

    sample: str
    cost_policy_id: str
    trades: tuple[LabTrade, ...]
    admitted: int
    refused: int
    skip_reasons: tuple[tuple[str, int], ...]
    metrics: VariantMetrics
    diagnosis: GeometryDiagnosis | None
    robustness: RobustnessReading | None
    largest_symbol_share: Decimal | None
    #: One JSON-safe geometry record per trade, positionally aligned with
    #: ``trades``. **This is the chart seam.** A `LabTrade` carries prices and an
    #: outcome but not *where its stop came from*, and a future instrument page
    #: asked to draw BTCUSDT → this trade → these levels would otherwise have to
    #: re-run the replay to find out. Carried here rather than on `LabTrade`
    #: because it is a property of the PLAN, and Milestones BW and BX both
    #: deliberately keep plans and trades apart.
    geometry: tuple[Mapping[str, Any], ...] = ()

    @property
    def expectancy(self) -> Decimal | None:
        return self.metrics.expectancy_r.value


@dataclass(frozen=True, slots=True)
class PolicyValidation:
    """One sealed hypothesis measured on every sample under every cost scenario."""

    hypothesis: Hypothesis
    measurements: tuple[SampleMeasurement, ...]
    plateau: PlateauReading | None
    assessment: CandidateAssessment

    @property
    def policy_id(self) -> str:
        return self.hypothesis.policy_id

    def measurement(self, sample: str, cost_policy_id: str) -> SampleMeasurement:
        for item in self.measurements:
            if item.sample == sample and item.cost_policy_id == cost_policy_id:
                return item
        raise SwingLabError(
            f"{self.policy_id} holds no measurement of {sample!r} under "
            f"{cost_policy_id!r}; it holds "
            + ", ".join(f"{m.sample}/{m.cost_policy_id}" for m in self.measurements)
        )


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """One chronological window, with the frozen policy and no re-optimisation."""

    label: str
    start: datetime
    end: datetime
    metrics: VariantMetrics

    def payload(self) -> dict[str, Any]:
        value = self.metrics.expectancy_r.value
        factor = self.metrics.profit_factor.value
        rate = self.metrics.win_rate.value
        return {
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "trades": self.metrics.trades,
            "measurable_trades": self.metrics.measurable_trades,
            "expectancy_r": None if value is None else str(value),
            "profit_factor": None if factor is None else str(factor),
            "win_rate": None if rate is None else str(rate),
            "total_r": str(self.metrics.total_r),
            "max_drawdown_r": str(self.metrics.max_drawdown.max_drawdown_r),
            "average_win_r": (
                None if self.metrics.average_win_r.value is None
                else str(self.metrics.average_win_r.value)
            ),
            "average_loss_r": (
                None if self.metrics.average_loss_r.value is None
                else str(self.metrics.average_loss_r.value)
            ),
        }


@dataclass(frozen=True, slots=True)
class Decomposition:
    """One way of cutting a policy's trades, and the cohorts it produced."""

    name: str
    question: str
    cohorts: tuple[VariantMetrics, ...]

    @property
    def reportable(self) -> tuple[VariantMetrics, ...]:
        return tuple(item for item in self.cohorts if item.expectancy_r.is_present)

    @property
    def agrees_on_sign(self) -> bool | None:
        values = [
            item.expectancy_r.value
            for item in self.reportable
            if item.expectancy_r.value is not None
        ]
        if len(values) < 2:
            return None
        return all(v > 0 for v in values) or all(v < 0 for v in values)


def _month_floor(moment: datetime, months: int, origin: datetime) -> int:
    """Which walk-forward window an instant belongs to, counted from ``origin``."""
    elapsed = (moment.year - origin.year) * 12 + (moment.month - origin.month)
    if moment.day < origin.day:
        elapsed -= 1
    return max(elapsed, 0) // months


def _add_months(moment: datetime, months: int) -> datetime:
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    # Every window boundary in this study lands on the first of a month, so no
    # day-clamping is needed; the assertion says so rather than assuming it.
    if moment.day > 28:  # pragma: no cover - boundaries are month firsts
        raise SwingLabError(
            "walk-forward windows must start on or before the 28th so no month "
            f"arithmetic can clamp; got {moment.isoformat()}"
        )
    return moment.replace(year=year, month=month)


def walk_forward_boundaries(
    *, start: datetime, end: datetime, months: int = WALK_FORWARD_MONTHS
) -> tuple[tuple[datetime, datetime], ...]:
    """The half-open windows a walk-forward curve is cut into. **One owner.**

    Extracted from `walk_forward` unchanged so Milestone CA — whose unit is a
    paired decision instant rather than a `LabTrade` — cuts its curve on exactly
    the same boundaries rather than deriving a second set that could drift. A
    regression asserts `walk_forward` still produces the identical windows it did
    before this function existed.

    Raises:
        SwingLabError: ``end`` is not after ``start``, or ``months`` is not a
            positive int.
    """
    if end <= start:
        raise SwingLabError("end must be after start")
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise SwingLabError("months must be a positive int")
    boundaries: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        following = min(_add_months(cursor, months), end)
        boundaries.append((cursor, following))
        cursor = following
    return tuple(boundaries)


def walk_forward(
    trades: Sequence[LabTrade],
    *,
    start: datetime,
    end: datetime,
    months: int = WALK_FORWARD_MONTHS,
    label: str,
) -> tuple[WalkForwardWindow, ...]:
    """Chronological rolling evaluation of a **frozen** policy.

    No parameter is re-optimised inside a window and none could be: the policy
    that produced these trades was sealed before the study ran, so a window is a
    slice of one measurement rather than a fresh fit. The question this answers
    is only "does the same rule behave consistently across time", which is the
    question §12 asks.

    Windows that hold no trade are **still emitted**, with a zero count. A curve
    that silently omits its empty windows reads as continuous coverage when the
    policy in fact stopped trading, and that is exactly what a reader needs to
    see.
    """
    if end <= start:
        raise SwingLabError("end must be after start")
    if isinstance(months, bool) or not isinstance(months, int) or months <= 0:
        raise SwingLabError("months must be a positive int")

    boundaries = walk_forward_boundaries(start=start, end=end, months=months)

    buckets: dict[int, list[LabTrade]] = {index: [] for index in range(len(boundaries))}
    for trade in trades:
        for index, (lower, upper) in enumerate(boundaries):
            if lower <= trade.signal_at < upper:
                buckets[index].append(trade)
                break

    return tuple(
        WalkForwardWindow(
            label=f"{lower.date().isoformat()}→{upper.date().isoformat()}",
            start=lower,
            end=upper,
            metrics=compute_lab_metrics(
                tuple(buckets[index]),
                label=f"{label}:{lower.date().isoformat()}",
            ),
        )
        for index, (lower, upper) in enumerate(boundaries)
    )


def _symbol_class(trade: LabTrade) -> str:
    return "major" if trade.symbol in MAJOR_SYMBOLS else "non_major"


#: Every decomposition §11 and §13 require, as (name, question, key). Declared as
#: data so `REQUIRED_DECOMPOSITIONS` in the pre-registration and what is actually
#: computed can be checked against each other by a test rather than by reading.
_DECOMPOSITIONS: Final[
    tuple[tuple[str, str, Callable[[LabTrade], str]], ...]
] = (
    ("symbol", "Is the result one symbol's, or the universe's?", lambda t: t.symbol),
    (
        "direction",
        "Does the rule work in one direction only? A long-only edge across a "
        "period crypto spent rising is a market call wearing a strategy's clothes.",
        lambda t: t.direction.value,
    ),
    (
        "symbol_class",
        "Do the liquid majors and the rest of the universe agree? A rule that "
        "works only on thin instruments is not executable at size.",
        _symbol_class,
    ),
    (
        "context_regime",
        "Does the result depend on the context regime the admission gate let through?",
        lambda t: t.context_regime_structure or "unstated",
    ),
    (
        "setup_structural_trend",
        "Does the result depend on the setup timeframe's own structural trend?",
        lambda t: t.setup_structural_trend or "unstated",
    ),
)


def decompose(trades: Sequence[LabTrade]) -> tuple[Decomposition, ...]:
    """Every required decomposition, computed over one policy's trades.

    Cohorts below the sample floor report an **absence with a reason** rather
    than a small number — `fmis.swing_lab.metrics.LabMeasure` refuses to state a
    rate it cannot support, and with fifteen symbols over a few hundred trades
    that is the common case for the per-symbol cut.
    """
    return tuple(
        Decomposition(
            name=name,
            question=question,
            cohorts=lab_breakdown_by(tuple(trades), key),
        )
        for name, question, key in _DECOMPOSITIONS
    )


def _geometry_records(outcome: PolicyOutcome) -> tuple[Mapping[str, Any], ...]:
    """Each plan's provenance, as data a chart can resolve without a replay.

    Positionally aligned with `PolicyOutcome.trades` — `trades_for_policy`
    appends a plan and its trade together — and the correspondence is asserted
    by `records_for`, which refuses a mismatch rather than silently pairing each
    trade with the next trade's geometry.
    """
    return tuple(
        {
            "setup_id": plan.candidate.setup_id,
            "symbol": plan.candidate.symbol,
            "signal_at": plan.candidate.signal_at.isoformat(),
            # The OHLC window reference: which bar of the execution series
            # produced the signal. A chart resolves the event from this alone.
            "signal_index": plan.candidate.signal_index,
            "execution_interval": plan.candidate.execution_interval,
            "setup_interval": plan.candidate.setup_interval,
            "context_interval": plan.candidate.context_interval,
            "entry": plan.entry,
            "stop": plan.stop.price,
            "target": plan.target.price,
            "stop_provenance": plan.stop.provenance,
            "target_provenance": plan.target.provenance,
            "risk": plan.risk,
            "reward": plan.reward,
            "planned_rr": plan.planned_rr,
            "stop_bps": plan.stop_bps,
            "target_bps": plan.target_bps,
            "stop_atr_multiple": plan.stop_atr_multiple,
            "target_atr_multiple": plan.target_atr_multiple,
            "execution_atr": plan.candidate.execution_atr,
            "setup_atr": plan.candidate.setup_atr,
        }
        for plan in outcome.plans
    )


def _measure(
    outcome: PolicyOutcome,
    capture: GeometryCapture,
    *,
    sample: SampleSpec,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
    with_diagnosis: bool,
) -> SampleMeasurement:
    """One policy-sample-cost cell. Trades are re-priced, never re-simulated."""
    priced = tuple(reprice(trade, costs) for trade in outcome.trades)
    label = f"{outcome.policy.policy_id}:{sample.name}"
    skips: dict[str, int] = {}
    for skip in outcome.skips:
        skips[skip.reason.value] = skips.get(skip.reason.value, 0) + 1
    diagnosis = None
    if with_diagnosis:
        # `records_for` measures MFE/MAE from the bars, which no cost scenario
        # changes, so the diagnosis is computed once on the frictionless trades
        # and shared. Recomputing it per scenario would produce three identical
        # objects and invite a reader to compare them for a difference that
        # cannot exist.
        diagnosis = diagnose_geometry(
            records_for(outcome, capture, evaluation_window_bars=evaluation_window_bars),
            outcome.skips,
            label=label,
        )
    return SampleMeasurement(
        sample=sample.name,
        cost_policy_id=costs.policy_id,
        trades=priced,
        admitted=outcome.admitted,
        refused=outcome.refused,
        skip_reasons=tuple(sorted(skips.items())),
        metrics=compute_lab_metrics(priced, label=label),
        diagnosis=diagnosis,
        robustness=measure_robustness(
            priced,
            variant_id=outcome.policy.policy_id,
            measurement_start=sample.signal_start,
            measurement_end=sample.signal_end,
        ),
        largest_symbol_share=concentration_of(priced, lambda trade: trade.symbol),
        geometry=_geometry_records(outcome),
    )


def _on_the_cross(policy: PlansGeometry) -> bool:
    """Whether this policy is a point of the pre-declared primary cross.

    **Family membership, not threshold arithmetic.** The first version of this
    test asked only whether a policy carried a stop floor and a reward multiple
    matching the cross, and `by_setup_stop_0_5atr_target_2r` — the 1D-invalidation
    *alternative* — carries exactly (0.50, 2.0) while being a different rule
    entirely. It silently displaced the primary point in the neighbourhood and
    the plateau was classified against the wrong measurement. Reading the sealed
    family makes the collision unrepresentable.
    """
    return (
        isinstance(policy, GeometryPolicy)
        and policy.family == FAMILY_PRIMARY
        and policy.min_stop_atr is not None
        and policy.min_planned_rr is not None
    )


def _neighbourhood_for(policy: PlansGeometry) -> tuple[tuple[str, float, bool], ...]:
    """Which pre-declared cross a policy sits on, if any. **Axis, value, is-centre.**

    Only the primary family has a neighbourhood; an isolation control, the
    alternative and the non-structural twin have no declared cross and therefore
    no plateau test, which `assess_candidate` records as *not evaluable* rather
    than as a pass.
    """
    if not _on_the_cross(policy):
        return ()
    stop, target = policy.min_stop_atr, policy.min_planned_rr
    axes: list[tuple[str, float, bool]] = []
    # BOTH axes, not the first that matches. The primary point sits on the stop
    # sweep AND the target sweep, and returning only the first meant its
    # `parameter_plateau` was decided by one axis while the other was never
    # applied to it — which is not what "whether EACH parameter sits on a
    # plateau" says. A policy on both must satisfy both.
    if target == PRIMARY_TARGET_R and stop in STOP_ATR_NEIGHBOURHOOD:
        axes += [("stop_atr", value, value == stop) for value in STOP_ATR_NEIGHBOURHOOD]
    if stop == PRIMARY_STOP_ATR and target in TARGET_R_NEIGHBOURHOOD:
        axes += [("target_r", value, value == target) for value in TARGET_R_NEIGHBOURHOOD]
    return tuple(axes)


@dataclass(frozen=True, slots=True)
class ValidationManifest:
    """What was run, read off the run — and the seal it was run under."""

    experiment_id: str
    schema_version: int
    generated_at: datetime
    preregistration_id: str
    preregistration_digest: str
    preregistration_digest_matches: bool
    samples: tuple[Mapping[str, Any], ...]
    sample_membership: Mapping[str, int]
    policy_ids: tuple[str, ...]
    cost_policy_ids: tuple[str, ...]
    deciding_cost_policy_id: str
    admission_variant_id: str
    admission_policy_id: str
    evaluation_window_bars: int
    candle_limit: int
    primary_candidate_count: int
    holdout_candidate_count: int
    capture_metadata: Mapping[str, Any]
    holdout_capture_metadata: Mapping[str, Any] | None
    no_lookahead_proven: bool
    limitations: tuple[str, ...]
    result_digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "preregistration_id": self.preregistration_id,
            "preregistration_digest": self.preregistration_digest,
            "preregistration_digest_matches": self.preregistration_digest_matches,
            "samples": [dict(item) for item in self.samples],
            "sample_membership": dict(self.sample_membership),
            "policy_ids": list(self.policy_ids),
            "cost_policy_ids": list(self.cost_policy_ids),
            "deciding_cost_policy_id": self.deciding_cost_policy_id,
            "admission_variant_id": self.admission_variant_id,
            "admission_policy_id": self.admission_policy_id,
            "evaluation_window_bars": self.evaluation_window_bars,
            "candle_limit": self.candle_limit,
            "primary_candidate_count": self.primary_candidate_count,
            "holdout_candidate_count": self.holdout_candidate_count,
            "capture_metadata": dict(self.capture_metadata),
            "holdout_capture_metadata": (
                None if self.holdout_capture_metadata is None
                else dict(self.holdout_capture_metadata)
            ),
            "no_lookahead_proven": self.no_lookahead_proven,
            "limitations": list(self.limitations),
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class ValidationStudy:
    """Everything one pre-registered validation produced."""

    manifest: ValidationManifest
    policies: tuple[PolicyValidation, ...]
    #: The primary universe's chronological curve — development and validation
    #: only, which are the SAME fifteen symbols over one continuous span.
    #: **The holdout is deliberately excluded and carried separately.** Mixing
    #: them doubled the traded universe at 2024-06 (13 symbols before, 33 after)
    #: and made every window after that boundary describe a different market
    #: from the windows before it: a curve that changes what it measures
    #: half-way along cannot separate a decay in time from a change in universe,
    #: and reading one as the other is exactly the mistake it invites.
    walk_forward: tuple[WalkForwardWindow, ...]
    #: The holdout universe's own curve, over its own window.
    holdout_walk_forward: tuple[WalkForwardWindow, ...]
    #: Cuts over the primary universe, on the same footing as `walk_forward`.
    decompositions: tuple[Decomposition, ...]
    #: Cuts over the holdout universe, kept apart for the same reason.
    holdout_decompositions: tuple[Decomposition, ...]
    walk_forward_policy_id: str

    def policy(self, policy_id: str) -> PolicyValidation:
        for item in self.policies:
            if item.policy_id == policy_id:
                return item
        raise SwingLabError(
            f"this study holds no policy {policy_id!r}; it holds "
            f"{', '.join(item.policy_id for item in self.policies)}"
        )

    @property
    def candidates(self) -> tuple[PolicyValidation, ...]:
        """Every policy that met every sealed criterion. Usually empty, and that is a result."""
        from fmis.swing_lab.models import LabVerdict

        return tuple(
            item
            for item in self.policies
            if item.assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST
        )


def validation_digest(policies: Sequence[PolicyValidation]) -> str:
    """A stable digest over every trade in the study, every sample, every scenario.

    Sorted by the trade's own identity rather than by iteration order, so it is
    invariant to symbol ordering and to `PYTHONHASHSEED`. Any change to a
    geometry rule, a window, a cost policy or a fill rule changes it.
    """
    rows = sorted(
        (
            canonical_trade(trade)
            for policy in policies
            for measurement in policy.measurements
            for trade in measurement.trades
        ),
        key=lambda row: (row[0], row[16], row[1], row[4], row[2]),
    )
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_validation_study(
    primary: GeometryCapture,
    *,
    holdout: GeometryCapture | None,
    experiment_id: str,
    run_at: datetime,
    evaluation_window_bars: int,
    candle_limit: int,
    no_lookahead_proven: bool,
    preregistration: Preregistration = PRE_REGISTRATION,
    cost_scenarios: Sequence[PaperCostPolicy] = VALIDATION_COST_SCENARIOS,
) -> ValidationStudy:
    """Measure every sealed hypothesis on every sample under every cost scenario.

    ``holdout`` may be ``None``, which is how a development pass runs before the
    holdout is opened: every holdout criterion then reports *not evaluable* and
    no policy can reach `CANDIDATE_FOR_FORWARD_TEST`. That is the correct
    behaviour — a candidate proposed without its holdout is a candidate proposed
    without the evidence its own criteria demand.

    Raises:
        SwingLabError: the pre-registration digest does not match the sealed
            constant, a sample claims no candidates, or the deciding cost
            scenario is absent from ``cost_scenarios``.
    """
    if not isinstance(primary, GeometryCapture):
        raise TypeError("primary must be a GeometryCapture")
    if holdout is not None and not isinstance(holdout, GeometryCapture):
        raise TypeError("holdout must be a GeometryCapture or None")
    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise SwingLabError("run_at must be a timezone-aware datetime")
    scenario_ids = [policy.policy_id for policy in cost_scenarios]
    if DECIDING_COST_POLICY_ID not in scenario_ids:
        raise SwingLabError(
            f"the deciding cost scenario {DECIDING_COST_POLICY_ID!r} is not "
            f"among {scenario_ids}; a verdict must be reachable"
        )

    # Two different checks, and conflating them was the first design here.
    #
    # (1) Is the pre-registration MODULE intact? That is a property of the
    #     repository, it must hold for any run to mean anything, and a broken
    #     seal is refused outright.
    if not verify_preregistration(PREREGISTRATION_DIGEST):
        raise SwingLabError(
            "fmis.swing_lab.preregistration no longer digests to its own sealed "
            f"constant {PREREGISTRATION_DIGEST}. A study run under a broken seal "
            "is not a pre-registered study; restore the content, or re-seal "
            "deliberately and say so in the report."
        )
    # (2) Is THIS study measuring the sealed manifest, or a substituted one? A
    #     substitution is allowed — offline tests need it, and refusing would
    #     leave the orchestration untestable, which is worse — but it is
    #     recorded, printed, and it blocks every promotion, because
    #     `pre_registered` reads both this flag and the sealed policy-id set.
    live_digest = preregistration_digest(preregistration)
    digest_matches = live_digest == PREREGISTRATION_DIGEST

    development_spec = preregistration.sample("development")
    validation_spec = preregistration.sample("validation")
    holdout_spec = preregistration.sample("holdout")

    membership = dict(
        sample_membership(
            [(c.symbol, c.signal_at) for c in primary.candidates],
            (development_spec, validation_spec),
        )
    )
    if holdout is not None:
        holdout_counts = sample_membership(
            [(c.symbol, c.signal_at) for c in holdout.candidates], (holdout_spec,)
        )
        membership["holdout"] = holdout_counts["holdout"]
        membership["unclaimed"] += holdout_counts["unclaimed"]
    else:
        membership["holdout"] = 0

    captures: list[tuple[SampleSpec, GeometryCapture | None]] = [
        (development_spec, narrow_to_sample(primary, development_spec)),
        (validation_spec, narrow_to_sample(primary, validation_spec)),
        (holdout_spec, None if holdout is None else narrow_to_sample(holdout, holdout_spec)),
    ]
    for spec, cut in captures:
        if cut is not None and not cut.candidates:
            raise SwingLabError(
                f"sample {spec.name!r} claims no candidates from its capture. "
                "A sample measuring nothing is a window boundary error, not a "
                "result, and is refused rather than reported as zero trades."
            )

    deciding = next(p for p in cost_scenarios if p.policy_id == DECIDING_COST_POLICY_ID)

    # ---- every policy on every sample, simulated once and re-priced ----
    outcomes: dict[tuple[str, str], PolicyOutcome] = {}
    for hypothesis in preregistration.hypotheses:
        for spec, cut in captures:
            if cut is None:
                continue
            outcomes[(hypothesis.policy_id, spec.name)] = trades_for_policy(
                cut, hypothesis.policy,
                costs=FRICTIONLESS_COSTS,
                evaluation_window_bars=evaluation_window_bars,
            )

    measurements: dict[tuple[str, str, str], SampleMeasurement] = {}
    for hypothesis in preregistration.hypotheses:
        for spec, cut in captures:
            outcome = outcomes.get((hypothesis.policy_id, spec.name))
            if outcome is None or cut is None:
                continue
            for index, costs in enumerate(cost_scenarios):
                measurements[(hypothesis.policy_id, spec.name, costs.policy_id)] = _measure(
                    outcome, cut, sample=spec, costs=costs,
                    evaluation_window_bars=evaluation_window_bars,
                    # The diagnosis reads bars, which no cost scenario changes.
                    with_diagnosis=(index == 0),
                )

    def _empty(policy_id: str, spec: SampleSpec, costs: PaperCostPolicy) -> SampleMeasurement:
        """A sample that was never opened. Zero trades, and an honest label."""
        return SampleMeasurement(
            sample=spec.name, cost_policy_id=costs.policy_id, trades=(),
            admitted=0, refused=0, skip_reasons=(),
            metrics=compute_lab_metrics((), label=f"{policy_id}:{spec.name}"),
            diagnosis=None, robustness=None, largest_symbol_share=None,
            geometry=(),
        )

    # ---- plateau, using the DECIDING scenario's development metrics ----
    def deciding_metrics(policy_id: str) -> VariantMetrics:
        found = measurements.get((policy_id, development_spec.name, deciding.policy_id))
        if found is None:  # pragma: no cover - development is always captured
            raise SwingLabError(f"{policy_id} has no development measurement")
        return found.metrics

    by_thresholds: dict[tuple[str, float], str] = {}

    def claim(axis: str, value: float, policy_id: str) -> None:
        """Bind one cross point to exactly one policy. **One owner, or an error.**

        Written once and used for both axes rather than twice: the first version
        repeated the check per axis, and a probe removing only the stop-axis copy
        survived because the target-axis copy still fired. A rule enforced in two
        places is a rule half of which can be deleted unnoticed.
        """
        key = (axis, value)
        if key in by_thresholds:
            raise SwingLabError(
                f"two sealed policies claim the cross point {key}: "
                f"{by_thresholds[key]} and {policy_id}. A neighbourhood point "
                "must name exactly one measurement."
            )
        by_thresholds[key] = policy_id

    for hypothesis in preregistration.hypotheses:
        policy = hypothesis.policy
        # Family membership, never threshold arithmetic — see `_on_the_cross`.
        if not _on_the_cross(policy):
            continue
        if policy.min_planned_rr == PRIMARY_TARGET_R:
            claim("stop_atr", policy.min_stop_atr, policy.policy_id)
        if policy.min_stop_atr == PRIMARY_STOP_ATR:
            claim("target_r", policy.min_planned_rr, policy.policy_id)

    validations: list[PolicyValidation] = []
    for hypothesis in preregistration.hypotheses:
        cells: list[SampleMeasurement] = []
        for spec, cut in captures:
            for costs in cost_scenarios:
                key = (hypothesis.policy_id, spec.name, costs.policy_id)
                cells.append(
                    measurements[key]
                    if key in measurements
                    else _empty(hypothesis.policy_id, spec, costs)
                )

        cross = _neighbourhood_for(hypothesis.policy)
        plateau: PlateauReading | None = None
        if cross:
            readings = []
            for axis, value, is_primary in cross:
                neighbour_id = by_thresholds.get((axis, value))
                if neighbour_id is None:  # pragma: no cover - the cross is sealed
                    continue
                readings.append(
                    NeighbourReading(
                        policy_id=neighbour_id, axis=axis, threshold=value,
                        is_primary=is_primary, metrics=deciding_metrics(neighbour_id),
                    )
                )
            if readings:
                plateau = classify_plateau(readings)

        frozen_cells = tuple(cells)
        development = next(
            c for c in frozen_cells
            if c.sample == development_spec.name and c.cost_policy_id == deciding.policy_id
        )
        validation_cell = next(
            c for c in frozen_cells
            if c.sample == validation_spec.name and c.cost_policy_id == deciding.policy_id
        )
        holdout_cell = next(
            c for c in frozen_cells
            if c.sample == holdout_spec.name and c.cost_policy_id == deciding.policy_id
        )
        validations.append(
            PolicyValidation(
                hypothesis=hypothesis,
                measurements=frozen_cells,
                plateau=plateau,
                assessment=assess_candidate(
                    policy_id=hypothesis.policy_id,
                    is_structural=hypothesis.is_structural,
                    manifest_digest_matches=digest_matches,
                    development=development.metrics,
                    validation=validation_cell.metrics,
                    holdout=holdout_cell.metrics,
                    development_symbol_share=development.largest_symbol_share,
                    plateau=plateau,
                    no_lookahead_proven=no_lookahead_proven,
                    cost_policy_id=deciding.policy_id,
                ),
            )
        )

    ordered = tuple(validations)

    # ---- walk-forward and decompositions, on the PRIMARY hypothesis ----
    # Read off the PARAMETER, never the module global: `preregistration` is a
    # supported input (offline tests substitute one) and reaching past it for
    # the subject would make a substituted manifest raise a bare StopIteration
    # below instead of the named error this function documents.
    primary_policy_id = preregistration.hypothesis_for(
        f"by_stop_{_slug(PRIMARY_STOP_ATR)}atr_target_{_slug(PRIMARY_TARGET_R)}r"
    ).policy_id
    primary_validation = next(
        (v for v in ordered if v.policy_id == primary_policy_id), None
    )
    if primary_validation is None:
        raise SwingLabError(
            f"the walk-forward subject {primary_policy_id!r} is not among the "
            f"measured policies ({', '.join(v.policy_id for v in ordered)}). A "
            "substituted pre-registration must still declare the primary point."
        )

    def trades_of(*samples: str) -> tuple[LabTrade, ...]:
        wanted = set(samples)
        return tuple(
            trade
            for measurement in primary_validation.measurements
            if measurement.cost_policy_id == deciding.policy_id
            and measurement.sample in wanted
            for trade in measurement.trades
        )

    # The primary universe is development + validation: the SAME fifteen symbols
    # over one continuous span, so a window boundary is a date and nothing else.
    primary_trades = trades_of(development_spec.name, validation_spec.name)
    windows = walk_forward(
        primary_trades,
        start=development_spec.signal_start,
        end=validation_spec.signal_end,
        label=primary_policy_id,
    )
    holdout_trades = trades_of(holdout_spec.name)
    holdout_windows = (
        walk_forward(
            holdout_trades,
            start=holdout_spec.signal_start,
            end=holdout_spec.signal_end,
            label=f"{primary_policy_id}:holdout",
        )
        if holdout_trades
        else ()
    )
    cuts = decompose(primary_trades)
    holdout_cuts = decompose(holdout_trades) if holdout_trades else ()

    manifest = ValidationManifest(
        experiment_id=experiment_id,
        schema_version=VALIDATION_SCHEMA_VERSION,
        generated_at=run_at,
        preregistration_id=preregistration.preregistration_id,
        preregistration_digest=live_digest,
        preregistration_digest_matches=digest_matches,
        samples=tuple(spec.payload() for spec in preregistration.samples),
        sample_membership=membership,
        policy_ids=tuple(item.policy_id for item in ordered),
        cost_policy_ids=tuple(scenario_ids),
        deciding_cost_policy_id=deciding.policy_id,
        admission_variant_id=primary.admission_variant_id,
        admission_policy_id=primary.admission_policy_id,
        evaluation_window_bars=evaluation_window_bars,
        candle_limit=candle_limit,
        primary_candidate_count=len(primary.candidates),
        holdout_candidate_count=0 if holdout is None else len(holdout.candidates),
        capture_metadata=dict(primary.metadata),
        holdout_capture_metadata=None if holdout is None else dict(holdout.metadata),
        no_lookahead_proven=no_lookahead_proven,
        limitations=VALIDATION_LIMITATIONS + GEOMETRY_LIMITATIONS + LAB_LIMITATIONS,
        result_digest=validation_digest(ordered),
    )
    return ValidationStudy(
        manifest=manifest,
        policies=ordered,
        walk_forward=windows,
        holdout_walk_forward=holdout_windows,
        decompositions=cuts,
        holdout_decompositions=holdout_cuts,
        walk_forward_policy_id=primary_policy_id,
    )


def _slug(value: float) -> str:
    return f"{value:g}".replace(".", "_").replace("-", "neg")


def run_validation_experiment(
    *,
    run_at: datetime,
    experiment_id: str,
    open_holdout: bool,
    no_lookahead_proven: bool,
    preregistration: Preregistration = PRE_REGISTRATION,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    transport: Transport | None = None,
    base_url: str | None = None,
    with_mechanics: bool = False,
) -> "tuple[ValidationStudy, Any | None]":
    """Fetch, capture and judge — with **every input read from the sealed manifest**.

    There is deliberately no symbol argument, no window argument and no threshold
    argument. Milestone BX's command took `--development` and `--holdout` because
    its samples were a choice; BY's are part of what was frozen, and a study
    whose universe could be renamed at a shell prompt is not a pre-registered
    study. The only two things a caller decides are *when* it ran and *whether
    the holdout is opened* — and the second is a decision the milestone brief
    says to make once, late, and deliberately.

    ``open_holdout=False`` runs the development pass: the holdout replay is not
    even fetched, so it cannot be inspected by accident.

    Raises:
        SwingLabError: the seal is broken, or a window is unsatisfiable.
    """
    development = preregistration.sample("development")
    validation = preregistration.sample("validation")
    holdout_spec = preregistration.sample("holdout")

    primary = capture_for_window(
        development.symbols,
        measurement_start=min(development.signal_start, validation.signal_start),
        measurement_end=max(development.signal_end, validation.signal_end),
        run_at=run_at, evaluation_window_bars=evaluation_window_bars, limit=limit,
        transport=transport, base_url=base_url,
    )
    holdout = (
        capture_for_window(
            holdout_spec.symbols,
            measurement_start=holdout_spec.signal_start,
            measurement_end=holdout_spec.signal_end,
            run_at=run_at, evaluation_window_bars=evaluation_window_bars, limit=limit,
            transport=transport, base_url=base_url,
        )
        if open_holdout
        else None
    )
    study = run_validation_study(
        primary,
        holdout=holdout,
        experiment_id=experiment_id,
        run_at=run_at,
        evaluation_window_bars=evaluation_window_bars,
        candle_limit=limit,
        no_lookahead_proven=no_lookahead_proven,
        preregistration=preregistration,
    )
    mechanics = (
        _mechanics_for(
            primary,
            preregistration=preregistration,
            spec=development,
            evaluation_window_bars=evaluation_window_bars,
            transport=transport,
            base_url=base_url,
        )
        if with_mechanics
        else None
    )
    return study, mechanics


def _mechanics_for(
    capture: GeometryCapture,
    *,
    preregistration: Preregistration,
    spec: SampleSpec,
    evaluation_window_bars: int,
    transport: Transport | None,
    base_url: str | None,
) -> "Any":
    """Fetch the 1H rung and run the entry, exit and ambiguity studies.

    Kept behind a flag because it costs a second fetch — ~400k 1H rows for the
    primary universe — and because §7–§9 answer a different question from the
    sealed hypotheses. Without it `fmits research validation` printed "NOT
    MEASURED for this run" unconditionally, which made the entire mechanics
    layer unreachable from any shipped command and its published figures
    irreproducible outside a scratch script.

    The subject is the **production geometry**, because that is where Milestone
    BX found the ambiguity it declared NOT MEASURABLE; the primary rule's wider
    stop removes almost all of it, so measuring §8 on the primary rule would
    report a resolution rate for a problem it does not have.
    """
    from fmis.swing_lab.validation_mechanics import (
        MechanicsStudy,
        ambiguity_reading,
        fetch_refinement_bars,
        ladder_set,
        run_entry_study,
        run_exit_study,
    )

    cut = narrow_to_sample(capture, spec)
    geometry = preregistration.hypothesis_for("geom_production").policy
    execution = capture.metadata.get("timeframes", {}).get("execution", "4h")
    refinement = fetch_refinement_bars(
        spec.symbols, REFINEMENT_INTERVAL,
        start=spec.signal_start,
        end=spec.signal_end
        + evaluation_window_bars * interval_duration(execution),
        transport=transport, base_url=base_url,
    )
    ladders = ladder_set(
        cut, execution_interval=execution,
        refinement=refinement, refinement_interval=REFINEMENT_INTERVAL,
    )
    costs = next(
        item for item in preregistration.cost_scenarios
        if item.policy_id == preregistration.deciding_cost_policy_id
    )
    exits = run_exit_study(
        cut, geometry=geometry, ladders=ladders, costs=costs,
        execution_window_bars=evaluation_window_bars, sample=spec.name,
    )
    entries = run_entry_study(
        cut, geometry=geometry, ladders=ladders, costs=costs,
        execution_window_bars=evaluation_window_bars, sample=spec.name,
    )
    return MechanicsStudy(
        geometry_policy_id=geometry.policy_id,
        sample=spec.name,
        entries=entries,
        exits=exits,
        ambiguity=ambiguity_reading(exits),
    )


def capture_for_window(
    symbols: Sequence[str],
    *,
    measurement_start: datetime,
    measurement_end: datetime,
    run_at: datetime,
    admission: LabVariant = BASELINE_VARIANT,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    base_url: str | None = None,
    require_availability: bool = True,
    observer: Callable[[Any], None] | None = None,
) -> GeometryCapture:
    """Fetch history and freeze one replay's geometry candidates.

    Extracted from `fmis.swing_lab.geometry_study.run_geometry_experiment`'s own
    prelude and reused rather than restated, so BX's window derivation — the
    per-role warm-up, the identity-priming prefix and the outcome tail — governs
    BY's captures identically. Milestone BY needs the capture as a *value*
    (three samples are cut from two replays, and a holdout replay is deliberately
    run later and separately), which BX's all-in-one entry point cannot express.

    Raises:
        SwingLabError: the window is not satisfiable for some symbol and
            ``require_availability`` is set.
    """
    requested = tuple(symbols)
    if not requested:
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
        requested, intervals,
        required_from=required_from_by_interval(window, warmup, intervals),
        probed_at=run_at, transport=transport, base_url=base_url,
    )
    if require_availability and not availability.is_satisfiable:
        worst = availability.unsatisfied[0]
        raise SwingLabError(
            "the requested measurement window is not satisfiable: "
            f"{worst.symbol} {worst.interval} begins "
            f"{'never' if worst.earliest_open is None else worst.earliest_open.date()}, "
            f"{worst.required_from.date()} is required, short by {worst.shortfall}. "
            f"{len(availability.unsatisfied)} of {len(availability.series)} series "
            "are short. Move the start later, or drop the symbol."
        )

    dataset = dataset_for_group(
        requested, intervals, window=window, warmup=warmup, fetched_at=run_at,
        transport=transport, base_url=base_url,
    )
    capture = capture_geometry_candidates(
        requested, admission,
        window=window, segments=segments, dataset=dataset, limit=limit,
        identity_priming_bars=identity_priming_bars,
        policy=policy, context_policy=context_policy, detection=detection,
        observer=observer,
    )
    return GeometryCapture(
        admission_variant_id=capture.admission_variant_id,
        admission_policy_id=capture.admission_policy_id,
        candidates=capture.candidates,
        bars_by_symbol=capture.bars_by_symbol,
        metadata={
            **dict(capture.metadata),
            "measurement_start": measurement_start.isoformat(),
            "measurement_end": measurement_end.isoformat(),
            "warmup_start": window.warmup_start.isoformat(),
            "outcome_tail_end": window.outcome_tail_end.isoformat(),
            "symbols": list(requested),
            "intervals": list(intervals),
            "timeframes": {role.value: name for role, name in timeframes.items()},
        },
    )
