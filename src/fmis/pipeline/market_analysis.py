"""Market Analysis Pipeline v1 — real candles to a structured analysis snapshot.

One workflow, `analyze_symbol`, connecting components that already exist:

    fmis.providers.binance.fetch_klines      public candles -> CandleSeries
    CandleSeries.closed()                    explicit closed-candle selection
    fmis.features.FeatureEngine              existing technical features
    fmis.data.candle_series_to_observations  candles -> ObservationSeries
    fmis.alignment.align_intersection        strict timestamp intersection
    fmis.relative_value                      the five existing v1a metrics

**No calculation is defined here.** Every number in an `AnalysisSnapshot` is
produced by one of the modules above; this module decides only what to call, in
what order, and how to report what happened. A test asserts the module contains
no arithmetic operator of its own.

Data policy:
  * **Closed candles only, always.** The forming candle is excluded before any
    calculation — not by default, but unconditionally, because a snapshot
    computed over a forming bar is not reproducible. `DataWindow` reports how
    many candles were fetched, how many were closed, and how many were excluded,
    so the exclusion is visible rather than implied.
  * **Warm-up is a result, not a failure.** An indicator without enough history
    returns `value=None` with its warm-up metadata — the documented Feature
    Engine behaviour. The snapshot carries it unchanged.
  * **Nothing partial.** Too few candles to analyse at all raises
    `InsufficientDataError`. If a benchmark comparison was requested and cannot
    be computed, the underlying error propagates rather than yielding a
    technical-only snapshot that silently drops what was asked for.

Fact-only: a snapshot restates measurements and provenance. It contains no
direction, score, ranking, confidence, label, or recommendation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable

from fmis.alignment import AlignmentReport, align_intersection
from fmis.data import CandleField, CandleSeries, candle_series_to_observations
from fmis.features import FeatureRegistry, FeatureSet
from fmis.features.feature_engine import FeatureEngine
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.macd import MovingAverageConvergenceDivergence
from fmis.features.indicators.rsi import RelativeStrengthIndex
from fmis.features.types import Feature
from fmis.providers.binance import Transport, fetch_klines
from fmis.relative_value import (
    RelativeValueResult,
    pearson_correlation,
    period_return,
    realized_volatility,
    relative_return,
    volatility_ratio,
)

__all__ = [
    "analyze_symbol",
    "default_features",
    "AnalysisSnapshot",
    "DataWindow",
    "RelativeValueSection",
    "PipelineError",
    "InsufficientDataError",
]

#: Minimum closed candles for a benchmark comparison. The strictest v1a metric
#: (`realized_volatility`, and so `volatility_ratio`/`pearson_correlation`) needs
#: three observations; checking here turns an obscure downstream error into a
#: clear one naming the actual shortfall.
_MIN_ALIGNED_OBSERVATIONS = 3


class PipelineError(Exception):
    """Base class for failures raised by the pipeline itself.

    Errors from the layers below — `BinanceError`, `IngestError`, feature-engine
    `ValueError`, alignment errors, `RelativeValueError` — are **not** wrapped.
    They are already precise, and re-wrapping would hide which stage failed.
    """


class InsufficientDataError(PipelineError, ValueError):
    """Not enough closed candles to perform the requested analysis.

    ``fetched``/``closed``/``required`` describe the shortfall, and ``subject``
    names which series was short (the symbol, or the aligned pair).
    """

    def __init__(
        self, *, subject: str, required: int, fetched: int, closed: int
    ) -> None:
        self.subject = subject
        self.required = required
        self.fetched = fetched
        self.closed = closed
        super().__init__(
            f"{subject}: need at least {required} closed candle(s), got {closed} "
            f"(fetched {fetched})"
        )


@dataclass(frozen=True, slots=True)
class DataWindow:
    """Factual description of the candles an analysis was computed over.

    ``first_timestamp``/``last_timestamp`` describe the **closed** candles used,
    and are ``None`` only for an empty window. ``excluded_forming_count`` is the
    difference between what the provider returned and what was analysed.
    """

    fetched_count: int
    closed_count: int
    excluded_forming_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class RelativeValueSection:
    """Benchmark comparison: the v1a metrics plus the alignment that enabled them.

    ``metrics`` maps a metric key to the `RelativeValueResult` the RVE returned,
    unchanged. ``alignment`` is the `AlignmentReport` from the intersection, so
    how much of each series survived alignment is auditable.
    """

    benchmark_symbol: str
    metrics: Mapping[str, RelativeValueResult]
    alignment: AlignmentReport
    benchmark_window: DataWindow

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, MappingProxyType):
            object.__setattr__(
                self, "metrics", MappingProxyType(dict(self.metrics))
            )


@dataclass(frozen=True, slots=True)
class AnalysisSnapshot:
    """One deterministic, fact-only analysis of one symbol at one point in time.

    ``as_of`` is the timestamp of the last closed candle analysed — never the
    wall clock. ``relative_value`` is present only when a benchmark was supplied.
    ``metadata`` records request provenance (the requested limit and window, the
    feature names run); it is defensively copied into an immutable mapping.
    """

    symbol: str
    interval: str
    as_of: datetime
    window: DataWindow
    features: FeatureSet
    benchmark_symbol: str | None = None
    relative_value: RelativeValueSection | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(
                self, "metadata", MappingProxyType(dict(self.metadata))
            )


def default_features() -> tuple[Feature, ...]:
    """The default technical feature set — existing indicators, standard periods.

    EMA(20), EMA(50), RSI(14), ATR(14), and MACD(12, 26, 9): every Tier-1
    indicator implemented today, at its conventional period. A fresh tuple is
    returned per call so no feature instance is shared between analyses.

    Pass an explicit ``features`` sequence to `analyze_symbol` to choose others;
    adding a *new* indicator means adding it to `fmis.features`, never here.
    """
    return (
        ExponentialMovingAverage(20),
        ExponentialMovingAverage(50),
        RelativeStrengthIndex(14),
        AverageTrueRange(14),
        MovingAverageConvergenceDivergence(),
    )


def _window_of(fetched: CandleSeries, closed: CandleSeries) -> DataWindow:
    candles = closed.candles
    return DataWindow(
        fetched_count=len(fetched.candles),
        closed_count=len(candles),
        excluded_forming_count=len(fetched.candles) - len(candles),
        first_timestamp=candles[0].timestamp if candles else None,
        last_timestamp=candles[-1].timestamp if candles else None,
    )


def _fetch_closed(
    symbol: str,
    interval: str,
    *,
    limit: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
    transport: Transport | None,
    clock: Callable[[], datetime] | None,
    base_url: str | None,
    required: int,
) -> tuple[CandleSeries, DataWindow]:
    """Fetch, drop the forming candle, and require a minimum of closed candles."""
    kwargs: dict[str, Any] = {
        "limit": limit,
        "start_time": start_time,
        "end_time": end_time,
        "transport": transport,
        "clock": clock,
    }
    if base_url is not None:
        kwargs["base_url"] = base_url

    fetched = fetch_klines(symbol, interval, **kwargs)
    closed = fetched.closed()
    window = _window_of(fetched, closed)
    if window.closed_count < required:
        raise InsufficientDataError(
            subject=symbol,
            required=required,
            fetched=window.fetched_count,
            closed=window.closed_count,
        )
    return closed, window


def _compare(
    primary: CandleSeries, benchmark: CandleSeries
) -> tuple[dict[str, RelativeValueResult], AlignmentReport]:
    """Align close-price series and run the five existing v1a metrics.

    No formula is defined here: each value is whatever `fmis.relative_value`
    returned, including an UNDEFINED result, which is passed through unchanged.
    """
    primary_obs = candle_series_to_observations(primary, CandleField.CLOSE)
    benchmark_obs = candle_series_to_observations(benchmark, CandleField.CLOSE)

    aligned = align_intersection((primary_obs, benchmark_obs))
    left, right = aligned.series

    if aligned.report.aligned_observation_count < _MIN_ALIGNED_OBSERVATIONS:
        raise InsufficientDataError(
            subject=f"{primary.symbol} vs {benchmark.symbol} (aligned)",
            required=_MIN_ALIGNED_OBSERVATIONS,
            fetched=len(primary_obs.timestamps),
            closed=aligned.report.aligned_observation_count,
        )

    metrics = {
        "relative_return": relative_return(left, right),
        "volatility_ratio": volatility_ratio(left, right),
        "pearson_correlation": pearson_correlation(left, right),
        "period_return_primary": period_return(left),
        "period_return_benchmark": period_return(right),
        "realized_volatility_primary": realized_volatility(left),
        "realized_volatility_benchmark": realized_volatility(right),
    }
    return metrics, aligned.report


def analyze_symbol(
    symbol: str,
    interval: str,
    *,
    limit: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    benchmark_symbol: str | None = None,
    features: Sequence[Feature] | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> AnalysisSnapshot:
    """Fetch candles, compute technical features, and optionally compare a benchmark.

    Args:
        symbol: exact provider symbol, e.g. ``"BTCUSDT"``.
        interval: provider interval, e.g. ``"4h"``.
        limit, start_time, end_time: passed to the provider unchanged; the same
            window is requested for the benchmark so the two are comparable.
        benchmark_symbol: when given, a second symbol is fetched and the five v1a
            relative-value metrics are computed against it.
        features: technical features to run. Defaults to `default_features()`.
        transport, clock, base_url: injection points forwarded to the provider,
            making a call deterministic and network-free.

    Returns:
        An `AnalysisSnapshot` over **closed candles only**, stamped ``as_of`` the
        last closed candle.

    Raises:
        InsufficientDataError: no closed candles for a series, or fewer than three
            aligned observations for a requested comparison.
        BinanceError / IngestError / ValueError / RelativeValueError: raised
            unwrapped by the provider, ingestion boundary, feature engine,
            alignment, or RVE. Nothing is swallowed and no partial snapshot is
            returned: if a benchmark comparison was requested and fails, the whole
            call fails.
    """
    selected = tuple(default_features() if features is None else features)

    primary, window = _fetch_closed(
        symbol,
        interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        transport=transport,
        clock=clock,
        base_url=base_url,
        required=1,
    )

    registry = FeatureRegistry()
    for feature in selected:
        registry.register(feature)
    feature_set = FeatureEngine(registry).compute(primary)

    section: RelativeValueSection | None = None
    if benchmark_symbol is not None:
        benchmark, benchmark_window = _fetch_closed(
            benchmark_symbol,
            interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            transport=transport,
            clock=clock,
            base_url=base_url,
            required=1,
        )
        metrics, report = _compare(primary, benchmark)
        section = RelativeValueSection(
            benchmark_symbol=benchmark_symbol,
            metrics=metrics,
            alignment=report,
            benchmark_window=benchmark_window,
        )

    return AnalysisSnapshot(
        symbol=symbol,
        interval=interval,
        as_of=feature_set.as_of,
        window=window,
        features=feature_set,
        benchmark_symbol=benchmark_symbol,
        relative_value=section,
        metadata={
            "requested_limit": limit,
            "requested_start_time": start_time,
            "requested_end_time": end_time,
            "feature_names": tuple(f.name for f in selected),
            "candle_policy": "closed_only",
            "relative_value_source_field": CandleField.CLOSE.value,
        },
    )
