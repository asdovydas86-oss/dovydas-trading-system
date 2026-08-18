"""The Statistics & Performance Engine — does this system actually have an edge.

    fmits statistics
    fmits performance
    fmits expectancy
    fmits equity
    fmits trades summary

**A pure projection, and that is architectural rather than a simplification.**
`AP` §25.2 classes cohort statistics and bias metrics as `Aggregate` —
*recomputable, disposable*. So this package adds **no record kind, no repository
and no write path at all**: delete every figure it produces, run it again over
the same store, and the answers are identical. Nothing here can drift from the
records it is computed over, because nothing here is stored beside them.

**Every rate carries `n` and is refused below a stated floor.** `AP` §20.7 rule
2 requires that guard *"at the boundary, so no surface can route around it"*, and
`fmis.statistics.sampling` is that boundary: nothing else in the package
divides, averages or takes a median. Counts and totals are **not** floored — *"you
closed three trades and lost on all three"* is a fact at `n = 3`, and refusing
to state it would be a different dishonesty from overstating it.

**Two sources of trade, one vocabulary, and the difference is never hidden.** A
simulated trade carries an R multiple, an excursion and a bar count, all frozen
at close by `AP` §25.3. A trade the owner recorded by hand carries none of them,
because nothing froze them. Every statistic over those fields reports how many
of the corpus actually contributed, so eight simulated excursions can never
stand for twelve trades.

**The multiplicity hazard is a mechanism, not a paragraph.**
`TRADER_WORKSPACE` §3.4.12: with roughly twenty-five segmentations and no
correction, *"a new set of striking-looking cells will appear, and the defence is
a document, not a mechanism."* `BreakdownSet.cells_examined` counts every cell
produced across every dimension and every page prints it. This engine applies no
multiplicity correction and says so rather than implying there was nothing to
correct.

**What it does not do.** It estimates nothing, infers nothing, predicts nothing
and calibrates no probability. It fetches no candle — a statistic is computed
from recorded history, and re-deriving an excursion from today's kline history
would make a past figure depend on what the venue still serves. It ranks no
market and recommends no action. `calibrated_probability` (`AP` §20.6) remains
absent until earned, and this milestone does not earn it.
"""

from __future__ import annotations

from fmis.statistics.breakdown import (
    DEFAULT_REGIME_DIMENSION,
    DIMENSION_NAMES,
    DIMENSIONS,
    MULTIPLICITY_NOTE,
    Breakdown,
    BreakdownCell,
    BreakdownSet,
    cut_by,
    breakdown_set,
)
from fmis.statistics.collect import (
    COLLECT_DUST_POLICY,
    PHASE_OF_CAPTURE_STATUS,
    PHASE_OF_LIFECYCLE_STATE,
    CollectedTrades,
    CorpusUnreadableError,
    collect_trades,
    open_risk_limit,
    quote_assets_of,
    stat_from_paper,
    stat_from_recorded,
)
from fmis.statistics.distribution import (
    HISTOGRAM_KINDS,
    HOLDING_TIME_EDGES,
    R_MULTIPLE_EDGES,
    Bucket,
    Histogram,
    histogram_of,
)
from fmis.statistics.drawdown import (
    DRAWDOWN_BASIS,
    DrawdownCurve,
    DrawdownPeriod,
    drawdown_curve,
)
from fmis.statistics.equity import (
    EQUITY_BASIS,
    EquityCurve,
    EquityPoint,
    as_percentage,
    equity_curve,
)
from fmis.statistics.general import (
    GeneralStatistics,
    general_statistics,
    total_duration,
)
from fmis.statistics.inputs import (
    DEFAULT_STATISTICS_STORE_ROOT,
    NO_EQUITY_BASIS,
    NO_POINT_IN_TIME_CUT,
    NO_STARTING_EQUITY,
    STATISTICS_ERRORS,
    as_of_from_text,
    baseline_from_text,
    equity_from_text,
    policy_from_text,
    statistics_store_root,
)
from fmis.statistics.models import (
    DEFAULT_SAMPLE_POLICY,
    SAMPLE_FLOOR_BASIS,
    STATISTICS_LIMITATIONS,
    STATISTICS_POLICY_ID,
    STATISTICS_POLICY_VERSION,
    LifecyclePhase,
    SamplePolicy,
    StatisticsError,
    StatisticsRefusedError,
    StatSource,
    TradeResult,
    TradeStat,
)
from fmis.statistics.performance import (
    EXPECTANCY_BASIS,
    PROFIT_FACTOR_BASIS,
    PerformanceStatistics,
    performance_statistics,
)
from fmis.statistics.quality import (
    CAPTURE_BASIS,
    EXCURSION_BASIS,
    QualityStatistics,
    quality_statistics,
)
from fmis.statistics.render import (
    duration_text,
    render_equity,
    render_expectancy,
    render_performance,
    render_statistics,
    render_trades_summary,
)
from fmis.statistics.report import (
    STATISTICS_OBJECTIVE,
    AssetReport,
    StatisticsReport,
    build_report,
    closed_between,
    recent_trades,
    report_for_store,
)
from fmis.statistics.risk import (
    RISK_UTILIZATION_BASIS,
    RiskStatistics,
    risk_statistics,
    utilization_of,
)
from fmis.statistics.sampling import (
    Sample,
    Tally,
    collect_values,
    count_of,
    extremum_or_absent,
    mean_duration_or_absent,
    mean_or_absent,
    median_duration_or_absent,
    median_or_absent,
    ordered_values,
    ratio_or_absent,
    share_or_absent,
    total_or_absent,
)

__all__ = [
    # errors
    "StatisticsError",
    "StatisticsRefusedError",
    "CorpusUnreadableError",
    # the unit and the policy
    "StatSource",
    "TradeResult",
    "LifecyclePhase",
    "SamplePolicy",
    "DEFAULT_SAMPLE_POLICY",
    "SAMPLE_FLOOR_BASIS",
    "TradeStat",
    "STATISTICS_LIMITATIONS",
    "STATISTICS_POLICY_ID",
    "STATISTICS_POLICY_VERSION",
    # the sample guard
    "Tally",
    "Sample",
    "collect_values",
    "count_of",
    "total_or_absent",
    "mean_or_absent",
    "median_or_absent",
    "extremum_or_absent",
    "mean_duration_or_absent",
    "median_duration_or_absent",
    "ratio_or_absent",
    "share_or_absent",
    "ordered_values",
    # the four families
    "GeneralStatistics",
    "general_statistics",
    "total_duration",
    "PerformanceStatistics",
    "performance_statistics",
    "EXPECTANCY_BASIS",
    "PROFIT_FACTOR_BASIS",
    "RiskStatistics",
    "risk_statistics",
    "utilization_of",
    "RISK_UTILIZATION_BASIS",
    "QualityStatistics",
    "quality_statistics",
    "CAPTURE_BASIS",
    "EXCURSION_BASIS",
    # distributions
    "Bucket",
    "Histogram",
    "histogram_of",
    "R_MULTIPLE_EDGES",
    "HOLDING_TIME_EDGES",
    "HISTOGRAM_KINDS",
    # the curves
    "EquityPoint",
    "EquityCurve",
    "equity_curve",
    "as_percentage",
    "EQUITY_BASIS",
    "DrawdownPeriod",
    "DrawdownCurve",
    "drawdown_curve",
    "DRAWDOWN_BASIS",
    # the cuts
    "BreakdownCell",
    "Breakdown",
    "BreakdownSet",
    "cut_by",
    "breakdown_set",
    "DIMENSIONS",
    "DIMENSION_NAMES",
    "MULTIPLICITY_NOTE",
    "DEFAULT_REGIME_DIMENSION",
    # reading the store
    "CollectedTrades",
    "collect_trades",
    "stat_from_paper",
    "stat_from_recorded",
    "quote_assets_of",
    "open_risk_limit",
    "COLLECT_DUST_POLICY",
    "PHASE_OF_LIFECYCLE_STATE",
    "PHASE_OF_CAPTURE_STATUS",
    # composition
    "AssetReport",
    "StatisticsReport",
    "build_report",
    "report_for_store",
    "recent_trades",
    "closed_between",
    "STATISTICS_OBJECTIVE",
    # the text boundary
    "statistics_store_root",
    "policy_from_text",
    "equity_from_text",
    "as_of_from_text",
    "baseline_from_text",
    "NO_STARTING_EQUITY",
    "NO_EQUITY_BASIS",
    "NO_POINT_IN_TIME_CUT",
    "DEFAULT_STATISTICS_STORE_ROOT",
    "STATISTICS_ERRORS",
    # rendering
    "duration_text",
    "render_statistics",
    "render_performance",
    "render_expectancy",
    "render_equity",
    "render_trades_summary",
]
