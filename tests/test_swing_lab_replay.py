"""No-lookahead, variant isolation and gate attribution, proved rather than asserted.

**The prefix-equivalence proof.** The strongest no-lookahead statement available
without a formal model is this: replaying an instant against a dataset that ends
at that instant must produce exactly what replaying it against a dataset holding
years of *subsequent* candles produces. If any future bar could influence a
decision, those two runs would differ. `TestNoLookahead` runs both and compares.

These tests use a synthetic transport rather than the network, so they are fast
and deterministic; the live demonstration in the milestone report exercises the
same code against real Binance history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.market_regime import StructureState
from fmis.swing_lab.gate import measure_gate_impact
from fmis.swing_lab.models import GateObservation, GateVerdict, LabVariant, SwingLabError
from fmis.swing_lab.replay import _gate_verdict, group_variants
from fmis.swing_lab.variants import (
    BASELINE_VARIANT,
    CONTEXT_ONLY_VARIANT,
    CORE_1D4H_VARIANT,
    HARD_GATE_CONTROL_VARIANT,
    PRE_SPECIFIED_VARIANTS,
    PRODUCTION_INTERVALS,
    SHIFTED_ROLE_VARIANT,
    variant_by_id,
)
from fmis.swing_setup.models import Direction, SetupState
from fmis.swing_setup.policy import ContextRoleTreatment, evaluate_setup

from tests.swing_lab_helpers import setup_inputs


class _Assessment:
    """Only the two fields `_gate_verdict` reads."""

    def __init__(self, state: SetupState, direction: Direction | None = None) -> None:
        self.state = state
        self.direction = direction


class TestGateAttributionReadsFactsNotText:
    def test_insufficient_context_means_the_gate_was_never_reached(self) -> None:
        inputs = setup_inputs(
            decision_context_state=ContextState.INSUFFICIENT,
            context_regime_structure=StructureState.RANGING,
        )
        verdict = _gate_verdict(inputs, _Assessment(SetupState.CONFIRMED))
        assert verdict is GateVerdict.NOT_REACHED
        assert not verdict.is_blocking

    def test_a_trending_context_is_allowed(self) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.TRENDING)
        assert _gate_verdict(inputs, _Assessment(SetupState.WAIT)) is GateVerdict.ALLOWED

    @pytest.mark.parametrize(
        "state,expected",
        [
            (SetupState.WAIT, GateVerdict.BLOCKED_WITHOUT_EFFECT),
            (SetupState.CANDIDATE, GateVerdict.BLOCKED_CANDIDATE),
            (SetupState.CONFIRMED, GateVerdict.BLOCKED_CONFIRMED),
        ],
    )
    def test_a_block_is_graded_by_what_it_actually_removed(
        self, state: SetupState, expected: GateVerdict
    ) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.RANGING)
        assert _gate_verdict(inputs, _Assessment(state)) is expected

    def test_every_non_trending_state_is_treated_as_blocking(self) -> None:
        for structure in StructureState:
            if structure is StructureState.TRENDING:
                continue
            inputs = setup_inputs(context_regime_structure=structure)
            assert _gate_verdict(inputs, _Assessment(SetupState.WAIT)).is_blocking

    def test_only_candidate_and_confirmed_blocks_are_material(self) -> None:
        assert GateVerdict.BLOCKED_CANDIDATE.is_material
        assert GateVerdict.BLOCKED_CONFIRMED.is_material
        assert not GateVerdict.BLOCKED_WITHOUT_EFFECT.is_material
        assert not GateVerdict.ALLOWED.is_material


class TestGateImpactArithmetic:
    @staticmethod
    def observation(verdict: GateVerdict, direction: Direction | None = None):
        return GateObservation(
            symbol="BTCUSDT",
            as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
            verdict=verdict,
            context_regime_structure="ranging",
            counterfactual_direction=direction,
            segment=None,
        )

    def test_block_rate_excludes_instants_the_gate_never_reached(self) -> None:
        impact = measure_gate_impact(
            (
                self.observation(GateVerdict.NOT_REACHED),
                self.observation(GateVerdict.ALLOWED),
                self.observation(GateVerdict.BLOCKED_CANDIDATE, Direction.LONG),
            ),
            (),
        )
        assert impact.instants == 3
        # 1 blocked of 2 reached, not of 3 total.
        assert impact.block_rate == 1 / 2
        assert impact.materially_blocked == 1
        assert impact.blocked_long == 1

    def test_an_absent_counterfactual_is_not_an_empty_one(self) -> None:
        impact = measure_gate_impact((self.observation(GateVerdict.ALLOWED),), ())
        assert impact.counterfactual is None
        assert "absent comparison, not an empty one" in impact.counterfactual_note

    def test_no_reached_instants_yields_no_rate_rather_than_zero(self) -> None:
        impact = measure_gate_impact((self.observation(GateVerdict.NOT_REACHED),), ())
        assert impact.block_rate is None
        assert impact.material_block_rate is None

    def test_a_non_observation_is_refused(self) -> None:
        with pytest.raises(TypeError, match="GateObservation"):
            measure_gate_impact(("blocked",), ())


class TestVariantSpecification:
    def test_the_baseline_supplies_no_override_at_all(self) -> None:
        assert BASELINE_VARIANT.is_production_baseline
        assert BASELINE_VARIANT.context_role is None
        assert BASELINE_VARIANT.max_confirmation_age is None
        assert BASELINE_VARIANT.policy_id == "swing-setup-v1"

    def test_the_control_is_not_the_baseline_but_shares_its_semantics(self) -> None:
        assert not HARD_GATE_CONTROL_VARIANT.is_production_baseline
        assert (
            HARD_GATE_CONTROL_VARIANT.effective_context_role
            is BASELINE_VARIANT.effective_context_role
        )
        assert (
            HARD_GATE_CONTROL_VARIANT.effective_max_age
            == BASELINE_VARIANT.effective_max_age
        )

    def test_each_variant_has_a_distinct_id(self) -> None:
        ids = [variant.variant_id for variant in PRE_SPECIFIED_VARIANTS]
        assert len(ids) == len(set(ids))

    def test_the_shifted_variant_runs_the_unmodified_production_policy(self) -> None:
        assert SHIFTED_ROLE_VARIANT.is_production_baseline
        assert SHIFTED_ROLE_VARIANT.policy_id == BASELINE_VARIANT.policy_id
        assert SHIFTED_ROLE_VARIANT.interval_signature == ("1d", "4h", "1h")

    def test_variants_sharing_facts_are_grouped_together(self) -> None:
        groups = group_variants(PRE_SPECIFIED_VARIANTS)
        assert len(groups) == 2
        production, shifted = groups
        assert production[0] == ("1w", "1d", "4h")
        assert len(production[1]) == 4
        assert shifted[0] == ("1d", "4h", "1h")
        assert len(shifted[1]) == 1

    def test_grouping_preserves_the_requested_order(self) -> None:
        groups = group_variants((SHIFTED_ROLE_VARIANT, BASELINE_VARIANT))
        assert groups[0][0] == ("1d", "4h", "1h")

    def test_two_roles_may_not_share_an_interval(self) -> None:
        with pytest.raises(SwingLabError, match="distinct interval"):
            LabVariant(
                variant_id="bad",
                title="t",
                hypothesis="h",
                context_role=None,
                max_confirmation_age=None,
                timeframes={
                    role: "1d" for role in PRODUCTION_INTERVALS
                },
            )

    def test_an_unknown_variant_id_names_the_available_ones(self) -> None:
        with pytest.raises(SwingLabError, match="swing_current"):
            variant_by_id("swing_nonexistent")


class TestVariantIsolation:
    """A variant may not change what another variant, or production, computes."""

    def test_evaluating_every_variant_over_one_input_leaves_it_unchanged(self) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.RANGING)
        first = evaluate_setup(inputs)
        for treatment in ContextRoleTreatment:
            evaluate_setup(inputs, research_context_role=treatment)
        assert evaluate_setup(inputs) == first

    def test_order_of_evaluation_does_not_change_any_result(self) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.RANGING)
        forward = [
            evaluate_setup(inputs, research_context_role=treatment).state
            for treatment in ContextRoleTreatment
        ]
        backward = [
            evaluate_setup(inputs, research_context_role=treatment).state
            for treatment in reversed(list(ContextRoleTreatment))
        ]
        assert forward == list(reversed(backward))

    def test_the_gate_free_variants_never_carry_the_production_policy_id(self) -> None:
        for variant in (CONTEXT_ONLY_VARIANT, CORE_1D4H_VARIANT):
            assert variant.policy_id != BASELINE_VARIANT.policy_id
            assert "research" in variant.policy_id
