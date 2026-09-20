"""Every table in report 0052, computed from the committed event artifact.

    .venv/bin/python research/zone_interactions/analyze.py

A pure function of `0052_zone_interaction_events.json.gz` plus the constants
the preregistration fixed. It chooses nothing: the horizons, the bins, the
grids, the cluster unit, the bootstrap seed, the minimum-cell rule and the
verdict thresholds all come from §3, §4, §7 and §9, and are imported here as
named constants rather than typed in again.
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))

from zone_interactions.events import ABSENT  # noqa: E402
from zone_interactions.run import write_gzip_json  # noqa: E402
from zone_interactions.stats import (  # noqa: E402
    cluster_bootstrap,
    holm,
    rate,
    wilcoxon_signed_rank,
)

EVENTS = ROOT / "reports" / "artifacts" / "0052_zone_interaction_events.json.gz"
OUT = ROOT / "reports" / "artifacts" / "0052_zone_interaction_tables.json.gz"

ROLES = ("context", "setup", "execution")
ROLE_TF = {"context": "1w", "setup": "1d", "execution": "4h"}
UNIVERSES = ("primary", "holdout")

#: §3.4 / §4.3, sealed.
H_PRIMARY = 10
H_SENSITIVITY = (5, 20)
DISP_BINS = ((None, 0.25), (0.25, 0.75), (0.75, None))
DISP_LABELS = ("<0.25", "0.25-0.75", ">=0.75")
ELAPSED_BINS = ((1, 1), (2, 3), (4, 6), (7, 10), (11, 20), (21, 40))

#: §7.3 minimum-cell rule, sealed.
MIN_EVENTS = 200
MIN_SYMBOLS = 10
MIN_PER_SYMBOL = 5

#: §9 verdict thresholds, sealed.
R3_SEPARATION_POINTS = 0.10
R4_HAZARD_RATIO = 1.25


# ---------------------------------------------------------------------------
# loading


class Table:
    """Row-wise access over the columnar artifact, without copying it."""

    def __init__(self, data: dict[str, list]) -> None:
        self.data = data
        self.n = len(data["t0"]) if data else 0

    def col(self, name: str) -> list:
        return self.data[name]

    def select(self, mask: list[bool]) -> "Table":
        return Table({k: [v for v, m in zip(values, mask) if m] for k, values in self.data.items()})


def load() -> tuple[dict, Table, Table]:
    with gzip.open(EVENTS, "rt") as handle:
        payload = json.load(handle)
    return payload["manifest"], Table(payload["real"]), Table(payload["placebo"])


def mask_of(table: Table, universe: int, role: int) -> list[bool]:
    u = table.col("universe")
    r = table.col("role")
    return [a == universe and b == role for a, b in zip(u, r)]


# ---------------------------------------------------------------------------
# R3


def _cell_ok(hits_by_symbol: dict[int, tuple[int, int]]) -> tuple[bool, int, int]:
    """§7.3, applied mechanically before any effect is read."""
    total = sum(n for _, n in hits_by_symbol.values())
    qualifying = sum(1 for _, n in hits_by_symbol.values() if n >= MIN_PER_SYMBOL)
    return (total >= MIN_EVENTS and qualifying >= MIN_SYMBOLS), total, qualifying


def group_rates(
    table: Table, group: list[int], outcome: str, valid: list[bool]
) -> dict[int, dict[int, tuple[int, int]]]:
    """`{group label: {symbol: (hits, n)}}` over rows where the outcome exists."""
    out: dict[int, dict[int, tuple[int, int]]] = defaultdict(lambda: defaultdict(lambda: (0, 0)))
    values = table.col(outcome)
    symbols = table.col("symbol")
    for i, ok in enumerate(valid):
        if not ok:
            continue
        v = values[i]
        if v == ABSENT or v is None:
            continue
        label = group[i]
        if label is None:
            continue
        hits, n = out[label][symbols[i]]
        out[label][symbols[i]] = (hits + (1 if v == 1 else 0), n + 1)
    return {k: dict(v) for k, v in out.items()}


def compare_two(
    by_symbol: dict[int, dict[int, tuple[int, int]]], a: int, b: int
) -> dict:
    """Group `b` minus group `a`, clustered on the symbol (§7.2)."""
    ga = by_symbol.get(a, {})
    gb = by_symbol.get(b, {})
    ok_a, n_a, sym_a = _cell_ok(ga)
    ok_b, n_b, sym_b = _cell_ok(gb)

    pooled_a = rate(sum(h for h, _ in ga.values()), sum(n for _, n in ga.values()))
    pooled_b = rate(sum(h for h, _ in gb.values()), sum(n for _, n in gb.values()))

    result = {
        "n_a": n_a,
        "n_b": n_b,
        "symbols_a": sym_a,
        "symbols_b": sym_b,
        "rate_a": pooled_a,
        "rate_b": pooled_b,
        "difference": (pooled_b - pooled_a) if (pooled_a is not None and pooled_b is not None) else None,
        "reportable": ok_a and ok_b,
    }
    if not result["reportable"]:
        result["verdict_cell"] = "UNDERPOWERED"
        return result

    shared = [s for s in ga if s in gb and ga[s][1] >= MIN_PER_SYMBOL and gb[s][1] >= MIN_PER_SYMBOL]
    diffs = [gb[s][0] / gb[s][1] - ga[s][0] / ga[s][1] for s in shared]
    p, used = wilcoxon_signed_rank(diffs)

    bundles = [(ga[s], gb[s]) for s in shared]

    def statistic(sample):
        ha = sum(x[0][0] for x in sample)
        na = sum(x[0][1] for x in sample)
        hb = sum(x[1][0] for x in sample)
        nb = sum(x[1][1] for x in sample)
        if not na or not nb:
            return None
        return hb / nb - ha / na

    lo, hi, boot_p = cluster_bootstrap(bundles, statistic)
    result.update(
        {
            "paired_symbols": len(shared),
            "median_symbol_difference": sorted(diffs)[len(diffs) // 2] if diffs else None,
            "wilcoxon_p": p,
            "wilcoxon_n": used,
            "ci_low": lo,
            "ci_high": hi,
            "bootstrap_p": boot_p,
            "verdict_cell": "REPORTABLE",
        }
    )
    return result


def disp_label(value) -> int | None:
    if value is None:
        return None
    for k, (lo, hi) in enumerate(DISP_BINS):
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return k
    return None


def r3_tables(real: Table) -> dict:
    out: dict = {}
    for ui, universe in enumerate(UNIVERSES):
        for ri, role in enumerate(ROLES):
            base = mask_of(real, ui, ri)
            b1 = real.col("beyond_at_1")
            b2 = real.col("beyond_at_2")
            disp = real.col("disp_atr")

            for h in (H_PRIMARY,) + H_SENSITIVITY:
                for metric in ("m1", "m2"):
                    # C1 — does close #2 add information? Classified at t0+1.
                    col = f"{metric}_C1_{h}"
                    group = [0 if v == 0 else (1 if v == 1 else None) for v in b1]
                    valid = [m and g is not None for m, g in zip(base, group)]
                    out[f"C1|{universe}|{role}|{metric}|H{h}"] = compare_two(
                        group_rates(real, group, col, valid), 0, 1
                    )

                    # C2 — does close #3 add information? Conditional on #2.
                    col = f"{metric}_C2_{h}"
                    group = [
                        (0 if y == 0 else (1 if y == 1 else None)) if x == 1 else None
                        for x, y in zip(b1, b2)
                    ]
                    valid = [m and g is not None for m, g in zip(base, group)]
                    out[f"C2|{universe}|{role}|{metric}|H{h}"] = compare_two(
                        group_rates(real, group, col, valid), 0, 1
                    )

                    # C3 — displacement, classified at t0.
                    col = f"{metric}_C3_{h}"
                    group = [disp_label(v) for v in disp]
                    valid = [m and g is not None for m, g in zip(base, group)]
                    rates = group_rates(real, group, col, valid)
                    out[f"C3|{universe}|{role}|{metric}|H{h}"] = {
                        "bins": {
                            DISP_LABELS[k]: {
                                "n": sum(n for _, n in rates.get(k, {}).values()),
                                "rate": rate(
                                    sum(x for x, _ in rates.get(k, {}).values()),
                                    sum(n for _, n in rates.get(k, {}).values()),
                                ),
                                "symbols": len(rates.get(k, {})),
                            }
                            for k in range(len(DISP_BINS))
                        },
                        "far_minus_near": compare_two(rates, 0, 2),
                    }

            # C4 — the joint table, at the primary horizon only.
            col = f"m1_C1_{H_PRIMARY}"
            joint: dict[str, dict] = {}
            for d in range(len(DISP_BINS)):
                group = [
                    (0 if x == 0 else (1 if x == 1 else None))
                    if disp_label(v) == d
                    else None
                    for x, v in zip(b1, disp)
                ]
                valid = [m and g is not None for m, g in zip(base, group)]
                joint[DISP_LABELS[d]] = compare_two(group_rates(real, group, col, valid), 0, 1)
            out[f"C4|{universe}|{role}"] = joint

            # descriptive splits the preregistration requires (§22 of the brief)
            side = real.col("side")
            gap = real.col("gapped")
            over = real.col("overlap_inside")
            m1 = real.col(f"m1_C1_{H_PRIMARY}")
            desc: dict[str, dict] = {}
            for name, selector in (
                ("upward", lambda i: side[i] == 1),
                ("downward", lambda i: side[i] == -1),
                ("gapped", lambda i: gap[i]),
                ("continuous", lambda i: not gap[i]),
                ("overlap_none", lambda i: over[i] <= 1),
                ("overlap_some", lambda i: over[i] > 1),
            ):
                idx = [i for i, m in enumerate(base) if m and selector(i) and m1[i] != ABSENT]
                hits = sum(1 for i in idx if m1[i] == 1)
                desc[name] = {"n": len(idx), "rate": rate(hits, len(idx))}
            out[f"DESC|{universe}|{role}"] = desc
    return out


# ---------------------------------------------------------------------------
# R4


def hazard(table: Table, mask: list[bool], j_max: int) -> dict[int, tuple[int, int]]:
    """`{elapsed j: (returns at j, at risk at j)}`, right-censored (§4.3)."""
    j_close = table.col("j_close")
    censored = table.col("censored_at")
    events = defaultdict(int)
    at_risk = defaultdict(int)
    for i, ok in enumerate(mask):
        if not ok:
            continue
        jc = j_close[i]
        observed = jc if jc != ABSENT else censored[i]
        if observed < 1:
            continue
        limit = min(observed, j_max)
        for j in range(1, limit + 1):
            at_risk[j] += 1
        if jc != ABSENT and jc <= j_max:
            events[jc] += 1
    return {j: (events[j], at_risk[j]) for j in range(1, j_max + 1) if at_risk[j]}


def binned(curve: dict[int, tuple[int, int]], j_max: int) -> dict[str, tuple[int, int]]:
    """Person-bar return rate per preregistered elapsed bin."""
    out: dict[str, tuple[int, int]] = {}
    for lo, hi in ELAPSED_BINS:
        if lo > j_max:
            continue
        top = min(hi, j_max)
        e = sum(curve.get(j, (0, 0))[0] for j in range(lo, top + 1))
        r = sum(curve.get(j, (0, 0))[1] for j in range(lo, top + 1))
        out[f"{lo}-{hi}" if lo != hi else str(lo)] = (e, r)
    return out


def r4_tables(real: Table, plac: Table) -> dict:
    out: dict = {}
    clean = [not c for c in plac.col("contaminated")]
    out["placebo_contamination"] = {
        "events": plac.n,
        "clean": sum(clean),
        "contaminated": plac.n - sum(clean),
        "clean_fraction": rate(sum(clean), plac.n),
    }

    for ui, universe in enumerate(UNIVERSES):
        for ri, role in enumerate(ROLES):
            j_max = 20 if role == "context" else 40
            rmask = mask_of(real, ui, ri)
            pmask = [m and c for m, c in zip(mask_of(plac, ui, ri), clean)]
            pall = mask_of(plac, ui, ri)

            r_curve = hazard(real, rmask, j_max)
            p_curve = hazard(plac, pmask, j_max)
            pa_curve = hazard(plac, pall, j_max)

            r_bin = binned(r_curve, j_max)
            p_bin = binned(p_curve, j_max)
            pa_bin = binned(pa_curve, j_max)

            # Cluster bootstrap of the hazard ratio, resampling symbols.
            r_sym = _by_symbol_curve(real, rmask, j_max)
            p_sym = _by_symbol_curve(plac, pmask, j_max)
            shared = sorted(set(r_sym) & set(p_sym))
            bundles = [(r_sym[s], p_sym[s]) for s in shared]

            bins_out: dict[str, dict] = {}
            for key in r_bin:
                lo, hi = _bin_bounds(key)

                def statistic(sample, lo=lo, hi=hi):
                    re_ = sum(sum(x[0].get(j, (0, 0))[0] for j in range(lo, hi + 1)) for x in sample)
                    rr = sum(sum(x[0].get(j, (0, 0))[1] for j in range(lo, hi + 1)) for x in sample)
                    pe = sum(sum(x[1].get(j, (0, 0))[0] for j in range(lo, hi + 1)) for x in sample)
                    pr = sum(sum(x[1].get(j, (0, 0))[1] for j in range(lo, hi + 1)) for x in sample)
                    if not rr or not pr or not pe:
                        return None
                    return (re_ / rr) - (pe / pr)

                clo, chi, cp = cluster_bootstrap(bundles, statistic)
                re_, rr = r_bin[key]
                pe, pr = p_bin.get(key, (0, 0))
                bins_out[key] = {
                    "real_returns": re_,
                    "real_at_risk": rr,
                    "real_rate": rate(re_, rr),
                    "placebo_returns": pe,
                    "placebo_at_risk": pr,
                    "placebo_rate": rate(pe, pr),
                    "placebo_all_rate": rate(*pa_bin.get(key, (0, 0))[::1])
                    if pa_bin.get(key, (0, 0))[1]
                    else None,
                    "ratio": (re_ / rr) / (pe / pr) if rr and pr and pe else None,
                    "difference": (re_ / rr) - (pe / pr) if rr and pr else None,
                    "ci_low": clo,
                    "ci_high": chi,
                    "bootstrap_p": cp,
                    "symbols": len(shared),
                    "reportable": rr >= MIN_EVENTS and pr >= MIN_EVENTS and len(shared) >= MIN_SYMBOLS,
                }
            out[f"HAZ|{universe}|{role}"] = {
                "j_max": j_max,
                "real_events": sum(1 for m in rmask if m),
                "placebo_clean_events": sum(1 for m in pmask if m),
                "curve_real": {str(j): r_curve[j] for j in sorted(r_curve)},
                "curve_placebo": {str(j): p_curve[j] for j in sorted(p_curve)},
                "bins": bins_out,
            }

            # R4-D: split by whether a second consecutive close occurred.
            b1 = real.col("beyond_at_1")
            for label, want in (("single", 0), ("double", 1)):
                sub = [m and b1[i] == want for i, m in enumerate(rmask)]
                out[f"HAZ_{label}|{universe}|{role}"] = {
                    "events": sum(1 for m in sub if m),
                    "bins": {
                        k: {"returns": v[0], "at_risk": v[1], "rate": rate(v[0], v[1])}
                        for k, v in binned(hazard(real, sub, j_max), j_max).items()
                    },
                }

            # R4-E: excursion preconditions.
            exc = real.col("excursion_atr")
            for threshold in (0.0, 0.5, 1.0):
                sub = [
                    m and exc[i] is not None and exc[i] >= threshold
                    for i, m in enumerate(rmask)
                ]
                psub = [
                    m and plac.col("excursion_atr")[i] is not None
                    and plac.col("excursion_atr")[i] >= threshold
                    for i, m in enumerate(pmask)
                ]
                rb = binned(hazard(real, sub, j_max), j_max)
                pb = binned(hazard(plac, psub, j_max), j_max)
                out[f"EXC{threshold}|{universe}|{role}"] = {
                    "real_events": sum(1 for m in sub if m),
                    "placebo_events": sum(1 for m in psub if m),
                    "bins": {
                        k: {
                            "real_rate": rate(*rb[k]),
                            "placebo_rate": rate(*pb[k]) if k in pb else None,
                            "ratio": (rb[k][0] / rb[k][1]) / (pb[k][0] / pb[k][1])
                            if k in pb and rb[k][1] and pb[k][1] and pb[k][0]
                            else None,
                        }
                        for k in rb
                    },
                }

            # R4-A: the touch definition, as a whole-curve alternative.
            out[f"HAZ_TOUCH|{universe}|{role}"] = {
                "bins": {
                    k: {"returns": v[0], "at_risk": v[1], "rate": rate(v[0], v[1])}
                    for k, v in binned(
                        _hazard_touch(real, rmask, j_max), j_max
                    ).items()
                },
                "placebo_bins": {
                    k: {"returns": v[0], "at_risk": v[1], "rate": rate(v[0], v[1])}
                    for k, v in binned(
                        _hazard_touch(plac, pmask, j_max), j_max
                    ).items()
                },
            }
    return out


def _bin_bounds(key: str) -> tuple[int, int]:
    if "-" in key:
        lo, hi = key.split("-")
        return int(lo), int(hi)
    return int(key), int(key)


def _by_symbol_curve(table: Table, mask: list[bool], j_max: int) -> dict[int, dict]:
    symbols = table.col("symbol")
    out: dict[int, dict] = {}
    for s in sorted({symbols[i] for i, m in enumerate(mask) if m}):
        sub = [m and symbols[i] == s for i, m in enumerate(mask)]
        out[s] = hazard(table, sub, j_max)
    return out


def _hazard_touch(table: Table, mask: list[bool], j_max: int) -> dict[int, tuple[int, int]]:
    j_touch = table.col("j_touch")
    censored = table.col("censored_at")
    events = defaultdict(int)
    at_risk = defaultdict(int)
    for i, ok in enumerate(mask):
        if not ok:
            continue
        jt = j_touch[i]
        observed = jt if jt != ABSENT else censored[i]
        if observed < 1:
            continue
        for j in range(1, min(observed, j_max) + 1):
            at_risk[j] += 1
        if jt != ABSENT and jt <= j_max:
            events[jt] += 1
    return {j: (events[j], at_risk[j]) for j in range(1, j_max + 1) if at_risk[j]}


def intervening(real: Table) -> dict:
    """R4-F: other bands' transitions inside this band's outside episode.

    Within one band, episodes are disjoint, so every other transition falling
    strictly inside `(t0, t_return)` necessarily belongs to a different band.
    No band identity is needed to count them.
    """
    by_series: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(real.n):
        by_series[(real.col("symbol")[i], real.col("role")[i])].append(real.col("t0")[i])
    for key in by_series:
        by_series[key].sort()

    from bisect import bisect_left, bisect_right

    counts = defaultdict(int)
    total = 0
    for i in range(real.n):
        jc = real.col("j_close")[i]
        if jc == ABSENT:
            continue
        t0 = real.col("t0")[i]
        series = by_series[(real.col("symbol")[i], real.col("role")[i])]
        n = bisect_left(series, t0 + jc) - bisect_right(series, t0)
        counts[min(n, 10)] += 1
        total += 1
    return {
        "episodes": total,
        "distribution": {str(k): counts[k] for k in sorted(counts)},
        "with_none": counts[0],
        "fraction_with_none": rate(counts[0], total),
    }


# ---------------------------------------------------------------------------


def main() -> None:
    manifest, real, plac = load()
    print(f"real {real.n:,}  placebo {plac.n:,}")

    tables = {
        "manifest": manifest,
        "r3": r3_tables(real),
        "r4": r4_tables(real, plac),
        "intervening": intervening(real),
    }

    # Holm within each preregistered family (§7.5).
    r3_family = [
        (key, tables["r3"][key]["wilcoxon_p"])
        for key in tables["r3"]
        if key.startswith(("C1|", "C2|"))
        and f"|m1|H{H_PRIMARY}" in key
        and "wilcoxon_p" in tables["r3"][key]
    ]
    r4_family = [
        (f"{key}::{b}", cell["bootstrap_p"])
        for key, block in tables["r4"].items()
        if key.startswith("HAZ|")
        for b, cell in block["bins"].items()
        if cell.get("bootstrap_p") is not None
    ]
    tables["holm_r3"] = holm(r3_family)
    tables["holm_r4"] = holm(r4_family)

    digest = write_gzip_json(OUT, tables)
    print(f"wrote {OUT.name}  sha256 {digest}")


if __name__ == "__main__":
    main()
