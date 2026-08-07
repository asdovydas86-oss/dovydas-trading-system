"""Milestone AR — Swing Setup Engine v1: the deterministic policy.

The claims this suite exists to pin, each independently:

* a directional candidate never forms from fewer than two agreeing families,
  and never when one family opposes (no single-indicator rule, no double
  counting via a majority-of-one);
* `fmis.decision_context.INSUFFICIENT` forecloses a candidate unconditionally;
* the CONTEXT-role regime structure gates a candidate without ever itself
  carrying a direction;
* EXECUTION never votes on direction — it only confirms or withholds;
* LONG and SHORT are exact structural mirrors of each other;
* stop/target geometry, once selected, always yields a valid, positive R/R;
* the policy is a pure function: equal inputs give equal outputs, always.

Expected values are derived by hand from the family-tally rule, never by
calling the policy under test.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.decision_support import Alignment, OverallState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.market_structure import StructuralSwingLabel
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import (
    Direction,
    ExecutionBreakEvent,
    Lean,
    SetupInputs,
    SetupState,
    evaluate_setup,
)
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    MINIMUM_AGREEING_FAMILIES,
    SETUP_POLICY_ID,
)

_AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)
_ORIGIN_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)

_OPPOSITE = {
    StructuralTrendType.SUSTAINED_HIGHER: StructuralTrendType.SUSTAINED_LOWER,
    StructuralTrendType.SUSTAINED_LOWER: StructuralTrendType.SUSTAINED_HIGHER,
}
_OPPOSITE_ALIGNMENT = {Alignment.UPWARD: Alignment.DOWNWARD, Alignment.DOWNWARD: Alignment.UPWARD}
_OPPOSITE_SIDE = {LevelSide.UPPER: LevelSide.LOWER, LevelSide.LOWER: LevelSide.UPPER}


def _level(side: LevelSide, price: float, index: int = 1) -> PriceLevel:
    label = StructuralSwingLabel.HIGHER_HIGH if side is LevelSide.UPPER else StructuralSwingLabel.LOWER_LOW
    return PriceLevel(
        side=side, price=price,
        origin=LevelOrigin(index=index, timestamp=_ORIGIN_TS, label=label, confirmation_bars=2),
    )


def _mirror_trend(trend: StructuralTrendType) -> StructuralTrendType:
    return _OPPOSITE.get(trend, trend)


def _breaks(*events: tuple[LevelSide, float, int]) -> tuple[ExecutionBreakEvent, ...]:
    """Build an `execution_breaks` history from ``(side, price, bar_index)`` triples."""
    return tuple(
        ExecutionBreakEvent(level=_level(side, price, index=1), index=bar_index)
        for side, price, bar_index in events
    )


def base_inputs(**overrides) -> SetupInputs:
    kwargs = dict(
        symbol="BTCUSDT",
        as_of=_AS_OF,
        source="fixture",
        context_interval="1w",
        setup_interval="1d",
        execution_interval="4h",
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        execution_structural_trend=StructuralTrendType.NEUTRAL,
        context_regime_structure=StructureState.TRENDING,
        context_regime_volatility=VolatilityState.STEADY,
        context_regime_participation=ParticipationState.TYPICAL,
        evidence_state=OverallState.WATCH,
        evidence_dominant_alignment=Alignment.UPWARD,
        decision_context_state=ContextState.SUFFICIENT,
        decision_context_statements=(),
        execution_close=100.0,
        execution_closed_count=10,
        execution_levels=(_level(LevelSide.UPPER, 110.0), _level(LevelSide.LOWER, 90.0)),
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5)),
        setup_levels=(_level(LevelSide.UPPER, 130.0), _level(LevelSide.LOWER, 70.0)),
        inherited_limitations=("X-1: test",),
    )
    kwargs.update(overrides)
    return SetupInputs(**kwargs)


def mirror(inputs: SetupInputs) -> SetupInputs:
    """Flip every directional fact to its opposite. A SHORT fixture, from a LONG one.

    Non-directional gates (the regime state, decision-context sufficiency) are
    carried through unchanged — mirroring them would test a different fixture.
    """
    return base_inputs(
        context_regime_structure=inputs.context_regime_structure,
        decision_context_state=inputs.decision_context_state,
        execution_closed_count=inputs.execution_closed_count,
        context_structural_trend=_mirror_trend(inputs.context_structural_trend),
        setup_structural_trend=_mirror_trend(inputs.setup_structural_trend),
        execution_structural_trend=_mirror_trend(inputs.execution_structural_trend),
        evidence_dominant_alignment=_OPPOSITE_ALIGNMENT.get(
            inputs.evidence_dominant_alignment, inputs.evidence_dominant_alignment
        ),
        execution_breaks=tuple(
            ExecutionBreakEvent(
                level=_level(
                    _OPPOSITE_SIDE[event.level.side],
                    200.0 - event.level.price,
                    index=event.level.origin.index,
                ),
                index=event.index,
            )
            for event in inputs.execution_breaks
        ),
        execution_levels=tuple(
            _level(_OPPOSITE_SIDE[lv.side], 200.0 - lv.price, index=lv.origin.index)
            for lv in inputs.execution_levels
        ),
        setup_levels=tuple(
            _level(_OPPOSITE_SIDE[lv.side], 200.0 - lv.price, index=lv.origin.index)
            for lv in inputs.setup_levels
        ),
    )


# ============================ 1. WAIT — the gates =============================


def test_insufficient_decision_context_forecloses_a_candidate_unconditionally() -> None:
    inputs = base_inputs(decision_context_state=ContextState.INSUFFICIENT)
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None
    assert "INSUFFICIENT" in result.thesis[0]


def test_insufficient_decision_context_wins_even_with_full_agreement() -> None:
    """Every other signal supports LONG; the context gate still wins."""
    inputs = base_inputs(
        decision_context_state=ContextState.INSUFFICIENT,
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        evidence_state=OverallState.WATCH,
        evidence_dominant_alignment=Alignment.UPWARD,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None


def test_a_ranging_context_regime_forecloses_a_candidate() -> None:
    inputs = base_inputs(context_regime_structure=StructureState.RANGING)
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None
    assert "ranging" in result.thesis[0]


@pytest.mark.parametrize(
    "state",
    [StructureState.TRANSITIONING, StructureState.INDETERMINATE, StructureState.INSUFFICIENT],
)
def test_every_non_trending_context_regime_state_forecloses_a_candidate(state) -> None:
    result = evaluate_setup(base_inputs(context_regime_structure=state))
    assert result.state is SetupState.WAIT
    assert result.direction is None


def test_regime_never_appears_as_a_directional_factor() -> None:
    """The regime gate is not a fourth vote — it never appears in the tally."""
    result = evaluate_setup(base_inputs())
    families = {factor.family for factor in result.directional_factors}
    assert not any("regime" in family for family in families)
    assert len(result.directional_factors) == 3


def test_a_single_agreeing_family_is_not_enough() -> None:
    inputs = base_inputs(
        setup_structural_trend=StructuralTrendType.INDETERMINATE,
        evidence_state=OverallState.INSUFFICIENT_DATA,
        evidence_dominant_alignment=None,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None
    factors = {f.family: f.lean for f in result.directional_factors}
    assert factors["context_structural_trend"] is Lean.LONG
    assert factors["setup_structural_trend"] is Lean.UNAVAILABLE
    assert factors["setup_evidence_alignment"] is Lean.UNAVAILABLE


def test_two_families_opposing_one_produce_wait_not_a_majority() -> None:
    """2 long vs 1 short is not a majority under this policy: zero opposition is required."""
    inputs = base_inputs(
        context_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        evidence_state=OverallState.WATCH,
        evidence_dominant_alignment=Alignment.DOWNWARD,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None


def test_two_short_families_opposed_by_one_long_produce_wait_not_a_majority() -> None:
    """The mirror of the case above: 2 short vs 1 long is also not a majority."""
    inputs = base_inputs(
        context_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        setup_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        evidence_state=OverallState.WATCH,
        evidence_dominant_alignment=Alignment.UPWARD,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None


def test_all_conflicting_produces_wait() -> None:
    inputs = base_inputs(
        context_structural_trend=StructuralTrendType.NEUTRAL,
        setup_structural_trend=StructuralTrendType.NEUTRAL,
        evidence_state=OverallState.WAIT,
        evidence_dominant_alignment=Alignment.NEUTRAL,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None
    assert all(f.lean is Lean.CONFLICTING for f in result.directional_factors)


def test_all_unavailable_produces_wait() -> None:
    inputs = base_inputs(
        context_structural_trend=StructuralTrendType.INDETERMINATE,
        setup_structural_trend=StructuralTrendType.INDETERMINATE,
        evidence_state=None,
        evidence_dominant_alignment=None,
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.WAIT
    assert result.direction is None


def test_wait_is_not_an_exception_and_carries_a_complete_result() -> None:
    result = evaluate_setup(base_inputs(context_regime_structure=StructureState.RANGING))
    assert result.state is SetupState.WAIT
    assert result.probability.value is None
    assert result.regime_context
    assert result.limitations


# ==================== 2. Candidate formation — never one indicator ============


def test_minimum_agreeing_families_is_two() -> None:
    assert MINIMUM_AGREEING_FAMILIES == 2


def test_two_agreeing_families_with_the_third_unavailable_forms_a_candidate() -> None:
    inputs = base_inputs(evidence_state=OverallState.INSUFFICIENT_DATA, evidence_dominant_alignment=None)
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state in (SetupState.CANDIDATE, SetupState.CONFIRMED)


def test_three_agreeing_families_form_a_candidate() -> None:
    result = evaluate_setup(base_inputs())
    assert result.direction is Direction.LONG


# ======================= 3. Confirmation — execution only =====================


def test_context_and_setup_supportive_execution_unconfirmed_stays_candidate() -> None:
    """The brief's own disagreement case: never silently promoted."""
    inputs = base_inputs(
        execution_breaks=_breaks((LevelSide.LOWER, 90.0, 5)),  # wrong side
    )
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CANDIDATE


def test_no_execution_break_at_all_stays_candidate() -> None:
    inputs = base_inputs(execution_breaks=())
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CANDIDATE
    assert result.trigger.level is not None  # nearest UPPER level is still named


def test_execution_trend_opposing_blocks_confirmation_even_with_a_matching_break() -> None:
    inputs = base_inputs(
        execution_structural_trend=StructuralTrendType.SUSTAINED_LOWER,
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5)),
    )
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CANDIDATE


def test_matching_break_and_non_opposing_execution_trend_confirms() -> None:
    result = evaluate_setup(base_inputs())
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CONFIRMED
    assert result.trigger.bar_index == 5


def test_a_same_bar_dual_break_confirms_long_from_the_upper_side() -> None:
    """Regression: `structure.breaks` can hold an upper and a lower break on one
    bar, and the array's positional 'latest' always resolves to the lower one.
    A LONG candidate must still see the matching UPPER break on that bar."""
    inputs = base_inputs(
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5), (LevelSide.LOWER, 95.0, 5)),
    )
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CONFIRMED
    assert result.trigger.level.side is LevelSide.UPPER


def test_a_same_bar_dual_break_confirms_short_from_the_lower_side() -> None:
    """The mirror of the case above — SHORT must not be favoured either."""
    long_inputs = base_inputs(
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5), (LevelSide.LOWER, 95.0, 5)),
    )
    inputs = mirror(long_inputs)
    result = evaluate_setup(inputs)
    assert result.direction is Direction.SHORT
    assert result.state is SetupState.CONFIRMED
    assert result.trigger.level.side is LevelSide.LOWER


def test_a_stale_break_beyond_the_lookback_window_does_not_confirm() -> None:
    inputs = base_inputs(
        execution_closed_count=100,
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5)),  # 94 bars old
    )
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CANDIDATE
    assert any("bar(s) old" in line for line in result.confirmation)


def test_the_most_recent_matching_break_is_used_not_the_earliest() -> None:
    """Two UPPER breaks exist; only the recent one should determine confirmation.

    Regression for the class of bug the independent review found: searching
    `execution_breaks` forward (earliest-first) instead of backward would pick
    the stale bar-2 break here and wrongly report CANDIDATE with a staleness
    note, even though the bar-15 break is well within the lookback window.
    """
    inputs = base_inputs(
        execution_closed_count=20,
        execution_breaks=_breaks(
            (LevelSide.UPPER, 105.0, 2),   # 17 bars old — would be stale
            (LevelSide.UPPER, 106.0, 15),  # 4 bars old — confirms
        ),
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.CONFIRMED
    assert result.trigger.bar_index == 15


def test_a_break_exactly_at_the_lookback_edge_still_confirms() -> None:
    inputs = base_inputs(
        execution_closed_count=CONFIRMATION_LOOKBACK_BARS + 6,
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5)),  # exactly 10 bars old
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.CONFIRMED


def test_one_bar_past_the_lookback_edge_does_not_confirm() -> None:
    inputs = base_inputs(
        execution_closed_count=CONFIRMATION_LOOKBACK_BARS + 7,
        execution_breaks=_breaks((LevelSide.UPPER, 105.0, 5)),  # 11 bars old
    )
    result = evaluate_setup(inputs)
    assert result.state is SetupState.CANDIDATE


def test_missing_execution_close_prevents_confirmation_and_stop_target() -> None:
    inputs = base_inputs(execution_close=None)
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.state is SetupState.CANDIDATE
    assert result.stop is None
    assert result.targets == ()
    assert result.risk_reward is None
    assert result.reference_price is None


# ============================ 4. Stop / target / R:R ==========================


def test_confirmed_long_has_correct_stop_target_and_positive_rr() -> None:
    result = evaluate_setup(base_inputs())
    assert result.state is SetupState.CONFIRMED
    assert result.stop.side is LevelSide.LOWER
    assert result.stop.price == 90.0
    assert result.targets[0].side is LevelSide.UPPER
    assert result.targets[0].price == 130.0
    assert result.risk_reward.risk == 10.0
    assert result.risk_reward.reward == 30.0
    assert result.risk_reward.ratio == 3.0


def test_no_qualifying_stop_level_leaves_stop_and_rr_unavailable() -> None:
    inputs = base_inputs(execution_levels=(_level(LevelSide.UPPER, 110.0),))  # no LOWER level
    result = evaluate_setup(inputs)
    assert result.stop is None
    assert result.risk_reward is None


def test_no_qualifying_target_level_leaves_target_and_rr_unavailable() -> None:
    inputs = base_inputs(setup_levels=(_level(LevelSide.LOWER, 70.0),))  # no UPPER level
    result = evaluate_setup(inputs)
    assert result.targets == ()
    assert result.risk_reward is None
    assert result.stop is not None  # the other side is still reported


def test_stop_and_target_are_never_fabricated_when_the_window_has_neither() -> None:
    inputs = base_inputs(execution_levels=(), setup_levels=())
    result = evaluate_setup(inputs)
    assert result.stop is None
    assert result.targets == ()
    assert result.risk_reward is None
    assert result.direction is not None  # a thesis can still exist without a level


def test_nearest_level_is_chosen_over_a_farther_one_on_the_correct_side() -> None:
    inputs = base_inputs(
        execution_levels=(
            _level(LevelSide.LOWER, 95.0, index=1),
            _level(LevelSide.LOWER, 80.0, index=2),
        ),
    )
    result = evaluate_setup(inputs)
    assert result.stop.price == 95.0  # nearest to close=100, not the farther 80


def test_a_level_exactly_at_close_is_never_selected() -> None:
    """Strict inequality is load-bearing: it is what guarantees positive risk."""
    inputs = base_inputs(
        execution_levels=(_level(LevelSide.LOWER, 100.0), _level(LevelSide.LOWER, 90.0)),
    )
    result = evaluate_setup(inputs)
    assert result.stop.price == 90.0


# ============================== 5. LONG/SHORT symmetry =========================


def test_long_and_short_are_structural_mirrors() -> None:
    long_inputs = base_inputs()
    short_inputs = mirror(long_inputs)

    long_result = evaluate_setup(long_inputs)
    short_result = evaluate_setup(short_inputs)

    assert long_result.state is SetupState.CONFIRMED
    assert short_result.state is SetupState.CONFIRMED
    assert long_result.direction is Direction.LONG
    assert short_result.direction is Direction.SHORT

    assert long_result.stop.side is LevelSide.LOWER
    assert short_result.stop.side is LevelSide.UPPER
    assert long_result.targets[0].side is LevelSide.UPPER
    assert short_result.targets[0].side is LevelSide.LOWER

    assert long_result.risk_reward.risk == short_result.risk_reward.risk
    assert long_result.risk_reward.reward == short_result.risk_reward.reward
    assert long_result.risk_reward.ratio == short_result.risk_reward.ratio


def test_long_and_short_waits_mirror_too() -> None:
    long_inputs = base_inputs(context_regime_structure=StructureState.RANGING)
    short_inputs = mirror(long_inputs)
    long_result = evaluate_setup(long_inputs)
    short_result = evaluate_setup(short_inputs)
    assert long_result.state is short_result.state is SetupState.WAIT
    assert long_result.direction is short_result.direction is None


def test_long_and_short_candidates_mirror_when_execution_is_unconfirmed() -> None:
    long_inputs = base_inputs(execution_breaks=())
    short_inputs = mirror(long_inputs)
    long_result = evaluate_setup(long_inputs)
    short_result = evaluate_setup(short_inputs)
    assert long_result.state is short_result.state is SetupState.CANDIDATE
    assert long_result.direction is Direction.LONG
    assert short_result.direction is Direction.SHORT


# ================================ 6. Determinism ================================


def test_evaluate_setup_is_pure_and_deterministic() -> None:
    inputs = base_inputs()
    first = evaluate_setup(inputs)
    second = evaluate_setup(inputs)
    assert first == second


def test_policy_id_is_stamped_on_every_result() -> None:
    assert evaluate_setup(base_inputs()).policy_id == SETUP_POLICY_ID
    assert evaluate_setup(
        base_inputs(context_regime_structure=StructureState.RANGING)
    ).policy_id == SETUP_POLICY_ID


# ============================ 7. LIMITED sufficiency ============================


def test_limited_decision_context_does_not_block_a_candidate() -> None:
    inputs = base_inputs(
        decision_context_state=ContextState.LIMITED,
        decision_context_statements=("warm-up incomplete on one view",),
    )
    result = evaluate_setup(inputs)
    assert result.direction is Direction.LONG
    assert result.sufficiency is ContextState.LIMITED
    assert any("LIMITED" in line for line in result.limitations)


# ============================ 8. Type checking ===================================


def test_evaluate_setup_rejects_a_non_setup_inputs_argument() -> None:
    with pytest.raises(TypeError):
        evaluate_setup(object())  # type: ignore[arg-type]


def test_evidence_lean_abstains_on_watch_with_a_non_directional_alignment() -> None:
    """A defensive branch: `_state()` never actually produces this combination
    today, but the family reader must not invent a direction if it ever did."""
    from fmis.swing_setup.policy import _evidence_lean

    assert _evidence_lean(OverallState.WATCH, Alignment.NEUTRAL) is Lean.UNAVAILABLE
    assert _evidence_lean(OverallState.WATCH, None) is Lean.UNAVAILABLE
