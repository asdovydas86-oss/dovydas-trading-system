"""Deterministic aggregate metrics over one `BacktestRun`.

Every number here is a count, a rate, or a percentile computed directly from
`BacktestRun.observations`/`.outcomes` — copied facts, arithmetic over them,
and nothing else. **No probability, no expected value, no confidence and no
win rate is computed anywhere in this module.** ``target_first_rate`` is
named for exactly what it measures — the fraction of resolved, unambiguous
outcomes where the target was touched first — never "win rate", which would
claim an entry/exit model this repository does not have.

Cohorts too small to mean anything report ``None`` (rendered as
``INSUFFICIENT SAMPLE``) rather than a rate computed from a handful of
observations and presented with the same confidence as one computed from
thousands.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Final

from fmis.swing_setup.backtest_models import (
    BacktestRun,
    HistoricalObservation,
    OutcomeStatus,
    SetupOutcome,
)
from fmis.swing_setup.models import Direction, SetupState

__all__ = [
    "MIN_SAMPLE_FOR_RATE",
    "Percentiles",
    "CohortCount",
    "PairAgreement",
    "TripleAgreement",
    "AgreementCohortOutcomes",
    "BacktestMetrics",
    "compute_metrics",
]

#: A rate computed from fewer resolved outcomes than this is reported as
#: `None` (rendered "INSUFFICIENT SAMPLE") rather than a number that reads as
#: precise. Chosen before any result was seen, and never adjusted afterward.
MIN_SAMPLE_FOR_RATE: Final[int] = 5

#: The exact substring `fmis.swing_setup.policy.evaluate_setup` emits when —
#: and only when — a candidate is blocked purely because the context-role
#: regime is not TRENDING (decision context already SUFFICIENT/LIMITED at
#: that point). Reading this already-produced, deterministic reason string is
#: the documented "deterministic reasons" this harness records, not a
#: recomputation of the regime gate.
_REGIME_ONLY_BLOCK_MARKER: Final[str] = (
    "not trending. A directional swing thesis requires a trending "
    "higher-timeframe environment"
)


@dataclass(frozen=True, slots=True)
class Percentiles:
    """Nearest-rank percentiles over a set of values. No interpolation, no guess."""

    count: int
    p10: float | None
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    maximum: float | None


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    index = min(len(sorted_values) - 1, int(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def _percentiles(values: Sequence[float]) -> Percentiles:
    if not values:
        return Percentiles(count=0, p10=None, p25=None, p50=None, p75=None, p90=None, maximum=None)
    ordered = sorted(values)
    return Percentiles(
        count=len(ordered),
        p10=_percentile(ordered, 0.10),
        p25=_percentile(ordered, 0.25),
        p50=_percentile(ordered, 0.50),
        p75=_percentile(ordered, 0.75),
        p90=_percentile(ordered, 0.90),
        maximum=ordered[-1],
    )


@dataclass(frozen=True, slots=True)
class CohortCount:
    """Outcome counts for one named slice (a symbol, a side, a month)."""

    label: str
    total: int
    target_first: int
    stop_first: int
    ambiguous_same_bar: int
    neither_within_window: int


def _cohort(label: str, outcomes: Sequence[SetupOutcome]) -> CohortCount:
    return CohortCount(
        label=label,
        total=len(outcomes),
        target_first=sum(1 for o in outcomes if o.status is OutcomeStatus.TARGET_FIRST),
        stop_first=sum(1 for o in outcomes if o.status is OutcomeStatus.STOP_FIRST),
        ambiguous_same_bar=sum(1 for o in outcomes if o.status is OutcomeStatus.AMBIGUOUS_SAME_BAR),
        neither_within_window=sum(
            1 for o in outcomes if o.status is OutcomeStatus.NEITHER_WITHIN_WINDOW
        ),
    )


@dataclass(frozen=True, slots=True)
class PairAgreement:
    """How often two independent evidence families agree, across all observations."""

    family_a: str
    family_b: str
    both_directional: int
    agree: int
    agreement_rate: float | None


@dataclass(frozen=True, slots=True)
class TripleAgreement:
    """How often all three independent evidence families agree at once."""

    all_directional: int
    all_agree: int
    agreement_rate: float | None


@dataclass(frozen=True, slots=True)
class AgreementCohortOutcomes:
    """Outcome counts split by how many of the three families agreed at confirmation."""

    label: str
    total: int
    target_first: int
    stop_first: int
    ambiguous_same_bar: int
    neither_within_window: int


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    """Every aggregate number this milestone requires, computed once."""

    total_observations: int
    wait_count: int
    candidate_count: int
    confirmed_count: int
    unique_setups: int
    unique_confirmed_setups: int
    evaluated_outcomes: int
    confirmed_without_geometry: int
    target_first: int
    stop_first: int
    ambiguous_same_bar: int
    neither_within_window: int
    target_first_rate: float | None
    stop_first_rate: float | None
    risk_reward_mean: float | None
    risk_reward_median: float | None
    risk_reward_percentiles: Percentiles
    risk_fraction_percentiles: Percentiles
    reward_fraction_percentiles: Percentiles
    by_symbol: tuple[CohortCount, ...]
    by_side: tuple[CohortCount, ...]
    by_month: tuple[CohortCount, ...]
    pair_agreement: tuple[PairAgreement, ...]
    triple_agreement: TripleAgreement
    agreement_cohort_outcomes: tuple[AgreementCohortOutcomes, ...]
    structure_state_distribution: Mapping[str, int]
    regime_change_rate: float | None
    blocked_only_by_regime: int


def _iter_occurrences(
    observations: Sequence[HistoricalObservation],
) -> list[list[HistoricalObservation]]:
    """Group observations into setup occurrences: one group per is_new_setup event.

    An occurrence is a maximal run of consecutive same-symbol, directional
    (`direction is not None`) observations starting at the one flagged
    ``is_new_setup``. `WAIT` observations belong to no occurrence and end
    whichever one preceded them. Reasoned independently from
    `fmis.swing_setup.backtest_identity.IdentityTracker`'s own logic — this
    reads only `is_new_setup`/`direction`/`status`, already recorded.
    """
    occurrences: list[list[HistoricalObservation]] = []
    current: list[HistoricalObservation] | None = None
    for observation in observations:
        if observation.direction is None:
            current = None
            continue
        if observation.is_new_setup or current is None:
            current = []
            occurrences.append(current)
        current.append(observation)
    return occurrences


def _outcome_rate(numerator: int, denominator: int) -> float | None:
    if denominator < MIN_SAMPLE_FOR_RATE:
        return None
    return numerator / denominator


def _observation_by_confirmation(
    observations: Sequence[HistoricalObservation],
) -> Mapping[tuple[str, object], HistoricalObservation]:
    """Index `CONFIRMED` observations by ``(symbol, execution_last_timestamp)``.

    That pair is the exact join key `SetupOutcome.confirmed_at` was stamped
    from in the harness — the same instant, the same symbol — so the lookup
    is exact rather than a heuristic match on `setup_id`, which is not
    guaranteed unique across two separated occurrences that happen to
    reference the same structural level.
    """
    index: dict[tuple[str, object], HistoricalObservation] = {}
    for observation in observations:
        if observation.status is SetupState.CONFIRMED and observation.execution_last_timestamp:
            index[(observation.symbol, observation.execution_last_timestamp)] = observation
    return index


def compute_metrics(run: BacktestRun) -> BacktestMetrics:
    """Compute every aggregate metric this milestone requires from one `BacktestRun`.

    Pure: no network, no clock, no randomness. Equal runs give equal metrics.
    """
    observations = run.observations
    outcomes = run.outcomes

    wait_count = sum(1 for o in observations if o.status is SetupState.WAIT)
    candidate_count = sum(1 for o in observations if o.status is SetupState.CANDIDATE)
    confirmed_count = sum(1 for o in observations if o.status is SetupState.CONFIRMED)

    occurrences = _iter_occurrences(observations)
    unique_setups = len(occurrences)
    unique_confirmed_setups = sum(
        1 for group in occurrences if any(o.status is SetupState.CONFIRMED for o in group)
    )
    evaluated_outcomes = len(outcomes)
    confirmed_without_geometry = max(0, unique_confirmed_setups - evaluated_outcomes)

    target_first = sum(1 for o in outcomes if o.status is OutcomeStatus.TARGET_FIRST)
    stop_first = sum(1 for o in outcomes if o.status is OutcomeStatus.STOP_FIRST)
    ambiguous = sum(1 for o in outcomes if o.status is OutcomeStatus.AMBIGUOUS_SAME_BAR)
    neither = sum(1 for o in outcomes if o.status is OutcomeStatus.NEITHER_WITHIN_WINDOW)
    resolved_unambiguous = target_first + stop_first

    rr_values = [o.risk_reward_ratio for o in outcomes]
    rr_sorted = sorted(rr_values)
    risk_reward_mean = sum(rr_values) / len(rr_values) if rr_values else None
    risk_reward_median = _percentile(rr_sorted, 0.5) if rr_sorted else None

    formation_rows = [
        group[0]
        for group in occurrences
        if group[0].risk_reward_ratio is not None
        and group[0].stop_price is not None
        and group[0].target_price is not None
        and group[0].reference_price is not None
    ]
    risk_fractions = [
        abs(row.reference_price - row.stop_price) / row.reference_price for row in formation_rows
    ]
    reward_fractions = [
        abs(row.target_price - row.reference_price) / row.reference_price for row in formation_rows
    ]
    formation_rr = [row.risk_reward_ratio for row in formation_rows]

    by_symbol = tuple(
        _cohort(symbol, [o for o in outcomes if o.symbol == symbol]) for symbol in run.symbols
    )
    by_side = tuple(
        _cohort(direction.value, [o for o in outcomes if o.direction is direction])
        for direction in (Direction.LONG, Direction.SHORT)
    )
    months = sorted({o.confirmed_at.strftime("%Y-%m") for o in outcomes})
    by_month = tuple(
        _cohort(month, [o for o in outcomes if o.confirmed_at.strftime("%Y-%m") == month])
        for month in months
    )

    families = sorted({factor.family for o in observations for factor in o.directional_factors})
    directional_leans = {"long", "short"}
    pair_agreement = []
    for i, family_a in enumerate(families):
        for family_b in families[i + 1 :]:
            both = 0
            agree = 0
            for observation in observations:
                leans = {f.family: f.lean for f in observation.directional_factors}
                if family_a not in leans or family_b not in leans:
                    continue
                lean_a, lean_b = leans[family_a], leans[family_b]
                if lean_a in directional_leans and lean_b in directional_leans:
                    both += 1
                    if lean_a == lean_b:
                        agree += 1
            pair_agreement.append(
                PairAgreement(
                    family_a=family_a,
                    family_b=family_b,
                    both_directional=both,
                    agree=agree,
                    agreement_rate=_outcome_rate(agree, both),
                )
            )

    all_directional = 0
    all_agree = 0
    for observation in observations:
        leans = [f.lean for f in observation.directional_factors]
        if len(leans) == len(families) and all(lean in directional_leans for lean in leans):
            all_directional += 1
            if len(set(leans)) == 1:
                all_agree += 1
    triple = TripleAgreement(
        all_directional=all_directional,
        all_agree=all_agree,
        agreement_rate=_outcome_rate(all_agree, all_directional),
    )

    confirmation_index = _observation_by_confirmation(observations)
    exactly_two: list[SetupOutcome] = []
    all_three: list[SetupOutcome] = []
    for outcome in outcomes:
        observation = confirmation_index.get((outcome.symbol, outcome.confirmed_at))
        if observation is None or observation.direction is None:
            continue
        agreeing = sum(
            1
            for factor in observation.directional_factors
            if factor.lean == observation.direction.value
        )
        (all_three if agreeing >= len(families) else exactly_two).append(outcome)
    agreement_cohort_outcomes = (
        _to_agreement_cohort("exactly_2_of_3", exactly_two),
        _to_agreement_cohort("all_agree", all_three),
    )

    structure_counts: dict[str, int] = defaultdict(int)
    for observation in observations:
        structure_counts[observation.context_regime_structure] += 1

    regime_changes = 0
    regime_pairs = 0
    for _symbol, group in groupby(observations, key=lambda o: o.symbol):
        previous_state: str | None = None
        for observation in group:
            if previous_state is not None:
                regime_pairs += 1
                if observation.context_regime_structure != previous_state:
                    regime_changes += 1
            previous_state = observation.context_regime_structure
    regime_change_rate = regime_changes / regime_pairs if regime_pairs else None

    blocked_only_by_regime = sum(
        1
        for observation in observations
        if observation.status is SetupState.WAIT
        and any(_REGIME_ONLY_BLOCK_MARKER in line for line in observation.thesis)
    )

    return BacktestMetrics(
        total_observations=len(observations),
        wait_count=wait_count,
        candidate_count=candidate_count,
        confirmed_count=confirmed_count,
        unique_setups=unique_setups,
        unique_confirmed_setups=unique_confirmed_setups,
        evaluated_outcomes=evaluated_outcomes,
        confirmed_without_geometry=confirmed_without_geometry,
        target_first=target_first,
        stop_first=stop_first,
        ambiguous_same_bar=ambiguous,
        neither_within_window=neither,
        target_first_rate=_outcome_rate(target_first, resolved_unambiguous),
        stop_first_rate=_outcome_rate(stop_first, resolved_unambiguous),
        risk_reward_mean=risk_reward_mean,
        risk_reward_median=risk_reward_median,
        risk_reward_percentiles=_percentiles(formation_rr),
        risk_fraction_percentiles=_percentiles(risk_fractions),
        reward_fraction_percentiles=_percentiles(reward_fractions),
        by_symbol=by_symbol,
        by_side=by_side,
        by_month=by_month,
        pair_agreement=tuple(pair_agreement),
        triple_agreement=triple,
        agreement_cohort_outcomes=agreement_cohort_outcomes,
        structure_state_distribution=dict(structure_counts),
        regime_change_rate=regime_change_rate,
        blocked_only_by_regime=blocked_only_by_regime,
    )


def _to_agreement_cohort(label: str, outcomes: Sequence[SetupOutcome]) -> AgreementCohortOutcomes:
    return AgreementCohortOutcomes(
        label=label,
        total=len(outcomes),
        target_first=sum(1 for o in outcomes if o.status is OutcomeStatus.TARGET_FIRST),
        stop_first=sum(1 for o in outcomes if o.status is OutcomeStatus.STOP_FIRST),
        ambiguous_same_bar=sum(1 for o in outcomes if o.status is OutcomeStatus.AMBIGUOUS_SAME_BAR),
        neither_within_window=sum(
            1 for o in outcomes if o.status is OutcomeStatus.NEITHER_WITHIN_WINDOW
        ),
    )
