"""The twenty adversarial fixtures of preregistration §11.

    .venv/bin/python research/zone_interactions/fixtures.py

**These fixtures deliberately assert almost no interpretation.** R3 and R4 are
precisely what is being researched, so a fixture that asserted "this is an
acceptance" would be inventing the answer it is supposed to guard. What they
assert instead is:

  * the observable vocabulary (§5) behaves as written — `EXIT`, `TRAVERSE`,
    `RETURN`, inclusive edges, no epsilon;
  * the candidate evidence forms are genuinely **different rules** (fixture 3);
  * the invariants of §8 hold — reflection, scale, censoring, warm-up;
  * nothing is silently dropped, and *absent* is never *negative*.

Run before the empirical tables are trusted, and re-run whenever `events.py`
changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))

from zone_interactions.events import (  # noqa: E402
    ABSENT,
    INSIDE,
    J_LONG,
    OUTSIDE_ABOVE,
    OUTSIDE_BELOW,
    Band,
    placebos,
    state_of,
    walk,
)

BAND = Band(low=100.0, high=110.0, width=10.0, established=0, zone_id=0)

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    _results.append((name, bool(condition), detail))


def run(
    closes: list[float],
    *,
    band: Band = BAND,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    atr: list[float] | None = None,
    full: bool = True,
):
    """Walk a synthetic series. Wicks default to the body; ATR defaults to 1."""
    n = len(closes)
    if highs is None:
        highs = [c + 0.01 for c in closes]
    if lows is None:
        lows = [c - 0.01 for c in closes]
    if atr is None:
        atr = [1.0] * n
    return walk(
        band,
        closes=closes,
        highs=highs,
        lows=lows,
        atr=atr,
        j_max=J_LONG,
        full=full,
    )


# --- 1 ----------------------------------------------------------------------
# A wick beyond the band with the close inside is not an interaction by close
# state. This is the fixture that keeps `EXIT` from drifting into WICK_BREACH.
cols, _ = run([105.0, 105.0, 105.0], highs=[105.1, 130.0, 105.1], lows=[104.9] * 3)
check("01 wick beyond, close inside -> no EXIT", len(cols["t0"]) == 0)

# --- 2 ----------------------------------------------------------------------
cols, _ = run([105.0, 111.0, 105.0, 105.0])
check("02 one close barely beyond, immediate return", len(cols["t0"]) == 1)
check("02 side is above", cols["side"][0] == OUTSIDE_ABOVE)
check("02 return at j=1", cols["j_close"][0] == 1)
check("02 not beyond at +1", cols["beyond_at_1"][0] == 0)

# --- 3 ----------------------------------------------------------------------
# The decisive fixture for R3-C: near and far transitions are the SAME event
# under E1-COUNT and DIFFERENT events under E2-DISP. If this ever stops being
# true, the two candidate evidence forms have collapsed into one rule and the
# comparison in §3.2 is vacuous.
near, _ = run([105.0, 111.0, 105.0, 105.0])
far, _ = run([105.0, 160.0, 105.0, 105.0])
check(
    "03 near and far agree under E1-COUNT",
    near["beyond_at_1"][0] == far["beyond_at_1"][0] == 0,
)
check(
    "03 near and far differ under E2-DISP",
    abs(near["disp_atr"][0] - far["disp_atr"][0]) > 1.0,
    f"near={near['disp_atr'][0]} far={far['disp_atr'][0]}",
)

# --- 4 ----------------------------------------------------------------------
cols, _ = run([105.0, 111.0, 112.0, 105.0, 105.0])
check("04 two closes beyond then return", len(cols["t0"]) == 1)
check("04 beyond at +1", cols["beyond_at_1"][0] == 1)
check("04 return at j=2", cols["j_close"][0] == 2)

# --- 5 ----------------------------------------------------------------------
# Alternating closes make three separate episodes, not one carried state.
cols, _ = run([105.0, 111.0, 105.0, 111.0, 105.0, 111.0, 105.0])
check("05 alternating -> three EXITs", len(cols["t0"]) == 3, str(cols["t0"]))
check("05 each returns at j=1", cols["j_close"] == [1, 1, 1])

# --- 6 ----------------------------------------------------------------------
# A bar wholly beyond the band: it never traded at the boundary.
cols, _ = run(
    [105.0, 130.0, 105.0],
    highs=[105.1, 135.0, 105.1],
    lows=[104.9, 125.0, 104.9],
)
check("06 gap wholly beyond -> gapped", cols["gapped"][0] is True)
cols, _ = run([105.0, 111.0, 105.0], highs=[105.1, 111.1, 105.1], lows=[104.9, 105.0, 104.9])
check("06 traded at the boundary -> not gapped", cols["gapped"][0] is False)

# --- 7 ----------------------------------------------------------------------
# Beyond one band while inside an overlapping one. Both are real states and
# neither is suppressed; the model must be able to say both.
other = Band(low=108.0, high=118.0, width=10.0, established=0, zone_id=1)
a_cols, _ = run([105.0, 111.0, 105.0])
b_cols, _ = run([105.0, 111.0, 105.0], band=other)
check("07 EXIT above the lower band at bar 1", a_cols["t0"] == [1])
check("07 close is inside the overlapping band", state_of(111.0, 108.0, 118.0) == INSIDE)
check("07 so the overlapping band has no EXIT at bar 1", 1 not in b_cols["t0"])
# The overlapping band has its own, different episode from the same bars —
# which is the point: interactions are zone-local and the two bands disagree
# about what bar 1 was. Neither reading is suppressed.
check("07 the overlapping band still has its own events", len(b_cols["t0"]) >= 1)

# --- 8 ----------------------------------------------------------------------
# One bar interacting with several bands produces one event per band, and the
# events are zone-local: no merging, no single "the" interaction.
bands = [
    Band(low=100.0, high=110.0, width=10.0, established=0, zone_id=0),
    Band(low=101.0, high=111.0, width=10.0, established=0, zone_id=1),
    Band(low=102.0, high=112.0, width=10.0, established=0, zone_id=2),
]
per_band = [len(run([105.0, 113.0, 105.0], band=b)[0]["t0"]) for b in bands]
check("08 one bar, one event per band", per_band == [1, 1, 1], str(per_band))

# --- 9 ----------------------------------------------------------------------
# Excursion away, then the range touches the band without closing inside.
cols, _ = run(
    [105.0, 120.0, 125.0, 120.0],
    highs=[105.1, 120.1, 125.1, 120.1],
    lows=[104.9, 119.9, 124.9, 109.5],
)
check("09 touch fires at j=2", cols["j_touch"][0] == 2, str(cols["j_touch"]))
check("09 close-inside does not", cols["j_close"][0] == ABSENT)

# --- 10 ---------------------------------------------------------------------
cols, _ = run([105.0, 120.0, 125.0, 105.0, 105.0])
check("10 excursion then full return at j=2", cols["j_close"][0] == 2)
check("10 touch at or before the return", 0 < cols["j_touch"][0] <= cols["j_close"][0])

# --- 11 ---------------------------------------------------------------------
# Away, then straight through to the far side without closing inside. The
# return does not fire on a close, and the pass-through is a TRAVERSE.
cols, traverses = run(
    [105.0, 120.0, 125.0, 90.0, 85.0],
    highs=[105.1, 120.1, 125.1, 126.0, 85.1],
    lows=[104.9, 119.9, 124.9, 89.0, 84.9],
)
check("11 pass-through is a TRAVERSE", traverses == 1, f"traverses={traverses}")
check("11 one EXIT only", len(cols["t0"]) == 1)
check("11 no close-inside return", cols["j_close"][0] == ABSENT)
check("11 but the band was touched", cols["j_touch"][0] == 2, str(cols["j_touch"]))

# --- 12 ---------------------------------------------------------------------
# A return after a very long interval is recorded with its true elapsed value.
# No window is applied at classification time — that is R4's question, not a
# setting in the harness.
long_series = [105.0, 120.0] + [125.0] * 300 + [105.0]
cols, _ = run(long_series)
check("12 long-interval return recorded truthfully", cols["j_close"][0] == 301,
      str(cols["j_close"]))

# --- 13 ---------------------------------------------------------------------
# Another band's transition between this band's exit and return does not break
# this band's episode. Attribution is measured, never assumed away.
seq = [105.0, 120.0, 125.0, 120.0, 105.0]
mine, _ = run(seq)
neighbour, _ = run(seq, band=Band(low=118.0, high=122.0, width=4.0, established=0, zone_id=9))
check("13 my episode is intact", mine["j_close"][0] == 3)
check("13 the neighbour had its own events", len(neighbour["t0"]) >= 1)

# --- 14 ---------------------------------------------------------------------
# Same-bar exit and return is impossible by construction: one bar has one
# close, and the state is a function of that close alone. The fixture asserts
# the construction rather than a market claim.
check("14 one bar has one state", state_of(111.0, 100.0, 110.0) == OUTSIDE_ABOVE)
cols, _ = run([105.0, 111.0, 105.0])
check("14 no zero-length episode", all(j != 0 for j in cols["j_close"]))

# --- 15 ---------------------------------------------------------------------
# Reflection. Upward and downward must receive identical semantics; a rule that
# behaves differently under mirroring is disqualified (§8.4).
MIRROR = 210.0
up_closes = [105.0, 111.0, 112.0, 105.0, 120.0, 105.0]
dn_closes = [MIRROR - c for c in up_closes]
dn_band = Band(
    low=MIRROR - BAND.high, high=MIRROR - BAND.low, width=BAND.width, established=0, zone_id=0
)
u, _ = run(up_closes)
d, _ = run(
    dn_closes,
    band=dn_band,
    highs=[MIRROR - (c - 0.01) for c in up_closes],
    lows=[MIRROR - (c + 0.01) for c in up_closes],
)
check("15 same number of EXITs under reflection", len(u["t0"]) == len(d["t0"]))
check("15 same transition bars", u["t0"] == d["t0"])
check("15 sides are exactly mirrored", all(a == -b for a, b in zip(u["side"], d["side"])))
check("15 same return elapsed", u["j_close"] == d["j_close"])
check(
    "15 same displacement",
    all(abs(a - b) < 1e-9 for a, b in zip(u["disp_atr"], d["disp_atr"])),
)
check("15 same snapshot outcome", u["m1_C1_5"] == d["m1_C1_5"])

# --- 16 ---------------------------------------------------------------------
# Scale. A decimal-shifted copy of the whole world must classify identically.
for scale in (2.0, 1024.0, 0.125):
    s_band = Band(
        low=BAND.low * scale,
        high=BAND.high * scale,
        width=BAND.width * scale,
        established=0,
        zone_id=0,
    )
    s, _ = run(
        [c * scale for c in up_closes],
        band=s_band,
        highs=[(c + 0.01) * scale for c in up_closes],
        lows=[(c - 0.01) * scale for c in up_closes],
        atr=[1.0 * scale] * len(up_closes),
    )
    check(f"16 scale ×{scale:g} same transition bars", u["t0"] == s["t0"])
    check(f"16 scale ×{scale:g} same returns", u["j_close"] == s["j_close"])
    check(
        f"16 scale ×{scale:g} same displacement",
        all(abs(a - b) < 1e-6 for a, b in zip(u["disp_atr"], s["disp_atr"])),
    )

# --- 17 ---------------------------------------------------------------------
# Missing ATR is an explicit unavailable, never a default width and never a
# substituted scale.
cols, _ = run([105.0, 111.0, 105.0], atr=[None, None, None])
check("17 missing ATR -> displacement is None", cols["disp_atr"][0] is None)
check("17 missing ATR -> excursion is None", cols["excursion_atr"][0] is None)
check("17 the event itself is still recorded", len(cols["t0"]) == 1)

# --- 18 ---------------------------------------------------------------------
# No future bars after classification: the event exists, the outcome is
# censored, and ABSENT is never counted as "did not persist".
cols, _ = run([105.0, 111.0])
check("18 event on the final bar is emitted", len(cols["t0"]) == 1)
check("18 outcome is ABSENT, not 0", cols["m1_C1_5"][0] == ABSENT)
check("18 return is censored", cols["j_close"][0] == ABSENT)
check("18 censoring horizon recorded", cols["censored_at"][0] == 0)

# --- 19 ---------------------------------------------------------------------
# An event near the window edge keeps a truthful censoring horizon, so the
# hazard estimator can remove it from the risk set at the right elapsed bar.
cols, _ = run([105.0, 111.0, 112.0, 112.0, 112.0])
check("19 censored_at counts observable bars after t0", cols["censored_at"][0] == 3)
check("19 short horizon resolves", cols["m1_C1_5"][0] == ABSENT)

# --- 20 ---------------------------------------------------------------------
# Repeated exits and returns are separate episodes and are never double counted.
cols, _ = run([105.0, 111.0, 105.0, 112.0, 105.0, 95.0, 105.0])
check("20 three episodes", len(cols["t0"]) == 3, str(cols["t0"]))
check("20 sides recorded independently", cols["side"] == [1, 1, -1], str(cols["side"]))
check("20 each resolves once", cols["j_close"] == [1, 1, 1])

# --- extra: the placebo construction is a pure displacement ------------------
ps = placebos(BAND)
check("P1 four placebos", len(ps) == 4)
check("P1 same width", all(p.width == BAND.width for p in ps))
check("P1 same establishment bar", all(p.established == BAND.established for p in ps))
check(
    "P1 displaced by whole band widths",
    sorted(round((p.low - BAND.low) / BAND.width) for p in ps) == [-4, -2, 2, 4],
)

# --- extra: edges are inclusive and comparison is exact ----------------------
check("E1 close exactly on the high is INSIDE", state_of(110.0, 100.0, 110.0) == INSIDE)
check("E1 close exactly on the low is INSIDE", state_of(100.0, 100.0, 110.0) == INSIDE)
check("E1 one ulp above is OUTSIDE", state_of(110.0 + 1e-13, 100.0, 110.0) == OUTSIDE_ABOVE)
check("E1 one ulp below is OUTSIDE", state_of(100.0 - 1e-13, 100.0, 110.0) == OUTSIDE_BELOW)
edge, _ = run([105.0, 110.0, 105.0])
check("E1 a close on the boundary is not an EXIT", len(edge["t0"]) == 0)


def main() -> int:
    failed = [r for r in _results if not r[1]]
    for name, ok, detail in _results:
        if not ok:
            print(f"FAIL  {name}  {detail}")
    print(f"\n{len(_results) - len(failed)}/{len(_results)} fixture assertions passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
