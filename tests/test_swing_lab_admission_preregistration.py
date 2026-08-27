"""Milestone CA's seal: the digest, and what must change it.

A pre-registration is only worth the guarantee that it cannot be edited quietly.
These tests assert that guarantee two ways: the pinned digest is recomputed from
the content, and a long list of deliberate mutations is each shown to CHANGE the
digest. A seal that survived a moved threshold would seal nothing.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fmis.swing_lab.admission import FORWARD_HORIZONS
from fmis.swing_lab.admission_preregistration import (
    CA_EDGE_CRITERIA,
    CA_MECHANISM_CRITERIA,
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
    MIN_HORIZON_AGREEMENT,
    NULL_PERCENTILE_BAR,
    PRIMARY_HORIZON,
    CaDirectionRule,
    CaControlSource,
    CaNullFamily,
    CaVerdict,
    ca_preregistration_digest,
    is_ca_pre_registered,
    verify_ca_preregistration,
)
from fmis.swing_lab.metrics import SAMPLE_FLOOR
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.preregistration import SAMPLES, VALIDATION_COST_SCENARIOS


class TestTheSeal:
    def test_the_pinned_digest_is_the_content(self) -> None:
        assert ca_preregistration_digest() == CA_PREREGISTRATION_DIGEST

    def test_verify_accepts_only_that_digest(self) -> None:
        assert verify_ca_preregistration(CA_PREREGISTRATION_DIGEST)
        assert not verify_ca_preregistration("0" * 64)

    def test_verify_refuses_a_non_string(self) -> None:
        with pytest.raises(TypeError):
            verify_ca_preregistration(None)  # type: ignore[arg-type]

    def test_the_digest_refuses_a_foreign_type(self) -> None:
        with pytest.raises(TypeError):
            ca_preregistration_digest(object())  # type: ignore[arg-type]

    def test_the_digest_is_stable_across_repeated_calls(self) -> None:
        assert ca_preregistration_digest() == ca_preregistration_digest()

    def test_the_payload_is_json_safe(self) -> None:
        import json

        json.dumps(CA_PRE_REGISTRATION.payload())


class TestTheSamplesAreMilestoneBys:
    def test_samples_are_imported_by_identity_not_copied(self) -> None:
        """A copy could drift; identity cannot. Milestone BZ's own assertion."""
        assert CA_PRE_REGISTRATION.samples is SAMPLES

    def test_cost_scenarios_are_imported_by_identity(self) -> None:
        assert CA_PRE_REGISTRATION.cost_scenarios is VALIDATION_COST_SCENARIOS

    def test_the_three_samples_are_named_and_distinct(self) -> None:
        names = [item.name for item in CA_PRE_REGISTRATION.samples]
        assert names == ["development", "validation", "holdout"]


class TestTheFamilies:
    def test_every_family_states_a_prediction_and_a_refutation(self) -> None:
        for family in CA_NULL_FAMILIES:
            assert "PREDICTION:" in family.hypothesis
            assert "REFUTED BY:" in family.hypothesis

    def test_a_family_without_a_refutation_cannot_be_constructed(self) -> None:
        with pytest.raises(SwingLabError, match="cannot fail"):
            CaNullFamily(
                family_id="ca_null_unfalsifiable",
                question=CA_NULL_FAMILIES[0].question,
                control_source=CaControlSource.MATCHED_ANY_STAGE,
                direction_rule=CaDirectionRule.FMITS,
                hypothesis="PREDICTION: it works.",
            )

    def test_a_family_without_a_prediction_cannot_be_constructed(self) -> None:
        with pytest.raises(SwingLabError, match="states no PREDICTION"):
            CaNullFamily(
                family_id="ca_null_unpredictive",
                question=CA_NULL_FAMILIES[0].question,
                control_source=CaControlSource.MATCHED_ANY_STAGE,
                direction_rule=CaDirectionRule.FMITS,
                hypothesis="REFUTED BY: nothing.",
            )

    def test_a_same_bar_family_cannot_take_the_controls_own_direction(self) -> None:
        """That control IS the admission, so it would compare a thing to itself."""
        with pytest.raises(SwingLabError, match="the admission itself"):
            CaNullFamily(
                family_id="ca_null_nonsense",
                question=CA_NULL_FAMILIES[0].question,
                control_source=CaControlSource.SAME_BAR,
                direction_rule=CaDirectionRule.CONTROL_OWN,
                hypothesis="PREDICTION: x. REFUTED BY: y.",
            )

    def test_family_ids_are_unique(self) -> None:
        ids = [item.family_id for item in CA_NULL_FAMILIES]
        assert len(ids) == len(set(ids))

    def test_all_four_brief_questions_are_covered(self) -> None:
        questions = {item.question.value for item in CA_NULL_FAMILIES}
        assert questions == {"timing", "direction", "combined", "gate"}

    def test_only_the_opposite_direction_family_declares_degeneracy(self) -> None:
        degenerate = [
            item.family_id for item in CA_NULL_FAMILIES if item.is_degenerate_at_primary
        ]
        assert degenerate == ["ca_null_opposite_direction"]

    def test_membership_is_the_promotion_gate(self) -> None:
        assert is_ca_pre_registered("ca_null_matched_timing")
        assert not is_ca_pre_registered("ca_null_invented_after_results")

    def test_membership_refuses_a_non_string(self) -> None:
        with pytest.raises(TypeError):
            is_ca_pre_registered(None)  # type: ignore[arg-type]

    def test_the_eligible_but_rejected_family_uses_productions_own_vocabulary(
        self,
    ) -> None:
        """NULL 3 must be `SetupState.CANDIDATE`, never an invented 'almost setup'."""
        family = next(
            item
            for item in CA_NULL_FAMILIES
            if item.family_id == "ca_null_eligible_but_rejected"
        )
        assert family.control_source is CaControlSource.MATCHED_UNCONFIRMED
        assert family.direction_rule is CaDirectionRule.CONTROL_OWN

    def test_which_families_need_a_drawn_instant(self) -> None:
        drawing = {
            item.family_id for item in CA_NULL_FAMILIES if item.draws_a_control_instant
        }
        assert drawing == {
            "ca_null_matched_timing",
            "ca_null_matched_timing_random_direction",
            "ca_null_eligible_but_rejected",
        }

    def test_which_families_need_a_coin(self) -> None:
        flipping = {
            item.family_id for item in CA_NULL_FAMILIES if item.draws_a_direction
        }
        assert flipping == {
            "ca_null_random_direction_same_bar",
            "ca_null_matched_timing_random_direction",
        }


class TestTheOutcome:
    def test_the_primary_horizon_obeys_its_own_stated_rule(self) -> None:
        """The rule is 'shortest declared horizon strictly greater than 19'."""
        resolved = min(item for item in FORWARD_HORIZONS if item > 19)
        assert PRIMARY_HORIZON == resolved

    def test_every_horizon_is_within_the_inherited_evaluation_window(self) -> None:
        from fmis.swing_lab.persistence import CHECKPOINT_BARS

        assert max(FORWARD_HORIZONS) == max(CHECKPOINT_BARS) == 60

    def test_the_horizons_are_a_subset_of_milestone_bzs_checkpoints(self) -> None:
        from fmis.swing_lab.persistence import CHECKPOINT_BARS

        assert set(FORWARD_HORIZONS) <= set(CHECKPOINT_BARS)

    def test_the_edge_bar_is_at_least_the_round_trip_cost(self) -> None:
        """0.10 ATR against a 10bps round trip at the primary universe's median
        ATR/close of 0.0202, which is 0.099 ATR. The bar may never be below it."""
        assert MIN_ADMISSION_EDGE_ATR >= 0.002 / 0.0202 - 1e-9


class TestTheVerdicts:
    def test_no_verdict_approves_trading(self) -> None:
        for verdict in CaVerdict:
            assert verdict.is_approved_for_trading is False

    def test_no_verdict_earns_a_forward_test_not_even_the_candidate(self) -> None:
        """CA measures admission with no geometry; there is no policy to run."""
        for verdict in CaVerdict:
            assert verdict.earns_forward_test is False

    def test_the_mechanism_criteria_are_a_subset_of_the_edge_criteria(self) -> None:
        names = {item.name for item in CA_EDGE_CRITERIA}
        assert set(CA_MECHANISM_CRITERIA) <= names

    def test_the_mechanism_criteria_exclude_every_generalisation_test(self) -> None:
        """MECHANISM_EVIDENCE asks about development only, by construction."""
        for name in ("validation_sign", "holdout_sign", "economically_meaningful"):
            assert name not in CA_MECHANISM_CRITERIA

    def test_every_criterion_names_itself_once(self) -> None:
        names = [item.name for item in CA_EDGE_CRITERIA]
        assert len(names) == len(set(names))

    def test_a_criterion_needs_a_name_and_a_requirement(self) -> None:
        from fmis.swing_lab.admission_preregistration import CriterionSpec

        with pytest.raises(SwingLabError):
            CriterionSpec("", "something", None)
        with pytest.raises(SwingLabError):
            CriterionSpec("named", "   ", None)


class TestTheDeclaredStrata:
    def test_the_conditional_edge_rule_forbids_a_stratum_candidate(self) -> None:
        joined = " ".join(CA_PRE_REGISTRATION.classification_rules)
        assert "CONDITIONAL EDGE" in joined
        assert "may never reach ADMISSION_EDGE_CANDIDATE" in joined

    def test_walk_forward_is_declared_per_universe_never_pooled(self) -> None:
        stratum = next(
            item for item in CA_PRE_REGISTRATION.declared_strata
            if item["name"] == "walk_forward"
        )
        assert "never pooled" in stratum["cuts"][0]

    def test_every_declared_stratum_states_why(self) -> None:
        for stratum in CA_PRE_REGISTRATION.declared_strata:
            assert stratum["why"].strip()


class TestTheLimitationsAreHonest:
    def test_the_outcome_is_declared_not_to_be_a_trade(self) -> None:
        joined = " ".join(CA_PRE_REGISTRATION.limitations)
        assert "THE OUTCOME IS NOT A TRADE" in joined

    def test_the_eligible_but_rejected_lookahead_constraint_is_stated(self) -> None:
        joined = " ".join(CA_PRE_REGISTRATION.limitations)
        assert "CLASSIFIED AT DECISION TIME" in joined

    def test_admission_dependence_is_stated_rather_than_assumed_away(self) -> None:
        joined = " ".join(CA_PRE_REGISTRATION.limitations)
        assert "ADMISSIONS ARE NOT INDEPENDENT OF EACH OTHER" in joined


def _digest_of(**changes) -> str:
    return ca_preregistration_digest(replace(CA_PRE_REGISTRATION, **changes))


@pytest.mark.parametrize(
    "name,changes",
    [
        ("the id", {"preregistration_id": "ca-something-else"}),
        ("the primary horizon", {"primary_horizon": 12}),
        ("the horizon set", {"horizons": (1, 3, 6, 12, 24)}),
        ("the horizon rule", {"primary_horizon_rule": "because it looked best"}),
        ("the research question", {"research_question": "does it make money"}),
        ("a family dropped", {"families": CA_NULL_FAMILIES[:-1]}),
        ("the families reordered", {"families": tuple(reversed(CA_NULL_FAMILIES))}),
        ("a criterion dropped", {"edge_criteria": CA_EDGE_CRITERIA[:-1]}),
        (
            "the mechanism criteria widened",
            {"mechanism_criteria": CA_MECHANISM_CRITERIA + ("holdout_sign",)},
        ),
        ("a sample edge moved", {"samples": SAMPLES[:2]}),
        ("a classification rule dropped", {"classification_rules": ()}),
        ("a stratum dropped", {"declared_strata": CA_PRE_REGISTRATION.declared_strata[:1]}),
        ("a limitation dropped", {"limitations": CA_PRE_REGISTRATION.limitations[:-1]}),
        ("a decomposition dropped", {"required_decompositions": ()}),
        ("a metric dropped", {"metrics": ()}),
        ("the deciding cost policy", {"deciding_cost_policy_id": "swing-lab-frictionless"}),
    ],
)
def test_a_mutation_changes_the_digest(name: str, changes) -> None:
    """Each is a change a reader would need to know about. None may be silent."""
    assert _digest_of(**changes) != CA_PREREGISTRATION_DIGEST, name


@pytest.mark.parametrize(
    "field,value",
    [
        ("calendar_radius_tiers", (540,)),
        ("minimum_separation_bars", 30),
        ("atr_log_tolerance", 0.9),
        ("minimum_pool", 5),
        ("excludes_admitted", False),
        ("same_symbol", False),
        ("same_sample", False),
    ],
)
def test_a_matching_mutation_changes_the_digest(field: str, value) -> None:
    """The matching rule IS the null. Every knob on it is sealed."""
    mutated = replace(CA_PRE_REGISTRATION.matching, **{field: value})
    assert _digest_of(matching=mutated) != CA_PREREGISTRATION_DIGEST


@pytest.mark.parametrize(
    "field,value",
    [
        ("master_seeds", (1, 2, 3)),
        ("primary_seed", 2),
        ("draws_per_admission", 50),
        ("null_replicates", 100),
        ("bootstrap_replicates", 500),
        ("seed_derivation", "python's built-in hash"),
    ],
)
def test_a_randomisation_mutation_changes_the_digest(field: str, value) -> None:
    mutated = replace(CA_PRE_REGISTRATION.randomisation, **{field: value})
    assert _digest_of(randomisation=mutated) != CA_PREREGISTRATION_DIGEST


def test_the_primary_seed_must_be_one_of_the_master_seeds() -> None:
    with pytest.raises(SwingLabError, match="primary seed"):
        replace(CA_PRE_REGISTRATION.randomisation, primary_seed=99)


def test_a_family_hypothesis_edit_changes_the_digest() -> None:
    """The sentence a family can be refuted by is part of what was sealed."""
    edited = (
        replace(
            CA_NULL_FAMILIES[0],
            hypothesis=CA_NULL_FAMILIES[0].hypothesis + " PREDICTION: also this.",
        ),
    ) + CA_NULL_FAMILIES[1:]
    assert _digest_of(families=edited) != CA_PREREGISTRATION_DIGEST


def test_a_threshold_moved_in_a_criterion_changes_the_digest() -> None:
    edited = tuple(
        replace(item, threshold=0.0) if item.name == "development_effect" else item
        for item in CA_EDGE_CRITERIA
    )
    assert _digest_of(edge_criteria=edited) != CA_PREREGISTRATION_DIGEST


def test_the_sealed_constants_are_the_ones_the_criteria_quote() -> None:
    """A criterion whose sentence and threshold disagree seals nothing useful."""
    by_name = {item.name: item for item in CA_EDGE_CRITERIA}
    assert by_name["development_effect"].threshold == MIN_ADMISSION_EDGE_ATR
    assert by_name["null_percentile"].threshold == NULL_PERCENTILE_BAR
    assert by_name["horizon_profile"].threshold == float(MIN_HORIZON_AGREEMENT)
    assert by_name["sample"].threshold == float(SAMPLE_FLOOR)


def test_the_preregistration_id_is_carried_in_the_payload() -> None:
    assert CA_PRE_REGISTRATION.payload()["preregistration_id"] == CA_PREREGISTRATION_ID


def test_the_digest_does_not_depend_on_the_hash_seed() -> None:
    """A digest a `PYTHONHASHSEED` could move would not be a seal."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    digests = set()
    for seed in ("0", "1", "12345"):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from fmis.swing_lab.admission_preregistration import "
                "ca_preregistration_digest as d; print(d())",
            ],
            capture_output=True,
            text=True,
            cwd=root,
            env={"PYTHONHASHSEED": seed, "PATH": ""},
        )
        assert result.returncode == 0, result.stderr
        digests.add(result.stdout.strip())
    assert digests == {CA_PREREGISTRATION_DIGEST}
