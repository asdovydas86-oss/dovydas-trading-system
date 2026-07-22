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

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)

        true_ranges: list[float] = []
        for i in range(1, available):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close
            true_ranges.append(
                max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close),
                )
            )

        base_metadata = {
            "period": self._period,
            "method": "wilder",
            "closed_candles_available": available,
            "true_ranges_available": len(true_ranges),
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

        if len(true_ranges) < self._period:
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

        # Wilder seed = SMA of the first `period` true ranges, then smooth the rest.
        atr = sum(true_ranges[: self._period]) / self._period
        for tr in true_ranges[self._period :]:
            atr = (atr * (self._period - 1) + tr) / self._period

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=atr,
            metadata={**base_metadata, "insufficient_data": False},
        )
