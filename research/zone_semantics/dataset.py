"""The offline dataset: Milestone CD's committed capture, aggregated to roles.

No network. No credential. No live path. The capture is a committed artifact
with its own content digest, written for a different milestone — which is
exactly why it could not have been selected to flatter a zone result.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fmis.data import Candle, CandleSeries

CAPTURE = Path(__file__).resolve().parents[2] / "reports" / "artifacts" / (
    "0040_cd_source_capture.json.gz"
)

#: The three timeframe roles, named as `fmis.pipeline.multi_timeframe` names them.
ROLES: tuple[tuple[str, str], ...] = (
    ("context", "1w"),
    ("setup", "1d"),
    ("execution", "4h"),
)

_BARS_PER_DAY = 6  # six UTC-aligned 4h bars


@dataclass(frozen=True, slots=True)
class Loaded:
    symbol: str
    universe: str
    bars: tuple[tuple[datetime, float, float, float, float], ...]


def load_capture() -> tuple[Loaded, ...]:
    """Every symbol in the capture, both universes, native 4h."""
    with gzip.open(CAPTURE) as handle:
        payload = json.load(handle)
    out: list[Loaded] = []
    for universe in ("primary", "holdout"):
        block = payload["universes"][universe]
        for symbol in block["symbols"]:
            rows = block["bars"][symbol]
            out.append(
                Loaded(
                    symbol=symbol,
                    universe=universe,
                    bars=tuple(
                        (
                            datetime.fromisoformat(ts),
                            float(o),
                            float(h),
                            float(low),
                            float(c),
                        )
                        for ts, o, h, low, c in rows
                    ),
                )
            )
    return tuple(out)


def capture_digest() -> str:
    with gzip.open(CAPTURE) as handle:
        payload = json.load(handle)
    return str(payload["manifest"]["content_digest"])


def _series(
    symbol: str,
    timeframe: str,
    rows: Sequence[tuple[datetime, float, float, float, float]],
) -> CandleSeries:
    return CandleSeries(
        symbol=symbol,
        timeframe=timeframe,
        candles=tuple(
            Candle(
                timestamp=ts,
                symbol=symbol,
                timeframe=timeframe,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=0.0,
                is_closed=True,
            )
            for ts, o, h, low, c in rows
        ),
    )


def _aggregate(
    rows: Sequence[tuple[datetime, float, float, float, float]],
    *,
    bucket: "callable",
    expect: int,
) -> tuple[tuple[datetime, float, float, float, float], ...]:
    """Group 4h rows by ``bucket`` and keep only **complete** buckets.

    A partial bucket at either end is dropped rather than half-formed: an
    incomplete weekly bar is not a weekly bar, and carrying one would put a
    fabricated extreme into the level set.
    """
    groups: dict[datetime, list[tuple[datetime, float, float, float, float]]] = {}
    for row in rows:
        groups.setdefault(bucket(row[0]), []).append(row)
    out: list[tuple[datetime, float, float, float, float]] = []
    for key in sorted(groups):
        members = sorted(groups[key])
        if len(members) != expect:
            continue
        out.append(
            (
                key,
                members[0][1],
                max(m[2] for m in members),
                min(m[3] for m in members),
                members[-1][4],
            )
        )
    return tuple(out)


def _day(ts: datetime) -> datetime:
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _week(ts: datetime) -> datetime:
    day = _day(ts)
    return day - timedelta(days=day.weekday())  # Monday anchor, Binance's own


def role_series(loaded: Loaded) -> Iterator[tuple[str, str, CandleSeries]]:
    """`(role, timeframe, series)` for each of the three roles."""
    four_hour = loaded.bars
    daily = _aggregate(four_hour, bucket=_day, expect=_BARS_PER_DAY)
    weekly = _aggregate(daily, bucket=_week, expect=7)
    for role, timeframe in ROLES:
        rows = {"4h": four_hour, "1d": daily, "1w": weekly}[timeframe]
        yield role, timeframe, _series(loaded.symbol, timeframe, rows)


def transform(
    series: CandleSeries, *, scale: float = 1.0, mirror_about: float | None = None
) -> CandleSeries:
    """A scaled or reflected copy of ``series``.

    Reflection swaps high and low, because the reflection of a bar's maximum is
    its minimum. Forgetting that produces a series with `low > high`, which the
    domain model rejects — the test would pass by crashing.
    """
    candles = []
    for candle in series.candles:
        if mirror_about is None:
            o, h, low, c = (
                candle.open * scale,
                candle.high * scale,
                candle.low * scale,
                candle.close * scale,
            )
        else:
            o = mirror_about - candle.open
            h = mirror_about - candle.low
            low = mirror_about - candle.high
            c = mirror_about - candle.close
        candles.append(
            Candle(
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=candle.volume,
                is_closed=True,
            )
        )
    return CandleSeries(
        symbol=series.symbol, timeframe=series.timeframe, candles=tuple(candles)
    )
