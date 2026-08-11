"""Deterministic aggregates over one `ResearchBacktestRun`, and its concentration.

Every number here is a count, a share or a nearest-rank percentile over
observations the harness already recorded. **No probability, no expected value,
no win rate.** ``target_first_rate`` names exactly what it measures, following
`fmis.swing_setup.backtest_metrics`'s own discipline, and small cohorts report
``None`` rather than a rate computed from a handful of outcomes.

**Two things this module does that AV's metrics do not.**

*Every denominator starts at ``run.measured``.* Warm-up and identity-priming
observations exist in the record so a reader can see them and are excluded from
every count. That is the whole of BB finding #1, expressed as arithmetic.

*Concentration is measured, not assumed away.* BB's most damaging observation
was not that AV's window was short — it was that 66 of 133 resolved outcomes
fell inside five calendar days, so a sample described as 133 independent
observations was closer to a handful of market episodes. `ConcentrationReport`
computes that same statistic on every run, so the question is answered on the
face of the report rather than by a reader who thinks to ask.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from fmis.swing_setup.backtest_metrics import (
    MIN_SAMPLE_FOR_RATE,
    CohortCount,
    Percentiles,
    outcome_cohort,
    percentiles_of,
)
from fmis.swing_setup.backtest_models import OutcomeStatus, SetupOutcome
from fmis.swing_setup.models import Direction, SetupState
from fmis.swing_setup.research_models import (
    ConfirmationRecord,
    ResearchBacktestRun,
    ResearchObservation,
)

__all__ = [
    "CONCENTRATION_WINDOW_DAYS",
    "ConcentrationReport",
    "ResearchMetrics",
    "compute_research_metrics",
    "confirmation_records",
    "first_confirmations",
]

#: The window BB measured AV's concentration over, kept identical so the two
#: numbers are directly comparable. Five calendar days, not five bars: the
#: question is "how much of this sample is one stretch of market?", and market
#: episodes are measured in days.
CONCENTRATION_WINDOW_DAYS: int = 5


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator < MIN_SAMPLE_FOR_RATE:
        return None
    return numerator / denominator


def first_confirmations(run: ResearchBacktestRun) -> tuple[ResearchObservation, ...]:
    """The first measured `CONFIRMED` observation of each opportunity, chronologically.

    One row per opportunity, never one per confirmed bar — the distinction AV's
    window-relative identity could not draw, and the reason its outcome count
    over-states how many distinct decisions were measured.

    An opportunity that first confirmed during the priming window is absent:
    the decision was not made inside the measured window, so measuring its
    outcome would readmit through the back door exactly what the measurement
    boundary excludes at the front.
    """
    return tuple(
        item
        for item in run.observations
        if item.in_measurement and item.is_first_confirmation
    )


def confirmation_records(run: ResearchBacktestRun) -> tuple[ConfirmationRecord, ...]:
    """Every opportunity's first confirmation, reduced to what a comparison joins on."""
    return tuple(
        ConfirmationRecord(
            symbol=item.symbol,
            opportunity_key=item.opportunity_key,
            confirmed_at=item.observation.execution_last_timestamp or item.as_of,
            direction=item.direction.value,
            confirmation_break_age_bars=item.confirmation_break_age_bars,
            reference_price=item.observation.reference_price,
            risk_reward_ratio=item.observation.risk_reward_ratio,
            segment=item.segment,
        )
        for item in first_confirmations(run)
    )


@dataclass(frozen=True, slots=True)
class ConcentrationReport:
    """How much of a sample is one stretch of market, and one symbol.

    ``largest_window_share`` is the largest fraction of all evaluated outcomes
    whose confirmations fall inside any `CONCENTRATION_WINDOW_DAYS` span. A
    sample where that number is near 1 is one market episode wearing the
    clothes of many observations, whatever its headline count says.
    """

    total_outcomes: int
    distinct_days: int
    largest_window_outcomes: int
    largest_window_share: float | None
    largest_window_start: datetime | None
    largest_symbol: str | None
    largest_symbol_outcomes: int
    largest_symbol_share: float | None
    by_week: tuple[CohortCount, ...]
    by_month: tuple[CohortCount, ...]
    by_year: tuple[CohortCount, ...]


def _concentration(outcomes: Sequence[SetupOutcome]) -> ConcentrationReport:
    total = len(outcomes)
    if total == 0:
        return ConcentrationReport(
            total_outcomes=0,
            distinct_days=0,
            largest_window_outcomes=0,
            largest_window_share=None,
            largest_window_start=None,
            largest_symbol=None,
            largest_symbol_outcomes=0,
            largest_symbol_share=None,
            by_week=(),
            by_month=(),
            by_year=(),
        )

    stamps = sorted(outcome.confirmed_at for outcome in outcomes)
    span = timedelta(days=CONCENTRATION_WINDOW_DAYS)
    best_count = 0
    best_start: datetime | None = None
    right = 0
    for left, start in enumerate(stamps):
        # Every window is anchored on a real confirmation: a window containing
        # the most outcomes can always be slid until its left edge sits on one,
        # so anchoring loses nothing and keeps the scan exact rather than
        # dependent on an arbitrary calendar grid.
        right = max(right, left)
        while right < len(stamps) and stamps[right] - start < span:
            right += 1
        if right - left > best_count:
            best_count = right - left
            best_start = start

    per_symbol: dict[str, int] = defaultdict(int)
    for outcome in outcomes:
        per_symbol[outcome.symbol] += 1
    top_symbol = min(per_symbol.items(), key=lambda pair: (-pair[1], pair[0]))

    def _grouped(key) -> tuple[CohortCount, ...]:
        buckets: dict[str, list[SetupOutcome]] = defaultdict(list)
        for outcome in outcomes:
            buckets[key(outcome.confirmed_at)].append(outcome)
        return tuple(
            outcome_cohort(label, buckets[label]) for label in sorted(buckets)
        )

    return ConcentrationReport(
        total_outcomes=total,
        distinct_days=len({stamp.date() for stamp in stamps}),
        largest_window_outcomes=best_count,
        largest_window_share=best_count / total,
        largest_window_start=best_start,
        largest_symbol=top_symbol[0],
        largest_symbol_outcomes=top_symbol[1],
        largest_symbol_share=top_symbol[1] / total,
        by_week=_grouped(lambda stamp: f"{stamp.isocalendar().year}-W{stamp.isocalendar().week:02d}"),
        by_month=_grouped(lambda stamp: stamp.strftime("%Y-%m")),
        by_year=_grouped(lambda stamp: stamp.strftime("%Y")),
    )


@dataclass(frozen=True, slots=True)
class ResearchMetrics:
    """Every aggregate the milestone brief asks for, over one variant's measured window.

    Two definitions worth stating rather than leaving to inference:

    * ``unique_opportunities`` counts the distinct opportunities **present in**
      the measured window, not the ones that began inside it. An opportunity
      already running when the window opened is one of them; its first
      confirmation, if it happened before the window, is not counted anywhere
      (see `first_confirmations`), so this number can legitimately exceed
      ``confirmed_opportunities`` by more than the geometry gap alone.
    * ``confirmed_without_geometry`` is the residue of confirmed opportunities
      that produced no outcome because a stop, target or reference price was
      unavailable — never a rounding of two independently computed totals.
    """

    variant_id: str
    policy_id: str
    effective_max_age: int
    measured_observations: int
    warmup_observations: int
    wait_count: int
    candidate_count: int
    confirmed_count: int
    unique_opportunities: int
    confirmed_opportunities: int
    evaluated_outcomes: int
    confirmed_without_geometry: int
    target_first: int
    stop_first: int
    ambiguous_same_bar: int
    unresolved: int
    target_first_rate: float | None
    risk_reward_percentiles: Percentiles
    confirmation_age_percentiles: Percentiles
    confirmation_age_distribution: Mapping[int, int]
    by_symbol: tuple[CohortCount, ...]
    by_side: tuple[CohortCount, ...]
    by_segment: tuple[CohortCount, ...]
    observations_by_segment: Mapping[str, int]
    concentration: ConcentrationReport
    measured_days: int
    insufficient_data_measured_instants: int


def compute_research_metrics(run: ResearchBacktestRun) -> ResearchMetrics:
    """Compute every reported aggregate for one run. Pure — equal runs, equal metrics."""
    if not isinstance(run, ResearchBacktestRun):
        raise TypeError(f"run must be a ResearchBacktestRun, got {type(run).__name__}")

    measured = run.measured
    outcomes = run.outcomes

    wait_count = sum(1 for item in measured if item.status is SetupState.WAIT)
    candidate_count = sum(1 for item in measured if item.status is SetupState.CANDIDATE)
    confirmed_count = sum(1 for item in measured if item.status is SetupState.CONFIRMED)

    opportunities = {
        item.opportunity_key for item in measured if item.opportunity_key is not None
    }
    confirmations = first_confirmations(run)
    confirmed_opportunities = len(confirmations)

    target_first = sum(1 for o in outcomes if o.status is OutcomeStatus.TARGET_FIRST)
    stop_first = sum(1 for o in outcomes if o.status is OutcomeStatus.STOP_FIRST)
    ambiguous = sum(1 for o in outcomes if o.status is OutcomeStatus.AMBIGUOUS_SAME_BAR)
    unresolved = sum(
        1 for o in outcomes if o.status is OutcomeStatus.NEITHER_WITHIN_WINDOW
    )

    ages = [
        item.confirmation_break_age_bars
        for item in confirmations
        if item.confirmation_break_age_bars is not None
    ]
    age_distribution: dict[int, int] = defaultdict(int)
    for age in ages:
        age_distribution[age] += 1

    by_segment = tuple(
        outcome_cohort(
            segment.label,
            [o for o in outcomes if segment.contains(o.confirmed_at)],
        )
        for segment in run.segments
    )
    observations_by_segment: dict[str, int] = {segment.label: 0 for segment in run.segments}
    for item in measured:
        if item.segment is not None:
            observations_by_segment[item.segment] += 1

    return ResearchMetrics(
        variant_id=run.variant.variant_id,
        policy_id=run.policy_id,
        effective_max_age=run.variant.effective_max_age,
        measured_observations=len(measured),
        warmup_observations=len(run.observations) - len(measured),
        wait_count=wait_count,
        candidate_count=candidate_count,
        confirmed_count=confirmed_count,
        unique_opportunities=len(opportunities),
        confirmed_opportunities=confirmed_opportunities,
        evaluated_outcomes=len(outcomes),
        confirmed_without_geometry=max(0, confirmed_opportunities - len(outcomes)),
        target_first=target_first,
        stop_first=stop_first,
        ambiguous_same_bar=ambiguous,
        unresolved=unresolved,
        target_first_rate=_rate(target_first, target_first + stop_first),
        risk_reward_percentiles=percentiles_of([o.risk_reward_ratio for o in outcomes]),
        confirmation_age_percentiles=percentiles_of([float(age) for age in ages]),
        confirmation_age_distribution=dict(sorted(age_distribution.items())),
        by_symbol=tuple(
            outcome_cohort(symbol, [o for o in outcomes if o.symbol == symbol])
            for symbol in run.symbols
        ),
        by_side=tuple(
            outcome_cohort(
                direction.value, [o for o in outcomes if o.direction is direction]
            )
            for direction in (Direction.LONG, Direction.SHORT)
        ),
        by_segment=by_segment,
        observations_by_segment=observations_by_segment,
        concentration=_concentration(outcomes),
        measured_days=run.window.measurement_duration.days,
        insufficient_data_measured_instants=int(
            run.metadata.get("insufficient_data_measured_instants", 0)
        ),
    )
