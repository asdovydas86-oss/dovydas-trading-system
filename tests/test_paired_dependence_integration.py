"""Feeding CD's dependence into Milestone CB, and re-reading Milestone CC.

The arithmetic asserted here decides the milestone's headline, so it is checked
against the formula rather than against itself: ``K = K* (1 - r) / (1 - K* r)``,
unreachable at ``r >= 1 / K*``, and CB's own 467 called rather than restated.
"""

from __future__ import annotations

import pytest

from fmis.paired_dependence.integration import (
    CC_PROVIDER_CEILING_CLUSTERS,
    assess_requirement,
    cb_required_clusters,
    cc_reevaluation,
    requirement_at,
)
from fmis.paired_dependence.models import PairedDependenceError, RequirementOutcome


class TestCbIsCalledNotCopied:
    def test_the_requirement_is_milestone_cb_s_published_467_and_4823(self):
        clusters, admissions, per_cluster = cb_required_clusters()
        assert clusters == 467
        assert admissions == 4823
        assert per_cluster == pytest.approx(155 / 15)

    def test_the_more_clusters_path_is_invariant_to_the_intracluster_correlation(self):
        baseline = cb_required_clusters(intracluster_correlation=0.0)
        for rho in (0.05, 0.10, 0.20, 0.50, 1.0):
            assert cb_required_clusters(intracluster_correlation=rho) == baseline

    def test_an_unpublished_sample_is_refused_by_milestone_cb(self):
        """Narrow, deliberately. `pytest.raises(Exception)` here would pass on an
        `AttributeError` from a deleted function — it would assert that the call
        broke, not that it was refused."""
        from fmis.swing_lab.models import SwingLabError

        with pytest.raises(SwingLabError, match="no published CA figure"):
            cb_required_clusters(sample="production")


class TestRequirementAt:
    def test_zero_correlation_leaves_the_requirement_at_cb_s_figure(self):
        point = requirement_at(
            0.0, label="p", independent_clusters=467, observations_per_cluster=10.0
        )
        assert point.reachable
        assert point.required_clusters == pytest.approx(467.0)
        assert point.required_admissions == pytest.approx(4670.0)

    def test_the_inversion_matches_the_closed_form(self):
        r = 0.0015
        point = requirement_at(
            r, label="p", independent_clusters=467, observations_per_cluster=10.0
        )
        assert point.required_clusters == pytest.approx(467 * (1 - r) / (1 - 467 * r))

    def test_at_the_threshold_it_is_unreachable_and_says_why(self):
        point = requirement_at(
            1.0 / 467, label="p", independent_clusters=467,
            observations_per_cluster=10.0,
        )
        assert not point.reachable
        assert point.required_clusters is None
        assert "UNREACHABLE" in point.note
        assert point.saturation_ceiling == pytest.approx(467.0)

    def test_an_unidentified_correlation_states_the_assumption_it_did_not_verify(self):
        point = requirement_at(
            None, label="p", independent_clusters=467, observations_per_cluster=10.0
        )
        assert point.required_clusters == 467.0
        assert "did NOT verify" in point.note

    def test_a_negative_correlation_is_clamped_and_the_ceiling_is_absent(self):
        point = requirement_at(
            -0.2, label="p", independent_clusters=467, observations_per_cluster=10.0
        )
        assert point.required_clusters == pytest.approx(467.0)
        assert point.saturation_ceiling is None

    def test_a_zero_cluster_target_is_refused(self):
        with pytest.raises(PairedDependenceError):
            requirement_at(
                0.0, label="p", independent_clusters=0, observations_per_cluster=1.0
            )


class TestAssessRequirement:
    def _assess(self, lower, point, upper, ceiling=CC_PROVIDER_CEILING_CLUSTERS):
        return assess_requirement(
            point=point, lower=lower, upper=upper,
            within_asset_correlation=0.05, provider_ceiling=ceiling,
        )

    def test_an_interval_straddling_the_threshold_is_inconclusive(self):
        assessment = self._assess(-0.05, 0.02, 0.20)
        assert assessment.outcome is RequirementOutcome.INCONCLUSIVE
        assert "spans from at or below zero" in assessment.reasoning

    def test_the_interval_is_read_BEFORE_the_point_estimate(self):
        # A point estimate below the threshold with an interval that reaches
        # above it must NOT report a finite requirement.
        assessment = self._assess(-0.30, 0.0005, 0.10)
        assert assessment.outcome is RequirementOutcome.INCONCLUSIVE
        assert assessment.point.reachable

    def test_a_point_above_the_threshold_with_a_tight_interval_is_unreachable(self):
        assessment = self._assess(0.0030, 0.0050, 0.0080)
        assert assessment.outcome is RequirementOutcome.UNREACHABLE

    def test_a_finite_requirement_above_cc_s_ceiling_is_underpowered(self):
        assessment = self._assess(0.0000, 0.0000, 0.0000)
        assert assessment.outcome is RequirementOutcome.UNDERPOWERED
        assert assessment.point.required_clusters == pytest.approx(467.0)

    def test_a_finite_requirement_below_a_generous_ceiling_is_resolvable(self):
        assessment = self._assess(0.0, 0.0, 0.0, ceiling=1000)
        assert assessment.outcome is RequirementOutcome.RESOLVABLE

    def test_no_interval_at_all_is_inconclusive(self):
        assessment = self._assess(None, 0.001, None)
        assert assessment.outcome is RequirementOutcome.INCONCLUSIVE
        assert "not a design input" in assessment.reasoning

    def test_the_order_of_magnitude_span_is_upper_over_lower(self):
        assessment = self._assess(0.0000, 0.0005, 0.0010)
        assert assessment.order_of_magnitude_span == pytest.approx(
            assessment.upper.required_clusters / assessment.lower.required_clusters
        )

    def test_the_span_is_none_when_a_bound_is_unreachable(self):
        assessment = self._assess(0.0000, 0.0010, 0.0030)
        assert not assessment.upper.reachable
        assert assessment.order_of_magnitude_span is None

    def test_the_within_asset_correlation_is_carried_and_never_substituted(self):
        assessment = self._assess(0.0, 0.0, 0.0)
        assert assessment.within_asset_correlation == 0.05
        assert assessment.point.correlation == 0.0

    def test_every_outcome_approves_nothing(self):
        for member in RequirementOutcome:
            assert member.is_approved_for_trading is False
            assert member.earns_forward_test is False
            assert member.says_nothing_about_the_hypothesis is True


class TestCcReevaluation:
    def test_cc_s_verdict_is_preserved_verbatim(self):
        comparison = cc_reevaluation(
            assess_requirement(
                point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
            )
        )
        assert comparison["cc_verdict_preserved"] == "infeasible"
        assert comparison["cc_binding_constraint_preserved"] == "cluster_count"
        assert comparison["cc_eligible_assets"] == 38
        assert comparison["cc_provider_ceiling_clusters"] == 106

    def test_it_answers_whether_the_ceiling_is_still_below_the_requirement(self):
        comparison = cc_reevaluation(
            assess_requirement(
                point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
            )
        )
        assert comparison["ceiling_still_below_requirement"] is True

    def test_an_unreachable_point_makes_the_ceiling_comparison_true_by_definition(self):
        comparison = cc_reevaluation(
            assess_requirement(
                point=0.01, lower=0.008, upper=0.012, within_asset_correlation=None
            )
        )
        assert comparison["ceiling_still_below_requirement"] is True
        assert comparison["is_467_still_the_right_order_of_magnitude"] is None

    def test_warm_up_help_is_explained_as_moving_the_ceiling_not_the_requirement(self):
        comparison = cc_reevaluation(
            assess_requirement(
                point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
            )
        )
        assert "CEILING and not" in comparison["warm_up_reduction_would_help"]

    def test_a_warm_up_milestone_is_justified_only_when_the_requirement_is_finite(self):
        underpowered = cc_reevaluation(
            assess_requirement(
                point=0.0, lower=0.0, upper=0.0, within_asset_correlation=None
            )
        )
        unreachable = cc_reevaluation(
            assess_requirement(
                point=0.01, lower=0.008, upper=0.012, within_asset_correlation=None
            )
        )
        assert underpowered["warm_up_sensitivity_is_justified"] is True
        assert unreachable["warm_up_sensitivity_is_justified"] is False

    def test_a_foreign_object_is_refused(self):
        with pytest.raises(PairedDependenceError):
            cc_reevaluation(object())
