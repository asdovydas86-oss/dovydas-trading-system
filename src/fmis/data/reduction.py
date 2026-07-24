"""Pure reduction of a `CandleSeries` to an `ObservationSeries`.

A `CandleSeries` is a multi-field OHLCV object; an `ObservationSeries` is a
single stream of timestamped numeric values. Relating a price series to another
series (the job of the future Relative Value Engine) needs the latter shape, so
this module reduces one explicitly chosen candle field to an `ObservationSeries`.

Two deliberate design choices:

  * **No implicit field.** The caller must name the field via the ``CandleField``
    enum — there is no default, and a raw string or any non-``CandleField`` value
    is rejected with ``TypeError``. This makes "which price did this series use?"
    always explicit and makes a silent wrong-field mistake hard to commit.
  * **Closed candles only.** Reduction runs over ``series.closed()``, mirroring
    the Feature Engine, so a still-forming bar can never leak into a series that
    downstream deterministic math depends on. An all-forming (or empty) input
    therefore yields an empty — but valid — ``ObservationSeries``.

This is a pure domain transform: it selects a field and carries the canonical
timestamps across unchanged. It performs no policy (no alignment, no fill, no
resampling), no I/O, and no unit or timezone conversion — the canonical-UTC
timestamps are reused as-is.
"""

from __future__ import annotations

from enum import Enum

from fmis.data.models import CandleSeries
from fmis.data.observation import ObservationSeries

__all__ = ["CandleField", "candle_series_to_observations"]


class CandleField(str, Enum):
    """The single candle field a reduction reads. No default — always explicit.

    Each member's value is the corresponding ``Candle`` attribute name, so the
    value doubles as the attribute accessor. ``str`` base makes members usable in
    deterministic string identifiers (e.g. a derived ``series_id``).
    """

    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    VOLUME = "volume"


# Dimension recorded as the ObservationSeries `unit`. Price fields share one unit
# so a later ratio of two price-derived series is meaningful; volume is distinct
# so a price/volume ratio can be refused by a unit-aware consumer (see RVE design).
_PRICE_FIELDS = frozenset(
    {CandleField.OPEN, CandleField.HIGH, CandleField.LOW, CandleField.CLOSE}
)


def candle_series_to_observations(
    series: CandleSeries,
    field: CandleField,
    *,
    series_id: str | None = None,
) -> ObservationSeries:
    """Reduce one field of ``series`` to an ``ObservationSeries``.

    Args:
        series: the candle series to reduce.
        field: which candle field becomes the observation value. **Required**;
            must be a ``CandleField`` (no default, no string coercion).
        series_id: optional explicit identity. If omitted, a deterministic id
            ``"{symbol}.{field}.{timeframe}"`` (e.g. ``"BTCUSDT.close.4H"``) is
            derived from the series.

    Returns:
        An ``ObservationSeries`` over the **closed** candles of ``series``: the
        canonical timestamps unchanged, the chosen field as values, ``unit`` set
        to ``"price"`` for OHLC fields or ``"volume"`` for volume, and
        ``frequency`` set to the series timeframe.

    Raises:
        TypeError: ``series`` is not a ``CandleSeries`` or ``field`` is not a
            ``CandleField``.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(
            f"series must be a CandleSeries, got {type(series).__name__}"
        )
    # bool is not a CandleField; the isinstance guard also rejects raw strings,
    # which is the point — the field must be named through the enum.
    if not isinstance(field, CandleField):
        raise TypeError(
            f"field must be a CandleField, got {type(field).__name__}"
        )

    closed = series.closed()
    timestamps = tuple(candle.timestamp for candle in closed.candles)
    values = tuple(getattr(candle, field.value) for candle in closed.candles)

    resolved_id = (
        series_id
        if series_id is not None
        else f"{series.symbol}.{field.value}.{series.timeframe}"
    )
    unit = "price" if field in _PRICE_FIELDS else "volume"

    return ObservationSeries(
        series_id=resolved_id,
        unit=unit,
        frequency=series.timeframe,
        timestamps=timestamps,
        values=values,
    )
