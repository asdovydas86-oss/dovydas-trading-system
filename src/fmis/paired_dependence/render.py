"""Presentation. **Owns no rule and decides nothing.**

Every number here was computed elsewhere. This module chooses column widths and
sentence order; it does not choose a threshold, does not compare a value against
one, and declares no float constant — a guard asserts all three, because a
renderer that owned a rule would make the report unreplaceable.

Three presentational commitments carry scientific weight and are not merely
style:

* **The five counts are printed together, always.** Rows, admissions, economic
  assets, informative blocks and effective clusters appear on adjacent lines under
  one heading, because the single most likely misreading of this milestone is to
  quote the row count as the sample size.
* **``rho_w`` and ``r_b`` are never printed in the same column.** They are
  different parameters with different units of grouping, and a table that stacked
  them would invite exactly the substitution the interpretation rules forbid.
* **The sections are named for what they are.** OBSERVATION, MEASUREMENT,
  UNCERTAINTY, DESIGN IMPLICATION and LIMITATIONS are separate blocks, so a
  reader can see where measurement stops and inference starts.
"""

from __future__ import annotations

__all__ = [
    "render_dependence_study",
    "render_observation",
    "render_measurement",
    "render_uncertainty",
    "render_design_implication",
    "render_limitations",
]

_RULE = "=" * 78
_THIN = "-" * 78


def _fmt(value, spec: str = ".4f") -> str:
    """A number, or a dash when it was not measured. **Never a zero.**"""
    if value is None:
        return "—"
    return format(value, spec)


def _count(value) -> str:
    return "—" if value is None else format(value, ",")


def render_observation(study) -> str:
    """What the panel is, before anything is estimated from it."""
    headline = study.headline
    coverage = headline.coverage
    concentration = headline.concentration
    lines = [
        "OBSERVATION",
        _THIN,
        f"  primary family                  {headline.family_id}",
        f"  primary sample                  {headline.sample}",
        "",
        "  the five counts, and they are five different numbers:",
        f"    rows (one admission x one family)   {_count(coverage['rows']):>10}",
        f"    admissions                          {_count(coverage['admissions']):>10}",
        f"    economic assets                     {_count(coverage['economic_assets']):>10}",
        f"    provider symbols                    {_count(coverage['provider_symbols']):>10}",
        f"    blocks with 2+ assets               "
        f"{_count(coverage['blocks_with_two_or_more_assets']):>10}",
        "",
        f"  time blocks occupied            {_count(coverage['blocks']):>10}",
        f"  (asset, block) cells            {_count(coverage['cells']):>10}",
        f"  possible asset pairs            {_count(coverage['possible_asset_pairs']):>10}",
        f"  measurable asset pairs          {_count(headline.pairwise['measurable_pairs']):>10}",
        f"  pairs below the shared-block floor "
        f"{_count(headline.pairwise['pairs_below_floor']):>8}",
        "",
        f"  observations per asset  min {_count(coverage['observations_per_asset_min'])}"
        f"  mean {_fmt(coverage['observations_per_asset_mean'], '.1f')}"
        f"  max {_count(coverage['observations_per_asset_max'])}",
        f"  assets with 2+ observations     "
        f"{_count(coverage['assets_with_two_or_more_observations']):>10}",
        "",
        f"  largest single-asset share      {_fmt(concentration['largest_share'])}",
        f"  top-three share                 {_fmt(concentration['top_three_share'])}",
    ]
    overlaps = [
        item
        for item in headline.overlap["by_family_sample"]
        if item["family_id"] == headline.family_id and item["sample"] == headline.sample
    ]
    for item in overlaps:
        lines.append(
            f"  admissions within {headline.overlap['evaluation_window_bars']} bars of "
            f"another on the same asset  {item['within_window_of_another']}"
            f" of {item['observations']} ({_fmt(item['share'], '.1%')})"
        )
    lines.append("")
    lines.append("  every one of these is a fact about the panel. None is an estimate.")
    return "\n".join(lines)


def render_measurement(study) -> str:
    """The two correlations, on their two axes, never in one column."""
    headline = study.headline
    between = headline.between_asset
    within = headline.within_asset
    lines = [
        "MEASUREMENT",
        _THIN,
        "  r_b — BETWEEN economic assets, same time block",
        f"    grouping                      time block",
        f"    member                        one (asset, block) cell mean",
        f"    groups / members              {between.components.groups} / "
        f"{between.components.members}",
        f"    mean square between / within  "
        f"{_fmt(between.components.mean_square_between)} / "
        f"{_fmt(between.components.mean_square_within)}",
        f"    k0                            {_fmt(between.components.k0)}",
        f"    variance components (a / e)   "
        f"{_fmt(between.components.between_variance)} / "
        f"{_fmt(between.components.within_variance)}",
        f"    r_b                           {_fmt(between.point, '+.6f')}",
        "",
        "  rho_w — WITHIN one economic asset, across its admissions",
        f"    grouping                      economic asset",
        f"    member                        one paired observation",
        f"    groups / members              {within.components.groups} / "
        f"{within.components.members}",
        f"    rho_w                         {_fmt(within.point, '+.6f')}",
        "",
        "  comparisons, none of which is an estimate:",
        f"    Milestone CC residual estimator  {_fmt(headline.cc_residual, '+.6f')}",
        f"    pairwise mean over measurable pairs "
        f"{_fmt(headline.pairwise['mean'], '+.6f')}"
        f"  (n={headline.pairwise['measurable_pairs']})",
        "",
        "  negative controls:",
    ]
    for control in headline.controls:
        lines.append(
            f"    {control.control_id:<26} observed {_fmt(control.observed, '+.5f')}"
            f"  under control {_fmt(control.under_control, '+.5f')}"
            f"  [{control.expectation}]"
        )
    return "\n".join(lines)


def render_uncertainty(study) -> str:
    """Every interval, with the axis it resampled and the draws it used."""
    headline = study.headline
    lines = ["UNCERTAINTY", _THIN]
    for label, interval in (
        ("r_b   (resampled: blocks)", headline.between_asset),
        ("r_b   (resampled: assets)", headline.between_asset_cross_axis),
        ("rho_w (resampled: assets)", headline.within_asset),
        ("rho_w (resampled: blocks)", headline.within_asset_cross_axis),
    ):
        lines.append(
            f"  {label:<26} {_fmt(interval.point, '+.6f')}  "
            f"[{_fmt(interval.lower, '+.6f')}, {_fmt(interval.upper, '+.6f')}]  "
            f"half-width {_fmt(interval.half_width, '.6f')}  "
            f"({interval.draws_used}/{interval.draws_requested} draws)"
        )
        if interval.reason:
            lines.append(f"      REFUSED: {interval.reason}")
        elif interval.point is not None and interval.lower is not None and (
            interval.point < interval.lower or interval.point > interval.upper
        ):
            lines.append(
                "      NOTE: this interval does NOT contain its own point "
                "estimate. Resampling the other axis duplicates a group inside "
                "the axis being estimated, and a duplicate is perfectly "
                "correlated with itself, so the estimate is inflated in every "
                "resample. It is a declared sensitivity, not an interval."
            )
    lines.append("")
    lines.append("  sensitivity — the WHOLE sealed grid, reported:")
    lines.append(
        "    rho_w is NOT a column here. It is computed on the economic-asset"
    )
    lines.append(
        "    axis, which reads no block length, no reduction and no weighting, so"
    )
    lines.append(
        "    it takes ONE value across the entire grid. Printing it sixteen times"
    )
    lines.append(
        "    would read as robustness when nothing was varied."
    )
    lines.append(
        f"    rho_w (invariant across every cell) "
        f"{_fmt(headline.sensitivity[0].within_asset, '+.5f')}"
    )
    lines.append("")
    lines.append(
        f"    {'block':>6} {'reduction':<11} {'weighting':<18} "
        f"{'r_b':>10} {'infm blk':>9}"
    )
    for cell in headline.sensitivity:
        lines.append(
            f"    {cell.block_bars:>6} {cell.reduction:<11} {cell.weighting:<18} "
            f"{_fmt(cell.between_asset, '+.5f'):>10} {cell.informative_blocks:>9}"
        )
    lines.append("")
    calibration = study.calibration
    lines.append(
        f"  estimator calibration            "
        f"{'PASSED' if calibration.passed else 'FAILED'}"
    )
    lines.append(f"    ordering reproduced            {calibration.ordering_reproduced}")
    for name, value in calibration.ordering_detail:
        lines.append(f"      {name:<24} {_fmt(value, '+.5f')}")
    if calibration.failures:
        lines.append(f"    FAILURES: {', '.join(calibration.failures)}")
    return "\n".join(lines)


def render_design_implication(study) -> str:
    """What the measurement does to Milestone CB's requirement, and to CC's."""
    requirement = study.requirement
    lines = [
        "DESIGN IMPLICATION",
        _THIN,
        f"  Milestone CB requirement (independent clusters)  "
        f"{_count(requirement.independent_clusters)}",
        f"  Milestone CB requirement (admissions)            "
        f"{_count(requirement.independent_admissions)}",
        f"  observations per cluster                         "
        f"{_fmt(requirement.observations_per_cluster, '.2f')}",
        f"  saturation threshold  1/K*                       "
        f"{_fmt(requirement.saturation_threshold, '.6f')}",
        f"  within-asset correlation supplied to CB          "
        f"{_fmt(requirement.within_asset_correlation, '+.6f')}",
        "",
        f"    {'bound':<14} {'r_b':>11} {'reachable':>10} {'clusters':>12} "
        f"{'admissions':>12}",
    ]
    for point in (requirement.lower, requirement.point, requirement.upper):
        lines.append(
            f"    {point.label:<14} {_fmt(point.correlation, '+.6f'):>11} "
            f"{('yes' if point.reachable else 'NO'):>10} "
            f"{_fmt(point.required_clusters, ',.0f'):>12} "
            f"{_fmt(point.required_admissions, ',.0f'):>12}"
        )
    lines.append("")
    lines.append("  POST-REVIEW CORRECTION (not sealed; see CD-8):")
    lines.append(
        "    r_b is an observation-level contemporaneous correlation, and the"
    )
    lines.append(
        "    effective-cluster formula expects a cluster-level one. The"
    )
    lines.append("    design-relevant quantity is q x r_b.")
    contemporaneity = study.headline.contemporaneity
    lines.append(
        f"    contemporaneity fraction q       "
        f"{_fmt(contemporaneity['contemporaneity_fraction'], '.4f')}"
    )
    lines.append(
        f"    q x r_b                          "
        f"{_fmt(contemporaneity['overlap_corrected_correlation'], '+.6f')}"
    )
    lines.append(
        f"    effective clusters at 38   sealed "
        f"{_fmt(contemporaneity['effective_clusters_at_38_sealed'], '.2f')}"
        f"   corrected "
        f"{_fmt(contemporaneity['effective_clusters_at_38_corrected'], '.2f')}"
    )
    lines.append(
        f"    effective clusters at 106  sealed "
        f"{_fmt(contemporaneity['effective_clusters_at_106_sealed'], '.2f')}"
        f"   corrected "
        f"{_fmt(contemporaneity['effective_clusters_at_106_corrected'], '.2f')}"
    )
    stability = study.headline.stability
    lines.append("")
    lines.append("  STABILITY (post-review; see CD-16):")
    for label, reading in (("drop one asset", stability["by_asset"]),
                           ("drop one block", stability["by_block"])):
        lines.append(
            f"    {label:<20} r_b spans "
            f"{_fmt(reading['minimum'], '+.4f')} to {_fmt(reading['maximum'], '+.4f')}"
            f"  ({_fmt(reading['ratio'], '.2f')}x over {reading['dropped']} drops)"
        )
    lines.append("")
    lines.append(f"  outcome                          {requirement.outcome.value.upper()}")
    lines.append(f"    {requirement.reasoning}")
    comparison = study.cc_comparison
    lines.append("")
    lines.append("  Milestone CC, re-read (CC's own verdict is NOT altered):")
    lines.append(
        f"    CC verdict preserved            {comparison['cc_verdict_preserved']}"
        f" / {comparison['cc_binding_constraint_preserved']}"
    )
    lines.append(
        f"    CC eligible assets              {_count(comparison['cc_eligible_assets'])}"
    )
    lines.append(
        f"    CC provider ceiling             "
        f"{_count(comparison['cc_provider_ceiling_clusters'])} clusters / "
        f"{_count(comparison['cc_provider_ceiling_admissions'])} admissions"
    )
    lines.append(
        f"    ceiling still below requirement {comparison['ceiling_still_below_requirement']}"
    )
    lines.append(
        f"    uncertainty makes it unidentifiable "
        f"{comparison['does_uncertainty_make_the_target_unidentifiable']}"
    )
    lines.append(
        f"    warm-up sensitivity justified   "
        f"{comparison['warm_up_sensitivity_is_justified']}"
    )
    return "\n".join(lines)


def render_limitations(study) -> str:
    """The sealed limitations, printed with the result rather than beside it."""
    from fmis.paired_dependence.preregistration import CD_LIMITATIONS

    from fmis.paired_dependence.preregistration import CD_POST_REVIEW_LIMITATIONS

    lines = ["LIMITATIONS", _THIN, "  SEALED:"]
    for item in CD_LIMITATIONS:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("  POST-REVIEW (established after the seal and after the result;")
    lines.append("  carried separately so the seal is not retro-fitted):")
    for item in CD_POST_REVIEW_LIMITATIONS:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("  reconstruction against Milestone CA's published figures:")
    lines.append(f"    {study.reconstruction['note']}")
    lines.append(
        f"    {'sample':<14} {'CD matched':>11} {'CA published':>13} {'delta':>8}"
    )
    for row in study.reconstruction["by_sample"]:
        lines.append(
            f"    {str(row['sample']):<14} {_count(row['cd_matched']):>11} "
            f"{_count(row['ca_published_matched']):>13} "
            f"{_count(row['matched_delta']):>8}"
        )
    return "\n".join(lines)


def render_dependence_study(study) -> str:
    """The complete Milestone CD report. **No BUY, no SELL, no recommendation.**"""
    assessment = study.assessment
    verdict = assessment.verdict
    lines = [
        _RULE,
        "MILESTONE CD — PAIRED-EFFECT DEPENDENCE MEASUREMENT",
        _RULE,
        f"  pre-registration   {study.manifest['preregistration_id']}",
        f"  seal               {study.manifest['preregistration_digest']}",
        f"  source capture     {study.manifest['capture_content_digest']}",
        f"  captured at        {study.manifest.get('capture_captured_at')}",
        f"  run at             {study.manifest['run_at']}",
        f"  source             {study.manifest.get('source')}",
        "",
        render_observation(study),
        "",
        render_measurement(study),
        "",
        render_uncertainty(study),
        "",
        render_design_implication(study),
        "",
        "VERDICT",
        _THIN,
        f"  scientific verdict               {verdict.value.upper()}",
        f"  design implication               {study.requirement.outcome.value.upper()}",
        f"    {assessment.reasoning}",
        "",
        f"  approves trading                 {verdict.is_approved_for_trading}",
        f"  earns a forward test             {verdict.earns_forward_test}",
        f"  says anything about the edge     "
        f"{not verdict.says_nothing_about_the_hypothesis}",
        "",
        "  Milestone CA's NO_EDGE, Milestone CB's UNDERPOWERED and Milestone CC's",
        "  INFEASIBLE all stand. This milestone measured a dependence and nothing",
        "  else; it promotes no setup, changes no production constant, and names",
        "  no position of any kind on any instrument.",
        "",
        render_limitations(study),
        _RULE,
    ]
    return "\n".join(lines)
