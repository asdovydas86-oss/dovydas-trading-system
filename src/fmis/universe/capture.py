"""Getting the inputs, cheapest question first. **The only module here that fetches.**

Milestone CC could be made to cost days of downloading, and a design that did
would answer its own question by exhausting the budget it exists to estimate. So
the funnel is staged, and each stage is only paid for by the instruments the
previous one admitted:

    exchangeInfo              1 request       3,645 instruments
      → name-level rules      0 requests      quote currency, asset class, identity
      → listing probe         1 per candidate one daily bar, from the epoch
      → window series         1 per survivor  the measurement window's daily bars

Nothing downloads a 4-hour series for an instrument that a name rule or a listing
date already refused, and nothing downloads nine years of daily bars to learn a
listing date that one bar answers.

**Read-only, unauthenticated, public.** Two endpoints — `exchangeInfo` and
`klines` — both of which need no key. Nothing here signs a request, reads a
credential, places an order or touches an account, and an architecture guard
asserts the absence by name.

**Caching is content-addressed and explicit.** Market data is mutable at source:
a re-run tomorrow can return different bars for the same window, which is the
failure Milestone BZ recorded as BZ-D2. `SeriesCache` persists what was fetched
together with the digest of what was fetched, so a later disagreement can be
attributed to the provider rather than argued about — and an offline re-run
reproduces the assessment from the cache with the network made fatal.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from fmis.providers.binance import (
    SPOT_PERMISSION,
    Transport,
    fetch_exchange_info,
    fetch_klines,
)
from fmis.universe.models import (
    PairStatus,
    TradingPair,
    UniverseError,
    require_aware,
    require_text,
)

__all__ = [
    "DailyBar",
    "SeriesCache",
    "CACHE_SCHEMA_VERSION",
    "EPOCH",
    "discover_pairs",
    "fetch_daily_bars",
    "series_digest",
    "network_is_fatal",
]

#: The cache file's schema. A reader refuses a version it does not know rather
#: than interpreting unfamiliar fields.
CACHE_SCHEMA_VERSION: Final[int] = 1

#: The instant `startTime=0` means to the provider. Asking for one bar from here
#: returns an instrument's first ever bar, which is its listing date.
EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=timezone.utc)

_MAX_ROWS: Final[int] = 1000


@dataclass(frozen=True, slots=True)
class DailyBar:
    """One daily bar, reduced to what Milestone CC actually measures.

    ``notional`` is ``close * volume`` — a **proxy** for the quote-asset volume
    the provider reports separately, computed from canonical fields rather than by
    teaching `fmis.data.Candle` a field it has no home for. Over a day the two
    differ by the gap between the closing price and the volume-weighted average
    price, which is small against a median taken over hundreds of days and far
    smaller than the order of magnitude the liquidity floor is set at. It is named
    ``notional`` rather than ``quote_volume`` so nothing downstream can mistake it
    for the provider's own figure.
    """

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        require_aware(self.open_time, "open_time")
        for field in ("open", "high", "low", "close", "volume"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise UniverseError(f"{field} must be a real number")
            if float(value) != float(value):
                raise UniverseError(f"{field} must be a real number, got NaN")

    @property
    def notional(self) -> float:
        return self.close * self.volume

    def payload(self) -> list[Any]:
        """A positional row. Compact, because a universe holds many of these."""
        return [
            round(self.open_time.timestamp() * 1000),
            repr(self.open), repr(self.high), repr(self.low),
            repr(self.close), repr(self.volume),
        ]

    @classmethod
    def from_payload(cls, row: Sequence[Any]) -> "DailyBar":
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != 6:
            raise UniverseError(f"a cached bar must be a 6-element row, got {row!r}")
        return cls(
            open_time=EPOCH + timedelta(milliseconds=int(row[0])),
            open=float(row[1]), high=float(row[2]), low=float(row[3]),
            close=float(row[4]), volume=float(row[5]),
        )


def discover_pairs(
    *, transport: Transport | None = None
) -> tuple[datetime, tuple[TradingPair, ...]]:
    """Every instrument the provider currently lists, with the instant it said so.

    Returns the provider's own ``serverTime`` and the pairs in **ascending symbol
    order**, not the provider's order. The provider does not promise its ordering
    and a universe whose membership or representative choice depended on it would
    not be reproducible; a hostile test shuffles the response and asserts the
    result is unchanged.
    """
    info = fetch_exchange_info(permissions=SPOT_PERMISSION, transport=transport)
    pairs = tuple(
        sorted(
            (
                TradingPair(
                    symbol=record.symbol,
                    base_asset=record.base_asset,
                    quote_asset=record.quote_asset,
                    status=PairStatus.from_provider(record.status),
                )
                for record in info.symbols
                # A listing the provider does not permit on spot has no spot
                # price series, whatever its status word says.
                if record.spot_trading_allowed
            ),
            key=lambda item: item.symbol,
        )
    )
    return info.server_time, pairs


def fetch_daily_bars(
    symbol: str,
    *,
    start: datetime | None,
    end: datetime | None = None,
    limit: int = _MAX_ROWS,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[DailyBar, ...]:
    """Daily bars for one instrument. **One request; no auto-pagination.**

    Two cheap probes are built on this and are worth naming, because between them
    they answer the whole depth question for one instrument in two requests:

    * ``start=EPOCH, limit=1`` — the **listing probe**. The provider returns from
      ``startTime`` forward, so the first row is the instrument's first ever bar.
    * ``start=None, limit=2`` — the **last-bar probe**. With no ``startTime`` the
      provider returns the most recent rows; two are asked for because the newest
      is usually still forming and is dropped. For a delisted instrument this is
      the bar it stopped trading on, which is exactly the survivorship
      information a current-listing snapshot cannot give.

    Bars are returned closed-only. A forming bar has not happened yet, and a
    coverage figure that counted one would report history the market has not
    produced.
    """
    require_text(symbol, "symbol")
    if start is not None:
        require_aware(start, "start")
    if end is not None:
        require_aware(end, "end")
    series = fetch_klines(
        symbol,
        "1d",
        start_time=start,
        end_time=end,
        limit=limit,
        transport=transport,
        clock=clock,
    )
    return tuple(
        DailyBar(
            open_time=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
        for candle in series.closed().candles
    )


def series_digest(bars: Sequence[DailyBar]) -> str:
    """SHA-256 over one series' canonical rows. **What makes a re-run comparable.**

    Two runs that disagree can be told apart here: an equal digest means the
    provider returned the same bars and the difference is in the code, and an
    unequal one means the market data itself moved. Milestone BZ could make
    neither statement, which is why it could not explain its own discrepancy.
    """
    canonical = json.dumps(
        [bar.payload() for bar in bars], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SeriesCache:
    """Fetched series, persisted with their digests. **The reproducibility layer.**

    A cache hit returns exactly the bars the original run measured, so an offline
    reproduction is a pure function of the file. A miss either fetches — when a
    transport was supplied — or refuses, which is what makes
    `network_is_fatal` a real check rather than a hopeful one.
    """

    def __init__(self, entries: dict[str, dict[str, Any]] | None = None) -> None:
        self._entries: dict[str, dict[str, Any]] = dict(entries or {})

    @staticmethod
    def key(
        symbol: str, start: datetime | None, end: datetime | None, limit: int
    ) -> str:
        """The identity of one request. Every argument that changes the answer."""
        parts = [
            symbol,
            "none" if start is None else start.astimezone(timezone.utc).isoformat(),
            "none" if end is None else end.astimezone(timezone.utc).isoformat(),
            str(limit),
        ]
        return "|".join(parts)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def get(self, key: str) -> tuple[DailyBar, ...] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        bars = tuple(DailyBar.from_payload(row) for row in entry["bars"])
        recorded = entry.get("digest")
        actual = series_digest(bars)
        if recorded != actual:
            raise UniverseError(
                f"cached series {key!r} has digest {recorded!r} but its rows digest "
                f"to {actual!r}. A capture whose contents do not match its own "
                "digest has been edited, and measuring it would attribute the edit "
                "to the market"
            )
        return bars

    def put(self, key: str, bars: Sequence[DailyBar]) -> None:
        rows = [bar.payload() for bar in bars]
        self._entries[key] = {"bars": rows, "digest": series_digest(tuple(
            DailyBar.from_payload(row) for row in rows
        ))}

    def series(
        self,
        symbol: str,
        *,
        start: datetime | None,
        end: datetime | None = None,
        limit: int = _MAX_ROWS,
        transport: Transport | None = None,
        clock: Callable[[], datetime] | None = None,
        allow_fetch: bool = True,
    ) -> tuple[DailyBar, ...]:
        """One series, from the cache when present and from the provider when not.

        Raises:
            UniverseError: the series is absent and ``allow_fetch`` is `False`.
                An offline reproduction that silently refetched would not be one.
        """
        key = self.key(symbol, start, end, limit)
        cached = self.get(key)
        if cached is not None:
            return cached
        if not allow_fetch:
            raise UniverseError(
                f"series {key!r} is not in the capture and fetching is disabled. "
                "An offline reproduction must be a pure function of the file; "
                "completing a gap from the provider would make it a new study"
            )
        bars = fetch_daily_bars(
            symbol, start=start, end=end, limit=limit, transport=transport, clock=clock
        )
        self.put(key, bars)
        return bars

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": {key: self._entries[key] for key in sorted(self._entries)},
        }

    def write(self, path: str | Path) -> Path:
        """Persist the cache. **Deterministic bytes, as Milestone BZ made them.**

        ``mtime=0`` and ``filename=""`` keep the gzip header free of the clock and
        of the path, so two equal caches produce two equal files.
        """
        target = Path(path)
        if target.suffix != ".gz":
            target = target.with_suffix(target.suffix + ".gz")
        canonical = json.dumps(
            self.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        with open(target, "wb") as raw:
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0
            ) as stream:
                stream.write(canonical)
        return target

    @classmethod
    def read(cls, path: str | Path) -> "SeriesCache":
        """Load a persisted cache, refusing a schema this build does not know."""
        source = Path(path)
        raw = source.read_bytes()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise UniverseError(f"{source}: a cache must be a JSON object")
        version = payload.get("schema_version")
        if version != CACHE_SCHEMA_VERSION:
            raise UniverseError(
                f"{source}: cache schema version {version!r}; this build reads "
                f"version {CACHE_SCHEMA_VERSION}. It is NOT read on a guess, "
                "because an unfamiliar field could change what a bar means"
            )
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            raise UniverseError(f"{source}: cache carries no 'entries' object")
        return cls(entries)


def network_is_fatal() -> Transport:
    """A transport that refuses every request. **The offline-reproduction control.**

    Handed to an assessment that claims to reproduce from a capture, this turns
    "it did not need the network" from a hope into a failure mode: any call at all
    raises, so a silent refetch cannot pass as a reproduction.
    """

    def _refuse(url: str):
        raise UniverseError(
            f"the network was reached for {url!r} during an offline reproduction. "
            "The assessment is not a pure function of its capture"
        )

    return _refuse
