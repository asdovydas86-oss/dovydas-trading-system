"""The gate's rule, one test per branch, plus the two boundaries it must hold.

The two boundaries are the milestone's whole point:

* a **holdout** may never inform a design, so a realised width measured on one is
  refused as an input rather than warned about;
* a **post-hoc** diagnostic may never be presented as prospective power, so the
  mode travels on the object that carries the number and there is no argument
  that sets it.
"""

from __future__ import annotations

import pytest

from fmis.research_design.models import (
    AssessmentMode,
    DesignVerdict,
    EstimatorKind,
    GrowthPath,
    LimitingFactor,
    ResearchDesignError,
    ResolutionCriterion,
    SampleRole,
)
from fmis.research_design.resolution import post_hoc_resolution, prospective_design
from fmis.research_design.verdict import assess_research_design
from tests.research_design_helpers import (
    OTHER_UNIT,
    UNIT,
    a_dependence,
    a_frame,
    a_question,
    a_target,
    an_effect,
    an_estimator,
)

CORRELATIONS = (0.0, 0.05, 0.10, 0.20, 0.50)


def _post_hoc(frame, width=0.5578, effect=None, target=None, estimator=None):
    return post_hoc_resolution(
        frame=frame,
        observed_half_width=width,
        effect=effect or an_effect(),
        target=target or a_target(),
        estimator=estimator or an_estimator(),
    )


def _assess(**overrides):
    """Build a valid assessment and vary exactly what a test names.

    A malformed ``effect``, ``target`` or ``estimator`` is passed to the GATE
    only: the resolution is always built from valid specs, so a type test
    exercises the gate's own guard rather than the resolution builder's.
    """
    frame = overrides.pop("frame", None) or a_frame()
    frames = overrides.pop("frames", (frame,))
    effect = overrides.get("effect") or an_effect()
    target = overrides.get("target") or a_target()
    estimator = overrides.get("estimator") or an_estimator()
    if not isinstance(effect, type(an_effect())):
        effect = an_effect()
    if not isinstance(target, type(a_target())):
        target = a_target()
    if not isinstance(estimator, type(an_estimator())):
        estimator = an_estimator()
    resolution = overrides.pop("resolution", None) or _post_hoc(
        frame, overrides.pop("width", 0.5578), effect=effect, target=target,
        estimator=estimator,
    )
    kwargs = dict(
        assessment_id="a-1",
        question=a_question(),
        effect=overrides.pop("effect", effect),
        uncertainty_unit=UNIT,
        dependence=a_dependence(),
        estimator=overrides.pop("estimator", estimator),
        target=overrides.pop("target", target),
        frames=frames,
        primary_sample=frame.name,
        resolution=resolution,
        sensitivity_correlations=CORRELATIONS,
    )
    kwargs.update(overrides)
    return assess_research_design(**kwargs)


class TestTheOrderedRule:
    def test_no_observations_is_not_measurable(self) -> None:
        frame = a_frame(
            observations=0, clusters=0, experimental_units=0, largest_cluster_share=None
        )
        assessment = _assess(
            frame=frame,
            resolution=post_hoc_resolution(
                frame=frame, observed_half_width=0.5, effect=an_effect(),
                target=a_target(), estimator=an_estimator(),
            ),
        )
        assert assessment.verdict is DesignVerdict.NOT_MEASURABLE
        assert assessment.limiting_factor is LimitingFactor.OBSERVATION_COUNT

    def test_one_observation_is_not_measurable(self) -> None:
        frame = a_frame(
            observations=1, clusters=1, experimental_units=1, largest_cluster_share=1.0
        )
        assert _assess(frame=frame).verdict is DesignVerdict.NOT_MEASURABLE

    def test_a_unit_mismatch_beats_every_other_finding(self) -> None:
        """Even a design that resolves its effect is refused on a unit mismatch."""
        assessment = _assess(uncertainty_unit=OTHER_UNIT, width=0.01)
        assert assessment.verdict is DesignVerdict.MISALIGNED_UNIT
        assert assessment.limiting_factor is LimitingFactor.UNIT_MISMATCH

    def test_too_few_clusters_is_insufficient_independence(self) -> None:
        assessment = _assess(
            frame=a_frame(clusters=3, largest_cluster_share=0.4),
            target=a_target(minimum_clusters=8),
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_COUNT

    def test_too_few_time_blocks_is_insufficient_independence(self) -> None:
        assessment = _assess(
            frame=a_frame(time_blocks=1), target=a_target(minimum_time_blocks=4)
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.TIME_BLOCKS

    def test_exactly_the_minimum_cluster_count_is_ACCEPTED(self) -> None:
        """A "minimum" is inclusive. Pinned because a mutation probe survived here.

        `clusters < minimum` and `clusters <= minimum` behave identically on every
        input except the boundary, so nothing else in the suite can tell them
        apart — and a design holding exactly the cluster count it declared as
        sufficient must not be rejected for holding it.
        """
        assessment = _assess(
            frame=a_frame(clusters=8, largest_cluster_share=0.2),
            target=a_target(minimum_clusters=8),
        )
        assert assessment.verdict is not DesignVerdict.INSUFFICIENT_INDEPENDENCE

    def test_one_cluster_below_the_minimum_is_REFUSED(self) -> None:
        assessment = _assess(
            frame=a_frame(clusters=7, largest_cluster_share=0.2),
            target=a_target(minimum_clusters=8),
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_COUNT

    def test_exactly_the_maximum_cluster_share_is_ACCEPTED(self) -> None:
        """A "maximum" is inclusive. Pinned because a mutation probe survived here."""
        assessment = _assess(
            frame=a_frame(largest_cluster_share=0.40),
            target=a_target(maximum_cluster_share=0.40),
        )
        assert assessment.verdict is not DesignVerdict.INSUFFICIENT_INDEPENDENCE

    def test_a_hair_above_the_maximum_cluster_share_is_REFUSED(self) -> None:
        assessment = _assess(
            frame=a_frame(largest_cluster_share=0.4001),
            target=a_target(maximum_cluster_share=0.40),
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_CONCENTRATION

    def test_exactly_the_minimum_time_block_count_is_ACCEPTED(self) -> None:
        assessment = _assess(
            frame=a_frame(time_blocks=4), target=a_target(minimum_time_blocks=4)
        )
        assert assessment.verdict is not DesignVerdict.INSUFFICIENT_INDEPENDENCE

    def test_one_cluster_dominating_is_insufficient_independence(self) -> None:
        assessment = _assess(
            frame=a_frame(largest_cluster_share=0.99),
            target=a_target(maximum_cluster_share=0.40),
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_CONCENTRATION

    def test_an_estimator_that_ignores_declared_clustering_is_refused(self) -> None:
        assessment = _assess(estimator=an_estimator(kind=EstimatorKind.PAIRED_BOOTSTRAP))
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.ESTIMATOR_RESOLUTION

    def test_an_unclustered_sample_may_use_an_unclustered_estimator(self) -> None:
        """One observation per cluster IS independence; the guard must not misfire."""
        assessment = _assess(
            frame=a_frame(observations=40, clusters=40, largest_cluster_share=0.025),
            estimator=an_estimator(kind=EstimatorKind.PAIRED_BOOTSTRAP),
        )
        assert assessment.verdict is not DesignVerdict.INSUFFICIENT_INDEPENDENCE

    def test_a_wide_interval_is_underpowered(self) -> None:
        assessment = _assess(width=0.5578)
        assert assessment.verdict is DesignVerdict.UNDERPOWERED

    def test_a_design_that_resolves_with_caveats_is_limited(self) -> None:
        assessment = _assess(width=0.01)
        assert assessment.verdict is DesignVerdict.LIMITED
        assert assessment.limiting_factor is LimitingFactor.NONE
        assert assessment.caveats

    def test_a_design_that_resolves_with_nothing_to_caveat_is_ready(self) -> None:
        assessment = _assess(
            width=0.01,
            dependence=a_dependence(
                correlation=0.05, source="a measured pilot", overlapping_horizon=0
            ),
        )
        assert assessment.verdict is DesignVerdict.READY
        assert assessment.caveats == ()

    def test_the_verdict_never_endorses_the_hypothesis(self) -> None:
        assert _assess().verdict.says_nothing_about_the_hypothesis


class TestTheBindingDimension:
    def test_a_positive_correlation_makes_the_cluster_count_binding(self) -> None:
        assessment = _assess()
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_COUNT

    def test_at_zero_correlation_only_the_observation_count_binds(self) -> None:
        assessment = _assess(
            dependence=a_dependence(correlation=0.0, source="assumed independent"),
            sensitivity_correlations=(0.0,),
        )
        assert assessment.limiting_factor is LimitingFactor.OBSERVATION_COUNT

    def test_an_information_cap_makes_the_effect_size_binding(self) -> None:
        assessment = _assess(
            dependence=a_dependence(correlation=0.0, source="assumed independent"),
            sensitivity_correlations=(0.0,),
            target=a_target(maximum_information_multiple=5.0),
        )
        assert assessment.limiting_factor is LimitingFactor.EFFECT_SIZE

    def test_a_generous_cap_leaves_the_observation_count_binding(self) -> None:
        assessment = _assess(
            dependence=a_dependence(correlation=0.0, source="assumed independent"),
            sensitivity_correlations=(0.0,),
            target=a_target(maximum_information_multiple=1000.0),
        )
        assert assessment.limiting_factor is LimitingFactor.OBSERVATION_COUNT

    def test_the_binding_correlation_is_the_declared_one_when_there_is_one(self) -> None:
        assessment = _assess(
            dependence=a_dependence(correlation=0.0, source="assumed independent")
        )
        assert any("declared intracluster correlation 0.0" in item
                   for item in assessment.assumptions)

    def test_the_binding_correlation_is_the_least_favourable_when_undeclared(self) -> None:
        assessment = _assess()
        assert any("largest of the declared sensitivity range" in item
                   for item in assessment.assumptions)


class TestHoldoutDiscipline:
    def test_a_realised_holdout_width_may_not_decide_a_design(self) -> None:
        frame = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        with pytest.raises(ResearchDesignError, match="already spent it"):
            _assess(frame=frame)

    def test_a_prospective_assessment_of_a_holdout_is_permitted(self) -> None:
        """It consumes an ASSUMED dispersion, so the holdout is not opened."""
        frame = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        assessment = _assess(
            frame=frame,
            resolution=prospective_design(
                frame=frame,
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a prior milestone's published summary",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            ),
        )
        assert assessment.mode is AssessmentMode.PROSPECTIVE

    def test_a_validation_sample_may_inform_a_design(self) -> None:
        frame = a_frame(name="validation", role=SampleRole.VALIDATION)
        assert _assess(frame=frame).mode is AssessmentMode.POST_HOC

    def test_the_profile_of_a_holdout_reads_no_outcome(self) -> None:
        """Every field is metadata, so an unopened holdout can still be profiled."""
        frame = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        assessment = _assess(
            frame=a_frame(),
            frames=(a_frame(), frame),
            resolution=_post_hoc(a_frame()),
        )
        profile = next(item for item in assessment.profiles if item.sample == "holdout")
        assert profile.observations == frame.observations
        assert profile.clusters == frame.clusters


class TestInputDiscipline:
    def test_no_frames_at_all_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least one sample frame"):
            _assess(frames=())

    def test_a_primary_sample_not_among_the_frames_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="not among the declared frames"):
            _assess(primary_sample="nowhere")

    def test_a_resolution_describing_another_sample_is_refused(self) -> None:
        other = a_frame(name="validation", role=SampleRole.VALIDATION,
                        starts_at=a_frame().ends_at)
        with pytest.raises(ResearchDesignError, match="pooling defect"):
            _assess(frames=(a_frame(), other), resolution=_post_hoc(other))

    def test_an_empty_sensitivity_range_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least one intracluster"):
            _assess(sensitivity_correlations=())

    def test_a_sensitivity_range_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match=r"lie in \[0, 1\]"):
            _assess(sensitivity_correlations=(0.0, 1.5))

    def test_a_range_that_excludes_the_declared_correlation_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="does not contain it"):
            _assess(
                dependence=a_dependence(correlation=0.30, source="a pilot"),
                sensitivity_correlations=(0.0, 0.10),
            )

    def test_an_empty_assessment_id_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="assessment_id"):
            _assess(assessment_id="  ")

    def test_a_label_cannot_be_passed_instead_of_a_resolution(self) -> None:
        with pytest.raises(TypeError, match="cannot be passed as a label"):
            _assess(resolution="prospective")

    @pytest.mark.parametrize(
        "field", ("question", "effect", "uncertainty_unit", "dependence", "estimator", "target")
    )
    def test_a_wrong_type_is_a_programmer_error(self, field: str) -> None:
        with pytest.raises(TypeError):
            _assess(**{field: "not the right type"})

    def test_a_non_frame_in_the_frame_list_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError):
            _assess(frames=(a_frame(), "validation"))


class TestTheAssessment:
    def test_it_carries_a_profile_for_every_frame(self) -> None:
        other = a_frame(name="validation", role=SampleRole.VALIDATION,
                        starts_at=a_frame().ends_at)
        assessment = _assess(frames=(a_frame(), other))
        assert [item.sample for item in assessment.profiles] == ["development", "validation"]

    def test_the_requirement_lookup_finds_a_computed_row(self) -> None:
        assessment = _assess()
        row = assessment.requirement(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.10)
        assert row.required_clusters == 467

    def test_the_requirement_lookup_refuses_a_row_it_did_not_compute(self) -> None:
        with pytest.raises(ResearchDesignError, match="no requirement was computed"):
            _assess().requirement(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.99)

    def test_the_independent_path_is_reported_once_not_per_correlation(self) -> None:
        assessment = _assess()
        rows = [
            item for item in assessment.requirements
            if item.path is GrowthPath.INDEPENDENT_OBSERVATIONS
        ]
        assert len(rows) == 1

    def test_repeated_measurement_of_one_unit_is_carried_as_a_caveat(self) -> None:
        assessment = _assess(dependence=a_dependence(repeated=True))
        assert any("not exchangeable even within a cluster" in item
                   for item in assessment.caveats)

    def test_more_observations_than_units_is_carried_as_a_caveat(self) -> None:
        """The gate-ladder failure, stated as a caveat rather than left implicit."""
        assessment = _assess(
            frame=a_frame(observations=155, experimental_units=40)
        )
        assert any("the unit of evidence is the coarser count" in item
                   for item in assessment.caveats)

    def test_an_unstated_concentration_is_carried_as_a_caveat(self) -> None:
        assessment = _assess(frame=a_frame(largest_cluster_share=None))
        assert any("An unchecked bound is not a passed one" in item
                   for item in assessment.caveats)

    def test_a_concentration_near_its_bound_is_carried_as_a_caveat(self) -> None:
        assessment = _assess(
            frame=a_frame(largest_cluster_share=0.35),
            target=a_target(maximum_cluster_share=0.40),
        )
        assert any("within 25 % of its" in item for item in assessment.caveats)

    def test_the_coin_flip_criterion_is_named_as_an_assumption(self) -> None:
        assert any("coin-flip" not in item and "about half the time" in item
                   for item in _assess().assumptions)

    def test_a_powered_target_does_not_carry_the_coin_flip_note(self) -> None:
        target = a_target(criterion=ResolutionCriterion.POWERED_DETECTION, power=0.8)
        assessment = _assess(target=target, estimator=an_estimator())
        assert not any("about half the time" in item for item in assessment.assumptions)

    def test_the_payload_is_json_safe_and_complete(self) -> None:
        import json

        payload = _assess().payload()
        json.dumps(payload)
        assert payload["verdict"] == "underpowered"
        assert payload["mode"] == "post_hoc"
        assert payload["effect"]["magnitude"] == "0.10"

    def test_the_resolvable_half_width_is_the_resolution_s_own(self) -> None:
        assessment = _assess(width=0.42)
        assert assessment.resolvable_half_width == pytest.approx(0.42)
