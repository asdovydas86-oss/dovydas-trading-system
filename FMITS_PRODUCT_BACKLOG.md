# FMITS Product Backlog

**Living document.** The current execution board: what is being built now, what comes next, what is
blocked, and why each item matters to the product.

**Not a roadmap.** [`reports/0005`](reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md)
remains the strategic roadmap and is immutable. This board changes as work moves.

**Not an architecture document.** Boundaries live in the ADRs and
[`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md).

| Field | Value |
|---|---|
| **Last verified against** | `ea865bdc3fc98b2d5d2e432c0b6bf4d397d0e7ab` |
| **Verified on** | 2026-08-02 |
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
| **HEAD** | `ea865bdc3fc98b2d5d2e432c0b6bf4d397d0e7ab` |
| **`origin/main`** | `ea865bdc3fc98b2d5d2e432c0b6bf4d397d0e7ab` — synchronised |
| **Working tree** | clean · 0 untracked · 0 staged |
| **Test count** | **3,305 passing**, identically under `-W error` |
| **Public exports / collisions** | 136 / 0 |
| **Import cycles** | 0 |
| **Runtime dependencies** | 0 |
| **Latest completed milestone** | **AF — First Light / Structural Fact Sheet v1** (`1505dd8`) |
| **Product Value Level** | **Level 1 — visible deterministic analysis** (ladder in [`reports/0004`](reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §12) |
| **Architecture maturity** | **M2 — Connected** ([`reports/0003`](reports/0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) §11) |
| **Immediate next milestone** | **AG — Multi-Timeframe Fact Sheet** |

### Current user-visible capability

```
fmits facts BTCUSDT --interval 4h --limit 200
python -m fmis.pipeline facts BTCUSDT      # works without reinstalling
```

Returns a deterministic fact sheet for **one instrument on one timeframe**: EMA/RSI/MACD/ATR with
warm-up status, relative volume, swing points, structural labels, structural trend, price levels,
level crossings, break of structure, change of character, nearest level above and below the last
close, and the inherited limitations — computed from live exchange data.

**This is the whole product surface today.** Everything else in the repository is a library beneath it.

---

## 5. NOW

Exactly one item.

### `AG` — Multi-Timeframe Fact Sheet

| Field | Value |
|---|---|
| **ID** | AG |
| **Epic** | EP-01 Technical Analysis & Market Structure |
| **Status** | **NOW** |
| **Priority** | **Critical** |
| **Implementation contract** | [`reports/0006`](reports/0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) **§5** — do not redesign |
| **Estimated size** | 1–2 weeks *(source: reports/0006 §5.12)* |
| **Confidence** | High — verified live that composition needs no new engine |

**Product value.** The owner analyses 1W/1D/4H every day; the fact sheet answers only one timeframe.
Worse, a single-timeframe reading can mislead: measured live on BTCUSDT, 1W was `sustained_higher`,
1D `neutral` and 4H `sustained_lower` — precisely the combination `PROJECT_SPECIFICATION_V1.md` §5
says must not be flattened into "bullish".

**What the owner can do after this that was impossible before.**
Run one command and see the structural state of all three timeframes side by side, each labelled with
its role, each with its own `as_of` and staleness — instead of running three commands and mentally
reconciling them, or reading one and being misled.

**User capability unlocked.** C-022 multi-timeframe analysis — classified *Core, before-v1* in
[`reports/0004`](reports/0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) §4.2.

**Dependencies.** AF (done). No new engine. No new data source.

**Acceptance criteria** *(condensed from reports/0006 §5.11 — that section governs)*

- `fmits mtf BTCUSDT` prints a role-labelled 1W/1D/4H sheet from live data
- Each view shows its own `as_of` and age; no shared timestamp is implied
- Three structural trends side by side with **no derived agreement field**
- `ema_200` present via a named `swing_features()`; `default_features()` byte-identical
- One `DetectionSettings` reaches every view — AST-asserted
- Zero arithmetic operators in the new module — AST-asserted
- No clock beneath the CLI — source-asserted
- A short timeframe raises; no partial sheet is ever returned
- Full suite green including `-W error`; ≥30 mutation probes, **zero survivors**
- ADR-0023, design and review records complete

**Out of scope.** Regime or any cross-timeframe verdict · support/resistance naming · scanning ·
watchlists · persistence · scheduling · alerts · JSON output · AI · portfolio · risk · second
provider · non-crypto assets · workspace/TUI/GUI · changing `default_features()` · fixing ADR-0020 D1.

**Related ADRs.** ADR-0007 (composition-root boundary) · ADR-0019 (level naming rule) ·
ADR-0020 (D1, contained) · ADR-0022 (AF, the root being reused). **New:** ADR-0023.

**Related reports.** 0004 §4.2, §18.5 · 0005 Phase 3 · **0006 §4–§6 (contract)**.

**Related repository paths.** `src/fmis/pipeline/multi_timeframe.py` *(new)* ·
`src/fmis/pipeline/render.py` · `src/fmis/pipeline/cli.py` · `src/fmis/pipeline/__init__.py` ·
`tests/test_multi_timeframe.py` *(new)*.

**Risks.** Scope creep into regime or a workspace — the contract's out-of-scope list is the control ·
per-view staleness being presented as a shared timestamp · emitting an agreement/alignment field,
which would pre-empt the Market Regime Engine.

---

## 6. NEXT

The forced sequence. Each item is blocked on the one above it.

### `AH` — LevelOrigin / confirmation-delay provenance (ADR-0020 D1)

| Field | Value |
|---|---|
| **Epic** | EP-01 · **Status** NEXT · **Priority** **Critical** |
| **Product value** | **Blocker removal** — removes a silent-corruption risk from every future consumer of the structural chain |

**What the owner can do after this that was impossible before.** Nothing directly. This is a
blocker-removal milestone under the product-first rule, and it states its blocker precisely: the
Market Regime Engine (`AI`) is the second consumer of `derive_structure_breaks`, and cannot be built
safely while a mismatched confirmation delay is undetectable.

**Why not sooner.** AF *contained* the hazard — `DetectionSettings` single-sources the delay, so a
mismatch is unrepresentable through the only caller that exists — and AG reuses that same root, so
containment holds through AG. The hazard goes live at consumer #2.

**Measured severity.** 300 seeded series × 5 wrong delays: **36.1 % produced materially different
breaks**, 155 of those also changed the change-of-character count, and **zero raised an error**
(`docs/reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md` §2).

**Dependencies.** AG. **Acceptance.** The delay is carried on a derived fact from detection through
to `LevelOrigin`; a mismatch is impossible or loudly rejected; all existing tests pass unchanged or
with documented widening. **Out of scope.** Any new structural rule; any interpretation.
**Known cost.** Changes shipped models across three packages; `SwingPoint` alone is constructed at 69
test sites. **Explicitly rejected approach.** A `right_bars` parameter on `structural_levels` — it
relocates the hand-matching while making a wrong value look like recorded provenance.
**Related.** ADR-0020 D1 · new ADR required · `reports/0006` §3.1.

### `AI` — Market Regime Engine

| Field | Value |
|---|---|
| **Epic** | EP-01 · **Status** NEXT · **Priority** **Critical** |
| **Product value** | Moves the regime call out of the TradingView prompt into versioned, testable code |

**What the owner can do after this that was impossible before.** See a regime classification that is
reproducible, diffable and checkable against history — instead of one produced inside a prompt that
cannot be versioned. This is the direct structural fix for the v2 LONG-bias failure recorded in
`docs/analysis-notes.md`.

**Dependencies.** AG (regime is per-timeframe by definition) **and** AH (regime is consumer #2).
**Acceptance.** Regime output carries component evidence and uncertainty, never a bare label; no
direction vocabulary at this layer; thresholds are versioned parameters, never literals.
**Out of scope.** Trade selection, sizing, strategy conditioning.
**Risks.** Being trusted before validation against history — mitigate by replaying over the archive.
**Related.** `reports/0003` §L5 · `reports/0004` C-023 · `reports/0005` Phase 3.

### `AJ` — Swing Trading Workspace

| Field | Value |
|---|---|
| **Epic** | EP-02 Swing Trading Product · **Status** NEXT · **Priority** High |
| **Product value** | The first surface built for a workflow rather than for an instrument |

**What the owner can do after this that was impossible before.** Work a swing candidate end to end in
one place — structure, regime, levels, evidence — instead of assembling it from CLI output and a chart.

**Dependencies.** AI. Deliberately *after* regime: `reports/0006` §2 rejected building a workspace
earlier precisely because it would present facts that were incomplete and, on one timeframe,
misleading. **Out of scope.** Sizing and portfolio context, which arrive with EP-04.

### `AK` — Deterministic daily workflow v1

| Field | Value |
|---|---|
| **Epic** | EP-03 Daily Market Intelligence · **Status** NEXT · **Priority** High |
| **Product value** | **This is v1** — the first version genuinely useful daily without the TradingView prompt doing the analysis |

**What the owner can do after this that was impossible before.** Open the system each morning and be
told what changed and what deserves attention, before asking. Requires scanning over a watchlist, a
generated brief, and scheduling — the last of which currently has **no owner in any architecture layer**.

**Dependencies.** AJ. **Related.** `reports/0004` §12 Level 3 · `reports/0005` Phase 4.

### `AL` — Memory / decision archive

| Field | Value |
|---|---|
| **Epic** | EP-18 Knowledge & Research · **Status** NEXT · **Priority** **Critical** |
| **Product value** | Closes the loop. Four of the project's nine success criteria depend on it |

**What the owner can do after this that was impossible before.** Ask *"what did I think about this in
October, and was I right?"* and get an answer. Until this exists, daily use accumulates nothing.

**Dependencies.** AK, and **OPEN DECISION D-01 (persistence schema)** must be settled first.
**Related.** `PROJECT_SPECIFICATION_V1.md` §25 · `reports/0004` C-159 · `reports/0005` Phase 5.

---

## 7. LATER — epics

In scope, not yet sequenced. One line per epic states what it delivers and what gates it.
Detail lives in `reports/0004` (capabilities) and `reports/0005` (phasing) — not restated here.

| ID | Epic | Delivers | Status | Priority | Gated by |
|---|---|---|---|---|---|
| **EP-01** | Technical Analysis & Market Structure | Support/resistance scoring, pattern detection, composite features, remaining indicators (RSI MA, MACD slope, ADX, Bollinger, VWAP), divergences | Partly DONE | High | — |
| **EP-02** | Swing Trading Product | Scanning, ranking, trade plan, confirmation/invalidation, stop and target logic, post-trade review | LATER | High | AJ |
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
| **EP-18** | Knowledge & Research | Decision archive, journal, searchable knowledge base, lessons learned | LATER | **Critical** | **D-01 persistence schema** |
| **EP-19** | Reporting & Delivery | Dashboard, structured reports, exports, notifications, transports | LATER | Low | AK |
| **EP-20** | Security & Operations | CI, type checking, system health, observability, AI budget, safety controls | LATER | Medium | **D-07 CI timing** |

**Bounded autonomous day trading** is deliberately **not** an epic on this board. It sits beyond
EP-17 and beyond the autonomy boundary that `reports/0003` §7.5 records as not crossed and not
designed. It requires its own vision decision (**D-14**, **D-15**) before it can be scheduled.

---

## 8. DONE

Repository-verified only. Every SHA below was confirmed to exist with `git cat-file -e`.

The **complete** 30-milestone history lives in
[`docs/AI_HANDOFF/CURRENT_STATE.md`](docs/AI_HANDOFF/CURRENT_STATE.md) and is not duplicated here.
This section carries the three most recent product-relevant milestones.

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

Carried, not solved. None of these blocks AG.

| ID | Decision | Blocks | Source |
|---|---|---|---|
| **D-01** | Persistence and serialization schema | EP-18, AL | `ARCH` §13.8 · `reports/0006` §6 |
| **D-02** | Money / portfolio numeric types (`float` vs `Decimal`) | EP-04 | Review R11 · `reports/0005` §7.2 |
| **D-03** | Availability-time model for released/revised data | EP-07, EP-08 | **ADR-0003 (formal gate)** |
| **D-04** | Journal scope as a formal product capability | EP-18 | `reports/0004` §15.3 |
| **D-05** | Scheduling ownership — belongs to no architecture layer | AK, EP-03 | `reports/0004` §13.5 |
| **D-06** | Watchlist / universe model | AK, EP-03 | `reports/0004` §13.5 |
| **D-07** | CI and type-checking timing | EP-20 | `reports/0001` §10.2 |
| **D-08** | Telegram as a delivery transport | EP-19 | `reports/0004` §15.2 |
| **D-09** | Excel / CSV export ecosystem | EP-19 | `reports/0004` §15.2 · blocked by D-01 |
| **D-10** | Tax Center scope | EP-19 | `reports/0004` §15.2 — recommended out of scope |
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
8. **Architecture work must name the product blocker it removes.** AH is the pattern: it delivers
   nothing user-visible and says exactly which milestone it unblocks and why.

### Known internal note

[`reports/0006`](reports/0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) §5.2 lists a root
`REPORT.md` among the files AG should update. That file was deleted under explicit authorization on
2026-08-02 and its unique content migrated into
[`reports/README.md`](reports/README.md). **That row is superseded.** Report 0006 is immutable and was
not edited.

---

*Living document · last verified against `ea865bd` on 2026-08-02*
