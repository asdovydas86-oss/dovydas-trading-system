# Operational Reports

Index of the project's operational reports: audits, design records, implementation records,
reviews, and any other point-in-time analysis produced while working on this repository.

## Purpose

This directory is the single home for **operational reports** — dated, numbered, immutable
records of work performed on the repository.

It is deliberately separate from `docs/`:

| Directory | Holds | Nature |
|---|---|---|
| `docs/` | ADRs, design documents, architecture, review records for milestones | The project's **standing** documentation — maintained and updated over time |
| `reports/` | Audits, analyses, and operational reports | **Point-in-time** records — written once, kept as-is |

A report describes the repository *as it was* at a given commit. It is not revised when the code
moves on; a later report supersedes it instead.

## Filename convention

```
NNNN_YYYY-MM-DD_DESCRIPTIVE_TITLE.md
```

- `NNNN` — zero-padded, four-digit report number
- `YYYY-MM-DD` — the date the report was produced
- `DESCRIPTIVE_TITLE` — uppercase snake case

Examples:

```
0001_2026-07-31_REPOSITORY_AUDIT.md
0002_2026-08-01_LEVEL_ORIGIN_DESIGN.md
0003_2026-08-01_LEVEL_ORIGIN_IMPLEMENTATION.md
0004_2026-08-01_LEVEL_ORIGIN_REVIEW.md
```

## Numbering rules

- Numbering is **global and sequential across all report types** — design, implementation, review
  and audit reports draw from one shared counter.
- A number is **never reused and never overwritten**, including for reports that are later
  archived, superseded, or withdrawn.
- Every new report **must** be added to the index table below in the same change that creates it.
- Reports are **never deleted** unless the user explicitly authorizes deletion.
- Do **not** create generic `REPORT.md` files in the repository root.

**Next available report number: `0012`**

## Metadata header

Each report should open with a short metadata table:

| Field | Value |
|---|---|
| **Report number** | 0001 |
| **Title** | Repository Audit |
| **Date** | 2026-07-31 |
| **Report type** | Audit |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `d132cea` |
| **Status** | Final |

`Status` is one of: `Draft`, `Final`, `Superseded`, `Archived`.

## Index

| # | Date | Type | Title | Status | Branch / Commit | File |
|---|---|---|---|---|---|---|
| 0011 | 2026-08-08 | Implementation | Swing Setup Historical Backtest Harness V1 — Implementation Record | Final | `main` / uncommitted (base `35bce7a`) | [0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md](0011_2026-08-08_SWING_SETUP_BACKTEST_V1_IMPLEMENTATION.md) |
| 0010 | 2026-08-07 | Implementation | Market Scanner Intelligence Report V1 — Implementation Record | Final | `main` / uncommitted (base `81a6202`) | [0010_2026-08-07_MARKET_SCANNER_INTELLIGENCE_REPORT_V1_IMPLEMENTATION.md](0010_2026-08-07_MARKET_SCANNER_INTELLIGENCE_REPORT_V1_IMPLEMENTATION.md) |
| 0009 | 2026-08-07 | Implementation | Market Scanner V1 — Implementation Record | Final | `main` / uncommitted (base `9977274`) | [0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md](0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md) |
| 0008 | 2026-08-04 | Audit | Documentation Consistency Audit | Final | `main` / `36f5a30` | [0008_2026-08-04_DOCUMENTATION_CONSISTENCY_AUDIT.md](0008_2026-08-04_DOCUMENTATION_CONSISTENCY_AUDIT.md) |
| 0007 | 2026-08-02 | Readiness Check | Implementation Readiness Check | Final | `main` / `d132cea` + uncommitted AF | [0007_2026-08-02_IMPLEMENTATION_READINESS_CHECK.md](0007_2026-08-02_IMPLEMENTATION_READINESS_CHECK.md) |
| 0006 | 2026-08-02 | Architecture Gate | Milestone AF Architecture Gate | Final | `main` / `d132cea` + AF | [0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md](0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) |
| 0005 | 2026-08-01 | Development Roadmap | FMITS Development Roadmap 2026–2027 | Final | `main` / `d132cea` | [0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md](0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md) |
| 0004 | 2026-08-01 | Business & Capability Architecture | FMITS Business & Capability Architecture V1 | Final | `main` / `d132cea` | [0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md](0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) |
| 0003 | 2026-08-01 | Architecture Blueprint | FMITS Architecture Blueprint V1 | Final | `main` / `d132cea` | [0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md](0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) |
| 0002 | 2026-07-31 | Master Map | FMITS Master Map V1 | Final | `main` / `d132cea` | [0002_2026-07-31_FMITS_MASTER_MAP.md](0002_2026-07-31_FMITS_MASTER_MAP.md) |
| 0001 | 2026-07-31 | Audit | Repository Audit | Final | `main` / `d132cea` | [0001_2026-07-31_REPOSITORY_AUDIT.md](0001_2026-07-31_REPOSITORY_AUDIT.md) |

## Document series

Some reports form a sequence and are best read in order. Later reports in a series never modify
earlier ones — they extend them, and record any differences explicitly.

**Architecture series** — the standing architectural reference:

| Read | Report | Answers |
|---|---|---|
| 1st | [0001 — Repository Audit](0001_2026-07-31_REPOSITORY_AUDIT.md) | What is the code? |
| 2nd | [0002 — FMITS Master Map](0002_2026-07-31_FMITS_MASTER_MAP.md) | What is the system? |
| 3rd | [0003 — Architecture Blueprint V1](0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) | How does it work as one architecture? |
| 4th | [0004 — Business & Capability Architecture V1](0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) | Why does it exist, and what must it let the user do? |
| 5th | [0005 — Development Roadmap 2026–2027](0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md) | What do we build next, in what order, and when does each capability become usable? |
| 6th | [0006 — Milestone AF Architecture Gate](0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md) | Which single milestone is built next, and is planning finished? |
| 7th | [0007 — Implementation Readiness Check](0007_2026-08-02_IMPLEMENTATION_READINESS_CHECK.md) | Is the repository actually ready to build it? |

For authority when documents disagree, see Appendix B of report 0002.

## Report summaries

One paragraph per report. Migrated here from a root `REPORT.md` that was deleted under explicit
authorization on 2026-08-02, because a generic root report file contradicts the numbering policy
above. This section is the single index; there is no root-level equivalent.

### 0001 — Repository Audit

**Date:** 2026-07-31 · **Type:** Audit · **File:** [`0001_2026-07-31_REPOSITORY_AUDIT.md`](0001_2026-07-31_REPOSITORY_AUDIT.md)

A complete read-only audit of the repository as code: structure, modules, dependency graph, dead and
duplicated files, TODO inventory, documentation drift, git state, and testing architecture. It found
the codebase in unusually good health — 11,128 lines across 17 packages, 3,221 tests passing in 3.84
seconds, 96 % measured line coverage, **zero circular dependencies** across a six-layer graph, zero
runtime dependencies, and a design→implement→review branch discipline followed without exception for
83 commits. Every instance of duplication it found was deliberate and argued for in a docstring; there
are no `FIXME`s, no `XXX`s and no hacks. Its substantive findings were that `fmis.evidence` is a
fully-built, fully-tested module with **no production consumer** while `decision_support` independently
owns the same concept; that the root `README.md` and the "authoritative" architecture document had
fallen roughly two months behind the ADRs; and that the entire safety net is manual — no CI, no type
checker, no coverage tooling, no tags. It closes with the five highest-value architectural
improvements.

### 0002 — FMITS Master Map V1

**Date:** 2026-07-31 · **Type:** Master Map · **File:** [`0002_2026-07-31_FMITS_MASTER_MAP.md`](0002_2026-07-31_FMITS_MASTER_MAP.md)

The definitive answer to *what is FMITS?*, mapping the entire project by domain: mission, philosophy,
principles, product vision, system context, **70 domains across 7 groups**, 20 user-facing products,
the data map, the user journey, and explicit scope boundaries. Every domain carries purpose,
responsibilities, inputs, outputs, dependencies, future expansion, maturity — and a **source tag**
separating approved vision from repository fact from proposal from items with no source at all, so
that nothing in the mission brief was silently promoted into project vision. It records that three
named source documents (`MASTER_PROJECT_CONTEXT`, `MASTER_PROJECT_CONTEXT_TRANSFER`, "Financial OS
Vision") exist in neither the repository nor Google Drive. Its central finding — §15 — is that FMITS
is currently two disconnected systems: a rigorously tested library that analyzes no markets, and a
199-line TradingView prompt that analyzes markets every day and uses none of it. Independent
recommendations are fenced into their own section.

### 0003 — FMITS Architecture Blueprint V1

**Date:** 2026-08-01 · **Type:** Architecture Blueprint · **File:** [`0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md`](0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md)

The technical architecture reference, reorganizing the same system from a domain axis to a **layer
axis**: twelve layers plus a cross-cutting platform, each with purpose, inputs, outputs, dependencies
and future evolution, with dependencies pointing downward only. It maps the canonical 22-stage
analysis pipeline stage-by-stage onto layers and modules (7 implemented, 1 in progress, 1 planned, 11
future, 2 blocked), defines the four AI boundaries — where deterministic computation ends, where
humans stay in control, where automation begins, and the autonomy line that is not crossed — and
**verifies that the deterministic core is already asset-agnostic**, deriving the *Three Admission
Points* rule that keeps it so. Its headline finding, obtained from the executable import graph, is a
second split *inside* the library: `fmis` is two islands sharing only the kernel with **zero edges
between them**, and the structure island — 5,695 LOC, **51.2 % of the codebase** — has no provider
path and no consumer. The fix is one additive composition root.

### 0004 — FMITS Business & Capability Architecture V1

**Date:** 2026-08-01 · **Type:** Business & Capability Architecture · **File:** [`0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md`](0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md)

The capability reference, starting from Dovydas's actual financial-market activities rather than from
code: mission architecture, user model, **184 operational capabilities across 19 business
capabilities**, 15 end-to-end workflows, 31 product surfaces, the Global Market Pulse and Buying Power
specifications, 17 business rules with their true enforcement state, a capability dependency map, and
a nine-level value ladder from *tested library only* to *bounded autonomy*. It defines v1 explicitly
(Value Level 3 — a daily market-intelligence workflow) so that "before or after v1" means something,
and it separates every statement into approved intent, verified capability, architectural implication,
independent recommendation, or open question. Its headline is that **6 of 184 capabilities are
implemented**, one of fifteen workflows partially operates — through a prompt — and two of nine of the
project's own success criteria are met. Its practical conclusion, reached from user value and
converging on Report 0003's conclusion from the dependency graph, is the **deterministic fact sheet**:
the smallest slice that makes the unreachable half of the codebase useful, requiring no new engine, no
AI, no persistence and no interface.

### 0005 — FMITS Development Roadmap 2026–2027

**Date:** 2026-08-01 · **Type:** Development Roadmap · **File:** [`0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md`](0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md)

The execution plan, turning the preceding three architecture documents into ordered work: current
position, **thirteen phases** in four movements, a timeline with best/expected/worst estimates
calibrated against the repository's own measured history, a capability unlock map for 23 named
capabilities, a business value curve, a technical-debt strategy naming twelve shortcuts that must never
be taken, a learning roadmap per phase, the critical path, and a 3–5 year vision. It defines v1 as
Value Level 3 and lands it around late 2026. Its most important structural point is that Phases 11–12
are gated by **calendar time, not developer time** — a shadow run takes months regardless of how fast
the code is written. §11 recommends exactly one next milestone: the **deterministic fact sheet**,
reached from user value and converging with Report 0003's dependency-graph conclusion.

### 0006 — Milestone AF Architecture Gate

**Date:** 2026-08-02 · **Type:** Architecture Gate · **File:** [`0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md`](0006_2026-08-02_MILESTONE_AF_ARCHITECTURE_GATE.md)

The architecture gate that follows Milestone AF, deciding one thing: the single highest-value
milestone to build next. It rejected the proposed **Workspace MVP** on three grounds — the proposal
was defined nowhere in the project record; every charitable reading fails the rule that presentation
must not precede facts; and the single-timeframe fact sheet AF had just shipped **can actively
mislead**, demonstrated live on BTCUSDT reading `sustained_higher` on 1W, `neutral` on 1D and
`sustained_lower` on 4H — precisely the case `PROJECT_SPECIFICATION_V1.md` §5 says must not be
flattened. It recommends **AG — Multi-Timeframe Fact Sheet** instead, verified live to need no new
engine, and supplies a complete implementation contract in §5. It also reverses the report series'
own prior recommendation of ADR-0020 D1, on the reasoning that AF contained that hazard and
multi-timeframe reuses the same composition root. Ends: *Planning phase complete.*

### 0007 — Implementation Readiness Check

**Date:** 2026-08-02 · **Type:** Readiness Check · **File:** [`0007_2026-08-02_IMPLEMENTATION_READINESS_CHECK.md`](0007_2026-08-02_IMPLEMENTATION_READINESS_CHECK.md)

The readiness check performed immediately before Milestone AG, verifying the repository directly
rather than trusting any document. It found Milestone AF **fully implemented and entirely
unversioned** — 3,305 tests passing in the working tree while `HEAD` and `origin/main` both sat at
the pre-AF commit `d132cea`, with 30 uncommitted paths. It answers six questions (implemented yes;
committed, merged, pushed all no), separates critical blockers from recommendations, and concludes
that the next action was not a milestone but `git commit`. It also corrected a figure that could
mislead: 136 public exports measured **after** AF added nine, coinciding by accident with the
pre-AF baseline recorded elsewhere.

### 0008 — Documentation Consistency Audit

**Date:** 2026-08-04 · **Type:** Audit · **File:** [`0008_2026-08-04_DOCUMENTATION_CONSISTENCY_AUDIT.md`](0008_2026-08-04_DOCUMENTATION_CONSISTENCY_AUDIT.md)

A read-only-first consistency pass across every document in `docs/`, `reports/`, and the
repository root, before resuming feature work on Milestone AO. Found the root `README.md` never
mentioned FMITS or `src/fmis/` at all, describing a pre-FMITS scaffold; `ARCHITECTURE_AND_ROADMAP_V1.md`
— required reading per `docs/README.md`'s onboarding order — frozen at a 147-test baseline with
status tags wrong for several shipped modules and no notice pointing readers at what superseded it;
and two ADRs (0020, 0023) missing forward pointers to the later ADR that closed the hazard they
describe as open. Also found, but left unfixed as explicitly out of scope for a documentation-only
pass: `CURRENT_STATE.md` and `FMITS_PRODUCT_BACKLOG.md` both claim Milestone AN is unpushed when five
further commits have since landed and pushed, and `FMITS_PRODUCT_CHANGELOG.md` §5 still lists AN as
unreleased against its own §3/§4. Zero broken links found across 79 markdown files. Fixed six files
with additive staleness banners and one extended index table; recommended, but did not attempt,
trimming `CURRENT_STATE.md`'s ~900 lines of full historical milestone narrative as the largest
unrealized reading-cost saving in the repository.

## Implementation milestones executed from these reports

Reports produce contracts; milestones deliver product. This table links each executed milestone to
its technical records in `docs/`. The current implementation state always lives in
[`../docs/AI_HANDOFF/CURRENT_STATE.md`](../docs/AI_HANDOFF/CURRENT_STATE.md), refreshed every milestone.

| Milestone | What it delivered | Records |
|---|---|---|
| **AF — First Light** | Connected the deterministic structural chain to real market data: a second composition root in `fmis.pipeline`, a single-timeframe deterministic fact sheet, and the repository's first product surface (`fmits facts SYMBOL`). No new engine. ADR-0020 D1 contained, not fixed | [ADR-0022](../docs/adr/ADR-0022-structural-fact-sheet-composition-root.md) · [design](../docs/design/STRUCTURAL_FACT_SHEET_V1.md) · [review](../docs/reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md) |
| **AG — Multi-Timeframe Fact Sheet v1** | A third composition root calling the AF root once per timeframe role (CONTEXT/SETUP/EXECUTION); no cross-timeframe synthesis. `fmits mtf SYMBOL`. Implementation contract was report 0006 §5 | [ADR-0023](../docs/adr/ADR-0023-multi-timeframe-composition.md) · [design](../docs/design/MULTI_TIMEFRAME_FACT_SHEET_V1.md) · [review](../docs/reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md) |
| **AH — Confirmation-Delay Provenance v1** | Closed ADR-0020 D1: the confirmation delay now travels with the origin that earned it, rather than being a separately-supplied argument that could silently disagree with detection | [ADR-0024](../docs/adr/ADR-0024-confirmation-delay-provenance.md) · [design](../docs/design/CONFIRMATION_DELAY_PROVENANCE_V1.md) · [review](../docs/reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md) |
| **AI — Market Regime Engine v1** | The first interpretation-adjacent layer: `fmis.market_regime`, three separate environment dimensions (structure/volatility/participation), never collapsed into a direction. `fmits regime SYMBOL [--multi]` | [ADR-0025](../docs/adr/ADR-0025-market-regime-engine-v1.md) · [design](../docs/design/MARKET_REGIME_ENGINE_V1.md) · [review](../docs/reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md) |
| **AK — Swing Trading Workspace v1** | Made the third stranded dependency island reachable: `fmis.workspace`, eleven sections (unbuilt ones rendered rather than omitted), deterministic conflict detection that never resolves. `fmits swing SYMBOL`. No ADR — no new boundary | [design](../docs/design/SWING_WORKSPACE_V1.md) · [review](../docs/reviews/SWING_WORKSPACE_V1_REVIEW.md) |
| **AL — Decision Context Engine v1** | `fmis.decision_context` answers one question — does this analysis contain enough trustworthy information to continue — and adds a twelfth workspace section; a policy object carrying no numbers | [ADR-0026](../docs/adr/ADR-0026-decision-context-boundary.md) · [design](../docs/design/DECISION_CONTEXT_V1.md) · [review](../docs/reviews/DECISION_CONTEXT_V1_REVIEW.md) |
| **AN — Deterministic Daily Workflow v1** | The first capability answering about more than one symbol: `fmis.daily`, a per-symbol error-isolated sequential runner, a readiness index that is never a ranking. `fmits daily SYMBOL...`. No ADR — no new boundary | [design](../docs/design/DETERMINISTIC_DAILY_WORKFLOW_V1.md) · [review](../docs/reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md) |
| **AT — Market Scanner v1** | The first market scanner: `fmis.swing_setup.scan`, a hardcoded twenty-symbol watchlist run through the existing Swing Setup Engine (AR) with per-symbol failure isolation, rendered as one compact table. No new engine, no ranking, no ADR | [design](../docs/design/MARKET_SCANNER_V1.md) · [review](../docs/reviews/MARKET_SCANNER_V1_REVIEW.md) · [report 0009](0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md) |
| **AU — Market Scanner Intelligence Report v1** | `fmis.swing_setup.scan_report`, a second, presentation-only renderer over AT's own scan result: scan summary, market overview, actionable CONFIRMED/CANDIDATE setups with verbatim reasons, and WAIT results grouped by reason. `fmits scan` now defaults to it; `--table` keeps AT's table. No new engine, no ranking, no ADR | [design](../docs/design/MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md) · [review](../docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md) · [report 0010](0010_2026-08-07_MARKET_SCANNER_INTELLIGENCE_REPORT_V1_IMPLEMENTATION.md) |

## Archive policy

- **Active and recent reports stay directly in `reports/`.**
- Older reports — superseded, or no longer relevant to current work — may be moved into
  [`archive/`](archive/). This is a housekeeping move, not a deletion.
- An archived report **keeps its number, its filename, and its row in the index table above**.
  Only its file link changes, to `archive/NNNN_...md`, and its `Status` becomes `Archived`
  (or `Superseded`, naming the report that replaced it).
- Archiving is never automatic. Move a report only when asked, or when a newer report explicitly
  supersedes it.
- Nothing is ever deleted from `reports/` or `reports/archive/` without explicit authorization.
