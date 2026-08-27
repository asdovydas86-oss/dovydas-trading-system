"""Rendering Milestone BZ's study. **Presentation only — this decides nothing.**

Every number printed here is computed by `fmis.swing_lab.persistence_study` and
carried on the study object. This module selects, orders and formats; it
recomputes nothing, and a figure that does not already exist cannot be produced
by reading this file.

The ordering is a decision aid rather than a data dump: the verdict first,
because that is what the reader came for; then the seal, so a number's basis is
visible before the number; then the observational half; then the sealed families
with their like-for-like column marked; then the limitations, which change what
every table above means.

**The descriptive and the causal halves are printed under separate headings**, and
that separation is the whole of BZ's methodological discipline made visible. A
reader must not be able to take a give-back distribution — which conditions on a
whole path — for a rule that could have been run.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fmis.swing_lab.persistence_study import (
    BzVerdict,
    FamilyComparison,
    PathSummary,
    PersistenceStudy,
)

__all__ = ["render_persistence_study"]

_RULE = "=" * 78
_THIN = "-" * 78


def _r(value: Decimal | float | None, width: int = 8) -> str:
    if value is None:
        return "n/a".rjust(width)
    return f"{float(value):+.4f}".rjust(width)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _verdict_line(study: PersistenceStudy) -> list[str]:
    lines = ["", _RULE, "MILESTONE BZ — SWING THESIS PERSISTENCE & EXIT MECHANICS", _RULE]
    candidates = [
        item for item in study.assessments if item.verdict is BzVerdict.CANDIDATE
    ]
    evidence = [
        item
        for item in study.assessments
        if item.verdict is BzVerdict.MECHANISM_EVIDENCE
    ]
    if candidates:
        lines.append(
            f"VERDICT: CANDIDATE — {len(candidates)} family/families cleared every "
            "sealed criterion."
        )
        for item in candidates:
            lines.append(f"  {item.hypothesis_id} {item.policy_id} "
                         f"on {item.geometry_policy_id}")
        lines.append(
            "  This means WORTH TESTING FORWARD. It is NOT approval to trade."
        )
    elif evidence:
        lines.append(
            f"VERDICT: NO_CANDIDATE — but {len(evidence)} family/families carry "
            "MECHANISM_EVIDENCE."
        )
        for item in evidence:
            lines.append(f"  {item.hypothesis_id} {item.policy_id} "
                         f"on {item.geometry_policy_id}")
        lines.append(
            "  MECHANISM_EVIDENCE is a finding about INFORMATION. It approves "
            "nothing and earns no forward test."
        )
    else:
        lines.append(
            "VERDICT: NO_CANDIDATE — no sealed exit family earned the right to "
            "shadow or paper testing."
        )
    return lines


def _seal(study: PersistenceStudy) -> list[str]:
    state = "MATCHES" if study.digest_matches else "*** MISMATCH ***"
    return [
        "",
        _THIN,
        "PRE-REGISTRATION",
        _THIN,
        f"  id      {study.preregistration_id}",
        f"  digest  {study.preregistration_digest}  [{state}]",
        f"  costs   deciding scenario: {study.deciding_cost_policy_id}",
        f"  window  {study.evaluation_window_bars} execution bars",
        f"  timeline instants observed: {study.timeline_instants:,}",
    ]


def _paths(study: PersistenceStudy) -> list[str]:
    lines = [
        "",
        _THIN,
        "POST-ENTRY PATHS — DESCRIPTIVE. These condition on a whole path and",
        "therefore contain the future. They may NEVER be read as decision rules.",
        _THIN,
        f"  {'geometry / sample':38s} {'paths':>6s} {'>=1R':>7s} {'gave 1R back':>13s}"
        f" {'peak p50':>9s} {'peak p75':>9s}",
    ]
    for (geometry, sample), summary in sorted(study.paths.items()):
        label = f"{geometry} / {sample}"
        lines.append(
            f"  {label:38s} {summary.paths:6d} "
            f"{_pct(summary.rate_reached('1.0')):>7s} "
            f"{_pct(summary.full_r_giveback_rate):>13s} "
            f"{_num(summary.peak_r_median):>9s} {_num(summary.peak_r_p75):>9s}"
        )
    lines += ["", "  Time to first arrival (median bars, over paths that reached it):"]
    for (geometry, sample), summary in sorted(study.paths.items()):
        arrivals = " ".join(
            f"{key}R={_num(value)}"
            for key, value in sorted(summary.median_bars_to.items())
        )
        lines.append(f"    {geometry}/{sample}: {arrivals}")
        lines.append(
            f"      first adverse 0.5R: {_num(summary.median_bars_to_adverse)} · "
            f"peak at: {_num(summary.median_bars_to_peak)}"
        )
    return lines


def _thesis(study: PersistenceStudy) -> list[str]:
    lines = [
        "",
        _THIN,
        "THESIS STATE BY TRADE AGE — CAUSAL. Each reading is confirmed by its own",
        "bar and is what an exit rule was entitled to see at that bar.",
        _THIN,
    ]
    for (geometry, sample), summary in sorted(study.paths.items()):
        if not summary.thesis_at_checkpoint:
            continue
        lines.append(f"  {geometry} / {sample}")
        states = sorted(
            {
                state
                for counts in summary.thesis_at_checkpoint.values()
                for state in counts
            }
        )
        lines.append("    bar  " + "  ".join(f"{s[:9]:>9s}" for s in states))
        for bar, counts in sorted(summary.thesis_at_checkpoint.items()):
            row = "  ".join(f"{counts.get(state, 0):9d}" for state in states)
            lines.append(f"    {bar:3d}  {row}")
    return lines


def _giveback(study: PersistenceStudy) -> list[str]:
    lines = [
        "",
        _THIN,
        "GIVE-BACK — Milestone BX measured 68.8 % on development. Reproduced here",
        "under BZ's dataset, then decomposed. DESCRIPTIVE.",
        _THIN,
    ]
    for (geometry, sample), item in sorted(study.giveback.items()):
        lines.append(
            f"  {geometry} / {sample}: {item.gave_back_a_full_r}/{item.paths} "
            f"= {_pct(item.rate)}   median bars peak→exit: "
            f"{_num(item.median_bars_peak_to_exit)}"
        )
        realised = " · ".join(
            f"after {key}R: n={count} median realised {_num(value)}"
            for key, (count, value) in sorted(item.realised_after_reaching.items())
        )
        lines.append(f"      {realised}")
        direction = " · ".join(
            f"{name}: n={count} rate={_pct(rate)}"
            for name, (count, rate) in sorted(item.by_direction.items())
        )
        lines.append(f"      by direction: {direction}")
        lines.append(
            f"      largest single-symbol share of gross |R|: "
            f"{_pct(None if item.largest_symbol_share is None else float(item.largest_symbol_share))}"
        )
    return lines


def _families(comparison: FamilyComparison) -> list[str]:
    lines = [
        "",
        f"  {comparison.geometry_policy_id} / {comparison.sample}  "
        f"(like-for-like over {comparison.shared_setups} shared setups)",
        f"    {'family':30s} {'n':>4s} {'amb':>4s} {'fired':>5s} "
        f"{'expectancy':>10s} {'like4like':>10s} {'vs H0':>10s}",
    ]
    for item in comparison.measurements:
        improvement = comparison.improvement(item.policy_id)
        marker = " (control)" if item.policy_id == comparison.control_policy_id else ""
        lines.append(
            f"    {item.policy_id:30s} {item.metrics.measurable_trades:4d} "
            f"{item.ambiguous:4d} {item.fired:5d} "
            f"{_r(item.expectancy, 10)} {_r(item.comparable_expectancy, 10)} "
            f"{_r(improvement, 10)}{marker}"
        )
    return lines


def _assessments(study: PersistenceStudy) -> list[str]:
    lines = ["", _THIN, "ASSESSMENT AGAINST THE SEALED CRITERIA", _THIN]
    for item in study.assessments:
        lines.append(
            f"  {item.geometry_policy_id:26s} {item.hypothesis_id:6s} "
            f"{item.policy_id:30s} {item.verdict.value.upper()}"
        )
        for criterion in item.mechanism_criteria + item.candidate_criteria:
            if criterion.passed is True:
                continue
            mark = "FAIL" if criterion.passed is False else "n/a "
            lines.append(f"      [{mark}] {criterion.name}: {criterion.detail}")
    return lines


def render_persistence_study(study: PersistenceStudy) -> str:
    """One complete BZ report as text. **Pure: no clock, no file, no network.**"""
    if not isinstance(study, PersistenceStudy):
        raise TypeError(
            f"study must be a PersistenceStudy, got {type(study).__name__}"
        )
    lines: list[str] = []
    lines += _verdict_line(study)
    lines += _seal(study)
    lines += _paths(study)
    lines += _thesis(study)
    lines += _giveback(study)
    lines += ["", _THIN, "SEALED EXIT FAMILIES — CAUSAL", _THIN]
    lines.append(
        "  'like4like' re-measures every family over the setups ALL of them could"
    )
    lines.append(
        "  measure. Read that column: a raw comparison flatters management, because"
    )
    lines.append(
        "  a mechanic that makes a bar ambiguous drops exactly the trades that ran"
    )
    lines.append("  a full R and then stopped — losers that had been winners.")
    for _key, comparison in sorted(study.comparisons.items()):
        lines += _families(comparison)
    lines += _assessments(study)
    lines += ["", _THIN, "LIMITATIONS", _THIN]
    for item in study.limitations:
        lines.append(f"  * {item}")
    lines += [
        "",
        _RULE,
        "RESEARCH ONLY. No production trading policy changed. No order placed.",
        "No strategy adopted. The strongest verdict this repository can produce",
        "means WORTH TESTING FORWARD and nothing stronger.",
        _RULE,
        "",
    ]
    return "\n".join(lines)
