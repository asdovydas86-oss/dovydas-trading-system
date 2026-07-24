"""Strict timestamp-intersection alignment for ObservationSeries.

The first — and currently only — temporal-comparison policy in the
``fmis.alignment`` layer. Alignment is a *policy* concern (how two or more
canonical series are made comparable in time), deliberately separated from the
canonical data models in ``fmis.data`` (what a series *is*). Future siblings of
this policy (as-of joins, resampling, availability-aware, calendar-aware) will
live beside it here. See ADR-0002.

Additive, deterministic, and free of pandas / NumPy. Given two or more
``ObservationSeries``, this computes the exact set of instants present in *every*
input and returns new aligned series restricted to those instants, together with
a transparent diagnostic report.

Scope — strict intersection ONLY. There is deliberately no interpolation,
forward/backward fill, resampling, nearest-match, tolerance, timezone conversion,
frequency conversion, or any numeric calculation. The service relies on the
canonical guarantees ``ObservationSeries`` already enforces (canonical-UTC,
strictly increasing, duplicate-free timestamps; equal-length timestamps/values),
so it does not revalidate input-series internals — it only constructs new,
independently-validated aligned series.

Timestamp / instant-equality policy:
    Every ``ObservationSeries`` timestamp is already a canonical, permanent
    zero-offset UTC instant (enforced at construction — see ADR-0001 and
    ``fmis.data._timeutils``). Two timestamps are therefore "the same" exactly
    when they denote the same absolute instant, and Python's aware-datetime
    equality and hashing give exactly that, with no timezone conversion needed
    here. One instant may still be written with two distinct zero-offset
    representations (``timezone.utc`` vs ``ZoneInfo("UTC")``); those compare and
    hash equal and so intersect correctly. When an instant is common to all
    inputs, the aligned output uses the timestamp OBJECT from the *first* input
    series as the single canonical representation of that instant, for every
    aligned series.

    Because the canonical-UTC contract makes fixed non-zero offsets and DST-aware
    (``zoneinfo``) zones unrepresentable in an ``ObservationSeries``, the DST
    "fall-back" ``fold`` ambiguity that would otherwise threaten set/dict-based
    intersection cannot arise here — it is structurally excluded upstream, not
    merely avoided by convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fmis.data.observation import ObservationSeries

__all__ = [
    "SeriesAlignmentStats",
    "AlignmentReport",
    "AlignmentResult",
    "align_intersection",
]


@dataclass(frozen=True, slots=True)
class SeriesAlignmentStats:
    """Per-series alignment diagnostics (one per input, in input order)."""

    series_id: str
    original_count: int
    aligned_count: int
    dropped_count: int


@dataclass(frozen=True, slots=True)
class AlignmentReport:
    """Immutable, transparent diagnostics for one alignment operation.

    ``common_start`` / ``common_end`` are ``None`` exactly when the intersection
    is empty. ``series_stats`` follows the caller-provided input order.
    """

    input_series_count: int
    aligned_observation_count: int
    common_start: datetime | None
    common_end: datetime | None
    series_stats: tuple[SeriesAlignmentStats, ...]


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    """Aligned series (in input order) plus the diagnostic report."""

    series: tuple[ObservationSeries, ...]
    report: AlignmentReport


def align_intersection(series: tuple[ObservationSeries, ...]) -> AlignmentResult:
    """Align ObservationSeries on the strict intersection of their timestamps.

    See the module docstring for the timestamp/timezone equality policy and the
    (deliberately narrow) scope.

    Complexity: with ``n`` series and ``M`` total observations, building the
    instant→value maps is ``O(M)``; selecting the common instants is
    ``O(m0 · n)`` where ``m0`` is the length of the first series; value selection
    is ``O(|common| · n)``. Overall linear in the input size.

    Raises:
        ValueError: fewer than two series, or duplicate ``series_id`` values.
        TypeError: any input element is not an ``ObservationSeries``.
    """
    inputs = tuple(series)  # defensive: never mutate the caller's collection

    if len(inputs) < 2:
        raise ValueError("align_intersection requires at least two series")
    for index, item in enumerate(inputs):
        if not isinstance(item, ObservationSeries):
            raise TypeError(
                f"series[{index}] must be an ObservationSeries, "
                f"got {type(item).__name__}"
            )
    ids = [s.series_id for s in inputs]
    if len(set(ids)) != len(ids):
        raise ValueError("series_id values must be unique across inputs")

    # instant -> value per series. Keys are unique within a series because its
    # timestamps are strictly increasing (no two entries share an instant).
    value_maps = [dict(zip(s.timestamps, s.values)) for s in inputs]

    # Canonical common instants: the FIRST series' timestamp objects, in order,
    # that are present in every other series. Aware-datetime hash/eq match equal
    # instants regardless of the stored offset.
    other_maps = value_maps[1:]
    common = tuple(
        ts for ts in inputs[0].timestamps if all(ts in m for m in other_maps)
    )

    aligned = tuple(
        ObservationSeries(
            series_id=s.series_id,
            unit=s.unit,
            frequency=s.frequency,
            timestamps=common,
            values=tuple(value_map[ts] for ts in common),
        )
        for s, value_map in zip(inputs, value_maps)
    )

    aligned_count = len(common)
    series_stats = tuple(
        SeriesAlignmentStats(
            series_id=s.series_id,
            original_count=len(s.timestamps),
            aligned_count=aligned_count,
            dropped_count=len(s.timestamps) - aligned_count,
        )
        for s in inputs
    )
    report = AlignmentReport(
        input_series_count=len(inputs),
        aligned_observation_count=aligned_count,
        common_start=common[0] if common else None,
        common_end=common[-1] if common else None,
        series_stats=series_stats,
    )
    return AlignmentResult(series=aligned, report=report)
