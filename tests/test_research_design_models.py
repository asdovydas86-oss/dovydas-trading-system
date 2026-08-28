"""The vocabulary refuses what cannot be assessed. **Every rejection by name.**

These are Phase 11's list, one test each: a zero effect threshold, a negative
sample size, malformed boundaries, a zero cluster count, an impossible confidence
level, inconsistent units and a validation sample reused as development. None of
them is folded into a verdict — a gate that reported "you passed a negative n" as
"insufficient data" would be worse than no gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.research_design.models import (
    AssessmentMode,
    ComparisonType,
    DependenceModel,
    DesignTarget,
    DesignVerdict,
    EffectDirection,
    EstimatorKind,
    EstimatorSpec,
    GrowthPath,
    LimitingFactor,
    MeaningfulEffect,
    MetricUnit,
    ResearchDesignError,
    ResolutionCriterion,
    SampleFrame,
    SampleRole,
    check_sample_frames,
)
from tests.research_design_helpers import (
    OTHER_UNIT,
    UNIT,
    a_dependence,
    a_frame,
    a_target,
    an_effect,
    an_estimator,
)

UTC = timezone.utc


class TestTheUnit:
    def test_two_spellings_of_one_unit_are_refused(self) -> None:
        for bad in ("ATR", "atr ", " atr", "a tr"):
            with pytest.raises(ResearchDesignError, match="lowercase"):
                MetricUnit(code=bad, description="x")

    def test_an_empty_code_or_description_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="unit code"):
            MetricUnit(code="  ", description="x")
        with pytest.raises(ResearchDesignError, match="unit description"):
            MetricUnit(code="atr", description="")

    def test_units_are_compared_by_code_never_by_description(self) -> None:
        first = MetricUnit(code="atr", description="one description")
        second = MetricUnit(code="atr", description="a completely different one")
        assert first.agrees_with(second)
        assert not first.agrees_with(OTHER_UNIT)

    def test_comparing_against_a_non_unit_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError):
            UNIT.agrees_with("atr")  # type: ignore[arg-type]


class TestTheMeaningfulEffect:
    def test_a_zero_threshold_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="strictly positive"):
            an_effect("0")

    def test_a_negative_threshold_is_refused_and_points_at_direction(self) -> None:
        with pytest.raises(ResearchDesignError, match="declare the DIRECTION"):
            an_effect("-0.10")

    def test_a_float_magnitude_is_refused_so_a_declared_bar_stays_exact(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a Decimal"):
            MeaningfulEffect(
                magnitude=0.10,  # type: ignore[arg-type]
                unit=UNIT,
                direction=EffectDirection.GREATER,
                rationale="r",
                source="s",
            )

    def test_a_non_finite_magnitude_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="finite"):
            MeaningfulEffect(
                magnitude=Decimal("NaN"),
                unit=UNIT,
                direction=EffectDirection.GREATER,
                rationale="r",
                source="s",
            )

    def test_an_unexplained_threshold_is_refused(self) -> None:
        for field in ("rationale", "source"):
            kwargs = {
                "magnitude": Decimal("0.1"),
                "unit": UNIT,
                "direction": EffectDirection.GREATER,
                "rationale": "r",
                "source": "s",
            }
            kwargs[field] = "   "
            with pytest.raises(ResearchDesignError, match=field):
                MeaningfulEffect(**kwargs)  # type: ignore[arg-type]

    def test_the_float_boundary_is_one_conversion(self) -> None:
        assert an_effect("0.10").as_float == pytest.approx(0.10)


class TestTheSampleFrame:
    def test_a_negative_observation_count_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="observations must be >= 0"):
            a_frame(observations=-1, clusters=0, largest_cluster_share=None)

    def test_observations_with_no_cluster_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="malformed frame"):
            a_frame(observations=10, clusters=0, largest_cluster_share=None)

    def test_more_clusters_than_observations_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="cluster with no observation"):
            a_frame(observations=5, clusters=9, largest_cluster_share=None)

    def test_more_units_than_observations_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="coarser of the two"):
            a_frame(observations=10, clusters=2, experimental_units=11)

    def test_a_window_that_ends_before_it_starts_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="not after it starts"):
            SampleFrame(
                name="d",
                role=SampleRole.DEVELOPMENT,
                population="p",
                observations=10,
                clusters=2,
                time_blocks=1,
                experimental_units=10,
                starts_at=datetime(2024, 1, 2, tzinfo=UTC),
                ends_at=datetime(2024, 1, 1, tzinfo=UTC),
            )

    def test_a_naive_boundary_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="timezone-aware"):
            SampleFrame(
                name="d",
                role=SampleRole.DEVELOPMENT,
                population="p",
                observations=10,
                clusters=2,
                time_blocks=1,
                experimental_units=10,
                starts_at=datetime(2024, 1, 1),
                ends_at=datetime(2024, 2, 1),
            )

    def test_a_share_below_the_uniform_one_is_impossible_and_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="cannot be below the uniform"):
            a_frame(clusters=15, largest_cluster_share=0.05)

    def test_the_uniform_share_itself_is_accepted(self) -> None:
        assert a_frame(clusters=10, largest_cluster_share=0.1).largest_cluster_share == 0.1

    def test_a_share_of_one_is_accepted_and_is_total_concentration(self) -> None:
        assert a_frame(clusters=1, observations=30, largest_cluster_share=1.0)

    def test_observations_per_cluster_is_absent_with_no_cluster(self) -> None:
        empty = a_frame(observations=0, clusters=0, experimental_units=0,
                        largest_cluster_share=None)
        assert empty.observations_per_cluster is None

    def test_the_payload_carries_every_field(self) -> None:
        payload = a_frame().payload()
        assert set(payload) == {
            "name", "role", "population", "observations", "clusters", "time_blocks",
            "experimental_units", "starts_at", "ends_at", "largest_cluster_share",
        }


class TestSampleFramesTogether:
    def test_two_frames_may_not_share_a_name(self) -> None:
        with pytest.raises(ResearchDesignError, match="both named"):
            check_sample_frames((a_frame(), a_frame(role=SampleRole.VALIDATION)))

    def test_a_validation_sample_overlapping_development_is_refused(self) -> None:
        development = a_frame(months=24)
        validation = a_frame(
            name="validation",
            role=SampleRole.VALIDATION,
            starts_at=development.starts_at + timedelta(days=300),
            months=12,
        )
        with pytest.raises(ResearchDesignError, match="already been fitted"):
            check_sample_frames((development, validation))

    def test_adjacent_windows_of_one_population_are_accepted(self) -> None:
        development = a_frame(months=24)
        validation = a_frame(
            name="validation",
            role=SampleRole.VALIDATION,
            starts_at=development.ends_at,
            months=12,
        )
        check_sample_frames((development, validation))

    def test_a_different_population_may_overlap_freely(self) -> None:
        """Milestone CA's holdout runs over 21 symbols the primary never held."""
        development = a_frame(months=24)
        holdout = a_frame(
            name="holdout",
            role=SampleRole.HOLDOUT,
            population="holdout",
            starts_at=development.starts_at + timedelta(days=365),
            months=26,
            clusters=21,
            observations=234,
            largest_cluster_share=None,
        )
        check_sample_frames((development, holdout))


class TestTheEstimator:
    def test_an_impossible_confidence_is_refused(self) -> None:
        for bad in (0.0, 1.0, -0.1, 1.5):
            with pytest.raises(ResearchDesignError):
                an_estimator(confidence=bad)

    def test_a_nan_confidence_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="NaN"):
            an_estimator(confidence=float("nan"))

    def test_replicates_that_cannot_resolve_the_tail_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="extremum of the draws"):
            an_estimator(resamples=20, confidence=0.999)

    def test_exactly_one_replicate_in_the_tail_is_the_supported_boundary(self) -> None:
        assert an_estimator(resamples=40, confidence=0.95).resamples == 40
        with pytest.raises(ResearchDesignError):
            an_estimator(resamples=39, confidence=0.95)

    def test_an_estimator_with_no_stated_assumption_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="validity conditions"):
            EstimatorSpec(
                kind=EstimatorKind.CLUSTER_BOOTSTRAP,
                comparison=ComparisonType.PAIRED_DIFFERENCE,
                resamples=2000,
                confidence=0.95,
                assumptions=(),
                rationale="because",
            )

    def test_an_analytic_estimator_may_not_declare_resamples(self) -> None:
        with pytest.raises(ResearchDesignError, match="draws nothing"):
            EstimatorSpec(
                kind=EstimatorKind.ANALYTIC_NORMAL,
                comparison=ComparisonType.PAIRED_DIFFERENCE,
                resamples=10,
                confidence=0.95,
                assumptions=("normality",),
                rationale="because",
            )

    def test_only_the_clustered_estimators_respect_clustering(self) -> None:
        assert EstimatorKind.CLUSTER_BOOTSTRAP.respects_clustering
        assert EstimatorKind.BLOCK_BOOTSTRAP.respects_clustering
        assert not EstimatorKind.PAIRED_BOOTSTRAP.respects_clustering
        assert not EstimatorKind.ANALYTIC_NORMAL.respects_clustering
        assert not EstimatorKind.ANALYTIC_NORMAL.is_resampling


class TestTheDesignTarget:
    def test_a_powered_target_without_a_power_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="requires a power target"):
            a_target(criterion=ResolutionCriterion.POWERED_DETECTION)

    def test_an_interval_target_with_a_power_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="coin-flip criterion"):
            a_target(power=0.8)

    def test_a_power_at_or_below_a_coin_flip_is_refused(self) -> None:
        for bad in (0.5, 0.4, 1.0):
            with pytest.raises(ResearchDesignError, match="power must lie"):
                a_target(
                    criterion=ResolutionCriterion.POWERED_DETECTION, power=bad
                )

    def test_a_zero_cluster_floor_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="minimum_clusters"):
            a_target(minimum_clusters=0)

    def test_a_zero_concentration_bound_admits_no_design_and_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="admits no design"):
            a_target(maximum_cluster_share=0.0)

    def test_an_information_cap_below_one_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="less information than it already has"):
            a_target(maximum_information_multiple=0.5)


class TestTheDependenceModel:
    def test_a_correlation_with_no_source_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="correlation_source"):
            DependenceModel(
                unit_of_evidence="u",
                cluster_axis="symbol",
                overlapping_horizon=0,
                repeated_measurements=False,
                intracluster_correlation=0.1,
                correlation_source=None,
                assumptions=("a",),
            )

    def test_a_source_with_no_correlation_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="describes nothing"):
            DependenceModel(
                unit_of_evidence="u",
                cluster_axis="symbol",
                overlapping_horizon=0,
                repeated_measurements=False,
                intracluster_correlation=None,
                correlation_source="a pilot",
                assumptions=("a",),
            )

    def test_no_assumption_at_all_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least one assumption"):
            a_dependence().__class__(
                unit_of_evidence="u",
                cluster_axis="symbol",
                overlapping_horizon=0,
                repeated_measurements=False,
                intracluster_correlation=None,
                correlation_source=None,
                assumptions=(),
            )

    def test_a_negative_overlap_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="overlapping_horizon"):
            a_dependence(overlapping_horizon=-1)


class TestTheEnums:
    def test_no_verdict_says_anything_about_the_hypothesis(self) -> None:
        """Asserted over the WHOLE enum, so a new member cannot quietly promote."""
        for member in DesignVerdict:
            assert member.says_nothing_about_the_hypothesis is True

    def test_exactly_two_verdicts_permit_the_study_to_proceed(self) -> None:
        assert {member for member in DesignVerdict if member.may_proceed} == {
            DesignVerdict.READY,
            DesignVerdict.LIMITED,
        }

    def test_only_a_prospective_assessment_may_justify_running_a_study(self) -> None:
        assert AssessmentMode.PROSPECTIVE.may_justify_running_a_study
        assert not AssessmentMode.POST_HOC.may_justify_running_a_study

    def test_only_the_holdout_may_not_inform_a_design(self) -> None:
        assert not SampleRole.HOLDOUT.may_inform_design
        assert SampleRole.DEVELOPMENT.may_inform_design
        assert SampleRole.VALIDATION.may_inform_design

    def test_every_enum_member_has_a_distinct_value(self) -> None:
        for enum in (
            DesignVerdict, LimitingFactor, GrowthPath, AssessmentMode,
            SampleRole, EstimatorKind, ResolutionCriterion, EffectDirection,
            ComparisonType,
        ):
            values = [member.value for member in enum]
            assert len(values) == len(set(values)), enum.__name__


class TestPayloads:
    def test_every_spec_renders_to_a_json_safe_payload(self) -> None:
        import json

        for payload in (
            a_dependence(correlation=0.1, source="a pilot").payload(),
            an_estimator().payload(),
            a_target().payload(),
            a_frame().payload(),
        ):
            json.dumps(payload)
