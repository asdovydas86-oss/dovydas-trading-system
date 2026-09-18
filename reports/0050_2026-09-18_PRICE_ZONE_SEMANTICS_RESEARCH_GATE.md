# Report 0050 — FMITS Price Zone Semantics & Parameter Research Gate

| Field | Value |
|---|---|
| **Report number** | 0050 |
| **Title** | FMITS Price Zone Semantics & Parameter Research Gate |
| **Date** | 2026-09-18 |
| **Report type** | Research / design record |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Baseline commit** | `96b56ea` |
| **Preregistration sealed at** | `c05e870` — **before the harness existed** |
| **Status** | Final — **D1 and D2 both resolved, with limitations.** ADR-0033 `Proposed`, awaiting Dovydas + ChatGPT |

> **Reading key.** **FACT** — verified against the live repository. **MEASUREMENT** — produced by
> this milestone's harness. **INTERPRETATION** — a reading of a measurement. **RECOMMENDATION** — a
> proposal. **UNRESOLVED** — open, and named as open.

---

## 1. Executive summary

**This gate did not pick a number. It found that the number was never the decision.**

Report 0047 §43 states **D1** as one question — *what tolerance groups levels into a zone* — and §15.3
argues it entirely in terms of the **unit**: ATR multiple (recommended), percentage (rejected), exact
prices (useless). §15.2 says levels are "clustered" and does not say how.

**MEASUREMENT.** The unit is the smaller half of the decision. The grouping rule decides everything,
and the three natural readings of "clustered" behave completely differently:

| Grouping rule | Result over 36 symbols × 3 roles |
|---|---|
| **single-linkage** (cut where the adjacent gap exceeds `w`) — the most natural reading of 0047's wording | **chains.** 247 of 339 levels into one zone on BTC 1D; zones up to **94× wider than the policy's own tolerance**; 1,823 cells exceeded it |
| **diameter-bounded greedy** over price-sorted levels — the textbook defence against chaining | **not long/short symmetric** (2 % of cells pass) and rewrote history on **120,441** prefix events |
| **anchored, online, bands frozen at creation** | **0** illegal prefix events; exact symmetry and exact unit-invariance throughout the admissible range |

**Exactly one family survived the preregistered admissibility gate:** anchored construction ·
ATR-multiple width · frozen at the anchor's establishment bar · `k ∈ [0.10, 1.00]`.

**And the parameter is still not measurable.** Every descriptive metric is **monotone** in `k`. There
is no plateau, no optimum and no knife-edge, because `k` is a **resolution control**, not a natural
constant — and a study that deliberately refuses outcome data cannot derive one. The evidence bounds
the region; it does not choose inside it. **V1 must declare `k`, and ADR-0033 says so in those words.**

**D2 was strengthened from an architectural position into a measurement.** The disposition forbids
*below price = support*. This milestone measured what that rule would cost: **22 %** of zones above
the close on 1W have no interaction history at all, and **39 % (1W) / 50 % (1D)** of zones have had
price close on **both** sides since they were established — meaning the position rule called one
zone *support* on some days and *resistance* on others with nothing about its behaviour changing.
The rule is not merely sometimes wrong; on half of all zones it is **not well-defined over time**.

**Three candidate rules were repaired mid-study, each because a measurement refuted them, and each
repair is recorded in place.** The most uncomfortable is §20.2: the preregistration's own tie-break
was wrong.

**No production code changed.** `src/` and `tests/` are untouched; the policy digest is unchanged.

---

## 2. Verified starting baseline

**FACT**, verified by live inspection before anything was read or written.

| Field | Prompt expected | Live repository | Match |
|---|---|---|---|
| `HEAD` | `96b56ea` | `96b56eac8162c7a4b1aa3ec176d2f4d451575e96` | ✅ |
| `main` = `origin/main` = remote | — | all three `96b56ea`, confirmed by `git ls-remote` | ✅ |
| Ahead / behind | — | `0 / 0` | ✅ |
| Stash | empty | empty | ✅ |
| Active Git operation | none | none — no `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD` | ✅ |
| Tracked tree | clean | clean | ✅ |
| Untracked | 16 research documents | **16**, all present and **untouched at close** | ✅ |
| Full suite | 15,092 / 0 / 0 / 0 | documented at `00c7723`; **not re-run** — see §31 | n/a |
| Policy baseline | 81 fixtures, 72 `WAIT` / 9 `CANDIDATE` | unchanged; **no fixture read or written** | ✅ |
| Digest | `8b22e6c9…` | unchanged — no policy input was touched | ✅ |
| Operator dashboard | may be on `127.0.0.1:8787` | **PID 46403 confirmed `LISTEN`**, read-only `lsof`, never signalled | ✅ |
| Risk config | none | `~/.fmits/` holds only `scan_memory/`; `risk_policy.json` **not created** | ✅ |

**One discrepancy, recorded.** `CURRENT_STATE.md` §0.1 records `HEAD` as `00c7723`; the live `HEAD`
is `96b56ea`. **This is not drift**: `96b56ea` is the documentation commit *"docs(ta): record the
commit TA Slice 5A was delivered at"*, made after §0.1 was written, and `00c7723` is its parent. The
live repository wins and this report is written at `96b56ea`.

---

## 3. Authority reconciliation

Read live: `START_HERE_FOR_AI.md` · `CURRENT_STATE.md` · `CAPABILITY_REGISTRY.md` ·
`FMITS_PRODUCT_BACKLOG.md` · `CLAUDE.md` · reports 0047, 0048, 0049 ·
`REPORT_0047_REVIEW_DISPOSITION.md` · ADR-0013, 0018, 0019, 0020, 0024, 0028, 0031, 0032 ·
`docs/design/`.

**Hierarchy applied:** ADR > `CURRENT_STATE` §0 > `CAPABILITY_REGISTRY` > backlog > historical report.
**Report 0047 was not modified.** Where this milestone contradicts it (§20), the contradiction is
recorded here and in the design document, never by rewriting 0047.

### 3.1 ADR numbering — 0047's proposal is superseded

**FACT.** Report 0047 §44 proposed ADR-0031 for Price Zones and ADR-0032 for Fact Carriage. TA Slice
5A then consumed both numbers for different decisions:

| Number | 0047 proposed | **Live repository** |
|---|---|---|
| ADR-0031 | Price Zone semantics | **`ADR-0031-feature-series-contract.md`** — Accepted 2026-09-17 |
| ADR-0032 | Fact carriage | **`ADR-0032-market-technical-context-carriage.md`** — Accepted 2026-09-17 |
| ADR-0033 | — | **this milestone's Price Zone ADR** — the next free live number |

Normal historical evolution. Nothing is renumbered and report 0047 is not rewritten.

### 3.2 A name collision worth recording

`docs/design/AP_D1_D2_INVESTIGATION.md` concerns **AP-D1 / AP-D2** — money semantics and the capture
contract — and has **nothing to do with report 0047's D1 / D2**. Two unrelated decision pairs share
a label. AP-D2 remains open and is unaffected by this milestone.

---

## 4. Current structural primitives — audited before designing

**FACT**, read from live source.

```
candles → detect_swings (left=2, right=2) → compare_swing_sequence → label_swing_sequence
        → structural_levels → PriceLevel(price, side, LevelOrigin(index, timestamp, label,
          confirmation_bars)) → derive_level_crossings → BOS → CHoCH → trend → regime
```

| Primitive | What it guarantees, verbatim from the source |
|---|---|
| `PriceLevel` | price **copied, never recomputed**; side from one authoritative label map; provenance carried |
| Equal prices | **stay distinct** — "two swings at exactly the same price produce two levels, because their origins differ" |
| `LevelOrigin.confirmation_bars` | copied off the swing, **never taken as an argument** (ADR-0024; a parameter would relocate the ADR-0020 D1 hazard and dress it as provenance) |
| `CrossingKind` | `TOUCH` / `WICK_BREACH` / `CLOSE_BREACH`, **exact comparison, no epsilon**; "tolerance belongs at ingestion behind a tick-size model that does not exist" |
| `CrossingMechanism` | `WITHIN_RANGE` / `GAPPED_BEYOND` / `ALREADY_BEYOND` |
| ADR-0019 **D2** | the first swing high and first swing low produce **no level** |
| `compute_series()` | ADR-0031, additive; `atr_14` publishes one value per closed candle from bar `period` |
| Index space | `SwingPoint.index` = `LevelOrigin.index` = `LevelCrossingEvent.index` = `FeatureSeriesPoint.index` |

**The zone model contradicts none of these.** The harness *calls* every one of them and reimplements
none.

---

## 5. D1, stated exactly

> How should FMITS decide that multiple confirmed structural levels belong to the same `PriceZone`?

**INTERPRETATION, and the load-bearing claim of this report:** D1 contains three independent
sub-decisions, and a wrong answer to any one cannot be repaired by the other two.

| Axis | Question | 0047's treatment |
|---|---|---|
| **A1 — distance scale** | in what units is *close enough* expressed? | the whole of §15.3 |
| **A2 — grouping geometry** | given `w`, by what rule do levels become zones? | **unaddressed** |
| **A3 — temporal reference** | *when* is a volatility-derived scale read? | named as a prerequisite, never specified |

The preregistration stated in advance that **A2 was expected to dominate**. It does.

## 6. D2, stated exactly

> When may a `PriceZone` be described as support, resistance, role-flipped, broken or held?

Disposition §E already fixes the derivation rule. Open here: **D2-A** may it be accepted
architecturally now · **D2-B** the exact internal vocabulary · **D2-C** may the renderer say
"Support zone" · **D2-D** what is premature · **D2-M** *(added)* how often would the forbidden rule
be wrong?

---

## 7. Preregistered methodology, and the seal

[`docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md`](../docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md),
`sha256 d5a94b0558f5bc69e346b66300b0fba81a62d2e6847f2012c64ec0fbf50baed0`, committed as **`c05e870`**
with the message *"seal the price-zone parameter preregistration"* — **before a single line of
`research/zone_semantics/` existed.** Git history is the evidence, not this sentence.

It fixes: the three axes · the candidate set with a reason per member · the grids · the dataset · the
metrics · the fourteen adversarial fixtures · the admissibility gate · the plateau rule · the four
verdicts · what would count as insufficient evidence · and what would **not** be measured.

**Everything added after results existed is labelled `POST-HOC` in §20 and §21.**

---

## 8. Dataset

**FACT.** `reports/artifacts/0040_cd_source_capture.json.gz`, content digest `07b500c7…`, committed
for Milestone CD by `fmis.paired_dependence.capture.capture_ca_sources`.

| Field | Value |
|---|---|
| Symbols | **36** — 15 `primary`, 21 `holdout` |
| Native timeframe | `4h`; 7,313 bars (primary, 2023-04-10 → 2026-08-11), 5,117 (holdout) |
| Roles | `4h` native; `1d` = 6 UTC-aligned 4h bars; `1w` = 7 days, Monday-anchored. **Partial periods dropped** |
| Network | **none.** No fetch, no credential, no live path |
| Price range | ~10⁴ (`BTCUSDT`) to <10⁻⁴ (`WINUSDT`) — **six orders of magnitude** |

**Why this beats a hand-picked BTC/ETH/SOL sample.** The six-order price span is what makes the
scale-invariance test capable of detecting a unit-dependent policy at all. And the capture was
assembled for a **different milestone**, so it could not have been selected to flatter a zone result.

**Stated limitations.** `SOLUSDT` and most post-2023 listings are **absent**; the sample is
survivorship-shaped toward pre-2023 Binance USDT pairs. Volume is not captured (no metric uses it).
An aggregated weekly bar is not a provider weekly bar, though over a complete gapless UTC-aligned
window it is arithmetically identical.

**Regime coverage** comes from cutting each history into non-overlapping windows (1w: 60 bars,
1d: 260, 4h: 900) and describing each by realised ATR-to-price and net displacement — by
construction, never by selection. **10,080 window rows.**

---

## 9–11. Candidates, grids, and the temporal question

| Axis | Candidates |
|---|---|
| **A1 scale** | `W-ATR` (`k × atr_14`) · `W-PCT` (control) · `W-STRUCT` (median adjacent level gap) · `W-STRUCT-CAUSAL` (that median over levels **already knowable**) · `W-TICK` **rejected a priori — not expressible** · `k = 0` reproduces exact-prices as the degenerate case |
| **A2 geometry** | `G-SINGLE` · `G-DIAM` · `G-ANCHOR` · `G-ANCHOR-FIRST` **(POST-HOC, §20.2)** · `G-ANCHOR-EPOCH` **(POST-HOC, §20.3)** · `G-ANCHOR-GROW` |
| **A3 temporal** | `T-ANCHOR` · `T-LAST` · `T-CURRENT` |

**`W-TICK` is rejected on evidence, not preference.** `fmis.data.Candle` carries timestamp · symbol ·
timeframe · OHLC · volume · is_closed, and **no instrument metadata**; no tick size exists anywhere
under `src/`. `CrossingKind`'s own docstring already records that tolerance belongs at ingestion
behind a tick-size model that does not exist. A tick policy is not writable against this data model.

**Hybrids were excluded in advance.** A two-parameter policy selected from the same data that
rejected both one-parameter policies is a fit, not a finding.

### 11. The ATR establishment-time question — tested, not assumed

**MEASUREMENT.** Illegal prefix events, summed across 1,836 policy-series cells per column:

| Temporal reference | `G-ANCHOR-EPOCH` | Reading |
|---|---|---|
| **`T-ANCHOR`** — ATR at the anchor's establishment bar | **0** | the band is knowable when the zone is |
| `T-LAST` — each level's own establishment ATR | **0** | under immutable bands this **is** `T-ANCHOR`: only the anchor's width is ever consumed. Reported as identical rather than as two results |
| `T-CURRENT` — ATR at the latest bar | **983,916** | every historical zone moved its own boundaries on every new bar |

**INTERPRETATION.** A zone whose edges depend on today's volatility is not a record of where an area
was; it is a redrawing of the past. §13 of the brief asks whether a zone may be recomputed from
current ATR. **Measured answer: no.**

**And the related question — may a joining member widen the band?** `G-ANCHOR-GROW` exists only to
answer it: **34,192 illegal events** against **0** for frozen bands. A level outside the zone
yesterday becomes inside it today with no new information about that level. **Measured answer: no.**

---

## 12. Zone geometry alternatives — the result that reframes D1

**MEASUREMENT**, `W-ATR` / `T-ANCHOR`, pooled over 1,836 cells per row:

| Geometry | unit-invariant (decimal) | unit-invariant (exact) | mirror | illegal prefix | `span > w` | admissible |
|---|---|---|---|---|---|---|
| `G-SINGLE` | 1.00 | 1.00 | 0.80 | 42,576 | **1,823** | **no** |
| `G-DIAM` | 1.00 | 1.00 | **0.02** | 120,441 | 0 | **no** |
| `G-ANCHOR` | **0.65** | 1.00 | 0.99 | 0 | 0 | **no** |
| `G-ANCHOR-GROW` | 0.64 | 1.00 | 0.99 | 34,192 | 0 | **no** |
| **`G-ANCHOR-FIRST`** | **1.00** | 1.00 | 0.98 | **0** | 0 | **yes, `k ≤ 1.00`** |
| **`G-ANCHOR-EPOCH`** | **1.00** | 1.00 | 0.98 | **0** | 0 | **yes, `k ≤ 1.00`** |

**`G-SINGLE` is the headline failure**, because it is what 0047's word "clustered" most naturally
means. On BTC 1D at `k = 1.00` it put **247 of 339 levels into one zone**; at `k = 2.00`, **all 339**.
Its widest zone reached **94× its own tolerance**. Chain-merging is not a corner case here; it is the
typical outcome.

**`G-DIAM` fails for a reason worth a minimal example.** A greedy scan over price-sorted levels is
not reflection-symmetric, and three levels suffice to show it (`w = 1.0`):

```
prices  0.0  0.9  1.6         G-DIAM → {0.0, 0.9} {1.6}
reflected about 2.5           G-DIAM → {0.9, 1.6} {2.5}
```

The reflection of `{0.0, 0.9} {1.6}` is `{1.6, 2.5} {0.9}`. The algorithm returns a different
partition of the same structure because ascending and descending scans disagree. `G-ANCHOR`'s bands
are centred on members, and a centre reflects to a centre.

---

## 13. Metrics — descriptive, never a composite

Per `(scale, geometry, parameter, symbol, timeframe)`: `n_levels` · `n_zones` · `zones_per_level` ·
`singleton_fraction` · `merged_level_fraction` · `max_members` · `mean_members` ·
**`max_span_over_w`** (the chain detector) · `median_width_over_atr` · `median_width_over_price` ·
`overlap_fraction` · unit-invariance (decimal **and** exact) · mirror symmetry (negation **and**
offset) · the six-way prefix classification · window agreement.

**No composite score was computed.** A composite would let a policy buy a prefix-stability failure
with a good fragmentation number, and those are not exchangeable quantities.

---

## 14. Adversarial fixtures

**MEASUREMENT.** All fourteen, at a supplied `w` so a grouping failure cannot be blamed on how `w`
was derived.

| # | Fixture | `G-SINGLE` | `G-DIAM` | `G-ANCHOR*` |
|---|---|---|---|---|
| 1 | **chain** — 6 levels at `0.6w` spacing | **FAIL** — 1 zone spanning `3w` | pass | pass |
| 2 | **bridge** — one level midway between two clusters | **FAIL** — 1 zone spanning `2w` | pass | pass |
| 10 | **dense-uniform** — 200 levels at `0.1w` | **FAIL** — 1 zone of 200, span `19.9w` | pass (19 zones) | pass (34 zones) |
| 3–9, 11–14 | two clusters · equal highs · equal lows · single level · outlier · overlapping sides · sparse · volatility jump · gap · scaled · mirrored | pass | pass | pass |

**Fixture 8 is recorded, not asserted.** An `UPPER` and a `LOWER` level at nearly the same price merge
under every geometry. The design states this as a **decision** (§5.4 of the design document): an area
is an area, and the side is a fact about the swing that made the level. Leaving it emergent was the
thing to avoid.

---

## 15. Prefix stability

**MEASUREMENT.** Zones computed on bar prefixes at 60/70/80/90 % of each run, then recomputed on the
full run, each prefix zone classified `PRESERVED` / `GREW` / `BOUNDARY_REWRITTEN` / `SPLIT` /
`MERGED` / `VANISHED`. `GREW` is legitimate — a zone gaining a later-knowable member is the lifecycle
working. The other four are repainting.

**`G-ANCHOR-EPOCH` / `W-ATR` / `T-ANCHOR`: zero illegal events at every cut and every grid value.**

**INTERPRETATION.** This is not a lucky result, it is the construction. An anchored rule answers
*given the zones that already exist, where does this level belong* — and the answer cannot change
what was already written. A clustering rule answers *given all these levels, how do they group*,
which has a different answer every time a level arrives, so every published zone is provisional. The
prompt asks that non-repainting be demonstrated rather than asserted; the demonstration is that the
three clustering formulations produced 42,576 / 120,441 / 696,588 illegal events on the same data.

---

## 16. Scale invariance — and the distinction that had to be made

**MEASUREMENT.** Two rescales, for two different questions:

| Factor | Exact in IEEE-754? | What a failure means |
|---|---|---|
| `2⁻¹⁰`, `2¹⁰` | **yes** | a genuine **unit dependence** in the policy |
| `10⁻³`, `10³` | no | **float sensitivity** — the inputs move by an ulp |

**Every policy passes the exact test (1.00 across all 55,728 cells).** No candidate is unit-dependent
in exact arithmetic. The decimal test separates them, and separating the two questions is what made
§20.2's defect findable at all — the preregistration specified only "multiply by `10±3`", which
conflates them.

---

## 17. Symmetry

**MEASUREMENT.** Reflection by **negation** (`p → −p`), which is exact in IEEE-754; the offset form
`C − p` is reported as a weaker second check. An earlier offset-only test was measuring floating-point
rounding as much as the policy.

`G-ANCHOR-EPOCH` / `W-ATR` / `T-ANCHOR`: **100 % symmetric for every `k ≤ 1.00`.** Failures begin at
`k = 1.25` (29 cells of 1,836 overall), concentrated in `ICXUSDT`, `ONTUSDT`, `NEOUSDT`, `ONGUSDT`.

**The mechanism, named rather than waved at** (§20.3): one candle can be both a swing high and a
swing low, so two levels share an establishment bar. At large `k` the two bands they open overlap
each other, and a later level inside both is assigned by band creation order — which must be broken
on side or price, both of which invert under reflection. **`G-ANCHOR-EPOCH` removes the case where a
sibling claims its twin but not the case where a later level chooses between two sibling bands.**
The residual lies entirely **above** the admissible ceiling, which is why the ceiling is `1.00`.

**`W-PCT` fails symmetry outright — 6 %.** A width proportional to price cannot mirror: zero is an
absolute floor and there is no corresponding ceiling. **This is a stronger and more specific
objection than 0047 §15.3's "invented threshold", and unlike that one it is measured.**

---

## 18–19. Cross-asset and cross-timeframe transfer (R20, R2)

**MEASUREMENT**, `G-ANCHOR-EPOCH` / `W-ATR` / `T-ANCHOR`, median per asset over the whole history:

| `k` | singleton fraction: min / median / max across 36 assets | spread |
|---|---|---|
| 0.30 | 0.152 / 0.357 / 0.505 | 0.353 |
| 0.50 | 0.111 / 0.228 / 0.369 | 0.258 |
| 1.00 | 0.074 / 0.157 / 0.244 | 0.170 |

**Cross-timeframe, at one `k` — the more consequential result:**

| `k` | 1W singleton / zones-per-level / max members | 1D | 4H |
|---|---|---|---|
| 0.30 | 0.556 / 0.588 / **4** | 0.357 / 0.350 / **11** | 0.203 / 0.186 / **32** |
| 0.50 | 0.429 / 0.483 / **5** | 0.233 / 0.248 / **15** | 0.139 / 0.117 / **50** |
| 1.00 | 0.368 / 0.322 / **8** | 0.161 / 0.134 / **24** | 0.091 / 0.059 / **88** |

**INTERPRETATION — R20 is answered "partly", and the honest form matters.** The *policy* transfers:
it is admissible at every role and every asset, with no per-role constant anywhere. The *resulting
zone map* does not: at one `k`, a 4H zone holds up to 50 members where a 1W zone holds 5. That is
largely correct behaviour — the 4H series genuinely contains 2,029 levels where 1W contains 47 — but
it means **the product meaning of "a zone" differs by role at a shared `k`**.

**UNRESOLVED.** Whether `k` should be per-role is a **product** question, not a representation one,
and this gate does not answer it. Report 0047 §12-G warns against hidden per-timeframe constants; if
a per-role `k` is ever taken it must be three explicit declared policies, never a magic table.

---

## 20. Sensitivity, and the three repairs

### 20.1 Sensitivity — there is no plateau, and that is the finding

**MEASUREMENT.** Median fractional change in zone count between adjacent grid values, 108 series:

| step | median | step | median | step | median |
|---|---|---|---|---|---|
| 0.00→0.10 | 0.325 | 0.35→0.40 | 0.095 | 0.60→0.70 | 0.123 |
| 0.10→0.20 | 0.280 | 0.40→0.45 | 0.080 | 0.70→0.80 | 0.108 |
| 0.20→0.25 | 0.129 | 0.45→0.50 | 0.080 | 0.80→1.00 | 0.185 |
| 0.25→0.30 | 0.116 | 0.50→0.55 | 0.071 | 1.00→1.25 | 0.192 |
| 0.30→0.35 | 0.102 | 0.55→0.60 | **0.066** | 2.00→3.00 | 0.322 |

Normalised per 0.05 of `k`, sensitivity **declines monotonically** across the whole admissible region
— 12.9 % at 0.20, 8.0 % at 0.45, 6.6 % at 0.55, 4.6 % by 1.00. **No cliff and no plateau.**

**INTERPRETATION.** The preregistration's §6.2 required "at least five consecutive grid values across
which every metric moves monotonically and without discontinuity." By the **letter** of that
criterion the entire region `[0.10, 1.00]` qualifies — which reveals the criterion was written for
the wrong shape of result. The **spirit** of a plateau is a region where the answer is *insensitive*,
and nothing here is insensitive: `k` directly and smoothly controls how coarse the zone map is.

**This is the honest verdict on the parameter, and this report refuses to dress it up.** `0.50` is
not better than `0.45` or `0.55` by any evidence in this study. The prompt's §41 asks that FMITS be
able to *explain, reproduce and challenge* why it groups these levels this way. It can. It cannot say
that any `k` in `[0.10, 1.00]` is the right one, and saying so would be the invented threshold
wearing the study as a costume.

### 20.2 POST-HOC repair 1 — **the preregistration's own tie-break was wrong**

**MEASUREMENT.** `G-ANCHOR` as specified in the preregistration (§2.2: ties go to the *nearest
centre*, then the older band) failed decimal unit-invariance on **35 %** of series.

**Diagnosis, not a guess.** Bands overlap heavily (70 % of adjacent pairs at `k = 0.50`), so ties are
common. Nearest-centre compares two distances, so the outcome turns on the *difference of two nearly
equal floats*; an inexact rescale perturbs both by an ulp and flips the assignment. No member sat
nearer than `1.2 × 10⁻³` of a band edge, so this was never a boundary effect.

**Repair.** `G-ANCHOR-FIRST`: the **oldest band that already contains the level** claims it. That
compares a price against a boundary rather than two distances against each other, is stable under any
perturbation smaller than the distance to that boundary, and says something defensible.
**Result: 1.00.**

### 20.3 POST-HOC repair 2 — one bar must be one instant

**MEASUREMENT.** `G-ANCHOR-FIRST` still failed mirror symmetry on 29 cells. Diagnosis: one candle can
produce both an `UPPER` and a `LOWER` level (measured: 3 such collisions on ICX 1W, 9 on 1D, **60** on
4H), and ordering them requires their side or price, both of which invert under reflection.

**Repair.** `G-ANCHOR-EPOCH`: every level established at bar *i* is tested against the bands that
existed **before** *i*, and bands opened at *i* cannot claim each other's levels. It removes that
mechanism. It does **not** remove the residual of §17, and this report says so rather than claiming
the fix was complete.

### 20.4 POST-HOC repair 3 — the rejected candidate got the same repairs

**This is the methodological point of the section.** Two repairs had been applied to the favoured
geometry and none to `W-STRUCT-CAUSAL`, which was failing mirror symmetry **for the same root cause**
— its causal median read levels in an order broken on side and price. Rejecting a candidate for a bug
that was fixed in its rival is not a result.

**So it was repaired identically** (ordered by establishment bar only, applied per bar) and re-run
across the full study. Mirror symmetry rose **0.81 → 0.99** and prefix illegality is **0**.

**It still fails decimal unit-invariance at 0.61**, and now for a reason that is its own: a median of
price *differences* involves enough arithmetic to be numerically fragile where a single ATR
multiplication is not. Its window-start agreement is also materially worse — **0.964 at `k = 1.00`**
against `W-ATR`'s **0.984**, because Wilder smoothing forgets its seed exponentially while a median
over all prior gaps never forgets.

**The rejection now rests on a fair comparison.** That cost one extra full re-run and it was the
right trade.

### 20.5 One harness defect, found and fixed

The transform comparison keyed partitions on `origin_index`, which **merges the two levels one candle
can produce** — so two different partitions could compare equal and one identical pair could compare
different. Identity was moved to a per-run sequence number carried through every transform, and an
assertion now **raises** if any transform drops it rather than silently comparing against the
sentinel. That assertion caught a second instance immediately (`_scale_levels` had lost the field),
which had been reporting every rescale as a failure.

---

## 21. Fragmentation and over-merging

**MEASUREMENT**, `G-ANCHOR-EPOCH` / `W-ATR` / `T-ANCHOR`, medians over all 108 series:

| `k` | zones/level | singleton | merged | max members | overlap | window agreement |
|---|---|---|---|---|---|---|
| 0.00 | 0.962 | **0.962** | 0.075 | 2.5 | 0.000 | 1.0000 |
| 0.10 | 0.633 | 0.628 | 0.601 | 6.0 | 0.355 | 0.9994 |
| 0.30 | 0.350 | 0.353 | 0.872 | 11.0 | 0.607 | 0.9970 |
| 0.50 | 0.248 | 0.228 | 0.941 | 15.0 | 0.703 | 0.9934 |
| 0.80 | 0.162 | 0.179 | 0.971 | 21.0 | 0.793 | 0.9884 |
| 1.00 | 0.134 | 0.145 | 0.979 | 24.5 | 0.831 | 0.9843 |
| 2.00 | 0.067 | 0.100 | **0.994** | **44.5** | 0.895 | 0.9620 |
| 3.00 | 0.047 | 0.080 | **0.998** | **60.5** | 0.952 | 0.9462 |

**Degeneracy at both ends, as the preregistration required be tested.** `k = 0` reproduces
0047 §15.3's "option A" — 96 % singletons, correct and useless. `k ≥ 2.00` merges 99.4 % of levels
into zones of 44+ members, destroying distinct areas.

**Overlap is a real property, not an artefact.** At `k = 0.50`, **70 %** of adjacent zone pairs have
intersecting bands. Membership is unique, but a *price* can sit inside several zones. Every consumer
must handle that, and the design says so rather than smoothing it away.

**Window-start sensitivity (POST-HOC).** Loading a symbol from a later start bar moves ATR's Wilder
seed and so moves band edges slightly. Pairwise agreement **0.9934** at `k = 0.50`, **0.9843** at
`k = 1.00`. Added after the preregistered battery left two scales standing, and added in the only
honest direction: it can disqualify a candidate, never promote one.

---

## 22. Qualitative inspection

**None was used.** No chart was eyeballed and no parameter was chosen by looking at one. The
preregistration permitted bounded qualitative inspection as secondary evidence; it was not needed,
because the admissibility gate resolved the geometry and no visual judgement could have chosen a `k`
that the metrics decline to choose.

---

## 23. Rejected alternatives

| Rejected | On what evidence |
|---|---|
| `G-SINGLE` | chains — 94× its own tolerance; 1,823 cells over; three fixture failures |
| `G-DIAM` | not reflection-symmetric (2 %); 120,441 illegal prefix events; 3-level counterexample |
| `G-ANCHOR` (nearest-centre) | unit-invariance 0.65 — an unstable tie-break (§20.2) |
| `G-ANCHOR-GROW` | 34,192 illegal events — a joining member rewrites history (§11) |
| `T-CURRENT` | 983,916 illegal events — historical zones redraw themselves every bar |
| `W-PCT` | not long/short symmetric, 6 % — measured, not asserted |
| `W-STRUCT` | 696,588 illegal events — its yardstick did not exist when the zone did |
| `W-STRUCT-CAUSAL` | after the **same** repairs: unit-invariance 0.61, worse window agreement (§20.4) |
| `W-TICK` | **not expressible** — no instrument metadata exists under `src/` |
| Hybrids | excluded in advance — two parameters fitted to the data that rejected one |

---

## 24. D1 verdict — **RESOLVED WITH LIMITATIONS**

| Sub-decision | Verdict |
|---|---|
| **A2 geometry** | **RESOLVED.** Anchored, online, bands frozen. Uniquely admissible; every alternative failed a preregistered criterion |
| **A3 temporal** | **RESOLVED.** `T-ANCHOR`. `T-CURRENT` and growable bands each disqualified by measurement |
| **A1 scale** | **RESOLVED.** `W-ATR`. One survivor after every candidate received equal repair |
| **The value of `k`** | **NOT RESOLVED, and not resolvable by this study.** Region bounded to `[0.10, 1.00]`; no interior optimum exists because every metric is monotone. **V1 must declare it** |

**Why not simply `RESOLVED`.** Three of four sub-decisions are settled on evidence. The fourth is
settled only as a *bounded region*, and calling that `RESOLVED` would let the number look measured.

## 25. D2 verdict — **RESOLVED**

| | Verdict |
|---|---|
| **D2-A** — accept role-from-interaction-history now? | **YES.** Disposition §E's rule is now supported by measurement, not only by architecture |
| **D2-B** — internal vocabulary | **RESOLVED.** `UNTESTED` · `HELD_FROM_ABOVE` · `HELD_FROM_BELOW` · `BROKEN_UPWARD` · `BROKEN_DOWNWARD` · `ROLE_FLIPPED` · `INDETERMINATE`, with `position` a **separate** field |
| **D2-C** — may the renderer say "Support zone"? | **YES, conditionally** — only as a label over a derived role, only once the interaction engine exists, never for `UNTESTED`. The three guards stay in force until then |
| **D2-D** — premature | `ACCEPTANCE`, `RECLAIM`, `RETURN_INSIDE`, retest, false breakout — each needs **R3** or **R4**. **A `CLOSE_BREACH` is not a breakout** |

**D2-M — the measurement (36 symbols):**

| | 1W | 1D |
|---|---|---|
| zones above the close with **no interaction history** — the position rule prints *resistance* on zero observations | **22 %** (max **75 %**) | **7 %** |
| zones below the close, same | **25 %** | **22 %** |
| **zones price has closed on _both_ sides of since establishment** | **39 %** | **50 %** |

**INTERPRETATION.** The last row is the decisive one. On half of all 1D zones the position rule
called the same zone *support* on some days and *resistance* on others, with nothing about its
behaviour changing in between — only price moving. The rule is not merely *sometimes wrong*; it is
**not well-defined over time**. This is a stronger statement than disposition §E makes, and it is
measured.

---

## 26. Recommended V1 semantics

Full contract: [`docs/design/PRICE_ZONE_ENGINE_V1.md`](../docs/design/PRICE_ZONE_ENGINE_V1.md).
Binding form: [ADR-0033](../docs/adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md)
(`Proposed`).

```
levels in establishment order
  inside an existing band?  → join it (oldest containing band)
  otherwise                 → open a band  [p − w/2, p + w/2]
                              w = k × atr_14 at this level's own establishment bar
one bar is one instant; bands never move, merge, split or vanish
no ATR at the anchor's bar → no zone, and never a default width
```

The tolerance is **scoped to zone membership**. `PriceLevel` equality, `classify_comparison` and
`CrossingKind` stay exact. `PriceLevel(A) != PriceLevel(B)` and `Zone.members == {A, B}` are both
true, and that is the design rather than a tension in it.

---

## 27. Known limitations

1. **`k` is declared, not measured.** The largest open item, open by construction.
2. **Symmetry fails above `k = 1.00`** — mechanism named (§17), bound is the admissible ceiling.
3. **Zones overlap heavily** — 70 % of adjacent pairs at `k = 0.50`.
4. **Band edges are window-sensitive at the margin** — 0.9934 agreement at `k = 0.50`.
5. **One `k` does not give one zone-map density across roles** (§18–19).
6. **Sample**: 36 pre-2023 Binance USDT pairs; no `SOLUSDT`; 1W/1D aggregated from captured 4H.
7. **ADR-0019 D2** — the earliest zone on each side is missing, inherited and stated.
8. **No role is derived yet** — no interaction engine exists.
9. **The window test is not evaluable at the 1W role** (too few bars after the offset); its prefix
   and symmetry results are.

## 28. Revisit triggers

**R3/R4** answered → interaction states may be specified. **R15** answered → and only then may
independence be discussed. **A tick-size model at ingestion** → `W-TICK` becomes expressible. **A
better-conditioned structural scale** → the width family reopens. **`k` shown to affect a product
outcome** → the declaration must be re-taken as a measurement.

---

## 29. Product First assessment

**This milestone shipped no user-visible capability, and must not claim one.**

**FMITS does not now understand support and resistance.** It has no zone engine. `/swing/SYMBOL` is
byte-identical.

**The narrow justification, which is the only one available.** TA Slice 5B was `NOW — BLOCKED` on an
owner decision that could not be taken because the evidence did not exist. It now exists: the
decision is reduced from *"invent a tolerance"* to *"accept a bounded, versioned declaration inside
an admissible region, on a construction that is provably non-repainting"*. A zone engine written
before this gate would have used single-linkage clustering with current-ATR width — the two choices
that measurement shows produce chaining and continuous repainting — and it would have looked correct.

**The clearest way to state the value:** this gate is the difference between a zone engine that is
trusted and one that is merely built.

## 30. Policy non-regression

**FACT.** No policy fixture, threshold, gate or evidence rule was read, written or touched.

| Held | State |
|---|---|
| 81 fixtures · 72 `WAIT` / 9 `CANDIDATE` | unchanged |
| Digest `8b22e6c9…` | unchanged |
| `src/` · `tests/` | **zero files changed** |
| Strategy gates · 1W regime gate · evidence voting | untouched |
| `fmis.scan_memory` | untouched; `~/.fmits/scan_memory` never written |
| Risk / capital | `~/.fmits/risk_policy.json` **not created** |
| Operator dashboard | PID 46403 on `127.0.0.1:8787` — **read-only `lsof` only**, never signalled; `pkill` used only against this milestone's own research processes, never by pattern against the dashboard |

## 31. Validation performed — proportional, and honestly scoped

**The full suite was not re-run, and this report does not quote a fresh suite result.** `src/` and
`tests/` are byte-unchanged, so a re-run would measure the same code at the same commit. The
15,092-test baseline stands **as established by report 0049 at `00c7723`**.

What *was* verified:

| Check | Result |
|---|---|
| `src/` and `tests/` unchanged | `git status` — zero entries under either |
| No production import of research code | `grep -rn "research.zone_semantics" src/ tests/` → **0 hits** |
| `fmis` imports with `research/` off the path | verified from `/tmp` |
| Determinism across processes and `PYTHONHASHSEED` | **IDENTICAL** — two separate processes at seeds `0` and `12345`, `PYTHONDONTWRITEBYTECODE=1`, byte-compared: `sha256 376b1095fdb2206b…` both times |
| Harness calls production code, never reimplements it | `detect_swings`, `compare_swing_sequence`, `label_swing_sequence`, `structural_levels`, `derive_level_crossings`, `AverageTrueRange.compute_series` — all imported from `fmis` |
| Artifact sizes before staging | 2.83 MB + 0.79 MB gzipped |
| No credential or secret in any artifact | payloads contain only prices, indices, timestamps and metrics |

## 32. Files changed

**Added — documentation**

- `docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md` *(sealed at `c05e870`)*
- `docs/design/PRICE_ZONE_ENGINE_V1.md`
- `docs/adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md`
- `reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md`

**Added — research harness** (`research/`, outside `src/`, deletable)

`__init__.py` · `dataset.py` · `structure.py` · `policies.py` · `metrics.py` · `fixtures.py` ·
`d2.py` · `run.py` · `secondary.py` · `analyze.py` · `verify.py`

**Added — artifacts**

`reports/artifacts/0050_zone_semantics_results.json.gz` (2.83 MB, 55,728 rows) ·
`reports/artifacts/0050_zone_semantics_secondary.json.gz` (0.79 MB, 10,080 + 216 rows)

**Modified — project memory**

`docs/AI_HANDOFF/CURRENT_STATE.md` · `docs/AI_HANDOFF/CAPABILITY_REGISTRY.md` ·
`FMITS_PRODUCT_BACKLOG.md` · `reports/README.md` · `docs/adr/README.md`

**Unchanged:** `src/`, `tests/`, `FMITS_PRODUCT_CHANGELOG.md` (no user-visible capability shipped —
recording a research gate there would violate `CLAUDE.md`), and the 16 pre-existing untracked
research documents.

## 33. ADR and design documents

| Document | Status |
|---|---|
| ADR-0033 | **Proposed** — the research earns a binding decision; the owner must accept §6's declaration knowingly |
| `PRICE_ZONE_ENGINE_V1.md` | **DESIGNED — not implemented**; records the three places it contradicts report 0047 §15.2 and why |
| `ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md` | **Sealed preregistration** |

## 34. Git state

| Field | Value |
|---|---|
| **Baseline** | `96b56ea` — `main` = `origin/main`, `0/0`, clean |
| **Preregistration seal** | `c05e870` — *"research(zones): seal the price-zone parameter preregistration"*, pushed before the harness existed |
| **This milestone's commits** | recorded in the handoff at close |
| **Untracked preserved** | the 16 pre-existing research documents, verified present and unmodified |

## 35. Exact next milestone

**TA Slice 5B — Price Zones & Interactions**, unblocked on D1 and D2, blocked only on the owner
accepting ADR-0033. Scope: `fmis.price_zones` implementing the design document; a real product
consumer on `/swing/SYMBOL`; **no interaction vocabulary beyond what §7.4 of the design permits**;
no strategy, evidence, gate, scan-memory or risk change.

## 36. Remaining owner / ChatGPT decisions

1. **Accept ADR-0033?** — including that `k` is **declared, not measured**.
2. **What `k`**, inside `[0.10, 1.00]`? The evidence bounds the region and declines to choose. `0.50`
   sits mid-region with 23 % singletons and 15-member zones at 1D; `0.30` keeps zones tighter
   (35 % singletons, 11 members); `0.80` merges harder (18 %, 21 members). **No evidence prefers any
   of them.**
3. **One `k` for all three roles, or three declared policies?** (§18–19) — a product judgement.
4. **May "Support zone" ever be rendered?** D2-C recommends yes, conditionally.
5. Unaffected and still open: **0047 D3**, **0047 D5**, **AP-D2**, **D-03**, the capital declaration.

---

## 37. WHAT A NEW AI MUST KNOW IN 5 MINUTES

1. **Read [ADR-0033](../docs/adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md) and
   [`PRICE_ZONE_ENGINE_V1.md`](../docs/design/PRICE_ZONE_ENGINE_V1.md).** They, not this report, are
   what Slice 5B implements.
2. **D1 was three decisions, not one.** Geometry, temporal reference, scale. The geometry dominates
   and report 0047 does not discuss it.
3. **Do not cluster levels.** Anchor them. Single-linkage chains catastrophically; every clustering
   formulation tested rewrote history.
4. **A zone's band is frozen at its anchor and never moves.** Not by a joining member, not by new
   volatility. Both alternatives were measured and both repaint.
5. **`k` is declared, not measured.** `[0.10, 1.00]`. Anyone claiming a value was found by research
   is misreading this report.
6. **Role comes from interaction history. Never from position.** Half of all zones have had price on
   both sides; the position rule is not well-defined over time.
7. **A `CLOSE_BREACH` is not a breakout.** Interaction semantics need R3/R4, unanswered.
8. **Zone evidence independence is NOT ESTABLISHED** (R15). No zone may reach evidence voting.
9. **`PriceLevel` equality is still exact, everywhere.** The tolerance is scoped to zone membership
   and nowhere else. ADR-0013 §4 is not weakened.
10. **Nothing in `src/` changed.** The policy digest is unchanged, and it must stay unchanged.
11. **Report 0047 is superseded in three places** — §2 of the design document names them. 0047 itself
    is not rewritten; it is historical evidence.
12. **The harness lives in `research/`, not `src/`.** Reproduce with
    `.venv/bin/python research/zone_semantics/run.py`, then `analyze.py`, then `verify.py`.
