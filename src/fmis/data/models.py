"""Normalized OHLCV data contract.

Immutable, validated primitives that every higher layer (features, strategies,
risk, backtesting) consumes. This module defines only the *shape* of market
data and its invariants — no indicator math, no strategy logic, no I/O.

Design decision — numeric type:
    OHLCV values use ``float``. Market data, technical indicators, and
    backtesting are tolerant of tiny binary-floating-point rounding and benefit
    from float's speed and standard-library simplicity. ``Decimal`` is
    deliberately deferred and will be reconsidered later for money, accounting,
    order sizing, and execution, where exact decimal arithmetic matters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

__all__ = ["Candle", "CandleSeries"]

_PRICE_FIELDS = ("open", "high", "low", "close", "volume")


def _is_timezone_aware(ts: datetime) -> bool:
    """Return True only if `ts` carries a concrete UTC offset."""
    return ts.tzinfo is not None and ts.tzinfo.utcoffset(ts) is not None


@dataclass(frozen=True, slots=True)
class Candle:
    """A single OHLCV bar for one symbol and timeframe.

    Frozen (immutable) so a validated candle can never drift out of its
    invariants after construction. `is_closed` distinguishes a completed bar
    from a still-forming one; only closed bars are safe for reproducible
    signals.
    """

    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty")

        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if not _is_timezone_aware(self.timestamp):
            raise ValueError("timestamp must be timezone-aware")

        for name in _PRICE_FIELDS:
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0:
                raise ValueError(f"{name} cannot be negative")

        if self.high < self.open or self.high < self.close or self.high < self.low:
            raise ValueError("high must be >= open, close, and low")
        if self.low > self.open or self.low > self.close or self.low > self.high:
            raise ValueError("low must be <= open, close, and high")


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """An ordered, single-symbol/single-timeframe collection of candles.

    Candles are normalized to a tuple so the container stays immutable. Every
    candle must match the series `symbol` and `timeframe`, and timestamps must
    be strictly increasing (no duplicates, no gaps backwards in time).
    """

    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol cannot be empty")
        if not self.timeframe or not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty")

        # Accept any iterable at construction; store an immutable tuple.
        object.__setattr__(self, "candles", tuple(self.candles))

        previous: datetime | None = None
        for candle in self.candles:
            if candle.symbol != self.symbol:
                raise ValueError(
                    f"candle symbol {candle.symbol!r} does not match "
                    f"series symbol {self.symbol!r}"
                )
            if candle.timeframe != self.timeframe:
                raise ValueError(
                    f"candle timeframe {candle.timeframe!r} does not match "
                    f"series timeframe {self.timeframe!r}"
                )
            if previous is not None and candle.timestamp <= previous:
                raise ValueError("candle timestamps must be strictly increasing")
            previous = candle.timestamp

    def closed(self) -> CandleSeries:
        """Return a new series containing only completed (closed) candles."""
        return CandleSeries(
            symbol=self.symbol,
            timeframe=self.timeframe,
            candles=tuple(c for c in self.candles if c.is_closed),
        )
