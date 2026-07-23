"""Tests for the strict-intersection alignment service (fmis.data.alignment)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from fmis.data import ObservationSeries
from fmis.data.alignment import (
    AlignmentReport,
    AlignmentResult,
    SeriesAlignmentStats,
    align_intersection,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _day(n: int) -> datetime:
    return _BASE + timedelta(days=n)


def obs(
    series_id: str,
    day_offsets: list[int],
    values: list[float],
    *,
    unit: str = "u",
    frequency: str = "1D",
) -> ObservationSeries:
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency=frequency,
        timestamps=tuple(_day(d) for d in day_offsets),
        values=tuple(values),
    )


# --- overlap scenarios -------------------------------------------------------


def test_two_fully_overlapping() -> None:
    a = obs("A", [0, 1, 2], [1.0, 2.0, 3.0])
    b = obs("B", [0, 1, 2], [4.0, 5.0, 6.0])
    result = align_intersection((a, b))
    assert result.report.aligned_observation_count == 3
    assert result.series[0].timestamps == (_day(0), _day(1), _day(2))
    assert result.series[0].values == (1.0, 2.0, 3.0)
    assert result.series[1].values == (4.0, 5.0, 6.0)


def test_two_partially_overlapping() -> None:
    a = obs("A", [0, 1, 2, 3], [1.0, 2.0, 3.0, 4.0])
    b = obs("B", [2, 3, 4, 5], [5.0, 6.0, 7.0, 8.0])
    result = align_intersection((a, b))
    assert result.report.aligned_observation_count == 2
    assert result.series[0].timestamps == (_day(2), _day(3))
    assert result.series[0].values == (3.0, 4.0)  # a's values at days 2,3
    assert result.series[1].values == (5.0, 6.0)  # b's values at days 2,3
    assert result.report.common_start == _day(2)
    assert result.report.common_end == _day(3)


def test_three_partially_overlapping() -> None:
    a = obs("A", [0, 1, 2, 3], [10.0, 11.0, 12.0, 13.0])
    b = obs("B", [1, 2, 3, 4], [20.0, 21.0, 22.0, 23.0])
    c = obs("C", [2, 3, 9], [30.0, 31.0, 32.0])
    result = align_intersection((a, b, c))
    assert result.report.aligned_observation_count == 2  # days 2,3
    assert result.series[0].values == (12.0, 13.0)
    assert result.series[1].values == (21.0, 22.0)
    assert result.series[2].values == (30.0, 31.0)
    assert result.series[0].timestamps == (_day(2), _day(3))


def test_no_common_timestamps() -> None:
    a = obs("A", [0, 1], [1.0, 2.0])
    b = obs("B", [5, 6], [3.0, 4.0])
    result = align_intersection((a, b))
    assert result.report.aligned_observation_count == 0
    assert result.series[0].timestamps == ()
    assert result.series[1].values == ()
    assert result.report.common_start is None
    assert result.report.common_end is None


# --- empty inputs ------------------------------------------------------------


def test_one_empty_input_series() -> None:
    a = obs("A", [], [])
    b = obs("B", [0, 1], [1.0, 2.0])
    result = align_intersection((a, b))
    assert result.report.aligned_observation_count == 0
    stats = {s.series_id: s for s in result.report.series_stats}
    assert stats["A"].original_count == 0 and stats["A"].dropped_count == 0
    assert stats["B"].original_count == 2 and stats["B"].dropped_count == 2


def test_multiple_empty_input_series() -> None:
    result = align_intersection((obs("A", [], []), obs("B", [], [])))
    assert result.report.aligned_observation_count == 0
    assert result.report.common_start is None
    assert all(s.timestamps == () for s in result.series)


# --- order / metadata preservation -------------------------------------------


def test_preserves_input_series_order() -> None:
    z = obs("Z", [0, 1], [1.0, 2.0])
    a = obs("A", [0, 1], [3.0, 4.0])
    result = align_intersection((z, a))
    assert [s.series_id for s in result.series] == ["Z", "A"]
    assert [s.series_id for s in result.report.series_stats] == ["Z", "A"]


def test_preserves_id_unit_frequency() -> None:
    a = obs("A", [0, 1], [1.0, 2.0], unit="usd", frequency="1M")
    b = obs("B", [0, 1], [3.0, 4.0], unit="ratio", frequency="1W")
    result = align_intersection((a, b))
    assert (result.series[0].series_id, result.series[0].unit,
            result.series[0].frequency) == ("A", "usd", "1M")
    assert (result.series[1].series_id, result.series[1].unit,
            result.series[1].frequency) == ("B", "ratio", "1W")


def test_value_selection_matches_timestamps_not_positions() -> None:
    a = obs("A", [0, 5, 10], [100.0, 200.0, 300.0])
    b = obs("B", [5, 10, 15], [1.0, 2.0, 3.0])
    result = align_intersection((a, b))
    assert result.series[0].timestamps == (_day(5), _day(10))
    assert result.series[0].values == (200.0, 300.0)
    assert result.series[1].values == (1.0, 2.0)


# --- immutability / non-mutation ---------------------------------------------


def test_inputs_are_not_mutated() -> None:
    a = obs("A", [0, 1, 2], [1.0, 2.0, 3.0])
    b = obs("B", [1, 2, 3], [4.0, 5.0, 6.0])
    align_intersection((a, b))
    assert a == obs("A", [0, 1, 2], [1.0, 2.0, 3.0])
    assert b == obs("B", [1, 2, 3], [4.0, 5.0, 6.0])


def test_caller_collection_is_not_mutated() -> None:
    a = obs("A", [0, 1], [1.0, 2.0])
    b = obs("B", [0, 1], [3.0, 4.0])
    collection = [a, b]
    align_intersection(collection)  # type: ignore[arg-type]
    assert collection == [a, b]


def test_result_and_report_are_immutable() -> None:
    result = align_intersection((obs("A", [0], [1.0]), obs("B", [0], [2.0])))
    with pytest.raises(AttributeError):
        result.series = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.report.common_start = None  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.report.series_stats[0].original_count = 99  # type: ignore[misc]


# --- report correctness ------------------------------------------------------


def test_report_counts_are_correct() -> None:
    a = obs("A", [0, 1, 2, 3], [1.0, 2.0, 3.0, 4.0])
    b = obs("B", [2, 3, 4], [5.0, 6.0, 7.0])
    report = align_intersection((a, b)).report
    assert report.input_series_count == 2
    assert report.aligned_observation_count == 2
    by_id = {s.series_id: s for s in report.series_stats}
    assert by_id["A"].original_count == 4 and by_id["A"].aligned_count == 2
    assert by_id["A"].dropped_count == 2  # 4 - 2
    assert by_id["B"].original_count == 3 and by_id["B"].aligned_count == 2
    assert by_id["B"].dropped_count == 1  # 3 - 2
    # aligned_count identical for every series, and dropped == original - aligned
    assert all(s.aligned_count == report.aligned_observation_count
               for s in report.series_stats)
    assert all(s.dropped_count == s.original_count - s.aligned_count
               for s in report.series_stats)


def test_common_boundaries_none_when_empty() -> None:
    report = align_intersection((obs("A", [0], [1.0]), obs("B", [9], [2.0]))).report
    assert report.common_start is None
    assert report.common_end is None


# --- rejection rules ---------------------------------------------------------


@pytest.mark.parametrize("bad", [(), (obs("A", [0], [1.0]),)])
def test_fewer_than_two_series_rejected(bad: tuple) -> None:
    with pytest.raises(ValueError, match="at least two series"):
        align_intersection(bad)


def test_non_observation_series_rejected() -> None:
    a = obs("A", [0], [1.0])
    with pytest.raises(TypeError, match="must be an ObservationSeries"):
        align_intersection((a, "not a series"))  # type: ignore[arg-type]


def test_duplicate_series_id_rejected() -> None:
    a = obs("DUP", [0], [1.0])
    b = obs("DUP", [0], [2.0])
    with pytest.raises(ValueError, match="unique"):
        align_intersection((a, b))


# --- public imports / no regression ------------------------------------------


def test_public_import_path() -> None:
    from fmis.data import (
        AlignmentReport as R,
        AlignmentResult as Res,
        SeriesAlignmentStats as S,
        align_intersection as fn,
    )

    assert fn is align_intersection
    assert R is AlignmentReport and Res is AlignmentResult and S is SeriesAlignmentStats


def test_candle_and_observation_imports_unaffected() -> None:
    from fmis.data import Candle, CandleSeries, ObservationSeries as OS

    assert Candle is not None and CandleSeries is not None
    assert OS is ObservationSeries


# --- timezone / instant equality policy --------------------------------------


def test_same_instant_two_utc_representations_intersect() -> None:
    # Migrated for the canonical UTC-only contract: the same instant expressed
    # with two distinct zero-offset representations (timezone.utc vs ZoneInfo).
    utc_tz = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    utc_zi = datetime(2026, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
    assert utc_tz == utc_zi  # same instant, different tzinfo objects

    a = ObservationSeries("A", "u", "1D", (utc_tz,), (1.0,))
    b = ObservationSeries("B", "u", "1D", (utc_zi,), (2.0,))
    result = align_intersection((a, b))

    assert result.report.aligned_observation_count == 1
    # Canonical rule: aligned timestamps use the FIRST input's object, for all series.
    assert result.series[0].timestamps[0] is utc_tz
    assert result.series[1].timestamps[0] is utc_tz
    assert result.series[0].values == (1.0,)
    assert result.series[1].values == (2.0,)


def test_non_utc_observation_series_rejected_by_contract() -> None:
    # Migrated: the old "same wall-clock, different offset -> different instant"
    # scenario is unreachable under the UTC-only contract, because a non-UTC
    # ObservationSeries cannot be constructed. (Genuinely different instants not
    # intersecting is covered by test_no_common_timestamps.)
    plus_one = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=1)))
    with pytest.raises(ValueError, match="must represent UTC"):
        ObservationSeries("A", "u", "1D", (plus_one,), (1.0,))
