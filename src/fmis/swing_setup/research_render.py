"""Human-readable terminal report for one research study.

Renders exactly the numbers `fmis.swing_setup.research_metrics` and
`fmis.swing_setup.research_compare` produced — nothing is computed here,
matching every other renderer in this repository.

Three things are printed whether or not anyone asks for them, because each is a
question BB had to reconstruct by hand from a document that did not answer it:
the **four window boundaries** with the derived warm-up beside them, the
**concentration** of the sample, and the **post-filter versus replay**
difference. A report that states a target-first rate without stating that half
its outcomes fell in one week has told the reader the smaller half of the truth.
"""

from __future__ import annotations

import textwrap

from fmis.swing_setup.backtest_metrics import CohortCount, Percentiles
from fmis.swing_setup.research_metrics import (
    ConcentrationReport,
    ResearchMetrics,
    compute_research_metrics,
)
from fmis.swing_setup.research_models import (
    AvailabilityReport,
    PostFilterComparison,
    ResearchBacktestRun,
    VariantComparison,
)

__all__ = ["render_research_report", "render_availability_report"]

_WIDTH = 78
_ABSENT = "—"
_INSUFFICIENT = "INSUFFICIENT SAMPLE"


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _heading(title: str) -> list[str]:
    return [_rule("="), f" {title}", _rule("=")]


def _pct(value: float | None) -> str:
    return _INSUFFICIENT if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, *, digits: int = 2) -> str:
    return _ABSENT if value is None else f"{value:,.{digits}f}"


def _wrapped(statement: str, *, indent: str = " ") -> list[str]:
    return textwrap.wrap(
        statement, width=_WIDTH, initial_indent=indent, subsequent_indent=indent + "  "
    ) or [indent.rstrip()]


def _percentile_row(label: str, percentiles: Percentiles) -> list[str]:
    if percentiles.count == 0:
        return [f" {label} {_ABSENT} (n=0)"]
    return _wrapped(
        f"{label} p10={_num(percentiles.p10)} p25={_num(percentiles.p25)} "
        f"p50={_num(percentiles.p50)} p75={_num(percentiles.p75)} "
        f"p90={_num(percentiles.p90)} max={_num(percentiles.maximum)} "
        f"(n={percentiles.count})"
    )


def _cohort_rows(cohorts: tuple[CohortCount, ...]) -> list[str]:
    if not cohorts or all(cohort.total == 0 for cohort in cohorts):
        return [f" {_ABSENT}"]
    lines = [f" {'LABEL':<18} {'N':>5} {'TGT':>5} {'STOP':>5} {'AMB':>5} {'NEITHER':>8}"]
    for cohort in cohorts:
        if cohort.total == 0:
            continue
        lines.append(
            f" {cohort.label[:18]:<18} {cohort.total:>5} {cohort.target_first:>5} "
            f"{cohort.stop_first:>5} {cohort.ambiguous_same_bar:>5} "
            f"{cohort.neither_within_window:>8}"
        )
    return lines


def _window_section(run: ResearchBacktestRun) -> list[str]:
    window = run.window
    lines = ["", " WINDOW BOUNDARIES (all four, kept apart on purpose)", _rule()]
    lines.append(f" warm-up start     {window.warmup_start.isoformat()}")
    lines.append(
        f" measurement start {window.measurement_start.isoformat()}   "
        f"(+{window.warmup_duration.days}d of warm-up)"
    )
    lines.append(
        f" measurement end   {window.measurement_end.isoformat()}   "
        f"({window.measurement_duration.days}d measured, half-open)"
    )
    lines.append(
        f" outcome tail end  {window.outcome_tail_end.isoformat()}   "
        f"(+{window.tail_duration.days}d, resolution only)"
    )
    lines.append("")
    lines.append(" DERIVED WARM-UP, ROLE BY ROLE")
    lines.append(f" {'ROLE':<10} {'TF':<5} {'BARS':>6}  {'DURATION':<14} BINDING COMPONENT")
    for role in run.warmup.by_role:
        binding = max(role.components, key=lambda component: component.bars)
        lines.append(
            f" {role.role:<10} {role.interval:<5} {role.required_bars:>6}  "
            f"{str(role.duration.days) + 'd':<14} {binding.name}"
        )
    return lines


def _concentration_section(concentration: ConcentrationReport) -> list[str]:
    lines = ["", " SAMPLE CONCENTRATION (how much of this is one stretch of market)", _rule()]
    if concentration.total_outcomes == 0:
        lines.append(f" {_ABSENT} no evaluated outcome")
        return lines
    lines.extend(
        _wrapped(
            f"largest 5-day cluster: {concentration.largest_window_outcomes} of "
            f"{concentration.total_outcomes} outcomes "
            f"({_pct(concentration.largest_window_share)}), starting "
            f"{concentration.largest_window_start.date()}"
        )
    )
    lines.extend(
        _wrapped(
            f"largest single symbol: {concentration.largest_symbol} with "
            f"{concentration.largest_symbol_outcomes} "
            f"({_pct(concentration.largest_symbol_share)})"
        )
    )
    lines.append(f" distinct confirmation days: {concentration.distinct_days}")
    lines.append("")
    lines.append(" OUTCOMES BY MONTH")
    lines.extend(_cohort_rows(concentration.by_month))
    return lines


def _warmup_verification_rows(run: ResearchBacktestRun) -> list[str]:
    """What was measured about the warm-up, not what was argued about it."""
    metadata = run.metadata
    warming = metadata.get("measured_role_views_with_warming_features")
    short = metadata.get("measured_role_views_below_requested_window")
    minimums = metadata.get("minimum_closed_candles_by_role") or {}
    if warming is None or short is None:
        return []
    lines = _wrapped(
        f"warm-up verified per instant: {warming} role-view(s) still warming, "
        f"{short} below the requested window"
    )
    if minimums:
        lines.extend(
            _wrapped(
                "minimum closed candles seen at any measured instant: "
                + ", ".join(f"{role}={count:,}" for role, count in minimums.items())
                + f" (requested {metadata.get('candle_limit', '?')})"
            )
        )
    return lines


def _variant_section(run: ResearchBacktestRun, metrics: ResearchMetrics) -> list[str]:
    lines = ["", f" VARIANT {metrics.variant_id}  ({metrics.policy_id})", _rule()]
    lines.append(
        f" confirmation staleness bound applied: {metrics.effective_max_age} bar(s)"
    )
    lines.append(
        f" measured observations {metrics.measured_observations:,}  "
        f"(warm-up/priming, excluded: {metrics.warmup_observations:,})"
    )
    lines.append(
        f" WAIT {metrics.wait_count:,}   CANDIDATE {metrics.candidate_count:,}   "
        f"CONFIRMED {metrics.confirmed_count:,}"
    )
    lines.append(
        f" unique opportunities {metrics.unique_opportunities:,}   "
        f"confirmed opportunities {metrics.confirmed_opportunities:,}   "
        f"without geometry {metrics.confirmed_without_geometry:,}"
    )
    lines.append(f" evaluated outcomes {metrics.evaluated_outcomes:,}")
    lines.append(
        f"   TARGET_FIRST {metrics.target_first:,}   STOP_FIRST {metrics.stop_first:,}"
        f"   AMBIGUOUS {metrics.ambiguous_same_bar:,}"
        f"   UNRESOLVED {metrics.unresolved:,}"
    )
    lines.append(f" target-first rate {_pct(metrics.target_first_rate)}")
    lines.extend(_warmup_verification_rows(run))
    lines.extend(_percentile_row("R:R at confirmation", metrics.risk_reward_percentiles))
    lines.extend(
        _percentile_row("confirming break age (bars)", metrics.confirmation_age_percentiles)
    )
    if metrics.insufficient_data_measured_instants:
        lines.extend(
            _wrapped(
                "WARNING: "
                f"{metrics.insufficient_data_measured_instants:,} measured instant(s) "
                "raised InsufficientDataError — the derived warm-up did not hold "
                "for them and they produced no observation."
            )
        )
    lines.append("")
    lines.append(" OUTCOMES BY SYMBOL")
    lines.extend(_cohort_rows(metrics.by_symbol))
    lines.append("")
    lines.append(" OUTCOMES BY SIDE")
    lines.extend(_cohort_rows(metrics.by_side))
    lines.append("")
    lines.append(" OUTCOMES BY TEMPORAL SEGMENT")
    lines.extend(_cohort_rows(metrics.by_segment))
    lines.extend(
        _wrapped(
            "measured observations per segment: "
            + ", ".join(
                f"{label}={count:,}"
                for label, count in metrics.observations_by_segment.items()
            )
        )
    )
    lines.extend(_concentration_section(metrics.concentration))
    return lines


def _comparison_rows(comparisons: tuple[VariantComparison, ...]) -> list[str]:
    lines = ["", " VARIANT VS BASELINE — CONFIRMATION LINEAGE", _rule()]
    lines.append(
        f" {'VARIANT':<20} {'BASE':>6} {'VAR':>6} {'SAME':>6} {'LATER':>6} "
        f"{'EARLY':>6} {'LOST':>6} {'NEW':>5}"
    )
    for comparison in comparisons:
        lines.append(
            f" {comparison.variant_id[:20]:<20} {comparison.baseline_confirmations:>6} "
            f"{comparison.variant_confirmations:>6} {comparison.unchanged:>6} "
            f"{comparison.shifted_later:>6} {comparison.shifted_earlier:>6} "
            f"{comparison.removed:>6} {comparison.added:>5}"
        )
    lines.extend(
        _wrapped(
            "SAME = same opportunity confirmed at the same instant; LATER/EARLY = "
            "same opportunity, different instant; LOST = baseline confirmation "
            "the variant never made; NEW = variant confirmation with no baseline "
            "counterpart."
        )
    )
    return lines


def _post_filter_rows(comparisons: tuple[PostFilterComparison, ...]) -> list[str]:
    lines = ["", " POST-FILTER (BA's method) VS TRUE REPLAY (BC)", _rule()]
    lines.append(
        f" {'BOUND':>5} {'FILTERED':>9} {'REPLAYED':>9} {'BOTH':>6} "
        f"{'FILT-ONLY':>10} {'REPL-ONLY':>10} {'AGREE':>7}"
    )
    for comparison in comparisons:
        lines.append(
            f" {comparison.max_confirmation_age:>5} {comparison.post_filter_kept:>9} "
            f"{comparison.replay_confirmations:>9} {comparison.in_both:>6} "
            f"{comparison.only_in_post_filter:>10} {comparison.only_in_replay:>10} "
            f"{_pct(comparison.agreement_rate):>7}"
        )
    lines.extend(
        _wrapped(
            "REPL-ONLY is the population a post-filter cannot reach: a "
            "confirmation that exists only because a stricter bound deferred a "
            "candidate onto a later, fresher break."
        )
    )
    return lines


def render_availability_report(report: AvailabilityReport) -> str:
    """Print measured provider history per (symbol, interval), and any shortfall."""
    lines = _heading("FMITS RESEARCH — MEASURED HISTORICAL DATA AVAILABILITY")
    lines.append(f" probed at {report.probed_at.isoformat()}")
    lines.append("")
    lines.append(
        f" {'SYMBOL':<10} {'TF':<4} {'EARLIEST':<12} {'LATEST':<12} {'BARS':>6} {'OK':>4}"
    )
    for item in report.series:
        lines.append(
            f" {item.symbol:<10} {item.interval:<4} "
            f"{(item.earliest_open.date().isoformat() if item.earliest_open else _ABSENT):<12} "
            f"{(item.latest_open.date().isoformat() if item.latest_open else _ABSENT):<12} "
            f"{item.implied_candle_count:>6} "
            f"{'yes' if item.satisfies_window else 'NO':>4}"
        )
    lines.append("")
    if report.is_satisfiable:
        lines.append(" every requested (symbol, interval) satisfies the derived warm-up.")
    else:
        empty = [item for item in report.unsatisfied if item.earliest_open is None]
        measurable = [
            item.shortfall for item in report.unsatisfied if item.earliest_open is not None
        ]
        worst = (
            f"short by {max(measurable).days} day(s)"
            if measurable
            else "no candle at all"
        )
        lines.extend(
            _wrapped(
                f"{len(report.unsatisfied)} of {len(report.series)} series are "
                f"short; the worst is {worst}. The measurement window must start "
                "later, or a symbol must be dropped — it will not be silently "
                "shortened."
            )
        )
        if empty and measurable:
            lines.append(f" {len(empty)} series hold no candle at all.")
    lines.append(_rule("="))
    return "\n".join(lines)


def render_research_report(
    runs: tuple[ResearchBacktestRun, ...],
    comparisons: tuple[VariantComparison, ...] = (),
    post_filters: tuple[PostFilterComparison, ...] = (),
) -> str:
    """One page per variant, then the lineage and post-filter comparisons.

    ``runs[0]`` is treated as the baseline for the window/warm-up header — every
    run in a study shares them by construction.
    """
    if not runs:
        raise ValueError("at least one run is required")
    lines = _heading("FMITS SWING SETUP — CORRECTED RESEARCH REPLAY (MILESTONE BC)")
    lines.append(f" symbols   {', '.join(runs[0].symbols)}")
    lines.append(
        "  timeframes "
        + ", ".join(f"{role}={interval}" for role, interval in runs[0].timeframes.items())
    )
    lines.extend(_window_section(runs[0]))
    for run in runs:
        lines.extend(_variant_section(run, compute_research_metrics(run)))
    if comparisons:
        lines.extend(_comparison_rows(tuple(comparisons)))
    if post_filters:
        lines.extend(_post_filter_rows(tuple(post_filters)))
    lines.append("")
    lines.append(" LIMITATIONS")
    lines.append(_rule())
    for limitation in runs[0].limitations:
        lines.extend(_wrapped(limitation))
    lines.append(_rule("="))
    return "\n".join(lines)
