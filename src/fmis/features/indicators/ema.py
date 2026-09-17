"""Exponential Moving Average (EMA) — the first Tier-1 indicator feature.

Plain-Python, auditable, no third-party TA library.

Formula:
    multiplier  k     = 2 / (period + 1)
    EMA_t             = (P_t - EMA_{t-1}) * k + EMA_{t-1}
                        (algebraically identical to  P_t * k + EMA_{t-1} * (1 - k))

Initialization convention (explicit and tested — never chosen silently):
    - P_t is the ``source`` price of the t-th **closed** candle (default: close).
    - The series is seeded with a Simple Moving Average of the first ``period``
      source values:  EMA_seed = mean(P_0 .. P_{period-1}).
    - The recursive step above is then applied to every remaining value.
    - Consequences of this convention, all asserted in the tests:
        * with exactly ``period`` closed candles, EMA == the seed SMA;
        * with ``period`` == 1, EMA == the most recent source value;
        * with fewer than ``period`` closed candles, the result is an explicit
          insufficient-data state (value is None), not a guessed number.

Only closed candles are used, so a still-forming bar can never change the value
(reproducibility). The calculation is pure arithmetic and therefore deterministic.
"""

from __future__ import annotations

from fmis.features.indicators.ema_math import ema_series
from fmis.features.indicators.sources import VALID_SOURCES
from fmis.features.series import FeatureSeries, FeatureSeriesPoint
from fmis.features.types import (
    BaseFeature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
)

__all__ = ["ExponentialMovingAverage"]


class ExponentialMovingAverage(BaseFeature):
    """EMA of a configurable period over a chosen price source.

    One instance = one (period, source) pair, exposed as a stable feature name
    (``ema_20`` for the close default, ``ema_20_high`` for another source).
    """

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(self, period: int, source: str = "close") -> None:
        # Reject bool explicitly: bool is a subclass of int but not a valid period.
        if isinstance(period, bool) or not isinstance(period, int):
            raise TypeError(f"period must be an int, got {type(period).__name__}")
        if period < 1:
            raise ValueError(f"period must be a positive integer, got {period}")
        if source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

        self._period = period
        self._source = source
        self.name = f"ema_{period}" if source == "close" else f"ema_{period}_{source}"

    @property
    def period(self) -> int:
        return self._period

    @property
    def source(self) -> str:
        return self._source

    def _base_metadata(self, available: int) -> dict[str, object]:
        """The parameters and provenance both output paths report.

        One dict builder rather than two literals, so `compute` and
        `compute_series` cannot describe the same calculation differently.
        """
        return {
            "period": self._period,
            "source": self._source,
            "multiplier": 2.0 / (self._period + 1),
            "closed_candles_available": available,
            "warmup_bars": self._period,
            "formula": "EMA_t = (P_t - EMA_{t-1}) * (2 / (period + 1)) + EMA_{t-1}",
            "initialization": "seed EMA_0 = SMA of the first `period` source values",
            "provenance": "fmis.features.indicators.ema.ExponentialMovingAverage",
        }

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        closed = context.primary.closed()
        prices = [getattr(candle, self._source) for candle in closed.candles]
        available = len(prices)
        base_metadata = self._base_metadata(available)

        if available < self._period:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={
                    **base_metadata,
                    "insufficient_data": True,
                    "required": self._period,
                },
            )

        # Seed with the SMA of the first `period` values, then smooth the rest.
        # Delegates to the shared ema_series helper (single source of EMA math),
        # which is the same call `compute_series` makes — so the latest value and
        # the final point of the history are one number, not two that agree.
        ema = ema_series(prices, self._period)[-1]

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=ema,
            metadata={**base_metadata, "insufficient_data": False},
        )

    def compute_series(self, context: FeatureContext) -> FeatureSeries:
        """This EMA at every closed candle where it is defined (ADR-0031).

        ``ema_series`` has always computed the whole history; before this method
        existed, `compute` kept ``[-1]`` and the rest was discarded. Nothing new
        is calculated here — the same call is made and all of it is published.

        Alignment: element ``k`` of the shared series describes closed candle
        ``k + period - 1``, so the first point sits at index ``period - 1`` and
        ``warmup_candles`` is ``period``.
        """
        closed = context.primary.closed()
        candles = closed.candles
        prices = [getattr(candle, self._source) for candle in candles]
        available = len(prices)

        values = ema_series(prices, self._period)
        points = tuple(
            FeatureSeriesPoint(
                index=offset + self._period - 1,
                timestamp=candles[offset + self._period - 1].timestamp,
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
            warmup_candles=self._period,
            points=points,
            metadata=self._base_metadata(available),
        )
