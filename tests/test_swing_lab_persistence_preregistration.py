"""Milestone BZ's seal. **A tamper-evident seal on a scientific claim.**

The digest is not a checksum for corruption. It works because the seal and the
content live in the same file: a change to either without the other is a red
test, and rewriting the pinned line is a one-line diff any review will see.

The parametrised mutations below are the point of this file. Each one edits
something the pre-registration fixed — a threshold, a criterion, a sample edge,
a neighbourhood point, the deciding cost scenario — and asserts the digest
moves. A seal that did not notice those edits would be decorative.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

from fmis.swing_lab.exits import ExitMechanic, ExitPolicy
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence_preregistration import (
    BZ_CANDIDATE_CRITERIA,
    BZ_CLASSIFICATION_RULES,
    BZ_GEOMETRIES,
    BZ_HYPOTHESES,
    BZ_HYPOTHESIS_IDS,
    BZ_MECHANISM_CRITERIA,
    BZ_PRE_REGISTRATION,
    BZ_PREREGISTRATION_DIGEST,
    BZ_PREREGISTRATION_ID,
    GIVEBACK_NEIGHBOURHOOD,
    MIN_MECHANISM_IMPROVEMENT_R,
    STAGNATION_NEIGHBOURHOOD,
    BzHypothesis,
    BzPreregistration,
    bz_preregistration_digest,
    is_bz_pre_registered,
    verify_bz_preregistration,
)


class TestTheSealHolds:
    def test_the_pinned_digest_matches_the_content(self) -> None:
        assert bz_preregistration_digest() == BZ_PREREGISTRATION_DIGEST

    def test_verification_accepts_the_live_digest_and_rejects_others(self) -> None:
        assert verify_bz_preregistration(BZ_PREREGISTRATION_DIGEST)
        assert not verify_bz_preregistration("0" * 64)

    def test_a_non_string_digest_is_a_type_error(self) -> None:
        with pytest.raises(TypeError, match="digest must be a str"):
            verify_bz_preregistration(None)  # type: ignore[arg-type]

    def test_the_digest_is_stable_across_repeated_computation(self) -> None:
        assert bz_preregistration_digest() == bz_preregistration_digest()

    def test_the_payload_is_json_safe_and_canonical(self) -> None:
        canonical = json.dumps(
            BZ_PRE_REGISTRATION.payload(), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        )
        assert json.loads(canonical)["preregistration_id"] == BZ_PREREGISTRATION_ID

    def test_a_non_preregistration_is_a_type_error(self) -> None:
        with pytest.raises(TypeError, match="must be a BzPreregistration"):
            bz_preregistration_digest(object())  # type: ignore[arg-type]


def _mutated(**overrides) -> BzPreregistration:
    return replace(BZ_PRE_REGISTRATION, **overrides)


class TestTheSealNoticesTampering:
    """Every edit below changes the experiment. The digest must say so."""

    def test_a_dropped_hypothesis_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(hypotheses=BZ_HYPOTHESES[:-1])
        ) != BZ_PREREGISTRATION_DIGEST

    def test_reordering_the_hypotheses_changes_the_digest(self) -> None:
        """Declaration order is part of what was frozen."""
        reordered = (BZ_HYPOTHESES[1], BZ_HYPOTHESES[0]) + BZ_HYPOTHESES[2:]
        assert bz_preregistration_digest(
            _mutated(hypotheses=reordered)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_moving_a_threshold_after_the_freeze_changes_the_digest(self) -> None:
        moved = tuple(
            BzHypothesis(
                hypothesis_id=item.hypothesis_id,
                role=item.role,
                policy=(
                    replace(item.policy, stagnation_bars=13)
                    if item.policy.mechanic is ExitMechanic.STAGNATION
                    else item.policy
                ),
            )
            for item in BZ_HYPOTHESES
        )
        assert bz_preregistration_digest(
            _mutated(hypotheses=moved)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_moving_the_giveback_fraction_changes_the_digest(self) -> None:
        moved = tuple(
            BzHypothesis(
                hypothesis_id=item.hypothesis_id,
                role=item.role,
                policy=(
                    replace(item.policy, giveback_fraction=Decimal("0.4"))
                    if item.policy.giveback_fraction is not None
                    else item.policy
                ),
            )
            for item in BZ_HYPOTHESES
        )
        assert bz_preregistration_digest(
            _mutated(hypotheses=moved)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_dropping_a_failing_neighbour_changes_the_digest(self) -> None:
        thinned = {
            "bz_exit_stagnation_12": {
                "parameter": "stagnation_bars", "points": [12, 18], "declared": 12,
            },
            "bz_exit_giveback_half": dict(
                BZ_PRE_REGISTRATION.robustness["bz_exit_giveback_half"]
            ),
        }
        assert bz_preregistration_digest(
            _mutated(robustness=thinned)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_switching_the_deciding_scenario_changes_the_digest(self) -> None:
        """Promoting on the frictionless column must be visible in the seal."""
        assert bz_preregistration_digest(
            _mutated(deciding_cost_policy_id="swing-lab-frictionless")
        ) != BZ_PREREGISTRATION_DIGEST

    def test_deleting_a_candidate_criterion_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(candidate_criteria=BZ_CANDIDATE_CRITERIA[:-1])
        ) != BZ_PREREGISTRATION_DIGEST

    def test_deleting_a_mechanism_criterion_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(mechanism_criteria=BZ_MECHANISM_CRITERIA[:-1])
        ) != BZ_PREREGISTRATION_DIGEST

    def test_lowering_the_improvement_bar_changes_the_digest(self) -> None:
        lowered = tuple(
            replace(item, threshold=0.0) if item.name == "improves_development" else item
            for item in BZ_MECHANISM_CRITERIA
        )
        assert bz_preregistration_digest(
            _mutated(mechanism_criteria=lowered)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_shifting_a_sample_edge_changes_the_digest(self) -> None:
        from datetime import timedelta

        shifted = tuple(
            replace(spec, signal_end=spec.signal_end + timedelta(days=1))
            if spec.name == "development"
            else spec
            for spec in BZ_PRE_REGISTRATION.samples
        )
        assert bz_preregistration_digest(
            _mutated(samples=shifted)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_changing_a_checkpoint_changes_the_digest(self) -> None:
        observation = dict(BZ_PRE_REGISTRATION.observation)
        observation["checkpoint_bars"] = [1, 2, 3]
        assert bz_preregistration_digest(
            _mutated(observation=observation)
        ) != BZ_PREREGISTRATION_DIGEST

    def test_adding_a_geometry_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(geometry_policy_ids=("geom_production",))
        ) != BZ_PREREGISTRATION_DIGEST

    def test_weakening_the_ambiguity_policy_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(ambiguity_policy=BZ_PRE_REGISTRATION.ambiguity_policy[:2])
        ) != BZ_PREREGISTRATION_DIGEST

    def test_deleting_a_classification_rule_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(classification_rules=BZ_CLASSIFICATION_RULES[:-1])
        ) != BZ_PREREGISTRATION_DIGEST

    def test_removing_a_limitation_changes_the_digest(self) -> None:
        assert bz_preregistration_digest(
            _mutated(limitations=BZ_PRE_REGISTRATION.limitations[:-1])
        ) != BZ_PREREGISTRATION_DIGEST


class TestWhatWasSealed:
    def test_every_family_states_a_prediction_and_a_refutation(self) -> None:
        for hypothesis in BZ_HYPOTHESES:
            if hypothesis.role == "control":
                continue
            assert "PREDICTION:" in hypothesis.policy.hypothesis
            assert "REFUTED BY:" in hypothesis.policy.hypothesis

    def test_a_hypothesis_without_a_refutation_cannot_be_constructed(self) -> None:
        with pytest.raises(SwingLabError, match="no stated refutation|states no"):
            BzHypothesis(
                hypothesis_id="X",
                role="thesis",
                policy=ExitPolicy(
                    policy_id="x", title="t",
                    mechanic=ExitMechanic.THESIS_FAILURE,
                    hypothesis="it will work",
                ),
            )

    def test_the_control_is_declared_and_findable(self) -> None:
        assert BZ_PRE_REGISTRATION.control.hypothesis_id == "BZ-H0"
        assert BZ_PRE_REGISTRATION.control.policy.is_baseline

    def test_exactly_one_combination_is_sealed(self) -> None:
        combinations = [item for item in BZ_HYPOTHESES if item.is_combination]
        assert len(combinations) == 1
        assert combinations[0].hypothesis_id == "BZ-H5"
        assert len(combinations[0].components) == 2

    def test_the_neighbourhood_is_not_pre_registered(self) -> None:
        """**The promotion gate.** No robustness point may ever be promoted."""
        for policy_id in BZ_PRE_REGISTRATION.robustness:
            assert is_bz_pre_registered(policy_id), "the declared point IS sealed"
        # ...but a neighbourhood variant of it is not.
        assert not is_bz_pre_registered("bz_exit_stagnation_8")
        assert not is_bz_pre_registered("bz_exit_stagnation_18")
        assert not is_bz_pre_registered("bz_exit_giveback_0_33")
        assert not is_bz_pre_registered("bz_exit_giveback_0_67")

    def test_the_neighbourhood_straddles_each_declared_point(self) -> None:
        """Neighbours below AND above, so the test can actually fail."""
        assert STAGNATION_NEIGHBOURHOOD == (8, 12, 18)
        assert min(STAGNATION_NEIGHBOURHOOD) < 12 < max(STAGNATION_NEIGHBOURHOOD)
        assert GIVEBACK_NEIGHBOURHOOD == ("0.33", "0.5", "0.67")
        assert Decimal("0.33") < Decimal("0.5") < Decimal("0.67")

    def test_the_two_geometries_are_fixed_and_not_hypotheses(self) -> None:
        ids = {policy.policy_id for policy in BZ_GEOMETRIES}
        assert ids == {"geom_production", "by_stop_0_5atr_target_2r"}
        for policy_id in ids:
            assert not is_bz_pre_registered(policy_id), (
                "a geometry is not a BZ exit hypothesis and cannot be promoted here"
            )

    def test_the_candidate_bar_requires_all_three_samples(self) -> None:
        """BY's bar, unchanged, and not weakened because BZ measures a new lever."""
        names = {item.name for item in BZ_CANDIDATE_CRITERIA}
        assert {
            "development_expectancy", "validation_expectancy", "holdout_expectancy",
        } <= names
        for item in BZ_CANDIDATE_CRITERIA:
            if item.name.endswith("_expectancy"):
                assert item.threshold == 0.0

    def test_mechanism_evidence_can_never_promote(self) -> None:
        """The two verdicts are distinct, and only one of them earns a forward test."""
        rules = "\n".join(BZ_CLASSIFICATION_RULES)
        assert "explicitly NOT approval" in rules
        assert "only verdict that earns shadow or paper testing" in rules

    def test_the_improvement_bar_is_declared_and_material(self) -> None:
        assert MIN_MECHANISM_IMPROVEMENT_R == 0.10

    def test_the_combination_cannot_launder_a_failed_component(self) -> None:
        requirement = next(
            item.requirement
            for item in BZ_CANDIDATE_CRITERIA
            if item.name == "components_earned_it"
        )
        assert "never launder" in requirement

    def test_the_samples_are_bys_own_objects(self) -> None:
        """Imported, never restated, so the two milestones cannot drift apart."""
        from fmis.swing_lab.preregistration import SAMPLES

        assert BZ_PRE_REGISTRATION.samples is SAMPLES

    def test_the_cost_scenarios_are_bys_own(self) -> None:
        from fmis.swing_lab.preregistration import VALIDATION_COST_SCENARIOS

        assert BZ_PRE_REGISTRATION.cost_scenarios is VALIDATION_COST_SCENARIOS
        assert BZ_PRE_REGISTRATION.deciding_cost_policy_id == (
            "swing-lab-conservative-10bps"
        )

    def test_an_unknown_sample_is_named_not_guessed(self) -> None:
        with pytest.raises(SwingLabError, match="no pre-registered sample"):
            BZ_PRE_REGISTRATION.sample("nope")

    def test_an_unknown_hypothesis_is_named_not_guessed(self) -> None:
        with pytest.raises(SwingLabError, match="is NOT pre-registered"):
            BZ_PRE_REGISTRATION.hypothesis_for("bz_exit_invented_later")

    def test_the_descriptive_fields_are_barred_from_rules(self) -> None:
        note = BZ_PRE_REGISTRATION.observation[
            "descriptive_fields_may_never_become_rules"
        ]
        for field in ("peak_r", "bars_to_peak_r", "final_close_r", "total_giveback_r"):
            assert field in note


class TestTheSealDependsOnNoMeasurement:
    def test_the_module_imports_no_bar_no_trade_and_no_capture(self) -> None:
        """A threshold cannot be derived from a measurement, even by accident."""
        import ast
        import pathlib

        source = pathlib.Path(
            "src/fmis/swing_lab/persistence_preregistration.py"
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.update(f"{node.module}.{a.name}" for a in node.names)
        for banned in (
            "PriceBar", "LabTrade", "GeometryCapture", "VariantMetrics",
            "PersistenceTrack", "simulate_trade", "simulate_managed_trade",
        ):
            assert not any(name.endswith(banned) for name in imported), (
                f"the pre-registration imports {banned}"
            )

    def test_the_sample_floor_is_imported_never_restated(self) -> None:
        import re
        import pathlib

        source = pathlib.Path(
            "src/fmis/swing_lab/persistence_preregistration.py"
        ).read_text(encoding="utf-8")
        assert "from fmis.swing_lab.metrics import SAMPLE_FLOOR" in source
        assert not re.search(r"^SAMPLE_FLOOR\s*[:=]", source, re.MULTILINE)
