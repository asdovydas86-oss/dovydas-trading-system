"""What a larger universe buys. **Assets in, resolvable effect out.**

This is Milestone CC's principal output and the place its two measurements meet.
`fmis.universe.eligibility` says how many economic assets exist and how many
usable years each contributes; `fmis.universe.dependence` says how much of a
larger universe is genuinely new; and `fmis.research_design` — Milestone CB's
machinery, **reused, not reimplemented** — says what half-width a design of that
shape produces and whether +0.10 ATR falls inside it.

**The chain, stated once.**

    N assets
      → n = N * years_per_asset * density      projected admissions
      → m = n / N                              admissions per REAL cluster
      → h_within = z * sigma * sqrt((rho + (1 - rho)/m) / N)      CB's formula
      → h = h_within * sqrt(1 + (N - 1) * r)                      CC's one factor
      → resolves when h < the required half-width

The split matters. Milestone CB's formula prices dependence **inside** a symbol
and knows nothing about dependence **between** symbols — correctly, because that
was not CB's question. CC's contribution is the second line: for ``N``
equicorrelated cluster means the variance of their average carries an extra
``1 + (N - 1) r``, so the half-width carries its square root. Equivalently, it is
CB's formula evaluated at ``K_eff = N / (1 + (N - 1) r)`` clusters, which is why
`effective_clusters` is the diagnostic reported beside it. Applying the factor to
CB's *output* keeps it exact; rounding a fractional effective count into CB's
integer *input* would not.

**This is the term that produces a floor**, and it is the milestone's central
mechanism. Projected admissions grow linearly in ``N``, so the two ``N``'s cancel
and the half-width approaches

    h → z * sigma * sqrt(r / (years_per_asset * density))

which no number of additional assets goes below. At ``r = 0`` there is no floor
and the requirement is CB's own ~4,823 admissions; at any ``r > 0`` there may be
no reachable universe size at all, and `requirement_for_effect` reports that as a
finding rather than as a large number.

``sigma`` is inverted from Milestone CA's published symbol-clustered interval by
CB's `observation_dispersion_from_half_width`, which is CB limitation CB-1 and is
inherited here rather than worked around: no observation-level CA data exists in
this repository to measure it from.

**``rho`` is held at zero — and the requirement turns out to be insensitive to
it, which is a stronger statement than the one this docstring used to make.**

``rho`` is the *within*-cluster correlation, which CB left unmeasured and CC
cannot measure either. An earlier draft claimed zero was "the most favourable
value" and that every requirement here was therefore a **lower bound**. An
independent review agreed with that claim; re-deriving it showed **both halves are
wrong**, and the truth is more useful.

``sigma`` is not a free constant: it is *inverted* from CA's interval under the
**same** ``rho``, so raising ``rho`` lowers ``sigma`` and the two effects very
nearly cancel. What survives is the ratio of the two structural factors, and CA's
observations-per-cluster (155/15 = 10.333) is almost exactly CC's projected
admissions-per-asset (years x density = 10.311) — so they cancel to within a
fraction of a percent. Measured across ``rho`` in [0, 0.8], the requirement for
+0.10 ATR moves from **468 assets to 467**: one asset, and in the direction
*opposite* to the discarded claim, since ``rho = 0`` demands very slightly MORE
data rather than less.

So the honest statement is not "this is a lower bound" but **"this requirement is
robust to the one dependence parameter nobody can measure"**, which is why the
`INFEASIBLE` verdict does not rest on it. `test_the_requirement_is_robust_to_the_
within_cluster_correlation` pins the figure.

**Observed and projected are structurally distinguishable.** `GrowthRow.observed`
is `True` only where the size is one the measured universe actually reaches.
Everything beyond is a model, it is marked as one in the dataclass, in the
artifact payload and in the rendered table, and no reader has to infer it from a
footnote.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Any, Final

from fmis.research_design.models import (
    DesignTarget,
    EffectDirection,
    GrowthPath,
    MeaningfulEffect,
)
from fmis.research_design.resolution import (
    RequiredInformation,
    half_width_for_design,
    observation_dispersion_from_half_width,
    required_half_width,
    required_information,
)
from fmis.swing_lab.admission_power import ATR_UNIT, ca_published, ca_target
from fmis.universe.dependence import DependenceSummary, effective_clusters
from fmis.universe.models import UniverseError, require_count, require_text

__all__ = [
    "WITHIN_CLUSTER_CORRELATION",
    "CA_CONFIDENCE",
    "DESIGN_SAMPLE",
    "GrowthRow",
    "EffectRequirement",
    "ca_observation_dispersion",
    "effect_for",
    "growth_row",
    "growth_curve",
    "requirement_for_effect",
    "cb_required_information",
]

#: The **within**-cluster correlation every projection here assumes.
#:
#: Zero — Milestone CA's own implicit assumption. CB limitation CB-2 records that
#: the true value is unmeasured, and CC does not close that gap.
#:
#: **It barely matters, and that is a measured statement.** ``sigma`` is inverted
#: from CA's interval under this same value, so it moves in the opposite direction
#: and the two nearly cancel; across ``rho`` in [0, 0.8] the +0.10 ATR requirement
#: moves by exactly one asset (468 -> 467). See the module docstring for why, and
#: `test_the_requirement_is_robust_to_the_within_cluster_correlation` for the pin.
WITHIN_CLUSTER_CORRELATION: Final[float] = 0.0

#: The confidence Milestone CA's sealed bootstrap was taken at, read from CA's own
#: target rather than retyped.
CA_CONFIDENCE: Final[float] = 0.95


#: The only sample whose realised interval may set a design parameter here.
#:
#: Milestone BY's `SampleRole.may_inform_design` is `False` for the holdout, and
#: Milestone CB's `assess_research_design` refuses a holdout-sourced width by name.
#: This module accepted any sample until an independent review pointed out that
#: nothing stopped a caller inverting sigma from the HOLDOUT's realised interval —
#: no live call site did, but a latent path to spending the holdout is a path to
#: spending the holdout. The refusal below closes it.
DESIGN_SAMPLE: Final[str] = "development"


def ca_observation_dispersion(*, sample: str = DESIGN_SAMPLE) -> float:
    """The per-observation dispersion Milestone CA's published interval implies.

    Inverted from the interval bounds report 0037 tabulates rather than from the
    rounded half-width its prose quotes — the bounds are the more precise
    statement. Inherits CB-1: this is a summary-statistic reproduction and the
    observation-level data to measure sigma directly does not exist here.

    Raises:
        UniverseError: ``sample`` is not `DESIGN_SAMPLE`. A design parameter
            inverted from a validation or holdout interval would be a design
            justified by the sample it is meant to be tested on.
    """
    if sample != DESIGN_SAMPLE:
        raise UniverseError(
            f"sample {sample!r} may not set a design parameter; only "
            f"{DESIGN_SAMPLE!r} may. Inverting a per-observation dispersion from a "
            "validation or holdout interval would spend the very sample held back "
            "to test the design — Milestone BY seals that role and Milestone CB "
            "refuses a holdout-sourced width for the same reason"
        )
    figure = ca_published(sample)
    return observation_dispersion_from_half_width(
        half_width=figure.half_width,
        clusters=figure.symbols,
        observations=figure.matched,
        intracluster_correlation=WITHIN_CLUSTER_CORRELATION,
        confidence=CA_CONFIDENCE,
    )


def effect_for(magnitude: Decimal) -> MeaningfulEffect:
    """One member of the sealed effect grid, in CA's unit and direction.

    The rationale distinguishes the primary target from the rest **in the object
    itself**, so a table printed from these cannot lose the distinction that
    +0.10 ATR is CA's question and the larger members are a different one.
    """
    if not isinstance(magnitude, Decimal):
        raise UniverseError("effect magnitude must be a Decimal")
    primary = magnitude == Decimal("0.10")
    return MeaningfulEffect(
        magnitude=magnitude,
        unit=ATR_UNIT,
        direction=EffectDirection.GREATER,
        rationale=(
            "Milestone CA's sealed bar: one round trip of the deciding cost "
            "scenario at the universe's median ATR/close. An admission edge "
            "smaller than the cost of acting on it is not an edge."
            if primary
            else
            f"NOT Milestone CA's question. {magnitude} ATR is a member of the "
            "pre-declared effect grid, reported to answer what a smaller universe "
            "could honestly test. Reading it as the answer to CA's question would "
            "be restating the hypothesis after seeing the result."
        ),
        source=(
            "report 0037 §9; sealed as MIN_ADMISSION_EDGE_ATR"
            if primary
            else "Milestone CC pre-registration, EFFECT_SIZE_GRID"
        ),
    )


@dataclass(frozen=True, slots=True)
class GrowthRow:
    """One universe size, and what a design of that size could resolve.

    ``observed`` separates measurement from model and is the field a reader must
    look at first. A row with ``observed=False`` describes a universe this
    repository has **not** shown exists; it says what would follow if one did.
    """

    assets: int
    observed: bool
    dependence_scenario: str
    between_asset_correlation: float
    effective_clusters: float
    years_per_asset: float
    admissions_per_asset_year: float
    projected_admissions: int
    admissions_per_effective_cluster: float
    half_width: float
    required_half_width: float
    resolves: bool

    def __post_init__(self) -> None:
        require_count(self.assets, "assets", minimum=1)
        require_text(self.dependence_scenario, "dependence_scenario")
        if not isinstance(self.observed, bool):
            raise UniverseError("observed must be a bool")
        if self.effective_clusters <= 0.0:
            raise UniverseError("effective_clusters must be positive")
        if self.effective_clusters > self.assets + 1e-9:
            raise UniverseError(
                f"{self.effective_clusters} effective clusters from {self.assets} "
                "assets; co-movement cannot create independent clusters"
            )
        if self.resolves != (self.half_width < self.required_half_width):
            raise UniverseError(
                "the resolves flag disagrees with its own inequality; a row whose "
                "verdict is not its arithmetic is a row that was edited"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "assets": self.assets,
            "observed": self.observed,
            "dependence_scenario": self.dependence_scenario,
            "between_asset_correlation": self.between_asset_correlation,
            "effective_clusters": self.effective_clusters,
            "years_per_asset": self.years_per_asset,
            "admissions_per_asset_year": self.admissions_per_asset_year,
            "projected_admissions": self.projected_admissions,
            "admissions_per_effective_cluster": self.admissions_per_effective_cluster,
            "half_width": self.half_width,
            "required_half_width": self.required_half_width,
            "resolves": self.resolves,
        }


def growth_row(
    *,
    assets: int,
    observed: bool,
    scenario: str,
    correlation: float,
    years_per_asset: float,
    admissions_per_asset_year: float,
    effect: MeaningfulEffect,
    target: DesignTarget | None = None,
    observation_sd: float | None = None,
) -> GrowthRow:
    """One row of the growth curve. **Every step is CB's arithmetic.**

    Raises:
        UniverseError: a rate is non-positive, or the projected admissions fall
            below the effective cluster count — a design cannot hold fewer
            observations than clusters and reporting one would be a malformed
            frame rather than a small one.
    """
    require_count(assets, "assets", minimum=1)
    if years_per_asset <= 0.0 or admissions_per_asset_year <= 0.0:
        raise UniverseError(
            "years per asset and admissions per asset-year must both be positive; "
            "a universe supplying zero of either supplies no observations and its "
            "resolvable effect is undefined rather than infinite"
        )
    chosen_target = ca_target() if target is None else target
    sigma = ca_observation_dispersion() if observation_sd is None else observation_sd

    k_eff = effective_clusters(assets, correlation)
    admissions = int(assets * years_per_asset * admissions_per_asset_year)
    if admissions < 1:
        raise UniverseError(
            f"{assets} asset(s) at {years_per_asset:.3f} years and "
            f"{admissions_per_asset_year:.3f} admissions per asset-year project "
            "fewer than one admission; there is no design to assess"
        )
    per_cluster = admissions / assets
    if per_cluster < 1.0:
        raise UniverseError(
            f"{admissions} projected admission(s) across {assets} asset(s) leaves "
            "less than one per cluster. The design effect cannot be evaluated on a "
            "frame that thin"
        )
    # Milestone CB's own formula, over the REAL clusters and their REAL occupancy.
    # It prices the dependence *inside* a symbol and knows nothing about
    # dependence *between* symbols, which is correct: that is not CB's question.
    within = half_width_for_design(
        observation_sd=sigma,
        clusters=assets,
        observations_per_cluster=per_cluster,
        intracluster_correlation=WITHIN_CLUSTER_CORRELATION,
        confidence=chosen_target.confidence,
    )
    # Milestone CC's one addition, named rather than folded into a count.
    #
    # For K equicorrelated cluster means with between-cluster correlation r, the
    # variance of their average carries an extra factor of (1 + (K-1) r):
    #
    #     Var(mean) = (v / K) * (1 + (K - 1) r),   v = Var of one cluster mean
    #
    # so the half-width is CB's, multiplied by sqrt(1 + (K - 1) r). Equivalently
    # it is CB's formula evaluated at K_eff = K / (1 + (K - 1) r) clusters — which
    # is why `effective_clusters` is the right diagnostic to report alongside it.
    #
    # **This is the term that produces a floor.** Projected admissions grow
    # linearly in K, so the two K's cancel as K grows and the half-width
    # approaches z * sigma * sqrt(r / (years * density)) — a bound no number of
    # additional assets goes below. Applying the inflation to CB's output rather
    # than rounding a fractional cluster count into CB's input keeps that exact
    # rather than approximate.
    width = within * sqrt(1.0 + (assets - 1) * correlation)
    needed = required_half_width(effect, chosen_target)
    return GrowthRow(
        assets=assets,
        observed=observed,
        dependence_scenario=scenario,
        between_asset_correlation=correlation,
        effective_clusters=k_eff,
        years_per_asset=years_per_asset,
        admissions_per_asset_year=admissions_per_asset_year,
        projected_admissions=admissions,
        admissions_per_effective_cluster=admissions / k_eff,
        half_width=width,
        required_half_width=needed,
        resolves=width < needed,
    )


def growth_curve(
    *,
    sizes: tuple[int, ...],
    scenarios: tuple[str, ...],
    dependence: DependenceSummary,
    eligible_assets: int,
    years_per_asset: float,
    admissions_per_asset_year: float,
    effect: MeaningfulEffect,
    target: DesignTarget | None = None,
) -> tuple[GrowthRow, ...]:
    """The full curve: every sealed size at every sealed dependence scenario.

    A size at or below ``eligible_assets`` is marked ``observed=True`` — the
    universe was measured to hold that many. Everything above is a projection and
    says so in the row itself.
    """
    rows: list[GrowthRow] = []
    for scenario in scenarios:
        correlation = dependence.correlation_for(scenario)
        for size in sizes:
            rows.append(
                growth_row(
                    assets=size,
                    observed=size <= eligible_assets,
                    scenario=scenario,
                    correlation=correlation,
                    years_per_asset=years_per_asset,
                    admissions_per_asset_year=admissions_per_asset_year,
                    effect=effect,
                    target=target,
                )
            )
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class EffectRequirement:
    """What one effect size would need, and whether the universe supplies it."""

    effect: str
    is_primary: bool
    dependence_scenario: str
    required_half_width: float
    required_assets: int | None
    required_admissions: int | None
    reachable: bool
    note: str

    def payload(self) -> dict[str, Any]:
        return {
            "effect": self.effect,
            "is_primary": self.is_primary,
            "dependence_scenario": self.dependence_scenario,
            "required_half_width": self.required_half_width,
            "required_assets": self.required_assets,
            "required_admissions": self.required_admissions,
            "reachable": self.reachable,
            "note": self.note,
        }


#: The largest universe the search below will consider before declaring an effect
#: unreachable. One hundred thousand economic assets is some three hundred times
#: every spot instrument Binance has ever listed; a requirement beyond it is
#: unreachable in every sense that matters, and the bound keeps the search finite
#: for the saturating case where no size ever suffices.
_SEARCH_CEILING: Final[int] = 100_000


def requirement_for_effect(
    *,
    magnitude: Decimal,
    scenario: str,
    dependence: DependenceSummary,
    years_per_asset: float,
    admissions_per_asset_year: float,
    target: DesignTarget | None = None,
) -> EffectRequirement:
    """The smallest universe that resolves ``magnitude``, or that none does.

    Searched by doubling and then bisecting on asset count, because the resolvable
    half-width is monotone in it. ``reachable=False`` is a **finding**, not a
    timeout: when the between-asset correlation is positive the effective cluster
    count saturates at ``1/r``, so the half-width approaches a floor and no
    universe size clears the bar. That is the case CC exists to be able to state.
    """
    effect = effect_for(magnitude)
    chosen_target = ca_target() if target is None else target
    correlation = dependence.correlation_for(scenario)
    needed = required_half_width(effect, chosen_target)

    def resolves(size: int) -> bool:
        try:
            return growth_row(
                assets=size, observed=False, scenario=scenario,
                correlation=correlation, years_per_asset=years_per_asset,
                admissions_per_asset_year=admissions_per_asset_year,
                effect=effect, target=chosen_target,
            ).resolves
        except UniverseError:
            # A universe too small to hold one admission per effective cluster
            # cannot resolve anything; that is a `False`, not an error.
            return False

    if not resolves(_SEARCH_CEILING):
        return EffectRequirement(
            effect=str(magnitude), is_primary=magnitude == Decimal("0.10"),
            dependence_scenario=scenario, required_half_width=needed,
            required_assets=None, required_admissions=None, reachable=False,
            note=(
                f"No universe up to {_SEARCH_CEILING:,} economic assets resolves "
                f"{magnitude} ATR under the {scenario!r} scenario at a "
                f"between-asset correlation of {correlation:.4f}. The effective "
                f"cluster count saturates at {0.0 if correlation <= 0 else 1.0 / correlation:.2f}, "
                "so the interval half-width approaches a floor that additional "
                "assets do not lower. This is a statement that no quantity of this "
                "kind of data suffices, not that a lot of it is needed"
            ),
        )

    low, high = 1, _SEARCH_CEILING
    while low < high:
        middle = (low + high) // 2
        if resolves(middle):
            high = middle
        else:
            low = middle + 1
    row = growth_row(
        assets=low, observed=False, scenario=scenario, correlation=correlation,
        years_per_asset=years_per_asset,
        admissions_per_asset_year=admissions_per_asset_year,
        effect=effect, target=chosen_target,
    )
    return EffectRequirement(
        effect=str(magnitude), is_primary=magnitude == Decimal("0.10"),
        dependence_scenario=scenario, required_half_width=needed,
        required_assets=low, required_admissions=row.projected_admissions,
        reachable=True,
        note=(
            f"{low:,} economic assets contributing {years_per_asset:.2f} usable "
            f"years each at {admissions_per_asset_year:.2f} admissions per "
            f"asset-year project {row.projected_admissions:,} admissions across "
            f"{row.effective_clusters:.2f} effective clusters, giving a half-width "
            f"of {row.half_width:.4f} ATR against the {needed:.4f} required. The "
            "within-cluster correlation is held at zero; the requirement is "
            "insensitive to it (468 vs 467 assets across rho in [0, 0.8]) because "
            "sigma is inverted under the same value and the two nearly cancel"
        ),
    )


def cb_required_information(*, correlation: float = 0.0) -> RequiredInformation:
    """Milestone CB's own requirement, recomputed. **The number CC starts from.**

    Reproduces CB's `MORE_CLUSTERS_SAME_DENSITY` figure from CA's published
    interval, so the ~4,823 admissions CC is testing the feasibility of are
    derived here rather than quoted from a report.
    """
    figure = ca_published("development")
    return required_information(
        path=GrowthPath.MORE_CLUSTERS_SAME_DENSITY,
        observed_half_width=figure.half_width,
        observations=figure.matched,
        clusters=figure.symbols,
        intracluster_correlation=correlation,
        effect=effect_for(Decimal("0.10")),
        target=ca_target(),
    )

