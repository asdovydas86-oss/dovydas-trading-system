"""Tests for the normalized OHLCV data contract (fmis.data.models)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from fmis.data import Candle, CandleSeries

FIXTURES = Path(__file__).parent / "fixtures"


def make_candle(
    *,
    ts: datetime | None = None,
    symbol: str = "BTCUSDT",
    timeframe: str = "1D",
    open_: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 105.0,
    volume: float = 1000.0,
    is_closed: bool = True,
) -> Candle:
    """Build a valid candle; override one field to exercise a failure case."""
    if ts is None:
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Candle(
        timestamp=ts,
        symbol=symbol,
        timeframe=timeframe,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


# --- Candle: valid -----------------------------------------------------------


def test_valid_candle_constructs_and_is_frozen() -> None:
    candle = make_candle()
    assert candle.symbol == "BTCUSDT"
    assert candle.close == 105.0
    with pytest.raises(AttributeError):
        candle.close = 1.0  # type: ignore[misc]


def test_high_equal_to_open_and_low_equal_to_close_is_valid() -> None:
    # Boundary: high == max(o, c) and low == min(o, c) must be allowed.
    make_candle(open_=100.0, high=100.0, low=95.0, close=95.0)


def test_zero_prices_and_volume_are_valid() -> None:
    make_candle(open_=0.0, high=0.0, low=0.0, close=0.0, volume=0.0)


# --- Candle: invalid ---------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_symbol_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="symbol cannot be empty"):
        make_candle(symbol=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_timeframe_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="timeframe cannot be empty"):
        make_candle(timeframe=bad)


@pytest.mark.parametrize("field", ["open_", "high", "low", "close", "volume"])
def test_negative_values_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        make_candle(**{field: -1.0})


def test_high_below_a_price_rejected() -> None:
    with pytest.raises(ValueError, match="high must be >="):
        make_candle(open_=100.0, high=104.0, low=90.0, close=105.0)


def test_low_above_a_price_rejected() -> None:
    with pytest.raises(ValueError, match="low must be <="):
        make_candle(open_=100.0, high=110.0, low=101.0, close=105.0)


@pytest.mark.parametrize("field", ["open_", "high", "low", "close", "volume"])
def test_nan_values_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        make_candle(**{field: math.nan})


@pytest.mark.parametrize("field", ["open_", "high", "low", "close", "volume"])
def test_positive_infinity_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="must be a finite number"):
        make_candle(**{field: math.inf})


@pytest.mark.parametrize("field", ["open_", "high", "low", "close", "volume"])
def test_negative_infinity_rejected(field: str) -> None:
    # -inf must fail the finite check, not the (later) negative check.
    with pytest.raises(ValueError, match="must be a finite number"):
        make_candle(**{field: -math.inf})


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_candle(ts=datetime(2024, 1, 1))  # no tzinfo


def test_non_datetime_timestamp_rejected() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        make_candle(ts="2024-01-01")  # type: ignore[arg-type]


# --- Candle: canonical UTC timestamp contract --------------------------------


@pytest.mark.parametrize(
    "tz",
    [
        timezone.utc,
        timezone(timedelta(0)),
        ZoneInfo("UTC"),
        ZoneInfo("Etc/UTC"),
        ZoneInfo("GMT"),
    ],
)
def test_utc_representations_accepted(tz: object) -> None:
    make_candle(ts=datetime(2024, 1, 1, tzinfo=tz))  # type: ignore[arg-type]


@pytest.mark.parametrize("zone", ["Europe/Stockholm", "America/New_York"])
def test_non_utc_zoneinfo_rejected(zone: str) -> None:
    with pytest.raises(ValueError, match="must represent UTC"):
        make_candle(ts=datetime(2024, 1, 1, tzinfo=ZoneInfo(zone)))


@pytest.mark.parametrize("month", [1, 7])  # winter (GMT, +0) and summer (BST, +1)
def test_regional_zero_offset_zone_rejected_both_seasons(month: int) -> None:
    # Europe/London is +00:00 in winter but must still be rejected: it is a DST
    # zone, not a permanent UTC zone (this is the loophole being closed).
    ts = datetime(2024, month, 15, tzinfo=ZoneInfo("Europe/London"))
    with pytest.raises(ValueError, match="must represent UTC"):
        make_candle(ts=ts)


def test_fixed_nonzero_offset_rejected() -> None:
    with pytest.raises(ValueError, match="must represent UTC"):
        make_candle(ts=datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=1))))


# --- CandleSeries: valid -----------------------------------------------------


def _series_candles() -> list[Candle]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [make_candle(ts=base + timedelta(days=i)) for i in range(3)]


def test_valid_series_constructs() -> None:
    series = CandleSeries(
        symbol="BTCUSDT", timeframe="1D", candles=tuple(_series_candles())
    )
    assert len(series.candles) == 3


def test_empty_series_is_valid() -> None:
    series = CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=())
    assert series.candles == ()


def test_closed_helper_filters_out_forming_candle() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = (
        make_candle(ts=base, is_closed=True),
        make_candle(ts=base + timedelta(days=1), is_closed=True),
        make_candle(ts=base + timedelta(days=2), is_closed=False),
    )
    series = CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=candles)
    closed = series.closed()
    assert len(closed.candles) == 2
    assert all(c.is_closed for c in closed.candles)
    assert isinstance(closed, CandleSeries)


# --- CandleSeries: invalid ---------------------------------------------------


def test_series_rejects_symbol_mismatch() -> None:
    candles = (make_candle(symbol="ETHUSDT"),)
    with pytest.raises(ValueError, match="does not match series symbol"):
        CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=candles)


def test_series_rejects_timeframe_mismatch() -> None:
    candles = (make_candle(timeframe="4H"),)
    with pytest.raises(ValueError, match="does not match series timeframe"):
        CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=candles)


def test_series_rejects_duplicate_timestamps() -> None:
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    candles = (make_candle(ts=ts), make_candle(ts=ts))
    with pytest.raises(ValueError, match="strictly increasing"):
        CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=candles)


def test_series_rejects_decreasing_timestamps() -> None:
    base = datetime(2024, 1, 2, tzinfo=timezone.utc)
    candles = (
        make_candle(ts=base),
        make_candle(ts=base - timedelta(days=1)),
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        CandleSeries(symbol="BTCUSDT", timeframe="1D", candles=candles)


def test_series_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol cannot be empty"):
        CandleSeries(symbol="", timeframe="1D", candles=())


# --- Fixture loading ---------------------------------------------------------


def test_fixture_builds_valid_candle_series() -> None:
    # Ad-hoc load kept inside the test on purpose: no production JSON
    # parsing/serialization helpers exist yet (deferred to a later milestone).
    records = json.loads((FIXTURES / "btcusdt_4h.json").read_text())
    assert len(records) == 20

    candles = [
        Candle(
            timestamp=datetime.fromisoformat(r["timestamp"]),
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            is_closed=r["is_closed"],
        )
        for r in records
    ]

    series = CandleSeries(symbol="BTCUSDT", timeframe="4H", candles=tuple(candles))

    assert len(series.candles) == 20
    assert all(c.is_closed for c in series.candles)
    # Every fixture candle is closed, so closed() keeps them all.
    assert len(series.closed().candles) == 20
