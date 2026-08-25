# Swing Trade Geometry Research & Policy Candidates — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0034 |
| **Title** | Swing Trade Geometry Research & Policy Candidates (Milestone BX) |
| **Date** | 2026-08-25 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `f5d59df`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final |

**Milestone:** BX — Swing Trade Geometry Research & Policy Candidates.

**Scope guard.** No production trading policy changed. The stop rule is still the
nearest execution-timeframe level, the target rule is still the nearest
setup-timeframe level, `CONFIRMATION_LOOKBACK_BARS` is still `10`,
`MINIMUM_AGREEING_FAMILIES` is still `2`, and `DEFAULT_TIMEFRAMES` is still
1W/1D/4H. **No geometry was promoted.** Nothing here is a forward test.

---

## 1. The answer, first

> **Do we now have a swing strategy candidate that deserves forward/shadow
> testing?**
>
> **No.** All thirteen pre-declared geometries are REJECTED. Every one of them
> lost money on the development sample, and the criteria that would have to be
> met before anything could be proposed are reported individually, by name, for
> each.

But the milestone did not come back empty. It came back with a **mechanism**,
and with a refutation of the obvious fix:

> **The "minimum R:R" hypothesis is not merely unsupported — it is backwards.**
> Requiring a minimum planned reward-to-risk made the development sample
> **worse**, from −0.276R to −0.605R, and collapsed the win rate from 45.5 % to
> 6.5 %. The reason is arithmetic: in this system a high planned R:R is produced
> by a **tight stop**, not by a distant target. Measured on both samples
> independently, the rank correlation between planned R:R and the
> volatility-normalised stop distance is **−0.65**. Setups planning ≥ 3.0R carry
> a median stop of **0.22 ATR**; setups planning < 1.0R carry a median stop of
> **1.31 ATR**. Filtering for R:R selects precisely the trades whose stops sit
> inside a fifth of an average bar's range.

And the diagnosis that explains it, from 240 reconstructed trades:

| Measurement | Development | What it means |
|---|---|---|
| Setups planning reward < risk | **45/85 (52.9 %)** | BW's 48 % reproduced on a new window and universe |
| Target exits returning under +1R | **30/35 (85.7 %)** | the winner is small *by design* |
| Stops inside one ATR(14) | **41/85 (48.2 %)** | half the stops are inside ordinary noise |
| Trades giving back a full R of open profit | **53/77 (68.8 %)** | exit management, not geometry |
| **Stop-outs whose target was reached afterwards** | **30/41 (73.2 %)** | **the finding** |
| Trades resolving in a single 4H bar | 54/85 (63.5 %) | this is not swing trading |

**Three quarters of stopped-out trades had their original target reached later,
inside the same evaluation window.** The thesis was right and the stop was
wrong. On the full 240-trade set the figure is 85/112 (75.9 %).

**The mechanism the evidence points at — and its honest verdict.** Relocating the
stop to the nearest *real* 4H level at least 0.5 ATR away, and requiring a real
1D level that pays the risk, produces a positive expectancy on both samples
frictionless (+0.212R development, +0.174R holdout) and survives a pessimistic
10 bp/side cost (+0.079R / +0.050R). **It is still rejected**, for three reasons
stated plainly: it was constructed **after** the results were seen, it is a
**single grid point** — its neighbours at 0.25 ATR and 0.75 ATR both fail under
costs — and §9 rejects a spike. It is recorded as the recommended hypothesis for
the next milestone, pre-declared there, never as a candidate here.

---

## 2. Starting Git state

```
branch            main
HEAD              f5d59df2851974292d08a7e4d7c311e7f77b6ca3
                  docs(product): record swing strategy research milestone
origin/main       f5d59df  (verified by `git ls-remote`; 0 ahead / 0 behind)
stash             empty
unresolved ops    none
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/ — untouched
```

Note that Milestone BW **is** committed, at `ba6ea8c` (code) and `f5d59df`
(docs), despite report 0033 §18 describing it as uncommitted — 0033 is a
point-in-time record and is not revised.

---

## 3. Architecture ownership map

The mandatory audit found every calculation BX needs already owned somewhere. No
engine was rebuilt.

| Concern | Owner (existing) | How BX uses it |
|---|---|---|
| Direction and admission | `swing_setup.policy.evaluate_setup` | **called**, unchanged, held fixed for every geometry |
| Level *ordering* | `swing_setup.policy` | `_nearest` **promoted** to `ordered_levels` (§4) |
| The level lists themselves | `SetupInputs.execution_levels` / `.setup_levels`, and `sheet.by_role[CONTEXT].sheet.structure.levels` | read by reference; no level is ever constructed |
| Volatility | `features.indicators.atr.AverageTrueRange`, already computed by `pipeline.regime.regime_features()` on every view | **read** from the fact sheet; no volatility engine added |
| Replay transport / warm-up / windows | `swing_setup.backtest_replay`, `research_warmup`, `research_models` | called |
| Setup identity | `swing_setup.research_identity.OpportunityTracker` | called |
| Fill rules, bar type, gap rule | `paper.fills`, `paper.models` | called — BX defines none |
| Trade simulation | `swing_lab.trades.simulate_trade` (BW) | called |
| Metrics, sample floor, drawdown | `swing_lab.metrics` | called |
| Robustness splits | `swing_lab.robustness` | called |
| Cost policy | `trade_lifecycle.PaperCostPolicy` | called |

**One defect found in the audit and fixed.** `fmits research swing` crashed on
**every** invocation: `cli.py` referenced `DEFAULT_BACKTEST_LIMIT` without
importing it (`NameError`). No test exercised `_run_research`, which is how it
shipped. Milestone BW's own results were produced through the Python API, so its
figures are unaffected — but the command the report advertised did not run. Fixed
by adding the import; a CLI regression now covers the path.

---

## 4. The one production seam

`swing_setup.policy._nearest` selected the closest level; BX needs the *second*
and *third*. Rather than copy the ordering into the research layer — where it
could silently drift from production's — the rule was **promoted**:

```python
def ordered_levels(levels, *, side, close, above) -> tuple[PriceLevel, ...]:
    """Every level of `side` strictly above/below `close`, nearest first."""

def _nearest(levels, *, side, close, above):
    candidates = ordered_levels(levels, side=side, close=close, above=above)
    return candidates[0] if candidates else None
```

`_STOP_SIDE`/`_TARGET_SIDE` were likewise promoted to public `STOP_SIDE`/
`TARGET_SIDE`, with the private names kept as aliases to the *same objects*, so
no existing import changes meaning.

**Proved equivalent, not assumed.** A differential over **16,000 cases** with
heavy deliberate price ties compared the new `_nearest` against the committed
implementation and found **0 mismatches** — by object identity, not equality.
And the whole-system proof: the BW primary study re-ran end to end and reproduced
its digest exactly (§5).

---

## 5. Baseline reproduction — exact

BW's primary study was re-run from scratch after the refactor:

```
fmits research swing BTCUSDT ETHUSDT BNBUSDT LTCUSDT \
  --start 2022-10-15T00:00:00+00:00 --end 2026-08-01T00:00:00+00:00 \
  --window 180 --robustness
```

| | BW report 0033 | This re-run |
|---|---|---|
| Result digest | `b2ffcdce149f7c42…` | **`b2ffcdce149f7c425cfec7638123a4a5a2daa0c05a303bc94e756107472ec2de`** |
| Trades (4 variants) | 59 / 59 / 124 / 117 | **identical** |
| `swing_current` expectancy | −0.535R (n=52) | **−0.535R (n=52)** |
| Win rate · PF · Total R | 34.6 % · 0.16 · −27.84 | **identical** |
| Gate-removed trades | 74, −0.270R (n=69) | **identical** |
| Walk-forward year totals | −6.51 / −9.18 / −12.16 | **identical** |
| Per-symbol totals | BNB −11.19 · BTC −2.66 · ETH −5.27 · LTC −8.71 | **identical** |

The digest covers all 359 trades across four variants. It would change if any
level selection, instant enumeration or fill differed. **The refactor is
faithful and BW's result stands.**

---

## 6. Datasets, and the sample-size problem BW named

BW's limitation BW-2 — the weekly warm-up costs ~4.8 years and excludes younger
symbols — was the binding constraint on its 59-trade sample. BX attacked it by
**probing the universe** rather than accepting BW's four symbols.

Forty-four candidate USDT pairs were probed for weekly history. Seventeen can
support a measurement window opening 2023-06-01. Two — **EOSUSDT and NULSUSDT** —
met the history requirement but **stopped trading inside the window** and were
dropped rather than measured over a truncated span (limitation **BX-3**: this is
survivorship filtering and it flatters every variant equally).

| Sample | Symbols | Rationale |
|---|---|---|
| **Development** (6) | BTC, ETH, BNB, LTC, XRP, ADA | **Every symbol Milestone BW already measured.** Contaminated by construction |
| **Holdout** (9) | NEO, QTUM, IOTA, XLM, ONT, ETC, ICX, TRX, VET | **Never measured by this repository**, identical window |

```
Measurement window  2023-06-01 → 2026-08-01  (3.17 y)   warm-up from 2018-08-06
Instants replayed   104,130 measured        Capture time 39 min (~22 ms/instant)
Candidates captured 246   (88 development · 158 holdout)
Evaluation window   180 execution bars (30 days on 4H)
```

**Why the holdout is a symbol split rather than a date split.** BW diagnosed the
geometry defect *on* BTC/ETH/BNB/LTC/XRP/ADA, and BX's hypotheses were written
after reading that diagnosis. No policy written now is out-of-sample on those
symbols, whatever a date split would claim. A symbol set this repository has
never looked at is the honest holdout available. A chronological split is still
run **inside** development, as one of four robustness splits, and is reported as
what it is — a test of whether a result is one period — not as a holdout.

Both samples are cut from **one capture**, so they see byte-identical candidate
facts. Two replays would re-derive them and any provider difference would surface
as a sample difference.

---

## 7. The thirteen pre-declared geometries

Fixed in `geometry_variants.py` **before any history was replayed**, following
the brief's families A–F.

| id | Family | Stop | Target | Admission |
|---|---|---|---|---|
| `geom_production` | A baseline | nearest 4H | nearest 1D | none — **control** |
| `geom_min_rr_1` … `_2` (4) | B | nearest 4H | nearest 1D | planned R:R ≥ 1.0 / 1.25 / 1.5 / 2.0 |
| `geom_min_stop_0_5atr` … `_1_5atr` (3) | C | nearest 4H | nearest 1D | risk ≥ 0.5 / 1.0 / 1.5 × ATR(14) |
| `geom_setup_stop` | D | **nearest 1D** | nearest 1D | none |
| `geom_second_target` | E | nearest 4H | **second** 1D level | none |
| `geom_context_target` | E | nearest 4H | **nearest 1W** level | none |
| `geom_combined_structural` | F | nearest 1D | first 1D level paying 1.5R | ≥ 1.0 ATR |
| `geom_combined_execution` | F | first 4H level ≥ 1.0 ATR | first 1D level paying 1.5R | — |

**A level is never invented.** Every stop and target above is a `PriceLevel` the
structural engines already produced. "Place the target at 2R" has **no spelling**
in this package: `TargetRule` enumerates sources of real levels, and an
architecture guard parses the two policy modules and asserts neither ever
constructs a `PriceLevel`. Family B *refuses* a trade rather than moving its
target — the distinction the brief draws, made structural.

---

## 8. Results — development and holdout

Frictionless. `n` is measurable trades. Digest
`722539817f87c4b4e3248784aaa7a436005f7866d09b3dfbd65ad6ad87d5b6f5`.

| policy | sample | trd | skip | n | win% | **expR** | medR | PF | totR | med R:R |
|---|---|---|---|---|---|---|---|---|---|---|
| `geom_production` | dev | 85 | 3 | 77 | 45.5 | **−0.2761** | −1.000 | 0.48 | −21.26 | 0.86 |
| | hold | 155 | 3 | 139 | 48.2 | **+0.0551** | −1.000 | 1.11 | +7.66 | 1.06 |
| `geom_min_rr_1` | dev | 40 | 48 | 36 | 13.9 | **−0.4695** | −1.000 | 0.45 | −16.90 | 4.52 |
| | hold | 83 | 75 | 76 | 27.6 | +0.0926 | −1.000 | 1.13 | +7.04 | 3.50 |
| `geom_min_rr_1_5` | dev | 34 | 54 | 31 | **6.5** | **−0.6045** | −1.000 | 0.35 | −18.74 | 6.00 |
| | hold | 64 | 94 | 60 | 21.7 | +0.0827 | −1.000 | 1.11 | +4.96 | 4.87 |
| `geom_min_rr_2` | dev | 32 | 56 | 29 | 6.9 | −0.5772 | −1.000 | 0.38 | −16.74 | 6.05 |
| | hold | 56 | 102 | 52 | 21.2 | +0.1428 | −1.000 | 1.18 | +7.43 | 5.74 |
| `geom_min_stop_0_5atr` | dev | 52 | 36 | 51 | 58.8 | −0.2471 | +0.024 | 0.38 | −12.60 | 0.33 |
| | hold | 90 | 68 | 89 | 60.7 | +0.0386 | +0.121 | 1.10 | +3.44 | 0.62 |
| `geom_min_stop_1atr` | dev | 44 | 44 | 44 | 56.8 | −0.3188 | +0.016 | 0.23 | −14.03 | 0.31 |
| | hold | 52 | 106 | 52 | 65.4 | −0.0141 | +0.115 | 0.96 | −0.73 | 0.44 |
| `geom_setup_stop` | dev | 85 | 3 | 81 | **61.7** | −0.1716 | +0.027 | 0.54 | −13.90 | 0.33 |
| | hold | 155 | 3 | 148 | **68.2** | −0.0088 | +0.110 | 0.97 | −1.30 | 0.32 |
| `geom_second_target` | dev | 80 | 8 | 78 | 32.1 | −0.1326 | −1.000 | 0.80 | −10.34 | 2.29 |
| | hold | 145 | 13 | 139 | 30.9 | **+0.5564** | −1.000 | 1.81 | +77.33 | 2.78 |
| `geom_context_target` | dev | 85 | 3 | 83 | 34.9 | **−0.0771** | −1.000 | 0.88 | −6.40 | 2.96 |
| | hold | 157 | 1 | 151 | 34.4 | **+0.5216** | −1.000 | 1.80 | +78.77 | 3.70 |
| `geom_combined_structural` | dev | 40 | 48 | 40 | 22.5 | −0.3127 | −1.000 | 0.58 | −12.51 | 1.92 |
| | hold | 85 | 73 | 85 | 30.6 | −0.0988 | −1.000 | 0.86 | −8.40 | 1.82 |
| `geom_combined_execution` | dev | 78 | 10 | 78 | 28.2 | **−0.0322** | −1.000 | 0.95 | −2.52 | 2.10 |
| | hold | 144 | 14 | 144 | 30.6 | **−0.0259** | −1.000 | 0.96 | −3.73 | 2.02 |

*(`geom_min_rr_1_25` and `geom_min_stop_1_5atr` omitted for width; both are in
the artifact and both are rejected.)*

### The four things this table says

1. **Every geometry loses money on development.** No exceptions, no near-misses
   above zero. That alone rejects all thirteen.

2. **Every minimum-R:R threshold makes development worse than the baseline**,
   and worse as the floor rises over the pre-declared range 1.0 → 1.5:
   −0.276 (no floor) → −0.470 → −0.482 → −0.605. The trend is **not monotonic
   across the whole family** — 2.0R reads −0.577, marginally above 1.5R's
   −0.605 — and the release gate corrected an earlier "monotonically" that
   implied it was. What holds without qualification is the direction: all four
   thresholds are worse than no threshold at all, and the win rate falls from
   45.5 % to 6.5 %. §9 explains why, and it is the milestone's most useful
   finding.

3. **The dev/holdout gap runs the *wrong way* for overfitting.** The usual
   failure is development-positive, holdout-negative. Here the **baseline
   itself** is positive on the holdout (+0.0551R) and negative on development
   (−0.2761R). A gap that large in the baseline is a property of the **symbol
   split**, not of any geometry — the holdout is nine high-beta, low-liquidity
   altcoins and the development set is six majors. **The large positive holdout
   figures for the target-selection family must therefore not be read as
   out-of-sample validation of those rules.** They are consistent with distant
   targets paying on high-beta instruments, which is a different claim and one
   this study did not set out to test.

4. **`geom_combined_execution` is the only variant whose two samples agree**
   (−0.032 / −0.026, PF 0.95 / 0.96). Consistency is not edge — both are
   negative — but it is the only rule here whose behaviour did not depend on
   which symbols it saw, and its mechanism is exactly the one §9 identifies.

### Costs

Pessimistic 10 bp per side (digest `cd9b3d9d6a63dc2c…`):

| policy | dev frictionless → costed | holdout frictionless → costed |
|---|---|---|
| `geom_production` | −0.2761 → **−0.9988** | +0.0551 → **−0.2988** |
| `geom_second_target` | −0.1326 → −1.0640 | +0.5564 → +0.1572 |
| `geom_context_target` | −0.0771 → −0.9301 | +0.5216 → +0.1368 |
| `geom_combined_execution` | −0.0322 → **−0.1230** | −0.0259 → **−0.1050** |

**Costs are not a rounding error here; they are decisive.** 20 bp of round-turn
friction costs the production geometry **0.723R per trade on average**, taking
its development expectancy from −0.276R to **−0.999R** — an almost exactly
break-even-looking figure that is in fact a full R of loss per trade. (The
release gate corrected an earlier phrasing that read as though the *drag* were
1R; the drag is 0.723R and the resulting expectancy is −0.999R.)

The drag is so large because it is charged against the **risk denominator**:
cost in R is `fee_rate × (entry + exit) / risk`. The median stop is 152 bp, where
20 bp costs a modest **0.132R** — but the minimum stop is **1.43 bp**, where the
same 20 bp costs **14.0R**. The per-trade drag ranges from 0.021R to **15.49R**.
A handful of noise-tight stops therefore dominate the average, which is a second,
independent argument for the same fix: every geometry that widens the stop is
dramatically less cost-sensitive.

> **Reading 1.43 bp beside BW's 1.29 bp.** Both describe the *same trade* —
> BNBUSDT 2024-12-24, stop 696.80 — measured in two different frames, and the
> release gate confirmed both arithmetically. BX's `stop_bps` is a **planning**
> statistic against the decision-time reference price (696.90 → 0.10 → 1.43 bp);
> report 0033's figure is against the **actual fill** (696.89 → 0.09 → 1.29 bp).
> Each layer uses the frame it can actually see: a plan cannot know its fill, and
> a realized R must not be measured against a price nobody traded. Neither number
> supersedes the other.

---

## 9. Why "minimum 2R" is backwards — the milestone's finding

The brief warned against assuming a minimum R:R was the answer. It is not, and
the reason is measurable.

**Planned R:R is a proxy for stop tightness, not for target distance.**

| | median stop (bp) | median stop / ATR | median target (bp) | median target / ATR |
|---|---|---|---|---|
| Setups planning **R:R ≥ 3.0** (n=73) | 43.6 | **0.220** | 310.4 | 1.629 |
| Setups planning **R:R < 1.0** (n=117) | 213.1 | **1.314** | 55.9 | 0.312 |

Spearman rank correlation between planned R:R and stop/ATR:
**−0.628 (development, n=85)** and **−0.650 (holdout, n=155)** — measured
independently on each sample, and agreeing.

So a "≥ 2R" filter does not select trades with generous targets. It selects
trades whose stop sits at **a fifth of an average bar's range**, which an
ordinary candle removes. That is confirmed by the outcome: the R:R-bucket
breakdown on development shows `rr < 0.5` at −0.0877R (n=32) and `rr ≥ 3.0` at
**−0.5096R (n=25)**. The highest planned reward-to-risk is the worst-performing
bucket.

**The corollary matters for the next milestone:** an R:R requirement is only
meaningful *once the stop is sound*. Applied to a broken denominator it is an
anti-filter.

### Parameter sensitivity

Both pre-declared grids were swept. Each is a **plateau** — every measurable
point agrees in sign — which here means *consistently negative*, not
consistently good.

| min R:R | 1.00 | 1.25 | 1.50 | 1.75 | 2.00 | 2.50 | 3.00 |
|---|---|---|---|---|---|---|---|
| dev expR | −0.470 | −0.482 | −0.605 | −0.605 | −0.577 | −0.529 | −0.510 |
| hold expR | +0.093 | +0.059 | +0.083 | +0.061 | +0.143 | +0.099 | +0.026 |

| min stop/ATR | 0.25 | 0.50 | 0.75 | 1.00 | 1.25 | 1.50 | 2.00 |
|---|---|---|---|---|---|---|---|
| dev expR | −0.165 | −0.247 | −0.293 | −0.319 | −0.388 | −0.324 | — (n=14) |
| hold expR | +0.019 | +0.039 | +0.010 | −0.014 | +0.007 | −0.027 | −0.219 |

No threshold rescues either family. Neither is fragile; both are reliably bad.

---

## 10. The post-hoc exploration, labelled as post-hoc

§10 of the brief requires every variant to be recorded, including those added
after results were seen. **Fifteen combinations** of the
`geom_combined_execution` mechanism were swept after the pre-declared results
were on screen. They are **not candidates** and cannot be described as validated.

**Isolating what does the work** (frictionless):

| Rule | dev | holdout |
|---|---|---|
| Relocate stop to nearest 4H level ≥ 0.25 ATR, production target | −0.2152 | −0.0025 |
| … ≥ 0.50 ATR | −0.1360 | −0.0224 |
| … ≥ 1.00 ATR | −0.1430 (win 62.4 %) | −0.0630 |
| **Relocation ≥ 0.25 ATR + real 1D target paying ≥ 2R** | **+0.1102** | **+0.2574** |
| **Relocation ≥ 0.50 ATR + real 1D target paying ≥ 2R** | **+0.2122** | **+0.1744** |
| Relocation ≥ 0.75 ATR + ≥ 2R | +0.0190 | −0.0022 |
| Relocation ≥ 1.00 ATR + ≥ 2R | −0.0921 | −0.0803 |

**Stop relocation alone does not work.** It lifts the win rate to 55–68 % and
leaves expectancy negative on both samples at every threshold, because widening
the risk without moving the target makes the ratio worse. It is only in
*combination* with a real, further structural target that the sign changes — the
two halves of the fix are individually useless and jointly effective, which is
why families C, D and E each fail alone.

**Under 10 bp/side, the region collapses to one point:**

| | dev | holdout |
|---|---|---|
| ≥ 0.25 ATR + ≥ 2R | −0.0894 | +0.0809 |
| **≥ 0.50 ATR + ≥ 2R** | **+0.0792** | **+0.0503** |
| ≥ 0.75 ATR + ≥ 2R | −0.0942 | −0.0977 |

One grid point survives; both immediate neighbours fail. **That is a spike, and
§9 rejects a spike.** It is recorded as the recommended pre-declared hypothesis
for the next milestone (§16), not as a result.

### Multiple-testing account, in full

| | count |
|---|---|
| Pre-declared geometries | **13** |
| Sensitivity grid points (pre-declared as *curves*, not candidates) | 14 |
| Plateau-neighbour evaluations (automatic, per policy) | 26 |
| **Post-hoc combinations, added after results were seen** | **20** |
| Cost scenarios per variant | 2 |
| **Variants that could be described as independently validated** | **0** |

---

## 11. Robustness and decomposition

| Split (development, `geom_production`) | Result |
|---|---|
| Direction | long −0.3020 (n=37) · short −0.2522 (n=40) — **agree in sign** |
| Largest symbol share of gross \|R\| | **27.5 %** — below the 40 % bound; no single symbol carries it |
| Context regime | trending −0.2761 (n=77) — the gate admits nothing else |
| Setup structural trend | neutral −0.2648 (n=38) · sustained_higher −0.3087 (n=21) |
| Per symbol | **every cohort below the 20-trade floor**; totals only: ADA +1.90 · XRP +0.83 · BTC −3.54 · ETH −4.53 · LTC −5.71 · BNB −10.19 |

**Per-symbol expectancy cannot be stated at this sample size** and the study
refuses to state it — six symbols over 88 trades leaves 6–19 trades each. This is
a real limitation, reported rather than papered over with a precise-looking
number.

---

## 12. Entry, stop, target or exit? — the attribution

The brief asked which of the four is responsible. The evidence says **stop
placement first, exit management second**, and it does not reduce to one score.

| Question | Measurement (development) | Reading |
|---|---|---|
| Are winners small because targets are close? | **YES** — 85.7 % of target exits pay < 1R; 52.9 % plan reward < risk | geometry, not execution |
| Are winners small because trades exit early? | **NO** — all 35 winners exited *at target* | the target is the binding constraint |
| Are stops too tight vs ordinary noise? | 48.2 % sit inside 1 ATR — below the 50 % bar, so reported **NO** by the stated rule, but see below | the rate understates it |
| Are targets valid but economically too close? | **YES** — 52.9 % | validity is not the issue |
| Does MFE materially exceed realized R? | **YES** — 68.8 % give back a full R | exit management, which geometry cannot fix |
| **Does price stop out and then reach target anyway?** | **YES — 73.2 %** | **the stop, not the thesis** |

**Entry quality.** Median `entry_position_in_range` is **0.537** — the entry sits
almost exactly halfway between its own stop and target, which is what a
coin-flip geometry looks like. p25 is 0.205 and p75 is 0.840, so the spread is
enormous: some entries have 80 % of the structural range as reward, others 20 %.
Median bars held is **1.0** and p75 is 3.0 — the typical trade is decided by the
next candle.

The honest attribution: **the entry is not systematically late** (0.537 is
neutral); **the stop is systematically too close** (73.2 % of stop-outs were
right); **the target is systematically too near** (85.7 % of target exits pay
under 1R); and **exit management gives back a further full R on 69 % of trades**.
Geometry addresses the middle two. The fourth is out of BX's scope and is named
as such.

---

## 13. Optional exit-management research — NOT MEASURED

§4 of the brief is explicitly optional and conditional on the existing fill
semantics being able to model a rule honestly. Partial exits at +1R, break-even
stop movement and trailing stops **were not measured**, and the reason is
recorded rather than glossed:

`simulate_trade` resolves one entry against one stop and one target, and halts a
bar that reaches both as **ambiguous** rather than guessing the intrabar path. A
partial exit at +1R adds a *third* level to the same bar, which multiplies the
ambiguous cases rather than resolving them; modelling it would require an
intrabar path assumption the data does not support. Per §4's own instruction it
is classified **NOT MEASURABLE with current fill semantics**, not estimated.

What *is* measured, and is the input a future exit study needs: **68.8 % of
trades give back at least a full R of open profit**, mean MFE +5.26R against mean
realized −0.276R.

---

## 14. No-lookahead

The proof is BW's method — **change the future and require the past not to
notice** — extended to everything BX added, plus a structural proof BW could not
give.

### The structural proof

`GeometryCandidate` holds prices, level lists and one ATR reading, all as of the
decision instant. It holds **no bar, no future timestamp and no outcome**. A
geometry policy is handed nothing else, so it *cannot* read forward — not by
discipline but by what exists. `test_planning_does_not_depend_on_the_bars_at_all`
demonstrates it directly: the bar array is thrown away entirely and every plan is
byte-identical.

### The mutation proof

| Mutation | Requirement | Result |
|---|---|---|
| Every 4H candle **after** the measurement window ×1000 | no candidate may change | **identical** |
| The same, checked through all 13 policies' selections | no plan may change | **identical** |
| Every candle after a **mid-window** cutoff ×1000 | earlier candidates unchanged | **identical** |
| The same, through every policy | earlier plans unchanged | **identical** |
| The same, checked on the **ATR reading** alone | a rolling average is the tempting leak | **identical** |
| Every candle in the **warm-up prefix** ×1.5 | candidates **must** change | **changed** ✅ |
| The same, through every policy | plans **must** change | **changed** ✅ |

The last two are the control that stops the others passing vacuously.

**Absolute checks, not just comparisons.** A shifted index cancels out of any
test comparing two captures, so two absolute assertions were added:
`bars[signal_index].open_time == signal_at`, and the entry fills at
`bars[signal_index + 1]`'s open, strictly after the signal. A mutation adding
`+ 1` to the captured index is killed by them.

**MFE/MAE isolation is architectural.** `geometry_outcome` owns every
after-the-fact measurement; `geometry.py` and `geometry_variants.py` import it
not at all, and a guard asserts both directions plus the absence of the tokens
`mfe`, `mae`, `net_r`, `PriceBar`, `simulate_trade` and `fill_at_level` from the
two policy modules.

**Holdout separation.** `GeometryCapture.for_symbols` selects; a test asserts the
returned candidates are the **same objects** (`is`), so development and holdout
cannot see different facts. A mutation removing the filter is killed.

---

## 15. Verification

| Gate | Result |
|---|---|
| Focused BX suite | **219 tests** (geometry 62 · study 72 · artifact 26 · render 19 · no-lookahead 26 · CLI name-resolution 14) |
| Full repository under `-W error` | **11,285 passing**, 0 failures (from 11,237 at BW) |
| **Mutation probes** | **45 / 45 killed**, byte-exact restoration verified by SHA-256, bytecode cleared each probe |
| **Production differential** | `evaluate_setup` vs committed HEAD over **2,352,000 combinations** — identical (§23) |
| `ordered_levels` differential vs committed `_nearest` | **16,000 cases, 0 mismatches** (by identity) |
| **BW digest reproduced** | `b2ffcdce…` **exactly** |
| Architecture guards (`swing_lab`) | 167, all passing (13 new) |
| Dashboard suite | 886 passing, including every AST guard |
| New runtime dependencies | 0 |
| ADRs required | 0 |
| Guards weakened | **0** |

### Mutation probes, by invariant

R arithmetic · stop and target distance · bps conversion · volatility
normalisation · four threshold-inclusion boundaries · target/stop side
validation · level-selection rules · `ordered_levels` ordering and strictness ·
zero-ATR handling · verdict conjunction · advisory-criterion isolation ·
concentration bound · pre-declaration · sample floor · holdout separation ·
sample disjointness · plateau `all`-vs-`any` · plateau floor handling ·
neighbour generation · MFE/MAE isolation · giveback sign · post-stop scoping ·
plan/trade correspondence · digest sensitivity · future-data isolation ·
capture ordering.

**The first run killed 27 of 37.** Every one of the ten survivors was a real
gap and each was closed by a test rather than by deleting the probe:

| Survivor | Why it survived | Closed by |
|---|---|---|
| `ordered_levels` sorted backwards / admitting the close | fixtures hand-build already-ordered lists, so the ordering was never called | 7 direct tests of `ordered_levels` |
| Volatility boundary exclusive | no fixture sat *exactly* on the threshold | a boundary test at exactly `k × ATR` |
| Zero ATR accepted | `_atr_of` unreached by offline fixtures | a direct test with a stub fact sheet |
| Post-hoc policy may be a candidate | every tested policy was pre-declared | a study run with an invented policy |
| No-threshold policy treated as a plateau | no test asserted the resulting verdict | a criterion-level assertion |
| Plateau `all`→`any` | neighbours never disagreed in sign on the fixture | **the rule was extracted** to `plateau_from` and tested directly |
| `reached_r` reads MAE | the assertion was satisfied vacuously by an empty tuple | two tests requiring non-empty *and* empty |
| Capture reads the next bar | a shift cancels between two compared captures | an **absolute** index assertion |
| Capture order iteration-dependent | one symbol per pass is already sorted | a reversed-universe invariance test |

Two further probes were added afterwards and also killed, and the release gate
added three cost-conversion probes plus two concentration probes. **Final:
45/45** — see §23 for why the three cost probes initially appeared to survive.

### Coverage

Statement + branch on the nine new modules:

| Module | Cover | Missed |
|---|---|---|
| `geometry_diagnosis.py` | **99 %** | 151, 266 |
| `geometry_artifact.py` | **99 %** | 218 |
| `geometry_outcome.py` | **99 %** | 165→173 |
| `geometry_verdict.py` | 98 % | 113 |
| `geometry.py` | 96 % | 190, 194, 311, 349, 353, 388, 391, 422, 433, 485 |
| `geometry_variants.py` | 96 % | 363, 377 |
| `geometry_replay.py` | 95 % | 287–291 |
| `geometry_study.py` | 92 % | 210, 674–717 |
| `geometry_render.py` | 91 % | 58, 65, 69–71, 270–276 |

**Not 100 %, and the misses are named.** `geometry_study.py` 674–717 is
`run_geometry_experiment`'s fetch-and-replay path, which needs a live provider;
its argument validation — everything that runs before the network — is covered.
The rest are defensive guards on paths offline fixtures cannot reach (a dataset
missing a series, a role absent from a fact sheet) and two unused convenience
properties. No coverage exclusion was added anywhere.

The release gate re-measured these figures after wiring the two §2 concentration
findings that the implementation session had written but left unreferenced, which
took `geometry_diagnosis.py` from 96 % to 99 %.

---

## 16. Classification

Every verdict is derived by `assess_geometry` from the measured result alone and
is recomputable from the artifact. **Nine criteria, all deciding except one
advisory.**

| Geometry | Verdict | Blocked by |
|---|---|---|
| `geom_production` | **REJECTED** | development_expectancy, drawdown_recovered, parameter_plateau |
| `geom_min_rr_1` / `_1_25` / `_1_5` / `_2` | **REJECTED** | development_expectancy, drawdown_recovered, parameter_plateau |
| `geom_min_stop_0_5atr` | **REJECTED** | development_expectancy, drawdown_recovered, parameter_plateau |
| `geom_min_stop_1atr` / `_1_5atr` | **REJECTED** | + holdout_expectancy |
| `geom_setup_stop` | **REJECTED** | + holdout_expectancy |
| `geom_second_target` | **REJECTED** | development_expectancy, **symbol_concentration**, drawdown_recovered, parameter_plateau |
| `geom_context_target` | **REJECTED** | development_expectancy, drawdown_recovered, parameter_plateau |
| `geom_combined_structural` / `_execution` | **REJECTED** | + holdout_expectancy |

**No geometry reached CANDIDATE_FOR_FORWARD_TEST, under either cost scenario.**

The bar was deliberately stricter than BW's single-criterion `classify`, which
promotes on a positive expectancy alone. BX requires: pre-declaration, ≥ 20
measurable trades on **both** samples, a positive expectancy on **both**, no
symbol above 40 % of gross |R|, a drawdown smaller than the total gained, and a
parameter plateau. `holdout_not_catastrophic` is computed and reported but
**never decides** — a softer reading needs a number for "catastrophic", and any
such number is one a researcher could argue down after seeing the result.

### One defect the real run exposed in the verdict layer

`holdout_not_catastrophic` originally compared the holdout against
`−development`. On real data that marked `geom_production` — which **made money**
on its holdout (+0.0551R) — as having *failed* a not-catastrophic test, because
it had not out-earned the magnitude of its own development loss. The comparison
is meaningless when development lost money: there is no gain to give back. It now
reports **not evaluable** in that case. The criterion is advisory, so no verdict
changed; a page that marks a passing holdout as a failure is still a page that
misleads, and it was fixed with a regression naming the real numbers.

---

## 17. Surfaces

### `fmits research geometry`

```
fmits research geometry \
  --development BTCUSDT ETHUSDT BNBUSDT LTCUSDT XRPUSDT ADAUSDT \
  --holdout NEOUSDT QTUMUSDT IOTAUSDT XLMUSDT ONTUSDT ETCUSDT ICXUSDT TRXUSDT VETUSDT \
  --start 2023-06-01T00:00:00+00:00 --end 2026-08-01T00:00:00+00:00 \
  --window 180 --save geometry.json
```

Both samples are **required** — a geometry study that could not say which symbols
were held back would have no holdout at all, and the command refuses rather than
defaulting. Geometries are defined in code and cannot be described on the command
line. There is no flag that changes a production strategy.

The report prints the **verdict first**, then both samples side by side, then
each policy's criteria by name, then the diagnosis with evidence separated from
interpretation, then the sensitivity curves, then the limitations in full.

### Dashboard `/geometry`

A new read-only page over a **saved** artifact, ordered for a decision rather
than for completeness: the verdict, both samples, why each rule was refused,
the production geometry's diagnosis, the sensitivity curves, the limitations.
Policies are listed in **pre-declaration order, never sorted by result** — a
table sorted by expectancy has chosen a winner.

**The dashboard still opens no file.** The artifact is decoded by the CLI
(`fmits dashboard --geometry-artifact PATH`) and handed in already parsed. The
contract layer computes nothing: two guards fired during development — one on a
percentage computed in `sections.py`, one on filtering methods on the read models
— and **both were fixed rather than widened**, by moving the work upstream and
carrying `Share`'s own canonical text.

### Trades are inspectable

Every trade in the artifact carries symbol, setup identity, decision timestamp,
entry, stop, target, exit, realized R, MFE and MAE, plus the stop's and target's
**structural provenance** (`4h:lower_low@231`). That is what a future chart
surface needs to open BTCUSDT → chart → setup → levels → trade geometry.

---

## 18. Hostile review

| Attack | Behaviour |
|---|---|
| Zero trades / one trade / empty sample | figures absent with a reason, counts visible; no crash |
| Sample below the floor | `LabMeasure` and `Share` both refuse a rate and state `n` |
| No losing trade | profit factor absent — *"no denominator"* |
| Reward = 0 / risk = 0 | **unrepresentable** — `ordered_levels`' strict inequality; `GeometryPlan` re-asserts and refuses |
| Target on the wrong side / stop on the wrong side | refused at construction; a side-swap mutation is killed |
| Stop equal to entry / target equal to entry | excluded by strict inequality |
| Very tight stop (1.4 bp) | **planned and measured, never hidden** — deleting it would delete the evidence |
| Very wide stop (price → 0) | planned without overflow |
| Gap through stop / through target | BW's `simulate_trade` rules, called |
| Same-bar stop and target | ambiguous, excluded from expectancy, counted beside it |
| Extreme volatility / near-zero volatility | ATR ≤ 0 refused as a broken measurement, not a calm market |
| **Missing volatility** | named refusal `NO_VOLATILITY_MEASURE`; never a silent pass |
| Missing structural target / stop | named refusals, counted by reason |
| Duplicate setup identity / repeated observations | `OpportunityTracker`; first confirmation only |
| Partial history / provider gap | availability probe refuses the window with the shortfall |
| Future timestamp | window boundaries reject it |
| Long symbols (400 chars) / long error text | carried intact |
| Empty holdout / overlapping samples | refused by name |
| **One-symbol apparent edge** | measured at 27.5 %; `symbol_concentration` rejected `geom_second_target` on it |
| Script injection on `/geometry` | escaped; asserted |
| Edited artifact | `verify_geometry_digest` fails |
| Overwriting an artifact | refused |

---

## 19. Limitations

`GEOMETRY_LIMITATIONS` (BX-1…BX-8) travels inside every artifact and prints on
every report, with BW-1…BW-7 beneath it unchanged. The four that most change what
the tables mean:

- **BX-2** — the development sample is **not** out-of-sample in any strict
  sense. BW measured those six symbols and BX's hypotheses were written after
  reading BW's diagnosis of them. Only holdout figures carry out-of-sample
  weight.
- **BX-3** — the universe is **survivorship-filtered**. EOSUSDT and NULSUSDT met
  the history requirement, stopped trading inside the window, and were dropped.
- **BX-4** — the holdout symbols are materially **less liquid** than the
  development symbols. This is the most likely explanation of the dev/holdout
  gap in §8, and it means the holdout tests whether a rule generalises across
  *structure*, not whether it would have been executable at size.
- **BX-7** — sensitivity grid points and every §10 combination are **post-hoc**
  and can never be described as pre-declared.

Additionally: per-symbol expectancy is unstatable at this sample size; trades
across geometries overlap heavily (they share admission instants) so the variants
are not independent experiments; and exit management is **NOT MEASURABLE** with
current fill semantics (§13).

---

## 20. Changed files

**New (`src/fmis/swing_lab/`):** `geometry.py`, `geometry_variants.py`,
`geometry_replay.py`, `geometry_outcome.py`, `geometry_diagnosis.py`,
`geometry_verdict.py`, `geometry_study.py`, `geometry_render.py`,
`geometry_artifact.py`

**Modified (`src/`):**
- `swing_setup/policy.py` — `_nearest` promoted to public `ordered_levels`
- `swing_setup/models.py` — `_STOP_SIDE`/`_TARGET_SIDE` promoted to `STOP_SIDE`/`TARGET_SIDE` (private aliases retained)
- `swing_setup/__init__.py` — exports
- `swing_lab/replay.py` — replay loop extracted to `replay_instants`/`decode_symbol_bars`/`ReplayInstant`/`UnanalysableInstant`; `replay_variant_group` now consumes it
- `swing_lab/artifact.py` — `_trade_payload`/`_trade_from_payload` promoted to public
- `pipeline/cli.py` — **`DEFAULT_BACKTEST_LIMIT` import fix**; `fmits research geometry`; `--geometry-artifact`
- `operator_dashboard/{models,sections,render,compose,server}.py` — the `/geometry` page

**New (`tests/`):** `swing_lab_geometry_fixture.py`,
`test_swing_lab_geometry{,_study,_artifact,_render,_nolookahead}.py`,
`test_pipeline_cli_name_resolution.py` (added at the release gate — §23 defect 10)

**Modified (`tests/`):** `swing_lab_helpers.py` (geometry fixtures),
`test_swing_lab_architecture.py` (13 new guards, module roster),
`test_level_crossing.py` (one guard widened, reason recorded in §21)

**Documentation:** this report; `reports/README.md`;
`docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated: BX delivers a research
capability and a read-only page, and its headline result is that no geometry
works. Recording that as a user-visible capability release would misrepresent it.

---

## 21. Guards widened, with reasons

**One**, and it was not weakened.

`test_level_crossing.py::test_nothing_below_imports_level_crossing` now admits
`fmis.swing_lab`, on the same footing as `fmis.swing_setup` and
`fmis.setup_observation`: the geometry layer reads `PriceLevel` and `LevelSide`
**by reference** to select a stop and a target, using production's own
`ordered_levels`. It derives no level and moves none — and that is not left as a
promise: a companion guard parses the two modules that decide a stop or a target
and asserts neither ever constructs a `PriceLevel`, which is the specific abuse
this package could commit.

Two dashboard guards **fired and were obeyed rather than widened** (§17).

---

## 22. Git state at completion

**Nothing was committed and nothing was pushed**, as instructed.

Two commits are **prepared but not created**:

```
Commit A   feat(research): add swing trade geometry laboratory
Commit B   docs(product): record swing geometry research milestone
```

`HEAD` remains `f5d59df`, `origin/main` remains `f5d59df`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.

---

## 23. Independent release-gate verification (2026-08-25)

BX was re-verified from the repository state before release, independently of the
implementation session. What was checked and what it found.

### Reproduced independently

| Check | Result |
|---|---|
| Starting `HEAD` / local `main` / `origin/main` / `git ls-remote` | all `f5d59df2851974292d08a7e4d7c311e7f77b6ca3`, 0 ahead / 0 behind, no stash, no in-progress operation |
| **Production behaviour unchanged** | `evaluate_setup` compared against the **committed HEAD copy** over **2,352,000 input combinations** — level sets with deliberate price ties, every structural-trend / regime / evidence / context combination, both `execution_close` states — **digest identical**, `f31da05b326b7a51…` |
| **BW baseline** | re-fetched and fully re-replayed: digest **`b2ffcdce149f7c42…` reproduced exactly**; 59/59/124/117 trades, 34.6 %, −0.535R, PF 0.16, −27.84R, gate-removed 74 at −0.270R — all identical |
| BW distributions recomputed from the fresh artifact | avg winner **+0.3010R**, avg loser **−0.9782R**, break-even **+1.8476R**, target exits < 1R **17/18 (94.4 %)**, reward < risk **25/52 (48 %)** — every 0033 figure reconciles |
| **BX capture** | **independently re-captured** (fresh fetch, 104,130 instants, 40 min): 246 candidates, identical per-symbol counts, and **both result digests reproduced exactly** — `722539817f87c4b4…` and `cd9b3d9d6a63dc2c…` |
| **Diagnosis recomputed without the diagnosis layer** | counted directly from plans, trades and bars: reward < risk **52.9 %**, target exits < +1R **85.7 %**, stops inside 1 ATR **48.2 %**, gave back ≥ 1R **68.8 %**, stop-out-then-target **73.2 %**, one-bar **63.5 %** — **all six exact** |
| **§5 mechanism** | Spearman(planned R:R, stop/ATR) = **−0.628** development, **−0.650** holdout, computed here rather than imported. Combined medians **0.220 ATR** (R:R ≥ 3) against **1.314 ATR** (R:R < 1) |
| All 13 variants | re-run; expectancy **hand-summed** and agreeing with `compute_lab_metrics` to 1e-12 on all 26 policy-sample pairs; **every development expectancy negative**; 13 distinct ids |
| Cost conversion | `fee_rate × (entry + exit) / risk` **verified from first principles on all 77 trades**, 0 mismatches. `gross_r`, `exit_reason`, `bars_held`, MFE and MAE asserted **identical** across scenarios — cost is applied once, to winners and losers alike |
| Determinism | result digest **stable across `PYTHONHASHSEED` 0 / 1 / 12345** |
| Six representative trades | reconciled against **freshly fetched provider candles**: entry, stop, target, ATR, stop bp, fill, exit, realized R, MFE, MAE — all matching |
| Hostile review | **24 probes, 0 failures** (§18 list, re-run at the gate) |
| Mutation probes | **45 / 45 killed**, byte-exact restoration verified by SHA-256, bytecode cleared each probe |
| Post-hoc discipline | a post-hoc policy is **unreachable by id**, absent from the pre-declared set, and **cannot reach CANDIDATE even with every other criterion passing** — verified by construction |
| Architecture | every reuse claim checked by **object identity**, not merely by import: `simulate_trade`, `evaluate_setup`, `ordered_levels`, `OpportunityTracker`, `compute_lab_metrics`, `measure_robustness`, `PaperCostPolicy`, `fill_at_level` all resolve to their existing owners |
| Absences | 0 hits for EVEDEX, AI clients, credentials, execution verbs, `TradingStore`; `records/`, `persistence/`, `ledger/`, `archive/` **untouched**; provider imports confined to the orchestration entry point, absent from all six deterministic-core modules |

### Defects the release gate found and fixed

| # | Defect | Fix |
|---|---|---|
| 10 | **The claimed CLI regression did not exist.** §3 and §11 stated "a CLI regression now covers the path", but no test referenced `_run_research`, the research command, or `DEFAULT_BACKTEST_LIMIT`. The fix was real; the *verification* of it was not | Added `tests/test_pipeline_cli_name_resolution.py` (14 tests). It is deliberately **static and total**: it walks every function in `cli.py` and asserts every module-scope name it loads actually resolves — catching the whole class of defect in any CLI runner, not just the line already fixed. Applied to the committed HEAD copy it reports exactly one unresolved name, `_run_research: DEFAULT_BACKTEST_LIMIT`, **proving it would have caught the shipped defect**. It also asserts no CLI function catches bare `Exception`/`BaseException`/`NameError`, so the next such defect cannot be swallowed |
| 11 | **"monotonically" overstated the R:R result.** The family is uniformly worse than the baseline, but 2.0R (−0.577) is not worse than 1.5R (−0.605) | §8 corrected to state what holds without qualification |
| 12 | **"loses a full R per trade" overstated the cost drag.** The drag is **0.723R**; the *resulting expectancy* is −0.999R | §8, `CURRENT_STATE.md` and the backlog corrected, with the drag's derivation and range (0.021R–15.49R) added |
| 13 | **Two §2 questions had helpers written but never wired.** `_share_by` and `_concentration_finding` — "does reward < risk concentrate in particular setup types?" and "does tight-stop behaviour concentrate in particular volatility regimes?" — were dead code | Wired into the findings, plus a symbol-concentration question. Coverage of `geometry_diagnosis.py` rose 96 % → **99 %**, and two mutation probes now guard the concentration rule |
| 14 | **1.43 bp vs report 0033's 1.29 bp** read as a contradiction | Both verified arithmetically as the **same trade in two frames** — planning (reference price) versus fill. A note in §8 records it so neither figure looks like an error |

### Investigated and found NOT to be defects

- **ATR drift of 1.6–7.8 %** appeared in a first reconciliation pass. Re-running with the candle window aligned to production's own 250-candle analysis window gives **0.000 % drift** across all three probes. The drift was in the ad-hoc verification script, not in BX: **no ATR-unit error, no seed error.**
- **Three mutation survivors in cost conversion** (`cost charged only to winners`, `cost applied twice`, `cost omitted from the exit notional`) were survivors of the *probe harness*, which was running BX's frictionless suite. Re-targeted at their real owner — Milestone BW's `test_swing_lab_trades.py` — **all three are killed**. The arithmetic was already constrained.
- **`RecordKind` appears once** in `geometry_diagnosis.py` — in a docstring stating that none was added. No record kind, repository or store path exists.

### What the gate did not change

No trading rule, no threshold, no variant definition, no classification, and no
result. `CONFIRMATION_LOOKBACK_BARS` is still 10, `MINIMUM_AGREEING_FAMILIES`
still 2, `DEFAULT_TIMEFRAMES` still 1W/1D/4H, and the 2,352,000-combination
differential above was re-run after every change. **All thirteen pre-declared
geometries remain REJECTED and there is still no candidate.**

---

## 24. Recommended next milestone — do not begin it

**BY — Volatility-Anchored Stop Placement, pre-declared and forward-shadowed.**

The evidence points at one change and BX must not make it: **the stop is the
defect**. 73 % of stopped-out trades had their target reached afterwards; half
the stops sit inside one ATR; the typical trade is decided by the next candle;
and planned R:R is an artifact of the broken denominator rather than a measure of
opportunity.

BY should:

1. **Pre-declare, before any run**, the rule §10 found post-hoc: the stop is the
   nearest *real* execution-timeframe level at least *k* × ATR(14) away, and the
   target is the nearest *real* setup-timeframe level paying at least *m* × the
   risk — with *k* and *m* written down first and their neighbours required to
   agree.
2. **Enlarge the sample before, not after.** 88 development trades cannot
   support a per-symbol decomposition. A shorter warm-up mapping (1D context)
   would admit far more symbols and years; BW's `swing_1d4h1h_roles` remains
   unmeasured and would answer that question at the same time.
3. **Test under costs from the first run.** §8 shows costs are decisive here,
   not a refinement.
4. **Then, and only then**, re-open exit management — 69 % of trades give back a
   full R, and no stop rule addresses that.

`swing_1d4h1h_roles` (BW) remains **INCONCLUSIVE** and unmeasured; BX did not run
it and did not reclassify it.
