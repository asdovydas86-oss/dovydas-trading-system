"""Read the result file and print the report's tables. No new computation."""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(
    sys.argv[1] if len(sys.argv) > 1
    else "reports/artifacts/0050_zone_semantics_results.json"
)


def load():
    return json.loads(RESULTS.read_text())


def med(values):
    values = [v for v in values if v is not None]
    return st.median(values) if values else None


def admissibility_by_k(rows):
    """Section 6.1, applied per grid value.

    A single pass/fail per policy family was the preregistration's shape and it
    turned out to be the wrong instrument: two criteria hold over part of the
    grid and fail over the rest, and collapsing that into one boolean throws away
    the only thing that tells you where the usable region ends. The gate is
    therefore reported as **the largest k at which every criterion still holds**.
    """
    groups = defaultdict(list)
    for row in rows:
        if row.get("empty") or row["k"] == 0.0:
            continue
        groups[(row["geometry"], row["scale"], row["temporal"])].append(row)
    print(f"{'geometry':16s}{'scale':17s}{'temporal':11s}"
          f"{'scale':>7s}{'exact':>7s}{'mirror':>8s}{'illegal':>9s}{'span>w':>8s}"
          f"{'k_max':>8s}")
    out = {}
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        block = groups[key]
        by_k = defaultdict(list)
        for row in block:
            by_k[row["k"]].append(row)
        k_ok = []
        for k in sorted(by_k):
            cell = by_k[k]
            if (
                all(r["scale_invariant"] for r in cell)
                and all(r.get("scale_invariant_exact", True) for r in cell)
                and all(r["mirror_symmetric"] for r in cell)
                and sum(r["prefix_illegal"] for r in cell) == 0
                and not any(r["max_span_over_w"] > 1.0 + 1e-9 for r in cell)
            ):
                k_ok.append(k)
        contiguous = []
        for k in sorted(by_k):
            if k in k_ok:
                contiguous.append(k)
            else:
                break
        out[key] = tuple(contiguous)
        print(f"{key[0]:16s}{key[1]:17s}{str(key[2]):11s}"
              f"{sum(1 for r in block if r['scale_invariant']) / len(block):7.2f}"
              f"{sum(1 for r in block if r.get('scale_invariant_exact', True)) / len(block):7.2f}"
              f"{sum(1 for r in block if r['mirror_symmetric']) / len(block):8.2f}"
              f"{sum(r['prefix_illegal'] for r in block):9d}"
              f"{sum(1 for r in block if r['max_span_over_w'] > 1.0 + 1e-9):8d}"
              f"{(f'{max(contiguous):g}' if contiguous else 'NONE'):>8s}")
    return out


def admissibility(rows):
    """The section 6.1 gate, applied to every (geometry, scale, temporal) pair."""
    groups = defaultdict(list)
    for row in rows:
        if row.get("empty") or row["k"] == 0.0:
            continue
        groups[(row["geometry"], row["scale"], row["temporal"])].append(row)
    print(f"{'geometry':16s}{'scale':17s}{'temporal':11s}"
          f"{'n':>6s}{'scale':>7s}{'exact':>7s}{'mirror':>8s}{'illegal':>9s}"
          f"{'span>w':>8s}{'verdict':>12s}")
    out = {}
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        block = groups[key]
        scale_ok = sum(1 for r in block if r["scale_invariant"])
        exact_ok = sum(1 for r in block if r.get("scale_invariant_exact", True))
        mirror_ok = sum(1 for r in block if r["mirror_symmetric"])
        illegal = sum(r["prefix_illegal"] for r in block)
        over = sum(1 for r in block if r["max_span_over_w"] > 1.0 + 1e-9)
        ok = (
            scale_ok == len(block)
            and mirror_ok == len(block)
            and illegal == 0
            and over == 0
        )
        out[key] = ok
        print(f"{key[0]:16s}{key[1]:17s}{str(key[2]):11s}{len(block):6d}"
              f"{scale_ok / len(block):7.2f}{exact_ok / len(block):7.2f}"
              f"{mirror_ok / len(block):8.2f}"
              f"{illegal:9d}{over:8d}{'ADMISSIBLE' if ok else 'rejected':>12s}")
    return out


def plateau(rows, geometry, scale, temporal, role=None):
    """Descriptive metric curves across the grid, pooled over the sample."""
    grid = defaultdict(list)
    for row in rows:
        if row.get("empty"):
            continue
        if (row["geometry"], row["scale"], row["temporal"]) != (
            geometry, scale, temporal
        ):
            continue
        if role and row["role"] != role:
            continue
        grid[row["k"]].append(row)
    print(f"\n--- {geometry} / {scale} / {temporal}"
          f"{' / role=' + role if role else ' / all roles'} ---")
    print(f"{'k':>6s}{'zones/lvl':>11s}{'singleton':>11s}{'merged':>9s}"
          f"{'maxmemb':>9s}{'w/ATR':>9s}{'overlap':>9s}{'window':>9s}"
          f"{'illegal':>9s}")
    for k in sorted(grid):
        block = grid[k]
        print(f"{k:6.2f}"
              f"{med(r['zones_per_level'] for r in block):11.3f}"
              f"{med(r['singleton_fraction'] for r in block):11.3f}"
              f"{med(r['merged_level_fraction'] for r in block):9.3f}"
              f"{med(r['max_members'] for r in block):9.1f}"
              f"{(med(r['median_width_over_atr'] for r in block) or 0):9.3f}"
              f"{med(r['overlap_fraction'] for r in block):9.3f}"
              f"{(f'{w:.4f}' if (w := med(r['window_agreement'] for r in block)) is not None else 'n/a'):>9s}"
              f"{sum(r['prefix_illegal'] for r in block):9d}")


def by_role(rows, geometry, scale, temporal):
    print(f"\n--- cross-timeframe transfer: {geometry} / {scale} / {temporal} ---")
    print(f"{'k':>6s}" + "".join(f"{r:>28s}" for r in ("context 1w", "setup 1d", "execution 4h")))
    print(f"{'':6s}" + "".join(f"{'sing / zones/lvl / maxm':>28s}" for _ in range(3)))
    grid = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("empty"):
            continue
        if (row["geometry"], row["scale"], row["temporal"]) != (geometry, scale, temporal):
            continue
        grid[row["k"]][row["role"]].append(row)
    for k in sorted(grid):
        cells = []
        for role in ("context", "setup", "execution"):
            block = grid[k].get(role, [])
            if not block:
                cells.append(f"{'-':>28s}")
                continue
            cells.append(
                f"{med(r['singleton_fraction'] for r in block):.3f} / "
                f"{med(r['zones_per_level'] for r in block):.3f} / "
                f"{med(r['max_members'] for r in block):.0f}".rjust(28)
            )
        print(f"{k:6.2f}" + "".join(cells))


def cross_asset(rows, geometry, scale, temporal, k):
    per = defaultdict(list)
    for row in rows:
        if row.get("empty"):
            continue
        if (row["geometry"], row["scale"], row["temporal"], row["k"]) != (
            geometry, scale, temporal, k
        ):
            continue
        per[row["symbol"]].append(row["singleton_fraction"])
    values = sorted(med(v) for v in per.values())
    return values


def sensitivity(rows, geometry, scale, temporal):
    """Does the zone map restructure chaotically between adjacent grid values?"""
    import itertools
    per = defaultdict(dict)
    for row in rows:
        if row.get("empty"):
            continue
        if (row["geometry"], row["scale"], row["temporal"]) != (
            geometry, scale, temporal
        ):
            continue
        per[(row["symbol"], row["timeframe"])][row["k"]] = row
    print(f"\n--- sensitivity: fractional change in zone count between "
          f"adjacent grid values ({geometry} / {scale} / {temporal}) ---")
    print(f"{'k_from':>8s}{'k_to':>8s}{'median |dz|/z':>16s}{'p90':>9s}")
    ks = sorted({k for series in per.values() for k in series})
    for a, b in itertools.pairwise(ks):
        deltas = []
        for series in per.values():
            if a in series and b in series and series[a]["n_zones"]:
                deltas.append(
                    abs(series[b]["n_zones"] - series[a]["n_zones"])
                    / series[a]["n_zones"]
                )
        if deltas:
            deltas.sort()
            print(f"{a:8.2f}{b:8.2f}{st.median(deltas):16.3f}"
                  f"{deltas[9 * len(deltas) // 10]:9.3f}")


def fixtures_table(payload):
    print("\n=== ADVERSARIAL FIXTURES ===")
    geometries = sorted(payload["fixtures"])
    names = [f["name"] for f in payload["fixtures"][geometries[0]]]
    print(f"{'#':>3s} {'fixture':18s}" + "".join(f"{g.replace('G-',''):>16s}" for g in geometries))
    for index, name in enumerate(names):
        cells = []
        for g in geometries:
            f = payload["fixtures"][g][index]
            cells.append(f"{'PASS' if f['passed'] else 'FAIL'} z={f['n_zones']} s={f['max_span_over_w']:.1f}")
        print(f"{index + 1:3d} {name:18s}" + "".join(f"{c:>16s}" for c in cells))


if __name__ == "__main__":
    payload = load()
    rows = payload["rows"]
    print(f"rows: {len(rows)}   symbols: "
          f"{len({r['symbol'] for r in rows})}   "
          f"capture: {payload['capture_digest'][:16]}")
    print("\n=== SECTION 6.1 ADMISSIBILITY GATE, PER GRID VALUE ===")
    print("k_max = largest k such that every criterion holds at that k and at "
          "every smaller k\n")
    verdicts = admissibility_by_k(rows)
    print("\nADMISSIBLE families (non-empty contiguous region from the grid floor):")
    for key, region in sorted(
        verdicts.items(), key=lambda kv: tuple(str(x) for x in kv[0])
    ):
        if region:
            print(f"    {key}  k in [{min(region):g}, {max(region):g}]  "
                  f"({len(region)} grid values)")

    fixtures_table(payload)

    winner = ("G-ANCHOR-EPOCH", "W-ATR", "T-ANCHOR")
    runner = ("G-ANCHOR-EPOCH", "W-STRUCT-CAUSAL", None)
    print("\n=== PLATEAU AND DESCRIPTIVE CURVES ===")
    for key in (winner, runner):
        plateau(rows, *key)
    for role in ("context", "setup", "execution"):
        plateau(rows, *winner, role=role)
    by_role(rows, *winner)
    sensitivity(rows, *winner)
    sensitivity(rows, *runner)
    print("\n=== CROSS-ASSET SPREAD (R20): singleton_fraction per asset ===")
    print(f"{'scale':17s}{'k':>6s}{'min':>8s}{'median':>9s}{'max':>8s}{'spread':>9s}")
    for key in (winner, runner):
        for k in (0.30, 0.50, 0.80, 1.00):
            values = cross_asset(rows, *key, k)
            if values:
                print(f"{key[1]:17s}{k:6.2f}{values[0]:8.3f}"
                      f"{st.median(values):9.3f}{values[-1]:8.3f}"
                      f"{values[-1] - values[0]:9.3f}")
