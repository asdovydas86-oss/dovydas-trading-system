"""Milestone BZ's study: the observational dataset, then the sealed exit families.

**Two halves, in this order, and the order is the discipline.** The path dataset
is built and understood first; only then is any exit policy measured. Reversing
them would mean choosing what to observe after seeing which rules worked, and
there is no way to tell that apart afterwards from the numbers alone.

    §5   observational   every entered position's causal post-entry path
    §7   give-back       BX's 68.8 % reproduced, then decomposed
    §8   exit families   six sealed hypotheses × two fixed geometries × three samples

**Nothing here decides what to measure.** Every symbol, window, checkpoint,
threshold, cost scenario and promotion criterion arrives from
`fmis.swing_lab.persistence_preregistration`, sealed and digested before the
first capture ran. This module reads that manifest and reports; it holds no
threshold of its own.

**Every family is measured against its own control on the same setups.** BY's
defect BY-D9 is the reason: a mechanic that watches a third level makes some
bars ambiguous that were clean for the control, and the trades that drop out are
exactly the ones that ran a full R and then stopped — losers that had been
winners. Comparing a depleted sample against a complete one flatters management
by construction, so every comparison here is over the setups **all** families
could measure, and the raw column is printed beside it rather than instead of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.swing_lab.exits import ExitPolicy, simulate_managed_trade
from fmis.swing_lab.geometry import GeometrySkip, PlansGeometry
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.intrabar import BarLadder
from fmis.swing_lab.metrics import (
    SAMPLE_FLOOR,
    VariantMetrics,
    compute_lab_metrics,
    lab_breakdown_by,
)
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_lab.persistence import (
    CHECKPOINT_BARS,
    EXCURSION_THRESHOLDS,
    PersistenceTrack,
    ThesisTimeline,
    observe_path,
)
from fmis.swing_lab.persistence_preregistration import (
    BZ_PRE_REGISTRATION,
    BZ_PREREGISTRATION_DIGEST,
    BzPreregistration,
    bz_preregistration_digest,
)
from fmis.swing_lab.robustness import concentration_of
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "BZ_SCHEMA_VERSION",
    "PathSummary",
    "GivebackDecomposition",
    "FamilyMeasurement",
    "FamilyComparison",
    "BzVerdict",
    "BzAssessment",
    "summarise_paths",
    "decompose_giveback",
    "observe_all_paths",
    "measure_family",
    "compare_families",
    "assess_bz",
    "PersistenceStudy",
    "run_persistence_experiment",
    "study_from_captures",
]

#: Bumped whenever a persisted BZ artifact changes shape.
BZ_SCHEMA_VERSION: Final[int] = 1


def _quantile(values: Sequence[Decimal], fraction: float) -> Decimal | None:
    """A nearest-rank quantile. **No interpolation between two real trades.**

    Interpolating would report a peak excursion that no position ever reached,
    which is a fabricated observation however small the error.
    """
    if not values:
        return None
    ordered = sorted(values)
    index = int(fraction * (len(ordered) - 1) + 0.5)
    return ordered[min(index, len(ordered) - 1)]


def _median_int(values: Sequence[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


# ---------------------------------------------------------------------------
# §5 — the observational dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PathSummary:
    """What the post-entry paths of one cohort looked like. **DESCRIPTIVE.**

    Every figure here conditions on a whole path and therefore contains the
    future as seen from any bar inside it. This type may be reported and may
    never be read as a decision rule; `assess_bz` consumes none of it.
    """

    label: str
    paths: int
    #: threshold → how many paths ever reached it
    ever_reached: Mapping[str, int]
    #: threshold → median bars to first arrival, over the paths that reached it
    median_bars_to: Mapping[str, float | None]
    ever_adverse: int
    median_bars_to_adverse: float | None
    median_bars_to_peak: float | None
    peak_r_p25: Decimal | None
    peak_r_median: Decimal | None
    peak_r_p75: Decimal | None
    giveback_median: Decimal | None
    gave_back_a_full_r: int
    #: checkpoint bar → thesis state → count. The state distribution over time.
    thesis_at_checkpoint: Mapping[int, Mapping[str, int]]

    @property
    def full_r_giveback_rate(self) -> float | None:
        return None if self.paths == 0 else self.gave_back_a_full_r / self.paths

    def rate_reached(self, threshold: str) -> float | None:
        if self.paths == 0:
            return None
        return self.ever_reached.get(threshold, 0) / self.paths

    def payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "paths": self.paths,
            "ever_reached": dict(sorted(self.ever_reached.items())),
            "median_bars_to": dict(sorted(self.median_bars_to.items())),
            "ever_adverse": self.ever_adverse,
            "median_bars_to_adverse": self.median_bars_to_adverse,
            "median_bars_to_peak": self.median_bars_to_peak,
            "peak_r_p25": None if self.peak_r_p25 is None else str(self.peak_r_p25),
            "peak_r_median": (
                None if self.peak_r_median is None else str(self.peak_r_median)
            ),
            "peak_r_p75": None if self.peak_r_p75 is None else str(self.peak_r_p75),
            "giveback_median": (
                None if self.giveback_median is None else str(self.giveback_median)
            ),
            "gave_back_a_full_r": self.gave_back_a_full_r,
            "full_r_giveback_rate": self.full_r_giveback_rate,
            "thesis_at_checkpoint": {
                str(bar): dict(sorted(states.items()))
                for bar, states in sorted(self.thesis_at_checkpoint.items())
            },
        }


def summarise_paths(
    tracks: Sequence[PersistenceTrack], *, label: str
) -> PathSummary:
    """Fold a cohort of paths into the distributions §5 asks for. **Pure.**"""
    reached: dict[str, int] = {}
    bars_to: dict[str, list[int]] = {}
    for track in tracks:
        for key, bar in track.bars_to_excursion.items():
            reached[key] = reached.get(key, 0) + 1
            bars_to.setdefault(key, []).append(bar)

    adverse = [t.bars_to_adverse for t in tracks if t.bars_to_adverse is not None]
    peaks = [t.bars_to_peak_r for t in tracks if t.bars_to_peak_r is not None]
    peak_values = [t.peak_r for t in tracks]
    givebacks = [t.total_giveback_r for t in tracks]

    at_checkpoint: dict[int, dict[str, int]] = {}
    for track in tracks:
        for checkpoint in track.checkpoints:
            states = at_checkpoint.setdefault(checkpoint.bar, {})
            key = checkpoint.thesis.value
            states[key] = states.get(key, 0) + 1

    return PathSummary(
        label=label,
        paths=len(tracks),
        ever_reached=reached,
        median_bars_to={
            str(threshold): _median_int(bars_to.get(str(threshold), []))
            for threshold in EXCURSION_THRESHOLDS
        },
        ever_adverse=len(adverse),
        median_bars_to_adverse=_median_int(adverse),
        median_bars_to_peak=_median_int(peaks),
        peak_r_p25=_quantile(peak_values, 0.25),
        peak_r_median=_quantile(peak_values, 0.50),
        peak_r_p75=_quantile(peak_values, 0.75),
        giveback_median=_quantile(givebacks, 0.50),
        gave_back_a_full_r=sum(1 for t in tracks if t.gave_back_a_full_r),
        thesis_at_checkpoint=at_checkpoint,
    )


def observe_all_paths(
    capture: GeometryCapture,
    *,
    geometry: PlansGeometry,
    timelines: Mapping[str, ThesisTimeline],
    sample_of,
    evaluation_window_bars: int,
) -> tuple[PersistenceTrack, ...]:
    """One causal path per position the geometry opened. **The shared input.**

    A candidate whose plan is skipped produces no path — there was no position —
    and a plan whose entry bar does not exist produces none either. Both are
    counted by the caller from the plan and trade counts rather than inferred
    from a missing path, because a silently absent path and a refused setup look
    identical in a length.
    """
    tracks: list[PersistenceTrack] = []
    for candidate in capture.candidates:
        outcome = geometry.plan(candidate)
        if isinstance(outcome, GeometrySkip):
            continue
        spec = sample_of(candidate.symbol, candidate.signal_at)
        if spec is None:
            continue
        bars = capture.bars_by_symbol[candidate.symbol]
        if len(bars) <= candidate.signal_index + 1:
            continue
        entry_price = bars[candidate.signal_index + 1].open
        stop = Decimal(str(outcome.stop.price))
        # A position that opened at or beyond its own stop has no risk
        # denominator, so it has no measurable path. `simulate_trade` records it
        # as ENTRY_GAPPED_THROUGH_STOP and so does the exit study; the path
        # dataset simply has nothing to observe, which is a different statement
        # from "it did not happen".
        side = 1 if candidate.direction.value == "long" else -1
        if side * (entry_price - stop) <= 0:
            continue
        tracks.append(
            observe_path(
                bars,
                symbol=candidate.symbol,
                setup_id=candidate.setup_id,
                direction=candidate.direction,
                sample=spec.name,
                signal_at=candidate.signal_at,
                signal_index=candidate.signal_index,
                entry_price=entry_price,
                initial_stop=stop,
                target=Decimal(str(outcome.target.price)),
                evaluation_window_bars=evaluation_window_bars,
                timeline=timelines.get(candidate.symbol),
                checkpoints=CHECKPOINT_BARS,
            )
        )
    return tuple(tracks)


# ---------------------------------------------------------------------------
# §7 — the give-back finding, reproduced and decomposed
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GivebackDecomposition:
    """BX's 68.8 % reproduced under BZ's dataset, then taken apart. **DESCRIPTIVE.**"""

    label: str
    paths: int
    gave_back_a_full_r: int
    #: excursion threshold → (paths that reached it, their median REALISED R)
    realised_after_reaching: Mapping[str, tuple[int, Decimal | None]]
    median_bars_peak_to_exit: float | None
    by_direction: Mapping[str, tuple[int, float | None]]
    largest_symbol_share: Decimal | None
    by_context_regime: Mapping[str, tuple[int, float | None]]

    @property
    def rate(self) -> float | None:
        return None if self.paths == 0 else self.gave_back_a_full_r / self.paths

    def payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "paths": self.paths,
            "gave_back_a_full_r": self.gave_back_a_full_r,
            "rate": self.rate,
            "realised_after_reaching": {
                key: [count, None if value is None else str(value)]
                for key, (count, value) in sorted(self.realised_after_reaching.items())
            },
            "median_bars_peak_to_exit": self.median_bars_peak_to_exit,
            "by_direction": {
                key: [count, rate] for key, (count, rate) in sorted(
                    self.by_direction.items()
                )
            },
            "largest_symbol_share": (
                None if self.largest_symbol_share is None
                else str(self.largest_symbol_share)
            ),
            "by_context_regime": {
                key: [count, rate] for key, (count, rate) in sorted(
                    self.by_context_regime.items()
                )
            },
        }


def decompose_giveback(
    tracks: Sequence[PersistenceTrack],
    control_trades: Sequence[LabTrade],
    *,
    label: str,
) -> GivebackDecomposition:
    """Reproduce the give-back rate, then cut it every way §7 asks for.

    ``control_trades`` are the H0 trades for the SAME setups, keyed by setup id,
    so "what did a path that reached +1R actually realise" is answered from the
    control's own exit rather than from the path's unrealised final close. The
    two are different quantities and conflating them would answer a question
    nobody asked.
    """
    by_setup = {trade.setup_id: trade for trade in control_trades}

    realised: dict[str, tuple[int, Decimal | None]] = {}
    for threshold in EXCURSION_THRESHOLDS:
        key = str(threshold)
        values = [
            by_setup[t.setup_id].net_r
            for t in tracks
            if key in t.bars_to_excursion
            and t.setup_id in by_setup
            and by_setup[t.setup_id].net_r is not None
        ]
        realised[key] = (len(values), _quantile(values, 0.50))

    peak_to_exit = [
        by_setup[t.setup_id].bars_held - t.bars_to_peak_r
        for t in tracks
        if t.bars_to_peak_r is not None
        and t.setup_id in by_setup
        and by_setup[t.setup_id].bars_held >= t.bars_to_peak_r
    ]

    def cut(key) -> Mapping[str, tuple[int, float | None]]:
        buckets: dict[str, list[PersistenceTrack]] = {}
        for track in tracks:
            buckets.setdefault(key(track), []).append(track)
        return {
            name: (
                len(members),
                (
                    None
                    if len(members) < SAMPLE_FLOOR
                    else sum(1 for m in members if m.gave_back_a_full_r) / len(members)
                ),
            )
            for name, members in sorted(buckets.items())
        }

    regime_of = {
        trade.setup_id: trade.context_regime_structure for trade in control_trades
    }
    return GivebackDecomposition(
        label=label,
        paths=len(tracks),
        gave_back_a_full_r=sum(1 for t in tracks if t.gave_back_a_full_r),
        realised_after_reaching=realised,
        median_bars_peak_to_exit=_median_int(peak_to_exit),
        by_direction=cut(lambda t: t.direction.value),
        largest_symbol_share=concentration_of(
            [t for t in control_trades if t.net_r is not None], lambda t: t.symbol
        ),
        by_context_regime=cut(lambda t: regime_of.get(t.setup_id, "unattributed")),
    )


# ---------------------------------------------------------------------------
# §8 — the sealed exit families
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FamilyMeasurement:
    """One exit family, one geometry, one sample, one cost scenario."""

    policy_id: str
    hypothesis_id: str
    geometry_policy_id: str
    sample: str
    cost_policy_id: str
    trades: tuple[LabTrade, ...]
    metrics: VariantMetrics
    fired: int
    ambiguous: int
    exit_reasons: tuple[tuple[str, int], ...]
    #: Re-measured over the setups EVERY family in the comparison could measure.
    #: `None` until `compare_families` has seen the whole set.
    comparable_metrics: VariantMetrics | None = None

    @property
    def expectancy(self) -> Decimal | None:
        return self.metrics.expectancy_r.value

    @property
    def comparable_expectancy(self) -> Decimal | None:
        if self.comparable_metrics is None:
            return None
        return self.comparable_metrics.expectancy_r.value

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "hypothesis_id": self.hypothesis_id,
            "geometry_policy_id": self.geometry_policy_id,
            "sample": self.sample,
            "cost_policy_id": self.cost_policy_id,
            "trades": self.metrics.trades,
            "measurable_trades": self.metrics.measurable_trades,
            "ambiguous_trades": self.ambiguous,
            "fired": self.fired,
            "expectancy_r": (
                None if self.expectancy is None else str(self.expectancy)
            ),
            "comparable_measurable_trades": (
                None if self.comparable_metrics is None
                else self.comparable_metrics.measurable_trades
            ),
            "comparable_expectancy_r": (
                None if self.comparable_expectancy is None
                else str(self.comparable_expectancy)
            ),
            "win_rate": (
                None if self.metrics.win_rate.value is None
                else str(self.metrics.win_rate.value)
            ),
            "profit_factor": (
                None if self.metrics.profit_factor.value is None
                else str(self.metrics.profit_factor.value)
            ),
            "average_win_r": (
                None if self.metrics.average_win_r.value is None
                else str(self.metrics.average_win_r.value)
            ),
            "average_loss_r": (
                None if self.metrics.average_loss_r.value is None
                else str(self.metrics.average_loss_r.value)
            ),
            "average_bars_held": (
                None if self.metrics.average_bars_held.value is None
                else str(self.metrics.average_bars_held.value)
            ),
            "max_drawdown_r": str(self.metrics.max_drawdown.max_drawdown_r),
            "total_r": str(self.metrics.total_r),
            "exit_reasons": [list(item) for item in self.exit_reasons],
        }


#: The exit reasons that mean a BZ mechanism actually acted, rather than the
#: position reaching its stop, its target or the window bound. Counted and
#: reported beside every expectancy: a mechanism that never fired did not
#: improve anything, and its expectancy would silently be the control's.
_MECHANISM_REASONS: Final[frozenset[LabExitReason]] = frozenset(
    {
        LabExitReason.THESIS_INVALIDATED,
        LabExitReason.STAGNATION,
        LabExitReason.GIVEBACK,
    }
)


def measure_family(
    capture: GeometryCapture,
    *,
    geometry: PlansGeometry,
    policy: ExitPolicy,
    hypothesis_id: str,
    timelines: Mapping[str, ThesisTimeline],
    ladders: Mapping[str, BarLadder] | None,
    sample_of,
    sample_name: str,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
) -> FamilyMeasurement:
    """Walk one exit family over one sample. **Pure with respect to history.**

    The geometry, the entry and the window are identical across every family, so
    a difference between two `FamilyMeasurement`s is management and nothing else.
    """
    trades: list[LabTrade] = []
    fired = ambiguous = 0
    for candidate in capture.candidates:
        outcome = geometry.plan(candidate)
        if isinstance(outcome, GeometrySkip):
            continue
        spec = sample_of(candidate.symbol, candidate.signal_at)
        if spec is None or spec.name != sample_name:
            continue
        bars = capture.bars_by_symbol[candidate.symbol]
        if len(bars) <= candidate.signal_index + 1:
            continue
        entry_bar = bars[candidate.signal_index + 1]
        managed = simulate_managed_trade(
            bars,
            variant_id=policy.policy_id,
            symbol=candidate.symbol,
            setup_id=candidate.setup_id,
            direction=candidate.direction,
            entry_index=candidate.signal_index + 1,
            entry_price=entry_bar.open,
            entry_at=entry_bar.open_time,
            signal_at=candidate.signal_at,
            reference_price=Decimal(str(outcome.entry)),
            stop_price=Decimal(str(outcome.stop.price)),
            target_price=Decimal(str(outcome.target.price)),
            planned_risk_reward=outcome.planned_rr,
            window_bars=evaluation_window_bars,
            costs=costs,
            policy=policy,
            ladder=None if ladders is None else ladders.get(candidate.symbol),
            timeline=(
                timelines.get(candidate.symbol) if policy.needs_timeline else None
            ),
            segment=candidate.segment,
            context_regime_structure=candidate.context_regime_structure,
            context_structural_trend=candidate.context_structural_trend,
            setup_structural_trend=candidate.setup_structural_trend,
        )
        trades.append(managed.trade)
        if managed.trade.exit_reason in _MECHANISM_REASONS:
            fired += 1
        if managed.trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR:
            ambiguous += 1

    frozen = tuple(trades)
    metrics = compute_lab_metrics(
        frozen, label=f"{policy.policy_id}:{geometry.policy_id}:{sample_name}"
    )
    return FamilyMeasurement(
        policy_id=policy.policy_id,
        hypothesis_id=hypothesis_id,
        geometry_policy_id=geometry.policy_id,
        sample=sample_name,
        cost_policy_id=costs.policy_id,
        trades=frozen,
        metrics=metrics,
        fired=fired,
        ambiguous=ambiguous,
        exit_reasons=metrics.exit_reasons,
    )


@dataclass(frozen=True, slots=True)
class FamilyComparison:
    """Every family on one geometry and one sample, made like-for-like."""

    geometry_policy_id: str
    sample: str
    cost_policy_id: str
    control_policy_id: str
    measurements: tuple[FamilyMeasurement, ...]
    shared_setups: int

    def by_policy(self, policy_id: str) -> FamilyMeasurement:
        for item in self.measurements:
            if item.policy_id == policy_id:
                return item
        raise SwingLabError(
            f"no measurement for {policy_id!r} on {self.geometry_policy_id}/"
            f"{self.sample}; this comparison holds "
            f"{', '.join(m.policy_id for m in self.measurements)}"
        )

    @property
    def control(self) -> FamilyMeasurement:
        return self.by_policy(self.control_policy_id)

    def improvement(self, policy_id: str) -> Decimal | None:
        """A family's like-for-like expectancy minus its control's.

        ``None`` when either side could not state an expectancy, which is a
        refusal rather than a zero: "no improvement" and "unmeasurable" are
        different findings and a zero would merge them.
        """
        mine = self.by_policy(policy_id).comparable_expectancy
        theirs = self.control.comparable_expectancy
        if mine is None or theirs is None:
            return None
        return mine - theirs

    def payload(self) -> dict[str, Any]:
        return {
            "geometry_policy_id": self.geometry_policy_id,
            "sample": self.sample,
            "cost_policy_id": self.cost_policy_id,
            "control_policy_id": self.control_policy_id,
            "shared_setups": self.shared_setups,
            "measurements": [item.payload() for item in self.measurements],
            "improvements": {
                item.policy_id: (
                    None if (value := self.improvement(item.policy_id)) is None
                    else str(value)
                )
                for item in self.measurements
            },
        }


def compare_families(
    measurements: Sequence[FamilyMeasurement], *, control_policy_id: str
) -> FamilyComparison:
    """Re-measure every family over the setups **all** of them could measure.

    This is BY defect BY-D9's `comparable` column, generalised. Without it a
    mechanism that makes a bar ambiguous drops exactly the trades that ran a
    full R and then stopped — losers that had been winners — and its expectancy
    is computed over a sample depleted of its worst cases while the control
    keeps them at −1R.
    """
    if not measurements:
        raise SwingLabError("a comparison needs at least one measurement")
    samples = {item.sample for item in measurements}
    geometries = {item.geometry_policy_id for item in measurements}
    scenarios = {item.cost_policy_id for item in measurements}
    if len(samples) != 1 or len(geometries) != 1 or len(scenarios) != 1:
        raise SwingLabError(
            "a comparison must hold one sample, one geometry and one cost "
            f"scenario; got samples={sorted(samples)}, "
            f"geometries={sorted(geometries)}, scenarios={sorted(scenarios)}"
        )

    common: set[str] | None = None
    for item in measurements:
        measurable = {t.setup_id for t in item.trades if t.is_measurable}
        common = measurable if common is None else (common & measurable)
    shared = common or set()

    compared = tuple(
        replace(
            item,
            comparable_metrics=compute_lab_metrics(
                tuple(t for t in item.trades if t.setup_id in shared),
                label=f"{item.policy_id}:{item.geometry_policy_id}:"
                      f"{item.sample}:comparable",
            ),
        )
        for item in measurements
    )
    return FamilyComparison(
        geometry_policy_id=next(iter(geometries)),
        sample=next(iter(samples)),
        cost_policy_id=next(iter(scenarios)),
        control_policy_id=control_policy_id,
        measurements=compared,
        shared_setups=len(shared),
    )


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------


class BzVerdict(str, Enum):
    """What BZ concluded about one exit family. **Derived, never asserted.**

    Five states, and the two that matter are kept apart on purpose:
    `MECHANISM_EVIDENCE` is a finding about information and approves nothing;
    `CANDIDATE` is the only verdict that earns shadow or paper testing, and it
    requires positive cost-inclusive expectancy on all three samples.
    """

    NOT_MEASURED = "not_measured"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    MECHANISM_EVIDENCE = "mechanism_evidence"
    CANDIDATE = "candidate"

    @property
    def is_approved_for_trading(self) -> bool:
        """Always ``False``. No verdict this repository produces approves trading."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        return self is BzVerdict.CANDIDATE


@dataclass(frozen=True, slots=True)
class Criterion:
    """One pre-registered requirement, and whether this family met it."""

    name: str
    requirement: str
    passed: bool | None
    detail: str

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requirement": self.requirement,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class BzAssessment:
    """One exit family judged against the sealed criteria. **Reconstructable.**"""

    policy_id: str
    hypothesis_id: str
    geometry_policy_id: str
    verdict: BzVerdict
    mechanism_criteria: tuple[Criterion, ...]
    candidate_criteria: tuple[Criterion, ...]
    preregistration_digest: str
    digest_matches: bool

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(
            item.name
            for item in self.mechanism_criteria + self.candidate_criteria
            if item.passed is False
        )

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "hypothesis_id": self.hypothesis_id,
            "geometry_policy_id": self.geometry_policy_id,
            "verdict": self.verdict.value,
            "failed_criteria": list(self.failed),
            "mechanism_criteria": [c.payload() for c in self.mechanism_criteria],
            "candidate_criteria": [c.payload() for c in self.candidate_criteria],
            "preregistration_digest": self.preregistration_digest,
            "preregistration_digest_matches": self.digest_matches,
        }


def _criterion(spec, passed: bool | None, detail: str) -> Criterion:
    return Criterion(
        name=spec.name, requirement=spec.requirement, passed=passed, detail=detail
    )


def assess_bz(
    policy_id: str,
    *,
    geometry_policy_id: str,
    comparisons: Mapping[str, FamilyComparison],
    causal_proven: bool,
    robust: bool | None,
    ambiguity_decisive: bool | None,
    component_expectancies: Mapping[str, Decimal | None] | None = None,
    preregistration: BzPreregistration = BZ_PRE_REGISTRATION,
) -> BzAssessment:
    """Judge one family against the sealed criteria. **Pure and reconstructable.**

    ``comparisons`` is keyed by sample name and each is already like-for-like.
    Nothing here holds a threshold: every number is read from the manifest, and
    the first criterion is pre-registration membership plus a digest match, so a
    policy invented after the results cannot be promoted whatever its numbers.
    """
    live = bz_preregistration_digest(preregistration)
    digest_matches = live == BZ_PREREGISTRATION_DIGEST
    sealed = policy_id in {item.policy_id for item in preregistration.hypotheses}
    hypothesis = (
        preregistration.hypothesis_for(policy_id) if sealed else None
    )

    def measurement(sample: str) -> FamilyMeasurement | None:
        comparison = comparisons.get(sample)
        if comparison is None:
            return None
        try:
            return comparison.by_policy(policy_id)
        except SwingLabError:
            return None

    names = [spec.name for spec in preregistration.samples]
    found = {name: measurement(name) for name in names}

    mechanism: list[Criterion] = []
    for spec in preregistration.mechanism_criteria:
        if spec.name == "pre_registered":
            mechanism.append(
                _criterion(
                    spec,
                    sealed and digest_matches,
                    f"sealed={sealed}, digest_matches={digest_matches}",
                )
            )
        elif spec.name == "causal":
            mechanism.append(
                _criterion(spec, causal_proven, f"proven={causal_proven}")
            )
        elif spec.name == "sample":
            counts = {
                name: (0 if item is None else item.metrics.measurable_trades)
                for name, item in found.items()
            }
            enough = all(value >= SAMPLE_FLOOR for value in counts.values())
            # **A thin sample is UNMEASURABLE, never a failure.** The sealed
            # classification rules say so in as many words: fewer than
            # SAMPLE_FLOOR measurable trades means "the test could not be run,
            # which is NOT a pass" — INCONCLUSIVE. Returning False here instead
            # would report a study that never opened its holdout as a REJECTED
            # hypothesis, which claims evidence against a rule that was never
            # measured. Defect BZ-D1, found by a regression written to close a
            # surviving mutant.
            mechanism.append(
                _criterion(
                    spec,
                    True if enough else None,
                    ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
                )
            )
        elif spec.name.startswith("improves_"):
            sample = spec.name.removeprefix("improves_")
            comparison = comparisons.get(sample)
            value = None if comparison is None else comparison.improvement(policy_id)
            bar = Decimal(str(spec.threshold or 0.0))
            mechanism.append(
                _criterion(
                    spec,
                    None if value is None else value >= bar,
                    "unmeasurable" if value is None else f"{value:+.4f}R vs {bar:+.2f}R",
                )
            )
        elif spec.name == "robust":
            mechanism.append(
                _criterion(spec, robust, "no threshold to sweep" if robust is None
                           else f"all neighbours improve={robust}")
            )
        elif spec.name == "ambiguity_not_decisive":
            mechanism.append(
                _criterion(
                    spec,
                    None if ambiguity_decisive is None else not ambiguity_decisive,
                    "unassessed" if ambiguity_decisive is None
                    else f"conclusion flips under a boundary assumption="
                         f"{ambiguity_decisive}",
                )
            )
        else:  # pragma: no cover - every sealed criterion is handled above
            mechanism.append(_criterion(spec, None, "unhandled"))

    mechanism_passed = all(item.passed is True for item in mechanism)

    candidate: list[Criterion] = []
    for spec in preregistration.candidate_criteria:
        if spec.name == "mechanism_evidence":
            candidate.append(
                _criterion(spec, mechanism_passed, f"passed={mechanism_passed}")
            )
        elif spec.name.endswith("_expectancy"):
            sample = spec.name.removesuffix("_expectancy")
            item = found.get(sample)
            value = None if item is None else item.expectancy
            if spec.name == "development_expectancy":
                ok = None if value is None else value > 0
            else:
                ok = None if value is None else value >= 0
            candidate.append(
                _criterion(
                    spec, ok,
                    "unmeasurable" if value is None else f"{value:+.4f}R",
                )
            )
        elif spec.name == "profit_factor":
            item = found.get("development")
            value = None if item is None else item.metrics.profit_factor.value
            candidate.append(
                _criterion(
                    spec,
                    None if value is None else float(value) > (spec.threshold or 1.0),
                    "unmeasurable" if value is None else f"{value}",
                )
            )
        elif spec.name == "drawdown_recovered":
            item = found.get("development")
            if item is None:
                candidate.append(_criterion(spec, None, "unmeasurable"))
            else:
                worst = item.metrics.max_drawdown.max_drawdown_r
                total = item.metrics.total_r
                candidate.append(
                    _criterion(
                        spec, worst < total, f"drawdown {worst} vs total {total}"
                    )
                )
        elif spec.name == "symbol_concentration":
            item = found.get("development")
            share = (
                None if item is None
                else concentration_of(
                    [t for t in item.trades if t.net_r is not None], lambda t: t.symbol
                )
            )
            candidate.append(
                _criterion(
                    spec,
                    None if share is None else float(share) <= (spec.threshold or 0.4),
                    "unmeasurable" if share is None else f"{share:.1%}",
                )
            )
        elif spec.name == "both_directions_understood":
            item = found.get("development")
            if item is None:
                candidate.append(_criterion(spec, None, "unmeasurable"))
            else:
                cohorts = lab_breakdown_by(
                    item.trades, lambda t: t.direction.value
                )
                candidate.append(
                    _criterion(
                        spec, len(cohorts) >= 1,
                        ", ".join(
                            f"{c.label}={c.measurable_trades}" for c in cohorts
                        ),
                    )
                )
        elif spec.name == "no_single_period":
            candidate.append(
                _criterion(
                    spec, None,
                    "assessed from the walk-forward table by the milestone, not "
                    "from a single run",
                )
            )
        elif spec.name == "components_earned_it":
            if hypothesis is None or not hypothesis.is_combination:
                candidate.append(_criterion(spec, True, "not a combination"))
            elif component_expectancies is None:
                candidate.append(_criterion(spec, None, "components not supplied"))
            else:
                ok = all(
                    value is not None and value > 0
                    for value in component_expectancies.values()
                )
                candidate.append(
                    _criterion(
                        spec, ok,
                        ", ".join(
                            f"{k}={'n/a' if v is None else f'{v:+.4f}'}"
                            for k, v in sorted(component_expectancies.items())
                        ),
                    )
                )
        else:  # pragma: no cover - every sealed criterion is handled above
            candidate.append(_criterion(spec, None, "unhandled"))

    verdict = _verdict(found, mechanism, candidate)
    return BzAssessment(
        policy_id=policy_id,
        hypothesis_id="" if hypothesis is None else hypothesis.hypothesis_id,
        geometry_policy_id=geometry_policy_id,
        verdict=verdict,
        mechanism_criteria=tuple(mechanism),
        candidate_criteria=tuple(candidate),
        preregistration_digest=live,
        digest_matches=digest_matches,
    )


def _verdict(
    found: Mapping[str, FamilyMeasurement | None],
    mechanism: Sequence[Criterion],
    candidate: Sequence[Criterion],
) -> BzVerdict:
    """The classification, applied in the sealed order. **Pure and total.**"""
    measured = [item for item in found.values() if item is not None]
    if not measured or all(item.metrics.measurable_trades == 0 for item in measured):
        return BzVerdict.NOT_MEASURED
    if any(item.passed is False for item in mechanism):
        # A failed criterion is a rejection. An UNMEASURABLE one is not a
        # rejection and not a pass — it is the state the sealed rules call
        # INCONCLUSIVE, and it is checked after, so a genuine failure is never
        # reported as merely inconclusive.
        return BzVerdict.REJECTED
    if any(item.passed is None for item in mechanism):
        return BzVerdict.INCONCLUSIVE
    if any(item.passed is False for item in candidate):
        return BzVerdict.MECHANISM_EVIDENCE
    if any(item.passed is None for item in candidate):
        return BzVerdict.MECHANISM_EVIDENCE
    return BzVerdict.CANDIDATE


# ---------------------------------------------------------------------------
# The experiment. **The only place this package reaches the network.**
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersistenceStudy:
    """One complete BZ run: the observational half, then the sealed families."""

    preregistration_id: str
    preregistration_digest: str
    digest_matches: bool
    evaluation_window_bars: int
    deciding_cost_policy_id: str
    #: (geometry_policy_id, sample) → the like-for-like family comparison
    comparisons: Mapping[tuple[str, str], FamilyComparison]
    #: (geometry_policy_id, sample) → what the paths looked like
    paths: Mapping[tuple[str, str], PathSummary]
    #: (geometry_policy_id, sample) → BX's give-back finding, decomposed
    giveback: Mapping[tuple[str, str], GivebackDecomposition]
    assessments: tuple[BzAssessment, ...]
    #: (geometry, universe, policy_id) → the chronological walk-forward.
    #: **One curve per UNIVERSE, never pooled.** Milestone BY defect BY-D6: the
    #: traded universe doubles when the holdout enters, so a pooled curve
    #: describes a different market after that boundary than before it.
    walk_forward: Mapping[tuple[str, str, str], tuple[Any, ...]]
    #: (geometry, universe, policy_id) → every required decomposition.
    decompositions: Mapping[tuple[str, str, str], tuple[Any, ...]]
    capture_metadata: Mapping[str, Any]
    holdout_capture_metadata: Mapping[str, Any] | None
    timeline_instants: int
    limitations: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": BZ_SCHEMA_VERSION,
            "preregistration_id": self.preregistration_id,
            "preregistration_digest": self.preregistration_digest,
            "preregistration_digest_matches": self.digest_matches,
            "evaluation_window_bars": self.evaluation_window_bars,
            "deciding_cost_policy_id": self.deciding_cost_policy_id,
            "comparisons": [
                {"key": [geometry, sample], **comparison.payload()}
                for (geometry, sample), comparison in sorted(self.comparisons.items())
            ],
            "paths": [
                {"key": [geometry, sample], **summary.payload()}
                for (geometry, sample), summary in sorted(self.paths.items())
            ],
            "giveback": [
                {"key": [geometry, sample], **item.payload()}
                for (geometry, sample), item in sorted(self.giveback.items())
            ],
            "assessments": [item.payload() for item in self.assessments],
            "walk_forward": [
                {
                    "key": [geometry, universe, policy_id],
                    "windows": [item.payload() for item in windows],
                }
                for (geometry, universe, policy_id), windows in sorted(
                    self.walk_forward.items()
                )
            ],
            "decompositions": [
                {
                    "key": [geometry, universe, policy_id],
                    "cuts": [
                        {
                            "name": cut.name,
                            "question": cut.question,
                            "agrees_on_sign": cut.agrees_on_sign,
                            "cohorts": [
                                {
                                    "label": cohort.label,
                                    "measurable_trades": cohort.measurable_trades,
                                    "expectancy_r": (
                                        None
                                        if cohort.expectancy_r.value is None
                                        else str(cohort.expectancy_r.value)
                                    ),
                                    "reason": cohort.expectancy_r.reason,
                                }
                                for cohort in cut.cohorts
                            ],
                        }
                        for cut in cuts
                    ],
                }
                for (geometry, universe, policy_id), cuts in sorted(
                    self.decompositions.items()
                )
            ],
            "capture_metadata": dict(self.capture_metadata),
            "holdout_capture_metadata": (
                None if self.holdout_capture_metadata is None
                else dict(self.holdout_capture_metadata)
            ),
            "timeline_instants": self.timeline_instants,
            "limitations": list(self.limitations),
        }


def run_persistence_experiment(
    *,
    run_at: datetime,
    open_holdout: bool,
    causal_proven: bool,
    preregistration: BzPreregistration = BZ_PRE_REGISTRATION,
    evaluation_window_bars: int | None = None,
    limit: int | None = None,
    transport: Any = None,
    base_url: str | None = None,
) -> PersistenceStudy:
    """Fetch, capture and judge — with **every input read from the sealed manifest**.

    There is deliberately no symbol argument, no window argument and no threshold
    argument, for Milestone BY's reason: a study whose universe could be renamed
    at a shell prompt is not a pre-registered study. The only two things a caller
    decides are *when* it ran and *whether the holdout is opened*.

    ``open_holdout=False`` runs the development pass: the holdout replay is not
    even fetched, so it cannot be inspected by accident, and every holdout
    criterion reports as unevaluable so no family can reach CANDIDATE.

    The capture is taken **once per universe** with a `TimelineCollector`
    attached, so the geometry candidates and the structural timeline come from
    one walk over one dataset rather than from two that could disagree.
    """
    from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
    from fmis.swing_lab.persistence_preregistration import BZ_GEOMETRIES
    from fmis.swing_lab.persistence_replay import TimelineCollector
    from fmis.swing_lab.preregistration import sample_of
    from fmis.swing_lab.validation_study import capture_for_window
    from fmis.swing_setup.backtest_harness import (
        DEFAULT_BACKTEST_LIMIT,
        DEFAULT_EVALUATION_WINDOW_BARS,
    )

    window_bars = (
        DEFAULT_EVALUATION_WINDOW_BARS
        if evaluation_window_bars is None
        else evaluation_window_bars
    )
    candle_limit = DEFAULT_BACKTEST_LIMIT if limit is None else limit

    development = preregistration.sample("development")
    validation = preregistration.sample("validation")
    holdout_spec = preregistration.sample("holdout")

    primary_collector = TimelineCollector()
    primary = capture_for_window(
        development.symbols,
        measurement_start=min(development.signal_start, validation.signal_start),
        measurement_end=max(development.signal_end, validation.signal_end),
        run_at=run_at, evaluation_window_bars=window_bars, limit=candle_limit,
        transport=transport, base_url=base_url, observer=primary_collector,
    )
    holdout_collector = TimelineCollector()
    holdout = (
        capture_for_window(
            holdout_spec.symbols,
            measurement_start=holdout_spec.signal_start,
            measurement_end=holdout_spec.signal_end,
            run_at=run_at, evaluation_window_bars=window_bars, limit=candle_limit,
            transport=transport, base_url=base_url, observer=holdout_collector,
        )
        if open_holdout
        else None
    )

    return study_from_captures(
        primary=primary,
        primary_timelines=primary_collector.timelines(),
        holdout=holdout,
        holdout_timelines=holdout_collector.timelines() if holdout is not None else {},
        causal_proven=causal_proven,
        preregistration=preregistration,
        evaluation_window_bars=window_bars,
    )


def study_from_captures(
    *,
    primary: GeometryCapture,
    primary_timelines: Mapping[str, ThesisTimeline],
    holdout: GeometryCapture | None,
    holdout_timelines: Mapping[str, ThesisTimeline],
    causal_proven: bool,
    preregistration: BzPreregistration = BZ_PRE_REGISTRATION,
    evaluation_window_bars: int | None = None,
) -> "PersistenceStudy":
    """Measure a BZ study from captures that are **already in hand**.

    Everything after the fetch, extracted so the identical code path serves both
    a live replay and a **persisted capture** read back from disk. That sharing
    is the whole point of the extraction: an offline reproduction that ran
    through a second, parallel measurement path would prove only that the second
    path agrees with itself.

    Deterministic and pure: no clock, no randomness, **no network**. Given equal
    captures it returns an equal study, which is what
    `test_swing_lab_persistence_artifact` asserts by measuring the same inputs
    twice — once from memory and once from a decoded file.
    """
    from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
    from fmis.swing_lab.persistence_preregistration import BZ_GEOMETRIES
    from fmis.swing_lab.preregistration import sample_of
    from fmis.swing_setup.backtest_harness import DEFAULT_EVALUATION_WINDOW_BARS

    window_bars = (
        DEFAULT_EVALUATION_WINDOW_BARS
        if evaluation_window_bars is None
        else evaluation_window_bars
    )
    development = preregistration.sample("development")
    validation = preregistration.sample("validation")
    holdout_spec = preregistration.sample("holdout")
    primary_collector_timelines = primary_timelines
    holdout_collector_timelines = holdout_timelines

    deciding = next(
        item for item in preregistration.cost_scenarios
        if item.policy_id == preregistration.deciding_cost_policy_id
    )
    geometries = {policy.policy_id: policy for policy in BZ_GEOMETRIES}
    control_id = preregistration.control.policy_id

    comparisons: dict[tuple[str, str], FamilyComparison] = {}
    paths: dict[tuple[str, str], PathSummary] = {}
    giveback: dict[tuple[str, str], GivebackDecomposition] = {}

    sources = [
        (primary, primary_collector_timelines, (development.name, validation.name)),
    ]
    if holdout is not None:
        sources.append(
            (holdout, holdout_collector_timelines, (holdout_spec.name,))
        )

    for capture, timelines, sample_names in sources:
        for geometry_id, geometry in geometries.items():
            tracks = observe_all_paths(
                capture, geometry=geometry, timelines=timelines,
                sample_of=sample_of, evaluation_window_bars=window_bars,
            )
            for sample_name in sample_names:
                measurements = [
                    measure_family(
                        capture, geometry=geometry, policy=item.policy,
                        hypothesis_id=item.hypothesis_id, timelines=timelines,
                        ladders=None, sample_of=sample_of, sample_name=sample_name,
                        costs=deciding, evaluation_window_bars=window_bars,
                    )
                    for item in preregistration.hypotheses
                ]
                comparison = compare_families(
                    measurements, control_policy_id=control_id
                )
                comparisons[(geometry_id, sample_name)] = comparison
                cohort = tuple(t for t in tracks if t.sample == sample_name)
                paths[(geometry_id, sample_name)] = summarise_paths(
                    cohort, label=f"{geometry_id}:{sample_name}"
                )
                giveback[(geometry_id, sample_name)] = decompose_giveback(
                    cohort, comparison.control.trades,
                    label=f"{geometry_id}:{sample_name}",
                )

    # ---- walk-forward and decompositions, PER UNIVERSE ----
    # The primary universe is development + validation: the SAME fifteen symbols
    # over one continuous span, so a window boundary there is a date and nothing
    # else. The holdout is twenty-one different symbols and gets its own curve.
    from fmis.swing_lab.validation_study import decompose, walk_forward

    universes = [
        (
            "primary",
            (development.name, validation.name),
            development.signal_start,
            validation.signal_end,
        )
    ]
    if holdout is not None:
        universes.append(
            (
                "holdout",
                (holdout_spec.name,),
                holdout_spec.signal_start,
                holdout_spec.signal_end,
            )
        )

    curves: dict[tuple[str, str, str], tuple[Any, ...]] = {}
    cuts: dict[tuple[str, str, str], tuple[Any, ...]] = {}
    for geometry_id in geometries:
        for universe, members, start, end in universes:
            for item in preregistration.hypotheses:
                pooled = tuple(
                    trade
                    for name in members
                    if (found := comparisons.get((geometry_id, name))) is not None
                    for trade in found.by_policy(item.policy_id).trades
                )
                if not pooled:
                    continue
                key = (geometry_id, universe, item.policy_id)
                curves[key] = walk_forward(
                    pooled, start=start, end=end,
                    label=f"{geometry_id}:{universe}:{item.policy_id}",
                )
                cuts[key] = decompose(pooled)

    assessments: list[BzAssessment] = []
    for geometry_id in geometries:
        by_sample = {
            sample: comparison
            for (geo, sample), comparison in comparisons.items()
            if geo == geometry_id
        }
        for item in preregistration.hypotheses:
            if item.role == "control":
                continue
            components = None
            if item.is_combination:
                development_comparison = by_sample.get(development.name)
                components = {}
                for mechanic in item.components:
                    match = next(
                        (
                            h.policy_id for h in preregistration.hypotheses
                            if h.policy.mechanic is mechanic
                        ),
                        None,
                    )
                    if match is None or development_comparison is None:
                        components[mechanic.value] = None
                        continue
                    try:
                        components[mechanic.value] = (
                            development_comparison.by_policy(match).expectancy
                        )
                    except SwingLabError:  # pragma: no cover - measured above
                        components[mechanic.value] = None
            assessments.append(
                assess_bz(
                    item.policy_id,
                    geometry_policy_id=geometry_id,
                    comparisons=by_sample,
                    causal_proven=causal_proven,
                    robust=None,
                    ambiguity_decisive=None,
                    component_expectancies=components,
                    preregistration=preregistration,
                )
            )

    live = bz_preregistration_digest(preregistration)
    return PersistenceStudy(
        preregistration_id=preregistration.preregistration_id,
        preregistration_digest=live,
        digest_matches=live == BZ_PREREGISTRATION_DIGEST,
        evaluation_window_bars=window_bars,
        deciding_cost_policy_id=deciding.policy_id,
        comparisons=comparisons,
        paths=paths,
        giveback=giveback,
        assessments=tuple(assessments),
        walk_forward=curves,
        decompositions=cuts,
        capture_metadata=dict(primary.metadata),
        holdout_capture_metadata=(
            None if holdout is None else dict(holdout.metadata)
        ),
        timeline_instants=(
            sum(len(t.observations) for t in primary_collector_timelines.values())
            + sum(len(t.observations) for t in holdout_collector_timelines.values())
        ),
        limitations=preregistration.limitations,
    )
