"""Milestone AR — Swing Setup Engine v1: model invariants.

The load-bearing claims: `direction` and `state` cannot disagree, a `WAIT`
result cannot smuggle a stop/target/trigger, a stop or target on the wrong side
for its stated direction cannot be constructed, `risk_reward` cannot exist
without both a stop and a target (and must exist when both are present), and a
calibrated probability cannot coexist with `NOT_CALIBRATED`.
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
    NOT_CALIBRATED,
    Direction,
    DirectionalFactor,
    ExecutionBreakEvent,
    Lean,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupInputs,
    SetupState,
    SwingSetupError,
    Trigger,
    TriggerKind,
)

_AS_OF = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _level(side: LevelSide, price: float, index: int = 1) -> PriceLevel:
    origin = LevelOrigin(
        index=index,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        label=StructuralSwingLabel.HIGHER_HIGH if side is LevelSide.UPPER else StructuralSwingLabel.LOWER_LOW,
        confirmation_bars=2,
    )
    return PriceLevel(side=side, price=price, origin=origin)


def _wait_kwargs(**overrides):
    base = dict(
        symbol="BTCUSDT",
        as_of=_AS_OF,
        objective="swing",
        state=SetupState.WAIT,
        direction=None,
        thesis=("no candidate",),
        directional_factors=(),
        confirmation=(),
        invalidation=(),
        trigger=None,
        reference_price=None,
        stop=None,
        targets=(),
        risk_reward=None,
        probability=NOT_CALIBRATED,
        regime_context=("context: trending",),
        sufficiency=ContextState.SUFFICIENT,
        limitations=("X-1: none",),
        policy_id="swing-setup-v1",
        source="fixture",
    )
    base.update(overrides)
    return base


# ============================ SetupState / Direction / Lean ==================


def test_setup_state_has_exactly_three_members() -> None:
    assert {m.value for m in SetupState} == {"wait", "candidate", "confirmed"}


def test_direction_has_exactly_two_members() -> None:
    assert {m.value for m in Direction} == {"long", "short"}


def test_lean_has_exactly_four_members() -> None:
    assert {m.value for m in Lean} == {"long", "short", "conflicting", "unavailable"}


# ================================ DirectionalFactor ===========================


def test_directional_factor_rejects_blank_fields() -> None:
    with pytest.raises(SwingSetupError):
        DirectionalFactor(family="", lean=Lean.LONG, observed="x", source="y")
    with pytest.raises(SwingSetupError):
        DirectionalFactor(family="f", lean=Lean.LONG, observed="", source="y")
    with pytest.raises(TypeError):
        DirectionalFactor(family="f", lean="long", observed="x", source="y")  # type: ignore[arg-type]


# ===================================== Trigger ================================


def test_awaiting_trigger_may_omit_the_level() -> None:
    trigger = Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="waiting")
    assert trigger.level is None
    assert trigger.bar_index is None


def test_confirmed_trigger_requires_level_and_bar_index() -> None:
    level = _level(LevelSide.UPPER, 100.0)
    with pytest.raises(SwingSetupError):
        Trigger(kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK, statement="confirmed")
    with pytest.raises(SwingSetupError):
        Trigger(
            kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK, statement="confirmed", level=level
        )
    Trigger(
        kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK,
        statement="confirmed",
        level=level,
        bar_index=5,
    )


def test_trigger_rejects_negative_bar_index() -> None:
    with pytest.raises(SwingSetupError):
        Trigger(
            kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK,
            statement="x",
            level=_level(LevelSide.UPPER, 1.0),
            bar_index=-1,
        )


# ==================================== RiskReward ===============================


def test_risk_reward_rejects_zero_or_negative_risk() -> None:
    with pytest.raises(SwingSetupError):
        RiskReward(entry=100.0, stop=100.0, target=110.0, risk=0.0, reward=10.0, ratio=0.0)
    with pytest.raises(SwingSetupError):
        RiskReward(entry=100.0, stop=105.0, target=110.0, risk=-5.0, reward=10.0, ratio=-2.0)


def test_risk_reward_rejects_zero_or_negative_reward() -> None:
    with pytest.raises(SwingSetupError):
        RiskReward(entry=100.0, stop=90.0, target=100.0, risk=10.0, reward=0.0, ratio=0.0)


def test_risk_reward_rejects_non_finite_values() -> None:
    with pytest.raises(SwingSetupError):
        RiskReward(
            entry=float("nan"), stop=90.0, target=110.0, risk=10.0, reward=10.0, ratio=1.0
        )
    with pytest.raises(SwingSetupError):
        RiskReward(
            entry=100.0, stop=90.0, target=110.0, risk=float("inf"), reward=10.0, ratio=1.0
        )


def test_risk_reward_accepts_a_valid_geometry() -> None:
    rr = RiskReward(entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0)
    assert rr.ratio == 3.0


# =================================== Probability ================================


def test_not_calibrated_carries_no_value() -> None:
    assert NOT_CALIBRATED.status is ProbabilityStatus.NOT_CALIBRATED
    assert NOT_CALIBRATED.value is None


def test_a_value_with_not_calibrated_status_is_rejected() -> None:
    with pytest.raises(SwingSetupError):
        Probability(status=ProbabilityStatus.NOT_CALIBRATED, value=0.7)


def test_probability_rejects_a_non_status_type() -> None:
    with pytest.raises(TypeError):
        Probability(status="not_calibrated")  # type: ignore[arg-type]


# ================================ SetupAssessment ==============================


def test_a_wait_result_with_a_direction_is_rejected() -> None:
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(direction=Direction.LONG))


def test_a_candidate_without_a_direction_is_rejected() -> None:
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(state=SetupState.CANDIDATE, direction=None))


def test_a_wait_result_cannot_carry_a_stop_trigger_or_risk_reward() -> None:
    stop = _level(LevelSide.LOWER, 90.0)
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(stop=stop))
    with pytest.raises(SwingSetupError):
        SetupAssessment(
            **_wait_kwargs(
                trigger=Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="x")
            )
        )
    with pytest.raises(SwingSetupError):
        SetupAssessment(
            **_wait_kwargs(targets=(_level(LevelSide.UPPER, 110.0),))
        )


def _candidate_kwargs(direction: Direction, **overrides):
    stop_side = LevelSide.LOWER if direction is Direction.LONG else LevelSide.UPPER
    target_side = LevelSide.UPPER if direction is Direction.LONG else LevelSide.LOWER
    base = _wait_kwargs(
        state=SetupState.CANDIDATE,
        direction=direction,
        thesis=(f"leans {direction.value}",),
        confirmation=("awaiting confirmation",),
        invalidation=("structural invalidation",),
        trigger=Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="awaiting"),
        reference_price=100.0,
        stop=_level(stop_side, 90.0 if direction is Direction.LONG else 110.0),
        targets=(_level(target_side, 130.0 if direction is Direction.LONG else 70.0),),
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_a_stop_on_the_wrong_side_is_rejected(direction: Direction) -> None:
    wrong_side = LevelSide.UPPER if direction is Direction.LONG else LevelSide.LOWER
    kwargs = _candidate_kwargs(direction, stop=_level(wrong_side, 90.0))
    with pytest.raises(SwingSetupError):
        SetupAssessment(**kwargs)


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_a_target_on_the_wrong_side_is_rejected(direction: Direction) -> None:
    wrong_side = LevelSide.LOWER if direction is Direction.LONG else LevelSide.UPPER
    kwargs = _candidate_kwargs(direction, targets=(_level(wrong_side, 130.0),))
    with pytest.raises(SwingSetupError):
        SetupAssessment(**kwargs)


def test_risk_reward_requires_both_stop_and_target() -> None:
    kwargs = _candidate_kwargs(Direction.LONG, targets=())
    kwargs["risk_reward"] = RiskReward(
        entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0
    )
    with pytest.raises(SwingSetupError):
        SetupAssessment(**kwargs)


def test_risk_reward_must_be_present_when_stop_and_target_both_are() -> None:
    kwargs = _candidate_kwargs(Direction.LONG)
    kwargs["risk_reward"] = None
    with pytest.raises(SwingSetupError):
        SetupAssessment(**kwargs)


def test_a_fully_specified_candidate_is_constructible() -> None:
    kwargs = _candidate_kwargs(Direction.LONG)
    kwargs["risk_reward"] = RiskReward(
        entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0
    )
    assessment = SetupAssessment(**kwargs)
    assert assessment.direction is Direction.LONG
    assert assessment.risk_reward.ratio == 3.0


def test_metadata_is_copied_into_a_read_only_mapping() -> None:
    kwargs = _wait_kwargs(metadata={"a": 1})
    assessment = SetupAssessment(**kwargs)
    with pytest.raises(TypeError):
        assessment.metadata["a"] = 2  # type: ignore[index]


def test_schema_version_must_be_an_int() -> None:
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(schema_version=True))


def test_a_confirmed_trigger_level_must_match_confirmation_side() -> None:
    kwargs = _candidate_kwargs(
        Direction.LONG,
        state=SetupState.CONFIRMED,
        trigger=Trigger(
            kind=TriggerKind.CONFIRMED_STRUCTURE_BREAK,
            statement="confirmed",
            level=_level(LevelSide.LOWER, 90.0),
            bar_index=5,
        ),
    )
    with pytest.raises(SwingSetupError):
        SetupAssessment(**kwargs)


# =================================== SetupInputs =================================


def _inputs_kwargs(**overrides):
    base = dict(
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
        execution_levels=(),
        execution_breaks=(),
        setup_levels=(),
        inherited_limitations=(),
    )
    base.update(overrides)
    return base


def test_setup_inputs_rejects_a_negative_or_non_finite_close() -> None:
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(execution_close=-1.0))
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(execution_close=float("nan")))


def test_setup_inputs_rejects_a_break_at_or_beyond_the_closed_count() -> None:
    level = _level(LevelSide.UPPER, 100.0)
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(
            execution_closed_count=10,
            execution_breaks=(ExecutionBreakEvent(level=level, index=10),),
        ))
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(
            execution_closed_count=10,
            execution_breaks=(ExecutionBreakEvent(level=level, index=15),),
        ))
    # In-range is fine.
    SetupInputs(**_inputs_kwargs(
        execution_closed_count=10,
        execution_breaks=(ExecutionBreakEvent(level=level, index=9),),
    ))


def test_setup_inputs_rejects_wrong_enum_types() -> None:
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(context_structural_trend="sustained_higher"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(decision_context_state="sufficient"))


def test_setup_inputs_rejects_every_remaining_wrong_type() -> None:
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(symbol=""))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(as_of="2026-01-01"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(context_regime_structure="trending"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(context_regime_volatility="steady"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(context_regime_participation="typical"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(evidence_state="watch"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(evidence_dominant_alignment="upward"))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(decision_context_statements=["not a tuple"]))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_close=True))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_closed_count=True))
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(execution_closed_count=-1))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_levels=["not a tuple"]))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_levels=(object(),)))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(setup_levels=(object(),)))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_breaks=["not a tuple"]))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(execution_breaks=(object(),)))
    with pytest.raises(TypeError):
        SetupInputs(**_inputs_kwargs(inherited_limitations=["not a tuple"]))


def test_execution_break_event_rejects_wrong_types() -> None:
    with pytest.raises(TypeError):
        ExecutionBreakEvent(level=object(), index=1)
    with pytest.raises(TypeError):
        ExecutionBreakEvent(level=_level(LevelSide.UPPER, 1.0), index=True)
    with pytest.raises(SwingSetupError):
        ExecutionBreakEvent(level=_level(LevelSide.UPPER, 1.0), index=-1)


def test_setup_inputs_rejects_a_non_finite_close() -> None:
    with pytest.raises(SwingSetupError):
        SetupInputs(**_inputs_kwargs(execution_close=float("nan")))


# ================================ Trigger — remaining branches ==================


def test_trigger_rejects_wrong_types() -> None:
    with pytest.raises(TypeError):
        Trigger(kind="awaiting_structure_break", statement="x")  # type: ignore[arg-type]
    with pytest.raises(SwingSetupError):
        Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="")
    with pytest.raises(TypeError):
        Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="x", level=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="x", bar_index="5")  # type: ignore[arg-type]


# ================================ RiskReward — remaining branches ================


def test_risk_reward_rejects_a_non_numeric_field() -> None:
    with pytest.raises(TypeError):
        RiskReward(entry="100", stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RiskReward(entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=True)  # type: ignore[arg-type]


# ================================ SetupAssessment — remaining branches ============


def test_setup_assessment_rejects_every_remaining_wrong_type() -> None:
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(symbol=""))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(as_of="2026-01-01"))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(state="wait"))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(direction="long"))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(thesis=["not a tuple"]))
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(thesis=("",)))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(directional_factors=["not a tuple"]))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(directional_factors=(object(),)))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(trigger=object()))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(reference_price=object()))
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(reference_price=float("nan")))
    with pytest.raises(SwingSetupError):
        SetupAssessment(**_wait_kwargs(reference_price=-1.0))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(stop=object()))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(targets=["not a tuple"]))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(targets=(object(),)))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(risk_reward=object()))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(probability=object()))
    with pytest.raises(TypeError):
        SetupAssessment(**_wait_kwargs(sufficiency="sufficient"))


def test_setup_assessment_reference_price_positive_when_set() -> None:
    kwargs = _candidate_kwargs(Direction.LONG)
    kwargs["risk_reward"] = RiskReward(
        entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0
    )
    assessment = SetupAssessment(**kwargs)
    assert assessment.reference_price == 100.0
