"""Milestone BO — the one candle crossing, and the exact bar it produces.

Two properties, and the second is the milestone's no-lookahead guarantee at its
narrowest point.

**The crossing is `fmis.money.exact_from_market_price`, reused.** A `float`
that reached a price comparison would put a fifty-five-digit expansion into a
content digest and therefore into a record id.

**A forming candle is refused, never filtered.** A converter that silently
dropped an open bar would make *"I passed you the wrong series"* and *"the last
bar has not closed yet"* the same event.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal

import pytest

from fmis.data import Candle, CandleSeries
from fmis.paper import PaperRefusedError, PriceBar, bar_from_candle, bars_from_series
from paper_helpers import START, at, bar


def candle(hours: int, *, closed: bool = True, **prices) -> Candle:
    fields = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}
    fields.update(prices)
    return Candle(
        timestamp=at(hours),
        symbol="BTCUSDT",
        timeframe="1h",
        volume=1.0,
        is_closed=closed,
        **fields,
    )


def test_a_closed_candle_becomes_an_exact_bar() -> None:
    converted = bar_from_candle(candle(0))
    assert isinstance(converted, PriceBar)
    assert converted.open == Decimal("100")
    assert converted.close == Decimal("100.5")
    assert converted.symbol == "BTCUSDT"
    assert converted.interval == "1h"
    assert converted.open_time == START


def test_the_crossing_uses_the_shortest_round_tripping_spelling() -> None:
    """`0.1` becomes `Decimal("0.1")` and not `Decimal(0.1)`'s expansion."""
    converted = bar_from_candle(
        candle(0, open=0.1, high=0.3, low=0.1, close=0.2)
    )
    assert converted.open == Decimal("0.1")
    assert str(converted.open) == "0.1"


def test_a_forming_candle_is_refused_and_says_which_one() -> None:
    with pytest.raises(PaperRefusedError, match="has not closed"):
        bar_from_candle(candle(0, closed=False))


def test_a_series_drops_its_forming_bar_through_the_one_existing_filter() -> None:
    series = CandleSeries(
        symbol="BTCUSDT",
        timeframe="1h",
        candles=(candle(0), candle(1), candle(2, closed=False)),
    )
    bars = bars_from_series(series)
    assert len(bars) == 2
    assert bars[-1].open_time == at(1)


def test_an_empty_series_converts_to_no_bars_rather_than_failing() -> None:
    series = CandleSeries(symbol="BTCUSDT", timeframe="1h", candles=())
    assert bars_from_series(series) == ()


def test_the_converter_refuses_something_that_is_not_a_candle() -> None:
    with pytest.raises(TypeError, match="Candle"):
        bar_from_candle("a candle")
    with pytest.raises(TypeError, match="CandleSeries"):
        bars_from_series(())


# --------------------------------------------------------------------------
# The exact bar's own rules
# --------------------------------------------------------------------------


def test_a_bar_whose_extremes_do_not_contain_it_is_not_a_bar() -> None:
    with pytest.raises(PaperRefusedError, match="high"):
        PriceBar(
            symbol="BTCUSDT",
            interval="1h",
            open_time=START,
            open=Decimal("100"),
            high=Decimal("99"),
            low=Decimal("98"),
            close=Decimal("98.5"),
        )
    with pytest.raises(PaperRefusedError, match="low"):
        PriceBar(
            symbol="BTCUSDT",
            interval="1h",
            open_time=START,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("100.5"),
            close=Decimal("100.4"),
        )


def test_a_zero_price_is_a_broken_reading_and_not_a_cheaper_market() -> None:
    with pytest.raises(PaperRefusedError, match="broken reading"):
        PriceBar(
            symbol="BTCUSDT",
            interval="1h",
            open_time=START,
            open=Decimal("0"),
            high=Decimal("1"),
            low=Decimal("0"),
            close=Decimal("1"),
        )


def test_a_naive_open_time_is_refused() -> None:
    from datetime import datetime

    with pytest.raises(Exception):
        PriceBar(
            symbol="BTCUSDT",
            interval="1h",
            open_time=datetime(2026, 8, 1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
        )


def test_a_bars_open_time_is_normalized_to_utc() -> None:
    shifted = START.astimezone(timezone(timedelta(hours=3)))
    assert bar(0, "100", "101", "99", "100").open_time == START
    assert PriceBar(
        symbol="BTCUSDT",
        interval="1h",
        open_time=shifted,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
    ).open_time == START
