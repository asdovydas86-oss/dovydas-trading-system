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

from fmis.features.indicators.sources import VALID_SOURCES
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

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        closed = context.primary.closed()
        prices = [getattr(candle, self._source) for candle in closed.candles]
        available = len(prices)
        multiplier = 2.0 / (self._period + 1)

        base_metadata = {
            "period": self._period,
            "source": self._source,
            "multiplier": multiplier,
            "closed_candles_available": available,
            "warmup_bars": self._period,
            "formula": "EMA_t = (P_t - EMA_{t-1}) * (2 / (period + 1)) + EMA_{t-1}",
            "initialization": "seed EMA_0 = SMA of the first `period` source values",
            "provenance": "fmis.features.indicators.ema.ExponentialMovingAverage",
        }

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
        ema = sum(prices[: self._period]) / self._period
        for price in prices[self._period :]:
            ema = (price - ema) * multiplier + ema

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=ema,
            metadata={**base_metadata, "insufficient_data": False},
        )
