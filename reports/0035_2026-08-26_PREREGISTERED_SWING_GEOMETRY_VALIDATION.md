# Pre-Registered Swing Geometry Validation & Execution Mechanics — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0035 |
| **Title** | Pre-Registered Swing Geometry Validation & Execution Mechanics (Milestone BY) |
| **Date** | 2026-08-26 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `3598b4c`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final |

**Milestone:** BY — Pre-Registered Swing Geometry Validation & Execution Mechanics.

**Scope guard.** No production trading policy changed. The stop rule is still the
nearest execution-timeframe level, the target rule is still the nearest
setup-timeframe level, `CONFIRMATION_LOOKBACK_BARS` is still `10`,
`MINIMUM_AGREEING_FAMILIES` is still `2`, and `DEFAULT_TIMEFRAMES` is still
1W/1D/4H. **No geometry was promoted.** Nothing here is a forward test.

---

## 1. The answer, first

> **Did the pre-registered geometry hypothesis survive honest unseen-data testing
> well enough to deserve shadow/forward testing?**
>
> **No. NO_CANDIDATE.** The hypothesis was **refuted**, in the precise sense the
> pre-registration defined before the study ran: positive on development
> (+0.1995R cost-inclusive) and **negative on both unseen samples** — −0.1761R on
> the later period and −0.2361R on twenty-one symbols this repository had never
> measured. **All eleven sealed hypotheses are REJECTED** — none is
> INCONCLUSIVE, because every sample cleared the twenty-trade floor, so every
> figure that decided anything was one the study was entitled to state.

Milestone BX ended with one post-hoc finding it correctly refused to promote:
relocate the stop to the nearest real 4H level at least 0.5 ATR away, and require
a real 1D level paying at least 2R. BY existed to **pre-declare that exact rule
and try to falsify it**. It falsified it, and the mechanism is legible:

| `by_stop_0_5atr_target_2r`, cost-inclusive | expectancy | n | PF |
|---|---|---|---|
| Development · 15 symbols · 2023-06 → 2025-06 | **+0.1995R** | 136 | 1.27 |
| Validation · same symbols · 2025-06 → 2026-08 | **−0.1761R** | 80 | 0.79 |
| **Holdout · 21 unseen symbols · 2024-06 → 2026-08** | **−0.2361R** | 200 | 0.72 |

And the two walk-forward curves say *why* — one per universe, because pooling
them would change what is being measured half-way along (§7, defect BY-D6):

| **15 primary symbols** | 23H2 | 24H1 | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|---|---|
| expectancy | **+0.2336** | −0.0387 | **+0.3522** | **+0.2592** | **−0.4504** | **−0.1500** |

| **21 holdout symbols** | — | — | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|---|---|
| expectancy | | | −0.3585 | −0.3568 | −0.3015 | −0.0605 |

**The rule fails two independent generalisation tests, and it fails them
differently.** On the fifteen symbols it was developed on it worked for two
years — positive in three of its first four windows — and then **broke at
exactly the development/validation boundary**, 2025-06-01, losing in every
window after it. On twenty-one symbols it had never seen it **never worked at
all**, losing in every window from its first.

So it does not generalise across *time* on its own universe, and it does not
generalise across *universe* at any time. Either failure alone would refute it.

**What did survive.** Three findings that are not candidates but are worth
carrying forward:

1. **Structure beats distance.** The pre-declared non-structural twin — a stop at
   0.5 ATR and a target at 2R, both invented — earned **+0.0240R** on development
   against the structural rule's **+0.1995R**. Where the rule worked at all, the
   *structural levels* did the work, not the distances.
2. **BX's "NOT MEASURABLE" is now measurable.** Real 1H and 15m candles resolved
   **17 of 19** ambiguous 4H bars on development (89.5 %) and **18 of 21** on the
   holdout (85.7 %). The remainder stay ambiguous and are refused, never guessed.
3. **Exit management is worth roughly +0.30R per trade — and cannot rescue a
   broken geometry.** Moving the stop to break-even at +1R took production
   geometry from −0.599R to −0.296R on development and from −0.484R to −0.213R on
   the holdout. Both are still large losses.
4. **BW's `swing_1d4h1h_roles` is measured at last, and REJECTED.** Shifting every
   role down a step (1D context, 4H setup, 1H execution) is worse on **all eleven**
   sealed policies, admits **seven times** the setups on the same six symbols and
   the same window, and loses on them. An INCONCLUSIVE that has stood since BW is
   now resolved.

---

## 2. Starting Git state

```
branch            main
HEAD              3598b4cf2dc8082c961f8b0c5d157d7023709cf3
                  docs(product): record swing geometry research milestone
origin/main       3598b4c  (0 ahead / 0 behind)
stash             empty
unresolved ops    none
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/ — untouched
```

---

## 3. The pre-registration, and why it is the milestone

`src/fmis/swing_lab/preregistration.py` fixes **every** hypothesis id, threshold,
symbol list, window boundary, cost scenario, candidate criterion and
classification rule, and pins their SHA-256:

```
id      by-swing-geometry-validation-v1
digest  a81b6ab8314bd3cf2e8a6358f3a19cf8d6bb6c152cef9efd55fbffd9883d640a
```

**The seal and the content live in the same file**, so a change to either without
the other is a red test (`test_swing_lab_preregistration.py`, 41 tests). Eleven
parametrised mutations — a threshold moved, a failing neighbour dropped, the
deciding scenario switched to frictionless, a criterion deleted, a window edge
shifted — are each shown to change the digest. The seal was computed and pinned
**before the first result was read**, and it is byte-identical now.

Two devices make "post-hoc" operational rather than aspirational:

* `assess_candidate`'s **first** criterion is `pre_registered`, decided by set
  membership in the sealed manifest plus a digest match — not by a flag a caller
  passes. A post-hoc policy cannot be promoted whatever its numbers.
* The study's manifest carries the digest it ran under, and
  `verify_preregistration_seal` reports a mismatch on every surface.

### The eleven sealed hypotheses

| id | policy | role | rule |
|---|---|---|---|
| BY-H0 | `geom_production` | control | the live rule, unchanged |
| BY-H1.1 | `by_stop_0_35atr_target_2r` | primary | 4H stop ≥ 0.35 ATR · 1D target ≥ 2R |
| **BY-H1.2** | **`by_stop_0_5atr_target_2r`** | **primary** | **≥ 0.50 ATR · ≥ 2R — BX's point** |
| BY-H1.3 | `by_stop_0_65atr_target_2r` | primary | ≥ 0.65 ATR · ≥ 2R |
| BY-H1.4 | `by_stop_0_8atr_target_2r` | primary | ≥ 0.80 ATR · ≥ 2R |
| BY-H1.5 | `by_stop_0_5atr_target_1_5r` | primary | ≥ 0.50 ATR · ≥ 1.5R |
| BY-H1.6 | `by_stop_0_5atr_target_2_5r` | primary | ≥ 0.50 ATR · ≥ 2.5R |
| BY-H2 | `by_stop_only_0_5atr` | isolation | stop half alone, production target |
| BY-H3 | `by_target_only_2r` | isolation | target half alone, production stop |
| BY-H4 | `by_setup_stop_0_5atr_target_2r` | alternative | **1D** invalidation beyond the floor |
| BY-H5 | `nonstruct_stop_0_5atr_target_2r` | **non-structural control** | invented stop and target at the same numbers |

**The neighbourhood is a cross, not a grid.** The stop threshold is swept at
target = 2.0 and the target multiple at stop = 0.50; the two meet at the primary
point and nowhere else. Six policies, not twelve — a grid has twice as many
chances to contain a winner and additionally invites picking the best cell.

Every hypothesis carries a **prediction** and a **`refuted_by`** sentence. A rule
with no stated refutation cannot fail, and a milestone whose rules cannot fail is
a search.

---

## 4. Datasets, and the universe problem BX named

Four hundred and eighty-four currently tradable USDT spot pairs were probed for weekly depth.
For a measurement window opening 2023-06-01 under production's 1W role, **exactly
sixteen qualify** — and fifteen of them are Milestone BX's universe. That is a
finding rather than a coincidence: the weekly role's 250-candle analysis window
costs 4.8 years of history, and the universe that can pay it is this one.
(The sixteenth, TUSDUSDT, is a USD-pegged stablecoin and is dropped — a
trend-following strategy measured against a peg measures the peg's noise.)

A genuine symbol holdout therefore required a **later window**: at 2024-06-01, 38
pairs qualify, of which **21 have never been measured by this repository**.

| sample | symbols | window | candidates | contamination |
|---|---|---|---|---|
| **Development** | 15 (BX's universe) | 2023-06-01 → 2025-06-01 | 155 | **CONTAMINATED BY CONSTRUCTION** — BX measured all fifteen and BY's hypothesis is BX's own post-hoc finding |
| **Validation** | the same 15 | 2025-06-01 → 2026-08-01 | 91 | **SEMI-CONTAMINATED** — new period, old symbols; tests *one regime*, not *one universe* |
| **Holdout** | **21 never measured** | 2024-06-01 → 2026-08-01 | 234 | **THE HOLDOUT** — a separate replay, run after development and validation existed |

```
primary capture   15 symbols · 104,130 instants · 246 candidates · 41.7 min
holdout capture   21 symbols ·  99,666 instants · 234 candidates · 40.4 min
```

**The primary capture reproduced Milestone BX exactly** — 246 candidates from
104,130 measured instants, the same two figures BX reported — which is an
independent confirmation of the replay before any BY-specific number was read.

The contamination sentence is a **required field on the sample**, not page copy
beside a table, so every surface printing the sample prints the caveat with it.

---

## 5. Results — all three samples, cost-inclusive

Deciding scenario `swing-lab-conservative-10bps` (10 bp per side). Result digest
`fadf29715551ebb0a6a1875fc503bd83da656691a627a117007ef5cda9bddd6a`.

| policy | development | validation | holdout | verdict |
|---|---|---|---|---|
| `geom_production` | −0.5990 (132) | −0.4688 (84) | −0.4842 (203) | REJECTED |
| `by_stop_0_35atr_target_2r` | **+0.2462** (136) | −0.2684 (80) | −0.2397 (198) | REJECTED |
| **`by_stop_0_5atr_target_2r`** | **+0.1995** (136) | **−0.1761** (80) | **−0.2361** (200) | **REJECTED** |
| `by_stop_0_65atr_target_2r` | **+0.1378** (136) | −0.2401 (80) | −0.1765 (200) | REJECTED |
| `by_stop_0_8atr_target_2r` | −0.0665 (134) | −0.2106 (80) | −0.1733 (198) | REJECTED |
| `by_stop_0_5atr_target_1_5r` | **+0.1595** (140) | −0.2382 (82) | −0.1569 (206) | REJECTED |
| `by_stop_0_5atr_target_2_5r` | **+0.1676** (134) | −0.1395 (79) | −0.2263 (199) | REJECTED |
| `by_stop_only_0_5atr` | −0.1504 (142) | −0.2322 (85) | −0.1418 (217) | REJECTED |
| `by_target_only_2r` | −0.2984 (128) | −0.6248 (80) | −0.4802 (191) | REJECTED |
| `by_setup_stop_0_5atr_target_2r` | −0.2945 (113) | −0.1897 (63) | −0.0118 (166) | REJECTED |
| `nonstruct_stop_0_5atr_target_2r` | +0.0240 (152) | −0.3755 (90) | — | REJECTED (non-structural) |

### The five things this table says

1. **The control behaves as predicted.** `geom_production` is negative on all
   three samples at roughly −0.5R. BW and BX measured the same thing. The harness
   reproduces a known result before anything else is read.

2. **Every primary point is positive on development and negative on both unseen
   samples.** Not one, not a near-miss: six for six, on the sample that was
   contaminated by construction, and the sign flips on every sample that was not.

3. **The isolation controls confirm BX's mechanism and refute nothing new.** The
   stop half alone (−0.1504) and the target half alone (−0.2984) are both
   negative on development, exactly as pre-declared. The two halves are
   individually useless and jointly effective — **on development only**.

4. **The 1D-invalidation alternative (BY-H4) is the one open question BX never
   asked, and it comes back negative on development (−0.2945) while being nearly
   flat on the holdout (−0.0118).** The direction was not predicted and the
   result does not support it; it is recorded rather than pursued.

5. **The non-structural twin is much worse than the structural rule on
   development (+0.0240 against +0.1995).** The structural claim therefore
   survives *as a claim about mechanism* even though the rule fails as a
   strategy: where the geometry earned anything, real levels earned it.

---

## 6. Cost sensitivity

| policy · sample | frictionless | 10 bp/side ★ | 15 bp/side |
|---|---|---|---|
| `geom_production` · development | −0.0551 | **−0.5990** | −0.8710 |
| `geom_production` · holdout | −0.0725 | **−0.4842** | −0.6900 |
| `by_stop_0_5atr_target_2r` · development | +0.3187 | **+0.1995** | +0.1399 |
| `by_stop_0_5atr_target_2r` · validation | −0.0351 | **−0.1761** | −0.2466 |
| `by_stop_0_5atr_target_2r` · holdout | −0.1456 | **−0.2361** | −0.2813 |

★ the deciding scenario. **No candidate may be selected on any other**, and the
verdict layer reads only this column.

**Costs remain decisive, and they matter most where the stop is tightest.** They
cost the production geometry **0.544R per trade** on development and the primary
rule only **0.119R** — the same asymmetry BX identified, since cost in R is
`fee × (entry + exit) / risk` and the primary rule's whole point is a larger
denominator. Note the honest reading of the frictionless column: the primary
rule's validation figure is −0.0351R *before* any friction. The rule does not
fail because of costs; it fails on its own, and costs widen the gap.

Every trade is simulated **once** and re-priced, so the three columns describe
byte-identical trades: same fills, same exit reasons, same gross R, same
excursions. Any difference between them is the cost model and nothing else, and
a test asserts both halves of that — the path is identical **and** the net figure
moves.

**Limitation BY-6.** The 15 bp scenario is a *friction proxy*, not a spread
model: it raises the fee rate rather than moving the fill price, so it
understates slippage's effect on R for the tightest stops.

---

## 7. Robustness: the plateau, and a defect the real run exposed

### Parameter plateau (development, cost-inclusive)

| stop/ATR axis (target = 2R) | 0.35 | **0.50** | 0.65 | 0.80 |
|---|---|---|---|---|
| expectancy | +0.2462 | **+0.1995** | +0.1378 | **−0.0665** |

| target axis (stop = 0.50 ATR) | 1.5R | **2.0R** | 2.5R |
|---|---|---|---|
| expectancy | +0.1595 | **+0.1995** | +0.1676 |

**The two axes behave differently, and that is the milestone's cleanest
mechanical finding:**

* the **reward requirement is a ROBUST_PLATEAU** — every measurable neighbour
  positive, a flat region rather than a point;
* the **stop floor is a FRAGILE_SPIKE** — a monotone decline with the 0.80
  neighbour negative. Widening the stop past ~0.65 ATR destroys the result.

The primary point is classified `FRAGILE_SPIKE` on the stricter of its two axes.
`ROBUST_PLATEAU` requires **`all`** measurable neighbours positive, never `any` —
one positive point beside a negative one is exactly the shape BX's §10 spike had.

### Defect BY-D1 — the neighbourhood was keyed on the wrong thing

The first real run reported the primary point's plateau as `NO_EDGE` with the
centre reading **−0.2945R (n=113)** — which is not the primary policy's figure at
all, but `by_setup_stop_0_5atr_target_2r`'s. The 1D-invalidation *alternative*
carries the same `(0.50, 2.0)` thresholds while being a different rule, and the
neighbourhood was built by matching those numbers rather than by reading the
sealed **family**. Being later in declaration order, it silently displaced the
primary measurement and every primary policy's plateau was classified against the
wrong number.

Fixed by `_on_the_cross`, which reads `policy.family == FAMILY_PRIMARY`. A
collision now raises by name rather than overwriting, and four regression tests
cover it — including one asserting that every neighbourhood point carries the
measurement of the policy whose id it names.

**This is why the run happened before the report.** The classification rule was
correct; the code selecting what to classify was not, and only real data with a
threshold collision in it could show that.

### Defects BY-D2 … BY-D8 — found by an independent code review AFTER release

Report 0035 was published and its two commits pushed before an independent
`/code-review` pass over the same diff. It raised thirteen findings; eight were
verified against the real captures and fixed, and the two most severe changed
what this report says. They are recorded here rather than quietly corrected,
because a reader who read the first version was told something false.

| # | defect | how it was verified | effect |
|---|---|---|---|
| **BY-D6** | **The walk-forward and every decomposition pooled all three samples.** The traded universe doubled at 2024-06 (13 symbols before, 33 after) as the holdout entered, so each window after that boundary described a different market from the windows before it | counted symbols per window on the real study | **The published "BX's finding was one six-month window" was wrong.** Corrected: the rule is positive in three of its first four windows on its own universe and breaks at the validation boundary; the holdout loses in every window. Two decomposition rows also reversed |
| **BY-D7** | **`--validation-artifact` and `--geometry-artifact` were inert.** `compose.refresh()` accepted both and forwarded neither, so the CLI decoded the artifact and the page still said nothing was loaded | `'validation=validation' in inspect.getsource(refresh)` → `False` | The shipped dashboard flag did nothing. Now forwarded; `--geometry-artifact` had the same pre-existing defect and is fixed with it |
| **BY-D8** | **The no-ladder exit control did not reproduce `simulate_trade`,** contrary to `exit_full_target`'s **sealed** hypothesis text, because `_process` consulted `opened_beyond` with no ladder | reproduced on a bar that opens beyond the stop and reaches the target: control gave `STOP −1.5R`, `simulate_trade` gave `AMBIGUOUS` | The seal is the contract, so the **code** was fixed. **§10's figures are unaffected** — measured on the real captures, `simulate_trade` ambiguity is **19** on development, exactly the count already reported |
| BY-D9 | The §9 exit comparison was not like-for-like: a managed mechanic watches a third level, so bars that ran +1R and then stopped became ambiguous for it and a clean −1R for the control | reasoned from `_State.levels`, confirmed by the ambiguous counts (2 → 20) | A **comparable** column now re-measures every mechanic over the setups all of them could measure, and the report says to read that one |
| BY-D10 | The entire §7–§9 mechanics layer was unreachable from any shipped command | no caller outside `tests/` | `fmits research validation --with-mechanics` now runs it |
| BY-D11 | `_neighbourhood_for` returned the first matching axis, so the primary point's plateau was decided by the stop axis alone | read from the branch order | Both axes are now evaluated and both must hold. **The verdict is unchanged** — the stop axis was already FRAGILE_SPIKE |
| BY-D12 | `bars_within` claimed a bisect but ran two O(n) passes in front of it, on every call, against ~26k rows | read from the body | Ordering validated once at `BarLadder` construction; the search is now genuinely O(log n) |
| BY-D13 | Four smaller defects: `verify_result_digest` hard-coded the cost scenarios and the frictionless id; `mean_mfe_captured` averaged an unbounded ratio; a `NO_ENTRY_BAR` record carried an entry; a truncated *execution* series was reported as a lower-timeframe gap | read and reproduced | all fixed |

**The result digest is unchanged at `fadf2971…`.** Every one of these was a
defect in analysis, presentation or reachability; none touched a measurement,
and the verdict — **NO_CANDIDATE, all eleven hypotheses REJECTED** — is
unaffected. Five findings were investigated and **not** accepted as defects, and
one of those is worth naming: `PlansGeometry` as a `runtime_checkable` Protocol
was queried, and data-member protocols do support `isinstance` (only
`issubclass` is forbidden), which was verified rather than assumed.

### Decomposition (primary rule, cost-inclusive) — **two universes, kept apart**

**Primary universe** — the 15 symbols, development + validation, 216 trades,
pooled +0.0604R:

| cut | result |
|---|---|
| direction | long −0.0166 (88) · short **+0.1134** (128) — **disagree in sign** |
| symbol class | major +0.0791 (76) · non-major +0.0503 (140) — **agree, both positive** |
| largest single symbol share | **10.2 %** of gross \|R\| on development — well below the 40 % bound |
| per symbol | **every cohort below the 20-trade floor**; expectancy refused |
| context regime | trending +0.0604 (216) — the gate admits nothing else |
| setup structural trend | neutral +0.0525 · sustained_higher +0.0556 · sustained_lower +0.0807 — **agree, all positive** |

**Holdout universe** — the 21 symbols, 200 trades, pooled −0.2361R:

| cut | result |
|---|---|
| direction | long −0.3917 (40) · short −0.1972 (160) — **agree, both negative** |
| symbol class | non_major −0.2361 (200) — the holdout contains no major |
| context regime | trending −0.2361 (200) |

**What this actually says, now that the two universes are not mixed.** On its own
universe the rule is *pooled positive* and its cohorts largely agree — majors and
non-majors both positive, all three structural-trend cohorts positive. The one
disagreement is direction: **short +0.1134 against long −0.0166**, which on a
universe and period crypto spent broadly rising is the opposite of the
market-call artefact one would fear, and is not a result at 88 and 128 trades.

The pooled +0.0604R is not an edge. It is the arithmetic of +0.1995R over 136
development trades and −0.1761R over 80 validation trades, and the walk-forward
above shows the whole gain is earned before 2025-06 and given back after.

**An earlier version of this table pooled all three samples and reported the
opposite on two rows** — "long and short agree, both negative" and "majors
positive, non-majors negative". Both were artefacts of mixing a 15-symbol
universe with a 21-symbol one whose trades are entirely non-major and entirely
negative. See defect **BY-D6**.

---

## 8. Geometry mechanism — what actually happened

BX established that planned R:R is a proxy for stop *tightness*: the rank
correlation between planned R:R and stop/ATR is −0.65, and a "≥ 2R" filter
selects trades whose stop sits at a fifth of a bar's range. BY's primary rule
attacked both halves at once, and the measured decomposition is:

| claim | evidence |
|---|---|
| widening the stop alone helps the **win rate** and not the **expectancy** | `by_stop_only_0_5atr` wins 49.3 % against production's 41.7 % and still loses 0.15R |
| demanding 2R alone is an **anti-filter** | `by_target_only_2r` −0.2984 dev, −0.4802 holdout — the worst structural rule measured |
| together they were positive **only where BX looked** | +0.1995 dev · −0.1761 validation · −0.2361 holdout |
| the reward requirement is the **robust** half | target axis is a plateau; stop axis is a spike |
| **structure**, not distance, produced what edge there was | +0.1995 structural against +0.0240 for the identical distances invented |

The honest summary: **the rule is not wrong about geometry, it is wrong about
persistence.** It selects a genuinely different and better-shaped trade — the
ambiguity rate falls from 19 trades to 0, the win rate and the average winner
both move the right way — and that better shape did not pay outside one window.

---

## 9. Entry refinement (§7)

Five pre-declared rules, same geometry, same exit mechanic, so the family
measures entry timing and nothing else. Development sample, cost-inclusive.

**Under the primary geometry** (`by_stop_0_5atr_target_2r`):

| rule | filled | fill % | n | expectancy |
|---|---|---|---|---|
| `entry_immediate` (control) | 136 | 100 % | 136 | +0.1995 |
| `entry_next_bar_continuation` | 65 | 47.8 % | 64 | +0.1180 |
| `entry_pullback_limit` | 136 | 100 % | 136 | **+0.2091** |
| `entry_immediate_1h` (resolution control) | 136 | 100 % | 136 | +0.1995 |
| `entry_1h_confirmation` | 68 | 50.0 % | 68 | +0.1119 |

**Under production geometry:**

| rule | filled | fill % | n | expectancy |
|---|---|---|---|---|
| `entry_immediate` | 151 | 100 % | 149 | −0.6245 |
| `entry_next_bar_continuation` | 68 | 45.0 % | 44 | **−0.1587** |
| `entry_pullback_limit` | 151 | 100 % | 149 | −0.6327 |
| `entry_1h_confirmation` | 73 | 48.3 % | 56 | **−0.3615** |

**Three readings, and the third is the important one.**

1. **The resolution control holds exactly.** `entry_immediate_1h` reproduces
   `entry_immediate` to the digit, so any 1H result is attributable to the entry
   rule rather than to walking the outcome at a finer resolution.
2. **Confirmation improves production geometry a lot and the primary geometry
   not at all** — from −0.62 to −0.16, but from +0.20 to +0.12. Waiting helps a
   trade whose stop is inside the noise and hurts one whose stop is already
   outside it. The two halves of the milestone are addressing the same defect.
3. **Every confirmation rule declines about half its setups, and that is a
   selection claim, not an improvement.** `entry_next_bar_continuation` takes 45 %
   of production's setups and its −0.1587R is measured on *those*. The miss rate
   is printed beside the expectancy precisely so the two are not confused.

`entry_pullback_limit` is the one rule whose fill is an assumption rather than a
printed trade of ours — a resting limit filled on a touch — and it is reported
with that assumption named. Its ~+0.01R edge over an immediate fill is not a
finding.

---

## 10. Lower-timeframe ambiguity (§8) — BX's NOT MEASURABLE, resolved

| | development | holdout |
|---|---|---|
| ambiguous on 4H alone (`geom_production`) | **19** | **21** |
| still ambiguous with 1H, then 15m | **2** | **3** |
| **resolved** | **17 (89.5 %)** | **18 (85.7 %)** |

The method uses two facts four prices genuinely contain — a bar that reached only
one level reached that one, and a bar that **opened beyond** a level reached it at
its first price — and otherwise descends to 1H, then to 15m, and then **refuses**.
15m was fetched for exactly the 39 spans that needed it rather than for years.

**A second control validates the ladder itself, and it is exact.** Walking a 4H
path and *descending* to 1H where a bar is ambiguous produces the **identical**
result to walking the 1H series natively: all 151 trades match on exit price,
exit reason and R, and the two expectancies are equal to 28 decimal places
(−0.6245148905404734442113914020). Two different routes through the same candles
agree exactly, which is what a correct descent should look like and is not
something the design guaranteed on its own.

**The no-ladder control reproduces `simulate_trade` trade-for-trade** across six
deliberately awkward paths (gap through target, same-bar collision, time stop, an
entry that opened through its own stop) under both cost policies and both
directions, so the difference between the laddered and unladdered rows is the
lower-timeframe evidence and nothing else.

Under the **primary** geometry the ambiguity count is **0** — a wider stop and a
further target simply stop colliding inside one bar. That is a real secondary
benefit of the geometry rule, and it is not enough to make it a candidate.

---

## 11. Exit mechanics (§9)

Four mechanics, all arming at the same +1R so the comparison is of *mechanics*
rather than of a threshold. Production geometry, development sample,
cost-inclusive.

| mechanic | n | expectancy | avg winner | avg loser |
|---|---|---|---|---|
| `exit_full_target` (with ladder) | 149 | −0.6245 | +0.941 | −1.710 |
| `exit_full_target` (**no ladder — control**) | 132 | −0.5990 | +0.967 | −1.718 |
| `exit_partial_1r` | 131 | **−0.3546** | +0.643 | −1.054 |
| **`exit_break_even_1r`** | 131 | **−0.2955** | +0.850 | −1.026 |
| `exit_trail_prior_bar` | 131 | −0.3533 | +0.698 | −1.163 |

Holdout, same geometry: full target −0.5047 → break-even **−0.2125**.

**Exit management is worth about +0.30R per trade and it is not enough.** Every
mechanic roughly halves the average loser — which is what BX's give-back finding
predicted — and none comes close to zero. The ordering BX recommended is
confirmed: fix the stop first, then re-open exits.

Two caveats reported rather than buried:

* **Ambiguity multiplies.** A third watched level takes the ambiguous count from
  2 to 20 on development and 3 to 33 on the holdout, because two of the three
  levels now collide in bars the ladder cannot split. Those trades are excluded
  from expectancy and counted beside it.
* **The arming convention costs resolution.** A state change takes effect from
  the bar *after* the bar that triggered it, at whatever resolution resolved the
  trigger. A break-even stop is not tested against the same bar's adverse
  extreme, because four prices cannot order a high against a low.

`exit_trail_prior_bar` is labelled **NOT a structural trail** everywhere it
appears: the prior bar's low is a price, not a level the structural engines
produced.

---

## 12. Timeframe roles (§6)

The owner's hypothesis has four timeframes — 1W context, 1D structure, 4H setup,
1H entry — and the engine's role model has **three**. That is stated rather than
worked around, and it decomposes the question into two answerable parts:

* **"1W context + 1D/4H core"** *is* the production mapping. There is nothing to
  compare; it is variant A.
* **"…+ 1H execution refinement"** is not a role remap at all — it is an entry
  rule layered on a 4H decision, which is `entry_1h_confirmation` in §9 above.
  Measured: it improves production geometry (−0.62 → −0.36) and does not improve
  the primary geometry (+0.20 → +0.11), while declining half the setups.
* **1D context + 4H setup + 1H execution** is BW's `swing_1d4h1h_roles`, which has
  been INCONCLUSIVE and unmeasured since BW. **BY measured it** — see §12.1.

### 12.1 `swing_1d4h1h_roles` — measured, and clearly worse

BW's variant has been INCONCLUSIVE and unmeasured since BW. **BY measured it.**

```
production roles  1w/1d/4h    54 candidates
shifted roles     1d/4h/1h   364 candidates   (105,264 instants, 43.5 min)
```

Both sides are the **same six symbols over the same window**, with the evaluation
window held at thirty calendar days on both (180 bars on 4H, 720 on 1H), so the
pair differs only in which candles play which part. Cost-inclusive:

| policy | 1w/1d/4h | 1d/4h/1h |
|---|---|---|
| `geom_production` | −1.1094 (44) | −1.1088 (288) |
| `by_stop_0_35atr_target_2r` | +0.3466 (44) | **−0.3948** (296) |
| **`by_stop_0_5atr_target_2r`** | **+0.3699** (44) | **−0.3395** (295) |
| `by_stop_0_65atr_target_2r` | +0.2942 (44) | −0.3421 (294) |
| `by_stop_0_8atr_target_2r` | +0.1334 (42) | −0.3017 (291) |
| `by_stop_0_5atr_target_1_5r` | +0.4056 (46) | −0.3517 (305) |
| `by_stop_0_5atr_target_2_5r` | +0.4799 (44) | −0.2933 (284) |
| `by_stop_only_0_5atr` | −0.1333 (50) | −0.3221 (329) |
| `by_target_only_2r` | −0.7598 (40) | −1.3012 (275) |
| `by_setup_stop_0_5atr_target_2r` | −0.3783 (36) | −0.2294 (250) |
| `nonstruct_stop_0_5atr_target_2r` | +0.0437 (54) | −0.6087 (353) |

**`swing_1d4h1h_roles` is worse on every one of the eleven policies, and it is
not close.** It also admits **seven times as many setups** on the same six
symbols and the same window (364 against 54) and loses on them: the shifted
mapping is not selecting different trades so much as selecting *far more* trades,
at a fifth of the timeframe scale, and paying the noise. `geom_production` is the
one row that barely moves (−1.109 either way), which says the production geometry
is equally broken at both scales rather than that the mapping is neutral.

**BW's INCONCLUSIVE is now resolved: the shifted role mapping is REJECTED.**

**Two cautions on the left-hand column, and they matter.** It is the six majors
over the *development* window — **not a pre-registered sample**. Its figures are
higher than the sealed 15-symbol development result (+0.3699 against +0.1995)
for exactly the reason §7's symbol-class split gives, and they are shown here
**only** as the comparison baseline for the role mapping. Reading +0.37R as a
result would be post-hoc slicing of a contaminated window, which is the specific
mistake this milestone is built to prevent.

**Limitation BY-10.** The role capture uses the **six majors** rather than all
fifteen symbols: a 1H execution timeframe multiplies the instant count sixfold
and the full universe would not complete in reasonable time. The production-roles
comparison is cut to the same six symbols so the pair differs only in the role
mapping.

---

## 13. No-lookahead (§19)

Verified **on the real captures**, not only on fixtures, with a non-vacuity
control for every claim.

| check | result |
|---|---|
| Plans over 246 candidates × 11 sealed policies, every bar × 1000 | **IDENTICAL** (2,706 pairs) |
| **Control** — trades from those same plans | **2,416 / 2,416 changed** (non-vacuous) |
| Plans with **only post-decision** bars × 1000 | **IDENTICAL** |
| **Control** — trades with only post-decision bars mutated | **143 / 2,416 changed** |
| Plans under an arbitrarily scrambled 1H series | **IDENTICAL** |
| **Control** — outcomes under the scrambled 1H series | **236 / 1,200 moved** |

The structural half of the proof is stronger than the mutational half: a
`GeometryCandidate` holds prices, level lists and one ATR reading and **no bar of
any resolution**, so a policy handed nothing else cannot read forward. BY's three
new surfaces get their own guards because bar-blindness does not cover them:

* **entry rules read bars.** Every rule is shown invariant to arbitrary mutation
  of every bar before `signal_close_at`, and **sensitive** to the bars after it —
  parametrised over all five rules, both directions.
* **the ladder is a second series.** `geometry.py`, `geometry_variants.py` and
  `nonstructural.py` are parsed and asserted to import neither `intrabar`,
  `exits`, `entry` nor `validation_*`, and to name none of `PriceBar`,
  `simulate_trade`, `fill_at_level`, `BarLadder`, `mfe_r`, `mae_r`, `net_r`.
* **the pre-registration is rules, not data.** It is asserted to import no
  `PriceBar`, no `LabTrade`, no `GeometryCapture`, no `VariantMetrics` — so a
  threshold cannot be derived from a measurement even by accident.

`entry.py` takes `signal_at` and `signal_close_at` as **separate arguments** and
refuses a close that precedes an open, because deriving one from the other by
convention is how a four-hour lookahead gets in.

---

## 14. Hostile review (§20)

**31 probes, 0 failures.** Each attack tries to make the milestone say something
it should not, run against the real result rather than a fixture.

| attack | outcome |
|---|---|
| 0.5 ATR is the only winning point | measured: `FRAGILE_SPIKE`, and the failing 0.80 neighbour is printed |
| neighbouring thresholds fail | reported, in the neighbourhood table, not summarised away |
| costs erase the result | monotone +0.3187 → +0.1995 → +0.1399; the deciding column is the costed one |
| holdout goes negative | **it does**, and it is reported: −0.2361R |
| one symbol creates all the profits | largest share **10.2 %**, bound is 40 % |
| one giant winner creates the PF | largest win 6.72R of 27.13R total — 25 % |
| thin sample | 136 / 80 / 200 measurable, floor is 20 |
| long works / short fails | primary universe **disagrees** — short +0.1134 (128), long −0.0166 (88); holdout loses in **both** directions |
| bull only / bear only | **the primary curve changes sign** and every gain is earned before the validation boundary; the holdout curve is negative in every window |
| lower-timeframe missing / gaps | a partial cover **refuses to descend**; a one-rung ladder behaves as BX did |
| ambiguous event remains ambiguous | 2 of 19 and 3 of 21 — refused, never guessed |
| stop widened to a nonsensical level | 0.80 ATR measured and negative; the rule is a *selection* among real levels |
| no valid structural target | named refusal `below_minimum_planned_rr` (15) and `no_target_level` (4) |
| NO-TRADE explosion | 19 of 155 refused on development — counted beside the trades |
| candidate trades become too rare | 136 measurable, above the floor |
| provider history shorter than claimed | availability probed; 468 of 484 pairs refused the window |
| deterministic rerun | digest stable across `PYTHONHASHSEED` 0 / 1 / 12345 |
| the non-structural twin wins | it does **not** (+0.024 vs +0.200) — and it is permanently ineligible either way |
| the seal was edited | recomputed and matched at report time |
| a candidate falls in no sample | **0 unclaimed** of 480 |
| a declining entry rule looks like an improvement | fill rate printed beside every expectancy |

---

## 15. Mutation testing (§21)

**57 probes · 55 killed · 2 analysed and shown non-defective · 0 genuine
survivors.** Seven were added after the code review, one per defect it found. Byte-exact restoration verified by SHA-256; `__pycache__` cleared
before every run.

Probed invariants: the seal · a threshold moved after freeze · a dropped
neighbour · promotion on the frictionless column · sample disjointness · sample
boundary half-openness · the volatility-floor comparison boundary · the
next-valid-level rule · the setup-vs-execution rung · R arithmetic · the
synthetic label · the control claiming to be structural · guessed ambiguity ·
partial 15m cover · ladder ordering · half-open bar windows · filling at the
signal bar · confirmation by wick · limit expiry · the 1H path constraint ·
weighted partial exits · widening a stop · a loosening trail · testing a state
change on its own bar · an arming level colliding with the target · plateau
`all`-vs-`any` · the three-point minimum · post-hoc promotion · non-structural
promotion · an ignored holdout · break-even development · a thin sample read as
rejected · a relaxed concentration bound · an always-passing lookahead criterion ·
mismatched sample labels · a re-computed cost path · a frictionless verdict · an
empty sample reported as zero · truncated bars · dropped walk-forward windows ·
a digest blind to an edited R · overwriting a measurement · a silent schema
upgrade · an unscaled evaluation window · a dropped miss count · a missing
no-ladder control · an estimated refinement series · a mis-rooted ladder.

**The first run killed 41 of 47.** Every one of the six survivors was
investigated and none was deleted:

| survivor | why it survived | resolution |
|---|---|---|
| next-valid-level rule | the fixture never had a nearest level inside the floor | 3 tests added, incl. the `SETUP_BEYOND_VOLATILITY` rung |
| setup rung read as execution | the new rung had no test at all | covered by the same 3 tests |
| unweighted partial average | a **50/50** split makes the weighted and plain means identical | a 25/75 fixture, where they differ |
| loosening trail | the fixture path rose monotonically | an asymmetric path where the prior bar is behind the stop |
| re-computed cost path | the test asserted the path was equal, never that the net figure **moved** | assert both, plus costed < frictionless |
| truncated bars | the sample boundary already sat past the last bar | a spec ending **inside** the bar array |

Two further probes were added after the §7 defect was found — *the cross keyed on
numbers rather than family* and *a cross collision overwriting silently* — and the
second of them survived its first run, because the collision check had been
written **twice, once per axis**, and removing one copy left the other firing. The
rule was extracted to a single `claim` helper and covered by a per-axis
parametrised test, which is the same lesson `plateau_from` taught Milestone BX: a
rule enforced in two places is a rule half of which can be deleted unnoticed.

**Two probes survive the final run and are equivalent, not gaps.** Both were
settled empirically rather than by argument:

* **`geometry:no-trade-refusal-bypassed`** — replacing the `STOP_INSIDE_VOLATILITY`
  fallthrough with `return levels[0]` produces a **byte-identical signature**
  over 246 real candidates × 11 policies. The fallthrough is reached only when no
  level qualifies, and `plan_geometry`'s own floor then produces the identical
  skip with the identical reason. The explicit refusal is kept because it names
  the condition where it is decided.
* **`exits:trail-loosens`** — the "only tighten" pre-check was instrumented and
  fired **0 times across 246 real candidates**. A bar whose adverse extreme is
  behind the current stop would already have stopped the trade out, so the branch
  is unreachable through the public path. It is a defensive guard, and the real
  constraint — `_State.tighten` refusing a widening outright — **is** killed by
  probe 22.

---

## 16. Verification

| gate | result |
|---|---|
| **Full repository under `-W error`** | **11,726 passing**, 0 failures (from 11,285 at BX) |
| Focused BY suite | **345 tests** across 12 new files |
| **Mutation probes** | **57 run · 55 killed · 2 equivalent · 0 survivors** |
| **Hostile review** | **31 probes, 0 failures** |
| **No-lookahead on real captures** | 3 claims, 3 non-vacuous controls, all held |
| **BX capture reproduced** | 246 candidates / 104,130 instants — **exact** |
| Determinism | result digest stable across `PYTHONHASHSEED` 0 / 1 / 12345 |
| Architecture guards (`swing_lab`) | all passing; module roster updated |
| Dashboard suite | passing, including every AST guard |
| New runtime dependencies | **0** |
| ADRs required | **0** |
| Guards weakened | **0** (one exemption *widened* — §17) |

### Coverage

Statement + branch on the ten new modules:

| module | cover | notable misses |
|---|---|---|
| `validation.py` | **99 %** | 146 |
| `intrabar.py` | **97 %** | 81, 87, 125, 157 |
| `preregistration.py` | **97 %** | 248, 252, 361, 601 |
| `validation_artifact.py` | **97 %** | 223, 302–305 |
| `exits.py` | 93 % | type guards, unreachable defensive branches |
| `nonstructural.py` | 93 % | type guards |
| `entry.py` | 92 % | type guards, 287, 346, 389 |
| `validation_mechanics.py` | 89 % | 481–488, 588–608 — the provider fetch path |
| `validation_study.py` | 84 % | 966–988, 1030–1078 — `run_validation_experiment` / `capture_for_window` |
| **total** | **92 %** | |

**Not 100 %, and the misses are named.** The two large blocks are the
fetch-and-replay entry points, which need a live provider — exactly the exclusion
BX recorded for `run_geometry_experiment`, and for the same reason. Their
argument validation, everything that runs before the network, is covered. The
rest are `isinstance` guards and defensive branches offline fixtures cannot
reach. **No coverage exclusion was added anywhere.**

---

## 17. Guards widened, with reasons

**One**, and it was not weakened.

`test_swing_lab_architecture.py::test_only_the_artifact_module_touches_the_filesystem`
now admits `validation_artifact.py` alongside `artifact.py` and
`geometry_artifact.py`, via a named `_ARTIFACT_MODULES` constant. It is the one
BY module that touches a file, it writes a JSON research record, and
`test_the_artifact_modules_write_no_store_record` was extended to cover it too.
No other BY module is exempt — the renderer, the study, the mechanics and the
pre-registration all fail that guard if they ever open a path.

**Two guards fired during development and were obeyed rather than widened.**

* `test_no_geometry_module_assigns_a_production_constant` caught
  `preregistration.py` restating `SAMPLE_FLOOR`. Fixed by **importing** the
  constant from `fmis.swing_lab.metrics`. The seal still covers its *value*,
  because every criterion interpolates it into its requirement text — change the
  floor to 25 and the digest changes, which is exactly the sensitivity a copy
  would have lost.
* `test_no_module_catches_bare_exception` caught a `try/except Exception` in
  `validation_render.py`. Fixed by removing the need for it: the renderer now
  reads sample names from the manifest's own declaration order instead of the
  membership tally's keys, and `run_validation_study` guarantees a cell exists
  for every one — including empty cells for a holdout that was not opened.

---

## 18. Surfaces

### `fmits research validation`

```
fmits research validation --open-holdout --save validation.json
```

**It takes no universe, no window and no threshold.** BX's command took
`--development` and `--holdout` because its samples were a choice; BY's are part
of what was sealed, and the command **refuses** `--start` and `--end` by name
rather than accepting and ignoring them — a flag that looks like it moves a
sealed boundary is worse than no flag.

`--open-holdout` is off by default. Without it the holdout replay is **not even
fetched**, every holdout criterion reports as unevaluable, and no policy can
reach candidate status. That is the development pass, and it is the default so
the holdout cannot be inspected by habit.

### Dashboard `/validation`

A read-only page over a **saved** artifact, ordered for a decision: the verdict,
the seal, the samples **with their contamination beside them**, the results in
pre-registration order, the plateau with its failing neighbours, costs with the
deciding scenario marked, walk-forward, decomposition, limitations.

The page shows two things BX's could not: **which pre-registration a number was
judged under**, and **which cost scenario decided it**. Both travel as data
rather than as page copy, because a figure whose basis is written in prose beside
it is a figure that can be quoted without its basis. The dashboard still opens no
file — the artifact is decoded by the CLI and handed in already parsed.

### Trades are inspectable — the chart seam

A `LabTrade` carries prices and an outcome but **not where its stop came from**,
so the artifact carries a `geometry` record beside every trade, positionally
aligned and asserted to be so. Each one holds:

```
symbol · setup_id · signal_at · signal_index · execution/setup/context interval
entry · stop · target · risk · reward · planned_rr
stop_provenance · target_provenance      e.g.  4h:lower_high@70 → 1d:higher_low@222
stop_bps · target_bps · stop_atr_multiple · target_atr_multiple
execution_atr · setup_atr
```

`signal_index` is the OHLC window reference: a future instrument page resolves
**BTCUSDT → historical trade → chart → levels** from the artifact alone, without
re-running an hour-long replay and without reverse-engineering a string. The
non-structural control's levels read `synthetic:atr_multiple_from_entry@?` and
can never be mistaken for a market fact.

**This was a real gap, found by checking the claim rather than asserting it.**
The first version of this section claimed provenance travelled with each trade;
inspecting a written artifact showed it did not. Adding it left the result digest
**byte-identical** (`fadf2971…` before and after), which is the correct outcome:
provenance is a property of the plan, not a measurement.

---

## 19. Limitations

`VALIDATION_LIMITATIONS` (BY-1…BY-10) travels inside every artifact and prints on
every report, with BX-1…BX-8 and BW-1…BW-7 beneath it unchanged. The five that
most change what the tables mean:

- **BY-2** — the development sample is **contaminated by construction**. BX
  measured all fifteen symbols and BY's primary hypothesis is BX's own post-hoc
  finding. A positive development figure is a *necessary condition* for a
  candidate, never evidence for one.
- **BY-3** — the holdout window opens 2024-06-01 rather than 2023-06-01 because
  those symbols' weekly history cannot reach the warm-up start any earlier.
  Holdout and development cover overlapping but not identical periods, and a
  difference between them confounds symbol with period to that extent.
- **BY-4** — the holdout symbols are materially **less liquid** (median 24h quote
  volume ~0.7M USDT against ~18.8M, measured at the run date and not over the
  window). The holdout tests whether a rule generalises across *structure*, not
  whether it would have been executable at size.
- **BY-5** — the universe is **survivorship-filtered**. Only currently-tradable
  pairs were probed, so every symbol delisted inside the window is absent by
  construction.
- **BY-10** — the timeframe-role capture uses six symbols rather than fifteen.

Additionally: per-symbol expectancy is unstatable at this sample size (34 of 36
cohorts below the floor); the sealed hypotheses overlap heavily and are not
independent experiments; and `entry_pullback_limit` is the one rule whose fill is
an assumption rather than a printed trade.

---

## 20. Decision

**B. NO_CANDIDATE.**

The pre-registered hypothesis failed, and it failed on the criteria that were
written down before it was measured:

* `validation_expectancy` — **−0.1761R**, required ≥ 0;
* `holdout_expectancy` — **−0.2361R**, required ≥ 0;
* `parameter_plateau` — **FRAGILE_SPIKE** on the stop axis, required ROBUST_PLATEAU.

It did **not** fail for want of data, for want of trades, for concentration, for
drawdown, or for costs. It cleared all of those. It failed **two independent
generalisation tests**: on the fifteen symbols it was developed on the effect
persisted through several windows and then broke at the development/validation
boundary, and on twenty-one symbols it had never seen it was absent from the
first window onward. Either failure alone would refute it.

**Stated no more strongly than the evidence allows.** Six half-year windows on
one universe and four on another cannot establish *why* the effect stopped —
regime, crowding, liquidity or chance are all consistent with what was measured,
and this milestone distinguishes none of them. What it establishes is narrower
and sufficient: the rule did not generalise across time on its own universe, and
did not generalise across universe at any time.

No strategy earned CANDIDATE status. **Production remains the current policy, and
nothing here is proposed for shadow, paper or forward testing.**

---

## 21. Changed files

**New (`src/fmis/swing_lab/`):** `preregistration.py`, `nonstructural.py`,
`intrabar.py`, `entry.py`, `exits.py`, `validation.py`, `validation_study.py`,
`validation_mechanics.py`, `validation_artifact.py`, `validation_render.py`

**Modified (`src/`):**
- `swing_lab/geometry.py` — `StopRule.SETUP_BEYOND_VOLATILITY`; the
  `PlansGeometry` protocol and `GeometryPolicy.plan`
- `swing_lab/geometry_replay.py` — `trades_for_policy` depends on the protocol
- `swing_lab/models.py` — `LabExitReason.ENTRY_NOT_TRIGGERED`
- `pipeline/cli.py` — `fmits research validation`; `--validation-artifact`
- `operator_dashboard/{models,sections,render,compose,server}.py` — `/validation`

**New (`tests/`):** `test_swing_lab_preregistration.py`,
`test_swing_lab_intrabar.py`, `test_swing_lab_entry.py`,
`test_swing_lab_exits.py`, `test_swing_lab_nonstructural.py`,
`test_swing_lab_validation.py`, `test_swing_lab_validation_study.py`,
`test_swing_lab_validation_artifact.py`,
`test_swing_lab_validation_mechanics.py`,
`test_swing_lab_validation_render.py`, `test_swing_lab_validation_surface.py`,
`test_swing_lab_validation_nolookahead.py`

**Modified (`tests/`):** `test_swing_lab_architecture.py` (module roster, one
exemption widened), `test_swing_lab_geometry.py` (3 tests closing mutation gaps),
`test_swing_lab_geometry_study.py` (one refusal message updated for the protocol)

**Documentation:** this report; `reports/README.md`;
`docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated: BY delivers a research
capability and a read-only page, and its headline result is that the hypothesis
failed. Recording that as a user-visible capability release would misrepresent it.

---

## 22. Git state at completion

**Nothing was committed and nothing was pushed.**

Two commits are **prepared but not created**:

```
Commit A   feat(research): add preregistered swing geometry validation
Commit B   docs(product): record swing geometry validation milestone
```

`HEAD` remains `3598b4c`, `origin/main` remains `3598b4c`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.

---

## 23. Recommended next milestone — do not begin it

**BZ — Persistence, not geometry.**

BY's result changes what the next question should be. Three milestones have now
measured this strategy and the pattern is consistent:

1. **Stop looking for a better geometry on this admission rule.** BW rejected the
   timeframe variants, BX rejected thirteen geometries, BY rejected six points of
   the one geometry BX's own evidence pointed at. The geometry search space has
   been covered thoroughly enough that a fourteenth rule is unlikely to be the
   answer.
2. **The measurable thing BY found is a decay, and nothing measures decay.** The
   primary rule earned +0.23R in 2023H2 and lost money in all five subsequent
   half-years. Whether that is regime, crowding or a structural change in the
   instruments is *answerable* and currently unanswered — and it is a better
   question than "which stop multiple".
3. **Exit management is the one lever that moved every sample in the same
   direction** (+0.30R on development, +0.27R on the holdout, under production
   geometry). It is not enough alone and it is now **measurable**, which it was
   not before BY. A milestone that combined it with a sounder admission rule
   would be testing something new rather than re-testing geometry.

`swing_1d4h1h_roles` is measured in §12.1 and **REJECTED** — worse on all eleven
policies, admitting seven times the setups and losing on them. BW's INCONCLUSIVE
is resolved, and the shifted mapping is not a direction worth reopening.
