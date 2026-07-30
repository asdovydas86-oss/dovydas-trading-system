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
| [reviews/TREND_FOUNDATION_REVIEW_V1.md](reviews/TREND_FOUNDATION_REVIEW_V1.md) | Independent review of Milestone AA before merge: all counts, exports, stability figures and mutation results re-derived from scratch against the shipped code; one P1 found and fixed (a headline prefix-stability figure measured trend values while being documented as measuring the guarantee), no P0, three P3s recorded | Review — verification |
| [reviews/STRUCTURAL_SEQUENCE_STATE_HISTORY_REVIEW_V1.md](reviews/STRUCTURAL_SEQUENCE_STATE_HISTORY_REVIEW_V1.md) | Independent review of Milestones Z0-Z1 before merge: re-derived claims, mutation review, P0-P3 findings | **Authoritative — Z0/Z1 acceptance** |
| [reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md](reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) | Audit of the complete deterministic market-structure foundation (ADR-0012…0015) at commit `1154622`: contract-ownership map, stability semantics, P0–P4 findings, recommended next milestone | **Authoritative — market-structure readiness** |
| [RVE_DESIGN_V1.md](RVE_DESIGN_V1.md) | Relative Value Engine technical design (Milestones J/K/L): contracts, public API, interactions, decisions RV-1…RV-11 | Design proposal — not authorization to implement |
| [REPOSITORY_MAP.md](REPOSITORY_MAP.md) | What each directory is for, and its allowed/forbidden dependencies | Reference — current repo |
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
