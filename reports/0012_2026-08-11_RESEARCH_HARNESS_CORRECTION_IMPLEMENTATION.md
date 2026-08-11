# Research Harness Correction V1 — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0012 |
| **Title** | Research Harness Correction V1 — Implementation Record |
| **Date** | 2026-08-11 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `f9ddc54`; this milestone's work committed locally on top of it, **not pushed** |
| **Status** | Final |

**Milestone:** BC — Research Dataset & Counterfactual Replay Correction.
**Scope guard.** No trading policy changed. `CONFIRMATION_LOOKBACK_BARS` is still `10`. No threshold
tuned, no indicator added, no AI introduced, and **no claim of improved trading performance is made
anywhere in this report.**

Design record: [`docs/design/RESEARCH_HARNESS_CORRECTION_V1.md`](../docs/design/RESEARCH_HARNESS_CORRECTION_V1.md).
Hostile review: [report 0013](0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md).

---

## 1. What was wrong, and what this milestone did about it

Milestone BB found two research-validity defects. Both are now corrected, and both corrections are
measured rather than asserted.

| BB finding | Correction | Evidence in this report |
|---|---|---|
| A "400-day" window in which the policy could reach `CONFIRMED` on ~43 days | Four explicit boundaries, a warm-up prefix derived from production dependencies and fetched **before** the measurement window | §4, §5, §6 |
| A counterfactual emulated by deleting stale confirmations | Every variant replays the full historical decision process with the bound supplied to the production policy | §8, §9 |

A third defect, **not previously reported**, was found while building this milestone and is
quantified in §7: Milestone AV's setup identity is derived from a window-relative bar index, so it
changes every bar. AV's "unique setups" is a count of directional bars.

---

## 2. Starting Git state

```
branch            main
HEAD              f9ddc545dbc0cdda167170f41766125fec06351e
                  docs(product): record Swing Setup backtest milestone
origin/main       f9ddc54 (in sync at start)
working tree      clean apart from 12 pre-existing untracked AP/AQ/BA/BB-era research
                  documents under docs/design/ and docs/reviews/ — untouched by this milestone
```

## 3. Root cause of the effective 41-day sample, reproduced

BB derived the defect from code and dated it to 2026-06-22. This milestone **re-ran AV's own harness**
over the same ten symbols for 400 days ending 2026-08-01 and measured it directly:

| AV measurement (400-day window, 2025-06-27 → 2026-08-01) | Value |
|---|---|
| Observations | 21,740 |
| `CONFIRMED` observations | 186 |
| Evaluated outcomes | 155 |
| **First outcome confirmed** | **2026-06-18** |
| **Last outcome confirmed** | **2026-07-29** |
| **Span in which any outcome exists** | **41 calendar days of a 400-day window** |
| Distinct confirmation days | 23 |
| Largest 5-day cluster | **76 of 155 outcomes — 49.0 %** |

BB reported 43 days and 49.6 %; this independent re-run gives 41 days and 49.0 % on a window ending
five days later. **BB's finding is confirmed, not merely repeated.**

The mechanism, read out of the code: the context-role regime needs weekly EMA(50) and ATR(50); the
harness's own `limit` asks for 250 candles per role; the 400-day fetch supplies 57 weekly candles in
total, all of them inside what AV called the measurement window. The first ~350 days of every AV run
are warm-up spent in the measurement period.

## 4. Corrected warm-up policy

Derived, never hand-picked — `fmis.swing_setup.research_warmup.derive_warmup` asks each production
object for its own requirement.

| Role | Interval | Required bars | Duration | Binding component |
|---|---|---|---|---|
| context | `1w` | 250 | **1,750 days** | `analysis_window` (the requested candle `limit`) |
| setup | `1d` | 250 | 250 days | `analysis_window` |
| execution | `4h` | 250 | 41.7 days | `analysis_window` |

Contributing components, each read from the object that owns it: every feature in
`regime_features()` (EMA(200) → 200, ATR(50) → 51, MACD → 34, RelVol(20) → 21, EMA(50) → 50, RSI/ATR(14)
→ 15), `required_candles(2,2)` → 5, `RegimePolicy.transition_lookback_bars`,
`CONFIRMATION_LOOKBACK_BARS` → 10, and the requested analysis window → 250, which binds.

**The requested analysis window is the component AV's reasoning missed.** The composition path asks
for 250 candles at every role and reads whatever it gets; a role holding fewer is analysed over a
shorter window than production uses, even when every indicator has a value.

The prefix additionally covers the 60-bar identity-priming replay (§6), so priming instants are as
warm as measured ones. Fetching is per interval — `1w` from 2020-09-21, `1d` from 2024-10-30, `4h`
from 2025-05-26 — rather than pulling 1,750 days of 4H candles no execution decision can read.

### The warm-up claim, verified per instant

Every measured instant records, per role, whether any feature was still warming up and whether the
role held fewer closed candles than requested. Across **all seven runs**:

| Check | Result |
|---|---|
| Role-views with a feature still warming up | **0** |
| Role-views below the requested 250-candle window | **0** |
| Measured instants raising `InsufficientDataError` | **0** |
| Minimum closed candles seen at any measured instant | context **250**, setup **250**, execution **250** |
| Outcomes resolved against a truncated tail | **0** |

## 5. Historical data availability, measured

`probe_availability` asked the provider directly for each series' first and last candle on
2026-08-11. All 30 (symbol, interval) pairs satisfy the derived requirement.

| Symbol | First weekly candle | Weekly candles | 250 weekly + priming complete at |
|---|---|---|---|
| BTCUSDT | 2017-08-14 | 470 | 2022-06-16 |
| ETHUSDT | 2017-08-14 | 470 | 2022-06-16 |
| BNBUSDT | 2017-11-06 | 458 | 2022-09-08 |
| ADAUSDT | 2018-04-16 | 435 | 2023-02-16 |
| XRPUSDT | 2018-04-30 | 433 | 2023-03-02 |
| LINKUSDT | 2019-01-14 | 396 | 2023-11-16 |
| DOGEUSDT | 2019-07-01 | 372 | 2024-05-02 |
| SOLUSDT | 2020-08-10 | 314 | 2025-06-05 |
| DOTUSDT | 2020-08-17 | 313 | 2025-06-12 |
| **AVAXUSDT** | **2020-09-21** | **308** | **2025-07-17 ← binds** |

An unsatisfiable window **raises with the measured shortfall**; it is never silently shortened.

## 6. The new common measurement window

```
warmup_start        2020-09-21T00:00:00Z    (1,750 days + 10 priming days of warm-up)
measurement_start   2025-07-17T00:00:00Z
measurement_end     2026-08-01T00:00:00Z    (380 days, half-open)
outcome_tail_end    2026-08-11T00:00:00Z    (10 days, resolution only)
```

Segments (equal-length, ladder-chosen before any result): `half_year_1_of_2`
2025-07-17 → 2026-01-23 and `half_year_2_of_2` 2026-01-23 → 2026-08-01, each carrying exactly
**11,400** measured observations.

**Effective usable period: 41 days → 380 days, a 9.3× increase.** Every day of the measurement
window is usable, which §4's per-instant verification establishes rather than assumes.

## 7. Corrected baseline, and why it is not comparable to AV's

| Measure | BC baseline (380 days) | AV (400-day window, 41 usable days) |
|---|---|---|
| Measured observations | 22,800 | 21,740 |
| `WAIT` / `CANDIDATE` / `CONFIRMED` | 17,832 / 3,002 / 1,966 | 21,188 / 366 / 186 |
| Unique opportunities | 52 | 549 "unique setups" |
| Confirmed opportunities | 45 | 186 |
| Evaluated outcomes | 44 | 155 |
| TARGET_FIRST / STOP_FIRST / AMBIGUOUS / unresolved | 21 / 18 / 3 / 2 | 64 / 78 / 5 / 8 |
| Target-first rate | 53.8 % | 45.1 % |

**These two columns must not be read as a before-and-after.** Three things differ at once, and only
one of them is the window:

1. **The window.** AV measured 41 usable days; BC measures 380.
2. **The identity.** This is the defect found during this milestone. AV's `setup_identity` keys on
   `Trigger.level.origin.index`, the pivot's position in the *sliding* analysis window, so a fixed
   swing's index falls by one every bar and the identity changes every bar. Measured on this run:
   **AV recorded 549 "unique setups" from 552 directional observations, and 186 "unique confirmed
   setups" from 186 confirmed observations — a 1:1 ratio.** One persisting confirmed setup was
   therefore outcome-evaluated once per bar, so AV's 155 outcomes are largely near-duplicate rows
   from a much smaller number of distinct decisions. BC's opportunity rule collapses 1,966 confirmed
   observations into **45** confirmed opportunities and evaluates each once.
3. **The sample size that follows.** BC's 44 outcomes are not a smaller measurement of the same
   thing; they are the de-duplicated count. The honest reading is that BC has **fewer but less
   correlated** observations, and 44 is still a small sample.

The 8.7-point difference in target-first rate is therefore **not evidence of anything**, and is
reported here only so nobody has to compute it and wonder.

### Sample concentration, re-measured

| Measure | BC baseline | AV | BB's figure for the AV–BA chain |
|---|---|---|---|
| Evaluated outcomes | 44 | 155 | 133 |
| Span of confirmations | **351 days** | 41 days | 43 days |
| Distinct confirmation days | **35** | 23 | — |
| **Largest 5-day cluster** | **5 of 44 — 11.4 %** | 76 of 155 — 49.0 % | 66 of 133 — 49.6 % |
| Largest single symbol | DOTUSDT 11 of 44 — 25.0 % | — | — |
| Months containing an outcome | 10 | 2 | — |
| Calendar years represented | 2 (18 in 2025, 26 in 2026) | 1 | 1 |

**Concentration improves materially: the largest five-day cluster falls from ~49 % to 11.4 %, and
confirmations spread across 35 distinct days in 10 months rather than 23 days in 2 months.** That is
the threshold the brief set for claiming any improvement in generalizability, and it is met on this
measure. It is *not* met on sample size: 44 outcomes across ten co-moving crypto majors, with
overlapping 60-bar evaluation windows, remains a small and partly dependent sample (§12).

## 8. Research-variant mechanism, and proof it is faithful

`evaluate_setup` gained one keyword-only parameter, `research_confirmation_max_age`. Containment is
asserted four independent ways (30 tests in `tests/test_swing_setup_research_boundary.py`); §10
covers it. The fidelity question — *is the replay really the production policy?* — is answered by
measurement, not by inspection:

> **Replaying the override at the production bound of 10 reproduces the production baseline
> exactly**: identical status, direction and opportunity key at all 22,860 observations, and an
> identical outcome tuple. The lineage comparison reports 45 baseline confirmations, 45 variant
> confirmations, **45 unchanged, 0 shifted, 0 lost, 0 new**.

The only difference is provenance: every assessment under the override carries
`policy_id = swing-setup-v1+research(max_confirmation_age=10)` and a `RESEARCH OVERRIDE ACTIVE`
limitation line, while the baseline carries `swing-setup-v1` and does not.

## 9. Counterfactual variant results

**This is sensitivity evidence. No winner is selected and none is implied.** Every row replays the
entire historical decision process; nothing is filtered.

| Variant | CAND obs | CONF obs | Confirmed opps | Outcomes | TGT | STOP | AMB | Unres | Target-first |
|---|---|---|---|---|---|---|---|---|---|
| production baseline (10) | 3,002 | 1,966 | 45 | 44 | 21 | 18 | 3 | 2 | 53.8 % |
| max_age 10 (via override) | 3,002 | 1,966 | 45 | 44 | 21 | 18 | 3 | 2 | 53.8 % |
| max_age 5 | 3,883 | 1,085 | 42 | 41 | 21 | 14 | 4 | 2 | 60.0 % |
| max_age 3 | 4,267 | 701 | 40 | 38 | 17 | 15 | 4 | 2 | 53.1 % |
| max_age 2 | 4,454 | 514 | 39 | 36 | 19 | 12 | 3 | 2 | 61.3 % |
| max_age 1 | 4,635 | 333 | 37 | 33 | 15 | 14 | 3 | 1 | 51.7 % |
| max_age 0 | 4,803 | 165 | 35 | 31 | 14 | 13 | 3 | 1 | 51.9 % |

Measured observations (22,800), `WAIT` (17,832) and unique opportunities (52) are **identical across
every variant**, which is the invariance the lineage join depends on: the override moves work between
`CANDIDATE` and `CONFIRMED` and touches nothing else.

### Confirmation lineage against the baseline

| Variant | Baseline conf. | Variant conf. | Same instant | Confirmed later | Lost | New |
|---|---|---|---|---|---|---|
| max_age 10 | 45 | 45 | 45 | 0 | 0 | 0 |
| max_age 5 | 45 | 42 | 33 | 9 | 3 | 0 |
| max_age 3 | 45 | 40 | 28 | 12 | 5 | 0 |
| max_age 2 | 45 | 39 | 21 | **18** | 6 | 0 |
| max_age 1 | 45 | 37 | 11 | **26** | 8 | 0 |
| max_age 0 | 45 | 35 | 7 | **28** | 10 | 0 |

`New = 0` everywhere, as a stricter bound logically requires; it is computed rather than assumed. The
"confirmed later" column is the population BB said could not be reached by deletion — for example
BTCUSDT's 2025-12-19 20:00 confirmation becoming 2025-12-25 20:00 under every stricter bound.

### Distributions (baseline)

- **R:R at confirmation** (n = 44): p10 0.05 · p25 0.19 · p50 0.98 · p75 2.59 · p90 10.70 · max 25.90
- **Confirming break age** (n = 45): p10 0 · p25 2 · p50 3 · p75 6 · p90 8 · max 10; distribution
  `{0:7, 1:4, 2:10, 3:7, 4:2, 5:3, 6:2, 7:3, 8:2, 9:2, 10:3}`
- **Side**: 12 LONG outcomes, 32 SHORT
- **Segment**: 21 outcomes in the first half-year, 23 in the second
- **Symbol**: DOTUSDT 11 · ADAUSDT 7 · DOGEUSDT 6 · ETHUSDT 4 · BNBUSDT 4 · XRPUSDT 4 · BTCUSDT 3 ·
  SOLUSDT 3 · LINKUSDT 2 · AVAXUSDT 0

## 10. Production-policy preservation

| Proof | Result |
|---|---|
| `evaluate_setup(inputs)` equals `evaluate_setup(inputs, research_confirmation_max_age=None)` | Asserted at five break ages |
| Override at the production constant matches production in state, direction, trigger, confirmation text, reference price, stop, targets, R:R and thesis | Asserted; only `policy_id` and one limitation line differ |
| `setup_assessment_for_sheet`, `setup_for_symbol`, `run_setup_for_symbols`, `run_market_scan` expose no research parameter and accept no `**kwargs` | Asserted against real signatures |
| No module outside `policy.py`, `compose.py` and `swing_setup/research_*.py` names the override | Asserted by scanning `src/fmis/**` |
| Live results never carry the research marker | Asserted |
| CLI refuses `--max-confirmation-age` without `--research` | Asserted; exits non-zero |
| The whole 380-day, 10-symbol baseline run reproduces bit-for-bit under the override at 10 | Measured — §8 |

## 11. Tests, coverage, mutations

**Tests: 4,488 collected before BC → 4,653 now (+165), all passing under `-W error`.**

- `tests/test_swing_setup_research.py` — 135 tests: window boundaries, segments, warm-up derivation,
  identity, replay index, harness integration, denominators, variant replay, post-filter versus
  replay, availability, model validation, rendering.
- `tests/test_swing_setup_research_boundary.py` — 30 tests: the production-preservation proofs above.

**Two long-standing test failures were resolved, and their cause is worth recording.** The suite had
carried two failures in `tests/test_swing_setup_scan_report.py` since Milestone AU — recorded on the
product backlog as "a float-formatting flake". They are neither a flake nor a source defect: a
git-ignored `__pycache__` entry for `scan_report.py`, dated 2026-08-07, had been compiled from a
version of that file using `,.2g` where the tracked source says `,.6g`, and its recorded source
mtime and size matched the current file exactly, so Python kept using it. The consequence was not
confined to tests — **`fmits scan` on this machine was printing prices in scientific notation**
(`target 1.3e+02` instead of `target 130`). Clearing `__pycache__` resolved both failures with no
source change; the full suite is now green.

Because that discovery casts doubt on any measurement taken before it, **the entire evidence run in
this report was re-executed from scratch on freshly compiled bytecode.**

**Coverage** (stdlib `sys.monitoring`; no coverage package is installed and none was added):

| Module | Lines | Covered |
|---|---|---|
| `research_models.py` | 400 | 92.2 % |
| `research_warmup.py` | 203 | 89.7 % |
| `research_identity.py` | 42 | 95.2 % |
| `research_harness.py` | 421 | 93.1 % |
| `research_metrics.py` | 156 | 90.4 % |
| `research_compare.py` | 126 | 92.1 % |
| `research_render.py` | 236 | 94.9 % |
| **Total** | **1,584** | **92.4 %** |

Uncovered lines are almost entirely defensive `raise TypeError` guards on constructors only the
harness itself calls.

**Mutation probes: 14 applied, 14 detected, 0 survivors.** All ten mutations the milestone brief
names are covered, plus four more. Every source was restored byte-identically, verified by SHA-256
rather than by trust.

| # | Mutation | Verdict |
|---|---|---|
| M1 | Warm-up boundary off by one | killed |
| M2 | Measurement-start inclusion (`>` for `>=`) | killed |
| M3 | Measurement-end inclusion (`<=` for `<`) | killed |
| M4 | Outcome-tail setup leak | killed |
| M5 | Research override folds `0` to production (falsy check) | killed |
| M6 | Research override reaches production by default | killed |
| M7 | Max-age comparison off by one | killed |
| M8 | Post-filter silently replaces the replay | killed |
| M9 | Later re-confirmation suppressed | killed |
| M10 | Policy-variant identity collision | killed |
| M11 | Temporal segment misclassification | killed (survived first pass; a membership test was added) |
| M12 | Warm-up ignores the requested analysis window | killed |
| M13 | Priming observations counted as measured | killed |
| M14 | Replay index answers a different set than the linear filter | killed |

## 12. Performance

| Operation | Cost |
|---|---|
| Seven full replays, 10 symbols, 380-day measurement window | 3,358 s (56 min) |
| Per simulated instant | ≈ 21 ms (≈ 160,000 instants) |
| AV 400-day comparison run | 269 s |
| Historical fetch | 30 (symbol, interval) pairs, once, reused by all seven variants |

`prepare_replay_index` replaces the replay transport's linear scan with a binary search over close
times. Without it the cost of one instant would grow with the length of history, which would penalise
a properly warmed dataset for being properly warmed. It changes no result; a test asserts
byte-identical transport responses with and without it.

## 13. Exact limitations

1. **The window is bounded by the youngest symbol.** 380 days, because AVAXUSDT's weekly history
   begins 2020-09-21. BTCUSDT alone could be measured from 2022-06-16. A common window was chosen so
   symbol comparisons are comparisons; the trade is stated, not hidden (`BC-3`).
2. **44 outcomes is a small sample.** Less concentrated than AV's 155, and de-duplicated rather than
   merely fewer — but small.
3. **Ten crypto majors co-move**, and 60-bar evaluation windows overlap. Concentration improved; the
   observations are not independent (`BC-8`).
4. **AVAXUSDT produced no outcome at all** in the measured window, and DOTUSDT produced a quarter of
   them.
5. **AV's identity defect is disclosed, not fixed in AV.** BC uses its own identity; `backtest_identity`
   is unchanged, so report 0011's counts stand as published and should be read with §7 beside them.
6. **Nothing here measures anything but the confirmation-age bound.** No other constant, timeframe or
   universe was varied (`BC-5`).
7. **No fees, slippage, spread, execution delay or position sizing**, and no realized PnL (`BC-1`).
8. **Concentration is reported, not solved.** Five outcomes still fall in one five-day span.

## 14. Files changed

**New (9)**

```
src/fmis/swing_setup/research_models.py
src/fmis/swing_setup/research_warmup.py
src/fmis/swing_setup/research_identity.py
src/fmis/swing_setup/research_harness.py
src/fmis/swing_setup/research_metrics.py
src/fmis/swing_setup/research_compare.py
src/fmis/swing_setup/research_render.py
tests/test_swing_setup_research.py
tests/test_swing_setup_research_boundary.py
```

**Modified (6)**

```
src/fmis/swing_setup/policy.py          research_confirmation_max_age, research_policy_id
src/fmis/swing_setup/compose.py         forwards the override on the one research seam
src/fmis/swing_setup/backtest_replay.py ReplayIndex / prepare_replay_index (performance only)
src/fmis/swing_setup/backtest_metrics.py percentiles_of / outcome_cohort made public for reuse
src/fmis/swing_setup/__init__.py        research exports
src/fmis/pipeline/cli.py                fmits backtest --research, --max-confirmation-age
```

**Release gates**

| Gate | Result |
|---|---|
| Full suite under `-W error` | 4,653 passed, 0 failed |
| No-lookahead suite | green (AV's and BC's) |
| Baseline production behaviour unchanged | proven — §10 |
| `pyproject.toml` / `uv.lock` | unchanged |
| Runtime dependencies added | 0 |
| Import cycles | 0 |
| Public export collisions | 0 |
| `git diff --check` | clean |
| Markdown relative links | all resolve |
| Pre-existing untracked research documents | untouched |
