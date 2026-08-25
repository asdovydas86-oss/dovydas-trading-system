"""Terminal report for one lab study. **Renders what was measured, computes nothing.**

Every number printed here came off a `VariantMetrics`, a `GateImpact` or a
`LabManifest`. This module holds no arithmetic beyond formatting a `Decimal` and
laying out a column, matching every other renderer in this repository.

Four things print whether or not anyone asks, because each is a way a
comparison table can mislead a reader who trusts it:

* **`n` beside every rate**, so a 12-trade cohort never sits beside a 200-trade
  one looking equally settled;
* **the control row**, so a reader can see for themselves that the override
  mechanism reproduced production before believing anything it measured;
* **the gate's two block counts**, separated — the raw one and the one that
  actually removed a setup;
* **the limitations**, in full, at the end. They are not an appendix: BW-2,
  BW-4 and BW-7 each change what the table above is allowed to mean.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal

from fmis.swing_lab.gate import GateImpact
from fmis.swing_lab.metrics import LabMeasure, VariantMetrics
from fmis.swing_lab.robustness import RobustnessReading
from fmis.swing_lab.study import LabStudy

__all__ = [
    "render_study",
    "render_comparison_table",
    "render_gate_impact",
    "render_robustness",
]

_WIDTH = 84
_ABSENT = "—"


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _heading(title: str) -> list[str]:
    return [_rule("="), f" {title}", _rule("=")]


def _decimal(value: Decimal | None, places: int = 3) -> str:
    if value is None:
        return _ABSENT
    return f"{float(value):+.{places}f}"


def _measure(measure: LabMeasure, places: int = 3) -> str:
    """A figure with its sample welded on, or the reason it is absent.

    ``n`` prints in both cases. A reader looking at a blank cell needs to know
    whether the cohort was empty or merely thin, and the count is the only
    thing that answers it.
    """
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{_decimal(measure.value, places)} (n={measure.n})"


def _rate(measure: LabMeasure) -> str:
    if measure.value is None:
        return f"{_ABSENT} (n={measure.n})"
    return f"{float(measure.value) * 100:5.1f}% (n={measure.n})"


def render_comparison_table(
    metrics: tuple[VariantMetrics, ...], *, titles: dict[str, str] | None = None
) -> str:
    """The variant comparison the brief asks for, one column per variant."""
    if not metrics:
        return "No variant produced a result."
    labels = [item.label for item in metrics]
    width = max(22, *(len(label) for label in labels)) + 2
    rows: list[tuple[str, list[str]]] = [
        ("Trades", [str(item.trades) for item in metrics]),
        ("Measurable", [str(item.measurable_trades) for item in metrics]),
        ("Ambiguous", [str(item.ambiguous_trades) for item in metrics]),
        ("Wins / losses", [f"{item.wins}/{item.losses}" for item in metrics]),
        ("Win rate", [_rate(item.win_rate) for item in metrics]),
        ("Expectancy (R)", [_measure(item.expectancy_r) for item in metrics]),
        ("Median R", [_measure(item.median_r) for item in metrics]),
        ("Profit factor", [_measure(item.profit_factor, 2) for item in metrics]),
        ("Total R", [_decimal(item.total_r, 2) for item in metrics]),
        (
            "Max drawdown (R)",
            [_decimal(-item.max_drawdown.max_drawdown_r, 2) for item in metrics],
        ),
        ("Avg MFE (R)", [_measure(item.average_mfe_r, 2) for item in metrics]),
        ("Avg MAE (R)", [_measure(item.average_mae_r, 2) for item in metrics]),
        ("Avg bars held", [_measure(item.average_bars_held, 1) for item in metrics]),
    ]
    lines = ["".ljust(20) + "".join(label.ljust(width) for label in labels)]
    lines.append(_rule("─"))
    for name, values in rows:
        lines.append(name.ljust(20) + "".join(value.ljust(width) for value in values))
    return "\n".join(lines)


def render_gate_impact(gate: GateImpact) -> str:
    """What the context-role gate did, with the two block counts kept apart."""
    lines = _heading("THE 1W GATE")
    reached = gate.instants - gate.not_reached
    lines.extend(
        [
            f"Instants judged                     {gate.instants}",
            f"  gate never reached (insufficient) {gate.not_reached}",
            f"  gate reached                      {reached}",
            "",
            f"Allowed (weekly regime TRENDING)    {gate.allowed}",
            f"Blocked, total                      {gate.blocked}"
            + (
                ""
                if gate.block_rate is None
                else f"   ({float(gate.block_rate) * 100:.1f}% of reached)"
            ),
            f"  ...with nothing to block          {gate.blocked_without_effect}",
            f"  ...removing a CANDIDATE           {gate.blocked_candidate}",
            f"  ...removing a CONFIRMED setup     {gate.blocked_confirmed}",
            f"Materially blocked                  {gate.materially_blocked}"
            + (
                ""
                if gate.material_block_rate is None
                else f"   ({float(gate.material_block_rate) * 100:.1f}% of reached)"
            ),
            f"  blocked LONG / SHORT              {gate.blocked_long}/{gate.blocked_short}",
        ]
    )
    lines.append("")
    lines.extend(textwrap.wrap(gate.counterfactual_note, _WIDTH))
    if gate.counterfactual is not None:
        lines.append("")
        lines.append("Trades the gate removed, measured through the same rules:")
        lines.append(render_comparison_table((gate.counterfactual,)))
    return "\n".join(lines)


def render_robustness(reading: RobustnessReading) -> str:
    """Every split for one variant, with cohort agreement stated rather than implied."""
    lines = _heading(f"ROBUSTNESS — {reading.variant_id}")
    for name, share in (
        ("Largest symbol share of gross R", reading.largest_symbol_share),
        ("Largest segment share of gross R", reading.largest_segment_share),
    ):
        lines.append(
            f"{name:34s} "
            + (_ABSENT if share is None else f"{float(share) * 100:.1f}%")
        )
    for split in reading.splits:
        lines.append("")
        lines.append(f"── {split.name} " + "─" * max(0, _WIDTH - len(split.name) - 4))
        lines.extend(textwrap.wrap(split.question, _WIDTH))
        agree = split.all_cohorts_agree_on_sign
        lines.append(
            "Cohorts agree on sign: "
            + (
                "not testable (fewer than two reportable cohorts)"
                if agree is None
                else ("yes" if agree else "NO — the result reverses across cohorts")
            )
        )
        lines.append(render_comparison_table(split.cohorts))
    return "\n".join(lines)


def render_study(study: LabStudy) -> str:
    """The whole report: what was run, what each variant did, and what it may mean."""
    manifest = study.manifest
    lines = _heading(f"SWING LAB — {manifest.experiment_id}")
    lines.extend(
        [
            f"Symbols            {', '.join(manifest.symbols)}",
            f"Measurement window {manifest.measurement_start.date()} → "
            f"{manifest.measurement_end.date()}",
            f"Warm-up from       {manifest.warmup_start.date()}  "
            f"(derived, fetched before the window)",
            f"Outcome tail to    {manifest.outcome_tail_end.date()}",
            f"Interval groups    "
            + "; ".join("/".join(group) for group in manifest.interval_groups),
            f"Evaluation window  {manifest.evaluation_window_bars} execution bars",
            f"Cost policy        {study.costs.basis}",
            f"Result digest      {manifest.result_digest}",
            "",
            _rule("─"),
            " VARIANT COMPARISON",
            _rule("─"),
        ]
    )
    lines.append(
        render_comparison_table(tuple(result.metrics for result in study.results))
    )
    lines.append("")
    for result in study.results:
        lines.append(f"  {result.variant.variant_id} — {result.variant.title}")
        lines.extend(
            textwrap.wrap(result.variant.hypothesis, _WIDTH - 4, initial_indent="    ",
                          subsequent_indent="    ")
        )
        lines.append(f"    policy_id: {result.variant.policy_id}")
        lines.append("")
    lines.append(render_gate_impact(study.gate))
    lines.append("")
    lines.extend(_heading("LIMITATIONS"))
    for item in manifest.limitations:
        lines.extend(textwrap.wrap(item, _WIDTH, subsequent_indent="      "))
    lines.append("")
    lines.extend(
        textwrap.wrap(
            "NOTHING HERE IS A PROMOTION. A variant that measures well is a "
            "candidate for forward testing and nothing more; the production "
            "strategy is unchanged by this run and cannot be changed by it.",
            _WIDTH,
        )
    )
    return "\n".join(lines)
