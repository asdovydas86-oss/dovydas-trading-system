"""Terminal report for one geometry study. **Renders what was measured, computes nothing.**

Every number printed here came off a `VariantMetrics`, a `Distribution`, a
`Share` or a `GeometryAssessment`. This module holds no arithmetic beyond
formatting a number and laying out a column, matching every other renderer in
this repository.

Five things print whether or not anyone asks, because each is a way a geometry
comparison can mislead a reader who trusts it:

* **`n` beside every rate**, and a refused rate below the sample floor;
* **the skip counts beside the trade counts** — a variant that trades six times
  because it refused ninety candidates is a different finding from one that
  trades six times because six setups formed;
* **development and holdout side by side**, never one without the other;
* **every failing criterion by name**, so a rejection says which requirement it
  missed rather than only that it missed one;
* **the limitations in full**, because BX-2 and BX-3 change what the tables above
  are allowed to mean.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal

from fmis.swing_lab.geometry_diagnosis import Distribution, GeometryDiagnosis, Share
from fmis.swing_lab.geometry_study import (
    GeometryStudy,
    PolicyResult,
    SensitivityCurve,
)
from fmis.swing_lab.geometry_verdict import GeometryAssessment
from fmis.swing_lab.metrics import LabMeasure, VariantMetrics

__all__ = [
    "render_geometry_study",
    "render_geometry_comparison",
    "render_diagnosis",
    "render_sensitivity",
    "render_assessment",
]

_WIDTH = 100
_ABSENT = "—"


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _heading(title: str) -> list[str]:
    return ["", _rule("="), f" {title}", _rule("=")]


def _decimal(value: Decimal | float | None, places: int = 3) -> str:
    if value is None:
        return _ABSENT
    return f"{float(value):+.{places}f}"


def _measure(measure: LabMeasure, places: int = 3) -> str:
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{_decimal(measure.value, places)} (n={measure.n})"


def _rate(measure: LabMeasure) -> str:
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{float(measure.value) * 100:5.1f}% (n={measure.n})"


def _plain(value: float | None, places: int = 2) -> str:
    return _ABSENT if value is None else f"{value:.{places}f}"


def render_geometry_comparison(results: tuple[PolicyResult, ...]) -> str:
    """Every policy, development beside holdout, one row per figure."""
    if not results:
        return "No geometry policy produced a result."
    lines = [
        f"{'policy':<26} {'sample':<12} {'trd':>4} {'skip':>5} {'meas':>5} "
        f"{'win%':>7} {'expR':>9} {'medR':>8} {'PF':>7} {'totR':>9} {'maxDD':>8} "
        f"{'plannedRR':>10}",
        _rule("─"),
    ]
    for result in results:
        for sample in (result.development, result.holdout):
            metrics = sample.metrics
            rr = sample.diagnosis.distribution("planned_rr")
            lines.append(
                f"{result.policy.policy_id:<26} {sample.sample:<12} "
                f"{metrics.trades:>4} {sample.outcome.refused:>5} "
                f"{metrics.measurable_trades:>5} "
                f"{(f'{float(metrics.win_rate.value) * 100:.1f}' if metrics.win_rate.value is not None else _ABSENT):>7} "
                f"{(_decimal(metrics.expectancy_r.value, 4) if metrics.expectancy_r.value is not None else _ABSENT):>9} "
                f"{(_decimal(metrics.median_r.value, 3) if metrics.median_r.value is not None else _ABSENT):>8} "
                f"{(_plain(float(metrics.profit_factor.value)) if metrics.profit_factor.value is not None else _ABSENT):>7} "
                f"{_decimal(metrics.total_r, 2):>9} "
                f"{_plain(float(metrics.max_drawdown.max_drawdown_r)):>8} "
                f"{_plain(rr.median):>10}"
            )
        lines.append("")
    return "\n".join(lines)


def _distribution_row(item: Distribution) -> str:
    return (
        f"{item.label:<26} n={item.n:<5} "
        f"min={_plain(item.minimum, 3):>10} p25={_plain(item.p25, 3):>10} "
        f"med={_plain(item.median, 3):>10} p75={_plain(item.p75, 3):>10} "
        f"max={_plain(item.maximum, 3):>10} mean={_plain(item.mean, 3):>10}"
    )


def _share_line(name: str, share: Share) -> str:
    return f"  {name:<52} {share.text}"


def render_diagnosis(diagnosis: GeometryDiagnosis) -> str:
    """The §2 diagnosis: distributions, shares, cohort breakdowns, then the readings."""
    lines = _heading(f"GEOMETRY DIAGNOSIS — {diagnosis.label}")
    lines.append("")
    lines.append("Distributions (quantiles by linear interpolation between closest ranks)")
    lines.append(_rule("─"))
    for item in diagnosis.distributions:
        lines.append(_distribution_row(item))

    lines.append("")
    lines.append("Headline shares (a rate is refused below the 20-trade floor)")
    lines.append(_rule("─"))
    lines.append(
        _share_line("setups planning reward < risk", diagnosis.reward_below_risk)
    )
    lines.append(
        _share_line(
            "target-exit trades returning under +1R", diagnosis.target_exits_below_one_r
        )
    )
    lines.append(
        _share_line("stops inside one ATR(14) of the entry", diagnosis.stops_inside_one_atr)
    )
    lines.append(
        _share_line(
            "trades giving back a full R of open profit",
            diagnosis.mfe_exceeds_realized_by_one_r,
        )
    )
    lines.append(
        _share_line(
            "stop-outs whose target was reached afterwards",
            diagnosis.stopped_then_reached_target,
        )
    )

    if diagnosis.skip_reasons:
        lines.append("")
        lines.append("Refusals by reason")
        lines.append(_rule("─"))
        for reason, count in diagnosis.skip_reasons:
            lines.append(f"  {reason:<52} {count}")

    for name, cohorts in diagnosis.breakdowns:
        reportable = [item for item in cohorts if item.trades]
        if not reportable:
            continue
        lines.append("")
        lines.append(f"By {name}")
        lines.append(_rule("─"))
        for cohort in reportable:
            label = cohort.label.split(":")[-1]
            lines.append(
                f"  {label:<34} trades={cohort.trades:<5} "
                f"expectancy={_measure(cohort.expectancy_r, 4)}  "
                f"total={_decimal(cohort.total_r, 2)}"
            )

    lines.append("")
    lines.append("Findings — INTERPRETATION, each shown beside the measurement it reads")
    lines.append(_rule("─"))
    for finding in diagnosis.findings:
        verdict = {True: "YES", False: "NO ", None: "N/A"}[finding.supported]
        lines.append(f"  [{verdict}] {finding.question}")
        lines.append(f"        evidence: {finding.evidence}")
        for wrapped in textwrap.wrap(finding.reading, width=_WIDTH - 10):
            lines.append(f"        {wrapped}")
        lines.append("")
    return "\n".join(lines)


def render_sensitivity(curve: SensitivityCurve) -> str:
    """One threshold swept across its grid, development beside holdout."""
    lines = [
        f"{curve.kind} sensitivity — a plateau is evidence, a spike is an artifact",
        _rule("─"),
        f"{'threshold':>10} {'dev trades':>11} {'dev expR':>10} "
        f"{'hold trades':>12} {'hold expR':>10}",
    ]
    for point in curve.points:
        lines.append(
            f"{point.threshold:>10.2f} "
            f"{point.development.measurable_trades:>11} "
            f"{(_decimal(point.development.expectancy_r.value, 4) if point.development.expectancy_r.value is not None else _ABSENT):>10} "
            f"{point.holdout.measurable_trades:>12} "
            f"{(_decimal(point.holdout.expectancy_r.value, 4) if point.holdout.expectancy_r.value is not None else _ABSENT):>10}"
        )
    plateau = curve.is_plateau
    lines.append(
        "  plateau: "
        + {
            True: "yes — every measurable point agrees in sign",
            False: "NO — the sign changes across the grid; this is a spike",
            None: "not evaluable — fewer than three points cleared the sample floor",
        }[plateau]
    )
    return "\n".join(lines)


def render_assessment(assessment: GeometryAssessment) -> str:
    """One policy against every criterion, each with the measurement that decided it."""
    lines = [f"{assessment.policy_id} — {assessment.verdict.value.upper()}", _rule("─")]
    for criterion in assessment.criteria:
        lines.append(f"  [{criterion.symbol}] {criterion.name}")
        lines.append(f"          requires: {criterion.requirement}")
        lines.append(f"          observed: {criterion.observed}")
    lines.append(f"  → {assessment.statement}")
    return "\n".join(lines)


def render_geometry_study(study: GeometryStudy) -> str:
    """The whole report, in the order a reader should meet it.

    The verdict summary comes **first**, because a reader who stops after the
    first screen must not come away with a different impression from one who
    reads to the end.
    """
    manifest = study.manifest
    lines: list[str] = []
    lines.extend(_heading("SWING TRADE GEOMETRY LABORATORY"))
    lines.append("")
    lines.append(f"Experiment          {manifest.experiment_id}")
    lines.append(
        f"Development         {', '.join(manifest.development_symbols)} "
        f"({len(manifest.development_symbols)} symbols)"
    )
    lines.append(
        f"Holdout             {', '.join(manifest.holdout_symbols)} "
        f"({len(manifest.holdout_symbols)} symbols, never previously measured)"
    )
    lines.append(
        f"Measurement window  {manifest.measurement_start.date()} → "
        f"{manifest.measurement_end.date()}   warm-up from {manifest.warmup_start.date()}"
    )
    lines.append(
        f"Admission           {manifest.admission_variant_id} "
        f"({manifest.admission_policy_id}) — held FIXED for every geometry"
    )
    lines.append(f"Candidates captured {manifest.candidate_count}")
    lines.append(
        f"Evaluation window   {manifest.evaluation_window_bars} execution bars   "
        f"costs: {manifest.cost_policy.get('policy_id')}"
    )
    lines.append(f"Result digest       {manifest.result_digest}")

    lines.extend(_heading("VERDICTS"))
    lines.append("")
    candidates = study.candidates
    if candidates:
        lines.append(
            f"{len(candidates)} of {len(study.results)} policies met every criterion:"
        )
        for item in candidates:
            lines.append(f"  * {item.policy.policy_id} — {item.policy.title}")
        lines.append("")
        lines.append(
            "  CANDIDATE_FOR_FORWARD_TEST means WORTH TESTING FORWARD. It is not "
            "approval to trade, and no verdict this repository produces is."
        )
    else:
        lines.append(
            "NO CANDIDATE. No geometry policy met every criterion, so none is "
            "proposed for forward or shadow testing."
        )
    lines.append("")
    for result in study.results:
        blocking = result.assessment.blocking
        summary = (
            "every criterion met"
            if not blocking
            else "blocked by " + ", ".join(item.name for item in blocking)
        )
        lines.append(
            f"  {result.policy.policy_id:<26} {result.policy.family:<32} "
            f"{result.assessment.verdict.value:<26} {summary}"
        )

    lines.extend(_heading("DEVELOPMENT AND HOLDOUT"))
    lines.append("")
    lines.append(render_geometry_comparison(study.results))

    if study.sensitivity:
        lines.extend(_heading("PARAMETER SENSITIVITY"))
        for curve in study.sensitivity:
            lines.append("")
            lines.append(render_sensitivity(curve))

    lines.extend(_heading("CRITERIA, POLICY BY POLICY"))
    for result in study.results:
        lines.append("")
        lines.append(render_assessment(result.assessment))

    lines.append(render_diagnosis(study.baseline_diagnosis))

    lines.extend(_heading("LIMITATIONS"))
    lines.append("")
    for limitation in manifest.limitations:
        for index, wrapped in enumerate(
            textwrap.wrap(limitation, width=_WIDTH - 6)
        ):
            lines.append(("  " if index == 0 else "        ") + wrapped)
        lines.append("")
    return "\n".join(lines)
