"""What a design can resolve, and what it would take to resolve more.

Two methodologies live here and they are **not** interchangeable. Which one
applies is decided by what exists, not by which is convenient.

**Empirical, and preferred whenever observation-level data exists.**
`cluster_bootstrap` and `empirical_design_curve` read the actual observations,
resample the actual clusters, and never assume a distribution. The design curve
sub-samples **real clusters** and **real observations inside them**; it refuses to
manufacture a cluster or an observation that was not there, so it stops at the
edge of the data and says so rather than extrapolating quietly.

**Analytic, and used when only a published summary survives.** Milestone CA left
no observation-level artifact in the repository — its 155 paired differences are
not recoverable without a 77-minute network replay that would produce a different
dataset. What survives is a sealed summary: 155 matched admissions, 15 symbols, a
symbol-clustered bootstrap half-width of 0.558 ATR. The analytic path takes those
numbers, inverts them for the dispersion they imply under a **declared**
intracluster correlation, and projects other designs from it. Every figure it
produces is conditional on that correlation, so every figure it produces is
reported across a range of them.

**The formula, in full, so it can be argued with.** For a mean over ``K`` clusters
of ``m`` observations each, with per-observation dispersion ``sigma`` and
intracluster correlation ``rho``, the cluster-resampled mean has

    standard error^2 = sigma^2 * (rho + (1 - rho) / m) / K
    half_width       = z(confidence) * standard error

Two consequences decide everything downstream:

* **At ``rho = 0`` the half-width is ``z * sigma / sqrt(K * m)``** — the familiar
  1/sqrt(n) rule, and the rule Milestone CA's ~4,800 estimate applies.
* **At any ``rho > 0`` there is a floor.** As ``m`` grows without bound the
  half-width approaches ``z * sigma * sqrt(rho / K)``, which depends on the
  **cluster count alone**. No quantity of additional history inside the same
  clusters goes below it. That floor is the difference between *more years* and
  *more symbols*, and it is why `GrowthPath` exists.

**No classical power is faked.** `ResolutionCriterion.INTERVAL_EXCLUDES_ZERO` is
labelled for what it is — a coin-flip criterion, met about half the time when the
true effect equals the declared magnitude. Asking for a real power guarantee
means `POWERED_DETECTION`, which costs ``((z_c + z_b) / z_c)^2`` times the
information: about 2.04x at 95 % confidence and 80 % power.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from random import Random
from typing import Any

from fmis.research_design.models import (
    AssessmentMode,
    DesignTarget,
    EstimatorSpec,
    GrowthPath,
    MeaningfulEffect,
    ResearchDesignError,
    ResolutionCriterion,
    SampleFrame,
)
from fmis.research_design.numeric import (
    derive_seed,
    largest_share,
    nearest_rank_quantile,
    one_sided_z,
    two_sided_z,
)

__all__ = [
    "ClusteredObservation",
    "BootstrapReading",
    "PostHocResolution",
    "ProspectiveDesign",
    "RequiredInformation",
    "DesignPoint",
    "cluster_bootstrap",
    "required_half_width",
    "information_inflation",
    "half_width_for_design",
    "observation_dispersion_from_half_width",
    "post_hoc_resolution",
    "prospective_design",
    "required_information",
    "analytic_design_curve",
    "empirical_design_curve",
    "concentration_of",
]


@dataclass(frozen=True, slots=True)
class ClusteredObservation:
    """One observation and the cluster it is not independent of."""

    cluster: str
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.cluster, str) or not self.cluster.strip():
            raise ResearchDesignError("cluster must be a non-empty str")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ResearchDesignError("value must be a real number")
        if not isfinite(float(self.value)):
            raise ResearchDesignError(f"value must be finite, got {self.value}")


@dataclass(frozen=True, slots=True)
class BootstrapReading:
    """A resampled interval and the design it came from."""

    point: float
    low: float
    high: float
    half_width: float
    observations: int
    clusters: int
    resamples: int
    confidence: float

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0.0 or self.high < 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "point": self.point,
            "low": self.low,
            "high": self.high,
            "half_width": self.half_width,
            "observations": self.observations,
            "clusters": self.clusters,
            "resamples": self.resamples,
            "confidence": self.confidence,
        }


def _grouped(observations: Sequence[ClusteredObservation]) -> dict[str, list[float]]:
    groups: dict[str, list[float]] = {}
    for item in observations:
        if not isinstance(item, ClusteredObservation):
            raise TypeError("every observation must be a ClusteredObservation")
        groups.setdefault(item.cluster, []).append(float(item.value))
    return groups


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def cluster_bootstrap(
    observations: Sequence[ClusteredObservation],
    *,
    confidence: float,
    resamples: int,
    master_seed: int,
    identity: Sequence[Any],
) -> BootstrapReading:
    """Resample **clusters** with replacement. The definition Milestone CA sealed.

    Each replicate draws ``K`` cluster labels with replacement from the ``K``
    present, pools every observation of every drawn cluster, and takes the plain
    mean of the pool. The interval is the nearest-rank quantile pair of those
    replicate means.

    **Not resampling observations.** Observations inside one cluster share
    whatever the cluster shares — a symbol's drift, a period's regime — and
    resampling them individually reports an interval too narrow by exactly that
    dependence. The cluster is the coarsest unit available and therefore the most
    conservative one.

    Raises:
        ResearchDesignError: no observations, or a malformed confidence or
            replicate count.
    """
    if not observations:
        raise ResearchDesignError(
            "a bootstrap needs at least one observation; an interval over an empty "
            "sample is not a wide interval, it is no interval"
        )
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ResearchDesignError(f"resamples must be a positive int, got {resamples!r}")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ResearchDesignError("confidence must be a real number")
    if not 0.0 < float(confidence) < 1.0:
        raise ResearchDesignError(
            f"confidence must lie strictly inside (0, 1), got {confidence}"
        )
    groups = _grouped(observations)
    labels = sorted(groups)
    generator = Random(derive_seed(master=master_seed, parts=[*identity, "cluster_bootstrap", resamples]))
    effects: list[float] = []
    for _ in range(resamples):
        drawn: list[float] = []
        for _ in labels:
            drawn.extend(groups[generator.choice(labels)])
        effects.append(_mean(drawn))
    tail = (1.0 - float(confidence)) / 2.0
    low = nearest_rank_quantile(effects, tail)
    high = nearest_rank_quantile(effects, 1.0 - tail)
    return BootstrapReading(
        point=_mean([float(item.value) for item in observations]),
        low=low,
        high=high,
        half_width=(high - low) / 2.0,
        observations=len(observations),
        clusters=len(labels),
        resamples=resamples,
        confidence=float(confidence),
    )


# ---------------------------------------------------------------------------
# The two criteria, expressed as one number the design must beat.
# ---------------------------------------------------------------------------


def information_inflation(target: DesignTarget) -> float:
    """How much more information `POWERED_DETECTION` costs than a bare interval.

    ``((z_confidence + z_power) / z_confidence)^2``, and exactly ``1.0`` for
    `INTERVAL_EXCLUDES_ZERO`. Derived rather than tabulated so that a caller who
    changes the confidence gets a consistent answer.
    """
    if not isinstance(target, DesignTarget):
        raise TypeError("target must be a DesignTarget")
    if target.criterion is ResolutionCriterion.INTERVAL_EXCLUDES_ZERO:
        return 1.0
    z_c = two_sided_z(target.confidence)
    z_b = one_sided_z(target.power)
    return ((z_c + z_b) / z_c) ** 2


def required_half_width(effect: MeaningfulEffect, target: DesignTarget) -> float:
    """The largest half-width at which ``effect`` counts as resolvable.

    For `INTERVAL_EXCLUDES_ZERO` this is the effect itself: an interval of
    half-width ``h`` centred on ``delta`` excludes zero exactly when ``h < delta``.
    For `POWERED_DETECTION` it is ``delta * z_c / (z_c + z_b)``, which is the
    condition that the stated share of repetitions produce such an interval.
    """
    if not isinstance(effect, MeaningfulEffect):
        raise TypeError("effect must be a MeaningfulEffect")
    if not isinstance(target, DesignTarget):
        raise TypeError("target must be a DesignTarget")
    return effect.as_float / sqrt(information_inflation(target))


# ---------------------------------------------------------------------------
# The analytic model: dispersion in, half-width out, and its inverse.
# ---------------------------------------------------------------------------


def _structural_factor(observations_per_cluster: float, intracluster_correlation: float) -> float:
    """``rho + (1 - rho) / m``. The part of the variance the design controls."""
    if observations_per_cluster < 1.0:
        raise ResearchDesignError(
            f"observations_per_cluster must be at least 1, got {observations_per_cluster}"
        )
    if not 0.0 <= intracluster_correlation <= 1.0:
        raise ResearchDesignError(
            f"intracluster_correlation must lie in [0, 1], got {intracluster_correlation}"
        )
    return intracluster_correlation + (1.0 - intracluster_correlation) / observations_per_cluster


def half_width_for_design(
    *,
    observation_sd: float,
    clusters: int,
    observations_per_cluster: float,
    intracluster_correlation: float,
    confidence: float,
) -> float:
    """``z * sigma * sqrt((rho + (1 - rho) / m) / K)``.

    **Valid under a normal approximation to the sampling distribution of a
    clustered mean**, which is an assumption and is carried as one by every caller.
    It is used for projection, never for reporting a measured interval: a measured
    interval comes off `cluster_bootstrap`, which assumes no distribution at all.
    """
    if isinstance(observation_sd, bool) or not isinstance(observation_sd, (int, float)):
        raise ResearchDesignError("observation_sd must be a real number")
    if float(observation_sd) < 0.0:
        raise ResearchDesignError(
            f"observation_sd must be non-negative, got {observation_sd}"
        )
    if isinstance(clusters, bool) or not isinstance(clusters, int) or clusters < 1:
        raise ResearchDesignError(f"clusters must be a positive int, got {clusters!r}")
    factor = _structural_factor(float(observations_per_cluster), float(intracluster_correlation))
    return two_sided_z(confidence) * float(observation_sd) * sqrt(factor / clusters)


def observation_dispersion_from_half_width(
    *,
    half_width: float,
    clusters: int,
    observations: int,
    intracluster_correlation: float,
    confidence: float,
) -> float:
    """Invert `half_width_for_design` for the ``sigma`` a measured interval implies.

    This is how a published summary — *"155 admissions, 15 symbols, half-width
    0.558"* — becomes something other designs can be projected from. The answer
    depends on the assumed ``rho``: the same interval implies a **larger**
    per-observation dispersion when the observations are assumed independent than
    when they are assumed correlated, because independence attributes all of the
    interval's width to sampling noise.

    Raises:
        ResearchDesignError: the half-width is not strictly positive, or the
            counts are malformed.
    """
    if isinstance(half_width, bool) or not isinstance(half_width, (int, float)):
        raise ResearchDesignError("half_width must be a real number")
    width = float(half_width)
    if not isfinite(width) or width <= 0.0:
        raise ResearchDesignError(
            f"half_width must be finite and strictly positive, got {half_width}. A "
            "zero-width interval implies zero dispersion and would report every "
            "effect as resolvable"
        )
    if isinstance(clusters, bool) or not isinstance(clusters, int) or clusters < 1:
        raise ResearchDesignError(f"clusters must be a positive int, got {clusters!r}")
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise ResearchDesignError("observations must be an int")
    if observations < clusters:
        raise ResearchDesignError(
            f"{observations} observation(s) cannot fill {clusters} cluster(s)"
        )
    per_cluster = observations / clusters
    factor = _structural_factor(per_cluster, float(intracluster_correlation))
    return width / (two_sided_z(confidence) * sqrt(factor / clusters))


# ---------------------------------------------------------------------------
# Post-hoc resolution: what a COMPLETED measurement could have seen.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PostHocResolution:
    """What a finished measurement could have resolved. **Never prospective power.**

    This is a diagnostic on a study that has already run, computed from the
    uncertainty that study actually produced. It answers *"was this test capable
    of returning the answer it was asked for"* and it is the honest reading of a
    negative result. It is **not** evidence about the hypothesis, and it must
    never be presented as the power calculation that justified running the study —
    it could not have been, because it consumes a number that did not exist until
    afterwards.

    `mode` is a property returning the constant `AssessmentMode.POST_HOC`. There
    is no field to set and no argument that changes it.
    """

    sample: str
    observations: int
    clusters: int
    observed_half_width: float
    unit_code: str
    meaningful_effect: float
    required_half_width: float
    resolves_meaningful_effect: bool
    smallest_resolvable_effect: float
    confidence: float
    criterion: str
    assumptions: tuple[str, ...]

    @property
    def mode(self) -> AssessmentMode:
        return AssessmentMode.POST_HOC

    @property
    def half_width(self) -> float:
        """The width this resolution rests on, under the name both modes share."""
        return self.observed_half_width

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "sample": self.sample,
            "observations": self.observations,
            "clusters": self.clusters,
            "observed_half_width": self.observed_half_width,
            "unit_code": self.unit_code,
            "meaningful_effect": self.meaningful_effect,
            "required_half_width": self.required_half_width,
            "resolves_meaningful_effect": self.resolves_meaningful_effect,
            "smallest_resolvable_effect": self.smallest_resolvable_effect,
            "confidence": self.confidence,
            "criterion": self.criterion,
            "assumptions": list(self.assumptions),
        }


def post_hoc_resolution(
    *,
    frame: SampleFrame,
    observed_half_width: float,
    effect: MeaningfulEffect,
    target: DesignTarget,
    estimator: EstimatorSpec,
) -> PostHocResolution:
    """Diagnose a completed measurement's resolution. **Reads a realised width.**

    Applicable to any sample, including a holdout, because a completed study has
    already opened whatever it measured. What may *not* happen is using this to
    justify a study that has not run — `fmis.research_design.verdict` enforces
    that separately, by refusing a holdout-sourced width when it builds a
    prospective case.

    ``smallest_resolvable_effect`` is the smallest magnitude this measurement's
    own uncertainty could have distinguished from zero under the declared
    criterion. For `INTERVAL_EXCLUDES_ZERO` it equals the observed half-width.
    """
    if not isinstance(frame, SampleFrame):
        raise TypeError("frame must be a SampleFrame")
    if not isinstance(estimator, EstimatorSpec):
        raise TypeError("estimator must be an EstimatorSpec")
    if isinstance(observed_half_width, bool) or not isinstance(
        observed_half_width, (int, float)
    ):
        raise ResearchDesignError("observed_half_width must be a real number")
    width = float(observed_half_width)
    if not isfinite(width) or width <= 0.0:
        raise ResearchDesignError(
            f"observed_half_width must be finite and strictly positive, got "
            f"{observed_half_width}"
        )
    if abs(estimator.confidence - target.confidence) > 1e-12:
        raise ResearchDesignError(
            f"the estimator reports a {estimator.confidence:.4g} interval and the "
            f"target asks for {target.confidence:.4g}. Comparing a width measured "
            "at one confidence against a bar set at another silently changes the "
            "question"
        )
    needed = required_half_width(effect, target)
    inflation = sqrt(information_inflation(target))
    return PostHocResolution(
        sample=frame.name,
        observations=frame.observations,
        clusters=frame.clusters,
        observed_half_width=width,
        unit_code=effect.unit.code,
        meaningful_effect=effect.as_float,
        required_half_width=needed,
        resolves_meaningful_effect=width < needed,
        smallest_resolvable_effect=width * inflation,
        confidence=target.confidence,
        criterion=target.criterion.value,
        assumptions=estimator.assumptions,
    )


# ---------------------------------------------------------------------------
# Prospective design: what a PLANNED study is expected to resolve.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProspectiveDesign:
    """What a planned study is expected to resolve. **Consumes no outcome.**

    Its inputs are a planned sample's *shape* and an **assumed** dispersion, so it
    is computable before a single outcome exists — including for a holdout that
    has never been opened. `mode` is a constant property, so nothing here can be
    relabelled as a post-hoc diagnostic or vice versa.
    """

    sample: str
    planned_observations: int
    planned_clusters: int
    assumed_observation_sd: float
    assumed_intracluster_correlation: float
    dispersion_source: str
    predicted_half_width: float
    unit_code: str
    meaningful_effect: float
    required_half_width: float
    resolves_meaningful_effect: bool
    confidence: float
    criterion: str
    assumptions: tuple[str, ...]

    @property
    def mode(self) -> AssessmentMode:
        return AssessmentMode.PROSPECTIVE

    @property
    def half_width(self) -> float:
        """The width this design predicts, under the name both modes share."""
        return self.predicted_half_width

    @property
    def observations(self) -> int:
        return self.planned_observations

    @property
    def clusters(self) -> int:
        return self.planned_clusters

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "sample": self.sample,
            "planned_observations": self.planned_observations,
            "planned_clusters": self.planned_clusters,
            "assumed_observation_sd": self.assumed_observation_sd,
            "assumed_intracluster_correlation": self.assumed_intracluster_correlation,
            "dispersion_source": self.dispersion_source,
            "predicted_half_width": self.predicted_half_width,
            "unit_code": self.unit_code,
            "meaningful_effect": self.meaningful_effect,
            "required_half_width": self.required_half_width,
            "resolves_meaningful_effect": self.resolves_meaningful_effect,
            "confidence": self.confidence,
            "criterion": self.criterion,
            "assumptions": list(self.assumptions),
        }


def prospective_design(
    *,
    frame: SampleFrame,
    assumed_observation_sd: float,
    assumed_intracluster_correlation: float,
    dispersion_source: str,
    effect: MeaningfulEffect,
    target: DesignTarget,
    estimator: EstimatorSpec,
) -> ProspectiveDesign:
    """Predict a planned design's half-width from an **assumed** dispersion.

    ``dispersion_source`` is required and must say where the assumption came
    from — a pilot, a prior milestone's published summary, a literature value.
    A prospective assessment whose variance assumption has no stated origin is a
    guess with a confidence interval drawn around it.

    Raises:
        ResearchDesignError: the frame holds no cluster, the dispersion is
            negative, or the dispersion source is empty.
    """
    if not isinstance(frame, SampleFrame):
        raise TypeError("frame must be a SampleFrame")
    if not isinstance(estimator, EstimatorSpec):
        raise TypeError("estimator must be an EstimatorSpec")
    if not isinstance(dispersion_source, str) or not dispersion_source.strip():
        raise ResearchDesignError(
            "dispersion_source must say where the assumed dispersion came from; a "
            "prospective assessment resting on an unattributed variance is a guess"
        )
    # DEFECT CB-D2, found by the independent review. `post_hoc_resolution` refused
    # an estimator and a target that disagree about the confidence level, and this
    # function did not — so a design could be planned with a 0.80 estimator against
    # a 0.95 bar and nothing would say so. The two modes must apply the same rule or
    # the check is decoration.
    if abs(estimator.confidence - target.confidence) > 1e-12:
        raise ResearchDesignError(
            f"the estimator reports a {estimator.confidence:.4g} interval and the "
            f"target asks for {target.confidence:.4g}. Planning a design against a "
            "bar set at a different confidence from the one the estimator will "
            "produce silently changes the question"
        )
    if not frame.clusters or not frame.observations:
        raise ResearchDesignError(
            f"sample {frame.name!r} plans {frame.observations} observation(s) in "
            f"{frame.clusters} cluster(s); there is no design here to assess"
        )
    predicted = half_width_for_design(
        observation_sd=assumed_observation_sd,
        clusters=frame.clusters,
        observations_per_cluster=frame.observations / frame.clusters,
        intracluster_correlation=assumed_intracluster_correlation,
        confidence=target.confidence,
    )
    needed = required_half_width(effect, target)
    return ProspectiveDesign(
        sample=frame.name,
        planned_observations=frame.observations,
        planned_clusters=frame.clusters,
        assumed_observation_sd=float(assumed_observation_sd),
        assumed_intracluster_correlation=float(assumed_intracluster_correlation),
        dispersion_source=dispersion_source,
        predicted_half_width=predicted,
        unit_code=effect.unit.code,
        meaningful_effect=effect.as_float,
        required_half_width=needed,
        resolves_meaningful_effect=predicted < needed,
        confidence=target.confidence,
        criterion=target.criterion.value,
        assumptions=estimator.assumptions,
    )


# ---------------------------------------------------------------------------
# Sample planning: more of WHAT?
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequiredInformation:
    """What one growth path would have to deliver, and whether it can.

    ``reachable`` is `False` when the path has a floor above the required
    half-width. That is not a large number reported as infinity: it is the
    statement that **no quantity of this kind of data suffices**, which is a
    different and more useful finding than "you need a lot".
    """

    path: GrowthPath
    reachable: bool
    required_clusters: int | None
    required_observations: int | None
    required_observations_per_cluster: float | None
    observation_multiple: float | None
    floor_half_width: float | None
    intracluster_correlation: float
    note: str

    def payload(self) -> dict[str, Any]:
        return {
            "path": self.path.value,
            "reachable": self.reachable,
            "required_clusters": self.required_clusters,
            "required_observations": self.required_observations,
            "required_observations_per_cluster": self.required_observations_per_cluster,
            "observation_multiple": self.observation_multiple,
            "floor_half_width": self.floor_half_width,
            "intracluster_correlation": self.intracluster_correlation,
            "note": self.note,
        }


def required_information(
    *,
    path: GrowthPath,
    observed_half_width: float,
    observations: int,
    clusters: int,
    intracluster_correlation: float,
    effect: MeaningfulEffect,
    target: DesignTarget,
) -> RequiredInformation:
    """How much information ``path`` would have to deliver to resolve ``effect``.

    The three paths do not agree, and the disagreement is the point.

    * `INDEPENDENT_OBSERVATIONS` reproduces the textbook rule
      ``n' = n * (h / h*)^2``. It is offered as a **named assumption** rather than
      as a default, because that is precisely the assumption a clustered sample
      violates.
    * `MORE_CLUSTERS_SAME_DENSITY` gives the **same** ``n'`` for every ``rho``,
      which is worth knowing: scaling a design by adding clusters at the observed
      density costs exactly what the naive rule predicts.
    * `MORE_OBSERVATIONS_SAME_CLUSTERS` is where the paths separate. Its
      half-width approaches ``h * sqrt(rho / (rho + (1 - rho) / m))`` and stops.
      Whenever that floor is at or above the required half-width the path is
      unreachable at any size.

    Raises:
        ResearchDesignError: a malformed count, correlation or width.
    """
    if not isinstance(path, GrowthPath):
        raise TypeError("path must be a GrowthPath")
    rho = float(intracluster_correlation)
    if not 0.0 <= rho <= 1.0:
        raise ResearchDesignError(f"intracluster_correlation must lie in [0, 1], got {rho}")
    if isinstance(clusters, bool) or not isinstance(clusters, int) or clusters < 1:
        raise ResearchDesignError(f"clusters must be a positive int, got {clusters!r}")
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise ResearchDesignError("observations must be an int")
    if observations < clusters:
        raise ResearchDesignError(
            f"{observations} observation(s) cannot fill {clusters} cluster(s)"
        )
    width = float(observed_half_width)
    if not isfinite(width) or width <= 0.0:
        raise ResearchDesignError(
            f"observed_half_width must be finite and strictly positive, got {observed_half_width}"
        )
    needed = required_half_width(effect, target)
    per_cluster = observations / clusters
    ratio = (width / needed) ** 2

    if path is GrowthPath.INDEPENDENT_OBSERVATIONS:
        required_n = observations * ratio
        return RequiredInformation(
            path=path,
            reachable=True,
            required_clusters=None,
            required_observations=_ceil(required_n),
            required_observations_per_cluster=None,
            observation_multiple=ratio,
            floor_half_width=None,
            intracluster_correlation=0.0,
            note=(
                "ASSUMES every observation is independent, so the half-width falls "
                "as 1/sqrt(n) wherever the observations come from. This is the rule "
                "a plain sample-size formula applies and it is stated here as an "
                "assumption, not used as a default."
            ),
        )

    if path is GrowthPath.MORE_CLUSTERS_SAME_DENSITY:
        required_k = clusters * ratio
        return RequiredInformation(
            path=path,
            reachable=True,
            required_clusters=_ceil(required_k),
            required_observations=_ceil(required_k * per_cluster),
            required_observations_per_cluster=per_cluster,
            observation_multiple=ratio,
            floor_half_width=None,
            intracluster_correlation=rho,
            note=(
                "More clusters at the observed density. The required observation "
                "count is the SAME for every intracluster correlation, because "
                "growing K at fixed m scales the whole variance by 1/K. This is the "
                "one path on which the naive 1/sqrt(n) answer is correct."
            ),
        )

    factor = _structural_factor(per_cluster, rho)
    floor = width * sqrt(rho / factor)
    if floor >= needed:
        return RequiredInformation(
            path=path,
            reachable=False,
            required_clusters=clusters,
            required_observations=None,
            required_observations_per_cluster=None,
            observation_multiple=None,
            floor_half_width=floor,
            intracluster_correlation=rho,
            note=(
                f"UNREACHABLE. With {clusters} cluster(s) fixed and an intracluster "
                f"correlation of {rho}, the half-width approaches {floor:.4f} as the "
                "observations per cluster grow without bound, and never goes below "
                f"it. The bar is {needed:.4f}. More observations inside the existing "
                "clusters cannot resolve this effect at any size."
            ),
        )
    denominator = needed**2 * factor / width**2 - rho
    required_m = (1.0 - rho) / denominator
    return RequiredInformation(
        path=path,
        reachable=True,
        required_clusters=clusters,
        required_observations=_ceil(required_m * clusters),
        required_observations_per_cluster=required_m,
        observation_multiple=(required_m * clusters) / observations,
        floor_half_width=floor,
        intracluster_correlation=rho,
        note=(
            f"More observations inside the existing {clusters} cluster(s). Reachable "
            f"because the floor of {floor:.4f} is below the {needed:.4f} bar, but the "
            "cost rises faster than 1/sqrt(n) as the floor is approached."
        ),
    )


def _ceil(value: float) -> int:
    """Round a required count up. A design that needs 4,825.1 needs 4,826."""
    whole = int(value)
    return whole if whole == value else whole + 1


# ---------------------------------------------------------------------------
# Design curves.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DesignPoint:
    """One point on a design curve.

    ``subsample_spread`` is the interquartile range of the sub-sampled half-widths
    behind a **measured** point, and `None` for a modelled one. It exists because
    an empirical curve is not monotone at small cluster counts: a particular
    five-cluster subset can genuinely be tighter than a particular ten-cluster
    one, and with few sub-samples the median inherits that noise. Reporting the
    spread makes a wobble visible as noise instead of readable as a finding — two
    points whose spreads overlap have not been told apart by this curve.
    """

    clusters: int
    observations: int
    observations_per_cluster: float
    half_width: float
    resolves: bool
    extrapolated: bool
    subsample_spread: float | None = None

    @property
    def is_measured(self) -> bool:
        return self.subsample_spread is not None

    def overlaps(self, other: "DesignPoint") -> bool:
        """Whether two measured points are indistinguishable at their own noise.

        ``True`` whenever the gap between the two half-widths is inside the larger
        of the two spreads. A curve reader must not draw a conclusion from a pair
        this returns ``True`` for.
        """
        if self.subsample_spread is None or other.subsample_spread is None:
            raise ResearchDesignError(
                "only measured points carry a sub-sample spread; two modelled "
                "points differ by exactly what the model says and comparing their "
                "noise would compare nothing"
            )
        return abs(self.half_width - other.half_width) <= max(
            self.subsample_spread, other.subsample_spread
        )

    def payload(self) -> dict[str, Any]:
        return {
            "clusters": self.clusters,
            "observations": self.observations,
            "observations_per_cluster": self.observations_per_cluster,
            "half_width": self.half_width,
            "resolves": self.resolves,
            "extrapolated": self.extrapolated,
            "subsample_spread": self.subsample_spread,
        }


def analytic_design_curve(
    *,
    path: GrowthPath,
    sizes: Sequence[int],
    observed_half_width: float,
    observations: int,
    clusters: int,
    intracluster_correlation: float,
    effect: MeaningfulEffect,
    target: DesignTarget,
) -> tuple[DesignPoint, ...]:
    """Project the half-width across design sizes under the analytic model.

    **The confidence level cancels, and knowing that is the point.** This function
    used to take a ``confidence`` argument of its own. The independent review
    flagged it as letting the widths and the ``resolves`` column describe different
    intervals — and that reading was **wrong, and is withdrawn**. Inverting the
    observed width for a dispersion divides by ``z``; projecting a new design
    multiplies by the same ``z``; the two cancel exactly, so every width here is
    identical at 50 %, 95 % and 99 %. The argument could never change a number.

    It is removed anyway, because a parameter that appears to control something and
    cannot is a trap for the next reader. What replaces it is the invariant that
    was always doing the real work and was never written down:

    > ``observed_half_width`` **must have been measured at**
    > ``target.confidence``. This function cannot check that — the width arrives as
    > a bare float — so the caller carries it. `post_hoc_resolution` enforces the
    > same agreement between an estimator and a target, and is the supported way to
    > obtain a width that satisfies it.

    A width measured at 80 % and projected against a 95 % bar would be wrong here,
    and it would be wrong for that reason rather than because of any argument.

    Points beyond the observed sample carry ``extrapolated=True``, because they
    are model output rather than measurement and a curve that does not say so
    reads as though the large sizes were seen.

    `INDEPENDENT_OBSERVATIONS` is refused here: a curve drawn under an assumption
    the data is known to violate would be the pseudoreplication this package
    exists to name, dressed as a chart.
    """
    if path is GrowthPath.INDEPENDENT_OBSERVATIONS:
        raise ResearchDesignError(
            "an independent-observation curve is refused. Its only use would be to "
            "show what the data would look like if the dependence were not there, "
            "and a reader will remember the curve rather than the caveat. Use "
            "required_information(INDEPENDENT_OBSERVATIONS) for the single number"
        )
    if not sizes:
        raise ResearchDesignError("sizes must name at least one design size")
    rho = float(intracluster_correlation)
    confidence = target.confidence
    sigma = observation_dispersion_from_half_width(
        half_width=observed_half_width,
        clusters=clusters,
        observations=observations,
        intracluster_correlation=rho,
        confidence=confidence,
    )
    needed = required_half_width(effect, target)
    per_cluster = observations / clusters
    points: list[DesignPoint] = []
    for size in sorted(set(sizes)):
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise ResearchDesignError(f"every design size must be a positive int, got {size!r}")
        if path is GrowthPath.MORE_CLUSTERS_SAME_DENSITY:
            k = max(1, _ceil(size / per_cluster))
            m = per_cluster
        else:
            k = clusters
            m = size / clusters
            if m < 1.0:
                raise ResearchDesignError(
                    f"design size {size} cannot fill {clusters} clusters; a curve "
                    "point with an empty cluster is not a smaller version of this "
                    "design, it is a different one"
                )
        width = half_width_for_design(
            observation_sd=sigma,
            clusters=k,
            observations_per_cluster=m,
            intracluster_correlation=rho,
            confidence=confidence,
        )
        points.append(
            DesignPoint(
                clusters=k,
                observations=int(round(k * m)),
                observations_per_cluster=m,
                half_width=width,
                resolves=width < needed,
                extrapolated=size > observations,
            )
        )
    return tuple(points)


def empirical_design_curve(
    observations: Sequence[ClusteredObservation],
    *,
    cluster_counts: Sequence[int],
    confidence: float,
    resamples: int,
    subsamples: int,
    master_seed: int,
    identity: Sequence[Any],
    effect: MeaningfulEffect,
    target: DesignTarget,
) -> tuple[DesignPoint, ...]:
    """Measure the half-width at smaller cluster counts, from the **real** clusters.

    For each requested ``K'`` at or below the observed cluster count, ``K'``
    distinct clusters are drawn **without replacement**, the cluster bootstrap is
    run on that subsample, and the median half-width over ``subsamples`` draws is
    reported. No cluster is invented and no observation is duplicated into a new
    one.

    **It cannot go above the observed cluster count**, and asking it to is an
    error rather than a silent extrapolation. A design curve that extends past its
    data by resampling rows as though they were independent is exactly the
    pseudoreplication this package refuses; when a larger design must be
    described, `analytic_design_curve` does it with the assumption written on it.

    **It is not monotone, and that is a property of the method rather than a
    defect.** A particular five-cluster subset can be tighter than a particular
    ten-cluster one, and at small ``subsamples`` the median inherits that noise.
    Every point therefore carries `DesignPoint.subsample_spread`, and
    `DesignPoint.overlaps` says whether two points were told apart at all. A
    reader who wants a smooth curve should raise ``subsamples``, not reinterpret
    a wobble.

    Raises:
        ResearchDesignError: a requested cluster count exceeds the clusters
            present, or is below 2 (a bootstrap over one cluster resamples one
            number and reports a zero-width interval).
    """
    if not observations:
        raise ResearchDesignError("an empirical curve needs observations")
    if isinstance(subsamples, bool) or not isinstance(subsamples, int) or subsamples < 1:
        raise ResearchDesignError(f"subsamples must be a positive int, got {subsamples!r}")
    groups = _grouped(observations)
    labels = sorted(groups)
    available = len(labels)
    needed = required_half_width(effect, target)
    points: list[DesignPoint] = []
    for count in sorted(set(cluster_counts)):
        if isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise ResearchDesignError(
                f"every cluster count must be an int of at least 2, got {count!r}; a "
                "cluster bootstrap over one cluster resamples one number"
            )
        if count > available:
            raise ResearchDesignError(
                f"{count} clusters were requested but only {available} exist. This "
                "curve is measured, not modelled: it stops at the data. Use "
                "analytic_design_curve for sizes beyond it"
            )
        widths: list[float] = []
        counts: list[int] = []
        for draw in range(subsamples):
            generator = Random(
                derive_seed(master=master_seed, parts=[*identity, "subsample", count, draw])
            )
            chosen = generator.sample(labels, count)
            subset = tuple(
                item for item in observations if item.cluster in set(chosen)
            )
            reading = cluster_bootstrap(
                subset,
                confidence=confidence,
                resamples=resamples,
                master_seed=master_seed,
                identity=[*identity, "curve", count, draw],
            )
            widths.append(reading.half_width)
            counts.append(reading.observations)
        width = nearest_rank_quantile(widths, 0.5)
        size = nearest_rank_quantile(counts, 0.5)
        points.append(
            DesignPoint(
                clusters=count,
                observations=size,
                observations_per_cluster=size / count,
                half_width=width,
                resolves=width < needed,
                extrapolated=False,
                subsample_spread=(
                    nearest_rank_quantile(widths, 0.75)
                    - nearest_rank_quantile(widths, 0.25)
                ),
            )
        )
    return tuple(points)


def concentration_of(observations: Sequence[ClusteredObservation]) -> float | None:
    """The largest cluster's share of the total absolute magnitude. ``None`` if flat zero."""
    return largest_share((item.cluster, abs(float(item.value))) for item in observations)
