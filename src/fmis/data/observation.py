"""Canonical observation-series data contract.

An ``ObservationSeries`` is an immutable, validated series of timestamped numeric
observations that are *not* OHLCV candles — for example macroeconomic prints,
on-chain metrics, derivatives metrics, sentiment scores, market breadth,
liquidity measures, benchmark/index levels, or (later) relative-value outputs.

This milestone (I-A) implements ONLY the reusable canonical model. It contains no
alignment, resampling, interpolation, forward-filling, indicators, relative-value
math, serialization, or provider logic — those belong to later milestones.

Conventions mirror the OHLCV contract in ``fmis.data.models`` (frozen slotted
dataclass, tuple-normalized immutable state, timezone-aware strictly-increasing
timestamps, no silent sorting/dedup/coercion). Two deliberate differences, driven
by the domain rather than preference:

  * Values MAY be negative. Observations such as real yields, net flows, or
    z-scores are legitimately negative, unlike prices/volume. Values are only
    required to be finite.
  * ``bool`` is explicitly rejected as a value. A boolean is not a numeric
    observation, and Python treats ``bool`` as a subclass of ``int``; rejecting
    it prevents ``True``/``False`` from silently entering a numeric series.

The representation is parallel arrays (``timestamps`` and ``values`` of equal
length) rather than a tuple of observation objects, because equal-length aligned
arrays are the natural substrate for the alignment work in a later milestone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

__all__ = ["ObservationSeries"]


def _is_timezone_aware(ts: datetime) -> bool:
    """Return True only if `ts` carries a concrete UTC offset.

    Mirrors the identical predicate in ``fmis.data.models``; duplicated as a
    trivial pure helper to keep this module additive (no import of a sibling's
    private name, no refactor of the OHLCV contract).
    """
    return ts.tzinfo is not None and ts.tzinfo.utcoffset(ts) is not None


@dataclass(frozen=True, slots=True)
class ObservationSeries:
    """An ordered series of timestamped numeric observations for one metric.

    ``series_id`` is the stable identity of the metric (the analogue of a
    candle series' symbol+timeframe). ``unit`` and ``frequency`` are descriptive
    metadata. ``timestamps`` and ``values`` are parallel, equal-length, and
    normalized to immutable tuples; timestamps must be timezone-aware and
    strictly increasing (no duplicates, no backward steps). An empty series
    (no observations) is valid.
    """

    series_id: str
    unit: str
    frequency: str
    timestamps: tuple[datetime, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.series_id or not self.series_id.strip():
            raise ValueError("series_id cannot be empty")
        if not self.unit or not self.unit.strip():
            raise ValueError("unit cannot be empty")
        if not self.frequency or not self.frequency.strip():
            raise ValueError("frequency cannot be empty")

        # Accept any iterable at construction; store immutable tuples so a
        # caller mutating the original inputs cannot mutate this series.
        object.__setattr__(self, "timestamps", tuple(self.timestamps))
        object.__setattr__(self, "values", tuple(self.values))

        if len(self.timestamps) != len(self.values):
            raise ValueError(
                "timestamps and values must have equal length "
                f"({len(self.timestamps)} != {len(self.values)})"
            )

        for index, value in enumerate(self.values):
            # bool is a subclass of int — reject it before the numeric check.
            if isinstance(value, bool):
                raise TypeError(f"value at index {index} must be numeric, not bool")
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"value at index {index} must be int or float, "
                    f"got {type(value).__name__}"
                )
            if not math.isfinite(value):
                raise ValueError(f"value at index {index} must be a finite number")

        previous: datetime | None = None
        for index, ts in enumerate(self.timestamps):
            if not isinstance(ts, datetime):
                raise TypeError(f"timestamp at index {index} must be a datetime")
            if not _is_timezone_aware(ts):
                raise ValueError(f"timestamp at index {index} must be timezone-aware")
            if previous is not None and ts <= previous:
                raise ValueError("timestamps must be strictly increasing")
            previous = ts
