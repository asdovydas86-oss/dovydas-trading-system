# ADR-0033: Price zone semantics and the tolerance boundary

**Status:** **Accepted** — 2026-09-18, by Dovydas after review with ChatGPT
**Date:** 2026-09-18 · **Accepted:** 2026-09-18
**Milestone:** Price Zone Semantics & Parameter Research Gate (report 0050); **implemented by**
TA Slice 5B — Price Zone Foundation & Product Surface ([report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md))
**Closes:** report 0047 **D1** and **D2**
**Evidence:** [report 0050](../../reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md) ·
[preregistration](../design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md) (sealed `c05e870`) ·
[design](../design/PRICE_ZONE_ENGINE_V1.md)
**Binds:** `fmis.price_zones`

> **Acceptance record — what was accepted, and in knowledge of what.**
>
> This ADR was written as `Proposed` because it bound no code and because the one number it
> contains is **declared rather than measured** (§6). It said it should be accepted only if the
> owner accepted that declaration knowingly. **He did, on 2026-09-18**, and the declaration is
> recorded here rather than inferred from the fact that code now exists:
>
> | Decision | What the owner declared |
> |---|---|
> | **A** | ADR-0033 is **accepted** as written. Its research claims below are unmodified; this block is added, nothing is rewritten. |
> | **B** | **`k = 0.50`** — a **declared V1 product/representation parameter**. Explicitly *not* an empirically discovered optimum, *not* a calibrated trading threshold, *not* a prediction threshold, *not* an edge claim and *not* a confidence value. §6 bounded the admissible region and identified no value inside it, and code, documentation and rendered output must all preserve that distinction. |
> | **C** | **One shared `k` for every role** — 1W, 1D and 4H. **No per-timeframe hidden constant.** If evidence later shows one shared `k` produces materially bad product behaviour, that is a new explicit research and product decision, never a quiet second default. |
> | **D** | The product **may** eventually render *"Support zone"* / *"Resistance zone"* — but **only** as UI labels over a role derived from actual interaction history, and **never** for `UNTESTED`. Role is never derived from position. **This approval is not permission to build the interaction engine**: R3 and R4 remain unresolved, and the implementing milestone was explicitly forbidden to fabricate those labels merely because their future use is approved. |
>
> **What the accepting milestone shipped and did not.** TA Slice 5B implemented §§1–5, §9's
> prohibitions and §8's `position`/`role` separation — and shipped **no** `ZoneInteraction`, **no**
> `ZoneReading`, **no** derived role and **no** role vocabulary in code at all, because a
> vocabulary present in the source is a vocabulary something will populate. §8's approved
> vocabulary therefore still lives only in this document. The 81-fixture policy digest
> `8b22e6c9…` is byte-identical across the implementation.

## Context

FMITS has `PriceLevel`: an exact price, a side its swing type implies, and provenance. It has no
concept of an *area*. A trader reading a chart sees one important region where FMITS sees three
unrelated exact lines, and the gap is the single largest one between what FMITS computes and how the
owner reads a market.

Grouping levels requires a **distance test**, and this repository has refused tolerance everywhere,
on principle: [ADR-0013](ADR-0013-swing-relationship-foundation.md) §4 states it, the
`fmis.level_crossing` package restates it, and `classify_comparison` restates it again.
`CrossingKind`'s own docstring records **why**: *"tolerance belongs at ingestion behind a tick-size
model that does not exist."*

Report 0047 §43 named this decision **D1** and recommended a versioned `ZoneWidthPolicy` carrying an
ATR multiple. The [0047 review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §C made
historical series access a prerequisite; [ADR-0031](ADR-0031-feature-series-contract.md) delivered
it. Disposition §E fixed that a zone's role must come from interaction history, never from position
relative to price, and left the vocabulary open as **D2**.

**What this ADR adds that report 0047 did not have: measurement.** Report 0050 ran 55,728 policy
cells over 36 symbols and three timeframe roles, on a committed offline capture, with the question,
the candidate set and the refutation criteria sealed in Git beforehand.

**The finding that reframes D1.** D1 reads as one decision and is three. Report 0047 §15.3 argues at
length about the *unit* of the tolerance and says of the grouping rule only that levels are
"clustered". The measurement is that the unit barely matters and the grouping rule decides
everything:

| Grouping rule | Outcome |
|---|---|
| single-linkage — cut where the adjacent gap exceeds `w` | **chains.** 247 of 339 levels into one zone on BTC 1D; zones up to **94× wider than the policy's own tolerance** |
| diameter-bounded greedy over price-sorted levels | **not reflection-symmetric** (passes on 2 % of cells) and rewrote history on **120,441** prefix events |
| anchored and online, bands frozen at creation | **0** illegal prefix events, exact symmetry and exact unit-invariance across the admissible range |

## Decision

### 1. `PriceZone` is a distinct abstraction from `PriceLevel`, and existing exact semantics are unchanged

**No existing structural primitive gains a tolerance.** `PriceLevel` equality stays exact.
`classify_comparison` stays exact. `CrossingKind`'s exact-equality-is-a-`TOUCH` rule stays exact.
ADR-0013 §4 is **not weakened**, globally or locally.

The tolerance is scoped to **one thing**: deciding which confirmed levels a zone's band contains.
Therefore

```
PriceLevel(A) != PriceLevel(B)       remains true
Zone.members  == {A, B}              is also true
```

and that is not a contradiction. It is the whole point: a zone is a **higher-order grouping over
exact facts**, not a fuzzy version of them.

### 2. Construction is anchored and online, never clustering

Levels are processed in order of the bar they became knowable. Each either falls inside an existing
zone's band and joins it, or opens a new zone anchored at its own price. **Zones are never merged,
split, resized or deleted.**

This is chosen because prefix stability becomes a property of the construction rather than a claim
checked afterwards — and because every clustering formulation tested rewrote history.

### 3. The band is frozen at the anchor

```
low = anchor.price − w/2      high = anchor.price + w/2
w   = k × atr_14  read at the anchor's own establishment bar
```

**Immutable thereafter.** Two rejected alternatives, both rejected on measurement:

- **width from current ATR** — 983,916 illegal prefix events. Every historical zone moved its own
  boundaries on every new bar.
- **a joining member widens the band** — 34,192 illegal events. A level outside the zone yesterday
  is inside it today with no new information about that level.

If `atr_14` has no value at the anchor's bar, **no zone forms**. There is no default width.

### 4. Ties go to the oldest band; one bar is one instant

A level inside two bands joins the **earliest created**. A level inside none opens a band. Every
level established at bar *i* is tested against the bands that existed **before** *i*, and bands
opened at *i* cannot claim each other's levels.

Both rules exist because measurement refuted the alternatives. *Nearest centre* — which the
preregistration specified — compares two nearly equal floats and flipped on **35 %** of series under
a rescale. Ordering two levels established by the **same candle** (a candle can be both a swing high
and a swing low) must break the tie on side or price, both of which invert under reflection, which
moved the zone map on 2 % of series.

### 5. Membership is by price alone

An `UPPER` and a `LOWER` level may share a zone. Membership is unique; **bands may overlap**, and at
`k = 0.50` **70 %** of adjacent pairs do, so a price may sit inside several zones. This is a real
property of the representation and is exposed rather than hidden.

### 6. `k` is **declared**, not measured — and the honest statement of why

Every descriptive metric is **monotone** in `k`. There is no plateau, no interior optimum and no
knife-edge either: `k` is a **resolution control**, and a study that deliberately excludes outcome
data cannot derive a preferred value from representation alone.

What the evidence fixes is the **admissible region, `k ∈ [0.10, 1.00]`**:

| Bound | Evidence |
|---|---|
| `k > 1.00` | long/short symmetry is lost (first failures at `1.25`) |
| `k < 0.10` | degenerates toward one-level-one-zone (`k = 0` leaves 96 % singletons) |
| `k ≥ 2.00` | over-merges: 99.4 % of levels in multi-member zones, largest zone 44 members |

V1 therefore **declares** a default inside that region as a versioned `ZoneWidthPolicy`, stamped on
every zone so a historical zone is reproducible from its own record. **This ADR does not claim the
number was discovered.** Report 0047 §15.3 anticipated this exactly: the multiple is *"a stated
hypothesis requiring research"*. The research has now bounded it and refused to invent it.

**The declared value, recorded 2026-09-18: `k = 0.50`**, shipped as
`ZoneWidthPolicy(policy_id="atr14-anchor-0_50", …)` and stamped by value onto every zone. The
admissible region is **enforced** by that type rather than documented beside it — a multiple
outside `[0.10, 1.00]` raises — because the region is the one thing about `k` that *was* measured,
and a bound that is written down but not enforced is a bound a later caller steps over without
noticing.

### 7. `W-PCT`, `W-TICK` and `W-STRUCT` are rejected, each for a stated reason

| Candidate | Rejected because |
|---|---|
| **percentage of price** | **Not long/short symmetric** — passes 6 % of cells. A width proportional to price cannot mirror, because zero is an absolute floor and there is no corresponding ceiling. This is a stronger objection than 0047 §15.3's *"invented threshold"*, and it is measured |
| **absolute / tick distance** | **Not expressible.** `fmis.data.Candle` carries no instrument metadata; no tick size exists anywhere under `src/`. Rejected on evidence, and revisitable the day an ingestion tick model exists |
| **structural spacing (median adjacent gap)** | The naive form reads the **whole** level set, a quantity that did not exist when the zone was established: 696,588 illegal prefix events. A causal form — the median gap over levels already knowable — was implemented, given the **same** symmetry repairs the winning geometry received, and still fails unit-invariance: a median of price *differences* involves enough arithmetic to be numerically fragile where a single ATR multiplication is not. A better-conditioned structural scale reopens this |

### 8. D2 — role comes from interaction history, and the vocabulary is fixed

`position` (`PRICE_ABOVE` / `PRICE_BELOW` / `PRICE_INSIDE`) is **geometry** and is a separate field
from `role`. The approved internal role vocabulary is:

```
UNTESTED · HELD_FROM_ABOVE · HELD_FROM_BELOW · BROKEN_UPWARD · BROKEN_DOWNWARD
ROLE_FLIPPED · INDETERMINATE
```

`UNTESTED` is not `INDETERMINATE`: the first means price never met the zone, the second that
interactions exist and do not resolve.

**The measured case against the forbidden derivation**, which disposition §E asserted and this
milestone quantified:

- **22 %** of zones above the close on 1W have **no interaction history at all** — the position rule
  would print *resistance* on zero observations (up to 75 % on one symbol).
- **39 % (1W) / 50 % (1D)** of zones have had price close on **both** sides since they were
  established. On those, the position rule called one zone *support* on some days and *resistance*
  on others, with nothing about the zone's behaviour changing in between.

The second number is the decisive one: the position rule is not merely sometimes wrong, it is **not
well-defined over time**.

**Rendering.** The operator surface may later print "Support zone" / "Resistance zone" as a *label
over a derived role* — `HELD_FROM_ABOVE` and `HELD_FROM_BELOW` respectively — and never for an
`UNTESTED` zone. The three existing guards forbidding those words stay in force until the
interaction engine exists.

### 9. What a zone engine may not do

No role from position. No strength, score, rank, confidence or quality. No direction. No deletion or
rewriting of a zone. No reimplementation of ATR, swing detection, level projection or crossing
classification — it calls them.

**No effect on strategy.** No zone reaches evidence voting, the swing policy, the 1W regime gate,
`fmis.scan_memory` or risk. The 81-fixture policy baseline and its digest are unchanged by this
decision and must be unchanged by the milestone that implements it.

### 10. Evidence independence is NOT established

Zones derive from the same confirmed pivots as structural trend and therefore share upstream
information with it. Per disposition §D the permitted description is *"a new / potentially more
orthogonal evidence family"*, status **`INDEPENDENCE NOT ESTABLISHED`**, until research question
**R15** measures it the way Milestone AW measured the existing 75–79 % family agreement.

## Consequences

- TA Slice 5B was **unblocked on D1 and D2** and blocked only on the owner accepting §6's
  declaration. He accepted it on 2026-09-18 and the slice shipped `fmis.price_zones` plus a
  `/swing/SYMBOL` product surface ([report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md)).
- A zone is publishable the moment it is created, because nothing later can rewrite it.
- Consumers must handle overlapping zones; a price inside three zones is normal.
- `ZoneInteraction` and `ZoneReading` are **not** in V1: each needs a parameter (**R3**, **R4**) this
  gate did not study. **A `CLOSE_BREACH` is not a breakout.**
- The earliest zone on each side is missing, inherited from
  [ADR-0019](ADR-0019-level-crossing-foundation-v1.md) D2 and stated on the zone set.

## Limitations

1. `k` is declared, not measured (§6).
2. Symmetry fails above `k = 1.00`; the residual mechanism is named and bounded.
3. Bands overlap heavily.
4. The band is window-sensitive at the margin — ATR's Wilder seed moves with the load start;
   measured pairwise agreement **0.995** at `k = 0.50`, **0.984** at `k = 1.00`.
5. The sample is 36 pre-2023 Binance USDT pairs; `SOLUSDT` and most later listings are absent, and
   1W/1D bars are deterministic aggregations of captured 4H bars.
6. No zone's role is derived yet, because no interaction engine exists.

## Revisit triggers

- **R3 / R4 answered** → interaction states may be specified.
- **R15 answered** → and only then may independence be discussed.
- **A tick-size model reaches ingestion** → `W-TICK` becomes expressible.
- **A better-conditioned structural scale** → the width family is reopened.
- **`k` shown to affect a product outcome** → the question stops being representation-only, and §6's
  declaration must be re-taken as a measurement.
