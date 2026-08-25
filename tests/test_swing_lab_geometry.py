"""Geometry policy: selection, refusal, arithmetic and every hostile case.

Milestone BX. These tests pin the two rules `fmis.swing_lab.geometry` exists to
enforce — **a level is never invented**, and **an admission rule may only
refuse** — and then attack the module with the cases §15 of the brief names.
"""

from __future__ import annotations

import pytest

from fmis.level_crossing import LevelSide
from fmis.swing_lab.geometry import (
    BASIS_POINT,
    GeometryCandidate,
    GeometryPlan,
    GeometryPolicy,
    GeometrySkip,
    LevelRef,
    SkipReason,
    StopRule,
    TargetRule,
    VolatilitySource,
    level_refs,
    plan_geometry,
)
from fmis.swing_lab.geometry_variants import (
    PRE_DECLARED_GEOMETRIES,
    PRODUCTION_GEOMETRY,
    geometry_by_id,
    min_rr_policy,
    min_stop_atr_policy,
    neighbours_of,
    sensitivity_series,
    with_thresholds,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction
from tests.swing_lab_helpers import candidate, ref


# ------------------------------------------------------- production control ---


def test_production_geometry_selects_the_nearest_execution_stop_and_setup_target() -> None:
    plan = plan_geometry(candidate(), PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.stop.price == 98.0
    assert plan.stop.interval == "4h"
    assert plan.target.price == 103.0
    assert plan.target.interval == "1d"


def test_production_geometry_computes_risk_reward_and_ratio_exactly() -> None:
    plan = plan_geometry(candidate(), PRODUCTION_GEOMETRY)
    assert plan.risk == pytest.approx(2.0)
    assert plan.reward == pytest.approx(3.0)
    assert plan.planned_rr == pytest.approx(1.5)
    assert plan.stop_bps == pytest.approx((2.0 / 100.0) / BASIS_POINT)
    assert plan.target_bps == pytest.approx((3.0 / 100.0) / BASIS_POINT)


def test_a_short_measures_risk_and_reward_the_other_way_round() -> None:
    short = candidate(
        direction=Direction.SHORT,
        execution_stop_levels=(ref(102.0, LevelSide.UPPER),),
        setup_stop_levels=(ref(108.0, LevelSide.UPPER, interval="1d"),),
        setup_target_levels=(ref(97.0, LevelSide.LOWER, interval="1d"),),
        context_target_levels=(ref(60.0, LevelSide.LOWER, interval="1w"),),
    )
    plan = plan_geometry(short, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.risk == pytest.approx(2.0)
    assert plan.reward == pytest.approx(3.0)


def test_the_production_control_applies_no_admission_rule() -> None:
    assert PRODUCTION_GEOMETRY.is_production_geometry
    assert PRODUCTION_GEOMETRY.min_planned_rr is None
    assert PRODUCTION_GEOMETRY.min_stop_atr is None


def test_only_the_control_reports_itself_as_production_geometry() -> None:
    others = [p for p in PRE_DECLARED_GEOMETRIES if p is not PRODUCTION_GEOMETRY]
    assert others
    assert not any(policy.is_production_geometry for policy in others)


# ------------------------------------------------- family B: minimum planned R:R ---


def test_min_rr_admits_a_geometry_that_already_pays_the_threshold() -> None:
    plan = plan_geometry(candidate(), min_rr_policy(1.5))
    assert isinstance(plan, GeometryPlan)
    assert plan.planned_rr == pytest.approx(1.5)


def test_min_rr_is_inclusive_at_its_boundary() -> None:
    """1.5R exactly must pass a '>= 1.5' rule. An off-by-one here silently
    deletes every trade sitting on the threshold."""
    assert isinstance(plan_geometry(candidate(), min_rr_policy(1.5)), GeometryPlan)


def test_min_rr_refuses_rather_than_moving_the_target() -> None:
    outcome = plan_geometry(candidate(), min_rr_policy(2.0))
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.BELOW_MINIMUM_PLANNED_RR
    # The target that failed is reported, not replaced.
    assert outcome.observed_planned_rr == pytest.approx(1.5)


def test_a_refusal_never_produces_a_trade_at_a_different_target() -> None:
    """The whole point of family B: no level moves. Under a 2.0R requirement the
    candidate has a REAL level at 112 that would pay 6R, and family B must still
    refuse — choosing it is family E's job, under its own name."""
    outcome = plan_geometry(candidate(), min_rr_policy(2.0))
    assert isinstance(outcome, GeometrySkip)


# ------------------------------------------- family C: volatility-aware stop ---


def test_min_stop_atr_refuses_a_stop_inside_ordinary_noise() -> None:
    tight = candidate(execution_stop_levels=(ref(99.9, LevelSide.LOWER),), execution_atr=1.0)
    outcome = plan_geometry(tight, min_stop_atr_policy(1.0))
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.STOP_INSIDE_VOLATILITY


def test_min_stop_atr_admits_a_stop_exactly_at_the_threshold() -> None:
    exact = candidate(execution_stop_levels=(ref(99.0, LevelSide.LOWER),), execution_atr=1.0)
    assert isinstance(plan_geometry(exact, min_stop_atr_policy(1.0)), GeometryPlan)


def test_a_missing_volatility_measure_is_a_named_refusal_never_a_pass() -> None:
    blind = candidate(execution_atr=None)
    outcome = plan_geometry(blind, min_stop_atr_policy(1.0))
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_VOLATILITY_MEASURE


def test_a_missing_volatility_measure_does_not_block_a_policy_that_never_reads_it() -> None:
    blind = candidate(execution_atr=None)
    plan = plan_geometry(blind, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.stop_atr_multiple is None


def test_the_volatility_source_selects_which_atr_is_read() -> None:
    policy = GeometryPolicy(
        policy_id="probe", title="t", family="Z", hypothesis="h",
        stop_rule=StopRule.NEAREST_EXECUTION, target_rule=TargetRule.NEAREST_SETUP,
        min_stop_atr=1.0, volatility_source=VolatilitySource.SETUP_ATR,
    )
    # setup_atr is 4.0 and the stop is 2.0 away, so a 1.0x SETUP-ATR floor refuses
    # what a 1.0x EXECUTION-ATR floor (1.0) would admit.
    assert isinstance(plan_geometry(candidate(), policy), GeometrySkip)
    assert isinstance(plan_geometry(candidate(), min_stop_atr_policy(1.0)), GeometryPlan)


def test_execution_beyond_volatility_walks_out_to_a_real_further_level() -> None:
    policy = GeometryPolicy(
        policy_id="probe", title="t", family="Z", hypothesis="h",
        stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
        target_rule=TargetRule.NEAREST_SETUP, min_stop_atr=4.0,
    )
    plan = plan_geometry(candidate(), policy)
    assert isinstance(plan, GeometryPlan)
    # 98 is 2.0 away and fails a 4.0x ATR(1.0) floor; 94 is 6.0 away and is a
    # level the engine produced — it was selected, never computed.
    assert plan.stop.price == 94.0


def test_execution_beyond_volatility_refuses_when_no_real_level_is_far_enough() -> None:
    policy = GeometryPolicy(
        policy_id="probe", title="t", family="Z", hypothesis="h",
        stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
        target_rule=TargetRule.NEAREST_SETUP, min_stop_atr=50.0,
    )
    outcome = plan_geometry(candidate(), policy)
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.STOP_INSIDE_VOLATILITY


# ------------------------------------------------- families D and E: selection ---


def test_the_setup_timeframe_stop_selects_the_1d_level() -> None:
    plan = plan_geometry(candidate(), geometry_by_id("geom_setup_stop"))
    assert isinstance(plan, GeometryPlan)
    assert plan.stop.price == 92.0
    assert plan.stop.interval == "1d"


def test_the_second_target_selects_the_second_level_and_never_the_first() -> None:
    plan = plan_geometry(candidate(), geometry_by_id("geom_second_target"))
    assert isinstance(plan, GeometryPlan)
    assert plan.target.price == 112.0


def test_the_second_target_refuses_when_only_one_level_exists() -> None:
    lonely = candidate(setup_target_levels=(ref(103.0, LevelSide.UPPER, interval="1d"),))
    outcome = plan_geometry(lonely, geometry_by_id("geom_second_target"))
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_SECOND_TARGET_LEVEL


def test_the_context_target_selects_the_weekly_objective() -> None:
    plan = plan_geometry(candidate(), geometry_by_id("geom_context_target"))
    assert isinstance(plan, GeometryPlan)
    assert plan.target.price == 140.0
    assert plan.target.interval == "1w"


def test_the_combined_policy_selects_the_first_real_level_that_pays_the_ratio() -> None:
    plan = plan_geometry(candidate(), geometry_by_id("geom_combined_structural"))
    assert isinstance(plan, GeometryPlan)
    # Stop is the 1D level at 92, so risk is 8.0 and 1.5R needs reward >= 12.0.
    # 103 pays 3.0 and fails; 112 pays 12.0 and is a real level — it is selected.
    assert plan.stop.price == 92.0
    assert plan.target.price == 112.0
    assert plan.planned_rr == pytest.approx(1.5)


def test_the_combined_policy_refuses_when_no_real_level_pays_the_ratio() -> None:
    near = candidate(
        setup_target_levels=(
            ref(103.0, LevelSide.UPPER, interval="1d"),
            ref(104.0, LevelSide.UPPER, interval="1d", index=2),
        ),
    )
    outcome = plan_geometry(near, geometry_by_id("geom_combined_structural"))
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.BELOW_MINIMUM_PLANNED_RR


# ----------------------------------------------------------- absent levels ---


def test_no_stop_level_is_a_named_refusal() -> None:
    outcome = plan_geometry(candidate(execution_stop_levels=()), PRODUCTION_GEOMETRY)
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_STOP_LEVEL


def test_no_target_level_is_a_named_refusal() -> None:
    outcome = plan_geometry(candidate(setup_target_levels=()), PRODUCTION_GEOMETRY)
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_TARGET_LEVEL


def test_no_setup_stop_level_is_a_named_refusal() -> None:
    outcome = plan_geometry(
        candidate(setup_stop_levels=()), geometry_by_id("geom_setup_stop")
    )
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_STOP_LEVEL


def test_no_context_level_is_a_named_refusal() -> None:
    outcome = plan_geometry(
        candidate(context_target_levels=()), geometry_by_id("geom_context_target")
    )
    assert isinstance(outcome, GeometrySkip)
    assert outcome.reason is SkipReason.NO_TARGET_LEVEL


def test_every_skip_reason_states_why_in_words() -> None:
    for reason in SkipReason:
        assert reason.statement.strip()


# ------------------------------------------------------------- invariants ---


def test_the_stop_and_target_always_sit_on_opposite_sides_of_the_entry() -> None:
    for policy in PRE_DECLARED_GEOMETRIES:
        for subject in (candidate(), candidate(direction=Direction.SHORT,
                                               execution_stop_levels=(ref(102.0, LevelSide.UPPER),),
                                               setup_stop_levels=(ref(108.0, LevelSide.UPPER, interval="1d"),),
                                               setup_target_levels=(ref(97.0, LevelSide.LOWER, interval="1d"),
                                                                    ref(88.0, LevelSide.LOWER, interval="1d", index=2)),
                                               context_target_levels=(ref(60.0, LevelSide.LOWER, interval="1w"),))):
            outcome = plan_geometry(subject, policy)
            if isinstance(outcome, GeometrySkip):
                continue
            sign = 1 if subject.direction is Direction.LONG else -1
            assert sign * (outcome.stop.price - outcome.entry) < 0
            assert sign * (outcome.target.price - outcome.entry) > 0


def test_a_plan_can_never_carry_a_zero_or_negative_risk() -> None:
    with pytest.raises(SwingLabError, match="risk must be positive"):
        GeometryPlan(
            candidate=candidate(), policy_id="x", entry=100.0,
            stop=ref(100.0, LevelSide.LOWER), target=ref(103.0, LevelSide.UPPER),
            risk=0.0, reward=3.0, planned_rr=1.0, stop_bps=0.0, target_bps=0.0,
            stop_atr_multiple=None, target_atr_multiple=None,
        )


def test_a_plan_can_never_carry_a_zero_or_negative_reward() -> None:
    with pytest.raises(SwingLabError, match="reward must be positive"):
        GeometryPlan(
            candidate=candidate(), policy_id="x", entry=100.0,
            stop=ref(98.0, LevelSide.LOWER), target=ref(100.0, LevelSide.UPPER),
            risk=2.0, reward=0.0, planned_rr=0.0, stop_bps=0.0, target_bps=0.0,
            stop_atr_multiple=None, target_atr_multiple=None,
        )


def test_entry_position_in_range_agrees_with_the_planned_ratio() -> None:
    plan = plan_geometry(candidate(), PRODUCTION_GEOMETRY)
    assert plan.entry_position_in_range == pytest.approx(2.0 / 5.0)


def test_reward_below_risk_is_the_bw_defect_as_a_predicate() -> None:
    close = candidate(setup_target_levels=(ref(101.0, LevelSide.UPPER, interval="1d"),))
    plan = plan_geometry(close, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.reward_below_risk
    assert not plan_geometry(candidate(), PRODUCTION_GEOMETRY).reward_below_risk


def test_planning_is_deterministic() -> None:
    for policy in PRE_DECLARED_GEOMETRIES:
        first = plan_geometry(candidate(), policy)
        second = plan_geometry(candidate(), policy)
        assert type(first) is type(second)
        if isinstance(first, GeometryPlan):
            assert (first.stop.price, first.target.price, first.planned_rr) == (
                second.stop.price, second.target.price, second.planned_rr
            )
        else:
            assert first.reason is second.reason


# ------------------------------------------------------ hostile construction ---


def test_a_candidate_refuses_a_non_positive_reference_price() -> None:
    with pytest.raises(SwingLabError, match="reference_price"):
        candidate(reference_price=0.0)


def test_a_candidate_refuses_a_non_positive_atr() -> None:
    """A zero ATR is a broken measurement, not a calm market; normalising by it
    would divide by zero or silently flip a comparison."""
    with pytest.raises(SwingLabError, match="execution_atr"):
        candidate(execution_atr=0.0)
    with pytest.raises(SwingLabError, match="setup_atr"):
        candidate(setup_atr=-1.0)


def test_a_policy_refuses_a_rule_whose_threshold_is_missing() -> None:
    with pytest.raises(SwingLabError, match="needs min_stop_atr"):
        GeometryPolicy(
            policy_id="x", title="t", family="Z", hypothesis="h",
            stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
            target_rule=TargetRule.NEAREST_SETUP,
        )
    with pytest.raises(SwingLabError, match="needs min_planned_rr"):
        GeometryPolicy(
            policy_id="x", title="t", family="Z", hypothesis="h",
            stop_rule=StopRule.NEAREST_EXECUTION,
            target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
        )


def test_a_policy_refuses_a_non_positive_threshold() -> None:
    with pytest.raises(SwingLabError, match="min_planned_rr"):
        min_rr_policy(0.0)
    with pytest.raises(SwingLabError, match="min_stop_atr"):
        min_stop_atr_policy(-1.0)


def test_plan_geometry_refuses_arguments_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="candidate must be"):
        plan_geometry(object(), PRODUCTION_GEOMETRY)
    with pytest.raises(TypeError, match="policy must be"):
        plan_geometry(candidate(), object())


def test_a_very_long_symbol_and_a_long_error_text_are_carried_intact() -> None:
    long_symbol = "X" * 400
    subject = candidate(symbol=long_symbol, setup_id="s" * 500)
    plan = plan_geometry(subject, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.candidate.symbol == long_symbol


def test_an_extremely_tight_stop_is_planned_and_measured_not_hidden() -> None:
    """BW found a 1.29 basis-point stop. Production geometry must still plan it —
    refusing it here would delete the evidence the diagnosis needs."""
    razor = candidate(execution_stop_levels=(ref(99.9871, LevelSide.LOWER),))
    plan = plan_geometry(razor, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.stop_bps == pytest.approx(1.29, abs=0.01)


def test_an_extremely_wide_stop_is_planned_without_overflow() -> None:
    wide = candidate(execution_stop_levels=(ref(1e-9, LevelSide.LOWER),))
    plan = plan_geometry(wide, PRODUCTION_GEOMETRY)
    assert isinstance(plan, GeometryPlan)
    assert plan.planned_rr < 1.0


def test_level_refs_copies_provenance_without_computing_anything() -> None:
    from tests.swing_lab_helpers import level

    refs = level_refs((level(LevelSide.UPPER, 110.0, index=7),), interval="4h")
    assert refs[0].price == 110.0
    assert refs[0].origin_index == 7
    assert refs[0].provenance == "4h:higher_high@7"


def test_a_level_ref_without_provenance_says_so_rather_than_inventing_one() -> None:
    bare = LevelRef(price=1.0, side=LevelSide.UPPER, interval="4h",
                    origin_index=None, origin_label=None)
    assert bare.provenance == "4h:unattributed@?"


# ------------------------------------------------------- variant discipline ---


def test_every_pre_declared_policy_has_a_distinct_id_and_a_stated_hypothesis() -> None:
    ids = [policy.policy_id for policy in PRE_DECLARED_GEOMETRIES]
    assert len(ids) == len(set(ids))
    for policy in PRE_DECLARED_GEOMETRIES:
        assert len(policy.hypothesis) > 80, policy.policy_id
        assert policy.family[0] in "ABCDEF"


def test_geometry_by_id_names_the_alternatives_when_it_fails() -> None:
    with pytest.raises(SwingLabError, match="geom_production"):
        geometry_by_id("no_such_geometry")


def test_sensitivity_series_covers_its_whole_grid_in_ascending_order() -> None:
    for kind, attr in (("min_rr", "min_planned_rr"), ("min_stop_atr", "min_stop_atr")):
        values = [getattr(policy, attr) for policy in sensitivity_series(kind)]
        assert values == sorted(values)
        assert len(values) == len(set(values))


def test_an_unknown_sensitivity_grid_is_refused_by_name() -> None:
    with pytest.raises(SwingLabError, match="no sensitivity grid"):
        sensitivity_series("min_everything")


def test_neighbours_move_one_threshold_one_step_and_keep_the_family() -> None:
    policy = min_rr_policy(1.5)
    neighbours = neighbours_of(policy)
    assert {n.min_planned_rr for n in neighbours} == {1.25, 1.75}
    assert all(n.family == policy.family for n in neighbours)
    assert all(n.policy_id != policy.policy_id for n in neighbours)


def test_a_policy_with_no_threshold_has_no_neighbours_rather_than_a_free_pass() -> None:
    assert neighbours_of(PRODUCTION_GEOMETRY) == ()
    assert neighbours_of(geometry_by_id("geom_setup_stop")) == ()


def test_a_two_threshold_policy_varies_each_one_separately() -> None:
    neighbours = neighbours_of(geometry_by_id("geom_combined_structural"))
    varied_rr = {n.min_planned_rr for n in neighbours}
    varied_atr = {n.min_stop_atr for n in neighbours}
    # Each neighbour moves exactly one threshold; the other keeps its value.
    assert varied_rr == {1.25, 1.75, 1.5}
    assert varied_atr == {1.0, 0.75, 1.25}
    for neighbour in neighbours:
        moved = (neighbour.min_planned_rr != 1.5) + (neighbour.min_stop_atr != 1.0)
        assert moved == 1


def test_with_thresholds_gives_a_moved_policy_a_new_id() -> None:
    moved = with_thresholds(min_rr_policy(1.5), min_planned_rr=2.0)
    assert moved.policy_id != min_rr_policy(1.5).policy_id
    assert moved.min_planned_rr == 2.0


def test_with_thresholds_refuses_a_non_policy() -> None:
    with pytest.raises(TypeError, match="must be a GeometryPolicy"):
        with_thresholds(object(), min_planned_rr=1.0)


def test_no_pre_declared_policy_can_express_a_computed_target() -> None:
    """The structural guarantee: every TargetRule names a source of REAL levels.
    'place the target at 2R' has no spelling here, and that is deliberate."""
    for rule in TargetRule:
        assert rule.value in {
            "nearest_setup", "second_setup", "nearest_context",
            "first_setup_supporting_rr",
        }


def test_a_geometry_candidate_carries_no_outcome_field() -> None:
    """No lookahead, made unrepresentable rather than merely forbidden."""
    forbidden = {"mfe", "mae", "net_r", "gross_r", "exit", "realized", "outcome", "bars"}
    fields = set(GeometryCandidate.__slots__)
    assert not any(
        any(token in field for token in forbidden) for field in fields
    ), fields


# ---------------------------------------------------- the ordering itself ---
#
# `ordered_levels` is PRODUCTION code (`fmis.swing_setup.policy`) that Milestone
# BX promoted out of `_nearest` so research could select beyond the first level.
# It is tested here because BX is what made it public, and because a mutation
# probe showed the geometry fixtures — which hand-build already-ordered level
# lists — cannot constrain it.


def _levels(*specs):
    from tests.swing_lab_helpers import level

    return tuple(level(side, price, index) for side, price, index in specs)


def test_ordered_levels_returns_nearest_first_above_the_close() -> None:
    from fmis.swing_setup.policy import ordered_levels

    levels = _levels(
        (LevelSide.UPPER, 130.0, 1), (LevelSide.UPPER, 105.0, 2),
        (LevelSide.UPPER, 118.0, 3),
    )
    prices = [item.price for item in ordered_levels(
        levels, side=LevelSide.UPPER, close=100.0, above=True
    )]
    assert prices == [105.0, 118.0, 130.0]


def test_ordered_levels_returns_nearest_first_below_the_close() -> None:
    """Below the close, *nearer* means a HIGHER price. A single sort key read
    backwards, so the two directions cannot drift apart."""
    from fmis.swing_setup.policy import ordered_levels

    levels = _levels(
        (LevelSide.LOWER, 70.0, 1), (LevelSide.LOWER, 95.0, 2),
        (LevelSide.LOWER, 82.0, 3),
    )
    prices = [item.price for item in ordered_levels(
        levels, side=LevelSide.LOWER, close=100.0, above=False
    )]
    assert prices == [95.0, 82.0, 70.0]


def test_ordered_levels_excludes_a_level_at_the_close_exactly() -> None:
    """Strict inequality is load-bearing: it is what guarantees a computed risk
    or reward can never be exactly zero."""
    from fmis.swing_setup.policy import ordered_levels

    levels = _levels((LevelSide.UPPER, 100.0, 1), (LevelSide.UPPER, 110.0, 2))
    result = ordered_levels(levels, side=LevelSide.UPPER, close=100.0, above=True)
    assert [item.price for item in result] == [110.0]

    lower = _levels((LevelSide.LOWER, 100.0, 1), (LevelSide.LOWER, 90.0, 2))
    result = ordered_levels(lower, side=LevelSide.LOWER, close=100.0, above=False)
    assert [item.price for item in result] == [90.0]


def test_ordered_levels_ignores_the_other_side() -> None:
    from fmis.swing_setup.policy import ordered_levels

    levels = _levels((LevelSide.UPPER, 110.0, 1), (LevelSide.LOWER, 90.0, 2))
    result = ordered_levels(levels, side=LevelSide.UPPER, close=100.0, above=True)
    assert [item.price for item in result] == [110.0]


def test_ordered_levels_breaks_price_ties_on_the_origin_index() -> None:
    from fmis.swing_setup.policy import ordered_levels

    levels = _levels(
        (LevelSide.UPPER, 110.0, 5), (LevelSide.UPPER, 110.0, 2),
    )
    above = ordered_levels(levels, side=LevelSide.UPPER, close=100.0, above=True)
    assert [item.origin.index for item in above] == [2, 5]
    lower = _levels((LevelSide.LOWER, 90.0, 5), (LevelSide.LOWER, 90.0, 2))
    below = ordered_levels(lower, side=LevelSide.LOWER, close=100.0, above=False)
    assert [item.origin.index for item in below] == [5, 2]


def test_the_nearest_level_is_exactly_the_first_ordered_one() -> None:
    """The single-owner property: production's choice and a research layer's
    second choice can never disagree about what 'nearer' means."""
    from fmis.swing_setup.policy import _nearest, ordered_levels

    levels = _levels(
        (LevelSide.UPPER, 130.0, 1), (LevelSide.UPPER, 105.0, 2),
        (LevelSide.LOWER, 95.0, 3), (LevelSide.LOWER, 70.0, 4),
    )
    for side, above in ((LevelSide.UPPER, True), (LevelSide.LOWER, False)):
        ordered = ordered_levels(levels, side=side, close=100.0, above=above)
        assert _nearest(levels, side=side, close=100.0, above=above) is ordered[0]


def test_ordered_levels_of_nothing_is_empty_not_an_error() -> None:
    from fmis.swing_setup.policy import _nearest, ordered_levels

    assert ordered_levels((), side=LevelSide.UPPER, close=100.0, above=True) == ()
    assert _nearest((), side=LevelSide.UPPER, close=100.0, above=True) is None


def test_the_volatility_floor_admits_a_level_exactly_at_the_requirement() -> None:
    """A boundary probe: at exactly ``min_stop_atr * atr`` the level qualifies.
    An exclusive comparison here silently discards every stop sitting on the
    threshold."""
    policy = GeometryPolicy(
        policy_id="probe", title="t", family="Z", hypothesis="h",
        stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
        target_rule=TargetRule.NEAREST_SETUP, min_stop_atr=2.0,
    )
    # ATR 1.0 × 2.0 = 2.0 required; the nearest stop at 98 is exactly 2.0 away.
    plan = plan_geometry(candidate(execution_atr=1.0), policy)
    assert isinstance(plan, GeometryPlan)
    assert plan.stop.price == 98.0
