"""The research override: faithful where it must be, isolated where it must be.

The whole milestone rests on two claims this file turns into measurements:

1. Supplying no override changes **nothing** — the production policy is
   byte-identical to what it was before `research_context_role` existed.
2. Supplying `GATE_AND_VOTE` explicitly reproduces production exactly. If it
   did not, every counterfactual measured through the override would be
   comparing against a baseline that never ran.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fmis.decision_context import ContextState
from fmis.market_regime import ParticipationState, StructureState, VolatilityState
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup.models import SetupState
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    MINIMUM_AGREEING_FAMILIES,
    PRODUCTION_CONTEXT_ROLE_TREATMENT,
    RESEARCH_POLICY_ID_PREFIX,
    SETUP_POLICY_ID,
    ContextRoleTreatment,
    evaluate_setup,
    research_policy_id,
)

from tests.swing_lab_helpers import setup_inputs


class TestProductionIsUnchanged:
    def test_no_override_keeps_the_production_policy_id(self) -> None:
        assessment = evaluate_setup(setup_inputs())
        assert assessment.policy_id == SETUP_POLICY_ID
        assert RESEARCH_POLICY_ID_PREFIX not in assessment.policy_id

    def test_no_override_adds_no_research_limitation(self) -> None:
        assessment = evaluate_setup(setup_inputs())
        assert not any(
            line.startswith("RESEARCH OVERRIDE ACTIVE")
            for line in assessment.limitations
        )

    def test_the_production_default_is_gate_and_vote(self) -> None:
        assert PRODUCTION_CONTEXT_ROLE_TREATMENT is ContextRoleTreatment.GATE_AND_VOTE

    def test_existing_research_ids_are_byte_identical(self) -> None:
        """Milestone BC's ids must not have changed shape when BW extended them."""
        assert research_policy_id(2) == "swing-setup-v1+research(max_confirmation_age=2)"
        assert research_policy_id(0) != research_policy_id(10)


class TestTheControlIsFaithful:
    def test_explicit_gate_and_vote_reproduces_production_state(self) -> None:
        for structure in StructureState:
            inputs = setup_inputs(context_regime_structure=structure)
            production = evaluate_setup(inputs)
            control = evaluate_setup(
                inputs,
                research_confirmation_max_age=CONFIRMATION_LOOKBACK_BARS,
                research_context_role=ContextRoleTreatment.GATE_AND_VOTE,
            )
            assert control.state is production.state, structure
            assert control.direction == production.direction, structure
            assert control.thesis == production.thesis, structure

    def test_the_control_still_marks_itself_as_research(self) -> None:
        control = evaluate_setup(
            setup_inputs(),
            research_confirmation_max_age=CONFIRMATION_LOOKBACK_BARS,
            research_context_role=ContextRoleTreatment.GATE_AND_VOTE,
        )
        assert control.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX)


class TestTheGate:
    def test_a_non_trending_context_waits_under_production(self) -> None:
        assessment = evaluate_setup(
            setup_inputs(context_regime_structure=StructureState.RANGING)
        )
        assert assessment.state is SetupState.WAIT
        assert "not trending" in assessment.thesis[0]

    def test_vote_only_removes_the_gate_but_keeps_the_vote(self) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.RANGING)
        assessment = evaluate_setup(
            inputs, research_context_role=ContextRoleTreatment.VOTE_ONLY
        )
        assert assessment.state is not SetupState.WAIT
        families = {factor.family for factor in assessment.directional_factors}
        assert "context_structural_trend" in families

    def test_ignored_removes_the_gate_and_the_vote(self) -> None:
        inputs = setup_inputs(context_regime_structure=StructureState.RANGING)
        assessment = evaluate_setup(
            inputs, research_context_role=ContextRoleTreatment.IGNORED
        )
        families = {factor.family for factor in assessment.directional_factors}
        assert "context_structural_trend" not in families
        assert len(assessment.directional_factors) == 2

    def test_ignored_does_not_relax_the_agreement_requirement(self) -> None:
        """Two families remain, and MINIMUM_AGREEING_FAMILIES is still 2.

        So under IGNORED both must agree — a stricter unanimity rule than the
        baseline's two-of-three, which is the consequence the variant's own
        hypothesis states rather than tunes away.
        """
        assert MINIMUM_AGREEING_FAMILIES == 2
        # Setup trend leans LONG, evidence is unavailable -> only one vote.
        inputs = setup_inputs(
            context_regime_structure=StructureState.RANGING,
            setup_structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            evidence_state=None,
        )
        assessment = evaluate_setup(
            inputs, research_context_role=ContextRoleTreatment.IGNORED
        )
        assert assessment.state is SetupState.WAIT

    def test_the_gate_is_never_reached_when_context_is_insufficient(self) -> None:
        inputs = setup_inputs(
            decision_context_state=ContextState.INSUFFICIENT,
            context_regime_structure=StructureState.RANGING,
        )
        assessment = evaluate_setup(inputs)
        assert "INSUFFICIENT" in assessment.thesis[0]


class TestIsolation:
    def test_a_context_override_alone_still_stamps_research(self) -> None:
        assessment = evaluate_setup(
            setup_inputs(), research_context_role=ContextRoleTreatment.VOTE_ONLY
        )
        assert assessment.policy_id.startswith(RESEARCH_POLICY_ID_PREFIX)
        assert "context_role=vote_only" in assessment.policy_id

    def test_each_treatment_has_a_distinct_policy_id(self) -> None:
        ids = {
            evaluate_setup(setup_inputs(), research_context_role=treatment).policy_id
            for treatment in ContextRoleTreatment
        }
        assert len(ids) == len(ContextRoleTreatment)

    def test_a_research_assessment_says_so_in_its_limitations(self) -> None:
        assessment = evaluate_setup(
            setup_inputs(), research_context_role=ContextRoleTreatment.IGNORED
        )
        assert any(
            "RESEARCH OVERRIDE ACTIVE" in line and "context role" in line
            for line in assessment.limitations
        )

    def test_a_bad_treatment_is_refused(self) -> None:
        with pytest.raises(TypeError, match="ContextRoleTreatment"):
            evaluate_setup(setup_inputs(), research_context_role="vote_only")

    def test_evaluating_twice_does_not_mutate_the_inputs(self) -> None:
        inputs = setup_inputs()
        before = replace(inputs)
        evaluate_setup(inputs, research_context_role=ContextRoleTreatment.IGNORED)
        evaluate_setup(inputs)
        assert inputs == before
