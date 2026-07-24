"""Deterministic Relative Value metrics (v1a) — pure functions over aligned series.

Five scalar metrics, all deterministic, reproducible, stdlib-only:

    period_return(series)              P_last / P_first - 1
    relative_return(left, right)       (1 + R_left) / (1 + R_right) - 1
    realized_volatility(series)        sample stdev of simple returns (Bessel)
    volatility_ratio(left, right)      vol(left) / vol(right)
    pearson_correlation(left, right)   Pearson corr of aligned simple-return series

Conventions fixed for v1a (ADR-0004):
  * **Simple returns only**: ``r_t = P_t / P_{t-1} - 1``. No log returns.
  * **No annualization** and **no frequency inference** — ``series_id`` and the
    ``frequency`` label are never parsed; every result carries
    ``annualized = False``.
  * **Alignment is upstream and explicit.** These functions never align, fill,
    resample, or drop. Pairwise metrics require ``left.timestamps ==
    right.timestamps`` and equal length, else ``NotAlignedError``.
  * **Hybrid result policy** (models.py): structural failures raise; a
    mathematically undefined result returns an ``UNDEFINED`` ``RelativeValueResult``.

Ordering for pairwise metrics: ``left`` is the subject / numerator, ``right`` the
reference / denominator; the supplied order is preserved in metadata even where
the value is symmetric (correlation).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fmis.data import ObservationSeries
from fmis.relative_value.models import (
    InsufficientObservationsError,
    NotAlignedError,
    RelativeValueResult,
    UndefinedReason,
)

__all__ = [
    "period_return",
    "relative_return",
    "realized_volatility",
    "volatility_ratio",
    "pearson_correlation",
]

# ------------------------------------------------------------------ helpers ---


def _require_series(obj: object, param: str) -> None:
    if not isinstance(obj, ObservationSeries):
        raise TypeError(
            f"{param} must be an ObservationSeries, got {type(obj).__name__}"
        )


def _require_aligned(left: object, right: object) -> None:
    """Both must be ObservationSeries, equal length, identical timestamps.

    Never aligns; a mismatch is a caller error raised as ``NotAlignedError``.
    """
    _require_series(left, "left")
    _require_series(right, "right")
    assert isinstance(left, ObservationSeries)  # for type-checkers
    assert isinstance(right, ObservationSeries)
    if len(left.timestamps) != len(right.timestamps):
        raise NotAlignedError(
            "left and right must have equal length "
            f"({len(left.timestamps)} != {len(right.timestamps)}); "
            "align upstream before calling the RVE"
        )
    if left.timestamps != right.timestamps:
        raise NotAlignedError(
            "left and right timestamps must be identical; align upstream "
            "(the RVE never aligns, intersects, fills, or drops observations)"
        )


def _simple_returns(values: Sequence[float]) -> list[float] | None:
    """Simple returns ``r_t = v_t / v_{t-1} - 1``.

    Returns ``None`` if any prior value is zero (a zero denominator makes the
    return sequence undefined); the caller maps that to an UNDEFINED result.
    Length of the result is ``len(values) - 1``.
    """
    out: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev == 0:
            return None
        out.append(cur / prev - 1.0)
    return out


def _sample_stdev(xs: Sequence[float]) -> float:
    """Bessel-corrected (N-1) sample standard deviation. Requires len(xs) >= 2."""
    n = len(xs)
    mean = math.fsum(xs) / n
    ss = math.fsum((x - mean) ** 2 for x in xs)
    return math.sqrt(ss / (n - 1))


def _span(series: ObservationSeries) -> tuple[datetime | None, datetime | None]:
    if not series.timestamps:
        return None, None
    return series.timestamps[0], series.timestamps[-1]


def _base_metadata(
    metric: str,
    *,
    series_ids: tuple[str, ...],
    units: tuple[str, ...],
    observation_count: int,
    span: tuple[datetime | None, datetime | None],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    md: dict[str, Any] = {
        "metric_name": metric,
        "source_series_ids": series_ids,
        "units": units,
        "observation_count": observation_count,
        "start_timestamp": span[0],
        "end_timestamp": span[1],
        "return_convention": "simple",
        "annualized": False,
        "formula": f"{metric}@1",
    }
    if extra:
        md.update(extra)
    return md


# ------------------------------------------------------------------ metrics ---


def period_return(series: ObservationSeries) -> RelativeValueResult:
    """``P_last / P_first - 1`` over a single series. Min observations: 2.

    Undefined: ``ZERO_DENOMINATOR`` if ``P_first == 0``; ``NON_FINITE_RESULT`` if
    the computed value is not finite.
    """
    name = "period_return"
    _require_series(series, "series")
    n = len(series.values)
    if n < 2:
        raise InsufficientObservationsError(metric=name, required=2, actual=n)

    md = _base_metadata(
        name,
        series_ids=(series.series_id,),
        units=(series.unit,),
        observation_count=n,
        span=_span(series),
    )

    first, last = series.values[0], series.values[-1]
    if first == 0:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)
    value = last / first - 1.0
    if not math.isfinite(value):
        return RelativeValueResult.undefined(name, UndefinedReason.NON_FINITE_RESULT, md)
    return RelativeValueResult.ok(name, value, md)


def relative_return(
    left: ObservationSeries, right: ObservationSeries
) -> RelativeValueResult:
    """``(1 + R_left) / (1 + R_right) - 1`` where ``R = P_last / P_first - 1``.

    Min observations: 2 per aligned series. ``left`` is the subject, ``right`` the
    reference. Undefined: ``ZERO_DENOMINATOR`` if either first price is 0 (period
    return undefined) or ``1 + R_right == 0`` (i.e. ``right`` last price is 0);
    ``NON_FINITE_RESULT`` otherwise-non-finite.
    """
    name = "relative_return"
    _require_aligned(left, right)
    n = len(left.values)
    if n < 2:
        raise InsufficientObservationsError(metric=name, required=2, actual=n)

    md = _base_metadata(
        name,
        series_ids=(left.series_id, right.series_id),
        units=(left.unit, right.unit),
        observation_count=n,
        span=_span(left),
    )

    lf, ll = left.values[0], left.values[-1]
    rf, rl = right.values[0], right.values[-1]
    if lf == 0 or rf == 0:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)
    growth_left = ll / lf          # == 1 + R_left
    growth_right = rl / rf         # == 1 + R_right
    if growth_right == 0:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)
    value = growth_left / growth_right - 1.0
    if not math.isfinite(value):
        return RelativeValueResult.undefined(name, UndefinedReason.NON_FINITE_RESULT, md)
    return RelativeValueResult.ok(name, value, md)


def realized_volatility(series: ObservationSeries) -> RelativeValueResult:
    """Sample standard deviation (Bessel, N-1) of simple returns. No annualization.

    Min price observations: 3 (so at least 2 returns). Undefined:
    ``ZERO_DENOMINATOR`` if any interior price is 0; ``NON_FINITE_RESULT`` if
    non-finite. A constant series yields ``0.0`` (a defined, OK result).
    """
    name = "realized_volatility"
    _require_series(series, "series")
    n = len(series.values)
    if n < 3:
        raise InsufficientObservationsError(metric=name, required=3, actual=n)

    returns = _simple_returns(series.values)
    m = 0 if returns is None else len(returns)
    md = _base_metadata(
        name,
        series_ids=(series.series_id,),
        units=(series.unit,),
        observation_count=n,
        span=_span(series),
        extra={"return_observation_count": m, "standard_deviation": "sample_bessel"},
    )

    if returns is None:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)
    value = _sample_stdev(returns)
    if not math.isfinite(value):
        return RelativeValueResult.undefined(name, UndefinedReason.NON_FINITE_RESULT, md)
    return RelativeValueResult.ok(name, value, md)


def volatility_ratio(
    left: ObservationSeries, right: ObservationSeries
) -> RelativeValueResult:
    """``vol(left) / vol(right)`` of simple-return sample stdevs. Min obs: 3.

    ``left`` is the subject, ``right`` the reference (denominator). Undefined:
    ``ZERO_DENOMINATOR`` if either series has an interior zero price;
    ``ZERO_REFERENCE_VOLATILITY`` if ``vol(right) == 0``; ``NON_FINITE_RESULT``
    otherwise-non-finite.
    """
    name = "volatility_ratio"
    _require_aligned(left, right)
    n = len(left.values)
    if n < 3:
        raise InsufficientObservationsError(metric=name, required=3, actual=n)

    ret_left = _simple_returns(left.values)
    ret_right = _simple_returns(right.values)
    m = 0 if ret_left is None else len(ret_left)
    md = _base_metadata(
        name,
        series_ids=(left.series_id, right.series_id),
        units=(left.unit, right.unit),
        observation_count=n,
        span=_span(left),
        extra={"return_observation_count": m, "standard_deviation": "sample_bessel"},
    )

    if ret_left is None or ret_right is None:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)
    vol_left = _sample_stdev(ret_left)
    vol_right = _sample_stdev(ret_right)
    if vol_right == 0:
        return RelativeValueResult.undefined(
            name, UndefinedReason.ZERO_REFERENCE_VOLATILITY, md
        )
    value = vol_left / vol_right
    if not math.isfinite(value):
        return RelativeValueResult.undefined(name, UndefinedReason.NON_FINITE_RESULT, md)
    return RelativeValueResult.ok(name, value, md)


def pearson_correlation(
    left: ObservationSeries, right: ObservationSeries
) -> RelativeValueResult:
    """Pearson correlation of the two aligned simple-return sequences. Min obs: 3.

    The value is symmetric in the two series, but the supplied ``left``/``right``
    order is preserved in metadata. Undefined: ``ZERO_DENOMINATOR`` if either
    series has an interior zero price; ``ZERO_VARIANCE`` if either return series
    is constant; ``NON_FINITE_RESULT`` otherwise-non-finite. The value is clamped
    to ``[-1, 1]`` to absorb floating-point drift.
    """
    name = "pearson_correlation"
    _require_aligned(left, right)
    n = len(left.values)
    if n < 3:
        raise InsufficientObservationsError(metric=name, required=3, actual=n)

    a = _simple_returns(left.values)
    b = _simple_returns(right.values)
    m = 0 if a is None else len(a)
    md = _base_metadata(
        name,
        series_ids=(left.series_id, right.series_id),
        units=(left.unit, right.unit),
        observation_count=n,
        span=_span(left),
        extra={"return_observation_count": m, "symmetric": True},
    )

    if a is None or b is None:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_DENOMINATOR, md)

    mean_a = math.fsum(a) / m
    mean_b = math.fsum(b) / m
    sxx = math.fsum((x - mean_a) ** 2 for x in a)
    syy = math.fsum((y - mean_b) ** 2 for y in b)
    if sxx == 0 or syy == 0:
        return RelativeValueResult.undefined(name, UndefinedReason.ZERO_VARIANCE, md)
    sxy = math.fsum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    value = sxy / math.sqrt(sxx * syy)
    if not math.isfinite(value):
        return RelativeValueResult.undefined(name, UndefinedReason.NON_FINITE_RESULT, md)
    # Correlation is mathematically bounded; clamp fp drift into [-1, 1].
    value = max(-1.0, min(1.0, value))
    return RelativeValueResult.ok(name, value, md)
