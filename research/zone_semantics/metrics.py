"""Descriptive diagnostics. Deliberately not a score.

Every function here answers one question about one zone set. Nothing combines
them, because a composite would let a policy buy a prefix-stability failure
with a good fragmentation number, and those are not exchangeable quantities.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb
from statistics import median

from research.zone_semantics.policies import Zone
from research.zone_semantics.structure import ResearchLevel


def describe(
    zones: Sequence[Zone],
    levels: Sequence[ResearchLevel],
    *,
    reference_atr: float | None,
    reference_price: float | None,
) -> dict:
    if not zones:
        return {"n_levels": len(levels), "n_zones": 0, "empty": True}
    sizes = [len(z.members) for z in zones]
    grouped = sum(size for size in sizes if size > 1)
    spans = [z.span for z in zones]
    widths = [z.high - z.low for z in zones]
    span_ratios = [
        z.span / z.width_used for z in zones if z.width_used > 0
    ]
    return {
        "n_levels": len(levels),
        "n_zones": len(zones),
        "n_placed": sum(sizes),
        "zones_per_level": len(zones) / sum(sizes),
        "singleton_fraction": sum(1 for s in sizes if s == 1) / len(zones),
        "merged_level_fraction": grouped / sum(sizes),
        "max_members": max(sizes),
        "mean_members": sum(sizes) / len(sizes),
        "median_span": median(spans),
        "max_span": max(spans),
        "max_span_over_w": max(span_ratios) if span_ratios else 0.0,
        "median_width_over_atr": (
            median(widths) / reference_atr if reference_atr else None
        ),
        "median_width_over_price": (
            median(widths) / reference_price if reference_price else None
        ),
        "overlap_fraction": _overlap_fraction(zones),
    }


def _overlap_fraction(zones: Sequence[Zone]) -> float:
    """Fraction of adjacent band pairs that intersect.

    Adjacent rather than all pairs: two zones at opposite ends of the range
    never overlap and counting them dilutes the signal toward zero for every
    policy equally.
    """
    if len(zones) < 2:
        return 0.0
    ordered = sorted(zones, key=lambda z: (z.low, z.high))
    hits = sum(
        1 for a, b in zip(ordered, ordered[1:]) if b.low <= a.high
    )
    return hits / (len(ordered) - 1)


def partition(zones: Sequence[Zone]) -> frozenset[frozenset]:
    """The zone set reduced to *which levels are together*, and nothing else."""
    return frozenset(z.member_keys for z in zones)


def adjusted_rand(a: Sequence[Zone], b: Sequence[Zone]) -> float | None:
    """ARI between two partitions of the same level set.

    `None` when the two runs placed different level sets — which happens
    whenever a warm-up boundary moved — because an ARI over different universes
    compares nothing.
    """
    keys_a = {k for z in a for k in z.member_keys}
    keys_b = {k for z in b for k in z.member_keys}
    if keys_a != keys_b or not keys_a:
        return None
    label_a = {k: i for i, z in enumerate(a) for k in z.member_keys}
    label_b = {k: i for i, z in enumerate(b) for k in z.member_keys}
    table: dict[tuple[int, int], int] = {}
    for key in keys_a:
        cell = (label_a[key], label_b[key])
        table[cell] = table.get(cell, 0) + 1
    n = len(keys_a)
    if n < 2:
        return 1.0
    rows: dict[int, int] = {}
    cols: dict[int, int] = {}
    for (i, j), count in table.items():
        rows[i] = rows.get(i, 0) + count
        cols[j] = cols.get(j, 0) + count
    index = sum(comb(c, 2) for c in table.values())
    exp_rows = sum(comb(c, 2) for c in rows.values())
    exp_cols = sum(comb(c, 2) for c in cols.values())
    total = comb(n, 2)
    expected = exp_rows * exp_cols / total
    maximum = (exp_rows + exp_cols) / 2.0
    if maximum == expected:
        return 1.0
    return (index - expected) / (maximum - expected)


PRESERVED = "PRESERVED"
GREW = "GREW"
BOUNDARY_REWRITTEN = "BOUNDARY_REWRITTEN"
SPLIT = "SPLIT"
MERGED = "MERGED"
VANISHED = "VANISHED"


def prefix_classification(
    prefix_zones: Sequence[Zone], full_zones: Sequence[Zone]
) -> dict[str, int]:
    """Classify what happened to each zone knowable at the prefix.

    `GREW` is legitimate: a zone gaining a member that only later became
    knowable is the lifecycle working as designed. `BOUNDARY_REWRITTEN`,
    `SPLIT`, `MERGED` and `VANISHED` are not — each one means a fact that was
    knowable at the prefix reads differently once the future arrives, which is
    the definition of repainting.
    """
    counts = {
        PRESERVED: 0,
        GREW: 0,
        BOUNDARY_REWRITTEN: 0,
        SPLIT: 0,
        MERGED: 0,
        VANISHED: 0,
    }
    owner: dict[tuple[int, int, str, float], int] = {
        key: i for i, z in enumerate(full_zones) for key in z.member_keys
    }
    destination: dict[int, list[int]] = {}
    for p_index, zone in enumerate(prefix_zones):
        targets = {owner[k] for k in zone.member_keys if k in owner}
        if not targets:
            counts[VANISHED] += 1
            continue
        if len(targets) > 1:
            counts[SPLIT] += 1
            continue
        target = targets.pop()
        destination.setdefault(target, []).append(p_index)
        full = full_zones[target]
        if not zone.member_keys <= full.member_keys:
            counts[VANISHED] += 1
            continue
        if _band_equal(zone, full):
            counts[PRESERVED if zone.member_keys == full.member_keys else GREW] += 1
        else:
            counts[BOUNDARY_REWRITTEN] += 1
    # Two prefix zones landing in one full zone is a merge, whatever the bands say.
    merged = sum(1 for sources in destination.values() if len(sources) > 1)
    if merged:
        counts[MERGED] += merged
    return counts


def _band_equal(a: Zone, b: Zone) -> bool:
    return a.low == b.low and a.high == b.high


def illegal(counts: dict[str, int]) -> int:
    return (
        counts[BOUNDARY_REWRITTEN]
        + counts[SPLIT]
        + counts[MERGED]
        + counts[VANISHED]
    )
