"""The event walk: observable states against one frozen band, and nothing else.

Every definition here is §5 of the preregistration, transcribed. No rule in
this module reads a bar later than the index it stamps as the event's
knowledge time, and no rule names an interpretation.

The band is an input. This module never constructs, widens, merges or moves
one — real bands come from production `derive_price_zones`, and a placebo band
is a pure price displacement of a real one (§4.2).

**Pure Python, deliberately.** `pyproject.toml` declares `dependencies = []`
and the repository has kept that property through every milestone; report 0050
measured 55,728 policy cells without a numerical library. A research gate is
not a reason to put NumPy into an environment that has never needed one.

The cost is kept linear by a fact about the events themselves: an `EXIT`
requires the previous bar to be `INSIDE`, so **outside episodes are disjoint**
and resolving every return costs one traversal of the band's history in total,
not one per event.

Output is **columnar** — a dict of equal-length lists — because an object per
event over ~750,000 events is memory spent on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Per-bar state codes (§5.1). `INSIDE` is 0 so `!= 0` reads as "outside".
INSIDE = 0
OUTSIDE_ABOVE = 1
OUTSIDE_BELOW = -1

#: Elapsed-bar ceiling for return-hazard work (§4.3).
J_LONG = 40
J_SHORT = 20

#: Evaluation horizons (§3.4). 10 is primary; 5 and 20 are sensitivity.
HORIZONS = (5, 10, 20)

#: The three matched-knowledge-time designs (§3.3), as classification offsets
#: from the transition bar:
#:   C3 classifies at t0,   evaluates [t0+1, t0+H]
#:   C1 classifies at t0+1, evaluates [t0+2, t0+1+H]
#:   C2 classifies at t0+2, evaluates [t0+3, t0+2+H]
DESIGNS = (("C3", 0), ("C1", 1), ("C2", 2))

#: "There is no such bar." Never confused with a real 0/1 answer, and never
#: silently treated as a negative outcome (§11 fixture 18).
ABSENT = -1

R4_COLUMNS = (
    "t0",
    "side",
    "disp_atr",
    "gapped",
    "beyond_at_1",
    "beyond_at_2",
    "j_close",
    "j_touch",
    "censored_at",
    "excursion_atr",
)


def r3_columns() -> tuple[str, ...]:
    """The 27 outcome columns: three designs × three horizons × three metrics."""
    out: list[str] = []
    for tag, _ in DESIGNS:
        for h in HORIZONS:
            out += [f"m1_{tag}_{h}", f"m2_{tag}_{h}", f"m3_{tag}_{h}"]
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Band:
    """One frozen band and the bar from which it may be observed.

    ``established`` is the anchor's ``joined_index`` for a real zone, and the
    *same* index for every placebo displaced from it — a placebo that came into
    existence at a different bar would differ from its counterpart in two
    respects rather than one.
    """

    low: float
    high: float
    width: float
    established: int
    zone_id: int
    kind: str = "real"
    delta: float = 0.0


def state_of(close: float, low: float, high: float) -> int:
    """Per-bar state against one band, inclusive at both edges.

    Exactly the rule `CrossingKind` uses for a level: equality is not a breach,
    so a close exactly on a boundary is `INSIDE`. No epsilon, no rounding.
    """
    if close > high:
        return OUTSIDE_ABOVE
    if close < low:
        return OUTSIDE_BELOW
    return INSIDE


def walk(
    band: Band,
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    atr: list[float],
    j_max: int,
    full: bool = True,
) -> tuple[dict[str, list], int]:
    """Every `EXIT` against one band, columnar, plus the `TRAVERSE` count.

    Traverses are counted and **never merged into the exit columns** (§5.2): a
    bar moving from one side of a band to the other never established an
    outside state relative to an inside one, and folding the two together would
    answer R4-H by assumption.

    ``full=False`` computes only the R4 columns — placebo bands are a control
    for attribution and the preregistration makes no R3 comparison on them.

    Every index written is absolute (a closed-candle index in the same space
    `SwingPoint`, `LevelOrigin` and `LevelCrossingEvent` use); the scan works
    in indices relative to ``established`` and converts on the way out.
    """
    names = R4_COLUMNS + (r3_columns() if full else ())
    cols: dict[str, list] = {name: [] for name in names}

    n = len(closes)
    start = band.established
    if start >= n - 1:
        return cols, 0

    lo = band.low
    hi = band.high
    st = [1 if c > hi else (-1 if c < lo else 0) for c in closes[start:]]
    m = len(st)

    # --- pass 1: transitions -------------------------------------------------
    exits: list[int] = []
    traverses = 0
    prev = st[0]
    for i in range(1, m):
        s = st[i]
        if s != prev:
            if prev == INSIDE:
                exits.append(i)
            elif s != INSIDE:
                traverses += 1
            prev = s

    if not exits:
        return cols, traverses

    # --- pass 2: episodes ----------------------------------------------------
    # Disjoint by construction, so the total scan below is one traversal.
    for e in exits:
        side = st[e]
        boundary = hi if side == OUTSIDE_ABOVE else lo
        t0 = start + e
        a = atr[t0]
        scaled = a is not None and a > 0

        extreme = closes[t0]
        touch_rel = ABSENT
        return_rel = ABSENT
        i = e + 1
        while i < m:
            if st[i] == INSIDE:
                return_rel = i
                break
            t = start + i
            if i - e <= j_max:
                c = closes[t]
                if side == OUTSIDE_ABOVE:
                    if c > extreme:
                        extreme = c
                elif c < extreme:
                    extreme = c
            if touch_rel == ABSENT and highs[t] >= lo and lows[t] <= hi:
                touch_rel = i
            i += 1
        if return_rel != ABSENT and touch_rel == ABSENT:
            # A close back inside the band is necessarily a range intersection
            # with it, so the return bar is the touch bar when none came first.
            touch_rel = return_rel

        beyond = (closes[t0] - boundary) if side == OUTSIDE_ABOVE else (boundary - closes[t0])
        peak = (extreme - boundary) if side == OUTSIDE_ABOVE else (boundary - extreme)

        cols["t0"].append(t0)
        cols["side"].append(side)
        cols["disp_atr"].append(beyond / a if scaled else None)
        cols["excursion_atr"].append(peak / a if scaled else None)
        cols["gapped"].append(
            lows[t0] > boundary if side == OUTSIDE_ABOVE else highs[t0] < boundary
        )
        cols["j_close"].append(return_rel - e if return_rel != ABSENT else ABSENT)
        cols["j_touch"].append(touch_rel - e if touch_rel != ABSENT else ABSENT)
        cols["censored_at"].append(m - 1 - e)
        cols["beyond_at_1"].append(_beyond_at(st, e + 1, side, m))
        cols["beyond_at_2"].append(_beyond_at(st, e + 2, side, m))

        if not full:
            continue

        for tag, offset in DESIGNS:
            classify = e + offset
            for h in HORIZONS:
                last = classify + h
                if last >= m:
                    cols[f"m1_{tag}_{h}"].append(ABSENT)
                    cols[f"m2_{tag}_{h}"].append(ABSENT)
                    cols[f"m3_{tag}_{h}"].append(None)
                    continue
                cols[f"m1_{tag}_{h}"].append(1 if st[last] == side else 0)
                cols[f"m2_{tag}_{h}"].append(
                    1 if INSIDE in st[classify + 1 : last + 1] else 0
                )
                c = closes[start + last]
                far = (c - boundary) if side == OUTSIDE_ABOVE else (boundary - c)
                cols[f"m3_{tag}_{h}"].append(far / a if scaled else None)

    return cols, traverses


def _beyond_at(st: list[int], i: int, side: int, m: int) -> int:
    """Is the close at relative bar ``i`` still beyond, on the same side?"""
    if i >= m:
        return ABSENT
    return 1 if st[i] == side else 0


def placebos(band: Band) -> list[Band]:
    """The four displaced controls for one real band (§4.2).

    Same width, same establishment bar, same series. One difference: no
    confirmed structural level anchored them.
    """
    return [
        Band(
            low=band.low + d * band.width,
            high=band.high + d * band.width,
            width=band.width,
            established=band.established,
            zone_id=band.zone_id,
            kind="placebo",
            delta=float(d),
        )
        for d in (-4, -2, 2, 4)
    ]
