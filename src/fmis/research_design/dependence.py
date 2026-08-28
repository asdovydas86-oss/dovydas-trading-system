"""How much information is actually here. **Several numbers, not one.**

The temptation is to collapse a sample into a single "effective N" and compare
designs on it. This module resists that, because the collapse hides exactly the
thing a research design has to decide: *more of what?*

An honest profile reads:

    observations                 155
    clusters (symbol)             15
    observations per cluster    10.3
    independent time blocks        4
    experimental units           155
    largest cluster share      0.113
    overlapping horizon           24 bar(s)

Every one of those is a fact about the sample and none of them needs an
assumption. A single effective sample size needs one — the intracluster
correlation — and this module offers it **only** when that correlation has been
declared, always with the derivation attached and the assumption named. When it
has not been declared, `effective_observations` is `None` with a reason, which is
a true statement about what is known. A framework that guessed a correlation in
order to print a tidier number would be manufacturing precision out of nothing,
and the number it printed would be the one a reader trusted most.

**The design effect, stated in full.** For a mean over ``K`` clusters holding
``m`` observations each, with intracluster correlation ``rho``:

    design_effect = 1 + (m - 1) * rho
    effective_observations = observations / design_effect

At ``rho = 0`` the design effect is 1 and every row is an experiment. At
``rho = 1`` it is ``m`` and each cluster contributes exactly one, however many
rows it holds. The formula assumes equal cluster sizes and is an approximation
whenever they differ; that assumption is carried in `InformationProfile.derivation`
rather than left in this docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fmis.research_design.models import (
    DependenceModel,
    ResearchDesignError,
    SampleFrame,
)

__all__ = [
    "InformationProfile",
    "design_effect",
    "effective_observations",
    "profile_of",
]

_NO_CORRELATION_DECLARED = (
    "No intracluster correlation was declared, so no single effective sample "
    "size is offered. The dimensions above are what is known; collapsing them "
    "would require assuming the number this design does not have."
)

_DERIVATION = (
    "effective_observations = observations / (1 + (observations_per_cluster - 1) "
    "* intracluster_correlation), the standard design effect for a cluster mean. "
    "ASSUMES equal cluster sizes and a common within-cluster correlation; with "
    "unequal clusters it is an approximation that understates the loss when the "
    "largest cluster is much larger than the mean."
)


def design_effect(observations_per_cluster: float, intracluster_correlation: float) -> float:
    """``1 + (m - 1) * rho``. The factor by which clustering costs information.

    Raises:
        ResearchDesignError: ``m`` is below 1, ``rho`` is outside [0, 1], or the
            pair would produce a design effect below 1 — which would claim
            clustering *added* information.
    """
    if isinstance(observations_per_cluster, bool) or not isinstance(
        observations_per_cluster, (int, float)
    ):
        raise ResearchDesignError("observations_per_cluster must be a real number")
    if isinstance(intracluster_correlation, bool) or not isinstance(
        intracluster_correlation, (int, float)
    ):
        raise ResearchDesignError("intracluster_correlation must be a real number")
    per_cluster = float(observations_per_cluster)
    rho = float(intracluster_correlation)
    if per_cluster < 1.0:
        raise ResearchDesignError(
            f"observations_per_cluster must be at least 1, got {per_cluster}. A "
            "cluster holding less than one observation is a malformed frame"
        )
    if not 0.0 <= rho <= 1.0:
        raise ResearchDesignError(
            f"intracluster_correlation must lie in [0, 1], got {rho}"
        )
    return 1.0 + (per_cluster - 1.0) * rho


def effective_observations(
    observations: int,
    observations_per_cluster: float,
    intracluster_correlation: float,
) -> float:
    """``observations / design_effect``. Always at most ``observations``.

    Raises:
        ResearchDesignError: any argument is malformed. See `design_effect`.
    """
    if isinstance(observations, bool) or not isinstance(observations, int):
        raise ResearchDesignError("observations must be an int")
    if observations < 0:
        raise ResearchDesignError(f"observations must be >= 0, got {observations}")
    return observations / design_effect(observations_per_cluster, intracluster_correlation)


@dataclass(frozen=True, slots=True)
class InformationProfile:
    """One sample's information, in every dimension that can be stated.

    `effective` is `None` unless the dependence model declared an intracluster
    correlation, and `derivation` always says which of the two situations holds.
    """

    sample: str
    observations: int
    clusters: int
    observations_per_cluster: float | None
    time_blocks: int
    experimental_units: int
    largest_cluster_share: float | None
    overlapping_horizon: int
    cluster_axis: str
    unit_of_evidence: str
    design_effect: float | None
    effective_observations: float | None
    derivation: str

    @property
    def has_effective_estimate(self) -> bool:
        return self.effective_observations is not None

    def payload(self) -> dict[str, Any]:
        return {
            "sample": self.sample,
            "observations": self.observations,
            "clusters": self.clusters,
            "observations_per_cluster": self.observations_per_cluster,
            "time_blocks": self.time_blocks,
            "experimental_units": self.experimental_units,
            "largest_cluster_share": self.largest_cluster_share,
            "overlapping_horizon": self.overlapping_horizon,
            "cluster_axis": self.cluster_axis,
            "unit_of_evidence": self.unit_of_evidence,
            "design_effect": self.design_effect,
            "effective_observations": self.effective_observations,
            "derivation": self.derivation,
        }


def profile_of(frame: SampleFrame, dependence: DependenceModel) -> InformationProfile:
    """Read one sample's information dimensions. **Reads no outcome, ever.**

    Every input is sample *metadata* — counts, boundaries, declared structure —
    so this is computable for a holdout that has never been opened. That property
    is what lets a prospective design assessment describe a holdout's adequacy
    without spending it, and a regression asserts it.
    """
    if not isinstance(frame, SampleFrame):
        raise TypeError("frame must be a SampleFrame")
    if not isinstance(dependence, DependenceModel):
        raise TypeError("dependence must be a DependenceModel")

    per_cluster = frame.observations_per_cluster
    rho = dependence.intracluster_correlation
    deff: float | None = None
    effective: float | None = None
    if rho is None or per_cluster is None or per_cluster < 1.0:
        derivation = (
            _NO_CORRELATION_DECLARED
            if rho is None
            else (
                "This sample holds no cluster with a whole observation in it, so a "
                "design effect is undefined for it."
            )
        )
    else:
        deff = design_effect(per_cluster, rho)
        effective = frame.observations / deff
        derivation = f"{_DERIVATION} Declared correlation {rho}, source: {dependence.correlation_source}."

    return InformationProfile(
        sample=frame.name,
        observations=frame.observations,
        clusters=frame.clusters,
        observations_per_cluster=per_cluster,
        time_blocks=frame.time_blocks,
        experimental_units=frame.experimental_units,
        largest_cluster_share=frame.largest_cluster_share,
        overlapping_horizon=dependence.overlapping_horizon,
        cluster_axis=dependence.cluster_axis,
        unit_of_evidence=dependence.unit_of_evidence,
        design_effect=deff,
        effective_observations=effective,
        derivation=derivation,
    )
