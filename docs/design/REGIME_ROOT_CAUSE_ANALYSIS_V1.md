# Market Regime — `RegimeInputError` root cause analysis v1

**Type:** Investigation — root cause analysis
**Status:** Investigation complete. No code changed, no fix applied.
**Date:** 2026-08-07
**Repository state:** branch `main`, `HEAD = 2a9bdcc`, working tree clean apart from five untracked
AP/AQ documents that this analysis does not touch.
**Subject:** `fmis.pipeline.regime.regime_input_from_sheet` → `fmis.market_regime.models.RegimeInput`
**Contracts touched by the finding:** [ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md) §6,
[ADR-0021](../adr/ADR-0021-change-of-character-foundation-v1.md),
[ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md)

> **Scope discipline.** This document investigates only. It contains no production code, no fix, no
> ADR, no backlog edit and no commit. Everything below is evidence gathered by reading the repository
> and by running it against real and cached market data. Every number is reproducible from the
> harnesses described in §2.4.

---

## 1. Executive summary

`fmis.pipeline.regime` supplies the regime engine with **the index of the last confirmed swing point**
in a field the engine validates and interprets as **the index of the last closed candle**. The two are
different positions in the same sequence, and they are never equal.

That single reference-frame mismatch produces two distinct defects:

| | Defect | Symptom | Measured frequency |
|---|---|---|---|
| **D-1** | The invariant `latest_change_index <= last_index` compares a change-of-character bar against the last *swing* rather than the last *candle* | `RegimeInputError`, command aborts | **16.1 %** of 23,627 historical states, per timeframe view |
| **D-2** | `bars_since = last_index - latest_change_index` measures the age of a change of character from the last *swing* rather than from *now* | Silent — age understated, `TRANSITIONING` over-reported | **0 %** of 15,156 successful classifications compute the age correctly; **16.3 %** get the wrong structure state |

**D-1 is the reported bug. D-2 is the same root cause with the crash removed, and it is worse**, because
it produces a confident wrong answer instead of an error. Any fix that addresses only D-1 converts
16 % of invocations from a loud failure into a silent one.

**What the owner experiences.** `fmits regime --multi`, `fmits swing`, `fmits setup` and `fmits daily`
each build three timeframe views and classify all three; one view raising aborts the whole command.
Across 1,800 simulated invocations reconstructed from cached history:

```
ABORTS with RegimeInputError                      731   40.61 %
completes but a view's structure state is wrong   431   23.94 %
correct                                           638   35.44 %
```

**Just under two thirds of three-view invocations are wrong or dead.** `fmits daily` is the worst
affected: `RegimeInputError` is deliberately absent from `_FAILURE_KINDS`, so one bad symbol aborts the
entire watchlist and discards the symbols that already succeeded — verified live (§2.2).

**The guard has never once fired for the reason it states.** Across 18,090 historical states, the
condition its message actually describes — a change of character after the last closed candle — occurred
**zero times**. Every firing of this guard, in the entire measured history of thirty symbols, is a false
positive.

**Not a regression.** The defect entered with Milestone AI (Market Regime Engine v1) and is present
unchanged in AR. It was independently reproduced against the pre-AR tree, as
[`CURRENT_STATE.md`](../AI_HANDOFF/CURRENT_STATE.md) already records.

**The repository already contains the correct pattern.** `fmis.swing_setup` — written in AR, four
milestones later — carries `execution_closed_count` and computes break age as
`execution_closed_count - 1 - break.index`, anchored to the candle count rather than to a swing. The
recommended fix (**Option B**, §7) is to adopt that existing pattern in `RegimeInput` rather than to
invent a new one.

**Recommended fix:** replace `RegimeInput.last_index` with `RegimeInput.closed_count`. It fixes D-1 and
D-2 with one change, keeps the "no arithmetic in `fmis.pipeline`" guarantee intact, matches the
repository's own newer precedent, and touches 11 test references.

---

## 2. Reproduction

### 2.1 The originally reported failure

```
$ fmits regime --multi ADAUSDT
fmits: RegimeInputError: latest_change_index (494) cannot exceed last_index (489);
       a change of character cannot occur after the last closed candle
$ echo $?
1
```

Note immediately that **`fmits regime ADAUSDT` (single view, 4h) succeeds** on the same data at the same
moment. The failure is per timeframe view and depends on where each view's last confirmed swing sits.

### 2.2 The full live surface

Sixteen liquid symbols, three commands, live Binance data, 2026-08-07:

| Command | Result |
|---|---|
| `fmits regime SYMBOL` (4h only) | 16 / 16 ok |
| `fmits regime --multi SYMBOL` | 14 ok, **ADAUSDT and NEARUSDT abort** |
| `fmits setup SYMBOL` | 14 ok, **ADAUSDT and NEARUSDT abort** |

Which view aborts, and why:

```
--- ADAUSDT
  context   1w  closed= 433  last_candle_idx= 432  last_swing=428  change=424  -> ok
  setup     1d  closed= 499  last_candle_idx= 498  last_swing=489  change=494  -> FAIL
  execution 4h  closed= 499  last_candle_idx= 498  last_swing=494  change=493  -> ok
--- NEARUSDT
  context   1w  closed= 303  last_candle_idx= 302  last_swing=298  change=302  -> FAIL
  setup     1d  closed= 499  last_candle_idx= 498  last_swing=496  change=483  -> ok
  execution 4h  closed= 499  last_candle_idx= 498  last_swing=491  change=484  -> ok
```

**Read the ADAUSDT 1d row carefully.** The change of character is at bar 494. The last closed candle is
at 498. The change is comfortably *inside* the series — the invariant's stated meaning is satisfied with
four bars to spare. It is rejected only because the last confirmed *swing* is at 489.

**Read the ADAUSDT 4h row too.** It does not crash, and it is still wrong: the engine computes
`494 - 493 = 1` and reports *"change of character 1 bars ago"*. The true age is `498 - 493 = 5`. That is
D-2, visible in shipped output on a command that exits 0.

The blast radius on `fmits daily`:

```
$ fmits daily BTCUSDT ADAUSDT ETHUSDT
fmits: RegimeInputError: latest_change_index (494) cannot exceed last_index (489); ...
$ echo $?
1
```

BTCUSDT had already been analysed successfully. Its result is discarded. `_FAILURE_KINDS` in
`src/fmis/daily/runner.py:73` lists only provider, ingest and insufficient-data errors as expected;
everything else propagates, on the stated principle *"a defect must stay a defect"*. That principle is
correct — this **is** a defect — but it means the daily run has no partial-result path for it.

### 2.3 Deterministic, network-free reproduction

Live reproduction depends on what the market did today. This one does not: cached ADAUSDT 1d klines are
served through the provider's own injected `transport` and `clock`, so it reproduces byte-identically
forever.

```
reproducing: regime_for_symbol('ADAUSDT', '1d') over 500 cached klines
last candle opens 2026-08-07T00:00:00+00:00

Traceback (most recent call last):
  File "repro.py", line 41, in main
    regime_for_symbol(SYMBOL, INTERVAL, transport=transport, clock=clock)
  File "src/fmis/pipeline/regime.py", line 225, in regime_for_symbol
    return sheet, regime_for_sheet(sheet, policy=policy)
  File "src/fmis/pipeline/regime.py", line 195, in regime_for_sheet
    return classify_regime(regime_input_from_sheet(sheet), policy)
  File "src/fmis/pipeline/regime.py", line 174, in regime_input_from_sheet
    return RegimeInput(
  File "<string>", line 16, in __init__
  File "src/fmis/market_regime/models.py", line 446, in __post_init__
    raise RegimeInputError(
fmis.market_regime.models.RegimeInputError: latest_change_index (494) cannot exceed
last_index (489); a change of character cannot occur after the last closed candle
```

### 2.4 Execution path, failing symbol, failing invariant

**Execution path.**

```
fmits regime --multi ADAUSDT                          cli.py:281
  multi_timeframe_regime_for_symbol                   pipeline/regime.py:270
    multi_timeframe_facts_for_symbol                  → 1w / 1d / 4h fact sheets
    regime_for_sheet(view.sheet)          per view    pipeline/regime.py:302
      regime_input_from_sheet(sheet)                  pipeline/regime.py:157
        last_index          = swings[-1].index        pipeline/regime.py:179  ◄── the defect
        latest_change_index = latest_change.index     pipeline/regime.py:180
      RegimeInput.__post_init__                       market_regime/models.py:441 ◄── raises
```

**Failing symbol.** `regime_input_from_sheet`, `src/fmis/pipeline/regime.py:179`.

**Failing input.** `last_index=489` (ADAUSDT 1d), `latest_change_index=494`, over 499 closed candles.

**Failing invariant**, `src/fmis/market_regime/models.py:441-450`:

```python
if (
    self.latest_change_index is not None
    and self.last_index is not None
    and self.latest_change_index > self.last_index
):
    raise RegimeInputError(
        f"latest_change_index ({self.latest_change_index}) cannot exceed "
        f"last_index ({self.last_index}); a change of character cannot "
        "occur after the last closed candle"
    )
```

**Reproduction harnesses**, all in the session scratchpad, all reading a fixed cache of raw klines so
every number in this document re-derives identically:

| Harness | What it does |
|---|---|
| `fetch_cache.py` | caches 1,000 raw klines × 30 symbols × {1w, 1d, 4h, 1h} |
| `repro.py` | the deterministic offline reproduction in §2.3 |
| `sweep.py` | walk-forward: replays each series prefix by prefix, records both indices and whether construction raises |
| `multiview.py` | reconstructs all three role views at a common instant — the per-command rate |
| `seed_sweep.py` | runs the repository's own test fixture generator over a wider seed range |
| `analyse.py` | aggregates the sweep into the tables in §5 and §6 |

---

## 3. Root cause

### 3.1 Walking backwards

**Why does `RegimeInput.__post_init__` reject valid data?**
Because it compares `latest_change_index` against `last_index`, and on this input 494 > 489.

**Why is 494 > 489 not a real problem?**
Because they are positions measured against different things. 494 is a *candle* index. 489 is a *swing*
index. Both are offsets into the same closed-candle sequence, but one is the endpoint of that sequence
and the other is the last position that satisfied a pivot test. Comparing them tests nothing.

**Why does the adapter supply a swing index?**
`src/fmis/pipeline/regime.py:179` reads `swings[-1].index`. That is the newest *confirmed swing point*.
The field it fills is named `last_index` — a name that says "the last index" without saying *the last
index of what*.

**Why does the engine believe it is a candle index?**
Because its own error message says so: *"a change of character cannot occur after the last closed
candle."* The validator author was checking the candle-sequence bound. The field docstring
(`models.py:379-382`) says the two fields are *"positions in the closed-candle sequence, matching
`SwingPoint.index`"* — a sentence that names both referents in one breath and distinguishes neither.

**Why can the two positions differ at all?**
Two independent, correct mechanisms in the layers below:

1. **The confirmation delay.** `detect_swings` iterates `range(left, len(candles) - right)`
   (`swings.py:150`), so the newest possible swing index is `n - 1 - right_bars`. The newest
   `right_bars` candles can never carry a swing. This is deliberate and is the subject of ADR-0024 —
   a pivot at bar `o` is knowable only once `right_bars` further candles have closed.
2. **Pivot sparsity.** A swing requires a local extremum. A market that runs in one direction produces
   no pivot for many bars. The last confirmed swing is therefore *at most* `n - 1 - right_bars` and
   routinely much older.

Meanwhile a change of character is a break bar. `derive_level_crossings` enumerates every closed candle
(`crossing.py:232`), `StructureBreak.index` projects `crossing.index` (`models.py:169-176`), and
`ChangeOfCharacter.index` projects `subject.index` (`models.py:154-165`). So a change of character can
land on **any** candle, including the last one — NEARUSDT 1w in §2.2 has `change = 302` on candle 302,
the newest closed bar.

**Why was that never validated earlier?**
It could not have been. Each layer's own invariant is satisfied. `SwingPoint.index >= 0`.
`ChangeOfCharacter.previous.index < subject.index`. `StructureBreak.crossing.index >=
eligible_from`. Every one of those compares **like with like**. The cross-frame comparison exists in
exactly one place in the repository, and that place is where it is wrong.

**Which architectural assumption failed?**
That an index is self-describing. In this repository a bar position is a bare `int` on
`SwingPoint`, `LevelCrossingEvent`, `StructureBreak`, `ChangeOfCharacter` and `ExecutionBreakEvent`.
The ADRs are explicit that these indices are *join keys* — ADR-0021's design calls `index`, `timestamp`
and `side` *"the three join keys every layer in this repository uses"*. They join correctly. What no
type carries is **which endpoint a position may be compared to**, and a field called `last_index`
silently invited a reader to supply the wrong one.

**Is there an earlier cause?**
Yes, and it is the last one. ADR-0025 §6 specifies the boundary as *"an identity, an `as_of`, one enum,
two indices and six optional floats"* and justifies carrying indices rather than a distance — *"the
subtraction is the engine's to do"* — but **never states what `last_index` is the index of**. The
contract that was supposed to fix the boundary left its most ambiguous field undefined, so the adapter
author and the validator author each resolved the name to a different referent, and no type, test or
review could see the disagreement because both referents are `int`.

### 3.2 The second defect

`_structure_dimension` (`classify.py:156`) computes:

```python
bars_since = subject.last_index - subject.latest_change_index
transitioning = bars_since <= policy.transition_lookback_bars
```

With `last_index` being the last swing, `bars_since` answers *"how many bars separate the change of
character from the last confirmed swing"* — a quantity with no meaning to any reader. The intended
question is *"how long ago did structure change"*, whose answer is `(n - 1) - latest_change_index`.

Because `last_swing_index <= last_candle_index` always, the reported age is **always an
understatement**. An understated age is more likely to fall inside the lookback, so
**`TRANSITIONING` is systematically over-reported** and `TRENDING` / `RANGING` systematically
suppressed. This is the opposite of a fail-safe bias, and §6 measures it.

---

## 4. Failure tree

```
ARCHITECTURAL ROOT CAUSE
A bar position is an unqualified `int`. No type records which sequence endpoint
a position may legitimately be compared against.
        │
        ▼
CONTRACT GAP  (ADR-0025 §6)
The boundary is specified as carrying "two indices". What `last_index` is the
index OF is never stated — not in the ADR, not in the design document.
        │
        ▼
WRONG ASSUMPTION, held in two places at once
  adapter   (pipeline/regime.py:179)     "last_index" = last confirmed SWING
  validator (market_regime/models.py:446) "last_index" = last closed CANDLE
Both are `int`. Neither can observe the other's reading.
        │
        ├────────────────────────────────┬───────────────────────────────────┐
        ▼                                ▼                                   │
LOWER-LAYER FACT 1               LOWER-LAYER FACT 2                          │
Confirmation delay (ADR-0024):   Pivot sparsity: a directional run           │
no swing in the newest           produces no local extremum for many         │
right_bars candles, so           bars, so the last swing is routinely        │
max(swing) = n-1-right_bars      far older than n-1-right_bars               │
        │                                │                                   │
        └────────────────┬───────────────┘                                   │
                         ▼                                                   │
              INVALID STATE (routine, not exceptional)
              last_swing_index  <  latest_change_index  <=  n-1
              A change of character on a bar that carries no swing.
              Measured: reachable in 16.1 % of historical states.
                         │                                                   │
        ┌────────────────┴───────────────────────┐                          │
        ▼                                        ▼                          ▼
BROKEN INVARIANT (D-1)                  BROKEN COMPUTATION (D-2)    ─────────┘
`latest_change_index > last_index`      `bars_since` measured to the
compares two reference frames.          last swing, not to now.
        │                                        │
        ▼                                        ▼
   RegimeInputError                     Age understated (median 3 bars,
        │                               max 19). Never once correct.
        │                                        │
        ▼                                        ▼
   COMMAND ABORTS                        TRANSITIONING over-reported
   regime --multi · swing ·                      │
   setup · daily (whole run)                     ▼
                                         swing_setup gates on
                                         `context_regime_structure is TRENDING`
                                         (policy.py:310) → false WAIT
                                                │
                                                ▼
                                         Wrong regime persisted into the
                                         append-only archive as
                                         `regime_summary` (codec.py:384),
                                         which is never recomputed.
```

The two branches are the same root cause with and without a crash. **Fixing only the left branch leaves
the right branch running, and the right branch is the one the owner cannot see.**

---

## 5. Symbol sweep

### 5.1 Method

Live symbol testing measures one instant and confounds "is there a bug" with "did the market happen to
be in the triggering state today". Instead, each cached series is **replayed prefix by prefix**: for
every prefix the full structural chain is rebuilt and `regime_input_from_sheet` is called. Each prefix
is a state the system genuinely could have been invoked in, so the failure rate over prefixes is the
probability of hitting the bug on a random invocation.

30 symbols × 4 intervals × the most recent 201 prefixes = **23,627 independent historical states.**

### 5.2 D-1 — abort rate by timeframe

| Interval | Prefixes | Failures | Rate |
|---|---:|---:|---:|
| 1w | 5,537 | 863 | **15.59 %** |
| 1d | 6,030 | 848 | **14.06 %** |
| 4h | 6,030 | 1,024 | **16.98 %** |
| 1h | 6,030 | 1,062 | **17.61 %** |
| **All** | **23,627** | **3,797** | **16.07 %** |

### 5.3 By symbol

**30 of 30 symbols fail.** Pooled across intervals, worst and best:

| | Symbol | Rate | | Symbol | Rate |
|---|---|---:|---|---|---:|
| 1 | NEARUSDT | 22.89 % | 26 | LTCUSDT | 12.77 % |
| 2 | ATOMUSDT | 21.23 % | 27 | AVAXUSDT | 12.44 % |
| 3 | AAVEUSDT | 20.23 % | 28 | ICPUSDT | 12.44 % |
| 4 | OPUSDT | 19.90 % | 29 | ETCUSDT | 12.11 % |
| 5 | ADAUSDT | 19.57 % | 30 | ARBUSDT | 11.94 % |

The spread is 12–23 %. **ADAUSDT is not special** — it is fifth, and it was reported only because it
happened to be in the triggering state during AR's live verification. Any symbol would have done.

### 5.4 Are these one bug or several?

**One.** All 3,797 failures raise the identical message from the identical line. No other exception type
appeared anywhere in 23,627 states. There is no second, independent defect hiding in the sweep.

### 5.5 Is the failure confined to the confirmation frontier?

This matters because "only the newest `right_bars` candles are affected" would suggest a small
clamp-style fix. It is false. Distribution of `change_index - last_swing_index` over the 2,934 failures
in the 1d/4h/1h sweep:

| Gap | Count | Share |
|---:|---:|---:|
| +1 | 359 | 12.24 % |
| +2 | 565 | 19.26 % |
| +3 | 774 | 26.38 % |
| +4 | 515 | 17.55 % |
| +5 | 367 | 12.51 % |
| +6 | 193 | 6.58 % |
| +7 … +13 | 161 | 5.48 % |

Only **31.5 %** of failures fall within `right_bars = 2`. The gap reaches **13**. The confirmation delay
explains the floor of the distribution; **pivot sparsity explains its tail**, and the tail is the
majority. A fix scoped to the confirmation window would leave two thirds of the failures in place.

### 5.6 The decisive control

> **Across 18,090 states, `latest_change_index > last_candle_index` occurred 0 times.**

The condition the guard's message describes has never happened, and by construction cannot: a change of
character is derived from a crossing of a closed candle, so its index is bounded by `n - 1` at the
source. **The guard is not defending an invariant. It is rejecting valid data 3,797 times out of
23,627 and correct data zero times.**

### 5.7 What the owner experiences per command

Three-view commands (`regime --multi`, `swing`, `setup`, `daily`) abort if any view raises. 1,800
invocations reconstructed by truncating all three interval series to a common wall-clock instant:

| Outcome | Count | Share |
|---|---:|---:|
| Aborts with `RegimeInputError` | 731 | **40.61 %** |
| Completes, but a view's structure state is wrong (D-2) | 431 | **23.94 %** |
| Correct | 638 | **35.44 %** |

Which role aborts (overlapping when several fail in one invocation):

| Role | Interval | Share of invocations |
|---|---|---:|
| context | 1w | 17.78 % |
| setup | 1d | 15.50 % |
| execution | 4h | 13.50 % |

---

## 6. D-2 measured

Restricted to the 15,156 states that **classify successfully** — no crash, a change of character
present, output the owner would read and trust:

| Measurement | Value |
|---|---|
| States where reported age equals true age | **0 of 15,156 (0.0 %)** |
| Median understatement | **3 bars** |
| Maximum understatement | **19 bars** |
| States where the understatement flips the `TRANSITIONING` decision | **2,468 (16.28 %)** |
| Direction of every flip | `TRANSITIONING` claimed when the true age is stale |

**The age reported by `fmits regime` has never been correct.** Not "usually correct" — the two
references coincide only when the last confirmed swing is the last closed candle, which the
confirmation delay makes impossible.

One in six successful classifications carries the wrong structure state, always biased the same way.
Because `fmis.swing_setup` hard-gates a directional candidate on
`inputs.context_regime_structure is StructureState.TRENDING` (`policy.py:310`), a falsely
`TRANSITIONING` context view forces `WAIT`. **The setup engine is being told to stand down by an
arithmetic error.**

AR's live verification recorded BTCUSDT / ETHUSDT / SOLUSDT all returning `WAIT` and read that as *"a
true, honest result"*. That reading may still be correct — but it **cannot be confirmed** until the
same symbols are re-run under a fixed `bars_since`. That re-run is a required acceptance step for the
fix (§8.4).

---

## 7. Alternative fixes

### Option A — Minimal: suppress the conflict in the adapter

Pass `latest_change_index` only when it does not exceed `last_index`, or clamp one to the other.

| | |
|---|---|
| **Pros** | Smallest possible diff. No model change, no engine change, no ADR amendment, no test migration. Stops the aborts immediately. |
| **Cons** | **Discards the single most decision-relevant structural fact.** A change of character that has not yet been overtaken by a confirmed swing is the *newest* one — exactly the event `TRANSITIONING` exists to report. Suppressing it makes structure report not-transitioning precisely when transition is most likely. It **does not fix D-2 at all**, and it converts D-1's loud failure into a second silent one, so 40 % of commands stop aborting and start lying. A clamp additionally needs `max()` or a subtraction in `fmis.pipeline`, which the AST guard `test_the_composition_root_contains_no_arithmetic` (`tests/test_pipeline_regime.py:139`) forbids. |
| **Risk** | **High.** Trades a visible defect for an invisible one, against a documented repository principle that unavailable evidence must never be silently converted into a classification. |
| **Testing impact** | Trivial — which is itself the warning sign. The existing suite cannot distinguish this from a correct fix. |
| **Architecture impact** | Cements the ambiguity of `last_index` by building a workaround on top of it. |
| **Maintenance cost** | High and permanent. Every future reader must rediscover why a real event is being dropped. |

**Rejected.**

### Option B — Correct the reference frame *(recommended)*

Replace `RegimeInput.last_index` with `RegimeInput.closed_count`, the number of closed candles the sheet
was computed over. The adapter supplies `sheet.window.closed_count`, one attribute from
`sheet.window.last_close` which it already reads. The engine computes
`bars_since = closed_count - 1 - latest_change_index`, and the invariant becomes
`latest_change_index < closed_count` — **the invariant the current error message already claims to
enforce**.

| | |
|---|---|
| **Pros** | Fixes D-1 and D-2 with one change, because they are one defect. Restores the guard to a real, satisfiable invariant instead of deleting it. **`closed_count` rather than `last_candle_index` is forced, not chosen**: the adapter may not perform the `- 1` (the AST guard forbids arithmetic in `fmis.pipeline`), and ADR-0025 §6 already states the subtraction is the engine's to do — so the correct fix is the one the existing contracts were already pointing at. It **matches `fmis.swing_setup` exactly** (`execution_closed_count`, with `execution_closed_count - 1 - break.index` in `policy.py:347` and the bound `event.index >= execution_closed_count` in `models.py:580`), so the repository ends with one pattern for "how long ago", not two. `last_index` has exactly one producer and one consumer, so nothing else must change. |
| **Cons** | A breaking change to a public field on a shipped model. ADR-0025 §6 must be amended to state what the field means. |
| **Risk** | **Low.** The change is mechanical and the correctness argument is already measured: `change_index < closed_count` held in **18,090 of 18,090** states, so the new invariant admits every real state and the guard stops firing entirely. |
| **Migration** | 11 references across three test files (`test_market_regime.py`, `test_pipeline_regime.py`, `test_workspace_build.py`), all constructing `RegimeInput` fixtures. No caller outside the adapter reads `last_index`. |
| **Future maintenance** | Low. The field's name states its own referent, so the misreading that caused this is no longer expressible. |

**Residual risk to design against.** `build_structural_facts` accepts a caller-supplied `window`,
documented as changing *"what is reported, never what is computed"*. Under Option B, `closed_count`
stops being merely reported and becomes load-bearing. On the shipped path the two agree —
`_window_of(fetched, closed)` sets `closed_count = len(closed.candles)` and the chain runs over the same
series — but a caller passing an inconsistent window would reintroduce a silent frame error. Pin it with
the regression test in §8.3.

### Option C — Future-proof: make bar positions carry their frame

Introduce a typed bar position (index plus the sequence it is anchored to), or a single shared
"bars ago" utility that every layer calls, so a cross-frame comparison becomes a type error rather than
a silent `int` comparison.

| | |
|---|---|
| **Pros** | Makes this entire class of defect unrepresentable rather than fixed once. There are already **two independent implementations** of "how long ago" (`market_regime/classify.py:156` and `swing_setup/policy.py:347`); a third will eventually disagree with both. |
| **Cons** | Blast radius far exceeds the defect. `SwingPoint`, `LevelCrossingEvent`, `StructureBreak`, `ChangeOfCharacter` and `ExecutionBreakEvent` all carry bare `int` indices, across eight packages, five ADRs (0012, 0019, 0020, 0021, 0024) and a large share of 4,319 tests. ADR-0021's design names `index` as a *join key* whose bareness is deliberate. |
| **Risk** | **High**, and concentrated in layers that are currently correct. The regression surface is every structural package, to fix a defect that lives in one adapter line. |
| **Complexity** | Large. A milestone in its own right, with no user-visible capability at the end of it — which `CLAUDE.md` explicitly asks to question. |
| **Long-term value** | Real but speculative. It buys insurance against a repeat, at the cost of destabilising the layers that have never had this bug. |

**Rejected now, recorded as a watch item.** The duplicated age arithmetic is genuine technical debt
(§9). The moment a **third** consumer needs "bars ago", the shared helper becomes worth building — but it
should be extracted from two working call sites, not designed ahead of them.

### Recommendation: Option B

Because the two defects are one defect, and B is the only option that fixes both. Because B is not a new
design — it adopts a pattern the repository already ships in its newest package, so the fix reduces the
number of ideas in the codebase rather than adding one. Because the "no arithmetic in `fmis.pipeline`"
guard and ADR-0025 §6's own reasoning independently force `closed_count` as the field to carry, meaning
B is what the existing contracts were already asking for. And because its correctness is **measured, not
argued**: the invariant it installs was satisfied in 18,090 of 18,090 historical states, while the
invariant it replaces was violated in 3,797 of 23,627 — every one of them a false positive.

---

## 8. Regression risks and the tests that are missing

### 8.1 What breaks when this is fixed

| Change | Consequence | Assessment |
|---|---|---|
| `TRANSITIONING` stops being over-reported | ~16 % of classifications move to `TRENDING` / `RANGING` / `INDETERMINATE` | **Intended.** This is the fix working. It will visibly change output on symbols the owner has already looked at, and must be announced rather than discovered. |
| `swing_setup` sees `TRENDING` where it previously saw `TRANSITIONING` | Symbols that returned `WAIT` may now produce `CANDIDATE` | **Intended, and the highest-value consequence** — the setup engine stops being suppressed by an arithmetic error. Also the highest-risk: it changes what the owner may act on. Requires the §8.4 acceptance run. |
| `bars_since` grows by a median of 3 bars | Evidence strings and `value` fields change on essentially every regime with a change of character | Expected. Any golden-output test over rendered regime pages must be re-baselined deliberately, not auto-updated. |
| `RegimeInput.last_index` removed | 11 test references stop compiling | Mechanical. |
| Archived `regime_summary` records | **Not retroactively corrected.** The archive is append-only and never recomputed (`fmits archive show` returns exactly what was archived). | `~/.fmits/archive` does not exist on this machine, so **no poisoned records exist yet**. This is a strong argument for fixing before the archive starts filling. |
| `policy.transition_lookback_bars = 5` | Was implicitly being applied to an understated age; it now applies to the true age, so `TRANSITIONING` becomes strictly rarer | The threshold was never calibrated (limitation AI-3). It should be **re-examined, not silently kept** — its observed behaviour changes even though its value does not. |

### 8.2 Why 4,319 passing tests never caught this

The suite is green — `4319 passed in 12.86s` on `2a9bdcc` — and reports 100 % line and branch coverage
on the regime modules. It still missed a defect that breaks 40 % of real invocations, for three
compounding reasons.

**1. Coverage measures lines, not states.** Every branch of the invariant is executed. The defect is not
an unexecuted branch; it is an executed branch reached with data whose *meaning* is wrong. No coverage
metric can see that.

**2. The fixture's data-generating process is biased against the bug.** `seeded_series` builds a random
walk from independent uniforms. A random walk pivots constantly — 105 swings in 260 bars — so its last
confirmed swing is almost always at the confirmation frontier and the gap almost never opens. Real
markets trend, and a trending market goes many bars without a pivot. Running the repository's own
generator, unmodified, over a wider seed range:

```
seeds tested 500   failing 12   rate 2.4 %
failing seeds within the suite's own 0..24 range: []
first failing seed: 58   (last_swing_index=254, change_index=255)
```

**The suite's fixture can produce the failure. The suite just never asks it to** — the bug first appears
at seed 58, and the suite uses seeds 0–24. The 2.4 % synthetic rate against the 16.1 % real rate is the
measure of how much a random walk understates a market.

**3. The review validated the guard as a feature.**
[`MARKET_REGIME_ENGINE_V1_REVIEW.md`](../reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md) §8 lists
`latest_change_index > last_index` → `RegimeInputError` in its adversarial-input table as **correct
behaviour**. The review asked *"does the guard fire when the condition holds?"* and never
*"can the adapter legitimately produce that condition?"* A guard tested only against hand-built inputs
proves the guard runs; it proves nothing about whether the guard is right.

The most specific test in the suite,
`test_the_adapter_carries_the_change_of_character_when_one_exists`, asserts
`subject.last_index == built.structure.swings[-1].index` — **it pins the defect as the expected
behaviour**, with a docstring explaining that seed 5 gives change at 254 and last swing at 255. A test
that pins the wrong quantity as correct is worse than no test, and this one will need rewriting rather
than adjusting.

### 8.3 Invariants that should become permanent regression tests

1. **Property, over generated series** — for any closed series and any `left_bars`/`right_bars`,
   `regime_input_from_sheet` never raises. The bug's whole shape is "valid data rejected", and only a
   property test over many series states that.
2. **Real-market corpus, not a random walk** — a small committed fixture of *trending* series (ADAUSDT
   1d at the cached state in §2.3 is a ready-made one) exercised on every run. Guards against the
   random-walk blind spot recurring.
3. **`bars_since` is measured from the last closed candle** — assert the exact value against a
   hand-computed one on a fixture where the last swing and the last candle differ. Directly pins D-2,
   which no current test can see.
4. **Frame consistency at the boundary** — `sheet.window.closed_count == len(series.closed().candles)`
   for every sheet built by `build_structural_facts`. Closes the residual risk named in §7 Option B.
5. **The engine's own bound** — `latest_change_index < closed_count` accepted at
   `closed_count - 1`; rejected at `closed_count`. Pins the corrected invariant on both sides.
6. **The confirmation-frontier case explicitly** — a fixture where the change of character lands on the
   last closed candle (NEARUSDT 1w in §2.2 is exactly this) and structure still classifies.
7. **Multi-view isolation** — a three-view command where one view carries a frontier change of character
   still returns all three regimes.
8. **`fmits daily` partial results** — decide, and then pin, whether a defect in one symbol may abort the
   whole run. Today it does; §8.5 argues that is a separate decision worth taking deliberately.

### 8.4 Edge cases that must always be tested

- change of character on the **last** closed candle (`change_index == closed_count - 1`);
- change of character within the confirmation frontier (`> n - 1 - right_bars`);
- a long directional run with **no** confirmed swing for many bars — the tail of §5.5;
- **no** change of character at all (`latest_change_index is None`);
- **no** confirmed swings at all (`swings` empty — the adapter's other branch, currently untested against real data);
- non-default `right_bars`, which moves the frontier and must not move correctness;
- `closed_count` of 0 and 1, at the boundary of `closed_count - 1`;
- the change of character exactly at, and one bar beyond, `transition_lookback_bars` measured from the
  **true** reference.

### 8.5 A separate decision this investigation surfaced

`RegimeInputError` aborting an entire `fmits daily` run is correct under the current rule ("a defect must
stay a defect") and is not itself a bug. But it means **any** future defect in any engine costs the owner
the whole watchlist rather than one row. Whether a daily run should degrade to a per-symbol failure for
unexpected exceptions is a real product question. It is **out of scope here** and is named so it is not
lost.

---

## 9. Technical debt assessment

| Axis | Rating | Basis |
|---|---|---|
| **Severity** | **Critical** | Aborts four of seven CLI commands, including `setup` and `daily`, the two the owner runs daily. Silently corrupts the structure dimension on runs that do not abort. |
| **Probability** | **Certain, not probabilistic** | 16.07 % per timeframe view, 40.61 % per three-view command, measured over 23,627 states. 30 of 30 symbols. Every interval. It is not an edge case; it is the common case. |
| **Impact — correctness** | **High** | The age reported by `fmits regime` has been wrong on **every** run since Milestone AI. 16.28 % of successful classifications carry the wrong structure state. |
| **Impact — product** | **High** | The setup engine's directional gate reads the corrupted state, so false `WAIT`s are produced by arithmetic rather than by the market. Directly contradicts the deterministic-first principle: a value computable exactly is being computed wrongly. |
| **Impact — trust** | **High** | Corrupted `regime_summary` values reach the append-only archive, which is never recomputed. The system's own memory would be poisoned. |
| **Blast radius** | 4 commands, 3 packages (`pipeline.regime`, `market_regime`, and every consumer: `workspace`, `swing_setup`, `daily`, `archive`) | |
| **Debt created so far** | **Moderate and contained** | One ambiguous field, one wrong adapter line, one test pinning the wrong behaviour, one review entry endorsing the wrong guard. No workaround has been built on top of it, which is what keeps the fix cheap. |
| **Cost if fixed correctly (Option B)** | **Low — roughly one focused milestone** | One field renamed, one adapter line, one engine expression, one invariant, ADR-0025 §6 amended, 11 test references migrated, plus the eight regression tests in §8.3, plus the acceptance re-run in §8.4. |
| **Cost if fixed minimally (Option A)** | **Negative value** | Cheaper today, and it makes the system worse: D-2 survives, D-1 goes silent, and the ambiguity that caused both is cemented behind a workaround. |
| **Cost if ignored** | **Compounding** | Every day of `fmits daily` writes archive records whose regime line may be wrong, into a store that is append-only by design and has no re-derivation path. The debt is currently **zero** — `~/.fmits/archive` does not exist. Once the owner starts archiving daily runs, the cost of this bug stops being "fix the code" and becomes "the system's memory is unreliable and cannot be repaired." |

**The single most important number in this document:** the guard rejected **3,797** valid states and
**0** invalid ones. It has never done its job, and it has never had a job to do.

---

## 10. Next implementation plan

Proposed, not executed. Nothing below has been started.

**Gate 0 — decision.** Owner confirms Option B and accepts that regime output will visibly change on
symbols already reviewed. *Nothing proceeds without this.*

**Step 1 — contract.** Amend ADR-0025 §6 to state what the field is the index of, and record the frame
rule: *a position may be compared only against the endpoint of the sequence it indexes.* Note ADR-0024
(confirmation delay) as the mechanism that makes swing and candle endpoints differ, and
`fmis.swing_setup` as the existing precedent being adopted. *No code yet — the contract gap is the root
cause and is closed first.*

**Step 2 — engine.** `RegimeInput`: `last_index` → `closed_count`; invariant becomes
`latest_change_index < closed_count`. `classify.py:156`: `bars_since = closed_count - 1 -
latest_change_index`. Docstrings state the referent explicitly.

**Step 3 — adapter.** `pipeline/regime.py:179` supplies `sheet.window.closed_count`. Confirm the AST
no-arithmetic guard still passes — it should, and if it does not, the design is wrong.

**Step 4 — tests.** Migrate the 11 references. **Rewrite** (not adjust)
`test_the_adapter_carries_the_change_of_character_when_one_exists`, which currently pins the defect.
Add the eight regression tests from §8.3, including the committed real-market fixture. Widen the seed
range in the fixture-based tests so seed 58 is inside it.

**Step 5 — verification.** Re-run the walk-forward sweep against the fixed tree; **expect 0 failures in
23,627 states**. Re-run the multi-view simulation; expect 0 aborts and 0 flips. Re-run the live CLI
sweep across the same 16 symbols; expect 16/16 on all three commands.

**Step 6 — acceptance.** Re-run `fmits setup` on BTCUSDT / ETHUSDT / SOLUSDT — AR's stated
demonstration — and record whether the `WAIT` results survive the corrected `bars_since`. **Report the
answer either way.** If a `WAIT` becomes a `CANDIDATE`, that is a product-visible change and belongs in
the changelog; if the `WAIT`s hold, AR's claim is confirmed rather than assumed.

**Step 7 — product documents.** Backlog and changelog per `CLAUDE.md`, on evidence from the repository.
A correctness fix that changes what the owner sees is user-visible capability; a fix that changes
nothing visible is not.

**Explicitly out of scope:** Option C's typed bar positions; extracting a shared "bars ago" helper; the
`fmits daily` partial-result question (§8.5); recalibrating `transition_lookback_bars`. Each is recorded
above so it is deferred rather than forgotten.

---

## Appendix — evidence index

| Claim | Source |
|---|---|
| Adapter supplies the swing index | `src/fmis/pipeline/regime.py:179` |
| Invariant compares two frames | `src/fmis/market_regime/models.py:441-450` |
| `bars_since` measured from the swing | `src/fmis/market_regime/classify.py:156` |
| Max swing index is `n-1-right_bars` | `src/fmis/market_structure/swings.py:150` |
| Crossings enumerate every closed candle | `src/fmis/level_crossing/crossing.py:232` |
| CHoCH index projects the break bar | `src/fmis/change_of_character/models.py:154-165` |
| Correct pattern already in the repository | `src/fmis/swing_setup/policy.py:347`, `models.py:580` |
| Setup gate reads the structure state | `src/fmis/swing_setup/policy.py:310` |
| Regime reaches the archive | `src/fmis/archive/codec.py:384` |
| `RegimeInputError` not an expected daily failure | `src/fmis/daily/runner.py:73` |
| No arithmetic permitted in the adapter | `tests/test_pipeline_regime.py:139` |
| Test pinning the defect as correct | `tests/test_pipeline_regime.py:443-455` |
| Review endorsing the guard | `docs/reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md` §8 |
| Contract gap | `docs/adr/ADR-0025-market-regime-engine-v1.md` §6 |
| Baseline suite green at `2a9bdcc` | `4319 passed in 12.86s` |
