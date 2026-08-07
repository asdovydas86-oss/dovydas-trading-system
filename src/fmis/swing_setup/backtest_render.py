"""Human-readable terminal report for one `BacktestRun` and its `BacktestMetrics`.

Renders exactly the numbers `fmis.swing_setup.backtest_metrics.compute_metrics`
produced — nothing is computed here, matching every other renderer in this
repository. Limitations are always printed, in full, at the end of the page —
never left to a document the terminal reader is not looking at.
"""

from __future__ import annotations

import textwrap

from fmis.swing_setup.backtest_metrics import (
    AgreementCohortOutcomes,
    BacktestMetrics,
    CohortCount,
    PairAgreement,
    Percentiles,
)
from fmis.swing_setup.backtest_models import BacktestError, BacktestRun

__all__ = ["render_backtest_report"]

_WIDTH = 78
_ABSENT = "—"
_INSUFFICIENT = "INSUFFICIENT SAMPLE"


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _pct(value: float | None) -> str:
    return _INSUFFICIENT if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, *, digits: int = 2) -> str:
    return _ABSENT if value is None else f"{value:,.{digits}f}"


def _percentile_rows(label: str, percentiles: Percentiles) -> list[str]:
    if percentiles.count == 0:
        return [f" {label} {_ABSENT} (n=0)"]
    statement = (
        f"{label} p10={_num(percentiles.p10)} p25={_num(percentiles.p25)} "
        f"p50={_num(percentiles.p50)} p75={_num(percentiles.p75)} "
        f"p90={_num(percentiles.p90)} max={_num(percentiles.maximum)} "
        f"(n={percentiles.count})"
    )
    return textwrap.wrap(statement, width=_WIDTH, initial_indent=" ", subsequent_indent="   ")


def _cohort_rows(cohorts: tuple[CohortCount, ...]) -> list[str]:
    if not cohorts or all(c.total == 0 for c in cohorts):
        return [f" {_ABSENT}"]
    lines = [
        f" {'LABEL':<12} {'N':>5} {'TGT':>5} {'STOP':>5} {'AMBIG':>6} {'NEITHER':>8}"
    ]
    for cohort in cohorts:
        if cohort.total == 0:
            continue
        lines.append(
            f" {cohort.label:<12} {cohort.total:>5} {cohort.target_first:>5} "
            f"{cohort.stop_first:>5} {cohort.ambiguous_same_bar:>6} "
            f"{cohort.neither_within_window:>8}"
        )
    return lines


def _agreement_rows(cohorts: tuple[AgreementCohortOutcomes, ...]) -> list[str]:
    lines = [
        f" {'AGREEMENT':<14} {'N':>5} {'TGT':>5} {'STOP':>5} {'AMBIG':>6} {'NEITHER':>8}"
    ]
    for cohort in cohorts:
        lines.append(
            f" {cohort.label:<14} {cohort.total:>5} {cohort.target_first:>5} "
            f"{cohort.stop_first:>5} {cohort.ambiguous_same_bar:>6} "
            f"{cohort.neither_within_window:>8}"
        )
    return lines


def _pair_rows(pairs: tuple[PairAgreement, ...]) -> list[str]:
    if not pairs:
        return [f" {_ABSENT}"]
    lines = []
    for pair in pairs:
        statement = (
            f"{pair.family_a} <-> {pair.family_b}: agree {pair.agree}/"
            f"{pair.both_directional} ({_pct(pair.agreement_rate)})"
        )
        lines.extend(
            textwrap.wrap(statement, width=_WIDTH, initial_indent=" ", subsequent_indent="   ")
        )
    return lines


def render_backtest_report(run: BacktestRun, metrics: BacktestMetrics) -> str:
    """Render the deterministic backtest report described in the AV task brief.

    Raises:
        TypeError: ``run``/``metrics`` are not the expected types.
        BacktestError: a rendered line exceeded the page width — a defect in
            this module, raised rather than silently truncated further.
    """
    if not isinstance(run, BacktestRun):
        raise TypeError(f"run must be a BacktestRun, got {type(run).__name__}")
    if not isinstance(metrics, BacktestMetrics):
        raise TypeError(f"metrics must be a BacktestMetrics, got {type(metrics).__name__}")

    lines: list[str] = []
    lines.append(_rule("═"))
    lines.append(" FMITS SWING SETUP — HISTORICAL BACKTEST (measurement, not advice)")
    lines.append(_rule("═"))
    lines.append(f" Policy ............... {run.policy_id} / {run.context_policy_id}")
    lines.extend(
        textwrap.wrap(
            f"Symbols .............. {len(run.symbols)}: {', '.join(run.symbols)}",
            width=_WIDTH, initial_indent=" ", subsequent_indent="   ",
        )
    )
    tf = ", ".join(f"{role}={interval}" for role, interval in run.timeframes.items())
    lines.extend(
        textwrap.wrap(
            f"Timeframe roles ...... {tf}", width=_WIDTH,
            initial_indent=" ", subsequent_indent="   ",
        )
    )
    lines.append(f" Evaluation window .... {run.evaluation_window_bars} execution-role bars")
    lines.append(f" Created at ........... {run.created_at.isoformat()}")
    lines.append("")

    lines.append(_rule())
    lines.append(" BACKTEST SUMMARY")
    lines.append(_rule())
    lines.append(f" Total observations ...... {metrics.total_observations}")
    lines.append(f" WAIT ..................... {metrics.wait_count}")
    lines.append(f" CANDIDATE ................ {metrics.candidate_count}")
    lines.append(f" CONFIRMED ................ {metrics.confirmed_count}")
    lines.append(f" Unique setups ............ {metrics.unique_setups}")
    lines.append(f" Unique confirmed setups .. {metrics.unique_confirmed_setups}")
    lines.append(f" Evaluated outcomes ....... {metrics.evaluated_outcomes}")
    lines.append(
        f" Confirmed w/o geometry ... {metrics.confirmed_without_geometry} "
        "(no stop and/or target; not evaluated)"
    )
    lines.append(f" Target first ............. {metrics.target_first}")
    lines.append(f" Stop first ............... {metrics.stop_first}")
    lines.append(f" Ambiguous (same bar) ..... {metrics.ambiguous_same_bar}")
    lines.append(f" Neither within window .... {metrics.neither_within_window}")
    lines.append("")

    lines.append(_rule())
    lines.append(" TARGET-FIRST RATE (excludes ambiguous / unresolved)")
    lines.append(_rule())
    lines.append(f" target-first rate ... {_pct(metrics.target_first_rate)}")
    lines.append(f" stop-first rate ..... {_pct(metrics.stop_first_rate)}")
    lines.append(" This is a target-first rate, not a win rate: no fees, slippage,")
    lines.append(" spread or fill quality are modelled. See LIMITATIONS.")
    lines.append("")

    lines.append(_rule())
    lines.append(" BY SYMBOL")
    lines.append(_rule())
    lines.extend(_cohort_rows(metrics.by_symbol))
    lines.append("")

    lines.append(_rule())
    lines.append(" BY SIDE")
    lines.append(_rule())
    lines.extend(_cohort_rows(metrics.by_side))
    lines.append("")

    if metrics.by_month:
        lines.append(_rule())
        lines.append(" BY MONTH (confirmation month)")
        lines.append(_rule())
        lines.extend(_cohort_rows(metrics.by_month))
        lines.append("")

    lines.append(_rule())
    lines.append(" RR DISTRIBUTION (printed R:R at formation — not realized PnL)")
    lines.append(_rule())
    lines.append(f" mean ................. {_num(metrics.risk_reward_mean)}")
    lines.append(f" median ............... {_num(metrics.risk_reward_median)}")
    lines.extend(_percentile_rows("R:R percentiles", metrics.risk_reward_percentiles))
    lines.append("")

    lines.append(_rule())
    lines.append(" STOP/TARGET GEOMETRY AUDIT (fraction of reference price)")
    lines.append(_rule())
    lines.extend(_percentile_rows("risk fraction", metrics.risk_fraction_percentiles))
    lines.extend(_percentile_rows("reward fraction", metrics.reward_fraction_percentiles))
    lines.append("")

    lines.append(_rule())
    lines.append(" EVIDENCE-FAMILY COHORTS (independence / double-counting audit)")
    lines.append(_rule())
    lines.extend(_pair_rows(metrics.pair_agreement))
    lines.append(
        f" all 3 agree: {metrics.triple_agreement.all_agree}/"
        f"{metrics.triple_agreement.all_directional} "
        f"({_pct(metrics.triple_agreement.agreement_rate)})"
    )
    lines.append("")
    lines.extend(_agreement_rows(metrics.agreement_cohort_outcomes))
    lines.append("")

    lines.append(_rule())
    lines.append(" REGIME BEHAVIOUR")
    lines.append(_rule())
    total_structure = sum(metrics.structure_state_distribution.values())
    for state in sorted(metrics.structure_state_distribution):
        count = metrics.structure_state_distribution[state]
        share = count / total_structure if total_structure else 0.0
        lines.append(f" {state:<15} {count:>6}  ({share * 100:.1f}%)")
    lines.append(f" bar-to-bar regime change rate ... {_pct(metrics.regime_change_rate)}")
    lines.append(f" WAIT blocked only by regime ..... {metrics.blocked_only_by_regime}")
    lines.append("")

    lines.append(_rule("═"))
    lines.append(" DATA BOUNDARIES")
    lines.append(_rule("═"))
    for boundary in run.data_boundaries:
        first = boundary.first_candle.date().isoformat() if boundary.first_candle else _ABSENT
        last = boundary.last_candle.date().isoformat() if boundary.last_candle else _ABSENT
        lines.append(
            f" {boundary.symbol:<10} {boundary.interval:<4} {first} -> {last} "
            f"({boundary.candle_count} candles, {boundary.source})"
        )
    lines.append("")

    lines.append(_rule("═"))
    lines.append(" LIMITATIONS")
    lines.append(_rule("═"))
    for limitation in run.limitations:
        lines.extend(
            textwrap.wrap(
                limitation, width=_WIDTH, initial_indent=" - ", subsequent_indent="   "
            )
        )
    lines.append(_rule("═"))

    for line in lines:
        if len(line) > _WIDTH:
            raise BacktestError(
                f"rendered line of {len(line)} exceeds the {_WIDTH}-column page: {line!r}"
            )
    return "\n".join(lines)
