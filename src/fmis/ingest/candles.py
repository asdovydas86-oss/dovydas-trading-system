"""Decode untrusted OHLCV candle records into canonical `Candle`/`CandleSeries`.

Three entry points, narrowest first:

    decode_candle(record, index=...)                -> Candle
    decode_candle_series(records, symbol=, timeframe=) -> CandleSeries
    decode_candle_series_from_json(text, ...)       -> CandleSeries

The canonical record shape is exactly `CANDLE_FIELDS` — the field names of
`Candle` itself — no more and no fewer. Renaming a provider's payload into these
names is the caller's job (see the package docstring on the adapter boundary).

Accepted field types (ADR-0005):
  * ``timestamp``  — a ``datetime``, or an ISO-8601 ``str`` carrying an explicit
    UTC offset (``...+00:00`` or ``...Z``). The UTC contract itself is enforced by
    ``Candle`` (ADR-0001); a naive string is parsed successfully here and then
    rejected there.
  * ``symbol`` / ``timeframe`` — ``str``.
  * ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` — ``int`` or ``float``
    (an ``int`` is widened to ``float``); ``bool`` is rejected because it
    subclasses ``int``; numeric **strings are rejected**, since silently parsing
    ``"1e3"`` or ``"1,000"`` is exactly the kind of repair this layer must not do.
  * ``is_closed`` — ``bool`` only; ``0``/``1`` are rejected, because a forming bar
    misread as closed silently corrupts every downstream signal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final

from fmis.data import Candle, CandleSeries

__all__ = [
    "decode_candle",
    "decode_candle_series",
    "decode_candle_series_from_json",
    "CANDLE_FIELDS",
    "IngestError",
    "RecordDecodeError",
    "SeriesDecodeError",
]

#: The exact set of keys a canonical candle record must carry.
CANDLE_FIELDS: Final[tuple[str, ...]] = (
    "timestamp",
    "symbol",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "is_closed",
)

_NUMERIC_FIELDS: Final[tuple[str, ...]] = ("open", "high", "low", "close", "volume")
_TEXT_FIELDS: Final[tuple[str, ...]] = ("symbol", "timeframe")


class IngestError(Exception):
    """Base class for every ingestion-boundary failure."""


class RecordDecodeError(IngestError, ValueError):
    """One record could not be decoded into a `Candle`.

    Carries the record's ``index`` in the payload and, when the failure is
    attributable to one field, its ``field`` name.
    """

    def __init__(self, message: str, *, index: int, field: str | None = None) -> None:
        self.index = index
        self.field = field
        where = f"record {index}"
        if field is not None:
            where += f" field {field!r}"
        super().__init__(f"{where}: {message}")


class SeriesDecodeError(IngestError, ValueError):
    """Records decoded individually but do not form a valid `CandleSeries`.

    Raised for series-level invariants: a heterogeneous symbol/timeframe, or
    timestamps that are not strictly increasing. ``index`` locates the first
    offending record when one can be identified.
    """

    def __init__(self, message: str, *, index: int | None = None) -> None:
        self.index = index
        prefix = "" if index is None else f"record {index}: "
        super().__init__(f"{prefix}{message}")


def _decode_timestamp(value: object, *, index: int) -> datetime:
    """A ``datetime`` passes through; an ISO-8601 string is parsed, never coerced."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise RecordDecodeError(
            f"must be a datetime or an ISO-8601 string, got {type(value).__name__}",
            index=index,
            field="timestamp",
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecordDecodeError(
            f"{value!r} is not a valid ISO-8601 timestamp", index=index,
            field="timestamp",
        ) from exc


def _decode_number(value: object, *, index: int, field: str) -> float:
    """Accept ``int``/``float`` (widening ``int``); reject ``bool`` and strings."""
    # bool subclasses int, so it must be rejected before the numeric check.
    if isinstance(value, bool):
        raise RecordDecodeError("must be a number, not bool", index=index, field=field)
    if not isinstance(value, (int, float)):
        raise RecordDecodeError(
            f"must be an int or float, got {type(value).__name__} "
            "(numeric strings are not parsed at this boundary)",
            index=index,
            field=field,
        )
    return float(value)


def decode_candle(record: Mapping[str, Any], *, index: int = 0) -> Candle:
    """Decode one canonical record into a validated `Candle`.

    ``record`` must be a mapping whose keys are exactly `CANDLE_FIELDS`. ``index``
    is the record's position in its payload and appears in every error message;
    it does not affect decoding.

    Raises `RecordDecodeError` for a non-mapping record, a missing or unexpected
    key, a wrong field type, or any `Candle` invariant violation (non-finite or
    negative price, inconsistent OHLC ordering, non-UTC timestamp). The original
    model error is preserved as ``__cause__``.
    """
    if not isinstance(record, Mapping):
        raise RecordDecodeError(
            f"must be a mapping, got {type(record).__name__}", index=index
        )

    keys = set(record)
    missing = [f for f in CANDLE_FIELDS if f not in keys]
    if missing:
        raise RecordDecodeError(
            f"missing required field(s): {', '.join(missing)}", index=index
        )
    unexpected = sorted(keys - set(CANDLE_FIELDS))
    if unexpected:
        raise RecordDecodeError(
            f"unexpected field(s): {', '.join(unexpected)} "
            "(map provider fields to the canonical names before decoding)",
            index=index,
        )

    for field in _TEXT_FIELDS:
        if not isinstance(record[field], str):
            raise RecordDecodeError(
                f"must be a str, got {type(record[field]).__name__}",
                index=index,
                field=field,
            )
    if not isinstance(record["is_closed"], bool):
        raise RecordDecodeError(
            f"must be a bool, got {type(record['is_closed']).__name__} "
            "(0/1 are not accepted)",
            index=index,
            field="is_closed",
        )

    timestamp = _decode_timestamp(record["timestamp"], index=index)
    numbers = {
        field: _decode_number(record[field], index=index, field=field)
        for field in _NUMERIC_FIELDS
    }

    # `Candle` stays the single authority on the domain invariants; re-raise its
    # error with the record's position so a bad row is findable in a big payload.
    try:
        return Candle(
            timestamp=timestamp,
            symbol=record["symbol"],
            timeframe=record["timeframe"],
            is_closed=record["is_closed"],
            **numbers,
        )
    except (ValueError, TypeError) as exc:
        raise RecordDecodeError(str(exc), index=index) from exc


def decode_candle_series(
    records: Iterable[Mapping[str, Any]],
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> CandleSeries:
    """Decode an ordered payload of canonical records into a `CandleSeries`.

    Records are decoded in the order supplied and are **never** sorted,
    deduplicated, or filtered — including by ``is_closed``; call
    `CandleSeries.closed` if only completed bars are wanted.

    ``symbol`` and ``timeframe`` declare the expected series identity. When given,
    a record disagreeing with them is an error rather than a silent regrouping.
    When omitted, identity is taken from the first record, and every later record
    must still match it. Decoding an empty payload therefore requires both to be
    supplied explicitly, since an empty series has no record to take identity from.

    Raises `RecordDecodeError` from the offending record, or `SeriesDecodeError`
    if the records do not form a valid series (mixed identity, or timestamps that
    are not strictly increasing).
    """
    candles = [decode_candle(record, index=i) for i, record in enumerate(records)]

    if symbol is None or timeframe is None:
        if not candles:
            raise SeriesDecodeError(
                "cannot decode an empty payload without an explicit "
                "symbol and timeframe"
            )
        symbol = candles[0].symbol if symbol is None else symbol
        timeframe = candles[0].timeframe if timeframe is None else timeframe

    try:
        return CandleSeries(symbol=symbol, timeframe=timeframe, candles=tuple(candles))
    except ValueError as exc:
        index = _first_offending_index(candles, symbol, timeframe)
        raise SeriesDecodeError(str(exc), index=index) from exc


def _first_offending_index(
    candles: list[Candle], symbol: str, timeframe: str
) -> int | None:
    """Locate the first record that breaks a series invariant, for diagnostics only.

    `CandleSeries` remains the authority on whether the series is valid; this runs
    only after it has already rejected the series, to point at a record index.
    """
    previous: datetime | None = None
    for index, candle in enumerate(candles):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            return index
        if previous is not None and candle.timestamp <= previous:
            return index
        previous = candle.timestamp
    return None


def decode_candle_series_from_json(
    text: str | bytes,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> CandleSeries:
    """Decode a JSON array of canonical candle records into a `CandleSeries`.

    A thin, dependency-free wrapper over `decode_candle_series`: the JSON payload
    must be a top-level array of objects. Raises `IngestError` for malformed JSON
    or a non-array top level, and otherwise the same errors as
    `decode_candle_series`.
    """
    try:
        payload = json.loads(text)
    except ValueError as exc:  # json.JSONDecodeError subclasses ValueError
        raise IngestError(f"payload is not valid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise IngestError(
            "payload must be a JSON array of candle records, "
            f"got {type(payload).__name__}"
        )

    return decode_candle_series(payload, symbol=symbol, timeframe=timeframe)
