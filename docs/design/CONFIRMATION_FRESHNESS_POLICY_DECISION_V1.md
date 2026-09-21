# Confirmation Freshness Policy Decision V1

**Milestone:** BB
**Status:** Decision analysis complete — evidence assessment only, no code changes, no policy change
**Date:** 2026-08-11
**Model:** Claude Opus 5 (the milestone brief nominated Claude Opus 4.1; the model that actually
produced this document is recorded here rather than the one requested, because a provenance header
that is not the truth is worth nothing to a committee)
**Repository state:** `main`. Working tree unchanged by this milestone under `src/`, `tests/`,
`docs/adr/`, `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`, `CURRENT_STATE.md`,
`reports/`. This file is the only artifact.
**Type:** Decision-analysis record. Produces no contract, no ADR, no backlog entry, no changelog
entry, no threshold, no filter, no policy proposal, and **no recommendation to implement anything.**

---

## Table of contents

- [0. What this document is, and is not](#0-what-this-document-is-and-is-not)
- [1. The decision under consideration, stated precisely](#1-the-decision-under-consideration-stated-precisely)
- [2. Evidence base, and the independent audit performed before assessing it](#2-evidence-base-and-the-independent-audit-performed-before-assessing-it)
- [3. RQ1 — the strongest defensible claim BA proves](#3-rq1--the-strongest-defensible-claim-ba-proves)
- [4. RQ2 — what BA does not prove](#4-rq2--what-ba-does-not-prove)
- [5. RQ3 — adopting `confirmation_age <= 2`: measured vs assumed](#5-rq3--adopting-confirmation_age--2-measured-vs-assumed)
- [6. RQ4 — evidence that adoption harms](#6-rq4--evidence-that-adoption-harms)
- [7. RQ5 — is BA measuring late entries rather than freshness?](#7-rq5--is-ba-measuring-late-entries-rather-than-freshness)
- [8. RQ6 — confounding, variable by variable](#8-rq6--confounding-variable-by-variable)
- [9. RQ7 — how much uncertainty remains, quantified](#9-rq7--how-much-uncertainty-remains-quantified)
- [10. RQ8 — the vote](#10-rq8--the-vote)
- [11. RQ9 — what the existing dataset can and cannot still answer](#11-rq9--what-the-existing-dataset-can-and-cannot-still-answer)
- [12. RQ10 — the smallest missing evidence](#12-rq10--the-smallest-missing-evidence)
- [13. Red team against this document](#13-red-team-against-this-document)
- [14. Errata found in the evidence base](#14-errata-found-in-the-evidence-base)
- [Appendix A — arithmetic, reproducible by hand](#appendix-a--arithmetic-reproducible-by-hand)

---

## 0. What this document is, and is not

Milestone BA (`docs/design/CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md`) measured a
fresh-vs-stale confirmation-age difference in 133 historical resolved outcomes and deliberately
stopped before making any product decision. This document does the one thing BA refused to do and
the one thing the brief for this milestone asks for: **decide whether the evidence already collected
is sufficient to justify changing production policy.**

It is not a new measurement. Every figure below is either quoted from AV, AW, AX, AY, AZ or BA, or is
arithmetic over figures those documents published, or is a fact read directly out of production code
under `src/`. No market data was fetched. No extraction script was run. Where this document computes
something the evidence base did not — a standardized rate difference, a z-statistic, a
window-length derivation — the inputs are named, the arithmetic is shown in Appendix A, and it is
labelled as arithmetic over published counts rather than as a new observation.

**No recommendation.** This document contains no sentence saying that
`CONFIRMATION_LOOKBACK_BARS`, or any other constant, should change; that an experimental branch
should be built; or that any milestone should follow. §10 delivers the committee verdict the brief
requires — an assessment of evidentiary sufficiency, which is what was asked for, and which is not
the same thing as a proposal to act. §12 names evidence that does not exist. Naming absent evidence
is not the same as scheduling work to produce it, and nothing in §12 should be read as a plan.

**Standard of proof applied.** The brief instructs: *assume production capital depends on this
decision.* This document therefore applies the standard a quantitative investment committee applies
to a proposed change in a live trading rule, not the standard a research note applies to an
interesting observation. Those two standards differ, and most of what follows is an account of the
gap between them.

---

## 1. The decision under consideration, stated precisely

The imprecision of "adopt `confirmation_age <= 2`" matters, because the candidate decisions differ in
what the evidence can say about them. Read against production code, the phrase can mean at least
three materially different changes:

| # | Reading | Mechanism in code | What BA measured about it |
|---|---|---|---|
| **D1** | Tighten the confirmation-staleness gate from 10 bars to 2 | `CONFIRMATION_LOOKBACK_BARS = 10` → `2` (`policy.py:78`), which flips `break_is_stale` at `policy.py:349` and therefore whether a candidate reaches `CONFIRMED` or stays `CANDIDATE` (`policy.py:394`) | **Nothing directly.** BA never replayed the policy under a changed constant (§5.2) |
| **D2** | Keep the policy and suppress display/ranking of confirmations older than 2 bars at a product surface | No production mechanism exists today; `confirmation_break_age_bars` is not persisted on `HistoricalObservation` at all | Nothing |
| **D3** | Keep the policy and treat age as one input to a future scoring or probability layer | No such layer exists; `probability` is `NOT_CALIBRATED` (`policy.py:483`) | Nothing |

**This document assesses D1**, because D1 is the reading that changes which trades the owner would
take and therefore the reading on which capital depends. Where a conclusion would differ for D2 or
D3, that is said explicitly.

Two properties of D1 read out of `policy.py` are load-bearing for everything below, and neither is
stated in BA:

1. **A tighter cap does not delete setups; it defers them.** When `break_is_stale` is true the
   assessment becomes `CANDIDATE`, not `WAIT` (`policy.py:410`). The candidate survives, keeps
   watching a level, and `_latest_matching_break` (`policy.py:162-177`) will select a *new* break on
   the confirming side if one occurs later — at which point `break_age` resets toward 0 and the setup
   can confirm, at a different bar, a different reference price, a different stop, a different target
   and a different RR. A cap therefore reshapes the confirmed population; it does not filter it.
2. **Confirmation age is exactly the number of execution bars between the confirming break's bar and
   the entry bar.** `break_age = execution_closed_count - 1 - matching_break.index`
   (`policy.py:344-348`), and the entry reference is the execution close at the confirming bar
   (`policy.py:358`, limitation AV-4). §7 returns to what that identity means for interpretation.

---

## 2. Evidence base, and the independent audit performed before assessing it

### 2.1 Documents relied on

| Milestone | Document | What this document takes from it |
|---|---|---|
| AV | `docs/design/SWING_SETUP_BACKTEST_V1.md`, `reports/0011` | The harness, the window, `BACKTEST_LIMITATIONS` AV-1…AV-9, the 400-day/EMA-50 rationale |
| AW | `docs/design/EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md` | Family dependence (κ = 0.02 CTX↔SETUP, 0.10 CTX↔EVID, 0.41 SETUP↔EVID) |
| AX | `docs/design/EVIDENCE_CALIBRATION_RESEARCH_V1.md` | The 177→146→133 funnel, per-field calibration, the 31 confirmed-without-geometry rows |
| AY | `docs/design/EDGE_SEGMENTATION_RESEARCH_V1.md` | Bucket edges, marginal win rates, correlations, the exact-age table, mean realized R = +0.240 |
| AZ | `docs/design/FAILURE_ATTRIBUTION_RESEARCH_V1.md` | The 3-level decision tree (the only published age-3–10 cut), the nine categories, the 0/24 leaf |
| BA | `docs/design/CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md` | Every fresh/stale table assessed here |
| — | `src/fmis/**` | `policy.py`, `backtest_harness.py`, `backtest_identity.py`, `backtest_outcomes.py`, `backtest_replay.py`, `market_regime/classify.py`, `features/indicators/ema.py`, `pipeline/regime.py` |

### 2.2 Arithmetic audit: BA reconciles exactly against AY and AZ

A committee should not assess a finding it has not first checked. Before any judgement below, BA's
published cells were reconciled against AY's and AZ's independently extracted numbers. **BA's tables
are internally consistent and cross-consistent with both, at the integer level.** Specifically:

- Every BA fresh/stale table sums to 40 fresh (26 wins) and 53 stale (20 wins): the RR table (§6),
  stop table (§7), target table (§8), symbol table (§9), direction table (§12) and temporal table
  (§11) each independently recover both marginals. Six independent recoveries, six matches.
- BA's fresh RR column (16/13, 6/5, 4/1, 5/4, 9/3) is **identical** to AZ §6's `fresh` subtree
  (`policy` tree, ages 0–2), row for row.
- Subtracting BA's stale (6–10) RR column from AZ §6's stale (3–10) RR subtree yields the middle
  bucket (ages 3–5) exactly: n = 19, 4, 5, 2, 10 (total 40) with 11, 1, 3, 1, 0 wins (total 16) —
  which is precisely BA §4's independently published MID row (n = 40, 16 wins, 40.0%). Two
  differently constructed documents, three age bands, one consistent partition.
- BA's own §2.2 reconciliation against AY/AX/AW's counts (21,680 / 21,102 / 401 / 177 / 146 / 62 /
  71 / 5 / 8) and its four reproduced correlation coefficients are accepted as stated; nothing in
  this audit contradicts them.
- Every LOSO row in BA §10 recovers from the §9 per-symbol table by subtraction (Appendix A.1).
- Every effect size in BA §5 is arithmetically correct (RR 1.722, OR 3.064).

**Conclusion of the audit: BA's numbers are sound. Nothing below disputes a single count.** Every
criticism in this document is about what those correct numbers can and cannot support — which is the
only kind of criticism that matters once the arithmetic checks out.

### 2.3 The one structural fact that changes how the whole evidence base reads

BA §11 presents a chronological split as temporal robustness. Its own date ranges show something it
does not comment on: **every resolved outcome in the entire AV–BA series was confirmed between
2026-06-22 and 2026-08-03 — a 43-day span, not the 400-day window every document names.**

This is not an artifact of BA's extraction. It is forced by production code, and the derivation is
exact:

1. A directional candidate requires `context_regime_structure is StructureState.TRENDING`; otherwise
   `evaluate_setup` returns `WAIT` before any vote is tallied (`policy.py:310-318`).
2. `StructureState.TRENDING` requires **both** the swing-structure family and the moving-average
   family to be readable and to agree; one readable family alone returns `INSUFFICIENT`
   (`market_regime/classify.py:200-213`).
3. The moving-average family needs `close`, `ema_fast` and `ema_slow`, else it is `UNAVAILABLE`
   (`market_regime/classify.py:123-131`). At the context role those are EMA(20) and **EMA(50)**
   (`pipeline/regime.py:90-91`).
4. `ExponentialMovingAverage` declares `warmup_bars = period` and yields no value until that many
   closed candles exist (`features/indicators/ema.py:82`).
5. `fetch_historical_dataset` fetches exactly `[start_time, end_time]` with no warm-up prefix
   (`backtest_replay.py:230-240`). Report 0011 §8 records the resulting boundary: **57 weekly
   candles, first 2025-07-07.**
6. The 50th weekly candle therefore opens 2025-07-07 + 49 weeks = **2026-06-15** and closes
   **2026-06-22**. Before that instant no context-role EMA(50) exists, so no `CONFIRMED` setup can
   exist anywhere in the ten symbols.

Step 6 lands on the same calendar day as the first `confirmed_at` in BA §11's own table. AV's
implementation report independently corroborates the mechanism from the other direction: a 180-day
run "produced **zero** `CONFIRMED` results, traced to exactly this cause" (report 0011 §31, P2).

The consequences are severe and run through every question below:

- **The usable decision window is ~6 weeks, not 400 days.** The first ~350 days of the window are
  EMA warm-up during which the policy is structurally incapable of producing an outcome. 21,102 of
  21,680 observations are `WAIT` for this reason as much as any market reason.
- **BA §11's "temporal robustness" is a split of 43 days into 28 days and 14 days.** Both halves
  being positive is a within-episode consistency check, not temporal generalization. Calling it
  "chronological robustness" without stating the span overstates what it tests.
- **Half the evidence is one week of market.** BA's own quarter boundaries put Q2 (33 outcomes) in
  2026-07-19→07-20 and Q3 (33 outcomes) in 2026-07-21→07-23. **66 of 133 resolved outcomes — 49.6% —
  were confirmed inside a 5-calendar-day span**, on five highly co-moving crypto majors, with 60-bar
  (10-day) evaluation windows that overlap almost entirely.
- **No out-of-sample period exists inside the cached data.** The cache contains exactly one usable
  period. This is the fact that makes §11's answer to RQ9 come out the way it does.

---

## 3. RQ1 — the strongest defensible claim BA proves

Stated as narrowly as the evidence permits, with every qualifier that is load-bearing:

> **Claim C1.** Within a single 43-day live-decision window (2026-06-22 to 2026-08-03) on the five of
> ten backtested symbols that produced any outcome, among first-confirmations of the unmodified Swing
> Setup v1 policy that had computable stop-and-target geometry and whose stop or target was touched
> within 60 execution-role bars: setups whose confirming break was **0–2 bars old** touched target
> before stop in **26 of 40 cases (65.0%)**, while setups whose confirming break was **6–10 bars old**
> did so in **20 of 53 cases (37.7%)** — an absolute difference of **+27.3 points**, relative risk
> 1.72×, odds ratio 3.06, with non-overlapping Wilson intervals.
>
> **The direction of that difference is stable to every single-variable reslicing BA performed**: it is
> positive in all five outcome-bearing symbols, positive after removing any one of them (including
> DOTUSDT, where it widens to +32.0), positive in both LONG and SHORT, positive in both halves of the
> window, positive in four of five RR buckets, positive in all four stop-distance buckets, positive in
> three of four target-distance buckets, and positive in the large majority of regime-state cells with
> `n≥5` on both sides.
>
> **Confirmation age is not linearly associated with the policy's own geometry** in that population:
> `corr(age, RR) = +0.016`, `corr(age, stop%) = +0.005`, `corr(age, target%) = −0.035`.

Three additions this document can make in BA's favour, which strengthen C1 beyond what BA claimed:

**(a) The decision-relevant cut is available and gives the same answer.** BA's PRIMARY comparison
discards the 40 middle-aged rows (ages 3–5). A cap at 2 does not: it partitions age ≤ 2 against age
≥ 3. That partition is recoverable from AZ §6's tree — 26/40 (65.0%) against 36/93 (**38.7%**), a
difference of **+26.3 points**. The headline is not an artifact of comparing extremes and dropping the
middle.

**(b) The effect survives direct standardization on each of BA's own stratification axes.** BA reports
stratified tables but never recombines them into an adjusted estimate. Standardizing the fresh and
stale rates to the pooled stratum distribution (Appendix A.2) gives:

| Standardized on | Adjusted fresh | Adjusted stale | Adjusted difference | vs crude +27.3 |
|---|---|---|---|---|
| Target-distance quartile | 62.6% | 39.3% | **+23.4 pt** | −3.9 |
| RR bucket | 65.4% | 40.9% | **+24.4 pt** | −2.9 |
| Stop-distance quartile | 64.5% | 37.9% | **+26.7 pt** | −0.6 |
| Symbol | 65.8% | 36.3% | **+29.5 pt** | +2.2 |

No single-variable adjustment removes more than about a seventh of the effect, and symbol adjustment
increases it. This is a stronger statement than "the sign is positive in every bucket," and it is the
strongest quantitative defence of C1 available from published data.

**(c) The claim is not merely the RR≥5 leaf in disguise.** Excluding RR ≥ 5 entirely leaves +22.9
points (BA §6); excluding the tightest stop quartile leaves +22.2 points (BA §7).

**What C1 is.** A description of one sample, whose ordering is robust to being resliced along the axes
that sample allows. That is genuinely more than "fresh looks better in a table." It is genuinely less
than a property of the policy.

---

## 4. RQ2 — what BA does not prove

Every item below is a limitation of the evidence, not a criticism of BA's honesty; BA states many of
them itself, and where it does, that is noted.

**On the outcome variable**

1. **No claim about money is proved, and none can be.** `TARGET_FIRST` is a wick touch of a price
   level within 60 bars. No fees, no spread, no slippage, no funding, no partial fills, no position
   sizing, no execution delay exist anywhere in this repository (AV-1, AV-2, AV-4). BA states this
   (§19). The consequence is stronger than a caveat: **the phrase "improves expected performance" has
   no measured referent anywhere in the AV–BA series.**
2. **No claim about expectancy is proved — and this is not merely a fee problem.** Expectancy depends
   jointly on hit rate and payoff. AY computed mean realized R over all 133 resolved outcomes
   (+0.240, treating a win as `+RR` and a loss as `−1`). **No document in the series reports mean
   realized R, or any expectancy measure, by confirmation age.** BA's entire case is a hit-rate case.
   A hit-rate improvement is not an expectancy improvement, and the sign of the latter is unmeasured
   (§5.3).
3. **13 of 146 evaluated outcomes are excluded from every table** (5 `AMBIGUOUS_SAME_BAR`, 8
   `NEITHER_WITHIN_WINDOW`), and their age distribution is nowhere published. A cap's effect on them
   is unmeasured.
4. **31 of 177 confirmed setups had no computable geometry** (AX §3.1) and were never scored. Their
   age distribution is nowhere published either.

**On the intervention**

5. **The effect of the policy change is not measured.** BA §14 is a **row-deletion** exercise: it
   reports what the surviving subset of the *existing* 133 rows looks like at each hypothetical cap.
   D1 is not row deletion (§1, property 1). BA labels §14 "counterfactual … sensitivity" and warns it
   is not a recommendation; the sharper statement is that it is **not a counterfactual of D1 at all**,
   because the population under D1 contains confirmations that do not exist in the observed data.
6. **Nothing establishes that a freshness cap is the best-supported intervention available from the
   same evidence.** AY's single strongest marginal cells are target distance (Near 85.3%, n=34) and RR
   (5+ 9.1%, n=33); AZ's strongest discriminator is `elevated_setup_participation` (91.3% loss rate,
   lift 1.71). Freshness was isolated because the brief for BA said to isolate it, not because it
   outranked those. No comparison of candidate interventions exists.

**On generalization**

7. **No out-of-sample test exists.** Every check in BA §9–§13 is a reslicing of the same rows (BA §19
   says so). §2.3 sharpens why this cannot be fixed inside the cache: there is only one usable period
   in it.
8. **The hypothesis was selected from the data it is tested on.** AY searched ~25 segmentations and
   surfaced `RR 5+ × stale` (0/27) among its cross-tabs; AZ's tree isolated `stale × RR≥5` (0/24);
   BA then tested freshness on **the identical 133 rows** that produced the hypothesis. BA's
   preregistration discipline (§1.1) governs which comparisons within BA are primary — it cannot
   undo the fact that the hypothesis itself is a survivor of a prior search over the same sample.
   This is the deepest methodological objection available, and BA does not raise it.
9. **Five of ten symbols contributed zero outcomes.** Nothing is known about freshness on SOLUSDT,
   BNBUSDT, XRPUSDT, DOGEUSDT, AVAXUSDT — not "no effect," no observations (BA §9).
10. **43 days of one asset class.** Not one crypto cycle, not one regime transition, not one
    macro environment. §2.3.

**On the shape of the relationship**

11. **Monotonic decay is disproved, not proved.** Spearman ρ = −0.045. Age 5 (50.0%) beats ages 3, 4,
    6, 7, 8, 9 and 10; age 10 is not the worst age (age 9 is). BA states this (§3.1, §16). The
    relationship is a fresh-end step, not a decay curve — which matters because a step at an
    unvalidated location is exactly the shape most vulnerable to being a small-sample accident.
12. **No cap location is validated.** The step could be at ≤1, ≤2 or ≤3. Cap 1 (62.5%, n=24), cap 2
    (65.0%, n=40) and cap 3 (57.4%, n=54) are not ordered monotonically with tightness (BA §14), and
    their Wilson intervals overlap heavily. The number "2" is an inheritance from the brief's
    bucket definition, not a measured optimum.
13. **Universality is disproved in at least one large stratum.** BA §16 reports the effect vanishing
    at RR 0–1. §8.1 shows that finding is itself bucket-definition-dependent, which makes the stratum
    uninformative rather than contradictory — a weaker objection than BA's own, but a wider
    uncertainty.

**On the mechanism**

14. **No causal mechanism is established or even discriminated between.** §7 shows BA cannot separate
    signal decay from entry displacement from selection, because it measured none of the three.
15. **The 3-family-agreement stratum is untestable** (zero fresh observations, BA §13.1). §6.3 shows
    this is not a neutral gap.

---

## 5. RQ3 — adopting `confirmation_age <= 2`: measured vs assumed

### 5.1 Measured

Exhaustively, this is everything on the supporting side that is a measurement rather than an
inference:

| # | Measured fact | Source |
|---|---|---|
| M1 | Among 93 resolved outcomes at ages 0–2 or 6–10, the 40 fresh ones touched target first 65.0% of the time vs 37.7% for the 53 stale ones (+27.3 pt; CIs non-overlapping) | BA §4–§5 |
| M2 | Under the decision-relevant partition (≤2 vs ≥3): 65.0% (n=40) vs 38.7% (n=93), +26.3 pt | AZ §6, arithmetic |
| M3 | The sign is positive in 5/5 symbols, 5/5 LOSO removals, 2/2 directions, 2/2 window halves, 4/5 RR buckets, 4/4 stop buckets, 3/4 target buckets | BA §6–§12 |
| M4 | Single-variable standardized differences: +23.4 to +29.5 pt | This doc, A.2 |
| M5 | `corr(age, RR / stop% / target%)` all within ±0.04 of zero | BA §2.2, AY |
| M6 | Fresh and stale medians are close: RR 1.478 vs 1.444, stop 1.421% vs 1.271%, target 1.669% vs 1.713% | BA §8 |
| M7 | Excluding RR≥5: +22.9 pt. Excluding the tightest stop quartile: +22.2 pt | BA §6–§7 |
| M8 | A 16-stratum equality-matched subsample (29 fresh / 30 stale) pools to 62.07% vs 33.33% (+28.7 pt) | BA §5.1 |
| M9 | With a cap at 2, all five outcome-bearing symbols and a similar L/S proportion remain in the surviving rows (17L/23S vs 58L/75S) | BA §14 |
| M10 | Naive two-sample z on M1 is 2.71 (nominal two-sided p ≈ 0.007); on M2, 2.90 (p ≈ 0.004) | This doc, A.3 |

M8 requires one downgrade the committee should note: BA pools **raw counts** across its 16 matched
strata. Pooling raw counts over unbalanced strata is a crude rate on a subsample, not a
stratum-weighted (Mantel–Haenszel-style) adjusted estimate; it removes confounding only to the extent
the strata happen to be balanced, and BA reports 29 fresh against 30 stale spread over 16 cells of
size 1–4, which cannot be assumed balanced. M8 is therefore weaker evidence of adjustment than its
framing suggests — the genuine adjustment evidence is M4, which this document had to compute.

### 5.2 Assumed

Everything the inference from M1–M10 to "adopting D1 today improves expected performance" additionally
requires, and which is **not measured anywhere**:

| # | Required assumption | Status |
|---|---|---|
| A1 | **That the cap's effect equals the observed subgroup difference.** | **Known to be false as stated.** A cap defers rather than deletes: candidates persist and can confirm later on a new break at a reset age, with different geometry and a different outcome (§1, property 1). The post-cap population is not the fresh subset of the observed population. Its size, geometry and win rate are all unmeasured. |
| A2 | That a higher wick-touch rate implies higher expectancy | Unmeasured. No expectancy figure by age exists (§4, item 2) |
| A3 | That the effect survives fees, spread and slippage | Unmeasurable in this repository (AV-1) |
| A4 | That the effect is not an artifact of dependence among 133 non-independent outcomes | Unmeasured. No cluster-robust or block-resampled interval exists anywhere in the series; §9.2 shows why this is decisive |
| A5 | That a 43-day window on 5 crypto majors generalizes | Untested, and untestable inside the cache (§2.3, §11) |
| A6 | That the step's location (2) is right | Unvalidated (§4, item 12) |
| A7 | That the effect is a property of freshness rather than of entry displacement or of the selection that made a confirmation late | Undiscriminated (§7) |
| A8 | That the residual after joint adjustment survives | Unmeasured. Only single-variable adjustment is possible from published tables (§8.6) |
| A9 | That reducing the confirmed population by ~70% is operationally acceptable | A preference, not a measurement (§6) |
| A10 | That losing ~70% of observations does not unacceptably degrade the system's own ability to detect future degradation | Unmeasured and not discussed anywhere in the series (§6.5) |

### 5.3 The honest summary of RQ3

**What evidence exists that adopting `confirmation_age <= 2` today improves expected performance?
None that is directly about the intervention, and none at all about expected performance.**

What exists is a robust in-sample association between a measured attribute and a wick-touch
classification, plus ten assumptions bridging that association to the intervention and to money. A1
is the load-bearing one and is known to be false in the specific form the bridge requires: BA's
strongest-looking artifact on this question (§14's cap table) measures a different operation than the
one under consideration.

---

## 6. RQ4 — evidence that adoption harms

Evidence of cost is thinner than evidence of benefit, because no document set out to look for it.
What can be established:

### 6.1 Trade frequency — a large, measured reduction, whose true magnitude is unknown

By row-deletion accounting, a cap at 2 retains **40 of 133** resolved outcomes: **93 removed,
69.9%** (BA §14). Over the 43-day usable window and the ten-symbol universe that is a fall from
about **3.1 to 0.9 resolved outcomes per day** across the whole universe (A.4).

Two corrections in opposite directions, both unmeasured:

- The true retained count under D1 is **higher** than 40, because deferred candidates can confirm
  later on a fresh break (§1). By how much is unknown.
- The published cap table covers **resolved rows only**. The effect on the 177 `CONFIRMED` rows, the
  31 geometry-less confirmations and the 13 ambiguous/unresolved outcomes is not published at any
  cap. The frequency figure the owner would actually experience — confirmations per week — has never
  been computed at any candidate cap.

### 6.2 Coverage and diversity — mostly preserved, with one complete wipeout

- **Symbols:** all five outcome-bearing symbols survive even at cap 0 (BA §14). The five
  zero-outcome symbols remain at zero. No coverage harm measured.
- **Direction:** L/S proportion is roughly preserved (17L/23S at cap 2 vs 58L/75S baseline).
- **RR distribution:** barely changes — mean RR 4.51 at cap 2 vs 4.99 baseline; median 1.48 vs 1.43.
  This cuts against the intervention's narrative rather than for it: the cap is **not** a targeted
  removal of poor geometry. It removes 93 rows across the whole geometry distribution in order to
  eliminate a 24-row leaf that AZ defined by RR ≥ 5 as much as by staleness.
- **Evidence-agreement diversity: a measured 100% wipeout.** All five resolved outcomes in which all
  **three** evidence families agreed sit in the stale band — BA §13.1 records zero fresh observations
  in that stratum. A cap at 2 therefore removes **every** maximum-agreement setup the dataset
  contains. Those five won only 20% of the time (AY §3 RQ9, n=5, CI 3.6%–62.4%), so this is not
  evidence that valuable setups are lost; it is evidence that the cap and the policy's own strongest
  corroboration signal are, in this sample, mutually exclusive. That interaction is untestable at
  n=5 and is a measured structural fact about what a cap would do.

### 6.3 Sample-mix instability over time

BA §11's own composition, unremarked there: the fresh/stale mix is strongly non-stationary within
43 days. First half: 27 fresh / 17 stale. Second half: **13 fresh / 36 stale**. A cap at 2 would have
removed 63% of the first half's resolved population but **73% of the second half's** — and the
second half is the more recent, more representative-of-now period. Whatever governs how often a break
and a thesis coincide is itself time-varying, so a cap's throughput is not a stable quantity.

The same table shows the effect weakening as the window advances: +27.0 points in the first half,
**+12.8 points in the second**. BA calls this "a real weakening, not a reversal," which is fair. For a
committee, "the effect halves in the more recent half of the only window we have" is a cost-side fact,
not a robustness result.

### 6.4 The 5-day burst carries the effect disproportionately

Decomposing BA §11's quarters (A.5): the 45 fresh/stale rows confirmed inside 2026-07-19→07-23 show
**+35.2 points** (fresh 14/19 = 73.7%, stale 10/26 = 38.5%), while the 48 rows outside that 5-day
span show **+20.1 points** (fresh 12/21 = 57.1%, stale 10/27 = 37.0%). Both positive — which is
reassuring, and is the single best argument that the effect is not purely one week's accident. But
nearly half the evidence, and the larger half of the effect, comes from five days.

### 6.5 A monitoring cost nobody has priced

Discarding ~70% of confirmations discards ~70% of the system's own future measurement stream. AZ, AY
and BA all rest on `n = 133` accumulated over 43 usable days; at post-cap rates, re-accumulating a
comparable sample would take proportionally longer. Adopting a filter derived from a small sample
while shrinking the sample available to audit that filter is a real cost of the change. It is
nowhere quantified in the series, and this document does not quantify it either — it names it.

### 6.6 What no evidence of harm exists for

- No evidence that fresh confirmations carry worse fills, worse liquidity or wider spreads (nothing
  in this repository can see any of those).
- No evidence that the cap degrades the policy's other measured properties (untested).
- One weak counter-signal on holding period: fresh outcomes take longer to resolve (mean 4.17 bars vs
  3.09, BA §8), so a fresh-only population holds risk marginally longer per trade. Immaterial at this
  precision, and reported for completeness.

---

## 7. RQ5 — is BA measuring late entries rather than freshness?

**The two are not competing hypotheses about different variables. They are competing interpretations
of one variable, and the code makes them the same measurement.**

From `policy.py:344-348` and `policy.py:358`: `break_age` is the count of execution bars between the
confirming break's bar and the confirming bar, and the entry reference price is the execution close
**at the confirming bar**. Therefore, by construction:

> confirmation age = the number of 4H bars that elapsed between the structural event and the entry.

"Fresh confirmation" and "early entry relative to the break" are the same fact stated twice. BA
cannot be measuring one rather than the other; it is measuring the single quantity both phrases name.
What remains genuinely open is *which causal story* explains the association, and BA measured none of
the three candidates:

**Story 1 — informational decay.** A structure break's predictive content about the next 60 bars
decays with age. This is the story BA's title implies.

**Story 2 — price displacement (the "late entry" story proper).** By the time a stale confirmation
fires, price has spent N bars beyond the broken level. The entry is further into the move; more of the
expected excursion is already spent; the entry sits at a worse point relative to the level that
justified it. **BA's defence against this is incomplete.** BA shows stop%, target% and RR are similar
between fresh and stale (M6) — but all three are measured *from the entry price*, so they say nothing
about how far the entry has travelled *from the broken level*. The quantity that would separate Story
1 from Story 2 — displacement between the entry close and the confirming break's level, or the
entry's position within the post-break range — is computable from data already in hand
(`trigger.level.price` against `reference_price`) and **is not reported in any document in the
series.** This is the single most consequential unmeasured variable in the evidence base.

Two published facts lean toward Story 2 rather than away from it:

- Stale outcomes resolve **faster** (mean 3.09 bars vs 4.17, BA §8). BA calls this "consistent with,
  but not proof of, stale confirmations more often being caught by a stop quickly." An entry that is
  already extended is closer to its protective level in path terms, which is exactly Story 2's
  prediction.
- BA's own red team concedes stale rows carry a slightly tighter median stop and slightly farther
  median target than fresh ones — "exactly the direction that would mechanically produce a lower
  stale win rate independent of freshness itself." That concession is a Story-2 concession.

**Story 3 — selection on why the confirmation was late.** This one is absent from the entire evidence
base and is arguably the most likely. A break can only confirm late if something blocked it earlier.
Reading `evaluate_setup`, the blockers are enumerable: decision context `INSUFFICIENT`
(`policy.py:299`), context structure not `TRENDING` (`policy.py:310`), fewer than two agreeing
families or any opposing family (`policy.py:320`), execution trend sustained against the direction
(`policy.py:342`), or no computable geometry (`policy.py:374`). A stale confirmation is therefore
**selected on "the thesis and the break failed to coincide"** — the evidence assembled itself late,
or the execution trend was opposing at the break and stopped opposing later. Under Story 3, age is a
proxy for the coherence of the setup's own formation, not a property of the break at all. Nothing in
AV–BA records which gate was blocking at the earlier bars, so Story 3 is completely untested.

A fourth mechanism, narrower but real, comes from `backtest_identity.py`: identity is keyed on the
watched/confirming level's origin, and **an intervening `WAIT` starts a new identity**
(`backtest_identity.py:105-107`). A thesis that lapses and re-forms against the same level produces a
second `is_first_confirmation` — at a larger age, on the same underlying break. How many stale rows
are re-confirmations of a break that already appeared in the dataset is unrecorded, and it bears
directly on both independence and interpretation.

**Answer to RQ5.** BA is not "simply measuring late entries," because there is no separate freshness
variable it could have measured instead — age *is* the entry lag. But BA cannot attribute the
association to informational decay rather than to entry displacement or to formation-lateness
selection, and it does not claim to. Of the three stories, the two BA never examined (2 and 3) are
the ones with mechanical support in the code, and Story 3 has none of BA's controls pointed at it.

---

## 8. RQ6 — confounding, variable by variable

**A framing correction first, because it governs every row below.** Stratification and standardization
cannot *disprove* confounding for any variable. They can show a variable does not explain the
association at the granularity measured. Residual confounding within a bucket, and confounding by
anything unmeasured, both survive every check BA ran. So the honest verdict column has two values,
"reduced" and "not addressed," and never "disproved." Where BA's evidence is genuinely strong, that
is said.

| Variable | What BA did | Verdict | Residual |
|---|---|---|---|
| **Displayed RR** | 5-bucket stratification; population `r = +0.016`; exclusion of RR≥5 (+22.9 pt); standardization here gives +24.4 pt | **Substantially reduced.** The strongest of BA's geometric controls | Within-bucket composition (buckets are 1.0–2.0 R wide, and 5+ is unbounded); joint interaction with stop/target not tested |
| **Stop distance** | 4 quartiles (AY's edges); `r = +0.005`; exclusion of tightest quartile (+22.2 pt); standardized +26.7 pt | **Substantially reduced** — the least influential confounder tested | AY §10.5's touch-probability mechanism is not separable from directional signal by any measurement in this repository |
| **Target distance** | 4 quartiles; `r = −0.035`; standardized +23.4 pt | **Reduced, and the most influential of the three** — adjustment removes ~14% of the effect. One bucket (near–mid) reverses sign | Fresh carries a higher share of AY's strongest mechanical bucket (Near: 32.5% of fresh vs 24.5% of stale). Age 2 alone — 16 rows, 11 of the 26 fresh wins — has a median target of 0.83%, against 1.7–2.3% for most other ages (BA §3) |
| **RR ∧ stop ∧ target jointly** | Never done | **Not addressed** | These are two numbers read three ways (AY §11, BA §17.4, BA's own red team). Three separate single-variable adjustments are *not* one joint adjustment, and the joint residual is unmeasured |
| **Symbol** | Per-symbol tables; full LOSO; standardized +29.5 pt | **Strongly reduced.** LOSO is the best control in the document; DOTUSDT's removal widens the gap | Every per-symbol cell is n=5–18; five symbols are absent entirely; symbol adjustment cannot address the fact that all five share one 43-day period |
| **Direction** | LONG/SHORT split, both positive | **Reduced** | n=17–27 per cell |
| **Calendar time** | Halves and quarters; both halves positive; Q3 reverses | **Not addressed, despite appearances.** The split covers 43 days; 49.6% of outcomes fall in 5 days (§2.3) | This is the largest unaddressed confounder in the document. Market-episode confounding — a single 6-week regime in which fresh breaks happened to work — is fully consistent with every table BA published |
| **Cross-sectional co-movement** | Never measured | **Not addressed** | 5 co-moving majors, overlapping 10-day evaluation windows, 66 outcomes in 5 days. One market move can determine dozens of "independent" outcomes simultaneously |
| **Volatility (ATR%, all roles)** | Regime-state cells with n≥5 on both sides; mostly positive | **Weakly reduced** | AY measured `r ≈ 0` for ATR% against outcome, so it is a weak confounder candidate to begin with. Cells are tiny; one known 16-row single-symbol single-week artifact sits inside them |
| **Structural trend / regime structure** | Regime-dimension cells; positive in most | **Weakly reduced** | CONTEXT structure has zero variance by construction (AY §3 RQ3) — it cannot confound. EXECUTION-role trend, which AY measured as the widest categorical gap in the series (60.8% vs 21.9%), also **gates confirmation staleness** (`policy.py:342`) and is therefore mechanically entangled with age. BA does not examine this entanglement |
| **Participation** | Included in the regime sweep | **Weakly reduced** | AZ's strongest single discriminator (`elevated_setup_participation`, 91.3% loss rate, lift 1.71) is never crossed with age anywhere in the series |
| **Evidence-family count** | Attempted | **Cannot be evaluated** | Zero fresh observations at 3-family agreement. Not neutral: §6.2 shows the cap and maximum agreement are mutually exclusive in this sample |
| **Post-break price displacement** | Never measured | **Not addressed** | §7, Story 2. Computable from data in hand; absent from the series |
| **Which gate delayed the confirmation** | Never measured | **Not addressed** | §7, Story 3. The selection mechanism that produces staleness is entirely unexamined |
| **Repeat confirmations of one break after an intervening `WAIT`** | Never measured | **Not addressed** | §7, fourth mechanism. Bears on both interpretation and independence |

### 8.1 The RR 0–1 stratum is unstable, not contradictory

BA's own strongest self-criticism (§18) is that the effect "disappears entirely at RR 0–1," the
largest RR bucket. That finding does not survive a change in the stale definition. Within RR 0–1:

| Age band | n | Wins | Rate | Source |
|---|---|---|---|---|
| 0–2 (fresh) | 16 | 13 | 81.2% | BA §6 |
| 3–5 (mid) | 19 | 11 | 57.9% | AZ §6 − BA §6 (A.1) |
| 6–10 (stale) | 17 | 14 | 82.4% | BA §6 |
| **3–10 (the decision-relevant cut)** | **36** | **25** | **69.4%** | AZ §6 |

Against BA's 6–10 band the difference is −1.1 points; against the band a cap at 2 would actually
create, it is **+11.8 points**. A stratum whose sign flips with the boundary definition, and whose
own shape is U-shaped across three adjacent age bands, is not evidence that the effect vanishes
there — it is a 52-row stratum that is uninformative in both directions. This widens the uncertainty
BA reported rather than resolving it, and it removes BA's sharpest self-objection while adding no
support for the intervention.

### 8.2 The verdict on RQ6 as asked

For **every** variable already measured, BA **fails to disprove** confounding, because stratification
cannot disprove it. What BA does establish, and establishes well, is that **no single measured
variable explains the association at the granularity available**: RR, stop distance, target distance,
symbol, direction and (weakly) regime each leave 22–30 points standing. What BA leaves entirely
unaddressed is the class of confounders that matter most for a capital decision — **market episode,
cross-sectional dependence, entry displacement, and the selection mechanism behind lateness** — and
three of those four are unmeasured rather than merely unadjusted.

---

## 9. RQ7 — how much uncertainty remains, quantified

### 9.1 Sampling uncertainty at face value

BA declines formal significance testing on stated grounds. For a capital decision the committee needs
the number anyway, so it is computed here from BA's own counts (A.3), with the caveat that a
two-sample z on 40 and 53 observations is itself approximate:

| Contrast | Difference | SE | z | Nominal two-sided p | 95% CI on the difference |
|---|---|---|---|---|---|
| Fresh (0–2) vs stale (6–10) | +27.3 pt | 0.1006 | 2.71 | ≈ 0.007 | **+7.5 pt to +47.0 pt** |
| Age ≤2 vs age ≥3 (decision-relevant) | +26.3 pt | 0.0908 | 2.90 | ≈ 0.004 | **+8.5 pt to +44.1 pt** |

Even taken entirely at face value, and even before any correction, **the interval on the effect spans
roughly a sixfold range** (+7.5 to +47.0 points). Nothing in the evidence base distinguishes "a small
edge" from "a very large edge."

### 9.2 Dependence: the decisive uncertainty

Both intervals above assume 93 independent Bernoulli trials. That assumption is false, in a way that
is measurable in outline from BA's own tables:

- 133 outcomes span 43 calendar days; 66 of them fall in 5 days (§2.3).
- Five symbols, all large-cap crypto, all co-moving.
- Evaluation windows are up to 60 4H bars ≈ 10 days, so outcomes confirmed within days of each other
  are resolved by overlapping price paths.
- AY §10.3, AZ §9.3 and BA §17.3 all name within-symbol non-independence; none quantifies it, and
  none names the cross-symbol, same-week case, which is the larger effect here.

The standard correction is a design effect, `deff = 1 + (m − 1)ρ` for average cluster size `m` and
intra-cluster outcome correlation `ρ`. With 133 outcomes over ~45 calendar days, `m ≈ 3` clustering by
day alone; inside the 5-day burst `m` is far larger. Because neither `m` nor `ρ` was measured, the
only honest presentation is a sensitivity table over assumed values (A.6). **The assumption is stated,
not measured:**

| Assumed `deff` | Implied SE | z | Nominal two-sided p | 95% CI on +27.3 pt |
|---|---|---|---|---|
| 1.0 (independence — BA's implicit assumption) | 0.1006 | 2.71 | 0.007 | +7.5 to +47.0 |
| 1.5 (`m≈3`, `ρ≈0.25`) | 0.1232 | 2.21 | 0.027 | +3.1 to +51.4 |
| 2.0 (`m≈3`, `ρ≈0.5`) | 0.1422 | 1.92 | 0.055 | **−0.6 to +55.1** |
| 3.0 (`m≈5`, `ρ≈0.5`) | 0.1742 | 1.57 | 0.117 | **−6.9 to +61.4** |

At a design effect of 2 — entirely plausible for 5 co-moving majors with half the sample inside one
week — **the 95% interval includes zero.** This is the crux of the whole assessment: the primary
result's apparent strength rests substantially on an independence assumption that the dataset's own
time structure contradicts, and no document in the series has ever tested it.

### 9.3 Selection uncertainty

The hypothesis was drawn from a prior search over the same 133 rows (§4, item 8). AY reports ~25
segmentations; AZ adds nine categories, a flag-count statistic, a tree and a dozen pair
cross-tabs; none corrects for multiplicity, by their own statement. A nominal p of 0.007 obtained by
re-testing a search survivor on its generating sample is not a 0.007 in the sense a committee needs.
No quantitative correction is available, because the size of the search space is not recorded. This is
an **unquantified** uncertainty, and it points in only one direction: the true evidential weight is
lower than the nominal figure.

### 9.4 Effect-location uncertainty

Cap 1: 62.5% (n=24). Cap 2: 65.0% (n=40). Cap 3: 57.4% (n=54). Non-monotonic, overlapping intervals
(BA §14). Uncertainty on the boundary is essentially total: the data cannot order 1, 2 and 3.

### 9.5 Translation uncertainty (unquantifiable)

| Unknown | Bound available? |
|---|---|
| Wick-touch rate → realized PnL | **None.** No fee/slippage/spread model exists (AV-1) |
| Hit rate → expectancy by age | **None.** Never computed by age; only the pooled +0.240 mean R exists |
| Observed subgroup difference → effect of D1 | **None.** Deferred-confirmation dynamics never simulated (§5.2, A1) |
| 43-day window → any other period | **None.** No out-of-sample period exists in the cache (§2.3) |
| 5 symbols → the other 5, or any other universe | **None.** Zero observations |

### 9.6 The uncertainty statement in one paragraph

The best available point estimate of the in-sample association is +26 to +27 percentage points of
wick-touch rate. Under independence, its 95% interval is +8 to +47 points. Under plausible clustering
it includes zero. It is selected from a search over the same data, with an unquantified inflation of
apparent significance. Its boundary location is undetermined among 1, 2 and 3 bars. Its translation
into the effect of the actual policy change is unmeasured and known to be non-trivial. Its
translation into money is unmeasurable in this repository today. **Five of the six uncertainties above
have no upper bound available from any evidence currently in hand.**

---

## 10. RQ8 — the vote

### 10.1 The vote

> **C — Interesting but insufficient.**

Not D. The evidence is well constructed, it audits cleanly (§2.2), the association survives every
single-variable adjustment this document could compute (§3b), and the direction is consistent across
symbols, sides, halves and geometry buckets. That is materially more than a suggestive table, and
dismissing it as insufficient-of-no-interest would misread it.

Not B. Not A.

### 10.2 Why not A (strong enough for production)

Any one of the following would be disqualifying on its own; all five hold simultaneously.

1. **The intervention was never evaluated.** BA's cap table deletes rows; D1 defers confirmations.
   Production code (§1) shows the post-cap population contains confirmations that do not exist in the
   measured data. The committee is being asked to price a change whose output has never been observed
   even in replay — and, per §11, could be observed with no new market data.
2. **The claim about "expected performance" has no measured referent.** The outcome variable is a wick
   touch. Expectancy by age has never been computed even in R-multiples, let alone after costs. A
   hit-rate improvement of 27 points on a population whose RR distribution barely changes (§6.2)
   *probably* implies higher expectancy — "probably implies" is not a measurement, and AY's own
   finding that displayed RR correlates **negatively** with hit rate (r = −0.30) is a standing warning
   against assuming hit rate and payoff move together in this system.
3. **The sample is one 6-week market episode, not a 400-day history.** §2.3 establishes this from
   production code. Half of it is five days. Every robustness check in BA is a reslicing of that
   episode; none is a second episode.
4. **The primary result is not robust to acknowledging dependence.** §9.2: at a design effect of 2 the
   interval includes zero. No cluster-aware interval exists anywhere in the series.
5. **The hypothesis was tested on its generating sample** (§9.3), with no multiplicity accounting
   anywhere in AY, AZ or BA, by those documents' own statements.

### 10.3 Why not B (strong enough only for an experimental branch)

This is the closest call, and the reasoning is specific rather than dispositional.

If B means *"the evidence justifies analysis of a policy variant,"* it is nearly right — and §11 shows
that analysis needs no new market data and no production change. But building an experimental branch
is a production-shaped commitment: a second policy path to maintain, test and reconcile, and a second
set of numbers to interpret. Committing to it **before** the free measurement in §12(1) is run would
be spending engineering to approximate an answer that already-cached data can produce directly. The
ordering matters: a branch cannot be specified sensibly (cap 1, 2 or 3? §9.4 cannot order them)
until the counterfactual replay has been evaluated.

If B means *"put capital on it in a small experimental allocation,"* it fails on §10.2 items 2 and 4
alone. A rule whose expectancy has never been computed and whose effect interval includes zero under
plausible dependence assumptions does not meet the bar for capital, however small the allocation.

### 10.4 Why C rather than D (insufficient)

D would imply the evidence does not warrant further attention. It does. Specifically, five features
distinguish this from a chance finding worth ignoring:

- **LOSO survival, including the dominant symbol.** Removing DOTUSDT (39.1% of the population)
  *widens* the gap to +32.0 points. This is the single most persuasive fact in the evidence base:
  the most obvious deflationary explanation was tested directly and failed.
- **Adjustment does not erode it.** +23.4 to +29.5 points after single-variable standardization on
  each of four axes (§3b).
- **Geometry is not the mechanism.** All three age-geometry correlations are within ±0.04 of zero,
  and the effect survives excluding both RR≥5 and the tightest stop quartile.
- **It is positive outside the burst.** +20.1 points on the 48 rows confirmed outside the 5-day
  cluster (§6.4).
- **A plausible mechanism exists** in each of the three stories in §7 — the association is not
  mechanism-free.

**The committee's position, stated plainly: a real association has been measured in one market
episode; nothing about the proposed intervention, its expectancy, or its durability has been measured
at all. That is a hypothesis with unusually good in-sample support, not a decision.**

### 10.5 What would move the vote

Not a recommendation to produce these things — a statement of what evidence the vote is conditional
on, which is what a committee owes whoever brings the next paper:

| To reach | Required |
|---|---|
| **B** | The D1 counterfactual replay (§12.1) showing what the policy actually produces under a tightened cap, plus a dependence-aware interval (§12.2) that excludes zero |
| **A** | The above, plus expectancy by age in R-multiples, plus replication in at least one period disjoint from 2026-06-22→08-03, plus a cost model sufficient to state the sign of the change after fees and slippage |

---

## 11. RQ9 — what the existing dataset can and cannot still answer

**Premise: no additional market data may be collected.** The available material is the cached
400-day, ten-symbol, three-interval kline dataset (identical to what `fetch_historical_dataset`
produced for AV–BA) plus the row-level extractions AV–BA built from it.

### 11.1 Answerable, with no new market data

Each item names the question, the mechanism, and why the existing data suffices.

| # | Question | How the existing dataset answers it |
|---|---|---|
| 1 | **What does the policy actually produce under a tightened confirmation cap?** | Re-run the identical replay loop (`run_backtest`'s own loop, or a mirror of it as AW–BA all used) over the **same cached candles** with `CONFIRMATION_LOOKBACK_BARS` bound to 2, 3 and 5 in a research-only scope. This captures the deferred-confirmation dynamics (§1) that row deletion cannot: real retained counts of `CONFIRMED`, evaluated and resolved rows, real geometry, real outcomes. Needs no market data, no production change, and no new metric — only the constant the replay reads |
| 2 | **Is the primary difference robust to dependence?** | Block bootstrap or cluster-robust intervals over BA's existing 133 rows, clustered by symbol, by calendar day, and by overlapping-evaluation-window episode. Pure re-analysis; the row-level fields (`confirmed_at`, symbol, age, outcome) are already extracted |
| 3 | **What is expectancy by age?** | Mean realized R per age band, using AY's own convention (win → `+RR`, loss → `−1`), over rows already extracted. Arithmetic only |
| 4 | **Is it entry displacement or signal decay?** (§7, Story 2) | At each confirmation instant, `trigger.level.price` and `reference_price` are both already computed by the policy; their distance, normalized by ATR or by the stop distance, measures post-break displacement directly. Requires re-extraction over cached candles, not new data |
| 5 | **Why was each stale confirmation late?** (§7, Story 3) | At each confirmation, walk back to the confirming break's bar in the same cached replay and record which gate was false at each intervening bar (context state, structure, family tally, execution opposition, geometry). This turns staleness from an attribute into a mechanism |
| 6 | **How much of the sample is one event?** | Count overlapping evaluation windows and concurrent same-direction outcomes across symbols, from `confirmed_at` / `resolved_at` fields already extracted. Gives a measured `m` and `ρ` to replace §9.2's assumed ones |
| 7 | **Does the effect survive joint adjustment?** | Logistic regression or Mantel–Haenszel stratification of outcome on age together with RR, stop% and target% over the existing 133 rows — the joint adjustment §8 identifies as missing |
| 8 | **How many stale rows are re-confirmations of a break already in the dataset?** | `setup_id`, `confirmed_at` and `trigger` level origin are already recorded; grouping by broken level answers it directly |
| 9 | **What happens to confirmations, not just resolved outcomes, under a cap?** | Falls out of (1) |
| 10 | **Is the step at 1, 2 or 3?** | Partially: (1) run at several caps gives real retained populations per cap. It will not resolve the ordering statistically at these sample sizes, and (2) will say so honestly |

Items 1 and 2 are, between them, the difference between the current vote and a different one.

### 11.2 Not answerable, at any effort, without new data

| # | Question | Why the existing dataset cannot answer it |
|---|---|---|
| 1 | **Does the effect replicate out of sample?** | **This is the structural blocker, and §2.3 is why.** The 400-day cache contains exactly *one* period in which the policy can produce an outcome at all — the 43 days after the weekly EMA(50) warm-up completes. Every earlier day in the cache is structurally silent. There is no second period to hold out. Splitting 43 days again yields ~3-week fragments already shown unstable (BA's Q3 reverses on 4 observations). An out-of-sample test requires **more history** — a longer fetch, so that warm-up completes earlier and earlier decision days become live — which is precisely the additional data collection this premise forbids |
| 2 | **Does it hold on the other five symbols, or any other universe?** | Zero observations exist. Nothing can be inferred from an empty cell |
| 3 | **Does it hold in a different volatility or macro regime?** | Only one regime is represented. Not a sample-size problem; the variation does not exist in the data |
| 4 | **Is it profitable?** | Requires a cost/execution model this repository does not contain (AV-1). Adding one is not data collection, but it is also not something the dataset can answer — and even with one, items 1–3 remain open |
| 5 | **Would the deferred confirmations under a cap have been fillable in live conditions?** | Requires intrabar or order-book data the repository has never held (AV-3 names the same limit for same-bar ambiguity) |

### 11.3 The answer to RQ9

**Yes for mechanism and specification; no for generalization.** The cached dataset can establish what
the intervention actually does, whether the association survives dependence-aware and jointly adjusted
analysis, what its expectancy is in R-multiples, and which of §7's three causal stories it supports.
It **cannot** establish that any of that generalizes beyond 2026-06-22→2026-08-03 on five symbols,
because the cache physically contains one usable period, and the warm-up structure that causes this is
a property of the policy's own indicator requirements, not of the extraction.

---

## 12. RQ10 — the smallest missing evidence

Missing **evidence**, ordered by how much of §9's uncertainty it removes. This is not a roadmap, not
a sequence of milestones, and not a proposal: it is the answer to "what would have to be known before
a decision on D1 could honestly be made," which is what the brief asks for.

**Tier 1 — without these, no honest decision on D1 is possible.**

1. **What the policy actually produces under a tightened cap.** The retained `CONFIRMED`, evaluated
   and resolved counts, the geometry distribution and the outcome distribution of the population D1
   would create — including the deferred confirmations that fire later on a fresh break. Every figure
   currently used to argue for D1 describes a population that D1 does not produce (§5.2, A1).
   Obtainable from cached data (§11.1.1).
2. **A dependence-aware interval on the primary difference.** Clustered by symbol, by day, and by
   overlapping evaluation window. §9.2 shows the sign of the entire conclusion turns on this, and it
   is currently an assumption, not a measurement. Obtainable from cached data (§11.1.2).
3. **Expectancy by confirmation age.** Mean realized R per age band. The decision is about expected
   performance; the evidence base measures touch frequency only (§4, item 2). Obtainable from cached
   data (§11.1.3).

**Tier 2 — without these, the decision would rest on an unidentified mechanism.**

4. **Post-break displacement per confirmation** — entry price against the broken level, normalized.
   Separates "the signal decayed" from "the entry was late" (§7, Stories 1 and 2), which are currently
   indistinguishable, and which would imply different interventions.
5. **The blocking-gate history behind each stale confirmation.** Whether staleness is a property of
   the break or a selection on incoherent setup formation (§7, Story 3). Entirely unexamined today.
6. **A joint adjustment of age against RR, stop distance and target distance simultaneously.** Four
   separate single-variable adjustments are not one joint adjustment (§8).

**Tier 3 — without these, durability is unknown and cannot be assumed.**

7. **Replication in at least one period disjoint from 2026-06-22→2026-08-03.** The single largest gap
   in the whole evidence base, and the only Tier-1-magnitude item that **cannot** be closed with the
   current cache (§11.2.1). Its absence is structural, caused by the 350-day EMA warm-up consuming
   the window.
8. **Any observation at all on a symbol universe other than the five that produced outcomes.**
9. **A cost model sufficient to state the sign of the change after fees, spread and slippage** — the
   minimum needed for the phrase "improves expected performance" to have a referent.

**Explicitly not on this list:** a threshold, a filter design, an ADR, a branch, a policy variant
specification, or any change to `src/`. None of those is evidence, and none is what was asked for.

---

## 13. Red team against this document

**"§2.3's 43-day window is this document's headline claim. Is it right?"** The derivation is
code-exact (EMA(50) `warmup_bars`, a 57-candle weekly boundary first opening 2025-07-07, no warm-up
prefix in `fetch_historical_dataset`, structure requiring both families) and lands on the same
calendar day as BA §11's own earliest `confirmed_at`. AV's report independently records that a
180-day window produced zero confirmations for exactly this reason. Two caveats: BA §11's dates cover
**resolved** outcomes only, so this document has not directly verified that no `CONFIRMED` row exists
before 2026-06-22 — the code argument, not the date table, is what establishes that. And the exact
first-eligible instant depends on weekly candle alignment to within a few days. Neither caveat changes
the order of magnitude: the usable window is weeks, not months.

**"The design-effect table (§9.2) assumes `ρ`. Isn't that inventing evidence?"** It would be if
presented as measured. It is presented as a sensitivity analysis over an explicitly assumed parameter,
with the assumption named in the table and the un-assumed `deff = 1` row shown alongside. The
underlying facts — 66 of 133 outcomes in 5 days, 5 co-moving symbols, 10-day overlapping evaluation
windows — are BA's and AV's own. The honest reading is: the independence assumption is contradicted by
the data's time structure, the correction has not been computed by anyone, and the effect's
significance is not robust across the plausible range. §12.2 names the measurement that would replace
the assumption.

**"Standardization (§3b) uses BA's crude marginal tables. Isn't that as flawed as the pooling it
criticizes?"** Partly. Direct standardization on published marginals is a genuine improvement on
"the sign is positive in every bucket" and on pooling raw counts across unbalanced strata, but it is
still single-variable, uses coarse buckets, and cannot address joint confounding — which §8 and §12.6
both say explicitly. It is offered as the best adjustment computable from published tables, not as an
adequate one.

**"The vote is C, but §10.4 lists five reasons the finding is credible. Isn't C too harsh?"** The
five reasons address whether an **association** exists. C addresses whether the **intervention** is
justified. Those are different questions, and the gap between them is the entire content of §5.2:
the operation under consideration has never been evaluated even in replay, using data already on
disk. A committee that approves an intervention on the strength of an association, while a direct
evaluation of the intervention remains uncomputed, has skipped a step, not made a judgement call.

**"Isn't the RQ5 answer (§7) just a semantic point?"** No, and this document should be judged on
whether the distinction changes anything. It does: under Story 2 the informative variable is
displacement from the level, which a cap on *age* only crudely proxies; under Story 3 the informative
variable is setup-formation coherence, which a cap on age proxies worse still. If either dominates,
D1 is a blunt instrument aimed at the wrong quantity, and the correct measurement (§12.4, §12.5) is
cheap. That is a substantive consequence, not a naming dispute.

**"Does this document simply demand impossible certainty?"** No, and §10.5 is the test of that: it
names what would move the vote to B (two measurements, both obtainable from cached data) and to A. If
those conditions were unreachable in principle, the criticism would land. They are not: three of the
four Tier-1/Tier-2 items require no new market data at all. The only genuinely blocked item is
out-of-sample replication (§11.2.1), and the vote does not depend on it — C rather than B is decided
by items 1 and 2, both of which are computable.

**"This document quotes BA against itself throughout. Is that fair to BA?"** BA is unusually candid;
several of the objections here are sharpened versions of objections BA raised first (its §16, §17,
§18). Where this document adds something BA did not have, it says so: the 43-day window (§2.3), the
5-day burst decomposition (§6.4), standardization (§3b), the z-statistics and design-effect
sensitivity (§9), the row-deletion-vs-replay distinction (§5.2), the RR 0–1 instability (§8.1), the
3-family wipeout (§6.2), and the expectancy gap (§4, item 2). BA's restraint in stopping before a
decision looks, on this review, well judged.

---

## 14. Errata found in the evidence base

Recorded because a committee should know the audit's exceptions, and because both are cited in
arguments about universality. Neither changes any conclusion.

1. **BA §6 and §16 mis-cite the RR 0–1 bucket's size as "33 of the 133 resolved outcomes, §3 RQ5 in
   AY's own terms."** AY §3 RQ5 gives the RR 0–1 bucket as `n_resolved = 51`; **33** is AY's RR **5+**
   bucket, and is also coincidentally the fresh+stale subtotal in BA's own RR 0–1 row (16 + 17). The
   qualitative claim — that RR 0–1 is the largest RR bucket — is correct at 51 of 133. Only the
   figure is wrong. §8.1 supersedes the surrounding argument for a separate reason.
2. **BA §2.2 introduces a bulleted list as "Two further internal cross-checks" and then lists three.**
   Cosmetic; all three checks are reported and all three pass.

Two apparent discrepancies that are **not** errata, examined and cleared: AZ's 24-row `stale × RR 5+`
leaf against AY's 27-row equivalent cell reconciles exactly as a stale-definition difference — AZ and
BA both use ages 3–10 (n=93), AY's §5.2 cluster uses a cut that admits three further rows — and AZ's
own red team already identifies this correctly. And BA §11's quarter boundaries appear to overlap on
shared dates (Q1 ends and Q2 begins 2026-07-19); this is boundary-date display, not double counting,
since the quarters' counts sum to 133 and their fresh/stale marginals recover 40/53 exactly.

---

## Appendix A — arithmetic, reproducible by hand

Every computation below uses only counts published in BA, AY or AZ. No dataset was read.

### A.1 Recovering the middle age band (ages 3–5)

AZ §6's tree publishes ages 3–10 (`stale`, n=93); BA §6 publishes ages 6–10 (n=53). Subtraction gives
ages 3–5 per RR bucket:

| RR bucket | AZ 3–10 (n / wins) | BA 6–10 (n / wins) | Ages 3–5 (n / wins) |
|---|---|---|---|
| 0–1 | 36 / 25 | 17 / 14 | 19 / 11 |
| 1–2 | 16 / 4 | 12 / 3 | 4 / 1 |
| 2–3 | 8 / 5 | 3 / 2 | 5 / 3 |
| 3–5 | 9 / 2 | 7 / 1 | 2 / 1 |
| 5+ | 24 / 0 | 14 / 0 | 10 / 0 |
| **Total** | **93 / 36** | **53 / 20** | **40 / 16** |

The recovered total (40 rows, 16 wins, 40.0%) equals BA §4's independently published MID row exactly.
This is the cross-document consistency check §2.2 relies on. The RR 0–1 column gives §8.1's 19 / 11 =
57.9%.

LOSO check (BA §10) by subtraction from BA §9, e.g. removing ETHUSDT: fresh 40 − 6 = 34, wins 26 − 5 =
21 → 61.8%; stale 53 − 13 = 40, wins 20 − 9 = 11 → 27.5%; difference +34.3 pt. Matches BA §10. All
five removals check the same way.

### A.2 Direct standardization

Weight each stratum by its pooled share `w_i = (fresh_i + stale_i) / 93`, then compute
`Σ w_i · rate_i` for each arm. Target-distance example (BA §8):

| Bucket | fresh n / rate | stale n / rate | `w_i` | fresh contribution | stale contribution |
|---|---|---|---|---|---|
| Near | 13 / 0.923 | 13 / 0.769 | 26/93 = 0.2796 | 0.2581 | 0.2150 |
| Near–mid | 9 / 0.333 | 15 / 0.400 | 24/93 = 0.2581 | 0.0860 | 0.1032 |
| Mid–far | 10 / 0.600 | 15 / 0.133 | 25/93 = 0.2688 | 0.1613 | 0.0358 |
| Far | 8 / 0.625 | 10 / 0.200 | 18/93 = 0.1935 | 0.1209 | 0.0387 |
| **Standardized** | | | **1.000** | **0.6263** | **0.3927** |

Difference +23.4 pt. Identically over BA §6 (RR): 0.6537 vs 0.4093 → +24.4 pt. Over BA §7 (stop):
0.6453 vs 0.3785 → +26.7 pt. Over BA §9 (symbol): 0.6582 vs 0.3625 → +29.5 pt.

### A.3 Two-sample z on the primary contrast

`p₁ = 26/40 = 0.650`, `p₂ = 20/53 = 0.3774`.
`SE = √(0.650·0.350/40 + 0.3774·0.6226/53) = √(0.005688 + 0.004431) = √0.010119 = 0.1006`.
`z = 0.2726 / 0.1006 = 2.71` → nominal two-sided `p ≈ 0.0067`. 95% CI: `0.2726 ± 1.96·0.1006` =
**[0.075, 0.470]**.

Decision-relevant cut: `p₁ = 26/40 = 0.650`, `p₂ = 36/93 = 0.3871`.
`SE = √(0.005688 + 0.3871·0.6129/93) = √(0.005688 + 0.002551) = 0.0908`; `z = 0.2629/0.0908 = 2.90`
→ `p ≈ 0.0037`; 95% CI **[0.085, 0.441]**.

### A.4 Frequency within the usable window

133 resolved outcomes over 43 usable days (2026-06-22→2026-08-03, §2.3) across the ten-symbol
universe = **3.09 resolved outcomes per day**. At cap 2's retained 40 rows = **0.93 per day**, a
69.9% reduction. Both figures are within-window rates over the measured period, not annualized
projections, and the post-cap figure is a row-deletion count, not the count D1 would produce (§5.2).

### A.5 Burst decomposition

From BA §11's quarters (Q2 = 2026-07-19→07-20, Q3 = 2026-07-21→07-23; win counts recovered by
multiplying each cell's n by its published rate, each landing on an integer):

| | Q1 | Q2 | Q3 | Q4 | Burst (Q2+Q3) | Non-burst (Q1+Q4) |
|---|---|---|---|---|---|---|
| Fresh n / wins | 12 / 7 | 15 / 13 | 4 / 1 | 9 / 5 | **19 / 14 = 73.7%** | **21 / 12 = 57.1%** |
| Stale n / wins | 10 / 5 | 7 / 3 | 19 / 7 | 17 / 5 | **26 / 10 = 38.5%** | **27 / 10 = 37.0%** |
| Difference | +8.3 | +43.8 | −11.8 | +26.1 | **+35.2 pt** | **+20.1 pt** |

Marginals recover exactly: fresh 19 + 21 = 40 with 14 + 12 = 26 wins; stale 26 + 27 = 53 with
10 + 10 = 20 wins. The burst spans 5 calendar days and holds 45 of the 93 fresh/stale rows (48.4%),
and 66 of all 133 resolved outcomes (49.6%).

### A.6 Design-effect sensitivity

`SE(deff) = SE_naive · √deff`, `SE_naive = 0.1006`; 95% CI `= 0.2726 ± 1.96 · SE(deff)`:

| `deff` | `SE` | `z` | nominal two-sided `p` | 95% CI |
|---|---|---|---|---|
| 1.0 | 0.1006 | 2.71 | 0.007 | [+0.075, +0.470] |
| 1.5 | 0.1232 | 2.21 | 0.027 | [+0.031, +0.514] |
| 2.0 | 0.1422 | 1.92 | 0.055 | [−0.006, +0.551] |
| 3.0 | 0.1742 | 1.57 | 0.117 | [−0.069, +0.614] |

`deff = 1 + (m − 1)ρ`. `m` and `ρ` are **assumed**, not measured; §12.2 names the measurement that
would replace them.

---

**Confirmation nothing else changed.** No file under `src/`, `tests/`, `docs/adr/`, `reports/`,
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md` or `CURRENT_STATE.md` was touched by this
milestone. The pre-existing untracked AP/AQ-era documents and the AV–BA research documents already
present before this milestone are unchanged. This file is the only new artifact.

**Confirmation nothing committed.** No `git add`, `git commit`, or any other git write operation was
performed as part of this milestone.

**Confirmation no recommendation is made.** This document assesses evidentiary sufficiency and
delivers the vote the brief requires (§10). It proposes no policy, no threshold, no branch, no ADR
and no implementation, and §12 names absent evidence rather than scheduling work to produce it.
