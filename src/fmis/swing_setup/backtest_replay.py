"""Historical data acquisition and closed-candle replay for the backtest harness.

**Core principle (task brief): backtesting must use the SAME deterministic
production logic as live analysis.** This module adds no signal logic, no
candle decoding and no closed/forming derivation of its own — both already
exist in `fmis.providers.binance.fetch_klines` (`map_kline`'s
``is_closed = close_time_ms < now_ms``) and in `CandleSeries.closed()`. What
this module adds is a **replacement data source**: a real historical raw-kline
cache, fetched once per (symbol, interval) by paging the same public endpoint
`fetch_klines` calls, plus a `Transport` (the same injection point every
composition root already accepts) that, bound to one simulated instant
``now``, serves exactly the raw rows Binance would have returned had the
query been made at that instant — filtered to ``close_time < now`` before a
single byte reaches `fetch_klines`.

    build_replay_transport(cache, now=T)  ──►  Transport
            │
            ▼ (fed into the UNCHANGED production composition root)
    multi_timeframe_facts_for_symbol(symbol, transport=replay, clock=lambda: T)

Because the replay transport pre-filters by ``close_time < now`` **and**
`fetch_klines` independently re-derives ``is_closed`` from the same clock,
a historical decision at instant ``T`` cannot see any candle that had not
closed by ``T`` — the no-lookahead guarantee holds even if either mechanism
alone had a bug, by construction of two independent checks over the same
boundary.

An unknown (symbol, interval) served by the replay transport answers with
Binance's own real error shape (``code -1121``, ``"Invalid symbol."``), so a
caller error surfaces through `fetch_klines`'s existing, unmodified
`BinanceAPIError` path rather than a new one invented here.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from fmis.providers.binance import (
    BINANCE_API_BASE,
    MAX_LIMIT,
    HttpResponse,
    KLINE_INTERVALS,
    Transport,
    build_klines_url,
    urlopen_transport,
)
from fmis.swing_setup.backtest_models import BacktestError, DataBoundary

__all__ = [
    "RawKlineCache",
    "fetch_raw_klines",
    "fetch_historical_dataset",
    "build_replay_transport",
    "DEFAULT_REPLAY_LIMIT",
    "OPEN_TIME_INDEX",
    "CLOSE_TIME_INDEX",
    "to_epoch_ms",
    "from_epoch_ms",
]

_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: Binance's own documented default row count when a request omits ``limit``.
#: Matched here so the replay transport's un-limited behaviour agrees with
#: what the real endpoint would have returned.
DEFAULT_REPLAY_LIMIT: Final[int] = 500

#: Positional indices into one raw kline row — the same provider contract
#: `fmis.providers.binance` documents. Public so the harness can locate a
#: candle's close time without a second, private copy of these positions.
OPEN_TIME_INDEX: Final[int] = 0
CLOSE_TIME_INDEX: Final[int] = 6
_OPEN_TIME_INDEX = OPEN_TIME_INDEX
_CLOSE_TIME_INDEX = CLOSE_TIME_INDEX

#: A Binance-shaped error payload for a (symbol, interval) the replay cache
#: was never asked to fetch — the exact real code/message Binance's own API
#: returns for `code=-1121`, so it exercises `fetch_klines`'s unmodified
#: `BinanceAPIError` path rather than inventing a new error shape.
_UNKNOWN_SERIES_PAYLOAD = {"code": -1121, "msg": "Invalid symbol."}


def to_epoch_ms(value: datetime) -> int:
    """Exact epoch milliseconds from a timezone-aware datetime."""
    return round(value.timestamp() * 1000)


def from_epoch_ms(value: int) -> datetime:
    """The exact UTC instant an epoch-millisecond value names."""
    return _EPOCH + timedelta(milliseconds=value)


_to_epoch_ms = to_epoch_ms
_from_epoch_ms = from_epoch_ms


def fetch_raw_klines(
    symbol: str,
    interval: str,
    *,
    start_time: datetime,
    end_time: datetime,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> list[list[Any]]:
    """Page real klines from ``start_time`` to ``end_time``, raw, undecoded.

    Deliberately returns the provider's own raw arrays rather than a
    `CandleSeries` — close-time, needed to reproduce the closed-candle
    boundary at replay time, does not survive decoding into a `Candle`. No
    row is dropped, mapped or validated here; that is `fetch_klines`'s job,
    exercised later, once per simulated instant, when a `SetupInputs`/
    `SetupAssessment` pair is actually built.

    `fetch_klines` itself is not called: it fetches one page and decodes
    immediately, and this function's whole purpose is to page **and** keep
    the raw shape. The two share only `build_klines_url` and the injectable
    `Transport`.

    Raises:
        BacktestError: ``start_time``/``end_time`` are not timezone-aware,
            ``start_time`` is after ``end_time``, ``interval`` is not a
            recognised provider interval, or the provider answered with an
            error payload.
    """
    if not isinstance(start_time, datetime) or start_time.utcoffset() is None:
        raise BacktestError("start_time must be a timezone-aware datetime")
    if not isinstance(end_time, datetime) or end_time.utcoffset() is None:
        raise BacktestError("end_time must be a timezone-aware datetime")
    if start_time > end_time:
        raise BacktestError("start_time must not be after end_time")
    if interval not in KLINE_INTERVALS:
        raise BacktestError(
            f"unsupported interval {interval!r}; expected one of "
            f"{', '.join(sorted(KLINE_INTERVALS))}"
        )

    send = urlopen_transport if transport is None else transport
    base = BINANCE_API_BASE if base_url is None else base_url

    rows: list[list[Any]] = []
    cursor = start_time
    while cursor <= end_time:
        url = build_klines_url(
            symbol=symbol,
            interval=interval,
            start_time=cursor,
            end_time=end_time,
            limit=MAX_LIMIT,
            base_url=base,
        )
        response = send(url)
        if not isinstance(response, HttpResponse):
            raise BacktestError(
                f"transport must return an HttpResponse, got {type(response).__name__}"
            )
        try:
            payload = json.loads(response.body)
        except ValueError as exc:
            raise BacktestError(
                f"{symbol} {interval}: response body is not valid JSON"
            ) from exc
        if not (200 <= response.status < 300):
            raise BacktestError(
                f"{symbol} {interval}: HTTP {response.status} fetching historical "
                f"klines: {payload!r}"
            )
        if isinstance(payload, Mapping):
            raise BacktestError(
                f"{symbol} {interval}: provider error fetching historical klines: "
                f"{payload!r}"
            )
        if not isinstance(payload, list) or not payload:
            break

        rows.extend(payload)
        last_close_ms = payload[-1][_CLOSE_TIME_INDEX]
        next_cursor = _from_epoch_ms(last_close_ms + 1)
        if next_cursor <= cursor:
            # No forward progress — stop rather than loop forever on a
            # provider payload that does not advance the cursor.
            break
        cursor = next_cursor
        if len(payload) < MAX_LIMIT:
            break
    return rows


class RawKlineCache(dict):
    """A mapping of ``(symbol, interval) -> raw kline rows``, keyed exactly.

    A thin, mutable dict subclass rather than a frozen dataclass: it exists
    only to be built once by `fetch_historical_dataset` and then read by
    `build_replay_transport`, never compared or hashed.
    """


def fetch_historical_dataset(
    symbols: Sequence[str],
    intervals: Sequence[str],
    *,
    start_time: datetime,
    end_time: datetime,
    fetched_at: datetime,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> tuple[RawKlineCache, tuple[DataBoundary, ...]]:
    """Fetch every (symbol, interval) pair once, and record its exact boundary.

    ``fetched_at`` is a required, caller-supplied stamp — this function reads
    no wall clock of its own, matching `fmis.pipeline.cli`'s convention that
    only the outermost edge owns the clock.

    Returns the raw cache `build_replay_transport` reads, plus one
    `DataBoundary` per pair recording exactly what was fetched — so a run's
    results are reproducible against a stated, inspectable window rather than
    an implicit "whatever Binance returns".
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise BacktestError("symbols must be a non-empty, non-string sequence")
    if isinstance(intervals, (str, bytes)) or not isinstance(intervals, Sequence) or not intervals:
        raise BacktestError("intervals must be a non-empty, non-string sequence")

    cache = RawKlineCache()
    boundaries: list[DataBoundary] = []
    for symbol in symbols:
        for interval in intervals:
            rows = fetch_raw_klines(
                symbol,
                interval,
                start_time=start_time,
                end_time=end_time,
                transport=transport,
                base_url=base_url,
            )
            cache[(symbol, interval)] = rows
            first = _from_epoch_ms(rows[0][_OPEN_TIME_INDEX]) if rows else None
            last = _from_epoch_ms(rows[-1][_OPEN_TIME_INDEX]) if rows else None
            boundaries.append(
                DataBoundary(
                    symbol=symbol,
                    interval=interval,
                    source="binance-spot",
                    first_candle=first,
                    last_candle=last,
                    candle_count=len(rows),
                    fetched_at=fetched_at,
                )
            )
    return cache, tuple(boundaries)


def build_replay_transport(cache: Mapping[tuple[str, str], Sequence[Sequence[Any]]], *, now: datetime) -> Transport:
    """Bind a `Transport` to one simulated instant, over an already-fetched cache.

    Every call is answered entirely from ``cache`` — no network access is
    made, matching every `Transport` this repository already injects for
    tests. The returned rows are exactly the provider's own raw shape,
    filtered to ``close_time < now`` (the identical inequality
    `fmis.providers.binance.map_kline` uses to derive ``is_closed``) and
    trimmed to the requested ``limit`` (or `DEFAULT_REPLAY_LIMIT` if the URL
    carried none) — the same two request parameters the real endpoint reads.

    Raises:
        BacktestError: ``now`` is not timezone-aware.
    """
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise BacktestError("now must be a timezone-aware datetime")
    now_ms = _to_epoch_ms(now)

    def _transport(url: str) -> HttpResponse:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        symbol = query.get("symbol", [""])[0]
        interval = query.get("interval", [""])[0]
        limit_values = query.get("limit")
        limit = int(limit_values[0]) if limit_values else DEFAULT_REPLAY_LIMIT

        rows = cache.get((symbol, interval))
        if rows is None:
            return HttpResponse(
                status=400, body=json.dumps(_UNKNOWN_SERIES_PAYLOAD).encode("utf-8")
            )

        closed_as_of_now = [row for row in rows if row[_CLOSE_TIME_INDEX] < now_ms]
        sliced = closed_as_of_now[-limit:] if limit > 0 else []
        return HttpResponse(status=200, body=json.dumps(sliced).encode("utf-8"))

    return _transport
