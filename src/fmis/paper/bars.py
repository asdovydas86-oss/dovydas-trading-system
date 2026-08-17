"""The one place a candle becomes an exact bar. Nothing else in either package
imports `fmis.data`, and a guard asserts it as a set.

**The crossing is `fmis.money.exact_from_market_price`, reused.** `AP-D1` Q3 named
exactly one `float` → exact conversion for the whole domain and the money package
implements it; a second one here would be a second definition of *"the bytes"*,
which is Law 1's failure at the level of a function. The conversion goes through
`repr`, the shortest string that round-trips a Python float, so `0.1` becomes
`Decimal("0.1")` and not `Decimal(0.1)`'s fifty-five-digit expansion.

**A forming candle is refused, never filtered.** `CandleSeries.closed()` already
exists and every caller in this repository uses it; a converter that silently
dropped an open bar would make *"I passed you the wrong series"* and *"the last
bar has not closed yet"* the same event. The refusal names which bar and why.

**A bar's `open_time` is its open, and the consequence is stated.** The canonical
`Candle` carries no close time — the provider's is consumed to decide `is_closed`
and is not part of the record — so every instant this package derives from a bar
is the bar's open. `fmis.marks` reached the identical conclusion and stated the
identical consequence: an age computed from it is **overstated, never
understated**, which is the safe direction.
"""

from __future__ import annotations

from collections.abc import Iterable

from fmis.data import Candle, CandleSeries
from fmis.money import exact_from_market_price
from fmis.paper.models import PaperRefusedError, PriceBar

__all__ = ["bar_from_candle", "bars_from_series", "bars_from_candles"]


def bar_from_candle(candle: Candle) -> PriceBar:
    """One closed candle, with its four prices crossed into exact decimals."""
    if not isinstance(candle, Candle):
        raise TypeError(f"candle must be a Candle, got {type(candle).__name__}")
    if not candle.is_closed:
        raise PaperRefusedError(
            f"the {candle.symbol} {candle.timeframe} candle opening "
            f"{candle.timestamp.isoformat()} has not closed. A simulator that read "
            "a forming bar would decide a fill from a price that had not settled, "
            "and re-running it an hour later would decide differently"
        )
    return PriceBar(
        symbol=candle.symbol,
        interval=candle.timeframe,
        open_time=candle.timestamp,
        open=exact_from_market_price(candle.open, "open"),
        high=exact_from_market_price(candle.high, "high"),
        low=exact_from_market_price(candle.low, "low"),
        close=exact_from_market_price(candle.close, "close"),
    )


def bars_from_candles(candles: Iterable[Candle]) -> tuple[PriceBar, ...]:
    """Every candle converted, in the order given. Refuses a forming one."""
    return tuple(bar_from_candle(candle) for candle in candles)


def bars_from_series(series: CandleSeries) -> tuple[PriceBar, ...]:
    """Every **closed** candle of a series, oldest first.

    Filters through `CandleSeries.closed()` rather than by hand, so what counts
    as closed stays the one definition `fmis.data` owns — and so a forming last
    bar is dropped here, where it is the documented behaviour, rather than
    reaching `bar_from_candle`'s refusal, which exists for a caller who assembled
    candles themselves.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    return bars_from_candles(series.closed().candles)
