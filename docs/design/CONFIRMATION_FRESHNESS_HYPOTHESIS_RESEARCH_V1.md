# Confirmation Freshness Hypothesis Research V1

**Milestone:** BA
**Status:** Investigation complete — measurement only, no code changes
**Date:** 2026-08-10
**Model:** Claude Sonnet 5
**Repository state:** `main`, working tree unchanged by this milestone under `src/`, `tests/`,
`docs/adr/`, `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`
**Type:** Controlled strategy research, not a design record — produces no contract, no ADR, no
backlog entry, no changelog entry, no CURRENT_STATE update, no policy change, no filter proposal,
no threshold proposal, no recommendation of any kind

---

## 0. What this document is

Milestone AZ (`docs/design/FAILURE_ATTRIBUTION_RESEARCH_V1.md`) found one especially strong
interaction inside 133 historical resolved outcomes: `stale_confirmation` combined with
`poor_rr_geometry` (RR ≥ 3) and `tight_stop` co-occurred in a leaf that produced 0 wins in 24
resolved outcomes (AZ §6, RQ10). AZ also stated plainly that no single measured characteristic in
that dataset is necessary or sufficient (AZ §7), and that several of its nine failure categories are
"correlated restatements of the same underlying geometry rather than nine independent signals" (AZ
§9.3).

This document isolates one variable from that interaction — **confirmation freshness** — and asks
whether it carries real incremental information on its own, or whether the apparent relationship
between confirmation age and outcome collapses once RR geometry, stop distance, target distance,
symbol concentration, direction and time period are accounted for. It is not a new backtest and not
a new metric: every number below is drawn from a sixth independent live draw over the identical
population AV/AW/AX/AY/AZ already measured (§2), reconciled exactly against their published counts.

**No recommendation anywhere in this document.** No sentence says a confirmation-age cap should
change, that a threshold is "better," or that production should do anything differently. §15–§16
report what supports and contradicts the hypothesis; §19 states plainly what can and cannot be
concluded.

---

## 1. Research question and preregistered hypothesis

**H1 (alternative):** Fresher confirmations produce better historical outcomes than stale
confirmations, in the existing, unmodified 133-row resolved-outcome population.

**H0 (null):** Any observed fresh-vs-stale difference is sample noise, symbol concentration, RR
geometry, stop distance, or another confounder — not a property of freshness itself.

This document's job is to try to falsify H1, not to prove it (per the brief).

### 1.1 Predeclared comparison discipline

Following AY/AZ's own multiple-comparison discipline (AY §10.7, AZ §9.5), every comparison below is
labelled one of three tiers, declared here before any table is read:

- **PRIMARY:** fresh (confirmation age 0–2 bars) vs. stale (confirmation age 6–10 bars), on the full
  133-row resolved population. One comparison. This is the headline test H1/H0 above is framed
  against.
- **SECONDARY:** the exact-age trend (§3), and every confounder-stratified fresh-vs-stale comparison
  (RR bucket, stop-distance bucket, target-distance bucket, symbol, LOSO, temporal half/quarter,
  direction, evidence-family count, regime dimension) — each answers "does the primary comparison
  survive controlling for X," not a new hypothesis.
- **EXPLORATORY:** everything else — the matched-comparison cells, the counterfactual age-cap
  sensitivity sweep, cross-tabulations of population mix, and the red-team checks. These describe
  the data; they are not additional tests of H1.

### 1.2 Statistical significance test

**No formal p-value significance test (chi-square, Fisher's exact, etc.) is used anywhere in this
document**, declared here before any result was computed, for the same reason AY/AZ gave: at
`n_resolved = 133` split across dozens of strata, many cells have `n < 20`, and a battery of
significance tests across that many comparisons without correction would produce exactly the
"significant-looking" noise this milestone's own multiple-comparison-discipline section warns
against. Instead, every comparison reports: **absolute rate difference, relative risk, odds ratio
(where denominators permit), and 95% Wilson score confidence intervals** — the same convention
AV/AW/AX/AY/AZ already used. A comparison is treated as "the confidence intervals do not overlap" or
"the confidence intervals overlap substantially" rather than "significant" or "not significant" —
Wilson CI overlap is a weaker, more conservative signal than a two-sample test would give, which is
the tradeoff this document accepts explicitly rather than silently.

**Limitation of this convention, stated up front:** CI-overlap reasoning is conservative (it under-
rejects) but is not equivalent to a hypothesis test with a stated significance level, and non-
overlapping CIs are not a formal p<0.05 claim. Every number below should be read with that in mind.

---

## 2. Dataset reconciliation

### 2.1 Method

One fresh, read-only extraction (`ba_extract.py`), mirroring
`fmis.swing_setup.backtest_harness.run_backtest`'s own instant-by-instant replay loop exactly — same
replay transport, same clock, same `IdentityTracker`, same call to
`setup_inputs_and_assessment_for_sheet`, same call to `evaluate_outcome` at `is_first_confirmation`
— identical precedent to AW/AX/AY/AZ's own extraction scripts (their own scripts, described in each
document's own Appendix, none shipped into the repository). This script lived outside the
repository, in a scratch directory (Appendix).

Beyond the replay loop itself, the script makes the same class of additional read-only calls to
already-public, already-used pure functions that AY/AZ's own scripts made, to recover facts the
production `HistoricalObservation`/`SetupOutcome` models compute internally but do not persist:
`regime_for_sheet` on the SETUP and EXECUTION role sheets (AY/AZ precedent), `regime_input_from_sheet`
for `atr_fast`/`close` per role, `assessment.trigger.bar_index` combined with
`inputs.execution_closed_count` for `break_age` (identical arithmetic to `policy.py:344-348`), and
`assessment.risk_reward.risk`/`.reward` for stop-distance/target-distance as a fraction of reference
price. No production module is imported differently than `run_backtest` already imports it, and
nothing under `src/` was changed.

Ten symbols (`DEFAULT_BACKTEST_SYMBOLS`): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT,
ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT. Real public Binance spot data, `2025-07-04` to `2026-08-07`
(400 days), `run_at=2026-08-10T00:00:00+00:00` — the identical window and symbol universe every
milestone in this series has used.

### 2.2 Reconciliation against AV/AW/AX/AY/AZ

| | This run (BA) | AZ | AY | AX | AW |
|---|---|---|---|---|---|
| Total observations | **21,680** | 21,680 | 21,680 | 21,680 | 21,680 |
| WAIT | 21,102 | 21,102 | 21,102 | 21,102 | 21,102 |
| CANDIDATE (rows) | 401 | 401 | 401 | 401 | 401 |
| CONFIRMED (rows) | 177 | 177 | 177 | 177 | 177 |
| Evaluated outcomes | 146 | 146 | 146 | 146 | — |
| TARGET_FIRST | 62 | 62 | 62 | 62 | — |
| STOP_FIRST | 71 | 71 | 71 | 71 | — |
| AMBIGUOUS_SAME_BAR | 5 | 5 | 5 | 5 | — |
| NEITHER_WITHIN_WINDOW | 8 | 8 | 8 | 8 | — |

Byte-identical to AZ/AY/AX's own numbers. Resolved outcomes (`TARGET_FIRST + STOP_FIRST`): **133**
(62 + 71), the identical denominator AY/AZ used throughout.

**Two further internal cross-checks performed before trusting the extraction, both passing exactly:**

- **Exact-age distribution** reproduces AY's own §3 RQ8 table exactly, row for row: ages 0–10 carry
  n = 12, 12, 16, 14, 14, 12, 11, 13, 10, 9, 10 respectively (sum 133), with win counts 6, 9, 11, 5,
  5, 6, 5, 6, 4, 2, 3 — identical to AY's published table to the integer.
- **Symbol population** reproduces AY §2.3 and AZ §2.3 exactly: DOTUSDT 52, ETHUSDT 26, ADAUSDT 23,
  BTCUSDT 16, LINKUSDT 16 resolved outcomes; the other five symbols (SOLUSDT, BNBUSDT, XRPUSDT,
  DOGEUSDT, AVAXUSDT) contribute zero, identical to every prior milestone in this series.
- **Correlation cross-check**, the same discipline AZ §1.2/§2.2 used: this document's own five
  independently computed point-biserial correlations over the 133 resolved outcomes reproduce AY's
  published values to the precision AY itself reported — RR r=−0.2999 (AY: −0.30), stop-distance
  r=+0.4112 (AY: +0.41), target-distance r=−0.3200 (AY: −0.32), confirmation age r=−0.2027 (AY:
  −0.20). Four of four match.

**Counts reconcile exactly. No investigation of a mismatch was required (the brief's own
stop-and-investigate condition never triggered).**

### 2.3 Inherited limitations

Every limitation `BACKTEST_LIMITATIONS` (AV-1 through AV-9) and every limitation AW §2.4/AX §2.3/AY
§2.4/AZ §2.4 name applies unchanged: no fees/slippage/spread modelled, `TARGET_FIRST`/`STOP_FIRST`
are wick-touch classifications and never a win rate in the trading sense, `AMBIGUOUS_SAME_BAR` is a
refusal to guess intrabar order, the 60-bar evaluation window is a stated measurement policy, and
every RR figure restates the printed R:R at confirmation, never a realized return. This document
adds no new limitation of its own.

---

## 3. Exact-age results

Resolved outcomes at every observed confirmation age, 0–10 bars — the entire reachable range, since
`CONFIRMATION_LOOKBACK_BARS = 10` is a hard policy ceiling (AY §7) that this milestone does not move:

| Age (bars) | n | TARGET_FIRST | STOP_FIRST | Target-first rate | 95% Wilson CI | Mean RR | Median RR | Median stop% | Median target% |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 12 | 6 | 6 | 50.0% | 25.4%–74.6% | 6.14 | 2.21 | 1.17% | 2.11% |
| 1 | 12 | 9 | 3 | 75.0% | 46.8%–91.1% | 5.96 | 2.38 | 1.19% | 1.78% |
| 2 | 16 | 11 | 5 | 68.75% | 44.4%–85.8% | 2.19 | 0.61 | 1.59% | 0.83% |
| 3 | 14 | 5 | 9 | 35.7% | 16.3%–61.2% | 4.23 | 1.26 | 1.46% | 2.33% |
| 4 | 14 | 5 | 9 | 35.7% | 16.3%–61.2% | 4.43 | 1.51 | 1.58% | 1.75% |
| 5 | 12 | 6 | 6 | 50.0% | 25.4%–74.6% | 6.95 | 0.81 | 1.47% | 1.91% |
| 6 | 11 | 5 | 6 | 45.5% | 21.3%–72.0% | 4.87 | 1.40 | 1.33% | 1.72% |
| 7 | 13 | 6 | 7 | 46.2% | 23.2%–70.9% | 8.54 | 1.24 | 1.71% | 1.09% |
| 8 | 10 | 4 | 6 | 40.0% | 16.8%–68.7% | 1.65 | 1.34 | 1.32% | 1.51% |
| 9 | 9 | 2 | 7 | 22.2% | 6.3%–54.7% | 3.36 | 3.09 | 1.15% | 1.71% |
| 10 | 10 | 3 | 7 | 30.0% | 10.8%–60.3% | 6.72 | 5.17 | 0.54% | 2.08% |

Roughly even distribution across all 11 ages (9–16 per bucket) — not a sample piling up at "fresh,"
matching AY's own observation. No bucket sums are re-merged in this table.

### 3.1 Monotonicity test

- **Point-biserial correlation** between confirmation age and resolved outcome (win=1/loss=0):
  **r = −0.2027** (n=133) — reproduces AY's published −0.20 exactly (§2.2). A mild, not negligible,
  negative relationship.
- **Spearman rank correlation** between age and outcome: **ρ = −0.0451** (n=133) — far weaker than
  the Pearson figure.
- **Reading both together:** the relationship is **not close to monotonic**. Ages 0–2 (ρ toward
  freshness) carry the three highest win rates in the table (50.0%, 75.0%, 68.75%); ages 3–10
  fluctuate between 22.2% and 50.0% with no consistent downward trend inside that range (age 5:
  50.0%, age 9: 22.2%, age 10: 30.0% — age 10 is *not* the lowest). The Pearson correlation's
  negative sign is driven substantially by the **fresh end sitting well above the rest**, not by a
  smooth, ordinal decay across all eleven ages — a materially different shape than "each additional
  bar of staleness makes an outcome a little worse." §4 restates this using the brief's own
  three-bucket cut, where the shape is more visible.

---

## 4. Fresh / Mid / Stale comparison

Predeclared buckets, not chosen from results (§0's brief specifies these verbatim):

| Bucket | Age range | n | TARGET_FIRST | STOP_FIRST | Target-first rate | 95% Wilson CI |
|---|---|---|---|---|---|---|
| FRESH | 0–2 | 40 | 26 | 14 | 65.0% | 49.5%–77.9% |
| MID | 3–5 | 40 | 16 | 24 | 40.0% | 26.3%–55.4% |
| STALE | 6–10 | 53 | 20 | 33 | 37.7% | 25.9%–51.2% |

FRESH sits well above MID and STALE; MID and STALE are close to each other (40.0% vs. 37.7%, heavily
overlapping CIs) — the three-bucket view shows the same shape §3.1 found: most of the apparent
"freshness effect" is FRESH-vs-everything-else, not a smooth staircase across all three buckets.

### PRIMARY comparison: FRESH (0–2) vs. STALE (6–10)

| | n | TARGET_FIRST | Rate | 95% Wilson CI |
|---|---|---|---|---|
| Fresh | 40 | 26 | 65.00% | 49.51%–77.87% |
| Stale | 53 | 20 | 37.74% | 25.94%–51.19% |

Confidence intervals do **not** overlap.

---

## 5. Effect sizes

For the PRIMARY comparison (FRESH 0–2 vs. STALE 6–10):

- **Absolute target-first-rate difference:** +27.26 percentage points (65.00% − 37.74%).
- **Relative risk** (fresh rate ÷ stale rate): **1.72×**.
- **Odds ratio:** **3.06** (26 fresh-wins × 33 stale-losses ÷ 14 fresh-losses × 20 stale-wins).
- **95% Wilson CIs:** fresh 49.51%–77.87%; stale 25.94%–51.19% — non-overlapping.

### 5.1 Matched comparison (EXPLORATORY)

Deterministic matched groups — same symbol, same side, same RR bucket (§6's five buckets), same
stop-distance bucket (§7's four buckets, AY's own edges) — differing only in confirmation freshness.
No clustering algorithm; plain equality grouping.

**16 matched strata** contain both a fresh (0–2) and a stale (6–10) observation. Individual strata
are small (n=1–4 each, most below the `n≥10` smallness floor this document otherwise applies — shown
in full in the Appendix data, not reproduced cell-by-cell here because every cell is too small to
read alone) but pooling across all 16 strata:

| | n | wins | rate | 95% Wilson CI |
|---|---|---|---|---|
| Matched-fresh | 29 | 18 | 62.07% | 44.00%–77.31% |
| Matched-stale | 30 | 10 | 33.33% | 19.23%–51.22% |

Absolute difference +28.7 points — closely matching the unmatched PRIMARY comparison's +27.3 points.
**The deterministic match, holding symbol/side/RR-bucket/stop-bucket fixed, does not shrink the
effect** (§9 returns to how much weight this can bear given per-stratum sample sizes).

---

## 6. RR-controlled results (SECONDARY)

Fresh vs. stale, stratified by displayed RR bucket (AY's own edges, §3 RQ5):

| RR bucket | Fresh n / win / rate | Stale n / win / rate | Absolute diff |
|---|---|---|---|
| 0–1 | 16 / 13 / 81.2% | 17 / 14 / 82.4% | −1.1 pt |
| 1–2 | 6 / 5 / 83.3% | 12 / 3 / 25.0% | +58.3 pt |
| 2–3 | 4 / 1 / 25.0% | 3 / 2 / 66.7% | −41.7 pt (n<10 both sides) |
| 3–5 | 5 / 4 / 80.0% | 7 / 1 / 14.3% | +65.7 pt |
| 5+ | 9 / 3 / 33.3% | 14 / 0 / 0.0% | +33.3 pt |

**RR interaction, answering the brief's own questions directly:**

- **RR < 2** (n=51 total): fresh 81.8% (n=22) vs. stale 58.6% (n=29), diff **+23.2 pt**. Freshness
  still shows a positive gap below RR 2, though CIs overlap (fresh 61.5%–92.7%, stale 40.7%–74.5%).
- **RR 2–5** (n=19 total): fresh 55.6% (n=9) vs. stale 30.0% (n=10), diff **+25.6 pt**.
- **RR ≥ 5 only** (n=23 total): fresh 33.3% (n=9) vs. stale 0.0% (n=14), diff **+33.3 pt** — the
  single most extreme cell, reproducing AY §5.2's and AZ §6's own finding that stale confirmation
  combined with RR ≥ 5 lost every time (this extraction's own stale-3-10 × RR≥5 cell: n=24, 0 wins,
  0.0%, matching AZ's published 24-row/0-win cluster exactly; this document's own predeclared
  stale-6-10 × RR≥5 cell: n=14, 0 wins).
- **Excluding RR ≥ 5 entirely** (RR < 5, n=70 total): fresh 74.2% (n=31) vs. stale 51.3% (n=39), diff
  **+22.9 pt**. **The effect is not entirely driven by the extreme RR ≥ 5 geometry** — removing it
  shrinks the primary gap only modestly (27.3 pt → 22.9 pt), and the direction is unchanged.
- **The one bucket where freshness shows no effect at all is RR 0–1** — the single largest RR bucket
  by volume (33 of the 133 resolved outcomes, §3 RQ5 in AY's own terms), where fresh and stale are
  statistically indistinguishable (81.2% vs. 82.4%). **The aggregate PRIMARY effect is materially a
  property of RR ≥ 1, not RR 0–1** — an important qualifier §15/§16 both return to.

---

## 7. Stop-distance-controlled results (SECONDARY)

Fresh vs. stale, stratified by stop-distance bucket (AY's own quartile edges, §3 RQ6):

| Stop bucket | Fresh n / win / rate | Stale n / win / rate | Absolute diff |
|---|---|---|---|
| Very tight (≤0.48%) | 9 / 4 / 44.4% | 12 / 0 / 0.0% | +44.4 pt |
| Tight–medium (0.48–1.35%) | 11 / 6 / 54.5% | 18 / 4 / 22.2% | +32.3 pt |
| Medium–wide (1.35–2.68%) | 12 / 9 / 75.0% | 10 / 5 / 50.0% | +25.0 pt |
| Very wide (>2.68%) | 8 / 7 / 87.5% | 13 / 11 / 84.6% | +2.9 pt |

**Stop-distance interaction:**

- **Excluding very-tight stops** (n=72 total): fresh 71.0% (n=31) vs. stale 48.8% (n=41), diff
  **+22.2 pt** — the freshness gap persists once the tightest-stop quartile is removed, only slightly
  smaller than the unconstrained primary gap (27.3 pt).
- **Very-tight stops only** (n=21 total): fresh 44.4% (n=9) vs. stale 0.0% (n=12) — the single most
  extreme stop-distance cell, diff **+44.4 pt**.
- **Very-wide stops** show almost no freshness effect (87.5% vs. 84.6%, diff +2.9 pt) — mirroring
  §6's finding at the RR-0–1 end: freshness matters far less, or not at all, at the "easiest"
  geometry (widest stop, lowest RR), and matters most where the setup's own geometry is already
  demanding (tight stop, high RR).

---

## 8. Target-distance-controlled results (SECONDARY)

Fresh vs. stale, stratified by target-distance bucket (AY's own quartile edges, §3 RQ7):

| Target bucket | Fresh n / win / rate | Stale n / win / rate | Absolute diff |
|---|---|---|---|
| Near (≤0.74%) | 13 / 12 / 92.3% | 13 / 10 / 76.9% | +15.4 pt |
| Near–mid (0.74–1.72%) | 9 / 3 / 33.3% | 15 / 6 / 40.0% | −6.7 pt |
| Mid–far (1.72–3.87%) | 10 / 6 / 60.0% | 15 / 2 / 13.3% | +46.7 pt |
| Far (>3.87%) | 8 / 5 / 62.5% | 10 / 2 / 20.0% | +42.5 pt |

**Target-distance mechanism check** (is the apparent freshness effect really just "distant targets
have more time to fail," per the brief's own question): fresh and stale outcomes carry **nearly
identical median target distances** (fresh 1.669%, stale 1.713%) and nearly identical median stop
distances (fresh 1.421%, stale 1.271%) and median RR (fresh 1.478, stale 1.444). §2.2's own
correlation cross-check already showed this at the population level: `corr(age, RR) = +0.016`,
`corr(age, stop%) = +0.005`, `corr(age, target%) = −0.035` — **all three essentially zero**. Fresh
and stale confirmations are not systematically different-geometry setups; the freshness effect is
not a relabelling of a target-distance or stop-distance effect at the population-correlation level,
though §9 and §18 (Red Team) both note the target-bucket table above (near–mid reversing sign) is not
fully clean either.

One further observed asymmetry, EXPLORATORY, not part of the freshness question directly: fresh
outcomes take longer to resolve on average (mean 4.17 bars to resolution) than stale outcomes (mean
3.09 bars) — consistent with, but not proof of, stale confirmations more often being caught by a stop
quickly rather than working toward either level gradually.

---

## 9. Symbol robustness

Fresh vs. stale, per symbol (only the five symbols that ever produced a resolved outcome):

| Symbol | Fresh n / win / rate | Stale n / win / rate | Absolute diff |
|---|---|---|---|
| ADAUSDT | 8 / 5 / 62.5% | 8 / 2 / 25.0% | +37.5 pt |
| BTCUSDT | 5 / 2 / 40.0% | 7 / 0 / 0.0% | +40.0 pt |
| DOTUSDT | 15 / 8 / 53.3% | 18 / 6 / 33.3% | +20.0 pt |
| ETHUSDT | 6 / 5 / 83.3% | 13 / 9 / 69.2% | +14.1 pt |
| LINKUSDT | 6 / 6 / 100.0% | 7 / 3 / 42.9% | +57.1 pt |

**Every one of the five outcome-bearing symbols shows a positive fresh-minus-stale difference** — no
symbol contradicts the aggregate direction, though the magnitude ranges widely (14.1 to 57.1 points)
and every per-symbol cell is small (n=5–18, below or near the `n≥10` smallness floor on both sides
for BTCUSDT, ADAUSDT, LINKUSDT). No symbol has enough resolved outcomes on both sides to draw a
symbol-specific conclusion in isolation; the value of this table is directional consistency, not
per-symbol precision.

- **Symbols supporting the aggregate finding:** all five (ADAUSDT, BTCUSDT, DOTUSDT, ETHUSDT,
  LINKUSDT) — same direction, magnitude varies.
- **Symbols contradicting it:** none.
- **Symbols with insufficient sample:** SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, AVAXUSDT produced zero
  resolved outcomes in this window (§2.1) — this document cannot say anything about freshness on
  those five symbols, not "no effect," simply no observations, identical to AY §10.2/AZ §9.2's own
  standing caveat.

---

## 10. Leave-one-symbol-out

Recomputing the PRIMARY fresh-vs-stale comparison with each outcome-bearing symbol removed in turn:

| Removed symbol | Fresh n / rate | Stale n / rate | Absolute diff |
|---|---|---|---|
| (none — baseline) | 40 / 65.0% | 53 / 37.7% | +27.3 pt |
| ADAUSDT | 32 / 65.6% | 45 / 40.0% | +25.6 pt |
| BTCUSDT | 35 / 68.6% | 46 / 43.5% | +25.1 pt |
| DOTUSDT | 25 / 72.0% | 35 / 40.0% | +32.0 pt |
| ETHUSDT | 34 / 61.8% | 40 / 27.5% | +34.3 pt |
| LINKUSDT | 34 / 58.8% | 46 / 37.0% | +21.9 pt |

**The finding survives removal of every individual symbol, including DOTUSDT** — the symbol prior
research (AY §2.3, AZ §2.3) identified as dominating the resolved population (39.1% of all resolved
outcomes). With DOTUSDT removed entirely, the fresh-stale gap is +32.0 points, if anything larger
than the +27.3-point baseline, not smaller. No leave-one-out removal collapses or reverses the
direction of the effect; the diff ranges narrowly between +21.9 and +34.3 points across all five
removals.

---

## 11. Temporal robustness

Predeclared chronological split (not chosen after seeing results — a simple first-half/second-half
cut of the 133 resolved outcomes ordered by `confirmed_at`, plus quarters where sample permits):

| Segment | n | Date range | Fresh n / rate | Stale n / rate | Absolute diff |
|---|---|---|---|---|---|
| First half | 66 | 2026-06-22 – 2026-07-20 | 27 / 74.1% | 17 / 47.1% | +27.0 pt |
| Second half | 67 | 2026-07-21 – 2026-08-03 | 13 / 46.2% | 36 / 33.3% | +12.8 pt |
| Q1 | 33 | 2026-06-22 – 2026-07-19 | 12 / 58.3% | 10 / 50.0% | +8.3 pt |
| Q2 | 33 | 2026-07-19 – 2026-07-20 | 15 / 86.7% | 7 / 42.9% | +43.8 pt |
| Q3 | 33 | 2026-07-21 – 2026-07-23 | 4 / 25.0% | 19 / 36.8% | **−11.8 pt** |
| Q4 | 34 | 2026-07-23 – 2026-08-03 | 9 / 55.6% | 17 / 29.4% | +26.1 pt |

**The effect holds in both halves** (both positive), though it is roughly half the size in the
second half (+12.8 pt) as in the first (+27.0 pt) — a real weakening, not a reversal. **At the
quarter level, one of four quarters (Q3) reverses direction** (−11.8 pt), the only reversal found
anywhere across every stratified cut in this document — but Q3's fresh cell has only 4 observations
(95% CI 4.6%–69.9%, effectively uninformative at that size), and this is exactly the kind of small,
noisy cell §9 (this document's own multiple-comparison discipline) warns against over-reading. The
three other quarters range from +8.3 to +43.8 points, all positive.

---

## 12. LONG / SHORT robustness

| Direction | Fresh n / win / rate | Stale n / win / rate | Absolute diff |
|---|---|---|---|
| LONG | 17 / 13 / 76.5% | 27 / 12 / 44.4% | +32.0 pt |
| SHORT | 23 / 13 / 56.5% | 26 / 8 / 30.8% | +25.8 pt |

**Both directions show the effect in the same direction**, LONG somewhat larger (32.0 pt) than SHORT
(25.8 pt) but both comfortably positive; freshness does not appear to help only one side. Not
averaged away — both are shown explicitly, per the brief's own instruction.

---

## 13. Evidence/regime controls (SECONDARY)

### 13.1 Evidence-family count

| Families agreeing | Fresh n / rate | Stale n / rate |
|---|---|---|
| 2 (of 3) | 40 / 65.0% | 48 / 39.6% |
| 3 (of 3) | 0 / — | 5 / 20.0% |

**Cannot be evaluated** — the 3-family stratum has zero fresh observations at all (n=0), matching
AY §3 RQ9's own finding that 3-family agreement is rare (5 of 133 resolved outcomes total). This
document cannot say whether freshness matters inside the 3-family stratum; it can only report the
2-family stratum, which shows the same +25.4-point direction as the aggregate.

### 13.2 Regime dimensions (context / setup / execution × structure / volatility / participation)

Every regime state with `n≥5` on both the fresh and stale side (full table in the Appendix data;
summarized here):

- **Direction of the fresh-vs-stale gap is positive (fresh wins more) in the large majority of
  regime-state cells checked** — context-role trending/contracting/subdued/typical, setup-role
  transitioning/trending/contracting/steady/elevated/subdued/typical, execution-role
  indeterminate/transitioning/trending/steady/elevated/subdued/typical all show a positive diff,
  ranging from +10.5 to +59.6 points.
- **Two small cells reverse direction**, both with `n<10` on at least one side: context-role
  volatility `INSUFFICIENT` (fresh 80.0% n=5 vs. stale 100.0% n=4, diff −20.0 pt — this is AY §6.2's
  own known 16-row, single-symbol, single-week DOTUSDT artifact, inherited unchanged here) and
  execution-role structure `ranging` (fresh n=0, stale 33.3% n=3 — no fresh observation exists in
  this cell, not a real reversal).
- **No regime dimension or state, at a sample size large enough to read, contradicts the aggregate
  finding.**

---

## 14. Counterfactual age-cap sensitivity

**Research/sensitivity only — no production policy change, per the brief's own repeated
instruction.** For each hypothetical maximum accepted confirmation age, this section reports what
the historical sample would look like if that cap had governed which candidates could confirm at
all:

| Cap (bars) | Retained | Removed | TARGET_FIRST | STOP_FIRST | Rate | 95% Wilson CI | Mean RR | Median RR | Symbols retained | Side mix |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 12 | 121 | 6 | 6 | 50.0% | 25.4%–74.6% | 6.14 | 2.21 | all 5 | 5L / 7S |
| 1 | 24 | 109 | 15 | 9 | 62.5% | 42.7%–78.8% | 6.05 | 2.21 | all 5 | 11L / 13S |
| 2 | 40 | 93 | 26 | 14 | 65.0% | 49.5%–77.9% | 4.51 | 1.48 | all 5 | 17L / 23S |
| 3 | 54 | 79 | 31 | 23 | 57.4% | 44.2%–69.7% | 4.44 | 1.45 | all 5 | 22L / 32S |
| 5 | 80 | 53 | 42 | 38 | 52.5% | 41.7%–63.1% | 4.81 | 1.39 | all 5 | 31L / 49S |
| 10 (baseline) | 133 | 0 | 62 | 71 | 46.6% | 38.4%–55.1% | 4.99 | 1.43 | all 5 | 58L / 75S |

**Critical survivorship caveat, restated per the brief's own instruction:** the retained subset's
target-first rate is not monotonically decreasing as the cap widens (cap 1 → cap 2 rises from 62.5%
to 65.0% before declining), and every row above discards a different-sized, differently-composed
sample — cap 0 discards 121 of 133 resolved outcomes (91.0% of the population), cap 2 discards 93
(69.9%). A tighter cap is not shown here as "better": it is shown as **retaining fewer setups, a
similar symbol mix (all five outcome-bearing symbols persist even at cap 0), and a similar side mix
proportion**, alongside a higher observed historical rate on a much smaller sample. The `n=12` cell
at cap 0 has a 95% CI spanning 25.4%–74.6% — wide enough that this table cannot distinguish "cap 0 is
genuinely better" from "cap 0 is a 12-observation sample." This is sensitivity analysis, not a
recommendation, exactly as instructed.

---

## 15. What supports H1

- The PRIMARY comparison shows a large, non-overlapping-CI gap: fresh 65.0% vs. stale 37.7%
  (+27.3 points, relative risk 1.72×, odds ratio 3.06) — §4, §5.
- The gap **survives every robustness check performed**: RR-bucket stratification (positive in 4 of
  5 buckets, tied in the largest), stop-distance stratification (positive in all 4 buckets), symbol
  stratification (positive in all 5 outcome-bearing symbols), leave-one-symbol-out (positive after
  removing any single symbol, including DOTUSDT, where it is if anything larger), both temporal
  halves (positive, though smaller in the second half), both directions (LONG and SHORT both
  positive), and the deterministic matched comparison (+28.7 points, closely matching the unmatched
  estimate) — §6–§12, §5.1.
- **Age is not meaningfully correlated with RR, stop distance, or target distance at the population
  level** (`r` all within ±0.04 of zero, §2.2/§8) — the mechanical "stale just means different
  geometry" explanation that AY/AZ flagged as a standing threat for RR/stop/target correlations does
  not appear to apply to confirmation age the same way.
- Excluding the most extreme RR≥5 geometry, and excluding the tightest stop-distance quartile, both
  shrink the gap only modestly (27.3 pt → 22.9 pt and → 22.2 pt respectively) rather than eliminating
  it — §6, §7.
- The exact-age table's fresh end (ages 0–2: 50.0%, 75.0%, 68.75%) sits clearly above the rest of the
  range in every case — §3.

## 16. What contradicts H1

- **The relationship is not monotonic.** Spearman rank correlation (age, outcome) is only −0.045,
  far weaker than the Pearson point-biserial (−0.20); ages 3–10 do not show a consistent decline —
  age 5 (50.0%) sits above age 3, 4, 6, 7, 8, 9, and 10 alike, and age 10 is not the single worst age
  (age 9 is) — §3.1.
- **The effect is concentrated in RR ≥ 1; it disappears entirely at RR 0–1**, the single largest RR
  bucket by volume (33 of 133 resolved outcomes) — fresh 81.2% vs. stale 82.4%, a −1.1-point
  difference indistinguishable from zero — §6. The same pattern repeats at the widest stop-distance
  quartile (fresh 87.5% vs. stale 84.6%, +2.9 pt) — §7. **Freshness appears to matter mainly where a
  setup's own geometry is already demanding (tight stop, high RR), not universally.**
- **One temporal quarter (Q3) reverses direction** (−11.8 pt), the only reversal in the entire
  document, though on a 4-observation fresh cell too small to weigh heavily — §11.
- The 3-family-agreement evidence stratum cannot be tested at all (zero fresh observations, §13.1) —
  H1 is untested, not confirmed, in that stratum.
- Every individual per-symbol cell (§9) and every matched stratum (§5.1) is small (most `n<20`,
  several `n<10` or even `n<5`); the aggregate direction is consistent, but no single stratified cell
  in this document reaches a sample size that would be persuasive on its own.

---

## 17. Threats to validity

Every table above should be read through this section, following AY §10/AZ §9's own discipline.

1. **DOTUSDT dominance, inherited unchanged.** 39.1% of the 133 resolved outcomes this document
   segments come from one symbol. §10's leave-one-out result (effect survives, even strengthens,
   without DOTUSDT) is the strongest available mitigation, but the underlying population is still one
   symbol-heavy 400-day window.
2. **Five of ten backtested symbols contributed zero evaluated outcomes.** Every finding here
   describes five symbols' price paths, not "the market."
3. **Within-symbol outcomes are not independent trials.** Consecutive confirmed setups on the same
   symbol during one sustained directional stretch share the same underlying price path — the same
   caveat AY §10.3/AZ §9.3 raised.
4. **RR is algebraically derived from stop distance and target distance** (AY §11, AZ §9.3
   restatement) — three of this document's own stratification axes (§6, §7, §8) are, to a first
   approximation, two underlying measurements read three times, so treating agreement across all
   three as three independent confirmations would overstate the robustness check.
5. **Small strata throughout.** Every RR-bucket, stop-bucket, target-bucket, symbol, temporal-quarter
   and matched-comparison cell in §6–§11 is well below the `n≥30` size that would let a Wilson CI
   narrow meaningfully; several are below `n=10`, flagged inline where relevant. The aggregate
   consistency across strata (§15) is the strongest evidence this document has; no single stratified
   cell is, by itself, strong evidence.
6. **Multiple comparisons were not corrected for**, per §1.2's own stated discipline — inherited from
   every prior milestone in this series rather than fixed here.
7. **The window itself (400 days, 2025-07-04 to 2026-08-07) is the same single window every milestone
   in this series has used**, for the structural reason AV originally stated (weekly EMA-50 warm-up).
   Every finding here inherits whatever was idiosyncratic about crypto markets during that period.
8. **A wider stop is, by construction, harder for price to reach before a target; a nearer target is,
   by construction, easier to touch** (AY §10.5) — this document's stop/target-distance-controlled
   comparisons (§7, §8) cannot fully separate genuine directional-evidence signal from pure
   touch-probability geometry, the same limitation AY/AZ both name for their own RR/stop/target
   findings.
9. **`AMBIGUOUS_SAME_BAR` and `NEITHER_WITHIN_WINDOW` outcomes (13 of 146 evaluated outcomes) are
   excluded from every table in this document**, matching AV/AW/AX/AY/AZ's own convention — a wick
   touching both levels on the same bar, or neither level within the 60-bar window, is not folded
   into either side of the freshness comparison.

---

## 18. Red Team

**Attacking this document's own strongest claim — that confirmation freshness carries real
incremental information.**

- *"The correlations between age and RR/stop/target are all near zero at the population level — but
  is that also true specifically between the fresh and stale groups the PRIMARY comparison uses?"*
  Partially, not fully. §8 shows fresh and stale groups have nearly identical **median** RR
  (1.478 vs. 1.444), stop distance (1.421% vs. 1.271%) and target distance (1.669% vs. 1.713%) — close
  but not identical, and stale outcomes do carry a slightly tighter median stop and slightly farther
  median target than fresh ones, which is exactly the direction that would mechanically produce a
  *lower* stale win rate independent of freshness itself (AY §10.5's touch-probability caveat). This
  document cannot rule out that a modest fraction of the 27.3-point gap is this small compositional
  difference rather than freshness itself, even though the population-wide linear correlations
  (§2.2) are near zero.
- *"RR-bucket, stop-bucket and target-bucket controls (§6–§8) are three views of two underlying
  numbers (AY §11) — doesn't checking all three overstate how independently confirmed this finding
  is?"* Yes, exactly as §17.4 states. A reader should treat §6–§8 together as **one** confounding
  check performed three overlapping ways, not three independent confirmations — the genuinely
  independent robustness checks in this document are §9–§12 (symbol, LOSO, temporal, direction),
  which use axes unrelated to RR/stop/target geometry.
- *"Every symbol shows the same direction (§9) — doesn't that prove the finding is symbol-general?"*
  Overstated. Every symbol's own cell is small (n=5–18 per side), and DOTUSDT alone supplies nearly
  40% of the underlying population (§17.1) — "five small samples pointing the same way" is real
  evidence, strengthened by §10's leave-one-out result, but it is not five independent, adequately
  powered replications.
- *"The effect vanishes at RR 0–1, the single largest bucket (§6, §16) — doesn't that mean the
  aggregate PRIMARY finding is being driven by a minority of the data (RR≥1, 100 of 133 resolved
  rows) dressed up as a population-wide effect?"* This is the single most serious objection this
  document can raise against its own headline number. The PRIMARY comparison (§4/§5) reports an
  aggregate over all RR levels; §6 shows that aggregate is not uniform — it is real and large at
  RR≥1 and statistically indistinguishable from zero at RR 0–1. A reader who takes only §4/§5's
  headline number away from this document, without §6's qualifier, would be misled about how
  universally the freshness relationship holds.
- *"Q3's reversal (§11, −11.8 pt) — is it noise, or does it suggest the effect is period-specific and
  could reverse again in an unseen future window?"* Most likely noise (fresh n=4, CI 4.6%–69.9%) —
  but this document cannot fully rule out a genuine period effect from one 400-day window alone; §17.7
  already names this as an open, unresolved limitation of every milestone in this series, not one
  this document can close.
- *"If the finding is real, why does it not survive to the 3-family-agreement stratum (§13.1)?"* It
  is not that the finding fails there — it is that the stratum has zero fresh observations to test
  against. This is an absence of evidence, not evidence of absence, and should not be read as a
  contradiction.

---

## 19. What can and cannot be concluded

**Can be concluded, from this dataset, under this document's own stated discipline:**

- In the existing, unmodified 133-row resolved-outcome population (`2025-07-04` to `2026-08-07`, ten
  symbols, five of which ever produced a resolved outcome), setups confirmed on a fresher break
  (0–2 bars old) touched their target before their stop **more often** than setups confirmed on a
  staler break (6–10 bars old) — 65.0% vs. 37.7%, a gap that persists across every RR bucket except
  the largest single one (RR 0–1), across every stop-distance bucket except the widest, in every
  outcome-bearing symbol, after removing any single symbol (including DOTUSDT), in both chronological
  halves of the window, and in both LONG and SHORT setups.
- Confirmation age is **not** meaningfully correlated, at the population level, with RR, stop
  distance, or target distance — the freshness relationship measured here is not, at least by linear
  correlation, simply a relabelling of one of AY's already-published geometric correlations.
- The relationship between confirmation age and outcome is **not fully monotonic** across all eleven
  possible ages, and is concentrated at the fresh end of the range rather than declining steadily
  bar by bar.

**Cannot be concluded, from this dataset, under this document's own stated discipline:**

- **Whether this is a durable, causal, symbol-general property of confirmation freshness**, as
  opposed to a property of this specific 400-day window, this specific five-symbol outcome-bearing
  population, or residual confounding this document's controls did not fully separate (§18's own
  strongest objection). No experiment varying the policy was run, and none could be under this
  milestone's rules.
- **Whether the effect would replicate on a different symbol universe or window** — every
  cross-check in this document (§9–§12) is a robustness check *within* the one dataset every
  milestone in this series has used, not an out-of-sample test.
- **Any profitability, expected value, Sharpe ratio, CAGR, or trading edge.** As in AV/AW/AX/AY/AZ:
  `TARGET_FIRST` is a wick-touch classification, not realized PnL. No fees, slippage, spread or
  execution model exists anywhere in this repository. Nothing in this document is a claim that a
  freshness-based rule would be profitable, would have been profitable historically, or should
  change anything about the current, unmodified Swing Setup v1 policy.
- **Whether a confirmation-age cap of any specific value is "better."** §14 is sensitivity analysis
  over a discarded-sample tradeoff, explicitly not a recommendation, and this document makes none.

---

## Appendix — reproduction

Three scripts, none part of the shipped package, living outside the repository in a scratch
directory, calling only already-public production functions plus the identical policy arithmetic
`policy.py:344-348` performs internally:

- **`ba_extract.py`** — mirrors `fmis.swing_setup.backtest_harness.run_backtest`'s own
  instant-by-instant loop (`fetch_historical_dataset` → per symbol, per instant:
  `build_replay_transport` → `multi_timeframe_facts_for_symbol(..., features=regime_features(),
  transport=replay_transport, clock=lambda moment=instant: moment)` →
  `setup_inputs_and_assessment_for_sheet` → `IdentityTracker.observe` → `evaluate_outcome` at
  `is_first_confirmation`), with the same class of additional read-only calls AY/AZ's own scripts
  made **only at confirmation instants** (146 times, not 21,680): `regime_for_sheet` on the SETUP and
  EXECUTION role sheets, `regime_input_from_sheet` for `atr_fast`/`close` per role, and direct reads
  of `assessment.trigger.bar_index` / `assessment.risk_reward.risk`/`.reward`, already computed by
  the policy. `_decode_full_series` is reimplemented from public functions
  (`fmis.providers.binance.map_kline`, `fmis.ingest.decode_candle_series`) rather than importing
  `backtest_harness`'s own private helper of the same name, to avoid reaching for a private name
  outside the package — the identical policy AY §1.1 stated for its own extraction's private-name
  avoidance. Serializes reconciliation counts plus all 146 evaluated outcomes' per-row fields
  (confirmation age, RR, stop/target distance as a fraction of reference price, agreeing evidence
  families, symbol, direction, confirmed-at timestamp, resolution bar count, and context/setup/
  execution regime state/volatility/participation/ATR%) to `ba_dataset.json` (~170KB). Run:
  `PYTHONPATH=<repo>/src <repo>/.venv/bin/python3 ba_extract.py > ba_dataset.json` — real Binance
  data, `DEFAULT_BACKTEST_SYMBOLS`, `start=2025-07-04T00:00:00+00:00`, `end=2026-08-07T00:00:00+00:00`,
  `run_at=2026-08-10T00:00:00+00:00`. Reconciles exactly against AW's, AX's, AY's and AZ's own
  independent draws (§2.2), including on four independently recomputed correlation coefficients
  matching AY's published values to the precision AY itself reported.
- **`ba_analyze.py` / `ba_analyze2.py` / `ba_analyze3.py`** — pure-Python (stdlib `json`/`math`/
  `statistics`/`collections` only, no third-party dependency) over `ba_dataset.json`. Compute every
  table in §3–§14: Wilson 95% CIs, Pearson point-biserial and Spearman rank correlations, the
  exact-age and fresh/mid/stale tables, RR/stop-distance/target-distance-controlled comparisons
  (using AY's own published quartile edges verbatim, per this milestone's own "no new threshold"
  rule), per-symbol and leave-one-symbol-out tables, chronological half/quarter splits, LONG/SHORT
  splits, evidence-family and regime-dimension stratifications, the 16-stratum deterministic matched
  comparison, and the counterfactual age-cap sensitivity sweep. All three are read-only with respect
  to the production package; none changed a line under `src/`.

---

**Confirmation nothing else changed:** No file under `src/`, `tests/`, `docs/adr/`,
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`, or `CURRENT_STATE.md` was touched by this
milestone. The pre-existing untracked AP/AQ-era docs and the AW/AX/AY/AZ research documents already
present before this milestone are unchanged. The only new artifact is this file.

**Confirmation nothing committed:** No `git add`, `git commit`, or any other git write operation was
performed as part of this milestone.
