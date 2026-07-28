"""The only derived calculation in the decision-support layer.

Everything else in this package classifies values that an engine already
produced. This module holds the one genuinely new number — ATR expressed as a
percentage of price — kept separate from orchestration so it can be read and
tested on its own.

Nothing here reads a snapshot, a feature, or a candle: these are plain functions
over plain floats.
"""

from __future__ import annotations

__all__ = ["atr_percent_of_close"]


def atr_percent_of_close(atr: float | None, close: float | None) -> float | None:
    """ATR as a percentage of price: ``atr / close * 100``.

    ATR is an absolute price range, so it cannot be compared across instruments
    or across time at different price levels. Dividing by price makes it
    comparable; multiplying by 100 keeps it in the units people read it in.

    Returns ``None`` — never a substitute value, and never a raised error — when
    the result is not defined:

      * ``atr`` is ``None`` (the indicator is still warming up), or
      * ``close`` is ``None`` (no analysed candle), or
      * ``close`` is ``0`` (division undefined; a zero close is possible in the
        canonical model, which permits zero prices).

    A negative ``atr`` is not possible from the ATR indicator (true range is a
    max of absolute differences) and is not special-cased here.
    """
    if atr is None or close is None or close == 0:
        return None
    return atr / close * 100.0
