"""Structural levels and ATR, composed from **production** functions only.

This module chooses no window, no threshold and no parameter of its own. It
calls `fmis` and re-shapes the result into the minimal record the grouping
policies need.
"""

from __future__ import annotations

from dataclasses import dataclass

from fmis.data import CandleSeries
from fmis.features import FeatureContext
from fmis.features.indicators.atr import AverageTrueRange
from fmis.level_crossing import PriceLevel, structural_levels
from fmis.market_structure import (
    compare_swing_sequence,
    detect_swings,
    label_swing_sequence,
)

ATR_PERIOD = 14


@dataclass(frozen=True, slots=True)
class ResearchLevel:
    """One production `PriceLevel`, plus the bar at which it became knowable.

    ``established_index`` is ``origin.index + origin.confirmation_bars`` — the
    pivot's own bar plus the right-hand bars its confirmation required. It is
    the earliest index at which this level could have been known, and it is the
    only temporal fact the grouping policies are allowed to read. Reading
    ``origin.index`` instead would let a zone exist before its own level did.
    """

    price: float
    side: str
    origin_index: int
    established_index: int
    label: str
    origin_timestamp: object = None
    seq: int = -1
    """Position in the level run this level came from.

    Identity for the transform tests. `origin_index` cannot serve: one candle
    can be both a swing high and a swing low, so two levels share it, and a
    comparison keyed on it silently merges them. `price` and `side` both invert
    under reflection. `seq` is assigned once, carried through every transform
    unchanged, and is the only field that is both unique and invariant.
    """

    @property
    def key(self) -> tuple[int, int, str, float]:
        """A stable identity for partition comparison."""
        return (self.origin_index, self.established_index, self.side, self.price)


def levels_for(series: CandleSeries) -> tuple[ResearchLevel, ...]:
    swings = detect_swings(series)
    labelled = label_swing_sequence(compare_swing_sequence(swings))
    return tuple(
        _convert(level, position)
        for position, level in enumerate(structural_levels(labelled))
    )


def _convert(level: PriceLevel, position: int = -1) -> ResearchLevel:
    origin = level.origin
    assert origin is not None  # structural_levels always sets one
    return ResearchLevel(
        price=level.price,
        side=level.side.value,
        origin_index=origin.index,
        established_index=origin.index + origin.confirmation_bars,
        label=origin.label.value,
        origin_timestamp=origin.timestamp,
        seq=position,
    )


def atr_by_index(series: CandleSeries, period: int = ATR_PERIOD) -> dict[int, float]:
    """`{closed-candle index: ATR}` from the production feature's own history."""
    feature = AverageTrueRange(period)
    result = feature.compute_series(FeatureContext(primary=series))
    return {
        point.index: float(point.value)
        for point in result.points
        if point.value is not None
    }


def atr_at(table: dict[int, float], index: int) -> float | None:
    """ATR at ``index``, or the **nearest earlier** index, never a later one.

    Falling back to a later value would be lookahead dressed as a lookup: a zone
    established at bar 20 would be sized by volatility it could not yet have
    measured. Returning `None` before warm-up is the honest answer, and the
    caller treats a zone it cannot size as unformed rather than guessing.
    """
    if index in table:
        return table[index]
    earlier = [i for i in table if i < index]
    if not earlier:
        return None
    return table[max(earlier)]
