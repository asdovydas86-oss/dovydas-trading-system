# FMITS Product Changelog

**What FMITS can actually do, and when it could first do it.**

This is a **product** changelog, not a Git changelog. It does not list commits, refactors, test
additions, documentation, or architecture work. It records only changes to what the owner can do.

| Field | Value |
|---|---|
| **Last verified against** | `99483494ea44e00f2c3a8d3256d6288f6c7035c5` (Milestone AH) |
| **Verified on** | 2026-08-03 |
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

**As of `9948349` — what the owner can do today.**

```
fmits mtf   BTCUSDT -n 260                     # 1W context · 1D setup · 4H execution
fmits facts BTCUSDT --interval 4h --limit 200  # one timeframe, exhaustively
python -m fmis.pipeline mtf BTCUSDT            # works without reinstalling
```

**Delivered:**

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
  since `ADR-0020 D1` was fixed and removed rather than left standing.

**Explicitly not delivered:**

| Not available | Where it is on the backlog |
|---|---|
| AI interpretation of any kind — the numbers are computed, not read | EP — after regime |
| Trade signal, direction, ranking, score or recommendation | Strategy layer, `EP-13` |
| Cross-timeframe **synthesis** — the views are reported, never reconciled | `AI` Market Regime Engine |
| Market regime classification | `AI` |
| Support/resistance naming — levels are reported as *nearest above / below* | `EP-01` |
| Portfolio or risk context, position sizing | `EP-04`, blocked on **D-02** |
| Persistence — a sheet is printed, never stored | `AL`, blocked on **D-01** |
| Scanning, watchlists, alerts, scheduling, brief | `AK`, `EP-03` |
| Any asset class other than crypto | `EP-05` |
| Backtesting, paper trading, shadow mode, execution | `EP-14` … `EP-17` |

**Safety position.** The system executes nothing, holds no credentials that could move funds, and
makes no directional claim. Every rung of the automation ladder remains unstarted.

---

## 4. Product milestones

Reverse-chronological. Every **Released** entry cites a commit verified to exist in this repository.
An entry whose milestone is implemented and validated but not yet versioned is marked
**Implemented — pending commit** and carries no SHA, per rule 4.

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

**The one thing the owner will actually see.** Both sheets now print **six limitations instead of
seven**. `ADR-0020 D1` — *"the confirmation delay is carried on no derived fact"* — is gone, because it
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

### `AI` — Market Regime Engine — **UNRELEASED**

**Status:** NOW on the [product backlog](FMITS_PRODUCT_BACKLOG.md) · **not started** · no commit, no
design and no ADR exists

**Capability it will add.** A regime classification that is reproducible, diffable and checkable
against history, instead of one produced inside a TradingView prompt that cannot be versioned.

**What it will change for the owner.** Not yet decided in detail, and deliberately not described here
as though it were. What can be said is that its precondition is met: `AH` removed the hazard that made
a second consumer of `derive_structure_breaks` unsafe, and regime is that second consumer.

No further capability is listed. The sequence after it is on the backlog — this changelog records what
shipped, not what is planned.

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

*Living document · last verified against `9948349` on 2026-08-03*
