"""Builders for research designs, so a test states only what it is varying.

Every default here is deliberately valid and deliberately boring. A test that
wants a malformed sample says so in one keyword; a test that wants everything
correct says nothing at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import sqrt
from random import Random

from fmis.research_design.models import (
    ComparisonType,
    DependenceModel,
    DesignTarget,
    EffectDirection,
    EstimatorKind,
    EstimatorSpec,
    MeaningfulEffect,
    MetricUnit,
    ResearchQuestion,
    ResolutionCriterion,
    SampleFrame,
    SampleRole,
)
from fmis.research_design.resolution import ClusteredObservation

UNIT = MetricUnit(code="atr", description="average true range at the decision bar")
OTHER_UNIT = MetricUnit(code="r", description="risk multiples of the initial stop")

START = datetime(2023, 6, 1, tzinfo=timezone.utc)


def a_unit(code: str = "atr") -> MetricUnit:
    return MetricUnit(code=code, description=f"the {code} unit, for testing")


def an_effect(magnitude: str = "0.10", unit: MetricUnit | None = None) -> MeaningfulEffect:
    return MeaningfulEffect(
        magnitude=Decimal(magnitude),
        unit=unit or UNIT,
        direction=EffectDirection.GREATER,
        rationale="the round-trip cost of acting on it",
        source="a test",
    )


def a_question() -> ResearchQuestion:
    return ResearchQuestion(
        question_id="q-1",
        description="does the rule select better than a matched control?",
        primary_metric="paired difference in forward excursion",
        comparison=ComparisonType.PAIRED_DIFFERENCE,
    )


def a_frame(
    *,
    name: str = "development",
    role: SampleRole = SampleRole.DEVELOPMENT,
    population: str = "primary",
    observations: int = 155,
    clusters: int = 15,
    time_blocks: int = 4,
    experimental_units: int | None = None,
    months: int = 24,
    starts_at: datetime | None = None,
    largest_cluster_share: float | None = 0.113,
) -> SampleFrame:
    begin = starts_at or START
    return SampleFrame(
        name=name,
        role=role,
        population=population,
        observations=observations,
        clusters=clusters,
        time_blocks=time_blocks,
        experimental_units=observations if experimental_units is None else experimental_units,
        starts_at=begin,
        ends_at=begin + timedelta(days=30 * months),
        largest_cluster_share=largest_cluster_share,
    )


def a_dependence(
    *,
    correlation: float | None = None,
    source: str | None = None,
    overlapping_horizon: int = 60,
    repeated: bool = False,
) -> DependenceModel:
    return DependenceModel(
        unit_of_evidence="one admitted decision instant",
        cluster_axis="symbol",
        overlapping_horizon=overlapping_horizon,
        repeated_measurements=repeated,
        intracluster_correlation=correlation,
        correlation_source=source if correlation is not None else None,
        assumptions=("symbols are exchangeable",),
    )


def an_estimator(
    *,
    kind: EstimatorKind = EstimatorKind.CLUSTER_BOOTSTRAP,
    resamples: int = 2000,
    confidence: float = 0.95,
) -> EstimatorSpec:
    return EstimatorSpec(
        kind=kind,
        comparison=ComparisonType.PAIRED_DIFFERENCE,
        resamples=0 if kind is EstimatorKind.ANALYTIC_NORMAL else resamples,
        confidence=confidence,
        assumptions=("symbols are exchangeable",),
        rationale="resampling admissions individually would understate the width",
    )


def a_target(
    *,
    criterion: ResolutionCriterion = ResolutionCriterion.INTERVAL_EXCLUDES_ZERO,
    confidence: float = 0.95,
    power: float | None = None,
    minimum_clusters: int = 2,
    minimum_time_blocks: int = 2,
    maximum_cluster_share: float = 0.40,
    maximum_information_multiple: float | None = None,
) -> DesignTarget:
    return DesignTarget(
        criterion=criterion,
        confidence=confidence,
        power=power,
        minimum_clusters=minimum_clusters,
        minimum_time_blocks=minimum_time_blocks,
        maximum_cluster_share=maximum_cluster_share,
        maximum_information_multiple=maximum_information_multiple,
    )


def clustered_sample(
    *,
    clusters: int = 15,
    per_cluster: int = 10,
    between_sd: float = 0.0,
    within_sd: float = 1.0,
    mean: float = 0.0,
    seed: int = 11,
) -> tuple[ClusteredObservation, ...]:
    """A synthetic clustered sample with a KNOWN variance decomposition.

    ``between_sd`` is the standard deviation of the cluster means and ``within_sd``
    the standard deviation inside a cluster, so the true intracluster correlation
    is ``between_sd^2 / (between_sd^2 + within_sd^2)``. Generated from seeded
    generators so a test is a fixed sample rather than a distribution.

    **The two draws use two generators, deliberately.** An earlier version drew the
    cluster offsets and the within-cluster noise from one interleaved stream, which
    meant the cluster MEANS changed whenever ``per_cluster`` changed — so a test
    comparing the same design at two densities was comparing two different sets of
    clusters and could conclude that extra rows had bought information they had
    not. The offsets now come from a generator seeded independently of
    ``per_cluster``, so growing the density holds the cluster means fixed and the
    comparison means what it says.
    """
    # A str seed is hashed with SHA-512 by `random.seed`, so these are stable
    # across processes and across PYTHONHASHSEED. `per_cluster` appears in the
    # noise identity and NOT in the offset identity: that is the whole fix.
    offsets = Random(f"offsets|{seed}|{clusters}|{between_sd}|{mean}")
    noise = Random(f"noise|{seed}|{clusters}|{per_cluster}|{within_sd}")
    out: list[ClusteredObservation] = []
    for index in range(clusters):
        offset = offsets.gauss(0.0, between_sd) if between_sd else 0.0
        for _ in range(per_cluster):
            out.append(
                ClusteredObservation(
                    cluster=f"C{index:03d}",
                    value=mean + offset + noise.gauss(0.0, within_sd),
                )
            )
    return tuple(out)


def true_correlation(between_sd: float, within_sd: float) -> float:
    total = between_sd**2 + within_sd**2
    return 0.0 if total == 0 else between_sd**2 / total


def analytic_half_width(
    *, sd: float, clusters: int, per_cluster: float, correlation: float, z: float
) -> float:
    factor = correlation + (1.0 - correlation) / per_cluster
    return z * sd * sqrt(factor / clusters)
