"""The candidate policies — three distance scales x three grouping geometries.

The preregistration's claim is that 0047 §43-D1 is three decisions, not one:

    A1  in what units is "close enough" expressed?      -> WidthScale
    A2  given a distance w, how do levels become zones? -> Geometry
    A3  when is a volatility-derived scale read?        -> TemporalRef

They are separated here so that a failure can be attributed to one of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from research.zone_semantics.structure import ResearchLevel, atr_at

# --------------------------------------------------------------------------
# A1 / A3 — the distance scale
# --------------------------------------------------------------------------

W_ATR = "W-ATR"
W_PCT = "W-PCT"
W_STRUCT = "W-STRUCT"
W_STRUCT_CAUSAL = "W-STRUCT-CAUSAL"

T_ANCHOR = "T-ANCHOR"
T_LAST = "T-LAST"
T_CURRENT = "T-CURRENT"


@dataclass(frozen=True, slots=True)
class WidthScale:
    """Produces a per-level width `w(L)`.

    `w` is a property of a **level**, not of a run, because every volatility-
    derived scale must be read at some bar and different levels became knowable
    at different bars. Collapsing it to one number per run would silently answer
    A3 with `T-CURRENT` and hide the decision.
    """

    kind: str
    k: float
    temporal: str = T_ANCHOR

    @property
    def policy_id(self) -> str:
        suffix = f"@{self.temporal}" if self.kind == W_ATR else ""
        return f"{self.kind}(k={self.k:g}){suffix}"

    def widths(
        self,
        levels: Sequence[ResearchLevel],
        *,
        atr: dict[int, float],
        last_index: int,
    ) -> tuple[float | None, ...]:
        if self.kind == W_PCT:
            return tuple(self.k * level.price for level in levels)
        if self.kind == W_STRUCT:
            scale = _structural_scale(levels)
            if scale is None:
                return tuple(None for _ in levels)
            return tuple(self.k * scale for _ in levels)
        if self.kind == W_STRUCT_CAUSAL:
            return tuple(
                None if s is None else self.k * s
                for s in causal_structural_scale(levels)
            )
        if self.kind == W_ATR:
            out: list[float | None] = []
            for level in levels:
                index = (
                    last_index if self.temporal == T_CURRENT else level.established_index
                )
                value = atr_at(atr, index)
                out.append(None if value is None else self.k * value)
            return tuple(out)
        raise ValueError(f"unknown width scale {self.kind!r}")


def _structural_scale(levels: Sequence[ResearchLevel]) -> float | None:
    """Median absolute gap between price-sorted adjacent levels.

    The structure's own spacing, used as its own yardstick. It needs no
    indicator and has no warm-up, which is the entire reason this candidate is
    in the set: if it works, the ATR dependency and with it the whole of A3
    disappears.
    """
    if len(levels) < 2:
        return None
    prices = sorted(level.price for level in levels)
    gaps = [b - a for a, b in zip(prices, prices[1:]) if b > a]
    if not gaps:
        return None
    return median(gaps)


_CAUSAL_CACHE: dict[int, tuple[float | None, ...]] = {}
#: `id()` is only unique among *live* objects, so a cache keyed on it must pin
#: its keys alive or a freed tuple's address will be reused and silently return
#: another series' answer. This list is that pin, and the bound is what stops it
#: becoming a leak.
_CAUSAL_KEEP: list = []


def causal_structural_scale(
    levels: Sequence[ResearchLevel],
) -> tuple[float | None, ...]:
    """`W-STRUCT`, restricted to what was knowable when each level arrived.

    The plain `W-STRUCT` reads the median gap of the **whole** level set, which
    is not a quantity that existed at the moment a zone was established — it
    includes levels from the future. Rejecting the idea on that basis would be
    rejecting an implementation choice and calling it a property of the family,
    so this variant computes, for each level in establishment order, the median
    adjacent gap over **only the levels already knowable**, and the comparison
    against `W-ATR` becomes a fair one.

    Memoised on the level tuple's identity because the series is independent of
    `k`: eleven grid values would otherwise pay for the same O(n^2) scan eleven
    times.
    """
    cache_key = id(levels)
    hit = _CAUSAL_CACHE.get(cache_key)
    if hit is not None and len(hit) == len(levels):
        return hit
    _CAUSAL_KEEP.append(levels)  # hold a reference so `id` cannot be recycled
    if len(_CAUSAL_KEEP) > 64:
        stale = _CAUSAL_KEEP.pop(0)
        _CAUSAL_CACHE.pop(id(stale), None)
    # Ordered by establishment bar only, and applied **per bar**. Ordering by
    # `key` inside a bar would break the tie on `side` and `price`, both of which
    # invert under reflection — the same defect the geometry carried, and it is
    # repaired here too so the two scale families are judged on equal terms
    # rather than on which one happened to get its bug found first.
    order = sorted(range(len(levels)), key=lambda i: levels[i].established_index)
    seen: list[float] = []
    out: list[float | None] = [None] * len(levels)
    import bisect

    position = 0
    while position < len(order):
        end = position
        bar = levels[order[position]].established_index
        while end < len(order) and levels[order[end]].established_index == bar:
            end += 1
        # Every level of this bar reads the scale as it stood *before* the bar,
        # then they are all inserted together.
        scale = None
        if len(seen) >= 2:
            gaps = [b - a for a, b in zip(seen, seen[1:]) if b > a]
            scale = median(gaps) if gaps else None
        for slot in order[position:end]:
            out[slot] = scale
        for slot in order[position:end]:
            bisect.insort(seen, levels[slot].price)
        position = end
    result = tuple(out)
    _CAUSAL_CACHE[cache_key] = result
    return result


# --------------------------------------------------------------------------
# A2 — the grouping geometry
# --------------------------------------------------------------------------

G_SINGLE = "G-SINGLE"
G_DIAM = "G-DIAM"
G_ANCHOR = "G-ANCHOR"
G_ANCHOR_GROW = "G-ANCHOR-GROW"
G_ANCHOR_FIRST = "G-ANCHOR-FIRST"
G_ANCHOR_EPOCH = "G-ANCHOR-EPOCH"


@dataclass(frozen=True, slots=True)
class Zone:
    members: tuple[ResearchLevel, ...]
    low: float
    high: float
    anchor_index: int
    established_index: int
    width_used: float

    @property
    def span(self) -> float:
        prices = [m.price for m in self.members]
        return max(prices) - min(prices)

    @property
    def member_keys(self) -> frozenset[tuple[int, int, str, float]]:
        return frozenset(m.key for m in self.members)

    @property
    def band(self) -> tuple[float, float]:
        return (self.low, self.high)


def group(
    geometry: str,
    levels: Sequence[ResearchLevel],
    widths: Sequence[float | None],
) -> tuple[Zone, ...]:
    """Partition ``levels`` into zones under ``geometry``.

    A level whose width is `None` (the feature had not warmed up when it became
    knowable) is **excluded entirely** rather than given a default. A default
    here would be an invented threshold introduced at the exact point the study
    exists to avoid one.
    """
    pairs = [(lvl, w) for lvl, w in zip(levels, widths) if w is not None]
    if not pairs:
        return ()
    if geometry == G_SINGLE:
        return _single_link(pairs)
    if geometry == G_DIAM:
        return _bounded_diameter(pairs)
    if geometry == G_ANCHOR:
        return _anchored(pairs)
    if geometry == G_ANCHOR_GROW:
        return _anchored(pairs, grow=True)
    if geometry == G_ANCHOR_FIRST:
        return _anchored(pairs, tie=_TIE_FIRST)
    if geometry == G_ANCHOR_EPOCH:
        return _anchored(pairs, tie=_TIE_FIRST, epoch=True)
    raise ValueError(f"unknown geometry {geometry!r}")


def _sorted_by_price(
    pairs: Sequence[tuple[ResearchLevel, float]],
) -> list[tuple[ResearchLevel, float]]:
    # Price first, then a total order over the level's own identity, so two
    # levels at an identical price never depend on input order.
    return sorted(pairs, key=lambda p: (p[0].price, p[0].key))


def _zone_from(members: Sequence[tuple[ResearchLevel, float]]) -> Zone:
    levels = tuple(m[0] for m in members)
    prices = [lvl.price for lvl in levels]
    return Zone(
        members=levels,
        low=min(prices),
        high=max(prices),
        anchor_index=min(lvl.established_index for lvl in levels),
        established_index=max(lvl.established_index for lvl in levels),
        width_used=min(m[1] for m in members),
    )


def _single_link(pairs: Sequence[tuple[ResearchLevel, float]]) -> tuple[Zone, ...]:
    """Cut the price-sorted run wherever the adjacent gap exceeds the tolerance.

    The tolerance for a pair is `min(w_a, w_b)` — symmetric, so the rule cannot
    depend on which of the two is read first.
    """
    ordered = _sorted_by_price(pairs)
    out: list[Zone] = []
    run: list[tuple[ResearchLevel, float]] = [ordered[0]]
    for previous, current in zip(ordered, ordered[1:]):
        if current[0].price - previous[0].price <= min(previous[1], current[1]):
            run.append(current)
        else:
            out.append(_zone_from(run))
            run = [current]
    out.append(_zone_from(run))
    return tuple(out)


def _bounded_diameter(pairs: Sequence[tuple[ResearchLevel, float]]) -> tuple[Zone, ...]:
    """Greedy over price-sorted levels; the zone's **total span** stays within w.

    The standard defence against chaining: it is the distance to the zone's
    far edge that is tested, not the distance to its nearest member.
    """
    ordered = _sorted_by_price(pairs)
    out: list[Zone] = []
    run: list[tuple[ResearchLevel, float]] = [ordered[0]]
    for current in ordered[1:]:
        candidate = run + [current]
        span = candidate[-1][0].price - candidate[0][0].price
        if span <= min(m[1] for m in candidate):
            run = candidate
        else:
            out.append(_zone_from(run))
            run = [current]
    out.append(_zone_from(run))
    return tuple(out)


_TIE_NEAREST = "nearest-centre"
_TIE_FIRST = "first-band"


def _anchored(
    pairs: Sequence[tuple[ResearchLevel, float]],
    *,
    grow: bool = False,
    tie: str = _TIE_NEAREST,
    epoch: bool = False,
) -> tuple[Zone, ...]:
    """Online, in establishment order, with **immutable** bands.

    Each level either falls inside a band already written, or writes a new one
    centred on itself. A band, once written, is never moved, widened or split.
    That is the whole idea: the only way to be prefix-stable by construction is
    to make the historical record unrewritable rather than to check afterwards
    that nothing rewrote it.

    ``tie`` selects what happens when a level falls inside **two** bands, which
    is common because bands overlap. The preregistration specified
    ``nearest-centre``; measurement rejected it. Comparing two centre distances
    means the outcome turns on the *difference* of two nearly equal floats, so a
    rescaling that perturbs both by one ulp can flip the assignment — and it did,
    on roughly a third of the 4h series. ``first-band`` compares nothing: the
    oldest band that already contains the level claims it. That is a comparison
    against a boundary rather than between two distances, it is stable under any
    perturbation smaller than the distance to that boundary, and it says
    something defensible — the area that was already there keeps the level.
    """
    ordered = sorted(pairs, key=lambda p: (p[0].established_index, p[0].key))
    bands: list[tuple[float, float, float, float, list[ResearchLevel], int]] = []
    # (low, high, centre, width, members, creation order)
    if epoch:
        return _anchored_epoch(ordered, tie=tie)
    for level, width in ordered:
        containing = [
            (abs(level.price - band[2]), band[5], index)
            for index, band in enumerate(bands)
            if band[0] <= level.price <= band[1]
        ]
        if containing:
            if tie == _TIE_FIRST:
                target = min(containing, key=lambda c: c[1])[2]
            else:
                containing.sort()
                target = containing[0][2]
            bands[target][4].append(level)
            if grow:
                # Section 13's question, made answerable: re-size the band to the
                # joining member's own volatility and keep the centre. This is
                # the only way a zone can "adapt" to later volatility, and the
                # prefix test measures what that costs.
                low, high, centre, _w, members, order = bands[target]
                half = width / 2.0
                bands[target] = (
                    min(low, centre - half),
                    max(high, centre + half),
                    centre,
                    max(_w, width),
                    members,
                    order,
                )
            continue
        half = width / 2.0
        bands.append(
            (
                level.price - half,
                level.price + half,
                level.price,
                width,
                [level],
                len(bands),
            )
        )
    out: list[Zone] = []
    for low, high, _centre, width, members, _order in bands:
        out.append(
            Zone(
                members=tuple(members),
                low=low,
                high=high,
                anchor_index=members[0].established_index,
                established_index=max(m.established_index for m in members),
                width_used=width,
            )
        )
    return tuple(sorted(out, key=lambda z: (z.low, z.high)))


def _anchored_epoch(
    ordered: Sequence[tuple[ResearchLevel, float]], *, tie: str
) -> tuple[Zone, ...]:
    """`_anchored`, with one establishment bar treated as one indivisible instant."""
    bands: list[list] = []  # [low, high, centre, width, members]
    position = 0
    while position < len(ordered):
        end = position
        bar = ordered[position][0].established_index
        while end < len(ordered) and ordered[end][0].established_index == bar:
            end += 1
        existing = len(bands)
        opened: list[list] = []
        for level, width in ordered[position:end]:
            target = None
            for index in range(existing):
                band = bands[index]
                if band[0] <= level.price <= band[1]:
                    target = index
                    break
            if target is not None:
                bands[target][4].append(level)
                continue
            half = width / 2.0
            opened.append(
                [level.price - half, level.price + half, level.price, width, [level]]
            )
        bands.extend(opened)
        position = end
    return tuple(
        sorted(
            (
                Zone(
                    members=tuple(members),
                    low=low,
                    high=high,
                    anchor_index=members[0].established_index,
                    established_index=max(m.established_index for m in members),
                    width_used=width,
                )
                for low, high, _centre, width, members in bands
            ),
            key=lambda z: (z.low, z.high),
        )
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    scale: WidthScale
    geometry: str
    extra: dict = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        return f"{self.geometry}|{self.scale.policy_id}"

    def zones(
        self,
        levels: Sequence[ResearchLevel],
        *,
        atr: dict[int, float],
        last_index: int,
    ) -> tuple[Zone, ...]:
        widths = self.scale.widths(levels, atr=atr, last_index=last_index)
        return group(self.geometry, levels, widths)
