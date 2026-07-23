"""Tests for the canonical ObservationSeries contract (fmis.data.observation)."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import ObservationSeries

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _ts(n: int) -> tuple[datetime, ...]:
    """`n` strictly-increasing timezone-aware timestamps."""
    return tuple(_BASE + timedelta(days=i) for i in range(n))


def make_series(
    *,
    series_id: str = "CPI_YOY",
    unit: str = "percent",
    frequency: str = "1M",
    timestamps: object = None,
    values: object = None,
) -> ObservationSeries:
    """Build a valid 3-point series; override one field to exercise a failure."""
    if timestamps is None:
        timestamps = _ts(3)
    if values is None:
        values = (3.1, 3.4, 3.2)
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency=frequency,
        timestamps=timestamps,  # type: ignore[arg-type]
        values=values,  # type: ignore[arg-type]
    )


# --- valid construction ------------------------------------------------------


def test_valid_construction_preserves_fields() -> None:
    s = make_series()
    assert s.series_id == "CPI_YOY"
    assert s.unit == "percent"
    assert s.frequency == "1M"
    assert s.timestamps == _ts(3)
    assert s.values == (3.1, 3.4, 3.2)


def test_negative_values_are_allowed() -> None:
    # Observations (real yields, net flows, z-scores) can be negative.
    s = make_series(values=(-1.5, 0.0, 2.3))
    assert s.values == (-1.5, 0.0, 2.3)


def test_integer_values_are_allowed_and_uncoerced() -> None:
    s = make_series(values=(1, 2, 3))
    assert s.values == (1, 2, 3)


def test_empty_series_is_valid() -> None:
    s = ObservationSeries(
        series_id="X", unit="count", frequency="1D", timestamps=(), values=()
    )
    assert s.timestamps == ()
    assert s.values == ()


def test_accepts_list_inputs_and_stores_tuples() -> None:
    s = ObservationSeries(
        series_id="X",
        unit="u",
        frequency="1D",
        timestamps=[_BASE, _BASE + timedelta(days=1)],
        values=[1.0, 2.0],
    )
    assert isinstance(s.timestamps, tuple)
    assert isinstance(s.values, tuple)


# --- identity / metadata validation ------------------------------------------


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_series_id_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="series_id cannot be empty"):
        make_series(series_id=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_unit_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="unit cannot be empty"):
        make_series(unit=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_frequency_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="frequency cannot be empty"):
        make_series(frequency=bad)


# --- length / ordering invariants --------------------------------------------


def test_mismatched_lengths_rejected() -> None:
    with pytest.raises(ValueError, match="equal length"):
        make_series(timestamps=_ts(3), values=(1.0, 2.0))


def test_duplicate_timestamps_rejected() -> None:
    dup = (_BASE, _BASE, _BASE + timedelta(days=1))
    with pytest.raises(ValueError, match="strictly increasing"):
        make_series(timestamps=dup, values=(1.0, 2.0, 3.0))


def test_unordered_timestamps_rejected() -> None:
    desc = (_BASE + timedelta(days=2), _BASE + timedelta(days=1), _BASE)
    with pytest.raises(ValueError, match="strictly increasing"):
        make_series(timestamps=desc, values=(1.0, 2.0, 3.0))


# --- timestamp validation ----------------------------------------------------


def test_non_datetime_timestamp_rejected() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        make_series(timestamps=("2024-01-01", _BASE), values=(1.0, 2.0))


def test_naive_timestamp_rejected() -> None:
    naive = (datetime(2024, 1, 1), _BASE + timedelta(days=1))
    with pytest.raises(ValueError, match="timezone-aware"):
        make_series(timestamps=naive, values=(1.0, 2.0))


# --- value validation --------------------------------------------------------


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_values_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        make_series(values=(1.0, bad, 2.0))


@pytest.mark.parametrize("bad", ["x", None, object()])
def test_non_numeric_values_rejected(bad: object) -> None:
    with pytest.raises(TypeError):
        make_series(values=(1.0, bad, 2.0))


@pytest.mark.parametrize("bad_values", [(True, 1.0, 2.0), (1.0, False, 2.0)])
def test_boolean_values_rejected(bad_values: tuple[object, ...]) -> None:
    with pytest.raises(TypeError, match="not bool"):
        make_series(values=bad_values)


# --- immutability ------------------------------------------------------------


def test_is_frozen() -> None:
    s = make_series()
    with pytest.raises(AttributeError):
        s.series_id = "OTHER"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        s.values = (1.0,)  # type: ignore[misc]


def test_defensive_copy_of_caller_inputs() -> None:
    timestamps = [_BASE, _BASE + timedelta(days=1)]
    values = [1.0, 2.0]
    s = ObservationSeries(
        series_id="X", unit="u", frequency="1D", timestamps=timestamps, values=values
    )
    timestamps.append(_BASE + timedelta(days=2))
    values.append(3.0)
    assert len(s.timestamps) == 2
    assert len(s.values) == 2


# --- equality ----------------------------------------------------------------


def test_structural_equality() -> None:
    assert make_series() == make_series()
    assert make_series() != make_series(values=(9.9, 9.9, 9.9))
    assert make_series() != make_series(series_id="OTHER")


# --- public API / no regression ----------------------------------------------


def test_public_import_path() -> None:
    from fmis.data import ObservationSeries as Imported

    assert Imported is ObservationSeries


def test_candle_imports_still_work() -> None:
    # ObservationSeries must be purely additive.
    from fmis.data import Candle, CandleSeries

    assert Candle is not None
    assert CandleSeries is not None
