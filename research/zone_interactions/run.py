"""Run the R3/R4 event walk over the committed capture and write the artifact.

    .venv/bin/python research/zone_interactions/run.py

No network, no credential, no wall clock, no randomness. Every structural fact
is produced by **production** `fmis` code — `detect_swings`,
`compare_swing_sequence`, `label_swing_sequence`, `structural_levels`,
`zone_width_series`, `derive_price_zones`, `AverageTrueRange` — called and
never reimplemented. This module owns the event walk, the placebo
construction, the overlap count and the bookkeeping, and nothing else.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from bisect import bisect_left, bisect_right
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))

from fmis.features import FeatureContext, FeatureRegistry  # noqa: E402
from fmis.features.indicators.atr import AverageTrueRange  # noqa: E402
from fmis.level_crossing import structural_levels  # noqa: E402
from fmis.market_structure import (  # noqa: E402
    compare_swing_sequence,
    detect_swings,
    label_swing_sequence,
)
from fmis.pipeline.structural_facts import default_features  # noqa: E402
from fmis.price_zones import derive_price_zones, zone_width_series  # noqa: E402

from zone_interactions.events import (  # noqa: E402
    J_LONG,
    J_SHORT,
    R4_COLUMNS,
    Band,
    placebos,
    r3_columns,
    walk,
)
from zone_semantics.dataset import capture_digest, load_capture, role_series  # noqa: E402

EVENTS = ROOT / "reports" / "artifacts" / "0052_zone_interaction_events.json.gz"

ATR_PERIOD = 14
ROLE_ID = {"context": 0, "setup": 1, "execution": 2}


def atr_history(series, n: int) -> list[float | None]:
    """ATR(14) per closed-candle index, warm-up left as `None`.

    Never back-filled and never carried forward from a later bar. A band whose
    anchor precedes warm-up produces no zone in production, so the `None` here
    is the same refusal expressed in the same place.
    """
    out: list[float | None] = [None] * n
    result = AverageTrueRange(ATR_PERIOD).compute_series(FeatureContext(primary=series))
    for point in result.points:
        if point.value is not None:
            out[point.index] = float(point.value)
    return out


def zones_for(series):
    """Production zones for one series, at the accepted V1 policy."""
    registry = FeatureRegistry()
    for feature in default_features():
        registry.register(feature)
    width = zone_width_series(registry, series)
    if width is None:
        return None
    swings = detect_swings(series)
    labelled = label_swing_sequence(compare_swing_sequence(swings))
    return derive_price_zones(structural_levels(labelled), width)


def _round(values: list) -> list:
    return [None if v is None else round(v, 6) for v in values]


class Collector:
    """Columnar accumulation across every symbol, role and band."""

    def __init__(self, columns: tuple[str, ...]) -> None:
        self.columns = columns + ("symbol", "universe", "role")
        self.data: dict[str, list] = {name: [] for name in self.columns}

    def add(self, cols: dict[str, list], symbol: int, universe: int, role: int) -> None:
        count = len(cols["t0"])
        if not count:
            return
        for name, values in cols.items():
            self.data[name].extend(values)
        self.data["symbol"].extend([symbol] * count)
        self.data["universe"].extend([universe] * count)
        self.data["role"].extend([role] * count)

    def size(self) -> int:
        return len(self.data["t0"])


def overlap_counts(bands: list[Band], closes: list[float], t0s: list[int]) -> list[int]:
    """How many bands of this same role contained the transition close (§5.3).

    Counted only over bands that existed by that bar — a band established later
    could not have been part of the state. Bands are indexed by ``low`` so the
    scan is over a prefix rather than the whole set.
    """
    order = sorted(range(len(bands)), key=lambda i: bands[i].low)
    lows = [bands[i].low for i in order]
    highs = [bands[i].high for i in order]
    ests = [bands[i].established for i in order]
    out: list[int] = []
    for t0 in t0s:
        c = closes[t0]
        stop = bisect_right(lows, c)
        total = 0
        for k in range(stop):
            if highs[k] >= c and ests[k] <= t0:
                total += 1
        out.append(total)
    return out


def write_gzip_json(path, payload) -> str:
    """Write gzipped JSON whose bytes depend only on the payload.

    `gzip.open` stamps the current time into the gzip header, so an identical
    result hashes differently on every run and a determinism check fails for a
    reason that has nothing to do with the research. `mtime=0` removes the only
    non-deterministic byte.
    """
    import gzip as _gzip
    import hashlib as _hashlib
    import json as _json

    raw = _json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    with open(path, "wb") as handle:
        with _gzip.GzipFile(fileobj=handle, mode="wb", mtime=0, filename="") as gz:
            gz.write(raw)
    return _hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    started = time.monotonic()
    real = Collector(R4_COLUMNS + r3_columns() + ("overlap_inside",))
    plac = Collector(R4_COLUMNS + ("delta", "contaminated"))
    symbols: list[str] = []
    per_series: list[dict] = []

    for loaded in load_capture():
        symbol_id = len(symbols)
        symbols.append(loaded.symbol)
        universe_id = 0 if loaded.universe == "primary" else 1

        for role, timeframe, series in role_series(loaded):
            candles = series.candles
            n = len(candles)
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            atr = atr_history(series, n)
            j_max = J_SHORT if timeframe == "1w" else J_LONG

            zone_set = zones_for(series)
            if zone_set is None:
                continue

            bands = [
                Band(
                    low=z.low,
                    high=z.high,
                    width=z.width,
                    established=z.anchor.joined_index,
                    zone_id=i,
                )
                for i, z in enumerate(zone_set.zones)
            ]

            # Confirmed level prices and the bar each became knowable, for
            # placebo contamination (§4.2). Read once, not per band.
            levels = sorted(
                (m.price, m.joined_index) for z in zone_set.zones for m in z.members
            )
            level_prices = [p for p, _ in levels]
            level_from = [k for _, k in levels]

            traverse_total = 0
            exits_here = 0
            for band in bands:
                cols, traverses = walk(
                    band,
                    closes=closes,
                    highs=highs,
                    lows=lows,
                    atr=atr,
                    j_max=j_max,
                    full=True,
                )
                traverse_total += traverses
                count = len(cols["t0"])
                if count:
                    cols["overlap_inside"] = overlap_counts(bands, closes, cols["t0"])
                    for key in ("disp_atr", "excursion_atr"):
                        cols[key] = _round(cols[key])
                    for key in cols:
                        if key.startswith("m3_"):
                            cols[key] = _round(cols[key])
                    real.add(cols, symbol_id, universe_id, ROLE_ID[role])
                    exits_here += count

                for p in placebos(band):
                    lo_k = bisect_left(level_prices, p.low)
                    hi_k = bisect_right(level_prices, p.high)
                    contaminated = any(
                        level_from[k] <= p.established for k in range(lo_k, hi_k)
                    )
                    pcols, _ = walk(
                        p,
                        closes=closes,
                        highs=highs,
                        lows=lows,
                        atr=atr,
                        j_max=j_max,
                        full=False,
                    )
                    pcount = len(pcols["t0"])
                    if pcount:
                        for key in ("disp_atr", "excursion_atr"):
                            pcols[key] = _round(pcols[key])
                        pcols["delta"] = [p.delta] * pcount
                        pcols["contaminated"] = [contaminated] * pcount
                        plac.add(pcols, symbol_id, universe_id, ROLE_ID[role])

            per_series.append(
                {
                    "symbol": loaded.symbol,
                    "universe": loaded.universe,
                    "role": role,
                    "timeframe": timeframe,
                    "bars": n,
                    "zones": len(bands),
                    "exits": exits_here,
                    "traverses": traverse_total,
                }
            )
        print(
            f"  {loaded.symbol:10s} {loaded.universe:8s}"
            f"  real={real.size():>7,}  placebo={plac.size():>8,}"
            f"  {time.monotonic() - started:6.1f}s",
            flush=True,
        )

    payload = {
        "manifest": {
            "preregistration": "docs/design/ZONE_INTERACTION_RESEARCH_QUESTIONS_V1.md",
            "preregistration_commit": "296831a",
            "capture_digest": capture_digest(),
            "symbols": symbols,
            "roles": sorted(ROLE_ID, key=lambda r: ROLE_ID[r]),
            "atr_period": ATR_PERIOD,
            "j_long": J_LONG,
            "j_short": J_SHORT,
            "horizon_primary": 10,
            "real_events": real.size(),
            "placebo_events": plac.size(),
            "per_series": per_series,
        },
        "real": real.data,
        "placebo": plac.data,
    }

    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    digest = write_gzip_json(EVENTS, payload)
    print(f"\nreal events    {real.size():,}")
    print(f"placebo events {plac.size():,}")
    print(f"{EVENTS.name}  sha256 {digest}")
    print(f"elapsed {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
