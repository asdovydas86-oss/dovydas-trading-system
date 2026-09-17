"""Shared, dependency-free Wilder-smoothing math used by ATR and RSI.

Kept as a small pure function — not a class, not a base abstraction — for the
reason `ema_math.ema_series` is: two indicators smoothing the same way must use
exactly the same arithmetic, in exactly the same order, so that the value the
latest-only path reports and the final value of the historical path are
**bit-identical** rather than merely close. This is the single source of truth
for Wilder smoothing; indicators must not re-implement it.

Convention, identical to the one ATR and RSI already documented and tested:

    seed  = mean of the first ``period`` values
    v_i   = (v_{i-1} * (period - 1) + value_i) / period
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["wilder_series"]


def wilder_series(values: Sequence[float], period: int) -> list[float]:
    """Return the SMA-seeded Wilder smoothing of ``values`` for ``period``.

    The returned list holds one value per input from the seed onward, so its
    length is ``len(values) - period + 1``. Element 0 corresponds to input index
    ``period - 1``. With fewer than ``period`` values the series is empty, and
    the caller decides how its layer reports insufficient data.

    Pure arithmetic — deterministic, reproducible, and free of any lookahead: a
    value at one position depends only on that position and the ones before it,
    so a prefix of the input yields a prefix of the output exactly.
    """
    if len(values) < period:
        return []

    smoothed = sum(values[:period]) / period
    out = [smoothed]
    for value in values[period:]:
        smoothed = (smoothed * (period - 1) + value) / period
        out.append(smoothed)
    return out
