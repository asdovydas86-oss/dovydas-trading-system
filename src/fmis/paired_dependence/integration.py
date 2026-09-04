"""Feeding CD's dependence back into Milestone CB, and re-reading Milestone CC.

**No second power calculator is written here.** Milestone CB owns the design
arithmetic and `fmis.swing_lab.admission_power.ca_required_information` is the
adapter that applies it to Milestone CA's published sample. Both are *called*.
What this module adds is the one step CB could not take and CC could not measure:
the requirement CB reports is stated in **independent** clusters, and CD has now
measured how far from independent the clusters actually are.

**The arithmetic, in full.**

Milestone CB's `GrowthPath.MORE_CLUSTERS_SAME_DENSITY` answers *how many clusters
at the observed density resolve the effect*, and its answer — roughly 467 — is
the same for every intracluster correlation, because growing ``K`` at fixed ``m``
scales the whole variance by ``1/K``. That is true **only while the clusters are
independent of one another**. If they share a common component with correlation
``r``, ``K`` real clusters supply

    K_eff = K / (1 + (K - 1) r)

independent ones, so ``K*`` independent clusters are bought at

    K = K* (1 - r) / (1 - K* r)      and only while r < 1 / K*.

At ``r = 1 / K*`` the denominator reaches zero and ``K_eff`` saturates **below**
the requirement: no universe of any size satisfies it. With ``K* ≈ 467`` the
threshold is ``r ≈ 0.00214``, which is the single most consequential number
Milestone CD has to compare its measurement against — and it is small enough that
the honest question is not *"is r above or below it"* but *"can this panel
resolve r to that precision at all"*.

**Two dependence parameters enter at two different places.** ``rho_w`` — the
within-asset correlation — is what `DependenceModel.intracluster_correlation` has
been `None` for since Milestone CB was written (limitation CB-2), and CD supplies
it. ``r_b`` — the between-asset correlation — is what the inversion above
consumes. Substituting one for the other would be wrong by orders of magnitude in
the direction that flatters the design, and `CD_INTERPRETATION_RULES` forbids it.

**Milestone CC's verdict is not rewritten.** `cc_reevaluation` reports what CC's
own measured ceiling — 106 economic assets and roughly 1,089 admissions over the
provider's entire history — becomes when read against CD's requirement. CC's
`INFEASIBLE` on `cluster_count` stands as the historical record; this is a
refinement recorded beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from fmis.paired_dependence.estimator import (
    effective_clusters_from,
    required_clusters_under_dependence,
)
from fmis.paired_dependence.models import (
    PairedDependenceError,
    RequirementOutcome,
    require_count,
)

__all__ = [
    "CC_PROVIDER_CEILING_CLUSTERS",
    "CC_PROVIDER_CEILING_ADMISSIONS",
    "CC_ELIGIBLE_ASSETS",
    "CC_CEILING_SOURCE",
    "RequirementPoint",
    "RequirementAssessment",
    "cb_required_clusters",
    "requirement_at",
    "assess_requirement",
    "cc_reevaluation",
]

#: Milestone CC's measured post-hoc ceiling: every year the provider has ever
#: produced, for every economic asset that could reach the production warm-up.
#: Quoted from report 0039 rather than recomputed, and labelled as CC's own
#: figure so a reader can see which milestone is responsible for it.
CC_PROVIDER_CEILING_CLUSTERS: Final[int] = 106
CC_PROVIDER_CEILING_ADMISSIONS: Final[int] = 1089
CC_ELIGIBLE_ASSETS: Final[int] = 38
CC_CEILING_SOURCE: Final[str] = (
    "report 0039 §13 — the post-hoc provider-history ceiling, explicitly not "
    "pre-registered by Milestone CC and able only to FAVOUR feasibility, quoted "
    "here as CC measured it"
)


@dataclass(frozen=True, slots=True)
class RequirementPoint:
    """The information requirement at one value of the between-cluster correlation."""

    label: str
    correlation: float | None
    reachable: bool
    required_clusters: float | None
    required_admissions: float | None
    effective_clusters_at_requirement: float | None
    saturation_ceiling: float | None
    note: str

    def payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "correlation": self.correlation,
            "reachable": self.reachable,
            "required_clusters": self.required_clusters,
            "required_admissions": self.required_admissions,
            "effective_clusters_at_requirement": self.effective_clusters_at_requirement,
            "saturation_ceiling": self.saturation_ceiling,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class RequirementAssessment:
    """Milestone CB's requirement, re-read at CD's point estimate and both bounds."""

    independent_clusters: int
    independent_admissions: int
    observations_per_cluster: float
    saturation_threshold: float
    within_asset_correlation: float | None
    point: RequirementPoint
    lower: RequirementPoint
    upper: RequirementPoint
    outcome: RequirementOutcome
    reasoning: str

    @property
    def order_of_magnitude_span(self) -> float | None:
        """``upper / lower`` on the required cluster count, or `None` if unbounded."""
        low = self.lower.required_clusters
        high = self.upper.required_clusters
        if low is None or high is None or low <= 0.0:
            return None
        return high / low

    def payload(self) -> dict[str, Any]:
        return {
            "independent_clusters": self.independent_clusters,
            "independent_admissions": self.independent_admissions,
            "observations_per_cluster": self.observations_per_cluster,
            "saturation_threshold": self.saturation_threshold,
            "within_asset_correlation": self.within_asset_correlation,
            "point": self.point.payload(),
            "lower": self.lower.payload(),
            "upper": self.upper.payload(),
            "order_of_magnitude_span": self.order_of_magnitude_span,
            "outcome": self.outcome.value,
            "reasoning": self.reasoning,
        }


def cb_required_clusters(
    *, sample: str = "development", intracluster_correlation: float = 0.0
) -> tuple[int, int, float]:
    """Milestone CB's requirement on the more-clusters path. **CB's function, called.**

    Returns ``(clusters, admissions, observations_per_cluster)``. The requirement
    is the same at every intracluster correlation on this path — CB says so and a
    regression asserts it — so the parameter exists to make that invariance
    checkable rather than to change the answer.

    Raises:
        PairedDependenceError: Milestone CB refuses the request, or returns a
            path with no cluster requirement on it.
    """
    from fmis.research_design.models import GrowthPath, ResearchDesignError
    from fmis.swing_lab.admission_power import ca_required_information

    try:
        needed = ca_required_information(
            GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
            intracluster_correlation,
            sample=sample,
        )
    except ResearchDesignError as error:
        raise PairedDependenceError(
            f"Milestone CB refused the requirement for sample {sample!r}: {error}"
        ) from None
    if needed.required_clusters is None or needed.required_observations is None:
        raise PairedDependenceError(
            "Milestone CB returned no cluster requirement on the more-clusters "
            "path; CD has nothing to apply a dependence to"
        )
    return (
        needed.required_clusters,
        needed.required_observations,
        needed.required_observations_per_cluster or 0.0,
    )


def requirement_at(
    correlation: float | None,
    *,
    label: str,
    independent_clusters: int,
    observations_per_cluster: float,
) -> RequirementPoint:
    """What ``correlation`` does to a requirement of ``independent_clusters``.

    A `None` correlation returns the undependent requirement with a note saying
    so — **not** a zero, which would silently assert independence.
    """
    require_count(independent_clusters, "independent_clusters", minimum=1)
    threshold = 1.0 / independent_clusters
    if correlation is None:
        return RequirementPoint(
            label=label,
            correlation=None,
            reachable=True,
            required_clusters=float(independent_clusters),
            required_admissions=independent_clusters * observations_per_cluster,
            effective_clusters_at_requirement=float(independent_clusters),
            saturation_ceiling=None,
            note=(
                "No correlation was identified at this bound, so the requirement "
                "is stated at Milestone CB's independent-cluster figure and is "
                "conditional on an assumption CD did NOT verify"
            ),
        )
    needed, reachable = required_clusters_under_dependence(
        independent_clusters, correlation
    )
    truncated = min(1.0, max(0.0, float(correlation)))
    ceiling = (1.0 / truncated) if truncated > 0.0 else None
    if not reachable:
        return RequirementPoint(
            label=label,
            correlation=correlation,
            reachable=False,
            required_clusters=None,
            required_admissions=None,
            effective_clusters_at_requirement=None,
            saturation_ceiling=ceiling,
            note=(
                f"UNREACHABLE. A between-cluster correlation of {correlation:.6f} "
                f"is at or above the saturation threshold {threshold:.6f}, so the "
                f"effective cluster count never passes {ceiling:.1f} however many "
                f"economic assets are added, and {independent_clusters} "
                "independent clusters are never bought"
            ),
        )
    assert needed is not None
    return RequirementPoint(
        label=label,
        correlation=correlation,
        reachable=True,
        required_clusters=needed,
        required_admissions=needed * observations_per_cluster,
        effective_clusters_at_requirement=effective_clusters_from(
            max(1, int(needed + 0.5)), correlation
        ),
        saturation_ceiling=ceiling,
        note=(
            f"At a between-cluster correlation of {correlation:.6f}, "
            f"{needed:.1f} economic assets supply {independent_clusters} "
            "independent clusters"
        ),
    )


def assess_requirement(
    *,
    point: float | None,
    lower: float | None,
    upper: float | None,
    within_asset_correlation: float | None,
    sample: str = "development",
    provider_ceiling: int = CC_PROVIDER_CEILING_CLUSTERS,
) -> RequirementAssessment:
    """Milestone CB's requirement, re-read across CD's whole interval.

    The outcome follows `CD_REQUIREMENT_RULES` exactly and reads the interval
    before the point estimate, because an interval that straddles the saturation
    threshold means the same data supports both a finite requirement and none —
    which is `INCONCLUSIVE` however tidy the point estimate looks.
    """
    require_count(provider_ceiling, "provider_ceiling", minimum=1)
    clusters, admissions, per_cluster = cb_required_clusters(sample=sample)
    threshold = 1.0 / clusters
    at_point = requirement_at(
        point,
        label="point_estimate",
        independent_clusters=clusters,
        observations_per_cluster=per_cluster,
    )
    at_low = requirement_at(
        lower,
        label="lower_bound",
        independent_clusters=clusters,
        observations_per_cluster=per_cluster,
    )
    at_high = requirement_at(
        upper,
        label="upper_bound",
        independent_clusters=clusters,
        observations_per_cluster=per_cluster,
    )

    straddles = (
        lower is not None
        and upper is not None
        and lower <= 0.0
        and upper >= threshold
    )
    if lower is None or upper is None:
        outcome = RequirementOutcome.INCONCLUSIVE
        reasoning = (
            "No interval was produced, so the requirement cannot be stated across "
            "the range of correlations the data supports. A point estimate alone "
            "is not a design input"
        )
    elif straddles:
        outcome = RequirementOutcome.INCONCLUSIVE
        reasoning = (
            f"The interval [{lower:.6f}, {upper:.6f}] spans from at or below zero "
            f"to at or above the saturation threshold {threshold:.6f}. The same "
            "data supports 'no dependence penalty at all' and 'unreachable at any "
            "universe size', which is not a design input"
        )
    elif not at_point.reachable:
        outcome = RequirementOutcome.UNREACHABLE
        reasoning = (
            f"The point estimate {point:.6f} is at or above the saturation "
            f"threshold {threshold:.6f}. The effective cluster count saturates "
            f"below {clusters} however many economic assets are added"
        )
    elif at_high.reachable and at_high.required_clusters is not None and (
        at_high.required_clusters <= provider_ceiling
    ):
        outcome = RequirementOutcome.RESOLVABLE
        reasoning = (
            f"Even at the upper bound the requirement is "
            f"{at_high.required_clusters:.0f} economic assets, at or below the "
            f"{provider_ceiling} Milestone CC measured as the provider's ceiling"
        )
    else:
        outcome = RequirementOutcome.UNDERPOWERED
        reasoning = (
            "The requirement is finite across the interval but exceeds the "
            f"{provider_ceiling} economic assets Milestone CC measured as the "
            "provider's entire-history ceiling"
            if at_high.reachable
            else (
                "The requirement is finite at the point estimate but unreachable "
                f"at the upper bound {upper:.6f}, so the universe needed is not "
                "bounded by anything this data can state"
            )
        )

    return RequirementAssessment(
        independent_clusters=clusters,
        independent_admissions=admissions,
        observations_per_cluster=per_cluster,
        saturation_threshold=threshold,
        within_asset_correlation=within_asset_correlation,
        point=at_point,
        lower=at_low,
        upper=at_high,
        outcome=outcome,
        reasoning=reasoning,
    )


def cc_reevaluation(assessment: RequirementAssessment) -> dict[str, Any]:
    """Milestone CC's feasibility comparison, recomputed under CD's dependence.

    **CC's verdict is not altered.** `INFEASIBLE` on `cluster_count` is the
    historical record of what CC measured under what CC sealed. This answers the
    six questions the CD brief asks about that record and records the answers
    beside it.
    """
    if not isinstance(assessment, RequirementAssessment):
        raise PairedDependenceError("assessment must be a RequirementAssessment")
    point = assessment.point
    return {
        "cc_verdict_preserved": "infeasible",
        "cc_binding_constraint_preserved": "cluster_count",
        "cc_eligible_assets": CC_ELIGIBLE_ASSETS,
        "cc_provider_ceiling_clusters": CC_PROVIDER_CEILING_CLUSTERS,
        "cc_provider_ceiling_admissions": CC_PROVIDER_CEILING_ADMISSIONS,
        "cc_ceiling_source": CC_CEILING_SOURCE,
        "ceiling_still_below_requirement": (
            None
            if point.required_clusters is None and point.reachable
            else (
                True
                if point.required_clusters is None
                else point.required_clusters > CC_PROVIDER_CEILING_CLUSTERS
            )
        ),
        "is_467_still_the_right_order_of_magnitude": (
            None
            if point.required_clusters is None
            else 0.1
            <= point.required_clusters / assessment.independent_clusters
            <= 10.0
        ),
        "does_positive_dependence_increase_the_requirement": (
            None
            if point.correlation is None
            else (point.correlation > 0.0)
        ),
        "does_uncertainty_make_the_target_unidentifiable": (
            assessment.outcome is RequirementOutcome.INCONCLUSIVE
        ),
        "warm_up_reduction_would_help": (
            "A shorter production warm-up raises the number of economic assets "
            "that clear the depth requirement, which moves the CEILING and not "
            "the REQUIREMENT. It therefore helps only where the requirement is "
            "finite and the ceiling is what binds. Where the correlation is at or "
            "above the saturation threshold the requirement is unreachable at any "
            "universe size and no warm-up change reaches it."
        ),
        "warm_up_sensitivity_is_justified": (
            assessment.outcome is RequirementOutcome.UNDERPOWERED
        ),
    }
