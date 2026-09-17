"""Shared, dependency-free MACD math: the line, and the signal over it.

The single source of truth for the MACD arithmetic, built on `ema_series` so its
smoothing is identical to the EMA feature's. Both the latest-value path and the
historical path read what this module produces (ADR-0031 §6).

MACD is also the protocol's proof that a feature value need not be one number:
one timestamp carries ``macd_line``, ``signal_line`` and ``histogram`` together,
and any representation assuming a scalar would have needed redesigning the first
time it met this indicator.

Alignment, stated once:

    macd_line[k]     describes closed candle  k + slow - 1
    signal_line[m]   describes closed candle  m + slow + signal - 2
                     and pairs with           macd_line[m + signal - 1]

so the first fully defined MACD point sits at closed-candle index
``slow + signal - 2`` — the ``required_candles = slow + signal - 1`` the feature
has always reported, expressed as an index rather than a count.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.features.indicators.ema_math import ema_series

__all__ = ["macd_lines"]


def macd_lines(
    prices: Sequence[float], fast_period: int, slow_period: int, signal_period: int
) -> tuple[list[float], list[float]]:
    """Return ``(macd_line, signal_line)`` for ``prices``.

    The fast and slow EMAs seed at different points — the slow one later, since
    it is the longer period — so the MACD line is defined only over their
    overlap, and the fast series is trimmed at the head to match the slow one's
    indices before subtracting. Both returned lists end at the last price.

    ``signal_line`` is the EMA of ``macd_line`` and is therefore shorter by
    ``signal_period - 1``; pair ``signal_line[m]`` with
    ``macd_line[m + signal_period - 1]``. Either list may be empty when there is
    not enough history, and the caller reports that in its own layer's terms.
    """
    fast_ema = ema_series(prices, fast_period)
    slow_ema = ema_series(prices, slow_period)
    fast_tail = fast_ema[slow_period - fast_period :]
    macd_line = [fast - slow for fast, slow in zip(fast_tail, slow_ema)]
    return macd_line, ema_series(macd_line, signal_period)
