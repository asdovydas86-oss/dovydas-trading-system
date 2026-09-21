# Evidence Calibration & Edge Validation Research V1

**Milestone:** AX
**Status:** Investigation complete — measurement only, no code changes
**Date:** 2026-08-10
**Model:** Claude Sonnet 5
**Repository state:** `main`, working tree unchanged by this milestone under `src/`, `tests/`,
`docs/adr/`, `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md` (see §0.3)
**Type:** Research investigation, not a design record — produces no contract, no ADR, no backlog
entry, no strategy change

---

## Table of contents

- [0. What this document is](#0-what-this-document-is)
- [1. Method](#1-method)
- [2. Dataset](#2-dataset)
- [3. Measurements](#3-measurements)
- [4. Tables](#4-tables)
- [5. Correlation](#5-correlation)
- [6. Information gain](#6-information-gain)
- [7. False assumptions found](#7-false-assumptions-found)
- [8. Unexpected discoveries](#8-unexpected-discoveries)
- [9. What the repository now knows that it did not know before](#9-what-the-repository-now-knows-that-it-did-not-know-before)
- [10. Red team](#10-red-team)
- [11. Open questions](#11-open-questions)
- [Appendix — reproduction](#appendix--reproduction)

---

## 0. What this document is

### 0.1 The question

The milestone brief asks one question, restated once here because every section below answers a
piece of it: **which evidence actually creates edge?** Not "what does the code claim to check" —
what, measured, changes the outcome. Two prior research milestones set up the tools this document
uses: Milestone AV (`docs/design/SWING_SETUP_BACKTEST_V1.md`) built the deterministic historical
replay harness; Milestone AW (`docs/design/EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md`) measured
that the three evidence **families** are not independent. This milestone goes one level deeper: into
the individual evidence **observations** inside each family, and asks the same question — does this
piece of evidence, specifically, earn its place — at that finer grain, across all ten research
questions (RQ1–RQ10) the brief poses.

### 0.2 What this document is not

- **Not a strategy change.** `fmis/swing_setup/policy.py`, `fmis/decision_support/*`,
  `fmis/market_regime/*` and every other production module have a zero-line diff from this
  milestone.
- **Not a recommendation.** No sentence in this document says a threshold, a family, or an
  individual evidence field *should* change. Where a finding implies an obvious follow-up decision,
  that decision is named and left alone.
- **Not an ADR, not a backlog change, not a report under `reports/`.** This is a `docs/design/`
  research record, matching the precedent set by AW and by
  `docs/design/FMITS_INFORMATION_EDGE_RESEARCH.md`.
- **Not a claim that this window, these ten symbols, or this measurement technique generalize**
  beyond what is explicitly stated. §11 is deliberately conservative about this.

### 0.3 What changed in the repository

Nothing under `src/`, `tests/`, `docs/adr/`, `FMITS_PRODUCT_BACKLOG.md` or
`FMITS_PRODUCT_CHANGELOG.md`. This file is the only new artifact. The two analysis scripts that
produced every number in this document live outside the repository, in a scratch directory, and are
described in full in the Appendix so the work is reproducible without being shipped as product code.

---

## 1. Method

### 1.1 Data source: the unmodified production path, called an extra way

Every number in this document derives from one fresh, read-only pass over real historical Binance
data, using **only already-public production functions**, called exactly as the harness itself calls
them, with one addition. Milestone AV's `run_backtest`
(`fmis.swing_setup.backtest_harness.run_backtest`) records, per historical instant, three
family-level leans (`HistoricalObservation.directional_factors`) — but the individual evidence
**observations** that feed one of those three families (`setup_evidence_alignment`) are reduced to a
single family-level lean before they reach `HistoricalObservation`, and are not otherwise persisted.

This milestone's extraction script therefore does not call `run_backtest` itself (which cannot
return them); it mirrors `run_backtest`'s own instant-by-instant loop — the same
`multi_timeframe_facts_for_symbol`, the same `setup_inputs_and_assessment_for_sheet`, the same
`IdentityTracker`, the same `evaluate_outcome` — and, at each instant, makes **one additional
read-only call** already used internally by `fmis.swing_setup.compose._evidence_for`:
`build_evidence_report(snapshot_from_sheet(sheet.by_role[SETUP_ROLE].sheet))`. This is the exact
same pure function, over the exact same snapshot, that the production composition path itself calls
to build the `setup_evidence_alignment` family — called a second time, read-only, to keep the five
individual observations behind that one reduced value instead of discarding them. No production
module, and no line inside one, was changed to do this.

```
multi_timeframe_facts_for_symbol(symbol, transport=replay, clock=lambda: T)
        │
        ├──► setup_inputs_and_assessment_for_sheet(sheet)   ── unmodified, as run_backtest calls it
        │         └──► SetupAssessment (family-level leans only)
        │
        └──► build_evidence_report(snapshot_from_sheet(sheet.by_role[SETUP_ROLE].sheet))
                  └──► EvidenceReport (5 individual observations, this milestone's addition)
```

### 1.2 The five individual evidence observations, named once

`fmis.decision_support.build_evidence_report` (`fmis/decision_support/report.py`) classifies five
directional observations from two of the ten named evidence families
(`fmis.evidence.EvidenceFamily`) — TREND and MOMENTUM are the only two populated in this repository
today, a fact already established by `FMITS_INFORMATION_EDGE_RESEARCH.md` Part 1 stage 8 and
reproduced here as a live measurement rather than restated from that document:

| Key | Family | What it compares | Classification | Directional? |
|---|---|---|---|---|
| `price_vs_ema_fast` | TREND | close vs EMA(20) | `above`/`below`/`equal`/`unavailable` | yes |
| `price_vs_ema_slow` | TREND | close vs EMA(50) | `above`/`below`/`equal`/`unavailable` | yes |
| `ema_fast_vs_ema_slow` | TREND | EMA(20) vs EMA(50) | `above`/`below`/`equal`/`unavailable` | yes |
| `macd_vs_signal` | MOMENTUM | MACD line vs signal line | `above`/`below`/`equal`/`unavailable` | yes |
| `macd_histogram` | MOMENTUM | sign of (MACD line − signal line) | `positive`/`negative`/`zero`/`unavailable` | yes |
| `rsi_zone` | MOMENTUM | RSI(14) band | five zones | **no** — `Alignment.NOT_DIRECTIONAL` by design (`fmis/decision_support/classification.py`) |

`build_evidence_report` reduces these five directional observations to one family-level value via
`_group`/`_state` (`fmis/decision_support/report.py:328-396`): a `dominant_alignment`
(`UPWARD`/`DOWNWARD`/`NEUTRAL`) by simple majority among the directional observations, and an
`OverallState` (`WATCH`/`WAIT`/`INSUFFICIENT_DATA`). `fmis/swing_setup/policy.py::_evidence_lean`
then reduces *that* to the one `setup_evidence_alignment` lean `run_backtest` already records. This
document's contribution is everything upstream of that final reduction.

### 1.3 Definitions carried over from Milestone AW, unchanged

**Family** — one of `context_structural_trend` (CTX), `setup_structural_trend` (SETUP),
`setup_evidence_alignment` (EVID). **Lean** — `long`/`short`/`conflicting`/`unavailable`.
**Directional** — a lean or alignment of `long`/`short` (families) or `upward`/`downward`
(individual evidence fields); `conflicting`, `neutral`, `unavailable` and `not_directional` are all
non-directional, for different, stated reasons, and this document keeps all of them distinct rather
than collapsing them into one "no signal" bucket, matching AW §1.3's own reasoning. **Pairwise
agreement**, **mutual information**, and **chance-corrected agreement (κ)** are defined exactly as
in AW §1.3, extended here from 3 signals (the families) to 8 (the three families plus the five
individual evidence fields). One deliberate methodological note: this document's mutual-information
figures in §5 are computed **conditional on both signals being directional** (the same restricted
subsample κ is computed from), which is a different quantity from AW's own **unconditional** MI
(computed over the full four-symbol alphabet, including `conflicting`/`unavailable`). Where this
document's κ values overlap with AW's three family-pair values, they match exactly (§2.2); the MI
values are not directly comparable across the two documents and are not presented as if they were.

**Necessity** (RQ3/RQ4/RQ8/RQ9, per AW's operationalization) — among observations that reached a
directional result, a voting element (a family, or — this document's extension — one of the five
individual evidence observations inside EVID's own internal count) is *necessary* if removing its
vote would change the result (drop a family below `MINIMUM_AGREEING_FAMILIES`, or flip/tie EVID's own
internal `dominant_alignment`), and *redundant* if the result is unchanged without it.

**RQ1's data-availability limit, stated before §3 rather than after it.** `run_backtest` calls
`evaluate_outcome` **exclusively** at `is_first_confirmation`
(`fmis/swing_setup/backtest_harness.py:340-361`) — never for a `CANDIDATE`-only episode. This is a
property of the harness's own data model, not a limitation introduced by this milestone, and it means
RQ1 as literally posed ("does CONFIRMED outperform CANDIDATE, measured by win rate") **cannot be
answered from this dataset**: there is no forward-looking outcome ever recorded for a
`CANDIDATE`-only episode to compare against. §3.1 states exactly what *can* be measured in its place,
and nothing here fabricates a proxy outcome for `CANDIDATE` episodes to work around this.

### 1.4 Analysis code

Two scripts, described in full in the Appendix, neither committed to the repository: one runs the
extraction described in §1.1 and serializes every observation (all 21,680, `WAIT` included) and every
evaluated outcome to JSON; the second is pure-Python arithmetic (stdlib `json`/`math`/`collections`/
`itertools` only, no third-party dependency) over that JSON, producing every number in §3–§6. Both are
read-only with respect to the production package. The analysis script's full stdout is preserved
alongside the two scripts per the Appendix, so every number in this document can be traced to its
exact computation.

---

## 2. Dataset

### 2.1 Scope

Identical scope to AV/AW, by design — this milestone measures a finer grain of the same population,
not a different one. Ten symbols (`DEFAULT_BACKTEST_SYMBOLS`): BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT,
XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT. Real public Binance spot data, `2025-07-04`
to `2026-08-07` (400 days). Per-symbol candle counts: 1w × 57, 1d × 400, 4h × 2,395, identical to both
prior runs.

### 2.2 Reconciliation against Milestones AV and AW

This is a **third** independent live draw from the same population report 0011 and AW each measured,
now two days later, over a window (`2025-07-04` to `2026-08-07`) that ended three days before this
draw was taken — every candle in it is fully closed and no longer subject to revision, unlike AW's
own re-fetch two days after report 0011's.

| | This run (2026-08-10) | AW (2026-08-08) | Report 0011 (2026-08-08) |
|---|---|---|---|
| Total observations | **21,680** | 21,680 | 21,730 |
| WAIT | 21,102 | 21,102 | 21,147 |
| CANDIDATE (rows) | 401 | 401 | 401 |
| CONFIRMED (rows) | 177 | 177 | 182 |
| Evaluated outcomes | 146 | 146 | 151 |

Every count in this run is **byte-identical to AW's**, not merely close — the expected result once
the underlying candles are no longer revisable (§2.2's own explanation in AW attributed AW-vs-report-
0011's smaller differences to live-data revision between two fetches a day apart; this run's window
closed entirely before either fetch, so no such revision was possible). Every family-pairwise
agreement rate and every necessity/participation number in §4 below that overlaps with AW's own
Part 3 reproduces AW's figures exactly (validated in the Appendix's analysis-script output), which is
this document's primary sanity check on the shared extraction machinery before extending it into new
territory.

### 2.3 Inherited limitations

Every limitation in `BACKTEST_LIMITATIONS` (`fmis/swing_setup/backtest_harness.py:135-167`, AV-1
through AV-9) and every limitation AW's §2.4 names applies unchanged here: no fees/slippage/spread
modelled, `TARGET_FIRST`/`STOP_FIRST` are wick-touch classifications and never a win rate,
`AMBIGUOUS_SAME_BAR` is a refusal to guess intrabar order, entry is the confirming bar's close, the
60-bar evaluation window is a stated policy not a tuned value. This document adds one further,
specific limitation of its own: the individual evidence observations are read from the **SETUP-role
(1d) snapshot only** — `fmis.decision_support` has no cross-timeframe notion, so this document cannot
and does not ask what the same five observations would have read on the CONTEXT (1w) or EXECUTION
(4h) role; only the one role the production `setup_evidence_alignment` family itself reads is
measured.

---

## 3. Measurements

### 3.1 RQ1 — CANDIDATE vs CONFIRMED

**Cannot be answered as a win-rate comparison, and this document says so rather than inventing a
substitute measurement.** Per §1.3's stated data-availability limit: 401 `CANDIDATE` observation-rows
(398 distinct episodes) exist in this dataset, and **zero** of them carry a forward-looking outcome —
`evaluate_outcome` is only ever invoked at first confirmation. What *is* measurable, and is reported
here instead:

- **398 distinct episodes reached `CANDIDATE`** at some point in this window; **177 distinct episodes
  reached `CONFIRMED`**.
- Of the 177 confirmed episodes (reconstructed from `is_new_setup` transitions, matching
  `IdentityTracker`'s own semantics exactly — validated against the harness's own outcome count in
  the Appendix), **146 (82.5%) had a computable stop and target** (a non-`None`
  `risk_reward_ratio`) and were actually evaluated; the other 31 confirmed episodes lacked a
  detected stop or target level on the required side and were never scored — a second, specific
  survivorship gate, distinct from the regime/family-tally gates §3.5 measures, examined further in
  §3.5 and §7.
- Among those 146 evaluated outcomes (the only outcome-bearing population this harness produces at
  all): 62/146 = 42.5% (95% CI 34.7%–50.6%) `TARGET_FIRST`, 71/146 = 48.6% (95% CI 40.7%–56.7%)
  `STOP_FIRST`, 5/146 = 3.4% `AMBIGUOUS_SAME_BAR`, 8/146 = 5.5% `NEITHER_WITHIN_WINDOW`. Win rate
  among the 133 resolved outcomes only: **62/133 = 46.6% (95% CI 38.4%–55.1%)**.

No comparable rate exists for `CANDIDATE`. The nearest legitimate proxy this dataset supports is the
**conversion rate** from `CANDIDATE` to `CONFIRMED` — not a win rate, a different question entirely
— which §3.5's regime/family-tally analysis and §3.9's funnel both speak to.

### 3.2 RQ2 — every evidence field, true vs false

**3.2a — marginal distributions, full dataset (n=21,680).** Every field's own base rate, independent
of direction or outcome:

| Field | Directional split | Non-directional |
|---|---|---|
| `price_vs_ema_fast` | above 7,282 (33.6%) / below 14,398 (66.4%) | none (always available) |
| `price_vs_ema_slow` | above 4,926 (22.7%) / below 16,034 (74.0%) | unavailable 720 (3.3%) |
| `ema_fast_vs_ema_slow` | above 4,440 (20.5%) / below 16,520 (76.2%) | unavailable 720 (3.3%) |
| `macd_vs_signal` | above 11,842 (54.6%) / below 9,838 (45.4%) | none (always available) |
| `macd_histogram` | positive 11,842 (54.6%) / negative 9,838 (45.4%) | none (always available) |
| `rsi_zone` | never directional (by design) | oversold 1,398 (6.4%) / lower-neutral 9,432 (43.5%) / neutral 6,926 (32.0%) / upper-neutral 3,592 (16.6%) / overbought 332 (1.5%) |

Every one of the five directional fields skews toward its "below"/"negative" reading in this
400-day, ten-symbol window — a market-character fact about this specific dataset, not a policy
property, consistent with AW §3.2's own finding that every family's directional marginal skewed
`short`.

**3.2b — agreement with the eventual assigned direction, restricted to the 578 `CANDIDATE`/
`CONFIRMED` observations.** "Evidence = true" is operationalized as: this field's alignment matches
the direction the setup eventually carried.

| Field | Agrees | Disagrees | Neutral/unavailable | Agreement rate |
|---|---|---|---|---|
| `price_vs_ema_slow` | 536 | 42 | 0 | **92.7%** (95% CI 90.3%–94.6%) |
| `price_vs_ema_fast` | 498 | 80 | 0 | 86.2% (95% CI 83.1%–88.7%) |
| `ema_fast_vs_ema_slow` | 470 | 108 | 0 | 81.3% (95% CI 77.9%–84.3%) |
| `macd_vs_signal` | 288 | 290 | 0 | 49.8% (95% CI 45.8%–53.9%) — a coin flip |
| `macd_histogram` | 288 | 290 | 0 | 49.8% (95% CI 45.8%–53.9%) — identical to `macd_vs_signal`, see §5.2 |

The three TREND observations are all well above chance; both MOMENTUM observations are statistically
indistinguishable from a coin flip against the direction the CTX+SETUP-dominated tally (§4.2)
actually assigned — consistent with, and a finer-grained restatement of, AW's own finding that EVID
participates in only 31.1% of directional results.

**3.2c — at the confirming bar, vs realized outcome (n=146, joined 146/146).** Small-cell warning
applies throughout this table — several cells sit at or below the harness's own `MIN_SAMPLE_FOR_RATE`
convention of 5, named explicitly rather than silently omitted:

| Field | Bucket | n | Target-first | Stop-first | Win rate of resolved |
|---|---|---|---|---|---|
| `price_vs_ema_fast` | agrees w/ trade direction | 131 | 56 | 62 | 47.5% (95% CI 38.7%–56.4%) |
| `price_vs_ema_fast` | opposes | 15 | 6 | 9 | 40.0% (95% CI 19.8%–64.3%) |
| `price_vs_ema_slow` | agrees | 140 | 61 | 69 | 46.9% (95% CI 38.6%–55.5%) |
| `price_vs_ema_slow` | opposes | 6 | 1 | 2 | 33.3% (95% CI 6.1%–79.2%, n below MIN_SAMPLE_FOR_RATE) |
| `ema_fast_vs_ema_slow` | agrees | 84 | 31 | 51 | 37.8% (95% CI 28.1%–48.6%) |
| `ema_fast_vs_ema_slow` | opposes | 62 | 31 | 20 | **60.8%** (95% CI 47.1%–73.0%) |
| `macd_vs_signal` | agrees | 76 | 34 | 30 | 53.1% (95% CI 41.1%–64.8%) |
| `macd_vs_signal` | opposes | 70 | 28 | 41 | 40.6% (95% CI 29.8%–52.4%) |
| `macd_histogram` | agrees | 76 | 34 | 30 | 53.1% (identical row to `macd_vs_signal`, see §5.2) |
| `macd_histogram` | opposes | 70 | 28 | 41 | 40.6% (identical row to `macd_vs_signal`, see §5.2) |

The `ema_fast_vs_ema_slow` row is the only one where "opposes" outperforms "agrees" (60.8% vs
37.8%) — the confidence intervals overlap substantially (47.1–73.0% vs 28.1–48.6%, a narrow but real
gap), and this is flagged, not concluded from, in §8 and §10.

### 3.3 RQ3 — every evidence pair

Answered in full in §5 (28 pairs across all 8 directional signals — 3 families and 5 individual
fields — computed once, not per research question, to avoid presenting the same arithmetic under two
headings).

### 3.4 RQ4 — every evidence family

`context_structural_trend` (CTX) and `setup_structural_trend` (SETUP) are structural-trend families
(one on each role); `setup_evidence_alignment` (EVID) is the only family with sub-structure this
document can see inside — TREND (3 observations) and MOMENTUM (2 directional observations; `rsi_zone`
never votes). §4.2 (family level, reconciling AW) and §4.3 (this milestone's new sub-family
breakdown) both bear on this question. Headline: CTX and SETUP jointly decide 68.9% of all
directional results without EVID at all (§4.2); within EVID's own internal vote, the three TREND
observations support its `dominant_alignment` far more often (73.1%–97.3% of the time each is
directional) than the two MOMENTUM observations (70.6%) — see §4.3.

### 3.5 RQ5/RQ6 — weakest and strongest evidence

Operationalized identically to AW's family-level necessity metric (§1.3), extended one level deeper
into EVID's own 5-observation internal vote. "Necessary" here means: this observation supported
EVID's `dominant_alignment`, and removing its single vote would have changed that dominant alignment
(flipped it or reduced it to a tie/deadlock).

| Field | Directional-in (of 21,680) | Supports dominant, when directional | Necessary, of support |
|---|---|---|---|
| `price_vs_ema_fast` | 21,680 (100.0%) | 21,084/21,680 = 97.3% | **9,524/21,084 = 45.2%** (95% CI 44.5%–45.8%) — strongest |
| `ema_fast_vs_ema_slow` | 20,960 (96.7%) | 15,326/20,960 = 73.1% | 6,516/15,326 = 42.5% (95% CI 41.7%–43.3%) |
| `price_vs_ema_slow` | 20,960 (96.7%) | 17,688/20,960 = 84.4% | 6,384/17,688 = 36.1% (95% CI 35.4%–36.8%) |
| `macd_vs_signal` | 21,680 (100.0%) | 15,296/21,680 = 70.6% | 3,476/15,296 = 22.7% (95% CI 22.1%–23.4%) — weakest |
| `macd_histogram` | 21,680 (100.0%) | 15,296/21,680 = 70.6% | 3,476/15,296 = 22.7% — **identical to `macd_vs_signal` in every cell**, because it is the same fact (§5.2) |

By this measure — how often a single observation's own vote is the deciding one inside EVID's
5-observation reduction — `price_vs_ema_fast` is the strongest individual evidence field in this
dataset and `macd_vs_signal`/`macd_histogram` (indistinguishable, §5.2) are the weakest. This is a
different question from §3.2b's "agreement with eventual direction" (where `price_vs_ema_slow` led):
§3.2b asks how often a field predicted the *outcome*'s direction; this section asks how often a
field's own vote was *pivotal to EVID's own internal count*, independent of whether that count went
on to matter to the final policy result at all (§4.2 already shows it usually did not).

### 3.6 RQ7 — regime dependence

| `context_regime_structure` | n | Share of dataset | Directional | Confirmed-rows |
|---|---|---|---|---|
| `insufficient` | 16,632 | 76.7% | 0/16,632 = 0.0% | 0/16,632 = 0.0% |
| `transitioning` | 3,554 | 16.4% | 0/3,554 = 0.0% | 0/3,554 = 0.0% |
| `indeterminate` | 734 | 3.4% | 0/734 = 0.0% | 0/734 = 0.0% |
| `trending` | 760 | 3.5% | 578/760 = **76.1%** (95% CI 72.9%–79.0%) | 177/760 = 23.3% (95% CI 20.4%–26.4%) |

Every single directional result in this dataset (578 of 578) occurred inside the 760 `trending`
observations (3.5% of the dataset) — a restatement, at the regime-state level rather than the
family-vote level, of AW §5.2's architectural finding. **76.7% of the entire dataset never had a
CONTEXT-role regime classification at all** (`insufficient`), the largest single category by a wide
margin. §7 examines this.

| `context_regime_volatility` | n | Share | Directional |
|---|---|---|---|
| `insufficient` | 19,320 | 89.1% | 42/19,320 = 0.2% |
| `contracting` | 2,192 | 10.1% | 494/2,192 = 22.5% |
| `steady` | 168 | 0.8% | 42/168 = 25.0% |

| `context_regime_participation` | n | Share | Directional |
|---|---|---|---|
| `insufficient` | 6,720 | 31.0% | 0/6,720 = 0.0% |
| `subdued` | 9,516 | 43.9% | 446/9,516 = 4.7% |
| `typical` | 3,974 | 18.3% | 132/3,974 = 3.3% |
| `elevated` | 1,470 | 6.8% | 0/1,470 = 0.0% |

Win rate at the confirming bar, split by the CONTEXT-role regime state that bar carried (n=133
resolved, joined 133/133):

| `context_regime_volatility` at confirmation | n | Target-first | Stop-first | Win rate of resolved |
|---|---|---|---|---|
| `insufficient` | 16 | 13 | 3 | **81.2%** (95% CI 57.0%–93.4%) |
| `contracting` | 111 | 46 | 55 | 45.5% (95% CI 36.2%–55.2%) |
| `steady` | 19 | 3 | 13 | 18.8% (95% CI 6.6%–43.0%, n below MIN_SAMPLE_FOR_RATE for the loss side alone but total n=16 resolved) |

| `context_regime_participation` at confirmation | n | Target-first | Stop-first | Win rate of resolved |
|---|---|---|---|---|
| `subdued` | 101 | 50 | 42 | 54.3% (95% CI 44.2%–64.1%) |
| `typical` | 45 | 12 | 29 | 29.3% (95% CI 17.6%–44.5%) |

The volatility-`insufficient` row's 81.2% win rate is the single most striking cell in this table
and is flagged, not concluded from, in §8 and §10 — it rests on only 16 resolved outcomes.

### 3.7 RQ8 — RR realism

Displayed R:R (`risk_reward_ratio` at confirmation) bucketed against realized outcome, n=146:

| Displayed RR | n | Target-first | Stop-first | Win rate of resolved |
|---|---|---|---|---|
| [0, 1) | 56 | 38 | 13 | **74.5%** (95% CI 61.1%–84.5%) |
| [1, 2) | 29 | 9 | 14 | 39.1% (95% CI 22.2%–59.2%) |
| [2, 5) | 27 | 12 | 14 | 46.2% (95% CI 28.8%–64.5%) |
| [5, 20) | 26 | 2 | 24 | **7.7%** (95% CI 2.1%–24.1%) |
| [20, ∞) | 8 | 1 | 6 | 14.3% (95% CI 2.6%–51.3%, n below MIN_SAMPLE_FOR_RATE) |

Mean/median displayed RR, split by realized outcome: winners (`TARGET_FIRST`, n=62) mean **1.66**,
median **0.40**; losers (`STOP_FIRST`, n=71) mean **7.90**, median **3.09**. RR distribution overall
(n=146): min 0.01, p25 0.37, median 1.40, p75 3.57, p90 13.04, max **41,282** — the same pathological
tail report 0011 and AW already measured, reproduced identically here (§2.2).

**A displayed R:R higher than roughly 5 is associated with a markedly lower, not higher, win rate in
this dataset** — the opposite of what "R:R" is colloquially read to promise. §8 examines this as an
unexpected discovery; §10 red-teams it.

### 3.8 RQ9 — survivorship / gating

A full funnel, every count from the same 21,680-observation dataset:

```
21,680 total observations
   │
   ├─ 0 (0.0%) blocked by decision_context == INSUFFICIENT   (the gate never fired — §7)
   │
   ├─ 20,920 (96.5%) blocked by context_regime_structure != TRENDING
   │     (16,632 insufficient · 3,554 transitioning · 734 indeterminate)
   │
   760 (3.5%) reach the family tally (context_regime_structure == TRENDING)
   │
   ├─ 182 (0.8% of 21,680; 23.9% of 760) fail the ≥2-agree-0-oppose tally → WAIT
   │
   578 (2.7% of 21,680; 76.1% of 760) reach CANDIDATE or CONFIRMED
   │     (398 distinct CANDIDATE episodes · 177 distinct CONFIRMED episodes)
   │
   177 confirmed episodes
   │
   ├─ 31 (17.5%) never evaluated — no computable stop/target on the required side
   │
   146 (82.5%) evaluated outcomes
   │
   ├─ 13 (8.9%) unresolved within the 60-bar window (8 neither · 5 ambiguous)
   │
   133 (91.1%) resolved: 62 target-first · 71 stop-first
```

Two gates dominate: the regime-structure gate discards 96.5% of the dataset before the family tally
is ever consulted, and the stop/target-availability gate discards a further 17.5% of confirmed
episodes after the policy has already committed to a direction. The decision-context sufficiency
gate — checked *first* in `evaluate_setup`'s own code order — contributed **zero** WAITs in this
entire dataset (§7).

**LONG/SHORT conversion asymmetry, reproducing AW §5.4 with exact counts AW did not itself publish:**
of 1,050 observations where ≥2 families agreed LONG with none opposing, **252 (24.0%, 95% CI
21.5%–26.7%)** converted to `CANDIDATE`/`CONFIRMED`; of 6,226 observations where ≥2 families agreed
SHORT with none opposing, **326 (5.2%, 95% CI 4.7%–5.8%)** converted — a 4.6× ratio, matching AW's
own reported ratio exactly, now with the raw numerator/denominator AW's own document did not carry.

### 3.9 RQ10 — information gain

Answered in full in §6.

---

## 4. Tables

### 4.1 Reconciliation table (restated from §2.2 for a reader who starts here)

| Metric | This run | AW | Match |
|---|---|---|---|
| Total observations | 21,680 | 21,680 | exact |
| CANDIDATE rows | 401 | 401 | exact |
| CONFIRMED rows | 177 | 177 | exact |
| Evaluated outcomes | 146 | 146 | exact |
| CTX↔SETUP agreement | 55.6% (n=6,160) | 55.6% (n=6,160) | exact |
| CTX↔EVID agreement | 79.0% (n=3,128) | 79.0% (n=3,128) | exact |
| SETUP↔EVID agreement | 75.1% (n=6,566) | 75.1% (n=6,566) | exact |
| CTX↔SETUP κ | 0.022 | 0.022 | exact |
| CTX↔EVID κ | 0.100 | 0.100 | exact |
| SETUP↔EVID κ | 0.412 | 0.412 | exact |
| CTX participation | 578/578 = 100.0% | 578/578 = 100.0% | exact |
| CTX necessity-of-participation | 416/578 = 72.0% | 72.0% | exact |
| SETUP participation | 560/578 = 96.9% | 96.9% | exact |
| EVID participation | 180/578 = 31.1% | 31.1% | exact |
| EVID necessity-of-participation | 18/180 = 10.0% | 10.0% | exact |

### 4.2 Family-level necessity/redundancy (reconciled, restated)

| Family | Participates in | Necessary in | Necessary share |
|---|---|---|---|
| CTX (context_structural_trend) | 578/578 = 100.0% | 416 | 72.0% |
| SETUP (setup_structural_trend) | 560/578 = 96.9% | 398 | 71.1% |
| EVID (setup_evidence_alignment) | 180/578 = 31.1% | 18 | 10.0% |

Deciding coalition, all 578 directional results:

| Coalition | Count | Share |
|---|---|---|
| CTX + SETUP only | 398 | 68.9% |
| All three | 162 | 28.0% |
| CTX + EVID only | 18 | 3.1% |
| SETUP + EVID only (CTX absent) | 0 | 0.0% |

### 4.3 New: individual evidence-field necessity within EVID's own vote (this milestone)

Restated from §3.5 for a single-glance table:

| Field | Family | Directional-in | Supports dominant | Necessary-of-support |
|---|---|---|---|---|
| `price_vs_ema_fast` | TREND | 100.0% | 97.3% | **45.2%** |
| `ema_fast_vs_ema_slow` | TREND | 96.7% | 73.1% | 42.5% |
| `price_vs_ema_slow` | TREND | 96.7% | 84.4% | 36.1% |
| `macd_vs_signal` | MOMENTUM | 100.0% | 70.6% | 22.7% |
| `macd_histogram` | MOMENTUM | 100.0% | 70.6% | 22.7% |

---

## 5. Correlation

### 5.1 Full pairwise table — 8 directional signals, 28 pairs, full dataset

Restricted to observations where both signals are directional (long/short or upward/downward),
exactly as AW's own κ methodology requires. Family lean and individual-field alignment are put on
the same long/short scale (`upward`→`long`, `downward`→`short`) purely for this comparison; §1.3
states the categories are otherwise kept distinct.

| Pair | n | Agree | Expected (chance) | κ | MI (conditional, bits) |
|---|---|---|---|---|---|
| CTX ↔ SETUP | 6,160 | 55.6% | 54.5% | 0.022 | 0.0007 |
| CTX ↔ EVID | 3,128 | 79.0% | 76.7% | 0.100 | 0.0066 |
| CTX ↔ `price_vs_ema_fast` | 8,766 | 63.2% | 60.1% | 0.078 | 0.0070 |
| CTX ↔ `price_vs_ema_slow` | 8,766 | 76.4% | 72.7% | 0.136 | 0.0131 |
| CTX ↔ `ema_fast_vs_ema_slow` | 8,766 | 82.2% | 79.2% | 0.147 | 0.0128 |
| CTX ↔ `macd_vs_signal` | 8,766 | 38.9% | 39.9% | **−0.016** | 0.0007 |
| CTX ↔ `macd_histogram` | 8,766 | 38.9% | 39.9% | −0.016 | 0.0007 |
| SETUP ↔ EVID | 6,566 | 75.1% | 57.7% | **0.412** | 0.1388 |
| SETUP ↔ `price_vs_ema_fast` | 15,434 | 69.2% | 54.1% | 0.329 | 0.0800 |
| SETUP ↔ `price_vs_ema_slow` | 15,152 | 70.2% | 56.5% | 0.315 | 0.0837 |
| SETUP ↔ `ema_fast_vs_ema_slow` | 15,152 | 69.5% | 57.1% | 0.288 | 0.0756 |
| SETUP ↔ `macd_vs_signal` | 15,434 | 52.1% | 48.8% | 0.065 | 0.0034 |
| SETUP ↔ `macd_histogram` | 15,434 | 52.1% | 48.8% | 0.065 | 0.0034 |
| EVID ↔ `price_vs_ema_fast` | 9,066 | **100.0%** | 64.2% | **1.000** | 0.7835 |
| EVID ↔ `price_vs_ema_slow` | 8,550 | **100.0%** | 67.3% | **1.000** | 0.7335 |
| EVID ↔ `ema_fast_vs_ema_slow` | 8,550 | **100.0%** | 67.3% | **1.000** | 0.7335 |
| EVID ↔ `macd_vs_signal` | 9,066 | **100.0%** | 64.2% | **1.000** | 0.7835 |
| EVID ↔ `macd_histogram` | 9,066 | **100.0%** | 64.2% | **1.000** | 0.7835 |
| `price_vs_ema_fast` ↔ `price_vs_ema_slow` | 20,960 | 83.8% | 59.4% | 0.600 | 0.2672 |
| `price_vs_ema_fast` ↔ `ema_fast_vs_ema_slow` | 20,960 | 71.2% | 60.2% | 0.277 | 0.0567 |
| `price_vs_ema_fast` ↔ `macd_vs_signal` | 21,680 | 67.8% | 48.5% | 0.375 | 0.1308 |
| `price_vs_ema_fast` ↔ `macd_histogram` | 21,680 | 67.8% | 48.5% | 0.375 | 0.1308 |
| `price_vs_ema_slow` ↔ `ema_fast_vs_ema_slow` | 20,960 | 87.5% | 65.3% | 0.639 | 0.2630 |
| `price_vs_ema_slow` ↔ `macd_vs_signal` | 20,960 | 53.9% | 47.5% | 0.122 | 0.0170 |
| `price_vs_ema_slow` ↔ `macd_histogram` | 20,960 | 53.9% | 47.5% | 0.122 | 0.0170 |
| `ema_fast_vs_ema_slow` ↔ `macd_vs_signal` | 20,960 | 42.7% | 47.3% | **−0.088** | 0.0094 |
| `ema_fast_vs_ema_slow` ↔ `macd_histogram` | 20,960 | 42.7% | 47.3% | −0.088 | 0.0094 |
| `macd_vs_signal` ↔ `macd_histogram` | 21,680 | **100.0%** | 50.4% | **1.000** | 0.9938 |

### 5.2 Two exact, code-provable redundancies found inside EVID's own five observations

Both facts below were checked against **every one of the 21,680 observations** (not sampled), with
zero exceptions found — they are proven identities, not statistical correlations, and are named as
such rather than left as an unusually high κ.

**`macd_vs_signal` and `macd_histogram` are the same fact, twice.** `fmis/features/indicators/macd.py`
defines `histogram = macd_line - signal_line`. By definition, `histogram > 0 ⟺ macd_line >
signal_line ⟺ macd_vs_signal == "above"`. Checked directly against all 21,680 observations: **zero
mismatches**. `EvidenceGroups`' five-observation MOMENTUM+TREND count therefore contains, at most,
**four** independent facts whenever MACD is available (100% of this dataset) — not five. This is the
mechanism behind every "identical row" flagged in §3.2c, §3.5 and §4.3: any statistic computed
per-observation for `macd_vs_signal` is, by construction, the identical statistic for
`macd_histogram`.

**The three TREND observations are constrained by transitivity, and the constraint binds 71.3% of
the time it can be checked.** `price_vs_ema_fast` (price vs EMA20), `price_vs_ema_slow` (price vs
EMA50) and `ema_fast_vs_ema_slow` (EMA20 vs EMA50) are the three pairwise sign comparisons among
three real numbers (`close`, `ema_20`, `ema_50`). Order transitivity means: whenever
`price_vs_ema_fast` and `ema_fast_vs_ema_slow` agree in direction (both `above` or both `below`),
`price_vs_ema_slow` is **mathematically forced** to agree with them — checked against every
observation where all three are available and non-equal (n=20,960): **zero violations** in the
14,934 cases (71.3%) where the constraint applies. In the remaining 6,026 cases (28.7%) — where
`price_vs_ema_fast` and `ema_fast_vs_ema_slow` disagree (price sits between the two EMAs, or both
EMAs sit on the same side of price with one crossed) — the constraint does not fix
`price_vs_ema_slow`, and this is exactly where the three observations carry genuinely independent
information from one another. **The three TREND observations are not three independent facts; they
are two independent facts (any two of the three) plus a third that is redundant 71.3% of the time
and informative the other 28.7%.**

### 5.3 What §5.1's table shows once §5.2's proofs are known

With the two proven redundancies named, the 28-pair table in §5.1 is not 28 independent
measurements: the `macd_vs_signal`/`macd_histogram` row-pairs (7 of the 28) are, by §5.2, guaranteed
identical and add no new information beyond confirming the identity holds throughout; and every
TREND-pair's κ (`price_vs_ema_fast`↔`price_vs_ema_slow` 0.600, `price_vs_ema_slow`↔
`ema_fast_vs_ema_slow` 0.639, `price_vs_ema_fast`↔`ema_fast_vs_ema_slow` 0.277 — the lowest of the
three, and the pair §5.2's transitivity argument treats as the two "generating" comparisons) is at
least partly a restatement of the same order-transitivity fact rather than three separately
noteworthy correlations. Genuinely separate, non-tautological dependencies in this table are the
cross-family ones: SETUP↔EVID (κ=0.412, already known from AW) and, new in this document,
SETUP↔`price_vs_ema_fast`/`price_vs_ema_slow`/`ema_fast_vs_ema_slow` (κ 0.29–0.33) — a real,
non-tautological correlation between the SETUP-role structural-trend family and the SETUP-role's own
TREND evidence observations, both reading the same 1d candle series through different algorithms
(swing-pivot detection vs EMA crossovers), exactly the "same series, different lens" hypothesis AW's
own Red Team section raised and explicitly declined to prove for the family-level SETUP↔EVID pair.
This document does not prove that hypothesis either (no source-level forcing argument is offered
here, unlike §5.2's two proofs) — it is named as the same open hypothesis, now visible one level
deeper, in §11.

---

## 6. Information gain

### 6.1 Each signal vs the eventual assigned direction (n up to 578)

Mutual information in bits, conditional on the observation being directional at all (matching §5's
own conditioning), computed over the 578 `CANDIDATE`/`CONFIRMED` observations:

| Signal | n | MI(signal; direction) | H(signal) | H(direction) | Raw agreement |
|---|---|---|---|---|---|
| EVID | 180 | 0.997 | 0.997 | 0.997 | 100.0% |
| SETUP | 560 | 0.993 | 0.993 | 0.993 | 100.0% |
| CTX | 578 | 0.988 | 0.988 | 0.988 | 100.0% |
| `price_vs_ema_slow` | 578 | 0.662 | 0.945 | 0.988 | 92.7% |
| `price_vs_ema_fast` | 578 | 0.419 | 0.998 | 0.988 | 86.2% |
| `ema_fast_vs_ema_slow` | 578 | 0.380 | 0.810 | 0.988 | 81.3% |
| `macd_vs_signal` | 578 | 0.0029 | 0.841 | 0.988 | 49.8% |
| `macd_histogram` | 578 | 0.0029 | 0.841 | 0.988 | 49.8% |

The three families' own MI is at or near their own full entropy (0.988–0.997 bits) because, by
construction (§1.3, AW §5.2/§5.3), a family that participates in the winning coalition always
matches the assigned direction exactly whenever it is directional at all in this restricted
subsample — this number restates §4.2's coalition mechanics in information-theoretic units, not a
new independent fact. The individual evidence fields, which never gate or vote directly on the final
policy result (only EVID's already-reduced value does), carry real but much smaller information about
the eventual direction: `price_vs_ema_slow` (0.662 bits) is the strongest of the five,
`macd_vs_signal`/`macd_histogram` (0.0029 bits, identical per §5.2) the weakest — a result consistent
with, but more precise than, §3.2b's raw-agreement ranking.

### 6.2 Each signal vs the realized outcome (n=133, resolved only)

The brief's RQ10 ("if you could keep only ONE evidence, which one") is best answered against the
*realized* outcome, not the assigned direction — but this is the smallest-sample measurement in this
document, and every number below should be read with that stated:

| Signal | n | MI(signal; outcome) | H(signal) | H(outcome) |
|---|---|---|---|---|
| `price_vs_ema_slow` | 133 | **0.0195** | 0.978 | 0.997 |
| `ema_fast_vs_ema_slow` | 133 | 0.0189 | 0.297 | 0.997 |
| `macd_vs_signal` | 133 | 0.0180 | 0.385 | 0.997 |
| `macd_histogram` | 133 | 0.0180 (identical, §5.2) | 0.385 | 0.997 |
| CTX | 133 | 0.0164 | 0.988 | 0.997 |
| SETUP | 125 | 0.0129 | 0.996 | 0.999 |
| `price_vs_ema_fast` | 133 | 0.0105 | 0.993 | 0.997 |
| EVID | 13 | 0.0024 | 0.961 | 0.779 | 

**Every MI value in this table is below 0.02 bits — under 2% of the outcome's own entropy (0.997
bits) is resolved by knowing any single signal's value at confirmation.** By this measure,
`price_vs_ema_slow` has the highest (barely) measured information content about the realized outcome
of any of the eight signals in this dataset, and EVID (the family itself, n=13 — far below
`MIN_SAMPLE_FOR_RATE`) has the lowest, though EVID's own n is too small here for that ordering to be
read as a confident ranking rather than a noisy one. **This document does not recommend keeping any
one of these** — the brief explicitly forbids it — and states plainly that at this outcome-level
sample size (133), no signal's MI value is distinguishable from the others with the confidence this
dataset supports; the ranking is reported as measured, not as a finding strong enough to act on.

---

## 7. False assumptions found

**Assumption: the decision-context sufficiency gate (`ContextState.INSUFFICIENT`), checked first in
`evaluate_setup`'s own code order, is a meaningful contributor to the WAIT rate.** Measured: it
contributed **zero** of the 21,102 WAIT results in this dataset (§3.8). Every WAIT in this window is
attributable to the regime-structure gate or the family tally, never to data insufficiency as
`fmis.decision_context` defines it. This does not mean the gate is defective — `sufficiency` read
`limited` for 9,720 observations (44.8%) rather than `sufficient`, so the gate's finer-grained
non-blocking signal is doing something — but its one *blocking* state never fired in this specific
window.

**Assumption (implicit in the harness's own default-window rationale,
`backtest_harness.py:100-111`): 400 days is enough for the CONTEXT-role (1w) regime classification to
warm up for most of the window.** Measured: `context_regime_structure` was `insufficient` for
**76.7%** of all 21,680 observations, and `context_regime_volatility` for **89.1%**. The stated
rationale (EMA(50) on weekly candles needing "roughly 350 days") is numerically consistent with this
finding (350/400 = 87.5%, the same order as the measured volatility-insufficiency rate and in the
right direction for structure's lower 76.7%) rather than contradicted by it, but the magnitude — over
three-quarters of the dataset having no structural regime read at all, not merely a ranging one — is
larger than "warm-up" alone might suggest to a reader who has not measured it.

**Assumption: `macd_vs_signal` and `macd_histogram`, reported as two separate MOMENTUM observations,
represent two pieces of evidence.** Measured and proven (§5.2): they are the identical fact under two
names, with zero exceptions across 21,680 observations. `EvidenceGroups`' "5 observations" feeding
`setup_evidence_alignment` are, whenever MACD is available (100% of this dataset), at most 4
independent facts.

**Assumption: the three TREND observations (`price_vs_ema_fast`, `price_vs_ema_slow`,
`ema_fast_vs_ema_slow`) are three independent pieces of evidence, the way three separately-named
observations in a report suggests.** Measured and proven (§5.2): by order transitivity among three
real numbers, the third is fully determined by the other two 71.3% of the time they are all
available. TREND, like MOMENTUM, carries fewer independent facts than it has named observations —
though (unlike MOMENTUM's exact duplication) TREND's redundancy is partial, not total, and the
remaining 28.7% is genuinely new information.

---

## 8. Unexpected discoveries

**A displayed R:R above ~5 is associated with a substantially *lower* win rate, not a higher one, in
this dataset (§3.7).** Losing (`STOP_FIRST`) outcomes carry a mean displayed RR of 7.90 (median
3.09); winning (`TARGET_FIRST`) outcomes carry a mean of 1.66 (median 0.40) — roughly a 5× gap in the
opposite direction from what "risk:reward" is colloquially read to promise. The RR[5,20) bucket's win
rate is 7.7% (95% CI 2.1%–24.1%, n=26) against RR[0,1)'s 74.5% (95% CI 61.1%–84.5%, n=56). No causal
claim is made here (§10 red-teams the candidate mechanisms) — this is reported because it is large,
easy to reproduce from the same data, and runs directly counter to an intuitive reading of the
metric's name.

**`context_regime_volatility == insufficient` at the confirming bar carries the highest measured win
rate of any regime-state cell in this document (81.2%, 95% CI 57.0%–93.4%, n=16 resolved) — the
opposite of what a reader might expect from a state literally named "insufficient."** This is the
smallest-n cell in §3.6's win-rate tables and is flagged rather than trusted; a state meaning
"not enough historical ATR data to classify volatility" correlating with the *best* measured outcome
in this dataset, if it held up at a larger sample, would be a genuinely surprising finding worth its
own future investigation — this document does not have the sample size to say more than that it is
observed.

**EVID agrees with every one of its own five directional sub-observations 100% of the time it is
itself directional (§5.1) — and this is provably architectural, not merely a high correlation.**
`OverallState.WATCH` (the state `_evidence_lean` maps to a directional lean) requires
`groups.conflicting` to be empty (`fmis/decision_support/report.py:392-396`) — by construction, EVID
can never be directional while disagreeing with any of its own directional sub-observations. This is
the same shape of finding as AW §5.2's CTX/regime-gate discovery (two values built from the same
underlying computation, one nested inside the policy's tally and one inside a lower layer's own
internal vote), found here one layer deeper in the pipeline.

**The `SETUP↔EVID` family-pair correlation AW's Red Team flagged as an open, unproven hypothesis
("same 1d series, different lens") reappears, unresolved in the identical way, one level lower.**
§5.3 measures a real, non-tautological κ (0.29–0.33) between the SETUP structural-trend family and
each of the three TREND evidence observations individually — the same phenomenon AW named for the
family pair, now visible in its component parts, and still not source-traced to a forcing mechanism
the way §5.2's two identities were. See §11.

---

## 9. What the repository now knows that it did not know before

- **EVID's five named observations are at most four independent facts, and sometimes fewer.**
  `macd_vs_signal`/`macd_histogram` are one fact under two names, always (§5.2, proven). The three
  TREND observations collapse to two independent facts 71.3% of the time all three are available
  (§5.2, proven). This was not previously measured or stated anywhere in the repository; AW's own
  research treated EVID as one atomic family and did not look inside it.
- **The decision-context sufficiency gate, positioned first in `evaluate_setup`'s own code order,
  never once blocked a result in this 21,680-observation, ten-symbol, 400-day dataset.** Every WAIT
  in this window came from the regime gate or the family tally.
- **Three-quarters of this dataset (76.7%) carries no CONTEXT-role structural regime classification
  at all**, not a `ranging` one — a materially larger fraction than the harness's own stated
  "roughly 350 days" warm-up rationale might suggest without measurement.
- **A displayed R:R above roughly 5 correlates with a markedly lower realized win rate, not a
  higher one, in this dataset** — the opposite of the metric's colloquial reading, previously
  unmeasured at this resolution (report 0011/AV measured a pathological RR *tail*; this document is
  the first to cross that tail against realized win/loss).
- **17.5% of confirmed episodes (31 of 177) are never evaluated for an outcome at all**, because no
  stop or target level exists on the required side at confirmation — a distinct, previously
  unnamed survivorship gate sitting between "the policy confirmed a direction" and "the harness could
  score it," separate from every gate AV/AW's own limitations already named.
- **The individual-evidence-field granularity this milestone added answers RQ2/RQ3/RQ5/RQ6/RQ10 at a
  resolution the repository's own data model (`HistoricalObservation`) does not persist** — every
  number in §3.2, §3.5, §4.3, §5, and §6 required re-deriving evidence observations the production
  composition path computes and discards before they reach the backtest harness's own recorded
  output.

---

## 10. Red team

Every major finding above, with the alternative explanation considered and weighed against the data
already in hand — matching AW's own discipline of attacking its own conclusions before publishing
them.

**Finding: `macd_vs_signal`/`macd_histogram` are provably identical (§5.2).**
*Attack considered:* none — this is a closed algebraic identity (`histogram = macd_line -
signal_line`), verified against every observation in the dataset with zero exceptions, not a
statistical claim open to an alternative explanation. The only genuinely open question is scope: this
proof covers this repository's specific MACD implementation
(`fmis/features/indicators/macd.py`); a different MACD variant elsewhere could in principle compute
the histogram differently, but that is not what this repository does, and is not this document's
claim.

**Finding: the three TREND observations collapse to two independent facts 71.3% of the time
(§5.2).**
*Alternative explanation:* the 71.3%/28.7% split could be an artifact of this dataset's specific
price action (e.g., unusually clean trends where price and both EMAs move in lockstep) rather than a
property that would hold in a differently-shaped window.
*Attack:* the *mechanism* (order transitivity among three reals) is a mathematical fact independent
of any dataset — whenever `price_vs_ema_fast` and `ema_fast_vs_ema_slow` agree, `price_vs_ema_slow`
is forced, in every possible market, not just this one. What *is* dataset-dependent is the 71.3%
figure itself — how often those two observations happen to agree in the first place — which could be
higher or lower in a choppier or more range-bound window. The proof is general; the frequency is
scoped to this dataset, and §11 says so.

**Finding: a displayed R:R above ~5 correlates with a lower win rate (§8).**
*Alternative explanations, none distinguished here:* (a) mechanical — `_nearest` selects the
*closest* same-side level as a stop and the closest opposite-side level as a target
(`fmis/swing_setup/policy.py:141-163`); a very high displayed RR is geometrically produced by an
unusually close stop (small risk) paired with a distant target (large reward), and a close stop is,
independently, easier for ordinary price noise to touch first regardless of any real directional
edge — this is a candidate mechanical explanation the code trace makes plausible but this milestone
did not isolate (it would require decomposing RR into its risk and reward legs separately, which
this document did not do); (b) small-sample noise — the [5,20) and [20,∞) buckets carry only 26 and 8
observations respectively, and their confidence intervals (2.1%–24.1%, 2.6%–51.3%) are wide; (c) a
regime confound — if unusually high-displayed-RR setups disproportionately occurred during the same
choppier conditions the RQ7 volatility findings (§3.6, §8) associate with worse outcomes, the
correlation could be regime-driven rather than RR-driven. None of the three is ruled in or out here.

**Finding: `context_regime_volatility == insufficient` shows an 81.2% win rate (§8).**
*Alternative explanation:* n=16 resolved outcomes is a small sample even by this document's own
already-small-sample standards (below every other cell's n in §3.6's win-rate table), and the 95% CI
(57.0%–93.4%) is wide enough to be consistent with a true rate anywhere from "somewhat better than
average" to "dramatically better."
*Attack:* not attacked further here — this is exactly the kind of cell this document's own §1.3/§6.2
discipline says to flag rather than trust. No claim beyond "measured, in this dataset, from 16
outcomes" is made.

**Finding: EVID agrees with all five of its own sub-observations 100% of the time it is directional
(§8).**
*Attack considered:* none needed — like the MACD identity, this is traced to source
(`OverallState.WATCH` structurally requires an empty `conflicting` group) and confirmed with zero
exceptions across the full dataset, the same standard AW's own §5.2 CTX finding was held to.

**Finding: SETUP correlates with the TREND evidence observations individually (κ 0.29–0.33), echoing
AW's unresolved SETUP↔EVID hypothesis one level down (§8).**
*Attack considered, and left open, exactly as AW left its own version open:* this document does not
trace a source-level forcing mechanism the way §5.2's two identities are traced — "same 1d series,
different lens" remains a plausible, architecturally-motivated hypothesis, not a proof. An equally
consistent alternative, unchanged from AW's own Red Team entry on this exact question, is that this
400-day window's specific price action (clean, sustained trends in the active symbols) inflates the
correlation without any structural entanglement. Carried into §11 rather than resolved here.

---

## 11. Open questions

Stated once, not answered, per the brief's own instruction.

- **Does the SETUP↔TREND-evidence correlation (§5.3, §8, §10) reflect a shared computational root
  (same candle series, correlated algorithms) or this window's specific market character?** AW asked
  this at the family level; this document narrows it to the individual-observation level without
  resolving it at either.
- **Would the 71.3% transitivity-binding rate (§5.2) differ in a choppier, more range-bound window?**
  The mechanism (order transitivity) is proven and dataset-independent; the frequency is not.
- **Does the RR-vs-win-rate inversion (§3.7, §8, §10) survive decomposing displayed RR into its risk
  leg and reward leg separately** — is a tight stop, a distant target, or both driving it? Not
  measured here.
- **Would `context_regime_volatility == insufficient`'s 81.2% win rate (n=16) hold at a larger
  sample?** Not distinguishable from noise at this milestone's sample size.
- **Why does `context_regime_participation` warm up (31.0% insufficient) so much faster than
  `context_regime_structure` (76.7%) and `context_regime_volatility` (89.1%)?** Measured as a fact
  (§3.6); no source trace of each dimension's specific warm-up requirement was performed in this
  milestone to explain the difference.
- **Would a fourth live re-fetch of this exact window continue to reproduce §2.2's byte-identical
  counts indefinitely, or could Binance still revise candles this document treated as closed?** Not
  tested beyond the one confirmation this document performed.
- **Does any individual evidence field's information-gain ranking against realized outcome (§6.2)
  hold at a materially larger sample than 133?** Every MI value in that table is small and the
  ordering is not claimed to be stable at this n.
- **RQ1 as posed by the brief — does CONFIRMED outperform CANDIDATE by win rate — has no answer in
  this harness's data model (§1.3, §3.1).** Whether a different harness design (one that also scored
  CANDIDATE-only episodes against a hypothetical forward window) would change that is a design
  question, explicitly out of scope for a measurement-only milestone.

---

## Appendix — reproduction

Two scripts, neither part of the shipped package, both calling only already-public production
functions (`fmis.swing_setup.backtest_harness.DEFAULT_BACKTEST_SYMBOLS`/
`DEFAULT_BACKTEST_LIMIT`/`DEFAULT_EVALUATION_WINDOW_BARS`, `fmis.pipeline.multi_timeframe
.multi_timeframe_facts_for_symbol`, `fmis.swing_setup.compose.setup_inputs_and_assessment_for_sheet`/
`snapshot_from_sheet`, `fmis.decision_support.build_evidence_report`,
`fmis.swing_setup.backtest_identity.IdentityTracker`, `fmis.swing_setup.backtest_outcomes
.evaluate_outcome`, `fmis.swing_setup.backtest_replay.fetch_historical_dataset`/
`build_replay_transport`):

1. **Extraction** (`ax_extract.py`) — mirrors `run_backtest`'s own per-instant loop exactly (§1.1),
   fetching `start_time=2025-07-04T00:00:00Z`, `end_time=2026-08-07T00:00:00Z` for
   `DEFAULT_BACKTEST_SYMBOLS`, and additionally calls `build_evidence_report` per instant to capture
   the five individual evidence observations `HistoricalObservation` does not persist. Serializes
   every observation (21,680, `WAIT` included) and every outcome (146) to JSON. Run against real
   Binance data on 2026-08-10 under the repository's own `.venv` (Python 3.12.13, the interpreter
   `pyproject.toml`'s `requires-python = ">=3.12"` names).
2. **Analysis** (`ax_analyze.py`) — pure Python (stdlib `json`/`math`/`collections`/`itertools`
   only), reading that JSON and computing every number in §3–§6: the survivorship funnel, per-field
   marginal/conditional distributions, the 28-pair correlation table (agreement, chance-corrected κ,
   conditional mutual information, using a Wilson score interval for every reported proportion), the
   family- and individual-field-level necessity/redundancy breakdown, the regime-dependence and RR-
   realism cross-tabulations, and the two information-gain tables. Its full stdout — every number
   quoted in this document, in the order computed — is preserved alongside both scripts.

Re-running script 1 against live Binance data reproduced, on 2026-08-10, **byte-identical** observation
and outcome counts to AW's own 2026-08-08 run (§2.2) — a stronger reconciliation than AW achieved
against report 0011, attributable to this window's candles now being fully closed and no longer
subject to revision. A reader re-running both scripts against a materially different window, symbol
universe, or date range should expect the two proven identities in §5.2 to hold exactly (they are
dataset-independent mathematical facts) and every other number in this document to vary with real
market data, the same discipline AV/AW both state about their own reproducibility.
