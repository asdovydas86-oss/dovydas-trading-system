# FMITS Product Changelog

**What FMITS can actually do, and when it could first do it.**

This is a **product** changelog, not a Git changelog. It does not list commits, refactors, test
additions, documentation, or architecture work. It records only changes to what the owner can do.

| Field | Value |
|---|---|
| **Last verified against** | `1480766e57526d48266a4aa5ff48b3a945614656` (Milestone AR) |
| **Verified on** | 2026-08-07 |
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

**As of `1480766` (`AR`) — what the owner can do today.**

```
fmits setup  BTCUSDT                            # a deterministic swing-trade setup assessment
fmits setup  BTCUSDT ETHUSDT SOLUSDT            # one per symbol, in the order requested
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

- a **deterministic swing-trade setup assessment**: `WAIT` / `CANDIDATE` / `CONFIRMED`, with a
  direction only when a candidate exists, the independent evidence families behind it, confirmation,
  invalidation, stop, target(s) and risk/reward when computable, and every limitation that applies.
  Direction never comes from one indicator — at least two of three independent families must agree
  with zero opposing — and `WAIT` is a first-class, successful result, not a failure;
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
| Opportunity ranking or score across symbols | `EP-02`/`EP-03` — deliberately absent from `fmits setup`'s multi-symbol mode: sequential, input order preserved, no sort |
| Cross-timeframe **synthesis** — the views are reported, never reconciled | `AI` Market Regime Engine |
| ~~Market regime classification~~ | **Delivered by `AI`** — see below |
| Support/resistance naming — levels are reported as *nearest above / below* | `EP-01` |
| Portfolio or risk context, position sizing | `EP-04`, blocked on **D-02** |
| ~~Persistence — a run is printed, never stored~~ | **Delivered by `AO`** — see above |
| Historical replay — recomputing a past analysis from its original raw inputs | not archived yet; snapshot reproduction only |
| A journal, discretionary notes, trade outcomes | `EP-18`, blocked on **D-04** |
| Opportunity scanning and candidate ranking | `EP-02`, `EP-03` — a **named future capability** (SPEC §10 and the Opportunity Scanner; vision addendum; `reports/0005` C-164). Deferred, not withdrawn, and it must arrive as an explicit, deterministic, testable, backtested policy |
| Ranking *by readiness* — sorting the daily index by its own states | **never**, in any version. Readiness describes the analysis, not the instrument; see AN's design §3.4 |
| Alerts, scheduling, unattended runs, notification delivery | `EP-03` — scheduling still owns no architecture layer |
| Watchlist persistence as its own model — a universe is typed, or supplied by the shell | `EP-03`, **D-06** — unrelated to D-01; `AO` archives whatever universe it is given |
| Any asset class other than crypto | `EP-05` |
| Backtesting, paper trading, shadow mode, execution | `EP-14` … `EP-17` |

**Safety position.** The system executes nothing and holds no credentials that could move funds.
`AR` is the first and only capability that makes a directional claim (`fmits setup`), confined to one
package by construction (ADR-0028) and never a position size, leverage or money amount. Every rung of
the automation ladder remains unstarted.

---

## 4. Product milestones

Reverse-chronological. Every **Released** entry cites a commit verified to exist in this repository.
An entry whose milestone is implemented and validated but not yet versioned is marked
**Implemented — pending commit** and carries no SHA, per rule 4.

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
