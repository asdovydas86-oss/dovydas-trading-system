"""Builders for the feature-series tests — deterministic, offline, clock-free.

One candle builder and one feature roster, shared by the correctness matrix and
the performance measurement so the two describe the same thing.

**Prices are generated from a seeded `random.Random`, never from a clock and
never fetched.** Two runs over the same seed produce byte-identical candles,
which is what lets prefix stability and no-lookahead be asserted as equalities
rather than as tolerances.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fmis.data import Candle, CandleSeries
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.macd import MovingAverageConvergenceDivergence
from fmis.features.indicators.rsi import RelativeStrengthIndex
from fmis.features.volume.statistics import AverageVolume, RelativeVolume

__all__ = [
    "BASE",
    "SYMBOL",
    "TIMEFRAME",
    "candles",
    "series",
    "prefix",
    "series_features",
    "warmup_of",
]

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = "SERIESTEST"
TIMEFRAME = "4h"

#: Every feature that gained series support in TA Slice 5A, at the periods the
#: repository actually runs them at, plus one non-default period so parameter
#: variation is exercised by the same roster rather than by a special case.
#:
#: **`AverageVolume` is here and is still not in `default_features()`.** ADR-0031
#: gave it series support because it shares `volume_math` with `RelativeVolume`;
#: it remains `DORMANT`, and a test asserts the default set did not grow.
def series_features() -> tuple[object, ...]:
    """A fresh instance of every series-capable feature, per call."""
    return (
        ExponentialMovingAverage(20),
        ExponentialMovingAverage(50),
        ExponentialMovingAverage(200),
        AverageTrueRange(14),
        RelativeStrengthIndex(14),
        MovingAverageConvergenceDivergence(),
        RelativeVolume(20),
        AverageVolume(20),
    )


#: Each feature's warm-up, derived from its own parameters rather than restated
#: as a literal, so a changed default cannot leave this table silently wrong.
def warmup_of(feature: object) -> int:
    """How many closed candles ``feature`` needs before its first point."""
    if isinstance(feature, ExponentialMovingAverage):
        return feature.period
    if isinstance(feature, (AverageTrueRange, RelativeStrengthIndex)):
        return feature.period + 1
    if isinstance(feature, MovingAverageConvergenceDivergence):
        return feature.required_candles
    if isinstance(feature, (RelativeVolume, AverageVolume)):
        return feature.lookback + 1
    raise AssertionError(f"no warm-up rule stated for {type(feature).__name__}")


def candles(
    count: int,
    *,
    seed: int = 11,
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
    volume: float | None = None,
    closed: bool = True,
) -> tuple[Candle, ...]:
    """``count`` deterministic candles. ``volume=0.0`` makes the ratio undefined."""
    rnd = random.Random(seed)
    price = 100.0
    out: list[Candle] = []
    for position in range(count):
        price = max(1.0, price * (1 + rnd.uniform(-0.03, 0.03)))
        high = price * (1 + rnd.uniform(0.0, 0.02))
        low = price * (1 - rnd.uniform(0.0, 0.02))
        out.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=BASE + timedelta(hours=4 * position),
                open=price,
                high=high,
                low=low,
                close=price,
                volume=rnd.uniform(10.0, 100.0) if volume is None else volume,
                is_closed=closed,
            )
        )
    return tuple(out)


def series(count: int, **kwargs) -> CandleSeries:
    """A `CandleSeries` of ``count`` deterministic candles."""
    symbol = kwargs.pop("symbol", SYMBOL)
    timeframe = kwargs.pop("timeframe", TIMEFRAME)
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles(count, symbol=symbol, timeframe=timeframe, **kwargs),
    )


def prefix(source: CandleSeries, count: int) -> CandleSeries:
    """The first ``count`` candles of ``source``, as a series of its own.

    A **slice of the same candle objects**, never a regenerated run: the whole
    point of a prefix test is that the inputs are identical, so a difference in
    the output can only have come from the computation.
    """
    return CandleSeries(
        symbol=source.symbol,
        timeframe=source.timeframe,
        candles=source.candles[:count],
    )
