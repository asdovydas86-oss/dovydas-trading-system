"""The gate. **Can this experiment answer its question — not, is the answer good.**

`assess_research_design` returns one of six verdicts and never says anything
about the hypothesis. `DesignVerdict.says_nothing_about_the_hypothesis` is `True`
for every member, asserted over the whole enum, in the same way Milestone CA
asserts `is_approved_for_trading` is `False` for every one of its verdicts. A gate
that could be read as endorsement would eventually be quoted as one.

**The rule, in full and in order.** The first condition that holds decides, and
the order is deliberate — a design measured in the wrong unit is not "a bit
underpowered", and a design with two clusters is not resolved by more rows.

1. `NOT_MEASURABLE` — the sample cannot support any estimate: no observations, no
   clusters, or fewer than two observations to average.
2. `MISALIGNED_UNIT` — the effect and the uncertainty are measured in different
   units. The inequality that would compare them is two questions sharing one
   symbol.
3. `INSUFFICIENT_INDEPENDENCE` — the design has the rows but not the independent
   information: fewer clusters or time blocks than declared, a single cluster
   above the declared concentration bound, or an estimator that ignores a
   dependence the design itself declared.
4. `UNDERPOWERED` — the uncertainty is wider than the declared effect requires.
5. `LIMITED` — it resolves the effect, with stated caveats attached.
6. `READY` — it resolves the effect with none.

**The binding dimension is measured, not guessed.** `required_information` is
computed for each growth path at each correlation in the declared sensitivity
range, and the limiting factor follows from which paths are reachable. When
adding observations inside the existing clusters has a floor above the bar, the
limit is the **cluster count** and no quantity of extra history changes it. That
is a finding, and it is the one CA's own estimate does not make.

**Holdout discipline is structural.** A post-hoc resolution measured on a holdout
sample is refused as an input to this gate. Not warned about — refused. A study
design justified by the holdout's own outcomes has already spent the holdout, and
the only way to make that unavailable is to make it raise.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fmis.research_design.dependence import InformationProfile, profile_of
from fmis.research_design.models import (
    AssessmentMode,
    DependenceModel,
    DesignTarget,
    DesignVerdict,
    EstimatorSpec,
    GrowthPath,
    LimitingFactor,
    MeaningfulEffect,
    MetricUnit,
    ResearchDesignError,
    ResearchQuestion,
    ResolutionCriterion,
    SampleFrame,
    check_sample_frames,
)
from fmis.research_design.resolution import (
    PostHocResolution,
    ProspectiveDesign,
    RequiredInformation,
    required_information,
)

__all__ = ["DesignAssessment", "assess_research_design"]

_COIN_FLIP_NOTE = (
    "The INTERVAL_EXCLUDES_ZERO criterion is met about half the time when the "
    "true effect equals the declared magnitude, because it asks only that an "
    "interval centred on that magnitude exclude zero. It is a resolution "
    "criterion, not a power guarantee. POWERED_DETECTION costs roughly 2.04x the "
    "information at 95 % confidence and 80 % power."
)


@dataclass(frozen=True, slots=True)
class DesignAssessment:
    """One design, assessed. Every input that decided the verdict travels with it."""

    assessment_id: str
    question: ResearchQuestion
    effect: MeaningfulEffect
    uncertainty_unit: MetricUnit
    dependence: DependenceModel
    estimator: EstimatorSpec
    target: DesignTarget
    frames: tuple[SampleFrame, ...]
    profiles: tuple[InformationProfile, ...]
    primary_sample: str
    resolution: PostHocResolution | ProspectiveDesign
    requirements: tuple[RequiredInformation, ...]
    verdict: DesignVerdict
    limiting_factor: LimitingFactor
    assumptions: tuple[str, ...]
    caveats: tuple[str, ...]

    @property
    def mode(self) -> AssessmentMode:
        """Read off the resolution, never set. See `AssessmentMode`."""
        return self.resolution.mode

    @property
    def resolvable_half_width(self) -> float:
        return self.resolution.half_width

    def requirement(self, path: GrowthPath, correlation: float) -> RequiredInformation:
        for item in self.requirements:
            if item.path is path and abs(item.intracluster_correlation - correlation) < 1e-12:
                return item
        raise ResearchDesignError(
            f"no requirement was computed for {path.value} at correlation {correlation}"
        )

    def payload(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "mode": self.mode.value,
            "question": self.question.payload(),
            "effect": {
                "magnitude": str(self.effect.magnitude),
                "unit": self.effect.unit.code,
                "unit_description": self.effect.unit.description,
                "direction": self.effect.direction.value,
                "rationale": self.effect.rationale,
                "source": self.effect.source,
            },
            "uncertainty_unit": self.uncertainty_unit.code,
            "dependence": self.dependence.payload(),
            "estimator": self.estimator.payload(),
            "target": self.target.payload(),
            "frames": [frame.payload() for frame in self.frames],
            "profiles": [profile.payload() for profile in self.profiles],
            "primary_sample": self.primary_sample,
            "resolution": self.resolution.payload(),
            "requirements": [item.payload() for item in self.requirements],
            "verdict": self.verdict.value,
            "limiting_factor": self.limiting_factor.value,
            "assumptions": list(self.assumptions),
            "caveats": list(self.caveats),
        }


def assess_research_design(
    *,
    assessment_id: str,
    question: ResearchQuestion,
    effect: MeaningfulEffect,
    uncertainty_unit: MetricUnit,
    dependence: DependenceModel,
    estimator: EstimatorSpec,
    target: DesignTarget,
    frames: Sequence[SampleFrame],
    primary_sample: str,
    resolution: PostHocResolution | ProspectiveDesign,
    sensitivity_correlations: Sequence[float],
) -> DesignAssessment:
    """Decide whether this design can resolve the effect it declared.

    ``resolution`` carries the mode. Build it with
    `fmis.research_design.resolution.prospective_design` for a study that has not
    run, or `post_hoc_resolution` for a diagnostic on one that has. There is no
    argument here that changes which it is.

    ``sensitivity_correlations`` is the range of intracluster correlations the
    required-information figures are reported across. It must be non-empty, and
    when the dependence model declares a correlation that value must be inside it
    — a sensitivity range that excludes the design's own assumption is describing
    a different design.

    Raises:
        ResearchDesignError: the frames are malformed or inconsistent, the primary
            sample is not among them, the resolution does not describe the primary
            sample, or a post-hoc resolution measured on a **holdout** is offered
            as a design input.
    """
    _require_text(assessment_id, "assessment_id")
    for name, value, expected in (
        ("question", question, ResearchQuestion),
        ("effect", effect, MeaningfulEffect),
        ("uncertainty_unit", uncertainty_unit, MetricUnit),
        ("dependence", dependence, DependenceModel),
        ("estimator", estimator, EstimatorSpec),
        ("target", target, DesignTarget),
    ):
        if not isinstance(value, expected):
            raise TypeError(f"{name} must be a {expected.__name__}")
    if not isinstance(resolution, (PostHocResolution, ProspectiveDesign)):
        raise TypeError(
            "resolution must be a PostHocResolution or a ProspectiveDesign; the "
            "mode is carried by the object and cannot be passed as a label"
        )

    ordered = tuple(frames)
    if not ordered:
        raise ResearchDesignError("a design assessment needs at least one sample frame")
    for frame in ordered:
        if not isinstance(frame, SampleFrame):
            raise TypeError("every frame must be a SampleFrame")
    check_sample_frames(ordered)

    by_name = {frame.name: frame for frame in ordered}
    if primary_sample not in by_name:
        raise ResearchDesignError(
            f"primary_sample {primary_sample!r} is not among the declared frames "
            f"({', '.join(sorted(by_name))})"
        )
    primary = by_name[primary_sample]
    if resolution.sample != primary_sample:
        raise ResearchDesignError(
            f"the resolution describes sample {resolution.sample!r} but the primary "
            f"sample is {primary_sample!r}; a verdict decided on one sample and "
            "reported for another is the pooling defect wearing two names"
        )
    if resolution.mode is AssessmentMode.POST_HOC and not primary.role.may_inform_design:
        raise ResearchDesignError(
            f"sample {primary_sample!r} is a {primary.role.value} and a realised "
            "measurement over it may not decide a study design. The holdout's own "
            "outcomes are the one thing a design assessment must not consult — a "
            "design justified by them has already spent it. Assess the design on "
            "development or validation, or state a PROSPECTIVE assumption instead"
        )

    correlations = tuple(float(item) for item in sensitivity_correlations)
    if not correlations:
        raise ResearchDesignError(
            "sensitivity_correlations must name at least one intracluster "
            "correlation; every required-information figure is conditional on one "
            "and reporting a single unlabelled number would hide that"
        )
    for value in correlations:
        if not 0.0 <= value <= 1.0:
            raise ResearchDesignError(
                f"every sensitivity correlation must lie in [0, 1], got {value}"
            )
    declared = dependence.intracluster_correlation
    if declared is not None and not any(abs(declared - item) < 1e-12 for item in correlations):
        raise ResearchDesignError(
            f"the dependence model declares an intracluster correlation of {declared} "
            f"but the sensitivity range {correlations} does not contain it"
        )

    profiles = tuple(profile_of(frame, dependence) for frame in ordered)

    # The correlation the binding dimension is decided at: the declared one when
    # there is one, and otherwise the LARGEST in the range, because that is the
    # assumption under which the design is hardest to satisfy. Stated rather than
    # implied, because it decides the limiting factor.
    binding_rho = declared if declared is not None else max(correlations)

    requirements: list[RequiredInformation] = []
    for rho in sorted(set(correlations)):
        for path in (
            GrowthPath.INDEPENDENT_OBSERVATIONS,
            GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS,
        ):
            if path is GrowthPath.INDEPENDENT_OBSERVATIONS and rho != min(correlations):
                # The independent path does not depend on rho; computing it once
                # keeps the table honest about that rather than repeating one
                # number under several correlations as though they differed.
                continue
            requirements.append(
                required_information(
                    path=path,
                    observed_half_width=resolution.half_width,
                    observations=primary.observations,
                    clusters=primary.clusters,
                    intracluster_correlation=rho,
                    effect=effect,
                    target=target,
                )
                if primary.clusters and primary.observations >= primary.clusters
                else _unassessable(path, rho)
            )

    verdict, limiting = _decide(
        primary=primary,
        effect=effect,
        uncertainty_unit=uncertainty_unit,
        dependence=dependence,
        estimator=estimator,
        target=target,
        resolution=resolution,
        requirements=tuple(requirements),
        binding_rho=binding_rho,
    )

    assumptions = _assumptions(
        estimator=estimator,
        dependence=dependence,
        target=target,
        binding_rho=binding_rho,
        declared=declared,
        correlations=correlations,
    )
    caveats = _caveats(
        primary=primary,
        dependence=dependence,
        estimator=estimator,
        target=target,
        declared=declared,
    )

    return DesignAssessment(
        assessment_id=assessment_id,
        question=question,
        effect=effect,
        uncertainty_unit=uncertainty_unit,
        dependence=dependence,
        estimator=estimator,
        target=target,
        frames=ordered,
        profiles=profiles,
        primary_sample=primary_sample,
        resolution=resolution,
        requirements=tuple(requirements),
        verdict=verdict,
        limiting_factor=limiting,
        assumptions=assumptions,
        caveats=caveats,
    )


def _unassessable(path: GrowthPath, rho: float) -> RequiredInformation:
    """A placeholder for a frame too malformed to plan from. Never a zero."""
    return RequiredInformation(
        path=path,
        reachable=False,
        required_clusters=None,
        required_observations=None,
        required_observations_per_cluster=None,
        observation_multiple=None,
        floor_half_width=None,
        intracluster_correlation=rho,
        note=(
            "NOT COMPUTED. The primary sample holds no cluster with an observation "
            "in it, so there is no design to grow."
        ),
    )


def _decide(
    *,
    primary: SampleFrame,
    effect: MeaningfulEffect,
    uncertainty_unit: MetricUnit,
    dependence: DependenceModel,
    estimator: EstimatorSpec,
    target: DesignTarget,
    resolution: PostHocResolution | ProspectiveDesign,
    requirements: tuple[RequiredInformation, ...],
    binding_rho: float,
) -> tuple[DesignVerdict, LimitingFactor]:
    """The ordered rule. Pure, total, and the only place a verdict is chosen."""
    if primary.observations < 2 or not primary.clusters:
        return DesignVerdict.NOT_MEASURABLE, LimitingFactor.OBSERVATION_COUNT
    if not effect.unit.agrees_with(uncertainty_unit):
        return DesignVerdict.MISALIGNED_UNIT, LimitingFactor.UNIT_MISMATCH
    if primary.clusters < target.minimum_clusters:
        return DesignVerdict.INSUFFICIENT_INDEPENDENCE, LimitingFactor.CLUSTER_COUNT
    if primary.time_blocks < target.minimum_time_blocks:
        return DesignVerdict.INSUFFICIENT_INDEPENDENCE, LimitingFactor.TIME_BLOCKS
    if (
        primary.largest_cluster_share is not None
        and primary.largest_cluster_share > target.maximum_cluster_share
    ):
        return DesignVerdict.INSUFFICIENT_INDEPENDENCE, LimitingFactor.CLUSTER_CONCENTRATION
    if primary.observations > primary.clusters and not estimator.kind.respects_clustering:
        return DesignVerdict.INSUFFICIENT_INDEPENDENCE, LimitingFactor.ESTIMATOR_RESOLUTION

    if not resolution.resolves_meaningful_effect:
        return DesignVerdict.UNDERPOWERED, _binding_dimension(
            requirements=requirements, target=target, binding_rho=binding_rho
        )

    caveat_free = (
        dependence.intracluster_correlation is not None
        and primary.largest_cluster_share is not None
        and not dependence.repeated_measurements
        and dependence.overlapping_horizon == 0
    )
    if caveat_free:
        return DesignVerdict.READY, LimitingFactor.NONE
    return DesignVerdict.LIMITED, LimitingFactor.NONE


def _binding_dimension(
    *,
    requirements: tuple[RequiredInformation, ...],
    target: DesignTarget,
    binding_rho: float,
) -> LimitingFactor:
    """Which dimension binds, decided at the binding correlation.

    * If growing inside the existing clusters cannot reach the bar at any size,
      the limit is the **cluster count** — the finding that "more data" of the
      wrong kind does nothing.
    * Otherwise, if the cheapest reachable path costs more information than the
      target is willing to acquire, the limit is the **effect size**: the design
      is fine and the question is too small for it.
    * Otherwise the limit is simply the **observation count**.
    """
    same_clusters = [
        item
        for item in requirements
        if item.path is GrowthPath.MORE_OBSERVATIONS_SAME_CLUSTERS
        and abs(item.intracluster_correlation - binding_rho) < 1e-12
    ]
    if same_clusters and not same_clusters[0].reachable:
        return LimitingFactor.CLUSTER_COUNT
    if target.maximum_information_multiple is not None:
        multiples = [
            item.observation_multiple
            for item in requirements
            if item.reachable and item.observation_multiple is not None
        ]
        if multiples and min(multiples) > float(target.maximum_information_multiple):
            return LimitingFactor.EFFECT_SIZE
    return LimitingFactor.OBSERVATION_COUNT


def _assumptions(
    *,
    estimator: EstimatorSpec,
    dependence: DependenceModel,
    target: DesignTarget,
    binding_rho: float,
    declared: float | None,
    correlations: tuple[float, ...],
) -> tuple[str, ...]:
    items = list(estimator.assumptions) + list(dependence.assumptions)
    items.append(
        "Required-information figures assume a clustered mean whose sampling "
        "distribution is approximately normal, with a common within-cluster "
        "correlation and equal cluster sizes. The MEASURED interval assumes "
        "neither: it is read off resampled quantiles."
    )
    if declared is None:
        items.append(
            "No intracluster correlation was declared, so the binding dimension is "
            f"decided at {binding_rho}, the largest of the declared sensitivity "
            f"range {correlations} — the assumption under which the design is "
            "hardest to satisfy."
        )
    else:
        items.append(
            f"The binding dimension is decided at the declared intracluster "
            f"correlation {declared}, reported across {correlations}."
        )
    if target.criterion is ResolutionCriterion.INTERVAL_EXCLUDES_ZERO:
        items.append(_COIN_FLIP_NOTE)
    return tuple(items)


def _caveats(
    *,
    primary: SampleFrame,
    dependence: DependenceModel,
    estimator: EstimatorSpec,
    target: DesignTarget,
    declared: float | None,
) -> tuple[str, ...]:
    items: list[str] = []
    if declared is None:
        items.append(
            "The intracluster correlation is unmeasured. Every required-information "
            "figure below is conditional on an assumed value, and the sensitivity "
            "table is the answer rather than any single row of it."
        )
    if primary.largest_cluster_share is None:
        items.append(
            f"Sample {primary.name!r} does not state its largest cluster's share, so "
            f"the {target.maximum_cluster_share} concentration bound could not be "
            "checked. An unchecked bound is not a passed one."
        )
    elif primary.largest_cluster_share > 0.75 * target.maximum_cluster_share:
        items.append(
            f"Sample {primary.name!r} carries a largest cluster share of "
            f"{primary.largest_cluster_share:.4f}, within 25 % of its "
            f"{target.maximum_cluster_share} bound."
        )
    if dependence.overlapping_horizon:
        items.append(
            f"Consecutive observations share up to {dependence.overlapping_horizon} "
            "period(s) of their evaluation window, so the raw observation count "
            "overstates the number of distinct experiments."
        )
    if dependence.repeated_measurements:
        items.append(
            "The same experimental unit is measured more than once, so observations "
            "are not exchangeable even within a cluster."
        )
    if primary.experimental_units < primary.observations:
        items.append(
            f"Sample {primary.name!r} holds {primary.observations} observation(s) over "
            f"{primary.experimental_units} experimental unit(s); the unit of evidence "
            "is the coarser count."
        )
    if not estimator.kind.respects_clustering and primary.observations > primary.clusters:
        items.append(
            f"The {estimator.kind.value} estimator treats observations as "
            "exchangeable while the design declares clustering."
        )
    return tuple(items)


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchDesignError(f"{field} must be a non-empty str")
    return value
