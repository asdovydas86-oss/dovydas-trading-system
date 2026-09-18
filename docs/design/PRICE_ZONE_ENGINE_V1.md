# Price Zone Engine V1 — design

**Reserved by** [report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §44.

| Field | Value |
|---|---|
| **Status** | **IMPLEMENTED** — `src/fmis/price_zones/` exists and satisfies §§4, 5, 8 and 9. §4.4 (`ZoneInteraction`, `ZoneReading`) and §7's *derivation* remain **not built**, by design |
| **Implemented by** | TA Slice 5B — [report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md), 2026-09-18 |
| **`k`** | **Declared `0.50`** by the owner on 2026-09-18 (ADR-0033 acceptance record, decision B), one value shared by 1W / 1D / 4H (decision C) |
| **Evidence** | [report 0050](../../reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md) |
| **Preregistration** | [`ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md`](ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md), sealed at `c05e870` |
| **Binds** | ADR-0033 (**Accepted** 2026-09-18) |
| **Supersedes** | report 0047 §15.2's sketch, in the three places §2 below records |

> **One place the implementation is stricter than this document, and why.** §6 says V1 must declare
> `k` inside `[0.10, 1.00]`. `ZoneWidthPolicy` **enforces** that region rather than documenting it:
> a multiple outside it raises. The region is the one thing about `k` that was measured, and a bound
> written down but not enforced is a bound a later caller steps over without noticing. §7.2's role
> vocabulary is deliberately **not** declared in code — a vocabulary present in the source is a
> vocabulary something will populate — so it lives in ADR-0033 §8 and here until the interaction
> engine exists.

---

## 1. What this document is, and is not

It specifies the types, the rules and the contracts a `fmis.price_zones` engine must satisfy, so
that TA Slice 5B implements a **decided** design rather than deciding one while coding.

**It is not an implementation and does not authorise one.** It contains no Python. It was written
before the package existed and is kept as the specification the package is checked against, not as a
description of it; where the two differ the header names the difference.

**Every rule below that differs from report 0047 §15.2 differs because a measurement refuted 0047's
version.** Those are marked ⚠ and each one names the measurement.

---

## 2. The three places this design contradicts report 0047 §15.2

Report 0047 is unmodified historical evidence; this section is how a reader learns it was superseded.

| # | 0047 §15.2 said | Measurement | This design says |
|---|---|---|---|
| ⚠ 1 | zones are formed by "clustering" levels — the grouping rule is unspecified | The three natural readings of "cluster" behave completely differently. Single-linkage chained six levels spanning `3w` into one zone on the synthetic fixture and **247 of 339 levels into one zone** on BTC 1D; a diameter-bounded greedy is **not reflection-symmetric** and rewrote history on 120,441 prefix events | Grouping is **anchored and online**, §5.2. It is the axis that decides everything, and it must be named in the ADR |
| ⚠ 2 | `established_index` = the bar the **last** member became knowable | A zone whose identity depends on its last member has no identity until it stops growing | A zone is identified by its **anchor** — the first member. `established_index` is the anchor's. The last member's bar is `latest_member_index`, a separate field, §4.2 |
| ⚠ 3 | boundaries are `low`/`high` of the member prices | Member-hull boundaries **move every time a member joins**, which is a retroactive rewrite of a fact that was already published. Measured: 34,192 illegal prefix events for the growing variant, against **0** for frozen bands | The band is **frozen at the anchor**, §5.3. Members never move it |

---

## 3. What a Price Zone is

> A **`PriceZone`** is a bounded price band, written once at the moment one confirmed structural
> level had no existing band to join, and thereafter collecting the confirmed structural levels that
> fall inside it.

Three consequences the implementation must not soften:

1. **A zone is not a cluster.** Clustering is a function of a whole set; a zone is a record written
   at an instant. This is why a zone can be published before the market is finished.
2. **A zone is not a level.** `PriceLevel` equality remains exact, everywhere, unchanged. Two levels
   in one zone are still two different levels — `PriceLevel(A) != PriceLevel(B)` while
   `Zone.members = {A, B}`.
3. **A zone has no role.** Role lives on a reading, §7.

---

## 4. Types

### 4.1 `ZoneMember`

One `PriceLevel`, held **by reference**, with its own `LevelOrigin` unchanged. The zone adds nothing
to it and reinterprets nothing.

| Field | Meaning |
|---|---|
| `level` | the `PriceLevel`, by reference |
| `joined_index` | `origin.index + origin.confirmation_bars` — the bar this level became knowable |

`joined_index` is **derived, never passed in**. A `confirmation_bars` parameter here would be the
ADR-0020 D1 hazard relocated one layer up and dressed as provenance — the approach
[ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md) records as explicitly rejected, and the
same reason `structural_levels` refuses one.

### 4.2 `PriceZone`

| Field | Meaning | Determined by |
|---|---|---|
| `low`, `high` | the band. **Immutable after construction** | the anchor's price and the width policy |
| `anchor` | the `ZoneMember` that opened the band | first level with no band to join |
| `members` | every member including the anchor, in join order | membership rule §5.4 |
| `established_index` | the bar the zone became knowable = `anchor.joined_index` | ⚠ **not** the last member's bar |
| `latest_member_index` | the most recent member's `joined_index` | grows; never affects identity |
| `width_policy` | the `ZoneWidthPolicy` record that produced the band | stamped, not referenced by name |
| `identity` | the `SeriesIdentity` of the series it was computed on | [ADR-0018](../adr/ADR-0018-series-identity-and-context-contract.md) |

**No `role` field. No `strength`. No score, rank or quality.** A zone with twelve members and a zone
with one are two facts, not a strong one and a weak one.

### 4.3 `ZoneWidthPolicy`

A named, versioned value object — the shape [`RegimePolicy`](MARKET_REGIME_ENGINE_V1.md) already
uses — **stamped onto every zone it produces**, so a zone recorded a year ago is reproducible from
its own record even after the default changes.

| Field | Value in V1 |
|---|---|
| `policy_id` | a stable string, e.g. `atr14-anchor-0_50` |
| `scale` | `ATR_MULTIPLE` |
| `feature_name` | `atr_14` — the production feature, by name, never a reimplementation |
| `multiple` | `k`, §6 |
| `temporal_reference` | `AT_ANCHOR_ESTABLISHMENT` |

### 4.4 Not in V1

`ZoneInteraction` and `ZoneReading` are **specified only as far as §7 requires and are not part of
V1's deliverable.** Report 0047 §15.2 sketches an interaction table containing `ACCEPTANCE`,
`RECLAIM` and `RETURN_INSIDE`; each needs a parameter (*how many closes?*, *within how many bars?*)
that research questions **R3** and **R4** exist to answer and that this gate did not study.
Shipping them now would invent exactly the thresholds this whole exercise refused to invent.

---

## 5. The rules

### 5.1 Source levels

Every member is a `PriceLevel` from `structural_levels`, and nothing else. No zone is formed from a
price the structural chain did not produce.

**Inherited limitation, carried and stated on the zone set rather than silently repaired:**
[ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) **D2** — the first swing high and first
swing low produce no level, so the earliest zone on each side is missing. 0047 §15.5 recommends
inheriting it rather than widening `LevelOrigin.label` speculatively, and this design does.

### 5.2 Construction — anchored, online, in establishment order ⚠

Levels are processed in order of `joined_index`, i.e. **the order the market made them knowable**,
not the order of their prices.

For each level:

1. if it lies inside the band of an existing zone → it **joins** that zone;
2. otherwise it **opens** a new zone, anchored at its own price.

Nothing else happens. Zones are never merged, never split, never deleted, never resized.

**Why this and not clustering.** A clustering algorithm answers *given all these levels, how do they
group* — a question that has a different answer every time a level is added, which means every
published zone is provisional. An anchored rule answers *given the zones that already exist, where
does this new level belong* — and the answer never changes what was already written. Prefix
stability is then a property of the construction rather than a claim to be checked afterwards, and
the measurement agrees: **0 illegal prefix events across 1,836 policy-series cells**, against
34,192 for the same rule with growable bands and 120,441 for a diameter-bounded clustering.

### 5.3 The band

```
low  = anchor.price − w/2
high = anchor.price + w/2
w    = k × ATR(14) at the anchor's own establishment bar
```

**Frozen at construction.** Not recomputed, not widened by a joining member, not adjusted when
volatility changes.

**Why establishment-time and not current ATR.** Measured, not assumed: recomputing width from the
latest ATR produced **983,916 illegal prefix events** — every historical zone in the sample moved
its own boundaries every time a new bar arrived. A zone whose edges depend on today's volatility is
not a record of where an area was; it is a redrawing of the past.

**Why a joining member may not widen it.** Also measured: 34,192 illegal events. Letting a member
widen the band means a level that was outside the zone yesterday is inside it today, with no new
information about the level — §13 of the gate brief asks this question directly and the answer is
that it causes retroactive reinterpretation.

**Undefined before warm-up.** If `atr_14` has no value at the anchor's establishment bar, **no zone
is formed** and the level is carried as unassigned. It is never given a default width. A default
here would be the invented threshold the whole design exists to avoid, placed at the one point where
nobody would look for it.

### 5.4 Membership

A level joins a zone iff `zone.low <= level.price <= zone.high`. **Inclusive at both edges.**

| Question | V1 answer | Why |
|---|---|---|
| May an `UPPER` and a `LOWER` level share a zone? | **Yes** | An area is an area. The side is a fact about the swing that made the level and travels on the level; making it a membership condition would assert that a former high and a former low at one price are two different areas, which is a claim no measurement supports. Fixture 8 records this as a **stated** decision rather than an emergent one |
| May a level belong to two zones? | **No** | Membership is unique. First matching band wins, §5.5 |
| May two zones overlap? | **Yes** | And they frequently do — at `k = 0.50`, **70 %** of adjacent zone pairs have intersecting bands. A price may therefore be inside several zones at once. This is a genuine property of the representation and must be visible in the API, not smoothed away |
| Do equal prices merge? | **Yes**, naturally | They are inside each other's band at any `k ≥ 0`. At `k = 0` a zone is a single point and only exactly-equal prices group — which reproduces 0047 §15.3's "option A" as the degenerate case rather than as a separate policy |

### 5.5 Ties — the first band, never the nearest ⚠

When a level lies inside **more than one** band, it joins the one **created earliest**.

**Not the nearest centre**, which is what the preregistration specified and what measurement
rejected. Choosing the nearest centre compares two distances, so the outcome turns on the
*difference* of two nearly equal floating-point numbers; rescaling the whole price series by `10³`
perturbs both by an ulp and flipped the assignment on **35 %** of series. Comparing a price against
a boundary instead is stable under any perturbation smaller than the distance to that boundary, and
it says something defensible: the area that was already there keeps the level.

### 5.6 One bar is one instant ⚠

Every level whose `joined_index` is bar *i* is tested against **the bands that existed before bar
*i***. The new bands they open are opened together, and a band opened at bar *i* cannot claim
another level from bar *i*.

**Why this rule is needed at all.** One candle can be both a swing high and a swing low, so two
levels can share an establishment bar *and* an origin bar. Any order between them must then come
from their side or their price, and both invert under reflection — which is exactly why mirroring
the price series moved the zone map on 2 % of series. Under this rule nothing inside a bar is
ordered, so nothing inside a bar can be ordered wrongly.

### 5.7 Closed bars only

Only closed candles participate, in the index space `SwingPoint.index`, `LevelOrigin.index`,
`LevelCrossingEvent.index` and `FeatureSeriesPoint.index` already share. One bar, one number.

---

## 6. The parameter `k`

**`k` is a resolution control, not a discovered constant.** The gate's central negative finding:
every descriptive metric is **monotone** in `k` over the admissible region, so no interior optimum
exists and no plateau can select a value. A study that excludes outcome data — as this one
deliberately does — cannot produce one, and a value produced any other way would be the invented
threshold in disguise.

What the evidence *does* fix is the **admissible region**:

| Bound | Value | Evidence |
|---|---|---|
| **Upper** | `k ≤ 1.00` | Above it, bands opened at one bar by sibling levels overlap each other and long/short symmetry is lost. First failures at `k = 1.25` |
| **Lower** | `k ≥ 0.10` | Below it the representation degenerates toward one-level-one-zone: `k = 0` leaves **96 %** singletons |
| **Degenerate above** | `k ≥ 2.00` | **99.4 %** of levels merged, largest zone 44 members — distinct areas destroyed |

**V1 must therefore declare `k`, not derive it**, inside `[0.10, 1.00]`, as a versioned
`ZoneWidthPolicy` default stamped on every zone. The ADR records the declaration and the revisit
trigger; it must not claim the number was measured.

---

## 7. Role — D2

### 7.1 The rule

> **A zone's role is a function of its interaction history. It is never a function of where price
> stands relative to it.**

This is [the 0047 disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §E, and the gate
measured what the forbidden derivation would cost:

| Measurement | 1W | 1D |
|---|---|---|
| Zones above the close that price has **never interacted with** — which the position rule would print as *resistance* on no observation at all | **22 %** (max 75 % on one symbol) | **7 %** |
| Zones below the close, same question, printed as *support* | **25 %** | **22 %** |
| Zones price has closed **on both sides of** since they were established — the position rule called the same zone support on some days and resistance on others, with no behaviour observed in between | **39 %** | **50 %** |

The second row is the decisive one. The position rule is not merely *sometimes wrong*; on half of
all zones it is **not well-defined over time**, because its answer changes when price moves and
nothing else does.

### 7.2 Vocabulary

`position` and `role` are two fields and must never be one.

| Field | Values | Status |
|---|---|---|
| `position` | `PRICE_ABOVE` · `PRICE_BELOW` · `PRICE_INSIDE` | **geometry only.** Not a role, and named so that it cannot be mistaken for one |
| `role` | `UNTESTED` · `HELD_FROM_ABOVE` · `HELD_FROM_BELOW` · `BROKEN_UPWARD` · `BROKEN_DOWNWARD` · `ROLE_FLIPPED` · `INDETERMINATE` | **Vocabulary approved; derivation deferred** to the interaction engine |

`UNTESTED` is the honest state for a zone price has never met, and it is **not** `INDETERMINATE` —
which means interactions exist but do not resolve. A zone above price with no interaction history is
`UNTESTED`, not resistance. That single distinction is what §7.1's first row measures.

### 7.3 What may be rendered

The operator surface **may** print "Support zone" / "Resistance zone" — but only as a *label over a
derived role*, only once the interaction engine exists, and only where the role is `HELD_FROM_ABOVE`
/ `HELD_FROM_BELOW` respectively. Three existing guards forbid those words in output today, and they
stay in force until the ADR and the engine both exist. **A zone whose role is `UNTESTED` is never
rendered with either word.**

### 7.4 What is premature

`ACCEPTANCE`, `RECLAIM`, `RETURN_INSIDE`, retest and false-breakout all need a parameter this gate
did not measure (**R3**, **R4**). **A `CLOSE_BREACH` is not a breakout** and must not be renamed one.
The crossing engine's three kinds are facts; breakout is a reading of them.

---

## 8. Contracts the implementation must satisfy

| Contract | Statement |
|---|---|
| **Determinism** | Same series, same policy → identical zones, across processes and hash seeds |
| **Prefix stability** | A zone knowable at bar *t* has the same identity, anchor and band when recomputed over any longer prefix. It may gain members; it may not change its boundaries, split, merge or vanish |
| **No lookahead** | A zone's width reads ATR **at or before** its anchor's establishment bar, never after |
| **Unit invariance** | Multiplying the series by a constant leaves the grouping unchanged (exactly, for a dyadic constant) |
| **Long/short symmetry** | Reflecting the series mirrors the zone map exactly, for `k ≤ 1.00` |
| **Provenance** | Every zone reaches back to exact `PriceLevel`s, to `LevelOrigin`s, to confirmed swings, with the confirmation window carried per member |
| **Identity** | One `SeriesIdentity` per zone set, by reference (ADR-0018) |
| **Insufficient history** | No ATR at the anchor bar → no zone. Never a default width |
| **No intrabar path** | A bar that touches and then breaks a zone has no provable order. Nothing may claim a sequence within one bar |

---

## 9. What the engine must never do

- Call a zone `support` or `resistance` in any value, field name or rendered string, until the
  interaction engine exists and an ADR permits the label.
- Assign a role from position.
- Emit a strength, score, rank, confidence or quality.
- Emit a direction.
- Delete or rewrite a zone.
- Reimplement ATR, swing detection, level projection or crossing classification. It **calls** them.
- Reach evidence voting, strategy policy, the 1W gate, Scan Memory or risk. **Zone evidence
  independence is `NOT ESTABLISHED`** and stays so until **R15** measures it.

---

## 10. Known limitations, carried forward

1. **`k` is declared, not measured** (§6). The largest open question, and it is open by construction.
2. **Zones overlap heavily** — 70 % of adjacent pairs at `k = 0.50`. A price inside three zones is
   normal, and every consumer must handle it.
3. **Symmetry fails above `k = 1.00`** (§5.6's residual). Bounded, measured, and the reason the
   admissible region has a ceiling.
4. **The band is window-sensitive at the margin.** Loading a symbol from a later start bar changes
   ATR's Wilder seed and so moves a band's edges slightly; measured pairwise agreement **0.995** at
   `k = 0.50`, falling to **0.984** at `k = 1.00`. Not zero, and not nothing.
5. **ADR-0019 D2** — the earliest zone on each side is missing (§5.1).
6. **1W zones are measured on few bars.** The window test is not evaluable at the context role at
   all; its prefix and symmetry results are.
7. **No interaction engine**, so no role is actually derived yet (§7.4).

## 11. Revisit triggers

- **R3/R4 answered** → interaction states may be specified.
- **R15 answered** → and only then may independence be discussed.
- **A tick-size model reaches ingestion** → `W-TICK` becomes expressible and must be re-evaluated;
  today `fmis.data.Candle` carries no instrument metadata and `CrossingKind`'s own docstring records
  that tolerance belongs at ingestion behind a tick-size model that does not exist.
- **A second scale family passes the full battery** → `W-STRUCT-CAUSAL` came close and failed on
  numerical fragility, not on principle. A better-conditioned structural scale reopens the choice.
- **`k` shown to matter to a product outcome** → the question stops being representation-only.
