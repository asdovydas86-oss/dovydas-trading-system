"""The seal: stable, complete, and moved by every material field.

Two properties are asserted and they are different. **Determinism** — the digest
is the same across `PYTHONHASHSEED` values and across processes, so a claim to
have measured under a seal is checkable. **Sensitivity** — changing any
scientifically material field moves the digest, so a design cannot be edited
under cover of an unchanged number.

The third property matters most and is the easiest to lose: **no result field can
enter the seal**. `CdPreregistration` has no attribute that could hold a measured
correlation, an interval, a count or a verdict, and the payload's key set is
pinned so adding one is a test failure rather than a silent contamination.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from fmis.paired_dependence.models import PairedDependenceError
from fmis.paired_dependence.preregistration import (
    CD_LIMITATIONS,
    CD_PRE_REGISTRATION,
    CD_PREREGISTRATION_DIGEST,
    CD_PREREGISTRATION_ID,
    CdPreregistration,
    cd_preregistration_digest,
    verify_cd_preregistration,
)
from fmis.swing_lab.admission_preregistration import (
    CA_PREREGISTRATION_DIGEST,
    PRIMARY_HORIZON,
)
from fmis.swing_lab.persistence_preregistration import BZ_PREREGISTRATION_DIGEST
from fmis.universe.preregistration import CC_PREREGISTRATION_DIGEST


class TestTheSeal:
    def test_the_pinned_digest_is_the_one_the_content_produces(self):
        assert cd_preregistration_digest() == CD_PREREGISTRATION_DIGEST

    def test_verify_accepts_the_pinned_digest_and_refuses_another(self):
        assert verify_cd_preregistration(CD_PREREGISTRATION_DIGEST)
        assert not verify_cd_preregistration("0" * 64)

    def test_verify_refuses_a_non_string(self):
        with pytest.raises(TypeError):
            verify_cd_preregistration(None)

    def test_the_digest_function_refuses_a_foreign_object(self):
        with pytest.raises(TypeError):
            cd_preregistration_digest(object())

    @pytest.mark.parametrize("seed", ["0", "1", "42", "1234567"])
    def test_the_digest_is_stable_across_hash_seeds_and_processes(self, seed):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from fmis.paired_dependence.preregistration import "
                "cd_preregistration_digest; print(cd_preregistration_digest())",
            ],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert result.stdout.strip() == CD_PREREGISTRATION_DIGEST

    def test_the_payload_is_json_serialisable_and_sorted_stable(self):
        first = json.dumps(CD_PRE_REGISTRATION.payload(), sort_keys=True)
        second = json.dumps(CD_PRE_REGISTRATION.payload(), sort_keys=True)
        assert first == second


class TestItStandsOnItsPredecessors:
    def test_it_carries_the_ca_bz_and_cc_seals_it_depends_on(self):
        payload = CD_PRE_REGISTRATION.payload()
        assert payload["ca_preregistration_digest"] == CA_PREREGISTRATION_DIGEST
        assert payload["bz_preregistration_digest"] == BZ_PREREGISTRATION_DIGEST
        assert payload["cc_preregistration_digest"] == CC_PREREGISTRATION_DIGEST

    def test_the_primary_horizon_is_ca_s_sealed_one(self):
        assert CD_PRE_REGISTRATION.primary_horizon == PRIMARY_HORIZON == 24

    def test_the_sample_boundaries_are_imported_not_restated(self):
        from fmis.swing_lab.preregistration import SAMPLES

        recorded = CD_PRE_REGISTRATION.payload()["sample_boundaries"]
        assert [item["name"] for item in recorded] == [item.name for item in SAMPLES]
        assert recorded[0]["symbols"] == list(SAMPLES[0].symbols)


class TestNoResultCanEnterTheSeal:
    #: Pinned. Adding a field here is a deliberate act; adding one to the payload
    #: without adding it here is a test failure.
    EXPECTED_KEYS = {
        "preregistration_id", "research_question", "estimand", "unit_of_evidence",
        "universe_source", "primary_family", "primary_sample", "measured_samples",
        "primary_horizon", "unmatched_rule", "repeated_observation_rule",
        "overlap_rule", "cross_asset_rule", "primary_estimator_id",
        "primary_estimator_rule", "secondary_estimators", "grouping_axes",
        "primary_block_bars", "block_bars_grid", "cell_reductions",
        "primary_cell_reduction", "weightings", "primary_weighting",
        "uncertainty_rule", "bootstrap_draws", "bootstrap_confidence",
        "master_seed", "min_groups", "min_members", "min_economic_assets",
        "min_informative_blocks", "min_shared_blocks_per_pair", "winsorisation",
        "calibration_replicates", "calibration_tolerance_rule", "verdict_rules",
        "requirement_rules", "interpretation_rules", "non_promotion_rule",
        "provider_mutability", "artifact_requirements", "limitations",
        "meaningful_effect_atr", "ca_preregistration_id",
        "ca_preregistration_digest", "bz_preregistration_id",
        "bz_preregistration_digest", "cc_preregistration_id",
        "cc_preregistration_digest", "identity_rules", "sample_boundaries",
        "dependence_verdict_vocabulary", "requirement_outcome_vocabulary",
    }

    def test_the_payload_holds_exactly_the_pinned_keys(self):
        assert set(CD_PRE_REGISTRATION.payload()) == self.EXPECTED_KEYS

    #: Design keys that legitimately contain a word the result guard watches for.
    #: `measured_samples` names WHICH samples are measured, not what was measured
    #: on them; `requirement_outcome_vocabulary` is the enum's member list, not a
    #: chosen member. Both are design, and both are pinned here so a genuine
    #: result field cannot be waved through by widening the guard.
    DESIGN_KEYS_CONTAINING_A_RESULT_WORD = {
        "measured_samples",
        "requirement_outcome_vocabulary",
    }

    def test_no_key_names_a_result(self):
        forbidden = (
            "correlation", "estimate", "interval", "verdict_reached", "measured",
            "r_b", "rho_w", "effect_size", "outcome", "result", "point",
        )
        for key in CD_PRE_REGISTRATION.payload():
            if key in self.DESIGN_KEYS_CONTAINING_A_RESULT_WORD:
                continue
            assert not any(word in key for word in forbidden), key

    def test_the_allowlist_is_not_a_way_to_wave_a_result_through(self):
        # Every allowlisted key must actually be in the payload, so a stale entry
        # cannot silently cover a field added later under the same name.
        assert self.DESIGN_KEYS_CONTAINING_A_RESULT_WORD <= set(
            CD_PRE_REGISTRATION.payload()
        )
        # And both must hold design content, not a number.
        payload = CD_PRE_REGISTRATION.payload()
        assert payload["measured_samples"] == ["development", "validation", "holdout"]
        assert payload["requirement_outcome_vocabulary"] == [
            "resolvable", "underpowered", "unreachable", "inconclusive"
        ]

    def test_the_dataclass_has_no_field_that_could_hold_one(self):
        fields = set(CdPreregistration.__dataclass_fields__)
        forbidden = {
            "correlation", "between_asset", "within_asset", "interval",
            "verdict", "point_estimate", "result", "required_clusters",
        }
        assert fields & forbidden == set()


class TestMutationMovesTheDigest:
    """Every scientifically material field must move the seal when it changes."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("preregistration_id", "cd-something-else"),
            ("research_question", "a different question"),
            ("estimand", "a different estimand"),
            ("unit_of_evidence", "one row"),
            ("universe_source", "CC's 38 eligible assets"),
            ("primary_family", "ca_null_eligible_but_rejected"),
            ("primary_sample", "validation"),
            ("measured_samples", ("development",)),
            ("unmatched_rule", "unmatched admissions are imputed"),
            ("repeated_observation_rule", "repeats are dropped"),
            ("overlap_rule", "overlapping admissions are dropped"),
            ("cross_asset_rule", "assets are matched by calendar day"),
            ("primary_estimator_id", "cd-something-else-v1"),
            ("primary_estimator_rule", "a different estimator"),
            ("secondary_estimators", ("only one",)),
            ("primary_block_bars", 120),
            ("block_bars_grid", (24, 60, 120, 180, 240)),
            ("primary_cell_reduction", "cell_first"),
            ("primary_weighting", "observation_count"),
            ("uncertainty_rule", "Fisher-z"),
            ("bootstrap_draws", 4000),
            ("bootstrap_confidence", 0.90),
            ("master_seed", 1),
            ("min_groups", 5),
            ("min_members", 10),
            ("min_economic_assets", 2),
            ("min_informative_blocks", 2),
            ("min_shared_blocks_per_pair", 2),
            ("winsorisation", "trim the top and bottom 1 %"),
            ("calibration_replicates", 5),
            ("calibration_tolerance_rule", "within 0.5"),
            ("verdict_rules", ("anything goes",)),
            ("requirement_rules", ("anything goes",)),
            ("interpretation_rules", ("anything goes",)),
            ("non_promotion_rule", "promotion is permitted"),
            ("provider_mutability", "the provider never changes"),
            ("artifact_requirements", ("none",)),
            ("limitations", ("none",)),
            ("meaningful_effect_atr", 0.30),
            ("ca_preregistration_digest", "0" * 64),
            ("bz_preregistration_digest", "0" * 64),
            ("cc_preregistration_digest", "0" * 64),
        ],
    )
    def test_changing_a_material_field_moves_the_digest(self, field, value):
        mutated = replace(CD_PRE_REGISTRATION, **{field: value})
        assert cd_preregistration_digest(mutated) != CD_PREREGISTRATION_DIGEST

    def test_changing_the_identity_rules_moves_the_digest(self):
        rules = dict(CD_PRE_REGISTRATION.identity_rules)
        rules["rule_id"] = "something-else"
        mutated = replace(CD_PRE_REGISTRATION, identity_rules=rules)
        assert cd_preregistration_digest(mutated) != CD_PREREGISTRATION_DIGEST

    def test_reordering_the_block_grid_moves_the_digest(self):
        mutated = replace(CD_PRE_REGISTRATION, block_bars_grid=(60, 24, 120, 180))
        assert cd_preregistration_digest(mutated) != CD_PREREGISTRATION_DIGEST

    def test_an_identical_copy_does_not_move_it(self):
        mutated = replace(CD_PRE_REGISTRATION)
        assert cd_preregistration_digest(mutated) == CD_PREREGISTRATION_DIGEST


class TestInvariants:
    def test_a_primary_block_length_outside_the_grid_is_refused(self):
        with pytest.raises(PairedDependenceError, match="not in the"):
            replace(CD_PRE_REGISTRATION, primary_block_bars=999)

    def test_a_primary_reduction_outside_the_declared_set_is_refused(self):
        with pytest.raises(PairedDependenceError, match="primary cell reduction"):
            replace(CD_PRE_REGISTRATION, primary_cell_reduction="cell_median")

    def test_a_primary_weighting_outside_the_declared_set_is_refused(self):
        with pytest.raises(PairedDependenceError, match="primary weighting"):
            replace(CD_PRE_REGISTRATION, primary_weighting="inverse_variance")

    def test_a_primary_sample_outside_the_measured_set_is_refused(self):
        with pytest.raises(PairedDependenceError, match="primary sample"):
            replace(CD_PRE_REGISTRATION, primary_sample="production")

    def test_a_family_milestone_ca_never_sealed_is_refused(self):
        with pytest.raises(PairedDependenceError, match="Milestone\\s+CA sealed"):
            replace(CD_PRE_REGISTRATION, primary_family="ca_null_invented_here")

    def test_a_horizon_that_is_not_ca_s_is_refused(self):
        with pytest.raises(PairedDependenceError, match="primary horizon"):
            replace(CD_PRE_REGISTRATION, primary_horizon=60)

    def test_an_empty_rule_tuple_is_refused(self):
        with pytest.raises(PairedDependenceError, match="non-empty tuple"):
            replace(CD_PRE_REGISTRATION, verdict_rules=())

    def test_a_blank_text_field_is_refused(self):
        with pytest.raises(PairedDependenceError, match="non-empty string"):
            replace(CD_PRE_REGISTRATION, estimand="  ")

    def test_a_confidence_outside_the_open_unit_interval_is_refused(self):
        with pytest.raises(PairedDependenceError):
            replace(CD_PRE_REGISTRATION, bootstrap_confidence=1.0)

    def test_a_derisory_bootstrap_is_refused(self):
        with pytest.raises(PairedDependenceError):
            replace(CD_PRE_REGISTRATION, bootstrap_draws=10)


class TestLimitations:
    def test_every_limitation_is_numbered_and_states_a_direction_or_a_fact(self):
        assert len(CD_LIMITATIONS) >= 7
        for index, item in enumerate(CD_LIMITATIONS, start=1):
            assert item.startswith(f"CD-{index} —"), item

    def test_the_heteroskedasticity_limitation_names_its_direction(self):
        text = " ".join(CD_LIMITATIONS)
        assert "DOWNWARD" in text and "flatters feasibility" in text

    def test_the_recapture_limitation_exists(self):
        assert any("RE-CAPTURED" in item for item in CD_LIMITATIONS)


class TestIdentity:
    def test_the_preregistration_id_is_the_one_the_artifact_will_carry(self):
        assert CD_PRE_REGISTRATION.preregistration_id == CD_PREREGISTRATION_ID
