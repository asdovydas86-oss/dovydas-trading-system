"""Presentation. **Owns no rule and decides nothing.**

Every number here was computed elsewhere. This module chooses column widths and
sentence order; it does not choose a threshold, does not compare a value against
one, and declares no float constant — a guard asserts all three, because a
renderer that owned a rule would make the report unreplaceable.

Two presentational commitments carry scientific weight and are therefore not
merely style:

* **A projected row is never printed like a measured one.** Every growth row
  carries an explicit ``obs``/``proj`` marker in its own column, so a reader
  scanning the table cannot mistake a model output for a measurement.
* **The verdict is printed with its binding constraint and its limitations**, and
  never on its own line as a bare word. A feasibility verdict detached from what
  bound it is the sentence most likely to be quoted out of context.
"""

from __future__ import annotations

from fmis.universe.models import FeasibilityVerdict

__all__ = ["render_universe_study", "render_funnel", "render_growth"]

_RULE = "=" * 78
_THIN = "-" * 78


def _fmt(value, spec: str = ".4f") -> str:
    """A number, or a dash when it was not measured. **Never a zero.**"""
    if value is None:
        return "—"
    return format(value, spec)


def render_funnel(study) -> str:
    """The staged funnel, with every exclusion reason and its count."""
    lines = [
        "ELIGIBILITY FUNNEL",
        _THIN,
        f"  discovered instruments          {study.discovered_instruments:>8,}",
        f"  economic assets after identity  {study.economic_assets:>8,}",
        f"  ELIGIBLE economic assets        {study.eligible_assets:>8,}",
        "",
        "  removed, by stage:",
    ]
    for stage, count in sorted(study.funnel.by_stage.items()):
        lines.append(f"    {stage:<28} {count:>8,}")
    lines.append(f"    {'TOTAL REMOVED':<28} {study.funnel.removed:>8,}")
    lines.append(
        f"    funnel reconciles            {'yes' if study.funnel.reconciles else 'NO':>8}"
    )
    lines.append("")
    lines.append("  removed, by reason:")
    counts: dict[str, int] = {}
    for item in study.exclusions:
        counts[item.reason.value] = counts.get(item.reason.value, 0) + 1
    for reason in sorted(counts, key=lambda key: (-counts[key], key)):
        lines.append(f"    {reason:<38} {counts[reason]:>8,}")
    return "\n".join(lines)


def render_growth(study) -> str:
    """The information-growth curve. **Observed and projected are marked.**"""
    lines = [
        "INFORMATION GROWTH CURVE",
        _THIN,
        "  A row marked 'proj' describes a universe this repository has NOT shown",
        "  exists. It says what would follow if one did.",
        "",
        f"  {'scenario':<12} {'assets':>7} {'kind':>5} {'K_eff':>9} {'admiss':>9} "
        f"{'half-width':>11} {'needed':>8} {'resolves':>9}",
    ]
    for row in study.growth:
        lines.append(
            f"  {row.dependence_scenario:<12} {row.assets:>7,} "
            f"{'obs' if row.observed else 'proj':>5} "
            f"{row.effective_clusters:>9.2f} {row.projected_admissions:>9,} "
            f"{row.half_width:>11.4f} {row.required_half_width:>8.4f} "
            f"{('YES' if row.resolves else 'no'):>9}"
        )
    return "\n".join(lines)


def _render_dependence(study) -> str:
    dependence = study.dependence
    return "\n".join(
        [
            "DEPENDENCE BETWEEN ECONOMIC ASSETS",
            _THIN,
            f"  assets measured                  {dependence.assets:>10,}",
            f"  pairs measured / skipped         {dependence.pairs_measured:>10,}"
            f" / {dependence.pairs_skipped:,}",
            f"  raw mean correlation             "
            f"{_fmt(dependence.raw_mean_correlation):>10}",
            f"  raw median correlation           "
            f"{_fmt(dependence.raw_median_correlation):>10}",
            f"  market factor share of variance  "
            f"{_fmt(dependence.market_factor_share):>10}",
            f"  residual mean correlation        "
            f"{_fmt(dependence.residual_mean_correlation):>10}",
            f"  demeaning artefact -1/(K-1)      "
            f"{_fmt(dependence.demeaning_artefact):>10}",
            f"  residual EXCESS over artefact    "
            f"{_fmt(dependence.residual_excess_over_artefact):>10}",
            "",
            "  The residual mean must be read against the demeaning artefact, not",
            "  against zero: subtracting a cross-sectional mean from K series",
            "  induces -1/(K-1) even among perfectly independent ones.",
            "",
            f"  measured co-moving groups (>= threshold): {len(study.correlated_groups)}",
        ]
    )


def _render_verdict(study) -> str:
    assessment = study.assessment
    lines = [
        "FEASIBILITY VERDICT",
        _RULE,
        f"  {assessment.verdict.value.upper()}",
        f"  binding constraint: {assessment.binding_constraint}",
        "",
        f"  eligible economic assets            {assessment.eligible_assets:>8,}",
        f"  required, independent scenario      "
        f"{_fmt(assessment.required_assets_independent, ',') :>8}",
        f"  required, residual scenario         "
        f"{_fmt(assessment.required_assets_residual, ',') :>8}",
        f"  required, raw scenario              "
        f"{_fmt(assessment.required_assets_raw, ',') :>8}",
        "",
        "  " + assessment.reasoning,
        "",
        f"  approves trading      {assessment.is_approved_for_trading}",
        f"  earns a forward test  {assessment.earns_forward_test}",
        "",
        "  NO VERDICT IN THIS STUDY IS PERMISSION TO TRADE, TO PAPER TRADE, TO",
        "  SHADOW TRADE OR TO PROMOTE ANYTHING. It says nothing about whether an",
        "  admission edge exists; Milestone CA's NO_EDGE stands untouched.",
    ]
    return "\n".join(lines)


def render_universe_study(study) -> str:
    """The whole study, as one report."""
    if not isinstance(study.assessment.verdict, FeasibilityVerdict):
        raise TypeError("study.assessment.verdict must be a FeasibilityVerdict")
    survivorship = study.survivorship
    header = "\n".join(
        [
            _RULE,
            "MILESTONE CC — UNIVERSE FEASIBILITY & INFORMATION EXPANSION",
            _RULE,
            f"  pre-registration digest  {study.preregistration_digest}",
            f"  provider                 {study.provider}",
            f"  discovered at            {study.discovered_at.isoformat()}",
            f"  measurement window       {study.window_start.date()} -> "
            f"{study.window_end.date()}",
            f"  derived production warm-up  {study.warmup_days:,} days",
            f"  mean usable years / asset   {study.mean_usable_years:.3f}",
        ]
    )
    density = "\n".join(
        [
            "ADMISSION DENSITY",
            _THIN,
            f"  pooled admissions per asset-year  "
            f"{study.density.pooled_per_asset_year:>8.4f}",
            f"  median per asset-year             "
            f"{study.density.median_per_asset_year:>8.4f}",
            f"  min / max per asset-year          "
            f"{study.density.minimum_per_asset_year:>8.4f} / "
            f"{study.density.maximum_per_asset_year:.4f}",
            f"  largest single share of admissions "
            f"{study.density.largest_share:>7.4f}",
            "",
            "  NOTE: that share is across the density SOURCES listed below, which",
            "  for the published figures are three whole samples — NOT across",
            "  individual assets. Per-asset admission concentration is NOT MEASURED",
            "  (limitation CC-2): Milestone CA published per-sample counts only.",
            "",
            "  sources:",
            *[f"    {item}" for item in study.density.sources],
        ]
    )
    requirement = "\n".join(
        [
            "MILESTONE CB'S REQUIREMENT, RECOMPUTED",
            _THIN,
            f"  required matched admissions  {study.cb_required_observations:>8,}",
            f"  required clusters            {study.cb_required_clusters:>8,}",
        ]
    )
    survivor = "\n".join(
        [
            "SURVIVORSHIP",
            _THIN,
            f"  classification        {survivorship.classification.value}",
            f"  halted instruments    {survivorship.halted_instruments:,} of "
            f"{survivorship.total_instruments:,} "
            f"({survivorship.halted_share:.3f})",
            f"  halted and eligible   {survivorship.eligible_halted:,}",
            "",
            "  " + survivorship.evidence,
        ]
    )
    effects = ["EFFECT-SIZE GRID", _THIN,
               "  The +0.10 ATR target is Milestone CA's and is NOT reopened. The larger",
               "  members answer a separate question: what could this universe test?",
               "",
               f"  {'effect':>7} {'scenario':<12} {'required assets':>16} "
               f"{'reachable':>10} {'primary':>8}"]
    for item in study.effect_requirements:
        effects.append(
            f"  {item.effect:>7} {item.dependence_scenario:<12} "
            f"{_fmt(item.required_assets, ',') :>16} "
            f"{('yes' if item.reachable else 'NO'):>10} "
            f"{('YES' if item.is_primary else '-'):>8}"
        )
    limitations = "\n".join(
        ["LIMITATIONS — SEALED WITH THE PRE-REGISTRATION", _THIN]
        + [f"  * {item}" for item in study.assessment.limitations]
        + [
            "",
            "LIMITATIONS — ESTABLISHED BY REVIEW, AFTER SEALING",
            _THIN,
            "  These are carried separately from the sealed set on purpose: a "
            "pre-registration",
            "  retro-fitted with what was learned later would not be one.",
            "",
        ]
        + [f"  * {item}" for item in study.post_review_limitations]
    )
    return "\n\n".join(
        [
            header,
            render_funnel(study),
            _render_dependence(study),
            density,
            requirement,
            render_growth(study),
            "\n".join(effects),
            survivor,
            _render_verdict(study),
            limitations,
        ]
    )
