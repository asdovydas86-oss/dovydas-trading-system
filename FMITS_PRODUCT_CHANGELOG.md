# FMITS Product Changelog

**What FMITS can actually do, and when it could first do it.**

This is a **product** changelog, not a Git changelog. It does not list commits, refactors, test
additions, documentation, or architecture work. It records only changes to what the owner can do.

| Field | Value |
|---|---|
| **Last verified against** | Milestone BO's production commit `e4195fc`, on top of `51814b1`, with this product-docs commit recorded directly on top of it. Milestone BN's own entry was verified against its product-docs commit on top of `b66a88f`, committed and pushed. Milestones `BJ`–`BM`, recorded here as pending commit, are in fact in `origin/main` at `4519d0a`; those entries are point-in-time records and are not revised |
| **Verified on** | 2026-08-16 |
| **Verification method** | live repository + `git log` + full test run + accepted ADRs |

---

## 1. Purpose and rules

**Purpose.** Answer, at any point in the project's life: *what could the owner do, and from when?*

An entry is recorded **only** if the change does one of these:

- adds a **user-visible capability**;
- **materially improves the reliability** of a user-visible capability;
- **removes a blocker** to practical use;
- **materially reduces financial or operational risk**.

Everything else — however large, however well engineered — belongs in the Git history, the ADRs, and
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md), not here.

**Foundational entries are permitted but must be labelled.** Some milestones deliver no user
capability yet are load-bearing for one that follows. They appear here marked **Foundational** so the
history is honest, and are never described as product releases.

---

## 2. Product versioning policy

> ### ⚠ RECOMMENDATION — NOT AN APPROVED SCHEME
>
> **No product versioning scheme has been approved for FMITS, and no product version number has been
> assigned to any milestone.** The section below proposes one. Until the owner approves it, entries
> in this changelog are identified by **milestone letter and commit SHA only**.

**Proposed pre-v1 scheme.**

```
0.MINOR.PATCH        while the system is pre-v1
```

- **MINOR** increments when a new user-visible capability ships.
- **PATCH** increments when an existing capability becomes materially more reliable, or a blocker to
  its practical use is removed.
- **Foundational milestones do not increment anything** — they change no capability.
- **1.0.0 is reserved** for the definition already recorded in
  [`reports/0004`](reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §4:
  *the first version genuinely useful in daily work without the TradingView prompt doing the
  analysis* — a daily market-intelligence workflow over real data. That is milestone `AK` on the
  backlog, not a date.

**If approved retroactively**, the only assignment implied by the record below is
`0.1.0 → milestone AF`. It is **not** claimed as an established fact anywhere in this repository.

**Not to be confused with the package version.** `pyproject.toml` carries `version = "0.0.1"`. That
is a Python package version and has never tracked product capability.

---

## 3. Current product capability

**As of Milestone `BO` (Paper Trading & Trade Lifecycle Engine) — what the owner can
do today.**

```
fmits trade plan BTCUSDT --stop … --target …    # record a commitment with no fill: what you intend
fmits trade activate PLAN_ID --size … --entry … # hand it to the paper simulator
fmits simulate --all                            # advance every paper trade over newly closed candles
fmits simulate BTCUSDT ETHUSDT                  # advance the markets you name
fmits trade status                              # every paper trade still running, with its monitor
fmits trade status --offline                    # the same page, no candle fetched, every gap named
fmits trade history                             # every finished paper trade, with its frozen outcome
fmits trade lifecycle ACTIVATION_ID             # one trade's whole event stream and stop history
fmits trade stop ACTIVATION_ID --to … --reason … # move a stop; append-only, the plan is untouched
fmits trade cancel ACTIVATION_ID --reason …     # withdraw an activation before anything filled
fmits approve BTCUSDT --direction long …        # how large this may be, and whether your limits permit it
fmits approve --plan PLAN_ID --entry …          # size a commitment already recorded, without retyping it
fmits approve … --risk-fraction 0.01            # size at a stated fraction, capped by your own ceiling
fmits approve … --max-mark-age 36h              # block on data older than a bound you set
fmits portfolio                                 # what the recorded positions are worth right now
fmits portfolio --no-marks                      # the same page, no price fetched, every gap named
fmits portfolio --mark-interval 4h              # price every holding from a coarser closed candle
fmits trade record BTCUSDT …                    # record a swing trade: commitment, fill and thesis
fmits trade show   TRADE_ID                     # one recorded trade, assembled and reconciled
fmits trade list   --status open                # every recorded trade, filtered, never ranked
fmits trade note   TRADE_ID --body "…"          # append a journal entry; nothing is ever edited
fmits trade close  TRADE_ID --reason …          # append an exit and the reason for it
fmits today                                     # the daily trading workspace: one page, eight sections
fmits today BTCUSDT ETHUSDT --store-root PATH   # a chosen watchlist, against a chosen store
fmits today --no-records                        # the same page, without reading the store
fmits today --no-marks                          # read the store, fetch no price
fmits today --risk-fraction 0.01                # every actionable candidate sized and approved inline
fmits setup  BTCUSDT                            # a deterministic swing-trade setup assessment
fmits setup  BTCUSDT ETHUSDT SOLUSDT            # one per symbol, in the order requested
fmits scan                                      # the fixed 20-symbol watchlist, a readable market report
fmits scan --table                              # the same scan, as the original compact table
fmits backtest                                  # the current policy, replayed over real history
fmits daily  BTCUSDT ETHUSDT SOLUSDT            # the morning routine, one row per symbol
fmits swing  BTCUSDT                            # the whole page, end to end
fmits regime BTCUSDT --multi                    # the environment, per role, with evidence
fmits mtf    BTCUSDT -n 260                     # 1W context · 1D setup · 4H execution
fmits facts  BTCUSDT --interval 4h --limit 200  # one timeframe, exhaustively
fmits swing  BTCUSDT --archive                  # archive the page durably
fmits daily  BTCUSDT ETHUSDT --archive          # archive the whole run
fmits archive list                              # every archived record, metadata only
fmits archive show RECORD_ID                    # render a stored record, no network access
fmits archive verify RECORD_ID                  # integrity check; omit the id to verify the archive
python -m fmis.pipeline daily BTCUSDT           # works without reinstalling
```

**Delivered:**

- a **deterministic answer to "can I take this trade"**: one command computes the largest position
  whose capital at risk stays inside the fraction of equity the owner chose **and** every ceiling
  they set, then evaluates the portfolio **as it would be with that position open** — total open
  risk, instrument, asset, account and group concentration, leverage, concurrent positions and
  reserve — and returns **APPROVED**, **BLOCKED** or **INDETERMINATE** with every reason named.
  It answers *can I take this* and never *is this good*: no setup quality, confidence or probability
  reaches the arithmetic, and there is no field on any type that could hold *take this trade* or
  *skip this trade* — that conclusion is the owner's. **Every threshold is one the owner set**; the
  system invents none, and where they have set none the answer is a stated absence rather than a
  guess — a 2 % ceiling is never used as a 2 % target. **A ceiling that reduced the size is always
  named beside it.** `INDETERMINATE` is never rendered, counted or reasoned about as approved.
  The same answer now appears inline against every actionable candidate on the daily workspace page.
  **Nothing is stored, nothing is ranked, no order is placed and no exchange is reached for
  execution**;
- a **valued portfolio**: one command reports what the recorded positions are worth right now —
  market value, cost basis, unrealized profit and loss, gross/net/long/short exposure, and equity
  where cash has been observed — with **every figure traceable to a specific closed candle on a
  stated timeframe**, and the price source, the selection rule and the age of every mark printed
  beside it. A price is always the close of the **last closed candle**; a forming bar is never read,
  so the same history always yields the same figure. A market with no price leaves its position
  **listed and unmarked**, and every total that depended on it says *unavailable* with the market
  that broke it named — never a smaller number that looks complete. A perpetual is never priced from
  its spot pair, a price from after the instant being valued is refused, and a holding quoted in
  another currency is reported unvalued rather than converted. **Nothing is stored**: a frozen
  portfolio observation needs deposits and withdrawals this build records nowhere, so a valuation is
  a reading that is recomputed rather than a record that could go stale. The same figures now appear
  in `fmits today`'s capital section, which previously said no mark source existed. **Reads the
  durable store and never writes to it; contacts no exchange for anything but public candles, places
  no order and executes nothing**;
- a **system of record for the owner's own trades**: one command records a complete swing trade —
  the commitment (direction, stop, target ladder, stated confidence, the setup and the analysis it
  came from), the entry fill under the full tax-capture contract, and the thesis behind it — as three
  linked records in the durable store. `show` reassembles them with capital at risk and risk/reward
  shown **beside the arithmetic that produced them**, `list` filters without ranking, `note` appends
  and never edits, and `close` appends an exit with a reason from the owner's own vocabulary.
  **Everything is append-only**: nothing already recorded is edited or deleted, the initial stop
  cannot change by any code path, and re-running an identical command records nothing twice.
  **FMITS places no order, contacts no exchange and executes nothing**; the owner remains the trader;
- a **daily trading workspace**: one command assembling market overview, portfolio overview, today's
  opportunities, a priority queue, the trade journal, recent analysis and every workspace warning onto
  a single page — health, capital and existing exposure *before* opportunity, absence always rendered
  with the inference it forbids, and nothing ranked by desirability. It reads the durable store and
  never writes to it; it executes nothing, places no order, sizes no position and sends no
  notification;
- a **deterministic historical backtest harness**: `fmits backtest` replays the exact, unmodified
  swing-setup policy over real historical closed candles — no lookahead, by construction of a replay
  transport verified two independent ways — and reports what it would have produced: every
  WAIT/CANDIDATE/CONFIRMED observation, what happened after each confirmed setup (target-first /
  stop-first / same-bar-ambiguous / unresolved-within-window), reconciled counts, and every limitation
  on the page itself. **Not a portfolio backtest** — no fees, no slippage, no realized PnL, no position
  sizing — and not a ranking or a tuning exercise: the policy is measured exactly as it stands;
- a **deterministic swing-trade setup assessment**: `WAIT` / `CANDIDATE` / `CONFIRMED`, with a
  direction only when a candidate exists, the independent evidence families behind it, confirmation,
  invalidation, stop, target(s) and risk/reward when computable, and every limitation that applies.
  Direction never comes from one indicator — at least two of three independent families must agree
  with zero opposing — and `WAIT` is a first-class, successful result, not a failure;
- a **fixed-watchlist market scanner**: one command runs the swing-setup assessment across twenty
  hardcoded major pairs. By default it prints a **readable market intelligence report** — a scan
  summary, which symbols are showing directional character, every `CONFIRMED`/`CANDIDATE` setup with
  its risk/reward, target, stop and the exact reasons the engine already computed, and every `WAIT`
  result grouped by why; `--table` prints the original compact one-row-per-symbol table. A symbol whose
  analysis fails is reported as `ERROR` and does not stop the scan. **Not a ranking**: symbols stay in
  the fixed list order in every section, and no score, probability or recommendation is computed;
- a **repeatable multi-symbol routine**: one command runs the same analysis over a requested universe
  under one set of settings, and prints one row per symbol in the order requested — with the symbols
  that **failed, and why**, kept on the page. **Not a ranking**: no score, no order by any property of
  the analysis, no direction;
- a **statement of whether the analysis can be trusted**: five named requirements, each delegating
  its rule to the layer that declared it, reported as sufficient, limited or insufficient with the
  unmet ones named;
- a **single-page swing workspace**: instrument and data quality, regime per role, structure per
  role, levels, evidence by family and the **disagreements between them** — with risk, portfolio,
  trade plan and AI interpretation shown as explicitly unavailable, each naming what its absence
  forbids;
- a **deterministic market-regime classification**: three environments — structure, volatility and
  participation — each with the evidence for it, the evidence against it, what was unavailable, and the
  exact policy that produced it. **Not a direction**, and no overall label or score;
- a **multi-timeframe deterministic fact sheet**: three role-labelled views of one instrument, each
  with its own `as_of` and staleness, structural trends side by side, **nothing derived from their
  combination**;
- a **single-timeframe deterministic structural fact sheet** for one instrument;
- a **CLI entry point** — the only product surface that exists;
- **real market-data input** from a live exchange endpoint;
- **calculated facts**: EMA, RSI, MACD, ATR, relative volume, swing points, structural labels,
  structural trend, price levels, level crossings, break of structure, change of character, nearest
  level above and below the last close;
- **warm-up status** stated per feature, so "not computed yet" never looks like a value;
- **inherited limitations printed on every sheet**, each citing the ADR that owns it — now **six**,
  since `ADR-0020 D1` was fixed and removed rather than left standing;
- **durable memory**: `--archive` on `swing`/`daily` records the complete page to a versioned,
  integrity-checked record; `archive list`/`show`/`verify` read it back exactly, with no network
  access and no recomputation. Snapshot reproduction only — not historical replay.

**Explicitly not delivered:**

| Not available | Where it is on the backlog |
|---|---|
| AI interpretation of any kind — the numbers are computed, not read | EP — after regime |
| ~~Trade signal, direction~~ | **Direction delivered by `AR`, scoped narrowly** — `fmits setup` states a `WAIT`/`CANDIDATE`/`CONFIRMED` direction under an explicit, testable policy; still no ranking, score, or recommendation |
| Opportunity ranking or score across symbols | `EP-02`/`EP-03` — deliberately absent from `fmits setup`'s and `fmits scan`'s multi-symbol modes: sequential, input order preserved, no sort |
| Cross-timeframe **synthesis** — the views are reported, never reconciled | `AI` Market Regime Engine |
| ~~Market regime classification~~ | **Delivered by `AI`** — see below |
| Support/resistance naming — levels are reported as *nearest above / below* | `EP-01` |
| Portfolio or risk context, position sizing | `EP-04`, blocked on **D-02** |
| ~~Persistence — a run is printed, never stored~~ | **Delivered by `AO`** — see above |
| Historical replay — recomputing a past analysis from its original raw inputs | not archived yet; snapshot reproduction only |
| A journal, discretionary notes, trade outcomes | `EP-18`, blocked on **D-04** |
| ~~Opportunity scanning~~ over a fixed watchlist, ranked | **Scanning over a fixed watchlist delivered by `AT`, presented as a readable report by `AU`**, unranked in both, exactly as designed — `fmits scan` returns every symbol's existing setup, never a score or order. **Ranking** remains `EP-02`/`EP-03` — a **named future capability** (SPEC §10 and the Opportunity Scanner; vision addendum; `reports/0005` C-164) that must arrive as its own explicit, deterministic, testable, backtested policy, per `AN`'s own warning against ranking as a side effect of a workflow |
| Ranking *by readiness* — sorting the daily index by its own states | **never**, in any version. Readiness describes the analysis, not the instrument; see AN's design §3.4 |
| Alerts, scheduling, unattended runs, notification delivery | `EP-03` — scheduling still owns no architecture layer |
| Watchlist persistence as its own model — a universe is typed, or supplied by the shell | `EP-03`, **D-06** — unrelated to D-01; `AO` archives whatever universe it is given |
| Any asset class other than crypto | `EP-05` |
| ~~Historical backtest of setup outcomes~~ | **Delivered by `AV`** — see above. A realized-PnL portfolio backtest, paper trading, shadow mode and execution remain `EP-14` … `EP-17` |

**Safety position.** The system executes nothing and holds no credentials that could move funds.
`AR` is the first and only capability that makes a directional claim (`fmits setup`), confined to one
package by construction (ADR-0028) and never a position size, leverage or money amount. Every rung of
the automation ladder remains unstarted.

---

## 4. Product milestones

### 2026-08-16 · `BO` — Paper Trading & Trade Lifecycle Engine

**Status:** Released — `e4195fc` (production code + tests), with the product-docs commit recorded
directly on top of it.

**What the owner can do that was impossible before: watch a trade live its whole life.**

Before `BO`, FMITS could find a setup, size it, approve it and record a fill the owner had already
taken. It could not tell them what happened next. Now it can:

```
fmits trade plan BTCUSDT --direction long --book paper --stop 62200 \
      --target 63300 --target 64200 --confidence moderate --thesis "…"
fmits trade activate <PLAN> --size 0.4 --entry-type limit --entry 62800 \
      --share 0.5 --share 0.5 --break-even-r 1 --trail-r 2
fmits simulate --all
fmits trade status
```

The entry waits at 62800 until a closed candle comes back to it. Half the position leaves at the
first target and half at the second. The stop moves to break-even once the trade is 1 R in front and
trails 2 R behind the best price it has seen. Every one of those is recorded as an event the owner
can read back, and **nothing is ever edited**: the commitment's original stop is still the original
stop, and the stop that is in force is the fold of every move made since.

`fmits trade status` answers the question the owner actually has: how much is open, at what entry,
how far from the stop, how far from the next target, how much risk is committed, what the trade has
made and lost in R, how far it ran in each direction, how long it has been on, and how many times
the stop was moved away from the commitment.

**It is paper only, and it says so on every page.** No exchange is reached, no order is placed, no
credential exists. A paper fill is what this system computes would have happened, at zero modelled
cost, and it is excluded from every real-money figure.

**Two things it refuses to do.** When a single candle reaches both the stop and a target, it does
not guess which came first — it **halts the trade and says so**, and the owner records the exit they
judge they would have taken. And it invents no price: a level fills at the level, or at the bar's
open when the bar gapped through it, and the same rule applies whether the gap helped or hurt.

**Re-running changes nothing.** `fmits simulate` replays each trade from the beginning every time
and writes only what is new — verified on a live store by comparing every byte before and after.

Full record: [report 0022](reports/0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md) ·
[design](docs/design/PAPER_TRADING_AND_TRADE_LIFECYCLE_V1.md).


Reverse-chronological. Every **Released** entry cites a commit verified to exist in this repository.
An entry whose milestone is implemented and validated but not yet versioned is marked
**Implemented — pending commit** and carries no SHA, per rule 4.

---

### 2026-08-15 · `BN` — Position Sizing & Trade Approval Engine

**Status:** Released — `b66a88f` (production code + tests), with the product-docs commit recorded
directly on top of it. **A new
user-visible capability**, and the first one that answers a question about the *owner's* capacity
rather than about the market.

**What the owner can do that they could not before.**

```
fmits approve BTCUSDT --direction long --entry 60000 --stop 58400 --target 64000
```

**How large may this position be, and do my own limits permit it.** Every milestone before this one
answered *"is there a setup here"* or *"what do I hold"*. This is the question that actually stands
between an idea and an order, and until now the owner answered it by hand, from memory, with a
balance retyped from an exchange screen.

**It answers *can I take this*, never *is this good*.** The setup engine already produced a
judgement about the idea and nothing here reads it: no confidence, no probability, no readiness state
and no risk/reward threshold of this system's own invention reaches the arithmetic. There is no field
on any type that could hold *take this trade* or *skip this trade*. `EXCEEDED` on the open-risk
budget is a fact; what to do about it is the owner's conclusion.

**Three answers, and the third is not a milder first.** `APPROVED` — every limit was measured and
none is breached by a position of this size. `BLOCKED` — a hard limit is breached, or no size could
be produced at all. `INDETERMINATE` — something could not be measured, which is *not* a quiet
approval and is never rendered, counted or reasoned about as one.

**Every threshold is one the owner set.** The fraction of equity, the per-trade ceiling, the
open-risk budget, the concentration caps, the staleness bounds, the minimum risk/reward and the
severity attached to each limit are all theirs. Where they have set none, the answer is a stated
absence naming what to configure — never a number this system chose. **A 2 % ceiling is a ceiling and
is never used as a target**: with no fraction stated and no default set below the ceiling, no size is
produced and the page says why.

**A ceiling that reduced the size is always named beside it.** A stated 10 % comes back as the
owner's own 2 %, with the limit that reduced it printed. A spent open-risk budget refuses any size
that increases open risk, and says so in those words — total portfolio risk outranks any single
candidate's quality.

**It reports the axes it was *not* asked to check.** A page showing every configured limit as
*within* reads as a portfolio checked on every axis; it was checked on the axes the owner wrote down.
So each unconstrained one — this candidate's instrument, its base asset, its account, its groups, the
total open-risk budget — is named, because an unchecked axis is not an axis that was found
acceptable.

**A recorded commitment is sized without retyping it.** `--plan PLAN_ID` reads the market, the book,
the side, the stop and the target ladder from a trade already recorded with `fmits trade record`, and
refuses to let any of them be restated — the stop is the field that record exists to keep immutable.

**`fmits today` now carries an approval on every actionable candidate**: the status, the recommended
size, the resulting open risk, the blocking reasons and the warnings. A candidate with no approval
prints a stated absence rather than a blank, and the page says which of the four possible missing
inputs — the store, the price source, a risk budget, an account — is the reason.

**A blocked answer exits 0.** The evaluation succeeded and its answer was no, which is a first-class
successful outcome in this product exactly as `WAIT` is. A non-zero exit means the evaluation could
not be produced at all.

**What it deliberately does not do.** It never executes: no order is placed, no exchange is reached
for anything but public candles, and no capital is reserved. It stores nothing. It measures no
correlation — duplicated exposure is reported because it is a fact, and whether two markets move
together is an inference this system has no data for. It ranks nothing and calibrates no probability.

Full record: [report 0021](reports/0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md).

---

### 2026-08-14 · `BM` — Market Snapshot & Price Integration

**Status:** Implemented — pending commit. **A new user-visible capability**, and it is also the
milestone that turns `BL` from a correct-but-silent engine into the number the owner reads.

**What the owner can do that they could not before.**

```
fmits portfolio
```

What the recorded positions are worth right now: market value, cost basis, unrealized profit and
loss, gross / net / long / short exposure, and equity where cash has been observed. Every figure is
traceable — the page prints the price source, the timeframe, the selection rule and the age of every
mark beside the figure it produced.

**One price rule, stated and never varied.** A price is the close of the **last closed candle** on a
stated interval (`1h` by default). A forming bar is never read, so two runs over the same history
produce the same valuation forever, and a portfolio's value never moves because nothing traded.

**A missing price is a sentence, never a zero.** A market that could not be priced leaves its
position **listed and unmarked**, and every total that depended on it reports *unavailable* naming
the market that broke it. `AP` §14.3's warning is the whole discipline: *"a zero makes the total
look plausible and survives for years."* One unreachable symbol never costs the page the prices it
already had, and never quietly shrinks a total.

**Three refusals, each visible on the page.** A **perpetual** is never priced from its spot pair —
they share a symbol and are two instruments with two prices. A price from **after** the instant being
valued is refused, with both dates named, rather than used. A holding quoted in a currency other than
the base is reported **unvalued** rather than converted, because this system holds no exchange rate.

**`fmits today` now prints money where it printed an absence.** Its capital section previously said
*"open risk needs a mark for every holding… no mark source exists."* Market value, unrealized P&L
and exposure are now figures. **Open risk is still absent**, and the page says why: it needs a
recorded stop, and a `TradePlan` is what states one. `--no-marks` keeps the store and skips only the
prices.

**Nothing is stored, deliberately.** A frozen portfolio observation requires deposits and withdrawals
since the previous one — without them a deposit looks like a gain and every return figure is wrong
— and this build records no transfer event. A valuation is therefore recomputed on demand rather
than becoming a record that could go stale. Printed on every page as limitation `VA-1`.

**FMITS still contacts no exchange for anything but public candles, places no order, sizes no
position and executes nothing.** The store is read and never written.

**Records:** [report 0020](reports/0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md)

---

### 2026-08-14 · `BL` — Portfolio Intelligence & Risk Engine

**Status:** Implemented — pending commit. **Foundational — not directly user-visible.** No command
was added and none changed, deliberately: the milestone was scoped to the deterministic backend and
explicitly forbidden from becoming a dashboard. **This is not a product release**, and it is recorded
here because it is load-bearing for the one that follows.

**What shipped.** `fmis.portfolio_risk` — the boundary `TRADING_DOMAIN_ARCHITECTURE_V1` §15 specified
and nothing had built. The system stops evaluating trades one at a time and can answer, as a library
call:

> What changes in the portfolio if the owner opens this proposed trade now?

It answers with **two portfolio states and the differences between them** — exposure on eight axes,
capital at risk per position and in total, each of the owner's own limits evaluated as `WITHIN`,
`AT_LIMIT`, `EXCEEDED` or `INDETERMINATE(reason)`, duplicate and scale-in detection, and the
classification groups the owner defines. **It returns no verdict, no score and no recommendation**, and
there is no field on any type it exports that could hold one.

**Why this is not yet a capability.** Open risk, duplicate detection and the constraint engine work
today against real recorded trades. **Gross exposure, net exposure, leverage and every concentration
share are `Absent`** — with a stated reason naming the market — because no price source reaches the
owner half of FMITS. The engine is correct and mostly silent, and it becomes the daily number the
owner reads on the day a mark source lands.

**What it changes about risk.** The 2 % rule is enforced as a **ceiling**: reaching it exactly is a
binding constraint rather than room left, and a limit stated with a lower default never has that
default promoted to the comparison value. A limit that cannot be measured is reported in its own list
and is never counted as within.

**Venue-agnostic, and proved rather than claimed.** Portfolio and risk logic operates only on domain
abstractions — account, venue, instrument, position, plan, budget, money. Five executable guards fail
the build if any module imports an exchange provider, imports a market-half engine, or names a venue
anywhere in its executable code. Binance, EVEDEX, a future DEX and a hand-kept account all reach the
same arithmetic.

**Risk-relevant defects found and fixed before release** ([report 0019](reports/0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md)):
two BTC positions quoted in different currencies read as unrelated symbols — correlated exposure
presented as diversification; a stale valuation was indistinguishable from a current one, so a
percent-of-equity limit could be measured against a months-old equity; and one limit stated in the
wrong currency took down the entire risk evaluation rather than producing one indeterminate result.

**Records:** [report 0018](reports/0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md)
· [report 0019](reports/0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md)

---

### 2026-08-13 · `BK` — Trade Capture & Decision Recording

**Status:** Implemented — pending commit. **A new user-visible capability.** It is the first
milestone in which FMITS **writes** to the durable store: `BI` built nine repositories that no
command reached, `BJ` read them and wrote nothing, and this one closes that loop for the workflow the
product exists for.

**What shipped.** `fmits trade` — five subcommands over the owner's own trades:

```
fmits trade record BTCUSDT --direction long --account binance_spot --book swing \
      --entry 60000 --stop 58400 --target 64000 --target 68000 --size 0.5 \
      --fee 15 --fx-rate 10.5 --fx-source riksbank --confidence moderate \
      --setup trend_continuation --thesis "weekly context up; the 4H retest held"
fmits trade show  TRADE_ID                      # commitment, fills, position, journal, warnings
fmits trade list  --status open --symbol BTCUSDT --since ISO8601
fmits trade note  TRADE_ID --body "…" --title "…"
fmits trade close TRADE_ID --price 63800 --fee 16 --reason target_reached --fx-rate 10.6 …
```

**A swing trade is recorded as three linked records, not one.** A `TradePlan` holds what the owner
committed to — the stop, the target ladder, the stated confidence, the originating setup, proposal,
market snapshot and archived analysis pages. A `Trade` holds each fill, under the full tax-capture
contract from the first record. A `JournalEntry` holds the owner's own words. They stay three because
they are three kinds of fact with three truth conditions — intent, money and opinion — and a single
row would make *"did I honour my stop?"* unanswerable the first time a stop moved.

**The initial stop cannot change, by construction rather than by rule.** There is no code path that
edits it and a test pins the four callables the record exposes, so adding one fails there rather than
three milestones after someone found it convenient.

**Capital at risk is shown and never stored.** It is `|entry − stop| × quantity`, printed beside the
subtraction and the multiplication that produced it, exactly as the risk/reward pair is printed
beside its division and the average entry beside its own. `AP` §5.3's rule — *no quotient is ever a
stored field* — applied to the one figure a trader most wants to see.

**Everything is append-only and nothing is silently corrected.** Re-running an identical command
records nothing twice and says so. Closing appends an exit fill; the entry, the commitment and every
note stay byte-identical. A refusal names the two values that disagree, exits non-zero and **writes
nothing at all** — a stop on the wrong side of the entry, a target the trade would reach by going
wrong, a size in the quote asset, a third-asset fee with no rate of its own, a numeric confidence
label, a naive timestamp, a close larger than the position, an exit with no reason.

**Eight warnings and five standing limitations print on every page**, including the one the journal
package calls the cheapest discipline metric in the system: *nothing has been written about this
trade*.

**What it still does not do**, and says so on the page: it places no order, contacts no exchange and
confirms nothing against a venue; it computes no position size from a risk allowance; it calibrates no
probability; realized profit and loss is the fold's figure for review and is **not** a taxable gain;
and the figures on a trade's page fold that commitment's own fills, which may differ from the
book-wide position in the same market.

**Quality.** 5,876 → **6,311 tests** (+435), passing under `-W error` with zero warnings. **100 %
statement coverage** of the nine new modules (962 statements). **30 mutation probes, 30 detected, 0
survivors.** 0 new runtime dependencies, 0 export collisions (697 → 764 public names), 0 import
cycles, 5 existing production files modified, all additively, and **0 domain types changed**.

**One design finding is recorded in full** in
[report 0017](reports/0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md) §2:
eight of the fourteen fields this command captures had no home in the domain, because `TradePlan` —
designed since Milestone `AP`, named as accepted debt by the MVP blueprint — had never been built.
It was built here, to the card the data model already wrote. `PlanAmendment`, the other half of that
debt and the thing that makes a *widened* stop visible, is still outstanding and is the next item.

---

### 2026-08-12 · `BJ` — Daily Trading Workspace MVP

**Status:** Implemented — pending commit. **A new user-visible capability**, and the first since `AV`
that changes what the owner can do. `BH` (Trade Domain Foundation) and `BI` (Trade Repository &
Journal Engine) are deliberately absent from this changelog: both were foundational, neither added a
command, and recording them here would have been the failure rule 1 exists to prevent. `BJ` is the
milestone that gives their work a surface.

**What shipped.** `fmits today` — one command that assembles a complete swing-trading cockpit from
components that already existed:

```
fmits today                                  # the fixed watchlist, plus everything on record
fmits today BTCUSDT ETHUSDT SOLUSDT          # a watchlist chosen at the command line
fmits today --store-root PATH                # read a specific durable store (read-only, always)
fmits today --no-records                     # skip the store; the page says that it did not look
fmits today --reference-time ISO8601         # pin the page, so two runs are byte-identical
```

Seven sections in a fixed order: **market overview** (what the scan concluded, and how many symbols
the engine could not read as distinct from how many it read and declined) · **portfolio overview**
(open positions folded from the ledger, the risk budget in force and its configured limits) ·
**today's opportunities** (`CONFIRMED` / `CANDIDATE` / `WAIT` / `ERROR`, grouped) · **priority
queue** (what deserves attention, and separately what this system refuses to produce a number for) ·
**trade journal** (recent entries, live proposals, recently closed positions) · **recent analysis**
(archived pages, citations and market snapshots, metadata only) · **workspace warnings**.

**Health, capital and existing exposure appear before opportunity**, deliberately. The
highest-probability way this product loses real money is not a bad signal — it is a position taken
while the owner is already committed, or three simultaneous same-direction setups on three correlated
majors.

**It reads the durable store and never writes to it.** Asserted by an AST guard over the whole
package (no `create`, `update`, `replace`, `publish` or append verb appears anywhere in it) and
observed in a live run: the store's file listing was byte-identical before and after.

**Nothing is ranked by desirability, and the mechanism is absent rather than merely unused.** The
priority queue orders by the engine's own readiness state and then by watchlist order; a guard test
asserts the module contains no `sorted`, `.sort`, `min`, `max`, `key=` or `reverse=`, and a
behavioural test plants a `CANDIDATE` with `R:R 49.00` against a `CONFIRMED` setup with `R:R 0.4` and
asserts the order does not move.

**Every absent value prints its reason, the slice that owns producing it, and the inference its
absence forbids** — *"Do not read an absent balance as a zero balance"*, *"Do not read this as risk
being within budget. Nothing was measured."* A blank capital section reads as no exposure; this one
cannot.

**Every measured number prints with its sample and what is wrong with it.** A displayed risk/reward
above the measured p90, or at or above 5, is annotated with the direction of the association in
words — R:R in `[5, 20)` resolved target-first 7.7 % of the time against 74.5 % for R:R in `[0, 1)` —
its `n`, and the note that the sample it came from was later proved to cover 41–43 usable days with a
setup identity that changed every bar.

**What it still does not do**, and says so on every page: no position size, portfolio risk or leverage
is computed; no probability is calibrated; no correlation between markets is measured; no single
bull/bear/neutral regime label is produced (ADR-0025 refuses a directional regime, and the page states
that refusal rather than leaving a gap); no macro, news, derivatives, on-chain or liquidity data is
represented; and nothing held at an exchange but not recorded in the store is visible to it.

**Quality.** 5,629 → **5,876 tests** (+247), passing under `-W error` with zero warnings. **100 %
statement and 100 % branch coverage** of the new package's 975 statements and 340 branches. **15
mutation probes, 15 detected, 0 survivors**, byte-identical source restoration verified by SHA-256.
0 new runtime dependencies, 0 export collisions (646 → 697 public names), 0 import cycles, 1 existing
production file modified (`pipeline/cli.py`, additively). Three real defects were found by the tests
before release — a blank provider message that took the whole page down, a corrupt store that escaped
as an unhandled traceback, and long identifiers overflowing the 78-column page in four places — and
all three are recorded in [report 0016](reports/0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md)
rather than quietly fixed.

**Live-verified against real Binance data** on 2026-08-12, four symbols, exit code 0 — against both an
empty store and one populated through the real repositories.

---

### 2026-08-11 · `BC` — Research Dataset & Counterfactual Replay Correction

**Status:** Released · **committed locally, not pushed**. **Foundational** — this changes no trading
policy and adds no trading capability. It is recorded here because it materially changes how far the
owner can trust every number `fmits backtest` has ever printed, which rule 1 counts as materially
improving the reliability of a user-visible capability.
**Commit:** committed locally on top of `f9ddc54`.

**What shipped.** `fmits backtest --research` — the corrected research harness. `--start`/`--end` now
name the **measurement** window; the warm-up prefix is derived from the production dependencies
themselves and fetched *before* it; outcome-tail candles are readable after it but can never create a
setup; and counterfactual confirmation-age bounds are **replayed** through the unmodified production
composition path rather than filtered out of the baseline's results. Without `--research`, the command
behaves exactly as it always has.

**Why it was needed.** Milestone BB found that AV's "400-day backtest" contained roughly 43 days in
which the policy could reach `CONFIRMED` at all — the rest was weekly-EMA warm-up spent inside the
measurement window — and that the confirmation-age counterfactual had been emulated by deleting
already-observed rows, which cannot produce the setups a stricter rule *defers* onto a later break.
Re-running AV's own harness confirmed it independently: outcomes spanned **41 calendar days of a
400-day window**, with **49.0 % of them inside a single five-day span**.

**What the owner can now trust that they could not before.**

- **A research window that means what it says.** The usable period rises from a measured **41 days to
  380 days** across the same ten symbols — and the harness *verifies*, at every one of ~160,000
  measured instants, that no role was still warming up and none held fewer candles than requested
  (measured: 0 and 0; minimum 250 closed candles at all three roles).
- **A sample that is much less one stretch of market.** Largest five-day outcome cluster
  **49.0 % → 11.4 %**; confirmations across **35 distinct days in 10 months and 2 calendar years**
  rather than 23 days in 2 months of 1.
- **A window the harness refuses to shorten silently.** If the provider cannot supply enough history,
  the run fails with the measured shortfall rather than quietly measuring less and reporting it under
  the requested dates.
- **Counterfactuals that are real replays.** At a bound of 2, the old post-filter method keeps 21
  confirmations; the true replay produces 39, of which **18 exist only in the replay** because a
  stricter rule deferred the candidate onto a later, fresher break.

**No policy changed, and no performance is claimed.** `CONFIRMATION_LOOKBACK_BARS` is still 10. The
research override is unreachable from every live entry point, self-identifies in its own `policy_id`,
and is contained by 30 dedicated tests; replaying it at the production bound reproduces the production
baseline exactly — 45 confirmations, 45 unchanged, 0 shifted, 0 lost, 0 new. **No confirmation-age
bound is recommended or described as better**, and the variant table is explicitly labelled
sensitivity evidence. The corrected baseline is **not** comparable to AV's published figures, and the
implementation record says so before it shows them.

**A third defect was found and disclosed rather than absorbed.** AV's setup identity is keyed on a
*window-relative* bar index, so it changes every bar: measured across ten symbols, AV recorded 549
"unique setups" from 552 directional observations. Report 0011's counts stand as published and should
be read beside report 0012 §7.

**Also resolved:** the two long-standing test failures carried on the backlog since `AU` as "a
float-formatting flake" were a stale, git-ignored bytecode cache compiled from an older
`scan_report.py` — which was also making **`fmits scan` print prices in scientific notation** on this
machine (`target 1.3e+02` instead of `target 130`). Clearing it fixed both with no source change, and
the entire evidence run was re-executed on fresh bytecode.

**Records:** [design](docs/design/RESEARCH_HARNESS_CORRECTION_V1.md) ·
[implementation](reports/0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) ·
[hostile review](reports/0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md).

---

### 2026-08-08 · `AV` — Swing Setup Historical Backtest Harness v1

**Status:** Released · **committed locally, not pushed**. A new capability: the owner can now ask, and
get a real answer to, "what would the current Swing Setup v1 policy have produced historically?"
**Commit:** `2000ba2`

**What shipped.** `fmits backtest [SYMBOL...]` replays the exact, unmodified Swing Setup v1 policy over
real historical closed candles from public Binance data — one simulated instant at a time, seeing only
candles already closed at that instant — and prints a deterministic report: every
WAIT/CANDIDATE/CONFIRMED observation counted and reconciled, what happened after each confirmed setup
(`TARGET_FIRST`/`STOP_FIRST`/`AMBIGUOUS_SAME_BAR`/`NEITHER_WITHIN_WINDOW`), the exact data window used,
and every limitation, printed on the page itself rather than left in a document. A default run needs no
arguments: ten liquid crypto pairs, 400 days, the production 1w/1d/4h timeframe roles.

**Zero duplicate signal logic.** The harness calls the same `multi_timeframe_facts_for_symbol` →
`setup_inputs_and_assessment_for_sheet` → `evaluate_setup` chain `fmits setup`/`fmits scan` already use,
through a real historical data cache and a replay `Transport` bound to one simulated instant — the same
injection point every existing test in this repository already uses to run network-free.
`fmis.swing_setup.policy` has a zero-line diff; the 2-of-3 family rule, regime thresholds, confirmation
lookback, stop rule, target rule and RR policy are all exactly what they were before this milestone.

**The first honest measurement of the policy this repository has produced.** Live, on real Binance data,
10 symbols, 400 days (2025-07-04 → 2026-08-07): 21,730 observations, 182 confirmed setups, 151 with
evaluable stop/target geometry — **47.4% target-first, 52.6% stop-first**, close to a coin flip and
reported as exactly that, not reinterpreted positively. 76.5% of observations fell in a regime the
context-role dimension classified `INSUFFICIENT` (a real, measured consequence of `fmis.market_regime`
needing 50 closed weekly candles before it can classify anything, not a defect). The R:R distribution's
tail is genuinely pathological (p90 = 20.0, max = 41,282 on this run) — evidence for, not against, the
hostile audit's own concern about unbounded stop/target geometry. None of this is spun; the task brief's
own instruction — *"if the result is bad, report that it is bad"* — is what this entry does.

**Not a portfolio backtest, and the report says so on every page.** No fees, slippage, spread, or
execution delay; no position sizing; printed R:R is never confused with realized PnL; a same-bar
touch of both stop and target is reported as `AMBIGUOUS_SAME_BAR`, never guessed from candle colour.

**Independently reviewed**, not merely tested: an explicit adversarial checklist (lookahead, duplicate
setups, a dishonest denominator, guessed ambiguity, LONG/SHORT asymmetry, run-order dependence,
non-determinism) tried directly against the shipped code, each with a reproducing test or a mutation
probe. Found and fixed: a real width-overflow defect that crashed the CLI's own documented default
arguments, caught only by the live Binance run (never by a hand-built fixture); a default lookback
window too short for the regime engine to ever classify anything, corrected before any live run. Full
record: [review](docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md).

**Quality.** 4,426 → **4,487 tests** (+61), identically under `-W error` except two pre-existing,
unrelated failures on `main` before this milestone (a float-formatting flake in
`test_swing_setup_scan_report.py`, reproduced on the clean tree and named rather than silently fixed
under this milestone's scope). 8 targeted mutation probes, 8 detected (1 initial survivor closed with a
new test), byte-identical source restoration verified by SHA-256. Full record:
[design](docs/design/SWING_SETUP_BACKTEST_V1.md) ·
[review](docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md) ·
[report 0011](reports/0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md).

---

### 2026-08-07 · `AU` — Market Scanner Intelligence Report v1

**Status:** Released · **committed locally, not pushed**. A material reliability/usability improvement
to the eighth capability (`AT`'s scanner) — the same command, a report the owner can act on instead of
a table they had to scan by eye.
**Commit:** `fd8a781`

**What shipped.** `fmits scan` now prints a readable market intelligence report by default: a scan
summary (counts), a market overview (which symbols are showing directional character, from data the
engine already computed), every `CONFIRMED`/`CANDIDATE` setup with its risk/reward, target, stop and
the exact reasons the engine already stated, and every `WAIT` result grouped by its own reason with a
count. `--table` prints `AT`'s original compact table, unchanged, for scripting or a narrower terminal.

**What changed for the owner.** Before `AU`, reading a scan meant scanning twenty rows by eye and
re-running `fmits setup SYMBOL` to see *why* any one of them landed where it did. `fmits scan` now
answers "what should I actually look at this morning, and why" in the same one command.

**No new engine, no new ADR, no invented text.** Every fact printed by the new report already existed
on `SetupAssessment` before this milestone — the "reason" lines are the engine's own
`thesis`/`confirmation`/`invalidation` sentences, printed verbatim, never paraphrased or summarised by
this presentation layer. `fmis.swing_setup.compose`/`.policy`/`.models` have a zero-line diff.

**Found and fixed before release, confirmed live.** An independent adversarial review (run against the
brief's own checklist: does the report lie, do counts disagree, is logic duplicated, does presentation
leak into the engine or vice versa) found one P0 and two P1s, all reproducible through real analysis of
real market data — not only hand-built test fixtures: a market-overview label that could sit beside a
`WAIT` reason literally stating the opposite for the same symbol, and `CANDIDATE` setups silently
dropping an already-computed risk/reward and target. Both were fixed and the fixes were confirmed
against a second live scan before this record was written. Full account:
[review](docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md).

**Validated before this record:** 4,423 → 4,426 tests, all green; no coverage tool available in this
offline environment, 7 targeted mutation probes run in its place, all detected, zero survivors,
byte-identical source restoration verified. Full record:
[design](docs/design/MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md) ·
[review](docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md) ·
[report 0010](reports/0010_2026-08-07_MARKET_SCANNER_INTELLIGENCE_REPORT_V1_IMPLEMENTATION.md).

**Committed locally, not pushed.** Per `CLAUDE.md`'s git safety rule and this milestone's own explicit
instruction ("commit locally only, do not push"), `fd8a781` exists on local `main` only; `origin/main`
remains at `81a6202` until the owner authorizes a push.

---

### 2026-08-07 · `AT` — Market Scanner v1

**Status:** Released · the eighth user-visible product capability.
**Commit:** code `a271f33` · docs `81a6202`

**What shipped.** `fmits scan`: one command runs the existing Swing Setup Engine (`AR`) across a
fixed, hardcoded twenty-symbol watchlist of major crypto pairs, isolating one symbol's failure from
the rest exactly as `fmits setup`'s own multi-symbol mode already does, and prints one compact table —
`SYMBOL`/`STATUS`/`SIDE`/`RR`/`STOP`/`TARGET` — plus a summary line and a `TOP OPPORTUNITIES` section
for whatever cleared `CANDIDATE`/`CONFIRMED`.

**What changed for the owner.** Before `AT`, seeing every symbol's setup meant one `fmits setup` call
per symbol, with no compact overview of which ones were worth a second look. `fmits scan` answers that
in one command, over the same deterministic engine, with nothing recomputed.

**No new engine, no new ADR.** `run_market_scan` is `run_setup_for_symbols` (`AR`) called with a
default watchlist; the table renderer formats fields `SetupAssessment` already carries.
`fmis.swing_setup.compose`/`.policy`/`.models`/`.render` have a zero-line diff. The scanner lives
inside `fmis.swing_setup` rather than a new top-level package specifically because
[ADR-0028](docs/adr/ADR-0028-directional-interpretation-boundary.md)'s directional-vocabulary boundary
already permits that location and no other outside `pipeline/cli.py` — reusing the ADR rather than
amending it.

**No ranking, on purpose.** `AN`'s own record already warns that a scanner "must rank on an explicit,
deterministic, testable and backtested policy... never as a side effect of a workflow." `AT` ships the
"return what the engine already knows" half only: rows stay in the fixed watchlist's order, and
`TOP OPPORTUNITIES` filters that order rather than sorting it — pinned by a test that deliberately
places a weaker result ahead of a stronger one to rule out an implicit sort.

**Validated before this record:** 4,332 → 4,375 tests, all green under `-W error`; 100 % line and
branch coverage on both new/modified production files; 7 targeted mutation probes, all detected, zero
survivors, byte-identical source restoration verified; independent review found no P0, P1 or P2. Full
record: [design](docs/design/MARKET_SCANNER_V1.md) ·
[review](docs/reviews/MARKET_SCANNER_V1_REVIEW.md) ·
[report 0009](reports/0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md).

**Committed and pushed.** Code `a271f33`, docs `81a6202` — confirmed against `HEAD`, local `main` and
`origin/main` all matching. Table output unchanged by `AU`; `--table` is the exact renderer this record
describes.

---

### 2026-08-07 · `AS` — Market Regime Time-Reference Correction

**Status:** Released · **reliability fix, not a new capability** — per §1, recorded because it
*materially improves the reliability* of an existing capability (`fmits regime`, and every command
that depends on it).
**Commit:** `aca2628`

**What was broken.** `fmis.pipeline.regime.regime_input_from_sheet` supplied the index of the last
*confirmed swing* into a field the engine validated and read as the index of the last *closed candle* —
two different, routinely divergent positions in the same closed-candle sequence (the confirmation
delay and ordinary pivot sparsity both hold the confirmed swing behind the candle count). One
reference-frame mismatch produced two defects, traced in full in
[`REGIME_ROOT_CAUSE_ANALYSIS_V1.md`](docs/design/REGIME_ROOT_CAUSE_ANALYSIS_V1.md): `RegimeInputError`
raised on **valid** data whenever a change of character occurred after the last confirmed swing
(measured live during this milestone at 15.6 % of 6,452 historical states across 11 symbols and 4
intervals — matching the RCA's own 30-symbol, all-prefix measurement of 16.1 %); and, on every run that
*did* succeed, the reported age of a change of character was silently understated (0 of 6,452
successful classifications computed it correctly), systematically over-reporting `TRANSITIONING`.

**What changed for the owner.** `fmits regime --multi`, `fmits swing`, `fmits setup` and `fmits daily`
no longer abort on data that was always valid — verified live against ADAUSDT (the symbol on which the
defect was originally reported; its previously-failing SETUP·1d view now classifies correctly) and
against BTCUSDT, ETHUSDT, SOLUSDT, DOTUSDT, LINKUSDT. `fmits daily BTCUSDT ADAUSDT ETHUSDT` — which
previously discarded already-succeeded symbols the moment one `RegimeInputError` occurred — now
completes with 3/3 analysed, 0 failed, as a downstream consequence of the fix rather than a change to
`fmis.daily` itself. And the age FMITS reports for a structural change is now correct: measured against
the same 6,452-state sweep, 837 classifications move from a wrongly-reported `TRANSITIONING` to the
correct state, zero move the other way — every flip in the direction the root-cause analysis predicted.

**The fix.** `RegimeInput.last_index` (ambiguous — the adapter and the engine's own validator had
silently resolved it to two different referents) becomes `RegimeInput.closed_count`: the number of
closed candles the sheet was computed over, matching the pattern `fmis.swing_setup` already shipped for
the same problem (`execution_closed_count`). The engine — never `fmis.pipeline`, which remains
arithmetic-free by an AST-enforced guard — now owns `bars_since = closed_count - 1 -
latest_change_index` and the invariant `latest_change_index < closed_count`. Three production files
changed; `fmis.swing_setup`, `fmis.workspace` and `fmis.daily` have a zero-line diff.

**Validated before release:** 4,332 tests green including `-W error` (4,319 before this milestone),
100 % line and branch coverage on every modified module, 8 targeted mutation probes (all detected, zero
survivors, byte-identical source restoration verified by SHA-256), and an independent adversarial review
across twelve specific failure angles that found no P0, P1 or P2. Full record:
[the review](docs/reviews/MARKET_REGIME_TIME_REFERENCE_FIX_REVIEW.md).

**What did not change.** `transition_lookback_bars` (the policy threshold `TRANSITIONING` is compared
against) is untouched — this milestone corrected the arithmetic, not the policy, and the two are kept
deliberately separate. No new architectural decision was required: this repair makes the implementation
conform to [ADR-0025](docs/adr/ADR-0025-market-regime-engine-v1.md) §6 (amended to state explicitly what
the boundary's fields mean) rather than changing it.

**Related.** RCA: [`REGIME_ROOT_CAUSE_ANALYSIS_V1.md`](docs/design/REGIME_ROOT_CAUSE_ANALYSIS_V1.md) ·
Review: [`MARKET_REGIME_TIME_REFERENCE_FIX_REVIEW.md`](docs/reviews/MARKET_REGIME_TIME_REFERENCE_FIX_REVIEW.md)

---

### 2026-08-07 · `AR` — Swing Setup Engine v1

**Status:** Released · **seventh user-visible product capability**
**Commit:** `1480766e57526d48266a4aa5ff48b3a945614656`
Validated before versioning: 4,319 tests green including `-W error`, 100 % line and branch coverage on
every new `fmis.swing_setup` module and on `pipeline/cli.py`, 27 mutation probes across two passes plus
an independent reviewer's own 3-mutation spot-check — 27 detected, 0 survivors, byte-identical source
restoration verified by SHA-256 — and an independent adversarial review that found and fixed three P1s
before release (see below). Live-verified against BTCUSDT/ETHUSDT/SOLUSDT and eight further symbols on
real Binance data, including a naturally-occurring `CANDIDATE`/`SHORT` result with valid stop/target
geometry (DOTUSDT) — not manufactured; the policy was not loosened to produce it.

**What the owner can now do that was impossible before.** Ask for a deterministic swing-trade setup
assessment on a real instrument and receive either a justified setup or a justified `WAIT` — the
working protocol's own stated *"first practical stage."* `fmits setup BTCUSDT` (or several symbols in
one call) prints state (`WAIT`/`CANDIDATE`/`CONFIRMED`), direction when a candidate exists, the
independent evidence behind it, confirmation, invalidation, stop, target(s), risk/reward when
computable, and every limitation that applies.

**The one narrow architecture decision this required, made and enforced, not merely documented.**
Every existing engine in this repository is contractually non-directional; something had to be the
first place `LONG`/`SHORT` is allowed to exist. [ADR-0028](docs/adr/ADR-0028-directional-interpretation-boundary.md)
names `fmis.swing_setup` as that one place, at the same top-level tier as `fmis.workspace`, and a new
repository-wide guard test (`tests/test_directional_vocabulary_boundary.py`) plus seven widened
import-boundary tests enforce it structurally — a future change that leaked `LONG` into
`fmis.market_structure` or any other engine fails a test, not a review.

**Never from one indicator, and it is unrepresentable, not merely discouraged.** A directional
candidate requires at least two of three independent evidence families — CONTEXT-role structural
trend, SETUP-role structural trend, SETUP-role evidence alignment — to agree, with **zero** opposing.
Regime gates whether a candidate may exist at all (a trending CONTEXT-role environment) without ever
itself voting a direction, staying inside ADR-0025's refusal to represent one. Decision Context
`INSUFFICIENT` forecloses a candidate unconditionally, before the tally is even reached.

**EXECUTION confirms; it never votes.** `CANDIDATE → CONFIRMED` requires a recent (within
`CONFIRMATION_LOOKBACK_BARS`, 10 bars — a stated policy, not an assumption), side-matching structure
break on the execution timeframe, and the execution trend not opposing. Either failing leaves the
result at `CANDIDATE` — context and setup supportive, execution unconfirmed, never silently promoted.

**No fabricated price, ever.** Stop and target are real `PriceLevel` objects the structural chain
already detected, reused **by reference**, or explicitly absent — never invented, never equal to the
reference price (geometry is unrepresentable otherwise, enforced by the model's own validation, not
just the policy). Risk/reward is computed in code from that geometry, never asked of AI. Probability is
always `NOT_CALIBRATED` — this repository has no backtester yet, and the product brief named a fake
number as a specific, named integrity failure to avoid.

**The independent review found three real P1s, all fixed and regression-tested.** A same-bar dual
break (`fmis.structure_break` can emit an upper and a lower break on one bar) always resolved toward
the LOWER side because "latest break" was one positional value — a genuine, provable directional
asymmetry, fixed by carrying the full break history and searching it by side. No recency bound existed
on a confirming break at all, so a break from months earlier could confirm a candidate that had only
just formed — fixed by `CONFIRMATION_LOOKBACK_BARS`. And nothing validated that CONTEXT and SETUP were
fetched at distinct intervals, so one CLI flag combination (`--context 1d --setup 1d`) collapsed the
two-independent-families guarantee to one fact counted twice — fixed by rejecting the collision in
`build_setup_inputs`. Full record: [the review](docs/reviews/SWING_SETUP_ENGINE_V1_REVIEW.md).

**No position sizing, no opportunity ranking, no scope creep.** `fmits setup` on several symbols is
sequential, preserves input order, isolates a failed symbol without losing the others, and sorts
nothing — the same discipline `AN`'s daily index applies, restated for direction rather than
readiness. The existing 2 % portfolio-risk maximum is untouched and unapplied here.

**Related.** ADR: [ADR-0028](docs/adr/ADR-0028-directional-interpretation-boundary.md) · Design:
[SWING_SETUP_ENGINE_V1.md](docs/design/SWING_SETUP_ENGINE_V1.md) · Review:
[SWING_SETUP_ENGINE_V1_REVIEW.md](docs/reviews/SWING_SETUP_ENGINE_V1_REVIEW.md)

---

### 2026-08-05 · `AO` — Memory & Decision Archive v1

**Status:** Released · **sixth user-visible product capability**
**Commit:** `b40663f178e612856d6420c966b8a71ca7966edc`
Validated before versioning: 4,181 tests green including `-W error`, coverage 100 % line and branch on
every new `fmis.archive` module and on `pipeline/cli.py`, 35 mutation probes (34 detected, 1
proven-equivalent, 0 no-ops) and byte-identical source restoration, independent review complete with
three P1s found and fixed, and `fmits swing --archive` / `fmits archive show` run against live Binance
data with byte-identical rendered output and zero network calls on show.

**What the owner can now do that was impossible before.** Ask *"what did I think about this in October,
and was I right?"* Before `AO`, every analysis FMITS produced was discarded the moment the terminal
closed. `fmits swing BTCUSDT --archive` and `fmits daily BTCUSDT ETHUSDT --archive` now record the
complete page durably; `fmits archive list` shows every archived record without opening one; `fmits
archive show RECORD_ID` renders a stored record exactly as it was, with no network access; `fmits
archive verify` detects corruption and unsupported schema versions.

**Snapshot reproduction only, and that is stated rather than implied.** A shown record is exactly what
was archived — no recomputation, no re-fetch. `AO` does **not** replay history from raw market data; no
candle history is archived, only the already-composed analysis. Historical replay is a future
capability, not claimed here.

**Limitations, printed nowhere as fine print — stated here directly.**

- **No historical replay.** What the system would say *now*, given what it knew *then*, is not
  answerable yet — that needs raw inputs this version does not store.
- **No migration path.** A schema version outside the one this build supports (envelope or payload) is
  rejected cleanly; an old record becomes unreadable rather than silently misread if either shape
  changes before a migration exists.
- **No concurrent-writer safety.** A second `fmits` process archiving at the same instant is not this
  version's concern — documented, not guarded against.
- **No retention or deletion.** Nothing in this milestone ever removes a record.

**Safety / risk notes.** No `pickle`, no `eval`, no reflective deserialization — every record is decoded
through explicit, hand-written codecs that reconstruct real, self-validating domain objects. No secrets,
credentials or absolute filesystem paths are ever written to a record (verified: `metadata` is built
only from deterministic engine outputs). An archive failure is reported distinctly from an analysis
failure — a symbol that analysed correctly but could not be written to disk is never described as a
failed analysis.

**Correction (same day, pre-push, annotated per rule 9 rather than rewritten above).** Commit
`c84b2a1c0e6a7d13b0bbd586e7a60d2fa027a40d` widened the record-ID digest prefix from 8 to **16 hex
characters (64 bits)** before anything from `AO` was pushed — 32 bits reaches meaningful
birthday-collision probability at record counts a personal archive could plausibly accumulate over
years, for IDs meant to become stable long-term references. See ADR-0027 §4. Combined validated totals
after the correction: **4,194 tests**, **39 mutation probes (38 detected, 1 proven-equivalent, 0
no-ops)**. No compatibility reader was added for the unpublished 8-character shape.

**Related.** ADR: [ADR-0027](docs/adr/ADR-0027-memory-and-decision-archive-persistence-schema.md)
(resolves D-01) ·
Design: [MEMORY_AND_DECISION_ARCHIVE_V1](docs/design/MEMORY_AND_DECISION_ARCHIVE_V1.md) ·
Review: [MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW](docs/reviews/MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW.md)
— no P0, three P1 found and fixed, one P2 found and fixed, two P3.

**Breaking changes.** None. `facts`, `mtf`, `regime`, `swing` and `daily` behave identically when
`--archive` is not passed; `archive` and the two new flags are additive.

---

### 2026-08-04 · `AN` — Deterministic Daily Workflow v1

**Status:** Released · **fifth user-visible product capability**
**Commit:** `74036a4b81967618a809e420b85d320ab566d6b5`
Validated before versioning: 3,905 tests green including `-W error`, coverage 100 % on all four new
modules and on `pipeline/cli.py`, 81 mutation probes all detected with zero survivors and zero no-ops
and byte-identical source restoration, independent review complete, and `fmits daily` run against
live Binance data including a deliberately invalid symbol.

**What the owner can now do that was impossible before.** Analyse a whole watchlist in **one
command**. Every capability before this answered about one symbol; watching eight instruments meant
eight commands and eight ~270-line pages, held side by side in the owner's head. `fmits daily` runs
the same analysis across the universe and prints **83 lines for fifty symbols**, each row carrying the
decision-context state and the regime.

**The part that matters most is the failure handling.** Before AN, a symbol whose fetch failed was a
command that scrolled past — and a morning where three symbols were analysed and a fourth silently was
not looked exactly like a morning where all four were analysed. A failed symbol now keeps its row,
names its reason in the provider's own words, and the run still completes.

**Limitations, printed on every run.**

- **It is an index, not a ranking.** Rows appear in the order requested; nothing here says which
  symbol is worth attention.
- **A readiness state is not an opportunity.** It describes whether an analysis rests on enough data.
- **No shared as-of.** Each symbol is fetched at a different instant, so rows are not comparable in
  time.
- **No substitution.** A failed symbol reports why and nothing more; no cached or previous analysis
  stands in for it.
- **At most 50 symbols per run** — a stated policy, so a run cannot be rate-limited halfway through.

**Safety / risk notes.** No direction, no recommendation, no score, no sizing, and — deliberately —
**no ranking**, which is the single thing a multi-symbol page most invites. A defect inside FMITS is
never rendered as an ordinary market failure: unexpected exceptions stop the run rather than appearing
as a row.

**Related.** ADR: none — no new boundary was created ·
Design: [DETERMINISTIC_DAILY_WORKFLOW_V1](docs/design/DETERMINISTIC_DAILY_WORKFLOW_V1.md) ·
Review: [DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW](docs/reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md)
— no P0, no P1, two P2 found and fixed, one P3 fixed, three P3 documented.

**Breaking changes.** None. `facts`, `mtf`, `regime` and `swing` are unchanged; `daily` is added.

---

### 2026-08-04 · `AL` — Decision Context Engine v1

**Status:** Released · **reliability, not a new capability**
**Commit:** `a728f3b9f1dbf70c3e00fcfb97b66d60872f8ece`
Validated before versioning: 3,766 tests green including `-W error`, coverage 100 % on all four new
modules, 43 mutation probes all detected with zero survivors, independent review complete, all four
real-data surfaces working.

**Why this is recorded.** It adds no new thing to *do*, and §1 admits it on the other ground: it
**materially improves the reliability** of the capability `AK` shipped.

**What it changes for the owner.** The page now says whether it can be trusted. Measured before the
work began, a 12-candle analysis and a 260-candle analysis rendered nearly identically — a section's
status reported whether it *produced output*, not whether the output was *sound*. A 40-candle page
showed its regime section as available while two of three regime dimensions underneath read
insufficient. Those three cases now read **insufficient**, **limited** and **sufficient**, and when the
answer is not sufficient the page names which requirement is unmet and which layer decided.

**Limitations.**

- The judgement is made about the **primary timeframe**. The other views contribute their adequacy but
  the requirements are evaluated against the one a setup would be built on.
- **Sufficient does not mean correct.** It means the data each layer asked for is present. A sufficient
  context over a wrong reading is still a wrong reading, and the page says so.
- **Conflicts do not affect it.** Sufficiency is about what is available, not whether it agrees.
- **No score.** Three states and five named checks; a number would compress the information a reader
  needs in order to disagree.

**Safety / risk notes.** No direction, no recommendation, no sizing. This milestone **reduces** the
chance of acting on an analysis the system already knew was thin.

**Related.** ADR: [ADR-0026](docs/adr/ADR-0026-decision-context-boundary.md) ·
Design: [DECISION_CONTEXT_V1](docs/design/DECISION_CONTEXT_V1.md) ·
Review: [DECISION_CONTEXT_V1_REVIEW](docs/reviews/DECISION_CONTEXT_V1_REVIEW.md) — no P0, no P1, two P2
found and fixed, three P3.

**Breaking changes.** None. `facts`, `mtf` and `regime` are unchanged; `swing` gains a section.

---

### 2026-08-04 · `AK` — Swing Trading Workspace v1

**Status:** Released · **fourth user-visible product capability**
**Commit:** `8121050b9d36a22f9a20995c98c5be1206911c33`
Validated before versioning: 3,702 tests green including `-W error`, coverage 100 % on every workspace
module, 49 mutation probes all detected with zero survivors, independent review complete, and all four
real-data surfaces working.

**Product capability added.** `fmits swing SYMBOL` — the whole analysis on one page: data quality,
market regime per role, structure per role, levels, evidence grouped by family, and the conflicts
between them.

**What the owner can now do.** Read one page instead of running three commands and assembling the
result against a chart — and, more importantly, see **what disagrees** and **what the system cannot
tell them**, both as first-class sections rather than as omissions.

**Why this matters more than convenience.** Four sections — risk, portfolio, trade plan and AI
interpretation — are **rendered as unavailable**, each naming the milestone that owns it and the
inference its absence forbids: *"No position size shown here would be legitimate. Do not infer one."*
An omitted section is invisible, and an invisible gap reads as a gap that does not exist. This is the
first surface in the system that shows the reader the shape of its own ignorance.

It also made **1,131 statements of shipped code reachable**. `fmis.decision_support`,
`fmis.evidence` and `fmis.trading_context` were accepted, ADR-governed and fully tested with **zero
production importers**; the workspace is the surface all three were designed for.

**Limitations.**

- **Conflicts are reported, never resolved.** No rule outranks another and no timeframe is weighted
  above another. Reconciling disagreement remains a later layer's decision.
- **Evidence is price-derived only.** Four of the ten catalogued families carry no descriptor, and two
  more have engines that are computed but not yet classified. The page says which, every run.
- **Evidence and levels describe the primary timeframe** (1D by default). The other views contribute
  regime and structure.
- **No risk, no portfolio, no trade plan, no interpretation.** Those sections are empty by design.

**Safety / risk notes.** No order placement, no credentials, no directional output, no recommendation,
no position size. The page states this in three places and a test asserts each one.

**Related.** Design: [SWING_WORKSPACE_V1](docs/design/SWING_WORKSPACE_V1.md) ·
Review: [SWING_WORKSPACE_V1_REVIEW](docs/reviews/SWING_WORKSPACE_V1_REVIEW.md) — no P0, no P1, five P2
found and fixed, three P3 · **No ADR**: the implementation proved no new architectural decision.

**Breaking changes.** None. `fmits facts`, `fmits mtf` and `fmits regime` are unchanged.

---

### 2026-08-03 · `AI` — Market Regime Engine v1

**Status:** Released · **third user-visible product capability**
**Commit:** `cd4bb574e3afbedeeb402fbaf2e254a5a9b5f8ca`
Validated before versioning: 3,582 tests green including `-W error`, coverage 100 % on every module
touched, 45 mutation probes all detected with zero survivors, independent review complete, and all
three real-data surfaces working.

**Product capability added.** `fmits regime SYMBOL [--multi]` — a deterministic classification of the
market **environment**: structure (trending / ranging / transitioning), volatility (expanding /
contracting / steady) and participation (elevated / subdued / typical), each with the evidence behind
it and the exact thresholds that produced it.

**What the owner can now do.** Get a regime assessment that is reproducible, diffable and checkable
against history, and see *why* it says what it says — including where it refuses to say anything.
Until now that judgement existed only inside the v3 TradingView prompt's STEP 1, where it could not be
versioned or tested.

**Why this matters more than convenience.** `docs/analysis-notes.md` records what an unexamined regime
call cost in v2: a trend gate counted twice so a LONG began with two free confirmations, and branches
that looked symmetric while one required a deep bear market. Those failures are not prevented here by
discipline but by construction — evidence votes by family, a threshold band is one number whose edges
are multiplicative mirrors, and the engine never learns which way a trend points.

**Limitations.**

- **A regime is not a direction.** `trending` does not mean rising. Which way structure points is a
  separate fact on the fact sheet, and this classification deliberately does not restate it. It also
  diverges from the v3 prompt, which classifies BULLISH / BEARISH / RANGE.
- **Volatility and participation each rest on a single evidence family**, so neither can be
  corroborated or contradicted within its own dimension. Only structure requires two families to agree.
- **The thresholds are stated policy, not measurements.** No backtest justifies them, because none
  exists yet.
- **Each timeframe is classified alone.** Under `--multi` the three regimes are reported side by side
  and never reconciled.
- There is **no overall regime label and no confidence score**, deliberately.

**Safety / risk notes.** No order placement, no credentials, no directional output, no recommendation.
The engine cannot express a trade idea.

**Related.** ADR: [ADR-0025](docs/adr/ADR-0025-market-regime-engine-v1.md) ·
Design: [MARKET_REGIME_ENGINE_V1](docs/design/MARKET_REGIME_ENGINE_V1.md) ·
Review: [MARKET_REGIME_ENGINE_V1_REVIEW](docs/reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md)
— no P0, no P1, four P2 found and fixed, three P3 · Contract: `ARCH` §9.

**Breaking changes.** None. `fmits facts` and `fmits mtf` compute and print exactly what they did:
their feature sets are byte-identical and tests assert neither page shows regime vocabulary.

---

### 2026-08-03 · `AH` — Confirmation-Delay Provenance v1

**Status:** Released · **reliability, not a new capability**
**Commit:** `99483494ea44e00f2c3a8d3256d6288f6c7035c5`
Validated before versioning: 3,449 tests green including `-W error`, 42 mutation probes with 41
detected and 1 proven equivalent, independent review complete, both real-data smoke tests valid.

**Why this is recorded at all.** It adds **no user-visible capability**, and §1 permits it on two of
the other three grounds: it **materially improves the reliability** of an existing capability, and it
**removes a named blocker**.

**What it changes for the owner.** Every break of structure and change of character on a fact sheet is
now guaranteed to have been derived under the confirmation delay that detection actually used. Before
this, `derive_structure_breaks` took that delay as an argument that lived on none of its inputs, so a
value disagreeing with detection silently changed which level was the reference at every bar — and
therefore which breaks and which changes of character existed. Measured across 300 seeded series
against five wrong delays: **36.1 % produced materially different breaks, and none raised an error**.

The delay is now stamped at detection onto every swing, copied onto every level's origin, and read
from there. The argument is **removed** from every public entry point, so the mistake cannot be
expressed rather than being warned about.

**The one thing the owner will actually see.** `fmits facts` now prints **five** limitations instead
of six, and `fmits mtf` **eight** instead of nine. `ADR-0020 D1` — *"the confirmation delay is carried on no derived fact"* — is gone, because it
stopped being true. A limitation kept past its fix teaches a reader to discount the list.

**Blocker removed.** The Market Regime Engine (`AI`) is the second consumer of
`derive_structure_breaks`. AF and AG contained the hazard by each using a single caller; containment
does not survive a second one. That is now moot.

**Limitations.**

- One derivation cannot span two confirmation windows. A mixed set is **rejected loudly** rather than
  guessed at; no producer in the repository can create one.
- `left_bars` is not carried on a swing, because no consumer reads it. Adding it later is additive.
- A break at bar 0 is no longer representable, since a level needs at least one confirming bar. No
  real detection run could ever produce one.

**Safety / risk notes.** No order placement, no credentials, no directional output. This milestone
**reduces** correctness risk and adds none.

**Related.** ADR: [ADR-0024](docs/adr/ADR-0024-confirmation-delay-provenance.md) ·
Design: [CONFIRMATION_DELAY_PROVENANCE_V1](docs/design/CONFIRMATION_DELAY_PROVENANCE_V1.md) ·
Review: [CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW](docs/reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md)
— no P0, no P1, two P2 found and fixed, three P3 · Closes ADR-0020 D1.

**Breaking changes.** Internal API only, and deliberate: `derive_structure_breaks` and
`contextual_structure_breaks` no longer accept `confirmation_bars`; `SwingPoint` and `LevelOrigin`
each require it; `StructureBreak.eligible_from` is now a projection. **No package's exported name list
changed**, and no CLI behaviour changed beyond the removed limitation line.

---

### 2026-08-02 · `AG` — Multi-Timeframe Fact Sheet v1

**Status:** Released · second user-visible product capability
**Commit:** `e589411eb575f91ff017713ffc5ed35c094942bb`
Validated before versioning: 3,404 tests green including `-W error`, 42/42 mutation probes with zero
survivors and byte-identical source restoration, coverage 100 % on all three touched modules, and an
independent review complete.

**Product capability added.** `fmits mtf SYMBOL` — three role-labelled timeframe views of one
instrument in a single command: 1W context, 1D setup, 4H execution by default, each role settable.

**What the owner can now do.** See all three timeframes at once, each carrying its own `as_of` and
staleness, with their structural trends listed side by side — instead of running three separate
commands and reconciling them mentally.

**Why this matters more than convenience.** The single-timeframe sheet AF shipped could mislead. On
live BTCUSDT data the same day, 1W read `sustained_higher`, 1D `neutral` and 4H `sustained_lower`;
`fmits facts BTCUSDT` returned the 4H row alone. `PROJECT_SPECIFICATION_V1.md` §5 names that exact
combination and states it *"is different from simply calling the asset bullish"*. This entry is
recorded under two of the four criteria in §1: it adds a capability **and** removes a way the previous
capability could be read wrongly.

**Limitations.**

- **No cross-timeframe synthesis, deliberately.** The views are reported side by side and nothing is
  derived from their combination — no agreement, no alignment, no verdict. Reconciling timeframes that
  disagree is the Market Regime Engine's job, and pre-empting it here would place the first
  interpretation in the application layer. The sheet states this on every run.
- **Views are not aligned in time.** Each is fetched independently; a weekly view's newest closed bar
  measured **13 days old** live because the week had not closed. Each view reports its own timestamp.
- `ema_200` needs 200 closed bars — roughly four years on a weekly view — and reports as warming up
  where unavailable.
- The per-view block is **less complete** than `fmits facts`, which remains the way to read one
  timeframe exhaustively.
- All six AF limitations are inherited unchanged, including **ADR-0020 D1 still contained, not fixed**.

**Safety / risk notes.** No order placement, no credentials, no directional output. Three facts, not
one conclusion.

**Related.** ADR: [ADR-0023](docs/adr/ADR-0023-multi-timeframe-composition.md) ·
Design: [MULTI_TIMEFRAME_FACT_SHEET_V1](docs/design/MULTI_TIMEFRAME_FACT_SHEET_V1.md) ·
Review: [MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW](docs/reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md)
— no P0, no P1, two P2 found and fixed, three P3 ·
Contract: [reports/0006](reports/0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) §5.

**Breaking changes.** None. No engine was modified; `default_features()` is byte-identical, so
`analyze_symbol` returns exactly what it did before.

---

### 2026-08-02 · `AF` — First Light / Structural Fact Sheet v1

**Status:** Released · **First user-visible product capability**
**Commit:** `1505dd8a4e95f25a5cd876e9cfa7ca89f1b86acd`
**Live on `origin/main`** since `ea865bd`.

**Product capability added.** A command-line fact sheet that turns live exchange data into computed
market facts.

**What the owner can now do.** Run one command and receive EMA, RSI, MACD, ATR, relative volume,
swing structure, structural labels, structural trend, price levels, level crossings, break of
structure and change of character for a real instrument — **computed**, with provenance and warm-up
status, rather than estimated by a model looking at a chart.

**Why this is the first product entry.** Before AF the repository contained 11,128 lines of tested
library code and delivered no user capability at all: 51.2 % of it could not be reached from real
market data, and the only working analysis tool was a 199-line prompt that estimated every value
visually. AF is where `PROJECT_SPECIFICATION_V1.md` §3.1 — *code computes what code can compute* —
became something the owner can actually use.

**Limitations.**

- **One timeframe per sheet.** This is a real hazard, not a gap: measured live on BTCUSDT, 1W read
  `sustained_higher`, 1D `neutral`, 4H `sustained_lower`. A single-timeframe reading can therefore
  mislead. Addressed by `AG`.
- One provider (crypto spot) · crypto only · text output only · nothing persisted.
- Levels are reported as *nearest above / nearest below*, never support or resistance — that naming
  is an interpretation reserved for a later layer.
- **ADR-0020 D1 is contained, not fixed.** A mismatched confirmation delay is undetectable in
  general; AF makes it unrepresentable through this one caller. Measured: 36.1 % of mismatched calls
  produce materially different breaks, none raising an error.

**Safety / risk notes.** No order placement, no credentials, no directional output. The renderer
states on every sheet that its contents are measurements, not conclusions.

**Related.** ADR: [ADR-0022](docs/adr/ADR-0022-structural-fact-sheet-composition-root.md) ·
Design: [STRUCTURAL_FACT_SHEET_V1](docs/design/STRUCTURAL_FACT_SHEET_V1.md) ·
Review: [STRUCTURAL_FACT_SHEET_V1_REVIEW](docs/reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md) —
no P0, no P1, one P2 found and fixed, four P3 ·
Report: [0006](reports/0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) §2.

**Breaking changes.** None. Purely additive; no existing engine source was modified.

---

### 2026-07-31 · `AE` — Change of Character Foundation v1

**Status:** Released · **Foundational — not directly user-visible**
**Commit:** `d132ceafc4048b89205772524bf192e3c7bc7b4b` *(merge; implementation `7276918`)*

**Capability added to the system.** Completed the deterministic structural chain:
`CandleSeries → swings → relationships → labels → sequence state → trend → context → level crossings
→ break of structure → change of character`. A change of character is the first break opposing the
last determinate one.

**What the owner could do after it.** **Nothing new directly.** No product surface existed at the
time, so this capability was unreachable by any user. It is recorded because it supplied the last
primitive AF needed, and because the honest history matters: the deterministic chain was finished
three days before anything could read it.

**Limitations.** A two-sided break bar leaves character indeterminate — resolving it needs sub-bar
data the system does not ingest. A change of character is never invalidated.

**Safety / risk notes.** None applicable — no execution path, no user surface.

**Related.** ADR: [ADR-0021](docs/adr/ADR-0021-change-of-character-foundation-v1.md) ·
Design: [CHOCH_FOUNDATION_V1](docs/design/CHOCH_FOUNDATION_V1.md) ·
Review: [CHOCH_FOUNDATION_V1_REVIEW](docs/reviews/CHOCH_FOUNDATION_V1_REVIEW.md) — no P0/P1/P2.
Verified 3,221 tests passing at that commit.

**Breaking changes.** None.

---

### 2026-07-31 · `AD` — Break of Structure Foundation v1

**Status:** Released · **Foundational — not directly user-visible**
**Commit:** `5aac1a3f652ea44e4523e2609e140c18a0b9f121` *(merge; implementation `458f3ac`)*

**Capability added to the system.** The first layer built entirely on derived facts — it reads no
candle at all. A break of structure is the first close beyond the reference level for its side, at a
bar where that level was already knowable.

**What the owner could do after it.** **Nothing new directly** — foundational, same as `AE`.

**Why it appears here despite not being user-visible.** It **named a limitation instead of defaulting
it away**. `confirmation_bars` was made a required argument with no default, and the fact that a
mismatch is undetectable was recorded as ADR-0020 D1. That decision is why the hazard is a scheduled
milestone (`AH` on the backlog) rather than a latent defect — a material reduction in future
operational risk, which is one of the four recording criteria in §1.

**Limitations.** The reference level is the most recent, not the most extreme. A break is never
invalidated. The first swing of each type yields no level.

**Related.** ADR: [ADR-0020](docs/adr/ADR-0020-break-of-structure-foundation-v1.md) ·
Design: [BREAK_OF_STRUCTURE_FOUNDATION_V1](docs/design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md) ·
Review: [BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW](docs/reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md)
— one P2 found and fixed, no P0/P1. Verified 3,033 tests passing at that commit.

**Breaking changes.** None.

---

### Earlier

Milestones before `AD` are recorded in
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md). **None of them delivered a
user-visible capability**, because no product surface existed until `AF`. They are deliberately not
restated here; a product changelog that listed thirty foundational milestones would obscure the one
fact that matters — the product began on 2026-08-02.

---

## 5. Upcoming

> **Unreleased. Planned. Not available.** Nothing in this section exists in the repository.

No milestone is currently sequenced. `AO` shipped (recorded in §3 and §4 below) and D-01 is resolved;
the next NOW item has not yet been chosen — see [the product backlog](FMITS_PRODUCT_BACKLOG.md) §5–§7.

*(This section previously listed `AN`, then `AO`, here as unreleased; both shipped and are recorded as
released in §3 and §4 above.)*

## 6. Entry template

Copy for each new entry.

```markdown
### YYYY-MM-DD · `ID` — Milestone name

**Status:** Released | Foundational | Unreleased
**Commit:** <full 40-character SHA>

**Product capability added.** One sentence.

**What the owner can now do.** Concrete, in the owner's terms. If nothing — say so plainly
and mark the entry Foundational.

**Limitations.** Explicit. Every known one. Cite the ADR that owns each.

**Safety / risk notes.** Execution, credentials, capital exposure, directional claims.

**Related.** ADR · design · review · report.

**Breaking changes.** None, or exactly what broke and what callers must do.
```

---

## 7. Changelog rules

1. **Never record documentation-only work as a product release.** Reports, ADRs, designs, reviews,
   indexes and this file itself are never entries.
2. **Internal refactors belong here only if they materially affect product reliability** — and the
   entry must say how, in the owner's terms.
3. **Planned work must never appear as released.** Unreleased items live in §5, are labelled
   UNRELEASED, and carry no commit SHA.
4. **Every released entry must point to a real commit** — a full 40-character SHA verified to exist
   in this repository.
5. **Limitations must be explicit.** An entry that omits a known limitation is a false claim. If a
   capability can mislead, say so, as the `AF` entry does.
6. **No profit or performance claims.** Ever. No return figures, no win rates, no backtest results
   presented as expected outcomes. The project's own success criteria contain no return figure.
7. **No claim of live-trading readiness** without the full ladder completed: research → explicit
   rules → backtesting → robustness → paper → shadow → small controlled live. No rung is skipped, and
   the changelog never implies otherwise.
8. **Foundational entries are labelled**, never dressed as releases.
9. **Entries are append-only.** A superseded entry is annotated, never rewritten or deleted.

---

*Living document · last verified against `c84b2a1` (Milestone `AO` + the pre-push record-ID correction)
on 2026-08-05*
