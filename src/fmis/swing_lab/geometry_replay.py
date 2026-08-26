"""Capturing geometry candidates once, so every geometry policy is free afterwards.

    replay (expensive, ~20 ms/instant)          plan + simulate (microseconds)
    ────────────────────────────────────        ─────────────────────────────────
    history ──► SetupInputs ──► admission ──►  GeometryCandidate ──► 13 policies
                                                       │              7 grid points
                                                       ▼              …
                                                  frozen facts        each a trade list

**Why this shape.** Milestone BW's primary study spent eleven minutes deriving
facts and four milliseconds evaluating policies over them. BX asks for far more
policies — thirteen pre-declared, two sensitivity grids, a development sample and
a holdout — and re-replaying history for each would cost hours and, worse, would
make every comparison approximate: two replays of the same window can differ for
provider reasons that have nothing to do with geometry.

So the replay happens **once** and freezes a `GeometryCandidate` per admitted
setup. Every policy is then a pure function over frozen records. This is
Milestone BW's *facts once, policies many* discipline applied one level further
down, and it buys the same two things: speed, and an exact comparison.

**It also makes lookahead unrepresentable.** A `GeometryCandidate` holds prices,
levels and one ATR reading, all as of the decision instant. It holds no bar, no
future timestamp and no outcome. A geometry policy is handed nothing else, so it
*cannot* read forward — not as a matter of discipline but as a matter of what
exists. Bars live beside the candidates, are handed only to the simulator, and
the simulator's output can never flow back into a plan.

**No admission rule is invented here.** Which setups become candidates is
`evaluate_setup`'s decision under a `LabVariant` — the production policy by
default — called exactly as `fmis.swing_lab.replay` calls it, over the same
`ReplayInstant` generator. This module chooses no direction and forms no thesis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fmis.decision_context import ContextPolicy
from fmis.features.indicators.atr import AverageTrueRange
from fmis.level_crossing import LevelSide
from fmis.market_regime import RegimePolicy
from fmis.paper.models import PriceBar
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import FAST_ATR_PERIOD
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.swing_lab.geometry import (
    GeometryCandidate,
    GeometryPlan,
    GeometrySkip,
    PlansGeometry,
    level_refs,
)
from fmis.swing_lab.models import LabTrade, LabVariant, SwingLabError
from fmis.swing_lab.replay import (
    ReplayInstant,
    UnanalysableInstant,
    decode_symbol_bars,
    replay_instants,
)
from fmis.swing_lab.trades import simulate_trade
from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_LIMIT
from fmis.swing_setup.models import STOP_SIDE, TARGET_SIDE, SetupState
from fmis.swing_setup.policy import evaluate_setup, ordered_levels
from fmis.swing_setup.research_harness import DEFAULT_IDENTITY_PRIMING_BARS, ResearchDataset
from fmis.swing_setup.research_identity import OpportunityTracker
from fmis.swing_setup.research_models import ResearchWindow, TemporalSegment
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "ATR_FEATURE_NAME",
    "GeometryCapture",
    "PolicyOutcome",
    "capture_geometry_candidates",
    "trades_for_policy",
]

#: The volatility feature this milestone reads, named from the **production
#: constant** rather than retyped. `fmis.pipeline.regime.regime_features` already
#: computes it on every view; BX adds no volatility calculation of its own, and
#: deriving the name here means a change to `FAST_ATR_PERIOD` moves this with it
#: instead of silently reading a feature that no longer exists.
ATR_FEATURE_NAME: str = AverageTrueRange(FAST_ATR_PERIOD).name


@dataclass(frozen=True, slots=True)
class GeometryCapture:
    """Every admitted candidate from one replay, plus the bars trades resolve over.

    ``bars_by_symbol`` is held beside the candidates rather than inside them, and
    that separation is the architecture: a `GeometryCandidate` is what a policy
    sees, bars are what the *simulator* sees, and no policy is ever handed both.
    """

    admission_variant_id: str
    admission_policy_id: str
    candidates: tuple[GeometryCandidate, ...]
    bars_by_symbol: Mapping[str, tuple[PriceBar, ...]]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def for_symbols(self, symbols: Sequence[str]) -> "GeometryCapture":
        """The same capture narrowed to a symbol set. **Selection, never recomputation.**

        This is how a development sample and a holdout are cut from one replay:
        both see byte-identical candidates, because they *are* the same objects.
        Two separate replays would each re-derive them and any provider
        difference would surface as a sample difference.
        """
        wanted = set(symbols)
        unknown = sorted(wanted - set(self.bars_by_symbol))
        if unknown:
            raise SwingLabError(
                f"this capture holds no candidates for {', '.join(unknown)}; it "
                f"holds {', '.join(sorted(self.bars_by_symbol))}"
            )
        return GeometryCapture(
            admission_variant_id=self.admission_variant_id,
            admission_policy_id=self.admission_policy_id,
            candidates=tuple(c for c in self.candidates if c.symbol in wanted),
            bars_by_symbol={
                symbol: bars
                for symbol, bars in self.bars_by_symbol.items()
                if symbol in wanted
            },
            metadata=dict(self.metadata),
        )


def _atr_of(sheet: Any, role: TimeframeRole) -> float | None:
    """One view's ATR(14), or ``None`` while it is still warming up.

    A missing feature and a warming-up feature are the same fact to this layer —
    the number is not available — and both stay ``None`` rather than becoming a
    zero that a comparison would treat as real. `fmis.pipeline.regime._value`
    reaches the identical conclusion for the identical reason.
    """
    view = sheet.by_role.get(role)
    if view is None:  # pragma: no cover - every role is always mapped
        return None
    result = view.sheet.features.features.get(ATR_FEATURE_NAME)
    if result is None or result.value is None:
        return None
    value = result.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):  # pragma: no cover
        return None
    # A non-positive ATR is a broken measurement rather than a calm market;
    # `GeometryCandidate` refuses to carry one, so it is dropped to absent here.
    return float(value) if value > 0 else None


def _candidate_from(
    item: ReplayInstant, *, setup_id: str, timeframes: Mapping[TimeframeRole, str]
) -> GeometryCandidate:
    """Freeze one instant's geometry facts. **A selection and a copy, never a calculation.**

    Every level list is `fmis.swing_setup.policy.ordered_levels` — production's
    own ordering, called — so a policy taking the second nearest level agrees
    with production about what "nearer" means.
    """
    inputs = item.inputs
    assessment = item.baseline_assessment
    direction = assessment.direction
    reference = assessment.reference_price
    stop_side = STOP_SIDE[direction]
    target_side = TARGET_SIDE[direction]
    context_interval = timeframes[TimeframeRole.CONTEXT]
    setup_interval = timeframes[TimeframeRole.SETUP]
    execution_interval = timeframes[TimeframeRole.EXECUTION]
    context_levels = item.sheet.by_role[TimeframeRole.CONTEXT].sheet.structure.levels

    def ordered(levels: Any, side: LevelSide, interval: str) -> tuple[Any, ...]:
        return level_refs(
            ordered_levels(
                tuple(levels),
                side=side,
                close=reference,
                above=(side is LevelSide.UPPER),
            ),
            interval=interval,
        )

    return GeometryCandidate(
        symbol=item.symbol,
        setup_id=setup_id,
        direction=direction,
        signal_at=item.last_timestamp,
        signal_index=item.signal_index,
        reference_price=reference,
        execution_stop_levels=ordered(
            inputs.execution_levels, stop_side, execution_interval
        ),
        setup_stop_levels=ordered(inputs.setup_levels, stop_side, setup_interval),
        setup_target_levels=ordered(inputs.setup_levels, target_side, setup_interval),
        context_target_levels=ordered(context_levels, target_side, context_interval),
        execution_atr=_atr_of(item.sheet, TimeframeRole.EXECUTION),
        setup_atr=_atr_of(item.sheet, TimeframeRole.SETUP),
        context_interval=context_interval,
        setup_interval=setup_interval,
        execution_interval=execution_interval,
        segment=item.segment,
        context_regime_structure=inputs.context_regime_structure.value,
        context_regime_volatility=inputs.context_regime_volatility.value,
        context_structural_trend=inputs.context_structural_trend.value,
        setup_structural_trend=inputs.setup_structural_trend.value,
        metadata={
            "production_stop": (
                None if assessment.stop is None else assessment.stop.price
            ),
            "production_target": (
                None if not assessment.targets else assessment.targets[0].price
            ),
            "production_planned_rr": (
                None if assessment.risk_reward is None else assessment.risk_reward.ratio
            ),
        },
    )


def capture_geometry_candidates(
    symbols: Sequence[str],
    admission: LabVariant,
    *,
    window: ResearchWindow,
    segments: Sequence[TemporalSegment],
    dataset: ResearchDataset,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
) -> GeometryCapture:
    """Replay history once and freeze every admitted setup's geometry facts.

    ``admission`` decides *which* setups become candidates and is
    `evaluate_setup` under a `LabVariant` — production's own policy when the
    variant supplies no override. This function never forms a thesis, never
    chooses a direction and never relaxes an admission rule.

    A setup is admitted on the same terms Milestone BW used — a first
    confirmation, inside the measurement window, with a direction and a
    reference price — with **one deliberate difference**: BW additionally
    required the production stop and target to exist, because it had no other
    geometry. Here their absence is a candidate whose policies each return a
    named `SkipReason`, so "the engine found no 4H level" and "the engine found
    one and it was too close" stop looking alike.

    Raises:
        SwingLabError: the dataset lacks a series the walk needs.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise SwingLabError("symbols must be a non-empty, non-string sequence")
    if not isinstance(admission, LabVariant):
        raise TypeError("admission must be a LabVariant")

    timeframes = dict(admission.timeframes)
    execution_interval = timeframes[TimeframeRole.EXECUTION]
    settings = DetectionSettings() if detection is None else detection

    candidates: list[GeometryCandidate] = []
    bars_by_symbol: dict[str, tuple[PriceBar, ...]] = {}
    insufficient_measured = 0
    insufficient_priming = 0
    confirmations_without_index = 0
    measured_instants = 0

    for symbol in symbols:
        bars, index_of = decode_symbol_bars(dataset, symbol, execution_interval)
        bars_by_symbol[symbol] = bars
        tracker = OpportunityTracker()
        for item in replay_instants(
            symbol,
            timeframes=timeframes,
            window=window,
            segments=segments,
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

            assessment = (
                item.baseline_assessment
                if admission.is_production_baseline
                else evaluate_setup(
                    item.inputs,
                    research_confirmation_max_age=admission.max_confirmation_age,
                    research_context_role=admission.context_role,
                )
            )
            if item.measured:
                measured_instants += 1
            setup_id, _is_new, is_first = tracker.observe(
                symbol, assessment.direction, assessment.state, item.as_of
            )
            if not (
                item.measured
                and is_first
                and assessment.state is SetupState.CONFIRMED
                and assessment.direction is not None
                and assessment.reference_price is not None
                and item.last_timestamp is not None
            ):
                continue
            if item.signal_index is None:  # pragma: no cover - same series both ways
                confirmations_without_index += 1
                continue
            # The assessment is re-bound onto the instant so `_candidate_from`
            # reads the ADMISSION variant's assessment rather than the
            # production baseline it may not be.
            frozen = ReplayInstant(
                symbol=item.symbol,
                as_of=item.as_of,
                measured=item.measured,
                segment=item.segment,
                sheet=item.sheet,
                inputs=item.inputs,
                baseline_assessment=assessment,
                last_timestamp=item.last_timestamp,
                signal_index=item.signal_index,
            )
            candidates.append(
                _candidate_from(frozen, setup_id=setup_id, timeframes=timeframes)
            )

    return GeometryCapture(
        admission_variant_id=admission.variant_id,
        admission_policy_id=admission.policy_id,
        # Sorted by identity rather than by iteration order, so a capture is
        # invariant to the order symbols were requested in and to PYTHONHASHSEED.
        candidates=tuple(
            sorted(candidates, key=lambda c: (c.symbol, c.signal_at, c.setup_id))
        ),
        bars_by_symbol=bars_by_symbol,
        metadata={
            "candle_limit": limit,
            "identity_priming_bars": identity_priming_bars,
            "measured_instants": measured_instants,
            "insufficient_data_measured_instants": insufficient_measured,
            "insufficient_data_priming_instants": insufficient_priming,
            "confirmations_without_bar_index": confirmations_without_index,
            "atr_feature": ATR_FEATURE_NAME,
        },
    )


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    """One geometry policy applied across one capture: its trades and its refusals.

    Skips are carried beside trades, never dropped. A policy that trades six
    times because it refused ninety candidates and a policy that trades six
    times because only six setups formed are different findings, and a trade
    list alone cannot tell them apart.
    """

    policy: PlansGeometry
    trades: tuple[LabTrade, ...]
    plans: tuple[GeometryPlan, ...]
    skips: tuple[GeometrySkip, ...]

    @property
    def admitted(self) -> int:
        return len(self.plans)

    @property
    def refused(self) -> int:
        return len(self.skips)


def trades_for_policy(
    capture: GeometryCapture,
    policy: PlansGeometry,
    *,
    costs: PaperCostPolicy,
    evaluation_window_bars: int,
) -> PolicyOutcome:
    """Plan every candidate under one policy and simulate the admitted ones.

    Pure with respect to history: the only market data consulted is the bar array
    the capture already holds, and it is consulted **only** by
    `fmis.swing_lab.trades.simulate_trade`, whose fill rules are the paper
    engine's own. This function compares no price to any level.

    The simulated trade's ``variant_id`` is the geometry ``policy_id``, so a
    trade record always says which geometry produced it and two policies' trades
    can never be summed by accident.
    """
    if not isinstance(capture, GeometryCapture):
        raise TypeError("capture must be a GeometryCapture")
    if not isinstance(policy, PlansGeometry):
        # `PlansGeometry` rather than `GeometryPolicy`: Milestone BY's
        # non-structural control lives in its own module by design (see
        # `fmis.swing_lab.nonstructural`), and measuring a control with different
        # machinery would make it useless as a control.
        raise TypeError(
            "policy must satisfy PlansGeometry — policy_id, family and "
            f"plan(candidate); {type(policy).__name__} does not"
        )

    trades: list[LabTrade] = []
    plans: list[GeometryPlan] = []
    skips: list[GeometrySkip] = []
    for candidate in capture.candidates:
        outcome = policy.plan(candidate)
        if isinstance(outcome, GeometrySkip):
            skips.append(outcome)
            continue
        plans.append(outcome)
        trades.append(
            simulate_trade(
                capture.bars_by_symbol[candidate.symbol],
                variant_id=policy.policy_id,
                symbol=candidate.symbol,
                setup_id=candidate.setup_id,
                direction=candidate.direction,
                signal_index=candidate.signal_index,
                signal_at=candidate.signal_at,
                reference_price=outcome.entry,
                stop_price=outcome.stop.price,
                target_price=outcome.target.price,
                planned_risk_reward=outcome.planned_rr,
                window_bars=evaluation_window_bars,
                costs=costs,
                segment=candidate.segment,
                context_regime_structure=candidate.context_regime_structure,
                context_structural_trend=candidate.context_structural_trend,
                setup_structural_trend=candidate.setup_structural_trend,
            )
        )
    return PolicyOutcome(
        policy=policy,
        trades=tuple(trades),
        plans=tuple(plans),
        skips=tuple(skips),
    )
