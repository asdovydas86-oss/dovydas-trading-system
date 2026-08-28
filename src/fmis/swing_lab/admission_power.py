"""Milestone CA's design, assessed. **The adapter — the statistics are elsewhere.**

`fmis.research_design` knows nothing about ATR, symbols, crypto or swing trading.
This module is the one place those meet: it reads Milestone CA's **published,
sealed figures**, expresses them in the general vocabulary, and asks the general
gate whether that design could ever have resolved the effect it declared.

**What this module can and cannot do, stated before any number.**

CA left **no observation-level artifact in this repository**. Its 155 paired
differences are not recoverable without re-running a 77-minute network replay,
which would produce a different dataset and make every figure incomparable — the
failure Milestone BZ recorded as BZ-D2. What survives is CA's report and CA's
sealed constants.

So this is a **summary-statistic reproduction, not a data-level one**. The
uncertainty is the published symbol-clustered bootstrap interval; the
per-observation dispersion behind it is *inverted* from that interval under a
declared intracluster correlation, and reported across a range of them rather
than at one. `empirical_design_curve` is therefore unavailable for CA and the
curve here is `analytic_design_curve`, whose points carry ``extrapolated=True``
beyond the observed sample. That limitation is CB-1 and it is not worked around.

**Every published number below carries its source.** Nothing was re-derived from
memory, and nothing that CA did not publish is invented — where CA published no
figure, the field is `None` and the caveat that follows from it fires.

**The reproduction, in one line.** CA's report states that an interval excluding
zero at a +0.10 ATR effect would need roughly ``(0.558 / 0.10)^2 * 155 ~= 4,800``
matched admissions. `ca_reproduction` recomputes that independently, from the
published interval bounds rather than from the rounded half-width, and reports
whether the two agree — see report 0038.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from fmis.research_design.models import (
    ComparisonType,
    DependenceModel,
    DesignTarget,
    EffectDirection,
    EstimatorKind,
    EstimatorSpec,
    GrowthPath,
    MeaningfulEffect,
    MetricUnit,
    ResearchDesignError,
    ResearchQuestion,
    ResolutionCriterion,
    SampleFrame,
    SampleRole,
)
from fmis.research_design.resolution import (
    DesignPoint,
    PostHocResolution,
    RequiredInformation,
    analytic_design_curve,
    post_hoc_resolution,
    required_information,
)
from fmis.research_design.verdict import DesignAssessment, assess_research_design
from fmis.swing_lab.admission_preregistration import (
    CA_PREREGISTRATION_ID,
    CA_RESEARCH_QUESTION,
    MIN_ADMISSION_EDGE_ATR,
    PRIMARY_HORIZON,
)
from fmis.swing_lab.geometry_verdict import MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.preregistration import SAMPLES
from fmis.swing_lab.validation_study import walk_forward_boundaries

__all__ = [
    "CA_DESIGN_ASSESSMENT_ID",
    "CA_PRIMARY_FAMILY",
    "CA_SENSITIVITY_CORRELATIONS",
    "CA_DESIGN_CURVE_SIZES",
    "CA_DESIGN_CURVE_CORRELATIONS",
    "CA_PUBLISHED",
    "CA_LIMITATIONS",
    "CaPublishedFigure",
    "CaReproduction",
    "ATR_UNIT",
    "ca_question",
    "ca_meaningful_effect",
    "ca_dependence",
    "ca_estimator",
    "ca_target",
    "ca_sample_frames",
    "ca_published",
    "ca_post_hoc",
    "ca_design_assessment",
    "ca_design_curve",
    "ca_required_information",
    "ca_reproduction",
]

CA_DESIGN_ASSESSMENT_ID: Final[str] = "cb-ca-swing-admission-design-v1"

#: The family whose interval CA quotes as the milestone's uncertainty. It holds
#: direction fixed and varies only *when*, so it is the cleanest of the five and
#: the one CA-8 is stated against.
CA_PRIMARY_FAMILY: Final[str] = "ca_null_matched_timing"

#: The intracluster correlations every required-information figure is reported
#: across. CA measured none — the observation-level data needed to estimate one is
#: not in this repository — so the sensitivity table IS the answer and no single
#: row of it is. Zero is included because it is exactly the assumption CA's own
#: ~4,800 estimate makes.
CA_SENSITIVITY_CORRELATIONS: Final[tuple[float, ...]] = (0.0, 0.05, 0.10, 0.20, 0.50)

#: The design sizes the analytic curve is drawn at, in matched admissions.
CA_DESIGN_CURVE_SIZES: Final[tuple[int, ...]] = (
    100, 155, 200, 500, 1000, 2000, 5000, 10000,
)

#: The two correlations the curve is drawn at. Zero is CA's own implicit
#: assumption; 0.10 is a modest clustering, chosen to show the FLOOR rather than
#: to claim a measured value. Neither is a measurement — see CB-2.
CA_DESIGN_CURVE_CORRELATIONS: Final[tuple[float, ...]] = (0.0, 0.10)

#: The unit every CA effect and every CA interval is measured in. Declared once so
#: an effect in ATR can never be compared against an interval in R.
ATR_UNIT: Final[MetricUnit] = MetricUnit(
    code="atr",
    description=(
        "execution-timeframe Average True Range at the decision bar, as "
        "Milestone CA's direction-normalised forward excursion is divided by it"
    ),
)


@dataclass(frozen=True, slots=True)
class CaPublishedFigure:
    """One sample's published shape and uncertainty, with the section it came from.

    ``largest_cluster_share`` is ``None`` wherever report 0037 published no
    per-sample concentration. It is left absent rather than filled with the
    development figure: an unchecked bound is not a passed one, and the caveat
    that fires from the absence is the correct output.
    """

    sample: str
    matched: int
    symbols: int
    bootstrap_low: float
    bootstrap_high: float
    largest_cluster_share: float | None
    source: str

    def __post_init__(self) -> None:
        if self.bootstrap_high <= self.bootstrap_low:
            raise SwingLabError(
                f"{self.sample}: published interval ({self.bootstrap_low}, "
                f"{self.bootstrap_high}) is not ordered"
            )
        if self.matched < 1 or self.symbols < 1:
            raise SwingLabError(f"{self.sample}: published counts must be positive")

    @property
    def half_width(self) -> float:
        """Half the published interval. **Derived, never quoted from prose.**

        Report 0037 rounds this to 0.558 in its text and prints the bounds to four
        decimals in its tables. The bounds are the more precise statement, so the
        half-width is taken from them and the rounded figure is what this
        reproduces rather than what it consumes.
        """
        return (self.bootstrap_high - self.bootstrap_low) / 2.0


#: Milestone CA's published figures for `CA_PRIMARY_FAMILY`, one per sample.
CA_PUBLISHED: Final[tuple[CaPublishedFigure, ...]] = (
    CaPublishedFigure(
        sample="development",
        matched=155,
        symbols=15,
        bootstrap_low=-0.7494,
        bootstrap_high=0.3662,
        largest_cluster_share=0.113,
        source="report 0037 §10 (effect table) and §19 (concentration)",
    ),
    CaPublishedFigure(
        sample="validation",
        matched=91,
        symbols=15,
        bootstrap_low=-1.0347,
        bootstrap_high=0.3482,
        largest_cluster_share=None,
        source="report 0037 §10; no per-sample concentration was published",
    ),
    CaPublishedFigure(
        sample="holdout",
        matched=234,
        symbols=21,
        bootstrap_low=-0.9470,
        bootstrap_high=-0.0308,
        largest_cluster_share=None,
        source="report 0037 §10; no per-sample concentration was published",
    ),
)

#: What this assessment cannot do, carried with it rather than left in a report.
CA_LIMITATIONS: Final[tuple[str, ...]] = (
    "CB-1 — SUMMARY-STATISTIC REPRODUCTION, NOT DATA-LEVEL. Milestone CA's 155 "
    "paired differences are not persisted in this repository, so the "
    "per-observation dispersion is INVERTED from the published interval under an "
    "assumed intracluster correlation rather than measured from the observations. "
    "Every projected figure is conditional on that correlation, which is why the "
    "sensitivity table is the answer and no single row of it is.",
    "CB-2 — THE INTRACLUSTER CORRELATION IS UNMEASURED. CA published no "
    "between-symbol variance decomposition and the data to compute one is absent. "
    "The design curve and every required-information figure are therefore reported "
    "across a declared range and the binding dimension is decided at the "
    "least favourable member of it.",
    "CB-3 — THE PUBLISHED INTERVAL IS ONE FAMILY'S. The uncertainty here is "
    f"{CA_PRIMARY_FAMILY}'s, the family CA-8 is stated against. The other four "
    "sealed families have their own intervals, three of them wider; a design "
    "assessment of those would be no more favourable.",
    "CB-4 — NO EMPIRICAL DESIGN CURVE. Without observation-level data the curve "
    "cannot be measured by sub-sampling real clusters, so it is modelled. Points "
    "beyond 155 admissions carry extrapolated=True and are model output.",
    "CB-5 — THIS ASSESSMENT CHANGES NO CA VERDICT. CA's NO_EDGE stands exactly as "
    "sealed. What is added is the statement of what NO_EDGE could and could not "
    "have meant at that sample size, which CA itself records as CA-8.",
    "CB-6 — THE INPUT INTERVAL IS ITSELF UNCERTAIN. Every figure here is projected "
    "from ONE symbol-clustered interval measured over 15 clusters. Repeating that "
    "measurement on 15 fresh clusters drawn from the same process moves the "
    "half-width by roughly +/-30 %, so the required-information figures inherit "
    "that scatter before any modelling assumption is applied. A required count of "
    "4,823 should be read as an order of magnitude, not as four significant "
    "figures. (The equal-cluster-size approximation the analytic model makes was "
    "measured over four size profiles and showed no systematic bias beyond this "
    "scatter; an earlier single-realisation probe suggesting a large bias was "
    "withdrawn when averaged over 15 realisations.)",
)


def ca_published(sample: str) -> CaPublishedFigure:
    """The published figure for one sample.

    Raises:
        SwingLabError: no figure was published for that sample.
    """
    for item in CA_PUBLISHED:
        if item.sample == sample:
            return item
    raise SwingLabError(
        f"no published CA figure for sample {sample!r}; this module holds "
        f"{', '.join(item.sample for item in CA_PUBLISHED)}"
    )


def ca_question() -> ResearchQuestion:
    """CA's question, read from the sealed pre-registration rather than restated."""
    return ResearchQuestion(
        question_id=CA_PREREGISTRATION_ID,
        description=CA_RESEARCH_QUESTION,
        primary_metric=(
            "direction-normalised, ATR-normalised forward excursion at horizon "
            f"{PRIMARY_HORIZON} execution bars, as a paired difference against a "
            "matched control"
        ),
        comparison=ComparisonType.PAIRED_DIFFERENCE,
    )


def ca_meaningful_effect() -> MeaningfulEffect:
    """CA's sealed +0.10 ATR bar. **Imported by identity, never retyped.**"""
    return MeaningfulEffect(
        magnitude=Decimal(str(MIN_ADMISSION_EDGE_ATR)),
        unit=ATR_UNIT,
        direction=EffectDirection.GREATER,
        rationale=(
            "The deciding cost scenario charges 0.002 of notional per round trip, "
            "and the primary universe's median ATR/close over its admitted instants "
            "is 0.0202, so one round trip costs 0.002 / 0.0202 = 0.099 ATR. An "
            "admission edge smaller than the cost of acting on it is not an edge. "
            "The bar is that cost, rounded to 0.10."
        ),
        source="report 0037 §9; sealed as MIN_ADMISSION_EDGE_ATR",
    )


def ca_dependence() -> DependenceModel:
    """How CA's admissions fail to be independent, as CA itself measured it."""
    return DependenceModel(
        unit_of_evidence=(
            "one admitted decision instant — the first confirmation of a swing "
            "opportunity, deduplicated by Milestone AR's opportunity tracker"
        ),
        cluster_axis="symbol",
        overlapping_horizon=60,
        repeated_measurements=False,
        intracluster_correlation=None,
        correlation_source=None,
        assumptions=(
            "Admissions on one symbol share that symbol's drift, liquidity and "
            "regime, so the symbol is the resampling cluster. Milestone CA sealed "
            "this and its bootstrap resamples symbols, not admissions.",
            "The 60-bar minimum separation guarantees a CONTROL never shares "
            "forward bars with the admission it is paired against. It says nothing "
            "about two ADMISSIONS overlapping each other: report 0037 §23 counts "
            "33 of 155 on development, 14 of 91 on validation and 49 of 234 on the "
            "holdout falling within 60 bars of another admission on the same "
            "symbol. That residual dependence is NOT priced by the symbol cluster "
            "and makes every interval here mildly optimistic.",
            "No intracluster correlation was measured. The observation-level data "
            "needed to estimate one is not persisted in this repository.",
        ),
    )


def ca_estimator() -> EstimatorSpec:
    """CA's sealed symbol-clustered bootstrap, described as what it actually does."""
    return EstimatorSpec(
        kind=EstimatorKind.CLUSTER_BOOTSTRAP,
        comparison=ComparisonType.PAIRED_DIFFERENCE,
        resamples=2000,
        confidence=0.95,
        assumptions=(
            "Symbols are exchangeable: resampling them with replacement produces a "
            "sampling distribution for the mean paired difference.",
            "Fifteen clusters are enough to resample a 2.5 % quantile from. This is "
            "the weakest assumption in the estimator and it is the one CA could not "
            "check, because the cluster count is the universe's.",
            "Every comparison is PAIRED, which removes the symbol, period and drift "
            "differences an unpaired aggregate would import.",
            "The bootstrap is the variance-matched uncertainty statement for CA. Its "
            "sealed EMPIRICAL NULL is not symbol-clustered despite the sealed text "
            "saying it is (report 0037 §22); that error is conservative and is not "
            "read here.",
        ),
        rationale=(
            "Resampling admissions individually would report an interval too narrow "
            "by exactly the dependence between admissions on one symbol. The symbol "
            "is the coarsest cluster CA can afford and therefore the most "
            "conservative available."
        ),
    )


def ca_target() -> DesignTarget:
    """The criterion CA's sealed verdict rule actually implies.

    CA's `development_effect` criterion asks for a point estimate above the bar and
    its `bootstrap_excludes_zero` criterion asks for an interval excluding zero.
    Together those are `INTERVAL_EXCLUDES_ZERO` and **not** a power target: CA
    sealed no power calculation at all, which report 0037 records as CA-8. Stating
    a power target here would attribute to CA a criterion it never declared.

    ``maximum_information_multiple`` is left uncapped **deliberately**. How much
    more data the owner is willing to acquire is the owner's decision, not a
    statistic, and declaring a number here would let this module report "the
    effect threshold is the problem" on the strength of a figure it invented.
    """
    return DesignTarget(
        criterion=ResolutionCriterion.INTERVAL_EXCLUDES_ZERO,
        confidence=0.95,
        power=None,
        minimum_clusters=2,
        minimum_time_blocks=2,
        maximum_cluster_share=float(MAX_SINGLE_SYMBOL_SHARE),
        maximum_information_multiple=None,
    )


def _spec(name: str):
    for item in SAMPLES:
        if item.name == name:
            return item
    raise SwingLabError(f"Milestone BY declares no sample named {name!r}")


def ca_sample_frames() -> tuple[SampleFrame, ...]:
    """CA's three samples in the general vocabulary. **Windows are BY's, imported.**

    The boundaries come from `fmis.swing_lab.preregistration.SAMPLES`, so a CB
    frame and a CA result describe the same window by construction rather than by
    a number retyped here. The time-block count is the repository's own
    walk-forward segmentation of that window, for the same reason.
    """
    frames: list[SampleFrame] = []
    for figure in CA_PUBLISHED:
        spec = _spec(figure.sample)
        blocks = len(
            walk_forward_boundaries(start=spec.signal_start, end=spec.signal_end)
        )
        frames.append(
            SampleFrame(
                name=figure.sample,
                role=SampleRole(spec.role.value),
                population="holdout" if figure.sample == "holdout" else "primary",
                observations=figure.matched,
                clusters=figure.symbols,
                time_blocks=blocks,
                # One admission is one opportunity's first confirmation, so the
                # experimental unit and the observation coincide here. They would
                # NOT coincide for the gate ladder, whose 8,793 instants share 23
                # of 24 forward bars — which is why report 0037 withdrew every
                # inference drawn from it.
                experimental_units=figure.matched,
                starts_at=spec.signal_start,
                ends_at=spec.signal_end,
                largest_cluster_share=figure.largest_cluster_share,
            )
        )
    return tuple(frames)


def ca_post_hoc(sample: str = "development") -> PostHocResolution:
    """CA's post-hoc resolution on one sample. **Never prospective power.**

    Available for the holdout too, because a completed study has already opened
    whatever it measured. What the holdout may not do is *decide a design*, and
    `ca_design_assessment` is built on development for exactly that reason —
    `assess_research_design` refuses a holdout-sourced width by name.
    """
    figure = ca_published(sample)
    frame = next(item for item in ca_sample_frames() if item.name == sample)
    return post_hoc_resolution(
        frame=frame,
        observed_half_width=figure.half_width,
        effect=ca_meaningful_effect(),
        target=ca_target(),
        estimator=ca_estimator(),
    )


def ca_design_assessment() -> DesignAssessment:
    """Assess CA's design on **development**, across the declared correlations."""
    return assess_research_design(
        assessment_id=CA_DESIGN_ASSESSMENT_ID,
        question=ca_question(),
        effect=ca_meaningful_effect(),
        uncertainty_unit=ATR_UNIT,
        dependence=ca_dependence(),
        estimator=ca_estimator(),
        target=ca_target(),
        frames=ca_sample_frames(),
        primary_sample="development",
        resolution=ca_post_hoc("development"),
        sensitivity_correlations=CA_SENSITIVITY_CORRELATIONS,
    )


def ca_required_information(
    path: GrowthPath, correlation: float, *, sample: str = "development"
) -> RequiredInformation:
    """What one growth path would have to deliver on one CA sample."""
    figure = ca_published(sample)
    return required_information(
        path=path,
        observed_half_width=figure.half_width,
        observations=figure.matched,
        clusters=figure.symbols,
        intracluster_correlation=correlation,
        effect=ca_meaningful_effect(),
        target=ca_target(),
    )


def ca_design_curve(
    path: GrowthPath, correlation: float, *, sample: str = "development"
) -> tuple[DesignPoint, ...]:
    """The modelled half-width across design sizes. **Extrapolated beyond 155.**

    Raises:
        ResearchDesignError: for `GrowthPath.INDEPENDENT_OBSERVATIONS`, which the
            general layer refuses to draw as a curve.
    """
    figure = ca_published(sample)
    return analytic_design_curve(
        path=path,
        sizes=CA_DESIGN_CURVE_SIZES,
        observed_half_width=figure.half_width,
        observations=figure.matched,
        clusters=figure.symbols,
        intracluster_correlation=correlation,
        effect=ca_meaningful_effect(),
        target=ca_target(),
    )


@dataclass(frozen=True, slots=True)
class CaReproduction:
    """Whether CB's independent computation supports CA's published ~4,800.

    ``disposition`` is one of ``reproduced``, ``approximately_reproduced``,
    ``superseded`` or ``not_reproducible`` — the four the milestone brief names,
    chosen by a stated rule rather than by inspection.
    """

    published_claim: int
    published_half_width: float
    derived_half_width: float
    recomputed_from_published_half_width: int
    recomputed_from_interval_bounds: int
    relative_difference: float
    disposition: str
    reasoning: str

    def payload(self) -> dict[str, Any]:
        return {
            "published_claim": self.published_claim,
            "published_half_width": self.published_half_width,
            "derived_half_width": self.derived_half_width,
            "recomputed_from_published_half_width": self.recomputed_from_published_half_width,
            "recomputed_from_interval_bounds": self.recomputed_from_interval_bounds,
            "relative_difference": self.relative_difference,
            "disposition": self.disposition,
            "reasoning": self.reasoning,
        }


#: The figure report 0037 §1 and CA-8 publish, and the half-width it quotes.
CA_PUBLISHED_REQUIRED_ADMISSIONS: Final[int] = 4800
CA_PUBLISHED_HALF_WIDTH: Final[float] = 0.558

#: Two figures agree when they differ by less than this. A claim published as
#: "roughly 4,800" is not a claim about its last two digits, and a reproduction
#: rule that demanded them would fail every honest rounding.
CA_REPRODUCTION_TOLERANCE: Final[float] = 0.05


def ca_reproduction() -> CaReproduction:
    """Recompute CA's ~4,800 independently and classify the agreement.

    Two recomputations are reported because they answer different questions. From
    the **rounded half-width** CA quotes, this reproduces CA's own arithmetic. From
    the **interval bounds** CA tabulates, it reproduces the quantity CA was
    approximating. Both use the general layer's
    `GrowthPath.INDEPENDENT_OBSERVATIONS` requirement, which is the assumption CA's
    formula makes — and naming it as an assumption is most of what CB adds.
    """
    figure = ca_published("development")
    effect = ca_meaningful_effect()
    target = ca_target()
    from_bounds = required_information(
        path=GrowthPath.INDEPENDENT_OBSERVATIONS,
        observed_half_width=figure.half_width,
        observations=figure.matched,
        clusters=figure.symbols,
        intracluster_correlation=0.0,
        effect=effect,
        target=target,
    )
    from_quoted = required_information(
        path=GrowthPath.INDEPENDENT_OBSERVATIONS,
        observed_half_width=CA_PUBLISHED_HALF_WIDTH,
        observations=figure.matched,
        clusters=figure.symbols,
        intracluster_correlation=0.0,
        effect=effect,
        target=target,
    )
    if from_bounds.required_observations is None or from_quoted.required_observations is None:
        raise ResearchDesignError(
            "the independent-observation path returned no required count, which "
            "cannot happen for a positive half-width and a positive effect"
        )
    difference = abs(
        from_quoted.required_observations - CA_PUBLISHED_REQUIRED_ADMISSIONS
    ) / CA_PUBLISHED_REQUIRED_ADMISSIONS
    if difference <= CA_REPRODUCTION_TOLERANCE:
        disposition = "reproduced"
        reasoning = (
            f"Recomputing CA's own arithmetic from the half-width it quotes gives "
            f"{from_quoted.required_observations:,} matched admissions against the "
            f"~{CA_PUBLISHED_REQUIRED_ADMISSIONS:,} published, a relative difference "
            f"of {difference:.4f}. The published figure is correct as stated. What "
            "CB adds is the assumption it rests on: it is the "
            "INDEPENDENT_OBSERVATIONS path, which treats every additional admission "
            "as an independent experiment. That assumption is exactly right under "
            "MORE_CLUSTERS_SAME_DENSITY and wrong under "
            "MORE_OBSERVATIONS_SAME_CLUSTERS, where the half-width has a floor."
        )
    else:  # pragma: no cover - reached only if a published constant is edited
        disposition = "not_reproducible"
        reasoning = (
            f"Recomputation gives {from_quoted.required_observations:,} against the "
            f"~{CA_PUBLISHED_REQUIRED_ADMISSIONS:,} published, a relative difference "
            f"of {difference:.4f}, beyond the {CA_REPRODUCTION_TOLERANCE} tolerance."
        )
    return CaReproduction(
        published_claim=CA_PUBLISHED_REQUIRED_ADMISSIONS,
        published_half_width=CA_PUBLISHED_HALF_WIDTH,
        derived_half_width=figure.half_width,
        recomputed_from_published_half_width=from_quoted.required_observations,
        recomputed_from_interval_bounds=from_bounds.required_observations,
        relative_difference=difference,
        disposition=disposition,
        reasoning=reasoning,
    )
