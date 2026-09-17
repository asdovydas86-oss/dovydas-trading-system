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

from fmis.features.indicators.rsi_math import gains_and_losses, rsi_series
from fmis.features.indicators.sources import VALID_SOURCES
from fmis.features.series import FeatureSeries, FeatureSeriesPoint
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

    def _base_metadata(
        self, available: int, changes_available: int
    ) -> dict[str, object]:
        """The parameters and provenance both output paths report.

        One dict builder rather than two literals, so `compute` and
        `compute_series` cannot describe the same calculation differently.
        """
        return {
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

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        # The changes, the Wilder smoothing and the zero-gain/zero-loss policy
        # all come from `rsi_math`, which is the same arithmetic
        # `compute_series` runs — so the latest value and the final point of the
        # history are one number, not two that agree (ADR-0031 §6).
        gains, _losses = gains_and_losses(prices)
        changes_available = len(gains)
        base_metadata = self._base_metadata(available, changes_available)

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

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=rsi_series(prices, self._period)[-1],
            metadata={**base_metadata, "insufficient_data": False},
        )

    def compute_series(self, context: FeatureContext) -> FeatureSeries:
        """This RSI at every closed candle where it is defined (ADR-0031).

        Alignment: a change needs a predecessor, so element ``k`` of the shared
        series describes closed candle ``k + period`` — the fifteenth bar for the
        default period of 14, matching the ``warmup_candles`` of ``period + 1``
        this feature has always reported.
        """
        closed = context.primary.closed()
        candles = closed.candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        gains, _losses = gains_and_losses(prices)
        values = rsi_series(prices, self._period)
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
            metadata=self._base_metadata(available, len(gains)),
        )
