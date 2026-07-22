"""Moving Average Convergence Divergence (MACD) — Tier-1 indicator feature.

Plain-Python, auditable, no third-party TA library. Uses the shared ``ema_series``
helper so its EMA math is identical to the EMA feature (SMA seed, alpha =
2/(period+1), deterministic recursion).

Formulas:
    fast_ema[t]   = EMA(source prices, fast_period)[t]
    slow_ema[t]   = EMA(source prices, slow_period)[t]
    macd_line[t]  = fast_ema[t] - slow_ema[t]          (aligned time indices)
    signal_line   = EMA(macd_line series, signal_period)
    histogram     = macd_line - signal_line

Alignment: fast and slow EMAs seed at different points (slow later, since
slow > fast). The MACD line is defined only where both exist — from the slow
EMA's first index onward — so the fast series is sliced to that overlap before
subtracting.

Warm-up derivation (SMA-seeded EMAs), for N closed candles:
    - slow EMA yields its first value at candle index slow-1  -> N - slow + 1
      MACD-line values overall;
    - the signal EMA needs `signal_period` MACD-line values to seed;
    - therefore N - slow + 1 >= signal_period, i.e.
          required_candles = slow_period + signal_period - 1.
    For the 12/26/9 default: 26 + 9 - 1 = 34 candles.
    With exactly that many candles there are exactly `signal_period` MACD-line
    values, so the signal EMA equals their SMA seed (no recursion yet).

Output representation:
    A single feature returning an immutable mapping value
    {"macd_line", "signal_line", "histogram"} — the contract's FeatureValue
    already permits a Mapping (see fmis.features.types), so no contract change is
    needed. Insufficient data -> value is None.

Only closed candles are used (reproducibility); pure arithmetic (deterministic).
"""

from __future__ import annotations

from types import MappingProxyType

from fmis.features.indicators.ema_math import ema_series
from fmis.features.indicators.sources import VALID_SOURCES
from fmis.features.types import (
    BaseFeature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
)

__all__ = ["MovingAverageConvergenceDivergence"]


class MovingAverageConvergenceDivergence(BaseFeature):
    """MACD over a chosen price source, returning an immutable structured value.

    One instance = one (source, fast, slow, signal) tuple, exposed as a stable
    feature name (``macd_close_12_26_9``).
    """

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        source: str = "close",
    ) -> None:
        for label, value in (
            ("fast_period", fast_period),
            ("slow_period", slow_period),
            ("signal_period", signal_period),
        ):
            # Reject bool explicitly: bool is a subclass of int but not a period.
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{label} must be an int, got {type(value).__name__}")
            if value < 1:
                raise ValueError(f"{label} must be a positive integer, got {value}")
        if fast_period >= slow_period:
            raise ValueError(
                f"fast_period ({fast_period}) must be < slow_period ({slow_period})"
            )
        if source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

        self._fast = fast_period
        self._slow = slow_period
        self._signal = signal_period
        self._source = source
        self.name = f"macd_{source}_{fast_period}_{slow_period}_{signal_period}"

    @property
    def fast_period(self) -> int:
        return self._fast

    @property
    def slow_period(self) -> int:
        return self._slow

    @property
    def signal_period(self) -> int:
        return self._signal

    @property
    def source(self) -> str:
        return self._source

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        fast_ema = ema_series(prices, self._fast)
        slow_ema = ema_series(prices, self._slow)

        # Align on the overlap (both series end at the last candle); slow starts
        # later, so trim the head of the fast series to match slow's indices.
        fast_tail = fast_ema[self._slow - self._fast :]
        macd_line = [f - s for f, s in zip(fast_tail, slow_ema)]
        macd_values_available = len(macd_line)
        required_candles = self._slow + self._signal - 1

        base_metadata = {
            "source": self._source,
            "fast_period": self._fast,
            "slow_period": self._slow,
            "signal_period": self._signal,
            "method": "ema",
            "ema_initialization": "sma_seed",
            "closed_candles_available": available,
            "required_candles": required_candles,
            "macd_values_available": macd_values_available,
            "warmup_candles": required_candles,
            "output_representation": (
                "immutable mapping {macd_line, signal_line, histogram}"
            ),
            "provenance": (
                "fmis.features.indicators.macd.MovingAverageConvergenceDivergence"
            ),
        }

        if macd_values_available < self._signal:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={**base_metadata, "insufficient_data": True},
            )

        signal_line = ema_series(macd_line, self._signal)[-1]
        macd_value = macd_line[-1]
        histogram = macd_value - signal_line

        value = MappingProxyType(
            {
                "macd_line": macd_value,
                "signal_line": signal_line,
                "histogram": histogram,
            }
        )
        return FeatureResult(
            name=self.name,
            category=self.category,
            value=value,
            metadata={**base_metadata, "insufficient_data": False},
        )
