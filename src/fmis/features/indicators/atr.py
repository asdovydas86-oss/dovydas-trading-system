"""Average True Range (ATR), Wilder's method — second Tier-1 indicator feature.

Plain-Python, auditable, no third-party TA library. Mirrors the EMA feature's
structure and honours the same closed-candles-only / deterministic contract.

True Range (needs the previous candle's close):
    TR_t = max(high_t - low_t,
               abs(high_t - close_{t-1}),
               abs(low_t  - close_{t-1}))

Because TR needs a previous close, it is defined from the *second* closed candle
onward. With N closed candles there are N-1 true ranges.

Initialization convention (explicit and tested — never chosen silently):
    - first ATR = SMA of the first `period` true ranges (Wilder's seed);
    - subsequent values use Wilder smoothing:
          ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period
    - at least `period + 1` closed candles are required (to yield `period` true
      ranges); with fewer, the result is an explicit insufficient-data state
      (value is None), not a guessed number.

Only closed candles are used, so a still-forming bar can never change the value
(reproducibility). The calculation is pure arithmetic and therefore deterministic.
"""

from __future__ import annotations

from fmis.features.indicators.atr_math import atr_from_ranges, true_ranges
from fmis.features.series import FeatureSeries, FeatureSeriesPoint
from fmis.features.types import (
    BaseFeature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
)

__all__ = ["AverageTrueRange"]


class AverageTrueRange(BaseFeature):
    """Wilder ATR of a configurable period over a CandleSeries.

    One instance = one period, exposed as a stable feature name (``atr_14``).
    """

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(self, period: int = 14) -> None:
        # Reject bool explicitly: bool is a subclass of int but not a valid period.
        if isinstance(period, bool) or not isinstance(period, int):
            raise TypeError(f"period must be an int, got {type(period).__name__}")
        if period < 1:
            raise ValueError(f"period must be a positive integer, got {period}")

        self._period = period
        self.name = f"atr_{period}"

    @property
    def period(self) -> int:
        return self._period

    def _base_metadata(self, available: int, ranges_available: int) -> dict[str, object]:
        """The parameters and provenance both output paths report.

        One dict builder rather than two literals, so `compute` and
        `compute_series` cannot describe the same calculation differently.
        """
        return {
            "period": self._period,
            "method": "wilder",
            "closed_candles_available": available,
            "true_ranges_available": ranges_available,
            "warmup_candles": self._period + 1,
            "true_range_formula": (
                "TR = max(high - low, abs(high - prev_close), abs(low - prev_close))"
            ),
            "initialization": (
                "seed ATR = SMA of the first `period` true ranges; then Wilder "
                "smoothing ATR_i = (ATR_{i-1} * (period - 1) + TR_i) / period"
            ),
            "provenance": "fmis.features.indicators.atr.AverageTrueRange",
        }

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)

        # The true ranges and the Wilder smoothing both come from `atr_math`,
        # which is the same arithmetic `compute_series` runs — so the latest
        # value and the final point of the history are one number, not two that
        # agree (ADR-0031 §6).
        ranges = true_ranges(candles)
        base_metadata = self._base_metadata(available, len(ranges))

        if len(ranges) < self._period:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={
                    **base_metadata,
                    "insufficient_data": True,
                    "required_candles": self._period + 1,
                },
            )

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=atr_from_ranges(ranges, self._period)[-1],
            metadata={**base_metadata, "insufficient_data": False},
        )

    def compute_series(self, context: FeatureContext) -> FeatureSeries:
        """This ATR at every closed candle where it is defined (ADR-0031).

        Alignment: a true range needs a previous close, so element ``k`` of the
        smoothed series describes closed candle ``k + period`` — the fifteenth
        bar for the default period of 14, matching the ``warmup_candles`` of
        ``period + 1`` this feature has always reported.
        """
        closed = context.primary.closed()
        candles = closed.candles
        available = len(candles)

        ranges = true_ranges(candles)
        values = atr_from_ranges(ranges, self._period)
        points = tuple(
            FeatureSeriesPoint(
                index=offset + self._period,
                timestamp=candles[offset + self._period].timestamp,
                value=value,
            )
            for offset, value in enumerate(values)
        )
        return FeatureSeries(
            name=self.name,
            category=self.category,
            identity=closed.identity,
            as_of=candles[-1].timestamp if candles else None,
            closed_candles=available,
            warmup_candles=self._period + 1,
            points=points,
            metadata=self._base_metadata(available, len(ranges)),
        )
