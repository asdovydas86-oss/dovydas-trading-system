# Swing Strategy Laboratory & Historical Replay — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0033 |
| **Title** | Swing Strategy Laboratory & Historical Replay (Milestone BW) |
| **Date** | 2026-08-25 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `d8e1b9e`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final — independently verified at the BW release gate (§20) |

**Milestone:** BW — Swing Strategy Laboratory & Historical Replay.

**Scope guard.** No production trading policy changed. `CONFIRMATION_LOOKBACK_BARS`
is still `10`, `MINIMUM_AGREEING_FAMILIES` is still `2`, `DEFAULT_TIMEFRAMES` is
still 1W/1D/4H, and no threshold was tuned. **No strategy was promoted.** Nothing
in this report is a forward test.

---

## 1. The answer, first

The owner asked one question: **is the 1W gate too restrictive for swing trading?**

**No — and the question turns out to be the wrong one.** The measured answer is
that the weekly gate is not what is wrong with this strategy. Removing it
improves every headline figure, and the strategy is still loss-making after it
is removed. The binding defect is elsewhere and is arithmetic:

> **Over 2022-10-15 → 2026-08-01, on BTC/ETH/BNB/LTC, the current production
> policy produced 59 trades at an expectancy of −0.535R, a 34.6 % win rate and a
> profit factor of 0.16. Its average winner paid +0.301R while its average loser
> cost −0.978R. At a 34.6 % win rate, break-even needs an average winner of
> +1.848R. The strategy is short by 1.55R per winning trade.**

The cause is the stop/target geometry, not the gate. The policy places the stop
at the *nearest* execution-timeframe (4H) structural level and the target at the
*nearest* setup-timeframe (1D) structural level. Nothing requires the target to
be further away than the stop, and usually it is not: **48 % of baseline setups
had a planned reward smaller than their planned risk**, and **94 % of the trades
that actually reached their target returned less than +1R**.

A worked example from §9: a BTC short that *won* — it reached its target cleanly
in three bars — and returned **+0.879R**, because its target was closer than its
stop. A strategy whose wins pay less than its losses cost does not need a better
filter; it needs different geometry.

The 1W gate's real measured effect is in §8. It blocked 54.7 % of the instants it
judged, but only 14.6 % of them were blocks that removed anything. The 74 trades
it removed were themselves loss-making (−0.270R, n=69). **The gate is removing
bad trades from a bad strategy.** That is why loosening it raises the win rate
and still does not produce an edge.

**The owner's specific hypothesis is not supported.** Demoting 1W from gate to
context (`swing_1w_context`) improved on the baseline in the primary study and
was **worse** than the baseline in the held-out study (§8a), with more than twice
the drawdown. It is not a reliable improvement. Removing the weekly role from the
decision *entirely* (`swing_1d4h_core`) was consistently the least-bad of the
four in both studies — and is still loss-making.

**Classification (§16): every variant tested is REJECTED. There is no
promising candidate. The strategy is not ready for forward testing in any of the
four configurations measured.**

---

## 2. Starting Git state

```
branch            main
HEAD              d8e1b9eedcc22dc861bbb1ebfa5c8140597fe13e
                  docs(product): record Operator Dashboard V0 milestone
origin/main       d8e1b9e  (in sync, 0 ahead / 0 behind)
stash             empty
unresolved ops    none
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/ — untouched
```

The expected HEAD in the brief was verified and matched exactly.

---

## 3. Existing research architecture, reused rather than rebuilt

The mandatory audit found a mature research harness already in place from
Milestone BC (reports [0012](0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md)
and [0013](0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md)). **No
second backtester was built.** What BW reuses, by calling it:

| Concern | Reused from | How |
|---|---|---|
| No-lookahead replay transport | `swing_setup.backtest_replay` | `build_replay_transport`, `prepare_replay_index` — called |
| Derived warm-up | `swing_setup.research_warmup` | `derive_warmup`, `probe_availability` — called |
| Window boundaries | `swing_setup.research_models` | `ResearchWindow`, `TemporalSegment` — used |
| One fetch, many variants | `swing_setup.research_harness` | `fetch_research_dataset`, `decode_full_series` — called |
| Stable setup identity | `swing_setup.research_identity` | `OpportunityTracker` — called |
| Setup policy | `swing_setup.policy` | `evaluate_setup` — called, never reimplemented |
| Composition path | `swing_setup.compose` | `setup_inputs_and_assessment_for_sheet` — called |
| **Fill semantics** | `fmis.paper.fills` | `fill_at_level` — called (see below) |
| **Bar type and touch rule** | `fmis.paper.models` | `PriceBar.reached`, `.opened_beyond` — called |
| **Cost policy** | `fmis.trade_lifecycle` | `PaperCostPolicy` — the same versioned type paper trades carry |

The single most important reuse is the **fill rule**. The commonest way a
backtest flatters itself is inventing a slightly kinder definition of where an
order filled, so `fmis.swing_lab.trades` owns no fill rule at all: the gap rule
(*a level fills at the level unless the bar opened past it, in which case it
fills at the open*) is `fmis.paper.fills.fill_at_level`, called. An architecture
guard asserts the package defines no function named `fill_at_level`, `reached`,
`opened_beyond`, `stop_reached` or `_hits`.

One promotion was made to avoid a private cross-module import:
`research_harness._decode_full_series` → `decode_full_series`, exported.

---

## 4. Architecture added

**One new package, `fmis.swing_lab`** (11 modules, 971 statements), one new
command `fmits research`, and one new dashboard page `/lab`.

| Module | What it owns |
|---|---|
| `models.py` | `LabVariant`, `LabTrade`, `LabExitReason`, `GateVerdict` — the vocabulary |
| `variants.py` | The five **pre-specified** variants, fixed before any result was seen |
| `trades.py` | The trade loop, R/MFE/MAE bookkeeping, cost scenarios, `reprice` |
| `replay.py` | Facts-once/policy-many replay; gate attribution from facts |
| `metrics.py` | Expectancy, PF, drawdown, equity curve — every figure welded to its `n` |
| `gate.py` | What the 1W gate did, and the trades it removed |
| `robustness.py` | Chronological, walk-forward, symbol and direction splits |
| `study.py` | Orchestration, the manifest, the result digest |
| `artifact.py` | JSON research artifacts; the only module that touches a file |
| `render.py` | The terminal report |

### The one production seam

`evaluate_setup` gained a second **research-only** keyword,
`research_context_role`, following the exact discipline Milestone BC established
for `research_confirmation_max_age`:

```python
class ContextRoleTreatment(Enum):
    GATE_AND_VOTE = "gate_and_vote"   # production
    VOTE_ONLY     = "vote_only"       # 1W informs direction, cannot block
    IGNORED       = "ignored"         # 1W neither blocks nor votes
```

Three **discrete named semantics, deliberately not a threshold** — there is no
way to spell "gate on a weaker regime reading", because a threshold is exactly
what a researcher could shop for. Omitted, the parameter changes nothing and the
production `policy_id` is unchanged. Supplied, it stamps a research `policy_id`
and adds a limitation line saying the assessment is not what the live product
would have said. `research_policy_id(2)` still returns exactly
`swing-setup-v1+research(max_confirmation_age=2)`, so every BC-era id is
byte-identical.

### Facts once, policies many

`SetupInputs` is built from candles, indicators and regimes — none of which know
what a policy is. Only `evaluate_setup` differs between variants sharing an
interval mapping. So the lab computes the facts **once** per (symbol, instant)
and evaluates four policies over them.

This is not merely ~4× cheaper. It is what makes the comparison **exact**: four
separate replays would each re-derive the same numbers, and any provider or
floating-point difference between them would surface as a policy difference. A
mutation probe that forces all variants into one facts group is killed.

---

## 5. The pre-specified variants

Fixed in `variants.py` **before any history was replayed**. A variant added after
a result is seen is a new experiment, not a hypothesis.

| id | Context role (1W) | Intervals | Role |
|---|---|---|---|
| `swing_current` | gate **and** vote (production) | 1w/1d/4h | **Baseline** — no override supplied at all |
| `swing_1w_hard_gate` | gate and vote, stated explicitly | 1w/1d/4h | **Control** — must reproduce the baseline exactly |
| `swing_1w_context` | votes, cannot block | 1w/1d/4h | The owner's hypothesis |
| `swing_1d4h_core` | neither blocks nor votes | 1w/1d/4h | 1D + 4H decide alone |
| `swing_1d4h1h_roles` | production policy, remapped | **1d/4h/1h** | 4H forms the setup, 1H times entry |

Two design notes recorded before results:

- **A and B are the same policy, and that is the point.** The current production
  behaviour *is* the hard gate, so B is a control rather than a candidate. If B
  and A disagreed, the override machinery would be unfaithful and every
  counterfactual here would be worthless. §7 reports the measurement.
- **D makes the agreement rule stricter, not looser.** With the context family
  removed only two families remain, and `MINIMUM_AGREEING_FAMILIES` is
  **unchanged at 2** — so both must agree. Relaxing it to compensate would have
  been tuning. Both surviving families are computed from the same 1D candles,
  which makes D also a direct test of the evidence-independence concern.

**Nothing tunes a threshold.** No variant varies a lookback, a band,
`MINIMUM_AGREEING_FAMILIES` or a detection setting. A guard asserts the package
never assigns `MINIMUM_AGREEING_FAMILIES`.

---

## 6. Datasets, and the constraint that shaped them

The **weekly context role costs ~4.8 years of warm-up** before the measurement
window opens. This is not arbitrary: `derive_warmup` takes the maximum over the
production dependencies, and the 250-candle analysis window production itself
uses binds at 250 weekly candles = 1,750 days. Faithful replay requires it.

Measured earliest satisfiable `measurement_start` per symbol at 1w/1d/4h:

| Symbol | 1W history from | Earliest measurement start |
|---|---|---|
| BTCUSDT, ETHUSDT | 2017-08-14 | 2022-06-09 |
| BNBUSDT | 2017-11-06 | 2022-09-01 |
| LTCUSDT | 2017-12-11 | 2022-10-06 |
| XRPUSDT / ADAUSDT | 2018-04 | 2023-02 |
| LINKUSDT | 2019-01-14 | 2023-11-09 |
| SOLUSDT / DOTUSDT / AVAXUSDT | 2020-08+ | **2025-05 or later** |

SOL, DOT and AVAX cannot support a multi-year window at all under the production
mapping. This is limitation **BW-2** and it is the single largest constraint on
sample size in this study.

Two datasets were therefore pre-specified:

| Experiment | Symbols | Window | Span |
|---|---|---|---|
| **primary** | BTC, ETH, BNB, LTC | 2022-10-15 → 2026-08-01 | 3.79 y |
| **broad** | + XRP, ADA, LINK | 2023-11-15 → 2026-08-01 | 2.71 y |

Both were run. The broad study is a **symbol and window holdout** for the
primary result, and §8a reports where the two agree and where they do not.

The primary window deliberately spans the 2022 bear market (post-LUNA/FTX), the
2023 recovery, the 2024 bull and 2025–26 — four regimes rather than one.

Data source: **real Binance spot klines** through the existing provider. Bar
counts travel in every manifest. Nothing here is called "live": it is historical
replay and the report says so.

**Evaluation window: 180 execution bars (30 days on 4H)**, pre-specified. The
BC default of 60 bars (10 days) would systematically truncate a swing strategy
whose targets are 1D structural levels — the cap would cut off the strategy's own
thesis rather than measure it.

**Costs.** Two scenarios, both reusing `PaperCostPolicy`: frictionless (a stated
zero, not a forgotten multiplication) and a deliberately pessimistic 10 bp per
side on entry and exit notional. `reprice` recomputes a cost scenario from a
completed trade, so both scenarios describe the *identical* trades and any
difference between them is the cost model and nothing else. No venue is named
and no venue-specific fee is claimed.

---

## 7. No-lookahead, and the control

### Prefix equivalence, proved by mutating the future

A backtest cannot prove the absence of lookahead by inspection. `tests/test_swing_lab_nolookahead.py`
proves it by **changing the future and requiring the past not to notice**:

| Mutation | Requirement | Result |
|---|---|---|
| Every 4H candle **after** the measurement window scaled ×1000 | No observation may change | **Identical, variant for variant** |
| Every 4H candle after a mid-window cutoff scaled ×1000 | Earlier observations may not change | **Identical** |
| Gate attribution under the same tail mutation | Verdicts may not change | **Identical** |
| Every 4H candle in the **warm-up prefix** scaled ×1.5 | Observations **must** change | **Changed** ✅ |

The fourth is the control that stops the first three passing vacuously: a replay
that read nothing at all would pass all three. Three further tests assert the
fixture is capable of failing — that it produces measured observations, reaches a
directional state, and exercises the gate.

A **latent defect in this milestone's own fixture** was found here and fixed: the
first draft requested a 60-candle analysis window believing that would shorten
the warm-up. It does not — EMA(200) is a real production dependency and binds at
200 bars regardless. The fixture was silently under-warmed until
`run_lab_study`'s availability probe refused it, which is Milestone BC's
derivation doing exactly the job it was built for. `_TEST_LIMIT` is now 200.

### The control variant reproduced production exactly

On the primary study, `swing_1w_hard_gate` agreed with `swing_current` on **every
one of 33,264 observations and all 59 trades** — state, direction, setup id,
signal instant, net R and exit reason. The override machinery is faithful, and
every counterfactual below rests on that measurement rather than on an assertion.

---

## 8. Results — the primary study

```
Symbols            BTCUSDT, ETHUSDT, BNBUSDT, LTCUSDT
Measurement window 2022-10-15 → 2026-08-01     Warm-up from 2017-12-20
Evaluation window  180 execution bars (30 days)  Costs: frictionless
Result digest      b2ffcdce149f7c425cfec7638123a4a5a2daa0c05a303bc94e756107472ec2de
```

| | swing_current | swing_1w_hard_gate | swing_1w_context | swing_1d4h_core |
|---|---|---|---|---|
| Trades | 59 | 59 | 124 | 117 |
| Measurable | 52 | 52 | 112 | 105 |
| Ambiguous | 7 | 7 | 12 | 12 |
| Win rate | 34.6 % (n=52) | 34.6 % (n=52) | 46.4 % (n=112) | **55.2 %** (n=105) |
| **Expectancy (R)** | **−0.535** | −0.535 | −0.335 | **−0.144** |
| Median R | −1.000 | −1.000 | −1.000 | **+0.038** |
| Profit factor | 0.16 | 0.16 | 0.37 | **0.68** |
| Total R | −27.84 | −27.84 | −37.47 | −15.16 |
| Max drawdown (R) | −29.99 | −29.99 | −39.74 | **−23.28** |
| Avg MFE (R) | +4.05 | +4.05 | +2.39 | +2.03 |
| Avg MAE (R) | −4.78 | −4.78 | −3.92 | −2.43 |
| Avg bars held | 7.0 | 7.0 | 5.9 | 5.6 |

Every variant is loss-making. Loosening the context role monotonically improves
win rate, expectancy, median R, profit factor and drawdown — and never reaches
break-even.

### The geometry, which is the actual finding

| | swing_current | swing_1w_context | swing_1d4h_core |
|---|---|---|---|
| Average winner | +0.301R | +0.419R | +0.549R |
| Average loser | −0.978R | −0.988R | −1.000R |
| **Average winner needed to break even** | **+1.848R** | +1.140R | +0.810R |
| **Shortfall** | **−1.547R** | −0.720R | −0.261R |
| Median planned R:R | 1.05 | 0.89 | 0.71 |
| Setups with planned R:R < 1 | 25/52 (48 %) | 58/112 (52 %) | 59/105 (56 %) |
| Target-exits returning **< +1R** | 17/18 (94 %) | 45/52 (87 %) | 49/58 (84 %) |

Risk distance as a share of price: median 1.27 %, **minimum 0.0129 %** (1.3 basis points). A stop
placed 1.3 basis points from entry is not a swing-trading stop; it is noise. This
is also why average MAE reads −4.78R — with a tiny risk denominator an ordinary
4H candle range is several R. That figure was investigated as a suspected
simulator defect and confirmed correct against raw candles (§9).

### The 1W gate, measured exactly

| | Instants |
|---|---|
| Judged | 33,264 |
| Gate never reached (context INSUFFICIENT) | 0 |
| **Allowed** (weekly regime TRENDING) | 15,078 |
| **Blocked, total** | 18,186 — **54.7 %** of reached |
|  …with nothing to block | 13,314 |
|  …removing a CANDIDATE | 2,945 |
|  …removing a CONFIRMED setup | 1,927 |
| **Materially blocked** | 4,872 — **14.6 %** of reached |
| Blocked LONG / SHORT | 2,514 / 2,358 |

The two counts are reported separately deliberately. "The gate blocks 54.7 % of
instants" is true and misleading — the large majority of those instants had no
direction to block. The number that matters is 14.6 %.

**The trades the gate removed**, measured through the identical entry, stop,
target and cost rules — never by asking whether price later rose:

| gate_removed_setups | |
|---|---|
| Trades | 74 (69 measurable, 5 ambiguous) |
| Win rate | 49.3 % (n=69) |
| Expectancy | **−0.270R** (n=69) |
| Profit factor | 0.47 |
| Total R | −18.63 |

**The gate was removing losing trades.** Its removal is not free.

### Robustness — the negative result survives every split

`swing_current`, largest symbol share of gross R **33.1 %**, largest segment
share **37.1 %** — no single symbol or period dominates.

| Split | Cohorts | Agree on sign |
|---|---|---|
| Chronological | first half −0.470R (n=22) · second half −0.583R (n=30) | **yes** |
| Walk-forward | year 1 −6.51R · year 2 −9.18R · year 3 −12.16R total | all negative |
| Symbol | BNB −11.19R · BTC −2.66R · ETH −5.27R · LTC −8.71R total | all negative |
| Direction | long −0.587R (n=27) · short −0.479R (n=25) | **yes** |

Every split, every year, every symbol and both directions are negative. This is
not a one-regime artifact.

**One post-hoc observation, flagged as post-hoc.** Under `swing_1d4h_core` the
SHORT cohort is marginally positive (+0.056R, PF 1.14, n=43) while LONG is
−0.283R (n=62). This was **not** pre-specified, n=43 is barely above the sample
floor, and the split was examined after the result. It is recorded as a
**hypothesis for a future experiment**, not a finding, and it must not be used
to justify a short-only policy.

---

## 8a. The broad study — a symbol and window holdout

Seven symbols over a different, shorter window. Neither the universe nor the
period overlaps the primary study exactly, so this is a genuine holdout rather
than a re-slice.

```
Symbols            BTC, ETH, BNB, LTC, XRP, ADA, LINK
Measurement window 2023-11-15 → 2026-08-01  (2.71 y)
Result digest      d3bb0716bff13eb6…
```

| | swing_current | swing_1w_hard_gate | swing_1w_context | swing_1d4h_core |
|---|---|---|---|---|
| Trades | 87 | 87 | 159 | 149 |
| Measurable | 79 | 79 | 145 | 133 |
| Win rate | 45.6 % (n=79) | 45.6 % (n=79) | 49.0 % (n=145) | **57.9 %** (n=133) |
| **Expectancy (R)** | **−0.239** | −0.239 | **−0.260** | **−0.088** |
| Median R | −1.000 | −1.000 | −1.000 | **+0.038** |
| Profit factor | 0.55 | 0.55 | 0.48 | **0.79** |
| Total R | −18.91 | −18.91 | −37.74 | −11.66 |
| Max drawdown (R) | −19.97 | −19.97 | −37.74 | −25.49 |

The control reproduced the baseline exactly again — all 87 trades.

**Two findings, and the second changes the answer to the owner's question.**

1. **The negative result holds on a held-out universe and window.** Every
   variant is loss-making in both studies. `swing_1d4h_core` is the best of the
   four in both, and negative in both.

2. **The owner's hypothesis does not survive the holdout.** In the primary study
   `swing_1w_context` improved on the baseline (−0.335R vs −0.535R). Here it is
   **worse** than the baseline (−0.260R vs −0.239R), with more than twice the
   drawdown (−37.74R vs −19.97R). So *"1W should be context rather than a gate"*
   is **not a reliable improvement** — its apparent benefit in the primary study
   did not reproduce. What did reproduce, in both studies, is that removing the
   weekly role **entirely** (`swing_1d4h_core`) is the least-bad of the four.

That distinction matters. The hypothesis as stated — demote 1W from gate to
context — is **not supported**. The adjacent variant that removes 1W from the
decision altogether is consistently better, and still does not make money.

---

## 9. One trade, reconciled by hand against raw candles

```
TRADE  BTCUSDT short   setup=BTCUSDT|short|from=2022-10-21T00:00:00+00:00
  signal bar close   2022-10-20T20:00  (close 19041.92)
  entry (next open)  2022-10-21T00:00  @ 19041.92
  initial stop       19180.21          target  18920.35
  exit               2022-10-21T08:00  @ 18920.35   (target)
  bars held 3   net R 0.8790946561573504953358883506
```

Raw Binance 4H candles, fetched independently:

| open_time | open | high | low | close | |
|---|---|---|---|---|---|
| 2022-10-20T20:00 | 19063.04 | 19098.00 | 18929.38 | 19041.92 | signal bar |
| 2022-10-21T00:00 | 19041.92 | 19131.39 | 18999.00 | 19051.77 | **entry at this open** |
| 2022-10-21T04:00 | 19051.19 | 19084.17 | 18991.69 | 19027.86 | neither level touched |
| 2022-10-21T08:00 | 19028.68 | 19041.96 | **18900.00** | 18945.65 | low ≤ target → **exit** |

Hand arithmetic: risk = |19041.92 − 19180.21| = **138.29**; reward =
19041.92 − 18920.35 = **121.57**; R = 121.57 / 138.29 = **0.87909465615735…** —
matching the engine to every recorded digit. The path check confirms no earlier
bar touched either level.

**This trade is a winner that pays +0.879R**, because its target sat closer than
its stop. It is the whole finding in one record.

---

## 10. Defects found

| # | Defect | Where | Status |
|---|---|---|---|
| 1 | **Winners pay less than losers cost.** Target is the nearest 1D level, stop the nearest 4H level; nothing requires reward > risk, and 48 % of setups have R:R < 1. | **Production** `swing_setup.policy` | **Reported, not fixed** — a policy change is the owner's decision |
| 2 | Stops can be placed **1.3 bp** (0.013 % of price) from entry, so an ordinary candle is several R | **Production** `swing_setup.policy._nearest` | Reported |
| 3 | Milestone BW's own no-lookahead fixture was under-warmed (EMA(200) binds, not `limit`) | This milestone's tests | **Fixed** — `_TEST_LIMIT` 60 → 200 |
| 4 | Two mutation probes survived: MFE/MAE swap on the normal exit path, and an ambiguity flip | This milestone's tests | **Fixed** — five tests added, both now killed |
| 5 | Four public-name collisions with existing packages | `fmis.swing_lab` exports | **Fixed** — renamed to `LabEquityPoint`, `LabExitReason`, `lab_breakdown_by`, `compute_lab_metrics`, `LabMeasure`, `LabDrawdownReading` |
| 6 | A lab study could not be pickled (`mappingproxy`), losing an 11-minute run | Research runner | **Fixed** — JSON artifacts, and results print before persisting |

Defects 1 and 2 are **production findings and are deliberately not fixed here**.
BW is a measurement milestone; changing the stop or target rule on the strength
of a backtest, in the same milestone that built the backtest, is exactly the
sequence this brief forbids.

### Methodology corrections made during the milestone

- **Entry moved to the next bar's open.** BC's `evaluate_outcome` treats the
  confirming close as the reference price. Filling at the close you were looking
  at when you decided is a one-bar lookahead in a realism costume, so the lab
  fills at the open of the bar *after* the signal, matching
  `fmis.paper.fills.entry_reached`. R is measured against the **actual fill**,
  not the planned reference price.
- **A gapped entry is recorded, never skipped.** Skipping would delete exactly
  the worst fills.
- **A time stop is an exit, not a deletion.** Dropping unresolved trades would
  silently remove every slow loser.

---

## 11. Verification

| Gate | Result |
|---|---|
| Focused BW suite | **273 tests**, all passing |
| Full repository under `-W error` | 10,671 → **10,969 passing**, 0 failures |
| Coverage of `fmis.swing_lab` (statement + branch) | **95 %** (993 statements, 34 missed; 234 branches, 26 partial). `variants.py`/`__init__.py` 100 %; `study.py` 98 %; lowest is `replay.py` 88 %. **Not 100 %** — the misses are listed in §20 |
| **Mutation probes** | **35 / 35 killed**, byte-exact in-memory restoration verified by SHA-256, bytecode cleared each probe |
| Architecture guards (new) | 89, all passing |
| Independent re-run (fresh fetch + full replay) | **digest reproduced exactly** (§20) |
| Existing regressions | backtest/research 229 · swing_setup 733 · dashboard 858 — all green |
| Import cycles | 0 across the package |
| Export collisions | 0 (four found and fixed) |
| New runtime dependencies | 0 |
| ADRs required | 0 |
| Guards weakened | **0** |

### Guards widened, each with its reason recorded in the test

Seven repository guards were widened. None was weakened: every one admits
`fmis.swing_lab` as a named application-layer or research root and continues to
assert the property it exists to protect.

- `test_structural_facts` / `test_multi_timeframe` — a fifth application-layer
  root above `swing_setup`; the direction rule (no engine reaches upward) is
  unchanged.
- `test_decision_context` / `test_market_regime` — the lab reads `ContextState`
  and `StructureState` to *attribute* what the production gate did; it
  classifies nothing and re-decides nothing.
- `test_swing_setup_research_boundary` — the research-override prefix now admits
  `swing_lab/`, on the same containment footing as `swing_setup/research_*`.
- `test_trade_capture_architecture` — the CLI may import the lab. The note
  records what this does *not* admit: the lab opens one file, that file is a
  research artifact rather than the trading store, and the CLI decodes it so the
  dashboard can keep opening nothing.
- `test_directional_vocabulary_boundary` (**ADR-0028 §5**) — the lab may spell
  LONG/SHORT because a trade record must say which way it went. Two **new**
  companion guards pin what this does not permit: the lab never derives a
  direction (every `Direction` is copied from an assessment), and it may not
  reach `_tally`, `_trend_lean`, `_evidence_lean` or `_directional_factors`. The
  market half remains scanned and remains clean.
- Four command-roster guards — `research` is additive and replaces nothing.

---

## 12. Hostile review

Attacked deliberately; each row is a case that was run.

| Attack | Behaviour |
|---|---|
| Zero trades / one trade / empty sample | Figures absent with a reason and the count visible; no crash, no zero |
| Sample below the floor | `LabMeasure` refuses a value and states `n`; never a precise-looking lie |
| No losing trade | Profit factor absent — *"no denominator"* — never infinity |
| Ambiguous bar (stop and target together) | Refused, excluded from expectancy, counted beside it |
| Green vs red ambiguous bar | Judged identically — candle colour resolves nothing |
| Entry gaps through the stop | Recorded as a loss at the fill, never skipped |
| Entry gaps past the target | Not a free win — no trade |
| Gap through the stop | Fills at the open (worse), not at the level: verified −1.5R not −1R |
| Signal bar pierces both levels | Cannot resolve the trade — the trade starts on the next bar |
| One symbol / one year / one regime dominating | Measured: 33.1 % and 37.1 % — reported, not assumed |
| Costs turning an edge negative | Both scenarios reported; the edge was already negative |
| Shuffled symbol order / `PYTHONHASHSEED` | Digest invariant — trades sorted by identity, not iteration order |
| An edited artifact | `verify_digest` fails |
| Overwriting an experiment | Refused |
| A suspiciously large MAE (−4.78R) | **Investigated as a suspected defect and confirmed correct** against raw candles — a real consequence of stops as tight as 1.3 bp |

The last row is the one worth naming. A figure that looked wrong was treated as
a possible flattering error and chased to raw provider data before being
believed.

---

## 13. Performance

| Measurement | Value |
|---|---|
| Per replayed instant (facts + 4 policy evaluations) | **~20 ms** |
| Primary study (4 symbols × 3.79 y = 33,264 instants × 4 variants) | **11.0 min** |
| Broad study (7 symbols × 2.71 y = 41,496 instants × 4 variants) | **14.8 min** |
| Speed-up from facts-once/policy-many | ~4× on a 4-variant group |

The 1D/4H/1H variant needs ~4× the instants of the production mapping (1H
execution), which is why it is reported separately in §15.

---

## 14. Surfaces

### `fmits research swing`

```
fmits research swing BTCUSDT ETHUSDT --start 2022-10-15T00:00:00+00:00 \
    --end 2026-08-01T00:00:00+00:00 --robustness --save study.lab.json
```

Variants are **defined in code and cannot be described on the command line** — a
policy invented at a shell prompt is a policy nobody pre-specified. `--variant`
selects from the pre-specified set by id. `--costs` chooses a scenario;
`--save` writes a research artifact and refuses to overwrite one. There is no
flag that changes a production strategy.

### Dashboard `/lab`

A read-only page showing a **saved** experiment: window, symbols, cost basis,
digest and whether it verifies; the variant comparison table with every `n`; the
gate's two block counts kept apart; each variant's pre-specified hypothesis and
`policy_id`; and the limitations in full. With no artifact loaded it says so
plainly rather than rendering an empty table that would read as *"no edge
found"*.

**The dashboard still opens no file.** Its architecture guard forbids `open()`
anywhere in the package, so the artifact is decoded by the CLI
(`fmits dashboard --lab-artifact PATH`) and handed in already parsed. A new guard
asserts no dashboard module imports `fmis.swing_lab`. All 858 dashboard tests
pass unchanged, including every AST guard — no arithmetic, no sort, no colour in
the contract layer.

There is no production-change control and no "use this strategy" button.

---

## 15. Limitations

`LAB_LIMITATIONS` travels inside every artifact and prints on every report.
BW-1…BW-7 in full are in `study.py`; the three that most change what the numbers
mean:

- **BW-2** — the measurement window is bounded by the weekly warm-up (~4.8 y),
  which excludes younger symbols entirely and is the largest constraint on
  sample size here.
- **BW-4** — trades are simulated one at a time with no portfolio, no position
  sizing and no concurrency limit. Expectancy in R is a **per-trade** statistic
  and is **not** a claim about account return.
- **BW-7** — nothing here is a forward test. Every figure is in-sample with
  respect to the repository's own history: the policy was written by people who
  had already lived through this price data.

Additionally: outcomes overlap on co-moving symbols (BW-5), so trades are not
independent observations and every implied confidence interval is narrower than
the truth.

### Work not completed

The **`swing_1d4h1h_roles` variant (1D context / 4H setup / 1H execution) was
specified but not measured.** It requires ~4× the instants of the production
mapping and did not fit inside this session alongside the primary and broad
studies. It is fully implemented and runnable —
`fmits research swing … --variant swing_1d4h1h_roles` — and is the first thing a
follow-up should run. Its absence is why §16 says *inconclusive* about the
timeframe-remap hypothesis specifically, rather than rejecting it.

---

## 16. Classification and recommendation

| Variant | Classification | Why |
|---|---|---|
| `swing_current` | **REJECTED** | −0.535R expectancy, PF 0.16, negative in every split, year, symbol and direction |
| `swing_1w_hard_gate` | **CONTROL — passed** | Reproduced the baseline exactly; not a candidate |
| `swing_1w_context` | **REJECTED** | The owner's hypothesis. Better than baseline on the primary study (−0.335R), **worse** on the holdout (−0.260R vs −0.239R) with 2× the drawdown. Not a reliable improvement, and negative in both |
| `swing_1d4h_core` | **REJECTED** | Consistently best of the four across both studies (−0.144R / −0.088R, PF 0.68 / 0.79) and loss-making in both |
| `swing_1d4h1h_roles` | **INCONCLUSIVE** | Specified and implemented; not measured (§15) |

**No variant is a promising candidate. Nothing is recommended for forward
testing.** Forward-testing a policy with a measured negative expectancy would
spend months confirming what 11 minutes of replay already established.

### What the evidence actually recommends

1. **Fix the geometry before re-testing any gate policy.** The binding constraint
   is that winners pay less than losers cost. A minimum reward-to-risk floor at
   setup formation, or a target chosen from a higher timeframe than the stop by
   construction, is the change the data points at. This is a **production policy
   change and therefore an owner decision**, not something this milestone makes.
2. **Re-run the same five variants after that change.** The laboratory exists
   now; re-measuring is one command. The gate question is worth re-asking once
   the strategy has a positive expectancy to protect — the current answer
   ("the gate removes losing trades") may reverse when the trades stop losing.
3. **Run `swing_1d4h1h_roles`** to close the one specified variant left unmeasured.

### Forward-test handoff

The output is already shaped for a later shadow/forward milestone: `LabVariant`
carries a stable `variant_id` and a `policy_id`, `LabTrade` is the outcome
schema, and the manifest plus `result_digest` make a run rebuildable and
checkable. A forward layer can name `swing_1d4h_core` and reuse the identical
version and schema without rewriting either. **No EVEDEX integration exists or
was added.**

---

## 17. Changed files

**New (`src/`):** `fmis/swing_lab/{__init__,models,variants,trades,replay,metrics,gate,robustness,study,artifact,render}.py`

**Modified (`src/`):**
- `fmis/swing_setup/policy.py` — `ContextRoleTreatment`, the research-only override
- `fmis/swing_setup/compose.py` — forwards the override
- `fmis/swing_setup/__init__.py` — exports the new names
- `fmis/swing_setup/research_harness.py` — `_decode_full_series` → public
- `fmis/pipeline/cli.py` — `fmits research`; `--lab-artifact` on `fmits dashboard`
- `fmis/operator_dashboard/{models,sections,render,compose,server}.py` — the `/lab` page

**New (`tests/`):** `swing_lab_helpers.py`, `test_swing_lab_{trades,metrics,policy,replay,nolookahead,architecture,artifact,render}.py`

**Modified (`tests/`):** the seven widened guards listed in §11.

**Documentation:** this report; `reports/README.md`; `docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated: BW delivers a research
capability and a read-only page, and its headline result is that the strategy
does not work. Recording that as a user-visible capability release would
misrepresent it.

---

## 18. Git state at completion

**Nothing was committed and nothing was pushed**, as instructed.

Two commits are **prepared but not created**:

```
Commit A   feat(research): add Swing Strategy Laboratory
Commit B   docs(product): record Swing Strategy Laboratory milestone
```

`HEAD` remains `d8e1b9e`, `origin/main` remains `d8e1b9e`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.

---

## 19. Research philosophy, honoured

The brief asked for the truth rather than a defence of the system, and named
three equally useful outcomes. This milestone returned the second and third at
once: **the 1W gate is not what is wrong**, and the reason it is not is that the
strategy's own trade geometry loses money before any filter is applied. The gate
was removing losing trades from a losing strategy.

That is a more useful answer than the one the hypothesis expected, and it was
only available because the measurement was built to be able to say it.

---

## 20. Independent release-gate verification (2026-08-25)

BW was re-verified from the repository state before release, independently of
the implementation session. What was checked and what it found:

### Reproduced independently

| Check | Result |
|---|---|
| Starting `HEAD` / `origin/main` / `git ls-remote` | all `d8e1b9e`, 0 ahead / 0 behind, no stash, no in-progress operation |
| **Production behaviour unchanged** | `evaluate_setup` with no override compared against the committed `HEAD` copy across **115,200 input combinations** — **0 mismatches** |
| **Deterministic re-run** | primary study re-fetched and re-replayed from scratch: digest `b2ffcdce…` **reproduced exactly** |
| **Production control** | `swing_1w_hard_gate` ≡ `swing_current`: 59 trades, 52 measurable, 18 W / 34 L, identical expectancy, PF and total R; 33,264 gate instants |
| Every headline statistic | recomputed from raw JSON trade fields: expectancy, win rate, PF, average win/loss and the break-even requirement all reconcile |
| Geometry distributions | 48.1 % of setups reward < risk; 94.4 % of target-exits < +1R — both confirmed |
| **Six representative trades** | winner, loser, reward<risk, tightest stop, time stop and ambiguous — all reconciled against freshly fetched candles, **0 mismatches** |
| Reuse claims | all nine (replay transport, warm-up, identity, fill rule, bar type, cost policy, policy, composition root, dataset fetch) confirmed as imports |
| Absences | no execution verb, no `RecordKind`, no `TradingStore`, no persistence root, no AI client, no EVEDEX, no duplicated market calculation |
| Holdout separation | variants are frozen `mappingproxy` constants; tampering with the module-level interval dict does not reach a constructed variant; no module-level cache, no global state, no result-dependent logic in `variants.py` |
| Hostile review | **36 probes, 0 failures** — zero/one trade, all winners, all losers, zero risk, reward = 0, tightest and largest stops, gaps both ways, same-bar ambiguity, duplicate identities, missing horizon, invalid timestamps, impossible bars, long-text and script injection on `/lab` |

### Defects the release gate found and fixed

| # | Defect | Fix |
|---|---|---|
| 7 | **Documentation overstated the tightest stop by 10×** — the minimum risk distance is 0.0129 % of price = **1.29 basis points**, documented as "13 basis points". The error *understated* the severity | Corrected in this report and `CURRENT_STATE.md`. The tightest observed stop is BNBUSDT 2024-12-24, entry 696.89, stop 696.80 — a risk of **0.09** on a 696.89 price |
| 8 | **`/lab` carried no verdict.** The page showed expectancy without stating what the study concluded, leaving a reader to classify variants themselves | Added `LabVerdict` (`INCONCLUSIVE` / `REJECTED` / `CANDIDATE_FOR_FORWARD_TEST`) and `classify`, derived from the measured expectancy alone so it is reconstructable from the artifact. Rendered as a column and a panel. `is_approved_for_trading` is `False` for every verdict, by construction |
| 9 | **The result digest's order-invariance was untested within a variant.** A mutation probe reducing the sort key to the variant id survived: the existing test only permuted trades *across* variants | Two regressions added — a within-variant permutation, and a distinctness check. The probe is now killed |

Sixteen tests were added closing 8 and 9. No production trading rule was touched:
`CONFIRMATION_LOOKBACK_BARS` is still 10, `MINIMUM_AGREEING_FAMILIES` still 2,
`DEFAULT_TIMEFRAMES` still 1W/1D/4H, and the 115,200-combination differential
above was re-run after every change.

### Coverage, stated honestly

**95 %**, not 100 %. 993 statements with 34 missed; 234 branches with 26 partial.

| Module | Cover | Missed |
|---|---|---|
| `__init__.py`, `variants.py` | 100 % | — |
| `study.py` | 98 % | 198, 313→316 |
| `models.py` | 98 % | 198, 270 |
| `metrics.py`, `render.py`, `robustness.py` | 97 % | 152/233/237, 51/137→141, 73 |
| `artifact.py` | 95 % | 138, 246, 274 |
| `gate.py` | 93 % | 124–125, 137→131 |
| `trades.py` | 90 % | 117–120, 139, 209, 352, 354, 373 |
| `replay.py` | 88 % | 138, 169, 181, 236, 239, 246, 270, 306–311, 382 |

The uncovered lines are defensive guards on paths the offline fixtures cannot
reach (a dataset missing a series, a symbol whose signal instant is absent from
its own decoded series) and unreachable `pragma`-style branches.

### Verdicts as released

Derived by `classify` from each variant's own measured expectancy, and
recomputable from the artifacts:

| Variant | Primary | Broad (holdout) |
|---|---|---|
| `swing_current` | REJECTED (−0.5354, n=52) | REJECTED (−0.2394, n=79) |
| `swing_1w_hard_gate` | REJECTED (−0.5354, n=52) | REJECTED (−0.2394, n=79) |
| `swing_1w_context` | REJECTED (−0.3345, n=112) | REJECTED (−0.2603, n=145) |
| `swing_1d4h_core` | REJECTED (−0.1444, n=105) | REJECTED (−0.0877, n=133) |
| `swing_1d4h1h_roles` | **INCONCLUSIVE** — specified and implemented, still not measured | — |

`swing_1d4h1h_roles` remains INCONCLUSIVE. The release gate did not run it and
did not reclassify it.

**No variant is approved for forward or live testing.** The strongest verdict
this system can produce means *worth testing forward*, and no variant reached
even that.
