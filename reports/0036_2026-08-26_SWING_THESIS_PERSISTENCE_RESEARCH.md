# Swing Thesis Persistence & Exit Mechanics — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0036 |
| **Title** | Swing Thesis Persistence & Exit Mechanics (Milestone BZ) |
| **Date** | 2026-08-26 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `fd1270b`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final |

**Milestone:** BZ — Swing Thesis Persistence & Exit Mechanics.

**Scope guard.** No production trading policy changed. The stop rule is still the
nearest execution-timeframe level, the target rule is still the nearest
setup-timeframe level, `CONFIRMATION_LOOKBACK_BARS` is still `10`,
`MINIMUM_AGREEING_FAMILIES` is still `2`, and `DEFAULT_TIMEFRAMES` is still
1W/1D/4H. **No exit policy was promoted.** Nothing here is a forward test, no
order was placed, and no exchange was contacted.

---

## 1. The answer, first

> **Did any pre-registered exit or persistence mechanism earn the right to enter
> shadow or paper testing?**
>
> **No. NO_CANDIDATE.** All five sealed families are **REJECTED** on both
> geometries — ten judgements, ten rejections — and not one reaches even
> `MECHANISM_EVIDENCE`. Every one fails the same sealed criterion first:
> `improves_development`, which required a **+0.10R** like-for-like gain over its
> own control. The best development improvement measured anywhere was **+0.0134R**.

**But the milestone's primary question is not the same as its verdict, and the
answer to the question is yes.**

> **Does thesis persistence exist, and is it measurable causally?**
>
> **Yes to both, and this is BZ's real finding.** The production engines' own
> structural reading decays measurably and monotonically with trade age, and
> every reading is confirmed by its own bar. On 151 development positions under
> production geometry:

| bars held | INTACT | STRENGTHENED | WEAKENED | CONFLICTED | INVALIDATED |
|---|---|---|---|---|---|
| 1 | 149 | 1 | 1 | 0 | 0 |
| 3 | 129 | 19 | 3 | 0 | 0 |
| 12 | 97 | 37 | 11 | 5 | 1 |
| 24 | 75 | 33 | 19 | 20 | 4 |
| 60 | 41 | 35 | 29 | 26 | 20 |

**A swing thesis is intact for essentially every position at bar 1 and for
barely a quarter of them at bar 60.** That is persistence, it is measured from
information available at each bar, and nothing in BW, BX or BY could state it.

**And acting on it does not pay.** The three findings that decide the milestone:

1. **The thesis-failure exit is too rare and too late.** It fired on **2 of 132**
   development positions under production geometry and 11 of 136 under BY's. By
   the time the setup timeframe has fully reversed, the stop has almost always
   already resolved the trade. Development improvement: **−0.0173R** and
   **−0.0311R**.

2. **The give-back finding is confirmed and is far larger than BX measured — and
   capping it destroys the edge.** Under BY's geometry, **99 of 136** development
   positions reached **+2R**, and the median *realised* return of those was
   **−1.05R**. Yet the expectancy is *positive* (+0.1906R, PF 1.25) because 44
   trades reached target. The distribution is a positive tail, and a give-back cap
   cuts the tail before it cuts the losers: development **−0.0772R**.

3. **Every mechanism helps on the holdout and hurts on development — the opposite
   of overfitting, and just as fatal.** Give-back protection is worth **+0.1992R**
   on the holdout and **−0.0772R** on development. A mechanism whose sign flips
   between samples is not a mechanism; it is a property of one sample. The sealed
   criteria catch this without a judgement call.

**What this changes for the next question.** BW rejected timeframe variants, BX
rejected thirteen geometries, BY rejected six points of one geometry, and BZ now
rejects five exit mechanisms. The consistent result across four milestones is
that **this admission rule's trades give back almost everything they earn** —
92.1 % surrender a full R of open profit — and that no exit rule tested can
recover it without also removing the tail that makes the expectancy positive.
The problem is not where the trade exits. It is what is being admitted.

---

## 2. Starting git state, and a correction to the brief

The milestone brief named `30d2bc6` as the starting release. **It was stale by
one commit**, and the difference mattered enough to stop and report before doing
anything else.

```
branch            main
HEAD              fd1270b540b72dd9c841e3daec7951d7bb640918
                  fix(research): correct BY walk-forward universe and dashboard wiring
origin/main       fd1270b  (0 ahead / 0 behind)
ls-remote         fd1270b  (local, origin and remote all agree)
stash             empty
unresolved ops    none
working tree      clean apart from 16 pre-existing untracked AP/BB-era research
                  documents under docs/design/ and docs/reviews/ — untouched
```

`30d2bc6` **is** an ancestor of `HEAD`. The intervening commit is a correction to
Milestone BY itself, and BZ depends on what it corrected: BY's walk-forward and
every decomposition had pooled all three samples, so the traded universe doubled
at 2024-06 as the holdout entered, and BY's published conclusion — *"BX's finding
was one six-month window"* — was wrong. Two decomposition rows also reversed
sign. The owner was asked and confirmed BZ should build on `fd1270b`.

**Baseline suite before any BZ code was written: 11,726 passing under `-W error`**
— exactly the count BY's report claims, which is the first independent
confirmation that the repository is what the record says it is.

---

## 3. Architecture audit — what BZ reused, and the one seam it added

§2 of the brief requires the existing owners to be mapped before any code is
written. They were, and the result is that **BZ added no backtester, no fill
engine, no ATR, no structure engine, no cost engine, no candle reducer and no
identity scheme.**

| Concern | Owner BZ reuses | How |
|---|---|---|
| replay transport | `swing_setup.backtest_replay.fetch_raw_klines` | via `capture_for_window` |
| warm-up derivation | `swing_setup.research_warmup` | via `capture_for_window` |
| candidate generation | `swing_lab.geometry_replay.capture_geometry_candidates` | called, one new optional argument |
| setup identity | `swing_setup.research_identity.OpportunityTracker` | untouched |
| timeframe roles | `pipeline.multi_timeframe.TimeframeRole` | untouched |
| market structure / trend / regime | `structural_trend`, `market_regime`, `decision_context` | **read**, never re-derived |
| directional evidence | `SetupInputs.evidence_state` / `evidence_dominant_alignment` | copied onto the observation |
| entry price | `swing_lab.trades.simulate_trade`'s rule — open of the bar after the signal | reproduced by the control, asserted equal |
| stop / target | `swing_lab.geometry.GeometryPolicy` | fixed, not under test |
| ATR | `features.indicators.atr` via `pipeline.regime.FAST_ATR_PERIOD` | untouched |
| fill semantics | `paper.fills.fill_at_level`, `PriceBar.reached`, `PriceBar.opened_beyond` | called; a guard forbids a second definition |
| MFE / MAE | `swing_lab.trades` and BZ's `persistence.observe_path` | same arithmetic, same sign convention |
| bars held | `simulate_trade` / `simulate_managed_trade` | untouched |
| cost policy | `trade_lifecycle.PaperCostPolicy`, BY's three scenarios | **imported**, never restated |
| intrabar ladder | `swing_lab.intrabar.BarLadder` | reused unchanged |
| exit mechanics | `swing_lab.exits.simulate_managed_trade` | **extended additively** |
| metrics | `swing_lab.metrics.compute_lab_metrics`, `SAMPLE_FLOOR` | imported |
| walk-forward / decomposition | `swing_lab.validation_study.walk_forward`, `decompose` | called |
| concentration | `swing_lab.robustness.concentration_of` | called |
| samples / cost scenarios | `swing_lab.preregistration.SAMPLES`, `VALIDATION_COST_SCENARIOS` | **imported by identity** — a test asserts `is SAMPLES` |
| result surface | `pipeline.cli` `research` area | one new choice |

### The one new seam, and why it was necessary

BZ needs the structural engines' reading at **every** 4H bar, not only at the
bars that admitted a setup — because an exit decision at bar *t* needs the
structure at bar *t* whether or not bar *t* produced a setup.

The cheap way to get that is a second replay. That is also the **wrong** way: two
walks over the same history can differ for provider reasons, and every BZ claim
about a state *transition* would then rest on comparing two datasets rather than
one. So `capture_geometry_candidates` grew exactly one additive argument — an
`observer` sink — and one pass now produces two outputs:

```
replay ──┬──► GeometryCandidate per admitted setup   (what BX and BY read)
         └──► ThesisObservation per analysable bar   (what BZ reads)
```

**The seam is justified by a proof, not by an argument.** The observer returns
nothing, is called after the admission assessment is already fixed, and is not
even constructed when absent — so every pre-BZ caller's behaviour and cost are
byte-identical. `test_the_observer_cannot_change_the_capture` asserts a capture
taken with a collector attached is equal, candidate for candidate and bar for
bar, to one taken without.

### What was NOT built, and why

* **No second exit walker.** BZ's mechanics live in `exits.py` beside BY's,
  because the ladder-descent logic is the subtle part and duplicating it would
  create two definitions of intrabar ordering. BY's four mechanics are asserted
  unchanged, and BY's pinned pre-registration digest is asserted byte-identical.
* **No second sample definition.** BZ imports BY's `SAMPLES` object by identity.
* **No artifact module.** BZ writes no file. The study is a value; the CLI prints
  it. Adding a fourth artifact writer to the filesystem exemption list would have
  widened a guard for a capability this milestone does not need.

---

## 4. The pre-registration, and when it was sealed

`src/fmis/swing_lab/persistence_preregistration.py` fixes every hypothesis id,
threshold, checkpoint, sample boundary, cost scenario, ambiguity rule and
promotion criterion, and pins their SHA-256:

```
id      bz-swing-thesis-persistence-v1
digest  4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175
```

**It was computed and pinned before the first capture was run**, and the run
script verifies it before fetching a single candle — the first line of the run
log is `seal verified 4d089ff4…`. The seal and the content live in the same file,
so a change to either without the other is a red test
(`test_swing_lab_persistence_preregistration.py`, 34 tests). Fifteen parametrised
mutations — a threshold moved, a failing neighbour dropped, the deciding scenario
switched to frictionless, a criterion deleted, a sample edge shifted, the
hypotheses re-ordered — are each shown to change the digest.

### The six sealed hypotheses

| id | policy | role | rule |
|---|---|---|---|
| BZ-H0 | `bz_exit_control` | control | one stop, one target, no management — BW/BX/BY's own rule |
| BZ-H1 | `bz_exit_thesis_failure` | thesis | exit when the 1D structural trend **opposes** the direction, or 1D and 4H disagree in sign |
| BZ-H2 | `bz_exit_stagnation_12` | time | exit after 12 4H bars without +0.5R of favourable progress |
| BZ-H3 | `bz_exit_giveback_half` | profit protection | after a peak of ≥ +1R, exit on surrendering half of that peak |
| BZ-H4 | `bz_exit_structural_trail` | structural trail | trail to newly **confirmed** 4H protective levels only |
| BZ-H5 | `bz_exit_thesis_and_giveback` | combination | H1 ∪ H3, both unchanged at their own thresholds |

Every non-control hypothesis carries a **`PREDICTION:`** and a **`REFUTED BY:`**
sentence, and `BzHypothesis.__post_init__` refuses to construct one without both.
A rule with no stated refutation cannot fail, and a milestone whose rules cannot
fail is a search.

### Two verdicts, and why that is not a softened bar

BY asked *is this geometry profitable*, and one verdict answers that. BZ asks
*does post-entry management add information*, which is answerable even where the
absolute level is negative — and production geometry loses roughly 0.5R per trade
on every sample BW, BX and BY measured. A milestone whose only verdict were
"positive expectancy" would have returned NO_CANDIDATE without measuring
anything.

So two verdicts are sealed, and they are **not** ranked as a consolation:

```
MECHANISM_EVIDENCE   did the family improve on its own H0 control, on the same
                     setups, robustly, on all three samples?
CANDIDATE            is the complete policy positive cost-inclusive on ALL THREE
                     samples, and does it clear every other gate?
```

**`MECHANISM_EVIDENCE` can never promote anything.** `BzVerdict.earns_forward_test`
is `True` for `CANDIDATE` alone, `is_approved_for_trading` is `False` for every
member, and both are asserted. **`CANDIDATE` uses Milestone BY's bar, unchanged**
— positive on development, non-negative on validation *and* on the holdout.

### The robustness neighbourhood is not a search

Two families carry a threshold and each is measured at three points (stagnation
at 8/12/18 bars, give-back at 0.33/0.50/0.67); the other three have no threshold
to sweep. **No neighbourhood point is pre-registered**, `is_bz_pre_registered`
returns `False` for every one of them, and `assess_bz`'s first criterion is
membership plus a digest match — so a neighbourhood point cannot be promoted
whatever its numbers.

---

## 5. The samples

Imported from Milestone BY **by identity**, not restated — a test asserts
`BZ_PRE_REGISTRATION.samples is SAMPLES`, so the two milestones cannot drift
apart and a BZ figure is comparable with a BY figure by construction.

| sample | symbols | window | contamination |
|---|---|---|---|
| **Development** | 15 (BX's universe) | 2023-06-01 → 2025-06-01 | **CONTAMINATED BY CONSTRUCTION** |
| **Validation** | the same 15 | 2025-06-01 → 2026-08-01 | **SEMI-CONTAMINATED** — new period, old symbols |
| **Holdout** | **21 never measured** | 2024-06-01 → 2026-08-01 | **THE HOLDOUT** |

BY's limitations BY-2 … BY-5 therefore apply to BZ unchanged and are restated in
`BZ_LIMITATIONS` as BZ-5.

---

## 6. The observational study — design before results

§5 of the brief requires the path dataset to be built and understood **before**
any exit policy is measured. It was, and the ordering is enforced by the module
layout: `persistence.py` holds the vocabulary and imports nothing that can plan a
trade; an architecture guard asserts `geometry.py`, `geometry_variants.py` and
`nonstructural.py` import nothing from it, in both directions.

### The distinction the whole milestone is built around

```
DESCRIPTIVE   what winning and losing paths looked like, in hindsight
CAUSAL        what was observable at bar t and could have decided at bar t
```

A sentence like *"trades that eventually won had an intact 1D structure"*
conditions on the outcome and therefore contains the future. It is **not** a
trading rule. `PersistenceTrack` carries both kinds of field because the
milestone needs both, and they are separated structurally:

* **CAUSAL** — `checkpoints`, each a `PostEntryCheckpoint` whose every field is
  confirmed by its own bar. Only these may build a rule.
* **DESCRIPTIVE** — `peak_r`, `bars_to_peak_r`, `final_close_r`,
  `total_giveback_r` and every `bars_to_*` timing. Reported, never a rule.

**The labelling is checkable rather than asserted.** A test mutates every bar
after the last checkpoint and requires the causal half to be byte-identical
**and** the descriptive half to move. A `peak_r` that could not move under a
future mutation would be causal and mislabelled.

### The vocabulary

`ThesisState` has six members and the partition is total: `INTACT`,
`STRENGTHENED`, `WEAKENED`, `CONFLICTED`, `INVALIDATED`, `UNAVAILABLE`. It is
derived from **two** observations and a direction — the entry instant and the
current one — because "weakened" is a statement about a change and a single
snapshot cannot make one. The precedence is fixed in the seal:

```
1. UNAVAILABLE   either instant is missing
2. INVALIDATED   the setup timeframe now OPPOSES the direction
3. CONFLICTED    setup and execution disagree in sign
4. WEAKENED      support present at entry is gone, or the regime left TRENDING
5. STRENGTHENED  support absent at entry has appeared
6. INTACT        none of the above
```

`INVALIDATED` outranks `CONFLICTED` deliberately: a setup timeframe that has
fully reversed is invalidation whatever the execution timeframe is doing, and
reporting that as a mere disagreement would understate it.

**`WEAKENED` is excluded from `is_adverse`** and therefore fires no exit. A rule
that exited on weakening would exit almost every trade almost immediately — the
setup trend passes through `NEUTRAL` constantly — and a mechanism that fires on
nearly every trade is a time stop wearing a structure rule's clothes.

**`UNAVAILABLE` is a stated absence, never agreement.** A data gap must not read
as a thesis failure, and a hostile probe asserts a position is not closed by one.

### The checkpoints

`CHECKPOINT_BARS = (1, 2, 3, 6, 12, 18, 24, 36, 48, 60)` — dense where BX
measured the typical trade to be decided (median 1 bar held, p75 of 3) and thin
afterwards, **ending exactly at the 60-bar evaluation window bound**. A
checkpoint past the bound would observe bars no trade was ever given.

---

## 7. The captures, and the production control reproduced

```
one replay per universe, with the timeline collector attached
primary capture   15 symbols · 104,130 measured instants · 2023-06 → 2026-08
holdout capture   21 symbols ·                            · 2024-06 → 2026-08
timeline          205,956 analysable instants observed
total wall clock  77.3 min
```

**104,130 measured instants is Milestone BY's figure exactly**, and BX's before
it. The capture reproduces before anything BZ-specific is read.

| control check | BZ | BY | |
|---|---|---|---|
| `geom_production` development expectancy | **−0.5990** (132) | −0.5990 (132) | **exact** |
| `geom_production` development ambiguity | **19** | 19 | **exact** |
| `geom_production` holdout ambiguity | **21** | 21 | **exact** |
| `by_stop_0_5atr_target_2r` development | **+0.1906** (136) | +0.1995 (136) | **differs by 0.0089R** |

### Defect BZ-D2 — RECONCILED MECHANICALLY, ROOT CAUSE UNRESOLVED

**This section was rewritten by the completion pass of 2026-08-27**, after the
capture was persisted. The first version said the cause "could not be
established". It can now be established *mechanically*, and the residual is
inside BY's own quoted precision — but **which** of two candidate causes actually
occurred remains unrecoverable, and that is stated rather than glossed.

#### The trade

One `TIME_STOP` exists on development under BY's geometry, and it is the whole
difference:

```
setup_id            BNBUSDT|long|from=2024-12-23T00:00:00+00:00
symbol / direction  BNBUSDT / long
signal_at           2024-12-24T20:00:00+00:00   (bar index 3747)
entry_at / entry    2024-12-25T00:00:00+00:00 / 696.89
stop  / provenance  682.68  ← 4h:higher_low@247
target / provenance 732.11  ← 1d:lower_high@239
risk                14.21
exit_at / exit      2025-01-03T20:00:00+00:00 / 714.88   (bar 60 of 60)
gross / cost / net   +1.266010 / 0.099350 / +1.166659 R
```

#### It is the most knife-edge trade in the sample

| within the 60-bar window | value | distance |
|---|---|---|
| **maximum high** | **731.24** | target 732.11 — **short by 0.87 = 0.0612 R** |
| **minimum low** | **683.00** | stop 682.68 — **margin 0.32 = 0.0225 R** |
| first bar reaching the target | **+77 bars** | the window bound is **60** |
| first bar reaching the stop | +86 bars | — |

The position spends sixty bars inside a corridor **six hundredths of an R** below
its target and **two hundredths of an R** above its stop, and then times out.

#### The arithmetic closes

| | |
|---|---|
| BZ measured total, 136 trades | **25.9234 R** → +0.190613 |
| BY implied total (`+0.1995 × 136`) | **27.1320 R** |
| BY − BZ | **1.2086 R** |
| this trade at `TARGET` instead of `TIME_STOP` | +2.377973 R vs +1.166659 R = **1.2113 R** |
| **unexplained residual** | **0.0027 R** |

BY quotes +0.1995 to four decimals, so ±0.00005 R per trade is ±0.0068 R across
136 — **the residual is inside BY's own quoted precision.** One trade's exit
classification therefore accounts for the entire discrepancy.

#### What is ruled out, and what is not

| hypothesis | verdict | evidence |
|---|---|---|
| **A — a BZ defect** | **RULED OUT** | the control walker matches `simulate_trade` over **4,000 randomised paths, 0 mismatches**, and reproduces BY's production figure to four decimals on 132 real trades |
| **B — a BY defect** | **CANNOT BE ASSESSED** | BY persisted no capture; its level lists and plans no longer exist |
| **C — mutable / refetched source data** | **CONSISTENT, UNCONFIRMABLE** | the provider may have revised a candle or extended a series between BY's fetch and BZ's, moving a 1D pivot and hence the selected target |
| **D — different replay / capture boundaries** | **RULED OUT** | the window is **not** truncated — 3,565 bars remain after the entry, the exit is not the last captured bar, and the window is anchored on timestamps rather than indices |
| **E — different `TIME_STOP` semantics** | **RULED OUT** | BZ's `TIME_STOP` *is* `simulate_trade`'s, proven equivalent; the exit is the close of exactly the 60th bar after entry |
| **F — another identified mechanism** | **IDENTIFIED** | **knife-edge level selection.** At 0.0612 R from its target, any sub-percent difference in the selected 1D target — or in the stop, which moves the 2R threshold and therefore *which* 1D level qualifies under `FIRST_SETUP_SUPPORTING_RR` — flips this trade between `TIME_STOP` (+1.17 R) and `TARGET` (+2.38 R) |
| **G — unrecoverable provenance** | **THE CLASSIFICATION FOR B vs C** | distinguishing a BY defect from a data revision needs BY's level lists, which were never stored |

**Formally: the discrepancy is RECONCILED to one trade and one exit
classification worth 1.2113 R, with the mechanism identified (F). The root cause
is classified UNRESOLVED_PROVENANCE (G) between hypotheses B and C.**

**Missing evidence, named exactly:** Milestone BY's `GeometryCapture` for the
15-symbol primary universe — specifically the 1D `setup_target_levels` and the 4H
`execution_stop_levels` for `BNBUSDT` at bar 3747, and the resulting
`GeometryPlan`. Nothing else would settle it, and nothing else is missing.

#### BZ reproduces itself; the instability is not on BZ's side

The completion pass replayed the entire experiment a **second** time, a day after
the first, from an independent fetch. Every control figure is identical:

| control, cost-inclusive | 2026-08-26 | 2026-08-27 |
|---|---|---|
| `geom_production` / development | −0.5990 (132, amb 19) | **−0.5990 (132, amb 19)** |
| `geom_production` / validation | −0.4566 (84, amb 4) | **−0.4566 (84, amb 4)** |
| `geom_production` / holdout | −0.4877 (203, amb 21) | **−0.4877 (203, amb 21)** |
| BY geometry / development | +0.1906 (136, amb 0) | **+0.1906 (136, amb 0)** |
| BY geometry / validation | −0.1661 (80) | **−0.1661 (80)** |
| BY geometry / holdout | −0.2110 (200) | **−0.2110 (200)** |

**BZ is stable across two independent replays; BY is the run that cannot be
reproduced, and it cannot be reproduced because it was not stored.** That is the
argument for §26, and it is why this milestone now persists its capture.

**This is not harmless because the verdict is unchanged.** A 0.0089 R per-trade
disagreement is 4.7 % of the figure in question, it lands on the single most
knife-edge trade in the sample, and had the sealed bar been placed anywhere near
+0.19 R it would have decided a promotion. The verdict survived it by luck of
margin, not by design.

---

## 8. The observational study — what post-entry paths look like

**DESCRIPTIVE. Every figure here conditions on a whole path and may never be read
as a decision rule.**

| geometry / sample | paths | ever +1R | ever +2R | median peak R | median give-back R |
|---|---|---|---|---|---|
| production / development | 151 | 128 (84.8 %) | 115 (76.2 %) | **5.26** | **6.25** |
| production / validation | 88 | 72 (81.8 %) | 58 (65.9 %) | 4.74 | 4.21 |
| production / holdout | 225 | 188 (83.6 %) | 163 (72.4 %) | 4.93 | 5.05 |
| BY geometry / development | 136 | 116 (85.3 %) | 99 (72.8 %) | 3.70 | 4.08 |
| BY geometry / validation | 80 | 65 (81.3 %) | 52 (65.0 %) | 3.62 | 3.45 |
| BY geometry / holdout | 200 | 169 (84.5 %) | 128 (64.0 %) | 3.22 | 3.20 |

### Time, and the shape it reveals

| production / development | +0.5R | +1R | +1.5R | +2R | first −0.5R | peak |
|---|---|---|---|---|---|---|
| median bars to first arrival | **1** | **2** | 3 | 4 | **1** | **19** |

**The favourable move arrives almost immediately and the peak arrives twenty bars
later.** A position typically reaches +1R inside two 4H bars, keeps drifting to a
peak around bar 19 of a 60-bar window, and then surrenders a median of 6.25R.
The adverse half-R also arrives at bar 1 — these positions move both ways
immediately, which is why BX measured a median hold of one bar.

### Give-back — BX's finding reproduced, and a definitional warning

| | rate | BX |
|---|---|---|
| production / development | **92.1 %** (139/151) | 68.8 % |
| production / validation | 85.2 % (75/88) | — |
| production / holdout | 88.9 % (200/225) | — |

**BZ's number is not BX's number, and the difference is definitional rather than
a disagreement.** BX measured `mfe_r − net_r` on a trade that had *already
exited*. BZ's path walk **takes no exit at all** — it holds the position for the
whole 60-bar window, because a path truncated at the control's own exit cannot
answer what a different rule would have done afterwards. Peak-to-final over 60
bars is necessarily ≥ peak-to-realised-exit, so **92.1 % and 68.8 % are two
different quantities and neither refutes the other.** Both are reported.

*(BZ's median peak of 5.26R and BX's mean MFE of +5.26R coincide numerically.
They are a median and a mean of differently-bounded quantities; the coincidence
is noted so a reader does not mistake it for a reproduction.)*

### The number that decides the milestone

**Median REALISED return, conditional on the path having reached a threshold**
— the path is descriptive, the realised return is the control's actual exit:

| reached… | BY geometry / development | production / development |
|---|---|---|
| +0.5R | **−1.059** (130) | −0.099 (121) |
| +1.0R | **−1.072** (116) | −0.082 (109) |
| +1.5R | **−1.062** (106) | −0.079 (101) |
| +2.0R | **−1.051** (99) | −0.046 (98) |

**Under BY's geometry, the median trade that ran two full R in favour ended at a
full loss.** And yet that policy's expectancy is **+0.1906R** with a profit
factor of 1.25, because 44 of 136 reached a 2R target. **The median is −1R and
the mean is positive**: the return distribution is almost entirely tail. That
single fact explains every negative result in §9 — a give-back cap, a stagnation
exit and a structural trail all remove tail before they remove losers.

---

## 9. The sealed exit families — results

Deciding scenario `swing-lab-conservative-10bps`. **Read the `vs H0` column**: it
is the like-for-like improvement over each family's own control, re-measured over
the setups every family could measure.

### Under production geometry (the live rule)

| family | dev n | fired | dev E | **vs H0** | val E | **vs H0** | holdout E | **vs H0** |
|---|---|---|---|---|---|---|---|---|
| `bz_exit_control` | 132 | — | −0.5990 | — | −0.4566 | — | −0.4877 | — |
| `bz_exit_thesis_failure` | 132 | 2 | −0.6163 | −0.0173 | −0.4577 | −0.0011 | −0.4765 | +0.0113 |
| `bz_exit_stagnation_12` | 132 | 3 | −0.5857 | **+0.0134** | −0.4551 | +0.0015 | −0.4844 | +0.0033 |
| `bz_exit_giveback_half` | 132 | 10 | −0.6246 | −0.0258 | −0.4281 | +0.0285 | −0.3832 | **+0.1115** |
| `bz_exit_structural_trail` | 131 | 0 | −0.6376 | +0.0081 | −0.4011 | +0.0555 | −0.3860 | **+0.1194** |
| `bz_exit_thesis_and_giveback` | 132 | 11 | −0.6211 | −0.0222 | −0.4292 | +0.0274 | −0.3770 | **+0.1177** |

### Under BY's refuted geometry (measured, never reopened)

| family | dev n | fired | dev E | **vs H0** | val E | **vs H0** | holdout E | **vs H0** |
|---|---|---|---|---|---|---|---|---|
| `bz_exit_control` | 136 | — | +0.1906 | — | −0.1661 | — | −0.2110 | — |
| `bz_exit_thesis_failure` | 136 | 11 | +0.1598 | −0.0311 | −0.2323 | −0.0663 | −0.1876 | +0.0234 |
| `bz_exit_stagnation_12` | 136 | 5 | +0.1666 | −0.0242 | −0.1625 | +0.0036 | −0.1992 | +0.0117 |
| `bz_exit_giveback_half` | 136 | 49 | +0.1139 | −0.0772 | −0.1557 | +0.0104 | **−0.0118** | **+0.1992** |
| `bz_exit_structural_trail` | 135 | 0 | +0.0236 | **−0.1468** | −0.1469 | +0.0191 | −0.0949 | +0.1160 |
| `bz_exit_thesis_and_giveback` | 136 | 52 | +0.1200 | −0.0712 | −0.1600 | +0.0061 | **−0.0054** | **+0.2055** |

### The five things this says

1. **Not one family clears the sealed +0.10R development bar.** The best figure
   anywhere on development is +0.0134R. Ten judgements, ten `REJECTED`.

2. **The thesis exit barely fires.** Two firings on 132 production positions,
   eleven on 136 under BY's geometry. §1's table shows *why*: `INVALIDATED`
   reaches 1 position by bar 12 and 20 by bar 60, but the median position is
   resolved by its stop long before that. **Persistence is real and its decay is
   too slow to trade.**

3. **The structural trail never fires as an exit and still changes everything.**
   `fired = 0` in every cell — because a trail produces a `STOP`, not a named
   mechanism exit. On BY's geometry it is the **worst** family on development
   (−0.1468R): it ratchets the stop into a position whose whole return is tail,
   and cuts it. On the holdout it is among the best (+0.1194R). Same rule,
   opposite sign.

4. **Give-back protection is the strongest mechanism measured and it is
   sample-dependent.** +0.1992R on the holdout, −0.0772R on development. It takes
   BY's geometry on the holdout from −0.2110 to **−0.0118 — essentially flat** —
   and its holdout walk-forward improves in **all four** windows. It is also
   negative where the strategy is profitable. That is not a mechanism.

5. **The combination behaves exactly like its stronger component** and adds
   nothing: +0.2055R against give-back's +0.1992R on the holdout, and it is
   additionally barred by `components_earned_it` because neither component
   cleared `development_expectancy` on production geometry.

### Walk-forward — one curve per universe, never pooled

**Primary universe (15 symbols), BY geometry, cost-inclusive:**

| | 23H2 | 24H1 | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|---|---|
| `bz_exit_control` | **+0.2336** | **−0.0387** | **+0.3522** | +0.2265 | −0.5395 | −0.0939 |
| `bz_exit_giveback_half` | +0.0709 | −0.3312 | +0.4013 | +0.3217 | −0.3802 | −0.1474 |

**Holdout universe (21 symbols):**

| | 24H2 | 25H1 | 25H2 | 26H1 |
|---|---|---|---|---|
| `bz_exit_control` | −0.2883 | −0.3989 | −0.2500 | −0.0456 |
| `bz_exit_giveback_half` | −0.2368 | −0.0790 | −0.0733 | **+0.2046** |

The control's first three primary windows match BY to four decimals. **Both
curves break at the same development/validation boundary**, so the give-back
mechanism does not rescue the decay BY found — it rides it. On the holdout it
improves every window, which is the sample-dependence §9.4 names.

### Decomposition and concentration

| cut | BY geometry / development |
|---|---|
| largest single-symbol share of gross \|R\| | **10.2 %** — bound is 40 % |
| give-back rate, long | 91.9 % (74) |
| give-back rate, short | 90.3 % (62) |
| median bars from peak to exit | **4.0** |

The validation long cohort holds 14 trades and its rate is **refused**, not
stated — the sample floor doing its job on a real cut.

---

## 10. Ambiguity, measured

| | production dev | production holdout | BY geometry dev |
|---|---|---|---|
| control | **19** | **21** | 0 |
| thesis / stagnation / give-back / combination | **19** | **21** | 0 |
| structural trail | 20 | 23 | 1 |

**Four of the five families add exactly zero ambiguity**, which is the claim the
sealed ambiguity policy makes and this measures rather than asserts: a mechanic
decided at a bar's close adds no watched level. Only the structural trail adds
any — 1, 2 and 1 event respectively — because moving a stop can create a new
collision with the target. No result in §9 turns on those four events.

BY's counts of 19 and 21 are reproduced exactly.

---

## 13. Intrabar ambiguity — a design property, not a solved problem

§9 of the brief requires that intrabar ordering never be invented. BZ's position
is narrower and stronger than BY's, and it is a consequence of the mechanism
design rather than a claim that ambiguity was defeated:

**BZ's five mechanics are decided at an execution bar's CLOSE and filled at the
next bar's OPEN.** A close and an open are single prices, so none of these
decisions has an intrabar ordering problem at all. That is why they are evaluated
at bar boundaries and not inside `_process`: a structural verdict, a bar count and
a peak-to-close give-back are facts a bar only settles when it ends, and there is
nothing finer to descend to.

What remains ambiguous is unchanged from BY: **the stop and the target are still
watched inside the bar and can still collide there.** That case is still
`AMBIGUOUS_SAME_BAR`, still resolved by descending to 1H and then 15m, and still
**refused** when the finest rung holds both.

**A structural trail adds no watched level — it moves the existing stop.** It
therefore does not multiply ambiguity the way BY's +1R arming level did (BY §11
measured that going from 2 to 20 on development). A regression asserts that no BZ
mechanic appears in the level-arming set, and a second asserts the observable
consequence: a bar that runs through +1R to the target is a clean `TARGET` for
the give-back family, where a watched arming level would have made it a
two-level collision.

The one-bar execution convention has a cost and it is stated rather than buried:
**a decision confirmed by bar *t*'s close is filled at bar *t+1*'s open**, so a
mechanism cannot capture the move that triggered it. That is the honest
treatment — the alternative fills at a close nobody could have traded on — and it
means every BZ figure is a slightly pessimistic estimate of its own mechanism.

---

## 14. No-lookahead

Proven the same way BW, BX and BY prove it — **change the future and require the
past not to notice** — with a non-vacuity control for every claim, because a test
that passes on a harness reading nothing at all proves nothing.

| claim | control that stops it passing vacuously |
|---|---|
| a `PostEntryCheckpoint` at bar *n* is invariant to every bar after *n* | mutating a bar at or before *n* **does** move it, and specifically the checkpoint that reads it |
| the descriptive half is NOT causal | a bar after the last checkpoint **does** move `peak_r` and `bars_to_peak_r` |
| a thesis exit is blind to bars after its fill | mutating the deciding bar **does** move the fill |
| a stagnation exit is blind to bars after its fill | mutating the fill bar **does** move the fill |
| a give-back exit is blind to bars after its fill | the exit reason and price are unchanged; the deciding bar moves them |
| a structural trail cannot read a level confirmed later | **the discriminating test**: the same level confirmed one bar earlier stops the trade out and one bar later does not |
| the capture is unchanged by the observer | candidate-for-candidate and bar-for-bar equality against a capture taken without it |

The **structural** half of the proof is stronger than the mutational half, and it
is the same argument BX and BY rest on: a `ThesisObservation` holds enum values,
a close and level references **and no bar of any resolution**, so a rule handed
one cannot read forward — not by discipline but by what exists. Architecture
guards assert that no geometry-policy module imports `persistence`,
`persistence_replay`, `persistence_study` or `exits`, and that none names
`peak_r`, `giveback`, `ThesisState`, `PersistenceTrack`, `PostEntryCheckpoint` or
`thesis_state`.

The pre-registration is asserted to import no `PriceBar`, no `LabTrade`, no
`GeometryCapture` and no `PersistenceTrack`, so a BZ threshold cannot be derived
from a measurement even by accident.

---

## 15. Hostile review

**33 probes, 0 failures.** Each attack tries to make BZ state something it is not
entitled to state.

| attack | outcome |
|---|---|
| zero paths states a rate | refused — `full_r_giveback_rate` is `None` |
| one trade states an expectancy | refused — below the 20-trade floor |
| a cohort exactly **at** the floor | stated; **one below** refused — boundary asserted both ways |
| a data gap reads as thesis failure | refused — `UNAVAILABLE` is not adverse, position not closed |
| a warming-up view invents an ordering reference | refused — both level sides report EMPTY |
| a structural trail with no structure falls back to a price | refused — moves nothing |
| an ambiguous bar is guessed | refused — `AMBIGUOUS_SAME_BAR`, excluded from expectancy, counted beside it |
| a close-decided mechanic multiplies ambiguity | measured: it does not (§10) |
| a zero-risk geometry is measured | refused — "no risk denominator" |
| an entry gapping through its stop is skipped | refused — recorded as −1R, never dropped |
| costs overwhelm a tiny-risk trade | reported, not clipped — >10R drag measured |
| a huge decimal loses precision | exact — 10-digit instrument divides cleanly |
| a policy nobody sealed is promoted | refused — first criterion is membership + digest |
| a neighbourhood point is promoted | refused — `is_bz_pre_registered` is `False` for all |
| a tampered seal still promotes | refused — `pre_registered` fails, digest mismatch reported |
| a verdict approves trading | **no member does**, asserted over the whole enum |
| `MECHANISM_EVIDENCE` earns a forward test | it does not — asserted |
| a comparison mixes samples | refused by name (BY defect BY-D6, one layer lower) |
| a duplicated observation overwrites silently | refused loudly |
| one symbol dominates | measured — 10.2 % against a 40 % bound |
| one period dominates | empty walk-forward windows still emitted |
| a future timestamp is special | it is not — no clock is read |
| `PYTHONHASHSEED` reaches a digest | it does not — 0 / 1 / 12345 all agree |

---

## 16. Mutation testing

**47 probes · 47 killed · 0 survivors · 0 broken anchors.** Restoration verified
byte-exact by SHA-256 after every probe; `git checkout --` was never used
because it would also discard this milestone's uncommitted work.
`__pycache__` was cleared before every run.

Probed invariants: the seal · a threshold moved after freeze · a dropped
neighbour · the digest sorting its hypotheses · a hypothesis with no refutation ·
the holdout criterion deleted · decision timing · the next-bar fill · the
future-data boundary · a checkpoint reading one bar ahead · MFE/MAE direction ·
give-back arithmetic · absolute-vs-fractional give-back · the arming threshold ·
stagnation off-by-one · stagnation from close rather than peak · thesis-state
precedence · weakening made actionable · a missing instant read as intact ·
structure confirmation · a loosening trail · a trail on the wrong side · a trail
falling back to a price · LONG/SHORT sign · exit reason · the firing tally ·
sample identity · the comparable column's intersection · sample filtering ·
candidate classification · post-hoc promotion · a thin cohort stating a rate · a
quantile interpolating · BY's arming set · a BZ parameter leaking into BY's
sealed payload · a duplicated instant · the level cap.

**The first run killed 35 of 45.** Every survivor was investigated and none was
deleted. They fell into three groups, and the second group is why mutation
testing was worth running:

| survivor | what it was | resolution |
|---|---|---|
| 3 probes | the probe did not run the file holding its regression — a **scoping** failure, not a scientific one | `T_EXIT_STUDY` added; a probe now runs the suite that covers it |
| 1 probe | written as a **no-op** (`return ()` → `return ()  # noqa`) — equivalent by construction, which is a badly-written probe rather than a finding | rewritten to substitute an ordering reference the view did not have; then killed by a direct unit test |
| **`exits:trail-loosens-the-stop`** | **a test passing for the wrong reason** — `test_it_never_loosens` used a path whose stop was hit on the very bar that offered the loosening level, so the trade ended before the rule was consulted | path rebuilt so the level is actually reached; the mutant now raises from `_State.tighten` |
| 5 probes | genuine gaps in `persistence_study.py`, which had no dedicated suite | `test_swing_lab_persistence_study.py` written — 36 tests, each verified individually to kill its mutant |

### Defect BZ-D1 — found by a regression written to close a mutant

`assess_bz` reported a below-floor or never-run sample as a **failed** criterion,
so a development-only pass came out `REJECTED`. BZ's own sealed classification
rules say the opposite in as many words: fewer than `SAMPLE_FLOOR` measurable
trades means *"the test could not be run, which is NOT a pass"* — `INCONCLUSIVE`.
Reporting it as `REJECTED` claims evidence against a hypothesis nobody measured.
Fixed; the `sample` criterion now returns `True` or **unmeasurable**, never
`False`, and a probe (`study:the-sample-criterion-rejects-instead-of-refusing`)
guards it.

**This did not change BZ's verdict**, because every family fails
`improves_development` independently — but it would have made a development-only
run report five refutations that had not been earned.

---

## 17. Verification

| gate | result |
|---|---|
| **Full repository under `-W error`** | **11,997 passing**, 0 failures (from 11,726 at BY) |
| Focused BZ suite | **226 tests** across 7 new files |
| **Mutation probes** | **47 run · 47 killed · 0 survivors** |
| **Hostile review** | **33 probes, 0 failures** |
| **Control equivalence** | **4,000 randomised paths, 0 mismatches** against `simulate_trade` |
| **BX/BY capture reproduced** | 104,130 measured instants — **exact** |
| **BY production control reproduced** | −0.5990 (132), ambiguity 19 — **exact** |
| BY's pinned seal `a81b6ab8…` | **byte-identical** after BZ grew `exits.py` |
| Determinism | BZ digest stable across `PYTHONHASHSEED` 0 / 1 / 12345 |
| Architecture guards | **283 passing**, 6 new BZ-specific |
| New runtime dependencies | **0** |
| ADRs required | **0** |
| Guards weakened | **0** — and **0 widened** |

### Coverage

Statement **and** branch, over BZ's scope:

| module | cover | notable misses |
|---|---|---|
| `persistence_replay.py` | **100 %** | — |
| `persistence_render.py` | **97 %** | 41, 150 — two formatting guards |
| `persistence.py` | **94 %** | 212–216, 266, 284, 458, 520, 526 — type guards |
| `persistence_preregistration.py` | **94 %** | 199, 201, 358, 617 — type guards |
| `exits.py` | 92 % | argument type guards; 725→723, 1036→1038 defensive branches |
| `persistence_study.py` | 76 % | **1136–1315 — `run_persistence_experiment`** |
| **total** | **88 %** | |

**Not 100 %, and the misses are named.** The one large block is the
fetch-and-replay entry point, which needs a live provider — exactly the exclusion
BX recorded for `run_geometry_experiment` and BY for its own, and for the same
reason. Everything before the network is covered. The rest are `isinstance`
guards and defensive branches offline fixtures cannot reach. **No coverage
exclusion was added anywhere.**

Two blocks that were uncovered on the first measurement were **closed rather than
excused**: `observe_all_paths` (its only other exercise was the 77-minute network
run) and the renderer's `CANDIDATE` / `MECHANISM_EVIDENCE` headlines (written but
never rendered by a test). Coverage rose from 85 % to 88 %.

---

## 18. Guards widened

**None.** BZ added no artifact module, so the filesystem exemption list is
unchanged at three. **Two guards fired during development and were obeyed rather
than widened:**

* `test_only_the_artifact_module_touches_the_filesystem` rejected
  `persistence.py` because the type name `PersistencePath(` contains the
  substring `Path(`. The guard is a deliberately blunt substring probe and
  tightening it would weaken it for every other module, so **the type was renamed
  to `PersistenceTrack`** instead.
* `test_no_module_defines_its_own_gap_or_touch_rule` rejected a property named
  `reached`, which collides with `PriceBar.reached` — the exact collision the
  guard exists to catch. Renamed to `excursions_reached`.

**Six guards were added**, all asserting absences: no geometry-policy module may
import the persistence layer or name a persistence measurement; the persistence
layer may not import a geometry policy; the BZ pre-registration may not import a
measurement; BY's four sealed exit policies are pinned by id; BY's digest is
asserted to survive every BZ change.

---

## 19. Surfaces

### `fmits research persistence`

```
fmits research persistence --open-holdout
```

**It takes no universe, no window and no threshold**, and it refuses them by
name rather than accepting and ignoring them — every one is part of what was
sealed. `--open-holdout` is off by default; without it the holdout replay is not
fetched, every holdout criterion reports as unevaluable, and no family can reach
candidate status.

The renderer computes nothing. It prints the verdict first, then the seal and the
deciding cost scenario, then the **descriptive** half and the **causal** half
under separate headings, then the sealed families with the like-for-like column
marked and an instruction to read it, then the limitations. A test asserts the
renderer holds no threshold, no `SAMPLE_FLOOR` and no `Decimal` — presentation
must stay replaceable, so it may own no rule.

**No dashboard page was added.** §17 of the brief permits extending `/lab` only
if it stays a thin presentation of the artifact; BZ writes no artifact, so there
was nothing thin to present. This is recorded as **not done** rather than
half-done — see §22.

---

## 20. Production safety

**BZ altered no production decision, and the claim is checked rather than made.**

* `swing_setup`, `paper`, `trade_lifecycle`, `positions`, `portfolio`,
  `position_sizing` and `journal` are **untouched** — they do not appear in the
  changed-file list at all.
* Architecture guards assert no `swing_lab` module names an execution verb
  (`place_order`, `submit_order`, `cancel_order`, `execute_trade`), mentions
  EVEDEX, calls an AI model, or touches the filesystem outside the three artifact
  modules. **BZ added no artifact module**, so the exemption list did not grow.
* `BzVerdict.is_approved_for_trading` is `False` for every member, asserted over
  the whole enum.
* No order was placed, no exchange API was contacted, no credential was read and
  no withdrawal permission exists anywhere in this repository.

The two production files BZ touched are `pipeline/cli.py` (one new `research`
choice) and `swing_lab/geometry_replay.py` + `swing_lab/validation_study.py` (one
optional argument, threaded). None changes a trading rule.

---

## 21. Decision

**B. NO_CANDIDATE.**

All five sealed families are `REJECTED` on both geometries. Every one fails
`improves_development` — a **+0.10R** like-for-like gain over its own control,
written down before anything was measured. The best figure anywhere was
**+0.0134R**, an order of magnitude short.

They did **not** fail for want of data (132–225 measurable trades per cell,
floor is 20), for concentration (10.2 % against a 40 % bound), for ambiguity
(four of five families added none), or for costs. They failed because
**the mechanisms do not do enough, and what they do is sample-dependent in
sign.**

**Stated no more strongly than the evidence allows.** Three samples and six
half-year windows cannot establish *why* every mechanism helps the holdout and
hurts development. Liquidity, regime, the holdout's later window and chance are
all consistent with what was measured, and this milestone distinguishes none of
them. What it establishes is narrower and sufficient: **no sealed exit mechanism
improved its own control by the pre-declared margin on the sample it was
developed on, and none held its sign across samples.**

**Nothing is proposed for shadow, paper or forward testing. Production remains
the current policy.**

### POST_HOC — recorded, not promoted

Two observations arrived after the results and are **not** eligible for any
verdict in this milestone. They are written here so a future milestone can
pre-register them rather than rediscover them:

1. **Give-back protection took BY's geometry on the holdout to −0.0118R** — from
   −0.2110 — and improved all four holdout windows. On a universe where the
   strategy is losing, capping give-back recovers nearly all of the loss.
2. **The return distribution is almost entirely tail.** Median realised return
   conditional on reaching +2R is −1.05R while the mean is +0.19R. Any rule that
   truncates the upside is fighting the only thing that makes this policy
   positive. A future study of *position sizing* rather than *exit timing* would
   be testing something new.

---

## 22. Limitations

`BZ_LIMITATIONS` (BZ-1 … BZ-6) travels inside the study and prints on every
report, with BY's, BX's and BW's beneath it unchanged.

- **BZ-1** — the evaluation window is **60 execution bars (10 calendar days)**,
  inherited unchanged from BW so BZ stays comparable with BW, BX and BY. Every
  statement about trade age, stagnation and time-to-peak is bounded by it. A
  longer window would give different answers to all three, and **for a strategy
  described as "swing" this bound is the most questionable inherited assumption
  in the whole series.**
- **BZ-2** — the thesis vocabulary is the production engines' output, so BZ
  inherits every limitation of `structural_trend`, `market_regime` and
  `decision_context`. A thesis rule can be no more sensitive than the structure
  detection underneath it.
- **BZ-3** — the timeline is sampled at execution-bar closes only, so a trail can
  never be tighter than 4H resolution.
- **BZ-4** — an observation carries the nearest five levels per side; a trail
  wanting a sixth is not measured.
- **BZ-5** — samples, symbols and windows are BY's, so BY-2 … BY-5 apply
  unchanged: development is contaminated by construction, the holdout window
  opens later, the holdout symbols are materially less liquid, and the universe
  is survivorship-filtered.
- **BZ-6** — production geometry loses ~0.5R per trade on every sample measured.
  A family measured over it is being asked to improve a losing strategy.

Additionally, and not in the sealed list because it was discovered during the
run: **BZ-D2**, the one-trade discrepancy in §7 — now reconciled mechanically,
with its root cause classified **UNRESOLVED_PROVENANCE**.

**BZ now persists its capture** (§26), so this limitation no longer applies to BZ
itself: this run *is* diffable against the next.

### What the brief asked for and BZ did not deliver

Stated plainly rather than omitted:

* **No dashboard page.** §17 permits extending `/lab` only as a thin presentation
  of a research artifact. BZ writes no artifact, so there was nothing to present
  thinly. The CLI is the surface.
* **No artifact writer** — *resolved by the completion pass of 2026-08-27.* §26
  records what was added and what it now guarantees.
* **The robustness neighbourhood was sealed but not measured.**
  `STAGNATION_NEIGHBOURHOOD` and `GIVEBACK_NEIGHBOURHOOD` are in the digest and
  the `robust` criterion is therefore reported as **unmeasurable**, not as
  passed. It changes no verdict — every family already fails
  `improves_development`, which is checked first — but the plateau question is
  **open**, and a report that let a sealed criterion quietly evaporate would be
  doing what this milestone exists to prevent.
* **1H entry refinement after entry was not re-measured.** BY §9 measured it and
  BZ adds nothing; §12's answer relies on BY's figures rather than new ones.

---

## 23. The twelve questions §22 of the brief asks

| # | question | answer |
|---|---|---|
| 1 | Does thesis persistence exist? | **Yes.** INTACT falls from 149/151 at bar 1 to 41/151 at bar 60, monotonically. |
| 2 | Is it measurable causally? | **Yes.** Every reading is confirmed by its own bar; proven by future-mutation with non-vacuity controls. |
| 3 | Which observable state transitions matter? | **INVALIDATED and CONFLICTED**, and they arrive too late — 1 position by bar 12, 46 by bar 60. WEAKENED is excluded by design: it fires on nearly everything. |
| 4 | Does exit management improve expectancy? | **Not by the pre-declared margin.** Best development improvement +0.0134R against a +0.10R bar. |
| 5 | Does it improve validation? | Marginally and inconsistently: +0.0555R at best, negative for the thesis exit. |
| 6 | Does it improve holdout? | **Yes, materially** — up to +0.2055R. And it is the only sample where it does. |
| 7 | Is any improvement robust? | **No.** Every mechanism flips sign between development and holdout. The neighbourhood test was sealed but not run (§22). |
| 8 | Does 1W add lifecycle information? | It is the context role; leaving `TRENDING` is one of two WEAKENED triggers, and WEAKENED fires no exit. **No measured lifecycle contribution.** |
| 9 | Does 1D add lifecycle information? | **Yes — it is the only timeframe that does.** INVALIDATED and CONFLICTED are both 1D-derived, and they are the only actionable states. |
| 10 | Does 4H add lifecycle information? | **Yes, as the disagreement partner** — CONFLICTED needs 4H to disagree with 1D, and it reaches 33 of 151 positions by bar 36. |
| 11 | Does 1H refinement help after entry? | **Not measured by BZ.** BY §9 measured it before entry: it improves production geometry and not BY's, while declining half the setups. |
| 12 | Does anything deserve shadow/paper testing? | **No.** |

---

## 24. Changed files

**New (`src/fmis/swing_lab/`):** `persistence.py`, `persistence_replay.py`,
`persistence_preregistration.py`, `persistence_study.py`, `persistence_render.py`,
`persistence_artifact.py` *(completion pass)*

**Modified (`src/`):**
- `swing_lab/exits.py` — five BZ mechanics, `BZ_EXIT_POLICIES`,
  `COMBINATION_COMPONENTS`, close-decided evaluation, optional `timeline`
- `swing_lab/models.py` — `THESIS_INVALIDATED`, `STAGNATION`, `GIVEBACK`
- `swing_lab/geometry_replay.py` — the optional `observer` sink
- `swing_lab/validation_study.py` — `observer` threaded through `capture_for_window`
- `swing_lab/persistence_study.py` — `study_from_captures` extracted so a live
  replay and a persisted capture share one measurement path *(completion pass)*
- `pipeline/cli.py` — `fmits research persistence`, `--save-capture`,
  `--from-capture`

**New (`tests/`):** `test_swing_lab_persistence.py`,
`test_swing_lab_persistence_exits.py`,
`test_swing_lab_persistence_preregistration.py`,
`test_swing_lab_persistence_replay.py`, `test_swing_lab_persistence_study.py`,
`test_swing_lab_persistence_surface.py`, `test_swing_lab_persistence_hostile.py`,
`test_swing_lab_persistence_artifact.py` *(completion pass)*

**Modified (`tests/`):** `test_swing_lab_architecture.py` (module roster, 6 new
guards)

**Documentation:** this report; `reports/README.md`;
`docs/AI_HANDOFF/CURRENT_STATE.md`; `FMITS_PRODUCT_BACKLOG.md`.

`FMITS_PRODUCT_CHANGELOG.md` is **not** updated: BZ delivers a research
capability whose headline result is that every sealed mechanism failed.
Recording that as a user-visible capability release would misrepresent it.

---

## 25. Recommended next scientific question — do not begin it

**Stop testing exits on this admission rule.**

Four milestones have now measured this strategy: BW rejected the timeframe
variants, BX rejected thirteen geometries, BY rejected six points of one
geometry, BZ rejected five exit mechanisms. The consistent, reproduced finding
across all four is not about geometry or exits at all:

> **92.1 % of positions surrender a full R of open profit, the median position
> that reaches +2R ends at a full loss, and the expectancy is positive only
> because of a thin tail of trades that reach target.**

Two questions follow, and the first is cheaper:

1. **Position sizing, not exit timing.** If the return distribution is almost
   entirely tail, then *how much* is risked on each trade may matter more than
   *when* it is closed — and every milestone so far has held size fixed at 1R.
   This is measurable with the existing captures and is a genuinely new lever.
2. **Admission, measured against a null.** No milestone has yet asked whether
   this admission rule selects better than a random entry of the same frequency
   and geometry on the same symbols. That is the control BW, BX, BY and BZ have
   all been missing, and until it exists, "the geometry is wrong" and "there is
   no edge to shape" cannot be told apart.

**Persisting the capture is done** — see §26. BZ could not close its one-trade
discrepancy against BY because BY stored nothing; BZ now stores everything, so
the next milestone's equivalent of BZ-D2 will be a diff rather than an inference.

---

## 23. Commit boundary

**Nothing was committed and nothing was pushed.**

Two commits are **prepared but not created**:

```
Commit A   feat(research): add swing thesis persistence laboratory
           src/ and tests/ only

Commit B   docs(product): record swing persistence research milestone
           documentation only
```

`HEAD` remains `fd1270b`, `origin/main` remains `fd1270b`, 0 ahead / 0 behind.
The 16 pre-existing untracked research documents under `docs/design/` and
`docs/reviews/` are untouched.


---

## 26. Reproducibility — the completion pass of 2026-08-27

Report 0036 was written, and BZ was **not** released, because the experiment was
not reproducible enough: §7's discrepancy could not be closed, and the reason was
that no milestone in this series had ever persisted its *inputs*. This section
records the narrow pass that fixed that. **No trading rule, threshold, geometry,
exit hypothesis, sample definition, cost scenario, sealed hypothesis or
production behaviour was changed by it, and no scientific result moved.**

### MEASURED RESULT — unchanged

Re-measured from the persisted capture, offline:

| | |
|---|---|
| pre-registration seal | `4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175` ✔ |
| BY's seal | `a81b6ab8…` byte-identical ✔ |
| production control, development | **−0.5990** (132, ambiguity 19) ✔ |
| all ten BZ judgements | **REJECTED** ✔ |
| candidates | **0** ✔ |
| verdict | **NO_CANDIDATE** ✔ |
| persistence tables, give-back, exit families | reproduce exactly ✔ |

### REPRODUCIBILITY — what now exists

`src/fmis/swing_lab/persistence_artifact.py` persists a **capture**, not a
result — the first artifact in this repository to do so.

```
schema_version   1
kind             bz-persistence-capture
content_digest   fcd0991b3646608b5a79decd91e15f74631a03f4933ddc5b908ddf4250df07ac
file             bz_capture.json.gz   13.4 MB
primary          15 symbols · 246 candidates · 105,030 observations
holdout          21 symbols · 234 candidates · 100,926 observations
```

**Provenance fields on the manifest:** `preregistration_id`,
`preregistration_digest`, `captured_at`, `evaluation_window_bars`,
`candle_limit`, `deciding_cost_policy_id`, `cost_scenarios`, `samples` (symbols,
window boundaries and contamination text), `geometry_policy_ids`, `provider`
(transport, base URL, and an explicit note that source data is mutable),
`writer`, and `content_digest`.

**Per universe:** `admission_variant_id`, `admission_policy_id`,
`execution_interval`, `symbols`, capture `metadata`, every **bar**, every
**candidate** (identity, decision timestamp, bar index, reference price, all four
ordered level lists with provenance, both ATRs, regime and trend), and the whole
**structural timeline** — one observation per analysable bar per symbol.

**The offline reproduction is exact.** A study measured from the decoded file
equals a study measured from the live capture **payload for payload**, and the
regression asserting it runs with `fetch_raw_klines` monkeypatched to raise, so
"no network" is proven by making a fetch fatal rather than by asserting it.

**It fails closed, never open.** A foreign schema version, a study artifact
handed in by mistake, a missing manifest field, an edited bar, an edited
observation, an edited manifest, a swapped digest, a truncated gzip, a candidate
whose symbol has no bars, a candidate past the end of its series, a candidate
whose bar index and timestamp disagree, an observation past the end, a timeline
for an unknown symbol — each is refused **by name**, and none is completed from
the provider.

**Two defects were found in the new code by its own mutation probes**, and both
would have quietly broken a reproducibility claim:

* **`GzipFile` embeds `fileobj.name` in the header.** The same capture written to
  two paths produced two different files. Fixed with `filename=""` alongside
  `mtime=0`. The digest was never affected — it is taken over canonical JSON —
  but the *file* reproducibility claim would have been false.
* **`Decimal` decoding through `float` was invisible to every test**, because the
  fixture's ten-digit prices survive a float round-trip by luck. A real
  eighteen-digit instrument price does not. Closed with a probe whose
  non-vacuity is itself asserted.

**`fmits research persistence --from-capture PATH`** re-measures offline and
prints the seal in the file beside the seal in the build, **reporting a mismatch
rather than resolving it** — a capture can be perfectly intact and still describe
a different experiment, and merging those two failures would report a foreign
experiment as a corrupt file.

**No dashboard feature was added.** §8 of the completion brief permits one only
if the artifact plugs into an existing research-artifact seam; the dashboard's
seam takes *study* artifacts, and this is a *capture*. Recorded as not done.

### KNOWN LIMITATIONS of the artifact

- **It fixes inputs, not correctness.** A capture makes a result reproducible; it
  does not make it right. Every limitation BZ-1 … BZ-6 stands unchanged.
- **13.4 MB per run, and it grows with the universe.** No pruning is applied and
  none is recommended: a capture that dropped "unused" bars would stop being able
  to answer the next question asked of it, which is exactly how BY ended up
  unable to answer this one.
- **Only the execution timeframe's bars are persisted.** The 1D and 1W series that
  *produced* the structural readings are not stored — the readings themselves
  are. A future question about *why* a pivot was detected still cannot be
  answered offline, and BZ-D2's root cause is precisely such a question.
  **This is the artifact's most important limitation and it is the direct reason
  BZ-D2 remains unresolved even now.**
- The capture is written by the milestone's runner rather than by
  `fmits research persistence`, which declines `--save-capture` rather than
  writing a partial artifact.

### UNRESOLVED PROVENANCE

**BZ-D2 is reconciled mechanically and its root cause is not recoverable.**

One trade — `BNBUSDT|long|from=2024-12-23`, sitting **0.0612 R** below its target
and **0.0225 R** above its stop for all sixty bars of its window — accounts for
the entire +0.1906 vs +0.1995 difference: 1.2113 R against an observed gap of
1.2086 R, a residual of 0.0027 R that is **inside BY's own four-decimal quoted
precision**.

**Ruled out:** a BZ defect, a capture-boundary difference, and a `TIME_STOP`
semantics difference. **Identified:** the mechanism — knife-edge level selection,
where any sub-percent change in the selected 1D target, or in the stop that sets
the 2R threshold, flips the trade between `TIME_STOP` (+1.17 R) and `TARGET`
(+2.38 R). **Not recoverable:** whether BY's target level differed because of a
provider revision or because of a BY defect.

**The missing evidence, named exactly:** Milestone BY's `GeometryCapture` for the
primary universe — the 1D `setup_target_levels` and 4H `execution_stop_levels`
for `BNBUSDT` at bar 3747, and the resulting `GeometryPlan`. Nothing else would
settle it; nothing else is missing.

**BZ is stable across two independent replays a day apart** — every control
figure identical to four decimals on all six geometry/sample cells. The run that
cannot be reproduced is BY's, and it cannot be reproduced because it was not
stored.

**No BZ number was altered to agree with BY.** The measured figure is +0.1906 and
it stays +0.1906.
