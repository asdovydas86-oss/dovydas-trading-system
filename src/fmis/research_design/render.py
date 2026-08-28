"""Rendering a design assessment in plain language. **It computes nothing.**

Every number printed here was decided by `fmis.research_design.verdict` and
`fmis.research_design.resolution`. This module holds no threshold, no formula and
no `Decimal`, and a guard asserts the absence rather than trusting it:
presentation must stay replaceable, so it may own no rule.

The order is the order a sceptical reader needs, and it puts the two sentences
that are most easily conflated next to each other:

    1. what is being asked, and what effect would matter
    2. how much information exists — in every dimension, not one
    3. how the observations fail to be independent
    4. the uncertainty, labelled PROSPECTIVE or POST-HOC without exception
    5. what this design can resolve, and what it cannot
    6. the verdict, and the dimension that binds
    7. what more information would have to look like
    8. assumptions and caveats, in full

**No trading recommendation appears anywhere**, and there is no code path that
could produce one. This report says whether an experiment can answer its
question. It does not know what the answer is.
"""

from __future__ import annotations

from fmis.research_design.models import (
    AssessmentMode,
    DesignVerdict,
    GrowthPath,
    ResolutionCriterion,
)

__all__ = ["render_design_assessment", "wrap_text", "rule"]

_WIDTH = 78

_MODE_BANNER = {
    AssessmentMode.PROSPECTIVE: (
        "PROSPECTIVE DESIGN ASSESSMENT — computed from a planned sample's shape and "
        "an ASSUMED dispersion. No outcome was consulted."
    ),
    AssessmentMode.POST_HOC: (
        "POST-HOC RESOLUTION DIAGNOSTIC — computed from the uncertainty a COMPLETED "
        "measurement produced. This is NOT the power calculation that justified "
        "running the study, and it must never be quoted as one."
    ),
}

_VERDICT_LINE = {
    DesignVerdict.READY: (
        "READY — this design can resolve the effect it declared, with no caveat "
        "attached. It says nothing about whether the effect is there."
    ),
    DesignVerdict.LIMITED: (
        "LIMITED — this design can resolve the effect it declared, but stated "
        "caveats weaken the answer it would give. Read them before the numbers."
    ),
    DesignVerdict.UNDERPOWERED: (
        "UNDERPOWERED — the uncertainty is wider than the declared effect requires. "
        "A negative result from this design would mean 'no effect large enough to "
        "see at this sample size', NOT 'no effect'."
    ),
    DesignVerdict.MISALIGNED_UNIT: (
        "MISALIGNED UNIT — the declared effect and the uncertainty are measured in "
        "different units. Nothing can be concluded until they agree; the inequality "
        "between them is two questions sharing one symbol."
    ),
    DesignVerdict.INSUFFICIENT_INDEPENDENCE: (
        "INSUFFICIENT INDEPENDENCE — the design has the rows but not the independent "
        "information. More observations of the same kind will not fix this."
    ),
    DesignVerdict.NOT_MEASURABLE: (
        "NOT MEASURABLE — the sample cannot support any estimate at all. This is a "
        "statement about the design, not a refutation of anything."
    ),
}


def _line(character: str = "-") -> str:
    return character * _WIDTH


def _number(value, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{digits}f}"


def _count(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}"


def wrap_text(text: str, indent: str = "  ") -> tuple[str, ...]:
    """Fold prose to this report's width. Exposed so a surface prints it the same."""
    return tuple(_wrap(text, indent))


def rule() -> str:
    """The section separator, at this report's width.

    Exposed so that a surface printing extra sections beneath the report gets the
    identical line without building one. `fmis.pipeline.cli` is guarded against
    defining any arithmetic at all — `'-' * 78` is arithmetic to that guard, and
    it is right to be: the width of a report is a presentation decision and the
    CLI is not where presentation decisions live.
    """
    return _line()


def _wrap(text: str, indent: str = "  ") -> list[str]:
    """Fold prose to the report width without importing a formatter."""
    out: list[str] = []
    current = indent
    for word in text.split():
        candidate = f"{current}{word} "
        if len(candidate.rstrip()) > _WIDTH and current.strip():
            out.append(current.rstrip())
            current = f"{indent}{word} "
        else:
            current = candidate
    if current.strip():
        out.append(current.rstrip())
    return out


def render_design_assessment(assessment) -> str:
    """One deterministic report. **No clock, no randomness, no computation.**"""
    out: list[str] = []
    add = out.append
    extend = out.extend

    resolution = assessment.resolution
    target = assessment.target
    dependence = assessment.dependence
    effect = assessment.effect

    add(_line("="))
    add("RESEARCH DESIGN ASSESSMENT")
    add(_line("="))
    add("")
    extend(_wrap(_MODE_BANNER[assessment.mode], indent=""))
    add("")
    add(f"  assessment            {assessment.assessment_id}")
    add(f"  primary sample        {assessment.primary_sample}")
    add("")

    add(_line())
    add("QUESTION")
    add(_line())
    add(f"  id                    {assessment.question.question_id}")
    add(f"  comparison            {assessment.question.comparison.value}")
    add("  primary metric")
    extend(_wrap(assessment.question.primary_metric, indent="    "))
    add("  question")
    extend(_wrap(assessment.question.description, indent="    "))
    add("")

    add(_line())
    add("MINIMUM MEANINGFUL EFFECT")
    add(_line())
    add(f"  magnitude             {effect.magnitude} {effect.unit.code}")
    add(f"  direction             {effect.direction.value}")
    add(f"  uncertainty unit      {assessment.uncertainty_unit.code}")
    add(f"  units agree           {effect.unit.agrees_with(assessment.uncertainty_unit)}")
    add(f"  source                {effect.source}")
    extend(_wrap(effect.rationale))
    add("")

    add(_line())
    add("AVAILABLE INFORMATION")
    add(_line())
    add(
        "  sample                role            obs  clusters  obs/cl  blocks"
        "   units"
    )
    for profile in assessment.profiles:
        frame = next(item for item in assessment.frames if item.name == profile.sample)
        add(
            f"  {profile.sample[:21]:<21} {frame.role.value:<12} "
            f"{profile.observations:>6} {profile.clusters:>9} "
            f"{_number(profile.observations_per_cluster, 1):>7} "
            f"{profile.time_blocks:>7} {profile.experimental_units:>7}"
        )
    add("")
    for profile in assessment.profiles:
        add(f"  {profile.sample}")
        add(f"    largest cluster share  {_number(profile.largest_cluster_share)}")
        add(f"    design effect          {_number(profile.design_effect)}")
        add(f"    effective observations {_number(profile.effective_observations, 1)}")
        extend(_wrap(profile.derivation, indent="      "))
    add("")

    add(_line())
    add("DEPENDENCE AND CLUSTERING")
    add(_line())
    add("  unit of evidence")
    extend(_wrap(dependence.unit_of_evidence, indent="    "))
    add(f"  cluster axis          {dependence.cluster_axis}")
    add(f"  overlapping horizon   {dependence.overlapping_horizon}")
    add(f"  repeated measurements {dependence.repeated_measurements}")
    add(f"  intracluster corr.    {_number(dependence.intracluster_correlation)}")
    add(f"  correlation source    {dependence.correlation_source or 'not declared'}")
    add("")

    add(_line())
    add("CURRENT UNCERTAINTY")
    add(_line())
    add(f"  estimator             {assessment.estimator.kind.value}")
    add(f"  resamples             {_count(assessment.estimator.resamples)}")
    add(f"  confidence            {target.confidence}")
    add(f"  criterion             {target.criterion.value}")
    if target.criterion is ResolutionCriterion.POWERED_DETECTION:
        add(f"  power                 {target.power}")
    label = (
        "observed half-width"
        if assessment.mode is AssessmentMode.POST_HOC
        else "predicted half-width"
    )
    add(f"  {label:<21} {_number(resolution.half_width)} {effect.unit.code}")
    add(f"  half-width required   {_number(resolution.required_half_width)} {effect.unit.code}")
    add("")

    add(_line())
    add("WHAT THIS DESIGN CAN AND CANNOT RESOLVE")
    add(_line())
    add(
        f"  resolves {effect.magnitude} {effect.unit.code}?   "
        f"{resolution.resolves_meaningful_effect}"
    )
    if assessment.mode is AssessmentMode.POST_HOC:
        add(
            f"  smallest resolvable   {_number(resolution.smallest_resolvable_effect)} "
            f"{effect.unit.code}"
        )
        extend(
            _wrap(
                "Any true effect smaller than that magnitude would have produced an "
                "interval containing zero at this sample size, whatever the market "
                "did. A negative result here is a statement about resolution at "
                "least as much as about the effect."
            )
        )
    add("")

    add(_line())
    add("VERDICT")
    add(_line())
    extend(_wrap(_VERDICT_LINE[assessment.verdict], indent="  "))
    add("")
    add(f"  verdict               {assessment.verdict.value.upper()}")
    add(f"  binding dimension     {assessment.limiting_factor.value}")
    add("")
    extend(
        _wrap(
            "This gate answers whether the experiment can credibly answer its own "
            "question. It does not say whether the hypothesis is true, whether a "
            "strategy is good, or whether anything should be traded."
        )
    )
    add("")

    add(_line())
    add("WHAT ADDITIONAL INFORMATION WOULD HELP")
    add(_line())
    add("  growth path                        rho  reachable  clusters  observations")
    for item in assessment.requirements:
        rho = "  —  " if item.path is GrowthPath.INDEPENDENT_OBSERVATIONS else f"{item.intracluster_correlation:>5.2f}"
        add(
            f"  {item.path.value:<32} {rho} {str(item.reachable):>10} "
            f"{_count(item.required_clusters):>9} {_count(item.required_observations):>13}"
        )
    add("")
    for item in assessment.requirements:
        add(f"  {item.path.value} @ rho={item.intracluster_correlation}")
        if item.floor_half_width is not None:
            add(f"    half-width floor     {_number(item.floor_half_width)} {effect.unit.code}")
        extend(_wrap(item.note, indent="    "))
    add("")

    add(_line())
    add("ASSUMPTIONS")
    add(_line())
    for index, item in enumerate(assessment.assumptions, start=1):
        extend(_wrap(f"{index}. {item}"))
    add("")

    add(_line())
    add("CAVEATS")
    add(_line())
    if not assessment.caveats:
        add("  none stated")
    for index, item in enumerate(assessment.caveats, start=1):
        extend(_wrap(f"{index}. {item}"))
    add("")

    return "\n".join(out)
