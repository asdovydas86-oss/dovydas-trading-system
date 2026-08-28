"""The vocabulary a research design is written in. **Values, never comments.**

Every assumption this package acts on is a field on a frozen dataclass, so it can
be rendered, digested and argued with. Nothing that changes an answer lives in a
docstring.

**What is deliberately absent.** No default effect threshold, no default unit, no
default universe, no default confidence and no trading vocabulary of any kind.
The research question owns the number that matters — *what effect is
economically meaningful* — and this module owns only the checks that it was
stated, that it is positive, that it carries a unit, and that the uncertainty it
will be compared against is measured in the **same** unit. An effect declared in
R compared against an interval measured in ATR is not a small error; it is two
different questions sharing one inequality, and it is refused by name.

**Programmer errors propagate.** A malformed sample, an impossible confidence
level, a zero cluster count or a negative observation count raises
`ResearchDesignError`. None of them is folded into a verdict, because
"insufficient data" and "you passed a negative n" are different facts and a gate
that reports the second as the first is worse than no gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

__all__ = [
    "ResearchDesignError",
    "MetricUnit",
    "ComparisonType",
    "EffectDirection",
    "MeaningfulEffect",
    "SampleRole",
    "SampleFrame",
    "check_sample_frames",
    "DependenceModel",
    "EstimatorKind",
    "EstimatorSpec",
    "ResolutionCriterion",
    "DesignTarget",
    "AssessmentMode",
    "DesignVerdict",
    "LimitingFactor",
    "GrowthPath",
    "ResearchQuestion",
]


class ResearchDesignError(Exception):
    """A research design that cannot be assessed as stated."""


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchDesignError(f"{field} must be a non-empty str")
    return value


def _require_count(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResearchDesignError(f"{field} must be an int, got {type(value).__name__}")
    if value < minimum:
        raise ResearchDesignError(f"{field} must be >= {minimum}, got {value}")
    return value


def _require_fraction(value: Any, field: str, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchDesignError(f"{field} must be a real number")
    value = float(value)
    if value != value:  # NaN is not a confidence level, and NaN <= x is False
        raise ResearchDesignError(f"{field} must be a real number, got NaN")
    if not low <= value <= high:
        raise ResearchDesignError(f"{field} must lie in [{low}, {high}], got {value}")
    return value


@dataclass(frozen=True, slots=True)
class MetricUnit:
    """What a magnitude is measured in. **Compared by code, never by description.**

    Two magnitudes may be compared only when their unit codes are identical.
    `MeaningfulEffect` in `atr` and an interval half-width in `r` describe
    different questions, and the arithmetic that would silently relate them is
    the arithmetic this type exists to prevent.

    The code is a slug so that a rendered report, a digest and an equality check
    all agree: `"ATR"`, `"atr "` and `"atr"` would otherwise be three units.
    """

    code: str
    description: str

    def __post_init__(self) -> None:
        code = _require_text(self.code, "unit code")
        if code != code.strip().lower() or any(character.isspace() for character in code):
            raise ResearchDesignError(
                f"unit code {self.code!r} must be lowercase with no whitespace; "
                "a unit compared by string cannot have two spellings"
            )
        _require_text(self.description, "unit description")

    def agrees_with(self, other: "MetricUnit") -> bool:
        if not isinstance(other, MetricUnit):
            raise TypeError("other must be a MetricUnit")
        return self.code == other.code


class ComparisonType(Enum):
    """What kind of statement the study is making."""

    PAIRED_DIFFERENCE = "paired_difference"
    UNPAIRED_DIFFERENCE = "unpaired_difference"
    SINGLE_SAMPLE_MEAN = "single_sample_mean"
    RATE_DIFFERENCE = "rate_difference"


class EffectDirection(Enum):
    """Which side of zero would count as the hypothesis being supported."""

    GREATER = "greater"
    LESS = "less"
    EITHER = "either"


@dataclass(frozen=True, slots=True)
class MeaningfulEffect:
    """The smallest effect worth detecting, and where the number came from.

    **This package does not choose it.** A threshold picked after seeing a result
    is not a threshold, and a threshold this framework supplied would be a
    trading preference smuggled into a statistics library. What is enforced is
    that one was declared, that it is strictly positive, that it carries a unit,
    and that it says where it came from — CA's +0.10 ATR is *the round-trip cost
    of the deciding cost scenario at the universe's median ATR/close*, and a bar
    that cannot state such a sentence is a number somebody liked.

    ``magnitude`` is `Decimal` because it is **declared** rather than estimated:
    it must render, digest and compare exactly. Everything this package computes
    is a float, and the boundary between the two is one conversion, here.
    """

    magnitude: Decimal
    unit: MetricUnit
    direction: EffectDirection
    rationale: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.magnitude, Decimal):
            raise ResearchDesignError(
                "meaningful effect magnitude must be a Decimal, so a declared "
                f"threshold renders and digests exactly; got {type(self.magnitude).__name__}"
            )
        if not self.magnitude.is_finite():
            raise ResearchDesignError("meaningful effect magnitude must be finite")
        if self.magnitude <= 0:
            raise ResearchDesignError(
                f"meaningful effect magnitude must be strictly positive, got {self.magnitude}. "
                "A design that must resolve an effect of zero can never be satisfied, "
                "and one that must resolve a negative magnitude is a sign convention "
                "error wearing a threshold's clothes — declare the DIRECTION instead"
            )
        if not isinstance(self.unit, MetricUnit):
            raise ResearchDesignError("meaningful effect unit must be a MetricUnit")
        if not isinstance(self.direction, EffectDirection):
            raise ResearchDesignError("meaningful effect direction must be an EffectDirection")
        _require_text(self.rationale, "meaningful effect rationale")
        _require_text(self.source, "meaningful effect source")

    @property
    def as_float(self) -> float:
        """The magnitude at the boundary of the resolution arithmetic."""
        return float(self.magnitude)


class SampleRole(Enum):
    """What a sample is permitted to be used for."""

    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HOLDOUT = "holdout"

    @property
    def may_inform_design(self) -> bool:
        """Whether a realised measurement on this sample may shape a study design.

        **The holdout may not**, and that is the whole point of holding it out.
        A design justified by the holdout's own outcomes has already spent it.
        """
        return self is not SampleRole.HOLDOUT


@dataclass(frozen=True, slots=True)
class SampleFrame:
    """One sample's shape, stated **before** any outcome is measured over it.

    Every field here is knowable from sample metadata alone — counts, boundaries
    and structure — which is what lets a prospective assessment describe a
    holdout without opening it.

    ``population`` names the universe the frame is cut from. Two frames of the
    same population in different roles may not overlap in time: that is a
    development sample being scored again as validation. Frames of *different*
    populations may overlap freely — Milestone CA's holdout runs
    2024-06→2026-08 over 21 symbols the primary universe never contained, and a
    rule that refused it would refuse the one genuinely clean sample in the series.
    """

    name: str
    role: SampleRole
    population: str
    observations: int
    clusters: int
    time_blocks: int
    experimental_units: int
    starts_at: datetime
    ends_at: datetime
    largest_cluster_share: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.name, "sample name")
        _require_text(self.population, "sample population")
        if not isinstance(self.role, SampleRole):
            raise ResearchDesignError("sample role must be a SampleRole")
        _require_count(self.observations, "observations")
        _require_count(self.clusters, "clusters")
        _require_count(self.time_blocks, "time_blocks")
        _require_count(self.experimental_units, "experimental_units")
        if not isinstance(self.starts_at, datetime) or not isinstance(self.ends_at, datetime):
            raise ResearchDesignError("sample boundaries must be datetimes")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ResearchDesignError(
                "sample boundaries must be timezone-aware; a naive boundary is a "
                "different instant on two machines"
            )
        if self.ends_at <= self.starts_at:
            raise ResearchDesignError(
                f"sample {self.name!r} ends at {self.ends_at.isoformat()}, which is "
                f"not after it starts at {self.starts_at.isoformat()}"
            )
        if self.observations and not self.clusters:
            raise ResearchDesignError(
                f"sample {self.name!r} holds {self.observations} observation(s) in 0 "
                "clusters. Every observation belongs to some cluster, so a zero "
                "cluster count is a malformed frame rather than a thin one"
            )
        if self.clusters > self.observations:
            raise ResearchDesignError(
                f"sample {self.name!r} declares {self.clusters} clusters over "
                f"{self.observations} observations; a cluster with no observation in "
                "it contributes no information and inflates every 1/sqrt(K) term"
            )
        if self.experimental_units > self.observations:
            raise ResearchDesignError(
                f"sample {self.name!r} declares {self.experimental_units} experimental "
                f"units over {self.observations} observations. The unit is the coarser "
                "of the two by construction — several observations may share a setup, "
                "never the reverse"
            )
        if self.largest_cluster_share is not None:
            share = _require_fraction(
                self.largest_cluster_share, "largest_cluster_share", low=0.0, high=1.0
            )
            if self.clusters and share < 1.0 / self.clusters - 1e-12:
                raise ResearchDesignError(
                    f"sample {self.name!r} declares a largest cluster share of {share} "
                    f"over {self.clusters} clusters, but the largest of {self.clusters} "
                    f"shares cannot be below the uniform {1.0 / self.clusters:.6f}"
                )
            # A "share of zero with observations present" check used to sit here and
            # was DEAD: any frame holding an observation holds at least one cluster
            # (the malformed-frame check above), and the uniform-share check then
            # rejects a zero share for it. A guard that cannot fire is worse than no
            # guard — it reads as coverage that is not there.

    @property
    def observations_per_cluster(self) -> float | None:
        """Mean observations per cluster. ``None`` when there are no clusters."""
        if not self.clusters:
            return None
        return self.observations / self.clusters

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "population": self.population,
            "observations": self.observations,
            "clusters": self.clusters,
            "time_blocks": self.time_blocks,
            "experimental_units": self.experimental_units,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "largest_cluster_share": self.largest_cluster_share,
        }


def check_sample_frames(frames: tuple[SampleFrame, ...]) -> None:
    """Refuse a set of frames that could not all be what they claim to be."""
    seen: set[str] = set()
    for frame in frames:
        if frame.name in seen:
            raise ResearchDesignError(
                f"two sample frames are both named {frame.name!r}; a result that "
                "cannot say which sample it belongs to is a pooled result"
            )
        seen.add(frame.name)
    for index, first in enumerate(frames):
        for second in frames[index + 1 :]:
            if first.role is second.role or first.population != second.population:
                continue
            if first.starts_at < second.ends_at and second.starts_at < first.ends_at:
                raise ResearchDesignError(
                    f"sample {first.name!r} ({first.role.value}) and {second.name!r} "
                    f"({second.role.value}) are both cut from population "
                    f"{first.population!r} and their windows overlap. The same "
                    "observations cannot serve two roles: a validation sample that "
                    "shares instants with development has already been fitted"
                )


@dataclass(frozen=True, slots=True)
class DependenceModel:
    """How observations fail to be independent, stated as measurements.

    **The unit of evidence is the first field for a reason.** Milestone CA's gate
    ladder counted 8,793 four-hourly instants whose forward windows overlap by 23
    of 24 bars, and reported an unclustered mean over them; the claim did not
    survive symbol clustering. The number of rows was never the question.

    ``intracluster_correlation`` is the one field that may be ``None``, because it
    is frequently unknown — and a framework that invented one would produce a
    precise-looking effective sample size out of an assumption nobody made. When
    it is ``None`` every derived quantity that needs it is absent, with a reason.
    When it is supplied, ``correlation_source`` must say where it came from.
    """

    unit_of_evidence: str
    cluster_axis: str
    overlapping_horizon: int
    repeated_measurements: bool
    intracluster_correlation: float | None
    correlation_source: str | None
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.unit_of_evidence, "unit_of_evidence")
        _require_text(self.cluster_axis, "cluster_axis")
        _require_count(self.overlapping_horizon, "overlapping_horizon")
        if not isinstance(self.repeated_measurements, bool):
            raise ResearchDesignError("repeated_measurements must be a bool")
        if self.intracluster_correlation is not None:
            _require_fraction(
                self.intracluster_correlation,
                "intracluster_correlation",
                low=0.0,
                high=1.0,
            )
            _require_text(
                self.correlation_source or "",
                "correlation_source (required whenever an intracluster correlation "
                "is declared, so a reader can tell a measurement from a guess)",
            )
        elif self.correlation_source is not None:
            raise ResearchDesignError(
                "correlation_source was given with no intracluster_correlation; a "
                "source for a number that was not declared describes nothing"
            )
        if not isinstance(self.assumptions, tuple) or not self.assumptions:
            raise ResearchDesignError(
                "a dependence model must state at least one assumption. 'None' is "
                "itself an assumption and must be written down as one"
            )
        for item in self.assumptions:
            _require_text(item, "assumption")

    def payload(self) -> dict[str, Any]:
        return {
            "unit_of_evidence": self.unit_of_evidence,
            "cluster_axis": self.cluster_axis,
            "overlapping_horizon": self.overlapping_horizon,
            "repeated_measurements": self.repeated_measurements,
            "intracluster_correlation": self.intracluster_correlation,
            "correlation_source": self.correlation_source,
            "assumptions": list(self.assumptions),
        }


class EstimatorKind(Enum):
    """How uncertainty is obtained. Each carries its own validity conditions."""

    CLUSTER_BOOTSTRAP = "cluster_bootstrap"
    PAIRED_BOOTSTRAP = "paired_bootstrap"
    BLOCK_BOOTSTRAP = "block_bootstrap"
    PERMUTATION = "permutation"
    ANALYTIC_NORMAL = "analytic_normal"

    @property
    def is_resampling(self) -> bool:
        return self is not EstimatorKind.ANALYTIC_NORMAL

    @property
    def respects_clustering(self) -> bool:
        """Whether this estimator prices in dependence between observations.

        `PAIRED_BOOTSTRAP` and `ANALYTIC_NORMAL` do not: both treat observations
        as exchangeable, so applying either to clustered data reports an interval
        too narrow by exactly the dependence it ignored.
        """
        return self in (EstimatorKind.CLUSTER_BOOTSTRAP, EstimatorKind.BLOCK_BOOTSTRAP)


@dataclass(frozen=True, slots=True)
class EstimatorSpec:
    """Which estimator, at what confidence, and what has to be true for it to work.

    ``assumptions`` is required and non-empty. Milestone CA sealed a null whose
    own description said it "carries the same clustering as the observed effect"
    when it did not; the claim sat inside a digest and could not be corrected.
    An estimator that must list its assumptions as data can at least be checked
    against what it does.

    A resampling estimator is additionally refused when its replicate count
    cannot resolve the tail it is asked for: 2,000 replicates can place a 2.5 %
    quantile, and 20 replicates asked for a 99.9 % interval is reporting the
    extremum of twenty numbers as a confidence bound.
    """

    kind: EstimatorKind
    comparison: ComparisonType
    resamples: int
    confidence: float
    assumptions: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EstimatorKind):
            raise ResearchDesignError("estimator kind must be an EstimatorKind")
        if not isinstance(self.comparison, ComparisonType):
            raise ResearchDesignError("estimator comparison must be a ComparisonType")
        _require_count(self.resamples, "resamples")
        confidence = _require_fraction(self.confidence, "confidence", low=0.0, high=1.0)
        if not 0.0 < confidence < 1.0:
            raise ResearchDesignError(
                f"confidence must lie strictly inside (0, 1), got {confidence}. A "
                "0 % interval is a point and a 100 % interval is the real line; "
                "neither can exclude anything"
            )
        if not isinstance(self.assumptions, tuple) or not self.assumptions:
            raise ResearchDesignError(
                "an estimator must state the assumptions that make it valid; a "
                "method whose validity conditions are not written down cannot be "
                "checked against the data it was applied to"
            )
        for item in self.assumptions:
            _require_text(item, "assumption")
        _require_text(self.rationale, "estimator rationale")
        if self.kind.is_resampling:
            if self.resamples < 1:
                raise ResearchDesignError(
                    f"{self.kind.value} needs at least one replicate, got {self.resamples}"
                )
            tail = (1.0 - confidence) / 2.0
            if self.resamples * tail < 1.0:
                raise ResearchDesignError(
                    f"{self.resamples} replicates cannot resolve a {confidence:.4g} "
                    f"interval: its tail holds {self.resamples * tail:.4g} replicate(s), "
                    "so the reported bound would be the extremum of the draws rather "
                    "than a quantile of them"
                )
        elif self.resamples:
            raise ResearchDesignError(
                f"{self.kind.value} draws nothing, so it cannot declare "
                f"{self.resamples} resamples"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "comparison": self.comparison.value,
            "resamples": self.resamples,
            "confidence": self.confidence,
            "assumptions": list(self.assumptions),
            "rationale": self.rationale,
        }


class ResolutionCriterion(Enum):
    """What "can detect it" is taken to mean. The two are not interchangeable."""

    #: The interval around an effect of exactly the meaningful magnitude excludes
    #: zero. This is a **coin-flip** criterion: it is met when the true effect is
    #: the declared magnitude and the estimate lands exactly on it, which happens
    #: about half the time. Milestone CA's ~4,800 figure is of this kind.
    INTERVAL_EXCLUDES_ZERO = "interval_excludes_zero"

    #: A stated share of repetitions produce an interval excluding zero. Costs
    #: roughly 2x the observations of the criterion above at 80 %.
    POWERED_DETECTION = "powered_detection"


@dataclass(frozen=True, slots=True)
class DesignTarget:
    """What the design has to achieve, and the structural floors it must clear.

    ``minimum_clusters``, ``minimum_time_blocks`` and ``maximum_cluster_share``
    are **declared by the caller**, not owned here. A cluster bootstrap over three
    symbols has three numbers to resample and reports an interval built from
    three; whether that is acceptable is a property of the study, so the study
    states it and this package checks it.

    ``maximum_information_multiple`` is how much more information the study is
    willing to acquire, as a multiple of what it has. It is what makes *"the
    effect threshold is the binding constraint"* a checkable statement rather
    than an opinion: when the cheapest reachable growth path costs more than this,
    the design's problem is the size of the effect it declared, not the data.
    ``None`` leaves it uncapped.
    """

    criterion: ResolutionCriterion
    confidence: float
    power: float | None
    minimum_clusters: int
    minimum_time_blocks: int
    maximum_cluster_share: float
    maximum_information_multiple: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, ResolutionCriterion):
            raise ResearchDesignError("criterion must be a ResolutionCriterion")
        confidence = _require_fraction(self.confidence, "target confidence", low=0.0, high=1.0)
        if not 0.0 < confidence < 1.0:
            raise ResearchDesignError(
                f"target confidence must lie strictly inside (0, 1), got {confidence}"
            )
        _require_count(self.minimum_clusters, "minimum_clusters", minimum=1)
        _require_count(self.minimum_time_blocks, "minimum_time_blocks", minimum=1)
        if self.maximum_information_multiple is not None:
            if isinstance(self.maximum_information_multiple, bool) or not isinstance(
                self.maximum_information_multiple, (int, float)
            ):
                raise ResearchDesignError("maximum_information_multiple must be a real number")
            if float(self.maximum_information_multiple) < 1.0:
                raise ResearchDesignError(
                    "maximum_information_multiple must be at least 1.0, got "
                    f"{self.maximum_information_multiple}. Below 1 it asks the study "
                    "to acquire less information than it already has"
                )
        share = _require_fraction(
            self.maximum_cluster_share, "maximum_cluster_share", low=0.0, high=1.0
        )
        if share <= 0.0:
            raise ResearchDesignError(
                "maximum_cluster_share must be strictly positive; a bound of zero "
                "admits no design at all"
            )
        if self.criterion is ResolutionCriterion.POWERED_DETECTION:
            if self.power is None:
                raise ResearchDesignError(
                    "POWERED_DETECTION requires a power target; without one it is "
                    "INTERVAL_EXCLUDES_ZERO wearing a stronger name"
                )
            power = _require_fraction(self.power, "power", low=0.0, high=1.0)
            if not 0.5 < power < 1.0:
                raise ResearchDesignError(
                    f"power must lie strictly inside (0.5, 1.0), got {power}. Below "
                    "0.5 the design is worse than the interval-excludes-zero "
                    "criterion it would replace, and 1.0 needs infinite data"
                )
        elif self.power is not None:
            raise ResearchDesignError(
                "INTERVAL_EXCLUDES_ZERO carries no power target. It is a coin-flip "
                "criterion by construction — met about half the time when the true "
                "effect equals the declared magnitude — and attaching a power number "
                "to it would claim a guarantee it does not make"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion.value,
            "confidence": self.confidence,
            "power": self.power,
            "minimum_clusters": self.minimum_clusters,
            "minimum_time_blocks": self.minimum_time_blocks,
            "maximum_cluster_share": self.maximum_cluster_share,
            "maximum_information_multiple": self.maximum_information_multiple,
        }


class AssessmentMode(Enum):
    """When the assessment was made relative to the measurement. **Never a label.**

    Nothing in this package lets a caller set this. `ProspectiveDesign` and
    `PostHocResolution` each expose it as a constant property, and the function
    that builds each takes inputs only the corresponding mode can have: an
    *assumed* dispersion for the first, a *realised* interval width for the
    second. Reporting a post-hoc calculation as prospective power is the single
    most common way an underpowered study is made to look planned, and here it is
    unreachable rather than discouraged.
    """

    PROSPECTIVE = "prospective"
    POST_HOC = "post_hoc"

    @property
    def may_justify_running_a_study(self) -> bool:
        return self is AssessmentMode.PROSPECTIVE


class DesignVerdict(Enum):
    """What the design can do. **No member says anything about the hypothesis.**

    A test asserts `says_nothing_about_the_hypothesis` over the whole enum, in the
    same way Milestone CA asserts `is_approved_for_trading` is `False` for every
    one of its verdicts. This gate answers whether an experiment can answer its
    question; whether the answer is favourable is not its business and there is no
    member it could use to say so.
    """

    READY = "ready"
    LIMITED = "limited"
    UNDERPOWERED = "underpowered"
    MISALIGNED_UNIT = "misaligned_unit"
    INSUFFICIENT_INDEPENDENCE = "insufficient_independence"
    NOT_MEASURABLE = "not_measurable"

    @property
    def may_proceed(self) -> bool:
        """Whether the study can be run and expect to resolve its declared effect."""
        return self in (DesignVerdict.READY, DesignVerdict.LIMITED)

    @property
    def says_nothing_about_the_hypothesis(self) -> bool:
        return True


class LimitingFactor(Enum):
    """Which dimension binds. The answer to *"more of what?"*."""

    CLUSTER_COUNT = "cluster_count"
    OBSERVATION_COUNT = "observation_count"
    CLUSTER_CONCENTRATION = "cluster_concentration"
    TIME_BLOCKS = "time_blocks"
    EFFECT_SIZE = "effect_size"
    ESTIMATOR_RESOLUTION = "estimator_resolution"
    UNIT_MISMATCH = "unit_mismatch"
    NONE = "none"


class GrowthPath(Enum):
    """How a design would acquire more information. **They are not equivalent.**

    This is the distinction Milestone CA's ~4,800 figure does not make. Under
    `MORE_CLUSTERS_SAME_DENSITY` that figure is right for any intracluster
    correlation. Under `MORE_OBSERVATIONS_SAME_CLUSTERS` it is unreachable for
    any correlation above zero, because the interval half-width approaches a floor
    set by the between-cluster spread and the cluster count — and no quantity of
    additional history inside the same symbols goes below it.
    """

    #: More clusters at the same observations-per-cluster. More symbols, same years.
    MORE_CLUSTERS_SAME_DENSITY = "more_clusters_same_density"

    #: More observations inside the existing clusters. More years, same symbols.
    MORE_OBSERVATIONS_SAME_CLUSTERS = "more_observations_same_clusters"

    #: Every observation independent. The assumption a plain 1/sqrt(n) rule makes,
    #: kept as a named path so that assuming it is a visible choice.
    INDEPENDENT_OBSERVATIONS = "independent_observations"


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    """What is being asked, in the form the design has to answer."""

    question_id: str
    description: str
    primary_metric: str
    comparison: ComparisonType

    def __post_init__(self) -> None:
        _require_text(self.question_id, "question_id")
        _require_text(self.description, "question description")
        _require_text(self.primary_metric, "primary_metric")
        if not isinstance(self.comparison, ComparisonType):
            raise ResearchDesignError("comparison must be a ComparisonType")

    def payload(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "description": self.description,
            "primary_metric": self.primary_metric,
            "comparison": self.comparison.value,
        }


#: The multiplier that turns an interval-excludes-zero requirement into a powered
#: one, applied to the required *variance* and therefore to the required
#: information. Derived rather than tabulated: ((z_a + z_b) / z_a)^2.
POWER_INFLATION_NOTE: Final[str] = (
    "A POWERED_DETECTION target costs ((z_confidence + z_power) / z_confidence)^2 "
    "times the information of an INTERVAL_EXCLUDES_ZERO target at the same "
    "confidence — about 2.04x at 95 % confidence and 80 % power."
)
