# FMITS Product Backlog

**Living document.** The current execution board: what is being built now, what comes next, what is
blocked, and why each item matters to the product.

**Not a roadmap.** [`reports/0005`](reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md)
remains the strategic roadmap and is immutable. This board changes as work moves.

**Not an architecture document.** Boundaries live in the ADRs and
[`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md).

| Field | Value |
|---|---|
| **Last verified against** | `HEAD` at `2000ba2` (Milestone AV — Swing Setup Historical Backtest Harness v1, code + tests + design + review + report, **committed locally, not pushed**), on top of `35bce7a` (Milestone AU's docs, committed and pushed). `origin/main` remains at `35bce7a` (§4) |
| **Verified on** | 2026-08-08 |
| **Verification method** | live repository + `git log` + full test run + accepted ADRs |

---

## 1. Purpose and usage rules

This board answers one question at a time: **what are we building, and what will the owner be able
to do when it lands?**

**Product-first rule.** FMITS is developed product-first. Every milestone must either

- deliver measurable user value, **or**
- remove a clearly identified blocker preventing measurable user value.

Every item on this board answers: *"What can the owner do after this milestone that was impossible
before?"* An item that cannot answer it does not belong here.

**Usage.**

- Read §4 first — it is the only section that states verified fact.
- §5 (NOW) holds exactly one active milestone.
- Status is never inferred from a roadmap or a vision document. **Only the repository and accepted
  ADRs can move an item to DONE.**
- When a milestone completes, move it to §8 with its commit SHA, and record it in
  [`FMITS_PRODUCT_CHANGELOG.md`](FMITS_PRODUCT_CHANGELOG.md) only if it changed what the owner can do.

---

## 2. Status definitions

| Status | Meaning |
|---|---|
| **NOW** | Actively being built. Exactly one, unless §11 rule 5 applies |
| **NEXT** | Approved, sequenced, and unblocked once NOW completes |
| **LATER** | In scope, not yet sequenced. Grouped by epic |
| **BLOCKED** | Cannot start until a named precursor exists. The precursor is always stated |
| **DONE** | Verified in the repository: code merged, tests passing, ADR accepted |
| **DEFERRED** | Deliberately postponed with a recorded reason. Not abandoned |
| **OPEN DECISION** | Scope or approach undecided. Carried, not solved, until the owner rules |

## 3. Priority definitions

| Priority | Meaning |
|---|---|
| **Critical** | Blocks the product, or removes a correctness/capital risk |
| **High** | Directly enables a workflow the owner performs or wants to perform |
| **Medium** | Broadens coverage or quality of an existing capability |
| **Low** | Valuable, removable, no dependant work |

---

## 4. Current product state

**Every figure below was measured, not quoted.**

| Fact | Value |
|---|---|
| **Milestone AV status** | **Committed locally, not pushed** — `2000ba2` (production code + tests + design + review + report, §8); see [report 0011](reports/0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md). The report itself was written and frozen pre-commit, per this repository's own point-in-time report convention (see report 0009/`AT`, which is never revised after its own later commit either) |
| **Milestone AU commit** | `35bce7a` (docs) on top of `fd8a781` (production code + tests) — **committed and pushed** |
| **Milestone AT commits** | code `a271f33` (production code + tests) · docs `81a6202` (backlog/changelog/current-state reconciliation) — **committed and pushed** |
| **Milestone AS commit** | `aca2628` (production fix + tests + RCA + independent review — defect fix, not a new capability) |
| **Milestone AR commit** | `1480766e57526d48266a4aa5ff48b3a945614656` (production code + tests + ADR-0028 + design + review) |
| **Milestone AO commits** | A `b40663f178e612856d6420c966b8a71ca7966edc` (production+docs) · B `aa78695d172bb23d8b4ff22c0898ba7f0b21a226` (product docs) · C `c84b2a1c0e6a7d13b0bbd586e7a60d2fa027a40d` (record-ID correction) |
| **HEAD** | `2000ba2` (AV production code + tests + design + review + report, committed locally on top of `35bce7a`) |
| **`origin/main`** | `35bce7a` — **one commit behind local `HEAD`; `2000ba2` (AV) is committed locally, not pushed, per this milestone's own explicit instruction. Pushing requires separate, explicit authorization** |
| **Working tree** | This product-docs commit (backlog/changelog/current-state reconciliation, recording `2000ba2`'s real SHA) is the only remaining uncommitted change. The pre-existing untracked AP/AQ-era docs (`ADR_IMPLEMENTATION_GATE.md` and siblings) predate this milestone and are unchanged |
| **Test count** | **4,488 collected, 4,486 passing** (4,426 before AV; +62 net, all in the new `tests/test_swing_setup_backtest.py`), identically under `-W error`, **except two pre-existing failures unrelated to this milestone** — a float-formatting flake in `tests/test_swing_setup_scan_report.py`, reproduced on the clean pre-AV tree and named here rather than silently absorbed into this milestone's scope |
| **Public exports / collisions** | +17 new names on `fmis.swing_setup` (34 → 51: the historical backtest harness's public API — `run_backtest`, `compute_metrics`, `render_backtest_report`, `BacktestRun`, `BacktestMetrics`, `HistoricalObservation`, `SetupOutcome`, `OutcomeStatus`, `DataBoundary`, `BacktestError` and five constants — plus `setup_inputs_and_assessment_for_sheet` from the `compose.py` refactor), 0 collisions |
| **Import cycles** | 0 |
| **Runtime dependencies** | 0 (`coverage`/`pytest-cov` unavailable offline in this environment; 8 targeted mutation probes used in their place, 8/8 detected — see report 0011 §7) |
| **Latest completed milestone** | **AV — Swing Setup Historical Backtest Harness v1** (uncommitted; see [report 0011](reports/0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md)) — `fmits backtest` replays the exact, unmodified Swing Setup v1 policy over real historical closed candles with no lookahead, classifies what happened after every confirmed setup, and reports deterministic, reconciled aggregate measurements. Live on real Binance data (10 symbols, 400 days): 21,730 observations, 182 confirmed setups, 151 evaluable outcomes, 47.4% target-first / 52.6% stop-first — reported as measured, not reinterpreted. See [the design](docs/design/SWING_SETUP_BACKTEST_V1.md) and [the review](docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md) |
| **Product Value Level** | **Level 2 — usable swing-analysis assistant**, now with a first honest measurement of the swing-setup policy's own historical behaviour (ladder in [`reports/0004`](reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §12) |
| **Architecture maturity** | **M2 — Connected** ([`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) §11) |
| **Immediate next milestone** | **Awaiting the owner's decision** (§5) — the exactly-one-NOW rule remains temporarily unsatisfied; AT, AU and AV were all explicitly-scoped, owner-directed implementation tasks, not NOW selections, and this row is unchanged by any of them. §6 holds the sequenced work that follows; §7 holds the unsequenced epics |

### Current user-visible capability

```
fmits setup  BTCUSDT                       # a deterministic swing-trade setup assessment
fmits setup  BTCUSDT ETHUSDT SOLUSDT       # one per symbol, in the order requested
fmits scan                                 # the fixed 20-symbol watchlist, a readable market report
fmits scan --table                         # the same scan, as the original compact table
fmits daily  BTCUSDT ETHUSDT SOLUSDT       # the morning routine, one row per symbol
fmits swing  BTCUSDT                       # the whole page, end to end
fmits regime BTCUSDT --multi               # the environment, per role, with evidence
fmits mtf    BTCUSDT -n 260                # 1W context · 1D setup · 4H execution
fmits facts  BTCUSDT --interval 4h         # one timeframe, exhaustively
fmits swing  BTCUSDT --archive             # archive the page durably (Memory & Decision Archive)
fmits daily  BTCUSDT ETHUSDT --archive     # archive the whole run
fmits archive list                         # every archived record, metadata only
fmits archive show RECORD_ID               # render a stored record, no network access
fmits archive verify RECORD_ID             # integrity check; omit the id to verify the whole archive
python -m fmis.pipeline daily BTCUSDT      # works without reinstalling
```

`scan` runs the **same** deterministic swing-setup assessment `setup` produces across a **fixed,
hardcoded** twenty-symbol watchlist of major pairs — not a caller-supplied universe — and prints one
compact table: state, direction, risk/reward, stop and target. A symbol whose analysis fails is
reported as `ERROR` and does not stop the scan. Rows stay in the fixed list order; it is **not a
ranking** — no score, no probability — and a `CANDIDATE`/`CONFIRMED` result also appears in a
`TOP OPPORTUNITIES` section, filtered from the same order rather than sorted by it.

`daily` runs the **same** swing analysis across a requested universe, one symbol at a time, and
prints a compact **readiness index**: one row per symbol, in the order requested, carrying the
decision-context state and the regime beside it. A symbol that fails reports why and does not stop
the run. It is **not a ranking** — no score, no direction, no recommendation — and the first
limitation printed on every run says exactly that.

`swing` is the **whole page in one command**: data quality, regime per role, structure per role,
levels, evidence by family, and the disagreements between them — with risk, portfolio, trade plan and
AI interpretation rendered as explicitly unavailable, each naming the milestone that owns it and the
inference its absence forbids.

`regime` classifies three **environments** — structure, volatility and participation — each with the
evidence behind it, the evidence against it, what was unavailable, and the exact policy that produced
it. It is **not a direction**: `trending` does not mean rising. Under `--multi` each role is
classified alone and nothing is derived from the combination.

`mtf` returns three **role-labelled** views of one instrument, each with its own `as_of` and
staleness, their structural trends side by side and nothing derived from the combination.

`facts` returns a deterministic fact sheet for **one instrument on one timeframe**: EMA/RSI/MACD/ATR with
warm-up status, relative volume, swing points, structural labels, structural trend, price levels,
level crossings, break of structure, change of character, nearest level above and below the last
close, and the inherited limitations — computed from live exchange data.

**This is the whole product surface today.** Everything else in the repository is a library beneath it.

---

## 5. NOW

**Exactly one item, by rule** ([`START_HERE_FOR_AI.md`](docs/AI_HANDOFF/START_HERE_FOR_AI.md) §5 states
this rule without exception). **That rule is not currently satisfied.** `AP` shipped on **2026-08-06**
(§8, commit `0ea0414`) and no successor has been sequenced — the same deliberate, temporary,
explicitly-authorized exception the board recorded after `AO`, not a silent redefinition of the rule:
the milestone brief that closed `AP` explicitly forbade choosing the next milestone in the same task.

This is therefore an **outstanding action for the owner**, not a stable resting state — **the next NOW
item must be named before the next implementation task on this board begins.** §6 holds the sequenced
work `AP` itself defined; §7 holds the epics still awaiting sequencing.

## 6. NEXT

The forced sequence. Each item is blocked on the one above it. **Sequenced, not started** — none of
these is a NOW item until the owner names one.

| # | Item | Blocked by | Note |
|---|---|---|---|
| 1 | **ADRs for AP-D1 and AP-D2** | — *(`AP` is DONE; this is unblocked)* | Days, not months. AP-D2 blocks everything: ADR-0027 §8's exact-match-no-migration policy was proportionate for regenerable analyses and is unsafe for records that cannot be recomputed |
| 2 | **The vertical slice** — deterministic Opportunity Proposal · its append-only lifecycle (owner decision, expiry, execution) · plan from acceptance · manual fill capture under the full tax capture contract · position fold · archived decision chain · full-dump export | 1 | *"FMITS proposed three setups this morning; I took one, and every part of that decision is recorded — including the two I passed on."* [Design §32 step 1](docs/design/TRADING_DOMAIN_ARCHITECTURE_V1.md) |
| 3 | **Journal** — Idea · Note · Review, tags with provenance, typed links | 2 | *"Why did I enter, and what was I thinking?"* |
| 4 | **Portfolio config events · snapshots · metric series** | 2 | *"What am I holding, what is it worth, how has it grown?"* |

*Step 2 is deliberately one milestone, not five: it is the smallest thing that closes the loop the
product exists for. Steps beyond 4 are sequenced in the design document §30 and are not promoted to
this board until the ADRs above are accepted.*

---

## 7. LATER — epics

In scope, not yet sequenced. One line per epic states what it delivers and what gates it.
Detail lives in `reports/0004` (capabilities) and `reports/0005` (phasing) — not restated here.

| ID | Epic | Delivers | Status | Priority | Gated by |
|---|---|---|---|---|---|
| **EP-01** | Technical Analysis & Market Structure | Support/resistance scoring, pattern detection, composite features, remaining indicators (RSI MA, MACD slope, ADX, Bollinger, VWAP), divergences | Partly DONE | High | — |
| **EP-02** | Swing Trading Product | Scanning, ranking, trade plan, confirmation/invalidation, stop and target logic, post-trade review | Partly DONE — trade plan/confirmation/invalidation/stop/target delivered by `AR`; scanning, ranking and post-trade review remain LATER | High | AJ |
| **EP-03** | Daily Market Intelligence | Global Market Pulse, Daily Brief, opportunity scanner, alerts, scheduling | LATER | High | AK |
| **EP-04** | Portfolio & Risk | Positions, exposure, correlation clustering, total open risk, position sizing, Buying Power | LATER | **Critical** | **D-02 money types** |
| **EP-05** | Multi-Asset Data Platform | Calendars and sessions, second adapter family, equities/ETFs/indices/commodities | LATER | High | Calendar layer |
| **EP-06** | Long-Term Investing | Thesis capture, thesis monitoring, valuation context, catalysts, position role | LATER | Medium | EP-04, EP-08 |
| **EP-07** | Macro & News Intelligence | Central-bank policy, rates, liquidity, calendar, news mechanism analysis, geopolitics | **BLOCKED** | Medium | **D-03 availability-time model** (ADR-0003) |
| **EP-08** | Fundamental Research | Business/protocol fundamentals, filings, valuation | **BLOCKED** | Medium | **D-03** |
| **EP-09** | China Intelligence | HKEX/mainland, A/H/ADR links, PBOC, policy, capital flows, sector tracks | LATER | Medium | EP-05 |
| **EP-10** | IPO & Special Opportunities | IPO calendar, new ETFs, M&A, spin-offs, lockups, index changes | LATER | Low | EP-05 |
| **EP-11** | Crypto On-Chain | Exchange flows, stablecoins, cohorts, realized metrics, unlocks, **provenance** | LATER | Medium | Adapters |
| **EP-12** | Derivatives | Funding, open interest, liquidations, basis, options, positioning | LATER | Medium | Adapters |
| **EP-13** | Strategy Laboratory | Rule specs, registry, versioning, frozen datasets, sensitivity | LATER | Medium | `compute_series()` |
| **EP-14** | Backtesting | Historical replay with fees/slippage, out-of-sample, walk-forward, robustness, regime segmentation | LATER | Medium | EP-13 |
| **EP-15** | Paper Trading | Simulated fills on unseen data, identical sizing/risk logic to live | LATER | Medium | EP-14 |
| **EP-16** | Shadow Mode | Live data, real timing, **executes nothing** | LATER | Medium | EP-15 |
| **EP-17** | Controlled Execution | Live orders under hard limits, kill switch, full logging, no withdrawal permission | LATER | Low | EP-16 + explicit human decision |
| **EP-18** | Knowledge & Research | Decision archive **(delivered by `AO`)**, journal, searchable knowledge base, lessons learned | LATER | **Critical** | **D-04 journal scope** |
| **EP-19** | Reporting & Delivery | Dashboard, structured reports, exports, notifications, transports | LATER | Low | AK |
| **EP-20** | Security & Operations | CI, type checking, system health, observability, AI budget, safety controls | LATER | Medium | **D-07 CI timing** |

**Bounded autonomous day trading** is deliberately **not** an epic on this board. It sits beyond
EP-17 and beyond the autonomy boundary that `reports/0003` §7.5 records as not crossed and not
designed. It requires its own vision decision (**D-14**, **D-15**) before it can be scheduled.

---

## 8. DONE

Repository-verified only. Every SHA below was confirmed to exist with `git cat-file -e`. `AU` is
committed locally at `fd8a781`, not yet pushed — per `CLAUDE.md`'s git safety rule, pushing requires
separate, explicit authorization, and this milestone's own instruction was "commit locally only, do
not push". `AT`, previously recorded here uncommitted, is now confirmed committed and pushed
(`a271f33` code, `81a6202` docs — both verified present on `origin/main`).

The **complete** milestone history lives in
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md) and is not duplicated here.
This section carries the five most recent milestones.

### `AU` — Market Scanner Intelligence Report v1 · **DONE** *(committed locally, not pushed)*

| Field | Value |
|---|---|
| **Commit** | `fd8a781` — committed locally on top of `81a6202`; push requires separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none** — reuses ADR-0028 exactly as written; the report renderer lives inside `fmis.swing_setup`, the location that ADR already permits directional vocabulary |
| **Design** | [MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md](docs/design/MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md) |
| **Review** | [MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md](docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md) — one P0 and two P1s found live and fixed (a market-overview label that could contradict a WAIT reason for the same symbol; CANDIDATE rows silently dropping an already-computed RR/target), confirmed against a second live scan; one P2 disclosed, not fixed, for a stated reason |
| **Tests** | 4,423 → **4,426** (+3 net; 45 new tests in `test_swing_setup_scan_report.py`). No automated coverage tool available offline; 7 targeted mutation probes run in its place, 7 detected, 0 survivors |

**Product value delivered.** `fmits scan` now prints a report a trader can actually act on in one
reading, not twenty rows to scan by eye: a summary, which symbols are showing directional character,
every CONFIRMED/CANDIDATE setup with its RR/target/stop and the exact reasons the engine already
computed, and every WAIT result grouped by why. `--table` keeps AT's original table for scripting or a
narrower terminal. No new engine, no ranking, no score — every fact printed already existed on
`SetupAssessment` before this milestone.

### `AT` — Market Scanner v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | code `a271f33` · docs `81a6202` — both confirmed present on `origin/main` |
| **ADR** | **none** — reuses ADR-0028 exactly as written; the scanner lives inside `fmis.swing_setup`, the location that ADR already permits directional vocabulary |
| **Design** | [MARKET_SCANNER_V1.md](docs/design/MARKET_SCANNER_V1.md) |
| **Review** | [MARKET_SCANNER_V1_REVIEW.md](docs/reviews/MARKET_SCANNER_V1_REVIEW.md) — no P0, no P1, no P2, one P3 found and closed during review, two P3 remaining (informational, inherited from existing patterns) |
| **Tests** | 4,332 → **4,375** (+43). 100 % line and branch coverage on both new/modified production files. 7 targeted mutation probes, 7 detected, 0 survivors |

**Product value delivered.** The first market scanner. Before `AT`, seeing every symbol's swing setup
meant typing `fmits setup` once per symbol, or once for all of them with no compact overview of which
ones actually produced a `CANDIDATE` or `CONFIRMED` result. `fmits scan` runs the fixed twenty-symbol
watchlist in one command and prints one table plus a `TOP OPPORTUNITIES` section for whatever cleared
the bar — reusing the exact engine `fmits setup` already shipped (Milestone AR), by reference, not by
reimplementation.

**No new engine, no new ADR.** `run_market_scan` is `run_setup_for_symbols` (AR) called with a default
watchlist; `render_scan` formats fields that already exist on `SetupAssessment`. `fmis.swing_setup.compose`,
`.policy`, `.models` and `.render` have a zero-line diff. The one design choice — placing the new
`scan.py` module inside `fmis.swing_setup` rather than a new top-level package — needed no ADR change,
because ADR-0028's own directional-vocabulary guard test already exempts every file directly inside
that package.

**No ranking, and Milestone `AN`'s own warning is why.** `AN`'s record
(`docs/AI_HANDOFF/CURRENT_STATE.md`) already states that a scanner "must rank on an explicit,
deterministic, testable and backtested policy... never as a side effect of a workflow, and never on a
readiness state." `AT` avoids that hazard by not ranking at all:
rows stay in the fixed watchlist's own order, and `TOP OPPORTUNITIES` is a filter over that order, not
a sort — pinned by a test that deliberately places a weaker result before a stronger one to rule out
an implicit sort.

**Status note.** Implemented, tested and reviewed on repository evidence: the full suite is green
under `-W error` at 4,375 tests, coverage is 100 % line and branch on every new/modified production
file, mutation is 7/7 with byte-identical source restoration, and the independent review found no
P0/P1/P2. **Committed and pushed** (code `a271f33`, docs `81a6202`) — confirmed against `HEAD`,
local `main` and `origin/main` all matching. Full record:
[report 0009](reports/0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md).

### `AS` — Market Regime Time-Reference Correction · **DONE** *(defect fix)*

| Field | Value |
|---|---|
| **Commit** | **`aca2628`** |
| **RCA** | [REGIME_ROOT_CAUSE_ANALYSIS_V1.md](docs/design/REGIME_ROOT_CAUSE_ANALYSIS_V1.md) — validated against the live tree before any code changed |
| **Review** | [MARKET_REGIME_TIME_REFERENCE_FIX_REVIEW.md](docs/reviews/MARKET_REGIME_TIME_REFERENCE_FIX_REVIEW.md) — **no P0, no P1, no P2**, one P3 (unreachable from any live call site) documented |
| **Tests** | 4,319 → **4,332** (+13 net; 11 pre-existing references migrated off the defective contract). 100 % line and branch coverage on all three modified modules. 8 targeted mutation probes, 8 detected, 0 survivors |

**Not a new capability — a correctness and reliability fix**, per §1's recording rule. `RegimeInput`
carried a field (`last_index`) that the adapter filled with the last confirmed swing's position and the
engine validated as the last closed candle's position — one reference-frame mismatch producing two
defects (D-1: valid data raising `RegimeInputError`, measured at 15.6 % of a live 6,452-state sweep;
D-2: the reported age of a structural change silently understated on every successful run). Fixed by
replacing `last_index` with `closed_count`, adopting the pattern `fmis.swing_setup` already shipped.
`fmits regime --multi`, `fmits swing`, `fmits setup` and `fmits daily` no longer abort on valid data;
recorded in [`FMITS_PRODUCT_CHANGELOG.md`](FMITS_PRODUCT_CHANGELOG.md) as a reliability entry, not a new
capability count.

### `AR` — Swing Setup Engine v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`1480766e57526d48266a4aa5ff48b3a945614656`** |
| **ADR** | [ADR-0028](docs/adr/ADR-0028-directional-interpretation-boundary.md) — the one narrow directional-interpretation boundary this milestone required |
| **Design** | [SWING_SETUP_ENGINE_V1.md](docs/design/SWING_SETUP_ENGINE_V1.md) |
| **Review** | [SWING_SETUP_ENGINE_V1_REVIEW.md](docs/reviews/SWING_SETUP_ENGINE_V1_REVIEW.md) — **three P1s found and fixed**, one P3 found and fixed, no P0 |
| **Tests** | 4,194 → **4,319** (+125). 100 % line and branch coverage on every new/modified file. 27 mutation probes across two passes plus an independent 3-mutation spot-check, 27 detected, 0 survivors |

**Product value delivered.** The owner's stated highest priority: `fmits setup SYMBOL [SYMBOL...]`
prints a deterministic swing-trade setup assessment — `WAIT`/`CANDIDATE`/`CONFIRMED`, direction when a
candidate exists, the independent evidence behind it, confirmation, invalidation, stop, target(s),
risk/reward when computable, every applicable limitation. `WAIT` is a successful result, not a failure.
Recorded in [`FMITS_PRODUCT_CHANGELOG.md`](FMITS_PRODUCT_CHANGELOG.md) as the seventh user-visible
capability.

**Resolves the gate this board's own `ADR_IMPLEMENTATION_GATE` assessment (2026-08-07) identified**:
that the owner's first priority required no accepted `AP-D1…AP-D6` decision, and the one real blocker —
where directional vocabulary may live — needed exactly one narrow ADR, written with the milestone
that crosses the boundary, per this repository's own unbroken 27-ADR precedent.

**Directional policy in one paragraph.** A candidate needs ≥2 of 3 independent evidence families
agreeing with zero opposing (never one indicator); a trending CONTEXT-role regime gates candidate
formation without itself voting a direction; Decision Context `INSUFFICIENT` forecloses a candidate
unconditionally; EXECUTION only confirms — via a recent, side-matching structure break — and never
votes. No fabricated price anywhere; probability always `NOT_CALIBRATED`; no position sizing.

**Independent review found three real P1s before release, all fixed.** A same-bar dual break always
resolved toward the LOWER side (a genuine directional asymmetry); no recency bound existed on a
confirming break; a one-CLI-flag CONTEXT/SETUP interval collision defeated the ≥2-independent-families
guarantee. Each closed with its own named regression test and reconfirmed by mutation testing.

### `AP` — Trading Domain Architecture v1 · **DONE** *(design only)*

| Field | Value |
|---|---|
| **Commit** | **`0ea041477dbe9584618495dc334e9685e3e6eb0e`** — three Markdown files, no production code, no tests |
| **ADR** | **none yet, by design.** `AP` *names* six decisions (AP-D1…AP-D6, §10) and binds none of them. A design document is not an accepted decision |
| **Design** | [TRADING_DOMAIN_ARCHITECTURE_V1.md](docs/design/TRADING_DOMAIN_ARCHITECTURE_V1.md) — v1.2, 2,151 lines |
| **Review** | Two independent passes, both recorded in the design's own §34: a hostile architecture review (Critical A1–A8, Strong B1–B12 — two rejected with reasons) and a vision-alignment pass. A final release gate found **2 P1 contradictions and 2 P2 over-claims**, all fixed before commit |
| **Tests** | **4,194 — unchanged.** No code changed |

**Product value delivered.** None directly, and it says so: this is an architecture milestone whose
output is a decision, not a capability (backlog rule 8). `AO` made analyses durable; nothing yet
records what the owner *proposed, decided or did*, and no milestone had made the domain decisions that
question requires.

**Blocker it removes.** EP-02 (swing trading product), EP-04 (portfolio and risk) and EP-18 (journal,
knowledge base) all stalled on the same undecided domain model. `AP` designs it: the five-object
decision chain (Opportunity Proposal → Trade Plan → Order → Trade → Position) with the proposal's
lifecycle as an append-only event stream, an append-only ledger whose balance effects are derived
rather than stored, Decision Episode as the unit of learning, one AI retrieval contract, a three-kind
journal, the Portfolio Intelligence boundary, Personal AI Memory, the Swedish tax capture contract,
and one durable store with measured thresholds for anything more.

**Decisions raised, none bound.** **AP-D1** money/quantity types · **AP-D2** capture contract and
migration guarantee (**blocking — must precede the first irreplaceable record**) · **AP-D3** ledger
event taxonomy and the derived balanced-effect contract · **AP-D4** the decision-chain boundary and
the proposal lifecycle stream · **AP-D5** provenance vocabulary ownership · **AP-D6** counterfactual
evaluation policy (needed before step 5, not before step 1). All six are open in §10.

**Decisions answered in substance.** **D-02** (money types, via AP-D1) · **D-04** (journal scope) ·
direction set for **D-09** (export) · **D-10** — the owner confirmed on 2026-08-06 that Swedish tax
readiness is in scope, superseding `reports/0004` §15.2's recommendation. **None is bound by an ADR.**

**Status note.** DONE on repository evidence — the design document is committed at `0ea0414` — and on
the owner's explicit decision of 2026-08-06 that the milestone is complete. **Not recorded in
[`FMITS_PRODUCT_CHANGELOG.md`](FMITS_PRODUCT_CHANGELOG.md)**: that document records user-visible
capability only, and `AP` delivered none. The Product Value Level and every measured code figure in §4
are unchanged.

### `AO` — Memory & Decision Archive v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`b40663f178e612856d6420c966b8a71ca7966edc`** (release); corrected in **`c84b2a1c0e6a7d13b0bbd586e7a60d2fa027a40d`** (record-ID digest widened 8→16 hex) |
| **ADR** | [ADR-0027](docs/adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) — resolves D-01 |
| **Design** | [MEMORY_AND_DECISION_ARCHIVE_V1.md](docs/design/MEMORY_AND_DECISION_ARCHIVE_V1.md) |
| **Review** | [MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW.md](docs/reviews/MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW.md) — no P0, **3 P1 found and fixed**, 1 P2 found and fixed, 2 P3 |
| **Tests** | 3,905 → **4,194** (+289 across release + correction). Mutation 38/39 detected across both passes, 1 proven-equivalent, zero no-ops |

**Product value delivered.** Durable memory. Before `AO`, `Workspace` (AK) and `DailyRun` (AN) were both
first-class, schema-versioned objects with no consumer — every analysis was discarded the moment the
terminal closed.

**What the owner can now do that was impossible before.** Ask *"what did I think about this in October,
and was I right?"* `fmits swing BTCUSDT --archive` / `fmits daily ... --archive` record the complete page
durably; `fmits archive list/show/verify` read it back exactly, with no network access and no
recomputation.

**D-01 is resolved, closing the only decision blocking this item** (§10). Explicit UTF-8 JSON envelopes,
hand-written codecs (no `pickle`, no reflection), a content-derived `record_id`, atomic single-record
writes, and a metadata-only manifest.

**Snapshot reproduction only, stated rather than implied.** No historical replay — no candle history is
archived, only the already-composed model. No migration path yet: an unsupported schema version is
rejected cleanly rather than guessed at.

**Pre-push correction, same day.** The record-ID digest prefix was widened from 8 to **16 hex characters
(64 bits)** before anything from `AO` was pushed — 32 bits reaches meaningful birthday-collision
probability at record counts a personal archive could plausibly accumulate over years, for IDs meant to
become stable long-term references (see ADR-0027 §4). No compatibility reader was added for the
unpublished 8-character shape; one canonical v1 format, not a migration.

**Status note.** DONE on repository evidence: the suite is green under `-W error`, coverage is 100 %
line and branch on every new `fmis.archive` module and on `pipeline/cli.py`, mutation is 38/39 across
both the initial release and the pre-push record-ID correction with one proven-equivalent survivor and
byte-identical source restoration, the review is complete with every P0–P2 fixed (three P1s found in
`archive verify` itself and closed), and `fmits swing --archive` / `fmits archive show` were run against
live Binance data — both before and after the record-ID correction — with byte-identical rendered
output and zero
network calls on show.

*Milestone `AN` — Deterministic Daily Workflow v1 — has aged out of this five-most-recent window. Its
full record, including the ranking-vs-readiness distinction `AT` above relies on, remains in
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md).*

### `AL` — Decision Context Engine v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`a728f3b9f1dbf70c3e00fcfb97b66d60872f8ece`** |
| **ADR** | [ADR-0026](docs/adr/ADR-0026-decision-context-boundary.md) |
| **Design** | [DECISION_CONTEXT_V1.md](docs/design/DECISION_CONTEXT_V1.md) |
| **Review** | [DECISION_CONTEXT_V1_REVIEW.md](docs/reviews/DECISION_CONTEXT_V1_REVIEW.md) — no P0, no P1, **2 P2 fixed**, 3 P3 |
| **Tests** | 3,702 → **3,766** (+64). Mutation 43/43, zero survivors |

**Product value delivered.** The page now says whether it can be trusted. Measured before the work
began: a 12-candle page and a 260-candle page rendered nearly identically, because a section's status
reports whether it produced output rather than whether the output is sound. 12 candles now reads
**insufficient**, 40 **limited**, 260 **sufficient**.

**What the owner can now do that was impossible before.** See, in one line, whether an analysis rests
on enough data — and when it does not, exactly which requirement is unmet and which layer decided.

**Why this preceded the daily workflow.** That milestone's named principal risk is an unfiltered brief.
The filter is this judgement, and building it inside the brief would have meant extracting it later.

**Limitations shipped with it.** The judgement is made about the primary timeframe · `SUFFICIENT`
means the data each layer asked for is present, not that the reading is correct · `strict` is one
flag, deliberately not a per-requirement override.

**Status note.** DONE on repository evidence: the commit exists, the suite is green under `-W error`,
coverage is 100 % on all four new modules, mutation is clean, the review is complete and all four
real-data surfaces work.

### `AK` — Swing Trading Workspace v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`8121050b9d36a22f9a20995c98c5be1206911c33`** |
| **ADR** | **none** — the implementation proved no new architectural decision |
| **Design** | [SWING_WORKSPACE_V1.md](docs/design/SWING_WORKSPACE_V1.md) |
| **Review** | [SWING_WORKSPACE_V1_REVIEW.md](docs/reviews/SWING_WORKSPACE_V1_REVIEW.md) — no P0, no P1, **5 P2 fixed**, 3 P3 |
| **Tests** | 3,582 → **3,702** (+120). Mutation 49/49, zero survivors |

**Product value delivered.** `fmits swing BTCUSDT` is the whole analysis in one command, replacing
three commands and a chart. It also made the **third stranded island reachable**:
`fmis.decision_support`, `fmis.evidence` and `fmis.trading_context` — 1,131 statements of accepted,
tested, ADR-governed code — had zero production importers before this milestone.

**What the owner can now do that was impossible before.** Read one page that states the facts, the
environment, the evidence, **what disagrees**, and **what it cannot tell you** — with risk, portfolio,
trade plan and AI interpretation rendered as explicitly unavailable rather than quietly absent.

**How the page stays honest.** An unbuilt section names the milestone that owns it and the inference
its absence forbids. Conflicts are reported and never resolved. Nothing on the page is a
recommendation, and no direction is expressed or implied.

**Limitations shipped with it.** `AK-1` evidence is price-derived only, and four of ten families
carry no descriptor · `AK-2` conflicts are reported, never resolved · `AK-3` risk, portfolio, trade
plan and interpretation are not computed · `AK-4` evidence and levels describe the primary timeframe.

**Status note.** DONE on repository evidence, as §11 rule 3 requires: the commit above exists, the full
suite is green under `-W error`, coverage is 100 % on every workspace module, mutation is clean, the
independent review is complete and all four real-data surfaces work.

### `AJ` — Swing Trading Workspace architecture · **DONE** *(design only)*

| Field | Value |
|---|---|
| **Commit** | **none** — delivered as an architecture specification, not as repository code |
| **Outcome** | The section-registry design `AK` implements. Its substance is recorded in [the AK design](docs/design/SWING_WORKSPACE_V1.md) |

**Product value delivered.** None directly, and it says so: this was an architecture milestone whose
output was a decision, not a capability. It answered three questions `AK` could not have started
without — whether the workspace displays a directional conclusion (no; a future Strategy engine owns
that vocabulary), whether `decision_support` is adopted or replaced (adopted as-is), and whether the
work splits (it did not need to).

### `AI` — Market Regime Engine v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`cd4bb574e3afbedeeb402fbaf2e254a5a9b5f8ca`** |
| **ADR** | [ADR-0025](docs/adr/ADR-0025-market-regime-engine-v1.md) |
| **Design** | [MARKET_REGIME_ENGINE_V1.md](docs/design/MARKET_REGIME_ENGINE_V1.md) |
| **Review** | [MARKET_REGIME_ENGINE_V1_REVIEW.md](docs/reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md) — no P0, no P1, **4 P2 fixed**, 3 P3 |
| **Tests** | 3,449 → **3,582** (+133). Mutation 45/45, zero survivors |

**Product value delivered.** The regime call moves out of a prompt and into versioned, testable code.
`fmits regime BTCUSDT` classifies three environments with the evidence behind each, the evidence
against it, what was unavailable, and the exact thresholds used.

**What the owner can now do that was impossible before.** Get a market-environment assessment that is
reproducible, diffable and checkable against history — and see *why* it says what it says, including
where it refuses to say anything. Previously this judgement existed only inside the v3 prompt's STEP 1.

**How the v2 bias is prevented.** Not by review discipline but by construction: evidence votes by
family so correlated indicators cannot corroborate themselves, a threshold band is one number whose
edges are multiplicative mirrors so an asymmetric gate cannot be expressed, and the engine never
learns which way a trend points.

**Limitations shipped with it.** `AI-1` regime is not direction · `AI-2` volatility and participation
each rest on a single evidence family, so neither can be corroborated within its dimension · `AI-3` the
thresholds are stated policy, not measurements · `AI-4` each timeframe is classified alone.

**Status note.** DONE on repository evidence, as §11 rule 3 requires: the commit above exists, the full
suite is green under `-W error`, coverage is 100 % on every module touched, mutation is clean, the
independent review is complete and all three real-data surfaces work.

### `AH` — Confirmation-Delay Provenance v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`99483494ea44e00f2c3a8d3256d6288f6c7035c5`** |
| **ADR** | [ADR-0024](docs/adr/ADR-0024-confirmation-delay-provenance.md) |
| **Design** | [CONFIRMATION_DELAY_PROVENANCE_V1.md](docs/design/CONFIRMATION_DELAY_PROVENANCE_V1.md) |
| **Review** | [CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md](docs/reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md) — no P0, no P1, **2 P2 fixed**, 3 P3 |
| **Tests** | 3,404 → **3,449** (+45). Mutation 42 probes, 41 detected, 1 proven equivalent, 0 no-ops |

**Product value delivered.** **Blocker removed**, as promised — and one reliability improvement the
owner can see. Every break and change of character on a fact sheet is now guaranteed to have been
derived under the confirmation delay detection actually used, because supplying a different one is no
longer expressible. ADR-0020 D1 is closed and has left the printed limitations: `fmits facts`
now shows five rather than six, and `fmits mtf` eight rather than nine.

**What the owner can now do that was impossible before.** Nothing new directly — this was a
blocker-removal milestone under the product-first rule, and it says so. What changed is that a whole
class of silently wrong output is gone: 36.1 % of 300 seeded series produced materially different
breaks under a mismatched delay, and none of them raised an error.

**How.** The delay is stamped where it is known and travels with the facts: `detect_swings` records
`right_bars` on every `SwingPoint`, `structural_levels` copies it onto every `LevelOrigin`, and
`derive_structure_breaks` reads `origin.knowable_from`. The argument is **removed** from every public
entry point rather than validated, so the mismatch is unrepresentable.

**Acceptance, against what was written before the work started.** The delay is carried on a derived
fact from detection through to `LevelOrigin` ✓ · a mismatch is impossible rather than merely rejected
✓ · existing tests pass with documented widening ✓ (80 construction sites migrated, two import guards
made docstring-aware, bar-0 fixtures shifted) · the explicitly rejected `structural_levels` parameter
was rejected again ✓.

**Cost, against the estimate.** `SwingPoint` was constructed at 69 test sites as predicted, plus 11
`LevelOrigin` sites; the migration was done by AST position rather than by hand.

**Limitations shipped with it.** One derivation cannot span two confirmation windows — rejected
loudly · `left_bars` is not carried, because no consumer reads it · a hand-built `PriceLevel` may
still carry no origin and is rejected at the break layer rather than at construction.

**Status note.** DONE on repository evidence, as §11 rule 3 requires: the commit above exists, the
full suite is green under `-W error`, mutation is clean, the independent review is complete and both
real-data smoke tests are valid.

### `AG` — Multi-Timeframe Fact Sheet v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`e589411eb575f91ff017713ffc5ed35c094942bb`** |
| **ADR** | [ADR-0023](docs/adr/ADR-0023-multi-timeframe-composition.md) |
| **Design** | [MULTI_TIMEFRAME_FACT_SHEET_V1.md](docs/design/MULTI_TIMEFRAME_FACT_SHEET_V1.md) |
| **Review** | [MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md](docs/reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md) — no P0, no P1, **2 P2 fixed**, 3 P3 |
| **Tests** | 3,305 → **3,404** (+99). Mutation 42/42, zero survivors |

**Product value delivered.** The daily swing workflow's deterministic step is complete. AF's
single-timeframe sheet could mislead — live on BTCUSDT, 1W `sustained_higher` while 4H read
`sustained_lower` — and `PROJECT_SPECIFICATION_V1.md` §5 names that combination as the case that must
not be flattened.

**What the owner can now do that was impossible before.** Run one command and see 1W context, 1D setup
and 4H execution side by side, each labelled with its role and carrying its own `as_of` and staleness
— instead of running three commands and reconciling them mentally, or reading one and being misled.

**Limitations shipped with it.** No cross-timeframe synthesis, deliberately · views are not aligned in
time · `ema_200` may warm up on a weekly view · plus all six inherited from AF, including ADR-0020 D1
still contained rather than fixed.

**Status note.** DONE on repository evidence, as §11 rule 3 requires: the commit above exists, the
full suite is green, mutation is clean and the independent review is complete.

### `AF` — First Light / Structural Fact Sheet v1 · **DONE**

| Field | Value |
|---|---|
| **Commit** | **`1505dd8a4e95f25a5cd876e9cfa7ca89f1b86acd`** |
| **Pushed in** | `ea865bd` range, live on `origin/main` |
| **ADR** | [ADR-0022](docs/adr/ADR-0022-structural-fact-sheet-composition-root.md) |
| **Design** | [STRUCTURAL_FACT_SHEET_V1.md](docs/design/STRUCTURAL_FACT_SHEET_V1.md) |
| **Review** | [STRUCTURAL_FACT_SHEET_V1_REVIEW.md](docs/reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md) — no P0, no P1, **1 P2 fixed**, 4 P3 |
| **Tests** | 3,221 → **3,305** (+84). Mutation 39/39, zero survivors |

**Product value delivered.** The first user-visible capability in the project's history. Before AF,
51.2 % of the codebase was unreachable from real market data and the only working analysis tool was a
prompt that estimated every value visually.

**What the owner can now do that was impossible before.** Obtain computed indicator values, swing
structure, structural trend, price levels, breaks of structure and changes of character for a real
instrument from live exchange data, via one command — the moment
`PROJECT_SPECIFICATION_V1.md` §3.1 became operational.

**Limitations shipped with it.** Single timeframe · one provider · crypto only · no persistence ·
text output only · ADR-0020 D1 contained, not fixed.

### `AE` — Change of Character Foundation v1 · **DONE** *(foundational)*

| Field | Value |
|---|---|
| **Commit** | **`d132ceafc4048b89205772524bf192e3c7bc7b4b`** (merge) · implementation `7276918` |
| **ADR** | [ADR-0021](docs/adr/ADR-0021-change-of-character-foundation-v1.md) |
| **Design** | [CHOCH_FOUNDATION_V1.md](docs/design/CHOCH_FOUNDATION_V1.md) |
| **Review** | [CHOCH_FOUNDATION_V1_REVIEW.md](docs/reviews/CHOCH_FOUNDATION_V1_REVIEW.md) — no P0/P1/P2, 3 P3 |
| **Tests** | **3,221 passing** at that commit. Mutation 59/59, zero survivors |

**Product value delivered.** Completed the deterministic structural chain. **Not directly
user-visible** — no product surface existed at the time. It is the last primitive AF needed.

### `AD` — Break of Structure Foundation v1 · **DONE** *(foundational)*

| Field | Value |
|---|---|
| **Commit** | **`5aac1a3f652ea44e4523e2609e140c18a0b9f121`** (merge) · implementation `458f3ac` |
| **ADR** | [ADR-0020](docs/adr/ADR-0020-break-of-structure-foundation-v1.md) |
| **Design** | [BREAK_OF_STRUCTURE_FOUNDATION_V1.md](docs/design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md) |
| **Review** | [BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md](docs/reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md) — 1 P2 fixed, 1 P3, no P0/P1 |
| **Tests** | **3,033 passing** at that commit. Mutation 42/42, zero survivors |

**Product value delivered.** The first layer built entirely on derived facts. **Not directly
user-visible.** It also *named* the D1 limitation rather than defaulting it away — which is why AH
exists as a scheduled milestone instead of a latent bug.

---

## 9. Backlog item schema

Every milestone item on this board carries these fields. Epic rows in §7 carry the subset that is
known before sequencing.

| Field | Required | Notes |
|---|---|---|
| **ID** | yes | Milestone letter (`AG`) or epic (`EP-04`) |
| **Epic** | yes | Which epic it belongs to |
| **Title** | yes | — |
| **Status** | yes | From §2. Never inferred from a roadmap |
| **Priority** | yes | From §3 |
| **Product Value** | yes | User value delivered, **or** the named blocker removed |
| **User capability unlocked** | yes | Reference the capability ID in `reports/0004` where one exists |
| **Dependencies** | yes | Milestones and open decisions |
| **Acceptance criteria** | yes | Checkable. Cite the contract if one exists rather than restating it |
| **Out of scope** | yes | What must *not* appear in the branch |
| **Related ADRs** | yes | Existing and new |
| **Related reports** | yes | Section-level |
| **Related repository paths** | yes | Files expected to change |
| **Risks** | yes | Concrete, not generic |
| **Estimated size / confidence** | if sourced | Cite the source; never invent an estimate |
| **Product Value Delivered question** | yes | *"What can the owner do after this that was impossible before?"* — answered explicitly |

---

## 10. Open decisions

Carried, not solved, except D-01 — closed this milestone.

> **Milestone letters corrected 2026-08-04.** Three rows once carried letters from before the two shifts
> recorded in §11, all of them meaning *the daily workflow* under its earlier name — corrected in place;
> see git history for the original text.

> **D-01 resolved 2026-08-05** by [ADR-0027](docs/adr/ADR-0027-memory-and-decision-archive-persistence-schema.md)
> (Milestone `AO`): explicit UTF-8 JSON envelopes, hand-written codecs, content-derived record IDs,
> atomic single-record files plus a metadata-only manifest. Kept in this table, struck through rather
> than deleted, so the decision's history and its blocked items remain traceable.

> **D-02, D-04, D-09 and D-10 were addressed in substance on 2026-08-06** by Milestone `AP`'s design
> ([`TRADING_DOMAIN_ARCHITECTURE_V1.md`](docs/design/TRADING_DOMAIN_ARCHITECTURE_V1.md) §22.2). A design
> document is **not** a decision: each row below stays open until an ADR is accepted, or — for D-10 —
> until the owner confirms the scope change the 2026-08-06 brief states. Rows are annotated, never
> deleted.

| ID | Decision | Blocks | Source |
|---|---|---|---|
| ~~**D-01**~~ | ~~Persistence and serialization schema~~ — **resolved, see above** | ~~EP-18, `AO`~~ | [ADR-0027](docs/adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) |
| **D-02** | Money / portfolio numeric types (`float` vs `Decimal`) — **answered in substance by AP-D1**; needs an ADR to bind | EP-04, `AP` step 1 | Review R11 · `reports/0005` §7.2 · `AP` design §5.3 |
| **D-03** | Availability-time model for released/revised data — **untouched by `AP`**; §4.3 of that design is a narrower, self-generated instance and does **not** unblock macro | EP-07, EP-08 | **ADR-0003 (formal gate)** |
| **D-04** | Journal scope as a formal product capability — **answered in substance** by `AP` design §16 (three kinds — Idea, Note, Review — with open subtypes, a closed *tag* vocabulary, and typed links); the owner's 2026-08-06 brief is the scope decision this row was waiting for | EP-18 | `reports/0004` §15.3 · `AP` design §16 |
| **AP-D1** | Money, quantity and currency types; the exact boundary at which `float` stops; per-asset dust thresholds | Every `AP` implementation step | `AP` design §5.3, §31.1 |
| **AP-D2** | **Capture contract and migration guarantee.** A small, versioned, additively-extensible capture contract plus forward-only readers, a golden-file corpus per version, and a full-dump export. ADR-0027 §8's exact-match-no-migration rule was proportionate for regenerable analyses; a ledger cannot be recomputed | **Blocking** — must precede the first written trade | `AP` design §4 Finding 1, §5.7, §31.1 |
| **AP-D3** | Ledger event taxonomy and the **derived** balanced-effect contract — balance effects are a pure function per event kind, never a stored second copy | Positions, portfolio, tax | `AP` design §11.4, §11.7 |
| **AP-D4** | The decision-chain boundary — Opportunity Proposal / Trade Plan / Order / Trade / Position as five objects with optional links, never collapsed | Proposal, plan, episode, learning | `AP` design §7, §8.3–§8.4, §31.1 |
| **AP-D5** | Provenance vocabulary ownership — a neutral `ValueOrigin` beside the kernel with a one-way mapping to `fmis.workspace.Tier`, so no trading concept is pushed into an L7 presentation type and no vocabulary is duplicated | Every record type | `AP` design §5.2, §31.1 |
| **AP-D6** | Counterfactual evaluation policy — fill assumption, horizon cap, ambiguous-bar resolution and the LONG/SHORT symmetry invariant, so an unexecuted proposal can be scored without pretending a fill was guaranteed | `AP` step 5 — **not blocking step 1**, which captures the assumption version as an opaque additive field | `AP` design §8.5, §31.1 |
| **D-05** | Scheduling ownership — belongs to no architecture layer | EP-03 — *not* AN, which shipped without it | `reports/0004` §13.5 |
| **D-06** | Watchlist / universe model | EP-03 — `AO` archives whatever universe the shell supplies, taking no position on this decision | `reports/0004` §13.5 |
| **D-07** | CI and type-checking timing | EP-20 | `reports/0001` §10.2 |
| **D-08** | Telegram as a delivery transport | EP-19 | `reports/0004` §15.2 |
| **D-09** | Excel / CSV export ecosystem — **direction set** by `AP` design §23: export is a versioned leaf projection, never a round trip; statement *import* is an L1-style adapter, not "Excel as source of truth". A full-dump export ships in `AP` step 1, not step 10 | EP-19, `AP` step 10 | `reports/0004` §15.2 — no longer blocked by D-01 · `AP` design §23 |
| **D-10** | Tax Center scope — **owner-confirmed 2026-08-06: Swedish tax readiness is in project scope.** This supersedes `reports/0004` §15.2's "out of scope unless an obligation requires it"; `FMITS_WORKING_PROTOCOL_2026-08-06` states the obligation. **Answered in substance, not yet bound by an ADR.** `AP` design §22.1 separates the two halves: the tax *engine* is step 9, but the tax **capture contract** is in step 1 because FX rates and reward acquisition values are unrecoverable if not captured at the moment of the transaction | EP-19, `AP` step 9 (engine); capture in step 1 | `reports/0004` §15.2 (superseded) · owner decision 2026-08-06 · `AP` design §22 |
| **D-11** | Voice interface | EP-19 | `reports/0004` §15.2 |
| **D-12** | AI model routing and budget | EP-20 | `reports/0004` §15.3 |
| **D-13** | Commercial / multi-user direction | — | `reports/0004` §3.2, §15.2 |
| **D-14** | Autonomous strategy modification | Beyond EP-17 | `reports/0003` §7.5 — boundary not crossed |
| **D-15** | Autonomous capital allocation | Beyond EP-17 | `reports/0003` §7.5 — boundary not crossed |

---

## 11. Backlog maintenance rules

1. **Never delete a completed milestone.** §8 is append-only. A superseded milestone is annotated,
   never removed.
2. **Never change a status silently.** Every status change carries a reason in the same edit.
3. **Every status change must be traceable** to a commit SHA or an explicit owner decision. A
   roadmap, a vision document or a plan is *not* sufficient evidence for DONE.
4. **Roadmap changes require justification.** If this board diverges from
   [`reports/0005`](reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md), say why here.
   Reports are immutable and are never edited to match.
5. **Only one NOW item**, unless a second is genuinely independent — no shared files, no shared
   contracts, no ordering dependency. Independence must be stated, not assumed.
6. **No new milestone without Product Value.** It delivers user value, or it names the blocker it
   removes. "Improves the architecture" is not a product value.
7. **No milestone may bypass the automation ladder.** Research → rules → backtest → robustness →
   paper → shadow → controlled live → bounded autonomy. No rung is skipped for any reason, including
   income pressure.
8. **Architecture work must name the product blocker it removes.** AH is the pattern: it named the
   milestone it unblocks (AI) before the work started, and the DONE row is written against that
   claim rather than around it.

### Milestone letters: two shifts, both recorded

The Decision Context Engine took `AL`, so the two unshipped items below it shifted again: daily
workflow `AL` → **`AN`**, memory `AM` → **`AO`**. Safe only because neither had shipped — no
commit, ADR or design document cites the old letters. `AM` is deliberately left unused rather than
reassigned, so no reader mistakes a renumbered item for the one they remember.

### Milestone letters: the workspace took `AK`

The board previously read `AJ` = Swing Trading Workspace, `AK` = daily workflow, `AL` = memory. The
owner named the workspace **implementation** `AK`, treating `AJ` as the architecture milestone that
preceded it. Both are recorded that way in §8, and the two unshipped items below them shifted one
letter: daily workflow `AK` → **`AL`**, memory `AL` → **`AM`**.

Renumbering is safe here and only here: neither item had shipped, so no commit, ADR or design document
cites the old letters. Nothing above `AJ` was touched.

### Known internal note

[`reports/0006`](reports/0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) §5.2 lists a root
`REPORT.md` among the files AG should update. That file was deleted under explicit authorization on
2026-08-02 and its unique content migrated into
[`reports/README.md`](reports/README.md). **That row is superseded.** Report 0006 is immutable and was
not edited.

---

*Living document · last verified against `b13c37e` on 2026-08-05*
