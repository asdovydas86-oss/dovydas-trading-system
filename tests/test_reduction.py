"""Tests for the CandleSeries -> ObservationSeries reduction helper.

Expected values are constructed by hand in each test — distinct OHLCV components
per candle so a wrong-field selection cannot pass by coincidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import (
    Candle,
    CandleSeries,
    CandleField,
    ObservationSeries,
    candle_series_to_observations,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _candle(
    i: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    is_closed: bool = True,
    symbol: str = "BTCUSDT",
    timeframe: str = "4H",
) -> Candle:
    return Candle(
        timestamp=_BASE + timedelta(hours=4 * i),
        symbol=symbol,
        timeframe=timeframe,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


def _series(*candles: Candle, symbol: str = "BTCUSDT", timeframe: str = "4H") -> CandleSeries:
    return CandleSeries(symbol=symbol, timeframe=timeframe, candles=candles)


# Two candles with all-distinct components, so each field is uniquely identifiable.
def _two_distinct() -> CandleSeries:
    return _series(
        _candle(0, open_=10.0, high=15.0, low=9.0, close=12.0, volume=100.0),
        _candle(1, open_=12.0, high=18.0, low=11.0, close=17.0, volume=250.0),
    )


# --- field selection ---------------------------------------------------------


@pytest.mark.parametrize(
    "field, expected",
    [
        (CandleField.OPEN, (10.0, 12.0)),
        (CandleField.HIGH, (15.0, 18.0)),
        (CandleField.LOW, (9.0, 11.0)),
        (CandleField.CLOSE, (12.0, 17.0)),
        (CandleField.VOLUME, (100.0, 250.0)),
    ],
)
def test_each_field_selects_its_own_values(
    field: CandleField, expected: tuple[float, ...]
) -> None:
    result = candle_series_to_observations(_two_distinct(), field)
    assert result.values == expected


def test_timestamps_are_preserved_exactly() -> None:
    series = _two_distinct()
    result = candle_series_to_observations(series, CandleField.CLOSE)
    assert result.timestamps == tuple(c.timestamp for c in series.candles)


def test_result_is_an_observation_series() -> None:
    result = candle_series_to_observations(_two_distinct(), CandleField.CLOSE)
    assert isinstance(result, ObservationSeries)


# --- identity, unit, frequency ----------------------------------------------


def test_series_id_is_derived_by_default() -> None:
    result = candle_series_to_observations(_two_distinct(), CandleField.CLOSE)
    assert result.series_id == "BTCUSDT.close.4H"


def test_series_id_reflects_field_and_timeframe() -> None:
    result = candle_series_to_observations(_two_distinct(), CandleField.HIGH)
    assert result.series_id == "BTCUSDT.high.4H"


def test_series_id_override_is_used_verbatim() -> None:
    result = candle_series_to_observations(
        _two_distinct(), CandleField.CLOSE, series_id="CUSTOM_ID"
    )
    assert result.series_id == "CUSTOM_ID"


@pytest.mark.parametrize(
    "field, unit",
    [
        (CandleField.OPEN, "price"),
        (CandleField.HIGH, "price"),
        (CandleField.LOW, "price"),
        (CandleField.CLOSE, "price"),
        (CandleField.VOLUME, "volume"),
    ],
)
def test_unit_is_price_for_ohlc_and_volume_for_volume(
    field: CandleField, unit: str
) -> None:
    result = candle_series_to_observations(_two_distinct(), field)
    assert result.unit == unit


def test_frequency_is_the_series_timeframe() -> None:
    series = _series(
        _candle(0, open_=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, timeframe="1D"),
        symbol="BTCUSDT",
        timeframe="1D",
    )
    result = candle_series_to_observations(series, CandleField.CLOSE)
    assert result.frequency == "1D"


# --- closed-candles-only -----------------------------------------------------


def test_forming_candle_is_dropped() -> None:
    series = _series(
        _candle(0, open_=10.0, high=15.0, low=9.0, close=12.0, volume=100.0),
        _candle(1, open_=12.0, high=18.0, low=11.0, close=17.0, volume=250.0,
                is_closed=False),
    )
    result = candle_series_to_observations(series, CandleField.CLOSE)
    assert result.values == (12.0,)
    assert result.timestamps == (series.candles[0].timestamp,)


def test_empty_series_yields_empty_observation_series() -> None:
    result = candle_series_to_observations(_series(), CandleField.CLOSE)
    assert result.timestamps == ()
    assert result.values == ()
    # Still a valid, fully-formed series with identity metadata.
    assert result.series_id == "BTCUSDT.close.4H"
    assert result.unit == "price"


def test_all_forming_series_yields_empty_observation_series() -> None:
    series = _series(
        _candle(0, open_=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, is_closed=False),
    )
    result = candle_series_to_observations(series, CandleField.CLOSE)
    assert result.values == ()


# --- misuse resistance -------------------------------------------------------


@pytest.mark.parametrize("bad_field", ["close", "CLOSE", None, 0, True])
def test_non_enum_field_is_rejected(bad_field: object) -> None:
    with pytest.raises(TypeError, match="field must be a CandleField"):
        candle_series_to_observations(_two_distinct(), bad_field)  # type: ignore[arg-type]


def test_non_candle_series_is_rejected() -> None:
    with pytest.raises(TypeError, match="series must be a CandleSeries"):
        candle_series_to_observations([1, 2, 3], CandleField.CLOSE)  # type: ignore[arg-type]


def test_there_is_no_default_field() -> None:
    # Selecting a field is mandatory: omitting it is a TypeError from Python,
    # which is the point — no silent default field exists.
    with pytest.raises(TypeError):
        candle_series_to_observations(_two_distinct())  # type: ignore[call-arg]


# --- enum vocabulary ---------------------------------------------------------


def test_candle_field_values_match_candle_attributes() -> None:
    assert {f.value for f in CandleField} == {"open", "high", "low", "close", "volume"}
    # Each value is a real Candle attribute (so getattr in the reducer is valid).
    candle = _two_distinct().candles[0]
    for field in CandleField:
        assert hasattr(candle, field.value)
