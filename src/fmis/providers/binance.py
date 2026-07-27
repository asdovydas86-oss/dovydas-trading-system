"""Binance public spot klines → canonical `CandleSeries`.

Uses the public `GET /api/v3/klines` endpoint, which needs **no API key** and no
authentication. Nothing in this module signs a request, reads a credential, or
touches a private, account, or order endpoint.

    from fmis.providers.binance import fetch_klines
    series = fetch_klines("BTCUSDT", "4h", limit=200)

Provider payload shape — each kline is a positional array whose first twelve
entries are the documented contract:

    [0] open time (ms)      [6]  close time (ms)
    [1] open   (string)     [7]  quote asset volume (string)
    [2] high   (string)     [8]  number of trades
    [3] low    (string)     [9]  taker buy base volume (string)
    [4] close  (string)     [10] taker buy quote volume (string)
    [5] volume (string)     [11] unused

Only indices 0–6 are read; the rest are ignored because they have no canonical
home. An array with fewer than twelve entries is malformed and rejected. Extra
trailing entries are tolerated: positions 0–11 are a documented stable prefix, so
an additive change upstream is not a reason to take the pipeline down.

Two provider conventions are translated here, and deliberately nowhere else:

  * **Prices and volume arrive as strings.** `fmis.ingest` rejects numeric strings
    on purpose (ADR-0005 §3); parsing them is the adapter's job, because only the
    adapter knows they are plain decimal and never locale-formatted.
  * **REST klines carry no closed/forming flag** (only the websocket stream does).
    `is_closed` is therefore derived explicitly: a kline is closed when its close
    time has already passed according to an injectable `clock`. It is never
    guessed from position in the array, and the last row is not assumed to be
    forming. See `fetch_klines` for the caveat this carries.

Timestamps are built as exact UTC instants from the integer millisecond epoch, so
the canonical time contract (ADR-0001) holds by construction and is enforced
again by `Candle`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Final, NamedTuple

from fmis.data import CandleSeries
from fmis.ingest import decode_candle_series

__all__ = [
    "fetch_klines",
    "map_kline",
    "build_klines_url",
    "urlopen_transport",
    "HttpResponse",
    "Transport",
    "BINANCE_API_BASE",
    "KLINE_INTERVALS",
    "MAX_LIMIT",
    "BinanceError",
    "BinanceRequestError",
    "BinanceTransportError",
    "BinanceAPIError",
    "BinanceResponseError",
]

BINANCE_API_BASE: Final[str] = "https://api.binance.com"
_KLINES_PATH: Final[str] = "/api/v3/klines"

#: Intervals the endpoint documents. Validated before any network call so a typo
#: fails locally instead of as an opaque provider error.
KLINE_INTERVALS: Final[frozenset[str]] = frozenset(
    {
        "1s", "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M",
    }
)

#: Maximum rows the endpoint returns in one call.
MAX_LIMIT: Final[int] = 1000

_MIN_KLINE_LENGTH: Final[int] = 12
_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=timezone.utc)

# Positional indices actually read from a kline array.
_OPEN_TIME, _OPEN, _HIGH, _LOW, _CLOSE, _VOLUME, _CLOSE_TIME = range(7)
_PRICE_INDICES: Final[tuple[tuple[int, str], ...]] = (
    (_OPEN, "open"),
    (_HIGH, "high"),
    (_LOW, "low"),
    (_CLOSE, "close"),
    (_VOLUME, "volume"),
)


# ------------------------------------------------------------------- errors ---


class BinanceError(Exception):
    """Base class for every failure originating in the Binance adapter."""


class BinanceRequestError(BinanceError, ValueError):
    """Arguments are invalid; raised before any network call is made."""


class BinanceTransportError(BinanceError):
    """The request could not be completed (DNS, connection, timeout, TLS)."""


class BinanceAPIError(BinanceError):
    """Binance answered with an error — a non-2xx status, an error payload, or both.

    ``status`` is the HTTP status. ``code`` and ``message`` are Binance's own
    error fields when the body carried them (e.g. ``-1121`` / ``Invalid symbol.``),
    and ``None`` when it did not.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: int | None = None,
        provider_message: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = provider_message
        super().__init__(message)


class BinanceResponseError(BinanceError, ValueError):
    """The response was accepted by HTTP but is malformed, partial, or ambiguous."""


# ---------------------------------------------------------------- transport ---


class HttpResponse(NamedTuple):
    """A raw HTTP result: the status code and the undecoded body."""

    status: int
    body: bytes


#: A callable taking a URL and returning an `HttpResponse`.
#:
#: It must **not** raise for a non-2xx status — the adapter interprets the status
#: together with the body, because Binance returns its error details in the body
#: of a 4xx. It should raise `BinanceTransportError` when the request could not be
#: completed at all. Injecting one is how the test suite avoids the network.
Transport = Callable[[str], HttpResponse]


def urlopen_transport(url: str, *, timeout: float = 10.0) -> HttpResponse:
    """Default `Transport`, built on `urllib.request` — no third-party dependency.

    Returns the status and body for any HTTP response, including 4xx/5xx, whose
    bodies carry Binance's error details. Raises `BinanceTransportError` only when
    the request could not be completed at all.
    """
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=response.status, body=response.read())
    except urllib.error.HTTPError as exc:  # a response, not a transport failure
        return HttpResponse(status=exc.code, body=exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BinanceTransportError(f"request to {url} failed: {exc}") from exc


# ------------------------------------------------------------------ request ---


def _require_symbol(symbol: object) -> str:
    if not isinstance(symbol, str):
        raise BinanceRequestError(
            f"symbol must be a str, got {type(symbol).__name__}"
        )
    if not symbol:
        raise BinanceRequestError("symbol cannot be empty")
    if not symbol.isalnum() or not symbol.isupper():
        raise BinanceRequestError(
            f"symbol {symbol!r} must be upper-case alphanumeric, e.g. 'BTCUSDT' "
            "(it is not upper-cased for you: a symbol is an exact identifier)"
        )
    return symbol


def _require_interval(interval: object) -> str:
    if not isinstance(interval, str):
        raise BinanceRequestError(
            f"interval must be a str, got {type(interval).__name__}"
        )
    if interval not in KLINE_INTERVALS:
        raise BinanceRequestError(
            f"unsupported interval {interval!r}; expected one of "
            f"{', '.join(sorted(KLINE_INTERVALS))}"
        )
    return interval


def _to_epoch_ms(value: datetime, *, param: str) -> int:
    """Exact epoch milliseconds from any timezone-aware datetime.

    Any aware timezone is unambiguous and converts exactly; a naive datetime has
    no defined instant and is rejected rather than assumed to be UTC.
    """
    if not isinstance(value, datetime):
        raise BinanceRequestError(
            f"{param} must be a datetime, got {type(value).__name__}"
        )
    if value.utcoffset() is None:
        raise BinanceRequestError(
            f"{param} must be timezone-aware (a naive datetime has no defined instant)"
        )
    return round(value.timestamp() * 1000)


def build_klines_url(
    *,
    symbol: str,
    interval: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int | None = None,
    base_url: str = BINANCE_API_BASE,
) -> str:
    """Build the klines request URL, validating every argument first.

    Parameters are emitted in a fixed order so the URL is deterministic and
    directly comparable in tests. Optional parameters are omitted entirely rather
    than sent empty. Raises `BinanceRequestError` for any invalid argument.
    """
    symbol = _require_symbol(symbol)
    interval = _require_interval(interval)

    params: list[tuple[str, str]] = [("symbol", symbol), ("interval", interval)]

    start_ms = (
        None if start_time is None else _to_epoch_ms(start_time, param="start_time")
    )
    end_ms = None if end_time is None else _to_epoch_ms(end_time, param="end_time")
    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise BinanceRequestError("start_time must not be after end_time")
    if start_ms is not None:
        params.append(("startTime", str(start_ms)))
    if end_ms is not None:
        params.append(("endTime", str(end_ms)))

    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise BinanceRequestError(
                f"limit must be an int, got {type(limit).__name__}"
            )
        if not 1 <= limit <= MAX_LIMIT:
            raise BinanceRequestError(
                f"limit must be between 1 and {MAX_LIMIT}, got {limit}"
            )
        params.append(("limit", str(limit)))

    return f"{base_url.rstrip('/')}{_KLINES_PATH}?{urllib.parse.urlencode(params)}"


# ------------------------------------------------------------------ mapping ---


def _parse_number(value: object, *, field: str, index: int) -> float:
    """Parse a Binance numeric field, which arrives as a plain decimal string."""
    if isinstance(value, bool):
        raise BinanceResponseError(f"kline {index}: {field} must be numeric, not bool")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise BinanceResponseError(
            f"kline {index}: {field} must be a string or number, "
            f"got {type(value).__name__}"
        )
    try:
        return float(value)
    except ValueError as exc:
        raise BinanceResponseError(
            f"kline {index}: {field} {value!r} is not a valid number"
        ) from exc


def _parse_epoch_ms(value: object, *, field: str, index: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BinanceResponseError(
            f"kline {index}: {field} must be an integer millisecond epoch, "
            f"got {type(value).__name__}"
        )
    return value


def map_kline(
    raw: Sequence[Any],
    *,
    symbol: str,
    interval: str,
    now_ms: int,
    index: int = 0,
) -> dict[str, Any]:
    """Map one Binance kline array into a canonical `CANDLE_FIELDS` record.

    ``symbol`` and ``interval`` come from the request, because the klines payload
    does not echo them. The interval is used verbatim as the canonical
    ``timeframe`` — it is a provider-native label and is deliberately not
    rewritten into some other casing or vocabulary.

    ``now_ms`` is the reference instant for the closed/forming decision: the kline
    is closed when its close time has already passed. Raises `BinanceResponseError`
    for any malformed entry.
    """
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise BinanceResponseError(
            f"kline {index}: expected an array, got {type(raw).__name__}"
        )
    if len(raw) < _MIN_KLINE_LENGTH:
        raise BinanceResponseError(
            f"kline {index}: expected at least {_MIN_KLINE_LENGTH} fields, "
            f"got {len(raw)}"
        )

    open_time_ms = _parse_epoch_ms(raw[_OPEN_TIME], field="open time", index=index)
    close_time_ms = _parse_epoch_ms(raw[_CLOSE_TIME], field="close time", index=index)
    if close_time_ms < open_time_ms:
        raise BinanceResponseError(
            f"kline {index}: close time {close_time_ms} precedes "
            f"open time {open_time_ms}"
        )

    record: dict[str, Any] = {
        "timestamp": _EPOCH + timedelta(milliseconds=open_time_ms),
        "symbol": symbol,
        "timeframe": interval,
        # A kline is complete only once its close time has passed; REST klines
        # carry no flag of their own, so this is the explicit derivation.
        "is_closed": close_time_ms < now_ms,
    }
    for position, field in _PRICE_INDICES:
        record[field] = _parse_number(raw[position], field=field, index=index)
    return record


# ------------------------------------------------------------------- fetch ----


def _decode_body(body: bytes, *, status: int) -> Any:
    try:
        return json.loads(body)
    except ValueError as exc:
        preview = body[:200].decode("utf-8", errors="replace")
        if 200 <= status < 300:
            raise BinanceResponseError(
                f"response body is not valid JSON: {preview!r}"
            ) from exc
        raise BinanceAPIError(
            f"HTTP {status} with a non-JSON body: {preview!r}", status=status
        ) from exc


def _raise_for_error_payload(payload: Any, *, status: int) -> None:
    """Raise if the payload is a Binance error object, or the status is not 2xx."""
    code: int | None = None
    provider_message: str | None = None
    if isinstance(payload, Mapping) and ("code" in payload or "msg" in payload):
        raw_code = payload.get("code")
        code = raw_code if isinstance(raw_code, int) else None
        raw_msg = payload.get("msg")
        provider_message = raw_msg if isinstance(raw_msg, str) else None
        raise BinanceAPIError(
            f"Binance error (HTTP {status}, code {code}): {provider_message}",
            status=status,
            code=code,
            provider_message=provider_message,
        )
    if not 200 <= status < 300:
        raise BinanceAPIError(f"HTTP {status} from Binance", status=status)


def fetch_klines(
    symbol: str,
    interval: str,
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str = BINANCE_API_BASE,
) -> CandleSeries:
    """Fetch public spot klines and return a canonical `CandleSeries`.

    ``symbol`` is an exact Binance symbol (``"BTCUSDT"``); ``interval`` is one of
    `KLINE_INTERVALS`. ``start_time``/``end_time`` are timezone-aware datetimes.
    ``limit`` caps the rows returned (1…`MAX_LIMIT`); the endpoint's own default
    applies when it is omitted. **There is no auto-pagination** — to walk a longer
    history, call repeatedly, advancing ``start_time`` past the last candle.

    ``transport`` and ``clock`` are injection points: `urlopen_transport` and
    `datetime.now(timezone.utc)` are the defaults, and supplying them makes a call
    fully deterministic and network-free.

    Candles are returned exactly as the provider ordered them, forming candle
    included; nothing is dropped. Whether the final candle is still forming is
    visible on `Candle.is_closed`, and `CandleSeries.closed` drops it. That flag is
    derived by comparing each kline's close time to ``clock()``, so a clock skewed
    far from Binance's could mislabel a boundary candle — the reason the clock is
    injectable rather than implicit.

    Raises `BinanceRequestError` (bad arguments, before any I/O),
    `BinanceTransportError` (request could not be completed), `BinanceAPIError`
    (Binance returned an error status or payload), `BinanceResponseError`
    (malformed or ambiguous body), or `fmis.ingest.IngestError` when the mapped
    records violate a canonical invariant. A provider failure is never turned into
    an empty series; an empty series means Binance genuinely returned no rows.
    """
    url = build_klines_url(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        base_url=base_url,
    )

    send = urlopen_transport if transport is None else transport
    response = send(url)
    if not isinstance(response, HttpResponse):
        raise BinanceResponseError(
            f"transport must return an HttpResponse, got {type(response).__name__}"
        )

    payload = _decode_body(response.body, status=response.status)
    _raise_for_error_payload(payload, status=response.status)

    if not isinstance(payload, list):
        raise BinanceResponseError(
            f"expected a JSON array of klines, got {type(payload).__name__}"
        )

    now = (datetime.now(timezone.utc) if clock is None else clock())
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise BinanceRequestError("clock must return a timezone-aware datetime")
    now_ms = round(now.timestamp() * 1000)

    records = [
        map_kline(raw, symbol=symbol, interval=interval, now_ms=now_ms, index=i)
        for i, raw in enumerate(payload)
    ]
    # The canonical boundary owns validation; symbol/timeframe are passed
    # explicitly so an empty payload still yields a correctly identified series.
    return decode_candle_series(records, symbol=symbol, timeframe=interval)
