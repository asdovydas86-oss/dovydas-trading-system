"""Shared, dependency-free ATR math: true ranges, and the smoothed series.

The single source of truth for the Average True Range arithmetic. Both the
latest-value path (`AverageTrueRange.compute`) and the historical path
(`AverageTrueRange.compute_series`) read the series this module produces, so
there is one formula rather than two that happen to agree (ADR-0031 §6).

Alignment, stated once so nothing downstream has to re-derive it:

    true_ranges[j]   describes closed candle  j + 1     (TR needs a previous close)
    atr_series[k]    describes closed candle  k + period

so with ``period`` = 14 the first ATR describes closed candle index 14, which is
the fifteenth bar — matching the ``warmup_candles = period + 1`` the feature has
always reported.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.data import Candle
from fmis.features.indicators.wilder_math import wilder_series

__all__ = ["true_ranges", "atr_from_ranges", "atr_series"]


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    """The true range of every candle that has a predecessor.

        TR_t = max(high_t - low_t,
                   abs(high_t - close_{t-1}),
                   abs(low_t  - close_{t-1}))

    Defined from the **second** candle onward, so ``N`` candles yield ``N - 1``
    true ranges and ``true_ranges[j]`` describes candle ``j + 1``.
    """
    out: list[float] = []
    for position in range(1, len(candles)):
        high = candles[position].high
        low = candles[position].low
        previous_close = candles[position - 1].close
        out.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
    return out


def atr_from_ranges(ranges: Sequence[float], period: int) -> list[float]:
    """Wilder ATR over already-computed true ranges.

    Exists so a caller that already holds the ranges — because it needs their
    count for metadata, or is about to place them on a timeline — does not have
    to derive them twice. ``atr_from_ranges(...)[k]`` describes closed candle
    ``k + period``.
    """
    return wilder_series(ranges, period)


def atr_series(candles: Sequence[Candle], period: int) -> list[float]:
    """Wilder ATR for every candle at which it is defined.

    ``atr_series(...)[k]`` describes closed candle ``k + period``. Empty when
    there are fewer than ``period + 1`` candles — the caller reports insufficient
    data in its own layer's terms rather than receiving a guessed number.
    """
    return atr_from_ranges(true_ranges(candles), period)
