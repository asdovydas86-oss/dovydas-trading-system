| Field | Value |
|---|---|
| **Report number** | 0047 |
| **Title** | Technical Analysis Capability Audit & Architecture Gate |
| **Date** | 2026-09-07 |
| **Report type** | Audit and architecture gate (read-only; no production change) |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Audited commit** | `66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3` |
| **Status** | Final — awaiting Dovydas + ChatGPT approval |

---

# Technical Analysis Capability Audit & Architecture Gate

**Nothing in `src/` was modified. No policy changed. No engine was implemented. This report is the
deliverable.**

---

## 1. Executive summary

### 1.1 The finding in one paragraph

FMITS has an **excellent price-structure spine and almost no technical-analysis body**. The chain
from candles to swings to labels to levels to crossings to break-of-structure to change-of-character
is real, non-repainting, prefix-stable, exhaustively tested and better specified than most commercial
implementations. Above that spine, the repository has **six empty packages** where the technical
analysis was supposed to go — `features/trend`, `features/momentum`, `features/volatility`,
`features/market_structure`, `features/support_resistance`, `features/pattern_detection` — each one a
docstring, a `from __future__ import annotations`, and `__all__: list[str] = []`. Between the two,
one function drops almost everything the spine produced.

### 1.2 The three findings that matter

**Finding A — the system is not blind; it is amnesiac.** The owner's example (*"consolidation beneath
resistance, improving EMA geometry, momentum cooling, breakout not confirmed"*) fails at four
different points, and only one of them is a missing calculation:

| The owner's observation | Why FMITS cannot say it |
|---|---|
| *"an important resistance zone around the recent highs"* | **Computation missing** — a `PriceLevel` is a line with no zone, no touch count, no role, no lifecycle |
| *"consolidation beneath that zone"* | **Computation missing** — no impulse/consolidation/range primitive exists anywhere |
| *"improving EMA geometry"* | **Computed and discarded** — `ema_20`, `ema_50`, `ema_200` are computed on all three timeframes and reach **no operator surface at all**; and only the *latest scalar* exists, so no slope is derivable even in principle |
| *"breakout not yet confirmed"* | **Computed and discarded** — the full `TOUCH` / `WICK_BREACH` / `CLOSE_BREACH` × `WITHIN_RANGE` / `GAPPED_BEYOND` / `ALREADY_BEYOND` crossing history is derived on every view and reduced to **one integer: a count** |

**Finding B — the richest primitive in the repository is thrown away whole.**
`fmis.level_crossing` already produces, per candle per level, a nine-way classification of how price
met a level. That is the exact substrate a breakout / acceptance / rejection / retest engine needs.
Today it is derived, used once to compute break-of-structure, rendered as `"Crossing events: 412"`,
and dropped at `build_setup_inputs`. **A breakout/retest engine is mostly a consumer problem, not a
computation problem.**

**Finding C — no two of the policy's three "independent" families are independent, and the fix is a
new evidence family, not a new indicator.** `fmis.setup_evidence.correlation` already proves this in
code: `standing_family_note()` returns a caveat precisely because no two of
`context_structural_trend`, `setup_structural_trend`, `setup_evidence_alignment` are family-disjoint
(all three are TREND; one is also MOMENTUM). Milestone AW measured 75–79% pairwise agreement.
Adding a fourth *trend* reading buys nothing. Adding **location** (where price stands relative to a
zone), **participation** (volume at the event) and **volatility state** (compression vs expansion)
would be the repository's first genuinely disjoint evidence — which is the strongest argument for
the recommended slice below.

### 1.3 The recommendation in one line

**Build the Level & Zone Engine and the Interaction (breakout/retest) Engine as one thin vertical
slice, and carry the crossing history that already exists across the seam that already drops it.**
Everything else in the brief — patterns, divergences, trendlines, Fibonacci, Elliott — depends on
primitives that do not exist yet, and building any of them first would mean building the primitive
badly inside the pattern.

### 1.4 What this report recommends **against**

| Asked about | Recommendation | Why |
|---|---|---|
| Fibonacci | **RESEARCH FIRST** (not core, not now) | Needs a validated anchor-selection policy, which needs a validated swing-significance measure the repository does not have |
| Elliott Wave | **DEFER** (hypothesis tier if ever) | The owner's prior expectation is correct and the repository evidence supports it more strongly than he stated |
| Chart patterns (flags, H&S, wedges) | **DEFER to after primitives** | Every one decomposes into impulse/consolidation/geometry primitives that do not exist; building them first means building each primitive five times, badly |
| Candlestick pattern catalogue | **REJECT as a catalogue; APPROVE as morphology-at-location** | `SPEC` §4.5 already forbids the catalogue reading, and location context does not exist yet either |
| An "opportunity score" | **REJECT** | Three research milestones (CA `NO_EDGE`, CB `UNDERPOWERED`, CC `INFEASIBLE`) already establish there is nothing to calibrate against |

---

## 2. Verified baseline

Every line below was read from the live repository, not from the brief.

| Claim in the brief | Verified? | Evidence |
|---|---|---|
| Slice 4 closed | **Yes** | `FMITS_PRODUCT_BACKLOG.md` §8, `DV` — Swing Product Slice 4 · **DONE**; report 0046 Final |
| `HEAD` = `main` = `origin/main` = `66bab74` | **Yes** | all three resolve to `66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3` |
| 16 untracked research documents, untouched | **Yes** | 15 under `docs/design/`, 1 under `docs/reviews/`; tracked tree clean; **none was read-modified — all reads were read-only** |
| 81 policy fixtures, 72 WAIT, 9 CANDIDATE | **Yes** | `tests/test_swing_setup_policy_non_regression.py` asserts `len(BASELINE) == 81` and `Counter({"wait": 72, "candidate": 9})` as executable contracts |
| Aggregate `sha256` starts `8b22e6c9…` | **Yes — and the formula is committed** | report 0045 §11.6 states it; independently recomputed in §2.2 below |
| Reliability Gate 9/9 smoke | **Yes** | `tests/test_operator_dashboard_startup_smoke.py` contains exactly 9 `def test_` functions |
| Slice 4 mutation campaign 12/12 killed | **Recorded, not re-runnable** | report 0046's own record; the campaign scripts are not in the repository (consistent with the research-script convention AW/AX/AY set). Not re-verified, and not treated as a live gate by this report |
| Dashboard at `127.0.0.1:8787`, PID 46403, serving `66bab74` | **Partly** | PID **46403** confirmed listening on `127.0.0.1:8787` (`lsof`), parent shell 46401. **The commit it is serving was not verified** — doing so would have required a request or a restart, and the instance was left completely untouched |
| Full suite 14,699 / 0 / 0 / 0 under `-W error` | **See §2.1** | re-run at `66bab74` |

**Discrepancies found: none material.** Two refinements are recorded rather than smoothed over: the
mutation campaign is a historical record and not a live gate, and the dashboard's served commit was
not confirmed because confirming it would have meant touching the operator's instance.

### 2.1 Full suite

Run at `66bab74`, `-W error`, `-p no:cacheprovider`, with **no other pytest process alive** and the
operator instance untouched:

```
.venv/bin/python -m pytest -q -W error -p no:cacheprovider
```

```
14699 passed in 689.62s (0:11:29)
EXIT=0
```

**14,699 passed · 0 failed · 0 skipped · 0 warnings.** The brief's figure is confirmed exactly.

One operational note worth recording: the first attempt failed instantly with
`command not found: python` — this repository has no bare `python` on `PATH`, and the venv
interpreter at `.venv/bin/python` is the only correct one. Recorded so the next session does not
lose the same two minutes.

### 2.2 Policy non-regression digest

Recomputed independently of the test file, using the formula report 0045 §11.6 committed:

```python
sha256(b"".join(repr(setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol))).encode()
                for key, seeds, symbol in _matrix()))
```

```
fixtures:          81
states:            {'wait': 72, 'candidate': 9}
aggregate sha256:  8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c
```

**All three confirmed.** This digest is the acceptance gate for every future commit of the work this
report proposes (§33.6, §40).

### 2.3 Every other measurement

Structural-chain scaling, the empty-package line counts and the dashboard check are in the
verification appendix, §46, with the commands that produced them.

---

## 3. Source reconciliation — what the specification requires vs what the code does

`PROJECT_SPECIFICATION_V1.md` is the authoritative statement of intent. It is unusually specific
about technical analysis, and that specificity makes the gap measurable rather than arguable.

| `SPEC` requirement | Section | Live implementation | Verdict |
|---|---|---|---|
| EMA values | §3.1 | `ExponentialMovingAverage`, any period/source, SMA-seeded | **Met** |
| EMA **slopes** | §3.1 | *nothing* — only the latest scalar is returned | **Not met** |
| RSI values | §3.1 | `RelativeStrengthIndex`, Wilder | **Met** |
| MACD line, signal, histogram | §3.1, §4.2 | `MovingAverageConvergenceDivergence`, structured `{macd_line, signal_line, histogram}` | **Met** |
| MACD **histogram direction, rate of change, consecutive improvement/deterioration** | §4.2 (named explicitly, five separate items) | *nothing* | **Not met** |
| MACD **divergence with price** | §4.2 | *nothing* | **Not met** |
| ATR and volatility | §3.1 | `AverageTrueRange` Wilder; `atr_percent_of_close` derived in `decision_support` | **Met (value only)** |
| Volume ratios | §3.1 | `AverageVolume`, `RelativeVolume`, trailing-mean baseline excluding the current bar | **Met (measurement only, ADR-0010 deferred interpretation)** |
| Distance from moving averages | §3.1 | `classify_comparison(close, ema)` → `ABOVE`/`BELOW`/`EQUAL` only. **No distance is ever computed.** | **Not met** |
| Swing highs and lows | §3.1, §4.5 | `fmis.market_structure.detect_swings` | **Met, and well** |
| **Support and resistance candidates** | §3.1, §4.5 | *nothing.* `PriceLevel` is deliberately **not** support/resistance (ADR-0019 §I), and three separate tests forbid the words in rendered output | **Not met — and structurally forbidden today** |
| Trend structure, HH/HL/LH/LL | §4.5 | `fmis.market_structure.labels` | **Met** |
| Break of structure | §4.5 | `fmis.structure_break` | **Met** |
| Change of character | §4.5 | `fmis.change_of_character` | **Met (computed) / unreachable (product)** |
| **Consolidation** | §4.5 | *nothing* | **Not met** |
| **Breakout** | §4.5 | Primitive exists (`CLOSE_BREACH`); the *concept* does not | **Partial — primitive only** |
| **Retest** | §4.5 | *nothing* | **Not met** |
| **Trend continuation** | §4.5 | *nothing* | **Not met** |
| **Trend exhaustion** | §4.5 | *nothing* | **Not met** |
| RSI slope, recovery from extremes, failure swings | §4.4 | *nothing* — only a five-band zone classification | **Not met** |
| RSI/MACD **divergence** | §4.2, §4.4 | *nothing* | **Not met** |
| EMA reclaim / rejection / compression / dynamic S/R / multi-EMA relationship | §4.3 (five named items) | *nothing* — one pairwise `ema_fast_vs_ema_slow` comparison | **Not met (1 of 6)** |
| Candlestick information used **but not dominant without context** | §4.5 | *nothing at all* — no candlestick engine exists, so the rule is trivially satisfied | **Absent, not violated** |
| Evidence grouped into broad categories, not counted | §4.6 | `EvidenceFamily` (10 members) + `fmis.setup_evidence.correlation` with six declared correlation rules | **Met, and exceeded** |
| Multi-timeframe with **explained roles**, never blended | §5 | `TimeframeRole` CONTEXT/SETUP/EXECUTION; `multi_timeframe` performs **zero** cross-timeframe synthesis by design | **Met** |
| Decision vocabulary beyond BUY/SELL: `WAIT`, `WATCH FOR CONFIRMATION`, `INVALIDATED` | §6 | `SetupState` = `WAIT`/`CANDIDATE`/`CONFIRMED`; `Trigger.AWAITING_STRUCTURE_BREAK`; `DevelopingEvidenceState` | **Mostly met — `INVALIDATED` has no state** |
| Bias control, strongest opposing case | §7 | Structural: `MINIMUM_AGREEING_FAMILIES=2` with **zero opposing**; `market_regime` cannot represent a direction at all; three repository-wide vocabulary guards | **Met, and exceeded** |
| Feature Engine calculating indicators, structure, volatility, volume | §16 | `FeatureEngine` orchestrates 6 features; **the four Tier-2 category packages it advertises are empty** | **Partial** |
| Technical Analysis Engine as a named analysis engine | §16 | **Does not exist as a package.** Its responsibilities are split across `features`, `market_structure`, `structural_trend`, `level_crossing`, `structure_break`, `change_of_character`, `market_regime`, `decision_support` | **Structurally absent** |

`PROJECT_VISION_ADDENDUM_V1.md` names nine technical items: EMA, MACD, RSI, Volume, Market Structure,
**Trendlines**, **Support/Resistance**, **Divergences**, Volatility. Six exist as measurements; the
three in bold do not exist at all.

**Reconciliation verdict.** The specification is not vague about this and the repository has not
drifted from it — it has simply **stopped short of it**. Every unmet item above is an item the
specification named explicitly in 2026-07, and every one is still unmet at `66bab74`. This milestone
is not an expansion of scope; it is the resumption of scope.

---

## 4. Current Technical Analysis capability matrix

Status vocabulary, as the brief defines it:

- **IMPLEMENTED** — real math, tested, reachable from production
- **PARTIAL** — exists but materially incomplete against its own stated purpose
- **DORMANT** — implemented and tested, but no production caller
- **PRODUCT-UNREACHABLE** — computed on the live path, then discarded before any operator surface
- **PLACEHOLDER** — a module exists; it contains no math
- **MISSING** — nothing exists

Columns: **Own** = owning package · **Prod?** = called on the live scan path · **Swing?** = reaches
`SetupInputs` · **Dash?** = visible on the operator dashboard · **CB** = closed-bar safe ·
**Sym** = long/short symmetric · **Fam** = evidence family it could belong to.

### 4.1 L3 — measurements

| Capability | Status | Own | Prod? | Swing? | Dash? | CB | Sym | Fam | Main limitation |
|---|---|---|---|---|---|---|---|---|---|
| EMA (any period/source) | IMPLEMENTED | `features.indicators.ema` | yes | **no** | **no** | yes | n/a | TREND | **latest scalar only**; no series, so no slope is derivable |
| EMA series math | IMPLEMENTED (private) | `features.indicators.ema_math` | yes | no | no | yes | n/a | — | `ema_series()` exists and returns the full series; **only `[-1]` escapes** |
| ATR (Wilder, 14) | IMPLEMENTED | `features.indicators.atr` | yes | **no** | **no** | yes | n/a | VOLATILITY | latest scalar only |
| RSI (Wilder) | IMPLEMENTED | `features.indicators.rsi` | yes | **no** | **no** | yes | n/a | MOMENTUM | latest scalar only |
| MACD (12/26/9) | IMPLEMENTED | `features.indicators.macd` | yes | **no** | **no** | yes | n/a | MOMENTUM | latest `{line, signal, hist}` only; no history, no ROC |
| Average volume | IMPLEMENTED | `features.volume.statistics` | registerable | no | no | yes | n/a | VOLUME | not in `default_features()` |
| Relative volume (20) | IMPLEMENTED | `features.volume.statistics` | yes | **no** | **no** | yes | n/a | VOLUME | ADR-0010 deferred all interpretation; the ratio is never classified |
| ATR % of close | IMPLEMENTED | `decision_support.derived` | yes | **no** | **no** | yes | n/a | VOLATILITY | reported as a raw number; `Alignment.NOT_DIRECTIONAL`; dies at `build_setup_inputs` |
| **Indicator *series* at the FeatureSet boundary** | **MISSING** | — | — | — | — | — | — | — | `FeatureValue` already permits `Sequence`; nothing produces one. **Recorded as review R5 since 2026-07-24** |
| ADX / DI± | MISSING | — | — | — | — | — | — | TREND | named as a TODO in `indicators/__init__.py` |
| Bollinger Bands / width / squeeze | MISSING | — | — | — | — | — | — | VOLATILITY | named as a TODO |
| VWAP / anchored VWAP | MISSING | — | — | — | — | — | — | VOLUME | named as a TODO |
| OBV / accumulation-distribution / money flow | MISSING | — | — | — | — | — | — | VOLUME | named as deferred in `features.volume.__init__` |
| Volume profile / VPOC / value area | MISSING | — | — | — | — | — | — | VOLUME | — |

### 4.2 L4 — structural price facts

| Capability | Status | Own | Prod? | Swing? | Dash? | CB | Sym | Fam | Main limitation |
|---|---|---|---|---|---|---|---|---|---|
| Swing highs / lows | IMPLEMENTED | `market_structure.swings` | yes | **no** | **no** | yes | **yes** | MARKET_STRUCTURE | fixed `left/right=2` window; plateau resolves to the *first* bar; confirmation delay `= right_bars` |
| Confirmation delay provenance | IMPLEMENTED | `market_structure` → `LevelOrigin` | yes | partial | no | yes | yes | — | ADR-0024 closed ADR-0020 D1; the window travels on every level |
| Swing relationships (numeric) | IMPLEMENTED | `market_structure.relationships` | yes | no | no | yes | yes | MARKET_STRUCTURE | same-type only; exact float equality, no tolerance |
| HH / HL / LH / LL / EQUAL_HIGH / EQUAL_LOW | IMPLEMENTED | `market_structure.labels` | yes | **no** | **no** | yes | **yes** | MARKET_STRUCTURE | equal structure is first-class and never folded |
| Structural sequence state | IMPLEMENTED | `market_structure.sequence_state` | yes | no | no | yes | yes | MARKET_STRUCTURE | 6 states; only 2 are directional |
| Structural sequence state history | IMPLEMENTED | `market_structure.state_history` | yes | no | no | yes | yes | MARKET_STRUCTURE | not stable under a cut *inside* a same-candle HIGH/LOW group (ADR-0016 §7) |
| Structural trend | IMPLEMENTED | `structural_trend` | yes | **yes** | **yes** (`TimeframeRow.structural_trend`) | yes | yes | TREND | `MINIMUM_DIRECTIONAL_SHIFTS = 2`; **unconditional persistence** — a trend survives 500 contracting snapshots |
| Price levels from swings | IMPLEMENTED | `level_crossing.levels` | yes | **partial** (setup + execution only) | no | yes | yes | MARKET_STRUCTURE | **a line, not a zone**; no strength, no touches, no role, no lifecycle. First swing of each type yields **no** level (ADR-0019 D2) |
| Level crossing events | IMPLEMENTED | `level_crossing.crossing` | yes | **NO** | **count only** | yes | yes | MARKET_STRUCTURE | **PRODUCT-UNREACHABLE.** 9-way classification derived per candle per level, rendered as one integer |
| — `TOUCH` / `WICK_BREACH` / `CLOSE_BREACH` | IMPLEMENTED | `level_crossing.models` | yes | no | no | yes | yes | — | exact equality is a touch, never a breach; not configurable, by design |
| — `WITHIN_RANGE` / `GAPPED_BEYOND` / `ALREADY_BEYOND` | IMPLEMENTED | `level_crossing.models` | yes | no | no | yes | yes | — | `open` is never consulted; no intrabar path is ever claimed |
| Break of structure | IMPLEMENTED | `structure_break` | yes | **execution role only** | no | yes | yes | MARKET_STRUCTURE | close-only; **breaks once, ever**; reference is *most recent* eligible, not most extreme (ADR-0020 D5); **never invalidated** (D3) |
| Change of character | **PRODUCT-UNREACHABLE** | `change_of_character` | yes | **no** | **no** | yes | yes | MARKET_STRUCTURE | computed on every view; consumed by `market_regime` as a *transition* flag and by a `snapshotting` string; **never reaches the policy or the swing page** |
| Nearest level above / below close | IMPLEMENTED | `pipeline.structural_facts` | yes | **no** | **no** | yes | yes | — | on the fact sheet and the snapshot; **dropped at `build_setup_inputs`** |
| Protected high / low | MISSING | — | — | — | — | — | — | — | ADR-0020 explicitly reserves this for a layer that does not exist |
| Failed / invalidated break | MISSING | — | — | — | — | — | — | — | ADR-0020 D3 names it as a later reading over the break sequence |
| Trend transition / exhaustion | PARTIAL | `market_regime` (`TRANSITIONING`) | yes | **gate only** | no | yes | yes | — | one state, from a recent CHoCH within a lookback; no exhaustion primitive |

### 4.3 L5 — everything this milestone is about

Every row below was verified by reading implementation, not by reading a file name.

| Capability | Status | Evidence |
|---|---|---|
| **Support / resistance zones** | **MISSING** | `features/support_resistance/__init__.py` is 16 lines: a docstring with four `TODO:` lines and `__all__: list[str] = []` |
| Level clustering | MISSING | — |
| Touch counting | MISSING | The data exists (`CrossingKind.TOUCH` per level per bar); nothing counts it |
| Rejection behaviour | MISSING | The data exists (`WICK_BREACH`); nothing reads it |
| Level strength / age / recency | MISSING | `LevelOrigin.index` and `.timestamp` exist; no age is derived |
| Zone width / volatility-normalised width | MISSING | ATR exists on the same sheet; nothing combines them |
| Broken / reclaimed level | PARTIAL | `StructureBreak` says a level broke, once. Nothing says it was reclaimed |
| Role flip (support ⇄ resistance) | MISSING | `LevelSide` is **intrinsic and immutable** — a swing high is `UPPER` forever. Role flip is *unrepresentable* in the current model |
| MTF level confluence | MISSING | Context-role levels never leave the fact sheet |
| Level lifecycle / invalidation / staleness | MISSING | ADR-0019 §2.7 explicitly excludes lifecycle from the crossing primitive and assigns it upward |
| **Trendlines (ascending / descending)** | **MISSING** | Named in `PROJECT_VISION_ADDENDUM_V1.md`; zero code, zero placeholder |
| Anchors, touch tolerance, slope, projection | MISSING | — |
| Trendline break / retest / failed break | MISSING | — |
| **Channels (parallel, ascending, descending, horizontal)** | **MISSING** | — |
| Channel width / compression / expansion | MISSING | — |
| **Breakout / breakdown as a concept** | **MISSING** | The *primitive* (`CLOSE_BREACH`) exists and is excellent. The word `breakout` appears in `src/` **only in prose** — 13 occurrences, every one a docstring or a comment, several of them explicitly saying the concept is *not* being claimed. No type, function, field or enum member names it |
| Acceptance beyond a level | MISSING | — |
| Reclaim | MISSING | — |
| Retest / successful retest / failed retest | MISSING | — |
| False breakout / failed breakout | MISSING | ADR-0020 D3 names this as a later reading |
| Breakout volume expansion | MISSING | `RelativeVolume` exists per bar; nothing joins it to a break event |
| Distance beyond level, ATR-normalised | MISSING | Both inputs exist on one sheet; nothing subtracts them |
| Time spent beyond level / return inside | MISSING | — |
| **Directional impulse** | **MISSING** | — |
| Impulse magnitude / ATR-normalised / duration | MISSING | — |
| **Consolidation** | **MISSING** | Named in `SPEC` §4.5 |
| Retracement depth / duration | MISSING | — |
| **Range detection** | PARTIAL | `market_regime.StructureState.RANGING` exists — but it is a **whole-timeframe environment label**, not a bounded range object with a high, a low, a start and an end |
| Compression / expansion | PARTIAL | `market_regime.VolatilityState` is an ATR-ratio band; no contraction *event* exists |
| Volume contraction / expansion | MISSING | — |
| **All chart patterns** (flag, pennant, triangle, wedge, rectangle, double top/bottom, H&S, V-top/bottom, rounding) | **MISSING** | `features/pattern_detection/__init__.py` is 23 lines: docstring, three `TODO:` lines, `__all__: list[str] = []` |
| **Pattern lifecycle** | MISSING | Nothing in the repository has a lifecycle except `fmis.proposal` and `fmis.trade_lifecycle`, both of which are trading-domain, not market-fact |
| **All candlestick patterns** | MISSING | No engine, no placeholder, no enum |
| **RSI divergence** (regular / hidden, bull / bear) | **MISSING** | Named in `SPEC` §4.4 and `features/momentum/__init__.py`'s TODO list |
| **MACD divergence** | **MISSING** | Named in `SPEC` §4.2 |
| Multi-swing / triple / failed divergence | MISSING | — |
| **EMA slope / normalized slope** | MISSING | Requires an indicator series, which does not exist |
| EMA distance / price distance from EMA | MISSING | `SPEC` §3.1 names it; only `ABOVE`/`BELOW`/`EQUAL` exists |
| Multi-EMA ordering / stacking | PARTIAL | One pair compared (`ema_fast_vs_ema_slow`); `ema_200` is computed on the swing path and compared to **nothing** |
| EMA spread / convergence / rate of convergence | MISSING | — |
| EMA crossover / proximity / time since | MISSING | — |
| EMA reclaim / rejection / compression / dynamic S/R | MISSING | All four named in `SPEC` §4.3 |
| **MACD histogram direction / ROC / consecutive improvement** | **MISSING** | All three named in `SPEC` §4.2. Only `classify_sign(histogram)` exists |
| MACD line-signal distance / convergence | MISSING | The distance **is** the histogram; it is classified only by sign |
| MACD zero-line position | PARTIAL | Derivable from `macd_line`, never classified |
| **RSI slope / direction / recovery from extremes / failure swings** | **MISSING** | All four named in `SPEC` §4.4 |
| RSI regime/range context | MISSING | Five fixed bands (30/45/55/70), asset- and timeframe-independent |
| **Volume: impulse / breakout / rejection / retest / consolidation volume** | **MISSING** | Volume is measured once per bar and never joined to an event |
| Price/volume disagreement | MISSING | — |
| **Volatility: realized range, compression/expansion events, contraction** | MISSING | Only an ATR-ratio band |
| **Fibonacci** (retracement, extension, anchors, confluence) | **MISSING** | Not named anywhere in `src/`, and **not named in `PROJECT_SPECIFICATION_V1.md` or the vision addendum either** — this is genuinely new scope |
| **Elliott Wave** | **MISSING** | Same — genuinely new scope, named in no approved source |
| **Opportunity state (WATCH LONG / WATCH SHORT)** | **PARTIAL — and closer than expected** | `DevelopingEvidenceState` = `DIRECTION_STATED` / `LEANING` / `DIVIDED` / `NONE_READABLE`, with a `lean` that names a side, already computed and already on the dashboard |
| **"What are we waiting for?"** | **PARTIAL — and closer than expected** | `Blocker` with five named kinds + `requirement` + `observed` + `source`, already computed and already rendered |

### 4.4 The six empty packages, measured

| Package | Lines | Math | `__all__` |
|---|---|---|---|
| `features/trend/` | 18 | none | `[]` |
| `features/momentum/` | 17 | none | `[]` |
| `features/volatility/` | 16 | none | `[]` |
| `features/market_structure/` | 20 | none | `[]` |
| `features/support_resistance/` | 16 | none | `[]` |
| `features/pattern_detection/` | 23 | none | `[]` |
| **total** | **110** | **none** | — |

These six are the *entire* Tier-2 layer the Feature Engine's own docstring advertises. They have been
placeholders since the Feature Engine was designed. **This is not rot — it is an honest, documented
skeleton.** Every one names its planned contents in a `TODO` list, and `features/__init__.py` states
plainly: *"No calculations exist yet — this milestone defines only the architecture that will hold
them."*

---

## 5. What the system genuinely understands today

Stated fairly, because the gap sections that follow would otherwise read as a condemnation of work
that is, in its own scope, excellent.

1. **Where price turned, and when that became knowable.** Confirmed swing pivots with an explicit
   confirmation delay that travels with the pivot as provenance. Plateaus resolve deterministically to
   one point. Equal highs separated by intervening structure stay two facts.
2. **Whether each turn was higher or lower than the last of its kind** — and that `EQUAL_HIGH` is its
   own fact, never folded into "higher" or renamed "double top".
3. **Whether structure has been shifting the same way repeatedly** — and, crucially, whether the
   evidence *conflicts* (`NEUTRAL`) or is merely *absent* (`INDETERMINATE`). Very few systems keep
   those apart.
4. **Whether a close has gone past the reference structural level on each side, once.**
5. **Whether the most recent such break opposed the one before it** (change of character), with a
   principled refusal to guess when a bar broke both sides.
6. **What the environment is like** — trending / ranging / transitioning, volatility band, participation
   band — computed by family vote where no number feeds two dimensions.
7. **Whether there was enough data to answer at all** — a genuine sufficiency gate that is about
   availability, never about agreement.
8. **How independent its own evidence is** — measured, declared with reasons, and *reported as not
   established* rather than assumed. This is rarer than everything above it.
9. **Which way the readable families lean even when the policy refuses** (`DevelopingEvidence`), and
   **which named gate stopped the reading** (`Blocker`) — both without ever presenting either as a
   trade.
10. **What changed since the last scan**, as structured state transitions, never prose diffs.

---

## 6. What the system is blind to today

Grouped by *why* it is blind, which is what makes the list actionable.

### 6.1 Blind because the computation does not exist

- **Location semantics.** A level is a price and a side. Nothing knows whether price has repeatedly
  respected it, rejected from it, accepted beyond it, or reclaimed it — nor whether two levels a few
  ticks apart are one area of interest.
- **Shape over time.** No impulse, no consolidation, no bounded range object, no compression event.
  The market is a sequence of pivots and a set of prices; it has no *phases*.
- **Rate of change of anything.** No slope, no acceleration, no "improving while still negative" —
  which is the exact case `SPEC` §4.2 uses as its worked example of why contextual interpretation is
  required.
- **Relationships between indicators and price over time.** No divergence of any kind.
- **Geometry.** No trendline, no channel, no pattern.
- **Joins between families at an event.** Volume is measured per bar; volatility is measured per
  window; a break is measured per level. Nothing asks *"what was volume doing at the bar that broke"* —
  and that join is where most of the information in technical analysis actually lives.

### 6.2 Blind because the computation is discarded

This is the more important half, because it is cheaper to fix.

- Every indicator value on every timeframe.
- The entire crossing history.
- Change of character.
- Nearest level above and below.
- The context-role level set (so a 1W zone can never matter).
- Setup-role and execution-role regime states (computed, used only as a *count* of insufficient
  dimensions, then dropped).
- All swings, labels and sequence-state history.
- Warm-up status per feature.

### 6.3 Blind by deliberate, correct policy — do not "fix" these

Recorded so that a future milestone does not mistake a decision for a gap.

- **No intrabar path.** OHLC cannot prove which of a bar's two extremes came first, and the repository
  refuses to pretend otherwise. This is right, and it constrains every pattern definition below.
- **No tolerance / epsilon anywhere.** Tolerance is a claim about instrument precision and belongs at
  ingestion behind a tick-size model that does not exist (ADR-0013 §4). **This is the single largest
  constraint on a zone engine** and §15 addresses it directly rather than working around it.
- **No probability.** `Probability` exists as a type and its only value is `NOT_CALIBRATED`.
- **No score, weight, rank or confidence** anywhere in the market half.
- **No direction outside `fmis.swing_setup`.**

---

## 7. What exists but is product-unreachable

The complete list, with the exact line where each dies.

| Fact | Computed at | Dies at | Survives as |
|---|---|---|---|
| `FeatureSet` (ema_20, ema_50, ema_200, rsi_close_14, atr_14, macd_close_12_26_9, relative_volume_20) × 3 roles | `structural_facts.py:429` | `compose.py:269` `build_setup_inputs` | **nothing** on the swing path. One `Alignment` enum, from the **setup role only** |
| `structure.crossings` × 3 roles | `structural_facts.py:348` | `compose.py:269` | a count on `fmits facts` (`render.py:243`); **nothing** above |
| `structure.changes` (CHoCH) × 3 roles | `structural_facts.py` | `compose.py:269` | a `TRANSITIONING` regime state; a `latest_change_of_character` string in `snapshotting` |
| `structure.swings` / `labelled` / `state_history` × 3 | `structural_facts.py` | `compose.py:269` | counts on `fmits facts` |
| `nearest_levels` × 3 | `structural_facts.py` | `compose.py:269` | two rows on `fmits facts`; `RoleReading` in `snapshotting` |
| **context-role `levels`** | `structural_facts.py` | `compose.py:269` | **nothing** — only setup and execution levels are passed |
| **setup-role `breaks`** | `structural_facts.py` | `compose.py:269` | **nothing** — only execution breaks are passed |
| setup- and execution-role `MarketRegime` | `compose.py:376` | `compose.py:196` | one integer: `dimensions_insufficient` |
| `warming_up` per role | `structural_facts.py` | `compose.py:269` | one integer in `ViewAdequacy` |
| `window` (fetched/closed/excluded/first/last) per role | `structural_facts.py` | `compose.py:269` | `closed_count` only |
| `AverageVolume` | never registered by default | — | — (DORMANT: implemented, tested, no production caller) |

**One function — `build_setup_inputs`, 75 lines — is where FMITS forgets almost everything it
computed.** It is not a badly written function; it is a deliberately narrow policy boundary
(`SetupInputs`' own docstring says so) that was correct when the policy read three things and is now
the reason the product cannot describe a market.

---

## 8. Information-loss seams

Traced end to end: provider → ingest → `CandleSeries` → `FeatureEngine` → market structure →
structural trend → levels → crossings → BOS → CHoCH → `StructuralFactSheet` →
`MultiTimeframeFactSheet` → regime → evidence → decision context → `SetupInputs` → `SetupAssessment` →
`SetupEvidenceReport` → `SymbolDecision` → `SymbolDecisionRow` → HTML.

Six seams, each classified as **computation missing** or **consumer drops it**, exactly as the brief
requires.

### Seam 1 — `FeatureEngine` returns latest values, never series
**Consumer drops it — and the producer never offered it.** `ema_series()` computes the whole series
and `FeatureResult` keeps `[-1]`. `FeatureValue` already permits `Sequence`, so no contract change is
needed. Recorded as review R5 on 2026-07-24, and referenced in reports 0002, 0003 and 0004 as the
`compute_series()` extension. **Nothing downstream can ever compute a slope, a rate of change, a
divergence or a compression event until this seam is opened.** It is the deepest seam in the report
and the one most likely to be under-estimated.

### Seam 2 — the evidence report is built for the SETUP role only
**Consumer drops it.** `compose.py:378` calls `_evidence_for(sheet.by_role[SETUP_ROLE].sheet)`. The
context (1W) and execution (4H) `FeatureSet`s are computed in full and **never classified at all**.
So "the weekly EMAs are stacked" and "the 4H RSI is recovering" are not merely unstated — they are
never even asked.

### Seam 3 — `build_setup_inputs`
**Consumer drops it.** Detailed in §7. Twenty-plus structured facts in; twenty-two narrow scalars and
two level tuples out.

### Seam 4 — `SetupAssessment` keeps at most three levels
**Consumer drops it.** Of the setup and execution level sets, exactly `stop`, one `target` and
`trigger.level` survive. Every other level — including the one price is currently consolidating
beneath — is gone. Everything else about the market becomes `thesis: tuple[str, ...]`, i.e. English.

### Seam 5 — states become prose at the assessment boundary
**Consumer drops it.** `confirmation`, `invalidation`, `thesis` and `regime_context` are all
`tuple[str, ...]`. `fmis.swing_setup.decision_summary` exists **specifically because** a later layer
was reduced to string-matching those sentences, and its docstring says so: *"Reading a conclusion back
out of a sentence a policy wrote is the inference this layer exists to remove."* That fix was applied
to two facts (the blocker and the developing lean). **Every other fact is still prose.**

### Seam 6 — three parallel evidence-state vocabularies
**Neither missing nor dropped — divergent.** Three enums express overlapping ideas:

| | supporting | conflicting | neutral-ish | unavailable | not-applicable |
|---|---|---|---|---|---|
| `decision_support.Alignment` | `UPWARD`/`DOWNWARD` | *(implicit)* | `NEUTRAL` | `UNAVAILABLE` | `NOT_DIRECTIONAL` |
| `market_regime.EvidenceStatus` | `CONSISTENT` | `CONFLICTING` | `CONTEXT` | `UNAVAILABLE` | — |
| `setup_evidence.SetupEvidenceStatus` | `SUPPORTING` | `CONFLICTING` | — | `UNAVAILABLE` | — (`MISSING` is a fourth idea) |

The brief's five requested states are **almost** present, spread across three vocabularies with three
different words for "reported but not counted". `MISSING` (*a named, readable condition that has not
happened yet*) is a genuinely good fourth idea the brief did not ask for and should keep. There is
**no** `NOT_APPLICABLE` anywhere.

### Seam 7 — the dashboard renders what it is given, and is given prose
**Consumer drops nothing.** `SymbolDecisionRow` carries `SymbolDecision` field for field, and
`SymbolDecision` carries what `SetupAssessment` and `SetupEvidenceReport` carry. **The dashboard is
not the problem and a dashboard redesign would not fix any of this.** This is stated explicitly
because the brief asks about UX: the page is thin because the model above it is thin.

### 8.1 The verdict the brief asks for

| Product gap | Computation missing | Consumer drops it |
|---|---|---|
| Resistance zone identified | ✅ | — |
| Consolidation beneath it | ✅ | — |
| Improving EMA geometry | ✅ (slope needs a series) | ✅ (values never leave the sheet) |
| Momentum cooling | ✅ (needs histogram ROC) | ✅ |
| Breakout not confirmed | — | ✅ (crossings are discarded) |
| Volume confirmed the prior move | ✅ (needs an event join) | ✅ |
| Price holding above reclaimed areas | ✅ (reclaim is undefined) | ✅ |

**Roughly half of the owner's example is already computed and thrown away.** That is the single most
useful sentence in this report for planning purposes.

---

## 9. Existing code that should be preserved and reused

**Do not rewrite any of this.** Each entry states what the new layer should consume from it.

| Package | Preserve because | New layers consume |
|---|---|---|
| `fmis.market_structure` | Non-repainting by construction; plateau policy is correct and argued; equal structure is first-class; ordering rules have exactly one implementation | Pivots, labels, and the ordering validator |
| `fmis.structural_trend` | Correctly separates conflict from absence; keeps its accumulator private so a run length cannot become a score | Trend as one family vote — **not** as an input to any break rule |
| `fmis.level_crossing` | **The most valuable under-used asset in the repository.** The nine-way crossing classification is exactly the substrate an interaction engine needs, it is exactly prefix-stable, and it reads at most one bar backwards | Touch counting, rejection counting, acceptance, reclaim, retest — all of it |
| `fmis.structure_break` | Close-only rule is right; eligibility-at-confirmation-bar is measured (0 violations vs 30); `bisect` fix already applied | Break events as anchors for retest windows |
| `fmis.change_of_character` | Correctly refuses to infer from a two-sided bar | Phase-transition anchoring |
| `fmis.market_regime` | **The template every new engine should copy**: family voting, one vote per family, nothing read by two dimensions, `UNAVAILABLE ≠ CONFLICTING`, no direction expressible | The pattern, not the code |
| `fmis.setup_evidence.correlation` | The only correlated-evidence machinery in the repository, and it works | Register every new family's correlations here |
| `fmis.swing_setup.decision_summary` | `DevelopingEvidence` and `Blocker` are **already the opportunity layer's two hardest parts** | Extend, do not replace |
| `fmis.features.indicators.*` | Wilder/SMA-seed conventions are explicit and tested | Keep the math; add a series accessor beside it |
| `fmis.series_context` | Identity propagation and mismatch rejection, once | Every new engine's identity check |
| `tests/architecture_tiers.py` | Tier partition forces every new package to be classified | Classify each new package PRODUCTION |

---

## 10. Existing code that should be corrected before extension

Three items. **None is a defect**; each is a decision whose cost is now being called in.

### 10.1 `Feature.compute()` returns a scalar — extend, do not replace
Add `compute_series(context) -> FeatureResult` **additively**, exactly as review R5 recorded in
2026-07. Do not change `compute()`. Do not change any existing feature's `name`, seeding convention
or metadata — the policy non-regression digest depends on `FeatureSet` `repr()` and must stay
byte-identical. This is a **prerequisite** for slope, ROC, divergence and compression, and it should
land as its own small milestone rather than inside a bigger one.

### 10.2 `PriceLevel.side` is intrinsic, so role flip is unrepresentable
`_SIDE_BY_LABEL` maps a swing high to `UPPER` permanently, and `PriceLevel.__post_init__` validates
`side` against provenance. That is correct for the *origin* of a level. It means a **zone** must be a
**new type in a new package**, referencing `PriceLevel`s rather than mutating them. Do not add a
mutable role to `PriceLevel`; do not make `side` optional. See §15.

### 10.3 `derive_level_crossings` is O(candles × levels), and levels grow with candles
`crossing.py:232-234` is a nested loop over candles × levels. Because `structural_levels` emits one
level per labelled swing, level count grows linearly with candle count — so the derivation is
effectively **O(n²) in candles today**. `structure_break` already fixed its own quadratic with
`bisect_right`; the crossing derivation has not been. It is invisible at current window sizes and
would not stay invisible under a historical replay or a larger universe. **Measure before optimising**
(§35), and do not touch it inside a feature milestone.

### 10.4 Three vocabulary guards will block a support/resistance engine — by design
- `tests/test_structural_facts.py:799` forbids `support` and `resistance` in the fact sheet's output.
- `tests/test_workspace_render.py:142` forbids `resistance` on the rendered `fmits swing` page, and
  asserts the page says *"Not support or resistance"*.
- `tests/test_market_structure_swings.py:122,585` forbids both tokens in `fmis.market_structure`.
- `market_regime.EvidenceStatus` chose the word `CONSISTENT` **specifically** to avoid the substring
  `support`.

These are not obstacles to route around. **They are the reason ADR-0019 §I exists**, and lifting any
of them for a specific, defined, evidence-based notion of role is exactly the kind of decision that
requires an ADR (§43). A zone engine that quietly renamed a level "support" without that decision
would be the single worst outcome of this milestone.

---

## 11. Proposed Technical Analysis architecture

### 11.1 Verdict on the brief's proposed decomposition

The brief's L3/L4/L5A–H/L7/L8/L9 decomposition is **broadly right and slightly over-split.** Four
changes are proposed.

**Change 1 — L5A and L5C merge into one engine.** The brief separates a Level & Zone Engine (L5A)
from a Breakout & Retest Engine (L5C). They cannot be separated: a zone's *strength* is its touch and
rejection history, and touches and rejections **are** interactions. Splitting them means either the
zone engine re-derives interactions (two implementations of one rule — the failure mode every ADR in
this repository is written to prevent) or the interaction engine owns zone state (the split achieves
nothing). **Propose: one `fmis.price_zones` engine owning zones and their interaction history.**

**Change 2 — L5D (impulse/consolidation/range) moves *before* L5B (trendlines).** Trendline anchor
selection is the hardest unsolved problem in the brief — *which* pivots anchor a line is exactly the
discretionary judgement that makes trendlines non-reproducible. An impulse/consolidation segmentation
gives anchor selection an objective scope (*the pivots inside this consolidation*), and without it,
anchor selection has no principled basis at all. **Propose: phase primitives before geometry.**

**Change 3 — L5G (dynamic indicator context) is blocked on a prerequisite the brief does not name.**
EMA slope, MACD histogram ROC and RSI slope all require indicator *series*. That is §10.1, and it must
be sequenced as its own item, not assumed.

**Change 4 — L5H (Fibonacci) and Elliott are not layers.** Fibonacci is a projection over an anchor
pair; Elliott is a hypothesis over a swing sequence. Giving either a layer number in the deterministic
stack asserts a standing they have not earned. **Propose: Fibonacci as an optional consumer of the
zone engine's confluence input; Elliott, if ever, as an L8 hypothesis with no vote.**

### 11.2 The proposed stack

```
L1  fmis.providers                     candles (unchanged)
L2  fmis.data / fmis.ingest            canonical closed candles (unchanged)

L3  fmis.features.indicators           EMA · RSI · MACD · ATR · volume
    + compute_series()                 ── PREREQUISITE (§10.1) ──
                                       the same math, exposed as a series

L4  fmis.market_structure              pivots · labels · sequence state   (unchanged)
    fmis.structural_trend              sustained direction                (unchanged)
    fmis.level_crossing                levels · 9-way interactions        (unchanged)
    fmis.structure_break               BOS                                (unchanged)
    fmis.change_of_character           CHoCH                              (unchanged)

L5  ── the new layer, five engines, each with one responsibility ──

    fmis.price_zones        NEW  zones from level clusters; interaction history
                                 (touch / rejection / acceptance / reclaim / retest);
                                 zone lifecycle; MTF confluence input
                                 consumes: level_crossing, structure_break, features(ATR)

    fmis.price_phases       NEW  impulse · retracement · consolidation · range ·
                                 compression / expansion events
                                 consumes: market_structure, features(ATR, volume series)

    fmis.indicator_context  NEW  slope · rate of change · consecutive runs ·
                                 spread · ordering · convergence · crossover events ·
                                 divergence anchors
                                 consumes: features.compute_series, market_structure

    fmis.trend_geometry     LATER trendlines · channels, anchored inside phases
                                 consumes: price_phases, market_structure

    fmis.chart_patterns     LATER flags · double tops · triangles, composed from
                                 phases + zones + geometry. Owns no primitive.

L6  fmis.market_regime               environment (unchanged)
    fmis.decision_context            sufficiency (unchanged)

L7  fmis.evidence                    the taxonomy (add families? see §25)
    fmis.decision_support            classification of L3/L5 readings

L8  fmis.market_opportunity   NEW    developing-opportunity state, orthogonal to
                                     the trade decision. Directional vocabulary lives
                                     here or in swing_setup — see §26/§43-D3.

L9  fmis.swing_setup                 the strategy policy (UNCHANGED THIS MILESTONE)

    fmis.risk_policy / position_sizing / portfolio_risk    (out of scope)
    execution                                              (does not exist; out of scope)
```

### 11.3 The rules every new L5 engine inherits

Copied from what the existing engines already enforce, not invented here:

1. **Closed candles only, always.**
2. **Never read forward.** State the earliest bar at which each fact becomes knowable.
3. **No direction.** `long`/`short`/`buy`/`sell`/`bullish`/`bearish` are banned by a repository-wide
   guard, and every new package is inside it.
4. **No score, weight, confidence, probability or rank** — in a value, a field name, or metadata.
5. **No tolerance without a stated, versioned policy object** (§35 and §15.3).
6. **One authoritative rule per concept, kept private.**
7. **A model may never contradict its own fields** — validate in `__post_init__`.
8. **Reject, never repair.** Unordered input is a caller bug.
9. **No global state, no cache, no clock, no randomness.**
10. **Delegate, never re-derive.** If a fact exists one layer down, consume it.
11. **Every engine declares its evidence family and its known correlations** (§25).
12. **Nothing below imports an L5 engine**, and an architecture guard asserts it.

---

## 12. Package and module ownership

**No `technical_analysis.py`. No `pattern_detector.py`.** One responsibility per package, explicit
inputs and outputs, no strategy opinion, no dashboard prose, no hidden state.

| Package | Owns | May import | Must never |
|---|---|---|---|
| `fmis.features.indicators` | indicator math, scalar **and series** | `fmis.data` | interpret anything |
| `fmis.price_zones` | zone identity, membership, interaction history, lifecycle | `fmis.data`, `level_crossing`, `structure_break`, `series_context`, `features` (ATR only) | name a side "support"; emit a direction; own a pattern |
| `fmis.price_phases` | impulse, retracement, consolidation, range, compression events | `fmis.data`, `market_structure`, `series_context`, `features` | own a zone; own a pattern; name a side |
| `fmis.indicator_context` | slope, ROC, run length, spread, ordering, crossover, divergence anchors | `features` (series), `market_structure`, `series_context` | read a level; read a zone; name a side |
| `fmis.trend_geometry` *(later)* | trendlines, channels | `price_phases`, `market_structure` | fit using future bars; own a pattern |
| `fmis.chart_patterns` *(later)* | pattern composition + lifecycle | `price_zones`, `price_phases`, `trend_geometry`, `indicator_context` | compute any primitive of its own |
| `fmis.market_opportunity` *(later)* | opportunity state, missing-confirmation description | every L5 engine, `market_regime`, `decision_context` | mutate `swing_setup`; produce a trade decision |
| `fmis.pipeline` | composition only | everything below | contain arithmetic (already guarded: `structural_facts` contains **no arithmetic operator at all**) |
| `fmis.operator_dashboard` | HTML | `swing_workspace` models | compute any market or monetary quantity (already guarded four ways) |
| `fmis.pipeline.cli` | argument parsing and printing | product surfaces | contain technical-analysis mathematics |

**AI consumes structured facts only.** No AI layer exists in the repository today. When one arrives,
it reads L5/L7/L8 objects and never a chart image, and it never produces a swing point, a zone, a
break, a divergence or a pattern state.

---

## 13. Dependency graph

Verified against the repository, and it differs from the brief's sketch in two places (marked ★).

```
                       CandleSeries  (closed candles only)
                             │
        ┌────────────────────┼─────────────────────────┐
        │                    │                         │
   indicators           detect_swings              volume/ATR
   (scalar)                  │                     (measurements)
        │                    ▼                         │
        │   ★ compare → label → sequence_state → state_history
        │                    │           │             │
        │                    │           └──► structural_trend
        │                    ▼                         │
        │            structural_levels                 │
        │                    │                         │
        │                    ▼                         │
        │            derive_level_crossings ◄──────────┘ (no dep; drawn to show
        │             (TOUCH/WICK/CLOSE ×                 they meet only in L5)
        │              WITHIN/GAPPED/ALREADY)
        │                    │
        │                    ├────► derive_structure_breaks ──► change_of_character
        │                    │
   ┌────┴────┐               │
   │         ▼               ▼
   │  ★ compute_series   ┌───────────────────┐        ┌──────────────────┐
   │  (PREREQUISITE)     │  fmis.price_zones │        │ fmis.price_phases│
   │         │           │  clusters, roles, │        │ impulse, consol- │
   │         │           │  interactions,    │        │ idation, range,  │
   │         │           │  lifecycle        │        │ compression      │
   │         ▼           └─────────┬─────────┘        └────────┬─────────┘
   │  fmis.indicator_context       │                           │
   │  slope · ROC · runs ·         │            ┌──────────────┘
   │  spread · crossover ·         │            ▼
   │  DIVERGENCE ANCHORS           │      fmis.trend_geometry
   │         │                     │      trendlines, channels
   │         │                     │            │
   │         └──────────┬──────────┴────────────┘
   │                    ▼
   │            fmis.chart_patterns
   │            flags · double tops · triangles · wedges · H&S
   │            (owns no primitive; composes only)
   │                    │
   └────────────────────┴──────────────► fmis.evidence / decision_support
                                                    │
                                                    ▼
                                         fmis.market_opportunity
                                                    │
                                                    ▼
                                            fmis.swing_setup
```

★ **Two corrections to the brief's sketch.**

1. The brief draws `confirmed swings → structural geometry → levels/zones → breakout semantics`.
   In the live repository, **levels come from *labelled* swings, not raw swings** — which means the
   **first swing high and first swing low have no level at all** (ADR-0019 D2). A zone engine
   inherits that hole. It is a real, documented limitation and §15.5 says what to do about it.
2. The brief places divergence downstream of "dynamic indicator context". It is better placed
   *inside* it: a divergence is an indicator-series extremum anchored to a **confirmed price pivot**,
   so it needs `market_structure` and `compute_series` and nothing else. Making it a separate engine
   would force it to re-derive anchoring.

**The one hard sequencing constraint:** `compute_series()` gates `indicator_context` entirely, which
gates divergences, EMA geometry, MACD dynamics and RSI context — i.e. **four of the brief's twelve
audit sections depend on one 30-line additive protocol extension.**

---

## 14. Core market facts vs contextual evidence vs hypothesis

The brief's three authority levels, mapped onto concrete proposed capabilities. **This table is the
spine of the anti-checklist requirement (§4 of the brief) and should be treated as a decision, not a
description.**

### Tier A — core market / price facts (deterministic, observable, may gate)

Closed candles · confirmed pivots · HH/HL/LH/LL/EQ · sequence state · structural trend · levels ·
**zones** · touch · wick breach · close breach · gap mechanism · BOS · CHoCH · **acceptance** ·
**rejection** · **reclaim** · **retest** · **range bounds** · raw volume · relative volume · ATR ·
realized range · MTF structure per role.

*Absence of a Tier-A fact is a real fact about the market and may legitimately gate a strategy.*

### Tier B — contextual / supporting evidence (deterministic, never gates alone)

EMA slope · EMA spread · EMA ordering · convergence rate · crossover recency · MACD histogram
direction · MACD ROC · consecutive improvement runs · RSI slope · RSI recovery-from-extreme ·
divergence · volume expansion/contraction at an event · volatility compression/expansion · chart
patterns · Fibonacci confluence (if approved).

*Absence of a Tier-B item is **`NOT_APPLICABLE` or `UNAVAILABLE`, never `CONFLICTING`.** This must be
enforced structurally, not documented — see §25.4.*

### Tier C — hypothesis-level interpretation (never deterministic truth, never a gate, never a vote)

Elliott candidate counts · alternative counts · ambiguous discretionary pattern readings · any
framework where multiple valid interpretations coexist.

*Multiple candidates must be representable simultaneously. "No credible interpretation" is a normal,
first-class result. **The system must be fully functional with Tier C entirely absent**, and a test
should assert that removing every Tier-C input changes no `SetupState` on the 81-fixture matrix.*

### 14.1 The anti-checklist rule, stated as an invariant

> **No Tier-B or Tier-C item may ever be a necessary condition for an opportunity or a trade
> decision, unless a specific, named, versioned strategy explicitly declares it.**

Concretely, none of these may ever be written:

```
no Elliott count  → no LONG          ✗   no Fibonacci confluence → no LONG   ✗
no RSI divergence → no LONG          ✗   no EMA crossover        → no LONG   ✗
no bull flag      → no LONG          ✗
```

The existing policy already satisfies this — its only hard gates are the decision-context sufficiency
check (a *data* condition) and the context-role regime (a Tier-A condition). **The risk this milestone
introduces is that a new engine's absence quietly becomes a gate**, and §25.4 proposes the structural
defence.

---

## 15. Support / resistance architecture

### 15.1 The question that must be answered first

**Does FMITS have support/resistance semantics today? No — and deliberately so.** It has
`PriceLevel`: a price, an intrinsic side derived from the swing type that produced it, and provenance.
ADR-0019 §I reserves the *interpretation* for a later layer, three tests enforce it, and
`NearestLevels`' own docstring explains why the level below the close is not called support.

The brief's warning is therefore already the repository's accepted position, and the proposed design
holds it: **role is a function of interaction history, never of position relative to price.**

### 15.2 Proposed model — `fmis.price_zones`

Four types.

**`ZoneMember`** — one `PriceLevel` inside a zone, by reference. Carries the level's own provenance
unchanged.

**`PriceZone`** — a bounded price band formed from one or more clustered `ZoneMember`s.

| Field | Meaning | Deterministic from |
|---|---|---|
| `low`, `high` | the band | member level prices |
| `members` | the clustered levels, by reference | `structural_levels` |
| `established_index` | the bar at which the **last** member became knowable | `max(origin.index + origin.confirmation_bars)` |
| `width_policy` | which named policy produced the band | a versioned policy object |
| *(no `role` field)* | — | role is on the **reading**, not the zone |

**`ZoneInteraction`** — one bar's interaction with one zone, derived **entirely from existing
`LevelCrossingEvent`s** plus the zone bounds. This is the type the whole design turns on:

| Interaction | Deterministic definition | Built from |
|---|---|---|
| `TOUCH` | the bar's range met the band without closing beyond it | `CrossingKind.TOUCH` / `WICK_BREACH` |
| `REJECTION` | the bar's extreme entered or passed the band and the close returned to the origin side | `WICK_BREACH` + close test |
| `CLOSE_BEYOND` | the bar closed on the far side of the band | `CLOSE_BREACH` |
| `ACCEPTANCE` | `N` consecutive closes beyond the band, `N` from a named policy | a run over `CLOSE_BEYOND` |
| `RECLAIM` | a `CLOSE_BEYOND` in the direction opposite a previously accepted one | the interaction sequence |
| `RETURN_INSIDE` | a close back within the band after a `CLOSE_BEYOND` | the interaction sequence |
| `ARRIVED_WITHOUT_TRADING` | the bar was wholly beyond and its predecessor was not | `CrossingMechanism.GAPPED_BEYOND` |

**`ZoneReading`** — a zone's state **as of one bar**, which is where role finally appears:

| Field | Values |
|---|---|
| `position` | `PRICE_ABOVE` / `PRICE_BELOW` / `PRICE_INSIDE` — *geometry only, explicitly not a role* |
| `role` | `HELD_FROM_BELOW` / `HELD_FROM_ABOVE` / `BROKEN_UPWARD` / `BROKEN_DOWNWARD` / `ROLE_FLIPPED` / `UNTESTED` / `INDETERMINATE` |
| `touch_count`, `rejection_count` | integers over the interaction history |
| `last_interaction_index`, `bars_since` | recency, as counts — **never a "freshness" verdict** |
| `established_index` | earliest bar the zone was knowable |

**`role` is derived from `interactions`, never from `position`.** `UNTESTED` is the honest state for a
zone price has never met — and it is *not* the same as `INDETERMINATE`, which means the interactions
exist but do not resolve. **A zone above price with no interaction history is `UNTESTED`, not
resistance.** That single rule is what the brief §9 asks for.

### 15.3 The tolerance problem — the hardest decision in this milestone

Clustering requires a distance test, and this repository **has no tolerance anywhere, on principle**
(ADR-0013 §4; the crossing package restates it; `classify_comparison` restates it again). Three
options:

| Option | Assessment |
|---|---|
| **A. Exact prices only** | Every level is its own zone. Correct, useless: two swings 0.02% apart are one area to any trader and two zones here |
| **B. A fixed percentage band** | **Reject.** An invented threshold, asset-dependent, timeframe-dependent, and precisely the "arbitrary threshold" §35 forbids |
| **C. A named, versioned `ZoneWidthPolicy` object carrying an ATR multiple, computed from the same series** | **Recommended** |

Option C keeps every existing guarantee: the policy is an explicit object (like `RegimePolicy`), it is
stamped on every zone (`width_policy`), so a historical zone is reproducible from its own record;
the multiple is a **stated hypothesis requiring research**, not a truth; and the tolerance is derived
from the instrument's own measured volatility rather than asserted about its tick size — which is
exactly the objection ADR-0013 raises against a percentage band.

**This requires an ADR** (§43-D1). It is a real weakening of a real principle, made deliberately, for
a stated reason, with the parameter versioned and the research question named.

### 15.4 What the zone engine must never do

- Call a zone "support" or "resistance" in any value, field name or rendered string **until an ADR
  decides the vocabulary** (§10.4).
- Assign a role from position.
- Emit a strength score, a rank, or a numeric "quality".
- Emit a direction.
- Delete a zone. Zones become `UNTESTED`/`BROKEN`/stale by policy and stay auditable.

### 15.5 Inherited limitations, carried forward and stated

- **ADR-0019 D2** — the first swing high and first swing low produce no level, so the earliest zone on
  each side is missing. A zone engine inherits this exactly. *Recommendation: inherit it and state it
  on the zone set, rather than widening `LevelOrigin.label` speculatively as ADR-0019 declined to do.*
- **ADR-0020 D5** — the break reference is the most recent eligible level, not the most extreme. A
  zone engine should compute its own reference from zone state and **not** reuse the break rule.
- **No intrabar path** — a bar that touches and then breaks a zone has no provable order, so
  `ZoneInteraction` must never claim a sequence within one bar.

---

## 16. Trendline and channel architecture

**Recommendation: DEFER to after `price_phases`. Do not build in the first slice.**

### 16.1 Why it is harder than it looks

Every other capability in this report has a definition that does not require a choice. A trendline
requires **anchor selection**, and anchor selection has no objectively correct answer: given twelve
pivots, which two (or three) define "the" trendline is exactly the discretionary judgement the
repository exists to remove. A naive "fit a line to the last N lows" changes its answer on every new
bar — the definition of repainting, wearing a different name.

### 16.2 The design that would be acceptable

If built later, a trendline must be an **anchored, immutable object**, not a fit:

| Property | Rule |
|---|---|
| Anchors | exactly the **confirmed pivots** that define it, by reference, never re-fitted |
| Scope | anchors must lie **inside one `price_phases` segment**, which is what makes selection objective rather than free |
| Minimum anchors | 2 to define; a third **touch** promotes state, never redefines the line |
| Observable from | `max(anchor.index + anchor.confirmation_bars)` — the bar the last anchor became knowable |
| Projected value | `slope × (bar − anchor0.index) + anchor0.price`, pure arithmetic |
| Touch | a bar whose range met the projected value within a named `TouchTolerancePolicy` (same ATR-derived mechanism as §15.3) |
| Break | a **close** beyond the projected value — same discipline as `structure_break` |
| Retest / failed break | readings over the interaction sequence, exactly as for zones |
| Immutability | **a line, once created, never changes.** A newer pivot creates a **new** line; it never re-anchors an existing one |

A channel is then two trendlines sharing a slope band, with `width` and a compression/expansion
reading over time. Horizontal channels are already better served by `price_phases.RANGE` and should
**not** be duplicated as a channel type.

### 16.3 Combinatorics — the reason for the phase constraint

With 143 confirmed levels at a production 500-bar window (measured, §35), unconstrained pairwise
anchor enumeration is 10,153 candidate lines **per side per view**, before any touch test. Scoping
anchors to one consolidation segment reduces this to tens. **This is the second reason phases must
come first, and it is a stronger one than the definitional argument.**

---

## 17. Breakout / retest architecture

**This is the highest-value, lowest-risk new capability in the entire report, and it is mostly
already computed.**

### 17.1 The full vocabulary, and where each term comes from

The brief asks the architecture to distinguish *crossed · breached · closed beyond · accepted beyond ·
retested · reclaimed · failed*. Every one is derivable. Six of nine need **no new bar-level
computation at all** — only the interaction sequence the repository already produces and throws away.

| Concept | Definition | New computation? |
|---|---|---|
| **touch** | `CrossingKind.TOUCH`, or a `WICK_BREACH` whose extreme met the band | **no** |
| **wick breach** | `CrossingKind.WICK_BREACH` | **no** |
| **close beyond** | `CrossingKind.CLOSE_BREACH` | **no** |
| **arrived without trading** | `CrossingMechanism.GAPPED_BEYOND` | **no** |
| **rejection** | extreme entered/passed the band, close returned to the origin side | **no** (a close comparison over an existing event) |
| **acceptance** | `N` consecutive `CLOSE_BEYOND` on the same side, `N` from a named policy | **no** (a run over the sequence) |
| **retest** | a `TOUCH` or `REJECTION` on the far side of a zone **after** an acceptance, within a named window | **no** |
| **failed retest** | a retest followed by a `RETURN_INSIDE` | **no** |
| **reclaim** | a `CLOSE_BEYOND` opposing a prior acceptance | **no** |
| **false breakout** | a `CLOSE_BEYOND` followed by `RETURN_INSIDE` **without** reaching acceptance | **no** |
| **breakout failure** | acceptance followed by `RETURN_INSIDE` and then a close beyond the opposite side | **no** |
| **distance beyond, ATR-normalised** | `(close − zone.high) / atr` | **yes** — trivial, needs ATR on the same sheet (already there) |
| **time spent beyond** | bar count since the first `CLOSE_BEYOND` | **no** |
| **breakout volume expansion** | `relative_volume` **at the breaking bar** | **yes** — needs volume **series** (§10.1), not just the latest value |

Two of fourteen need new computation, and one of those two is a single subtraction.

### 17.2 Why `close > level` is explicitly *not* the definition

The brief warns against reducing breakout to `close > level`. The repository already agrees, at the
primitive layer: `CrossingKind` is *"deliberately absent: BOS, CHOCH, BREAK, SWEEP, REJECTION,
FAKEOUT, CONFIRMED, INVALID, STRONG, WEAK — each is a reading of the fact rather than the fact."*
The proposed engine adds exactly those readings, **in a layer above**, leaving the primitive
untouched.

### 17.3 Non-repainting

Every interaction above depends on bar `i` and bars `< i`, plus a zone whose `established_index` is
already `≤ i`. **Nothing reads forward.** Acceptance and retest introduce a *confirmation delay* (you
cannot know a breakout was accepted until `N` further bars closed) — and that delay is **honest and
must be reported on the reading**, exactly as `confirmation_bars` is reported on a pivot. Prefix
stability is therefore exact, and should be measured over seeded prefixes the way `structure_break`'s
was (0 violations over 40 fixtures).

---

## 18. Impulse / consolidation / range primitives

**`fmis.price_phases` — the reusable substrate every pattern needs.** The brief is right that these
must precede patterns; the evidence for that is that a bull flag, a pennant, a rectangle, a
descending triangle and a rising wedge are **all** "impulse, then a bounded retracement with a
constrained slope, then a boundary test", differing only in the constraints. Building the patterns
first means writing that decomposition five times.

### 18.1 Proposed segmentation

A pure function over confirmed pivots (with ATR for normalisation) yielding a **non-overlapping,
exhaustive, ordered** segmentation of the closed-bar sequence.

| Segment | Definition sketch (all thresholds are **research parameters**, not decided here) |
|---|---|
| `IMPULSE` | a run of same-direction structural movement whose ATR-normalised displacement exceeds a policy multiple within a duration bound |
| `RETRACEMENT` | movement opposing the preceding impulse, whose depth as a fraction of that impulse is below a policy bound |
| `CONSOLIDATION` | a bounded segment whose ATR-normalised range is below a policy multiple, for at least a policy duration |
| `RANGE` | a consolidation with **two or more** touches of each boundary — i.e. a consolidation that has been *tested*, which is a strictly stronger fact |
| `UNDEFINED` | the honest state. A segmentation that always produces a phase is a segmentation that means nothing |

### 18.2 Derived measures on every segment

`direction_of_structure` (not a market direction — which way the pivots moved) · `magnitude` ·
`atr_normalised_magnitude` · `duration_bars` · `boundary_high` / `boundary_low` · `width` ·
`atr_normalised_width` · `slope_of_boundaries` · `pivot_count` · `retracement_depth_fraction` ·
`volatility_trend` (contraction / expansion / neither) · `volume_trend` (contraction / expansion /
neither, once volume series exist).

### 18.3 What this buys immediately, before any pattern is built

- *"price is consolidating beneath a zone"* — a `CONSOLIDATION` segment whose `boundary_high` lies
  within/below a zone. **This is one of the two facts the owner's BTC example needs, and it needs no
  pattern engine at all.**
- *"the prior move was a strong impulse"* — an `IMPULSE` segment with a high ATR-normalised magnitude.
- *"volatility is compressing"* — a contraction reading on the current segment.
- *"this is a range, not a trend"* — a `RANGE` segment, with actual bounds, unlike
  `market_regime.RANGING` which is a whole-timeframe label with no coordinates.

### 18.4 The `UNDEFINED` requirement

`UNDEFINED` must be common in real data and a test must assert it occurs. A phase engine that labels
every bar is a phase engine that has learned to say nothing precisely.

---

## 19. Pattern architecture

**Recommendation: build no pattern in this milestone. Classify each, decide the order, and stop.**

### 19.1 Classification

Criteria: product usefulness · objective definability · dependency readiness · validation difficulty ·
false-positive risk · overlap with simpler primitives · parameter-explosion risk.

| Pattern | Value | Objectively definable? | Overlaps a primitive? | FP risk | Verdict |
|---|---|---|---|---|---|
| **Range / rectangle continuation** | HIGH | **yes** — it *is* `price_phases.RANGE` | **completely** | LOW | **Do not implement as a pattern.** It is a phase |
| **Bull / bear flag** | HIGH | yes, once phases exist | high — impulse + consolidation + boundary break | MEDIUM | **First pattern, after phases** |
| **Pennant** | MEDIUM | yes | very high — a flag with converging boundaries | MEDIUM | **Fold into flag** as a boundary-slope variant; do not make it a second detector |
| **Double bottom / double top** | HIGH | **yes, and best of all** — it is almost pure `EQUAL_HIGH`/`EQUAL_LOW` structure + a neckline break | moderate | LOW–MED | **Second pattern.** Cheapest real pattern in the repository |
| **Ascending / descending triangle** | MEDIUM | yes — a flat zone boundary + a sloped trendline | high | MEDIUM | **DEFER** — needs `trend_geometry` |
| **Symmetrical triangle** | LOW–MED | weakly — two sloped lines, both anchor-dependent | high | **HIGH** | **DEFER**; adds little over "consolidation with compression" |
| **Rising / falling wedge** | LOW–MED | weakly | high | **HIGH** | **DEFER** |
| **Head & shoulders / inverse** | MEDIUM | partially — five pivots, ambiguous symmetry rules | moderate | **HIGH** | **DEFER**; the most over-claimed pattern in retail TA |
| **Triple top / bottom** | LOW | yes | **almost total** with double | MEDIUM | **REJECT for v1** — a double with a third touch; report the touch count instead |
| **V-top / V-bottom** | LOW | no useful definition beyond "a sharp pivot" | total with `IMPULSE` reversal | **VERY HIGH** | **REJECT** |
| **Rounded top / bottom** | LOW | no | — | **VERY HIGH** | **REJECT** |
| **Candlestick catalogue** | LOW as a catalogue | yes individually | — | **VERY HIGH** in isolation | **REJECT as a catalogue** — see §22 |

### 19.2 The single most important pattern decision

**Two of the "patterns" the brief lists are not patterns — they are primitives wearing a pattern's
name.** A rectangle is a range. A triple top is a double top with a touch count. Implementing either
as a detector would create a second definition of a fact a primitive already owns, which is the exact
failure mode every ADR in this repository is written to prevent.

---

## 20. Pattern lifecycle

The brief proposes `POTENTIAL / FORMING / MATURE / CONFIRMED / FAILED / INVALIDATED / EXPIRED` and
invites simplification. **Simplify to five.**

| Proposed state | Verdict |
|---|---|
| `POTENTIAL` vs `FORMING` | **Merge.** No deterministic event distinguishes them. Two names for one state is how a lifecycle starts lying |
| `MATURE` | **Drop.** "Mature" is a quality judgement — a score wearing an enum's clothing, and `setup_evidence` already rejected exactly that shape |
| `FAILED` vs `INVALIDATED` | **Keep both.** They are genuinely different: `FAILED` = the pattern completed and the thesis did not hold; `INVALIDATED` = the geometry stopped being true before completion |

### 20.1 The recommended lifecycle

| State | Entered when | Observable at | Historic state can change? |
|---|---|---|---|
| `FORMING` | every structural precondition holds; the completing event has not occurred | the bar the last required pivot became knowable (`index + confirmation_bars`) | **no** |
| `CONFIRMED` | the named completing event occurs (a close beyond the pattern's own boundary) | the closing bar | **no** |
| `INVALIDATED` | a geometric precondition ceases to hold **before** confirmation | the invalidating bar | **no** |
| `FAILED` | after `CONFIRMED`, price returns beyond the completion boundary within a named window | the returning bar | **no** |
| `EXPIRED` | no completing event within a named maximum age | the expiry bar | **no** |

### 20.2 The non-repainting requirement, stated as a testable invariant

> A pattern occurrence is an **append-only sequence of dated state transitions**, never a mutable
> object. `PatternOccurrence.states` is a tuple of `(state, bar_index)`. A pattern whose state at bar
> `i` was `FORMING` **still reads `FORMING` at bar `i`** after ten more bars close.

The property test: for every prefix `k`, the pattern history derived over `candles[:k]` equals the
full history truncated to bars `< k`. **Measured, like `structure_break`'s 0-violations-over-40-prefixes
result — not asserted.**

**"Pattern updated" is the disguise repainting wears.** A transition is a new entry; a pattern is
never edited.

### 20.3 Bull / bear flag — the decomposition standard (§15 of the brief)

Not implemented here. Recorded as the standard any future implementation must meet.

| Primitive | Owner | Deterministic? | Parameter class |
|---|---|---|---|
| prior impulse exists | `price_phases.IMPULSE` | yes | — |
| impulse direction of structure | `price_phases` | yes | — |
| impulse magnitude | `price_phases` | yes | — |
| **magnitude ÷ ATR ≥ M** | `price_phases` | yes | **research parameter `M`** |
| impulse duration within `[a, b]` | `price_phases` | yes | **research parameters `a`, `b`** |
| retracement follows the impulse | `price_phases.RETRACEMENT` | yes | — |
| **retracement depth ≤ D of impulse** | `price_phases` | yes | **research parameter `D`** |
| retracement duration within `[c, d]` | `price_phases` | yes | **research parameters** |
| consolidation boundary slope opposes the impulse | `trend_geometry` **or** a pivot-regression inside the phase | yes | engineering tolerance |
| consolidation width ÷ ATR ≤ W | `price_phases` | yes | **research parameter `W`** |
| swing sequence inside the consolidation | `market_structure` | yes | — |
| volatility contraction | `price_phases` | yes | **research parameter** |
| volume contraction | `price_phases` (needs volume series) | yes | **research parameter** |
| breakout boundary | the consolidation's own boundary | yes | — |
| breakout confirmation | `price_zones` interaction (`CLOSE_BEYOND`/`ACCEPTANCE`) | yes | **research parameter `N`** |
| invalidation | close beyond the opposing boundary | yes | — |
| expiration | maximum bars in `FORMING` | yes | **research parameter** |

**Nine research parameters for one pattern.** That number is the argument for §34's ordering: a flag
built before phases exist would bury all nine inside a detector where none of them could be varied,
measured, or versioned.

**Bearish symmetry is mandatory and structural.** The definition must be written once over a
`direction_of_structure` value and applied to both, never as two mirrored code paths — the exact
discipline `market_regime` uses when it treats `SUSTAINED_HIGHER` and `SUSTAINED_LOWER` identically
with no branch distinguishing them, and asserts it with a swap test. `docs/analysis-notes.md` records
that asymmetric mirrored checklists were the largest single cause of the v2 LONG bias.

### 20.4 Double top / bottom — the decomposition standard (§16 of the brief)

| Primitive | Owner | Notes |
|---|---|---|
| first extreme | `market_structure` confirmed pivot | — |
| intervening opposite pivot | `market_structure` | **required** — two highs with nothing between them are one plateau, which `detect_swings` already resolves to one point |
| second extreme | `market_structure` confirmed pivot | — |
| **price similarity** | new | `EQUAL_HIGH`/`EQUAL_LOW` gives the exact case free; near-equality needs the **same ATR-derived tolerance policy as §15.3 — one mechanism, not a second one** |
| minimum / maximum separation in bars | new | **research parameters** |
| neckline | the intervening pivot's price | — |
| rejection behaviour at each extreme | `price_zones` interaction history | reuses the zone engine |
| **confirmation** | a **close** beyond the neckline | reuses the crossing rule |
| failure | return beyond the neckline after confirmation | — |
| invalidation | a close beyond both extremes before neckline break | — |

`FORMING` (two extremes, no neckline break) and `CONFIRMED` (neckline broken on a close) are the
`POTENTIAL` / `CONFIRMED` distinction the brief asks for, using the existing lifecycle rather than a
second vocabulary. Mirrored exactly for bottoms, by the same one-definition rule.

### 20.5 Head & shoulders, triangles, wedges (§17 of the brief)

Decompositions recorded; **all DEFER**.

| Pattern | Anchors | Constraints | Boundary | Ambiguity — the reason to defer |
|---|---|---|---|---|
| H&S | 5 pivots (L shoulder, head, R shoulder + 2 troughs) | head beyond both shoulders; shoulder similarity; **time symmetry** | neckline through the two troughs | **Shoulder similarity and time symmetry have no non-arbitrary definition.** Two of five constraints are pure judgement, and the pattern is the single most over-claimed shape in retail TA |
| Ascending triangle | flat upper boundary + rising lower anchors | ≥2 upper touches, ≥2 rising lows | the flat boundary | Adds little over *"consolidation beneath a tested zone with a rising floor"*, which zones + phases already state |
| Descending triangle | mirror | mirror | mirror | same |
| Symmetrical triangle | two converging sloped lines | both anchor-dependent | apex-directed | **Both boundaries are anchor-selection problems.** Strictly worse than "consolidation with volatility contraction", which is objective |
| Rising / falling wedge | two same-direction converging lines | convergence rate | boundary break | same, plus a contested directional reading |

**Recommendation: implement none of these until zones, phases and geometry exist and have been
validated — and then re-ask whether each adds information beyond them.** For symmetrical triangles and
wedges the honest expectation is that it will not.

---

## 21. Divergence architecture

**Recommendation: APPROVE the design; sequence it after `compute_series()`; it is the highest-value
Tier-B capability.**

### 21.1 Why it is high value here specifically

`SPEC` names divergence in §4.2 and §4.4; the vision addendum names it; `features/momentum`'s TODO
names it. And structurally it is the **only** proposed Tier-B capability whose evidence is not a
restatement of trend — it compares price structure against an oscillator's own structure, which is
genuinely different information from "price is above its EMA".

### 21.2 The design, answering each of the brief's questions

| Question | Answer |
|---|---|
| Which price swings anchor it? | **Confirmed `SwingPoint`s only** — never an indicator extremum found independently. This is what makes the anchor non-repainting for free |
| Which indicator values correspond? | The indicator series value **at the pivot's own bar index**. Aligned by index, never searched |
| Temporal mismatch allowed? | **None.** Index alignment is exact. Searching a ±k window for a "nearby" indicator extremum is where divergence detectors start repainting |
| What counts as meaningful? | Price and indicator relations **disagree in sign** between two consecutive same-type pivots — `HIGHER_HIGH` on price with a lower indicator value, and the three mirrors |
| Regular vs hidden | Regular: price extends, indicator does not. Hidden: price retraces, indicator extends. Both fall out of the same 2×2 sign table — **one definition, four readings, no separate detector** |
| When confirmed? | At `max(pivot.index + pivot.confirmation_bars)` of the two anchors — the bar the **second** anchor became knowable |
| When does it expire? | After a named maximum age in bars — a **research parameter** |
| When invalidated? | When a third same-type pivot forms that resolves the disagreement |
| How is repainting prevented? | Anchors are confirmed pivots and the indicator value is read at the anchor's own index. Both were settled before the divergence was emitted. **Prefix stability is inherited, not engineered** |
| How are trivial divergences filtered? | **Do not filter — report the magnitudes.** A minimum-magnitude threshold is a research parameter, and pre-filtering destroys the data needed to choose it. Carry `price_delta` and `indicator_delta`; let a strategy threshold them |

### 21.3 The non-negotiable rule

**Divergence is Tier B. `NO_DIVERGENCE` is a normal, common, first-class result and must map to
`NOT_APPLICABLE` or `NEUTRAL`, never to `CONFLICTING`.** No divergence may ever be a required
condition for an opportunity or a decision (§14.1).

### 21.4 Advanced variants

Multi-swing, triple and failed divergence: **DEFER.** Each multiplies the anchor-pair space and none
has a stable definition. Two-anchor regular and hidden divergence on RSI and MACD is four readings
from one table and is enough.

---

## 22. EMA / MACD / RSI contextual architecture

All three live in one package, `fmis.indicator_context`, because all three need exactly one thing that
does not exist: an indicator **series**.

### 22.1 The prerequisite, stated once more

```
Feature.compute(context)         -> FeatureResult        (latest value)      EXISTS
Feature.compute_series(context)  -> FeatureResult        (Sequence value)    DOES NOT EXIST
```

`FeatureValue` already permits `Sequence`. `ema_series()` already computes the whole series. **The
gap is an accessor, not an algorithm.** Everything in §22.2–§22.4 is blocked on it, and nothing else
is.

### 22.2 EMA context

| Reading | Definition | Notes |
|---|---|---|
| value, price-vs-EMA | exists today | — |
| **distance** | `close − ema` | `SPEC` §3.1 asks for it; nothing computes it |
| **normalised distance** | `(close − ema) / atr` | comparable across assets and timeframes |
| **slope** | `ema[i] − ema[i−k]` over a named `k` | `k` is an **engineering choice**, stated and versioned |
| **normalised slope** | `slope / atr` | — |
| ordering / stacking | the ordinal arrangement of 20/50/200 | 6 arrangements; a **state**, not a score |
| spread | pairwise differences | — |
| normalised spread | spread ÷ ATR | — |
| convergence / divergence | sign of the change in `|spread|` | — |
| **rate of convergence** | `Δ|spread| / bar` | — |
| crossover event | the bar the ordering of a pair changed | non-repainting: a closed-bar fact |
| bars since crossover | count | a **fact**, not a freshness verdict |
| reclaim / rejection | `price_zones` interactions against the EMA **as a moving boundary** | reuses the zone interaction vocabulary — **one mechanism for static and dynamic boundaries** |
| compression | all spreads below a policy multiple of ATR | **research parameter** |

**The prophecy rule, and how to enforce it structurally.** The brief is right that *"golden cross
approaching"* must not become a forecast. The defence is not a naming convention: **no type in the
package may have a field whose value refers to a bar index greater than the current one.** A
convergence rate is a measured past; a projected crossing bar is a forecast. An architecture test
should assert no identifier in the package matches `predict|forecast|approach|imminent|will_|expected_`.

### 22.3 MACD context

`SPEC` §4.2 is the most specific paragraph in the whole specification and the least implemented. All
seven of its named items become derivable at once:

| Reading | Definition |
|---|---|
| histogram direction | sign of `hist[i] − hist[i−1]` |
| histogram rate of change | `hist[i] − hist[i−1]`, and the second difference for acceleration |
| **consecutive improvement / deterioration** | run length of same-signed histogram changes |
| line-signal distance | **is** the histogram; report it as a magnitude, not only a sign |
| convergence / divergence of the lines | sign of the change in `|hist|` |
| zero-line position | sign of `macd_line` — a **separate fact** from the histogram sign |
| acceleration / deceleration | second difference of the histogram |

**The `SPEC` §4.2 worked case, made representable.** *"A negative histogram that is rapidly improving
must not automatically be treated as bearish."* Today the system computes exactly
`classify_sign(hist) → NEGATIVE → Alignment.DOWNWARD`. With the readings above, that same bar reads
as `histogram_sign=NEGATIVE`, `histogram_direction=IMPROVING`, `improvement_run=4`,
`zero_line=BELOW` — four distinguishable facts where there is currently one. **This single change is
the clearest example in the report of the difference between what FMITS computes and what it
understands.**

### 22.4 RSI context

| Reading | Definition |
|---|---|
| level, zone | exists today (5 fixed bands) |
| **direction / slope** | `rsi[i] − rsi[i−k]` |
| **recovery from extreme** | the bar RSI left `OVERSOLD_ZONE`/`OVERBOUGHT_ZONE`, plus bars since |
| **failure swing** | a definable structural reading over the RSI series' own pivots |
| range context | the observed min/max over a named window — **which is what makes 30/70 asset-specific rather than universal** |
| divergence | §21 |
| structural context | the RSI reading at a confirmed price pivot |

**Oversold is not a buy, and the repository already enforces that structurally**: `RsiZone` maps to
`Alignment.NOT_DIRECTIONAL`, so it is reported and then excluded from directional grouping. That
property must survive — new RSI readings are Tier B and must not acquire a vote.

### 22.5 The correlation warning that must be registered

Every reading in §22.2–§22.4 is derived from the **same closes**. EMA slope, MACD histogram direction
and RSI slope on one timeframe are three views of one price series' recent direction. **They must be
declared correlated in `fmis.setup_evidence.correlation` at the moment they are introduced**, not
afterwards — otherwise this milestone re-creates, in a new place, the exact indicator-count bias the
repository has spent four milestones measuring and containing.

---

## 23. Volume and volatility architecture

### 23.1 The one structural change both need

Volume and volatility are currently **per-window measurements**. Their information lives in
**per-event joins**: volume *at the breaking bar*, volatility *across the consolidation*. Both need
series (§10.1), and both then become properties of a `ZoneInteraction` or a `PhaseSegment` rather than
standalone readings.

| Reading | Attaches to | New computation |
|---|---|---|
| relative volume at a breaking bar | `ZoneInteraction` | needs volume series |
| impulse volume | `PhaseSegment(IMPULSE)` | mean relative volume over the segment |
| consolidation volume contraction | `PhaseSegment(CONSOLIDATION)` | trend of relative volume over the segment |
| retest volume | `ZoneInteraction(retest)` | — |
| rejection volume | `ZoneInteraction(REJECTION)` | — |
| volume expansion / contraction | `PhaseSegment` | sign of the segment's volume trend |
| volume anomaly | `PhaseSegment` | **research parameter**; report the ratio, classify later |
| realized range | `PhaseSegment` | `max(high) − min(low)` |
| ATR-normalised range | `PhaseSegment` | — |
| volatility contraction / expansion | `PhaseSegment` | trend of ATR or realized range |
| price/volume disagreement | `PhaseSegment` | **DEFER** — no non-arbitrary definition; name the research question |

### 23.2 Two rules

- **ADR-0010 stands: measurement and interpretation stay separate.** A relative volume of 3.0 means
  different things for a 24/7 perpetual and an HKEX share with a closing auction. The engines compute;
  interpretation is a per-consumer decision.
- **Low volatility is not a direction.** `VolatilityState` is already `NOT_DIRECTIONAL`-shaped and
  must stay so. A compression event is a **volatility** family fact and may never vote on direction.

---

## 24. Multi-timeframe architecture

### 24.1 What must not change

ADR-0023's central decision — **`multi_timeframe` performs no cross-timeframe synthesis** — is
correct and must survive. `SPEC` §5's worked case (weekly `sustained_higher`, daily `neutral`, 4H
`sustained_lower` "is different from simply calling the asset bullish") is exactly what the refusal
protects.

### 24.2 What must change

Today the cross-timeframe question is answered by *dropping two of the three timeframes*:

| Fact | 1W CONTEXT | 1D SETUP | 4H EXECUTION |
|---|---|---|---|
| structural trend | ✅ votes | ✅ votes | ✅ (opposition check only) |
| regime | ✅ gates | ❌ computed, discarded | ❌ computed, discarded |
| indicator evidence | ❌ **never computed** | ✅ one `Alignment` | ❌ **never computed** |
| levels | ❌ **not passed at all** | ✅ targets only | ✅ stops + confirmation |
| breaks | ❌ | ❌ **not passed** | ✅ |
| crossings / CHoCH / nearest levels | ❌ | ❌ | ❌ |

**A 1W resistance zone can never affect a 1D setup today, because 1W levels never leave the fact
sheet.** That is the multi-timeframe gap, and it is a *plumbing* gap, not a synthesis gap.

### 24.3 The proposed rule

> **Every L5 engine runs per view and its output stays labelled with its role and interval. Composition
> above may *relate* two views' facts, and must name both sides of every relation. It may never merge
> them into an unlabelled aggregate.**

Concretely, and each of these is a **relation**, not a blend:

| Relation | Both sides named | Deterministic |
|---|---|---|
| MTF zone confluence | *"the 1D zone [a,b] overlaps the 1W zone [c,d]"* — both carried, never merged | yes (interval overlap) |
| Breakout into higher-timeframe zone | *"a 1D `CLOSE_BEYOND` of zone Z occurred while price is inside the 1W zone W"* | yes |
| Retest of a higher-timeframe break | *"a 4H `retest` interaction against the 1D zone that a 1D break crossed"* | yes |
| Conflicting structure | already reported side by side; unchanged | — |
| Pattern nesting | a 4H pattern whose bounds lie inside a 1D consolidation | yes |
| Different confirmation delays | already carried per pivot; **must be carried per zone and per pattern too** | yes |
| Different relevance horizons | **research question** — no validated per-role staleness bound exists (`TimeframeLine` says so explicitly) | **not yet** |

### 24.4 Where MTF composition belongs

**Not** in `multi_timeframe` (ADR-0023 forbids it), and **not** in a new engine of its own. It belongs
in `fmis.market_opportunity` (L8), which is the first layer whose job is relating facts across views.
Each relation carries both sides' role, interval and `as_of` — so provenance and timeframe identity
survive, which is the property §27 of the brief demands.

---

## 25. Evidence-family and double-counting policy

### 25.1 The state today, measured

`fmis.evidence.EvidenceFamily` has ten members; **two are populated**. Six descriptors exist, all
TREND or MOMENTUM, all mirroring a `decision_support` observation. `MARKET_STRUCTURE`, `VOLUME`,
`VOLATILITY`, `LIQUIDITY`, `RELATIVE_STRENGTH`, `MACRO`, `NEWS`, `SENTIMENT` are **empty by
design** — ADR-0011's rule is that a calculation earns a descriptor only when something *classifies*
it.

`fmis.setup_evidence.correlation` declares six correlation rules and maps the policy's three factors:

```
context_structural_trend  -> (TREND,)
setup_structural_trend    -> (TREND,)
setup_evidence_alignment  -> (TREND, MOMENTUM)
```

`standing_family_note()` computes whether any two are family-disjoint. **They are not**, so the note
fires on every page: *"the directional factors behind every line here draw on overlapping evidence
families, so their agreement is not independent corroboration."* Milestone AW measured 75–79% pairwise
agreement, which is the same finding arrived at empirically.

### 25.2 The strategic consequence for this milestone

> **The repository has zero independent evidence pairs today, and the fix is a new *family*, not a new
> indicator.**

This reframes the whole milestone. Adding EMA slope, MACD ROC and RSI slope — the most obviously
"missing" items — adds **no independence at all**: they are all TREND/MOMENTUM over the same closes.
What would add independence:

| New capability | Family | Independent of the current three? |
|---|---|---|
| Zone interaction state (*where price stands relative to a tested area*) | `MARKET_STRUCTURE` | **yes** — a location fact, not a direction-of-movement fact |
| Volume at an event | `VOLUME` | **yes** — currently zero descriptors |
| Volatility compression/expansion | `VOLATILITY` | **yes** — currently zero descriptors |
| Divergence | `MOMENTUM` | **partly** — same family as MACD, but genuinely different information within it |
| EMA slope / MACD ROC / RSI slope | `TREND` / `MOMENTUM` | **no** |
| Chart patterns | mostly `MARKET_STRUCTURE` | **partly** — but they *compose* zones and phases, so they are correlated with them by construction |

**This is the strongest argument for the recommended first slice** and it is an argument from measured
repository evidence, not from preference.

### 25.3 Proposed family assignments for every new capability

| Capability | Family | Declared correlations |
|---|---|---|
| zone interaction / role reading | `MARKET_STRUCTURE` | with `structural_trend` (both from the same pivots) |
| zone confluence (MTF) | `MARKET_STRUCTURE` | with the single-timeframe zone reading |
| phase segment (impulse/consolidation/range) | `MARKET_STRUCTURE` | with zones (shared pivots) and with `structural_trend` |
| volatility compression | `VOLATILITY` | with ATR-percent |
| volume at event | `VOLUME` | with relative volume |
| EMA geometry | `TREND` | with `price_vs_ema_*`, `structural_trend`, and **transitively among itself** — the three EMA comparisons are already declared transitive |
| MACD dynamics | `MOMENTUM` | with `macd_vs_signal` and `macd_histogram` — **already declared as one fact counted twice** |
| RSI context | `MOMENTUM` | with `rsi_zone` |
| divergence | `MOMENTUM` | with the underlying oscillator's own readings |
| chart pattern | `MARKET_STRUCTURE` | **with every primitive it composes** — this is the biggest new double-counting risk in the report |
| Fibonacci confluence | *(none — it is a geometric restatement)* | **with the zone it coincides with, always** |

### 25.4 Four structural defences

**Defence 1 — no naive counting, and the existing rule already provides it.**
`MINIMUM_AGREEING_FAMILIES = 2` counts **families**, not items, and requires **zero opposing**. Keep
it. A new engine adds a *family*, never a fourth vote inside an existing one.

**Defence 2 — a new family must declare its correlations at introduction.**
Propose an architecture test: **every `family` value appearing in an evidence item must appear in
`FACTOR_FAMILIES`, and every new item key must appear in at least one `CorrelationRule` or be
explicitly registered as independent.** Today an unmapped factor family silently resolves to an empty
tuple and raises a report warning; that is good, and making it a hard test is better.

**Defence 3 — absence must be structurally incapable of becoming negative evidence.**
The strongest available form: **a Tier-B reading's status enum must not contain `CONFLICTING` as a
value reachable from an absence.** Concretely, a `NOT_APPLICABLE` member must exist and every "the
thing did not happen" path must map to it or to `UNAVAILABLE`. A test should enumerate every Tier-B
producer, feed it an input where the phenomenon is absent, and assert the status is never
`CONFLICTING`. **This is the single most important new test this milestone should require**, because
"no divergence → bearish" is the exact bug the brief is written to prevent and prose cannot prevent it.

**Defence 4 — pattern items must inherit their components' correlations.**
A `PatternOccurrence` composed from a zone reading and two phase segments is **not** independent of
either. Its `correlated_with` must be computed from its components, not declared by hand — otherwise a
pattern becomes a free third vote for facts already counted.

### 25.5 On qualitative labels

The brief proposes *strong supporting / supporting / mixed / conflicting / insufficient*. **Recommend
against the "strong" tier.** A monotone ordinal with no deterministic rule per level is a score in an
enum's clothing — `fmis.setup_evidence.models` explicitly considered and dropped a four-level strength
enum for exactly this reason, and that decision should stand. The four states
`SUPPORTING / CONFLICTING / MISSING / UNAVAILABLE`, plus a new `NOT_APPLICABLE`, plus a `NEUTRAL` where
a comparison is genuinely equal, are sufficient and are already implemented.

**And no invented probabilities.** `Probability` exists with one value, `NOT_CALIBRATED`. Three
research milestones (`CA NO_EDGE`, `CB UNDERPOWERED`, `CC INFEASIBLE`) establish there is nothing to
calibrate against. *"78% breakout probability"* is forbidden, and the type system already forbids it.

---

## 26. Opportunity-state architecture

### 26.1 Two-thirds of this already exists

`fmis.swing_setup.decision_summary` already computes, per symbol, on the live path, and already
renders on the dashboard:

```
DevelopingEvidenceState = DIRECTION_STATED | LEANING | DIVIDED | NONE_READABLE
                          + lean: Direction | None
                          + agreeing / opposing / non_voting family names
```

`LEANING` is *"no direction was stated, and every family that cast a vote cast it on the same side"* —
which **is** WATCH-LONG/WATCH-SHORT, computed from evidence, carried beside `SetupState` and validated
so it can never be shown without it. Its docstring already states the exact orthogonality the brief
asks for.

**Recommendation: extend this, do not build a parallel opportunity state.** A second state machine
naming a side would put the vocabulary in two places, and the guard test that ensures a leaning
summary never accompanies a state the policy did not reach would have to be duplicated or weakened.

### 26.2 What is genuinely missing

`DevelopingEvidence` is a tally of the **same three correlated trend families** the policy tallies. It
is a *directional-evidence* state, not an *opportunity* state, and the difference is precisely what
this milestone would add:

| | Today | With the proposed engines |
|---|---|---|
| basis | 3 correlated trend readings | + location (zones), + phase, + participation, + volatility |
| can say *"approaching a tested area"* | no | yes |
| can say *"consolidating beneath"* | no | yes |
| can name the missing event | policy gates only | **a market event, with a price** |

### 26.3 The proposed state set — four, not six

| State | Meaning |
|---|---|
| `NONE` | nothing developing that the engines can name |
| `WATCH_LONG` | developing structure on the upside; **not** a candidate, **not** a trade |
| `WATCH_SHORT` | mirror |
| `CONFLICTED` | developing structure on both sides; neither is named |

**Reject `DEVELOPING_LONG` / `DEVELOPING_SHORT` as separate members.** The brief itself warns against
state proliferation, and the distinction between "developing" and "watch" has no deterministic event
behind it — it would be a maturity judgement, which is a score (§20's `MATURE` argument, applied
again). *How far along* a setup is belongs in the **structured facts attached to the state** (which
zone, which phase, which confirmation is missing), where a reader can see it, not in the state's name.

### 26.4 The five distinctions the brief asks to be defined exactly

| Term | Exact meaning | Where it lives |
|---|---|---|
| **directional evidence** | one family's `Lean` — what a single reading says | `DirectionalFactor.lean` (exists) |
| **developing opportunity** | ≥1 named Tier-A structural condition holds and the strategy's gates are not satisfied | `OpportunityState` (new) |
| **strategy candidate** | the strategy's directional policy produced a direction; confirmation has not occurred | `SetupState.CANDIDATE` (exists) |
| **confirmed strategy condition** | the strategy's named confirmation event occurred | `SetupState.CONFIRMED` (exists) |
| **open position** | the owner committed capital and a fill was recorded | `fmis.positions` / `fmis.ledger` (exists) |

**`OPEN LONG` must never be used for anything but the last row.** The repository already gets this
right: `SetupState` has no `OPEN` member, and position direction lives in a different package under a
different enum for a documented reason (*"an owner assertion about their own money, not an engine's
opinion about a market"*).

---

## 27. Opportunity vs trade decision — the orthogonality contract

### 27.1 The invariant

> `OpportunityState` and `SetupState` are **independent axes**. No value of one implies, permits or
> forbids any value of the other. All twelve combinations are representable, and the four that matter
> are reachable.

| | `WAIT` | `CANDIDATE` | `CONFIRMED` |
|---|---|---|---|
| `NONE` | ✅ common | possible | possible |
| `WATCH_LONG` | ✅ **the case this milestone exists for** | ✅ | ✅ |
| `WATCH_SHORT` | ✅ | ✅ | ✅ |
| `CONFLICTED` | ✅ | possible | possible |

### 27.2 Six structural protections

1. **The opportunity layer is a separate package** and `fmis.swing_setup` **does not import it**. The
   dependency runs opportunity → *reads* swing_setup's output, or both are composed above. Direction
   cannot flow into the policy because the import does not exist, and an architecture test asserts it.
2. **`evaluate_setup` gains no new parameter.** Its signature is unchanged.
3. **The 81-fixture non-regression digest must be byte-identical** — `8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c`, 72 `WAIT` / 9 `CANDIDATE` — after every commit of this work. This is the acceptance gate.
4. **No surface may render an opportunity state without the decision state beside it.** `DecisionSummary` already enforces exactly this pairing in `__post_init__` and the new state joins it there.
5. **`WATCH` is not a weaker `CANDIDATE`.** A guard test should assert that no `OpportunityState` value ever appears in a `SetupState` position, and that removing the opportunity layer entirely changes no `SetupState` anywhere in the matrix.
6. **HTF gates are untouched.** `CONTEXT_ROLE_STRUCTURE_REQUIREMENT = TRENDING` and
   `MINIMUM_AGREEING_FAMILIES = 2` are unchanged by this milestone. If the owner later wants the
   weekly gate relaxed, the machinery to *measure* that already exists —
   `ContextRoleTreatment.VOTE_ONLY` — and it is a **research** override that stamps a research
   `policy_id`. That is the correct path, and it is a separate decision.

---

## 28. "What are we waiting for?" — design

### 28.1 What exists

`Blocker` already answers this for **policy** conditions: five named kinds, each with `statement`,
`requirement`, `observed` and `source`, walked in the policy's own exit order and pinned by an
81-fixture agreement test. Its docstring states the boundary precisely: *"`requirement` states what the
existing gate already demands; it never states what the market must do to get there."*

### 28.2 What is missing, and why it was correctly deferred

`Blocker` deliberately holds no price, because **no engine below it supplied one for that purpose**.
`Trigger.AWAITING_STRUCTURE_BREAK` does carry a level — but only once a `CANDIDATE` already exists.
For a `WAIT` symbol there is nothing.

The zone engine changes exactly that: it supplies a named level that a market condition can reference.

### 28.3 Proposed `MissingConfirmation`

```
MissingConfirmation:
    statement   : str            what has not happened yet
    kind        : enum           ACCEPTANCE_BEYOND_ZONE | RETEST_AFTER_BREAK |
                                 RECLAIM_OF_ZONE | RANGE_RESOLUTION |
                                 PATTERN_COMPLETION | NOT_DETERMINABLE
    reference   : PriceZone | PriceLevel | None    ← supplied by an engine, never authored
    source      : str            the engine that supplied the reference
    observable  : bool           whether an engine can actually detect the event
```

**The three rules that keep it honest:**

1. **`reference` is always a value an engine produced.** If no engine supplied one, the kind is
   `NOT_DETERMINABLE` and `reference` is `None`. **Never a price parsed out of prose, never a price
   this layer computed.**
2. **`observable` is false when the event is namable but not detectable.** An honest gap beats a
   confident guess — this is the same discipline `BlockerKind.UNDETERMINED` already applies.
3. **It states a condition, never a forecast.** *"Price has not accepted beyond the zone at 82,000–83,400"* is a
   statement about what has not happened. *"Price will break 83,400"* is a forecast and is forbidden.

### 28.4 What the operator would then read

```
BTCUSDT   Opportunity: WATCH LONG      Decision: WAIT
  Structure   1W sustained_higher · 1D sustained_higher · 4H neutral
  Phase       1D CONSOLIDATION, 14 bars, width 0.7 ATR, volatility contracting
  Zone        1D zone 82,000–83,400 · 3 touches · 2 rejections · role HELD_FROM_ABOVE · price BELOW
  Waiting for acceptance above the 82,000–83,400 zone   (source: fmis.price_zones)
  Blocked by  the context-role regime is not TRENDING   (source: fmis.market_regime)
  Weakened by a close below the 1D zone at 78,200
```

Every line is a value from a named engine. **No sentence in that block is authored prose.** That is
the target, and the gap between it and today's page is almost entirely the gap this report describes.

---

## 29. Fibonacci recommendation

## **RESEARCH FIRST**

### Reasoning

**1. It is genuinely new scope.** Fibonacci appears in **no** approved source — not
`PROJECT_SPECIFICATION_V1.md`, not `PROJECT_VISION_ADDENDUM_V1.md`, not any accepted ADR, not the
backlog's EP-01 line. Every other capability in this report is a resumption of stated scope; this one
is an addition, and it should be treated as one.

**2. The arithmetic is trivial; the anchor selection is not.** Given two anchors, retracement levels
are `high − (high − low) × r`. That is one line. **Which** swing high and swing low anchor the
measurement is the entire problem, and it is the same unsolved problem as trendline anchor selection
(§16.1): with 143 confirmed levels in a production window, *"the" swing* is a choice. An anchor policy
that changes as new pivots form is a repainting Fibonacci — and that is what most implementations are.

**3. The dependency is the wrong way round from what it looks like.** A defensible anchor policy is
*"the most recent completed impulse segment"* — which needs `price_phases`. So Fibonacci is downstream
of the phase engine, not a parallel option.

**4. There is nothing to validate it against yet.** The honest use the brief itself proposes —
*"an independently derived zone overlaps a commonly watched retracement area"* — requires the zone
engine to exist first. Without it, a Fibonacci level has nothing to be confluent **with**, and a
lone Fibonacci level is precisely what must never influence anything.

### If later approved, the binding constraints

- **Tier B at most, and arguably Tier B-minus.** It is a *geometric restatement* of an anchor pair,
  not an independent observation.
- **Belongs to no evidence family, and must be declared correlated with any zone it coincides with.**
  A retracement level near a tested zone is **one** fact, not two — and this is the specific
  double-counting trap Fibonacci creates.
- **May never**: create a direction, block a trade, produce confidence, or be a required condition.
- **Anchors must be confirmed pivots** with their `confirmation_bars` carried, and the anchor policy
  must be a named, versioned object stamped on every projection.
- **Levels: 0.382, 0.5, 0.618, 0.786 only.** No others without evidence. 0.5 is not a Fibonacci ratio
  and should be labelled as the convention it is.
- **The useful output is a confluence relation, not a level list**: *"the independently derived zone
  [a,b] contains the 0.618 retracement of impulse I"* — with the zone as the subject and the
  retracement as the annotation, never the reverse.

### The research questions to answer first

1. Does an objective anchor policy over completed impulse segments produce stable anchors under prefix
   extension? (Measurable, and the answer may be no.)
2. Over the existing historical dataset, do independently derived zones coincide with the four ratios
   more often than with an equivalent set of arbitrary ratios? **If not, the whole idea is decoration**,
   and this test is cheap.

---

## 30. Elliott Wave recommendation

## **DEFER** — and the owner's prior expectation is not merely acceptable, it is better supported than he stated

### Reasoning

**1. Genuinely new scope, like Fibonacci.** Named in no approved source.

**2. It is the only capability in the brief that is definitionally non-deterministic.** Every other
item has a definition that two implementations would agree on. Elliott's rules (a wave 2 does not
retrace beyond the start of wave 1; wave 3 is not the shortest; wave 4 does not overlap wave 1) are
checkable, but the **assignment of pivots to waves** is a search over an exponentially large labelling
space with multiple valid solutions. That is not a calculation; it is an interpretation.

**3. The repository has an architectural argument the owner did not use, and it is stronger than
his.** Every existing engine's contract is *"this is a fact about closed bars, and appending later
bars never changes a fact already emitted."* An Elliott count **inherently** changes as the market
develops — that is what a count *is*. It therefore cannot satisfy the prefix-stability contract every
L4/L5 engine holds. It is not that Elliott would be *unwise* at the fact layer; **it is structurally
incompatible with the layer's defining guarantee.** That is a harder line than "it belongs closer to
interpretation", and it is the line this report recommends.

**4. It would be the repository's first capability requiring an AI or search layer that does not
exist.** No AI layer exists at all.

**5. Its deterministic components are already in scope elsewhere.** Confirmed swings, sequence,
magnitude, duration, retracement, extension and Fibonacci relationships are all covered by
`market_structure` + `price_phases` + (optionally) Fibonacci. **Elliott adds only the labelling** —
and the labelling is the part that is not deterministic.

### If ever approved, the binding constraints

- **Tier C. L8 hypothesis. No vote, no gate, no veto — ever.**
- **Multiple candidate counts must be representable simultaneously**, each with its own invalidation
  price. A single "the count" is the failure mode.
- *"No credible interpretation"* is a **normal, frequent, first-class result**, not an error.
- **A test must assert the system is fully functional with Elliott entirely absent** — specifically,
  that removing every Elliott input changes no `SetupState` across the 81-fixture matrix.
- **Never** `possible wave 3` → `market is in wave 3`. The hypothesis type must be structurally
  incapable of collapsing to a single assertion — e.g. a count is only ever reachable through a
  collection, never as a scalar field.
- **Never** `no Elliott count → no LONG`.

---

## 31. Product UX proposal

**Stated first, because it is the finding that matters most for UX planning: the page is thin because
the model behind it is thin.** `SymbolDecisionRow` carries `SymbolDecision` field for field, and
`SymbolDecision` carries what the assessment carries. **A dashboard redesign would change nothing about
what FMITS can say.** Progressive disclosure is worth doing, and it is a presentation improvement, not
a capability one.

### 31.1 First screen — the scanner

Answerable in 5–10 seconds. One row per symbol, seven columns:

```
Symbol   Opportunity   Decision    Structure          Key area            Waiting for            Changed
BTCUSDT  ▲ WATCH LONG  WAIT        1W↑ 1D↑ 4H·        82,000–83,400 ↑     acceptance above       structure 4H
ETHUSDT  — none        WAIT        1W· 1D↓ 4H↓        —                   regime not trending    —
SOLUSDT  ▼ WATCH SHORT WAIT        1W↓ 1D↓ 4H·        118.40–121.00 ↓     breakdown confirmation decision WAIT→…
BNBUSDT  ▲ WATCH LONG  CANDIDATE   1W↑ 1D↑ 4H↑        604.0–611.2 ↑       4H close above 611.2   opportunity NONE→…
```

Every cell is an engine value. `Structure` is the three roles' `structural_trend`, never merged.
`Key area` is the nearest zone with an interaction history, with an arrow for **which side price is
on** — not a role claim. `Changed` is `fmis.scan_memory`'s existing dimension names.

**Ordering.** Lexicographic over states the engines already decided, exactly as
`swing_workspace.ranking` already does it: `CONFIRMED` → `CANDIDATE` → `WATCH_*` → `NONE`, then
sufficiency, then scan order. **No composite score. No "closeness". No opportunity ranking.** The
existing `RANK_KEYS` mechanism is the model and the existing guard test (that a richer evidence digest
cannot move a row up) should extend to the new columns.

### 31.2 Detail page — progressive disclosure

Three tiers. **Nothing is deleted; complexity moves down.**

**Tier 1 — always visible (the decision):** operator summary · opportunity + decision side by side ·
structure per role · the key zone · what is missing · what would weaken it · what changed.

**Tier 2 — one click (the analysis):** zones with interaction histories · phase segments ·
breakout/retest history · developing patterns *(when they exist)* · EMA/MACD/RSI context *(when it
exists)* · divergences *(when they exist)* · volume · volatility · multi-timeframe relations ·
scenarios.

**Tier 3 — one more click (the audit):** the full evidence report with statuses, families,
correlations and independence caveats · every limitation · provenance and `as_of` per role · policy
ids and schema versions · risk planning.

**Auditability is preserved in full.** Tier 3 is exactly today's page. Nothing is removed; the first
screen stops being the audit report.

### 31.3 The two things the UX must never do

- **Never show an opportunity state without the decision state beside it.** Already enforced in
  `DecisionSummary.__post_init__`; extend that enforcement to the new state.
- **Never rank by anything but named, engine-decided states.**

---

## 32. Accessible visual and colour semantics

**Rule 1: colour is never the only cue.** Every state carries a text label and a shape/glyph.

**Rule 2: direction and actionability are separate encodings.** This is the brief's central point and
it is right — a SHORT is not "bad".

| Axis | Encoding | Never |
|---|---|---|
| **Direction** | glyph + position: `▲ LONG` / `▼ SHORT` / `— none` / `± conflicted` | colour |
| **Actionability** | colour: amber = watching/waiting · blue = candidate · green = confirmed · grey = none/unavailable | a glyph alone |
| **Risk / invalidation** | red, reserved **exclusively** for invalidation, failure and risk warnings | for `SHORT` |
| **Availability** | grey + explicit text (*"unavailable"*, *"insufficient history"*) | an empty cell |
| **Change** | a neutral change marker + the dimension name | colour alone |

**Green is never used for direction.** Green means *"a named condition completed"* — which is why a
confirmed SHORT is green and an unconfirmed LONG is amber. That inversion is the whole point of
separating the axes, and it should be stated on the page's own legend.

**Grey vs empty.** Unavailable is grey **with words**; nothing-to-show is empty. `UNAVAILABLE`,
`NOT_APPLICABLE` and `MISSING` must be visually distinguishable, because they are three different
facts (§25).

**No heat maps, no gradients, no colour intensity by magnitude** — an intensity ramp is a score
rendered as a colour, and the same prohibition applies.

The dashboard's existing `theme.py` is the seam for all of this and requires no engine change.

---

## 33. Validation and testing architecture

Every item the brief lists, plus what the repository already does that should be inherited.

### 33.1 Fixtures — hand-built, offline, seeded

| Fixture class | Purpose | Required for |
|---|---|---|
| **Mirrored bullish/bearish pairs** | long/short symmetry | **every** engine |
| Insufficient history | warm-up is a result, not a failure | every engine |
| Exact-equality edges (equal highs, close == level) | the no-tolerance rule | zones, interactions |
| Wick-only interaction | `WICK_BREACH` ≠ `CLOSE_BREACH` | zones |
| Breakout then failed retest | interaction sequencing | zones |
| False breakout (close beyond, return inside, no acceptance) | the distinction that matters most | zones |
| Noisy range | false-positive resistance | phases, patterns |
| Gap cases | `GAPPED_BEYOND` / `ALREADY_BEYOND` | zones |
| Low/zero volume | zero volume is legal in the `Candle` contract | volume readings |
| Identical highs/lows | plateau policy | phases, patterns |
| Threshold boundary (exactly at, one tick either side) | every named parameter | every parameterised engine |
| **Absent-phenomenon** | *"no divergence"* → never `CONFLICTING` | **every Tier-B engine** (§25.4) |

### 33.2 Property tests

- **Prefix stability** — for every prefix `k`, deriving over `candles[:k]` equals the full derivation
  truncated to bars `< k`. **Measured and reported as a violation count over seeded fixtures**, the way
  `structure_break` reports 0 over 40 and `change_of_character` reports 0 over 6,400. Not asserted —
  measured.
- **Order invariance** — permuting an input set produces byte-identical output.
- **Long/short symmetry** — a price-mirrored series produces the mirrored result, with **no branch in
  the code distinguishing the two directions**. `market_regime`'s swap test is the template.
- **Idempotence** — re-deriving over already-closed input changes nothing.
- **Determinism** — two runs, byte-identical.

### 33.3 Mutation tests

Required on the high-risk predicates, and each of these is a place where a wrong sign or a wrong
comparison would be invisible:

- the zone-membership test
- the interaction classifier (all seven kinds)
- the acceptance run counter
- the retest window bound
- the role derivation from interaction history
- the phase boundary tests
- the divergence sign table (all four readings)
- every `NOT_APPLICABLE` vs `CONFLICTING` mapping

### 33.4 Replay / observability

Every engine must be derivable inside `swing_setup.backtest_harness`'s existing instant-by-instant
replay with **no look-ahead**. The acceptance test: a fact emitted at bar `i` in replay is identical to
the fact emitted at bar `i` in a full-history derivation.

### 33.5 The distinction the brief insists on, and it is right

> **Detecting a bull flag correctly and a bull-flag strategy being profitable are two different
> questions, tested by two different mechanisms, and one must never be used to justify the other.**

- **Geometry validation** — hand-built fixtures, deterministic assertions. *"Given these bars, this is
  a `FORMING` flag at bar 34."* This is an engineering question with a right answer.
- **Edge validation** — the existing preregistration machinery (`fmis.research_design`,
  `fmis.swing_lab`, `fmis.universe`, `fmis.paired_dependence`). This is a statistical question, and
  the repository's own record on it is `NO_EDGE` / `UNDERPOWERED` / `INFEASIBLE`.

**A correctly detected pattern is not evidence of anything except correct detection.** No threshold in
a detector may ever be tuned on outcome data and then presented as a definition (§41).

### 33.6 Non-regression gates for every commit of this work

1. Full suite green under `-W error`, 0 warnings.
2. **Policy digest byte-identical**: `8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c`, 72 `WAIT` / 9 `CANDIDATE`.
3. Reliability Gate 9/9.
4. Every architecture guard green — tier partition, directional vocabulary, no-arithmetic in the
   composition roots, dashboard computes nothing.
5. **Non-vacuity**: each new guard proved to fail against a deliberately broken copy.

---

## 34. Non-repainting and look-ahead policy

**The rule, stated once and applied to every capability:**

> Every derived fact carries the **bar index at which it first became knowable**, and a fact already
> emitted at bar `i` is identical when re-derived over any longer series.

### 34.1 Observability table for every proposed capability

| Capability | Earliest knowable at | Confirmation delay | Can history change? |
|---|---|---|---|
| indicator series value at bar `i` | `i` | 0 (after warm-up) | **no** |
| EMA slope over `k` | `i` | 0 | **no** |
| MACD histogram ROC | `i` | 0 | **no** |
| RSI slope | `i` | 0 | **no** |
| confirmed pivot at `o` | `o + right_bars` | `right_bars` | **no** |
| level from that pivot | `o + right_bars` | inherited | **no** |
| **zone** | `max(member.origin.index + member.origin.confirmation_bars)` | inherited from its **latest** member | **no** for the zone's identity; **a new member creates a NEW zone version, never mutates one** |
| zone interaction at bar `i` | `i` | 0 | **no** |
| acceptance (`N` closes) | `i + N − 1` | `N` | **no** |
| retest | the retesting bar | 0 | **no** |
| BOS / CHoCH | the closing bar | 0 above eligibility | **no** |
| **phase segment** | the bar its last defining pivot became knowable | inherited | **no** — an extension creates a **new** segment record |
| trendline | `max(anchor.index + anchor.confirmation_bars)` | inherited | **no** — a new pivot creates a **new** line |
| divergence | the second anchor's confirmation bar | inherited | **no** |
| pattern `FORMING` | last required pivot's confirmation bar | inherited | **no** |
| pattern `CONFIRMED` | the completing bar | 0 | **no** |
| Fibonacci projection | the anchor pair's confirmation bar | inherited | **no** given a fixed anchor policy |
| Elliott count | — | — | **YES — which is exactly why it is DEFER** (§30) |

### 34.2 Three specific prohibitions

- **No centred-window result may appear before its right edge closed.** `detect_swings` already
  guarantees this; every consumer inherits it and none may bypass it by reading raw pivots differently.
- **No retroactive breakout.** An interaction is a fact about one bar and its predecessor.
- **Growth is not mutation.** A zone gaining a member, a phase extending, a trendline gaining a touch —
  each produces a **new record** with a new `established_index`, never an edit to an existing one.
  Append-only is the mechanism that makes non-repainting checkable rather than promised.

### 34.3 The one honest exception, named

The zone engine's `ZoneWidthPolicy` (§15.3) means a zone's *bounds* depend on ATR at the time of
derivation. **If ATR is read at the derivation instant rather than at the zone's establishment bar,
the zone's width changes retroactively — which is repainting.** The rule: **ATR is read at the zone's
`established_index` and stamped onto the zone**, never re-read. This is a real trap and it is the
kind that ships quietly; it is named here so the implementation cannot fall into it by default.

---

## 35. Performance and scale

### 35.1 Measured, at `66bab74`, on synthetic seeded 4H candles

The full structural chain, single view:

| candles | swings | levels | crossings | breaks | structure | **crossings** | breaks |
|---|---|---|---|---|---|---|---|
| 200 | 64 | 62 | 1,016 | 26 | 0.4 ms | **2.2 ms** | 0.2 ms |
| 500 | 145 | 143 | 4,836 | 60 | 0.8 ms | **10.5 ms** | 1.0 ms |
| 1,000 | 292 | 290 | 15,799 | 121 | 1.4 ms | **40.2 ms** | 3.6 ms |
| 2,000 | 559 | 557 | 30,724 | 234 | 2.9 ms | **133.3 ms** | 7.9 ms |

**Levels ≈ 0.28 × candles — linear.** So `derive_level_crossings`, a nested loop over candles ×
levels (`crossing.py:232-234`), is **quadratic in candles**: 10× the candles gives 60× the time,
measured. Everything else is comfortably linear.

At the production window (Binance's default 500 klines): ~10.5 ms per view, ×3 roles ×20 symbols ≈
**0.63 s per scan** — invisible next to the ~38 s the network fetch costs. **This is not a problem
today.** It becomes one at 2,000-bar windows (≈8 s), in a historical replay (which re-derives per
instant), or at a larger universe.

### 35.2 Complexity of every proposed engine

| Engine | Complexity | Notes |
|---|---|---|
| `compute_series` | O(n) per indicator | **cheaper than today** — `ema_series` already computes the whole series and discards it |
| `indicator_context` (slope, ROC, runs, spread) | O(n) | trivial |
| divergence | O(pivots) | anchors are consecutive same-type pivots — **linear, not pairwise** |
| **zone clustering** | O(L log L) | sort levels, single sweep. **Never O(L²)** |
| **zone interactions** | O(crossings) | a **projection** of an existing derivation, not a new scan |
| zone readings | O(interactions) | one fold |
| `price_phases` | O(pivots) | one pass |
| trendline anchors | **O(pivots-per-segment²)** ⚠ | the reason for the phase constraint (§16.3): unconstrained is 10,153 candidates per side per view at 500 bars; scoped to a segment it is tens |
| patterns | O(segments) or O(pivots) | **only** because they compose primitives instead of scanning |

### 35.3 Three rules

1. **Never scan pattern combinations over raw bars.** Every pattern anchors on pivots or segments,
   whose counts are ~0.3× and ~0.05× the bar count respectively.
2. **Derive once per view, project many times.** Zones, phases and interactions are all projections of
   one crossing derivation and one pivot run.
3. **Measure before optimising.** `derive_level_crossings`'s quadratic is real, measured, and **not
   worth fixing inside a feature milestone**. `structure_break` fixed its own with `bisect` when it
   mattered; the same applies here, as its own small task, when a replay or a larger universe makes it
   matter. Correctness first.

---

## 36. Threshold policy

**No threshold is decided in this report.** Every number a future engine needs is classified into one
of four kinds, and the kind determines who may set it.

| Class | Definition | Who decides | Versioned? |
|---|---|---|---|
| **Mathematical definition** | follows from the concept; no choice exists | the definition | no |
| **Engineering tolerance** | a representation or window choice with no market claim | the implementer, stated in a docstring | no, but stated |
| **Strategy / research parameter** | a market claim requiring evidence | **research, then the owner** | **yes — versioned policy object** |
| **Asset/timeframe calibration** | a parameter that provably differs per instrument or interval | research, per segment | **yes, and per-segment** |

### 36.1 Classification of every parameter this architecture would need

| Parameter | Class | Notes |
|---|---|---|
| swing `left_bars` / `right_bars` | **strategy** | exists, defaulted to 2, explicitly "encodes no market opinion" |
| `MINIMUM_DIRECTIONAL_SHIFTS = 2` | **strategy** | exists, named as a policy |
| `MINIMUM_AGREEING_FAMILIES = 2` | **strategy** | exists, named as a policy |
| `CONFIRMATION_LOOKBACK_BARS = 10` | **strategy** | exists; already has a research override |
| RSI band edges 30/45/55/70 | **asset/timeframe calibration** | currently fixed and universal — **a known simplification** |
| **zone width (ATR multiple)** | **strategy → likely calibration** | §15.3; the milestone's single biggest new parameter |
| zone cluster gap | **strategy** | may be the same parameter as width |
| acceptance run length `N` | **strategy** | — |
| retest window | **strategy** | — |
| zone staleness / max age | **strategy** | — |
| impulse magnitude ÷ ATR | **strategy** | — |
| impulse min/max duration | **strategy** | — |
| retracement max depth | **strategy** | — |
| consolidation max width ÷ ATR | **strategy** | — |
| consolidation min duration | **strategy** | — |
| range min touches per side | **strategy** | 2 is the smallest integer expressing repetition, by the `MINIMUM_DIRECTIONAL_SHIFTS` argument |
| slope lookback `k` | **engineering** | a window choice; state it, version it if it turns out to matter |
| divergence max age | **strategy** | — |
| divergence min magnitude | **strategy** | **do not pre-filter** (§21.2) |
| trendline touch tolerance | **strategy** | reuse the zone tolerance mechanism, not a second one |
| trendline min anchors = 2 | **mathematical** | two points define a line |
| pattern expiry | **strategy** | — |
| double-top price similarity | **strategy** | reuse the zone tolerance |
| Fibonacci ratios | **mathematical** (given the convention) | 0.5 is a convention, not a ratio — label it |

### 36.2 The rules

- **None of the "strategy" rows above is decided by this report.** Each is a hypothesis needing
  research.
- **Every strategy/calibration parameter lives on a named, versioned policy object**, stamped onto the
  fact it produced, so a historical fact is reproducible from its own record. `RegimePolicy` and
  `ContextPolicy` are the templates.
- **No parameter is a per-call knob on a production entry point.** `evaluate_setup`'s two research
  overrides show the correct shape: a research-only argument that stamps a research `policy_id` and a
  limitation line, unreachable from any production call site.
- **A parameter with a default is a decision.** State it as one, in the constant's own docstring, the
  way `MINIMUM_DIRECTIONAL_SHIFTS` and `CONFIRMATION_LOOKBACK_BARS` already do.
- **Never optimise all detector thresholds on one dataset and call the result correct** (§41).

---

## 37. Deterministic vs AI vs strategy vs research

The mapping the brief requires, for every proposed capability.

| Capability | Responsibility |
|---|---|
| swings, labels, sequence, trend | **DETERMINISTIC** (exists) |
| levels, crossings, BOS, CHoCH | **DETERMINISTIC** (exists) |
| zone clustering and membership | **DETERMINISTIC**, under a versioned width policy |
| zone interactions (all seven kinds) | **DETERMINISTIC** |
| zone role from interaction history | **DETERMINISTIC** |
| phase segmentation | **DETERMINISTIC**, under versioned parameters |
| indicator series, slope, ROC, runs, spread, ordering, crossover | **DETERMINISTIC** |
| divergence anchors and readings | **DETERMINISTIC** |
| trendline anchors, projection, break | **DETERMINISTIC** given a scoping rule |
| pattern geometry and lifecycle | **DETERMINISTIC** given the primitives |
| Fibonacci projection from an anchor pair | **DETERMINISTIC**; the **anchor policy** is a RESEARCH question |
| opportunity state | **DETERMINISTIC** — a fold over engine states |
| missing-confirmation reference | **DETERMINISTIC** — supplied by an engine, never authored |
| — | — |
| *"what does this combination of facts mean"* | **AI** |
| *"compare the bullish and bearish readings of this same evidence"* | **AI** |
| *"what is the strongest opposing case"* | **AI** (`SPEC` §7 asks for exactly this) |
| *"why do these two engines disagree"* | **AI** |
| *"explain the transmission mechanism of this macro event"* | **AI** (out of scope here) |
| alternative Elliott hypotheses, if ever | **AI**, Tier C, no vote |
| — | — |
| *"this strategy requires a confirmed 1D acceptance + a 4H retest"* | **STRATEGY** |
| candidate qualification, gates, confirmation | **STRATEGY** (exists) |
| which timeframes fill which roles | **STRATEGY** (exists) |
| — | — |
| every threshold in §36's strategy/calibration rows | **RESEARCH** |
| whether any detected pattern precedes anything | **RESEARCH** |
| whether Fibonacci ratios coincide with zones better than chance | **RESEARCH** |
| whether a new family adds real independence | **RESEARCH** |

### 37.1 The prohibition

> **AI must never fabricate a support level, a swing point, a breakout, a Fibonacci anchor, a
> divergence, a zone or a pattern state.** If deterministic code can compute it, deterministic code
> computes it, and AI receives the computed object.

No AI layer exists today, so this is a constraint on a future milestone rather than a change to an
existing one. It should be written into the ADR that introduces the first AI consumer.

---

## 38. Priority matrix

| # | Capability | Product value | Dependency leverage | Validation difficulty | False-positive risk |
|---|---|---|---|---|---|
| 1 | **Carry existing facts across `build_setup_inputs`** | **VERY HIGH** | **VERY HIGH** | **LOW** | **LOW** |
| 2 | **`compute_series()`** | MEDIUM *(alone)* | **VERY HIGH** | **LOW** | **LOW** |
| 3 | **Zones + interaction history** | **VERY HIGH** | **VERY HIGH** | MEDIUM | LOW–MED |
| 4 | **Phase primitives** | **HIGH** | **VERY HIGH** | MEDIUM | MEDIUM |
| 5 | Indicator context (EMA/MACD/RSI dynamics) | **HIGH** | HIGH | LOW | LOW |
| 6 | Volume/volatility at events | MEDIUM | HIGH | MEDIUM | MEDIUM |
| 7 | Opportunity state + missing confirmation | **VERY HIGH** | MEDIUM | LOW | LOW |
| 8 | Divergences | MEDIUM | MEDIUM | MEDIUM | MEDIUM |
| 9 | Trendlines / channels | MEDIUM | MEDIUM | **HIGH** | **HIGH** |
| 10 | Flags / pennants | MEDIUM | LOW | **HIGH** | MEDIUM |
| 11 | Double tops / bottoms | MEDIUM | LOW | MEDIUM | LOW–MED |
| 12 | Triangles / wedges | LOW–MED | LOW | **HIGH** | **HIGH** |
| 13 | Head & shoulders | LOW–MED | LOW | **VERY HIGH** | **VERY HIGH** |
| 14 | Candlestick morphology at location | LOW–MED | LOW | MEDIUM | **HIGH** if context-free |
| 15 | Fibonacci | LOW | LOW | **HIGH** *(anchor policy)* | MEDIUM |
| 16 | Elliott | **LOW** | **NONE** | **VERY HIGH** | **VERY HIGH** |

**Row 1 is the finding of this report.** It is the only row that is very high on value **and** leverage
while being low on both difficulty and risk, because the facts already exist and are already correct —
they are simply not carried.

---

## 39. Recommended milestone sequence

The brief offers a 15-step hypothesis and asks for it to be improved. **Three changes.**

| Brief's order | Recommended | Change and why |
|---|---|---|
| *(not listed)* | **0. Carry existing facts across the seam** | **Added, and placed first.** Half the owner's BTC example is already computed and discarded (§8.1). This is the cheapest real capability gain available and it is invisible in the brief's ordering |
| *(not listed)* | **1. `compute_series()`** | **Added.** Four of the brief's twelve audit sections (EMA context, MACD context, RSI context, divergences) are blocked on one additive protocol extension the brief does not mention |
| 1. structural primitives | **audit only, no work** | Confirmed sound; §9 says preserve |
| 2. S/R zones | **2. Zones + interactions** | **Merged with the brief's step 3** — they cannot be separated (§11.1) |
| 3. breakout/retest | *(merged into 2)* | — |
| 4. trendlines | **moved to 8** | Anchor selection needs phases first (§16.3) |
| 5. EMA/MACD/RSI context | **4** | Unblocked once step 1 lands |
| 6. volume/volatility context | **5** | Attaches to zones and phases as event joins |
| 7. impulse/consolidation/range | **3 — moved *up*, ahead of geometry** | **The brief's largest ordering error.** Phases scope trendline anchors and decompose every pattern |
| 8. divergences | **6** | — |
| 9. flags | **9** | After phases *and* geometry |
| 10. double top/bottom | **10** | Cheapest real pattern; could precede flags |
| 11. triangles/wedges | **11** | Re-ask whether they add anything |
| 12. H&S | **12** | Re-ask harder |
| 13. opportunity projection | **7 — moved *up*** | Once zones + phases exist, the opportunity layer is a fold, and it is what makes steps 2–6 visible to the owner. **Delivering it after patterns would leave the owner unable to see six milestones of work** |
| 14. Fibonacci | **13, if research approves** | — |
| 15. Elliott | **DEFER indefinitely** | §30 |

### The recommended sequence

```
0.  Carry existing facts across build_setup_inputs        ← smallest, highest leverage
1.  compute_series() — additive protocol extension        ← unblocks four capabilities
2.  fmis.price_zones — zones + interactions + roles       ← THE FIRST SLICE (with 0)
3.  fmis.price_phases — impulse/consolidation/range
4.  fmis.indicator_context — EMA/MACD/RSI dynamics
5.  volume + volatility at events
6.  divergences
7.  fmis.market_opportunity — WATCH state + missing confirmation
─────────────────── re-evaluate here, with real usage ───────────────────
8.  fmis.trend_geometry — trendlines/channels
9.  flags (and pennants as a variant)
10. double tops/bottoms
11. triangles/wedges — re-ask whether they earn their place
12. head & shoulders — re-ask harder
13. Fibonacci, if the research in §29 supports it
──  Elliott: not scheduled
```

**The re-evaluation point after step 7 is deliberate.** Steps 0–7 deliver a genuinely different
product. Whether steps 8–12 are worth building should be decided **after the owner has used steps 0–7
for a while**, not now.

---

## 40. Recommended FIRST thin vertical slice

## Slice 5 — Where price stands, and what it is waiting for

**The brief's hypothesis is zones + breakout/retest + a small opportunity projection. That is
correct, with one addition it does not name: the seam.**

### 40.1 Scope

| # | Deliverable | Why |
|---|---|---|
| **A** | **Carry the discarded facts across `build_setup_inputs`** — crossings, CHoCH, nearest levels, **context-role levels**, setup-role breaks, all three `FeatureSet`s, per-role regimes | Half the target capability already exists and is thrown away. **Nothing else in the slice works without it** — a zone engine above the seam would have no crossings to read |
| **B** | **`fmis.price_zones`** — `PriceZone`, `ZoneMember`, `ZoneInteraction`, `ZoneReading`, `ZoneWidthPolicy`; clustering, the seven interaction kinds, role from history, touch/rejection counts, recency, lifecycle | The one Tier-A capability whose absence explains the owner's example most directly |
| **C** | **Zone facts on `StructuralFactSheet`**, per view | Follows the established composition-root pattern; makes `fmits facts` the first surface |
| **D** | **`MissingConfirmation`** on the existing `Blocker`, referencing a real zone | The "what are we waiting for" answer the product exists to give |
| **E** | **Zone + interaction facts on `SymbolDecision` and the dashboard**, in the Tier-1/Tier-2 split | Otherwise the owner cannot see any of it |
| **F** | **One new evidence family populated**: `MARKET_STRUCTURE`, with a zone-interaction descriptor and its declared correlations | The repository's **first genuinely independent evidence** (§25.2) |

### 40.2 Explicitly out of scope

Phases · trendlines · channels · patterns of any kind · candlesticks · divergences · EMA/MACD/RSI
dynamics · `compute_series()` · Fibonacci · Elliott · opportunity **state** (the `WATCH_LONG` enum) ·
dashboard redesign · **any change to `evaluate_setup`**.

**`WATCH_LONG` is deliberately deferred to a later slice.** Naming a side is `swing_setup`'s privilege
under ADR-0028, and doing it needs the ADR in §43-D3. Slice 5 delivers the **facts** a `WATCH` state
would be built from, plus the missing-confirmation sentence — which is most of the operator value
without the architectural decision.

### 40.3 Why this slice and not another

| Criterion | How it is met |
|---|---|
| Real product value | The operator sees, for the first time, *which price area matters, how price has behaved there, and what has not yet happened* |
| Consumes existing foundations | Reads `level_crossing`, `structure_break`, `market_structure`, ATR — **adds no primitive of its own** |
| Clear deterministic semantics | Every interaction is a comparison over an existing event |
| Testable | Hand-built fixtures; mirrored bull/bear; prefix stability measurable the way `structure_break`'s was |
| Bounded | One new package, one seam widened, one family populated |
| Reaches the Swing Workspace | Deliverables C and E |
| Improves *"what deserves attention?"* | Deliverable D |
| Preserves the WAIT/CANDIDATE policy | `evaluate_setup` is untouched; digest `8b22e6c9…` must stay byte-identical |

### 40.4 Challenging the brief's hypothesis — where it is right and where it is not

**Right:** zones + interaction semantics is the correct first target, and it does address the owner's
case directly.

**Incomplete in two ways:**
1. **It omits the seam.** A zone engine that produced perfect zones which then died at
   `build_setup_inputs` would deliver **zero** operator value. Deliverable A is not optional plumbing;
   it is the slice's foundation.
2. **"A small opportunity projection" hides an ADR.** A `WATCH_LONG` state names a side, and ADR-0028
   makes that a decision, not an implementation detail. Splitting it out keeps Slice 5 approvable
   without pre-committing the owner to a new directional boundary.

**Also considered and rejected as the first slice:**

| Alternative | Why not first |
|---|---|
| Trend geometry first *(the brief asks whether it must precede)* | **No.** Anchor selection needs phases, phases need no geometry. Geometry first would mean inventing an anchor rule with no basis — the worst outcome available |
| Phases first | Defensible, and close. But a phase alone answers *"the market is consolidating"* without answering *"beneath what"*, and the second half is the operator's actual question |
| `compute_series()` + indicator context first | Highest leverage per line, but delivers **no Tier-A fact** and no new evidence family — it makes the existing correlated trend evidence more detailed rather than adding independent information (§25.2) |
| Divergences first | Depends on `compute_series()`; Tier B; cannot gate; smaller product change |

---

## 41. Research vs engineering

The brief's four-way classification, applied.

**A — implementable now as deterministic market description**
Zone clustering (given a width policy) · all seven interaction kinds · role from history · touch and
rejection counts · recency in bars · zone lifecycle · phase segmentation (given parameters) ·
indicator series · slope · ROC · run length · spread · ordering · crossover events · divergence
anchors and readings · trendline projection from fixed anchors · pattern geometry from primitives ·
opportunity fold · missing-confirmation reference.

**B — requires empirical parameter research before being trusted**
Zone width multiple · cluster gap · acceptance run length · retest window · zone staleness · every
phase threshold · divergence max age and min magnitude · trendline touch tolerance · pattern expiry ·
double-top price similarity · RSI band edges per asset/timeframe · Fibonacci anchor policy.

**C — requires strategy backtesting to know whether it has edge**
Whether any zone interaction precedes anything · whether acceptance beats a bare close · whether a
retest improves outcomes · whether divergence precedes reversal · whether any pattern precedes
anything · whether opportunity state predicts candidate formation.

**D — too subjective; hypothesis/AI only**
Elliott counts · discretionary pattern interpretation · symmetry judgements in H&S · "the" trendline
where several are defensible · narrative significance of a candlestick.

### 41.1 Two rules that must not be broken

> **Do not use backtest profitability to redefine a basic market fact.** If research shows breakouts
> underperform, the definition of a breakout does not change. The *strategy* changes. A definition
> that moves with its measured outcome is not a definition.

> **Do not optimise every detector threshold on one dataset and call the result objectively
> correct.** The repository already has the machinery to avoid this — preregistration
> (`fmis.research_design`, `fmis.swing_lab.preregistration`), power analysis, and paired-dependence
> measurement — and it has already produced `NO_EDGE`, `UNDERPOWERED` and `INFEASIBLE` verdicts using
> them. Any parameter research must go through that machinery, not around it.

---

## 42. What NOT to build yet

Recorded explicitly so a later session does not treat this report as permission.

| Do not build | Until |
|---|---|
| Any chart pattern | zones **and** phases exist and have been used |
| Trendlines or channels | phases exist (anchor scoping) |
| Head & shoulders, symmetrical triangles, wedges | after the simpler patterns, and only if they add information the primitives do not |
| A candlestick pattern catalogue | **never as a catalogue**; morphology-at-location only, after zones |
| Fibonacci | the §29 research answers both questions |
| Elliott Wave | indefinitely |
| An opportunity **score** or ranking key | never — nothing to calibrate against |
| Calibrated probabilities | a validated edge exists; `NOT_CALIBRATED` stands |
| Any relaxation of the HTF regime gate | separate research, through `ContextRoleTreatment`, with its own versioned policy |
| A dashboard redesign | the model behind it is richer (§31) |
| Triple tops, V-tops, rounded structures | never — they are a touch count and a pivot |
| A generic "pattern framework" | a second pattern exists and shows real shared structure |
| `technical_analysis.py` or `pattern_detector.py` | never |

---

## 43. Decisions requiring Dovydas + ChatGPT approval

Seven. **D1, D2 and D3 block the first slice; the rest can wait.**

| ID | Decision | Why it needs approval | Recommendation |
|---|---|---|---|
| **D1** | **Zone width tolerance.** Clustering needs a distance test, and the repository has no tolerance anywhere on principle (ADR-0013 §4) | A deliberate, scoped weakening of an accepted principle | **Approve** a named, versioned `ZoneWidthPolicy` carrying an ATR multiple, stamped on every zone; **reject** any fixed percentage |
| **D2** | **May a zone carry a role, and what may it be called?** Three tests forbid `support`/`resistance` in output; ADR-0019 §I reserves the interpretation | The reason those guards exist | **Approve** role **derived from interaction history only**, never position. **Recommend keeping the words out of value strings** — `HELD_FROM_BELOW` / `BROKEN_UPWARD` are more precise and preserve the guards' intent. A rendered page may use the familiar words in a **label**, if the owner wants them, once the ADR says so |
| **D3** | **Where does opportunity state live, and may it name a side?** `WATCH_LONG` names a direction; ADR-0028 makes `fmis.swing_setup` the only package permitted to | A boundary an accepted ADR fixed | **Defer past Slice 5.** When taken: extend `DevelopingEvidence` inside `swing_setup` rather than creating a second directional package |
| **D4** | **`compute_series()` on the `Feature` protocol** | A change to a core contract, though additive | **Approve as additive** — `compute()` unchanged, every existing feature name, seeding convention and metadata unchanged, digest byte-identical |
| **D5** | **Do the three evidence-status vocabularies converge?** (§8, seam 6) | Touches three accepted engine boundaries | **Do not merge them.** Add `NOT_APPLICABLE` where missing and document the mapping. Merging would reopen ADR-0008, ADR-0011 and ADR-0025 for a naming improvement |
| **D6** | **Fibonacci: research first?** | New scope, not in any approved source | **Approve the research, not the feature** |
| **D7** | **Elliott: defer?** | New scope | **Approve the deferral** |

### 43.1 One question this report deliberately does not answer

**Should the 1W regime gate be relaxed?** The owner's example is a symbol the gate rejects. This
report **does not recommend touching it**, for three reasons: the machinery to measure the
counterfactual already exists (`ContextRoleTreatment.VOTE_ONLY`, added by Milestone BW for exactly
this question); it is a strategy-policy change requiring its own versioning and its own research; and
**the opportunity layer makes the question less urgent**, because a gated symbol can be visibly
`WATCH` without the gate moving at all. That is the whole point of §27's orthogonality.

---

## 44. ADRs and design documents recommended before implementation

**Two ADRs before Slice 5. Not five.** The brief warns against ADR bureaucracy and the warning is
right — most of this architecture follows existing accepted decisions and needs no new one.

### Required before Slice 5

| ADR | Title | Decides |
|---|---|---|
| **ADR-0031** | **Price zone semantics and the tolerance boundary** | D1 + D2 together. Zones as a distinct type from `PriceLevel`; role from interaction history, never position; the `ZoneWidthPolicy` mechanism and why an ATR multiple is admissible where a percentage band is not; which vocabulary guards are scoped and which stand unchanged; the ADR-0019 D2 and ADR-0020 D5 limitations carried forward |
| **ADR-0032** | **Fact carriage across the setup input boundary** | The seam. Which facts cross `build_setup_inputs`, why the narrow boundary was right for a policy input and is wrong for a product surface, and — **critically** — that carrying a fact **must not** make it a policy input. The 81-fixture digest is the enforcement mechanism |

### Required later, when their capability is scheduled

| ADR | Decides | Before |
|---|---|---|
| **Pattern lifecycle and non-repainting observability** | the five-state lifecycle, append-only transitions, the prefix-stability contract | the first pattern |
| **Opportunity state vs trade decision** | D3 — orthogonality, where a side may be named, the six protections in §27.2 | the `WATCH_*` state |
| **Feature series protocol extension** | D4 | `compute_series()` |
| **Correlated-evidence policy for new families** | the §25.4 defences as hard tests | the second new family |

### Not needed

- **Fibonacci authority level** — a research document decides whether it happens at all; an ADR only if it does.
- **Elliott authority level** — deferred; **an ADR to record a deferral is bureaucracy**. This report's §30 is the record.
- **Trendline semantics** — a design document when scheduled; it introduces no boundary an ADR must fix.

### Design documents (not ADRs)

`docs/design/PRICE_ZONE_ENGINE_V1.md` (the full type contract, interaction table, and every fixture
class) · `docs/design/PHASE_PRIMITIVES_V1.md` (when scheduled) ·
`docs/design/ZONE_PARAMETER_RESEARCH_QUESTIONS_V1.md` (§45's list, preregistered before any number is
chosen).

---

## 45. Research questions

Numbered so a future milestone can cite them.

### Zones
- **R1** What ATR multiple, if any, produces stable zone membership under prefix extension? Is stability even achievable, or does membership churn at every multiple?
- **R2** Does zone membership stability differ materially by timeframe role (1W/1D/4H) or by asset volatility band?
- **R3** How many consecutive closes make "acceptance" a distinguishable state rather than a restatement of a close breach?
- **R4** Within how many bars must a retest occur to be attributable to the break?
- **R5** At what age does a zone stop describing current behaviour?
- **R6** Do touch and rejection counts carry information beyond zone existence, or are they a proxy for zone age?

### Phases
- **R7** What ATR-normalised displacement distinguishes an impulse from noise, and does the answer transfer across assets?
- **R8** What width and duration bounds make consolidation a distinguishable state rather than "everything that is not an impulse"?
- **R9** What fraction of production bars fall in `UNDEFINED` at candidate parameters? *(If it is near zero, the segmentation is meaningless.)*

### Indicators
- **R10** What slope lookback `k` makes EMA slope stable rather than a noise derivative?
- **R11** Are the fixed RSI bands (30/45/55/70) defensible across assets and timeframes, or is a per-segment calibration required?
- **R12** How much of MACD-histogram-direction's information is already in EMA slope? *(A correlation question, and the answer is probably "most".)*

### Divergence
- **R13** What minimum magnitude, if any, separates a meaningful divergence from float noise?
- **R14** How long does a divergence remain relevant before it should expire?

### Evidence and independence
- **R15** **Does a zone-interaction family actually add independence to the existing three-family tally, measured the way Milestone AW measured the current 75–79% agreement?** *(The most important question in this list — it is the empirical test of §25.2, the whole argument for the recommended slice.)*
- **R16** Does volume-at-event add independence beyond zone interaction, or do they co-occur?
- **R17** Does a `WATCH` opportunity state precede `CANDIDATE` formation more often than chance?

### Fibonacci
- **R18** Does an anchor policy over completed impulse segments produce prefix-stable anchors?
- **R19** Do independently derived zones coincide with 0.382/0.5/0.618/0.786 more often than with an equivalent set of arbitrary ratios? *(Cheap, decisive, and should be run before any Fibonacci code is written.)*

### Cross-cutting
- **R20** Do any of the above thresholds transfer across assets and timeframes, or is every one a per-segment calibration? *(Milestone CC's `INFEASIBLE` verdict on universe expansion is directly relevant and should be read first.)*

**Every one of these must go through the existing preregistration machinery** — `fmis.research_design`
for power and resolution, `fmis.swing_lab.preregistration` for frozen hypotheses,
`fmis.paired_dependence` for correlated comparisons. Not around it.

---

## 46. Verification appendix — every measurement in this report

All measurements taken at `66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3`, read-only.

### 46.1 Repository state

```
HEAD          66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3
main          66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3
origin/main   66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3
tracked tree  clean
untracked     16 files — 15 under docs/design/, 1 under docs/reviews/  (unchanged)
```

### 46.2 Full test suite

```
$ .venv/bin/python -m pytest -q -W error -p no:cacheprovider
14699 passed in 689.62s (0:11:29)
EXIT=0
```

**14,699 passed · 0 failed · 0 skipped · 0 warnings** — matching the brief exactly. No other pytest
process was running.

### 46.3 Policy non-regression — independently recomputed

Using report 0045 §11.6's committed formula, run outside the test suite:

```
fixtures:          81
states:            {'wait': 72, 'candidate': 9}
aggregate sha256:  8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c
```

**Matches the brief's `8b22e6c9…` exactly.** This is the acceptance gate for every future commit of
this work.

### 46.4 Reliability Gate

`tests/test_operator_dashboard_startup_smoke.py` contains exactly **9** `def test_` functions, all
passing inside the full run above.

### 46.5 Structural chain scaling

Synthetic seeded 4H candles, single view, `.venv/bin/python`:

```
n=  200 swings=  64 levels=  62 crossings=  1016 breaks= 26 | struct=  0.4ms crossings=   2.2ms breaks=0.2ms
n=  500 swings= 145 levels= 143 crossings=  4836 breaks= 60 | struct=  0.8ms crossings=  10.5ms breaks=1.0ms
n= 1000 swings= 292 levels= 290 crossings= 15799 breaks=121 | struct=  1.4ms crossings=  40.2ms breaks=3.6ms
n= 2000 swings= 559 levels= 557 crossings= 30724 breaks=234 | struct=  2.9ms crossings= 133.3ms breaks=7.9ms
```

### 46.6 Empty-package measurement

```
features/trend/__init__.py               18 lines   __all__: list[str] = []
features/momentum/__init__.py            17 lines   __all__: list[str] = []
features/volatility/__init__.py          16 lines   __all__: list[str] = []
features/market_structure/__init__.py    20 lines   __all__: list[str] = []
features/support_resistance/__init__.py  16 lines   __all__: list[str] = []
features/pattern_detection/__init__.py   23 lines   __all__: list[str] = []
```

### 46.7 Operator dashboard — untouched

```
PID 46403  python3  127.0.0.1:8787 (LISTEN)     — confirmed via lsof, read-only
```

**Never stopped, never signalled, never requested. `pkill` was not used. No development dashboard was
started** — this audit required no running surface. The commit it is serving was therefore **not**
verified.

### 46.8 What this session changed

| Path | Change |
|---|---|
| `src/**` | **none** |
| `tests/**` | **none** |
| `docs/**` | **none** — the 16 untracked research documents were read only |
| `FMITS_PRODUCT_BACKLOG.md` | **none** |
| `FMITS_PRODUCT_CHANGELOG.md` | **none** — correctly, since no user-visible capability shipped |
| `reports/0047_…md` | **created** (this file) |
| `reports/README.md` | index row added, next number bumped to `0048` |

---

## 47. Confirmation that existing policy was not changed

Stated explicitly, as the brief requires.

| Protected | Status |
|---|---|
| `fmis.swing_setup.policy` | **unmodified** |
| `SETUP_POLICY_ID = "swing-setup-v1"` | **unchanged** |
| `MINIMUM_AGREEING_FAMILIES = 2` | **unchanged** |
| `CONTEXT_ROLE_STRUCTURE_REQUIREMENT = TRENDING` | **unchanged** |
| `CONFIRMATION_LOOKBACK_BARS = 10` | **unchanged** |
| `PRODUCTION_CONTEXT_ROLE_TREATMENT = GATE_AND_VOTE` | **unchanged** |
| WAIT / CANDIDATE / CONFIRMED outputs | **unchanged** — digest `8b22e6c9…` reproduced |
| The 81 fixtures | **unchanged** — 72 WAIT / 9 CANDIDATE |
| Risk semantics, the 2% ceiling, capital declaration | **untouched** — `~/.fmits/risk_policy.json` **not created, not read, not inferred** |
| Execution state | **untouched** (none exists) |
| Portfolio semantics | **untouched** |
| Scan memory | **untouched** — no scan was run, no history written |
| Operator dashboard | **untouched** — see §46.7 |

**No live trade candidate was manufactured. No market was queried. No threshold was invented. No
capability was implemented.**

---

## 48. Self-review against §52 of the brief

| Question | Answer |
|---|---|
| Did I turn TA into a BUY/SELL engine? | No. Every proposed engine is banned from directional vocabulary by an existing repository-wide guard, and none may vote alone |
| Did I make WATCH a weaker trade signal? | No. §27 makes the axes orthogonal, with six structural protections and a byte-identical digest as the gate. `WATCH_LONG` is deferred out of the first slice precisely so it cannot be smuggled in |
| Did I make Fibonacci mandatory? | No — **RESEARCH FIRST**, and never a gate or a vote even if approved |
| Did I make Elliott mandatory? | No — **DEFER**, with a stronger structural argument than the owner's own |
| Did I treat missing evidence as negative? | No — §25.4 Defence 3 proposes a **hard test** that no absence maps to `CONFLICTING`, because prose cannot prevent it |
| Did I create naive indicator voting? | No. Family voting is preserved; the report's central argument is that **more indicators add no independence** (§25.2) |
| Did I double-count correlated evidence? | Addressed directly — §25.3 assigns families and declares correlations for every new capability *before* it is built, and §25.4 Defence 4 makes pattern items inherit their components' correlations |
| Did I invent probabilities? | No. `NOT_CALIBRATED` stands; §25.5 rejects even the "strong supporting" ordinal |
| Did I invent thresholds? | No. §36 classifies every one and decides none. §45 lists twenty research questions |
| Did I permit repainting or look-ahead? | No. §34 gives an observability table per capability, names growth-is-not-mutation as the rule, and names the ATR-restamping trap that would otherwise ship quietly |
| Did I confuse a detector with a strategy? | No — §33.5 separates them explicitly, and §41 forbids redefining a fact from its backtest |
| Did I collapse direction and actionability? | No — §32 encodes them on separate axes and states why a confirmed SHORT is green |
| Did I rewrite good market-structure work? | No — §9 lists eleven packages to preserve; §10 proposes **no rewrite**, only one additive protocol method |
| Too many patterns before primitives? | No — **zero** patterns in the first slice; three rejected outright; five deferred |
| Does every new engine have a real consumer? | Yes — each maps to a named `SymbolDecision` field and a named operator question |
| Does it help see opportunities *before* confirmation? | Yes — that is deliverables B and D of the slice, and §28.4 shows the target output |
| Can the system still legitimately return WAIT? | Yes — and it must. The gate is unchanged and 72 of 81 fixtures must still say WAIT |
| Is it symmetric? | Yes — mandated structurally (**one definition over a direction value, no mirrored branches**), enforced by the swap-test pattern `market_regime` already uses |
| Is every claim grounded in the live repository? | Yes — every status, line number, threshold, count and timing in this report was read or measured at `66bab74`; §46 lists the measurements |
| Did I stop before implementation? | **Yes.** `src/` and `tests/` are byte-identical to `66bab74` |

---

# WHAT WE WILL BUILD IF APPROVED

*Written for Dovydas. No engineering vocabulary.*

---

## The problem, in one sentence

**FMITS knows where price turned. It does not know where price *stands*.**

It can tell you that the market made a higher high in March, and another in July, and that a weekly
close went past the July one. It cannot tell you that 82,000 to 83,400 is an area this market has
bounced off three times, that price is sitting just underneath it, and that nothing has happened there
yet. A trader thinks in areas and in what has happened at them. FMITS thinks in individual turning
points and has no memory of what happened when price came back.

## The surprise in the audit

**Roughly half of what you observe on the BTC chart, FMITS already calculates — and then throws
away.**

Every time it analyses a symbol, it works out — for every candle, against every level — whether price
touched it, poked through it and fell back, or closed past it, and whether it got there by trading
through or by gapping over. That is thousands of small facts per symbol.

All of it is reduced to a single number on one screen: *"Crossing events: 412"*.

The same is true of the moving averages, RSI and MACD. They are calculated on all three timeframes,
every scan. **Not one of those numbers appears anywhere you can see it.** They are squeezed into a
single word — roughly "up" or "down" — from one timeframe only, and everything else is discarded.

So when you look at BTC and say *"EMA geometry is improving, momentum is cooling"*, FMITS is not
failing to calculate it. It is calculating something related, keeping one word, and forgetting the
rest before anyone can look.

## What FMITS will gain

**1. It will know which price areas matter, and why.**

Not "there is a level at 83,400" — but "this is an area between 82,000 and 83,400, formed from three
separate turning points, which price has touched three times and been rejected from twice, most
recently eleven bars ago, and price is currently just below it."

That is a different kind of statement. It is the difference between a line on a chart and a place with
a history.

**2. It will know what has happened at those areas — and what has not.**

Touched. Poked through and fallen back. Closed beyond. Settled beyond for several bars. Come back to
test it from the other side. Failed that test. Reclaimed it. Each one is a different fact and each one
means something different to a trader. Right now FMITS has all the raw material and none of the
vocabulary.

**3. It will be able to tell you what it is waiting for — with a price.**

Today, when FMITS says WAIT, it can explain which of *its own rules* stopped it: "the weekly regime is
not trending." That is honest and it is useful, but it is a statement about FMITS, not about the
market.

After this work it will be able to add a statement about the market: *"price has not yet settled above
the 82,000–83,400 area."* That is a real, checkable condition with a real number, produced by a
calculation — not a sentence somebody wrote.

**4. It will start being able to tell you something genuinely new.**

This is the part that matters most, and it is the least obvious.

FMITS currently reaches its conclusion from three pieces of evidence, and the system has *measured*
that those three largely say the same thing — they agree with each other 75–79% of the time, because
they are all reading the same thing: which way price has been moving. Adding more indicators would not
help. Five ways of measuring direction is still one piece of information.

**Where price stands relative to an area it has repeatedly respected is a different kind of
information.** It is the first genuinely independent thing FMITS would know. That is worth more than
any number of extra indicators, and it is the strongest reason to do this first.

## The first milestone, specifically

**"Where price stands, and what it is waiting for."**

1. Stop throwing away what is already calculated — carry it through to where you can see it.
2. Build the engine that groups nearby turning points into **areas**, and remembers everything that
   has happened at each one.
3. Put those areas on the analysis pages, per timeframe, with their full history.
4. Add a line saying what has not happened yet, referencing a real area at a real price.
5. Show it on the dashboard: the key area, how price has behaved there, and what is missing.

**Everything else stays exactly as it is.** The trading decision does not change. WAIT stays WAIT. The
weekly gate is not touched. Risk is not touched. We have an exact fingerprint of today's decisions
across 81 test cases, and it has to come out identical afterwards — if a single decision moved, the
work is wrong and we would know immediately.

## What comes after

Once areas exist, everything else has something to stand on:

- **Market phases** — a strong move, then a pause, then a range. This is what lets FMITS say *"price is
  consolidating beneath that area"*, which is the other half of your BTC observation.
- **Indicator dynamics** — moving average slopes, momentum improving or fading, RSI recovering. Right
  now FMITS keeps only today's number; it needs the recent history to see a direction of travel. That
  is a small change and it unlocks four different capabilities at once.
- **Divergences** — price making a new high while momentum does not.
- **The WATCH state** — a proper "worth watching, not yet a trade" label, once there is enough
  underneath it to justify one.
- **Then, and only then:** trendlines, flags, double tops. Not before — every one of those is built
  out of areas and phases, and building them first would mean building the foundations five separate
  times, badly, hidden inside each pattern.

## What Fibonacci will and will not do

**Recommendation: research it before building anything.**

The arithmetic is trivial. The hard part is choosing *which* high and *which* low to measure from —
there are hundreds of candidates, and most software quietly changes its answer every time a new candle
arrives. That is not analysis; it is redecoration.

**If it is ever added, it will do exactly one thing:** note when an area FMITS worked out *on its own*
happens to sit where a lot of other traders are looking. That is a mildly interesting coincidence and
occasionally a useful one.

**It will never:** create a trade, block a trade, add confidence, or mean anything on its own. "0.618
equals buy" will not exist in this system.

And there is a cheap test worth running before writing any of it: check whether the areas FMITS finds
by itself land on those ratios more often than on arbitrary ones. **If they do not, Fibonacci is
decoration and we will not build it.**

## What Elliott Wave will and will not do

**Recommendation: do not build it. Not now, and probably not later.**

Your instinct that it belongs with interpretation rather than fact is right, and the audit found a
stronger reason than the one you gave.

Every fact FMITS produces obeys one rule: **once it says something happened at a particular candle,
that never changes.** Ten more candles close and the old statement still reads the same. That is what
makes the system trustworthy and what makes historical testing meaningful.

**An Elliott count breaks that rule by its nature.** Re-labelling the count as the market develops is
what a count *is*. It cannot live where the facts live without destroying the one guarantee that makes
the facts worth having.

And the useful parts of Elliott — the wave sizes, the durations, the retracement depths — are already
covered by the swing structure that exists and the phase engine described above. What Elliott adds on
top is the labelling, and the labelling is exactly the part that is a matter of opinion.

**If it is ever added,** it will be a clearly-labelled opinion, several competing counts shown side by
side, never one answer, never a vote, never a veto. FMITS must work perfectly with it switched off —
and there will be a test that proves it does.

## Why "WATCH LONG" can appear before a valid trade

Because they are answers to two different questions, and FMITS has been conflating them by only asking
one.

- **"Is something worth my attention developing here?"** — a question about the market.
- **"Do the rules of my strategy permit a trade?"** — a question about the strategy.

A market can be clearly setting up while a strategy correctly refuses to act. That is not a
contradiction; **that is what patience looks like written down.**

Today FMITS only answers the second question, so a symbol that is genuinely developing looks identical
to a symbol where nothing is happening. Both say WAIT. You then have to check the chart yourself to
tell them apart — which is the specific work this is meant to save you.

After this: *"WATCH LONG · decision: WAIT · waiting for price to settle above 82,000–83,400."*

Three separate facts, none pretending to be another. And **"WATCH" is not a quiet downgrade of the
trade rules** — the rules are untouched, and there is a test whose only job is to prove they are.

## Why the system will still, correctly, say WAIT

**Because most of the time, WAIT is the right answer, and a system that produces trades on demand is
not a decision-support system — it is a slot machine with a chart.**

Nothing here loosens a single rule. The weekly gate stays. Two independent families must still agree,
with none against. Every one of today's 81 test decisions must come out identical afterwards, and if
one moves we stop.

What changes is the **quality of the WAIT.**

- Today: *"WAIT — the weekly regime is not trending."* True, complete, and it tells you nothing about
  the market.
- After: *"WAIT — the weekly regime is not trending. Meanwhile: price is holding beneath an area it has
  been rejected from twice, structure is improving on the daily, and nothing has happened at that area
  yet."*

Same decision. Same discipline. **A far better answer** — and one you can act on by watching, rather
than by re-checking the chart yourself.

## What we are asking you to approve

**Two things, and one of them is a genuine trade-off worth thinking about.**

1. **Areas need a notion of "close enough".** Two turning points a few ticks apart are one area to a
   trader and two separate levels to FMITS today. FMITS has been strict about never using
   approximations anywhere, deliberately, and this is the first place that strictness stops being
   useful. The proposal is to measure "close enough" using the market's own recent volatility rather
   than a made-up percentage — so it adapts per asset and per timeframe instead of being a number
   someone picked. **This is a real, deliberate softening of an existing principle, in one specific
   place, for a stated reason.**

2. **Whether these areas may be called "support" and "resistance" on screen.** FMITS currently
   *forbids* those words, on purpose, because calling a level "support" claims price will hold there —
   and until now nothing knew whether it ever had. Once an area carries its own history of holding and
   breaking, that objection weakens. It is your call whether the familiar words appear on the page. The
   internal facts will stay precise either way.

Everything else follows rules the project already agreed to.

## What we will not do

- Not weaken any trading rule to produce more trades.
- Not invent thresholds — every number that needs choosing is listed as a research question, and none
  is chosen here.
- Not show a percentage or a probability anywhere. Nothing has been validated well enough to earn one.
- Not build a score, a ranking, or a "setup quality" number.
- Not build patterns before the foundations they stand on.
- Not tune anything to make BTC look bullish. Nothing in this design mentions BTC, 82,000, or any
  symbol.
- Not touch risk, capital, or execution.

## Where this leaves the product

Today FMITS is an honest system that says WAIT and, most of the time, cannot tell you much about why
the market is interesting.

After this first milestone it becomes a system that can say: **here is the area that matters, here is
what has happened there, here is what has not happened yet, and here is why I am still not calling it a
trade.**

That is the difference between a system that filters and a system you watch the market with.

---

**This report ends here. Nothing was implemented. Awaiting review.**
