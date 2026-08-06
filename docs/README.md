# FMITS Documentation

**FMITS** — Financial Market Intelligence & Trading System.

This is the entry point to the project's documentation. If you are a human developer or an AI coding
agent arriving at this repository, start here.

---

## What FMITS is

FMITS is a modular, AI-assisted financial-market decision-support system. Its purpose is **not** to emit
BUY/SELL signals, and **not** to run automated live trading. Its purpose is to improve the *quality,
consistency, transparency, and testability* of market analysis by building — one small, tested layer at
a time — a pipeline:

```
Data → deterministic calculations → structured features → AI interpretation → decision support
```

Objective values are computed by code. AI is reserved for interpreting structured facts, conflicts,
scenarios, and uncertainty. `WAIT` and `NO TRADE` are valid outcomes. Capital preservation and
testability rank above impressive-looking signals.

The full vision and principles live in the authoritative specifications (see the index below); this
README summarizes and points, it does not restate them.

---

## Documentation index

| Document | What it is | Authority |
|---|---|---|
| [README.md](README.md) | This entry point | Navigation |
| [ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) | Target architecture, module boundaries, dependency rules, Relative Value Engine spec, roadmap, decisions | **Authoritative — architecture** |
| [ARCHITECTURE_REVIEW_2026-07-24.md](ARCHITECTURE_REVIEW_2026-07-24.md) | Full architectural verification at commit `5e7e3d5`: findings R1–R14, divergences from the architecture doc, readiness verdict | **Authoritative — amends the architecture doc §5** |
| [adr/](adr/README.md) | Architecture Decision Records — one decision per file, with alternatives and consequences | **Authoritative — decisions** |
| [design/STRUCTURAL_SEQUENCE_STATE_HISTORY_DESIGN_V1.md](design/STRUCTURAL_SEQUENCE_STATE_HISTORY_DESIGN_V1.md) | Approved design for structural sequence state history (Milestones Z0-Z1): domain model, prefix-stability proof, P2 architecture, test strategy, risks, roadmap | Design — implemented by [ADR-0016](adr/ADR-0016-structural-sequence-state-history-foundation.md) |
| [design/TREND_FOUNDATION_DESIGN_V1.md](design/TREND_FOUNDATION_DESIGN_V1.md) | Approved design for Trend Foundation v1 (Milestone AA): the four evaluated policies and the measured grounds for rejecting three, the chosen sustained-run policy, state diagram, transition and decision tables, invariants, prefix-stability analysis and its stated limits, API, test and mutation plan | Design — implemented by [ADR-0017](adr/ADR-0017-structural-trend-foundation.md) |
| [design/SERIES_IDENTITY_CONTEXT_CONTRACT_V1.md](design/SERIES_IDENTITY_CONTEXT_CONTRACT_V1.md) | Approved design for Series Identity & Context Contract v1 (Milestone AB): the audit that found identity already owned by `CandleSeries`, eight alternatives against sixteen criteria, identity semantics and normalization policy, the context contract's fifteen principles, the context-free vs pipeline-boundary API split, and 11 reproducible experiments | Design — implemented by [ADR-0018](adr/ADR-0018-series-identity-and-context-contract.md) |
| [design/LEVEL_CROSSING_FOUNDATION_V1.md](design/LEVEL_CROSSING_FOUNDATION_V1.md) | Approved design for Level-Crossing Foundation v1 (Milestone AC): the audit establishing that no crossing logic existed, twelve architecture alternatives against eighteen criteria, eight level models, the crossing/equality/gap/outside-bar/lifecycle policies, the ordering and prefix-stability contracts, and 25 reproducible experiments | Design — implemented by [ADR-0019](adr/ADR-0019-level-crossing-foundation-v1.md) |
| [reviews/LEVEL_CROSSING_FOUNDATION_V1_REVIEW.md](reviews/LEVEL_CROSSING_FOUNDATION_V1_REVIEW.md) | Independent review of Level-Crossing Foundation v1, re-derived from production code: 45 adversarial cases, 38 mutation probes, four performance shapes, and the one P1 it found — an event ordering key that depended on the host's time zone and was not total for far-future timestamps | Review record — 1 P1 and 2 P2 found and fixed; no P0 |
| [design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md](design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md) | Approved design for Break of Structure Foundation v1 (Milestone AD): the targeted audit that found BOS needs levels *and* crossings but no candle, the missing confirmation-delay primitive and its measured prefix-instability, the five conjuncts of a break, and 14 reproducible experiments | Design — implemented by [ADR-0020](adr/ADR-0020-break-of-structure-foundation-v1.md) |
| [design/CHOCH_FOUNDATION_V1.md](design/CHOCH_FOUNDATION_V1.md) | Approved design for Change of Character Foundation v1 (Milestone AE): the audit conclusion that BOS already supplies every primitive CHoCH needs, the finding that ADR-0020 §7's adjacency sketch infers a change from an ordering the layer below refuses to read as temporal, the four conjuncts, the twelve-row transition table, the two-step prefix-stability proof, and 17 reproducible experiments | Design — implemented by [ADR-0021](adr/ADR-0021-change-of-character-foundation-v1.md) |
| [design/STRUCTURAL_FACT_SHEET_V1.md](design/STRUCTURAL_FACT_SHEET_V1.md) | Approved design for Structural Fact Sheet v1 (Milestone AF — First Light): the measured two-island split, why ADR-0020 D1's real fix is a separate milestone and why a `structural_levels` parameter would be a fake fix, the single-source containment, the nearest-above/below naming decision, and the stage-attributed performance profile | Design — implemented by [ADR-0022](adr/ADR-0022-structural-fact-sheet-composition-root.md) |
| [design/MULTI_TIMEFRAME_FACT_SHEET_V1.md](design/MULTI_TIMEFRAME_FACT_SHEET_V1.md) | Approved design for Multi-Timeframe Fact Sheet v1 (Milestone AG): the measured single-timeframe hazard, composition over AF with no new engine, why no cross-timeframe synthesis is emitted, per-view staleness, the six test-enforced invariants, and the stage-attributed performance profile | Design — implemented by [ADR-0023](adr/ADR-0023-multi-timeframe-composition.md) |
| [reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md](reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md) | Independent review of Multi-Timeframe Fact Sheet v1: no-synthesis verified against the live class, D1 containment proved by object identity across three views, 42 mutation probes, adversarial inputs, and two P2s — 26 lines of renderer duplication and an untested row order — plus a methodological defect in the mutation harness itself (stale bytecode) | Review record — no P0, no P1, two P2 found and fixed, three P3 |
| [design/CONFIRMATION_DELAY_PROVENANCE_V1.md](design/CONFIRMATION_DELAY_PROVENANCE_V1.md) | Approved design for Confirmation-Delay Provenance v1 (Milestone AH): why storing the window on `LevelOrigin` alone would have relocated the hazard rather than removed it, why `eligible_from` is derived and not stored, why the property is named `knowable_from`, why no compatibility path is safe, what became unrepresentable, and the 80-site AST-positioned migration | Design — implemented by [ADR-0024](adr/ADR-0024-confirmation-delay-provenance.md) |
| [reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md](reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md) | Independent review of Confirmation-Delay Provenance v1: the removal verified against live signatures, correct behaviour proved against a reimplementation of the pre-AH algorithm across 40 seeded series at four windows, 42 mutation probes, and two P2s — a render row indistinguishable while `L=R`, and a rejection message asserted only by substring — plus one probe reported as a **proven equivalent mutant** rather than rounded to zero | Review record — no P0, no P1, two P2 found and fixed, three P3 |
| [design/MARKET_REGIME_ENGINE_V1.md](design/MARKET_REGIME_ENGINE_V1.md) | Approved design for Market Regime Engine v1 (Milestone AI): the v2 post-mortem read as a specification, why regime is the environment and never a direction, why evidence votes by family, why a threshold band is one number, the narrow input boundary chosen over three fact-sheet candidates, and the twelve test-enforced invariants | Design — implemented by [ADR-0025](adr/ADR-0025-market-regime-engine-v1.md) |
| [reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md](reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md) | Independent review of Market Regime Engine v1: direction bias, forced classification and double-counting each checked against live code, 45 mutation probes of which seven first-run survivors were all real test gaps, adversarial inputs, and four P2s — a direction printed in the evidence, a provenance field typed `Any`, a validation order raising the wrong exception, and an assertion that could never fail | Review record — no P0, no P1, four P2 found and fixed, three P3 |
| [design/SWING_WORKSPACE_V1.md](design/SWING_WORKSPACE_V1.md) | Approved design for Swing Trading Workspace v1 (Milestone AK): the third stranded island measured, why the workspace is an object rather than a command, why an unbuilt section is rendered with an owner and a prohibition, why conflict detection may report but never resolve, the free evidence join through `Observation.key`, and the twelve test-enforced invariants | Design — no ADR required; follows the Milestone AJ architecture |
| [reviews/SWING_WORKSPACE_V1_REVIEW.md](reviews/SWING_WORKSPACE_V1_REVIEW.md) | Independent review of Swing Trading Workspace v1: composition-not-computation verified by AST, reachability of three previously-unimported packages, 49 mutation probes of which **twelve first-run survivors were all real assertion gaps against 100 % line coverage**, and five P2s — order-dependent conflicts, a mislabelled levels section, four page-width overruns, a factually wrong coverage label, and an ADR-0009 import violation | Review record — no P0, no P1, five P2 found and fixed, three P3 |
| [design/DECISION_CONTEXT_V1.md](design/DECISION_CONTEXT_V1.md) | Approved design for Decision Context Engine v1 (Milestone AL): the Phase-1 evidence that a 12-candle page and a 260-candle page rendered alike, why the engine invents no threshold, why conflicts never reduce sufficiency, and the ten test-enforced invariants | Design — implemented by [ADR-0026](adr/ADR-0026-decision-context-boundary.md) |
| [reviews/DECISION_CONTEXT_V1_REVIEW.md](reviews/DECISION_CONTEXT_V1_REVIEW.md) | Independent review of Decision Context Engine v1: the milestone's own justification re-verified, 43 mutation probes of which **eleven first-run survivors were real assertion gaps against 100 % line coverage**, and two P2s — `may_continue` contradicting its own state under a strict policy, and an export collision the repository's guard caught | Review record — no P0, no P1, two P2 found and fixed, three P3 |
| [design/DETERMINISTIC_DAILY_WORKFLOW_V1.md](design/DETERMINISTIC_DAILY_WORKFLOW_V1.md) | Approved design for Deterministic Daily Workflow v1 (Milestone AN): the measured cost of a one-symbol-at-a-time product, why a run is an object, why the rows are **never sorted** — a sorted list is a claim — why `INSUFFICIENT` and `FAILED` must stay different things, why a defect is never converted into a market failure, the measured case for sequential execution (compute is 1.4 % of wall clock), and the thirteen test-enforced invariants | Design — no ADR required; composes AK and AL under ADR-0007 |
| [reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md](reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md) | Independent review of Deterministic Daily Workflow v1: 81 mutation probes of which **five first-run survivors and three no-ops were all real gaps against 100 % line coverage**, and two P2s — a page printing `2026-08-04T08:0` because a value overflowed its column and the row's truncation cut a *different* value in half, and a run recording intervals it had not used | Review record — no P0, no P1, two P2 found and fixed, one P3 fixed, three P3 documented |
| [design/MEMORY_AND_DECISION_ARCHIVE_V1.md](design/MEMORY_AND_DECISION_ARCHIVE_V1.md) | Approved design for Memory & Decision Archive v1 (Milestone AO): what a codec must handle given `Workspace`/`DailyRun` are presentation-shaped, the import-direction guard with its one necessary exception (`pipeline/cli.py`), the twelve test-enforced invariants, and the test-file-per-concern strategy | Design — implemented by [ADR-0027](adr/ADR-0027-memory-and-decision-archive-persistence-schema.md) |
| [reviews/MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW.md](reviews/MEMORY_AND_DECISION_ARCHIVE_V1_REVIEW.md) | Independent review of Memory & Decision Archive v1: a fresh adversarial pass against the milestone's own 20-item review checklist found **three P1s, all in `archive verify` itself** — an unsupported payload schema version decoding silently, a forged `record_id` undetected because nothing recomputed it from content, and a hand-edited manifest field never cross-checked against the record it describes — all three fixed and independently regression-tested; 34/35 mutation probes detected after the fix, 1 proven-equivalent, 0 no-ops | Review record — no P0, three P1 found and fixed, one P2 found and fixed, two P3 |
| [design/TRADING_DOMAIN_ARCHITECTURE_V1.md](design/TRADING_DOMAIN_ARCHITECTURE_V1.md) | Proposed architecture for the trading domain (Milestone AP — **architecture only, no implementation**), v1.2 after a hostile architecture review and a vision-alignment pass: the five-object decision chain (Opportunity Proposal → Trade Plan → Order → Trade → Position) and why collapsing any adjacent pair erases a measurable behaviour, the proposal's **append-only lifecycle** that separates owner assertion from deterministic market fact and keeps rejected, expired, invalidated and entered-anyway proposals scoreable, a hypothetical-outcome type with no money field so a counterfactual can never become fictional P&L, the append-only ledger with balance effects *derived* rather than stored, the freezing policy separating captured artifacts from rebuildable projections, the Decision Episode that lets long-term holdings and no-trade decisions enter the learning corpus without forcing R-multiple, the **Portfolio Intelligence boundary** — three strata and one deterministic constraint check, no score and no invented thresholds — the one AI retrieval contract, a three-kind low-friction journal with tag provenance, **Personal AI Memory** as evidence-linked versioned insights the owner alone may confirm, the Swedish tax **capture** contract that must hold from the first transaction even though the engine ships much later, one durable store with measured thresholds for anything more, a two-scenario stress test, 42 rejected alternatives, and the six ADRs required before any code | **Design proposal — not authorization to implement.** Names AP-D1…AP-D6 (AP-D2 blocking); resolves backlog D-02 and D-04 in substance. §34 dispositions every review finding — including two rejected — and states what was deliberately not added |
| [reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md](reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md) | Independent review of Structural Fact Sheet v1: the D1 hazard quantified over 1,500 mismatched calls (36.1 % materially different breaks, zero errors), cross-process determinism, 39 mutation probes, adversarial inputs, and the one P2 — a render branch no fixture reached | Review record — no P0, no P1, one P2 found and fixed, four P3 documented |
| [reviews/CHOCH_FOUNDATION_V1_REVIEW.md](reviews/CHOCH_FOUNDATION_V1_REVIEW.md) | Independent review of Change of Character Foundation v1, re-derived from production code: adversarial cases, 59 mutation probes, measured scaling to 100,000 breaks, and a from-scratch re-derivation of the superseded-sketch finding | Review record — no P0, no P1, no P2; three P3 documented |
| [reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md](reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md) | Independent review of Break of Structure Foundation v1, re-derived from production code: 48 adversarial cases, 42 mutation probes, instrumented complexity measurement, and the one P2 it found — a reference lookup that was linear per crossing, at 125M inner iterations | Review record — 1 P2 and 1 P3 found and fixed; no P0 or P1 |
| [reviews/SERIES_IDENTITY_CONTEXT_CONTRACT_V1_REVIEW.md](reviews/SERIES_IDENTITY_CONTEXT_CONTRACT_V1_REVIEW.md) | Independent review of Milestone AB before merge: all counts, exports and mutation results re-derived from production code, plus the twenty adversarial identity cases; one P2 found and fixed (an empty-but-valid contextual series was falsy), no P0/P1, two P3s recorded | Review — verification |
| [reviews/TREND_FOUNDATION_REVIEW_V1.md](reviews/TREND_FOUNDATION_REVIEW_V1.md) | Independent review of Milestone AA before merge: all counts, exports, stability figures and mutation results re-derived from scratch against the shipped code; one P1 found and fixed (a headline prefix-stability figure measured trend values while being documented as measuring the guarantee), no P0, three P3s recorded | Review — verification |
| [reviews/STRUCTURAL_SEQUENCE_STATE_HISTORY_REVIEW_V1.md](reviews/STRUCTURAL_SEQUENCE_STATE_HISTORY_REVIEW_V1.md) | Independent review of Milestones Z0-Z1 before merge: re-derived claims, mutation review, P0-P3 findings | **Authoritative — Z0/Z1 acceptance** |
| [reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md](reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) | Audit of the complete deterministic market-structure foundation (ADR-0012…0015) at commit `1154622`: contract-ownership map, stability semantics, P0–P4 findings, recommended next milestone | **Authoritative — market-structure readiness** |
| [RVE_DESIGN_V1.md](RVE_DESIGN_V1.md) | Relative Value Engine technical design (Milestones J/K/L): contracts, public API, interactions, decisions RV-1…RV-11 | Design proposal — not authorization to implement |
| [REPOSITORY_MAP.md](REPOSITORY_MAP.md) | What each directory is for, and its allowed/forbidden dependencies | Reference — current repo |
| [development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md](development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md) | AI model-selection and session-cost policy: Sonnet as default, the four cases that justify Opus, per-task model declaration, `/clear` vs `/compact` boundaries | **Authoritative — AI workflow and cost** |
| [AI_HANDOFF/START_HERE_FOR_AI.md](AI_HANDOFF/START_HERE_FOR_AI.md) | Onboarding + non-negotiable rules for AI agents | Reference — workflow |
| [AI_HANDOFF/CURRENT_STATE.md](AI_HANDOFF/CURRENT_STATE.md) | Snapshot of the repository today (updated every milestone) | **Reference — current state** |
| [../PROJECT_SPECIFICATION_V1.md](../PROJECT_SPECIFICATION_V1.md) | Original vision, principles, priorities | **Authoritative — vision** |
| [../PROJECT_VISION_ADDENDUM_V1.md](../PROJECT_VISION_ADDENDUM_V1.md) | Vision update (Core Modules list) | **Authoritative — vision** |
| [CURRENT_SYSTEM_AUDIT_V1.md](CURRENT_SYSTEM_AUDIT_V1.md) | Historical audit of the pre-code repository state | Historical record |
| [SETUP.md](SETUP.md) | TradingView MCP + local setup | Operational |
| [analysis-notes.md](analysis-notes.md) | v2→v3 swing-analyzer bias post-mortem | Historical record |

---

## Reading order

**New human developer:**
1. This README.
2. [AI_HANDOFF/CURRENT_STATE.md](AI_HANDOFF/CURRENT_STATE.md) — what exists today.
3. [REPOSITORY_MAP.md](REPOSITORY_MAP.md) — where things live.
4. [ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) — where things are going.
5. The source in `src/fmis/` and its tests in `tests/`.

**Future AI coding agent:**
1. [AI_HANDOFF/START_HERE_FOR_AI.md](AI_HANDOFF/START_HERE_FOR_AI.md) — rules first.
2. [AI_HANDOFF/CURRENT_STATE.md](AI_HANDOFF/CURRENT_STATE.md) — current snapshot.
3. [ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) — authoritative boundaries.
4. [REPOSITORY_MAP.md](REPOSITORY_MAP.md) — dependency rules per directory.

---

## Documentation philosophy

**Milestone documentation.** Development proceeds in small, reviewable milestones (roughly one
implementation → audit → commit → push cycle each). Milestones are lettered (A, B, C, …); the current
one and the completed ones are tracked in [CURRENT_STATE.md](AI_HANDOFF/CURRENT_STATE.md), which is the
snapshot updated after every milestone. Roadmap milestones (H onward) are specified in the architecture
document.

**Architecture Decision Records (ADR) philosophy.** Significant architectural choices are recorded with
their alternatives and trade-offs so future readers understand *why*, not just *what*. These live in two
places, both authoritative: the decision table in
[ARCHITECTURE_AND_ROADMAP_V1.md §12](ARCHITECTURE_AND_ROADMAP_V1.md) (decisions D1–D11), and the
[adr/](adr/README.md) directory for decisions that need more than a table row. Nothing in §12 was
migrated retroactively; new significant decisions are written as ADRs. See
[adr/README.md](adr/README.md) for the conventions.

**Testing philosophy.** Every deterministic calculation is verified against **independently derived**
expected values — hand calculations, arithmetic means, or exact rational arithmetic (`fractions`) —
never against the output of the implementation under test. Warm-up boundaries are tested on both sides
(exactly-enough vs one-short). The suite must stay green at every commit.

**Deterministic-first philosophy.** If a value can be computed objectively, code computes it —
deterministically, reproducibly, from closed candles only, with explicit warm-up and insufficient-data
states, and with provenance recorded in metadata. Low-level features never emit opinions
(no "bullish", no scores, no trades).

**AI role vs the deterministic engine.** The deterministic engine produces *facts*. The AI layer
(a **Planned** future layer — not yet implemented) *interprets* those facts: weighing conflicting
evidence, framing scenarios, constructing the strongest opposing case, and expressing uncertainty. AI
never computes what code can compute, and never overrides a deterministic fact. This separation is the
core discipline of the project.

---

## One-line orientation

> Read [START_HERE_FOR_AI.md](AI_HANDOFF/START_HERE_FOR_AI.md) (rules) and
> [CURRENT_STATE.md](AI_HANDOFF/CURRENT_STATE.md) (snapshot) before changing anything; treat
> [ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) as authoritative for boundaries.
