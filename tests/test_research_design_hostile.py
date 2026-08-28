"""Hostile review. **Every probe the milestone brief names, as a checklist.**

Some of these overlap the focused suites deliberately. A hostile review is only
useful if it can be read straight through as *"here is what was attacked and here
is what happened"*, and a probe that lives only inside a class about bootstrap
mechanics is not readable that way.

The governing rule for the whole file: **programmer errors propagate.** A negative
sample size, an impossible confidence and a malformed unit each raise. None of
them is folded into `NOT_MEASURABLE`, because "insufficient data" and "you passed
nonsense" are different facts and a gate that reports the second as the first has
converted a bug into a finding.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal

import pytest

from fmis.research_design.dependence import design_effect, effective_observations, profile_of
from fmis.research_design.models import (
    AssessmentMode,
    DesignVerdict,
    EstimatorKind,
    GrowthPath,
    LimitingFactor,
    MeaningfulEffect,
    ResearchDesignError,
    ResolutionCriterion,
    SampleRole,
)
from fmis.research_design.resolution import (
    ClusteredObservation,
    cluster_bootstrap,
    post_hoc_resolution,
    required_information,
)
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
    clustered_sample,
)

CORRELATIONS = (0.0, 0.05, 0.10, 0.20, 0.50)


def _assess(frame, width=0.5578, **overrides):
    effect = overrides.pop("effect", an_effect())
    target = overrides.pop("target", a_target())
    estimator = overrides.pop("estimator", an_estimator())
    resolution = overrides.pop(
        "resolution",
        post_hoc_resolution(
            frame=frame, observed_half_width=width, effect=effect,
            target=target, estimator=estimator,
        ),
    )
    kwargs = dict(
        assessment_id="hostile",
        question=a_question(),
        effect=effect,
        uncertainty_unit=UNIT,
        dependence=a_dependence(),
        estimator=estimator,
        target=target,
        frames=(frame,),
        primary_sample=frame.name,
        resolution=resolution,
        sensitivity_correlations=CORRELATIONS,
    )
    kwargs.update(overrides)
    return assess_research_design(**kwargs)


class TestDegenerateSamples:
    def test_n_equals_zero_is_not_measurable(self) -> None:
        frame = a_frame(observations=0, clusters=0, experimental_units=0,
                        largest_cluster_share=None)
        assert _assess(frame).verdict is DesignVerdict.NOT_MEASURABLE

    def test_n_equals_one_is_not_measurable(self) -> None:
        frame = a_frame(observations=1, clusters=1, experimental_units=1,
                        largest_cluster_share=1.0)
        assert _assess(frame).verdict is DesignVerdict.NOT_MEASURABLE

    def test_a_negative_sample_size_raises_and_is_never_a_verdict(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be >= 0"):
            a_frame(observations=-5, clusters=0, experimental_units=0,
                    largest_cluster_share=None)

    def test_a_zero_cluster_count_with_observations_raises(self) -> None:
        with pytest.raises(ResearchDesignError, match="malformed frame"):
            a_frame(observations=100, clusters=0, largest_cluster_share=None)

    def test_a_single_cluster_is_insufficient_independence_not_underpowered(self) -> None:
        frame = a_frame(observations=100, clusters=1, largest_cluster_share=1.0)
        assessment = _assess(frame, target=a_target(minimum_clusters=2))
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_COUNT

    def test_one_cluster_holding_ninety_nine_percent_is_refused(self) -> None:
        frame = a_frame(clusters=15, largest_cluster_share=0.99)
        assessment = _assess(frame)
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.CLUSTER_CONCENTRATION

    def test_every_observation_in_one_time_block_is_refused(self) -> None:
        frame = a_frame(time_blocks=1)
        assessment = _assess(frame, target=a_target(minimum_time_blocks=2))
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE
        assert assessment.limiting_factor is LimitingFactor.TIME_BLOCKS


class TestDegenerateData:
    def test_perfectly_identical_observations_give_a_zero_width_interval(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster=f"C{i % 5}", value=1.0) for i in range(50)
        )
        assert cluster_bootstrap(
            observations, confidence=0.95, resamples=200, master_seed=1, identity=["h"]
        ).half_width == 0.0

    def test_a_zero_width_interval_can_never_become_a_resolution(self) -> None:
        """**The failure this closes.** A zero-width interval resolves every effect.

        Perfectly correlated clusters produce one: resampling identical clusters
        returns identical means whatever is drawn, so the bootstrap cannot see the
        dependence and reports a width of zero. If that could be handed to
        `post_hoc_resolution` the design would be reported READY on data carrying
        no independent information at all. It fails closed instead.
        """
        with pytest.raises(ResearchDesignError, match="finite and strictly positive"):
            post_hoc_resolution(
                frame=a_frame(),
                observed_half_width=0.0,
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            )

    def test_symbols_grow_but_the_data_is_perfectly_correlated(self) -> None:
        """100 clusters that move identically carry the information of one."""
        observations = tuple(
            ClusteredObservation(cluster=f"S{i:03d}", value=float(j))
            for i in range(100)
            for j in range(10)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["h"]
        )
        assert reading.clusters == 100
        assert reading.observations == 1000
        assert reading.half_width == 0.0
        with pytest.raises(ResearchDesignError):
            post_hoc_resolution(
                frame=a_frame(observations=1000, clusters=100,
                              largest_cluster_share=0.01),
                observed_half_width=reading.half_width,
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            )

    def test_rows_grow_but_clusters_do_not(self) -> None:
        """Ten clusters at ten and at a thousand rows: the width must plateau."""
        widths = []
        for per_cluster in (10, 100, 1000):
            observations = clustered_sample(
                clusters=10, per_cluster=per_cluster,
                between_sd=1.0, within_sd=1.0, seed=3,
            )
            widths.append(
                cluster_bootstrap(
                    observations, confidence=0.95, resamples=500,
                    master_seed=1, identity=["h", per_cluster],
                ).half_width
            )
        assert widths[2] > 0.5 * widths[0], (
            "a hundredfold increase in rows inside the same clusters must not "
            f"behave like a hundredfold increase in information: {widths}"
        )

    def test_all_positive_observations_give_an_interval_excluding_zero(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster=f"C{i % 10}", value=1.0 + i * 0.01)
            for i in range(100)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["h"]
        )
        assert reading.point > 0
        assert reading.low > 0
        assert reading.excludes_zero

    def test_all_negative_observations_give_an_interval_excluding_zero(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster=f"C{i % 10}", value=-1.0 - i * 0.01)
            for i in range(100)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["h"]
        )
        assert reading.high < 0
        assert reading.excludes_zero

    def test_huge_variance_widens_the_interval_rather_than_breaking(self) -> None:
        small = cluster_bootstrap(
            clustered_sample(within_sd=1.0, seed=4),
            confidence=0.95, resamples=500, master_seed=1, identity=["a"],
        )
        huge = cluster_bootstrap(
            clustered_sample(within_sd=1_000_000.0, seed=4),
            confidence=0.95, resamples=500, master_seed=1, identity=["a"],
        )
        assert huge.half_width > 1000 * small.half_width

    def test_a_heavy_tailed_sample_is_measured_rather_than_refused(self) -> None:
        """Pareto-like magnitudes: the bootstrap assumes no distribution."""
        observations = tuple(
            ClusteredObservation(cluster=f"C{i % 12}", value=(i + 1) ** 3 * 0.001)
            for i in range(120)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["h"]
        )
        assert reading.half_width > 0
        assert reading.low < reading.point < reading.high

    def test_one_extreme_outlier_widens_the_interval_it_belongs_to(self) -> None:
        base = list(clustered_sample(clusters=10, per_cluster=10, seed=8))
        contaminated = base + [ClusteredObservation(cluster="C000", value=10_000.0)]
        clean = cluster_bootstrap(
            tuple(base), confidence=0.95, resamples=500, master_seed=1, identity=["a"]
        )
        dirty = cluster_bootstrap(
            tuple(contaminated), confidence=0.95, resamples=500,
            master_seed=1, identity=["a"],
        )
        assert dirty.half_width > clean.half_width

    def test_a_nan_or_infinite_observation_is_refused_at_construction(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ResearchDesignError, match="finite"):
                ClusteredObservation(cluster="C1", value=bad)


class TestMalformedDeclarations:
    def test_a_zero_effect_threshold_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="strictly positive"):
            an_effect("0")

    def test_an_effect_in_r_against_an_interval_in_atr_is_a_verdict_not_a_crash(self) -> None:
        """The brief's own example. It is a MISALIGNED_UNIT, reported as one."""
        assessment = _assess(a_frame(), uncertainty_unit=OTHER_UNIT)
        assert assessment.verdict is DesignVerdict.MISALIGNED_UNIT
        assert assessment.limiting_factor is LimitingFactor.UNIT_MISMATCH

    def test_a_unit_mismatch_is_not_rescued_by_a_narrow_interval(self) -> None:
        assessment = _assess(a_frame(), width=0.0001, uncertainty_unit=OTHER_UNIT)
        assert assessment.verdict is DesignVerdict.MISALIGNED_UNIT

    @pytest.mark.parametrize("bad", (0.0, 1.0, -0.5, 1.5, float("nan")))
    def test_an_impossible_confidence_is_refused(self, bad: float) -> None:
        with pytest.raises(ResearchDesignError):
            a_target(confidence=bad)

    def test_the_supported_confidence_boundary_is_the_replicate_count(self) -> None:
        """Exactly one replicate in the tail is allowed; fewer is not."""
        an_estimator(resamples=40, confidence=0.95)
        with pytest.raises(ResearchDesignError, match="extremum of the draws"):
            an_estimator(resamples=39, confidence=0.95)

    def test_an_effect_exactly_at_the_resolution_boundary_does_not_resolve(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(), observed_half_width=0.10, effect=an_effect("0.10"),
            target=a_target(), estimator=an_estimator(),
        )
        assert not reading.resolves_meaningful_effect

    def test_a_malformed_sample_boundary_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="not after it starts"):
            a_frame(months=0)

    def test_a_correlation_outside_zero_to_one_is_refused(self) -> None:
        for bad in (-0.1, 1.1):
            with pytest.raises(ResearchDesignError):
                a_dependence(correlation=bad, source="a pilot")

    def test_a_design_effect_below_one_cannot_be_produced(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least 1"):
            design_effect(0.5, 0.1)
        assert design_effect(1.0, 0.9) == pytest.approx(1.0)

    def test_effective_observations_never_exceed_the_observations(self) -> None:
        for correlation in (0.0, 0.01, 0.5, 1.0):
            assert effective_observations(1000, 10.0, correlation) <= 1000

    def test_a_negative_observation_count_cannot_reach_the_design_effect(self) -> None:
        with pytest.raises(ResearchDesignError, match="must be >= 0"):
            effective_observations(-1, 10.0, 0.1)


class TestSampleContamination:
    def test_a_validation_sample_overlapping_development_is_refused(self) -> None:
        development = a_frame(months=24)
        validation = a_frame(
            name="validation", role=SampleRole.VALIDATION,
            starts_at=development.starts_at, months=24,
        )
        with pytest.raises(ResearchDesignError, match="already been fitted"):
            _assess(development, frames=(development, validation))

    def test_a_holdout_outcome_can_never_decide_a_design(self) -> None:
        holdout = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        with pytest.raises(ResearchDesignError, match="already spent it"):
            _assess(holdout)

    def test_the_holdout_can_still_be_planned_for_without_being_opened(self) -> None:
        from fmis.research_design.resolution import prospective_design

        holdout = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        assessment = _assess(
            holdout,
            resolution=prospective_design(
                frame=holdout, assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a published prior summary",
                effect=an_effect(), target=a_target(), estimator=an_estimator(),
            ),
        )
        assert assessment.mode is AssessmentMode.PROSPECTIVE

    def test_a_holdout_profile_reads_only_metadata(self) -> None:
        holdout = a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h")
        profile = profile_of(holdout, a_dependence())
        assert profile.observations == holdout.observations
        assert profile.effective_observations is None


class TestModeIntegrity:
    def test_a_post_hoc_diagnostic_cannot_be_declared_prospective(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(), observed_half_width=0.5, effect=an_effect(),
            target=a_target(), estimator=an_estimator(),
        )
        assert reading.mode is AssessmentMode.POST_HOC
        with pytest.raises((AttributeError, TypeError)):
            reading.mode = AssessmentMode.PROSPECTIVE  # type: ignore[misc]

    def test_the_gate_takes_no_mode_argument_at_all(self) -> None:
        import inspect

        signature = inspect.signature(assess_research_design)
        assert "mode" not in signature.parameters

    def test_neither_resolution_type_has_a_mode_field(self) -> None:
        from fmis.research_design.resolution import PostHocResolution, ProspectiveDesign

        for kind in (PostHocResolution, ProspectiveDesign):
            assert "mode" not in {field for field in kind.__dataclass_fields__}

    def test_a_string_cannot_be_passed_where_a_resolution_belongs(self) -> None:
        with pytest.raises(TypeError, match="cannot be passed as a label"):
            _assess(a_frame(), resolution="prospective")


class TestImpossibleDesigns:
    def test_a_design_that_can_never_meet_its_target_says_so_rather_than_a_number(
        self,
    ) -> None:
        result = required_information(
            path=GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
            observed_half_width=0.5578, observations=155, clusters=15,
            intracluster_correlation=0.5, effect=an_effect("0.10"), target=a_target(),
        )
        assert not result.reachable
        assert result.required_observations is None
        assert "UNREACHABLE" in result.note

    def test_an_absurdly_small_effect_gives_a_finite_number_not_an_overflow(self) -> None:
        result = required_information(
            path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            observed_half_width=0.5578, observations=155, clusters=15,
            intracluster_correlation=0.0,
            effect=MeaningfulEffect(
                magnitude=Decimal("0.000000001"), unit=UNIT,
                direction=an_effect().direction, rationale="r", source="s",
            ),
            target=a_target(),
        )
        assert isinstance(result.required_observations, int)
        assert result.required_observations > 10**18

    def test_a_perfect_correlation_makes_more_history_worthless(self) -> None:
        result = required_information(
            path=GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
            observed_half_width=0.5578, observations=155, clusters=15,
            intracluster_correlation=1.0, effect=an_effect("0.10"), target=a_target(),
        )
        assert not result.reachable
        assert result.floor_half_width == pytest.approx(0.5578)


class TestDeterminismUnderAttack:
    def test_changing_the_master_seed_moves_the_interval(self) -> None:
        observations = clustered_sample()
        widths = {
            cluster_bootstrap(
                observations, confidence=0.95, resamples=300,
                master_seed=seed, identity=["d"],
            ).half_width
            for seed in (1, 2, 3, 4, 5)
        }
        assert len(widths) > 1

    def test_changing_the_master_seed_never_moves_the_point_estimate(self) -> None:
        observations = clustered_sample()
        points = {
            cluster_bootstrap(
                observations, confidence=0.95, resamples=300,
                master_seed=seed, identity=["d"],
            ).point
            for seed in (1, 2, 3, 4, 5)
        }
        assert len(points) == 1

    @pytest.mark.parametrize("hash_seed", ("0", "1", "12345"))
    def test_the_whole_ca_assessment_is_stable_across_pythonhashseed(
        self, hash_seed: str
    ) -> None:
        script = (
            "import json;"
            "from fmis.swing_lab.admission_power import ca_design_assessment;"
            "from fmis.research_design.artifact import encode_design_assessment;"
            "p = encode_design_assessment(ca_design_assessment(), writer='t');"
            "print(p['manifest']['content_digest'])"
        )
        digests = set()
        for _ in range(1):
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True,
                env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin"},
                cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
            )
            assert result.returncode == 0, result.stderr
            digests.add(result.stdout.strip())
        assert digests == {
            _ca_assessment_digest()
        }, f"PYTHONHASHSEED={hash_seed} moved the assessment digest"


def _ca_assessment_digest() -> str:
    from fmis.research_design.artifact import encode_design_assessment
    from fmis.swing_lab.admission_power import ca_design_assessment

    return encode_design_assessment(ca_design_assessment(), writer="t")["manifest"][
        "content_digest"
    ]


class TestTheGateNeverEndorses:
    def test_no_verdict_can_be_read_as_an_endorsement(self) -> None:
        for member in DesignVerdict:
            assert member.says_nothing_about_the_hypothesis

    def test_the_assessment_carries_no_field_naming_an_edge_or_a_strategy(self) -> None:
        """Checked over FIELD NAMES, and over the assessment that actually ships.

        An earlier version of this test matched the serialised payload as one
        string and ran only against the generic fixture. It passed for the wrong
        reason: the fixture's prose happens not to contain the word "edge", while
        Milestone CA's real assessment does — inside its own effect rationale,
        *"an admission edge smaller than the cost of acting on it is not an edge"*,
        which is the sentence from report 0037 §9 saying where the +0.10 bar came
        from. That is provenance and the artifact should carry it. What must be
        absent is a **field** a reader could mistake for a verdict about trading.
        """
        from fmis.swing_lab.admission_power import ca_design_assessment

        def field_names(node) -> set[str]:
            if isinstance(node, dict):
                return set(node) | {
                    name for value in node.values() for name in field_names(value)
                }
            if isinstance(node, list):
                return {name for value in node for name in field_names(value)}
            return set()

        for payload in (_assess(a_frame()).payload(), ca_design_assessment().payload()):
            names = " ".join(field_names(payload)).lower()
            for token in (
                "edge", "profit", "approved", "promote", "forward_test", "candidate",
                "recommend", "signal", "strategy",
            ):
                assert token not in names, f"a field name contains {token!r}"

    def test_an_estimator_that_ignores_clustering_cannot_pass_as_ready(self) -> None:
        assessment = _assess(
            a_frame(), width=0.001,
            estimator=an_estimator(kind=EstimatorKind.PAIRED_BOOTSTRAP),
        )
        assert assessment.verdict is DesignVerdict.INSUFFICIENT_INDEPENDENCE

    def test_a_powered_target_is_strictly_harder_than_an_interval_target(self) -> None:
        interval = _assess(a_frame(), width=0.09)
        powered = _assess(
            a_frame(), width=0.09,
            target=a_target(
                criterion=ResolutionCriterion.POWERED_DETECTION, power=0.80
            ),
        )
        assert interval.verdict is DesignVerdict.LIMITED
        assert powered.verdict is DesignVerdict.UNDERPOWERED
