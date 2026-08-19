# FMITS Product Backlog

**Living document.** The current execution board: what is being built now, what comes next, what is
blocked, and why each item matters to the product.

**Not a roadmap.** [`reports/0005`](reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md)
remains the strategic roadmap and is immutable. This board changes as work moves.

**Not an architecture document.** Boundaries live in the ADRs and
[`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md).

| Field | Value |
|---|---|
| **Last verified against** | `HEAD` at `dbc4765` (Milestones BC, BH and BI, committed locally and **not pushed**; `origin/main` is at `f9ddc54`) plus **Milestones BJ — Daily Trading Workspace MVP** and **BK — Trade Capture & Decision Recording**, both in the working tree and **not committed** (§4, §8) |
| **Verified on** | 2026-08-13 |
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
| **Milestone BC status** | **Committed locally, not pushed** — research-harness correction (production code + tests + design + implementation record + hostile review, §8); see [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) |
| **Milestone AV status** | **Committed and pushed** — `2000ba2` code, `f9ddc54` docs; see [report 0011](reports/0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md). **Read report 0011's setup counts beside report 0012 §7**: AV's setup identity is derived from a window-relative bar index and changes every bar, so its "unique setups" figure counts directional bars (549 from 552) rather than distinct setups |
| **Milestone AV report caveat** | Report 0011 was written and frozen pre-commit, per this repository's point-in-time report convention, and is not revised |
| **Milestone AU commit** | `35bce7a` (docs) on top of `fd8a781` (production code + tests) — **committed and pushed** |
| **Milestone AT commits** | code `a271f33` (production code + tests) · docs `81a6202` (backlog/changelog/current-state reconciliation) — **committed and pushed** |
| **Milestone AS commit** | `aca2628` (production fix + tests + RCA + independent review — defect fix, not a new capability) |
| **Milestone AR commit** | `1480766e57526d48266a4aa5ff48b3a945614656` (production code + tests + ADR-0028 + design + review) |
| **Milestone AO commits** | A `b40663f178e612856d6420c966b8a71ca7966edc` (production+docs) · B `aa78695d172bb23d8b4ff22c0898ba7f0b21a226` (product docs) · C `c84b2a1c0e6a7d13b0bbd586e7a60d2fa027a40d` (record-ID correction) |
| **HEAD** | Milestone BN's product-docs commit, recorded directly on top of `b66a88f` (BN's production code + tests). Previously `4519d0a` |
| **`origin/main`** | **level with local `HEAD`** after Milestone BN's two commits, whose push the milestone brief explicitly authorized. Previously `4519d0a`. Any future push requires separate, explicit authorization |
| **Working tree** | Clean apart from the 16 pre-existing untracked AP/AQ/BA/BB-era research documents under `docs/design/` and `docs/reviews/`, which predate Milestone BN and are unchanged by it |
| **Test count** | **7,359 collected, 7,359 passing**, identically under `-W error` (6,964 before Milestone BN; +395). Earlier note, retained: **A second stale-`__pycache__` incident occurred during BM and is recorded rather than absorbed:** BM's mutation harness restores each probed file byte-identically, which inside one filesystem mtime second reproduces the exact `(mtime, size)` pair a `.pyc` header records — so the interpreter kept serving bytecode compiled from the *mutated* source and a passing test failed as a phantom. SHA-256 restoration is necessary and not sufficient; the harness now clears every `__pycache__` on both sides of every probe. See [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md) §6. Earlier note, retained: Earlier note, retained: The two long-standing `test_swing_setup_scan_report.py` failures previously recorded here as "a float-formatting flake" were neither a flake nor a source defect: a git-ignored `__pycache__` entry compiled from an older `scan_report.py` (`,.2g` where the source says `,.6g`), with a matching recorded mtime and size, which also made `fmits scan` print prices in scientific notation on this machine. Clearing the cache resolved both with no source change — see [report 0013](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) F7 |
| **Public exports / collisions** | **896 public names, 0 collisions** across the repository after Milestone BN (`fmis.position_sizing` 44 new, `fmis.today` 51 → 52). Previously **851 public names, 0 collisions** after Milestone BM (`fmis.marks` 12 new, `fmis.valuation` 23 new, `fmis.pipeline` 35 → 40). Previously **811 public names, 0 collisions** after Milestone BL (`fmis.portfolio_risk` 47 new; two names were renamed during BL — `stop_distance` and `read_exposure_lines` — precisely because the zero-collision guard caught them against `fmis.plan.risk_distance` and `fmis.persistence.read_lines`). Previously **764 public names, 0 collisions** after Milestone BK (`fmis.plan` 14 new, `fmis.trade_capture` 52 new, `fmis.persistence` 60 → 61). Earlier note, retained: `fmis.swing_setup` 53 → **94** names (+41: the corrected research harness — `run_research_study`, `derive_warmup`, `compare_variant`, `post_filter_comparison`, the research models and their constants), **0 collisions** |
| **Import cycles** | 0 — measured at module granularity across 221 modules after Milestone BN (212 before it) |
| **Runtime dependencies** | 0 added, and `pyproject.toml` / `uv.lock` are unchanged. Milestone BN measured **100 % statement and 100 % branch coverage** of all thirteen new and modified modules (1,933 statements, 662 branches) with `coverage` run through `uv run --with coverage`, installed into nothing. Earlier note, retained: Milestone BM measured **100 % statement and 100 % branch coverage** of its 692 new statements and 196 new branches the same way. Earlier note, retained: Milestone BL measured coverage with `coverage.py` run through `uv run --no-project`, which builds an **ephemeral** environment and installs nothing into the project venv — 95 % of its eight new modules, with every uncovered line inspected and reported as a defensive type guard. Earlier note, retained: no coverage package is installed; BC measured 92.4 % line coverage on its seven new modules using the stdlib `sys.monitoring`, and ran 14 mutation probes (14/14 detected) — see [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) §11 |
| **Latest completed milestone** | **BG-D1b — Setup Identity Pipeline Integration** (§8) — the milestone that makes the stable setup identity reachable from live market data. One new application-layer package, `fmis.setup_observation`; **0 record kinds, 0 repositories, 0 CLI changes, `fmis.swing_setup` untouched**. Placed outside `fmis.pipeline` because that package is market-half and Law 6 forbids it naming a domain root — tried, failed the guard, and rehomed onto the same application-layer tier `pipeline/prices.py` already delegates to. 53 focused tests, 8,499 passing under `-W error`, **100 % statement and branch coverage**, 22/23 adapter and 33/34 domain mutation probes detected. **Not committed, not pushed, and no user-visible capability yet** — no surface calls it, by design. See [report 0025](reports/0025_2026-08-19_SETUP_IDENTITY_PIPELINE_INTEGRATION.md). Previously: **BG-D1 — Stable Setup Identity** (§8) — the milestone that makes a setup keep its name from one bar to the next. Issued as `BQ`, whose own gate (*"confirm no existing package already owns this responsibility"*) **failed** and which was re-scoped by the owner before any code was written. **No new package, no new record kind, no new domain vocabulary**: three modules in `fmis.proposal`, keyed on the `MEASURED` `Anchor` the data model specifies and the repository had built but never constructed. Closes the defect in which 552 directional observations of one unchanged idea were counted as 549 distinct setups, and closes a **latent defect** in which `lifecycle.admit` compared anchors with `==` — including the window-relative `swing_index` — so creation rule 4 could never have deduplicated. 66 new tests, 8,440 passing under `-W error`, **100 % statement and branch coverage** of all three new modules, 33/34 mutation probes detected with the survivor proven equivalent, 0 record kinds added, 0 domain types changed, 0 architecture guards weakened. **Not committed and not pushed; no user-visible capability yet** — the composition-root adapter and the CLI are deliberately the next slice. See [report 0024](reports/0024_2026-08-19_SETUP_IDENTITY_IMPLEMENTATION.md). Previously: **BP — Statistics & Performance Engine** (§8) — the first milestone that answers *"does this system actually have an edge"* rather than *"what happened to this trade"*. One new package, `fmis.statistics` (15 modules), and **no record kind, no repository and no write path at all**: `AP` §25.2 classes cohort statistics as recomputable and disposable, so the engine is a pure projection that leaves the store byte-identical. Five new commands — `fmits statistics`, `performance`, `expectancy`, `equity`, `trades summary` — plus a ninth `fmits today` section and `--as-of` replay on every page. Every rate carries its `n` and is refused below a stated floor; counts never are. 570 new tests, **100 % statement and branch coverage** of all 15 new modules, 60/60 mutation probes detected, 0 record kinds added, 0 domain types changed, no ADR widened and no directional exemption taken, live-verified against a store built entirely through the product's own commands. Ten findings recorded in [report 0023](reports/0023_2026-08-18_STATISTICS_AND_PERFORMANCE_ENGINE_IMPLEMENTATION.md) §5 rather than quietly fixed — the most consequential being a default regime dimension naming a dimension the regime engine has never emitted, which made the per-regime breakdown silently empty. Previously: **BO — Paper Trading & Trade Lifecycle Engine** (§8) — the first milestone that answers *"what happened to this trade"* rather than *"can I take it"*. Two new packages — `fmis.trade_lifecycle` (the domain: four record types and the two folds that are the only place a state or an effective stop exists) and `fmis.paper` (the engine: `advance(state, bar)`, one closed candle at a time) — plus a twelfth command, **`fmits simulate`**, six new `fmits trade` subcommands and an eighth `fmits today` section. A simulated fill is a real ledger `Trade` under `Book.PAPER`, so the position fold, the exposure engine, the valuation and the day's page all work on it with **no new code**. 446 new tests, **100 % statement and branch coverage** of all 19 new and 7 modified modules, 45/45 mutation probes detected, 4 record kinds added (11 → 15), 0 domain types changed, no ADR widened and no directional exemption taken, live-verified against real Binance data with byte-level idempotence. Ten findings recorded in [report 0022](reports/0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md) §5 rather than quietly fixed. Previously: **BN — Position Sizing & Trade Approval Engine** (§8) — the first milestone that answers *"can I take this trade"* rather than *"is this setup good"*. One new package, `fmis.position_sizing` (nine modules in three guarded tiers), and one new command, **`fmits approve`**; `fmits today` now carries an approval status, a recommended size, the resulting open risk, the blocking reasons and the warnings on every actionable candidate. 395 new tests, **100 % statement and branch coverage** of all thirteen new and modified modules, 44/44 mutation probes detected, 0 record kinds added, 0 domain types changed, no ADR widened and no exemption taken, live-verified against real Binance data. See [report 0021](reports/0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md). Previously: **BM — Market Snapshot & Price Integration** (§8) — the bridge between the Market half and the Owner half. Two new packages (`fmis.marks`, the deterministic price snapshot service, and `fmis.valuation`, the one place a price becomes a `MarkQuote`) plus `fmis.pipeline.prices`, the single module in the repository that binds a provider to a mark. **`fmits portfolio`** — what the recorded positions are worth right now, what they cost, what is unrealized and what is exposed, every figure traceable to a named closed candle. `fmits today`'s capital section prints money where it used to print *"no mark source exists"*. 285 new tests, **100 % statement and branch coverage**, 26/26 mutation probes detected, 0 record kinds added, 0 domain types changed, live-verified against real Binance data. See [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md). Previously: **BL — Portfolio Intelligence & Risk Engine** (§8) — `fmis.portfolio_risk`: `AP` §15's boundary, built. Portfolio state, exposure on eight axes, the owner's risk budget evaluated as per-limit facts, and the proposed-trade impact that answers *what changes if I open this now* — with **no verdict, no score and no CLI**, by design. 368 new tests, 96 % coverage reported honestly, 62/64 mutation probes killed with both survivors proven equivalent, venue-agnosticism proved by five executable guards. **Foundational: no user-visible capability yet, and every exposure figure is `Absent` until a mark source exists.** See [report 0018](reports/0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) and [report 0019](reports/0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md). Previously: **BK — Trade Capture & Decision Recording** (§8) — `fmits trade record / show / list / note / close`: the first milestone in which FMITS **writes** to the durable store. Two new packages (`fmis.plan`, holding the `TradePlan` the data model specified and Milestone BH did not build, and `fmis.trade_capture`), a tenth repository, 435 new tests, 100 % statement coverage of the nine new modules, 30/30 mutation probes detected, 0 domain types changed. See [report 0017](reports/0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md). Previously: **BJ — Daily Trading Workspace MVP** (§8) — `fmits today`: one command, seven sections, assembled from the scan and the durable store. The first package reading both halves of FMITS, and the first milestone since AV to change what the owner can do. 247 new tests, 100 % statement **and** branch coverage, 15/15 mutation probes detected, reads the store and writes nothing. See [report 0016](reports/0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md). Previously: **BI — Trade Repository & Journal Engine** (§8) — the durable store for the owner half: nine repositories, a hash-chained write journal, a version engine, 366 new tests, 100 % statement **and** branch coverage, an 81.6 % mutation score, **no user-visible capability yet**. See [report 0015](reports/0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md). Previously: **BH — Trade Domain Foundation** (§8) — the pure domain layer of the owner half: thirteen packages, 608 new domain tests, 100 % statement coverage, **no user-visible capability yet**. See [report 0014](reports/0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md). Previously: **BC — Research Dataset & Counterfactual Replay Correction** (§8) — `fmits backtest --research` derives its warm-up prefix from the production dependencies, fetches it before the measurement window, and verifies per instant that nothing was still warming. Usable research period **41 → 380 days**; largest five-day outcome cluster **49.0 % → 11.4 %**; counterfactual confirmation-age bounds replayed rather than filtered. **No trading policy changed and no performance claim made.** See [the design](docs/design/RESEARCH_HARNESS_CORRECTION_V1.md), [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) and [report 0013](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) |
| **Product Value Level** | **Level 2 — usable swing-analysis assistant**, now with a daily workspace command, a system of record for the owner's own trades, a valued portfolio *and* a deterministic answer to *"can I take this trade"* (ladder in [`reports/0004`](reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §12). **Not Level 3**: no probability is calibrated anywhere, correlation is never measured, liquidity is absent entirely, and open risk is still `Absent` for any position no `TradePlan` records a stop for |
| **Architecture maturity** | **M2 — Connected** ([`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) §11) |
| **Immediate next milestone** | **Awaiting the owner's decision** (§5) — the exactly-one-NOW rule remains temporarily unsatisfied; AT, AU, AV, BH, BI, BJ, BK, BL, BM and BN were all explicitly-scoped, owner-directed implementation tasks, not NOW selections, and this row is unchanged by any of them. §6 holds the sequenced work that follows; §7 holds the unsequenced epics |

### Current user-visible capability

```
fmits trade record BTCUSDT …               # record a swing trade: commitment, fill and thesis
fmits trade show   TRADE_ID                # one recorded trade, assembled and reconciled
fmits trade list   --status open           # every recorded trade, filtered, never ranked
fmits trade note   TRADE_ID --body "..."   # append a journal entry; nothing is ever edited
fmits trade close  TRADE_ID --reason ...   # append an exit and the reason for it
fmits approve BTCUSDT --direction long …   # how large this may be, and whether your limits permit it
fmits approve --plan PLAN_ID --entry …     # size a commitment already recorded, without retyping it
fmits approve … --risk-fraction 0.01       # size at a stated fraction, capped by your own ceiling
fmits portfolio                            # what the recorded positions are worth right now
fmits portfolio --no-marks                 # the same page, with no price fetched and every gap named
fmits portfolio --mark-interval 4h         # price every holding from a coarser closed candle
fmits today                                # the daily trading workspace: one page, seven sections
fmits today --risk-fraction 0.01           # every actionable candidate sized and approved on the page
fmits today BTCUSDT --store-root PATH      # a chosen watchlist, against a chosen store (read-only)
fmits today --no-records                   # the same page, without reading the store at all
fmits today --no-marks                     # read the store, fetch no price
fmits setup  BTCUSDT                       # a deterministic swing-trade setup assessment
fmits setup  BTCUSDT ETHUSDT SOLUSDT       # one per symbol, in the order requested
fmits scan                                 # the fixed 20-symbol watchlist, a readable market report
fmits scan --table                         # the same scan, as the original compact table
fmits backtest                             # replay the policy over real historical candles
fmits backtest --research                  # the corrected research harness (Milestone BC)
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

`trade` is the **system of record for what the owner decided and did**. `record` writes three linked
records — a `TradePlan` holding the commitment (stop, target ladder, stated confidence, originating
setup, proposal, market snapshot and archived analyses), a `Trade` holding the entry fill under the
full tax-capture contract, and a `JournalEntry` holding the thesis. `show` reassembles them and
prints capital at risk and risk/reward **beside the arithmetic that produced them**; `list` filters
and states what it excluded; `note` appends; `close` appends an exit with a reason from the owner's
own vocabulary. **Everything is append-only** — nothing recorded is edited or deleted, the initial
stop cannot change by any code path, and an identical re-run records nothing twice. Every refusal
names the two values that disagree and writes nothing at all. **FMITS places no order, contacts no
exchange and executes nothing.**

`today` assembles one page from what already exists: the market overview and opportunities come from
the same scan `fmits scan` runs, and the portfolio, journal and analysis sections come from the
durable store. It **reads the store and never writes to it**, computes no position size and no open
risk, ranks nothing by desirability, and prints every value it cannot produce with the reason, the
slice that owns it, and the inference its absence forbids.

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

Repository-verified only. Every SHA below was confirmed to exist with `git cat-file -e`. **A
correction, recorded rather than left silent: the "not committed, not pushed" notes on `BJ`, `BK`,
`BL` and `BM` below were true when written and are no longer true** — all four are in `origin/main`
at `4519d0a`, verified by `git cat-file -e` against each package's own modules. Those entries
describe the state at the time each milestone landed and are left unrevised, per this board's
point-in-time convention; this paragraph is the standing correction. `AU` is committed locally at
`fd8a781`, not yet pushed — per `CLAUDE.md`'s git safety rule, pushing requires
separate, explicit authorization, and this milestone's own instruction was "commit locally only, do
not push". `AT`, previously recorded here uncommitted, is now confirmed committed and pushed
(`a271f33` code, `81a6202` docs — both verified present on `origin/main`).

The **complete** milestone history lives in
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md) and is not duplicated here.
This section carries the most recent milestones.

### `BG-D1b` — Setup Identity Pipeline Integration · **DONE**

| Field | Value |
|---|---|
| **Commit** | `1909134` — production code and tests, on top of `ec352b7`'s product-docs commit, with this product-docs commit directly on top of it |
| **Delivered** | The stable identity `BG-D1` built is now reachable from live market data. `fmis.setup_observation` turns a live `SetupAssessment` into a `SetupObservation`, groups a run into `SetupOccurrence`s, and answers *"is this a new idea, or the same one again"* — the fact a surface needs to stop printing one idea as forty |
| **Placement** | **`fmis.setup_observation`, not `fmis.pipeline`.** The brief asked for it beside `pipeline/prices.py`; `fmis.pipeline` is a market-half package and `test_no_market_half_package_imports_the_trading_domain` — *"or the analysis becomes a function of the position, the oldest bias in trading"* — forbids it naming a domain root. It was tried and failed. `prices.py` is the pattern rather than the counter-example: it holds no domain import either and delegates to `fmis.marks`, an application package, which is the same shape as every domain edge `pipeline/cli.py` has |
| **Shape** | One application-layer package, two modules, six exports. **0 record kinds added (15 → 15)**, 0 repositories, 0 CLI changes, 0 lines of `fmis.swing_setup` touched |
| **The rules held** | The anchor is the stop's `MEASURED` origin (`BD` R-13); `LevelOrigin.index` travels as provenance and never as identity; `float` → `Decimal` crosses once through `exact_from_market_price`; an AST test asserts the package contains no arithmetic operator at all; the direction map is **derived** from the engine's own members, so ADR-0028's directional guard needed no exemption |
| **Quality** | 53 focused tests; 8,440 → 8,499 passing under `-W error`; **100 % statement and branch coverage** of the new package; **22/23** adapter mutation probes detected and **33/34** domain probes re-detected, both survivors proven equivalent; 4 import-order regression tests; 0 new runtime dependencies |
| **Guards** | **One allowlist extended and stated plainly**: `test_nothing_below_imports_level_crossing` gained a seventh permitted consumer, on the identical footing Milestone AR was admitted (*reuses `PriceLevel`/`LevelSide` by reference, computing nothing new*), with the justification written into the test. The rule it protects is unchanged. No other guard file was touched |
| **Records** | [report 0025](reports/0025_2026-08-19_SETUP_IDENTITY_PIPELINE_INTEGRATION.md) |
| **Not built, deliberately** | **No surface calls it yet** — `fmits setup`, `fmits scan` and `fmits today` are byte-identical, so there is **no user-visible capability** and the changelog is correctly unchanged. Wiring a surface is the next slice and is where the capability arrives. Freshness's three bar ages stay `Absent` with a reason: the engine computes none, and a composition root may not derive one. `SetupType` is still never populated |

### `BG-D1` — Stable Setup Identity · **DONE**

| Field | Value |
|---|---|
| **Commit** | `ec352b7` — production code and tests, on top of `2da08b9`, with its product-docs commit directly on top of it |
| **Delivered** | A setup keeps the same name from one bar to the next. One idea that persists for a week is **one** setup rather than forty — closing the defect in which 552 directional observations of a single unchanged idea were counted as 549 distinct setups (report 0012 §7) |
| **Origin** | Issued as `BQ — Swing Setup Engine Foundation` (a new `src/fmis/setup/` package, twelve types, an append-only repository, a `fmits setup` CRUD command). That brief's own gate — *"confirm no existing package already owns this responsibility"* — **failed**: `OpportunityProposal` + `OpportunityRepository` already are the immutable append-only setup record, `SetupState`/`SetupAssessment`/`EvidenceCitation` already are the rest, and `fmits setup` already exists. `TRADING_DOMAIN_DATA_MODEL_V1` §174 forbids a fourth meaning of "setup", §617–618 places the Setup types in `fmis.proposal`, and §9.3–9.4 class two of them as non-storable projections. Re-scoped to `BG-D1` by the owner before any code was written |
| **Shape** | **No new package, no new record kind (15 → 15), no new domain vocabulary.** Three modules inside `fmis.proposal` — `setup_identity`, `observation`, `occurrence` — plus two fixes to existing code |
| **The rule** | An identity may only be built from facts that do not move when the window moves. A setup's identity is its `MEASURED` `Anchor`; the level origin contributes the pivot candle's **absolute timestamp**, its label and its confirmation window. `LevelOriginRef.swing_index` is **window-relative** and is carried as provenance but excluded from identity |
| **Reuse** | `SetupType` is **not** a new class — §9.2 makes it a `VersionedTerm` in the `setup` vocabulary, the shape `TradePlan.setup_type` already carries. `SetupObservation` composes `SetupReading` rather than redeclaring its eighteen fields. `Anchor`, `LevelOriginRef`, `FreshnessReading` and `StopTriggerSemantics` were built in `BH` and are used, not rebuilt |
| **Latent defect closed** | `lifecycle._anchor_matches` compared anchors with `==`, which includes `swing_index` — so **creation rule 4 could never have deduplicated** and would have created a new proposal every bar, with frozen artifacts pointing at them. It was inert only because nothing in `src/` had ever constructed an `Anchor` |
| **Quality** | 8,378 → 8,440 tests under `-W error`, 0 failures; **100 % statement and branch coverage** of all three new modules (0 missed); **33/34 mutation probes detected**, the one survivor proven equivalent; identical digests across separate processes; 0 new packages, 0 record kinds, 0 domain types changed, 0 architecture guards weakened, 0 new runtime dependencies. The zero-engine-edge guard passes unchanged — the domain still imports nothing from the market half |
| **Records** | [report 0024](reports/0024_2026-08-19_SETUP_IDENTITY_IMPLEMENTATION.md) |
| **Not built, deliberately** | **No composition-root adapter** converting a live `SetupAssessment` into a `SetupObservation`, and **no CLI** — so there is **no user-visible capability yet** and the changelog is correctly unchanged. The adapter belongs in `fmis.pipeline` beside `pipeline/prices.py` and is the natural next slice. `occurrence_gap_bars` is left unchosen, as the data model requires. `research_identity`'s separate grouping rule is left in place; consolidating it onto `anchor_identity` is follow-up work |
| **Correction on record** | The task premise that BP's statistics overcount setups is **not accurate**: `fmis.statistics.collect` folds over trades, one `TradeStat` per trade, and never counts observations. No change to `fmis.statistics` was required or made. The overcounting was in the backtest harness, and that is where it was fixed |

### `BP` — Statistics & Performance Engine · **DONE**

| Field | Value |
|---|---|
| **Commit** | `e1cfad0` — production code and tests, on top of `3a2bd3a`, with the product-docs commit directly on top of it. Committed and pushed on the owner's explicit instruction, after an independent release gate |
| **Delivered** | The answer to *"does this system actually have an edge"*, from recorded history alone. `fmits statistics` — counts, performance, risk, excursion quality, the equity and drawdown curves and twelve breakdowns; `fmits performance`; `fmits expectancy`, which puts the sample in front of the numbers; `fmits equity`; `fmits trades summary`. `--as-of` replays any of them as they stood at a past instant. `fmits today` gains a ninth section |
| **Shape** | One package (`fmis.statistics`, 15 modules), 5,280 new production lines, **no record kind, no repository and no write path** — `AP` §25.2 classes cohort statistics as recomputable and disposable, and a guard asserts no store write verb appears anywhere in the package |
| **Reuse** | No risk arithmetic, position fold, R calculation, sizing, portfolio maths, valuation, capture or paper logic is duplicated. The partial-total rule is `fmis.portfolio_risk.sum_or_absent`, the capital at risk is `fmis.plan.capital_at_risk` through `TradeView`, the frozen excursion is `OutcomeReading`'s, the two read paths are `fmis.paper.views` and `fmis.trade_capture.views` called rather than re-implemented, and `UNCLASSIFIED` is `fmis.portfolio_risk`'s own constant |
| **The discipline** | Every rate carries its `n` and is refused below a stated floor — `AP` §20.7 rule 2's guard, at the boundary where no surface can route around it. **Counts are never floored**: a count is a fact at any `n` and a rate is a claim about a process. Breakdowns apply no multiplicity correction and print the number of cells examined, which is `TRADER_WORKSPACE` §3.4.12's mechanism rather than its paragraph |
| **Quality** | 7,805 → 8,378 tests under `-W error`; 100 % statement and branch coverage of all 15 new modules (0 missed) and of the 4 modified `fmis.today` modules; 60/60 mutation probes detected, 0 survivors; 0 collisions across 1,147 exports; 0 import cycles across 257 modules; 0 new runtime dependencies; 0 record kinds added; 0 domain types changed; no ADR widened and no directional exemption taken |
| **Records** | [report 0023](reports/0023_2026-08-18_STATISTICS_AND_PERFORMANCE_ENGINE_IMPLEMENTATION.md) |
| **Not built, deliberately** | `AP` §20.5's behavioural and bias metrics — stale-proposal rate, invalid-entry rate, rejection quality, disposition effect — which need the `DecisionEpisode` corpus `C10` owns and the whole proposal lifecycle behind it. `calibrated_probability` (`AP` §20.6) remains `ABSENT` until earned. The `n` guard they will all need exists now and is load-bearing before they arrive |

### `BO` — Paper Trading & Trade Lifecycle Engine · **DONE**

| Field | Value |
|---|---|
| **Commit** | `e4195fc` — production code and tests, on top of `51814b1`, with the product-docs commit directly on top of it. Committed and pushed on the owner's explicit instruction, after an independent release gate |
| **Delivered** | The complete deterministic life of a swing trade, simulated. `fmits trade plan` records a commitment with no fill; `fmits trade activate` hands it to the simulator with an entry type, a size, an exit ladder and stop rules; `fmits simulate` advances every live activation one closed candle at a time; `fmits trade status`, `history` and `lifecycle` read it back; `fmits trade stop` and `cancel` are the owner's own acts, appended. `fmits today` gains an eighth section |
| **Shape** | Two packages (`fmis.trade_lifecycle`, 5 modules; `fmis.paper`, 12), `fmis.pipeline.candles`, `fmis.persistence.lifecycle_repositories`, four record kinds, an eleventh repository. 7,684 new production lines |
| **Reuse** | No risk arithmetic, position fold, RR calculation, sizing, portfolio maths, valuation, mark calculation, trade capture or approval logic is duplicated. The sign rule is `TradeDirection.sign`, the risk distance is `fmis.portfolio_risk.stop_distance`, the average entry is `AverageCost.per_unit`, the realized P&L is the position fold's, and the ledger, journal, exposure and constraint engines are called rather than re-implemented |
| **Quality** | 7,359 → 7,805 tests under `-W error`; 100 % statement and branch coverage of every new and modified module; 45/45 mutation probes detected, 0 survivors; 0 collisions across 1,045 exports; 0 import cycles; 0 new runtime dependencies; 0 domain types changed |
| **Records** | [report 0022](reports/0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md) · [design](docs/design/PAPER_TRADING_AND_TRADE_LIFECYCLE_V1.md) |
| **Not built, deliberately** | A venue `Order`; a general `PlanAmendment` for targets, size and expiry; walk-forward, shadow mode and execution validation — the engine is `(state, bar) → events` precisely so those are the same function driven by a different sequence |

### `BN` — Position Sizing & Trade Approval Engine · **DONE** *(committed and pushed)*

| Field | Value |
|---|---|
| **Commit** | **A** `b66a88f` (production code + tests) · **B** the product-docs commit recorded directly on top of A. Both pushed to `origin/main` on the owner's explicit authorization for this milestone |
| **ADR** | **none written, none amended, and no exemption taken.** ADR-0028's directional-vocabulary guard covers `fmis.position_sizing` with **no edit**: the package passes `TradeDirection` through opaquely and lets `fmis.portfolio_risk.stop_distance` own the sign rule, so it never spells a side. A test asserts the package is absent from both exemption lists and present in the covered set, so a future exemption is a deliberate act. `AP` §15.4–15.6 and `SWING_TRADING_MVP_BLUEPRINT_V1` §7/§9.4 already specify this boundary, the refusals and the sizer's inputs and outputs by name |
| **Design** | **none written.** The milestone creates no new contract; `BH`, `BI`, `BK`, `BL` and `BM` built every type it assembles |
| **Report** | [report 0021](reports/0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md) |
| **Tests** | 6,964 → **7,359** (+395, in eleven new files), identically under `-W error`. **100 % statement and 100 % branch coverage** of all thirteen new and modified modules (1,933 statements, 662 branches). **44 mutation probes, 44 detected, 0 survivors**, byte-identical restoration verified by SHA-256 *and* by a cleared bytecode cache |

**Product value delivered — the first milestone that answers *"can I take this trade"*.** Every
milestone before it answered *"is there a setup here"* (`AR`, `AT`, `AU`) or *"what do I hold"*
(`BK`, `BL`, `BM`). **`fmits approve`** answers the question that actually stands between an idea and
an order: how large may this position be, and do the owner's own limits permit it. **`fmits today`**
now carries an approval status, a recommended size, the resulting open risk, the blocking reasons and
the warnings on every actionable candidate.

**`ApprovalResult` is a deterministic fact, not an opinion.** No model is consulted anywhere in the
package, no probability is attached to anything, and there is no field on any type that could hold
*"take this trade"* or *"skip this trade"* — a guard asserts the package names neither. `AP` §15.5,
unchanged: *"`EXCEEDED` on the open-risk budget is a fact; 'don't take this trade' is the owner's
conclusion."*

**It duplicates no arithmetic.** The sign rule, the risk distance, the capital at risk, the maximum
quantity for a risk allowance, the exposure fold, the before/after impact and every limit comparison
are `fmis.portfolio_risk`'s, called rather than re-implemented. The one thing this package adds is
the step that engine deliberately left out — deciding what the risk allowance should be, which `AP`
§15.4 places in the risk layer precisely so a portfolio object never acquires a recommendation.

**It invents no threshold, and the ceiling is not a target.** The fraction is resolved from the
owner's own choice, else from `RiskLimit.default_below_ceiling`, else from **nothing** — `SPEC` §8.1
calls 2 % *"a hard ceiling, not a default target"*, and a system that sized at the ceiling when
nothing else was stated would have converted one into the other with nobody deciding to. A guard
asserts the four computing modules hold no numeric literal beyond `0` and `1`.

**Severity is the owner's at every point it is read.** `EXCEEDED` on a `HARD_BLOCK` limit blocks;
on an `ADVISORY` one it warns. `AT_LIMIT` warns on both — a stated maximum is not breached by
touching it, so a candidate landing exactly on the line is approved and the *next* one is blocked.
An unmeasurable limit is indeterminate or a warning by the same rule, and is **never** silently
within.

**Nothing is stored and nothing is executed.** No `RecordKind` was added, no repository was touched,
no write verb appears anywhere in the package, and a CLI test observes the store's bytes before and
after a run and asserts they are identical.

**Nine defects and design errors were found before release** (report 0021 §4), the most consequential
being an advisory limit that blocked a trade the owner had explicitly said not to block. Two were
found by the live run and by no test, because both offending lines fitted the page. One is **not
fixed and is recorded**: an exact quotient that does not terminate carries a 28-digit tail onto the
page, and shortening it would be a rounding policy this system does not set.

**Live-verified against real Binance data** on 2026-08-15: `fmits approve ETHUSDT` returned
`APPROVED` at 4.625 ETH with 925 USDT at risk; a stated 10 % fraction was reduced to the owner's 2 %
ceiling with the reduction named; a transposed stop returned `BLOCKED` with **exit code 0**, because
the evaluation succeeded and its answer was no; and `fmits today` over the full watchlist returned 2
confirmed and 2 candidates, each carrying its own approval status, size, resulting open risk and
warnings.

**What it still does not do.** Nothing is stored, so *"what did the engine say when I took this"* is
unanswerable. Correlation is never measured — `TR-DUP` reports duplication, which is a fact, not
correlation, which is an inference this system has no data for. Liquidity is absent entirely. Period
loss and drawdown limits remain unmeasurable and are reported as such. Candidates are evaluated
independently and the page says so. There is no override log. All ten limitations are in report 0021
§6.

### `BM` — Market Snapshot & Price Integration · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **Commit** | **none.** The work is in the working tree on top of `dbc4765`, alongside `BJ`, `BK` and `BL`; committing and pushing each require separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written, none amended.** The milestone creates no new contract: `AP` §14 specifies the mark and its provenance, `IMPLEMENTATION_ROADMAP_V1` §C6 names the selection basis by name — *"the last available closed-candle close"* — and `BH`/`BI`/`BL` built every type this assembles. Two exposure labels were reworded rather than exempting a package from ADR-0028's guard, and one docstring was reworded rather than widening `fmis.daily`'s raw-text import guard. See [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md) §7 |
| **Design** | **none written.** Wiring that needs an ADR is wiring that crossed a boundary it should not have |
| **Report** | [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md) |
| **Tests** | 6,679 → **6,964** (+285, in eleven new files), identically under `-W error`. **100 % statement and 100 % branch coverage** of the ten new/modified modules (692 statements, 196 branches). **26 mutation probes, 26 detected, 0 survivors**, byte-identical restoration verified by SHA-256 *and* by a cleared bytecode cache |

**Product value delivered — the market half and the owner half finally meet.** `BL`'s own record
named the gap: *"every exposure figure is `Absent`, because no mark source reaches the owner half."*
This milestone closes it. **`fmits portfolio`** answers *what are my positions worth right now* —
market value, cost basis, unrealized P&L, gross/net/long/short exposure — with every figure traceable
to a specific closed candle on a stated timeframe, and every figure that cannot be computed printed
with the market that broke it.

**Two packages and one module, split exactly along the existing boundary.** `fmis.marks` (market
half) imports `fmis.data` and nothing else; `fmis.valuation` (the bridge) holds the one function in
the repository that turns a price into a `MarkQuote`; `fmis.pipeline.prices` is the one module that
binds a provider to a mark. All three claims are executable guards, not prose.

**`fmis.portfolio_risk` was not touched.** Its dependency surface is byte-for-byte what `BL` shipped
and its venue-agnostic guards still pass unchanged — the adapter is outside the owner domain, which
is what the brief required.

**No pricing logic is duplicated, and each delegation is named.** Market value delegates to
`PortfolioState.net_exposure`, unrealized P&L to `Position.unrealized_pnl`, the float→exact crossing
to `fmis.money.exact_from_market_price` (*"the one `float` → exact crossing in the whole domain"*),
and the partial-total rule to `sum_or_absent`.

**Three refusals, each stated rather than approximated.** A **perpetual** is never priced from its
spot pair — two instruments, two prices. A price from **after** the instant being valued is refused
per market with both dates named. A holding quoted in a currency other than the base is reported
**unvalued** rather than converted, because this system holds no FX rate.

**Nothing is stored, and that is a decision.** A frozen `PortfolioSnapshot` requires deposits and
withdrawals since the previous one, and no transfer event kind exists in this build — so a snapshot
written now would carry a fabricated `FlowSummary` and every return figure derived from it would be
wrong. Recorded as limitation `VA-1` on every page. **No `RecordKind` was added.**

**Three real defects were found before release and are recorded rather than quietly fixed** (report
0020 §5): an invalid CLI flag reported as a corrupt store, a shadowed parameter, and a
doubly-indented header the width tests could not see. A fourth finding is methodological: the
mutation harness poisoned its own bytecode cache (§6).

**What it still does not do.** Open risk is still `Absent` for any position no `TradePlan` records a
stop for — this milestone closed the *mark* half of `BJ`'s `TD-3` and left the *plan* half untouched.
No historical prices, so a past valuation refuses today's candles rather than reading the right ones.
Equity needs a `PortfolioSnapshot` for its cash half. Non-spot markets are unpriceable by refusal.
One mark interval for every market. Nothing is scheduled. All eight limitations are in report 0020 §9.

### `BL` — Portfolio Intelligence & Risk Engine · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **Commit** | **none.** The work is in the working tree on top of `dbc4765`, alongside `BJ` and `BK`; committing and pushing each require separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written, none amended.** ADR-0028 §5's directional-vocabulary rule was widened **inside its own stated extension point**, from five domain packages to six — `fmis.portfolio_risk` computes long, short and directional exposure and carries the sign rule capital at risk depends on. The justification is written into the guard test itself, and a new assertion now holds every exempt domain package to the no-engine rule that the ban exists to protect. See [report 0018](reports/0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) §10 |
| **Design** | **none written.** The design already existed and had not been built: `TRADING_DOMAIN_ARCHITECTURE_V1` §15 specifies the Portfolio Intelligence boundary and the `PortfolioConstraintCheck` contract in full, and `TRADING_DOMAIN_DATA_MODEL_V1` §12.5–12.6 writes the entity cards. Report 0018 records what was built against them |
| **Report** | [report 0018](reports/0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) · hostile review [report 0019](reports/0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md) |
| **Tests** | 6,311 → **6,679** (+368: 367 in seven new files, one added to the ADR-0028 boundary guard), identically under `-W error`. **96 % statement coverage** of the eight new modules (1,218 statements), reported honestly rather than rounded — 43 of the 47 uncovered lines are `raise` type/validation guards and the other 4 are defensive branches unreachable through the package's public entry points. **64 mutation probes, 62 killed, 2 survivors, both proven equivalent** |

**Product value delivered — the system stops evaluating trades one at a time.** One new package,
`fmis.portfolio_risk`, holding `AP` §15's boundary: the deterministic step between portfolio facts and
the owner's own limits. It answers **what changes in the portfolio if the owner opens this proposed
trade now** — as two portfolio states and the differences between them, never as a verdict. **3,767
production lines, 47 new public exports, 0 collisions, 0 new dependencies, 0 import cycles, 0
production files outside the new package modified, and 0 domain types changed.**

**No CLI command was added, and that is deliberate** — the milestone was scoped to the deterministic
backend and explicitly forbidden from becoming a dashboard. Its changelog entry is therefore
**Foundational**, not a product release.

**Venue-agnostic by construction, and proved rather than claimed.** Five executable guards assert that
no module imports a provider, imports a market-half engine, or names a venue anywhere in its
*executable* code — one of which found and rejected a real hit, a `venue:binance` example baked into a
help string. Binance, EVEDEX, a future DEX and a hand-kept account all reach the same arithmetic
through the same records.

**What the hostile review found.** Three defects, all fixed. The one that mattered: two BTC longs
quoted in USDT and USDC read as **unrelated symbols** — correlated exposure presented as
diversification, the exact attack the brief named. Fixed with a base-asset exposure axis and
cross-quote duplicate detection. Also fixed: a stale snapshot's equity was indistinguishable from a
current one, and a limit stated in the wrong currency took down the entire constraint check instead of
producing one indeterminate result.

**What it still does not do.** **Every exposure figure is `Absent` until a mark source exists** — open
risk, duplicate detection and the constraint engine work today; gross, net, leverage and every
concentration share do not, because no price reaches the owner half. No position sizing product (the
primitive exists; the equity contract it needs is a recorded decision gap). No `PortfolioConstraintCheck`
is persisted. No statistical correlation. `fmits today` is unchanged and its integration point is
documented. All limitations are enumerated in report 0018 §§11–14.

### `BK` — Trade Capture & Decision Recording · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **Commit** | **none.** The work is in the working tree on top of `dbc4765`, alongside `BJ`; committing and pushing each require separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written, none amended.** The milestone crosses no boundary an existing ADR does not govern — ADR-0027 supplies identity and publication, ADR-0001 the timestamps, ADR-0005 reject-never-repair. ADR-0028 §5's directional-vocabulary rule was widened **inside its own stated extension point**, to five domain packages and one surface, each justified in the guard test itself and in report 0017 §9 |
| **Design** | **none written.** The design already existed and had not been built: `TRADING_DOMAIN_ARCHITECTURE_V1` §9 and `TRADING_DOMAIN_DATA_MODEL_V1` §10.3 specify `TradePlan` in full, down to its package name, and `SWING_TRADING_MVP_BLUEPRINT_V1` §12.3 records the omission as accepted debt. Report 0017 §2 records the finding and the three rejected alternatives |
| **Report** | [report 0017](reports/0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md) |
| **Tests** | 5,876 → **6,311** (+435), identically under `-W error`. **100 % statement coverage** of the nine new modules (962 statements). **30 mutation probes, 30 detected, 0 survivors**; two probes exposed real gaps in the tests during development and both were closed by adding a test rather than weakening the probe |

**Product value delivered — FMITS becomes the system of record.** Two new packages (`fmis.plan`,
`fmis.trade_capture`), a tenth repository, and one new command with five subcommands. **This is the
first milestone in which FMITS writes to the durable store**: `BI` built nine repositories no command
reached, `BJ` read them and wrote nothing. **3,279 production lines, 66 new public exports, 0
collisions, 0 new dependencies, 0 import cycles, 5 existing production files modified — all
additively — and 0 domain types changed.**

**What the owner can do after it that was impossible before.** Record a complete swing trade in one
command — the commitment (direction, stop, target ladder, size, stated confidence, the setup and the
analysis it came from), the entry fill under the full tax-capture contract, and the thesis behind it —
then read it back with capital at risk and risk/reward shown beside the arithmetic that produced them,
append notes to it, and close it with a reason. Before this, the owner's stop existed on a chart and
in their memory; after it, *"did I honour my stop?"* has an answer.

**The finding that shaped it.** Eight of the fourteen fields the brief asks for had no home in the
domain, because `TradePlan` — the data model's entity 19, designed since `AP` — had never been built.
`fmis.plan` builds it to the card the data model already wrote. `Trade.plan_id`, an optional field
present since `BH` precisely because the package did not exist, is the link.

**What it still does not do.** No `PlanAmendment`, so a *widened* stop is still invisible — the
largest remaining piece of C4 and the natural next item. No risk-first sizing (it records the size the
owner filled and reports the risk it implies). No `fmits trade correct`, though the store's correction
path exists and the read path already resolves and reports one. `fmits today` does not yet read a
`TradePlan`. All eight limitations are enumerated in report 0017 §8.

### `BJ` — Daily Trading Workspace MVP · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **Commit** | **none.** The work is in the working tree on top of `dbc4765`; committing and pushing each require separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written, none amended.** The milestone creates no new contract. It does occupy a boundary — the first package reading both halves of FMITS — which is asserted by test in both directions and recorded in report 0016 §3; whether that boundary deserves an ADR of its own is an open decision for the owner (§10) |
| **Design** | **none written.** Implementation forced no design decision the existing records did not already contain: `BE` designed the page, `BF` the warning taxonomy, `BG` the domain, `BI` the store. The one place implementation departed from the brief — no single directional regime label, per ADR-0025 — is recorded in report 0016 §2.1 |
| **Report** | [report 0016](reports/0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md) |
| **Tests** | 5,629 → **5,876** (+247). **100 % statement and 100 % branch coverage** of the 975 statements and 340 branches in the new package. **15 targeted mutation probes, 15 detected, 0 survivors**, byte-identical restoration verified by SHA-256; the two initial survivors each exposed a real gap in a test rather than in the code, and both are recorded in report 0016 §6.1 |

**Product value delivered — the store, the domain and the engines get a surface.** One new package,
`fmis.today`, and one new command, `fmits today`: seven sections on one page — market overview,
portfolio overview, today's opportunities, a priority queue, the trade journal, recent analysis, and
every workspace warning with its stated source. It is the **first package in this repository that
reads both halves of FMITS**, and the crossing is exactly one package wide, asserted in both
directions. **2,603 production lines, 51 new public exports, 0 collisions, 0 new dependencies, 0
import cycles, 1 existing production file modified** (`pipeline/cli.py`, additively; eight existing
guard tests were widened, each with its own recorded justification).

**What the owner can do after it that was impossible before.** Open one command in the evening and
see, in one place: what the market is doing, what positions and capital are recorded, what is
actionable, what deserves attention and what this system refuses to size, what has been decided and
written down, what has been durably archived, and what none of it can be trusted to say. `BI`'s store
had no reader; it has one now.

**What it still does not do**, stated on every page it prints: no position size, portfolio risk or
leverage; no calibrated probability; no correlation between markets; no per-role freshness triple; no
single bull/bear/neutral regime label (ADR-0025); no macro, news, derivatives, on-chain or liquidity
data; and nothing about holdings that are not recorded in the store. It writes nothing — asserted by
an AST guard over the whole package and observed against a real store on disk.

### `BI` — Trade Repository & Journal Engine · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **Commit** | **none.** The work is in the working tree on top of `c96c3e4`; committing and pushing each require separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written, none amended.** The store implements Architecture §24 as accepted; nothing in it required a new decision the ADRs do not already carry |
| **Design** | [TRADE_REPOSITORY_AND_JOURNAL_ENGINE_V1.md](docs/design/TRADE_REPOSITORY_AND_JOURNAL_ENGINE_V1.md) (new — records what was built, not a proposal) |
| **Report** | [report 0015](reports/0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md) |
| **Tests** | 5,263 → **5,629** (+366). **100 % statement and 100 % branch coverage** of the 1,623 statements and 416 branches in the new package. Four `mutmut` 3.7.0 sweeps over 1,987 mutants took survivors 490 → 363, a **81.6 %** score. A verification pass re-audited the residue and found **eighteen behavioural survivors the first triage had misclassified**; all eighteen were closed and each test verified against its own mutant. Report 0015 §7 records that the first classification was wrong and why |

**Product value delivered — the domain becomes keepable.** One new package, `fmis.persistence`: nine
repositories over one durable store, an append-only **hash-chained write journal** carrying timestamp,
source, author, reason, version and provenance for every write, a **version engine** answering *what
does this say now*, *what did it say then* and *every version between*, and a **rebuildable index**
proven rebuildable by a test that deletes it. `update` raises on all nine — the only ways a record's
meaning changes are supersession and the next observation — and `PositionRepository` refuses every
write, which is Architecture §24.3's durability classification enforced instead of documented.
**4,700 production lines, 60 new public exports, 0 collisions, 0 new dependencies, 0 existing source
files modified** (one test file gained two shared fixtures).

**What the owner can do after it that was impossible before: nothing.** There is still no CLI surface
and no composition root filling a `MarketSnapshot` from the engines. That is why there is **no
changelog entry**. The one thing report 0015 §8 names as blocking real use is the **full-dump export**
Architecture §5.7 item 4 requires *before the first real record is written* — it is not built, and it
is the natural next slice.

### `BH` — Trade Domain Foundation · **DONE** *(committed locally, not pushed)*

| Field | Value |
|---|---|
| **Commit** | `64e82e9` (production code + tests + boundary note) — committed locally on top of `7ced9e2`; push requires separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none written.** One accepted ADR is crossed — ADR-0028 §5's directional-vocabulary rule — and amending an accepted ADR was not authorized by this milestone. The crossing, the guard change and the proposed amendment are recorded in [DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md](docs/design/DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md) and are **an open decision for the owner** (§10) |
| **Design** | [TRADING_DOMAIN_DATA_MODEL_V1.md](docs/design/TRADING_DOMAIN_DATA_MODEL_V1.md) (`BG`, implemented) · [DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md](docs/design/DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md) (new, implementation-revealed) |
| **Report** | [report 0014](reports/0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md) |
| **Tests** | 4,653 → **5,263** (+610). **100 % statement and 99 % branch coverage** of the 3,697 statements in the new domain, measured with `coverage` run through `uv run --with coverage` (not installed into `.venv`, not added to `pyproject.toml`). No mutation sweep was run — stated as a weaker signal in report 0014 §8 |

**Product value delivered — objects, not capability.** Thirteen new packages implement the pure domain
layer of the owner half: `Trade` and `TradeStatus` with correction-by-supersession, `OpportunityProposal`
with an append-only lifecycle stream whose fold *is* its state, `Position` as a pure fold over the
resolved ledger, `MarketSnapshot` as the frozen bundle a decision rests on, `AnalysisRecord` as the
citation edge to the archive, `JournalEntry`/`TradeJournal`, `RiskBudget`/`RiskBudgetState` and
`PortfolioSnapshot`. Exact asset-tagged money, content-derived identity, `Absent(reason)` everywhere,
no stored quotient, no composite score, no invented threshold, and a model may author exactly one
record type. **10,285 production lines, 228 new public exports, 0 collisions, 0 new dependencies, 0
existing source files modified.**

**What the owner can do after it that was impossible before: nothing.** There is no CLI surface and no
composition root; a later slice wires the engines into `MarketSnapshot` and the CLI into the ledger.
That is why there is **no changelog entry** — `CLAUDE.md` reserves the changelog for user-visible
capability, and recording this as a release would be exactly the failure that rule prevents.

### `BC` — Research Dataset & Counterfactual Replay Correction · **DONE** *(committed locally, not pushed)*

| Field | Value |
|---|---|
| **Commit** | committed locally on top of `f9ddc54`; push requires separate, explicit authorization (`CLAUDE.md`) |
| **ADR** | **none** — adds no boundary. One keyword-only, research-only parameter on `evaluate_setup`, contained by 30 tests |
| **Design** | [RESEARCH_HARNESS_CORRECTION_V1.md](docs/design/RESEARCH_HARNESS_CORRECTION_V1.md) |
| **Review** | [report 0013](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) — hostile review; no P0, three P1 and three P2 found **during** the milestone and all fixed before the evidence run, four items disclosed as open limitations |
| **Report** | [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) |
| **Tests** | 4,488 → **4,653** (+165). 92.4 % line coverage on the seven new modules (stdlib `sys.monitoring`; no coverage package installed or added). 14 mutation probes, 14 detected, 0 survivors |

**Product value delivered — research validity, not trading performance.** Milestone BB showed that
every research number in the AV–BA chain rested on ~43 usable days of a window described as 400 days,
and that the confirmation-age counterfactual had been emulated by deleting rows rather than replaying
the policy. `fmits backtest --research` now derives the warm-up prefix from the production
dependencies themselves, fetches it **before** the measurement window, and verifies at every measured
instant that no role was warming up or short of its requested window (measured: 0 and 0, minimum 250
candles at all three roles). The usable period rises from a measured **41 days to 380 days**, and the
largest five-day outcome cluster falls from **49.0 % to 11.4 %**. Counterfactual staleness bounds are
replayed through the unmodified production path; replaying at the production bound reproduces the
baseline exactly. **No policy changed** — `CONFIRMATION_LOOKBACK_BARS` is still 10, no bound is
recommended, and the milestone makes no claim of improved trading performance.

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
| **D-16** | **Where directional vocabulary is permitted to live.** ADR-0028 §5 names `fmis.swing_setup` and `fmis/pipeline/cli.py`; Milestone `BH`'s ledger, position, proposal and snapshot types necessarily hold `LONG`/`SHORT`/`BUY`/`SELL` as **owner assertions about the owner's own money**, not as an engine's reading of a market. The repository-wide guard was widened by name and strengthened with a market-half-only scan; the ADR was **not** amended, because amending an accepted ADR was outside this milestone's authorization. `ADR_IMPLEMENTATION_GATE.md` Part 3 predicted this as *"the one genuinely required decision not on any list"* | Every further owner-half package | [DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md](docs/design/DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md) · [ADR-0028](docs/adr/ADR-0028-directional-interpretation-boundary.md) §5 · [report 0014](reports/0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md) §6 |
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
