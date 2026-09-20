"""POST-HOC — the control the preregistration did not require for R3.

    .venv/bin/python research/zone_interactions/posthoc.py

**This analysis was not preregistered, and it is labelled POST-HOC everywhere
it appears.** It is recorded here, in place, rather than folded silently into
§9's criteria — the discipline report 0050 established when its own sealed
tie-break turned out to be wrong.

**Why it exists.** §4.2 built a placebo control for R4 because a return
hazard declines with elapsed time under a driftless walk whether or not zones
mean anything. Reading the R3 result made it obvious that R3 has *the same
exposure and no such control*: a price that closed beyond a band twice is
further from that band than one that closed beyond it once, and a random walk
started further away is more likely to be further away ten bars later. The
preregistered R3 comparison cannot distinguish

    "a second close marks a distinguishable state of this structural area"

from

    "position relative to any horizontal band persists."

The placebo bands already exist and already have the property needed: same
width, same establishment bar, same series, no structural level. Running the
identical C1 comparison on them costs one more pass and answers the question.

**What it cannot do.** It cannot promote R3 beyond what §9 allows, and it
cannot be used to *lower* a preregistered bar. It can only qualify the
interpretation, which is what the report does with it.
"""

from __future__ import annotations

import gzip
import json
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))

from zone_interactions.analyze import H_PRIMARY, ROLES, UNIVERSES, compare_two  # noqa: E402
from zone_interactions.events import (  # noqa: E402
    ABSENT,
    INSIDE,
    J_LONG,
    J_SHORT,
    Band,
    placebos,
    walk,
)
from zone_interactions.run import (  # noqa: E402
    ROLE_ID,
    atr_history,
    write_gzip_json,
    zones_for,
)
from zone_semantics.dataset import load_capture, role_series  # noqa: E402

OUT = ROOT / "reports" / "artifacts" / "0052_posthoc_placebo_r3.json.gz"


def main() -> None:
    # {(universe, role): {group: {symbol: (hits, n)}}}
    placebo_cells: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: (0, 0))))
    # Decomposition of the real SINGLE group: where was price at t0+1?
    single_state: dict = defaultdict(lambda: defaultdict(int))
    # Real DOUBLE/SINGLE separation restricted to events whose t0+1 close was
    # still outside on *either* side — the strictest de-tautologised subset.
    strict_cells: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: (0, 0))))

    for symbol_id, loaded in enumerate(load_capture()):
        universe = 0 if loaded.universe == "primary" else 1
        for role, timeframe, series in role_series(loaded):
            candles = series.candles
            n = len(candles)
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            atr = atr_history(series, n)
            j_max = J_SHORT if timeframe == "1w" else J_LONG
            key = (universe, ROLE_ID[role])

            zone_set = zones_for(series)
            if zone_set is None:
                continue

            levels = sorted(
                (m.price, m.joined_index) for z in zone_set.zones for m in z.members
            )
            level_prices = [p for p, _ in levels]
            level_from = [k for _, k in levels]

            for i, z in enumerate(zone_set.zones):
                band = Band(
                    low=z.low,
                    high=z.high,
                    width=z.width,
                    established=z.anchor.joined_index,
                    zone_id=i,
                )

                # --- real: decompose SINGLE, and build the strict subset ----
                cols, _ = walk(
                    band,
                    closes=closes,
                    highs=highs,
                    lows=lows,
                    atr=atr,
                    j_max=j_max,
                    full=True,
                )
                for k in range(len(cols["t0"])):
                    t0 = cols["t0"][k]
                    side = cols["side"][k]
                    b1 = cols["beyond_at_1"][k]
                    if t0 + 1 >= n:
                        continue
                    c1 = closes[t0 + 1]
                    if c1 > band.high:
                        at1 = 1
                    elif c1 < band.low:
                        at1 = -1
                    else:
                        at1 = INSIDE
                    if b1 == 0:
                        single_state[key]["inside" if at1 == INSIDE else "opposite"] += 1
                    outcome = cols[f"m1_C1_{H_PRIMARY}"][k]
                    if outcome == ABSENT:
                        continue
                    # Strict subset: price was still outside the band at the
                    # classification bar in BOTH groups, so the comparison is
                    # not "already back inside" versus "still out".
                    if at1 != INSIDE:
                        group = 1 if b1 == 1 else 0
                        hits, total = strict_cells[key][group][symbol_id]
                        strict_cells[key][group][symbol_id] = (
                            hits + (1 if outcome == 1 else 0),
                            total + 1,
                        )

                # --- placebo: the identical C1 comparison, clean only -------
                for p in placebos(band):
                    lo_k = bisect_left(level_prices, p.low)
                    hi_k = bisect_right(level_prices, p.high)
                    if any(level_from[q] <= p.established for q in range(lo_k, hi_k)):
                        continue  # contaminated: a real level sits inside it
                    pcols, _ = walk(
                        p,
                        closes=closes,
                        highs=highs,
                        lows=lows,
                        atr=atr,
                        j_max=j_max,
                        full=True,
                    )
                    for k in range(len(pcols["t0"])):
                        b1 = pcols["beyond_at_1"][k]
                        outcome = pcols[f"m1_C1_{H_PRIMARY}"][k]
                        if b1 == ABSENT or outcome == ABSENT:
                            continue
                        group = 1 if b1 == 1 else 0
                        hits, total = placebo_cells[key][group][symbol_id]
                        placebo_cells[key][group][symbol_id] = (
                            hits + (1 if outcome == 1 else 0),
                            total + 1,
                        )
        print(f"  {loaded.symbol:10s} {loaded.universe}", flush=True)

    out: dict = {"note": "POST-HOC. Not preregistered. See module docstring.", "cells": {}}
    for ui, universe in enumerate(UNIVERSES):
        for ri, role in enumerate(ROLES):
            key = (ui, ri)
            out["cells"][f"PLACEBO_C1|{universe}|{role}"] = compare_two(
                {g: dict(v) for g, v in placebo_cells[key].items()}, 0, 1
            )
            out["cells"][f"STRICT_C1|{universe}|{role}"] = compare_two(
                {g: dict(v) for g, v in strict_cells[key].items()}, 0, 1
            )
            out["cells"][f"SINGLE_STATE|{universe}|{role}"] = dict(single_state[key])

    digest = write_gzip_json(OUT, out)
    print(f"wrote {OUT.name}  sha256 {digest}")


if __name__ == "__main__":
    main()
