"""Terminal report for one validation study. **Renders what was measured, computes nothing.**

Every number printed here came off a `VariantMetrics`, a `PlateauReading` or a
`CandidateAssessment`. This module holds no arithmetic beyond formatting a number
and laying out a column, matching every other renderer in this repository.

**The order is the argument.** A validation report that opened with a table of
expectancies would invite a reader to find the best row, which is the exact
mistake the whole milestone is built to prevent. So it opens with the *verdict*,
then the *seal*, and only then the numbers:

1. **the answer** — is there a candidate, and if not, what blocked it;
2. **the seal** — which pre-registration these numbers were judged against, and
   whether it still matches the repository;
3. **the samples** — with each one's contamination printed beside its name, never
   in a footnote;
4. **the results**, in **pre-registration order and never sorted by result** — a
   table sorted by expectancy has chosen a winner;
5. **the plateau**, with every neighbour including the failing ones;
6. **costs**, with the deciding scenario marked, because a frictionless column
   read as a result is how BX's §10 spike looked convincing;
7. **walk-forward and the decompositions**;
8. **the limitations in full**, because BY-2 and BY-4 change what the tables
   above are allowed to mean.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal

from fmis.swing_lab.metrics import LabMeasure, VariantMetrics
from fmis.swing_lab.models import LabVerdict
from fmis.swing_lab.validation import CandidateAssessment, PlateauReading
from fmis.swing_lab.validation_mechanics import MechanicsStudy
from fmis.swing_lab.validation_study import (
    Decomposition,
    PolicyValidation,
    ValidationStudy,
    WalkForwardWindow,
)

__all__ = [
    "render_validation_study",
    "render_verdict_first",
    "render_samples",
    "render_results",
    "render_plateau",
    "render_costs",
    "render_walk_forward",
    "render_decompositions",
    "render_mechanics",
]

_WIDTH = 100
_ABSENT = "—"


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _heading(title: str) -> list[str]:
    return ["", _rule("="), f" {title}", _rule("=")]


def _decimal(value: Decimal | float | None, places: int = 4) -> str:
    return _ABSENT if value is None else f"{float(value):+.{places}f}"


def _measure(measure: LabMeasure, places: int = 4) -> str:
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{_decimal(measure.value, places)} (n={measure.n})"


def _rate(measure: LabMeasure) -> str:
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{float(measure.value) * 100:.1f}% (n={measure.n})"


def _plain(value: Decimal | float | None, places: int = 2) -> str:
    return _ABSENT if value is None else f"{float(value):.{places}f}"


def _sample_names(study: ValidationStudy) -> tuple[str, ...]:
    """The samples in declaration order. **Never the membership tally's keys.**

    The tally also carries `unclaimed`, which is a diagnostic count rather than a
    sample, and reading the table's rows off it would print a column no policy
    was ever measured on. `run_validation_study` guarantees a cell exists for
    every name here, including empty ones for a holdout that was not opened, so
    no lookup below needs a guard.
    """
    return tuple(spec["name"] for spec in study.manifest.samples)


def _wrap(text: str, indent: str = "   ") -> list[str]:
    return textwrap.wrap(text, width=_WIDTH - len(indent), initial_indent=indent,
                         subsequent_indent=indent)


# ------------------------------------------------------------- the answer ---


def render_verdict_first(study: ValidationStudy) -> str:
    """The milestone's answer, before any table that could argue with it."""
    lines = _heading("VALIDATION VERDICT")
    candidates = study.candidates
    if candidates:
        lines.append("")
        lines.append(" CANDIDATE FOR FORWARD TEST — RESEARCH ONLY, NOT LIVE")
        for item in candidates:
            lines.append(f"   {item.assessment.statement}")
        lines.append("")
        lines.extend(
            _wrap(
                "This is NOT approval to trade. It means the frozen policy version "
                "below is worth running unchanged in a shadow/forward test, and "
                "nothing more. Production remains the current policy."
            )
        )
    else:
        lines.append("")
        lines.append(" NO FORWARD-TEST CANDIDATE")
        lines.append("")
        lines.extend(
            _wrap(
                "No pre-registered hypothesis met every sealed criterion. The "
                "criteria each policy missed are named below, by policy and by "
                "criterion, so the failure can be read rather than guessed at."
            )
        )

    inconclusive = [
        item for item in study.policies
        if item.assessment.verdict is LabVerdict.INCONCLUSIVE
    ]
    if inconclusive:
        lines.append("")
        lines.append(
            f" {len(inconclusive)} of {len(study.policies)} hypotheses are "
            "INCONCLUSIVE — too few measurable trades to state a figure. That is "
            "not a negative result; nothing was established about them."
        )
    return "\n".join(lines)


def render_seal(study: ValidationStudy) -> str:
    """Which pre-registration these numbers were judged against."""
    manifest = study.manifest
    lines = _heading("PRE-REGISTRATION")
    lines.append(f" id      {manifest.preregistration_id}")
    lines.append(f" digest  {manifest.preregistration_digest}")
    lines.append(
        " seal    "
        + (
            "MATCHES the pre-registration in this repository"
            if manifest.preregistration_digest_matches
            else "DOES NOT MATCH — these numbers were judged against different rules"
        )
    )
    lines.append(f" deciding cost scenario  {manifest.deciding_cost_policy_id}")
    lines.append(
        f" no-lookahead suite      "
        + ("passed for this capture" if manifest.no_lookahead_proven else "NOT PROVEN")
    )
    lines.append("")
    lines.extend(
        _wrap(
            "Every hypothesis id, threshold, symbol list, window boundary, cost "
            "scenario and candidate criterion was fixed and digested before this "
            "study ran. Anything not sealed is post-hoc and cannot be promoted."
        )
    )
    return "\n".join(lines)


def render_samples(study: ValidationStudy) -> str:
    """Each sample with its contamination beside it, never in a footnote."""
    lines = _heading("SAMPLES")
    membership = study.manifest.sample_membership
    for spec in study.manifest.samples:
        lines.append("")
        lines.append(
            f" {spec['name'].upper():<12} {spec['signal_start'][:10]} → "
            f"{spec['signal_end'][:10]}   "
            f"{len(spec['symbols'])} symbols   "
            f"{membership.get(spec['name'], 0)} candidates"
        )
        lines.extend(_wrap(spec["contamination"], indent="      "))
    if membership.get("unclaimed"):
        lines.append("")
        lines.append(
            f" {membership['unclaimed']} captured candidates fall in NO sample "
            "and are measured by nothing. Reported rather than dropped."
        )
    return "\n".join(lines)


# ------------------------------------------------------------- the tables ---


def _sample_row(item: PolicyValidation, sample: str, cost: str) -> str:
    measurement = item.measurement(sample, cost)
    metrics = measurement.metrics
    return (
        f"   {sample:<12} {measurement.admitted:>4} {measurement.refused:>5} "
        f"{metrics.measurable_trades:>4} {metrics.ambiguous_trades:>4} "
        f"{_rate(metrics.win_rate):>16} {_measure(metrics.expectancy_r):>20} "
        f"{_plain(metrics.profit_factor.value):>7} "
        f"{_decimal(metrics.total_r, 2):>9}"
    )


def render_results(study: ValidationStudy) -> str:
    """Every hypothesis, in **pre-registration order**. Never sorted by result."""
    cost = study.manifest.deciding_cost_policy_id
    lines = _heading(f"RESULTS — cost-inclusive ({cost})")
    lines.append("")
    lines.append(
        "   sample       trd  skip    n  amb          win rate            "
        "expectancy      PF     totR"
    )
    for item in study.policies:
        hypothesis = item.hypothesis
        lines.append("")
        lines.append(
            f" {hypothesis.hypothesis_id}  {item.policy_id}  "
            f"[{hypothesis.role}]"
            + ("" if hypothesis.is_structural else "  ** NON-STRUCTURAL CONTROL **")
        )
        for sample in _sample_names(study):
            lines.append(_sample_row(item, sample, cost))
        lines.append(f"   → {item.assessment.statement}")
    return "\n".join(lines)


def render_criteria(item: PolicyValidation) -> str:
    """Every criterion by name, so a rejection says which requirement it missed."""
    assessment: CandidateAssessment = item.assessment
    lines = [f" {item.policy_id}"]
    for criterion in assessment.criteria:
        lines.append(f"   [{criterion.symbol}] {criterion.name}")
        lines.extend(_wrap(f"observed: {criterion.observed}", indent="          "))
    return "\n".join(lines)


def render_plateau(reading: PlateauReading | None, policy_id: str) -> str:
    """Every neighbour, including the failing ones. **Nothing is hidden here.**"""
    if reading is None:
        return f" {policy_id}: no pre-declared neighbourhood, so no plateau test"
    lines = [f" {policy_id}: {reading.classification.value.upper()}"]
    lines.extend(_wrap(reading.classification.statement, indent="      "))
    for point in reading.readings:
        marker = "*" if point.is_primary else " "
        value = point.expectancy
        lines.append(
            f"    {marker} {point.axis}={point.threshold:<5g} "
            f"{_decimal(value) if value is not None else _ABSENT:>12} "
            f"(n={point.metrics.measurable_trades})"
        )
    return "\n".join(lines)


def render_costs(study: ValidationStudy) -> str:
    """Every scenario side by side, with the deciding one marked."""
    deciding = study.manifest.deciding_cost_policy_id
    scenarios = study.manifest.cost_policy_ids
    lines = _heading("COST SENSITIVITY — expectancy in R")
    lines.append("")
    header = "   policy".ljust(40) + "sample".ljust(14)
    for name in scenarios:
        header += f"{name:>32}" if name != deciding else f"{name + ' *':>32}"
    lines.append(header)
    lines.append("   * the deciding scenario. No candidate may be selected on any other.")
    for item in study.policies:
        for sample in _sample_names(study):
            row = f"   {item.policy_id:<37} {sample:<13}"
            for name in scenarios:
                metrics = item.measurement(sample, name).metrics
                row += f"{_measure(metrics.expectancy_r):>32}"
            lines.append(row)
    return "\n".join(lines)


def render_walk_forward(
    windows: tuple[WalkForwardWindow, ...], policy_id: str
) -> str:
    """The frozen policy across time. Empty windows are printed, never omitted."""
    lines = _heading(f"WALK-FORWARD — {policy_id}, frozen, no re-optimisation")
    lines.append("")
    lines.append(
        "   window                        trd    n          win rate"
        "            expectancy      PF     totR     maxDD"
    )
    for window in windows:
        metrics = window.metrics
        lines.append(
            f"   {window.label:<28} {metrics.trades:>4} {metrics.measurable_trades:>4} "
            f"{_rate(metrics.win_rate):>16} {_measure(metrics.expectancy_r):>20} "
            f"{_plain(metrics.profit_factor.value):>7} "
            f"{_decimal(metrics.total_r, 2):>9} "
            f"{_plain(metrics.max_drawdown.max_drawdown_r):>9}"
        )
    return "\n".join(lines)


def render_decompositions(cuts: tuple[Decomposition, ...]) -> str:
    """Every required cut. Cohorts below the floor report an absence with a reason."""
    lines = _heading("DECOMPOSITION")
    for cut in cuts:
        lines.append("")
        agreement = {
            True: "every reportable cohort agrees on sign",
            False: "cohorts DISAGREE on sign",
            None: "too few reportable cohorts to compare",
        }[cut.agrees_on_sign]
        lines.append(f" {cut.name}  —  {agreement}")
        lines.extend(_wrap(cut.question, indent="      "))
        for cohort in cut.cohorts:
            lines.append(
                f"      {cohort.label.split(':')[-1]:<24} "
                f"{_measure(cohort.expectancy_r):>20}  "
                f"totR {_decimal(cohort.total_r, 2):>9}"
            )
    return "\n".join(lines)


def render_mechanics(study: MechanicsStudy | None) -> str:
    """§7, §8 and §9: entry timing, intrabar resolution and exit management."""
    if study is None:
        return "\n".join(
            _heading("ENTRY, EXIT AND INTRABAR MECHANICS")
            + ["", " NOT MEASURED for this run — no lower-timeframe series was loaded."]
        )
    lines = _heading("ENTRY, EXIT AND INTRABAR MECHANICS")
    lines.append("")
    lines.append(f" geometry {study.geometry_policy_id} · sample {study.sample}")

    reading = study.ambiguity
    lines.append("")
    lines.append(" §8 INTRABAR AMBIGUITY")
    lines.append(
        f"      ambiguous on 4H alone     {reading.without_ladder}"
    )
    lines.append(
        f"      still ambiguous with 1H/15m {reading.still_ambiguous}"
    )
    rate = reading.resolution_rate
    lines.append(
        "      resolved                  "
        + (
            f"{reading.resolved} ({rate * 100:.1f}%)"
            if rate is not None
            else f"{reading.resolved}"
        )
    )
    if reading.still_ambiguous:
        lines.extend(
            _wrap(
                "The remainder stay AMBIGUOUS and are excluded from expectancy. "
                "They are never guessed.",
                indent="      ",
            )
        )

    lines.append("")
    lines.append(" §7 ENTRY RULES")
    lines.append(
        "      policy                          filled  missed   fill%      "
        "n           expectancy"
    )
    for item in study.entries:
        share = item.fill_rate
        lines.append(
            f"      {item.policy.policy_id:<31} {item.filled:>6} {item.missed:>7} "
            + (f"{share * 100:>6.1f}%" if share is not None else f"{_ABSENT:>7}")
            + f" {item.metrics.measurable_trades:>6} "
            f"{_measure(item.metrics.expectancy_r):>20}"
        )
        for reason, count in item.miss_reasons:
            lines.append(f"          {count:>4} × {reason}")

    lines.append("")
    lines.append(" §9 EXIT MECHANICS")
    lines.append(
        "      policy                          ladder   amb    n           "
        "expectancy      avgWin     avgLoss"
    )
    for item in study.exits:
        lines.append(
            f"      {item.policy.policy_id:<31} "
            f"{'yes' if item.used_ladder else 'NO ':>6} {item.ambiguous:>5} "
            f"{item.metrics.measurable_trades:>4} "
            f"{_measure(item.metrics.expectancy_r):>20} "
            f"{_measure(item.metrics.average_win_r, 3):>12} "
            f"{_measure(item.metrics.average_loss_r, 3):>12}"
        )
    lines.append("")
    lines.extend(
        _wrap(
            "The 'NO ladder' row is the control: it must reproduce "
            "simulate_trade exactly, so any difference between it and the "
            "'yes' row of the same policy is the lower-timeframe evidence and "
            "not the management rule."
        )
    )
    return "\n".join(lines)


def render_validation_study(
    study: ValidationStudy, mechanics: MechanicsStudy | None = None
) -> str:
    """The whole report, in the order a decision is made rather than measured."""
    blocks = [
        render_verdict_first(study),
        render_seal(study),
        render_samples(study),
        render_results(study),
    ]

    blocks.append("\n".join(_heading("CRITERIA, BY POLICY")))
    blocks.extend(render_criteria(item) for item in study.policies)

    blocks.append("\n".join(_heading("PARAMETER PLATEAU")))
    blocks.extend(
        render_plateau(item.plateau, item.policy_id)
        for item in study.policies
        if item.plateau is not None
    )

    blocks.append(render_costs(study))
    blocks.append(render_walk_forward(study.walk_forward, study.walk_forward_policy_id))
    blocks.append(render_decompositions(study.decompositions))
    blocks.append(render_mechanics(mechanics))

    limitations = _heading("LIMITATIONS")
    for item in study.manifest.limitations:
        limitations.append("")
        limitations.extend(_wrap(item, indent="   "))
    blocks.append("\n".join(limitations))

    blocks.append("")
    blocks.append(_rule("="))
    blocks.append(f" result digest  {study.manifest.result_digest}")
    blocks.append(f" seal           {study.manifest.preregistration_digest}")
    blocks.append(_rule("="))
    return "\n".join(blocks)
