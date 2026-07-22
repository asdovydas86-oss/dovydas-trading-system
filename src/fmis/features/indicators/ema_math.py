"""Shared, dependency-free EMA-series math used by EMA and MACD.

Kept as a small pure function (not a class, not a base abstraction) so that any
indicator needing SMA-seeded EMA math — over candle prices or over a derived
series such as the MACD line — uses exactly the same arithmetic. This is the
single source of truth for EMA smoothing; indicators must not re-implement it.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["ema_series"]


def ema_series(values: Sequence[float], period: int) -> list[float]:
    """Return the SMA-seeded EMA of ``values`` for ``period``.

    Convention (identical to the EMA feature):
        - seed EMA_0 = SMA of the first ``period`` values;
        - EMA_t = (v_t - EMA_{t-1}) * (2 / (period + 1)) + EMA_{t-1}.

    The returned list holds one EMA per input from the seed onward, so its length
    is ``len(values) - period + 1``. If there are fewer than ``period`` values,
    the series is empty (the caller decides how to report insufficient data).
    Pure arithmetic — deterministic and reproducible.
    """
    n = len(values)
    if n < period:
        return []

    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    out = [ema]
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
        out.append(ema)
    return out
