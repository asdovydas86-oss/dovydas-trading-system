"""Milestone CA's design, assessed — and the three seals CB did not touch.

The reproduction is the centre of this file. Report 0037 §1 and CA-8 publish
*"roughly 4,800 matched admissions per sample"*, derived as
``(0.558 / 0.10)^2 * 155``. CB recomputes that through a general layer that knows
nothing about CA, from the interval bounds CA tabulated rather than from the
rounded half-width CA quoted, and classifies the agreement by a stated rule.

The second half of the file is what CB **adds**: that CA's figure is correct
under one growth path and unreachable under another, which CA's own arithmetic
cannot distinguish because it makes no distinction between them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.research_design.models import (
    AssessmentMode,
    DesignVerdict,
    GrowthPath,
    LimitingFactor,
    ResearchDesignError,
    ResolutionCriterion,
    SampleRole,
)
from fmis.research_design.resolution import prospective_design
from fmis.research_design.verdict import assess_research_design
from fmis.swing_lab.admission_power import (
    ATR_UNIT,
    CA_DESIGN_ASSESSMENT_ID,
    CA_LIMITATIONS,
    CA_PUBLISHED,
    CA_PUBLISHED_HALF_WIDTH,
    CA_PUBLISHED_REQUIRED_ADMISSIONS,
    CA_SENSITIVITY_CORRELATIONS,
    CaPublishedFigure,
    ca_dependence,
    ca_design_assessment,
    ca_design_curve,
    ca_estimator,
    ca_meaningful_effect,
    ca_post_hoc,
    ca_published,
    ca_question,
    ca_reproduction,
    ca_required_information,
    ca_sample_frames,
    ca_target,
)
from fmis.swing_lab.admission_preregistration import (
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
)
from fmis.swing_lab.geometry_verdict import MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence_preregistration import BZ_PREREGISTRATION_DIGEST
from fmis.swing_lab.preregistration import (
    PREREGISTRATION_DIGEST as BY_PREREGISTRATION_DIGEST,
    SAMPLES,
)


class TestTheSealsAreUntouched:
    """CB extracted three primitives out of the laboratory. No seal moved."""

    def test_milestone_bys_pinned_digest_is_byte_identical(self) -> None:
        assert BY_PREREGISTRATION_DIGEST == (
            "a81b6ab8314bd3cf2e8a6358f3a19cf8d6bb6c152cef9efd55fbffd9883d640a"
        )

    def test_milestone_bzs_pinned_digest_is_byte_identical(self) -> None:
        assert BZ_PREREGISTRATION_DIGEST == (
            "4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175"
        )

    def test_milestone_cas_pinned_digest_is_byte_identical(self) -> None:
        assert CA_PREREGISTRATION_DIGEST == (
            "910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a"
        )


class TestThePublishedFigures:
    def test_the_half_width_is_derived_from_the_bounds_not_quoted_from_prose(self) -> None:
        development = ca_published("development")
        assert development.bootstrap_low == -0.7494
        assert development.bootstrap_high == 0.3662
        assert development.half_width == pytest.approx(0.5578)

    def test_the_derived_half_width_rounds_to_the_figure_ca_quotes(self) -> None:
        assert round(ca_published("development").half_width, 3) == CA_PUBLISHED_HALF_WIDTH

    def test_every_published_sample_carries_its_source(self) -> None:
        for figure in CA_PUBLISHED:
            assert "report 0037" in figure.source

    def test_where_ca_published_no_concentration_the_field_is_absent(self) -> None:
        """An unchecked bound is not a passed one; it is left as a hole."""
        assert ca_published("development").largest_cluster_share == 0.113
        assert ca_published("validation").largest_cluster_share is None
        assert ca_published("holdout").largest_cluster_share is None

    def test_an_unpublished_sample_is_refused_by_name(self) -> None:
        with pytest.raises(SwingLabError, match="no published CA figure"):
            ca_published("dev")

    def test_a_disordered_interval_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="is not ordered"):
            CaPublishedFigure(
                sample="x", matched=10, symbols=2,
                bootstrap_low=0.5, bootstrap_high=0.1,
                largest_cluster_share=None, source="s",
            )

    def test_a_non_positive_count_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be positive"):
            CaPublishedFigure(
                sample="x", matched=0, symbols=2,
                bootstrap_low=-0.5, bootstrap_high=0.1,
                largest_cluster_share=None, source="s",
            )


class TestNothingIsRetyped:
    def test_the_effect_bar_is_milestone_cas_own_sealed_constant(self) -> None:
        assert ca_meaningful_effect().magnitude == Decimal(str(MIN_ADMISSION_EDGE_ATR))

    def test_the_question_id_is_the_sealed_preregistration_id(self) -> None:
        assert ca_question().question_id == CA_PREREGISTRATION_ID

    def test_the_concentration_bound_is_the_laboratorys_own(self) -> None:
        assert ca_target().maximum_cluster_share == float(MAX_SINGLE_SYMBOL_SHARE)

    @pytest.mark.parametrize("name", ("development", "validation", "holdout"))
    def test_every_window_is_milestone_bys_own(self, name: str) -> None:
        spec = next(item for item in SAMPLES if item.name == name)
        frame = next(item for item in ca_sample_frames() if item.name == name)
        assert frame.starts_at == spec.signal_start
        assert frame.ends_at == spec.signal_end

    def test_the_symbol_counts_match_the_sealed_universes(self) -> None:
        for name in ("development", "validation", "holdout"):
            spec = next(item for item in SAMPLES if item.name == name)
            frame = next(item for item in ca_sample_frames() if item.name == name)
            assert frame.clusters == len(spec.symbols)

    def test_the_roles_are_the_sealed_roles(self) -> None:
        frames = {item.name: item for item in ca_sample_frames()}
        assert frames["development"].role is SampleRole.DEVELOPMENT
        assert frames["validation"].role is SampleRole.VALIDATION
        assert frames["holdout"].role is SampleRole.HOLDOUT

    def test_the_holdout_is_a_separate_population_so_it_may_overlap_in_time(self) -> None:
        frames = {item.name: item for item in ca_sample_frames()}
        assert frames["development"].population == frames["validation"].population
        assert frames["holdout"].population != frames["development"].population
        assert frames["holdout"].starts_at < frames["development"].ends_at

    def test_development_and_validation_do_not_overlap(self) -> None:
        frames = {item.name: item for item in ca_sample_frames()}
        assert frames["development"].ends_at == frames["validation"].starts_at


class TestTheReproduction:
    def test_cas_published_requirement_is_reproduced(self) -> None:
        result = ca_reproduction()
        assert result.disposition == "reproduced"
        assert result.published_claim == CA_PUBLISHED_REQUIRED_ADMISSIONS

    def test_recomputing_cas_own_arithmetic_gives_4827(self) -> None:
        """From the half-width CA quotes: (0.558 / 0.10)^2 * 155 = 4,826.1 -> 4,827."""
        assert ca_reproduction().recomputed_from_published_half_width == 4827

    def test_recomputing_from_the_tabulated_bounds_gives_4823(self) -> None:
        assert ca_reproduction().recomputed_from_interval_bounds == 4823

    def test_both_recomputations_agree_with_the_published_figure(self) -> None:
        result = ca_reproduction()
        assert result.relative_difference < 0.01
        for value in (
            result.recomputed_from_published_half_width,
            result.recomputed_from_interval_bounds,
        ):
            assert abs(value - 4800) / 4800 < 0.01

    def test_the_reasoning_names_the_assumption_ca_did_not_name(self) -> None:
        reasoning = ca_reproduction().reasoning
        assert "INDEPENDENT_OBSERVATIONS" in reasoning
        assert "MORE_OBSERVATIONS_SAME_CLUSTERS" in reasoning

    def test_the_reproduction_payload_is_json_safe(self) -> None:
        import json

        json.dumps(ca_reproduction().payload())


class TestWhatCbAddsToTheReproduction:
    """CA's figure is right on one growth path and unreachable on another."""

    def test_more_clusters_at_the_same_density_costs_exactly_cas_figure(self) -> None:
        for correlation in CA_SENSITIVITY_CORRELATIONS:
            result = ca_required_information(
                GrowthPath.MORE_CLUSTERS_SAME_DENSITY, correlation
            )
            assert result.required_observations == 4823
            assert result.required_clusters == 467
            assert result.reachable

    def test_more_years_on_the_same_symbols_is_unreachable_at_any_correlation(self) -> None:
        for correlation in (0.05, 0.10, 0.20, 0.50):
            result = ca_required_information(
                GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, correlation
            )
            assert not result.reachable, correlation
            assert result.floor_half_width > 0.10

    def test_even_the_mildest_clustering_leaves_a_floor_three_times_the_bar(self) -> None:
        result = ca_required_information(
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.05
        )
        assert result.floor_half_width == pytest.approx(0.3311, abs=1e-3)
        assert result.floor_half_width > 3 * 0.10

    def test_only_at_exactly_zero_correlation_does_more_history_suffice(self) -> None:
        result = ca_required_information(
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.0
        )
        assert result.reachable
        assert result.required_observations == 4823

    def test_the_floor_at_ten_percent_is_four_times_the_bar(self) -> None:
        result = ca_required_information(
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.10
        )
        assert result.floor_half_width == pytest.approx(0.4078, abs=1e-3)


class TestTheAssessment:
    def test_ca_is_underpowered_for_its_own_sealed_bar(self) -> None:
        assessment = ca_design_assessment()
        assert assessment.verdict is DesignVerdict.UNDERPOWERED

    def test_the_binding_dimension_is_the_cluster_count(self) -> None:
        assert ca_design_assessment().limiting_factor is LimitingFactor.CLUSTER_COUNT

    def test_it_is_a_post_hoc_diagnostic_and_says_so(self) -> None:
        assessment = ca_design_assessment()
        assert assessment.mode is AssessmentMode.POST_HOC
        assert not assessment.mode.may_justify_running_a_study

    def test_it_is_decided_on_development_never_on_the_holdout(self) -> None:
        assert ca_design_assessment().primary_sample == "development"

    def test_a_holdout_measured_width_cannot_decide_cas_design(self) -> None:
        """The holdout's own outcomes may not justify a study. Refused, not warned."""
        with pytest.raises(ResearchDesignError, match="already spent it"):
            assess_research_design(
                assessment_id=CA_DESIGN_ASSESSMENT_ID,
                question=ca_question(),
                effect=ca_meaningful_effect(),
                uncertainty_unit=ATR_UNIT,
                dependence=ca_dependence(),
                estimator=ca_estimator(),
                target=ca_target(),
                frames=ca_sample_frames(),
                primary_sample="holdout",
                resolution=ca_post_hoc("holdout"),
                sensitivity_correlations=CA_SENSITIVITY_CORRELATIONS,
            )

    def test_a_prospective_assessment_of_the_holdout_is_permitted(self) -> None:
        """Because it reads an ASSUMED dispersion, the holdout is never opened."""
        holdout = next(item for item in ca_sample_frames() if item.name == "holdout")
        assessment = assess_research_design(
            assessment_id="cb-future-holdout-design",
            question=ca_question(),
            effect=ca_meaningful_effect(),
            uncertainty_unit=ATR_UNIT,
            dependence=ca_dependence(),
            estimator=ca_estimator(),
            target=ca_target(),
            frames=ca_sample_frames(),
            primary_sample="holdout",
            resolution=prospective_design(
                frame=holdout,
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="report 0037 §10's development interval",
                effect=ca_meaningful_effect(),
                target=ca_target(),
                estimator=ca_estimator(),
            ),
            sensitivity_correlations=CA_SENSITIVITY_CORRELATIONS,
        )
        assert assessment.mode is AssessmentMode.PROSPECTIVE
        assert assessment.verdict is DesignVerdict.UNDERPOWERED

    def test_the_verdict_says_nothing_about_whether_an_edge_exists(self) -> None:
        assert ca_design_assessment().verdict.says_nothing_about_the_hypothesis

    def test_the_criterion_is_the_one_ca_actually_sealed(self) -> None:
        """CA sealed no power calculation, so attributing one to it would be false."""
        assert ca_target().criterion is ResolutionCriterion.INTERVAL_EXCLUDES_ZERO
        assert ca_target().power is None

    def test_the_information_cap_is_left_to_the_owner(self) -> None:
        assert ca_target().maximum_information_multiple is None

    def test_no_effective_sample_size_is_offered_because_none_was_measured(self) -> None:
        for profile in ca_design_assessment().profiles:
            assert profile.effective_observations is None
            assert "No intracluster correlation was declared" in profile.derivation

    def test_the_unmeasured_correlation_is_carried_as_a_caveat(self) -> None:
        caveats = " ".join(ca_design_assessment().caveats)
        assert "intracluster correlation is unmeasured" in caveats

    def test_the_overlapping_window_is_carried_as_a_caveat(self) -> None:
        assert any("share up to 60" in item for item in ca_design_assessment().caveats)


class TestPostHocOnEverySample:
    @pytest.mark.parametrize("name", ("development", "validation", "holdout"))
    def test_no_sample_resolves_the_sealed_bar(self, name: str) -> None:
        reading = ca_post_hoc(name)
        assert not reading.resolves_meaningful_effect
        assert reading.smallest_resolvable_effect > 0.10

    def test_the_holdout_is_the_sharpest_sample_and_still_cannot_resolve_it(self) -> None:
        widths = {name: ca_post_hoc(name).observed_half_width
                  for name in ("development", "validation", "holdout")}
        assert widths["holdout"] == min(widths.values())
        assert widths["holdout"] > 0.10

    def test_every_reading_is_post_hoc(self) -> None:
        for name in ("development", "validation", "holdout"):
            assert ca_post_hoc(name).mode is AssessmentMode.POST_HOC


class TestTheDesignCurve:
    def test_the_curve_reproduces_the_observed_width_at_155(self) -> None:
        for path in (
            GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
        ):
            points = ca_design_curve(path, 0.0)
            at_155 = next(item for item in points if item.observations == 155)
            assert at_155.half_width == pytest.approx(0.5578, abs=1e-3)

    def test_every_point_beyond_155_is_marked_extrapolated(self) -> None:
        for point in ca_design_curve(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.0):
            assert point.extrapolated == (point.observations > 155)

    def test_more_clusters_resolves_the_bar_somewhere_near_five_thousand(self) -> None:
        points = ca_design_curve(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.10)
        resolving = [item for item in points if item.resolves]
        assert resolving
        assert min(item.observations for item in resolving) > 2_000

    def test_more_years_at_ten_percent_never_resolves_at_any_size_drawn(self) -> None:
        points = ca_design_curve(GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.10)
        assert not any(item.resolves for item in points)
        assert points[-1].half_width == pytest.approx(0.4105, abs=1e-3)

    def test_the_more_clusters_curve_is_the_same_at_every_correlation(self) -> None:
        first = ca_design_curve(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.0)
        second = ca_design_curve(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.50)
        assert [item.half_width for item in first] == pytest.approx(
            [item.half_width for item in second]
        )

    def test_an_independent_observation_curve_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError):
            ca_design_curve(GrowthPath.INDEPENDENT_OBSERVATIONS, 0.0)


class TestTheLimitations:
    def test_the_summary_statistic_limitation_is_stated_first(self) -> None:
        assert CA_LIMITATIONS[0].startswith("CB-1")
        assert "NOT DATA-LEVEL" in CA_LIMITATIONS[0]

    def test_every_limitation_is_numbered_and_non_empty(self) -> None:
        for index, item in enumerate(CA_LIMITATIONS, start=1):
            assert item.startswith(f"CB-{index} —"), item

    def test_it_states_that_it_changes_no_ca_verdict(self) -> None:
        assert any("CA's NO_EDGE stands exactly as" in item for item in CA_LIMITATIONS)


class TestDeterminism:
    def test_two_assessments_are_equal(self) -> None:
        assert ca_design_assessment().payload() == ca_design_assessment().payload()

    def test_two_reproductions_are_equal(self) -> None:
        assert ca_reproduction() == ca_reproduction()
