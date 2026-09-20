# FMITS Capability Registry

**One question, and only this one: *what capabilities does FMITS know about, and what is their
actual status?***

This is **not** a second backlog. [`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) answers
*what are we building next*. This file answers *what exists, what does not, and what was deliberately
set aside and why*. An item can sit here for a year with status `DEFERRED` and never appear on the
board at all — that is the point of the file.

**The rule this document exists to enforce:**

> ## DEFERRED ≠ FORGOTTEN
>
> A capability with status `DEFERRED` or `CANDIDATE` is **not cancelled**. It is recorded with the
> reason it was set aside, what must exist before it is reconsidered, and the event that triggers
> reconsideration. Only an explicit recorded decision may move something to `REJECTED`.

| Field | Value |
|---|---|
| **Last verified against** | **TA Slice 5B — Price Zone Foundation & Product Surface**, [report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md) (baseline `693e162`; `HEAD` = `main` = `origin/main` = remote, tracked tree clean) |
| **Verified on** | 2026-09-18 |
| **Verification method** | live `src/` inspection + `grep` over the repository + accepted ADRs + the full test suite under `-W error` + the policy digest recomputed outside the suite + **rendered `/swing/SYMBOL` pages for four live markets** on a development instance on port 8799 |
| **Authority** | **Status index only.** This file is not an ADR, not a test, and not a specification. Where it disagrees with the live code, **the code is right and this file is stale** — fix this file |

---

## 1. Status vocabulary

These states are materially different and are never collapsed into each other.

| Status | Meaning | The distinction that matters |
|---|---|---|
| `IMPLEMENTED` | Built, tested, and **reachable from a product surface** | The owner can see its output |
| `PARTIAL` | Built, but materially incomplete against approved scope | Something real works; something named is absent |
| `PRODUCT_UNREACHABLE` | Computed correctly and **thrown away before any operator surface** | Not a missing computation — a missing *carriage*. Cheapest class of gap in the repository |
| `DORMANT` | Implemented and tested, with **no production caller at all** | Nothing constructs it. Different from `PRODUCT_UNREACHABLE`, where a producer exists and a consumer does not |
| `PLACEHOLDER` | A named package/module exists with **no math in it** | An honest documented skeleton, not rot |
| `MISSING` | **Approved scope**, not built, no code | Named in an approved source. Absence is a gap |
| `PLANNED` | Sequenced work, not built | Has a place in the sequence (§6) |
| `DEFERRED` | Deliberately postponed. **Still desired** | Carries a reason, a prerequisite and a revisit trigger |
| `CANDIDATE` | **Not approved scope.** Research must justify it before it is built | Absence is not a gap — it was never promised |
| `BLOCKED` | Cannot start until a **named** precursor exists | The precursor is always stated |
| `REJECTED` | Explicitly decided against | Only by a recorded decision. Rare |
| `UNKNOWN` | Not verified in this pass | Never a synonym for "absent" |

---

## 2. Technical Analysis and Swing — the immediate product priority

### 2.1 Measurements and the structural spine — `IMPLEMENTED`

Everything in this table is computed, tested, non-repainting and reaches at least one product surface.

| Capability | Owner package | Status | Reaches | ADR |
|---|---|---|---|---|
| EMA (20/50/200) | `fmis.features.indicators` | `IMPLEMENTED` — **latest value and full aligned history** | `fmits facts`, `/swing/SYMBOL` technical context | [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| RSI (14) | `fmis.features.indicators` | `IMPLEMENTED` — latest value and full aligned history | `fmits facts`, `/swing/SYMBOL` technical context | [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| MACD (12/26/9) | `fmis.features.indicators` | `IMPLEMENTED` — latest value and full aligned history, **structured three-component points** | `fmits facts`, `/swing/SYMBOL` technical context | [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| ATR (14) | `fmis.features.indicators` | `IMPLEMENTED` — latest value and full aligned history | `fmits facts`, `/swing/SYMBOL` technical context | [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| Relative volume (20) | `fmis.features.volume` | `IMPLEMENTED` — latest value and full aligned history | `fmits facts`, `/swing/SYMBOL` technical context | [ADR-0010](../adr/ADR-0010-volume-foundation.md), [ADR-0031](../adr/ADR-0031-feature-series-contract.md) |
| Swing pivots | `fmis.market_structure` (1,775 lines) | `IMPLEMENTED` | `fmits facts` | [ADR-0012](../adr/ADR-0012-market-structure-foundation.md) |
| Swing relationships | `fmis.market_structure` | `IMPLEMENTED` | `fmits facts` | [ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md) |
| HH / HL / LH / LL labels | `fmis.market_structure.labels` | `IMPLEMENTED` | `fmits facts` | [ADR-0014](../adr/ADR-0014-structural-swing-label-foundation.md) |
| Sequence state + history | `fmis.market_structure.sequence_state` | `IMPLEMENTED` | `fmits facts` | [ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md), [ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md) |
| Structural trend | `fmis.structural_trend` (688 lines) | `IMPLEMENTED` | every surface — **gates the swing policy** | [ADR-0017](../adr/ADR-0017-structural-trend-foundation.md) |
| Series identity / context | `fmis.series_context` (515 lines) | `IMPLEMENTED` | internal contract | [ADR-0018](../adr/ADR-0018-series-identity-and-context-contract.md) |
| Price levels | `fmis.market_structure` | `IMPLEMENTED` | `fmits facts`, swing policy | [ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) |
| Level crossings (nine-way) | `fmis.level_crossing` (1,365 lines) | `IMPLEMENTED` — full run carried per role; latest event and latest close breach rendered | `fmits facts`, **`/swing/SYMBOL` technical context** | [ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md), [ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) |
| Break of structure (BOS) | `fmis.structure_break` (832 lines) | `IMPLEMENTED` — **all three roles** above `facts` since TA Slice 5A | swing policy, **`/swing/SYMBOL` technical context** | [ADR-0020](../adr/ADR-0020-break-of-structure-foundation-v1.md), [ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) |
| Change of character (CHoCH) | `fmis.change_of_character` (650 lines) | `IMPLEMENTED` — full run per role; latest change rendered with the break it changed from | **`/swing/SYMBOL` technical context** | [ADR-0021](../adr/ADR-0021-change-of-character-foundation-v1.md), [ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) |
| Structural fact sheet | `fmis.pipeline.structural_facts` | `IMPLEMENTED` | `fmits facts` | [ADR-0022](../adr/ADR-0022-structural-fact-sheet-composition-root.md) |
| Multi-timeframe composition (1W/1D/4H) | `fmis.pipeline.multi_timeframe` | `IMPLEMENTED` | `fmits mtf`, swing policy | [ADR-0023](../adr/ADR-0023-multi-timeframe-composition.md) |
| Confirmation-delay provenance | `fmis.provenance` | `IMPLEMENTED` | fact sheets | [ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md) |
| Market regime (3 dimensions) | `fmis.market_regime` (1,091 lines) | `IMPLEMENTED` — **all three roles reach the product** since TA Slice 5A | `fmits regime`, swing policy, **`/swing/SYMBOL` technical context** | [ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md), [ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) |
| Decision context | `fmis.decision_context` | `IMPLEMENTED` | swing policy | [ADR-0026](../adr/ADR-0026-decision-context-boundary.md) |
| Evidence aggregation + families | `fmis.evidence`, `fmis.setup_evidence` | `PARTIAL` — built for the **SETUP role only**; 1W and 4H indicators are never classified | `fmits evidence`, `/swing/SYMBOL` | [ADR-0008](../adr/ADR-0008-decision-support-evidence-boundary.md), [ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) |
| Swing setup policy | `fmis.swing_setup` | `IMPLEMENTED` | `fmits setup`/`scan`, `/swing` | [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md) |
| Swing Workspace | `fmis.swing_workspace`, `fmis.operator_dashboard` | `IMPLEMENTED` | `/swing`, `/swing/SYMBOL` | — |
| Scan Memory / "What Changed" | `fmis.scan_memory` | `IMPLEMENTED` | `/swing` | [ADR-0027](../adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) |
| Risk & trade-planning foundation | `fmis.risk_policy` → `fmis.position_sizing` | `IMPLEMENTED`, **product-unavailable until capital is declared** — see §5 | `/swing/SYMBOL` risk panel | [ADR-0029](../adr/ADR-0029-money-and-numeric-semantics.md), [ADR-0030](../adr/ADR-0030-risk-policy-declaration-boundary.md) |

### 2.2 What was computed and thrown away — **recovered by TA Slice 5A**

**This was the most important section in the file, and it is now a record of a closed gap.** None of
these was ever a missing computation: FMITS calculated all of them correctly and then discarded them
one layer before the operator. Report 0047 traced every one; the table was re-verified against live
code on 2026-09-16 and **re-verified again on 2026-09-17, after the carriage was built.**

**Where they used to die: `build_setup_inputs` in `src/fmis/swing_setup/compose.py`** — 75 lines that
receive three complete `StructuralFactSheet`s and pass through trend, the context regime's three
dimensions, evidence state, decision-context state, and execution close/levels/breaks. Everything
else in those three sheets stopped there.

**`build_setup_inputs` still passes exactly what it always passed, and `SetupInputs` gained no
field.** The repair was not to widen the strategy's input — [ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md)
records why that was refused — but to compose a **sibling** `MarketTechnicalContext` beside the
assessment, from the objects the composition had already built.

| Fact | Computed at | Survived as, before 5A | Status now | Reaches |
|---|---|---|---|---|
| `FeatureSet` × 3 roles (ema_20/50/200, rsi, atr, macd, relative_volume) | `pipeline/structural_facts.py` | **nothing** on the swing path | `IMPLEMENTED` | `/swing/SYMBOL` technical context, per role, with warm-up stated |
| `structure.crossings` × 3 roles (nine-way classification) | `fmis.level_crossing` | one integer count on `fmits facts` | `IMPLEMENTED` | full run carried per role; the count, the latest event and the latest close breach rendered |
| `structure.changes` (CHoCH) × 3 roles | `fmis.change_of_character` | a `TRANSITIONING` regime state | `IMPLEMENTED` | full run per role; the latest change rendered **with the break it changed from** |
| `nearest_levels` × 3 roles | `pipeline/structural_facts.py` | two rows on `fmits facts` | `IMPLEMENTED` | both sides per role, with each level's price, side and originating swing |
| **context-role `levels`** | `pipeline/structural_facts.py` | **nothing** | `IMPLEMENTED` | carried in full; the count and both nearest levels rendered |
| **setup-role `breaks`** | `pipeline/structural_facts.py` | **nothing** | `IMPLEMENTED` | carried in full for all three roles; the latest rendered |
| setup- and execution-role `MarketRegime` | `swing_setup/compose.py` | one integer: `dimensions_insufficient` | `IMPLEMENTED` | all three dimensions, for all three roles |
| `warming_up` per role | `pipeline/structural_facts.py` | one integer in `ViewAdequacy` | `IMPLEMENTED` | named per role, and each unavailable reading states *which* absence it is |
| `window.last_close` per role | `pipeline/structural_facts.py` | `closed_count` only | `IMPLEMENTED` | the last closed price and the closed-bar count, per role |
| `swings` / `labelled` / `state_history` × 3 roles | `pipeline/structural_facts.py` | counts on `fmits facts` | **`PRODUCT_UNREACHABLE`** — deliberately not recovered | — |

**The one row deliberately left behind.** `swings`, `labelled` and `state_history` are the *inputs*
to facts already carried: the levels are derived from the labelled swings, and the structural trend
is derived from the state history. Carrying them too would have widened the contract for no current
or named future consumer, which is the rule
[ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) applies — *recover information with
a clear consumer*. Revisit trigger: **a deterministic engine that needs pivot-level detail**, which
Price Phases plausibly will.

**Verified 2026-09-17** by `tests/test_technical_context_carriage.py`, which asserts each fact's
survival by **identity, classification, timing and referenced level** rather than by count — a count
is satisfied by a layer that carried the wrong four hundred events.

### 2.3 Dormant and placeholder

| Capability | Status | Evidence | Why | Revisit trigger |
|---|---|---|---|---|
| `AverageVolume` | **`DORMANT`** — and deliberately still so after TA Slice 5A | Exported in `__all__`; nothing in `src/` constructs it. It **gained `compute_series()`** ([ADR-0031](../adr/ADR-0031-feature-series-contract.md)) because it shares `volume_math` with `RelativeVolume` and leaving one class in one module series-capable and its sibling not would have been an arbitrary asymmetry | Never registered by default; `market_analysis.py` says it is "registerable on request" and no caller requests it. **A history is not a promotion** — a test asserts `default_features()` did not grow | Volume-at-event work (§6 step 5) |
| `features/trend/` | **`PLACEHOLDER`** | 18 lines, no math, `__all__ = []` | Tier-2 feature layer designed, never filled | Indicator Context (§6 step 4) |
| `features/momentum/` | **`PLACEHOLDER`** | 17 lines, no math, `__all__ = []` | as above; its `TODO` names "momentum divergence flags (price vs. RSI/MACD)" | Indicator Context / Divergence |
| `features/volatility/` | **`PLACEHOLDER`** | 16 lines, no math, `__all__ = []` | as above | Volatility compression/expansion |
| `features/market_structure/` | **`PLACEHOLDER`** | 20 lines, no math, `__all__ = []` | as above; its `TODO` names "consolidation vs. expansion state" | Price Phases (§6 step 3) |
| `features/support_resistance/` | **`PLACEHOLDER`** | 16 lines, no math, `__all__ = []`. **Still empty after TA Slice 5B, deliberately**: the zone engine is `fmis.price_zones`, a deterministic TA engine over confirmed levels, not a *feature* the `FeatureEngine` computes per bar — and its own name presumes the role the engine refuses to derive | as above | the interaction engine, if a zone reading ever becomes a per-bar feature |
| `features/pattern_detection/` | **`PLACEHOLDER`** | 23 lines, no math, `__all__ = []` | as above | Simple Patterns, after their primitives |

**110 lines total, zero math.** This is the *entire* Tier-2 layer the Feature Engine's own docstring
advertises. It is an honest documented skeleton, not rot — every package names its planned contents.
Whether a new capability belongs in `fmis.features.*` or in a new top-level `fmis.*` package is an
open design question, not settled by the placeholder's existence.

### 2.4 `compute_series()` — **IMPLEMENTED**, and what it unblocked

| Field | Value |
|---|---|
| **Status** | **`IMPLEMENTED`** — `SeriesFeature.compute_series()` returns an aligned `FeatureSeries` for EMA, ATR, RSI, MACD, `RelativeVolume` and `AverageVolume`. `Feature.compute()` is **unchanged**, and a test asserts the latest value equals the final point of the history exactly, per feature |
| **Why it mattered** | Slope, acceleration, ROC and divergence are **not derivable in principle** from a scalar. `PROJECT_SPECIFICATION_V1.md` §4.1 requires *direction, momentum, acceleration or deceleration, slope, divergences* — none of which the previous contract could express |
| **History** | Review item **R5, open since 2026-07-24** ([`ARCHITECTURE_REVIEW_2026-07-24.md`](../ARCHITECTURE_REVIEW_2026-07-24.md)). Closed by TA Slice 5A, **additively**, exactly as the recorded intent always was |
| **Contract** | [ADR-0031](../adr/ADR-0031-feature-series-contract.md). Explicit alignment to the closed-candle index space · warm-up stated and **never backfilled** · *undefined here* distinguished from *not warmed up yet* · provenance and `SeriesIdentity` carried · structured (multi-component) values first-class · prefix stability and no-lookahead tested · one mathematical implementation per indicator |
| **What is now unblocked, and is NOT built** | EMA dynamics · MACD dynamics · RSI dynamics · divergence · volatility compression/expansion · establishment-time ATR for zone width. **Every one of these is still `MISSING`** — the brief for TA Slice 5A explicitly defers all of them, and the existence of the data is not authorisation for the interpretation |
| **Measured cost** | O(n) for the recursive indicators, O(n · lookback) for the volume baseline with lookback a parameter. 2,000 closed candles × seven series-capable features: ~8.5 ms. Linear across 200 / 500 / 1,000 / 2,000 — see `tests/test_feature_series_performance.py` |
| **Not built, deliberately** | An engine-level `compute_series`. `FeatureEngine.compute` threads each feature's **latest** result into the next feature's context, and threading latest values into a historical computation is lookahead produced by the orchestration. No feature declares a dependency today. [ADR-0031](../adr/ADR-0031-feature-series-contract.md) §8 |

### 2.5 Approved TA scope that is not built

The vision addendum's Technical Analysis section names: *EMA · MACD · RSI · Volume · Market Structure ·
**Trendlines** · **Support/Resistance** · **Divergences** · Volatility*. The first five are built. The
bolded three are not.

| Capability | Status | In approved scope? | What is missing | Prerequisite | Revisit trigger |
|---|---|---|---|---|---|
| **Structural price areas** (`fmis.price_zones`) | **`IMPLEMENTED`** | **Yes** — vision addendum | Nothing against V1 scope. Bands are **anchored, frozen and causal**, `k = 0.50` **declared** and stamped, and they reach `/swing/SYMBOL`. **They are not called support or resistance** — see the two rows below, which is why this row is deliberately renamed | [ADR-0033](../adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md) **Accepted** 2026-09-18 · [`PRICE_ZONE_ENGINE_V1.md`](../design/PRICE_ZONE_ENGINE_V1.md) · [report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md) | product evidence that one shared `k` is unsuitable, or `k` shown to affect an outcome → §6 of the ADR must be re-taken as a **measurement** |
| **Support/resistance *roles*** | **`BLOCKED` — on evidence** | **Yes** — vision addendum | The areas exist; **the roles do not, and [report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md) measured why**. A zone has `position` (geometry only) and **no `role` field at all**. **R4 is `NO SUPPORT`** and **R3's persistence state is not attributable to the zone**, so **six of the seven approved labels are underivable** — only `UNTESTED` is, and it means nothing has happened. The owner's approval of the eventual labels (ADR-0033 decision D) stands and cannot be exercised | a derivation that does not exist; see [ADR-0034](../adr/ADR-0034-zone-interaction-evidence-boundary.md) | **not scheduled** — deferred, not parked |
| Zone interactions (touch/hold/break/reclaim/retest) | **`BLOCKED` — on evidence** | Yes (implied) | no interaction vocabulary exists. **R3/R4 are now answered and the answer is mostly no** ([report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md), [ADR-0034](../adr/ADR-0034-zone-interaction-evidence-boundary.md) `Proposed`): **no `RETEST`** (real and placebo return hazards are indistinguishable, 0.96–1.02) and **no `ACCEPTANCE`** (a placebo band separates as well as a real zone). Admissible instead: `EXIT` · `TRAVERSE` · `RETURN_TO_ZONE_AFTER_OUTSIDE_STATE` · `CLOSED_BEYOND_FOR_N_BARS`. **A `CLOSE_BREACH` is not a breakout** | a null-controlled result that does not exist | **not scheduled** |
| Zone role (`HELD_FROM_ABOVE`, `BROKEN_UPWARD`, `ROLE_FLIPPED`, …) | **`BLOCKED`** | Yes | **0047 D2 is RESOLVED** (report 0050) and the vocabulary is **deliberately not in the code** — a role vocabulary present in the source is one something will populate, so it lives in ADR-0033 §8 alone. Vocabulary fixed — `UNTESTED` · `HELD_FROM_ABOVE` · `HELD_FROM_BELOW` · `BROKEN_UPWARD` · `BROKEN_DOWNWARD` · `ROLE_FLIPPED` · `INDETERMINATE` — with `position` a **separate** field. Derivation still needs the interaction engine. **Measured**: 22 % of zones above the close on 1W have *no interaction history at all*; **39 % (1W) / 50 % (1D)** have had price close on **both** sides, so the position rule is **not well-defined over time** | zone interactions | after Slice 5B |
| **Trendlines** | `MISSING` | **Yes** — vision addendum | `grep -ri trendline src/` → **0 files** | Phases first (anchor scoping: 10,153 unconstrained candidates per side per view at 500 bars). **Anchor policy is an open research question — see §7** | Trend Geometry (§6 step 8) |
| Channels | `MISSING` | Yes (implied) | none | trendlines | Trend Geometry |
| **Divergences** | `MISSING` | **Yes** — vision addendum and `SPEC` §4.1 | No price/oscillator divergence engine exists. The `divergence` hits under `src/` remain unrelated senses (`exit_divergence` on trade plans, one `TODO`, and the technical-context panel's own sentence **denying** that any is computed) | `compute_series()` — **satisfied** (§2.4). Alignment policy is still open: disposition §H | Divergence (§6 step 6) |
| Volatility compression / expansion | `MISSING` | Yes | none | `compute_series()` — **satisfied** (§2.4) | §6 step 5 |
| Breakout / acceptance / rejection / retest | `MISSING` — **and three of the four are now rejected on evidence** | Yes (implied by S/R) | `close > level` is explicitly **not** an acceptable definition, and **a `CLOSE_BREACH` is not a breakout**. [Report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md) rejects **acceptance** (not attributable to the zone) and **retest** (`NO SUPPORT`); **breakout** was never measured; **rejection** needs R4 | a null-controlled result that does not exist | **not scheduled** |
| Impulse / retracement / range / consolidation phases | `MISSING` | Yes | `grep -ri consolidation src/` returns docstrings **denying** the sense (*"`CONTRACTED` is not consolidation"*) plus one `TODO`. Deliberately not built | zones — **satisfied** | **Price Phases** (§6 step 3) |
| EMA dynamics (slope, separation, stack) | `MISSING` | Yes — `SPEC` §4.1 | Derivable now and **deliberately not derived**: TA Slice 5A's brief defers every indicator interpretation | `compute_series()` — **satisfied** (§2.4) | Indicator Context |
| MACD dynamics (histogram direction, ROC) | `MISSING` | Yes — `SPEC` §4.2 names this explicitly | as above. The three components are now available **per bar**, and none is compared with its predecessor anywhere | `compute_series()` — **satisfied** (§2.4) | Indicator Context |
| RSI dynamics (slope, location in context) | `MISSING` | Yes — `SPEC` §4.1 | as above | `compute_series()` — **satisfied** (§2.4) | Indicator Context |
| Volume at event | `MISSING` | Yes | `RelativeVolume` now has a history and structural events now carry their bar index, so the join is **expressible** — and is not made anywhere | zones/phases | §6 step 5 |
| Chart patterns (generic) | `DEFERRED` | Partly | **No generic pattern framework before a second real pattern demonstrates shared abstraction.** Build primitives first | phases + geometry | after §6 step 9 |
| Bull / bear flag | `DEFERRED` | Yes (pattern detection) | decomposes into impulse + consolidation + break — build the primitives, not the pattern | phases | §6 step 9 |
| Double top / bottom | `DEFERRED` | Yes | decomposes into two zone interactions + a structural break | zones | §6 step 10 |
| Rectangles | `REJECTED as a pattern` | — | **A rectangle is a range**, and should be represented by the range/phase primitive rather than duplicated as a separate pattern | — | — |
| Triple / V / rounded tops | `REJECTED` | No | 0047: a triple top is a touch count and a V is a pivot — both already expressible | — | — |
| Head & shoulders, symmetrical triangles, wedges | `DEFERRED` | Partly | high subjectivity, low marginal information over the primitives | phases + geometry | re-ask **after** the owner has used §6 steps 0–7 in practice |

### 2.6 Market opportunity — the gap that triggered this work

| Capability | Status | Notes |
|---|---|---|
| Market Opportunity state (e.g. `WATCH_LONG` / `WATCH_SHORT`) | **`MISSING`** / `PLANNED` | The operator sees too many undifferentiated `WAIT`s and cannot tell *nothing interesting* from *a directional opportunity is developing but unconfirmed*. **Must remain architecturally separate from strategy** — see §7 A |
| `MissingConfirmation` (*what market event has not happened yet*) | **`MISSING`** / `PLANNED` | **Not the same thing as a policy `Blocker`** (*why did the strategy stop*). See §7 B |
| Policy `Blocker` | `IMPLEMENTED` | `fmis.swing_setup` names the blocking condition on every `WAIT` |
| Naming a side outside `fmis.swing_setup` | `BLOCKED` | [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md) makes `fmis.swing_setup` the only package permitted to hold `LONG`/`SHORT`. An opportunity state that names a side is an **ADR decision**, not an implementation detail |

### 2.7 Not approved scope — research first

Both are recorded here **precisely so that a future agent does not silently treat them as either
approved or forbidden.** Verified 2026-09-16: `Fibonacci` and `Elliott` each appear **0 times** in
`PROJECT_SPECIFICATION_V1.md` and **0 times** in `PROJECT_VISION_ADDENDUM_V1.md`, and in **0 files**
under `src/`.

#### Fibonacci

| Field | Value |
|---|---|
| **Status** | **`CANDIDATE` / RESEARCH FIRST** |
| **Original approved scope** | **No.** Named in no approved source |
| **Still desired?** | Undecided. Approved as a *research question*, not as a feature |
| **Role if later justified** | Optional **contextual confluence** only |
| **It may never become** | a mandatory gate · a veto · a direction source by itself · a confidence multiplier or vote · a substitute for independently derived market structure |
| **Prerequisites** | zones + phases (an anchor needs a structurally meaningful swing to measure from) + anchor-selection research |
| **Revisit trigger** | **a research design is approved** — not an implementation request |
| **Authority** | [0047 review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §I; report 0047 §29 |

#### Elliott Wave

| Field | Value |
|---|---|
| **Status** | **`DEFERRED` / UNSCHEDULED / hypothesis-level only** |
| **Original approved scope** | **No.** Named in no approved source |
| **Deterministic core?** | **No.** It must never sit in deterministic L4/L5 market truth |
| **Current schedule** | **None** |
| **Possible future home** | a hypothesis / interpretation layer able to represent **multiple alternative counts, invalidation levels, and hypotheses that change as the market develops** |
| **It may never become** | a mandatory gate · a veto · deterministic market truth · a vote |
| **The ground for deferral** | A count **re-labels as the market develops**, which is structurally incompatible with the prefix-stability contract every L4/L5 engine in this repository holds. That is a stronger and more precise reason than "it changes as the market evolves" |
| **What is NOT recorded** | *"Elliott can never exist."* That is **not** the decision. A hypothesis layer that represents changing, invalidatable alternatives is a legitimate future design |
| **Revisit trigger** | only after the core TA / opportunity architecture is mature **and** there is a concrete product or research reason |
| **Authority** | [0047 review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §J; report 0047 §30 |

---

## 3. Evidence independence — a measured constraint, not an opinion

| Capability | Status | Detail |
|---|---|---|
| Evidence family taxonomy | `IMPLEMENTED` | [ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) |
| Family independence **in practice** | **`PARTIAL` — and this is a known defect of the current evidence set** | No two of the policy's three directional families are family-disjoint. `standing_family_note()` fires on **every** page. Milestone AW measured **75–79 % agreement** between families |
| Zone / location evidence independence | **`INDEPENDENCE NOT ESTABLISHED`** | Zones derive from the same pivots as structural trend. Until research establishes otherwise, describe zone evidence as a *"new / potentially more orthogonal evidence family"* — **never** as proven independent. See §7 D |

**The consequence that must survive every future session:**

> **More indicators add no independence — a new *family* does.**
> Adding EMA slope, MACD ROC and RSI slope does **not** create independent confirmation; they are
> largely the same reading three times. This does **not** mean EMA/MACD/RSI context is useless —
> it is valuable contextual market information. The point is narrower and exact:
> **contextual usefulness ≠ independent evidence family.**

---

## 4. The wider FMITS domains

FMITS is **not merely a trading bot**. It is a personal Financial Market Intelligence operating
environment. Swing Trading / Technical Market Intelligence is the **immediate priority**, not the
whole project. This table exists so that narrowing FMITS to swing trading is visibly a change of
scope rather than a drift.

| Domain | Status | Owner package(s) | Notes |
|---|---|---|---|
| Global market pulse | `IMPLEMENTED` | `fmis.market_pulse` | `fmits pulse`, `/markets` |
| Macro & cross-asset context | `PARTIAL` | `fmis.macro`, `fmis.providers.fred` | `fmits macro`. First non-crypto data source |
| Portfolio intelligence | `IMPLEMENTED` (engine) / `PARTIAL` (product) | `fmis.portfolio`, `fmis.portfolio_risk`, `fmis.valuation` | `fmits portfolio`, `/portfolio`. Cross-book aggregation not built |
| Risk | `IMPLEMENTED`, product-unavailable until capital declared | `fmis.risk`, `fmis.risk_policy`, `fmis.position_sizing` | See §5 |
| Trade capture & journal | `IMPLEMENTED` | `fmis.trade_capture`, `fmis.journal`, `fmis.plan`, `fmis.ledger` | `fmits trade …` |
| Paper trading | `IMPLEMENTED` | `fmis.paper`, `fmis.trade_lifecycle` | `fmits simulate`, `/paper` |
| Statistics & performance | `IMPLEMENTED` | `fmis.statistics` | `fmits statistics`/`performance`/`expectancy`/`equity`, `/performance` |
| Backtesting (swing policy replay) | `PARTIAL` | `fmis.swing_setup.backtest_*`, `fmis.swing_lab` | `fmits backtest`, `/lab`. **No fees, slippage, spread or execution delay modelled** — printed on every run |
| Research harness & design | `IMPLEMENTED` | `fmis.research_design`, `fmis.paired_dependence` | `fmits research`, `/validation` |
| Memory & decision archive | `IMPLEMENTED` | `fmis.archive`, `fmis.analysis_record` | `fmits archive …` |
| Operator dashboard | `IMPLEMENTED` | `fmis.operator_dashboard` | 10 pages + dynamic `/swing/SYMBOL` |
| **Long-term investing** | `MISSING` | — | Approved scope (`SPEC` §9). **A separate discipline and a separate book from Swing** — see §5 |
| **Day trading** | `DEFERRED` | — | `SPEC` §11. Beyond the autonomy boundary; needs its own vision decision |
| News intelligence | `BLOCKED` | — | Precursor: **availability-time model** ([ADR-0003](../adr/ADR-0003-availability-time-boundary.md)) |
| Geopolitics | `BLOCKED` | — | Precursor: availability-time model |
| Fundamental research | `BLOCKED` | — | Precursor: availability-time model |
| On-chain intelligence | `MISSING` | — | Approved scope (`SPEC` §13). Needs an adapter |
| Derivatives intelligence | `MISSING` | — | Approved scope (`SPEC` §14). Needs an adapter |
| Flows | `MISSING` | — | Needs an adapter |
| China intelligence | `MISSING` | — | Approved scope (`SPEC` §15, vision addendum). Gated by the multi-asset data platform |
| IPO / special opportunities | `MISSING` | — | Approved scope (vision addendum) |
| Daily Brief | `MISSING` | — | Approved scope (vision addendum) |
| Opportunity Scanner (ranking) | `DEFERRED` | — | **Ranking by *readiness* is refused permanently** — a readiness state describes the analysis, not the instrument. **Opportunity ranking is a different capability and remains approved roadmap scope**, requiring an explicit, deterministic, testable, backtested policy of its own |
| Alerts / Telegram / notifications / export | `MISSING` | — | Approved scope (vision addendum). Scheduling owns no architecture layer yet and needs one before it gets code |
| Shadow mode | `MISSING` | — | Ladder step after paper trading |
| Controlled execution | `DEFERRED` | — | Requires an explicit human decision. **No automated trading system may ever have withdrawal permissions** |
| Economic calendar | `BLOCKED` | — | Precursor: availability-time model |

---

## 5. Risk and capital — the current owner decision

| Item | Current state |
|---|---|
| **Per-trade ceiling** | **2 % of portfolio risk — a HARD MAXIMUM, never a default or a target.** Structural in `fmis.risk_policy`: a declaration above 2 % **cannot be constructed** |
| **Is it a default?** | **No.** `budget_from` leaves `default_below_ceiling` `Absent`. An undeclared fraction resolves to **no fraction**, not to the ceiling |
| **Capital** | **Declared by the owner, never inferred.** Read from `~/.fmits/risk_policy.json`, marked `ASSERTED`. Keys are a closed set, so a credential is refused *by name* |
| **Is capital declared today?** | **No.** `~/.fmits/risk_policy.json` **does not exist and must not be created by an agent.** Declaring capital is the owner's decision |
| **Discussed figure** | The owner has discussed possibly beginning Swing with approximately 500 USDT. **This is NOT an active capital declaration and must never be written into configuration** |
| **Consequence** | Risk sizing is **product-unavailable** until capital is declared. Every planning panel states the absence and prints the file to write. **Market analysis and opportunity detection must function without configured capital** |
| **Book separation** | **Swing Trading capital is a separate capital domain from long-term investing and from future day trading.** Cross-book portfolio intelligence may later *observe* aggregate exposure, correlation and concentration — but **one book must never size another** |

---

## 6. Current implementation sequence

**Planning state, not authorization.** Each step needs its own implementation brief. The sequence is
deliberately product-first and may be revised when live implementation reveals new facts.

```
MEMORY GATE                                      ← DONE (report 0048)
    ↓
ChatGPT + Dovydas review
    ↓
0.  TA Slice 5A — Recover Technical Context      ← DONE (report 0049)
1.  TA Slice 5B — Price Zone Foundation          ← DONE (report 0051)
1b. Zone Interactions      ← BLOCKED on evidence (report 0052 / ADR-0034), not scheduled
2.  Price Phases
3.  Market Opportunity
4.  Indicator Context
5.  Volume & volatility at events
6.  Divergence
7.  Trend Geometry
─────────── re-evaluate here, with real usage ───────────
8.  Simple Patterns (flags, then double tops/bottoms)
9.  later research-dependent capabilities
──  Fibonacci: only if its research supports it
──  Elliott: not scheduled
```

**The re-evaluation point is deliberate.** Whether steps 8+ are worth building should be decided
**after the owner has used steps 0–7**, not now.

### TA Slice 5A — Recover Technical Context *(**DONE**, 2026-09-17 — [report 0049](../../reports/0049_2026-09-17_TECHNICAL_ANALYSIS_SLICE_5A.md))*

**Purpose:** stop throwing away already-computed technical information, and establish the historical
series access later engines need. Both delivered.

| In scope | Delivered as |
|---|---|
| Widen the `build_setup_inputs` information-loss seam | **Not widened — sidestepped.** `SetupInputs` gained no field; a sibling `MarketTechnicalContext` is composed beside the assessment ([ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md)) |
| Preserve relevant per-role structured facts | Three complete per-role views, canonical objects carried by reference |
| Carry crossings / CHoCH / levels / nearest levels / regimes / `FeatureSet`s | All six, all three roles — §2.2 |
| Additive `compute_series()` protocol capability | [ADR-0031](../adr/ADR-0031-feature-series-contract.md), six features — §2.4 |
| A small **real product consumer** | The **technical context panel** on `/swing/SYMBOL` |

| Explicitly out of scope, and stayed out |
|---|
| Any Swing **policy** change — the 81-fixture digest is byte-identical |
| Invented TA thresholds — none exists anywhere in the slice |
| Zones · `WATCH` / opportunity states · any risk or capital change |
| Every indicator interpretation `compute_series()` now makes easy (§2.5) |

**Stop condition met**, and the slice stopped there. It did **not** continue into 5B.

### TA Slice 5B — Price Zone Foundation & Product Surface *(**DONE**, 2026-09-18 — [report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md))*

**Purpose:** make FMITS understand repeated structural **areas** rather than only isolated exact
levels, and put them where the owner can read them.

| In scope | Delivered as |
|---|---|
| The deterministic zone foundation ADR-0033 decided | `fmis.price_zones` — `ZoneWidthPolicy` · `ZoneMember` · `PriceZone` · `PriceZoneSet` · `ZonePricePosition`, anchored construction with frozen bands |
| Per-role computation for 1W / 1D / 4H over the existing pipeline | `StructureFacts.zones`, built in `build_structural_facts` beside the levels it groups; **no second market-data path** |
| Carriage to the operator | `TechnicalContextView.zones`, by reference, plus limitation **TC-6** ([ADR-0032](../adr/ADR-0032-market-technical-context-carriage.md) unchanged) |
| A real product consumer | The **price zones panel** on `/swing/SYMBOL` |
| `k` declared, versioned and stamped | `ZONE_WIDTH_POLICY_V1`, `k = 0.50`, **one policy for all three roles**, admissible region **enforced** |

| Explicitly out of scope, and stayed out |
|---|
| `ZoneInteraction`, `ZoneReading`, and the role vocabulary **even in code** |
| Breakout · acceptance · reclaim · retest · false breakout · rejection |
| Any role derived from position, and the words support / resistance outside a denial |
| Zone strength, quality, score, rank, confidence or direction |
| Any Swing **policy** change — the 81-fixture digest is byte-identical |
| Risk, capital, Scan Memory, evidence voting, `WATCH` / opportunity |

**Stop condition met**, and the slice stopped there.

### The slices after it, in one line each

- **Zone Interactions** *(**blocked on evidence**, and no longer "next")*. What price has actually
  done at an area, and the roles that follow from it. **R3 and R4 have now been measured**
  ([report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md),
  [ADR-0034](../adr/ADR-0034-zone-interaction-evidence-boundary.md) `Proposed`) and the answer
  forecloses most of this slice rather than unblocking it: **retest is `NO SUPPORT`** — a return to
  a real zone is no likelier than a return to a displaced band no level anchored — and the
  persistence state R3 *does* identify is **matched exactly by a placebo band**, so it is not a
  fact about the zone and may not be called acceptance. **The question was never "how many closes?"
  — that phrasing was a paraphrase, and report 0047 §45 asked whether the state is distinguishable
  and whether the return is attributable.** **A `CLOSE_BREACH` is not a breakout.** The foundation it needs is built: bands are frozen and causal, every member
  keeps its exact `PriceLevel` and its confirmation window, and the full crossing run is already
  carried per role.
- **Price Phases.** Impulse / retracement / consolidation / range / compression–expansion primitives
  **with explicit scale semantics**.
- **Market Opportunity.** Distinguish *nothing interesting* from *a developing directional
  opportunity* **without weakening strategy policy**. Internal vocabulary and any ADR change are
  designed then, not now.
- **Indicator Context.** EMA geometry, MACD dynamics, RSI dynamics, volume and volatility context —
  **not treated as independent votes merely because there are more indicators** (§3).

---

## 7. Open architectural questions — do NOT freeze these prematurely

These are recorded because a future agent could easily "resolve" one by accident and lock the
architecture into a choice nobody made. Full reasoning: the
[0047 review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md).

| # | Question | What is decided | What is **not** decided |
|---|---|---|---|
| **A** | Opportunity vs Strategy | They are **conceptually separate**. `Opportunity: WATCH LONG` + `Strategy: WAIT` must remain logically possible, as must `WATCH LONG` + `CANDIDATE`, and `NONE` + `WAIT` | Internal vocabulary; package ownership; whether opportunity may name a side (ADR-0028) |
| **B** | `MissingConfirmation` vs policy `Blocker` | They are **different questions** and must not be conflated. *"What market event has not happened yet"* ≠ *"why did the strategy stop"* | The type, where it lives, how it renders |
| **C** | `compute_series()` vs ATR-based zone width | **Closed.** `compute_series()` landed in TA Slice 5A ([ADR-0031](../adr/ADR-0031-feature-series-contract.md)) before any zone engine, and TA Slice 5B then used it: **establishment-time ATR** was chosen on measurement (983,916 illegal prefix events for the alternative), the owner declared `k = 0.50`, and `ZoneWidthPolicy` stamps both on every zone | Whether `k = 0.50` is a *good* value. It is **declared, not measured**, and report 0050 found every descriptive metric monotone in it |
| **D** | Zone evidence independence | **NOT ESTABLISHED.** Describe as *"new / potentially more orthogonal"* | Whether it is actually independent — needs empirical research |
| **E** | Support / resistance terminology | **Owner-approved, and deliberately unused.** Role is derived from **interaction history, never from position relative to price**. `below price = support` is **forbidden** — and [report 0050](../../reports/0050_2026-09-18_PRICE_ZONE_SEMANTICS_RESEARCH_GATE.md) §25 measured the cost: **39 % (1W) / 50 % (1D)** of zones have had price close on **both** sides since establishment, so the position rule is **not well-defined over time**, not merely sometimes wrong | **Settled by ADR-0033**: user-facing *"Support zone"* / *"Resistance zone"* is permitted **only** as a label over a derived role (`HELD_FROM_ABOVE` / `HELD_FROM_BELOW`), only once the interaction engine exists, and **never for an `UNTESTED` zone**. The three guards stay in force until then |
| **F** | Price phase segmentation | Phases before trendlines | **Not decided:** whether one exhaustive non-overlapping phase per candle is the model. Markets may contain nested / scale-dependent structure. Segmentation scale, overlap/nesting, and timeframe identity are all open |
| **G** | Trendline anchors | Phases before trendlines (anchor scoping) | **Not decided, and explicitly NOT approved:** *"anchors must always lie inside exactly one phase"*. Trendlines may legitimately connect structurally meaningful pivots **across** phases |
| **H** | Divergence alignment | Exact price-pivot indexing is a safe v1. Arbitrary ±N-bar cherry-picking is **never** acceptable | A later, explicitly researched oscillator-pivot alignment policy is **not** ruled out |
| **L** | Pattern order | Primitives before patterns: `swings → zones/interactions → phases → geometry → patterns` | Which patterns ultimately earn their place |

---

## 8. How to maintain this file

**Event-driven, not per-commit.** Update a row when a capability's **status** changes — not when its
implementation is merely edited.

1. Change the status and the **Last verified** header.
2. Cite **live evidence** (a path, a `grep` result, a test), never a plan or a report's intention.
3. If a capability becomes `DEFERRED`, you **must** record: why · whether it remains desired · what
   must exist first · what triggers reconsideration.
4. Never move an item to `REJECTED` without an explicit recorded decision.
5. Never let a status claim outlive its verification — if you did not check, write `UNKNOWN`.

**Related durable memory:** [`START_HERE_FOR_AI.md`](START_HERE_FOR_AI.md) (entry point) ·
[`CURRENT_STATE.md`](CURRENT_STATE.md) (current operational state) ·
[`daily/`](daily/) (session handoffs) · [`../adr/README.md`](../adr/README.md) (binding decisions) ·
[`../../FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) (the board).
