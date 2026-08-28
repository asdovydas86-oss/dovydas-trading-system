"""The two methodologies, and the fact that they agree.

The empirical cluster bootstrap assumes no distribution; the analytic model
assumes a normal sampling distribution for a clustered mean. They are used for
different jobs — measuring and projecting — and the most important test here is
that they produce the same answer on data whose variance decomposition is known,
because that is what entitles the analytic path to describe designs the empirical
one cannot reach.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from fmis.research_design.models import (
    AssessmentMode,
    GrowthPath,
    ResearchDesignError,
    ResolutionCriterion,
    SampleRole,
)
from fmis.research_design.numeric import two_sided_z
from fmis.research_design.resolution import (
    ClusteredObservation,
    analytic_design_curve,
    cluster_bootstrap,
    concentration_of,
    empirical_design_curve,
    half_width_for_design,
    information_inflation,
    observation_dispersion_from_half_width,
    post_hoc_resolution,
    prospective_design,
    required_half_width,
    required_information,
)
from tests.research_design_helpers import (
    analytic_half_width,
    a_frame,
    a_target,
    an_effect,
    an_estimator,
    clustered_sample,
    true_correlation,
)

Z95 = two_sided_z(0.95)


class TestTheClusterBootstrap:
    def test_two_runs_of_one_identity_are_identical(self) -> None:
        observations = clustered_sample()
        first = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["a"]
        )
        second = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["a"]
        )
        assert first == second

    def test_a_different_seed_moves_the_interval_but_not_the_point(self) -> None:
        observations = clustered_sample()
        first = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["a"]
        )
        second = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=2, identity=["a"]
        )
        assert first.point == second.point
        assert (first.low, first.high) != (second.low, second.high)

    def test_a_different_identity_moves_the_interval(self) -> None:
        observations = clustered_sample()
        first = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["a"]
        )
        second = cluster_bootstrap(
            observations, confidence=0.95, resamples=500, master_seed=1, identity=["b"]
        )
        assert (first.low, first.high) != (second.low, second.high)

    @pytest.mark.parametrize("hash_seed", ("0", "1", "12345"))
    def test_the_reading_is_stable_across_pythonhashseed(self, hash_seed: str) -> None:
        script = (
            "import sys; sys.path.insert(0, '.');"
            "from tests.research_design_helpers import clustered_sample;"
            "from fmis.research_design.resolution import cluster_bootstrap;"
            "r = cluster_bootstrap(clustered_sample(), confidence=0.95, "
            "resamples=200, master_seed=3, identity=['x']);"
            "print(f'{r.low!r}|{r.high!r}|{r.point!r}')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == (
            "-0.12952829865229934|0.1260547940468722|-0.0044787405373908065"
        )

    def test_an_empty_sample_is_no_interval_rather_than_a_wide_one(self) -> None:
        with pytest.raises(ResearchDesignError, match="not a wide interval"):
            cluster_bootstrap([], confidence=0.95, resamples=10, master_seed=1, identity=["a"])

    def test_zero_replicates_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="positive int"):
            cluster_bootstrap(
                clustered_sample(), confidence=0.95, resamples=0, master_seed=1, identity=["a"]
            )

    def test_an_impossible_confidence_is_refused(self) -> None:
        for bad in (0.0, 1.0, 2.0):
            with pytest.raises(ResearchDesignError, match="strictly inside"):
                cluster_bootstrap(
                    clustered_sample(),
                    confidence=bad,
                    resamples=10,
                    master_seed=1,
                    identity=["a"],
                )

    def test_perfectly_identical_observations_give_a_zero_width_interval(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster=f"C{i % 5}", value=2.0) for i in range(50)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=200, master_seed=1, identity=["a"]
        )
        assert reading.half_width == 0.0
        assert reading.point == 2.0
        assert reading.excludes_zero

    def test_one_cluster_resamples_one_number_and_says_so_by_its_width(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster="only", value=float(i)) for i in range(30)
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=200, master_seed=1, identity=["a"]
        )
        assert reading.clusters == 1
        assert reading.half_width == 0.0

    def test_a_non_observation_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError):
            cluster_bootstrap(
                [("C1", 1.0)],  # type: ignore[list-item]
                confidence=0.95,
                resamples=10,
                master_seed=1,
                identity=["a"],
            )

    def test_a_non_finite_observation_is_refused_at_construction(self) -> None:
        for bad in (float("nan"), float("inf")):
            with pytest.raises(ResearchDesignError, match="finite"):
                ClusteredObservation(cluster="C1", value=bad)

    def test_an_empty_cluster_label_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="non-empty"):
            ClusteredObservation(cluster="  ", value=1.0)


class TestTheTwoMethodologiesAgree:
    """The cross-validation that entitles the analytic path to extrapolate."""

    @pytest.mark.parametrize("between_sd", (0.0, 0.5, 1.0))
    def test_the_bootstrap_reproduces_the_analytic_half_width(self, between_sd: float) -> None:
        observations = clustered_sample(
            clusters=40, per_cluster=20, between_sd=between_sd, within_sd=1.0, seed=5
        )
        reading = cluster_bootstrap(
            observations, confidence=0.95, resamples=2000, master_seed=1, identity=["t"]
        )
        rho = true_correlation(between_sd, 1.0)
        expected = analytic_half_width(
            sd=(between_sd**2 + 1.0) ** 0.5,
            clusters=40,
            per_cluster=20,
            correlation=rho,
            z=Z95,
        )
        assert reading.half_width == pytest.approx(expected, rel=0.15)

    def test_clustering_widens_the_interval_relative_to_independence(self) -> None:
        """Rows grow but clusters do not: the interval must NOT keep shrinking."""
        clustered = cluster_bootstrap(
            clustered_sample(clusters=10, per_cluster=100, between_sd=1.0, within_sd=1.0),
            confidence=0.95, resamples=1000, master_seed=1, identity=["c"],
        )
        independent = cluster_bootstrap(
            clustered_sample(clusters=1000, per_cluster=1, between_sd=0.0, within_sd=1.0),
            confidence=0.95, resamples=1000, master_seed=1, identity=["i"],
        )
        assert clustered.observations == independent.observations == 1000
        assert clustered.half_width > 5 * independent.half_width

    def test_the_inversion_round_trips(self) -> None:
        width = half_width_for_design(
            observation_sd=1.25,
            clusters=15,
            observations_per_cluster=10.0,
            intracluster_correlation=0.2,
            confidence=0.95,
        )
        recovered = observation_dispersion_from_half_width(
            half_width=width,
            clusters=15,
            observations=150,
            intracluster_correlation=0.2,
            confidence=0.95,
        )
        assert recovered == pytest.approx(1.25)

    def test_at_zero_correlation_the_half_width_is_the_textbook_rule(self) -> None:
        width = half_width_for_design(
            observation_sd=2.0,
            clusters=15,
            observations_per_cluster=10.0,
            intracluster_correlation=0.0,
            confidence=0.95,
        )
        assert width == pytest.approx(Z95 * 2.0 / (150**0.5))

    def test_the_half_width_has_a_floor_at_positive_correlation(self) -> None:
        widths = [
            half_width_for_design(
                observation_sd=1.0,
                clusters=15,
                observations_per_cluster=size,
                intracluster_correlation=0.1,
                confidence=0.95,
            )
            for size in (10, 100, 1_000, 100_000)
        ]
        assert widths == sorted(widths, reverse=True)
        assert widths[-1] == pytest.approx(Z95 * (0.1 / 15) ** 0.5, rel=1e-3)

    def test_zero_dispersion_produces_a_zero_width_and_is_allowed(self) -> None:
        assert half_width_for_design(
            observation_sd=0.0,
            clusters=5,
            observations_per_cluster=10.0,
            intracluster_correlation=0.0,
            confidence=0.95,
        ) == 0.0

    def test_a_zero_width_interval_cannot_be_inverted(self) -> None:
        with pytest.raises(ResearchDesignError, match="every effect as resolvable"):
            observation_dispersion_from_half_width(
                half_width=0.0, clusters=5, observations=50,
                intracluster_correlation=0.0, confidence=0.95,
            )

    def test_malformed_counts_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="positive int"):
            half_width_for_design(
                observation_sd=1.0, clusters=0, observations_per_cluster=10.0,
                intracluster_correlation=0.0, confidence=0.95,
            )
        with pytest.raises(ResearchDesignError, match="at least 1"):
            half_width_for_design(
                observation_sd=1.0, clusters=5, observations_per_cluster=0.5,
                intracluster_correlation=0.0, confidence=0.95,
            )
        with pytest.raises(ResearchDesignError, match=r"lie in \[0, 1\]"):
            half_width_for_design(
                observation_sd=1.0, clusters=5, observations_per_cluster=10.0,
                intracluster_correlation=1.5, confidence=0.95,
            )
        with pytest.raises(ResearchDesignError, match="non-negative"):
            half_width_for_design(
                observation_sd=-1.0, clusters=5, observations_per_cluster=10.0,
                intracluster_correlation=0.0, confidence=0.95,
            )
        with pytest.raises(ResearchDesignError, match="cannot fill"):
            observation_dispersion_from_half_width(
                half_width=0.5, clusters=50, observations=10,
                intracluster_correlation=0.0, confidence=0.95,
            )


class TestTheCriteria:
    def test_an_interval_criterion_costs_no_extra_information(self) -> None:
        assert information_inflation(a_target()) == 1.0
        assert required_half_width(an_effect("0.10"), a_target()) == pytest.approx(0.10)

    def test_a_powered_criterion_costs_about_two_times(self) -> None:
        powered = a_target(
            criterion=ResolutionCriterion.POWERED_DETECTION, power=0.80
        )
        assert information_inflation(powered) == pytest.approx(2.0433, abs=1e-3)
        assert required_half_width(an_effect("0.10"), powered) == pytest.approx(
            0.10 / 2.0433**0.5, rel=1e-3
        )

    def test_a_non_target_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError):
            information_inflation("95%")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            required_half_width("0.1", a_target())  # type: ignore[arg-type]


class TestRequiredInformation:
    def _call(self, path: GrowthPath, rho: float, **kwargs):
        base = dict(
            observed_half_width=0.5578,
            observations=155,
            clusters=15,
            intracluster_correlation=rho,
            effect=an_effect("0.10"),
            target=a_target(),
        )
        base.update(kwargs)
        return required_information(path=path, **base)

    def test_the_independent_path_is_the_textbook_answer(self) -> None:
        result = self._call(GrowthPath.INDEPENDENT_OBSERVATIONS, 0.0)
        assert result.required_observations == 4823
        assert result.observation_multiple == pytest.approx((0.5578 / 0.10) ** 2)
        assert "ASSUMES every observation is independent" in result.note

    def test_more_clusters_at_the_same_density_costs_the_same_at_every_rho(self) -> None:
        counts = {
            self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, rho).required_observations
            for rho in (0.0, 0.05, 0.1, 0.2, 0.5, 1.0)
        }
        assert counts == {4823}

    def test_more_clusters_reports_the_cluster_count_it_needs(self) -> None:
        result = self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.1)
        assert result.required_clusters == 467
        assert result.reachable

    def test_more_observations_in_the_same_clusters_is_unreachable_above_zero(self) -> None:
        for rho in (0.05, 0.1, 0.2, 0.5):
            result = self._call(GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, rho)
            assert not result.reachable, rho
            assert result.required_observations is None
            assert result.floor_half_width > 0.10
            assert "UNREACHABLE" in result.note

    def test_the_floor_rises_with_the_correlation(self) -> None:
        floors = [
            self._call(GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, rho).floor_half_width
            for rho in (0.05, 0.1, 0.2, 0.5)
        ]
        assert floors == sorted(floors)

    def test_at_zero_correlation_the_same_clusters_path_matches_the_naive_answer(self) -> None:
        result = self._call(GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.0)
        assert result.reachable
        assert result.required_observations == 4823
        assert result.floor_half_width == 0.0

    def test_a_reachable_same_cluster_path_reports_its_floor_too(self) -> None:
        """A bar the floor clears: the path works, and the floor is still stated."""
        result = self._call(
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS, 0.1, effect=an_effect("0.45")
        )
        assert result.reachable
        assert result.floor_half_width == pytest.approx(0.4078, abs=1e-3)
        assert result.required_observations > 155

    def test_an_effect_exactly_at_the_resolution_boundary_does_not_resolve(self) -> None:
        """``h < delta`` is strict: an interval whose bound touches zero excludes nothing."""
        frame = a_frame()
        reading = post_hoc_resolution(
            frame=frame,
            observed_half_width=0.10,
            effect=an_effect("0.10"),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert not reading.resolves_meaningful_effect

    def test_a_width_a_hair_below_the_boundary_does_resolve(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(),
            observed_half_width=0.099999,
            effect=an_effect("0.10"),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert reading.resolves_meaningful_effect

    def test_malformed_inputs_are_refused_rather_than_reported_as_thin_data(self) -> None:
        with pytest.raises(ResearchDesignError, match=r"lie in \[0, 1\]"):
            self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 1.5)
        with pytest.raises(ResearchDesignError, match="positive int"):
            self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.1, clusters=0)
        with pytest.raises(ResearchDesignError, match="cannot fill"):
            self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.1, observations=5)
        with pytest.raises(ResearchDesignError, match="strictly positive"):
            self._call(GrowthPath.MORE_CLUSTERS_SAME_DENSITY, 0.1, observed_half_width=0.0)
        with pytest.raises(TypeError):
            required_information(
                path="more",  # type: ignore[arg-type]
                observed_half_width=0.5,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=a_target(),
            )


class TestTheModes:
    def test_a_post_hoc_resolution_cannot_be_relabelled(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(),
            observed_half_width=0.5578,
            effect=an_effect(),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert reading.mode is AssessmentMode.POST_HOC
        with pytest.raises((AttributeError, TypeError)):
            reading.mode = AssessmentMode.PROSPECTIVE  # type: ignore[misc]

    def test_a_prospective_design_cannot_be_relabelled(self) -> None:
        design = prospective_design(
            frame=a_frame(),
            assumed_observation_sd=3.5,
            assumed_intracluster_correlation=0.0,
            dispersion_source="a pilot",
            effect=an_effect(),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert design.mode is AssessmentMode.PROSPECTIVE
        with pytest.raises((AttributeError, TypeError)):
            design.mode = AssessmentMode.POST_HOC  # type: ignore[misc]

    def test_a_prospective_design_consumes_no_realised_width(self) -> None:
        """Its only dispersion input is ASSUMED, so a holdout may be described."""
        design = prospective_design(
            frame=a_frame(name="holdout", role=SampleRole.HOLDOUT, population="h"),
            assumed_observation_sd=1.0,
            assumed_intracluster_correlation=0.0,
            dispersion_source="a prior milestone's published summary",
            effect=an_effect(),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert design.predicted_half_width > 0
        assert "observed" not in design.payload()

    def test_an_unattributed_dispersion_assumption_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="is a guess"):
            prospective_design(
                frame=a_frame(),
                assumed_observation_sd=1.0,
                assumed_intracluster_correlation=0.0,
                dispersion_source="  ",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            )

    def test_a_design_with_no_observations_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="no design here"):
            prospective_design(
                frame=a_frame(observations=0, clusters=0, experimental_units=0,
                              largest_cluster_share=None),
                assumed_observation_sd=1.0,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a pilot",
                effect=an_effect(),
                target=a_target(),
                estimator=an_estimator(),
            )

    def test_a_width_measured_at_another_confidence_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="silently changes the question"):
            post_hoc_resolution(
                frame=a_frame(),
                observed_half_width=0.5,
                effect=an_effect(),
                target=a_target(confidence=0.90),
                estimator=an_estimator(confidence=0.95),
            )

    def test_a_planned_design_at_another_confidence_is_refused(self) -> None:
        """DEFECT CB-D2, found by the independent review.

        `post_hoc_resolution` already refused an estimator and a target that
        disagree about the confidence level. This function did not, so a design
        could be planned with a 0.80 estimator against a 0.95 bar and nothing
        would say so. The two modes now apply the same rule.
        """
        with pytest.raises(ResearchDesignError, match="silently changes the question"):
            prospective_design(
                frame=a_frame(),
                assumed_observation_sd=3.5,
                assumed_intracluster_correlation=0.0,
                dispersion_source="a pilot",
                effect=an_effect(),
                target=a_target(confidence=0.95),
                estimator=an_estimator(confidence=0.80),
            )

    def test_both_modes_apply_the_identical_confidence_rule(self) -> None:
        for build in (
            lambda: post_hoc_resolution(
                frame=a_frame(), observed_half_width=0.5, effect=an_effect(),
                target=a_target(confidence=0.90), estimator=an_estimator(confidence=0.95),
            ),
            lambda: prospective_design(
                frame=a_frame(), assumed_observation_sd=1.0,
                assumed_intracluster_correlation=0.0, dispersion_source="p",
                effect=an_effect(), target=a_target(confidence=0.90),
                estimator=an_estimator(confidence=0.95),
            ),
        ):
            with pytest.raises(ResearchDesignError, match="changes the question"):
                build()

    def test_a_non_positive_observed_width_is_refused(self) -> None:
        for bad in (0.0, -0.1, float("nan")):
            with pytest.raises(ResearchDesignError, match="strictly positive"):
                post_hoc_resolution(
                    frame=a_frame(),
                    observed_half_width=bad,
                    effect=an_effect(),
                    target=a_target(),
                    estimator=an_estimator(),
                )

    def test_the_smallest_resolvable_effect_is_the_width_under_the_bare_criterion(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(),
            observed_half_width=0.5578,
            effect=an_effect(),
            target=a_target(),
            estimator=an_estimator(),
        )
        assert reading.smallest_resolvable_effect == pytest.approx(0.5578)

    def test_a_powered_criterion_raises_the_smallest_resolvable_effect(self) -> None:
        reading = post_hoc_resolution(
            frame=a_frame(),
            observed_half_width=0.5578,
            effect=an_effect(),
            target=a_target(criterion=ResolutionCriterion.POWERED_DETECTION, power=0.80),
            estimator=an_estimator(),
        )
        assert reading.smallest_resolvable_effect == pytest.approx(
            0.5578 * 2.0433**0.5, rel=1e-3
        )


class TestTheDesignCurves:
    def test_the_analytic_curve_marks_what_it_extrapolated(self) -> None:
        points = analytic_design_curve(
            path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            sizes=(100, 155, 5000),
            observed_half_width=0.5578,
            observations=155,
            clusters=15,
            intracluster_correlation=0.0,
            effect=an_effect(),
            target=a_target(),
        )
        assert [item.extrapolated for item in points] == [False, False, True]
        assert [item.resolves for item in points] == [False, False, True]

    def test_the_curve_reproduces_the_observed_width_at_the_observed_size(self) -> None:
        points = analytic_design_curve(
            path=GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
            sizes=(155,),
            observed_half_width=0.5578,
            observations=155,
            clusters=15,
            intracluster_correlation=0.3,
            effect=an_effect(),
            target=a_target(),
        )
        assert points[0].half_width == pytest.approx(0.5578)

    def test_the_same_cluster_curve_flattens_at_the_floor(self) -> None:
        points = analytic_design_curve(
            path=GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
            sizes=(155, 1000, 10_000, 1_000_000),
            observed_half_width=0.5578,
            observations=155,
            clusters=15,
            intracluster_correlation=0.10,
            effect=an_effect(),
            target=a_target(),
        )
        widths = [item.half_width for item in points]
        assert widths == sorted(widths, reverse=True)
        assert widths[-1] == pytest.approx(0.4078, abs=1e-3)
        assert not any(item.resolves for item in points)

    def test_the_curve_takes_no_confidence_of_its_own(self) -> None:
        """It used to, and the argument could never change a number. See below."""
        import inspect

        assert "confidence" not in inspect.signature(analytic_design_curve).parameters

    def test_the_confidence_level_cancels_out_of_every_projected_width(self) -> None:
        """The invariant that makes the removed argument harmless. **Pinned.**

        Inverting an observed width for a dispersion divides by ``z``; projecting
        a new design multiplies by the same ``z``. A mutation probe that hardcoded
        the confidence to 0.5 survived the whole suite for exactly this reason, and
        it is an equivalent mutant rather than a gap — but the property it exposed
        is worth holding, because it is also the reason the curve CANNOT detect a
        width supplied at the wrong confidence.
        """
        widths = set()
        for confidence in (0.50, 0.80, 0.95, 0.99):
            sigma = observation_dispersion_from_half_width(
                half_width=0.5578, clusters=15, observations=155,
                intracluster_correlation=0.0, confidence=confidence,
            )
            widths.add(
                round(
                    half_width_for_design(
                        observation_sd=sigma, clusters=484,
                        observations_per_cluster=155 / 15,
                        intracluster_correlation=0.0, confidence=confidence,
                    ),
                    12,
                )
            )
        assert len(widths) == 1

    def test_only_the_bar_moves_with_the_target_confidence(self) -> None:
        for confidence in (0.80, 0.95, 0.99):
            target = a_target(confidence=confidence)
            points = analytic_design_curve(
                path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
                sizes=(155,),
                observed_half_width=0.5578,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=target,
            )
            assert points[0].half_width == pytest.approx(0.5578)
            assert points[0].resolves is (
                0.5578 < required_half_width(an_effect(), target)
            )

    def test_an_independent_observation_curve_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="remember the curve"):
            analytic_design_curve(
                path=GrowthPath.INDEPENDENT_OBSERVATIONS,
                sizes=(100,),
                observed_half_width=0.5,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=a_target(),
            )

    def test_a_curve_with_no_sizes_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="at least one design size"):
            analytic_design_curve(
                path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
                sizes=(),
                observed_half_width=0.5,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=a_target(),
            )

    def test_a_size_that_cannot_fill_the_clusters_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="a different one"):
            analytic_design_curve(
                path=GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
                sizes=(5,),
                observed_half_width=0.5,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=a_target(),
            )

    def test_a_non_positive_size_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="positive int"):
            analytic_design_curve(
                path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
                sizes=(0,),
                observed_half_width=0.5,
                observations=155,
                clusters=15,
                intracluster_correlation=0.0,
                effect=an_effect(),
                target=a_target(),
            )

    def test_the_empirical_curve_is_measured_and_falls_with_the_cluster_count(self) -> None:
        """With enough sub-samples the curve is monotone. It is measured, not modelled."""
        observations = clustered_sample(
            clusters=20, per_cluster=15, between_sd=0.4, within_sd=1.0, seed=7
        )
        points = empirical_design_curve(
            observations,
            cluster_counts=(5, 10, 20),
            confidence=0.95,
            resamples=300,
            subsamples=21,
            master_seed=1,
            identity=["curve"],
            effect=an_effect("2.0"),
            target=a_target(),
        )
        widths = [item.half_width for item in points]
        assert widths == sorted(widths, reverse=True)
        assert all(not item.extrapolated for item in points)
        assert all(item.is_measured for item in points)

    def test_the_curve_is_NOT_monotone_at_few_subsamples_and_says_so(self) -> None:
        """The method's own noise, asserted rather than assumed away.

        Five sub-samples of five clusters out of twenty produce a median that can
        sit below the ten-cluster median. The curve reports it and the spread makes
        it readable as noise; a test asserting monotonicity here would be asserting
        something the estimator does not promise.
        """
        observations = clustered_sample(
            clusters=20, per_cluster=15, between_sd=0.4, within_sd=1.0, seed=7
        )
        points = empirical_design_curve(
            observations,
            cluster_counts=(5, 10, 20),
            confidence=0.95,
            resamples=300,
            subsamples=5,
            master_seed=1,
            identity=["curve"],
            effect=an_effect("2.0"),
            target=a_target(),
        )
        widths = [item.half_width for item in points]
        assert widths != sorted(widths, reverse=True)
        assert points[0].overlaps(points[1]), (
            "the wobble must be inside the reported noise, or the spread is not "
            "doing the job it exists for"
        )

    def test_two_modelled_points_carry_no_spread_and_refuse_the_comparison(self) -> None:
        points = analytic_design_curve(
            path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            sizes=(155, 5000),
            observed_half_width=0.5578,
            observations=155,
            clusters=15,
            intracluster_correlation=0.0,
            effect=an_effect(),
            target=a_target(),
        )
        assert all(not item.is_measured for item in points)
        with pytest.raises(ResearchDesignError, match="comparing their"):
            points[0].overlaps(points[1])

    def test_the_empirical_curve_refuses_to_invent_a_cluster(self) -> None:
        observations = clustered_sample(clusters=5, per_cluster=10)
        with pytest.raises(ResearchDesignError, match="stops at the data"):
            empirical_design_curve(
                observations,
                cluster_counts=(50,),
                confidence=0.95,
                resamples=100,
                subsamples=2,
                master_seed=1,
                identity=["c"],
                effect=an_effect(),
                target=a_target(),
            )

    def test_the_empirical_curve_refuses_a_single_cluster_point(self) -> None:
        with pytest.raises(ResearchDesignError, match="resamples one number"):
            empirical_design_curve(
                clustered_sample(clusters=5, per_cluster=10),
                cluster_counts=(1,),
                confidence=0.95,
                resamples=100,
                subsamples=2,
                master_seed=1,
                identity=["c"],
                effect=an_effect(),
                target=a_target(),
            )

    def test_the_empirical_curve_needs_observations(self) -> None:
        with pytest.raises(ResearchDesignError, match="needs observations"):
            empirical_design_curve(
                [],
                cluster_counts=(2,),
                confidence=0.95,
                resamples=10,
                subsamples=1,
                master_seed=1,
                identity=["c"],
                effect=an_effect(),
                target=a_target(),
            )

    def test_the_empirical_curve_is_deterministic(self) -> None:
        observations = clustered_sample(clusters=8, per_cluster=10)
        kwargs = dict(
            cluster_counts=(4, 8),
            confidence=0.95,
            resamples=100,
            subsamples=3,
            master_seed=2,
            identity=["c"],
            effect=an_effect(),
            target=a_target(),
        )
        assert empirical_design_curve(observations, **kwargs) == empirical_design_curve(
            observations, **kwargs
        )

    def test_zero_subsamples_are_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="positive int"):
            empirical_design_curve(
                clustered_sample(clusters=4, per_cluster=5),
                cluster_counts=(2,),
                confidence=0.95,
                resamples=10,
                subsamples=0,
                master_seed=1,
                identity=["c"],
                effect=an_effect(),
                target=a_target(),
            )


class TestConcentration:
    def test_one_cluster_dominating_is_reported_as_such(self) -> None:
        observations = (
            ClusteredObservation(cluster="BIG", value=99.0),
            ClusteredObservation(cluster="a", value=0.5),
            ClusteredObservation(cluster="b", value=0.5),
        )
        assert concentration_of(observations) == pytest.approx(0.99)

    def test_a_flat_zero_sample_reports_absence_rather_than_a_zero_share(self) -> None:
        observations = tuple(
            ClusteredObservation(cluster=f"C{i}", value=0.0) for i in range(4)
        )
        assert concentration_of(observations) is None
