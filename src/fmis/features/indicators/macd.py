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

from fmis.features.indicators.macd_math import macd_lines
from fmis.features.indicators.sources import VALID_SOURCES
from fmis.features.series import FeatureSeries, FeatureSeriesPoint
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

    @property
    def required_candles(self) -> int:
        """Closed candles needed before the signal line can be seeded.

        ``slow + signal - 1`` — 34 for the 12/26/9 default. A projection rather
        than a stored number, so the metadata, the warm-up field and the series
        alignment all quote one expression.
        """
        return self._slow + self._signal - 1

    def _base_metadata(
        self, available: int, macd_values_available: int
    ) -> dict[str, object]:
        """The parameters and provenance both output paths report.

        One dict builder rather than two literals, so `compute` and
        `compute_series` cannot describe the same calculation differently.
        """
        return {
            "source": self._source,
            "fast_period": self._fast,
            "slow_period": self._slow,
            "signal_period": self._signal,
            "method": "ema",
            "ema_initialization": "sma_seed",
            "closed_candles_available": available,
            "required_candles": self.required_candles,
            "macd_values_available": macd_values_available,
            "warmup_candles": self.required_candles,
            "output_representation": (
                "immutable mapping {macd_line, signal_line, histogram}"
            ),
            "provenance": (
                "fmis.features.indicators.macd.MovingAverageConvergenceDivergence"
            ),
        }

    def _value_at(
        self, macd_line: list[float], signal_line: list[float], offset: int
    ) -> MappingProxyType:
        """One timestamp's three MACD components, as the immutable value.

        ``offset`` indexes ``signal_line``; the paired MACD-line element sits
        ``signal - 1`` further along, because the signal EMA seeds that much
        later than the line it smooths. Built here so the pairing exists once —
        the latest value and every historical point read the same expression.
        """
        macd_value = macd_line[offset + self._signal - 1]
        signal_value = signal_line[offset]
        return MappingProxyType(
            {
                "macd_line": macd_value,
                "signal_line": signal_value,
                "histogram": macd_value - signal_value,
            }
        )

    def compute(self, context: FeatureContext) -> FeatureResult:
        # Closed candles only — idempotent even if the engine already closed them.
        candles = context.primary.closed().candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        # Both lines come from `macd_math`, which is the same arithmetic
        # `compute_series` runs — so the latest value and the final point of the
        # history are one mapping, not two that agree (ADR-0031 §6).
        macd_line, signal_line = macd_lines(
            prices, self._fast, self._slow, self._signal
        )
        macd_values_available = len(macd_line)
        base_metadata = self._base_metadata(available, macd_values_available)

        if macd_values_available < self._signal:
            return FeatureResult(
                name=self.name,
                category=self.category,
                value=None,
                metadata={**base_metadata, "insufficient_data": True},
            )

        return FeatureResult(
            name=self.name,
            category=self.category,
            value=self._value_at(macd_line, signal_line, len(signal_line) - 1),
            metadata={**base_metadata, "insufficient_data": False},
        )

    def compute_series(self, context: FeatureContext) -> FeatureSeries:
        """MACD at every closed candle where all three components exist.

        **The protocol's proof that a feature value need not be a scalar.** Each
        point carries the same immutable ``{macd_line, signal_line, histogram}``
        mapping `compute` produces for the latest bar; a representation that
        assumed one float per timestamp would have needed redesigning here
        (ADR-0031 §5).

        Alignment: element ``m`` of the signal series describes closed candle
        ``m + slow + signal - 2``, so the first point sits at
        ``required_candles - 1`` — the thirty-fourth bar for the 12/26/9 default.
        """
        closed = context.primary.closed()
        candles = closed.candles
        available = len(candles)
        prices = [getattr(candle, self._source) for candle in candles]

        macd_line, signal_line = macd_lines(
            prices, self._fast, self._slow, self._signal
        )
        first = self.required_candles - 1
        points = tuple(
            FeatureSeriesPoint(
                index=offset + first,
                timestamp=candles[offset + first].timestamp,
                value=self._value_at(macd_line, signal_line, offset),
            )
            for offset in range(len(signal_line))
        )
        return FeatureSeries(
            name=self.name,
            category=self.category,
            identity=closed.identity,
            as_of=candles[-1].timestamp if candles else None,
            closed_candles=available,
            warmup_candles=self.required_candles,
            points=points,
            metadata=self._base_metadata(available, len(macd_line)),
        )
