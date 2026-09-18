"""Builders for the price-zone tests — deterministic, offline, clock-free.

Two kinds of input, and they answer two different questions:

* **hand-built levels and a flat width history**, for the rules that need an
  exact arrangement — a tie between two bands, two levels sharing a bar, two
  equal prices with different origins. A real market rarely produces those on
  demand, and a test that waited for one would be testing the fixture.
* **real production output** — `detect_swings` → `label_swing_sequence` →
  `structural_levels` over seeded candles, with the real `AverageTrueRange` — for
  the invariants that must hold over whatever a market actually produces.

Not a test module itself (no `test_` prefix, so pytest does not collect it).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fmis.data import Candle, CandleSeries, SeriesIdentity
from fmis.features import FeatureContext
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.series import FeatureSeries, FeatureSeriesPoint
from fmis.features.types import FeatureCategory
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel, structural_levels
from fmis.market_structure import (
    StructuralSwingLabel,
    compare_swing_sequence,
    detect_swings,
    label_swing_sequence,
)

__all__ = [
    "BASE",
    "SYMBOL",
    "TIMEFRAME",
    "IDENTITY",
    "level",
    "flat_width_series",
    "width_series_from",
    "seeded_series",
    "levels_of",
    "atr_series_of",
    "scaled",
    "reflected",
    "zone_map",
]

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SYMBOL = "ZONETEST"
TIMEFRAME = "4h"
IDENTITY = SeriesIdentity(symbol=SYMBOL, timeframe=TIMEFRAME)

#: One label per side, so a hand-built level's side and provenance agree without
#: every call site restating the mapping `PriceLevel` already validates.
_LABEL = {
    LevelSide.UPPER: StructuralSwingLabel.HIGHER_HIGH,
    LevelSide.LOWER: StructuralSwingLabel.HIGHER_LOW,
}


def level(
    price: float,
    *,
    index: int,
    confirmation_bars: int = 2,
    side: LevelSide = LevelSide.UPPER,
    label: StructuralSwingLabel | None = None,
) -> PriceLevel:
    """One hand-built level. ``index + confirmation_bars`` is its establishment bar."""
    chosen = _LABEL[side] if label is None else label
    return PriceLevel(
        price=price,
        side=side,
        origin=LevelOrigin(
            index=index,
            timestamp=BASE + timedelta(hours=4 * index),
            label=chosen,
            confirmation_bars=confirmation_bars,
        ),
    )


def flat_width_series(
    value: float,
    *,
    bars: int = 400,
    first_index: int = 15,
    name: str = "atr_14",
    identity: SeriesIdentity = IDENTITY,
) -> FeatureSeries:
    """A width history that is ``value`` everywhere from ``first_index`` onward.

    Flat on purpose: every rule about *which* band a level joins is then a
    statement about the geometry alone, with volatility held still so it cannot
    be the explanation for an outcome.
    """
    return width_series_from(
        {index: value for index in range(first_index, bars)},
        bars=bars,
        name=name,
        identity=identity,
    )


def width_series_from(
    values: dict[int, float],
    *,
    bars: int = 400,
    name: str = "atr_14",
    identity: SeriesIdentity = IDENTITY,
) -> FeatureSeries:
    """A width history with exactly the points ``values`` names."""
    return FeatureSeries(
        name=name,
        category=FeatureCategory.INDICATOR,
        identity=identity,
        as_of=BASE + timedelta(hours=4 * (bars - 1)),
        closed_candles=bars,
        warmup_candles=15,
        points=tuple(
            FeatureSeriesPoint(
                index=index,
                timestamp=BASE + timedelta(hours=4 * index),
                value=values[index],
            )
            for index in sorted(values)
        ),
    )


def seeded_series(
    count: int = 400,
    *,
    seed: int = 7,
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
    drift: float = 0.0,
) -> CandleSeries:
    """Deterministic candles. ``drift`` adds a trend so levels spread out.

    A flat random walk piles every level into a handful of wide bands, which
    hides exactly the behaviour the overlap and prefix tests are about.
    """
    rnd = random.Random(seed)
    price = 100.0
    candles = []
    for position in range(count):
        price = max(1.0, price * (1 + drift + rnd.uniform(-0.02, 0.02)))
        open_ = price * (1 + rnd.uniform(-0.005, 0.005))
        close = price * (1 + rnd.uniform(-0.005, 0.005))
        candles.append(
            Candle(
                timestamp=BASE + timedelta(hours=4 * position),
                symbol=symbol,
                timeframe=timeframe,
                open=open_,
                high=max(open_, close) * (1 + rnd.uniform(0.0, 0.01)),
                low=min(open_, close) * (1 - rnd.uniform(0.0, 0.01)),
                close=close,
                volume=rnd.uniform(1.0, 5.0),
                is_closed=True,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=tuple(candles))


def levels_of(series: CandleSeries) -> tuple[PriceLevel, ...]:
    """The production level run, through the production chain and nothing else."""
    return structural_levels(
        label_swing_sequence(compare_swing_sequence(detect_swings(series.closed())))
    )


def atr_series_of(series: CandleSeries, period: int = 14) -> FeatureSeries:
    """The production ATR's own aligned history over ``series``."""
    return AverageTrueRange(period).compute_series(
        FeatureContext(primary=series.closed())
    )


def scaled(series: CandleSeries, factor: float) -> CandleSeries:
    """Every price multiplied by ``factor``. A dyadic factor rescales exactly."""
    return CandleSeries(
        symbol=series.symbol,
        timeframe=series.timeframe,
        candles=tuple(
            Candle(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                open=candle.open * factor,
                high=candle.high * factor,
                low=candle.low * factor,
                close=candle.close * factor,
                volume=candle.volume,
                is_closed=True,
            )
            for candle in series.candles
        ),
    )


def reflected(series: CandleSeries, about: float) -> CandleSeries:
    """The series mirrored about a price — a long market becomes a short one.

    High and low swap, because the reflection of a bar's maximum is its minimum.
    Forgetting that produces ``low > high``, which `Candle` rejects, and the test
    would then pass by crashing.
    """
    return CandleSeries(
        symbol=series.symbol,
        timeframe=series.timeframe,
        candles=tuple(
            Candle(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                open=about - candle.open,
                high=about - candle.low,
                low=about - candle.high,
                close=about - candle.close,
                volume=candle.volume,
                is_closed=True,
            )
            for candle in series.candles
        ),
    )


def zone_map(zone_set) -> tuple[tuple[int, int, tuple[tuple[int, int], ...]], ...]:
    """A zone set reduced to its **partition**, free of prices.

    Each zone becomes ``(established bar, anchor's origin bar, every member's
    (origin index, establishment bar))``. Prices are deliberately excluded: under
    a rescale they all move, and under a reflection they all invert, so a
    comparison that included them could only ever fail. What must be invariant is
    *which levels grouped with which*, and that is what this records.
    """
    return tuple(
        (
            zone.established_index,
            zone.anchor.level.origin.index,
            tuple(
                (member.level.origin.index, member.joined_index)
                for member in zone.members
            ),
        )
        for zone in zone_set.zones
    )
