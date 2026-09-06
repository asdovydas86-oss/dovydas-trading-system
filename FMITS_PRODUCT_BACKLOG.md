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
| **Test count** | **14,049 collected, 14,049 passing**, identically under `-W error` (13,384 before Milestone CD; +665 — 660 in `fmis.paired_dependence` and the shared import-tier guard, plus 5 new or rewritten architecture guards in existing files). Earlier note, retained: **8,954 collected, 8,954 passing**, identically under `-W error` (8,703 before Milestone BS; +251). Earlier note, retained: **7,359 collected, 7,359 passing**, identically under `-W error` (6,964 before Milestone BN; +395). Earlier note, retained: **A second stale-`__pycache__` incident occurred during BM and is recorded rather than absorbed:** BM's mutation harness restores each probed file byte-identically, which inside one filesystem mtime second reproduces the exact `(mtime, size)` pair a `.pyc` header records — so the interpreter kept serving bytecode compiled from the *mutated* source and a passing test failed as a phantom. SHA-256 restoration is necessary and not sufficient; the harness now clears every `__pycache__` on both sides of every probe. See [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md) §6. Earlier note, retained: Earlier note, retained: The two long-standing `test_swing_setup_scan_report.py` failures previously recorded here as "a float-formatting flake" were neither a flake nor a source defect: a git-ignored `__pycache__` entry compiled from an older `scan_report.py` (`,.2g` where the source says `,.6g`), with a matching recorded mtime and size, which also made `fmits scan` print prices in scientific notation on this machine. Clearing the cache resolved both with no source change — see [report 0013](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) F7 |
| **Public exports / collisions** | **1,220 public names, 0 collisions** across the repository after Milestone BS (`fmis.swing_workspace` 42 new; `fmis.today` 60 → 62). **Two names were renamed during BS precisely because the zero-collision guard caught them** — `PAGE_WIDTH` → `WORKSPACE_PAGE_WIDTH` against `fmis.setup_evidence`, and `OBJECTIVE` withdrawn from the package root against `fmis.today`. Previously **896 public names, 0 collisions** across the repository after Milestone BN (`fmis.position_sizing` 44 new, `fmis.today` 51 → 52). Previously **851 public names, 0 collisions** after Milestone BM (`fmis.marks` 12 new, `fmis.valuation` 23 new, `fmis.pipeline` 35 → 40). Previously **811 public names, 0 collisions** after Milestone BL (`fmis.portfolio_risk` 47 new; two names were renamed during BL — `stop_distance` and `read_exposure_lines` — precisely because the zero-collision guard caught them against `fmis.plan.risk_distance` and `fmis.persistence.read_lines`). Previously **764 public names, 0 collisions** after Milestone BK (`fmis.plan` 14 new, `fmis.trade_capture` 52 new, `fmis.persistence` 60 → 61). Earlier note, retained: `fmis.swing_setup` 53 → **94** names (+41: the corrected research harness — `run_research_study`, `derive_warmup`, `compare_variant`, `post_filter_comparison`, the research models and their constants), **0 collisions** |
| **Import cycles** | 0 — measured at module granularity across **275 modules** after Milestone BS. Previously 221 modules after Milestone BN (212 before it) |
| **Runtime dependencies** | 0 added, and `pyproject.toml` / `uv.lock` are unchanged. Milestone BN measured **100 % statement and 100 % branch coverage** of all thirteen new and modified modules (1,933 statements, 662 branches) with `coverage` run through `uv run --with coverage`, installed into nothing. Earlier note, retained: Milestone BM measured **100 % statement and 100 % branch coverage** of its 692 new statements and 196 new branches the same way. Earlier note, retained: Milestone BL measured coverage with `coverage.py` run through `uv run --no-project`, which builds an **ephemeral** environment and installs nothing into the project venv — 95 % of its eight new modules, with every uncovered line inspected and reported as a defensive type guard. Earlier note, retained: no coverage package is installed; BC measured 92.4 % line coverage on its seven new modules using the stdlib `sys.monitoring`, and ran 14 mutation probes (14/14 detected) — see [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) §11 |
| **Latest completed milestone** | **BS — Swing Decision Workspace v1** (§8) — the first FMITS surface that **orders** setups, and it pays for that in public: the order is a lexicographic key over four named engine states, printed component by component on the row it placed, with nine quantities named as excluded and risk/reward first among them. One new package, `fmis.swing_workspace`, and one new command, `fmits workspace`; **0 record kinds, 0 repositories, 0 write paths, 0 ADRs, 0 guards weakened**. It computes nothing: the composition root calls `fmis.today.assemble_today` and rearranges what it returns, so a figure here and the same figure on `fmits today` are one calculation rendered twice — asserted by object identity, not by equality. 251 focused tests, 8,954 passing under `-W error`, **100 % statement and branch coverage** of all five new modules and of the modified `fmis/today/builder.py`, **two independent mutation harnesses at 45/45 each with zero survivors**, live-verified against Binance with a byte-identical store before and after and byte-identical pages from two processes. Two defects were found by attacking the surface rather than by the tests, and both are fixed; an independent release gate on 2026-08-21 then found five assertion gaps and one guard hole, all fixed with regressions. Committed as `b6a456c`. See [report 0029](reports/0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md). Previously: **BG-D1c — Setup Identity Surface Integration** (§8) — the first **user-visible** capability of the BG-D1 line. `fmits setup SYMBOL` now closes its page with the setup's stable identity, so a setup that persists for a week reads as one idea instead of seven. The existing page is **byte-identical**; the block is appended. It refuses to print a repeat count, because one invocation observes one bar and the number would be `1` forever. 31 focused tests, 8,530 passing under `-W error`, **100 % statement and branch coverage** of `fmis.setup_observation`, **21/21 mutation probes detected with zero survivors**, live-verified against real Binance data across two independent processes. 0 record kinds, 0 repositories, 0 domain types, `fmis.swing_setup` untouched. **Not committed and not pushed.** See [report 0026](reports/0026_2026-08-19_SETUP_IDENTITY_SURFACE_INTEGRATION.md). Previously: **BG-D1b — Setup Identity Pipeline Integration** (§8) — the milestone that makes the stable setup identity reachable from live market data. One new application-layer package, `fmis.setup_observation`; **0 record kinds, 0 repositories, 0 CLI changes, `fmis.swing_setup` untouched**. Placed outside `fmis.pipeline` because that package is market-half and Law 6 forbids it naming a domain root — tried, failed the guard, and rehomed onto the same application-layer tier `pipeline/prices.py` already delegates to. 53 focused tests, 8,499 passing under `-W error`, **100 % statement and branch coverage**, 22/23 adapter and 33/34 domain mutation probes detected. **Not committed, not pushed, and no user-visible capability yet** — no surface calls it, by design. See [report 0025](reports/0025_2026-08-19_SETUP_IDENTITY_PIPELINE_INTEGRATION.md). Previously: **BG-D1 — Stable Setup Identity** (§8) — the milestone that makes a setup keep its name from one bar to the next. Issued as `BQ`, whose own gate (*"confirm no existing package already owns this responsibility"*) **failed** and which was re-scoped by the owner before any code was written. **No new package, no new record kind, no new domain vocabulary**: three modules in `fmis.proposal`, keyed on the `MEASURED` `Anchor` the data model specifies and the repository had built but never constructed. Closes the defect in which 552 directional observations of one unchanged idea were counted as 549 distinct setups, and closes a **latent defect** in which `lifecycle.admit` compared anchors with `==` — including the window-relative `swing_index` — so creation rule 4 could never have deduplicated. 66 new tests, 8,440 passing under `-W error`, **100 % statement and branch coverage** of all three new modules, 33/34 mutation probes detected with the survivor proven equivalent, 0 record kinds added, 0 domain types changed, 0 architecture guards weakened. **Not committed and not pushed; no user-visible capability yet** — the composition-root adapter and the CLI are deliberately the next slice. See [report 0024](reports/0024_2026-08-19_SETUP_IDENTITY_IMPLEMENTATION.md). Previously: **BP — Statistics & Performance Engine** (§8) — the first milestone that answers *"does this system actually have an edge"* rather than *"what happened to this trade"*. One new package, `fmis.statistics` (15 modules), and **no record kind, no repository and no write path at all**: `AP` §25.2 classes cohort statistics as recomputable and disposable, so the engine is a pure projection that leaves the store byte-identical. Five new commands — `fmits statistics`, `performance`, `expectancy`, `equity`, `trades summary` — plus a ninth `fmits today` section and `--as-of` replay on every page. Every rate carries its `n` and is refused below a stated floor; counts never are. 570 new tests, **100 % statement and branch coverage** of all 15 new modules, 60/60 mutation probes detected, 0 record kinds added, 0 domain types changed, no ADR widened and no directional exemption taken, live-verified against a store built entirely through the product's own commands. Ten findings recorded in [report 0023](reports/0023_2026-08-18_STATISTICS_AND_PERFORMANCE_ENGINE_IMPLEMENTATION.md) §5 rather than quietly fixed — the most consequential being a default regime dimension naming a dimension the regime engine has never emitted, which made the per-regime breakdown silently empty. Previously: **BO — Paper Trading & Trade Lifecycle Engine** (§8) — the first milestone that answers *"what happened to this trade"* rather than *"can I take it"*. Two new packages — `fmis.trade_lifecycle` (the domain: four record types and the two folds that are the only place a state or an effective stop exists) and `fmis.paper` (the engine: `advance(state, bar)`, one closed candle at a time) — plus a twelfth command, **`fmits simulate`**, six new `fmits trade` subcommands and an eighth `fmits today` section. A simulated fill is a real ledger `Trade` under `Book.PAPER`, so the position fold, the exposure engine, the valuation and the day's page all work on it with **no new code**. 446 new tests, **100 % statement and branch coverage** of all 19 new and 7 modified modules, 45/45 mutation probes detected, 4 record kinds added (11 → 15), 0 domain types changed, no ADR widened and no directional exemption taken, live-verified against real Binance data with byte-level idempotence. Ten findings recorded in [report 0022](reports/0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md) §5 rather than quietly fixed. Previously: **BN — Position Sizing & Trade Approval Engine** (§8) — the first milestone that answers *"can I take this trade"* rather than *"is this setup good"*. One new package, `fmis.position_sizing` (nine modules in three guarded tiers), and one new command, **`fmits approve`**; `fmits today` now carries an approval status, a recommended size, the resulting open risk, the blocking reasons and the warnings on every actionable candidate. 395 new tests, **100 % statement and branch coverage** of all thirteen new and modified modules, 44/44 mutation probes detected, 0 record kinds added, 0 domain types changed, no ADR widened and no exemption taken, live-verified against real Binance data. See [report 0021](reports/0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md). Previously: **BM — Market Snapshot & Price Integration** (§8) — the bridge between the Market half and the Owner half. Two new packages (`fmis.marks`, the deterministic price snapshot service, and `fmis.valuation`, the one place a price becomes a `MarkQuote`) plus `fmis.pipeline.prices`, the single module in the repository that binds a provider to a mark. **`fmits portfolio`** — what the recorded positions are worth right now, what they cost, what is unrealized and what is exposed, every figure traceable to a named closed candle. `fmits today`'s capital section prints money where it used to print *"no mark source exists"*. 285 new tests, **100 % statement and branch coverage**, 26/26 mutation probes detected, 0 record kinds added, 0 domain types changed, live-verified against real Binance data. See [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md). Previously: **BL — Portfolio Intelligence & Risk Engine** (§8) — `fmis.portfolio_risk`: `AP` §15's boundary, built. Portfolio state, exposure on eight axes, the owner's risk budget evaluated as per-limit facts, and the proposed-trade impact that answers *what changes if I open this now* — with **no verdict, no score and no CLI**, by design. 368 new tests, 96 % coverage reported honestly, 62/64 mutation probes killed with both survivors proven equivalent, venue-agnosticism proved by five executable guards. **Foundational: no user-visible capability yet, and every exposure figure is `Absent` until a mark source exists.** See [report 0018](reports/0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) and [report 0019](reports/0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md). Previously: **BK — Trade Capture & Decision Recording** (§8) — `fmits trade record / show / list / note / close`: the first milestone in which FMITS **writes** to the durable store. Two new packages (`fmis.plan`, holding the `TradePlan` the data model specified and Milestone BH did not build, and `fmis.trade_capture`), a tenth repository, 435 new tests, 100 % statement coverage of the nine new modules, 30/30 mutation probes detected, 0 domain types changed. See [report 0017](reports/0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md). Previously: **BJ — Daily Trading Workspace MVP** (§8) — `fmits today`: one command, seven sections, assembled from the scan and the durable store. The first package reading both halves of FMITS, and the first milestone since AV to change what the owner can do. 247 new tests, 100 % statement **and** branch coverage, 15/15 mutation probes detected, reads the store and writes nothing. See [report 0016](reports/0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md). Previously: **BI — Trade Repository & Journal Engine** (§8) — the durable store for the owner half: nine repositories, a hash-chained write journal, a version engine, 366 new tests, 100 % statement **and** branch coverage, an 81.6 % mutation score, **no user-visible capability yet**. See [report 0015](reports/0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md). Previously: **BH — Trade Domain Foundation** (§8) — the pure domain layer of the owner half: thirteen packages, 608 new domain tests, 100 % statement coverage, **no user-visible capability yet**. See [report 0014](reports/0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md). Previously: **BC — Research Dataset & Counterfactual Replay Correction** (§8) — `fmits backtest --research` derives its warm-up prefix from the production dependencies, fetches it before the measurement window, and verifies per instant that nothing was still warming. Usable research period **41 → 380 days**; largest five-day outcome cluster **49.0 % → 11.4 %**; counterfactual confirmation-age bounds replayed rather than filtered. **No trading policy changed and no performance claim made.** See [the design](docs/design/RESEARCH_HARNESS_CORRECTION_V1.md), [report 0012](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) and [report 0013](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) |
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
fmits workspace                            # the operator's page, ordered by a stated key
fmits workspace BTCUSDT ETHUSDT ARBUSDT    # a watchlist you name, in the order you named it
fmits workspace --no-records               # fetch the market, read no store, name every gap
fmits pulse                                # what the tracked markets are doing, and what is unreadable
fmits pulse ETH BTC                        # only these markets, in the order you typed them
fmits pulse --as-of ISO8601                # a reproducible page
fmits pulse --max-age 6                    # mark any reading older than six hours stale
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

`workspace` is the **operator's page**: the same run `today` assembles, arranged for one decision
and — uniquely in this product — **ordered**. The order is a lexicographic key over four components
compared left to right (readiness → approval → decision-context sufficiency → watchlist position),
every one of them a state an engine already decided, every one printed on the row it placed, so two
adjacent rows can be compared component by component without reading any code. Nine quantities are
named as ordering nothing and printed under the rule — **risk/reward first**, because the one
measurement this repository has published found higher displayed R:R associated with a *worse*
outcome. The page states that readiness is not desirability. Each actionable row also carries the
setup's stable identity, its evidence digest with independence *reported* rather than assumed, and
whether the owner is already in that market — in the paper book and in the recorded position,
separately. It reuses `today`'s own composition root, so it costs one scan, one store read, one
valuation and one approval pass; it computes nothing and writes nothing.

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

**`BR` — Setup Evidence — is DONE (2026-08-20), and was an owner-directed implementation task, not a
NOW selection.** It sits on the same footing as `AT`, `AU`, `AV`, `BH`–`BN` and the `BG-D1` line
above: explicitly scoped by the owner, delivered against that scope, and **it does not satisfy the
exactly-one-NOW rule**, which remains outstanding. Evidence: `src/fmis/setup_evidence/`,
`fmits evidence SYMBOL`, 163 new tests, full suite 8,693 passing under `-W error`, and
[report 0027](reports/0027_2026-08-20_SETUP_EVIDENCE_IMPLEMENTATION.md).

**`BS` — Swing Decision Workspace v1 — is DONE (2026-08-20), and was an owner-directed
implementation task, not a NOW selection.** It sits on the same footing as `AT`, `AU`, `AV`,
`BH`–`BN`, the `BG-D1` line and `BR`: explicitly scoped by the owner, delivered against that scope,
and **it does not satisfy the exactly-one-NOW rule**, which remains outstanding. Evidence:
`src/fmis/swing_workspace/`, `fmits workspace`, 251 new tests, full suite 8,954 passing under
`-W error`, and [report 0029](reports/0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md).
Committed as `b6a456c` (production code + tests) with the documentation commit directly on top.

**`BT` — Global Market Pulse Foundation — is DONE (2026-08-22), and was an owner-directed
implementation task, not a NOW selection.** It sits on the same footing as `AT`, `AU`, `AV`,
`BH`–`BN`, the `BG-D1` line, `BR` and `BS`: explicitly scoped by the owner, delivered against that
scope, and **it does not satisfy the exactly-one-NOW rule**, which remains outstanding. It is
nevertheless the first milestone since `AK` to open a *new product direction* rather than deepen the
swing slice: it describes markets, not an asset and not the owner's money, and it is deliberately
usable with no reference to swing trading. Evidence: `src/fmis/market_pulse/`,
`src/fmis/pipeline/pulse.py`, `fmits pulse`, 366 new tests, full suite **9,320 passing** under
`-W error`, 100 % statement and branch coverage of all seven new modules, 38/38 development and
20/20 release-gate mutation probes detected, and [report 0030](reports/0030_2026-08-22_GLOBAL_MARKET_PULSE_IMPLEMENTATION.md).
Committed as `1b56069`.

> The milestone's own boundary is worth carrying forward: `BT` builds the deterministic foundation
> that Macro, News, Geopolitics, On-chain and Derivatives will later attach to, and it built **none
> of them**. It also declined the Swing Workspace integration §17 of its brief permitted only if
> clean, and documented the seam instead — a guard test asserts neither `fmis.today` nor
> `fmis.swing_workspace` imports it, so wiring it later is a deliberate edit rather than a drift.

**`BU` — Macro & Cross-Asset Context Foundation — is DONE (2026-08-23), and was an owner-directed
implementation task, not a NOW selection.** It sits on the same footing as `AT`, `AU`, `AV`,
`BH`–`BN`, the `BG-D1` line, `BR`, `BS` and `BT`: explicitly scoped by the owner, delivered against
that scope, and **it does not satisfy the exactly-one-NOW rule**, which remains outstanding. It is
the first milestone to attach a real second data source to FMITS and the first to describe markets
outside crypto. Evidence: `src/fmis/macro/`, `src/fmis/providers/fred.py`,
`src/fmis/pipeline/market_data.py`, `src/fmis/pipeline/macro.py`, `fmits macro`, 496 new tests, full
suite **9,824 passing** under `-W error`, 99 % statement coverage over the BU scope, 36/36 semantic
mutation probes killed, 32 hostile-review attacks kept as permanent tests, and
[report 0031](reports/0031_2026-08-23_MACRO_AND_CROSS_ASSET_CONTEXT_IMPLEMENTATION.md).
Committed as `2b30e38` (production code + tests) with the documentation commit directly on top.

> **`BU`'s honest result is as much what it declined to read as what it read.** Five of `BT`'s five
> dark markets are now measured from a public Federal Reserve download that needs no key. Two stay
> dark — the ICE Dollar Index because it is licensed, and spot gold because the source's series were
> discontinued — and the page names each reason. The Fed's broad dollar index *is* read, under its
> own name and its own unit, and is never printed as DXY: they are different measures over different
> baskets, and substituting one would have been the most plausible-looking error the page could
> make.

> **The milestone's central engineering result is that a yield is no longer representable as a
> price.** `QuantityKind` was added to the shared benchmark vocabulary, a rate-like market produces
> no percentage move and no realized volatility at all, and `fmis.macro.rates` states a yield's move
> as three separately-named quantities with no field called *the* change. That last guard was added
> because the live demonstration — run after the whole suite was green — printed
> `US10Y latest_observation: +0.86%` on `fmits pulse`. The suite had asserted the *comparison* rule
> and not the *display* rule. Recorded in §17 of report 0031 rather than quietly fixed.

> **`BU` stopped before interpretation, deliberately.** No AI, no prompt, no regime, no
> risk-on/risk-off, no causal claim, no forecast. Two limitations are carried forward rather than
> hidden: a macro observation carries a *date* and not an instant, so every age is overstated by up
> to one period and never understated; and this build still holds no trading calendar, so no window
> is described in days or weeks. It also declined the swing-workspace integration:
> a guard test asserts `fmis.swing_workspace`, `fmis.today` and `fmis.setup_evidence` consume none
> of it, so attaching macro as a separate evidence domain later is a deliberate edit.

**`BX` — Swing Trade Geometry Research & Policy Candidates — is DONE (2026-08-25), and was an
owner-directed research task, not a NOW selection.** It sits on the same footing as `AT`, `AU`,
`AV`, `BH`–`BN`, the `BG-D1` line, `BR`, `BS`, `BT`, `BU`, `BV` and `BW`: explicitly scoped by the
owner, delivered against that scope, and **it does not satisfy the exactly-one-NOW rule**, which
remains outstanding. It is the second milestone whose deliverable is an **answer**, and the answer
is again negative — but this time it comes with a mechanism. Evidence: nine new modules in
`src/fmis/swing_lab/`, `fmits research geometry`, the read-only `/geometry` dashboard page, 179 new
tests, full suite **11,271 passing** under `-W error`, 91–99 % statement and branch coverage of the
new modules, **42/42 mutation probes killed**, and
[report 0034](reports/0034_2026-08-25_SWING_TRADE_GEOMETRY_RESEARCH.md).

**`BZ` — Swing Thesis Persistence & Exit Mechanics — is DONE (2026-08-26), and was an
owner-directed research task, not a NOW selection.** It sits on the same footing as every
owner-scoped milestone before it and **does not satisfy the exactly-one-NOW rule**, which remains
outstanding. It is the fourth milestone whose deliverable is an **answer**, and the first to ask what
happens to a trade *after* it opens. Evidence: five new modules in `src/fmis/swing_lab/`,
`fmits research persistence`, 226 new focused tests, full suite **11,997 passing** under `-W error`,
88 % statement and branch coverage of the new scope, **47 mutation probes — 47 killed, 0 survivors**,
33 hostile probes with 0 failures, and
[report 0036](reports/0036_2026-08-26_SWING_THESIS_PERSISTENCE_RESEARCH.md).

> **What the owner can do after `BZ` that was impossible before:** see what the structural engines
> said at **every bar of an open position**, not only at the bar that admitted it — and read a
> post-entry thesis state that is causal by construction. One replay now yields both the candidates
> and the timeline, so a claim about a state *transition* rests on one dataset rather than two.

> **`BZ` answered its primary question YES and its promotion question NO, and the two are
> different.** Post-entry thesis persistence **exists and is measurable causally**: under production
> geometry the thesis is INTACT for 149 of 151 development positions at bar 1 and for 41 of 151 at
> bar 60, decaying monotonically. **No exit mechanism built on it earned promotion.** All five sealed
> families are REJECTED on both geometries — ten judgements, ten rejections — every one failing the
> pre-declared +0.10R development bar against a best measured figure of +0.0134R.

> **Why they fail, in one number.** Under BY's geometry, 99 of 136 development positions reached
> +2R and the **median realised return of those was −1.05R**, while the policy's mean expectancy is
> +0.1906R. The return distribution is almost entirely tail, so a give-back cap, a stagnation exit
> and a structural trail each remove upside before they remove losers.

> **The result that is not a candidate.** Every mechanism helps the holdout and hurts development.
> Give-back protection is worth **+0.1992R** on twenty-one unseen symbols and **−0.0772R** on the
> sample it was developed on, taking BY's geometry on the holdout from −0.2110R to −0.0118R. A
> mechanism whose sign flips between samples is a property of one sample, and the sealed criteria
> caught it without a judgement call.

> **Two defects found and fixed, and one of them would have manufactured evidence.** **BZ-D1**: a
> below-floor or never-run sample was reported as a *failed* criterion rather than as unmeasurable,
> so a development-only pass would have reported five refutations it had not earned — BZ's own
> sealed rules say a thin sample is INCONCLUSIVE. **BZ-D2**: one trade's TIME_STOP exit differs from
> BY's run by 1.21R; the walker is proven equivalent over 4,000 randomised paths and BY persisted no
> capture, so the cause could not be closed. Both are recorded in report 0036 §7 and §16.

> **What BZ did not deliver, stated plainly:** no dashboard page, and the sealed robustness
> neighbourhood was **not measured** — the `robust` criterion reports as unmeasurable, which
> changes no verdict but leaves the plateau question open.

> **Completion pass (2026-08-27) — BZ is now a reproducible experiment.** BZ was held back from
> release because its result could not be re-derived: no milestone in this series had ever persisted
> its *inputs*. `persistence_artifact.py` now writes a digested **capture** — every bar, candidate
> and structural observation, with full provenance — and `fmits research persistence
> --from-capture` re-measures from it **without touching the network**, proven by a regression that
> makes a fetch fatal. Every result is unchanged: seal verified, ten judgements REJECTED, zero
> candidates, NO_CANDIDATE. **BZ-D2 is reconciled mechanically** to one knife-edge trade worth
> 1.2113R against an observed 1.2086R gap, with the root cause classified **UNRESOLVED_PROVENANCE**
> — BY's level lists no longer exist. Two further defects were caught by the new mutation probes: a
> gzip header that made identical captures produce different files, and a `Decimal` decode that
> would have lost precision on high-precision instruments.

**`CB` — Statistical Power & Research Design Foundation — is DONE (2026-08-28), and was an
owner-directed research-infrastructure task, not a NOW selection.** It sits on the same footing as
every owner-scoped milestone before it and **does not satisfy the exactly-one-NOW rule**, which
remains outstanding. It is the first milestone in the series whose deliverable is an **instrument**
rather than an answer. Evidence: `src/fmis/research_design/` (8 modules), the CA adapter
`src/fmis/swing_lab/admission_power.py`, `fmits research design`, 565 new focused tests, full suite
**12,952 passing** under `-W error`, **99 % statement and branch coverage** of the new scope with 7 of
9 modules at 100 %, 52 hostile probes with 0 failures, 42 mutation probes with 41 killed and 1 proven
equivalent, and
[report 0038](reports/0038_2026-08-28_STATISTICAL_POWER_AND_RESEARCH_DESIGN.md).

> **What the owner can do after `CB` that was impossible before:** ask, **before** committing hours of
> compute and before opening a validation or holdout sample, whether a proposed experiment can
> resolve the effect it claims to test — and get back a verdict, the dimension that binds, and what
> more information would have to look like. `fmits research design` reads no market data at all, so it
> is safe to run before a study rather than only after one.

> **It reproduced CA's published requirement and then sharpened it.** CA's `~4,800 admissions per
> sample` is **REPRODUCED** — 4,827 recomputed from the half-width CA quotes, 4,823 from the interval
> bounds CA tabulates, both within 0.6 %. What CB adds is the assumption CA never states: that figure
> belongs to the *independent-observations* growth path. Distinguishing the paths changes the answer.
> **More symbols at the observed density: 467 symbols / 4,823 admissions, identical at every assumed
> clustering. More years on the same 15 symbols: NOT REACHABLE AT ANY SIZE** for any intracluster
> correlation above zero, because the half-width approaches a floor of 0.331 (ρ=0.05) to 0.533
> (ρ=0.50) — three to five times the 0.10 ATR bar.

> **"Collect more data" was never the answer to CA.** More *years* is not more information for this
> question; more *symbols* is. That distinction is invisible to CA's own arithmetic because that
> arithmetic has no term for it. And CA's figure is the optimistic reading: it is a coin-flip
> `INTERVAL_EXCLUDES_ZERO` criterion, and a genuine 80 % power guarantee costs 2.043× — **954 symbols
> and 9,854 admissions**.

> **Three separations are enforced structurally, not by convention.** A **post-hoc** resolution
> cannot be relabelled **prospective** power: neither result type has a `mode` field, each is produced
> only by a function taking inputs the other mode cannot have, and the gate takes no mode argument at
> all. A **holdout's** realised outcome is *refused* as a design input by name, while a prospective
> assessment of that same holdout is permitted because it opens nothing. And **rows are not
> information**: several dimensions are reported, and a single effective sample size is offered only
> when an intracluster correlation has been declared — CA declared none, so none is offered.

> **The gate says nothing about the hypothesis, and cannot.**
> `DesignVerdict.says_nothing_about_the_hypothesis` is `True` for every member, asserted over the
> whole enum, and the assessment payload carries no field naming an edge, a profit, an approval or a
> forward test. **CA's `NO_EDGE` stands exactly as sealed**; BY's, BZ's and CA's pinned digests are
> byte-identical after three behaviour-preserving extractions.

> **The reusability claim is guarded, not asserted.** The core names no instrument, no unit and no
> universe *in code* — checked over the parsed tree, so docstrings stay free to explain that CA's bar
> was +0.10 ATR while no identifier or emitted string can know what an ATR is. `research_design`
> cannot import the laboratory, opens no file anywhere, reaches no network and reads no clock.

> **Two defects fixed, and two of my own review findings withdrawn after verification.** A test helper
> drew cluster offsets and within-cluster noise from one interleaved stream, so cluster means moved
> whenever the density moved and any across-density comparison was invalid (**CB-D1**, found by a
> hostile probe). `prospective_design` accepted an estimator/target confidence mismatch that
> `post_hoc_resolution` refused (**CB-D2**). A claimed curve-confidence defect and a claimed 40 %
> equal-cluster-size bias were both **refuted by my own verification** — `z` cancels exactly, and the
> bias was a single-realisation artifact that vanished over 15 realisations — and both are recorded as
> withdrawn.

> **Limitations, stated rather than glossed.** The CA reproduction is a **summary-statistic**
> reproduction: CA's 155 paired differences are not persisted in this repository, so the dispersion is
> *inverted* from the published interval under an assumed correlation, no empirical design curve is
> available for CA, and a half-width measured once over 15 clusters carries roughly **±30 %**
> realisation scatter. **4,823 is an order of magnitude, not four significant figures.**

> **No dashboard page**, and the dashboard's 30–45 s refresh was deliberately left untouched, as the
> brief directed.

**`CA` — Swing Admission Edge vs Random-Entry Null — is DONE (2026-08-27), and was an
owner-directed research task, not a NOW selection.** It sits on the same footing as every
owner-scoped milestone before it and **does not satisfy the exactly-one-NOW rule**, which remains
outstanding. It is the fifth milestone whose deliverable is an **answer**, and the first to put the
**admission rule itself** on trial rather than what is done around it. Evidence: six new modules in
`src/fmis/swing_lab/`, `fmits research admission`, sealed pre-registration `910cad28…`, 282 new
focused tests, full suite **12,380 passing** under `-W error`, **96 % statement and branch coverage**
of the new scope, 33 hostile probes with 0 failures, and
[report 0037](reports/0037_2026-08-27_SWING_ADMISSION_NULL_MODEL_RESEARCH.md).

> **What the owner can do after `CA` that was impossible before:** ask whether a swing admission is
> *worth making at all*, against controls matched on symbol, sample, volatility band and calendar
> neighbourhood — separately from the geometry and the exit that BW–BZ already refuted. Until CA,
> *"the geometry is wrong"* and *"there is no signal to shape"* were indistinguishable.

> **`CA` answered NO, and the answer is not merely an absence.** `NO_EDGE` on all five sealed null
> families, with **negative** effects at the sealed primary horizon of 24 execution bars: timing
> −0.2028 / −0.3347 / −0.5337, direction −0.0110 / −0.2036 / −0.3125, combined +0.0357 / −0.1918 /
> −0.3088, gate −0.1947 / −0.0641 / −0.1227 across development / validation / holdout.

> **An independent code review refuted the first draft's strongest claim, and it was withdrawn.**
> The draft reported that the **admitted** rung is the worst directional rung on all three samples
> and that the confirmation gate "selects the wrong tail of its own candidate set". The gate ladder
> is **unclustered, unmatched and unbounded**: under CA's own symbol-clustered estimator zero is
> inside the interval on all three samples ((−0.644,+0.387), (−0.996,+0.166), (−0.658,+0.220)),
> roughly 40 % of symbols point the other way, and **equal-symbol weighting reverses the holdout**.
> The `confirmed_repeat` figure was additionally **90 % one symbol** (TRXUSDT: +0.4102 of +0.4538).
> Every finding was verified independently before the claim was withdrawn.

> **CA is also underpowered for its own sealed bar, and that is the most important thing to carry
> forward.** The development bootstrap half-width is ≈0.558 ATR against a 0.10 ATR bar; an interval
> excluding zero would need ≈4,800 matched admissions per sample against the 155 that exist. **No
> realisation of this data could have produced `ADMISSION_EDGE_CANDIDATE`.** `NO_EDGE` therefore
> means *"no edge large enough to see at this sample size"*, not *"no edge"*.

> **What survives, and it is still decisive for sequencing.** No sealed family cleared the bar and no
> interval excludes zero on the positive side. Five milestones have now searched timeframes,
> geometries, geometry neighbourhoods, exit mechanisms and admission itself without producing
> measurable evidence of an edge anywhere. Continuing to tune components around this admission rule
> is optimising inside a space nobody has shown contains anything.

> **A hypothesis worth pre-registering, not a finding.** Every family is positive at 1–6 bars (4–24
> hours) and negative by 12–24 bars, and admissions win the ±1 ATR race on two of three samples while
> losing the four-day return on all three — a shape *consistent with* confirming on a structure break
> and entering near the end of a short impulse. CA did not establish it.

> **What CA cannot say, stated plainly.** The two lowest rungs — the 1W regime gate and the
> two-family tally — carry no production direction, so a direction-normalised return is undefined for
> them and is **refused** rather than computed as a long's. Three further limitations are recorded
> rather than hidden: the sealed empirical null is **conservative** and the seal's own text
> **overstates** its clustering (both can only produce false negatives, and neither decided a
> verdict), and the sealed conditional-edge rule is **unmeasurable** because per-stratum bootstrap
> and null statistics were commissioned per family and sample only.

> **Three code defects were found by the review and fixed.** **CA-D1** — the headline effect was the
> one figure exempt from `SAMPLE_FLOOR`, so a three-admission family could be reported `NO_EDGE` by a
> test its own `sample` criterion said could not be run; this is the BZ-D1 class one layer down.
> **CA-D2** — a strided ladder rung reported a full count beside a sampled mean. **CA-D3** — a sealed
> family could be measured against a pool its seal does not name, and the control-identity digest
> would still have verified. **The experiment was re-run after all three and every effect, interval,
> percentile and verdict is byte-identical.**

> **No dashboard page**, and the dashboard's 30–45 s refresh was deliberately left untouched for a
> later UX milestone, as the brief directed.

**`BY` — Pre-Registered Swing Geometry Validation & Execution Mechanics — is DONE (2026-08-26), and
was an owner-directed research task, not a NOW selection.** It sits on the same footing as `AT`,
`AU`, `AV`, `BH`–`BN`, the `BG-D1` line, `BR`, `BS`, `BT`, `BU`, `BV`, `BW` and `BX`: explicitly
scoped by the owner, delivered against that scope, and **it does not satisfy the exactly-one-NOW
rule**, which remains outstanding. It is the third milestone whose deliverable is an **answer**, and
the first to seal its hypotheses before measuring them. Evidence: ten new modules in
`src/fmis/swing_lab/`, `fmits research validation`, the read-only `/validation` dashboard page, 345
new tests, full suite **11,726 passing** under `-W error`, 84–99 % statement and branch coverage of
the new modules, **50 mutation probes — 48 killed, 2 proven equivalent**, 27 hostile probes with 0
failures, and
[report 0035](reports/0035_2026-08-26_PREREGISTERED_SWING_GEOMETRY_VALIDATION.md).

> **What the owner can do after `BY` that was impossible before:** state a hypothesis, **seal it with
> a digest**, and have the repository refuse to promote anything that was not in the seal — however
> good its numbers look afterwards. `fmits research validation` takes no universe, no window and no
> threshold, because all three are part of what was frozen.

> **Eight defects were found and fixed, two of them AFTER the release commits were pushed.** An
> independent code-review pass over the pushed diff found that the walk-forward and every
> decomposition **pooled all three samples**, doubling the traded universe mid-curve — which made
> the originally published "one six-month window" claim wrong and reversed two decomposition rows —
> and that `--validation-artifact` and `--geometry-artifact` were **inert**. All are fixed and
> recorded in report 0035 §7; the result digest is unchanged and the verdict is unaffected.

> **`BY` promoted nothing, and it refuted the hypothesis it was built to test.** `BX`'s post-hoc
> finding — a 4H stop ≥ 0.5 ATR plus a real 1D target paying 2R — is **positive on development
> (+0.1995R cost-inclusive) and negative on both unseen samples**: −0.1761R on the later period and
> −0.2361R on twenty-one symbols this repository had never measured. All eleven sealed hypotheses
> are REJECTED. The production stop and target rules are byte-for-byte unchanged.
>
> **The rule fails two independent generalisation tests.** On its own fifteen symbols it worked for
> two years (+0.234, −0.039, +0.352, +0.259) and broke at exactly the validation boundary (−0.450,
> −0.150); on twenty-one unseen symbols it never worked at all. Neither time nor universe carries it.
>
> **Three things did survive, and none of them is a candidate.** Structure beats distance — a
> non-structural control at the same numbers earned +0.0240R against the structural rule's +0.1995R.
> `BX`'s "NOT MEASURABLE" is now measurable — real 1H/15m candles resolved **17 of 19** ambiguous 4H
> bars on development and **18 of 21** on the holdout, refusing the rest rather than guessing. And
> exit management is worth about **+0.30R per trade** on both samples while still leaving production
> geometry deeply negative.
>
> **`BW`'s `swing_1d4h1h_roles` is measured at last and REJECTED** — worse on all eleven policies,
> admitting seven times the setups and losing on them. An INCONCLUSIVE standing since `BW` is
> resolved.

> **What the owner can do after `BX` that was impossible before:** ask *which stop and which target*
> — not just *which timeframe* — and get a measured answer against a symbol set the repository has
> never looked at, with every criterion for promotion reported by name. `fmits research geometry`
> and `/geometry` are that surface.

> **`BX` promoted nothing.** All thirteen pre-declared geometries are REJECTED under both cost
> scenarios. The production stop and target rules are byte-for-byte unchanged.
>
> **The finding worth carrying forward is a refutation.** A minimum planned reward-to-risk — the
> obvious response to `BW`'s diagnosis — makes the strategy **worse** (development −0.276R →
> −0.605R, win rate 45.5 % → 6.5 %), because in this system **a high planned R:R is produced by a
> tight stop, not a distant target** (rank correlation −0.65 on both samples independently).
>
> **The defect is the stop.** 73.2 % of stopped-out trades had their original target reached
> afterwards inside the same window; 48.2 % of stops sit inside one ATR(14); 63.5 % of trades are
> decided by the very next 4H candle. And costs are decisive rather than marginal: at 10 bp per side
> the production geometry carries a mean drag of **0.723R per trade** (development expectancy
> −0.276R → −0.999R), because cost in R is charged against the risk denominator — 0.132R at the
> median 152 bp stop, but **14.0R** at the tightest 1.43 bp stop.
>
> The rule the evidence points at — relocate the stop to the nearest *real* 4H level at least
> 0.5 ATR away, then require a *real* 1D target that pays the risk — is positive on both samples and
> survives costs, but it was constructed **after** the results were seen and is a single grid point
> whose neighbours fail. It is recorded as the **next milestone's pre-declared hypothesis, not as a
> candidate**. Acting on it remains an owner decision.

**`BW` — Swing Strategy Laboratory & Historical Replay — is DONE (2026-08-25), and was an
owner-directed research task, not a NOW selection.** It sits on the same footing as `AT`, `AU`,
`AV`, `BH`–`BN`, the `BG-D1` line, `BR`, `BS`, `BT`, `BU` and `BV`: explicitly scoped by the owner,
delivered against that scope, and **it does not satisfy the exactly-one-NOW rule**, which remains
outstanding. It is the first milestone whose deliverable is an **answer** rather than a feature,
and the answer is negative: measured over 3.79 years on four symbols and confirmed on a seven-symbol
holdout, **the swing strategy has no edge in any of the four configurations tested**, and the 1W
gate is not the reason. Evidence: `src/fmis/swing_lab/` (11 modules), `fmits research swing`, the
read-only `/lab` dashboard page, 273 new tests, full suite **10,969 passing** under `-W error`,
95 % statement and branch coverage of the new package, 35/35 mutation probes killed, nine defects
found, and [report 0033](reports/0033_2026-08-25_SWING_STRATEGY_LABORATORY_IMPLEMENTATION.md).
Released at the BW release gate: production behaviour proved unchanged over 115,200 input
combinations, and the primary study's digest reproduced exactly on an independent re-run.

> **`BW` promoted nothing, and that is the milestone's own rule.** Every variant is classified
> REJECTED; the one specified variant that was not measured (`swing_1d4h1h_roles`, 1D/4H/1H) is
> INCONCLUSIVE. The production strategy is byte-for-byte unchanged — `CONFIRMATION_LOOKBACK_BARS`
> is still 10, `MINIMUM_AGREEING_FAMILIES` still 2, `DEFAULT_TIMEFRAMES` still 1W/1D/4H. The two
> production defects it found (winners paying less than losers cost, and stops as tight as 13 basis
> points) are **reported and deliberately not fixed**: changing a trading policy on the strength of
> a backtest, inside the milestone that built the backtest, is exactly the sequence this work was
> commissioned to avoid. **Acting on them is an owner decision and is the natural next milestone.**

**`BV` — FMITS Operator Dashboard V0 — is DONE (2026-08-24), and was an owner-directed
implementation task, not a NOW selection.** It sits on the same footing as `AT`, `AU`, `AV`,
`BH`–`BN`, the `BG-D1` line, `BR`, `BS`, `BT` and `BU`: explicitly scoped by the owner, delivered
against that scope, and **it does not satisfy the exactly-one-NOW rule**, which remains outstanding.
It is the first milestone to deliver a *visual* surface: everything FMITS knew was previously
readable only as terminal text. Evidence: `src/fmis/operator_dashboard/` (seven modules, 4,323
lines), `fmits dashboard` serving seven routes on `http://127.0.0.1:8787/`, 847 new tests, full suite
**10,671 passing** under `-W error`, **100 % statement and branch coverage** of all seven new
modules, 34/34 semantic mutation probes killed, five hostile-review defects found and fixed, and
[report 0032](reports/0032_2026-08-24_OPERATOR_DASHBOARD_V0_IMPLEMENTATION.md).
Committed as `0f31293` (production code + tests) with the documentation commit directly on top.

> **`BV` added no dependency, and that was a repository constraint rather than a preference.**
> `pyproject.toml` declares `dependencies = []` and an existing guard names `flask`, `django`,
> `fastapi`, `numpy` and `pandas` as source-level absences — which rules out FastAPI and Flask
> directly and Streamlit through its dependency tree. The dashboard is served by the standard
> library's `http.server` with hand-written HTML. A clean-environment install shows `fmis==0.0.1`
> and nothing else.

> **The milestone's central architectural result is a presentation seam that the engines do not know
> about.** `fmis.operator_dashboard.models` is the whole contract; `render.py` and `theme.py` are
> replaceable in their entirety without touching it, and guards assert the contract layer imports no
> presentation module, holds no markup and holds no colour literal. The brief said the visual design
> *will* change, so the cost of changing it was made the design's first constraint.

> **It computes nothing, and four guards assert each way it could start to.** No indicator, no
> ranking, no return, no risk figure, no statistic. `REFRESH_READS` names exactly four engine reads
> per refresh and a test asserts the count, so a fifth is a decision somebody makes rather than one
> that happens because a section needed a number. Ordering is inherited from `BS` index-for-index —
> a mutation re-sorting rows by symbol is killed.

> **The hostile review earned its place.** Five real defects were found *after* the suite was green,
> every one a misleading page rather than a crash: crypto rows showing three false *unavailable*
> cells for windows never measured (a regression of a fix `BU` had already made in the terminal
> renderer); DXY and XAU vanishing entirely because unsupported markets live on the universe rather
> than in the failure tuple; one 60-word reason printed six times across a row; healthy sources
> rendering as *"unavailable: no detail was stated"*; and the paper/portfolio separation notes
> disappearing when either section was empty. All fixed, all now guarded.

> **`BS` is the first FMITS surface that orders setups, and the order is a key rather than a
> score.** Every previous surface refused to order at all, on the stated ground that a top row reads
> as the best idea. `BS` orders by four named engine states, prints every component on the row it
> placed, and names the nine quantities — risk/reward first — that order nothing. Whether the
> *approval* component belongs in the key at all, given that it can rank a row the owner cannot act
> on yet, is a judgement worth revisiting with live use; it is stated on every row rather than
> hidden.

**`BR` shipped with two defects, fixed in `f2cacf5` (2026-08-20).** An independent release gate run
*after* `BR` was pushed found that `fmits evidence` crashed on live symbols where a single evidence
item carried two families, and that one symbol's projection failure suppressed every symbol behind
it in a multi-symbol run. Both are fixed, with eleven regressions that fail against the unfixed
code; full suite 8,703 passing under `-W error`. See
[report 0028](reports/0028_2026-08-20_BR_RELEASE_GATE_FIXES.md).

> **The gate itself is the lesson worth keeping.** A green 8,693-test suite, 94% statement coverage
> and fifteen killed mutation probes did not catch a crash on the first live symbol outside the
> fixture set. Both defects were found by running the product, not by running the tests. A milestone
> is not verified until its surface has been driven against live data across more than one symbol.

> **`BR` recorded a finding that is a decision for the owner, not for the milestone.** The Swing
> Setup policy requires `MINIMUM_AGREEING_FAMILIES = 2` independent families. `BR` proved that the
> context regime gate and the context structural-trend factor are the **same reading** — passing the
> gate guarantees the vote — so the effective bar is *the gate's own family plus one other*. `BR` is
> a projection and deliberately changed no policy; it reports the correlation instead. Whether to
> raise the bar, or to source a genuinely independent third family, is unsequenced work.

> **`BS` surfaced one condition that is deliberately unfixed, and it is follow-up work rather
> than a defect.** On 2026-08-21 the release gate reproduced it against live data: `BTCUSDT` sat
> under **NO TRADE** — the context-role regime was indeterminate, not trending — while a `pending`
> `BTCUSDT` paper activation sat under **ACTIVE PAPER TRADES**. Both facts are on the page, in
> different sections, and nothing on the page connects them. Connecting them is
> *lifecycle-versus-current-assessment* intelligence: it needs a stated rule for when a commitment
> made under one reading becomes stale under a later one — when to warn, when to expire, and what
> the owner is being told to do about a position they already hold. That is a **policy decision**,
> not a presentation one, and `BS` is a presentation milestone. It was explicitly left out of `BS`
> rather than patched in, and it should be designed before it is built. See
> [report 0029](reports/0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md) §11.

## 6. NEXT

The forced sequence. Each item is blocked on the one above it. **Sequenced, not started** — none of
these is a NOW item until the owner names one.

**Item 0 was the exception, and it is now DONE** *(2026-09-04, report 0041)*: a live product
outage named as the immediate next task on 2026-09-04. Its row is left in place as the
point-in-time record; the resolution is `DR` in §8. **EP-21 is not covered by it** and is now the
recommended next dashboard task.

**Swing Product Slice 4 is DONE** *(2026-09-06, report 0046)*: the risk, sizing and portfolio
engines were complete, tested and **unreachable** — `RiskBudget` and `RiskLimit` were constructed
nowhere in `src/`, so the chain had no first link, and the dashboard showed no risk figure and could
not say why. Resolved as `DV` in §8. It **does not satisfy the exactly-one-NOW rule**, which remains
outstanding. Slice 4 is deterministic trade-risk arithmetic against declared capital and nothing
else: it built no execution, no order, no broker connection, no portfolio impact, no correlation, no
AI interpretation and no backtest, and it did not begin Slice 5. **One operator action remains
outstanding and was deliberately not taken on the owner's behalf**: declaring his planning capital
and per-trade risk fraction in `~/.fmits/risk_policy.json`.

**Swing Product Slice 3 is DONE** *(2026-09-05, report 0044)*: the operator could read the current
state of twenty symbols and could not tell which of them had *moved*. Resolved as `DU` in §8. It
**does not satisfy the exactly-one-NOW rule**, which remains outstanding. Slice 3 is deterministic
temporal state comparison and nothing else: it built no alert, no notification, no AI
interpretation, no ranking and no freshness policy, and it did not begin Slice 4.

**Swing Product Slice 2 is DONE** *(2026-09-04, report 0043)*: the operator used Slice 1 and
reported that the page answered an audit question before a trading one. Resolved as `DT` in §8. It
**does not satisfy the exactly-one-NOW rule**, which remains outstanding. Slice 1's deferred second
seam — the per-view `as_of` values discarded in the composition — **is now closed**; what remains
deferred is a freshness *policy*, which needs a validated per-role staleness bound the repository
does not have. Slice 3 was not begun.

**Swing Product Slice 1 was the second exception, and it is now DONE** *(2026-09-04, report 0042)*:
an owner-directed product task following the Swing Product Capability Audit, resolved as `DS` in §8.
It **does not satisfy the exactly-one-NOW rule**, which remains outstanding — it sits on the same
footing as every owner-scoped implementation task above. The audit's two named information-loss
seams were confirmed in the code and the first was closed; the second — per-view `as_of` and the
setup/execution regime dimensions dropped in `build_setup_inputs` — is **Slice 2**, and is deferred
deliberately because carrying it changes `SetupAssessment.regime_context` and therefore needs a
milestone that is allowed to change assessment output.

| # | Item | Blocked by | Note |
|---|---|---|---|
| **0** | **Dashboard startup diagnosis and smallest safe repair** — `fmits dashboard` no longer opens. Diagnose the cause, implement the **smallest safe repair**, and add a real **startup / product smoke test** so a dead surface fails a test rather than a user. | — *(unblocked; **this is the immediate next task, ahead of everything below**)* | **Named as NEXT AFTER CD on 2026-09-04 and deliberately NOT started inside Milestone CD** — CD's brief scoped it out and CD's closure brief scoped it out again. Distinct from **EP-21** (§7), which is the *refresh UX* epic: progress, per-source success/failure, freshness and what-changed. EP-21 is a feature; this is a **product outage** and takes precedence. **DONE 2026-09-04 — see `DR` in §8.** The dashboard was never dead: it started, served a correct page, and took 37.9 s to answer its first request because all four live engine reads were performed before the first byte of HTTP was written. Repaired by paying the refresh before the URL is announced (37.9 s → 1.7 ms), and pinned by a real startup smoke test |
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
| **EP-21** | **Operator Dashboard refresh UX** ⟵ *see also the NEXT-AFTER-CD item in §6* | The operator can see refresh **progress** while it runs, an explicit **success/failure** outcome per source, the **freshness** of every figure on the page, and **what changed** since the last refresh. Today `fmits dashboard` blocks for 30–45 s with no indication it is working, and a partially-failed refresh is indistinguishable from a slow one. Recorded as *not done* by `BV`, `CA` and `CC` in turn and **never tracked as an item until now** | LATER | Medium | — *(unblocked; `fmis.operator_dashboard` §BV already carries `as_of`, `source`, `status` and an unavailability reason on every `DashboardSection`, so the data exists and only the surface is missing)* |

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

### `DV` — Dashboard Shutdown Reliability Gate · **DONE**

Not a product milestone: an engineering-reliability gate that removes a blocker to trusting the
suite at all. It is recorded here because report 0044 §16.1 left it as the named next dashboard
task, and because the finding corrects that report's diagnosis.

| Field | Value |
|---|---|
| **The blocker** | The suite could not be trusted. Two startup smoke tests failed every full run — `14,529 passed / 2 failed` — and the working diagnosis was **order dependence** ("only after ~4,650 tests") with a very high `RLIMIT_NOFILE` suspected. A suite with two accepted failures cannot tell anyone whether the next change broke something |
| **Root cause** | **A `SIG_IGN` disposition is inherited across `exec`, and `subprocess` does not restore it.** A shell without job control starts a background job with `SIGINT` and `SIGQUIT` **ignored**; `Popen(restore_signals=True)` restores only the three signals CPython itself ignores (`SIGPIPE`, `SIGXFZ`, `SIGXFSZ`); and CPython deliberately does not override an inherited `SIG_IGN`. So a dashboard spawned from a **backgrounded** pytest could not receive `SIGINT` at all, and `os.kill` was discarded by the kernel |
| **Why it looked like ordering** | Only long runs get backgrounded. The short isolated runs were foreground and passed; the long full runs were backgrounded and failed. The reproducer was reduced from 4,660 tests to **7** — the smoke file alone: `2 failed / 65.85 s` from a `SIG_IGN` session, `7 passed / 5.26 s` from a terminal. The 67-file prefix run that was reported failing passes **3/3** in a terminal and reproduces `2 failed / 4,658 passed / 90.62 s` under `SIG_IGN`, matching report 0044 to 0.03 s |
| **What was excluded, with evidence** | `RLIMIT_NOFILE` in **both** directions (`ulimit -n 4096` still fails; `1048576` still passes). Descriptor leaks, thread leaks, orphan children, pipe deadlock, process-group errors and leaked global state — all excluded structurally, because the failure reproduces on 7 tests where nothing can accumulate and does not reproduce on 4,660 where accumulation is maximal. `setrlimit`, `signal.signal`, `os.chdir` and `set_start_method` appear **nowhere** in `tests/` or `src/` |
| **The hung child, observed** | Single-threaded, 9 descriptors, no child process, `ps` state `S` at 0 % CPU, stack in `serve_forever`'s `poll()` — **exactly where a healthy serving dashboard sits**. Not stalled in `shutdown()`, not on a lock, not on a pipe, not on a socket. A second `SIGINT` 60 s later changed nothing |
| **The fix, and the layer** | `tests/dashboard_smoke_driver.py` restores its own `SIGINT` handler under `if __name__ == "__main__"`. In the child rather than `preexec_fn`, which is unsafe in a process with threads and the harness keeps one pump thread per dashboard. **`src/` is deliberately untouched** — `fmits dashboard &` ignoring Ctrl-C is correct POSIX for a background job, and overriding it in the product would be compensating for how a test was launched. **156 added lines, 0 deletions, two test files** |
| **Tests** | **Two** (14,531 → **14,533**): a root-cause reproducer that ignores `SIGINT` in the pytest process and asserts Ctrl-C still works — **it fails in a plain terminal pre-fix**, so the defect can no longer hide until the next full run — and a three-cycle start/stop contract asserting exit 0, a re-bindable port and a 5 s shutdown budget against a measured 23 ms. Nothing weakened: no timeout raised, no sleep, no retry, no `xfail`, no `skip`, no reordering, no `SIGKILL` as normal shutdown |
| **Verification** | Full suite **14,533 passed in 11:18** under `-W error` **in the exact formerly-failing `SIG_IGN` session**, plus a normal-session full run; the failing scenarios re-run eleven times with zero failures. Real `fmits dashboard` on port 8799: address at 0.25 s, ready after the genuine **37.8 s** warm refresh, first HTTP **5.3 ms**, Ctrl-C → exit **84 ms** code 0, port released — report 0041's startup repair measured intact |
| **Non-regression** | Policy per-fixture digests all match, 72 `WAIT` / 9 `CANDIDATE` unchanged; no `src/` file touched. Live 8787 instance (PID **74079**) never stopped or signalled — `/`, `/swing`, `/swing/BTCUSDT` all 200, the *Since the previous comparable scan* block comparing two real scans across a restart, and three page loads recorded **no** history |
| **A correction to reports 0042–0044** | The aggregate `sha256 096a575a…` those reports quote over "81 records" is **not reproducible from this repository** — the formula was never committed, and 36 plausible reconstructions fail to match. The committed per-fixture table is strictly stronger and passes. Report 0045 §11.6 states a reproducible aggregate and its formula |
| **What it did NOT deliver** | No product capability whatsoever, and nothing in `FMITS_PRODUCT_CHANGELOG.md` — this changed no behaviour the owner can observe. Slice 4 not started |
| **Report** | [report 0045](reports/0045_2026-09-06_DASHBOARD_SHUTDOWN_RELIABILITY_GATE.md) |

### `DV` — Swing Product Slice 4: Risk & Trade-Planning Foundation · **DONE**

| Field | Value |
|---|---|
| **What shipped** | **FMITS can now tell the owner what a trade would risk.** `/swing/SYMBOL` carries a *risk and trade planning* panel for every scanned symbol; `/swing` carries a risk state column and the note that says whether a size was computed at all. Where the owner has declared his planning capital and the fraction he risks, the panel shows entry, invalidation, risk per unit, reward:risk, capital at risk, maximum quantity and position value. **No execution, no order, no broker, no account connection, no AI** |
| **The problem** | **The risk engine was finished and unreachable.** ~8,300 lines across `fmis.risk`, `fmis.portfolio_risk`, `fmis.position_sizing`, `fmis.portfolio`, `fmis.valuation` and `fmis.money` — correct, tested, guarded, and producing not one figure the owner could see. Opening `/swing/BTCUSDT` gave a complete decision and evidence report and said **nothing at all** about what a trade there would cost, or that anything was missing |
| **The audit's finding — two breaks, both at the edges** | (1) **No producer.** `RiskBudget(` and `RiskLimit(` appeared **nowhere in `src/`**, only in four test files, so `per_trade_ceiling` was never consulted, `fraction_for` never resolved and the chain was unreachable by construction. (2) **No consumer.** `swing_workspace` put `approval_note` in `workspace.metadata`; `swing_view` read that mapping **nowhere**, and `SymbolDecisionRow` carried no risk field at all. Proved live before any change: `/swing/BTCUSDT` returned four panels and zero risk content, and `~/.fmits/` held only `scan_memory/` |
| **Connect, do not rebuild** | The audited code is good and **none of it was rewritten**. It already satisfies almost every capital-preservation principle: unknown risk is `Absent(reason)` and never zero, `INDETERMINATE` is structurally distinct from `APPROVED`, the long/short sign rule is written once and refuses a transposed stop rather than absolute-valuing it, and no taxonomy, liquidity figure or event-risk verdict is invented. **No arithmetic was added** — an AST guard asserts the new package takes no quotient; every division remains `portfolio_risk.geometry`'s through `PositionSizer.size` |
| **Where the 2 % now lives** | `SPEC` §8.1's ceiling lived in **no code at all**, and could not live in `fmis.risk` or `fmis.position_sizing`'s computing modules, both AST-guarded to hold no literal beyond `0` and `1` — a guard **not weakened**. It now sits in `fmis.risk_policy`, written once, asserted to appear in exactly one module, and it is **structural**: a declaration above 2 % *cannot be constructed*, so there is no object to render and no branch to forget. Exact on both sides — `1.9999999999 %` accepted, `2.0000000001 %` refused |
| **The ceiling is never a default** | `budget_from` leaves `default_below_ceiling` `Absent`, because the specification states a maximum and no default. The owner's fraction travels on `SizingPolicy.risk_fraction` instead, so an **undeclared fraction resolves to no fraction** and the page names the missing input rather than sizing at the ceiling |
| **Capital is declared, never inferred** | `~/.fmits/risk_policy.json`, outside the repository, `ASSERTED` and dated — *"a figure the owner typed, not a balance this system observed"*. Deliberately **not** `PortfolioState.equity`, which is `MEASURED` from fills he does not have and which inventing would be fabricating his holdings. The file's keys are a **closed set**, so an API key or secret is refused **by name**; a loader that skipped unknown keys would make a credential invisible rather than impossible |
| **No geometry invented** | Entry is the engine's own `reference_price` carrying its *not an order price* caveat onto the page; invalidation is the engine's structural stop. **No stop from ATR, no assumed 2R or 3R target.** A candidate with no stop or no reference price is `NOT EVALUABLE` with the reason named |
| **`WAIT` gets no figures at all** | Not a zero, not a blank — one sentence saying there is no trade to plan, *"nothing is missing and nothing is wrong"*. A waiting symbol with a size beside it reads as almost a trade, and it is not almost anything |
| **Unknown portfolio risk is never zero** | Sizing runs with `remaining_open_risk=None` (*no portfolio read*), distinct from `Absent` (*read and unmeasurable*). `portfolio_impact` is always a stated absence and the type refuses anything else: total open risk, concentration and correlation are **not evaluated**, and a plan inside the per-trade ceiling is **not** one the book has room for |
| **Risk is not confidence, enforced three ways** | A vocabulary guard banning `confidence`/`probability`/`score`/`strength`/`evidence`/`independence`/`candidate` as identifiers; an import guard (no `swing_setup`, no `setup_evidence`, no `decision_support` — it duck-types over the assessment); and a **whole-record comparison** of every decision field with and without a declared policy, plus the workspace's groups, summary and ordering. All identical. **`WAIT` remains `WAIT`; `CANDIDATE` remains `CANDIDATE`** |
| **Money semantics** | The contract was already built and had **no ADR** in 0001–0028. [ADR-0029](docs/adr/ADR-0029-money-and-numeric-semantics.md) ratifies it, **changing no production code**: money and quantities exact and asset-tagged, market OHLCV stays `float` deliberately, `exact_from_market_price` the one crossing, and **fractions and ceilings follow money** — `0.02` as a binary float is `0.0200000000000000004163…`, and a ceiling decided by representation error is not a ceiling |
| **Adversarial proof** | **12 targeted mutants of the financial arithmetic, 12 killed** — `>` → `>=`, ceiling removed, ceiling raised, ceiling from a float, a default placed on the ceiling, the budget ignored, long/short swapped, entry/stop transposed, the quotient inverted, a missing figure becoming zero, portfolio impact claiming zero, the fraction doubled. **M10 found a real hole** — the existing zero-check exercised only the pre-sizing path — and it was closed by a test for the sized path |
| **Non-vacuity** | `_constructions_of("RiskBudget") == {"risk_policy/planning.py": 1}`, which returned `{}` before this milestone. A spy asserts the size is produced by the **existing** engine, so no parallel implementation can grow in the projection layer |
| **Test vectors** | Six independently **hand-calculated** examples — long, wider stop, short, the exact 2 % ceiling, a 0.00004 price, 250k capital — with every expectation written as a literal, plus the three refusals (stop above entry on a long, below on a short, equal to entry) |
| **Non-regression** | Policy **byte-identical**: `sha256 8b22e6c9…` over the committed reproducible aggregate, 81 fixtures, **72 `WAIT` / 9 `CANDIDATE`**. (The undocumented `096a575a…` is **not** cited — report 0045 established its formula was never committed.) Reliability Gate intact, smoke driver untouched. Scan Memory unchanged: no schema change, no risk state persisted, **no write path added** |
| **Two existing tests changed** | Both pinned a **panel index** to express an ordering invariant, and this milestone inserts a panel. Both now state the relation — decision **first**, audit **last**, trading panels above it. The invariant is not weakened; it is now expressed |
| **Performance** | `plan_for` **49.6 µs**, a whole 12-symbol watchlist **615 µs**, workspace build **+0.62 ms**, `/swing` render **+0.00 ms**. Sub-millisecond against a 30–45 s provider fetch |
| **Live verification** | Port 8799 (PID 15519); operator's **8787 (PID 74079) never stopped and never signalled**. `/`, `/swing`, `/swing/BTCUSDT` → 200. Panel order: decision → timeframes → families → **risk and trade planning** → evidence audit. Live market produced only `WAIT`, so **no candidate was fabricated** — candidate cases used controlled fixtures through the real projection and renderer. `~/.fmits/risk_policy.json` was **not created** |
| **Tests** | **163 new**, all offline and deterministic, in one helper and seven files: the ceiling and its exact boundaries, the hand-calculated vectors, the missing-input semantics, the declaration file and its security boundary, the architecture guards, the non-vacuity proof, and the end-to-end product scenarios |
| **What it did NOT deliver** | Portfolio impact from recorded positions, total open risk across a book, correlation as risk context, concentration axes, fees, slippage, lot-size rounding, leverage, non-linear instruments, FX conversion, a `fmits risk` command, a persisted `RiskBudget` lineage, risk in Scan Memory, alerts, AI interpretation, backtesting, paper trading — and **any form of execution, order, preview or broker connection**. Slice 5 was not begun |
| **Operator action still required** | **One decision remains the owner's and was deliberately not made for him**: write `~/.fmits/risk_policy.json` with the capital he plans against and the fraction of it he risks per trade (`"0.005"` is 0.5 %; the hard maximum is `"0.02"`). Until then every planning section states its absence and prints the remedy — **the correct product result, not a defect** |
| **Report** | [report 0046](reports/0046_2026-09-06_SWING_RISK_AND_TRADE_PLANNING_SLICE_4.md) |

### `DU` — Swing Product Slice 3: Scan Memory and "What Changed" · **DONE**

| Field | Value |
|---|---|
| **What shipped** | **FMITS remembers the previous scan, so the operator does not have to.** `/swing` opens with *Since the previous comparable scan* — which symbols changed, and exactly which named dimensions moved, from what to what; `/swing/SYMBOL` carries the same block beneath the current decision. **No policy change, no alert, no notification, no AI, no ranking, no freshness verdict, no redesign** |
| **The problem** | Slices 1 and 2 answered *what is happening with this symbol now, and why*. Nothing answered *what changed since I last looked*. The Swing scan is twenty symbols and most of them sit at `WAIT` for days — so a `WAIT` symbol whose **reason** moved from *the higher-timeframe regime gate rejected it* to *the directional families disagree* is in a materially different situation and rendered identically. The comparison required holding twenty symbols × eight states in his head between sessions, and in practice it did not happen |
| **Persistence — reuse, then a bounded store** | Four existing mechanisms were read first. `fmis.persistence.RecordStore` is the trade domain's journalled audit trail of money movements and **never prunes**; `fmis.archive.ArchiveStore` (ADR-0027) is permanent by definition and pruning it is forbidden; `fmis.snapshotting` has no producer. So the *primitive* was reused — `fmis.archive.atomic.atomic_write`, exactly as `fmis.persistence.store` reuses it — and the store is a small bounded rolling buffer of its own, at `~/.fmits/scan_memory`, **outside the git checkout** beside the archive and the durable store. No ignore rule was needed or added |
| **The central invariant** | **Scan memory observes decisions; it does not participate in them.** The arrow runs `swing_workspace → scan_memory` and never back, asserted for **26 packages** by an import-direction guard, and again functionally: the same workspace renders the same decision, direction, blocker and developing-evidence state against an empty store, a matching baseline and a *contradicting* one |
| **Where the write lives** | Not in `fmis.operator_dashboard`, which writes nothing by any means and has three guards saying so. `fmis/pipeline/scan_memory.py` wraps `refresh` through its **existing** `workspace_runner` seam, so the scan the page renders and the scan that is remembered are **one call** — the same discipline the three research artifacts already follow, applied to the one input produced per refresh |
| **Structured state, never prose** | A change is a difference between two named values an engine already decided. `CHANGE_DIMENSIONS` — twelve members — **is the whole comparison surface**, and a test asserts the comparator reads exactly it. No sentence, thesis line, blocker statement or rendered fragment is compared anywhere, guarded by name over thirteen prose fields |
| **Time passing is not a change** | Structural, not intentional: **no instant, age or bar count is a dimension, and per-role instants, ages and bar counts are not persisted at all** — so the comparator cannot report a routine observation update, because it cannot see one. Proved live: two real scans 83 s apart, every per-role age advanced, **zero events** |
| **Honest absence** | Four statuses, and *unchanged* is only one of them. First scan → *Baseline scan recorded*; incomparable → the reason; unreadable history → the reason, with the market analysis untouched; write failure → *this scan was not recorded*. `ScanComparison` **refuses at the type level** to carry per-symbol results under any status but `COMPARED`, so *nothing changed* cannot be said without a real comparison |
| **No score, no rank** | No field in the package could hold one, guarded against a sixteen-word vocabulary. Attention is a **partition** — changed before unchanged, each group in the scan's own universe order — asserted as an ordering test. The whole package contains **five arithmetic expressions**, written out and checked as a set: four path joins and one set difference |
| **Restart continuity** | The acceptance requirement, proved three ways: offline across two store objects, in a real subprocess through the real command, and **live** — the dev dashboard was killed, a new process started over the same history root, and the second scan compared against the surviving baseline |
| **Idempotence** | The record path is a pure function of the scan's identity, and the identity digest deliberately **excludes the results** — a digest over states would make *nothing changed* indistinguishable from *nothing ran*. A page `GET` renders a held snapshot, performs no refresh, and records nothing: asserted offline, and again in a real process across six page loads |
| **Policy non-regression** | **Byte-identical, and identical to Slices 1 and 2**: the same 81 fixtures through the full composition root, `sha256 096a575a…`. No policy file was touched |
| **Live verification** | Port 8799 with an isolated history root; **the operator's 8787 instance (PID 49813) was never stopped**, verified by `lsof` before and after. 20 symbols, complete, baseline persisted (11,080 bytes), decoded by a *new* store object, 7 page loads → still 1 record, process restarted → baseline survived, second scan compared → **0 material changes across 20 symbols**, honestly |
| **Performance** | Per refresh: append 0.26 ms · read+decode 0.13 ms · compare 0.08 ms · render +0.07 ms — about **0.5 ms** against a 30–45 s provider fetch. 9.7 KB per scan, at most 8 retained (~78 KB) |
| **Tests** | **375 new**, all offline, plus a seventh startup smoke test that proves the real command records one scan and page loads record none. Invariant/property tests over generated pairs, and non-vacuity proved by reconstructing the product without the feature |
| **Verification** | Focused suites green (1,247 across the Slice 3 scope and every guard it touches); full suite **14,155 → 14,531 collected**, **14,529 passed / 2 failed** under `-W error` (12:21), zero skips and zero new warnings — the delta is exactly the tests added. Two genuine regressions were found by the full suite and fixed at the architecture — an export-name collision with `fmis.swing_workspace.UNSTATED`, and a pipeline import-direction breach — with **no guard weakened**. **The 2 failures are pre-existing and are not this milestone's**: two startup smoke tests time out waiting for the dashboard subprocess to exit after `SIGINT`, they fail only when run after ~4,650 other tests, and they were **reproduced identically in a clean worktree at `77b956d`** with Slice 3 absent. No fix was attempted — it is outside scope and the code it would touch is the shutdown path report 0041 repaired. See report 0044 §16.1; recommended as the next dashboard task |
| **What it did NOT deliver** | Alerts of any kind, AI interpretation, long-term history analytics, historical charts, opportunity ranking, a validated freshness policy, terminal renderer parity, and any Slice 4 work |
| **Report** | [report 0044](reports/0044_2026-09-05_SWING_SCAN_MEMORY_SLICE_3.md) |

### `DT` — Swing Product Slice 2: The Operator Decision Layer · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | **The trading question, above the audit question — and the three timeframe clocks the page had been collapsing into one.** `/swing` opens with a scan snapshot and six operator columns; `/swing/SYMBOL` becomes four panels with the decision first and the evidence audit last, complete and unchanged. **No policy change, no risk, no sizing, no stops, no alerts, no redesign** |
| **The feedback** | Slice 1 succeeded and the operator used it. His report was **not** that anything was wrong or missing: it was that understanding BTCUSDT meant reading a long technical record to assemble four facts — what was decided, which way the readable evidence points, what is holding it, and how old the data is |
| **Root cause 1 — four facts, no values** | All four were *derivable* and none was *represented*. The three `Lean`s were on the assessment and nothing reduced them to a line — a surface doing it itself would have been a renderer inferring a side. The policy's three `WAIT` exits were distinguishable only as three different English sentences, and a sentence cannot be counted, grouped, or compared across two symbols |
| **Root cause 2 — the discarded clocks** | `MultiTimeframeFactSheet` carries an `as_of` **per view** and says explicitly that `newest_as_of` is *"not a shared observation instant"* — and `run_setup_for_symbols` threw the whole sheet away with a literal `_`. So one instant stood for three timeframes that close at different rates. **Measured live**: BTCUSDT's page said `as_of 2026-09-04T04:00Z`, and behind it the 4h role was 7h 59m old, the 1d role 1d 11h — and **the 1w role, which gates whether any direction may exist at all, was 11 days 11 hours old** |
| **The architecture** | Three additions in `fmis.swing_setup` — the ADR-0028 package, because `DevelopingEvidence` names a side and building this one layer up would have meant spelling `LONG` where the repository forbids it, or inferring a side from prose. `TimeframeReading` owns `age_at` beside the instant it measures (the arrangement `fmis.market_pulse` already uses, and why both layers above stay guarded against arithmetic); `SetupReadings` carries the per-role instants and the **structured** context-regime dimensions; `decision_summary.py` projects `DevelopingEvidence` and `Blocker`. Carried on one new defaulted `SetupRunResult.readings`, which reaches the workspace with **no change to `fmis.today` at all**. **One fetch, one regime evaluation, one assessment** — the new composition root calls the function `setup_assessment_for_sheet` was already a wrapper over |
| **`WAIT` never becomes a signal** | A `WAIT` whose families all lean one way is real and was being discarded; reporting it as `LONG` would contradict the policy. So it is reported as **developing evidence**, in its own type and vocabulary, always beside the decision chip — *"long leaning · not confirmed, and no direction was stated"*. Enforced at **five points**, two on the types themselves: `DecisionSummary` rejects `DIRECTION_STATED` beside `WAIT` and rejects a direction the assessment does not carry, `DevelopingEvidence` rejects a lean with an opposing family, and two tests hold the model and the rendered row |
| **The blocker, and the anti-drift guard** | `Blocker` names which of `evaluate_setup`'s exits fired, walked in the policy's own order over the same structured values, and states **the requirement the gate already demands** (*"must be `trending`"*) — never a price, a date or a prediction, asserted by a test that rejects currency symbols, decimal prices and the words *will/expect/likely/soon/predict*. A test walks all 27 seed triples and asserts the named blocker matches the sentence the policy itself wrote — **24 WAIT exits, both kinds, zero mismatches** — so a future policy change that this projection misses fails a test. Where the structured facts are absent the answer is `UNDETERMINED`, not a guess recovered from thesis prose |
| **Freshness — what was decided and why it stopped there** | The dormant `fmis.snapshotting.FreshnessReading` was **inspected and deliberately not activated**: it has no producer anywhere, it measures **bar ages at snapshot-freeze**, and constructing one means standing up the snapshot-record pipeline — a large architecture for a display concern. Instead the per-role `as_of`, `closed_count` and an age against the page's own instant are carried from the sheet that already had them. **No `FRESH`/`STALE` verdict is published**: no validated staleness bound exists for any role and the roles are not comparable, so three invented thresholds would be three unvalidated policies. A test forbids any model field matching `fresh\|stale\|expired\|verdict\|ok\|healthy`, and the page says so in words |
| **Nothing was removed** | The Slice 1 audit moved to panel 4 behind a disclosure, unchanged — a test asserts every evidence item's key, statement and observed value is still on the page. One genuine repetition went: `_IndependenceNotes` numbers each **distinct** explanation, prints it once beneath the table and marks each row with its number, the pattern the page's own `_Footnotes` already used. Family keys gained readable labels with **the engine key printed beside every one** |
| **Policy non-regression** | **Byte-identical, and identical to Slice 1's**: 81 fixtures through the full composition root, canonicalised as complete recursive `repr()` renderings — `sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42` before and after, 72 WAIT / 9 CANDIDATE unchanged. Covers both policy-adjacent edits: naming `CONTEXT_ROLE_STRUCTURE_REQUIREMENT` (a constant equal to the literal it replaced, compared with the identical `is` test) and the composition refactor |
| **Live verification** | Port 8899, operator instance untouched; all twelve routes 200. Six symbols, and the overview answered before opening one: 5 held by the HTF regime gate, 1 by a timeframe conflict, 5 leaning, 1 divided. **BTC** — leaning long, gate `transitioning`, 1w neutral / 1d sustained_higher, independence not established, 1w **11d 11h** old. **BNB** — divided, gate **passed**, 1w `sustained_lower` against 1d `sustained_higher`. **SOL** — leaning and gate-blocked like BTC but with a `neutral` setup timeframe and an inverted evidence balance. No quantified edge claim, no score, no *almost ready*, no `>fresh<` or `>stale<` |
| **Tests** | **53 new**, all offline. One was **found vacuous during review and replaced**: the independence-deduplication test inspected a fixture whose four explanations are four distinct strings, so its loop never ran; it now tests the mechanism directly plus a rendered assertion that every marker resolves. Non-vacuity proved against the pre-Slice-2 shape, still constructible because every widened carrier is defaulted |
| **Verification** | Focused suites green (1,578 in the Slice-2 scope); **full suite 14,102 → 14,155 passing under `-W error`** (11:14) — the delta is exactly the tests added, with no failures, no new warnings and no skips. **One regression was found by the full suite and fixed**: `test_structural_trend`'s layering guard scans files below that engine for the *text* `fmis.structural_trend`, and a renderer docstring plus a hardcoded provenance label both contained it. The guard was right — the producing engine was already on the page, supplied by the engine itself — so both literals were removed and no exemption was widened |
| **What it did NOT deliver** | A freshness **policy** (per-role bounds, any fresh/stale verdict) — needs a validated bound per role and none exists. The terminal `fmits workspace`, `fmits scan` and `fmits setup` renderers show neither the operator summary nor the per-role times; the model carries both. Risk, sizing, stops, targets, execution, paper, AI, alerts, scan-to-scan change tracking and EP-21 untouched |
| **Report** | [report 0043](reports/0043_2026-09-04_SWING_OPERATOR_DECISION_LAYER_SLICE_2.md) |

### `DS` — Swing Product Slice 1: The Symbol Decision Surface · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | **One row per scanned symbol, and a detail page for every one of them.** `/swing` gains an *Every scanned symbol* table (symbol · status · direction · classification · the engine's own condition, each linked); `/swing/SYMBOL` now resolves for **every** assessed symbol — not only actionable ones — and renders four panels: decision, timeframe/regime context, directional families, and the evidence report item by item. **No policy change, no new indicator, no ranking, no redesign** |
| **The problem** | The operator's verdict was *"today I cannot make a better swing-trading decision with this system"* — and the audit established the cause was **not** missing analysis. FMITS computed a full `SetupAssessment` and a complete `SetupEvidenceReport` for every symbol, `WAIT` included, and discarded almost all of it one layer before the screen |
| **The root cause** | `no_trade_groups` was the **only** path a `WAIT` symbol had into the workspace, and it folds each into `NoTradeGroup(reason, classification, symbols)` — three fields, in which a symbol arrives as *a name inside a list of names* under one sentence shared with every symbol that reached the same conclusion. Its regime reading, its three directional families, its sufficiency, its `as_of` and its whole evidence report reached the workspace **nowhere at all**. Consequently `SwingView.row_for` — the detail route's lookup — consulted `opportunities` and `wait_list` only, and `/swing/BTCUSDT` answered *"not an actionable or waiting setup on this refresh"* for a symbol the engine had fully assessed. Second seam: `evidence_digest_for` reduced a whole report to four integers, dropping every `statement`, `observed`, `source`, `scope`, `families`, `correlated_with` and `independence_note` |
| **The architecture** | The stated preference, followed exactly: *existing calculation → existing structured evidence → narrow product projection → workspace → renderer*. `SymbolDecision` (workspace) → `SwingWorkspace.decisions` → `SymbolDecisionRow` (dashboard) → HTML. **No trading logic in the dashboard, no parallel representation** — the projection carries `SetupAssessment`'s and `SetupEvidenceReport`'s own fields and leaves `SetupRow`, `EvidenceDigest`, `NoTradeGroup` and `RankedSetup` untouched. `no_trade_groups` and `symbol_decisions` now derive `reason` and `classification` through **the same two helpers**, so the grouped section and the per-symbol row cannot describe one symbol differently |
| **Policy non-regression** | **Byte-identical.** 81 fixtures (27 seed triples × 3 symbols) run through the full composition root `setup_assessment_for_sheet` — three regime evaluations, evidence report, decision context, `build_setup_inputs`, `evaluate_setup` — canonicalised as complete recursive `repr()` renderings and compared before and after: `sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42` both times, 72 WAIT / 9 CANDIDATE unchanged. The per-fixture digests are committed, so a future policy change breaks the test and **names the seed triple that moved**. A fourth test guards the guard: it asserts the matrix still covers all three `WAIT` exits, so a matrix that silently stopped exercising them fails rather than passes vacuously |
| **No ranking, guarded** | A regex over both models' field names rejecting `score|rank|closeness|confidence|probabilit|weight|strength|percentile|priority|opportunity_|likelihood|conviction`; an order-reversal test proving scan order is the only order; a check that the rendered table carries no ordering column; and limitation **WS-11** stating on the page that scan order carries no meaning. The research record (CA NO_EDGE, CB UNDERPOWERED, CC INFEASIBLE, CD dependence-exists) is neither rewritten nor reinterpreted — it forbids claiming a validated edge, not explaining a deterministic conclusion |
| **Independence preserved** | `correlated_with` and `independence_note` survive the seam and are **rendered**: every non-independent item is marked *not independent* with the projection's own note and the keys it shares inputs with. Three correlated observations shown as three plain rows would read as three-fold corroboration; they are one reading seen thrice, and the page says so |
| **Non-vacuity** | Proved **directly** against the three unmodified pre-Slice-1 carriers, not by test-count increase. `NoTradeGroup` is asserted to have exactly three fields and every new fact is asserted **absent** from what it produced; `evidence_digest_for` is asserted to have no `statement`/`observed`/`source`/`scope`/`correlated_with`, and its `repr()` to contain no `structure=`, no `1w`/`1d`, no `sustained_higher`/`sustained_lower`; `row_for` is asserted to return `None` for both waiting symbols while `decision_for` returns records for both |
| **Live verification** | Run on port **8899**, leaving the operator's 8787 instance untouched; all ten routes 200. The live market reproduced the audit exactly. **BTCUSDT**: two of three families lean long (`setup_structural_trend` `sustained_higher` 1d, `setup_evidence_alignment` `watch (dominant=upward)`) and the **weekly regime gate rejected it first** (`structure=transitioning`). **BNBUSDT**: *cleared* that gate (`structure=trending`) and then hit weekly `sustained_lower` against daily `sustained_higher` — a real higher/lower-timeframe structural conflict. Before this milestone both were one line of shared text |
| **What it did NOT deliver** | **Per-view `as_of` and freshness policy** — `SetupInputs` carries one `newest_as_of`; Slice 1 carries the assessment's own instant and explicitly makes no claim about whether it is recent enough to act on. **Setup-role and execution-role regime dimensions** — computed and discarded in `build_setup_inputs`; carrying them changes `SetupAssessment.regime_context`, which this milestone forbade. The terminal `fmits workspace` renderer does not show the new section. EP-21, scan memory and alerts untouched |
| **Verification** | 41 new tests, all offline (no provider, no clock, no filesystem, no network); focused suites green; **full suite 14,061 → 14,102 passing under `-W error`** — the delta is exactly the tests added, with no failures, no new warnings and no skips (see report 0042 §8) |
| **Report** | [report 0042](reports/0042_2026-09-04_SWING_SYMBOL_DECISION_SURFACE_SLICE_1.md) |

### `DR` — Dashboard Startup Repair & Product Smoke Test · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | The existing dashboard, opening again — and the first automated test in this repository that performs the **operator's own sequence**: run the command, read the URL off the terminal, request it, look at the page, press Ctrl-C. Two production files changed, two test files added, six tests added beside them. **No redesign, no new dashboard feature, no second dashboard, EP-21 untouched** |
| **The failure** | `fmits dashboard` bound its socket, printed a URL, and served a correct page — in **37.9 s**. The first request performed all four live engine reads *before writing a single byte of HTTP*. A browser given an accepted connection that stays silent that long reports the server as having stopped responding, so the command started and the dashboard never opened. Intermittent by construction: whether it crosses the browser's timeout depends on how slow Binance and FRED are that day |
| **The root cause** | `SnapshotHolder.current()` refreshed lazily on the first request while holding its lock, and `serve()` announced the URL immediately after binding. **Deliberate and documented** — `_run_dashboard` said *"the first refresh happens on the first request, not here… the owner sees the page assemble"* — and wrong in exactly one assumption: server-side HTML is written once and complete, so there is no progressive render to watch. The choice traded a silent terminal for a silent socket |
| **Regression origin** | **A dormant defect since `BV` (`0f31293`, 2026-08-24), not a recent regression.** No commit broke it; nothing has touched `src/fmis/operator_dashboard/` since `fd1270b` (2026-08-26). It became visible as refresh cost grew. This board has recorded the 30–45 s block since `BV`, through `CA` and `CC`, without ever connecting it to the dashboard failing to open |
| **Why 14,049 tests missed it** | Every piece was covered and the sequence was not. `test_operator_dashboard_server.py` binds a **real** socket and makes **real** HTTP requests over every route — with a stub refresher that returns instantly, so it never pays a refresh and never runs `_run_dashboard`. `test_pipeline_cli_dashboard.py`'s 8 tests parse arguments, check help text and refuse bad binds; **none of them serve**. Nothing crossed CLI → `serve` → `compose` → HTTP in one piece. **Classified: product testing gap** |
| **The repair** | `serve()` gains `warm` and `preparing`; when warming it refreshes once between the bind and the announcement, so the URL is printed only when a request to it can be answered. `warm` defaults to `False` — `serve` is the mechanism, and the decision belongs to the command the operator runs — so **no existing caller or test changes behaviour**. A warming refresh that raises is **not** swallowed (`compose.refresh` already absorbs every *source did not answer* family, so anything escaping it is a defect worth reporting at startup), and the listener is closed on that path |
| **What the operator sees** | A two-part banner: `address` and the reason for the wait immediately, then `open` when it is ready. The terminal is never silent, and the URL is never offered before it can be served. **37.9 s → 1.7 ms** for the first page load; the wait moved to where it is visible and explained |
| **The smoke test** | A **subprocess** runs the real `cli.main(["dashboard", …])`. Process, argument parsing, runner, warming refresh, `serve`, bound socket, HTTP handler, composition root, every `sections` mapping, renderer and interrupt are production code. **Only the three networked reads are replaced**, through `SnapshotHolder`'s own documented `refresher` seam, by the real `SwingWorkspace` / `MarketPulse` / `MacroContextReport` fixtures the dashboard suite already uses. Proves: starts · does not crash · becomes ready · main route 200 · **recognisably FMITS** (title, product name, a link to every route in `PAGES`, a benchmark only an engine read could produce) · every declared route answers · **real `SIGINT`, exit 0, "stopped" on stderr**. Offline, **4.8 s** |
| **Non-vacuity, proved by running it** | Three break modes — `startup` (the refresh raises), `route` (every path resolves to nothing, so the process still starts and still announces: the trap a startup-only check falls into), and `slow` (the refresh costs real time, because offline an instant fixture makes the *ordering* invisible and would leave the repair's own test measuring nothing). **The repair was then temporarily reverted and the suite re-run: 3 of 6 failed**, including the one that tests it directly |
| **Architecture finding** | **No live market provider is required to render the shell** — asserted, so if that ever changes the smoke test hangs against Binance and FRED rather than passing quietly. One defect was found and fixed in the repair itself during review: a failed warm-up leaked the bound listener |
| **What it did NOT deliver** | **EP-21 in any part.** `?refresh=1` from the browser still blocks 30–45 s with no progress, no per-source outcome, and no way to tell a slow refresh from a partially-failed one. Report 0041 §11 records the full product-state assessment: **0 broken, 4 stale, 6 unrepresented backend capabilities, 5 UX debts, 6 things not implemented anywhere** |
| **Verification** | 6 smoke tests + 4 `serve()`-level + 2 CLI-wiring tests; every route verified by hand against **live** data at `http://127.0.0.1:8787/`; full suite under `-W error` (see report 0041 §10) |
| **Report** | [report 0041](reports/0041_2026-09-04_DASHBOARD_STARTUP_REGRESSION_REPAIR.md) |

### `CD` — Paired-Effect Dependence Measurement · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | `fmis.paired_dependence` (13 modules) and the command **`fmits research dependence`**, which has **no live path**: `--from-capture` or `--from-study`, never a fetch. Two persisted artifacts under `reports/artifacts/`: the Milestone BZ source capture (`07b500c7…`, 13.4 MB) and the CD study (`754dccd6…`, **2,390 observation-level paired differences**) |
| **What it answered** | *How dependent are the **actual** paired admission-vs-control forward effects — within one economic asset, and between assets in the same period — and what does that do to Milestone CB's information requirement?* **Within-asset: essentially independent. Between-asset: positively dependent, at ~100× the level at which the requirement stops being finite.** Verdict **`INCONCLUSIVE`**, because 15 assets cannot pin the number |
| **The gap it closed first** | Milestone CA is a pure function of a saved BZ capture and has no live path — **and that capture was never written into the repository.** The runner that made it during BZ was ad hoc and is gone. That single missing file is the direct cause of CB-1, CB-2 and CC-1. CD wrote the runner down and persisted the result |
| **`rho_w` — within asset** | **−0.0355**, 95 % asset-clustered bootstrap **[−0.0774, −0.0064]**, over 15 assets and 155 admissions; in **[−0.0355, +0.0322]** across all 15 panels. The design effect `1 + (m−1)ρ` at `m` = 10.33 is **1.00**: clustering by symbol costs no information. **Milestone CB's limitation CB-2 is closed with a measurement** |
| **`r_b` — between assets** | **+0.1984**, 95 % block bootstrap **[−0.0491, +0.4181]**. Positive in **all 15 (family, sample) panels** (+0.095…+0.549, median +0.197) and **all 16 sensitivity cells** (+0.112…+0.514). The 24-bar block gives **+0.514**, so the sealed 60-bar choice is the *conservative* half of the grid |
| **Where Milestone CC was wrong** | CC assumed CA's paired within-symbol difference removes the market factor and measured a residual of +0.0023 by proxy. **It does not remove it** — the measured value is +0.1984, ~80× larger. **CD's own first explanation of why was also wrong and was withdrawn after review**: the matching radius is a **ceiling**, not a floor (controls sit 10–90 days away for 1,387 of 1,430 matched rows), and two of five families draw a **same-bar** control (960 of 2,390 rows). The real cause is that `control_forward` is a mean over **200** draws carrying 2.8 % of the admission leg's variance, so `corr(D, admission) = +0.987` and `D` is arithmetically close to the raw admission outcome — for `ca_null_opposite_direction`, `D ≡ 2 × admission` to 6e-14 |
| **The design implication** | `K*` = 467 so the saturation threshold `1/K*` = **0.002141**. **Review found the effective-cluster arithmetic overstated ~3×** — `r_b` is an observation-level correlation while `K/(1+(K−1)r)` consumes a cluster-level one; arbitrated by simulation (true design effect 1.4266 vs the sealed formula's 3.7446). Corrected, the design-relevant `q · r_b` is **+0.037**, still **17×** the threshold; CC's **38** eligible assets supply **8.0–23.1** effective clusters and its **106**-asset ceiling **9.1–37.5**, against **467** — a **12–51×** shortfall. The sealed path is unchanged and the correction is carried beside it as **CD-8** |
| **Why the verdict is nevertheless `INCONCLUSIVE`** | The headline interval spans from at-or-below zero to far above the threshold, so the same data supports "dependence costs nothing" and "no universe of any size is enough". CD refuses to read the point estimate as though the interval were not there. **5 of 15 panels — every family on validation — are `UNREACHABLE`** across their whole interval, but validation is semi-contaminated by construction, so that is corroboration and not confirmation |
| **A reproducibility result nobody asked for** | A fresh 80-minute replay three years on reproduces Milestone CA's counts **exactly**: **246** and **234** candidates, and **155 / 91 / 234** matched admissions, **delta 0 on all three samples**. The 21.3 % overlapping-admission share matches report 0037 §23's "33 of 155" to the unit |
| **Estimator validation** | 14 synthetic scenarios × 25 replicates. Every point expectation recovered within a **derived** `1/(K−1)` tolerance, ordering reproduced strictly (0.0007 < 0.0573 < 0.2016 < 0.4897). The decisive row: CC's cross-sectional demeaning applied to a *known* panel returns **−0.071428 = −1/(15−1)** to six decimal places — **CC's failure reproduced with CD's own machinery**. On real data CC's estimator returns −0.05…−0.33 everywhere, never near the +0.095…+0.549 the data contains |
| **Reuse, not duplication** | No second power calculator, no second correlation primitive, no second quantile rule, no second seed derivation, no second candle model, no second CLI framework. CB's `required_information`, CC's `effective_clusters`, `pearson`, `market_residuals` and `economic_asset_id`, and `research_design.numeric`'s three primitives are all **called**. The only new mathematics is the one-way random-effects ICC and the inversion of the saturation curve |
| **The one change to a sealed milestone** | **14 lines.** `study_from_capture` gained an **additive** `record_observer` sink — Milestone BZ's own pattern on `capture_geometry_candidates` — so CD reads CA's `PairedRecord`s from CA's own loop instead of copying it. A regression asserts a study run with an observer is equal field for field to one run without, and that alternate-seed records are **not** observed |
| **Production safety** | `CONFIRMATION_LOOKBACK_BARS` = 10, `MINIMUM_AGREEING_FAMILIES` = 2, `DEFAULT_TIMEFRAMES` = 1w/1d/4h, `DEFAULT_BACKTEST_LIMIT` = 250, warm-up 1,750 days — each asserted by import. CA, BY, BZ and CC seals byte-identical; CB reproduces. No production module imports `fmis.paired_dependence` |
| **Verification** | 660 CD tests; full suite **14,049** under `-W error` (13,384 before; +665); **96 % statement and branch coverage** of `fmis.paired_dependence`. **43/43 rule-level mutation probes killed, 0 survivors**, re-run in one campaign against the final tree — 9 first-pass survivors and 1 bad anchor, **every one investigated and closed with a regression**. Offline reproduction proven with **both** `fetch_raw_klines` and `study_from_capture` monkeypatched to raise, and the published artifacts are now pinned by a committed test. Seal determinism across 4 `PYTHONHASHSEED` values in separate processes; 47 seal-mutation tests |
| **Three vacuous tests found by mutation** | A shared-block floor never exercised because `pearson` refused the pair first; a single-bucket refusal reached through the *point estimate* being undefined; and an economic-identity test using `BTCUSDT`, whose base asset and identity are the same string, so it could not tell the call from a no-op. All three passed for the wrong reason and all three are now non-vacuous |
| **Guards** | One fired on the renderer during development and was **obeyed, not widened**. Four existing allowlists were extended for CD on the footing CC already established. **CD's first attempt at strengthening them was defeated by a reviewer** — the guards derived their exemption set from the allowlist they were checking, and a fake package was admitted with a two-line edit and an empty guard file. The invariant is now declared **once** as a **partition** (`tests/architecture_tiers.py`): research ∪ production = the packages on disk, so silence is not a classification. **56 packages, 4 research, 52 production, `pipeline/cli.py` the only non-research importer.** The bypass is reproduced and rejected, and four unauthorised dependencies injected into `src/` were each caught. The zero public-name collision invariant caught three CD exports; **CD renamed its own** |
| **Independent review** | **Performed, and it changed the science** — three narrow reviewers, **30 findings, 2 critical**, every one reproduced independently before acceptance and two arbitrated by fresh simulation. The two critical findings overturned CD's **mechanism** and its **effective-cluster arithmetic**; neither moved a headline estimate or the verdict, which all three reviewers recomputed from the artifact and confirmed exactly. **9 defects fixed with regressions** — a weighted-ICC bug whose fix also repaired a real pseudoreplication hole, an observer hook that could have mutated Milestone CA's published effect, and **two architecture guards CD had advertised as a strengthening that were in fact circular** (a reviewer admitted a fake package with a two-line edit and an empty file). **5 findings sit inside the digest and are disclosed rather than fixed**, each pinned by a test — Milestone CA's own precedent. 12 post-review limitations (CD-8…CD-19) carried separately from the seal. **The report was substantially rewritten and every withdrawn claim is marked as withdrawn** |
| **Record** | [report 0040](reports/0040_2026-09-03_PAIRED_EFFECT_DEPENDENCE_MEASUREMENT.md) |
| **No permission granted** | `DependenceVerdict` and `RequirementOutcome` each report `is_approved_for_trading` `False` and `earns_forward_test` `False` for **every** member, asserted over both enums. CA's `NO_EDGE`, CB's `UNDERPOWERED` and CC's `INFEASIBLE` all stand, and CC's verdict is preserved verbatim with the refinement recorded beside it. **No verdict here approves trading of any kind** |
| **What it removes from the roadmap** | CC recommended a **Warm-Up Requirement Sensitivity** study as the next milestone. **CD removes its premise**: warm-up moves the *ceiling*, and the ceiling is not what binds — and the corrected arithmetic does not restore it. CD's *own* first proposal — a control at the same instant — was **also withdrawn after review**, because two sealed families already do exactly that and return `r_b` of +0.188 and +0.200: a same-instant opposite-direction control **doubles** the market factor rather than cancelling it. The open question is whether the estimand can be given a control leg with **real, contemporaneous variance**. The honest alternative — stopping this swing-admission research branch after five milestones — is equally on the table and is the owner's decision |

### `CC` — Universe Feasibility & Information Expansion Study · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | `fmis.universe` (15 modules), the command **`fmits research universe`**, and one read-only public endpoint added to the existing Binance adapter (`exchangeInfo`). Two persisted artifacts under `reports/artifacts/`: the raw series capture and the derived feasibility study |
| **What it answered** | *Can FMITS build a research universe large and independent enough to test Milestone CA's +0.10 ATR admission effect?* **No.** Verdict **`INFEASIBLE`**, binding constraint `cluster_count` |
| **The numbers** | 3,649 listed spot instruments → **660 economic assets** → **38 eligible**, against the **467 clusters / 4,823 admissions** Milestone CB requires |
| **The finding nobody expected** | Dependence was **not** the wall. Crypto co-moves heavily (mean pairwise correlation **0.604**, one market factor explaining **62.5 %** of variance) — but CA's estimand is a *paired within-symbol* difference that removes that factor, and the residual sits **+0.0023 above the −1/(K−1) demeaning artefact**: indistinguishable from independence |
| **The actual wall** | **FMITS's own warm-up.** The weekly context role at 250 candles costs **1,750 days of history per instrument**, and **598 of 622 depth exclusions are that requirement**. Zero instruments were lost to missing bars, gaps, duplicates or liquidity. The binding constraint is internal, not the market's |
| **The generous bound** | A post-hoc ceiling — explicitly not pre-registered, and able only to move the answer toward FEASIBLE — over **every year the provider has ever produced** reaches **106 clusters and ~1,089 admissions**. Still 4.4× short on both dimensions |
| **What FMITS can ask today** | With 38 assets it can resolve an effect of **~0.3–0.5 ATR**, three to five times the cost of trading. It cannot resolve 0.10, and CC forbids substituting one question for the other |
| **Density, tested not assumed** | CA's three disjoint samples give **5.145 / 5.163 / 5.202** admissions per symbol-year — agreeing to **1.1 %** across two periods and two symbol sets, one materially less liquid. The ~5.2 divisor behind CB's 467 is well supported |
| **Survivorship** | **`PARTIALLY_SURVIVORSHIP_AWARE`.** Binance retains delisted pairs as `BREAK` with their klines back to 2018, and three halted assets sit in the eligible 38 — but `HSRUSDT` is absent from both endpoints, so retention is demonstrably incomplete and the gap is recorded as **unmeasurable**, never zero |
| **Reuse, not duplication** | No second candle model, no second exchange adapter, no second bootstrap, no second power calculator, no second CLI. The warm-up is **asked of** `derive_warmup`, the design arithmetic **is** Milestone CB's `fmis.research_design`, and CA's constants and BY's windows are imported by identity. The only new abstraction is economic-asset identity, which the repository genuinely lacked |
| **Defect found in provider data** | `KLAYUSDT` returns a kline whose **close time precedes its open time**. The canonical `fmis.ingest` boundary refused it; CC records it as a named `MALFORMED_BARS` exclusion rather than crashing |
| **Defect found and fixed in CC itself** | The first model passed the *effective* cluster count as both the cluster count and the per-cluster divisor, which cancelled the between-asset correlation out entirely — the dependence measurement was decorative. Caught by a hostile test, re-derived, and fixed by applying `sqrt(1 + (N−1)r)` to CB's output |
| **Production safety** | `CONFIRMATION_LOOKBACK_BARS` = 10, `MINIMUM_AGREEING_FAMILIES` = 2, `DEFAULT_TIMEFRAMES` = 1w/1d/4h, `DEFAULT_BACKTEST_LIMIT` = 250 — each asserted by import. BY and CA seals byte-identical; CB reproduces. No production module imports `fmis.universe` |
| **Verification** | 432 focused tests (393 + 39 review/audit regressions); full suite **13,384**; 10/10 rule mutants killed, 0 survivors; **90 %** statement + branch coverage of CC scope; 23 seal mutations all moving the digest; digest determinism across 4 `PYTHONHASHSEED` values; offline reproduction with the candle transport made fatal; 4 no-lookahead controls each paired with a non-vacuity check; **0 safety guards weakened** (one endpoint guard widened to an exact two-set, with its reason recorded) |
| **Independent review** | **Performed** — 3 reviewers, 16 findings, **2 rejected with evidence** (one of them agreed with the report and was wrong to). Biggest result: the sealed residual-dependence scenario **cannot measure residual dependence at all** — demeaning pins it at −1/(K−1) for any true value — so the scenarios do not bracket the answer, and a correlation of just **0.0023** would make +0.10 ATR unreachable at any size. That strengthens the negative. Also fixed: a latent path to inverting a design parameter from the **protected holdout**; an ordering control that could not detect an expectancy sort; a claimed holdout control that did not exist; an eigenvalue routine that could return a subdominant value silently. **26 regressions added; no measured figure moved; verdict unchanged** |
| **Honestly not done** | The sealed 12-asset density replay was **not executed** (≈1 h wall clock) and is reported as NOT MEASURED. **Discovery is not frozen** in the capture, so offline reproduction covers the funnel and everything downstream, not the discovered count. The pre-review artifact was **deleted in error** during the post-review re-persist; layer B was regenerated on a 2026-09-03 discovery, all downstream figures bit-identical |
| **Record** | [report 0039](reports/0039_2026-08-28_UNIVERSE_FEASIBILITY_AND_INFORMATION_EXPANSION.md) |
| **No permission granted** | `FeasibilityVerdict.is_approved_for_trading` is `False` for every member, asserted over the enum. CA's `NO_EDGE` is untouched. **No verdict here approves trading of any kind** |

### `BX` — Swing Trade Geometry Research & Policy Candidates · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | Nine new modules in `fmis.swing_lab` (`geometry`, `geometry_variants`, `geometry_replay`, `geometry_outcome`, `geometry_diagnosis`, `geometry_verdict`, `geometry_study`, `geometry_render`, `geometry_artifact`), the command **`fmits research geometry`**, and a read-only **`/geometry`** dashboard page |
| **What it answered** | *Why does the swing strategy produce poor payoff geometry, and can a small set of explicit geometry policies fix it?* **Thirteen pre-declared geometries, all REJECTED**, under both cost scenarios. **No candidate deserves forward testing** |
| **The finding** | **"Minimum 2R" is backwards.** An R:R floor makes development worse (−0.276R → −0.605R; win rate 45.5 % → 6.5 %), because a high planned R:R is produced by a **tight stop**, not a distant target — rank correlation −0.65 with stop/ATR on both samples independently. Setups planning ≥ 3R carry a median stop of **0.22 ATR** |
| **The diagnosis** | 240 trades reconstructed. 52.9 % plan reward < risk · 85.7 % of target exits pay under +1R · 48.2 % of stops sit inside one ATR(14) · 68.8 % give back a full R of open profit · **73.2 % of stop-outs had their target reached afterwards** · 63.5 % resolve in a single 4H bar |
| **Costs** | Decisive, not marginal. At 10 bp/side the mean drag is **0.723R per trade** (development expectancy −0.276R → −0.999R). Cost in R is `fee_rate × (entry + exit) / risk`, so it scales inversely with the stop: **0.132R** at the median 152 bp stop, **14.0R** at the tightest 1.43 bp stop |
| **The holdout** | Nine symbols this repository had **never measured**, over the identical window, cut from one capture so both samples see byte-identical facts. Read limitation **BX-4** before quoting its figures: the *baseline itself* is +0.055R there against −0.276R on development, so the gap is a symbol-class effect, not a geometry effect |
| **Reuse, not duplication** | No second backtester, no second simulator, no volatility engine. `evaluate_setup`, `ordered_levels`, `simulate_trade`, `PaperCostPolicy`, `OpportunityTracker`, BC's replay transport and the existing ATR(14) feature are all **called**. The BW replay loop was **extracted and shared** rather than copied |
| **Production seam** | `_nearest` promoted to public `ordered_levels`; `_STOP_SIDE`/`_TARGET_SIDE` to `STOP_SIDE`/`TARGET_SIDE` (private aliases retained). Proved faithful by a 16,000-case differential **and** by BW's primary digest `b2ffcdce…` reproducing exactly |
| **No-lookahead** | Structural first — `GeometryCandidate` holds no bar and no outcome, so a policy *cannot* read forward; plans are byte-identical with the bar array discarded entirely. Then by mutation, with a warm-up control that must change, plus **absolute** index assertions a shifted-index mutation cannot cancel out of |
| **Defect found in shipped code** | **`fmits research swing` crashed on every invocation** — `DEFAULT_BACKTEST_LIMIT` referenced but never imported in `cli.py`; no test covered `_run_research`. Fixed, with a regression. BW's figures are unaffected (produced via the Python API) |
| **Verification** | 219 focused tests; full suite **11,285** under `-W error`; 91–99 % statement and branch coverage of the new modules (not 100 %, misses named); **45/45** mutation probes killed; 13 new architecture guards; **0 guards weakened** (one widened with its reason recorded; two dashboard guards fired and were *obeyed*) |
| **Release gate** | Independently re-verified. Production `evaluate_setup` unchanged over **2,352,000** input combinations against the committed HEAD copy; BW's digest and **both** BX digests reproduced exactly from fresh fetches; the six headline diagnosis figures recomputed without the diagnosis layer; six trades reconciled against raw provider candles; 24 hostile probes, 0 failures. **Five defects found and fixed** — the largest being that the claimed CLI regression **did not exist**; a static name-resolution guard now covers every CLI runner and is proven to catch the original defect. No trading rule and no result changed |
| **Not done** | Exit management (partial at +1R, break-even, trailing) is classified **NOT MEASURABLE** with current fill semantics rather than estimated — a third level on one bar multiplies the ambiguous cases. `swing_1d4h1h_roles` remains unmeasured from BW |
| **Evidence** | `src/fmis/swing_lab/geometry*.py`, `fmits research geometry --help`, `/geometry`, [report 0034](reports/0034_2026-08-25_SWING_TRADE_GEOMETRY_RESEARCH.md) |

### `BW` — Swing Strategy Laboratory & Historical Replay · **DONE** *(not committed, not pushed)*

| Field | Value |
|---|---|
| **What shipped** | One new application-layer package, `fmis.swing_lab` (11 modules), one command **`fmits research swing`**, and a read-only **`/lab`** dashboard page. A reproducible historical laboratory that replays the production swing policy and four pre-specified alternatives over the *same* facts at the same instants |
| **What it answered** | *Is the 1W gate too restrictive for swing trading?* **No.** The gate blocks 54.7 % of judged instants but only 14.6 % materially, and the 74 trades it removed were themselves losers (−0.270R). The strategy is loss-making with the gate (−0.535R) and without it (−0.335R), on a holdout too (−0.239R / −0.260R) |
| **The real finding** | **Trade geometry.** Average winner +0.301R, average loser −0.978R; break-even at a 34.6 % win rate needs +1.848R. 48 % of setups plan a reward smaller than their risk; 94 % of target-exits return under +1R. The stop is the nearest 4H level and the target the nearest 1D level, and nothing requires reward > risk |
| **Reuse, not duplication** | No second backtester. BC's replay transport, derived warm-up, window boundaries and `OpportunityTracker` are called; so are `fmis.paper.fills.fill_at_level` (the gap rule) and `fmis.trade_lifecycle.PaperCostPolicy`. A guard asserts the package defines no fill rule of its own |
| **Production seam** | One research-only keyword on `evaluate_setup`, `research_context_role`, taking a `ContextRoleTreatment` — three discrete named semantics, never a threshold. Omitted it changes nothing; every BC-era research `policy_id` is byte-identical |
| **No-lookahead** | Proved by mutating the future: post-window candles scaled ×1000 change no observation, while a warm-up mutation *does* — the control that stops the proof being vacuous. The explicit hard-gate control reproduced production on all 33,264 observations and 59 trades |
| **Verification** | 273 focused tests; full suite **10,969** under `-W error`; 95 % statement and branch coverage (not 100 %); **35/35** mutation probes killed with SHA-256-verified byte-exact restoration; 0 import cycles; 0 export collisions (four found and fixed); 0 ADRs; **0 guards weakened** (seven widened, each with its reason recorded) |
| **Not done** | `swing_1d4h1h_roles` (1D context / 4H setup / 1H execution) is specified and implemented but **not measured** — it needs ~4× the instants. It is the first thing a follow-up should run |
| **Evidence** | `src/fmis/swing_lab/`, `fmits research --help`, `/lab`, [report 0033](reports/0033_2026-08-25_SWING_STRATEGY_LABORATORY_IMPLEMENTATION.md) |

### `BV` — FMITS Operator Dashboard V0 · **DONE** *(committed and pushed)*

| Field | Value |
|---|---|
| **What shipped** | One new application-layer package, `fmis.operator_dashboard` (7 modules, 4,323 lines), and one new command, **`fmits dashboard`**: a local, read-only web surface over seven routes — Overview, Markets, Swing (+ per-symbol detail), Portfolio, Paper, Performance, System. The first *visual* surface FMITS has ever had |
| **UI technology** | Standard-library `http.server` with server-rendered HTML. **Zero new dependencies.** Streamlit was rejected because `pandas`/`numpy` are on this repository's existing forbidden list; FastAPI and Flask because they are named in it directly; React/Next because a Node toolchain and a build step for seven static routes is not a V0 |
| **The seam** | `models.py` is the entire presentation contract — `OperatorDashboardSnapshot` over seven `DashboardSection[T]` envelopes, each carrying `as_of`, `source`, `status` and an unavailability reason. `render.py` + `theme.py` are replaceable in full without touching it; guards assert the contract layer imports no presentation module, holds no markup and holds no colour literal |
| **Computes nothing** | Every figure was produced by an engine and carried across unchanged. Guards assert the package holds no indicator vocabulary, performs no `sum`/`sorted`/`min`/`max`, contains no arithmetic on an engine value outside the equity chart's pixel scaling, and never sorts. Ordering is `BS`'s, inherited index-for-index |
| **One refresh, seven pages** | `REFRESH_READS` names exactly four engine reads — `run_swing_workspace`, `run_market_pulse`, `run_macro_context`, `report_for_store` — and a test asserts the count. Measured live: 45.45 s for the refresh, then 0.00 s for each of six subsequent pages. Concurrent refreshes collapse under a lock |
| **Read-only** | `GET`/`HEAD` only; `POST`/`PUT`/`PATCH`/`DELETE`/`OPTIONS` all `405`. Binds `127.0.0.1` and refuses any other address without `allow_public=True`. No form, button, input or script on any page. No store write verb, no execution verb and no `open()` anywhere in the package. Live proof: the owner's store did not exist before browsing and **still did not exist after** |
| **Record kinds / repositories / write paths** | **0 added** |
| **Verification** | 847 focused tests; 9,824 → **10,671** passing under `-W error`; **100 % statement and branch coverage** of all 7 new modules; **34/34 semantic mutation probes killed** with byte-exact in-memory restoration; 0 import cycles across 297 modules; 0 export collisions; clean-environment install verified (`fmis==0.0.1`, nothing else); 0 new dependencies; 0 ADRs; 0 guards weakened (six roster widenings for an additive command, each with its reason recorded) |
| **Live demonstration** | Real data, 2026-08-24: six crypto markets from Binance; SPX, USDBROAD, US2Y, US10Y and VIX from FRED with yields in basis points; DXY and XAU shown as unsupported with their full reasons; 20 symbols scanned with 20 waiting; per-source data health with no composite score; 19/19 content checks; every mutating method refused; every traversal route `404` |
| **Defects found by attacking the surface** | Five, all misleading pages rather than crashes: crypto rows showing three false *unavailable* cells for windows never measured; DXY and XAU vanishing entirely; one 60-word reason printed six times per row; healthy sources rendering as *"unavailable: no detail was stated"*; and the paper/portfolio separation notes disappearing when empty. All fixed and guarded |
| **Screenshot** | Not captured — the browser-automation extension is not connected and the repository holds no screenshot tooling. No dependency was added for one; a text rendering of the live Overview is in report 0032 §15 |

### `BS` — Swing Decision Workspace v1 · **DONE** *(committed and pushed)*

| Field | Value |
|---|---|
| **What shipped** | One new application-layer package, `fmis.swing_workspace` (5 modules), and one new command, **`fmits workspace`**: global market summary, top opportunities, wait list, no trade, active paper trades, portfolio summary, statistics snapshot, warnings — with the actionable setups **ordered**, which no FMITS surface had ever done |
| **The ordering** | A lexicographic key over four components, compared left to right and **printed on every row it places**: readiness (`SetupState`) → approval (`ApprovalStatus`) → sufficiency (`ContextState`) → watchlist position. Each is an ordinal over a written-out vocabulary; `ranking.py` holds no division, no multiplication and no float literal at all. Nine quantities are named as excluded and printed under the rule, **risk/reward first**, because this repository measured higher displayed R:R with a *worse* outcome |
| **Reuse, not duplication** | The composition root calls `fmis.today.assemble_today` — the exact sequence `fmits today` runs — so the page costs **one** scan, **one** store read, **one** valuation and **one** approval pass. Three tests assert *object identity* between this page's market, portfolio and statistics sections and the day's page's own |
| **New in `fmis.today`** | `TodayRun` and `assemble_today`, a seam rather than a rewrite: `run_today` is one delegation over it, keeps its exact signature and result, and is asserted byte-identical |
| **Record kinds / repositories / write paths** | **0 added.** A guard asserts no store write verb appears in the package, and a live run leaves the store byte-identical |
| **Verification** | 251 focused tests; 8,703 → **8,954** passing under `-W error`; **100 % statement and branch coverage** of all 5 new modules *and* the modified `fmis/today/builder.py`; **two independent mutation harnesses, 45/45 and 45/45, 0 survivors**; an independent release gate on 2026-08-21 that found five assertion gaps and one guard hole, all fixed with regressions (report 0029 §8a); 0 new dependencies; 0 ADRs; 0 guards weakened (six extended with justification, four *not* widened) |
| **Live demonstration** | Five symbols against Binance: a real CONFIRMED LONG, a real CANDIDATE SHORT with its awaiting condition, two no-trade groups, a pending paper trade with every excursion absent-with-reason, byte-identical store before and after, byte-identical pages from two processes |
| **Defects found by attacking the surface** | `fmits workspace BTCUSDT BTCUSDT` lost the whole page to a duplicate guard; and a row printed `paper: none` beside a real open position. Both fixed |
| **Commits** | `b6a456c` (production code + tests) on top of `cc4e748`, with the product-docs commit recorded directly on top of it |
| **Record** | [report 0029](reports/0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md) |

### `BG-D1c` — Setup Identity Surface Integration · **DONE**

| Field | Value |
|---|---|
| **Commit** | `a4191f2` — production code and tests, with this product-docs commit directly on top of it |
| **Delivered** | **The first user-visible capability of the BG-D1 line.** `fmits setup SYMBOL` closes its page with the setup's stable identity — the line the owner compares between runs to tell *"the same idea, still there"* from *"a new idea"*. Before this, a setup that persisted for a week read as seven unrelated setups |
| **Shape** | One new module (`fmis.setup_observation.render`), three lines in `_run_setup`, one helper and one named constant in `cli.py`. **0 record kinds (15 → 15), 0 repositories, 0 domain types, 0 new dependencies, `fmis.swing_setup` untouched** |
| **The existing page** | **Byte-identical**, asserted: the test compares the whole of stdout against `render_setup(assessment)` plus the appended block, so no field can be altered, reordered or dropped without failing |
| **What it refuses to claim** | A repeat count. One invocation observes **one bar** — the command fetches each timeframe once, and `StructuralFactSheet` keeps a `DataWindow` rather than its candles — so `is_new_occurrence` would be `True` and the count `1` for every setup forever. A field that is always the same value dressed as a measurement is exactly the *stale or misleading* case the brief warned against. `render_identity_run` holds the counts, built and tested, for the first surface that holds a series. `swing_index` is never printed: it is window-relative and would read as identity |
| **Honest absences** | A `WAIT` reading prints *"the reading has no stop with a MEASURED level origin to anchor on"*. A symbol FMITS cannot split into base and quote prints its full analysis with **no** identity block, rather than a fabricated market under an identity heading |
| **Quality** | 31 focused tests; 8,499 → 8,530 passing under `-W error`; **100 % statement and branch coverage** of `fmis.setup_observation`; 0 lines missed in the new `cli.py` region; **21/21 mutation probes detected, zero survivors**; live-verified against real Binance data — `fmits setup DOTUSDT` printed a byte-identical block across two independent processes on a real `CONFIRMED SHORT`, and `ARBUSDT` printed a different one the same day |
| **Guards** | **One allowlist extended and stated plainly**: `test_the_cli_reaches_neither_the_domain_nor_the_store` gained `fmis.setup_observation` — the fourth application-tier prefix after `BN`, `BO` and `BP`, with the justification written into the test. The CLI still names no domain root and opens no store; both downstream assertions pass unchanged |
| **Records** | [report 0026](reports/0026_2026-08-19_SETUP_IDENTITY_SURFACE_INTEGRATION.md) |
| **Recorded, not fixed** | `render_setup`'s own content lines exceed its `_WIDTH = 70` (up to 93 when a limitation is long); that is the engine's page and this slice does not own it, but the identity block holds the stricter rule and two tests pin it. Freshness and `SetupType` remain unpopulated. `fmits scan` and `fmits today` are the natural next callers of `render_identity_run` |

### `BG-D1b` — Setup Identity Pipeline Integration · **DONE**

| Field | Value |
|---|---|
| **Commit** | `1909134` — production code and tests, with its product-docs commit directly on top of it |
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
