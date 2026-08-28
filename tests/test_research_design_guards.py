"""Every type guard, fired once. **A guard nobody has seen fire is untested.**

These are cheap and they are not ceremony. Each one is the difference between a
caller's mistake surfacing as a named error and it surfacing three frames later
as an `AttributeError` on a float — or worse, as a plausible number. The
milestone's governing rule is that programmer errors propagate rather than
becoming "insufficient data", and this file is where that rule is checked
one branch at a time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fmis.research_design.dependence import (
    design_effect,
    effective_observations,
    profile_of,
)
from fmis.research_design.models import (
    ComparisonType,
    DependenceModel,
    DesignTarget,
    EffectDirection,
    EstimatorKind,
    EstimatorSpec,
    MeaningfulEffect,
    ResearchDesignError,
    ResearchQuestion,
    ResolutionCriterion,
    SampleFrame,
    SampleRole,
)
from fmis.research_design.numeric import (
    derive_seed,
    largest_share,
    nearest_rank_quantile,
    one_sided_z,
    two_sided_z,
)
from fmis.research_design.resolution import (
    ClusteredObservation,
    cluster_bootstrap,
    half_width_for_design,
    information_inflation,
    observation_dispersion_from_half_width,
    post_hoc_resolution,
    prospective_design,
    required_information,
)
from fmis.research_design.verdict import assess_research_design
from tests.research_design_helpers import (
    UNIT,
    a_dependence,
    a_frame,
    a_question,
    a_target,
    an_effect,
    an_estimator,
)

UTC = timezone.utc


class TestNumericGuards:
    def test_a_non_int_master_seed_is_refused(self) -> None:
        for bad in ("1", 1.0, True, None):
            with pytest.raises(ResearchDesignError, match="master must be an int"):
                derive_seed(master=bad, parts=("a",))  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ("half", None, True))
    def test_a_non_numeric_confidence_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="must be a real number"):
            two_sided_z(bad)

    @pytest.mark.parametrize("bad", (0.0, 1.0, -0.5, 2.0))
    def test_a_confidence_outside_the_open_unit_interval_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="strictly inside"):
            two_sided_z(bad)

    @pytest.mark.parametrize("bad", ("half", None, True))
    def test_a_non_numeric_probability_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="must be a real number"):
            one_sided_z(bad)

    @pytest.mark.parametrize("bad", (0.0, 1.0, -1.0))
    def test_a_probability_outside_the_open_unit_interval_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="strictly inside"):
            one_sided_z(bad)

    def test_the_two_quantiles_are_the_ones_a_reader_expects(self) -> None:
        assert two_sided_z(0.95) == pytest.approx(1.959963, abs=1e-5)
        assert one_sided_z(0.80) == pytest.approx(0.841621, abs=1e-5)

    def test_a_bool_fraction_is_refused_rather_than_read_as_zero_or_one(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a real number"):
            nearest_rank_quantile([1, 2, 3], True)

    def test_the_quantile_boundaries_return_the_extremes(self) -> None:
        assert nearest_rank_quantile([3, 1, 2], 0.0) == 1
        assert nearest_rank_quantile([3, 1, 2], 1.0) == 3

    def test_a_negative_contribution_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="negative magnitude"):
            largest_share([("a", -1.0)])


class TestDependenceGuards:
    @pytest.mark.parametrize("bad", ("ten", None, True))
    def test_a_non_numeric_cluster_size_is_refused(self, bad) -> None:
        with pytest.raises(
            ResearchDesignError, match="observations_per_cluster must be a real number"
        ):
            design_effect(bad, 0.1)

    @pytest.mark.parametrize("bad", ("some", None, True))
    def test_a_non_numeric_correlation_is_refused(self, bad) -> None:
        with pytest.raises(
            ResearchDesignError, match="intracluster_correlation must be a real number"
        ):
            design_effect(10.0, bad)

    @pytest.mark.parametrize("bad", (-0.1, 1.1))
    def test_a_correlation_outside_zero_to_one_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match=r"lie in \[0, 1\]"):
            design_effect(10.0, bad)

    @pytest.mark.parametrize("bad", ("many", None, True))
    def test_a_non_int_observation_count_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="observations must be an int"):
            effective_observations(bad, 10.0, 0.1)

    def test_a_non_frame_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError, match="frame must be a SampleFrame"):
            profile_of("development", a_dependence())  # type: ignore[arg-type]

    def test_a_non_dependence_model_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError, match="must be a DependenceModel"):
            profile_of(a_frame(), "clustered")  # type: ignore[arg-type]

    def test_a_profile_reports_whether_it_carries_an_effective_estimate(self) -> None:
        without = profile_of(a_frame(), a_dependence())
        assert not without.has_effective_estimate
        withit = profile_of(
            a_frame(), a_dependence(correlation=0.1, source="a measured pilot")
        )
        assert withit.has_effective_estimate
        assert withit.effective_observations < withit.observations

    def test_a_frame_with_no_cluster_has_no_design_effect(self) -> None:
        empty = a_frame(
            observations=0, clusters=0, experimental_units=0, largest_cluster_share=None
        )
        profile = profile_of(
            empty, a_dependence(correlation=0.1, source="a measured pilot")
        )
        assert profile.design_effect is None
        assert "undefined for it" in profile.derivation

    def test_the_profile_payload_is_json_safe(self) -> None:
        import json

        json.dumps(profile_of(a_frame(), a_dependence()).payload())


class TestModelGuards:
    def test_a_non_int_count_is_refused_with_its_own_type_named(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be an int, got str"):
            a_frame(observations="many")  # type: ignore[arg-type]

    def test_a_non_numeric_share_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a real number"):
            a_frame(largest_cluster_share="a lot")  # type: ignore[arg-type]

    def test_a_non_unit_effect_unit_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a MetricUnit"):
            MeaningfulEffect(
                magnitude=Decimal("0.1"), unit="atr",  # type: ignore[arg-type]
                direction=EffectDirection.GREATER, rationale="r", source="s",
            )

    def test_a_non_direction_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be an EffectDirection"):
            MeaningfulEffect(
                magnitude=Decimal("0.1"), unit=UNIT,
                direction="up",  # type: ignore[arg-type]
                rationale="r", source="s",
            )

    def test_a_non_role_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a SampleRole"):
            a_frame(role="development")  # type: ignore[arg-type]

    def test_a_non_datetime_boundary_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be datetimes"):
            SampleFrame(
                name="d", role=SampleRole.DEVELOPMENT, population="p",
                observations=10, clusters=2, time_blocks=1, experimental_units=10,
                starts_at="2024-01-01",  # type: ignore[arg-type]
                ends_at=datetime(2024, 2, 1, tzinfo=UTC),
            )

    def test_a_zero_share_is_refused_by_the_uniform_bound(self) -> None:
        """One cluster must hold all of it; a zero share is arithmetically impossible."""
        with pytest.raises(ResearchDesignError, match="cannot be below the uniform"):
            SampleFrame(
                name="d", role=SampleRole.DEVELOPMENT, population="p",
                observations=10, clusters=1, time_blocks=1, experimental_units=10,
                starts_at=datetime(2024, 1, 1, tzinfo=UTC),
                ends_at=datetime(2024, 2, 1, tzinfo=UTC),
                largest_cluster_share=0.0,
            )

    def test_a_non_bool_repeated_measurement_flag_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a bool"):
            DependenceModel(
                unit_of_evidence="u", cluster_axis="symbol", overlapping_horizon=0,
                repeated_measurements="yes",  # type: ignore[arg-type]
                intracluster_correlation=None, correlation_source=None,
                assumptions=("a",),
            )

    def test_a_non_kind_estimator_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be an EstimatorKind"):
            EstimatorSpec(
                kind="bootstrap",  # type: ignore[arg-type]
                comparison=ComparisonType.PAIRED_DIFFERENCE, resamples=100,
                confidence=0.95, assumptions=("a",), rationale="r",
            )

    def test_a_non_comparison_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a ComparisonType"):
            EstimatorSpec(
                kind=EstimatorKind.CLUSTER_BOOTSTRAP,
                comparison="paired",  # type: ignore[arg-type]
                resamples=100, confidence=0.95, assumptions=("a",), rationale="r",
            )

    def test_a_resampling_estimator_with_no_replicate_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least one replicate"):
            EstimatorSpec(
                kind=EstimatorKind.CLUSTER_BOOTSTRAP,
                comparison=ComparisonType.PAIRED_DIFFERENCE, resamples=0,
                confidence=0.95, assumptions=("a",), rationale="r",
            )

    def test_a_non_criterion_target_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a ResolutionCriterion"):
            a_target(criterion="interval")  # type: ignore[arg-type]

    def test_a_non_numeric_information_cap_is_refused(self) -> None:
        with pytest.raises(
            ResearchDesignError, match="maximum_information_multiple must be a real number"
        ):
            a_target(maximum_information_multiple="lots")  # type: ignore[arg-type]

    def test_a_non_comparison_research_question_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a ComparisonType"):
            ResearchQuestion(
                question_id="q", description="d", primary_metric="m",
                comparison="paired",  # type: ignore[arg-type]
            )

    def test_an_information_cap_of_exactly_one_is_the_supported_boundary(self) -> None:
        assert a_target(maximum_information_multiple=1.0).maximum_information_multiple == 1.0


class TestResolutionGuards:
    def test_a_non_numeric_observation_value_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="value must be a real number"):
            ClusteredObservation(cluster="C1", value="high")  # type: ignore[arg-type]

    def test_a_non_numeric_confidence_is_refused_by_the_bootstrap(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be a real number"):
            cluster_bootstrap(
                (ClusteredObservation(cluster="C1", value=1.0),),
                confidence="95%",  # type: ignore[arg-type]
                resamples=10, master_seed=1, identity=["a"],
            )

    def test_a_non_target_cannot_inflate_information(self) -> None:
        with pytest.raises(TypeError, match="must be a DesignTarget"):
            information_inflation("95%")  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ("wide", None, True))
    def test_a_non_numeric_dispersion_is_refused(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="observation_sd must be a real number"):
            half_width_for_design(
                observation_sd=bad, clusters=5, observations_per_cluster=10.0,
                intracluster_correlation=0.0, confidence=0.95,
            )

    @pytest.mark.parametrize("bad", ("wide", None, True))
    def test_a_non_numeric_half_width_cannot_be_inverted(self, bad) -> None:
        with pytest.raises(ResearchDesignError, match="half_width must be a real number"):
            observation_dispersion_from_half_width(
                half_width=bad, clusters=5, observations=50,
                intracluster_correlation=0.0, confidence=0.95,
            )

    def test_a_non_int_cluster_count_cannot_be_inverted(self) -> None:
        with pytest.raises(ResearchDesignError, match="clusters must be a positive int"):
            observation_dispersion_from_half_width(
                half_width=0.5, clusters="five",  # type: ignore[arg-type]
                observations=50, intracluster_correlation=0.0, confidence=0.95,
            )

    def test_a_non_int_observation_count_cannot_be_inverted(self) -> None:
        with pytest.raises(ResearchDesignError, match="observations must be an int"):
            observation_dispersion_from_half_width(
                half_width=0.5, clusters=5,
                observations="fifty",  # type: ignore[arg-type]
                intracluster_correlation=0.0, confidence=0.95,
            )

    def test_a_non_frame_cannot_be_diagnosed(self) -> None:
        with pytest.raises(TypeError, match="frame must be a SampleFrame"):
            post_hoc_resolution(
                frame="development",  # type: ignore[arg-type]
                observed_half_width=0.5, effect=an_effect(), target=a_target(),
                estimator=an_estimator(),
            )

    def test_a_non_estimator_cannot_be_diagnosed(self) -> None:
        with pytest.raises(TypeError, match="estimator must be an EstimatorSpec"):
            post_hoc_resolution(
                frame=a_frame(), observed_half_width=0.5, effect=an_effect(),
                target=a_target(),
                estimator="bootstrap",  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("bad", ("wide", None, True))
    def test_a_non_numeric_observed_width_is_refused(self, bad) -> None:
        with pytest.raises(
            ResearchDesignError, match="observed_half_width must be a real number"
        ):
            post_hoc_resolution(
                frame=a_frame(), observed_half_width=bad, effect=an_effect(),
                target=a_target(), estimator=an_estimator(),
            )

    def test_a_non_frame_cannot_be_planned_for(self) -> None:
        with pytest.raises(TypeError, match="frame must be a SampleFrame"):
            prospective_design(
                frame="holdout",  # type: ignore[arg-type]
                assumed_observation_sd=1.0, assumed_intracluster_correlation=0.0,
                dispersion_source="a pilot", effect=an_effect(), target=a_target(),
                estimator=an_estimator(),
            )

    def test_a_non_estimator_cannot_be_planned_for(self) -> None:
        with pytest.raises(TypeError, match="estimator must be an EstimatorSpec"):
            prospective_design(
                frame=a_frame(), assumed_observation_sd=1.0,
                assumed_intracluster_correlation=0.0, dispersion_source="a pilot",
                effect=an_effect(), target=a_target(),
                estimator="bootstrap",  # type: ignore[arg-type]
            )

    def test_a_prospective_design_reports_its_counts_under_the_shared_names(self) -> None:
        design = prospective_design(
            frame=a_frame(), assumed_observation_sd=1.0,
            assumed_intracluster_correlation=0.0, dispersion_source="a pilot",
            effect=an_effect(), target=a_target(), estimator=an_estimator(),
        )
        assert design.observations == design.planned_observations == 155
        assert design.clusters == design.planned_clusters == 15

    def test_a_non_int_observation_count_cannot_be_planned_from(self) -> None:
        with pytest.raises(ResearchDesignError, match="observations must be an int"):
            required_information(
                path=__import__(
                    "fmis.research_design.models", fromlist=["GrowthPath"]
                ).GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
                observed_half_width=0.5,
                observations="many",  # type: ignore[arg-type]
                clusters=15, intracluster_correlation=0.0,
                effect=an_effect(), target=a_target(),
            )

    def test_every_reading_renders_a_json_safe_payload(self) -> None:
        import json

        frame = a_frame()
        json.dumps(
            cluster_bootstrap(
                (ClusteredObservation(cluster="C1", value=1.0),
                 ClusteredObservation(cluster="C2", value=2.0)),
                confidence=0.95, resamples=50, master_seed=1, identity=["a"],
            ).payload()
        )
        json.dumps(
            post_hoc_resolution(
                frame=frame, observed_half_width=0.5, effect=an_effect(),
                target=a_target(), estimator=an_estimator(),
            ).payload()
        )
        json.dumps(
            prospective_design(
                frame=frame, assumed_observation_sd=1.0,
                assumed_intracluster_correlation=0.0, dispersion_source="a pilot",
                effect=an_effect(), target=a_target(), estimator=an_estimator(),
            ).payload()
        )


class TestAdapterGuards:
    def test_an_unknown_sample_is_refused_by_name(self) -> None:
        from fmis.swing_lab.admission_power import ca_post_hoc
        from fmis.swing_lab.models import SwingLabError

        with pytest.raises(SwingLabError, match="no published CA figure"):
            ca_post_hoc("nowhere")

    def test_a_published_figure_naming_no_sealed_sample_is_refused(self) -> None:
        """The two lists must agree; a CB figure for a sample BY never declared
        would build a frame with an invented window."""
        from fmis.swing_lab.admission_power import _spec
        from fmis.swing_lab.models import SwingLabError

        with pytest.raises(SwingLabError, match="declares no sample named"):
            _spec("pilot")

    def test_every_published_ca_sample_is_a_sealed_by_sample(self) -> None:
        from fmis.swing_lab.admission_power import CA_PUBLISHED, _spec

        for figure in CA_PUBLISHED:
            assert _spec(figure.sample).name == figure.sample


class TestTheGateRejectsMalformedFrames:
    def test_a_powered_target_is_carried_through_to_the_verdict(self) -> None:
        frame = a_frame()
        target = a_target(
            criterion=ResolutionCriterion.POWERED_DETECTION, power=0.80
        )
        assessment = assess_research_design(
            assessment_id="a",
            question=a_question(),
            effect=an_effect(),
            uncertainty_unit=UNIT,
            dependence=a_dependence(),
            estimator=an_estimator(),
            target=target,
            frames=(frame,),
            primary_sample=frame.name,
            resolution=post_hoc_resolution(
                frame=frame, observed_half_width=0.5578, effect=an_effect(),
                target=target, estimator=an_estimator(),
            ),
            sensitivity_correlations=(0.0, 0.10),
        )
        assert assessment.target.power == 0.80
        assert assessment.payload()["target"]["power"] == 0.80
