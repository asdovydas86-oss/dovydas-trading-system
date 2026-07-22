"""Relative Strength Index (RSI), Wilder's method — third Tier-1 indicator.

Plain-Python, auditable, no third-party TA library. Mirrors the EMA/ATR features'
structure and honours the same closed-candles-only / deterministic contract.

Price changes (between consecutive `source` values of closed candles):
    change_t = P_t - P_{t-1}
    gain_t   = max(change_t, 0)
    loss_t   = max(-change_t, 0)

Because RSI needs differences, N closed candles yield N-1 changes, so at least
`period + 1` closed candles are required.

Initialization convention (explicit and tested — never chosen silently):
    - first average gain = SMA of the first `period` gains
    - first average loss = SMA of the first `period` losses
    - subsequent values use Wilder smoothing (for gain and loss independently):
          avg_i = (avg_{i-1} * (period - 1) + value_i) / period

RSI, with explicit zero-gain/zero-loss policy:
    - avg_loss == 0 and avg_gain  > 0 -> RSI = 100.0
    - avg_gain == 0 and avg_loss  > 0 -> RSI = 0.0
    - avg_gain == 0 and avg_loss == 0 -> RSI = 50.0  (flat: neither strength)
    - otherwise: RS = avg_gain / avg_loss ; RSI = 100 - (100 / (1 + RS))

Only closed candles are used (reproducibility); pure arithmetic (deterministic).
"""

from __future__ import annotations

from fmis.features.indicators.sources import VALID_SOURCES
from fmis.features.types import (
    BaseFeature,
    FeatureCategory,
    FeatureContext,
    FeatureResult,
)

__all__ = ["RelativeStrengthIndex"]


class RelativeStrengthIndex(BaseFeature):
    """Wilder RSI of a configurable period over a chosen price source.

    One instance = one (source, period) pair, exposed as a stable feature name
    (``rsi_close_14``).
    """

    category = FeatureCategory.INDICATOR
    dependencies: tuple[str, ...] = ()

    def __init__(self, period: int = 14, source: str = "close") -> None:
        # Reject bool explicitly: bool is a subclass of int but not a valid period.
        if isinstance(period, bool) or not isinstance(period, int):
            raise TypeError(f"period must be an int, got {type(period).__name__}")
        if period < 1:
            raise ValueError(f"period must be a positive integer, got {period}")
        if source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

        self._period = period
        self._source = source
        self.name = f"rsi_{source}_{period}"

    @property
    def period(self) -> int:
        return self._period

    @property
    def source(self) -> str:
        return self._source

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        gains: list[float] = []
        losses: list[float] = []
        for i in range(1, available):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, 0.0))
            losses.append(max(-change, 0.0))
        changes_available = len(gains)

        base_metadata = {
            "period": self._period,
            "source": self._source,
            "method": "wilder",
            "closed_candles_available": available,
            "changes_available": changes_available,
            "warmup_candles": self._period + 1,
            "initialization": (
                "seed avg gain/loss = SMA of the first `period` gains/losses; "
                "then Wilder smoothing avg_i = (avg_{i-1}*(period-1) + value_i)/period"
            ),
            "zero_gain_zero_loss_policy": (
                "avg_loss==0 & avg_gain>0 -> 100; avg_gain==0 & avg_loss>0 -> 0; "
                "both 0 -> 50"
            ),
            "provenance": "fmis.features.indicators.rsi.RelativeStrengthIndex",
        }

        if changes_available < self._period:
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

        # Wilder seed = SMA of the first `period` gains/losses, then smooth the rest.
        avg_gain = sum(gains[: self._period]) / self._period
        avg_loss = sum(losses[: self._period]) / self._period
        for i in range(self._period, changes_available):
            avg_gain = (avg_gain * (self._period - 1) + gains[i]) / self._period
            avg_loss = (avg_loss * (self._period - 1) + losses[i]) / self._period

        if avg_loss == 0.0 and avg_gain > 0.0:
            rsi = 100.0
        elif avg_gain == 0.0 and avg_loss > 0.0:
            rsi = 0.0
        elif avg_gain == 0.0 and avg_loss == 0.0:
            rsi = 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=rsi,
            metadata={**base_metadata, "insufficient_data": False},
        )
