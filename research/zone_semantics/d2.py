"""D2-M — how often would the forbidden derivation be wrong?

Disposition §E forbids `below price = support / above price = resistance`. That
is an architectural position, and this module turns it into a number: among the
zones a reader would meet on a real chart, how many sit above the close having
**never been touched at all**?

**This module implements no interaction semantics.** It does not define
breakout, retest, acceptance, reclaim or rejection, and it does not name a
`TOUCH` a rejection. It asks one question the production crossing engine
already answers: has any `LevelCrossingEvent` occurred against any member of
this zone, at or after the bar the zone became knowable? That is the difference
between `UNTESTED` and *everything else*, and it is the only distinction D2-M
needs.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fmis.data import CandleSeries  # noqa: E402
from fmis.level_crossing import (  # noqa: E402
    LevelOrigin,
    LevelSide,
    PriceLevel,
    derive_level_crossings,
)
from fmis.market_structure import StructuralSwingLabel  # noqa: E402

from research.zone_semantics.policies import Zone  # noqa: E402
from research.zone_semantics.structure import ResearchLevel  # noqa: E402

_SIDE = {"upper": LevelSide.UPPER, "lower": LevelSide.LOWER}


def _to_price_level(level: ResearchLevel) -> PriceLevel:
    return PriceLevel(
        price=level.price,
        side=_SIDE[level.side],
        origin=LevelOrigin(
            index=level.origin_index,
            timestamp=level.origin_timestamp,
            label=StructuralSwingLabel(level.label),
            confirmation_bars=level.established_index - level.origin_index,
        ),
    )


def interaction_counts(
    series: CandleSeries, levels: Sequence[ResearchLevel]
) -> dict[tuple[int, int, str, float], int]:
    """Crossings per level, counting only bars at or after the level was knowable.

    A crossing recorded before ``established_index`` is a fact about a price the
    engine could not yet have drawn. Counting it would be lookahead, and would
    make every zone look tested.
    """
    unique: dict[tuple, ResearchLevel] = {}
    for level in levels:
        unique.setdefault(level.key, level)
    price_levels = [_to_price_level(lvl) for lvl in unique.values()]
    if not price_levels:
        return {}
    counts: dict[tuple[int, int, str, float], int] = {k: 0 for k in unique}
    for event in derive_level_crossings(series, price_levels):
        origin = event.level.origin
        assert origin is not None
        established = origin.index + origin.confirmation_bars
        if event.index < established:
            continue
        key = (origin.index, established, event.level.side.value, event.level.price)
        if key in counts:
            counts[key] += 1
    return counts


def sided_history(
    series: CandleSeries, zones: Sequence[Zone]
) -> dict:
    """How often does the position rule change its own answer about one zone?

    This uses **no interaction vocabulary at all** — only the comparison 0047
    §15.2 already calls `position`, and explicitly labels *geometry only, not a
    role*. For each zone, count the closed bars since it became knowable whose
    close sat above its band and whose close sat below it.

    A zone with bars on **both** sides is the decisive case. The position rule
    would have called that one zone *support* on some days and *resistance* on
    others, with no observation of behaviour changing in between — only price
    moving. Interaction history says something different and stable: the zone
    was broken, and by which side.

    This is the argument for §E that does not depend on how often a zone is
    untested. It is a statement about the rule being **ill-defined over time**,
    not about it being rarely wrong.
    """
    candles = series.closed().candles
    both = above_only = below_only = neither = 0
    for zone in zones:
        start = zone.established_index
        above = below = 0
        for candle in candles[start + 1 :]:
            if candle.close > zone.high:
                above += 1
            elif candle.close < zone.low:
                below += 1
        if above and below:
            both += 1
        elif above:
            above_only += 1
        elif below:
            below_only += 1
        else:
            neither += 1
    total = len(zones)
    return {
        "sided_both": both,
        "sided_above_only": above_only,
        "sided_below_only": below_only,
        "sided_neither": neither,
        "sided_both_fraction": (both / total) if total else None,
    }


def disagreement(
    zones: Sequence[Zone],
    counts: dict[tuple[int, int, str, float], int],
    last_close: float,
) -> dict:
    """The size of the error the position rule would make.

    `above_untested` is the headline: zones the position rule would print as
    *resistance* which price has never met. Naming those resistance is not a
    rounding error in the vocabulary — it is an assertion about behaviour for
    which no observation exists.
    """
    above = below = inside = 0
    above_untested = below_untested = 0
    tested = 0
    for zone in zones:
        touched = any(counts.get(k, 0) > 0 for k in zone.member_keys)
        tested += 1 if touched else 0
        if zone.low > last_close:
            above += 1
            above_untested += 0 if touched else 1
        elif zone.high < last_close:
            below += 1
            below_untested += 0 if touched else 1
        else:
            inside += 1
    return {
        "n_zones": len(zones),
        "above": above,
        "below": below,
        "inside": inside,
        "tested": tested,
        "untested": len(zones) - tested,
        "above_untested": above_untested,
        "below_untested": below_untested,
        "above_untested_fraction": (above_untested / above) if above else None,
        "below_untested_fraction": (below_untested / below) if below else None,
    }
