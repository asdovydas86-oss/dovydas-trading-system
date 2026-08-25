"""Replaying history once and judging it many times. **Facts are shared; policies are not.**

    fetch (Milestone BC's dataset)  ──►  one instant  ──►  SetupInputs
                                                              │
                                        ┌─────────────────────┼─────────────────────┐
                                        ▼                     ▼                     ▼
                                   swing_current       swing_1w_context      swing_1d4h_core
                                        │                     │                     │
                                        └──────────► one LabObservation each ◄──────┘

**Why one facts pass.** Every variant that shares a role→interval mapping reads
*identical* market facts: `SetupInputs` is built from candles, indicators and
regimes, none of which know what a policy is. Only `evaluate_setup` differs.
Computing the facts once and evaluating four policies over them is therefore not
merely four times cheaper — it is what makes the comparison **exact**. Four
separate replays would each re-derive the same numbers, and any floating-point
or provider difference between them would show up as a policy difference.

Variants whose interval mapping differs cannot share a pass, get their own
dataset and their own derived warm-up, and are grouped accordingly.

**No-lookahead is inherited, not reimplemented.** The replay transport, the
closed-candle semantics and the three window boundaries are Milestone BC's
(`fmis.swing_setup.research_harness`, `fmis.swing_setup.backtest_replay`), used
unchanged. This module adds no data access of its own: it cannot see a future
candle because it never asks for one, and the one place it deliberately reads
forward — resolving what happened *after* a decision already frozen — operates
on a separately decoded series and can never flow back into an assessment.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.decision_context import ContextPolicy, ContextState
from fmis.market_regime import RegimePolicy, StructureState
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.pipeline.multi_timeframe import TimeframeRole, multi_timeframe_facts_for_symbol
from fmis.pipeline.regime import regime_features
from fmis.paper.models import PriceBar
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport
from fmis.swing_lab.models import (
    GateObservation,
    GateVerdict,
    LabTrade,
    LabVariant,
    SwingLabError,
)
from fmis.swing_lab.trades import simulate_trade, to_price_bars
from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_LIMIT
from fmis.swing_setup.backtest_models import DataBoundary
from fmis.swing_setup.backtest_replay import CLOSE_TIME_INDEX, build_replay_transport, from_epoch_ms
from fmis.swing_setup.compose import setup_inputs_and_assessment_for_sheet
from fmis.swing_setup.models import Direction, SetupAssessment, SetupInputs, SetupState
from fmis.swing_setup.policy import evaluate_setup
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    ResearchDataset,
    decode_full_series,
    fetch_research_dataset,
)
from fmis.swing_setup.research_identity import OpportunityTracker
from fmis.swing_setup.research_models import (
    AvailabilityReport,
    ResearchWindow,
    TemporalSegment,
    WarmupRequirement,
    interval_duration,
)
from fmis.swing_setup.research_warmup import derive_warmup
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "LabObservation",
    "VariantReplay",
    "ReplayInstant",
    "UnanalysableInstant",
    "decode_symbol_bars",
    "replay_instants",
    "replay_variant_group",
    "group_variants",
]


@dataclass(frozen=True, slots=True)
class LabObservation:
    """What one variant concluded at one instant. Deliberately compact.

    A study replays tens of thousands of instants across several variants, so
    this holds the fields a breakdown or a gate attribution actually consumes
    and not a second copy of the assessment. The assessment itself is
    reconstructible by rerunning the instant, which the manifest makes possible.
    """

    symbol: str
    as_of: datetime
    state: SetupState
    direction: Direction | None
    setup_id: str
    is_first_confirmation: bool
    in_measurement: bool
    segment: str | None
    context_regime_structure: str
    context_structural_trend: str
    setup_structural_trend: str
    decision_context_state: str
    policy_id: str


@dataclass(frozen=True, slots=True)
class VariantReplay:
    """One variant's observations and trades over one dataset."""

    variant: LabVariant
    observations: tuple[LabObservation, ...]
    trades: tuple[LabTrade, ...]
    metadata: Mapping[str, Any]

    @property
    def measured_observations(self) -> tuple[LabObservation, ...]:
        return tuple(item for item in self.observations if item.in_measurement)


def group_variants(
    variants: Sequence[LabVariant],
) -> tuple[tuple[tuple[str, str, str], tuple[LabVariant, ...]], ...]:
    """Partition variants by role→interval mapping, preserving requested order.

    Variants in one group read identical facts and share a replay pass; two
    groups cannot, because their candles differ. Returned as a tuple of pairs
    rather than a dict so the iteration order is the caller's and a run is
    reproducible regardless of hash seed.
    """
    order: list[tuple[str, str, str]] = []
    grouped: dict[tuple[str, str, str], list[LabVariant]] = {}
    for variant in variants:
        if not isinstance(variant, LabVariant):
            raise TypeError("every variant must be a LabVariant")
        key = variant.interval_signature
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(variant)
    return tuple((key, tuple(grouped[key])) for key in order)


def _gate_verdict(
    inputs: SetupInputs, counterfactual: SetupAssessment | None
) -> GateVerdict:
    """What the production context-role gate did, read from facts alone.

    The production policy checks decision-context sufficiency *before* the
    regime gate, so an `INSUFFICIENT` context means the gate was never reached
    — attributing that instant to the gate would blame it for a refusal it had
    no part in, and would inflate exactly the number this milestone exists to
    measure.

    ``counterfactual`` is the assessment the same instant produced under the
    treatment that removes the gate. It is what turns "the gate blocked" into
    "the gate blocked *something*": without it, every non-trending weekly bar
    would count as a blocked opportunity, including the overwhelming majority
    where no direction existed to block.
    """
    if inputs.decision_context_state is ContextState.INSUFFICIENT:
        return GateVerdict.NOT_REACHED
    if inputs.context_regime_structure is StructureState.TRENDING:
        return GateVerdict.ALLOWED
    if counterfactual is None:
        return GateVerdict.BLOCKED_WITHOUT_EFFECT
    if counterfactual.state is SetupState.CONFIRMED:
        return GateVerdict.BLOCKED_CONFIRMED
    if counterfactual.state is SetupState.CANDIDATE:
        return GateVerdict.BLOCKED_CANDIDATE
    return GateVerdict.BLOCKED_WITHOUT_EFFECT


def _segment_of(segments: Sequence[TemporalSegment], instant: datetime) -> str | None:
    for segment in segments:
        if segment.contains(instant):
            return segment.label
    return None


@dataclass(frozen=True, slots=True)
class UnanalysableInstant:
    """An instant whose window the production fact path refused. **A value, not a raise.**

    Roughly one instant in a warm-up prefix cannot be analysed, and that is an
    ordinary countable outcome of a replay rather than an error in it. Raising
    would end the walk; swallowing it would lose a count every manifest reports.
    ``measured`` is carried because *where* the refusal fell is what decides
    which counter it belongs to, and only the generator knows it.
    """

    symbol: str
    as_of: datetime
    measured: bool
    error: InsufficientDataError


@dataclass(frozen=True, slots=True)
class ReplayInstant:
    """One symbol at one decision instant, with the facts that instant produced.

    **The one place history is read, so the one place lookahead could hide.**
    Every consumer in this package — the variant replay of Milestone BW and the
    geometry capture of Milestone BX — is handed these objects rather than
    reaching for candles itself. A second loop that re-derived the same facts
    would be a second chance to accidentally read one bar too far, and there is
    deliberately only one.

    ``signal_index`` is the position, in the symbol's decoded bar array, of the
    bar whose **close** produced this instant. A trade entered from here fills at
    ``signal_index + 1``'s open, never at the close that was being looked at.
    """

    symbol: str
    as_of: datetime
    measured: bool
    segment: str | None
    sheet: Any
    inputs: SetupInputs
    baseline_assessment: SetupAssessment
    last_timestamp: datetime | None
    signal_index: int | None


def decode_symbol_bars(
    dataset: ResearchDataset, symbol: str, execution_interval: str
) -> tuple[tuple[PriceBar, ...], dict[datetime, int]]:
    """One symbol's execution-timeframe bars, and an open-time → position index.

    Raises:
        SwingLabError: the dataset holds no such series.
    """
    rows = dataset.cache.get((symbol, execution_interval))
    if rows is None:
        raise SwingLabError(
            f"the dataset holds no {execution_interval} series for {symbol}"
        )
    bars = to_price_bars(decode_full_series(symbol, execution_interval, rows))
    return bars, {bar.open_time: position for position, bar in enumerate(bars)}


def replay_instants(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str],
    window: ResearchWindow,
    segments: Sequence[TemporalSegment],
    dataset: ResearchDataset,
    index_of: Mapping[datetime, int],
    limit: int = DEFAULT_BACKTEST_LIMIT,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
) -> Iterator[ReplayInstant | UnanalysableInstant]:
    """Walk one symbol's decision instants, yielding the facts each produced.

    An instant the production fact path refuses is yielded as an
    `UnanalysableInstant` rather than raised — see that type for why.

    The transport handed to the production fact path is Milestone BC's replay
    transport, rebuilt per instant with ``now`` pinned to that instant, which is
    what makes a future candle unreachable rather than merely unread.
    """
    execution_interval = timeframes[TimeframeRole.EXECUTION]
    settings = DetectionSettings() if detection is None else detection
    ordered_segments = tuple(segments)
    rows = dataset.cache.get((symbol, execution_interval))
    if rows is None:  # pragma: no cover - decode_symbol_bars already refused
        raise SwingLabError(
            f"the dataset holds no {execution_interval} series for {symbol}"
        )
    priming_start = window.measurement_start - identity_priming_bars * interval_duration(
        execution_interval
    )
    instants = sorted(
        instant
        for instant in {from_epoch_ms(row[CLOSE_TIME_INDEX] + 1) for row in rows}
        if priming_start <= instant < window.measurement_end
    )
    for instant in instants:
        measured = window.is_measured(instant)
        replay_transport = build_replay_transport(
            dataset.cache, now=instant, index=dataset.index
        )
        try:
            sheet = multi_timeframe_facts_for_symbol(
                symbol,
                timeframes=dict(timeframes),
                limit=limit,
                features=regime_features(),
                detection=settings,
                transport=replay_transport,
                clock=lambda moment=instant: moment,
            )
            # The one production composition call in this package. Every policy
            # is `evaluate_setup` over THESE inputs — there is no second fact path.
            inputs, baseline_assessment = setup_inputs_and_assessment_for_sheet(
                sheet, policy=policy, context_policy=context_policy
            )
        except InsufficientDataError as error:
            yield UnanalysableInstant(
                symbol=symbol, as_of=instant, measured=measured, error=error
            )
            continue
        last_timestamp = sheet.by_role[TimeframeRole.EXECUTION].sheet.window.last_timestamp
        yield ReplayInstant(
            symbol=symbol,
            as_of=instant,
            measured=measured,
            segment=_segment_of(ordered_segments, instant) if measured else None,
            sheet=sheet,
            inputs=inputs,
            baseline_assessment=baseline_assessment,
            last_timestamp=last_timestamp,
            signal_index=None if last_timestamp is None else index_of.get(last_timestamp),
        )


def dataset_for_group(
    symbols: Sequence[str],
    intervals: Sequence[str],
    *,
    window: ResearchWindow,
    warmup: WarmupRequirement,
    fetched_at: datetime,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> ResearchDataset:
    """Fetch one group's history. Milestone BC's fetch, called — never a second one."""
    return fetch_research_dataset(
        symbols,
        intervals,
        window=window,
        warmup=warmup,
        fetched_at=fetched_at,
        transport=transport,
        base_url=base_url,
    )


def replay_variant_group(
    symbols: Sequence[str],
    variants: Sequence[LabVariant],
    *,
    window: ResearchWindow,
    warmup: WarmupRequirement,
    segments: Sequence[TemporalSegment],
    dataset: ResearchDataset,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    gate_counterfactual_id: str | None = None,
) -> tuple[tuple[VariantReplay, ...], tuple[GateObservation, ...]]:
    """Replay one interval group: facts once per instant, every variant judged on them.

    ``gate_counterfactual_id`` names the variant whose assessments answer *what
    would have happened without the gate*. It must be present in ``variants``
    and must be a treatment that removes the gate; supplying a variant that
    keeps it would make every gate verdict read `BLOCKED_WITHOUT_EFFECT` and
    silently report the gate as harmless.

    Raises:
        SwingLabError: the variants do not share one interval mapping, the
            dataset lacks a required series, or the counterfactual id is unknown.
    """
    if not variants:
        raise SwingLabError("variants must be a non-empty sequence")
    signatures = {variant.interval_signature for variant in variants}
    if len(signatures) != 1:
        raise SwingLabError(
            "replay_variant_group needs one interval mapping; got "
            f"{sorted(signatures)}"
        )
    if gate_counterfactual_id is not None and gate_counterfactual_id not in {
        variant.variant_id for variant in variants
    }:
        raise SwingLabError(
            f"gate counterfactual {gate_counterfactual_id!r} is not in this group"
        )

    timeframes = dict(variants[0].timeframes)
    execution_interval = timeframes[TimeframeRole.EXECUTION]
    settings = DetectionSettings() if detection is None else detection
    ordered_segments = tuple(segments)

    observations: dict[str, list[LabObservation]] = {v.variant_id: [] for v in variants}
    trades: dict[str, list[LabTrade]] = {v.variant_id: [] for v in variants}
    trackers: dict[str, OpportunityTracker] = {}
    gate_observations: list[GateObservation] = []
    insufficient_measured = 0
    insufficient_priming = 0
    truncated_tail = 0

    for symbol in symbols:
        bars, index_of = decode_symbol_bars(dataset, symbol, execution_interval)
        for variant in variants:
            trackers[variant.variant_id] = OpportunityTracker()

        for item in replay_instants(
            symbol,
            timeframes=timeframes,
            window=window,
            segments=ordered_segments,
            dataset=dataset,
            index_of=index_of,
            limit=limit,
            identity_priming_bars=identity_priming_bars,
            policy=policy,
            context_policy=context_policy,
            detection=settings,
        ):
            if isinstance(item, UnanalysableInstant):
                if item.measured:
                    insufficient_measured += 1
                else:
                    insufficient_priming += 1
                continue

            inputs = item.inputs
            measured = item.measured
            segment = item.segment

            assessments: dict[str, SetupAssessment] = {}
            for variant in variants:
                assessments[variant.variant_id] = (
                    item.baseline_assessment
                    if variant.is_production_baseline
                    else evaluate_setup(
                        inputs,
                        research_confirmation_max_age=variant.max_confirmation_age,
                        research_context_role=variant.context_role,
                    )
                )

            if measured and gate_counterfactual_id is not None:
                gate_observations.append(
                    GateObservation(
                        symbol=symbol,
                        as_of=item.as_of,
                        verdict=_gate_verdict(
                            inputs, assessments[gate_counterfactual_id]
                        ),
                        context_regime_structure=inputs.context_regime_structure.value,
                        counterfactual_direction=assessments[
                            gate_counterfactual_id
                        ].direction,
                        segment=segment,
                    )
                )

            for variant in variants:
                assessment = assessments[variant.variant_id]
                key, _is_new, is_first = trackers[variant.variant_id].observe(
                    symbol, assessment.direction, assessment.state, item.as_of
                )
                observations[variant.variant_id].append(
                    LabObservation(
                        symbol=symbol,
                        as_of=item.as_of,
                        state=assessment.state,
                        direction=assessment.direction,
                        setup_id=key,
                        is_first_confirmation=is_first,
                        in_measurement=measured,
                        segment=segment,
                        context_regime_structure=inputs.context_regime_structure.value,
                        context_structural_trend=inputs.context_structural_trend.value,
                        setup_structural_trend=inputs.setup_structural_trend.value,
                        decision_context_state=inputs.decision_context_state.value,
                        policy_id=assessment.policy_id,
                    )
                )
                if not (
                    measured
                    and is_first
                    and assessment.direction is not None
                    and assessment.stop is not None
                    and assessment.targets
                    and assessment.reference_price is not None
                    and assessment.risk_reward is not None
                    and item.last_timestamp is not None
                ):
                    continue
                signal_index = item.signal_index
                if signal_index is None:  # pragma: no cover - series is the same one
                    continue
                if len(bars) - signal_index - 1 < evaluation_window_bars:
                    truncated_tail += 1
                trades[variant.variant_id].append(
                    simulate_trade(
                        bars,
                        variant_id=variant.variant_id,
                        symbol=symbol,
                        setup_id=key,
                        direction=assessment.direction,
                        signal_index=signal_index,
                        signal_at=item.last_timestamp,
                        reference_price=assessment.reference_price,
                        stop_price=assessment.stop.price,
                        target_price=assessment.targets[0].price,
                        planned_risk_reward=assessment.risk_reward.ratio,
                        window_bars=evaluation_window_bars,
                        costs=costs,
                        segment=segment,
                        context_regime_structure=inputs.context_regime_structure.value,
                        context_structural_trend=inputs.context_structural_trend.value,
                        setup_structural_trend=inputs.setup_structural_trend.value,
                    )
                )

    replays = tuple(
        VariantReplay(
            variant=variant,
            observations=tuple(observations[variant.variant_id]),
            trades=tuple(trades[variant.variant_id]),
            metadata={
                "candle_limit": limit,
                "insufficient_data_measured_instants": insufficient_measured,
                "insufficient_data_priming_instants": insufficient_priming,
                "trades_against_truncated_tail": truncated_tail,
                "cost_policy_id": costs.policy_id,
                "evaluation_window_bars": evaluation_window_bars,
            },
        )
        for variant in variants
    )
    return replays, tuple(gate_observations)
