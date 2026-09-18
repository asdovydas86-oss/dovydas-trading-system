"""The measurement driver. Emits one machine-readable JSON result file.

Deterministic: no clock is read into a result, no random number is drawn, no
set is iterated without an explicit sort. Running it twice under different
`PYTHONHASHSEED` values must produce byte-identical output, and `verify.py`
checks exactly that.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.zone_semantics import dataset, fixtures, metrics  # noqa: E402
from research.zone_semantics.policies import (  # noqa: E402
    G_ANCHOR,
    G_ANCHOR_EPOCH,
    G_ANCHOR_FIRST,
    G_ANCHOR_GROW,
    G_DIAM,
    G_SINGLE,
    T_ANCHOR,
    T_CURRENT,
    T_LAST,
    W_ATR,
    W_PCT,
    W_STRUCT,
    W_STRUCT_CAUSAL,
    Candidate,
    WidthScale,
)
from research.zone_semantics.structure import (  # noqa: E402
    ResearchLevel,
    atr_by_index,
    levels_for,
)

GEOMETRIES = (
    G_SINGLE,
    G_DIAM,
    G_ANCHOR,
    G_ANCHOR_FIRST,
    G_ANCHOR_EPOCH,
    G_ANCHOR_GROW,
)

GRIDS = {
    W_ATR: (
        0.0, 0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
        0.55, 0.60, 0.70, 0.80, 1.00, 1.25, 1.50, 2.00, 3.00,
    ),
    W_PCT: (0.0, 0.0010, 0.0025, 0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300, 0.0500),
    W_STRUCT: (0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00, 4.00, 6.00, 8.00),
    W_STRUCT_CAUSAL: (0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00, 4.00, 6.00, 8.00),
}

PREFIX_CUTS = (0.60, 0.70, 0.80, 0.90)
SCALE_FACTORS = (1e-3, 1e3)
#: Powers of two rescale **exactly** in IEEE-754, so a disagreement under these
#: is a real unit dependence; a disagreement only under the decimal factors is
#: float sensitivity, and the two are different findings.
DYADIC_FACTORS = (2.0**-10, 2.0**10)
# The reflection is a **negation**, not `C - p`. Negating a float is exact in
# IEEE-754; subtracting from a constant is not, and an inexact reflection makes
# a symmetry test measure floating-point rounding instead of the policy. The
# offset form is kept as a second, weaker check.
MIRROR_OFFSET = 4.0


def _scales() -> list[WidthScale]:
    out: list[WidthScale] = []
    for k in GRIDS[W_ATR]:
        for temporal in (T_ANCHOR, T_LAST, T_CURRENT):
            out.append(WidthScale(W_ATR, k, temporal))
    for k in GRIDS[W_PCT]:
        out.append(WidthScale(W_PCT, k))
    for k in GRIDS[W_STRUCT]:
        out.append(WidthScale(W_STRUCT, k))
    for k in GRIDS[W_STRUCT_CAUSAL]:
        out.append(WidthScale(W_STRUCT_CAUSAL, k))
    return out


def _mirror_levels(
    levels: Sequence[ResearchLevel], about: float | None = None
) -> tuple[ResearchLevel, ...]:
    """Reflect the level set. ``about=None`` negates, which is exact."""
    flip = {"upper": "lower", "lower": "upper"}
    return tuple(
        ResearchLevel(
            price=(-lvl.price if about is None else about - lvl.price),
            side=flip[lvl.side],
            origin_index=lvl.origin_index,
            established_index=lvl.established_index,
            label=lvl.label,
            origin_timestamp=lvl.origin_timestamp,
            seq=lvl.seq,
        )
        for lvl in levels
    )


def _scale_levels(
    levels: Sequence[ResearchLevel], factor: float
) -> tuple[ResearchLevel, ...]:
    return tuple(
        ResearchLevel(
            price=lvl.price * factor,
            side=lvl.side,
            origin_index=lvl.origin_index,
            established_index=lvl.established_index,
            label=lvl.label,
            origin_timestamp=lvl.origin_timestamp,
            seq=lvl.seq,
        )
        for lvl in levels
    )


def _shape(zones) -> frozenset:
    """A partition reduced to *which levels sit together*, by `seq`.

    Prices are dropped because a transformed partition holds different prices by
    construction; what must survive is which structural facts are grouped.
    `seq` rather than `origin_index` because one candle can produce two levels,
    and keying on the candle merges them into one element — which made two
    genuinely different partitions compare equal, and one identical pair compare
    different.
    """
    blocks = frozenset(frozenset(m.seq for m in z.members) for z in zones)
    if any(-1 in block for block in blocks):
        raise AssertionError(
            "a level reached the shape comparison without a `seq`; some "
            "transform dropped it, and every comparison would silently be "
            "against the sentinel rather than against the level"
        )
    return blocks


def _timestamp_shape(zones, keep=None) -> frozenset:
    """A partition keyed by the pivot's **timestamp**, not its index.

    A run that starts at a different bar assigns different indices to the same
    pivot, so index-keyed comparison would report a difference that is purely
    an artefact of the offset. The timestamp is the same fact in both runs.
    """
    out = []
    for zone in zones:
        block = frozenset(
            m.origin_timestamp
            for m in zone.members
            if keep is None or m.origin_timestamp in keep
        )
        if block:
            out.append(block)
    return frozenset(out)


_WINDOW_CACHE: dict[tuple[str, str, int], object] = {}


def _window_inputs(series, fraction: float):
    """The later-start run's levels and ATR, computed **once per series**.

    Recomputing the structural chain inside the per-candidate loop cost 344
    identical `detect_swings` passes per series. The chain does not depend on
    the candidate, so it is computed once and the candidates read it.
    """
    key = (series.symbol, series.timeframe, len(series.closed().candles))
    hit = _WINDOW_CACHE.get(key)
    if hit is not None:
        return hit
    candles = series.closed().candles
    offset = int(len(candles) * fraction)
    if offset < 60 or len(candles) - offset < 200:
        value = None
    else:
        later = series.__class__(
            symbol=series.symbol, timeframe=series.timeframe, candles=candles[offset:]
        )
        value = (
            levels_for(series),
            atr_by_index(series),
            len(candles) - 1,
            levels_for(later),
            atr_by_index(later),
            len(later.closed().candles) - 1,
        )
    _WINDOW_CACHE.clear()
    _WINDOW_CACHE[key] = value
    return value


def window_start_agreement(
    candidate, series, *, fraction: float = 0.30
) -> float | None:
    """Does the same zone survive loading the symbol from a later start bar?

    **POST-HOC** — added after the preregistered battery left two scales
    standing, and added in the only direction that is honest: it can disqualify
    a candidate, never promote one. The question it asks is whether the
    tolerance is a property of the market or of how much history the caller
    happened to request. A policy that answers differently for the same pivot
    depending on where the download began is not describing the instrument.
    """
    cached = _window_inputs(series, fraction)
    if cached is None:
        return None
    full_levels, full_atr, full_last, part_levels, part_atr, part_last = cached
    if not full_levels or not part_levels:
        return None
    full_zones = candidate.zones(
        full_levels, atr=full_atr, last_index=full_last
    )
    part_zones = candidate.zones(
        part_levels, atr=part_atr, last_index=part_last
    )
    common = {lvl.origin_timestamp for lvl in full_levels} & {
        lvl.origin_timestamp for lvl in part_levels
    }
    if len(common) < 20:
        return None
    full_label = {
        ts: i
        for i, zone in enumerate(full_zones)
        for ts in (m.origin_timestamp for m in zone.members)
        if ts in common
    }
    part_label = {
        ts: i
        for i, zone in enumerate(part_zones)
        for ts in (m.origin_timestamp for m in zone.members)
        if ts in common
    }
    shared = sorted(set(full_label) & set(part_label), key=str)
    if len(shared) < 20:
        return None
    # Pairwise agreement: over every pair of shared pivots, do the two runs
    # agree on whether they belong together? That is the Rand index, computed
    # from the contingency table in O(n) rather than by enumerating the pairs —
    # the quadratic form cost 2M comparisons per candidate row and dominated the
    # whole study.
    from math import comb

    table: dict[tuple[int, int], int] = {}
    rows_: dict[int, int] = {}
    cols_: dict[int, int] = {}
    for ts in shared:
        i, j = full_label[ts], part_label[ts]
        table[(i, j)] = table.get((i, j), 0) + 1
        rows_[i] = rows_.get(i, 0) + 1
        cols_[j] = cols_.get(j, 0) + 1
    n = len(shared)
    total = comb(n, 2)
    if not total:
        return None
    both = sum(comb(v, 2) for v in table.values())
    only_full = sum(comb(v, 2) for v in rows_.values()) - both
    only_part = sum(comb(v, 2) for v in cols_.values()) - both
    neither = total - both - only_full - only_part
    return (both + neither) / total


def measure_series(symbol: str, universe: str, role: str, timeframe: str, series):
    levels = levels_for(series)
    atr = atr_by_index(series)
    last_index = len(series.closed().candles) - 1
    if not levels or not atr:
        return []

    reference_atr = atr[max(atr)]
    reference_price = series.closed().candles[-1].close

    prefixes = []
    for cut in PREFIX_CUTS:
        n = int(len(series.closed().candles) * cut)
        if n < 60:
            continue
        sub = series.__class__(
            symbol=series.symbol,
            timeframe=series.timeframe,
            candles=series.closed().candles[:n],
        )
        prefixes.append((cut, levels_for(sub), atr_by_index(sub), n - 1))

    mirrored = _mirror_levels(levels)
    mirrored_offset = _mirror_levels(
        levels, MIRROR_OFFSET * max(lvl.price for lvl in levels)
    )
    # Built once. Building them inside the candidate loop made every scale's
    # per-level width series a cache miss, which turned one O(n^2) causal scan
    # per series into several hundred.
    scaled = {
        factor: (_scale_levels(levels, factor), {i: v * factor for i, v in atr.items()})
        for factor in SCALE_FACTORS + DYADIC_FACTORS
    }

    rows: list[dict] = []
    for scale in _scales():
        for geometry in GEOMETRIES:
            candidate = Candidate(scale=scale, geometry=geometry)
            zones = candidate.zones(levels, atr=atr, last_index=last_index)
            row = {
                "symbol": symbol,
                "universe": universe,
                "role": role,
                "timeframe": timeframe,
                "geometry": geometry,
                "scale": scale.kind,
                "k": scale.k,
                "temporal": scale.temporal if scale.kind == W_ATR else None,
                "candidate_id": candidate.candidate_id,
            }
            row.update(
                metrics.describe(
                    zones,
                    levels,
                    reference_atr=reference_atr,
                    reference_price=reference_price,
                )
            )
            base = zones

            # --- scale invariance -------------------------------------------
            scale_ok = True
            dyadic_ok = True
            for factor in SCALE_FACTORS + DYADIC_FACTORS:
                scaled_levels, scaled_atr = scaled[factor]
                other = candidate.zones(
                    scaled_levels,
                    atr=scaled_atr,
                    last_index=last_index,
                )
                if _shape(other) != _shape(base):
                    if factor in DYADIC_FACTORS:
                        dyadic_ok = False
                    else:
                        scale_ok = False
            row["scale_invariant"] = scale_ok
            row["scale_invariant_exact"] = dyadic_ok

            # --- mirror symmetry --------------------------------------------
            mirror_zones = candidate.zones(
                mirrored, atr=atr, last_index=last_index
            )
            row["mirror_symmetric"] = _shape(mirror_zones) == _shape(base)
            row["mirror_offset_symmetric"] = _shape(
                candidate.zones(mirrored_offset, atr=atr, last_index=last_index)
            ) == _shape(base)

            # --- prefix stability -------------------------------------------
            totals = {
                metrics.PRESERVED: 0,
                metrics.GREW: 0,
                metrics.BOUNDARY_REWRITTEN: 0,
                metrics.SPLIT: 0,
                metrics.MERGED: 0,
                metrics.VANISHED: 0,
            }
            for _cut, p_levels, p_atr, p_last in prefixes:
                p_zones = candidate.zones(
                    p_levels, atr=p_atr, last_index=p_last
                )
                counts = metrics.prefix_classification(p_zones, zones)
                for key, value in counts.items():
                    totals[key] += value
            row["prefix"] = totals
            row["prefix_illegal"] = metrics.illegal(totals)
            row["window_agreement"] = window_start_agreement(candidate, series)
            rows.append(row)
    return rows


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "reports" / "artifacts"
    target = out_dir / "0050_zone_semantics_results.json"
    only: set[str] | None = None
    argv = sys.argv[1:]
    if argv:
        target = Path(argv[0])
    if len(argv) > 1:
        only = set(argv[1].split(","))

    loaded = dataset.load_capture()
    if only is not None:
        loaded = tuple(item for item in loaded if item.symbol in only)
    rows: list[dict] = []
    for item in loaded:
        for role, timeframe, series in dataset.role_series(item):
            rows.extend(
                measure_series(item.symbol, item.universe, role, timeframe, series)
            )
        print(f"  {item.symbol} done ({len(rows)} rows)", flush=True)

    fixture_results = {g: fixtures.run_all(g) for g in GEOMETRIES}

    payload = {
        "schema_version": 1,
        "preregistration": "docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md",
        "preregistration_sha256": (
            "d5a94b0558f5bc69e346b66300b0fba81a62d2e6847f2012c64ec0fbf50baed0"
        ),
        "capture_digest": dataset.capture_digest(),
        "grids": {k: list(v) for k, v in GRIDS.items()},
        "prefix_cuts": list(PREFIX_CUTS),
        "scale_factors": list(SCALE_FACTORS),
        "fixtures": fixture_results,
        "rows": rows,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    print(f"wrote {target} ({target.stat().st_size} bytes, {len(rows)} rows)")


if __name__ == "__main__":
    main()
