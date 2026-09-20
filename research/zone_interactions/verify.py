"""§8 admissibility, on real data — plus the two isolation assertions.

    .venv/bin/python research/zone_interactions/verify.py

The fixtures (§11) prove the invariants on synthetic series where the expected
answer is constructible by hand. This module proves the ones that can only be
checked against the real capture and the real production zone engine:

  * **prefix stability** — an event's classification, once emitted, never
    changes as history extends, and an outcome that was knowable in the prefix
    equals the outcome in the full history;
  * **window-start insensitivity** — truncating the leading 10 % of bars does
    not change the classification of events on bands that survive;
  * **reflection and scale** on real price paths, not hand-built ones;
  * **determinism** across processes and `PYTHONHASHSEED`;
  * **`src/` does not import `research/`**, and `fmis` imports with `research/`
    off the path.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))

from fmis.data import Candle, CandleSeries  # noqa: E402
from zone_interactions.events import ABSENT, J_LONG, Band, walk  # noqa: E402
from zone_interactions.run import atr_history, zones_for  # noqa: E402
from zone_semantics.dataset import load_capture, role_series  # noqa: E402

#: Classification fields split by **when they become knowable** — the same
#: distinction the whole study is built on (§3.3). The first group is settled
#: at the transition bar; the second cannot be known until one or two bars
#: later, so in a prefix that ends too early it is legitimately `ABSENT` and
#: only becomes an answer as history arrives. A stability test that treated
#: `ABSENT -> 1` as drift would be demanding that the harness never learn
#: anything.
AT_T0 = ("t0", "side", "gapped")
LATER = ("beyond_at_1", "beyond_at_2")
CLASSIFICATION = AT_T0 + ("disp_atr",) + LATER

#: `disp_atr` divides by ATR(14), which is a **recursive** Wilder average with
#: no finite warm-up: begin the series at a different bar and every later value
#: differs in its last few bits. That is a property of the production indicator,
#: not of this harness, so displacement is compared as a **bin** (which is what
#: the research actually consumes) plus a relative tolerance.
DISP_RTOL = 1e-9

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))


def _disp_bin(value) -> int | None:
    if value is None:
        return None
    if value < 0.25:
        return 0
    return 1 if value < 0.75 else 2


def _disp_same(a, b) -> bool:
    """Same displacement *bin*, and equal to within recursive-ATR noise."""
    if a is None or b is None:
        return a is b or a == b
    if _disp_bin(a) != _disp_bin(b):
        return False
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / scale <= DISP_RTOL


def events_for(series) -> dict[tuple, dict]:
    """`{(low, high, established): classification}` over one series."""
    n = len(series.candles)
    closes = [c.close for c in series.candles]
    highs = [c.high for c in series.candles]
    lows = [c.low for c in series.candles]
    atr = atr_history(series, n)
    zone_set = zones_for(series)
    if zone_set is None:
        return {}
    out: dict[tuple, dict] = {}
    for i, z in enumerate(zone_set.zones):
        band = Band(
            low=z.low,
            high=z.high,
            width=z.width,
            established=z.anchor.joined_index,
            zone_id=i,
        )
        cols, _ = walk(
            band, closes=closes, highs=highs, lows=lows, atr=atr, j_max=J_LONG, full=True
        )
        for k in range(len(cols["t0"])):
            key = (round(z.low, 9), round(z.high, 9), cols["t0"][k])
            out[key] = {c: cols[c][k] for c in CLASSIFICATION}
            out[key]["m1"] = cols["m1_C1_10"][k]
    return out


def truncated(series: CandleSeries, drop: int) -> CandleSeries:
    return CandleSeries(
        symbol=series.symbol, timeframe=series.timeframe, candles=series.candles[drop:]
    )


def transformed(series: CandleSeries, *, scale=1.0, mirror=None) -> CandleSeries:
    candles = []
    for c in series.candles:
        if mirror is None:
            o, h, low, cl = c.open * scale, c.high * scale, c.low * scale, c.close * scale
        else:
            o, h, low, cl = mirror - c.open, mirror - c.low, mirror - c.high, mirror - c.close
        candles.append(
            Candle(
                timestamp=c.timestamp,
                symbol=c.symbol,
                timeframe=c.timeframe,
                open=o,
                high=h,
                low=low,
                close=cl,
                volume=c.volume,
                is_closed=True,
            )
        )
    return CandleSeries(symbol=series.symbol, timeframe=series.timeframe, candles=tuple(candles))


def main() -> int:
    sample = [loaded for loaded in load_capture() if loaded.symbol in ("BTCUSDT", "XRPUSDT", "LINKUSDT")]

    for loaded in sample:
        for role, timeframe, series in role_series(loaded):
            if timeframe != "1d":
                continue
            tag = f"{loaded.symbol} {timeframe}"
            full = events_for(series)

            # --- prefix stability -------------------------------------------
            cut = int(len(series.candles) * 0.8)
            prefix = CandleSeries(
                symbol=series.symbol, timeframe=series.timeframe, candles=series.candles[:cut]
            )
            pre = events_for(prefix)
            drifted = []
            outcome_drift = []
            for key, row in pre.items():
                if key not in full:
                    drifted.append(("missing", key))
                    continue
                later = full[key]
                if any(row[c] != later[c] for c in AT_T0):
                    drifted.append(("changed", key))
                # Knowable-later fields: compare only where the prefix already
                # had an answer. `ABSENT` becoming a value is history arriving.
                if any(
                    row[c] != ABSENT and row[c] != later[c] for c in LATER
                ):
                    drifted.append(("changed-late", key))
                if not _disp_same(row["disp_atr"], later["disp_atr"]):
                    drifted.append(("disp", key))
                if row["m1"] != ABSENT and row["m1"] != later["m1"]:
                    outcome_drift.append(key)
            check(f"prefix: classification stable  {tag}", not drifted, f"{len(drifted)} drifted")
            check(
                f"prefix: knowable outcome stable  {tag}",
                not outcome_drift,
                f"{len(outcome_drift)} drifted",
            )

            # --- window start ------------------------------------------------
            shift = int(len(series.candles) * 0.10)
            late = events_for(truncated(series, shift))
            shared = 0
            mismatched = 0
            for key, row in late.items():
                lo, hi, t0 = key
                origin = (lo, hi, t0 + shift)
                if origin not in full:
                    continue
                shared += 1
                if any(row[c] != full[origin][c] for c in AT_T0 if c != "t0"):
                    mismatched += 1
                elif any(row[c] != full[origin][c] for c in LATER):
                    mismatched += 1
                elif not _disp_same(row["disp_atr"], full[origin]["disp_atr"]):
                    mismatched += 1
            check(
                f"window start: surviving events unchanged  {tag}",
                mismatched == 0 and shared > 0,
                f"{mismatched}/{shared} mismatched",
            )

            # --- reflection ----------------------------------------------------
            mirror = 2.0 * max(c.high for c in series.candles)
            flipped = events_for(transformed(series, mirror=mirror))
            check(
                f"reflection: same event count  {tag}",
                len(flipped) == len(full),
                f"{len(flipped)} vs {len(full)}",
            )
            up_sides = sorted((k[2], v["side"]) for k, v in full.items())
            dn_sides = sorted((k[2], -v["side"]) for k, v in flipped.items())
            check(f"reflection: sides exactly mirrored  {tag}", up_sides == dn_sides)

            # --- scale ---------------------------------------------------------
            for factor in (2.0, 1024.0, 0.125):
                scaled = events_for(transformed(series, scale=factor))
                same = sorted((k[2], v["side"], v["beyond_at_1"]) for k, v in scaled.items())
                base = sorted((k[2], v["side"], v["beyond_at_1"]) for k, v in full.items())
                check(f"scale ×{factor:g}: identical classification  {tag}", same == base)

    # --- determinism ---------------------------------------------------------
    artifact = ROOT / "reports" / "artifacts" / "0052_zone_interaction_events.json.gz"
    baseline = hashlib.sha256(artifact.read_bytes()).hexdigest()
    digests = []
    for seed in ("0", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(ROOT / "research/zone_interactions/run.py")],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        digests.append(hashlib.sha256(artifact.read_bytes()).hexdigest())
    check(
        "determinism: byte-identical across processes and hash seeds",
        digests[0] == digests[1] == baseline,
        f"{baseline[:12]} {digests[0][:12]} {digests[1][:12]}",
    )

    # --- isolation -----------------------------------------------------------
    hits = subprocess.run(
        # The import path, not the bare word: `fmits research` is a real and
        # unrelated production command (Milestone BC) and its flag is not an
        # import of this package.
        ["grep", "-rn", "-E", r"research\.zone_interactions|from zone_interactions|import zone_interactions",
         "--include=*.py", "src", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    check("isolation: src/ and tests/ never name research/", not hits, hits[:300])

    probe = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "-c", "import fmis, fmis.price_zones; print('ok')"],
        cwd="/",
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        capture_output=True,
        text=True,
    )
    check("isolation: fmis imports with research/ off the path", probe.returncode == 0, probe.stderr[:200])

    failed = [r for r in _results if not r[1]]
    for name, ok, detail in _results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
