"""Builders for price snapshots, marks and the transports that produce them.

Extends `tests/trade_domain_helpers.py` and `tests/persistence_helpers.py`
rather than duplicating either: the market, the assets and the instants are
already defined there.

**Every builder here is offline.** `klines_transport` returns a canned provider
payload, so a test that exercises the real fetch path — argument construction,
error isolation, the closed-candle rule, the whole chain into a `MarkQuote` —
never opens a socket. That is the same `transport` injection point every other
provider test in this repository already uses.

**No clock.** Every instant is derived from `AT(...)`, so a snapshot built here
is identical on every run and on every machine.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from trade_domain_helpers import AT

from fmis.data import Candle, CandleSeries
from fmis.marks import PriceBasis, PriceReading, PriceSnapshot, build_price_snapshot
from fmis.providers.binance import HttpResponse

__all__ = [
    "SOURCE",
    "candle",
    "series",
    "reading",
    "snapshot",
    "klines_body",
    "klines_transport",
    "failing_transport",
]

#: A provenance label that is not a venue. Tests that need to assert the label
#: travels intact use this rather than the production one, so a change to the
#: production label is a one-line edit there and not a suite-wide rename.
SOURCE = "test-price-source"


def candle(
    hour: int,
    close: float,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    is_closed: bool = True,
) -> Candle:
    """One flat candle. Open, high, low and close are equal on purpose: this
    package reads exactly one of the four, and a fixture whose other three
    differ invites a test that passes for the wrong reason."""
    return Candle(
        timestamp=AT(hour),
        symbol=symbol,
        timeframe=interval,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        is_closed=is_closed,
    )


def series(
    *closes: float,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    forming: float | None = None,
    first_hour: int = 8,
) -> CandleSeries:
    """A series of closed candles, optionally followed by a forming one."""
    candles = [
        candle(first_hour + offset, close, symbol=symbol, interval=interval)
        for offset, close in enumerate(closes)
    ]
    if forming is not None:
        candles.append(
            candle(
                first_hour + len(closes),
                forming,
                symbol=symbol,
                interval=interval,
                is_closed=False,
            )
        )
    return CandleSeries(symbol=symbol, timeframe=interval, candles=tuple(candles))


def reading(**overrides: Any) -> PriceReading:
    values: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "price": 61000.0,
        "observed_at": AT(11),
        "basis": PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
        "source": SOURCE,
        "closed_count": 2,
    }
    values.update(overrides)
    return PriceReading(**values)


def snapshot(
    *closes: float,
    symbol: str = "BTCUSDT",
    taken_at: datetime | None = None,
    source: str = SOURCE,
    unreadable: dict[str, str] | None = None,
) -> PriceSnapshot:
    """A snapshot over one symbol, priced at the last close supplied.

    Called with no closes it prices nothing and records nothing unreadable —
    the *"asked for nothing"* shape, which is distinct from a failed fetch.
    """
    return build_price_snapshot(
        (series(*closes, symbol=symbol),) if closes else (),
        taken_at=AT(12) if taken_at is None else taken_at,
        source=source,
        unreadable=unreadable,
    )


def klines_body(*closes: float, first_hour: int = 8, forming: bool = False) -> bytes:
    """A Binance-shaped klines payload, as bytes.

    Twelve fields per row because that is what the endpoint returns; the mapper
    reads five of them and the rest are present so a fixture cannot pass a
    shape the real endpoint never sends.
    """
    rows = []
    for offset, close in enumerate(closes):
        opened = AT(first_hour + offset)
        closes_at = opened + timedelta(hours=1)
        rows.append(
            [
                int(opened.timestamp() * 1000),
                f"{close}",
                f"{close}",
                f"{close}",
                f"{close}",
                "1.0",
                int(closes_at.timestamp() * 1000),
                "0",
                0,
                "0",
                "0",
                "0",
            ]
        )
    if forming and rows:
        # Push the final row's close time far enough out that the provider's own
        # `close_time < now` derivation marks it forming against any plausible
        # clock the caller injects.
        rows[-1][6] = int(AT(23, day=28).timestamp() * 1000)
    return json.dumps(rows).encode("utf-8")


def klines_transport(
    *closes: float, first_hour: int = 8, forming: bool = False, status: int = 200
) -> Any:
    """A `Transport` returning the same payload for every symbol requested."""
    body = klines_body(*closes, first_hour=first_hour, forming=forming)

    def _transport(url: str) -> HttpResponse:
        return HttpResponse(status=status, body=body)

    return _transport


def failing_transport(message: str = "connection reset") -> Any:
    """A `Transport` that raises the provider's own transport error every time."""
    from fmis.providers.binance import BinanceTransportError

    def _transport(url: str) -> HttpResponse:
        raise BinanceTransportError(message)

    return _transport
