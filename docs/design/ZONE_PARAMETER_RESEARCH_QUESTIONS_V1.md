# Zone Parameter Research — Preregistration V1

**Reserved by** [report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §44
as `docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md` — "§45's list, preregistered before any
number is chosen".

| Field | Value |
|---|---|
| **Status** | **PREREGISTRATION — sealed before any outcome was computed** |
| **Written at commit** | `96b56ea` |
| **Date** | 2026-09-18 |
| **Milestone** | Price Zone Semantics & Parameter Research Gate (report 0050) |
| **Decides** | nothing. It fixes *what will be measured* and *what would refute a candidate* |
| **Subjects** | **0047 D1** (zone-width tolerance) · **0047 D2** (zone role semantics) · research questions **R1**, **R2**, **R20** |

> **This document was committed before the measurement harness produced a single number.**
> Git history is the evidence. Anything added after results exist is marked
> `POST-HOC` in place and is not part of the preregistration.

---

## 0. Why a preregistration is required here

D1 asks for a **tolerance** — the one thing this repository has refused everywhere
([ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md) §4; restated in `fmis.level_crossing`
and again in `classify_comparison`). A tolerance chosen after looking at which number "looked nicest"
on BTC is an invented threshold wearing a research costume. The only defence is to fix the question,
the candidate set, the metrics and the refutation criteria first.

---

## 1. The exact research questions

### D1 — the primary question

> **How should FMITS decide that multiple confirmed structural levels belong to the same
> `PriceZone`?**

This preregistration asserts that D1, as written in 0047 §43, **contains three independent
sub-decisions** that 0047 §15.3 presents as one. They are measured separately because a wrong answer
to any one of them cannot be repaired by the other two:

| Axis | Question | 0047's treatment |
|---|---|---|
| **A1 — distance scale** | In what units is "close enough" expressed? | the whole of §15.3 (`ATR multiple` vs `percentage` vs `exact`) |
| **A2 — grouping geometry** | Given a distance `w`, by what rule do levels become zones? | **not addressed** — §15.2 says "clustered" and stops |
| **A3 — temporal reference** | If the scale is volatility-derived, *when* is that volatility read? | named as a prerequisite by disposition §C, never specified |

**A2 is the axis this preregistration expects to matter most**, because prefix stability and
chain-merging are properties of the grouping rule, not of the distance unit. If that expectation is
wrong, the results will say so.

### D2 — the role question

> **When may a `PriceZone` be described as support, resistance, role-flipped, broken or held?**

Disposition §E already fixes the *derivation* rule (interaction history, never position). This gate
asks the parts that remain open, and adds one measurement:

- **D2-A** — may role-from-interaction-history be accepted architecturally now?
- **D2-B** — what exact internal vocabulary should production use?
- **D2-C** — may the operator renderer say "Support zone" / "Resistance zone"?
- **D2-D** — which states are premature until an interaction engine exists?
- **D2-M** *(measurement)* — **how often would the forbidden derivation be wrong?** Among zones that
  sit above the current close, what fraction have **no interaction history at all** and would
  therefore be falsely labelled "resistance" by the position rule?

### Cited research questions

- **R1** — what multiple, if any, produces stable zone membership under prefix extension?
- **R2** — does stability differ by timeframe role or volatility band?
- **R20** — does any threshold transfer across assets and timeframes?

**R3–R6 and R15 are explicitly NOT in scope.** They require an interaction engine that this gate is
forbidden to build.

---

## 2. Candidate set, and why each member is in it

### 2.1 Axis A1 — distance scale

| ID | Definition | Admissible in production? | Why it is in the set |
|---|---|---|---|
| **W-ATR** | `w = k · ATR(14)` on the same series and timeframe | **candidate** | 0047 §15.3 option C; volatility-derived rather than asserted; ATR history exists since [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| **W-PCT** | `w = k_pct · p` | **RESEARCH CONTROL ONLY** | 0047 §15.3 rejects it as an invented, asset- and timeframe-dependent threshold. Kept because a control that is *known* to be scale-invariant but *not* volatility-adaptive isolates which property each metric is actually detecting |
| **W-STRUCT** | `w = k_s · S`, `S` = median absolute gap between price-sorted adjacent levels in the run | **candidate** | The one genuinely different idea: the tolerance comes from the **structure's own spacing**, needs no indicator, and carries no warm-up. If it works it removes the ATR dependency entirely |
| **W-TICK** | absolute / tick-multiple distance | **REJECTED A PRIORI — not expressible** | `fmis.data.Candle` carries `timestamp · symbol · timeframe · OHLC · volume · is_closed` and **no instrument metadata**; no tick size, lot size or price filter exists anywhere under `src/`. A tick policy cannot be written against this repository's data model, and inventing a per-symbol tick table is a new ingestion contract, not a zone decision. Recorded as rejected on **evidence**, not preference |
| **W-EXACT** | no tolerance; every level is its own zone | **degenerate reference** | 0047 §15.3 option A. Measured as the `k = 0` end of every grid so that "a tolerance is needed at all" is a result rather than an assumption |

**Hybrids are deliberately excluded from the preregistered set.** A hybrid (`max(ATR-band,
percentage-floor)`) has two parameters, and a two-parameter policy selected from the same data that
rejected both one-parameter policies is a fit, not a finding. A hybrid may be proposed **only** if a
single-scale policy fails for a reason a hybrid demonstrably repairs; it would then be `POST-HOC` and
labelled so.

### 2.2 Axis A2 — grouping geometry

| ID | Rule | Why it is in the set |
|---|---|---|
| **G-SINGLE** | sort levels by price; start a new zone wherever the gap to the previous level exceeds `w` | The obvious implementation, and the one 0047's word "clustered" most naturally reads as. In the set **to be attacked**: it is single-linkage and therefore chains |
| **G-DIAM** | greedy over price-sorted levels; a level joins the open zone only if the resulting **total span** stays ≤ `w` | The standard defence against chaining. Bounded by construction |
| **G-ANCHOR** | process levels in **establishment order**; a level joins the first existing zone whose **frozen band** contains it, else opens a new zone anchored at its own price with band `[p − w/2, p + w/2]`, `w` frozen at the anchor's establishment | The only candidate that is **online** and whose boundaries are immutable once written. Expected to be the only prefix-stable one. Introduces an order dependence that the others do not have — which is itself something to measure |

### 2.3 Axis A3 — temporal ATR reference (applies to W-ATR only)

| ID | `ATR` is read at | Expected hazard |
|---|---|---|
| **T-ANCHOR** | the anchor member's establishment index | none obvious; frozen |
| **T-LAST** | the most recent member's establishment index | width changes as members join → boundaries move |
| **T-CURRENT** | the final closed bar of the run | **recomputes every run → historical zones drift.** Included specifically so the drift is measured rather than asserted |

### 2.4 Parameter grid — fixed now

| Scale | Grid |
|---|---|
| **W-ATR** `k` | `0.00, 0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80, 1.00, 1.25, 1.50, 2.00, 3.00` |
| **W-PCT** `k_pct` | `0.000, 0.0010, 0.0025, 0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300, 0.0500` |
| **W-STRUCT** `k_s` | `0.00, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 3.00, 4.00, 6.00, 8.00` |

The W-ATR grid is deliberately **denser between 0.25 and 0.60** than elsewhere, because 0047 §15.3
gestures at that region and a plateau claim there must be resolvable at 0.05 resolution. Density is
not a prediction that the answer lies there; the grid extends to `3.00` so an answer outside the
region is reachable.

---

## 3. Dataset

**Source: `reports/artifacts/0040_cd_source_capture.json.gz`** — already committed, content-digest
`07b500c7…`, written by `fmis.paired_dependence.capture.capture_ca_sources` for Milestone CD.

| Field | Value |
|---|---|
| **Symbols** | **36** — 15 `primary` + 21 `holdout` |
| **Native timeframe** | `4h` |
| **Span** | `2023-04-10` → `2026-08-11` (primary, 7,313 bars); `2024-04-10` → `2026-08-11` (holdout, 5,117 bars) |
| **Network access** | **none.** No fetch, no credential, no live path |

**Timeframe roles.** The capture is 4H only. `1d` and `1w` are produced by **deterministic
aggregation** of the 4H bars: six UTC-aligned 4H bars to one day, seven days to one Monday-anchored
week — Binance's own kline boundaries. **Partial periods at both ends are dropped**, so every
aggregate bar is complete. Aggregation is stated as a limitation, not hidden: an aggregated weekly
bar is not a provider weekly bar, though for OHLC over a complete, gapless UTC-aligned window it is
arithmetically identical.

**Scale diversity — the reason this capture beats a hand-picked BTC/ETH/SOL sample.** The 36 symbols
span roughly six orders of magnitude of quoted price (`BTCUSDT` at ~10⁴ to `WINUSDT` below 10⁻⁴).
That range is what makes the scale-invariance test meaningful; a BTC/ETH/SOL sample could not detect
a unit-dependent policy at all.

**Stated sample limitations.**

- **`SOLUSDT` is absent** from the capture, as are most post-2023 listings. The sample is
  survivorship-shaped toward assets listed before 2023.
- **Volume is not captured** (bars carry timestamp + OHLC only). No metric in this study uses volume.
- The capture was assembled for a different milestone. It was **not** selected for this one, which is
  the point: it could not have been cherry-picked for a zone result.

**Regime coverage** is obtained by cutting each symbol's history into non-overlapping windows and
classifying each window by realised ATR-to-price ratio and by net directional displacement, so that
*expansion*, *range*, *high-volatility* and *low-volatility* windows are all represented **by
construction rather than by selection**. No window is excluded for looking untidy.

---

## 4. Metrics — descriptive, never a composite score

No candidate will be reduced to a single number. Per `(scale, geometry, parameter, symbol,
timeframe)`:

| # | Metric | What it detects |
|---|---|---|
| 1 | `n_levels`, `n_zones` | size |
| 2 | `singleton_fraction` | **fragmentation** |
| 3 | `merged_level_fraction` | how much structure is actually grouped |
| 4 | `max_members`, `mean_members` | **over-merging** |
| 5 | `max_span_over_w` | **chain-merging.** `> 1` means the zone is wider than the policy's own tolerance |
| 6 | `median_width_over_atr`, `median_width_over_price` | scale behaviour |
| 7 | `overlap_fraction` | how often bands intersect |
| 8 | `zones_per_level` | degeneracy in both directions |

### Robustness checks

| Check | Method | Pass condition |
|---|---|---|
| **Determinism** | run twice in separate processes under different `PYTHONHASHSEED` | byte-identical digest |
| **Scale invariance** | multiply every OHLC by `c ∈ {10⁻³, 10³}` | the **partition of levels into zones is identical** as a set of sets |
| **Mirror symmetry** | reflect every candle about a constant (`p → C − p`, high↔low) | the partition mirrors **exactly** |
| **Prefix stability** | compute zones on bar prefixes at 60/70/80/90 % of the run, then on the full run | every prefix zone classified `PRESERVED` / `GREW` / `BOUNDARY_REWRITTEN` / `SPLIT` / `MERGED` / `VANISHED` |
| **Sensitivity** | Adjusted Rand Index between the partitions at adjacent grid values | reported as a curve, never thresholded into a verdict |

**`GREW` is legitimate and `BOUNDARY_REWRITTEN` is not.** A zone gaining a member that later becomes
knowable is the lifecycle working. A zone whose `low`/`high` change for a bar that was already in the
past is a historical rewrite, and that is the disqualifying event.

---

## 5. Adversarial fixtures — every one fixed now

Synthetic level sets, evaluated against the **geometry** axis at a supplied `w` so that grouping is
tested independently of how `w` was derived.

| # | Fixture | What it must not do |
|---|---|---|
| 1 | **chain**: levels at `0, 0.6w, 1.2w, 1.8w, 2.4w, 3.0w` | collapse into one zone spanning `3w` |
| 2 | **bridge**: two tight clusters with one level exactly midway | join the clusters |
| 3 | **two clusters, clean gap** | fail to separate them |
| 4 | **repeated equal highs** (identical prices) | fragment them |
| 5 | **repeated equal lows** | fragment them |
| 6 | **single level** | produce anything but one one-member zone |
| 7 | **outlier**: a tight cluster plus one level `50w` away | absorb the outlier |
| 8 | **overlapping sides**: an `UPPER` and a `LOWER` level at nearly the same price | depends on the membership rule; the rule must be *stated*, not emergent |
| 9 | **sparse**: 2 levels, far apart | merge them |
| 10 | **dense uniform**: 200 levels evenly spaced at `0.1w` | produce one zone of 200 members |
| 11 | **volatility jump**: identical structure, ATR ×10 partway | rewrite earlier boundaries |
| 12 | **gap**: a price gap spanning a zone | claim an intrabar sequence |
| 13 | **scaled**: fixture 3 with every price × 10³ | change the partition |
| 14 | **mirrored**: fixture 3 reflected | change the partition's shape |

---

## 6. Decision rule — fixed before results

### 6.1 Admissibility (a gate, not a score)

A `(scale, geometry)` pair is **production-admissible** only if it passes **all** of:

1. deterministic across processes and hash seeds;
2. **exact** scale invariance at `10⁻³` and `10³`;
3. **exact** mirror symmetry;
4. **zero** `BOUNDARY_REWRITTEN`, `SPLIT`, `MERGED` or `VANISHED` prefix-stability events at every
   cut and every grid value tested;
5. `max_span_over_w ≤ 1` on every real series and every adversarial fixture;
6. no chain-merge on fixture 1 and no bridge-merge on fixture 2;
7. the scale is expressible from data this repository actually holds.

Failing any one is disqualifying. There is no partial credit and no weighting.

### 6.2 Parameter selection — only among admissible pairs

A value may be recommended only if it sits in a **plateau**: at least **five consecutive grid
values** across which every descriptive metric moves **monotonically and without discontinuity**, and
across which the level partition changes slowly (no ARI cliff). The recommended value is the
plateau's **interior**, never its edge.

**If only one isolated value behaves well, that is a refutation, not a discovery**, and the verdict
becomes `INCONCLUSIVE`.

### 6.3 Verdicts

| Verdict | Condition |
|---|---|
| **RESOLVED** | exactly one admissible pair, with a plateau, whose behaviour transfers across assets and timeframe roles |
| **RESOLVED WITH LIMITATIONS** | as above, but transfer is partial or a known failure mode survives; limitations and revisit triggers stated |
| **INCONCLUSIVE** | several admissible pairs and no evidence to choose; or an admissible pair with no plateau |
| **BLOCKED** | no pair is admissible, or a prerequisite is missing |

### 6.4 What would count as insufficient evidence

- No geometry passes §6.1 → **BLOCKED**.
- Two or more pass and metrics cannot separate them → **INCONCLUSIVE**.
- A plateau on 4H that does not exist on 1D or 1W → **RESOLVED WITH LIMITATIONS** at most, scoped to
  the roles where it holds.
- Cross-asset metric spread so wide that one `k` cannot serve the sample → **INCONCLUSIVE**, and R20
  is answered *no*.

---

## 7. What will NOT be measured — and why

**No outcome variable of any kind appears in this study.** Not PnL, win rate, expectancy, profit
factor, Sharpe, forward return after a touch, forward return after a break, breakout success rate,
strategy candidate count, `LONG`/`SHORT` counts, or any current policy output.

This study measures **market representation**, not trading performance. A zone definition that
becomes "true" because it produced better trades is a fitted parameter, and every guarantee in
[ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) and §35 of report 0047 exists to prevent exactly
that. The harness has **no access to a forward return** — not as a discipline, but because the
function that would compute one is not written.

Also not measured, because the engine they need does not exist: acceptance (R3), retest windows
(R4), zone ageing (R5), touch-count information (R6), evidence independence (R15).

---

## 8. Non-regression commitments

This milestone changes no production behaviour. Held at close:

- `src/` and `tests/` unchanged (a research-only directory is not `src/`);
- **81 policy fixtures · 72 `WAIT` · 9 `CANDIDATE`**;
- digest `8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c`;
- `PriceLevel` equality, `classify_comparison` and ADR-0013 §4 untouched **globally**;
- no zone reaches evidence voting, strategy policy, the 1W gate or Scan Memory;
- no risk or capital configuration is created.

---

## 9. Seal

The preregistration is sealed by committing this file before the harness is run. Its
`sha256` at seal time, and the commit that carried it, are recorded in report 0050 §7.
