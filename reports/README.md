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

**Next available report number: `0041`**

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
| 0014 | 2026-08-12 | Implementation | Trade Domain Foundation (Milestone BH) — Implementation Record | Final | `main` / uncommitted (base `7ced9e2`) | [0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md](0014_2026-08-12_TRADE_DOMAIN_FOUNDATION_IMPLEMENTATION.md) |
| 0015 | 2026-08-12 | Implementation | Trade Repository & Journal Engine (Milestone BI) — Implementation Record | Final | `main` / uncommitted (base `c96c3e4`) | [0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md](0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md) |
| 0016 | 2026-08-12 | Implementation | Daily Trading Workspace MVP (Milestone BJ) — Implementation Record | Final | `main` / uncommitted (base `dbc4765`) | [0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md](0016_2026-08-12_DAILY_TRADING_WORKSPACE_MVP_IMPLEMENTATION.md) |
| 0017 | 2026-08-13 | Implementation | Trade Capture & Decision Recording (Milestone BK) — Implementation Record | Final | `main` / uncommitted (base `dbc4765`) | [0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md](0017_2026-08-13_TRADE_CAPTURE_AND_DECISION_RECORDING_IMPLEMENTATION.md) |
| 0018 | 2026-08-14 | Implementation | Portfolio Intelligence & Risk Engine (Milestone BL) — Implementation Record | Final | `main` / uncommitted (base `dbc4765`) | [0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md](0018_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_IMPLEMENTATION.md) |
| 0019 | 2026-08-14 | Hostile Review | Portfolio Intelligence & Risk Engine (Milestone BL) — Hostile Review | Final | `main` / uncommitted (base `dbc4765`) | [0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md](0019_2026-08-14_PORTFOLIO_INTELLIGENCE_AND_RISK_ENGINE_HOSTILE_REVIEW.md) |
| 0020 | 2026-08-14 | Implementation | Market Snapshot & Price Integration (Milestone BM) — Implementation Record | Final | `main` / uncommitted (base `dbc4765`) | [0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md](0020_2026-08-14_MARKET_SNAPSHOT_AND_PRICE_INTEGRATION_IMPLEMENTATION.md) |
| 0021 | 2026-08-15 | Implementation | Position Sizing & Trade Approval Engine (Milestone BN) — Implementation Record | Final | `main` / `b66a88f` | [0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md](0021_2026-08-15_POSITION_SIZING_AND_TRADE_APPROVAL_IMPLEMENTATION.md) |
| 0022 | 2026-08-16 | Implementation | Paper Trading & Trade Lifecycle Engine (Milestone BO) — Implementation Record | Final | `main` / `e4195fc` | [0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md](0022_2026-08-16_PAPER_TRADING_AND_TRADE_LIFECYCLE_IMPLEMENTATION.md) |
| 0023 | 2026-08-18 | Implementation | Statistics & Performance Engine (Milestone BP) — Implementation Record | Final | `main` / `e1cfad0` | [0023_2026-08-18_STATISTICS_AND_PERFORMANCE_ENGINE_IMPLEMENTATION.md](0023_2026-08-18_STATISTICS_AND_PERFORMANCE_ENGINE_IMPLEMENTATION.md) |
| 0024 | 2026-08-19 | Implementation | Stable Setup Identity (Milestone BG-D1) — Implementation Record | Final | `main` / `2da08b9` | [0024_2026-08-19_SETUP_IDENTITY_IMPLEMENTATION.md](0024_2026-08-19_SETUP_IDENTITY_IMPLEMENTATION.md) |
| 0025 | 2026-08-19 | Implementation | Setup Identity Pipeline Integration (BG-D1b) — Implementation Record | Final | `main` / `2da08b9` | [0025_2026-08-19_SETUP_IDENTITY_PIPELINE_INTEGRATION.md](0025_2026-08-19_SETUP_IDENTITY_PIPELINE_INTEGRATION.md) |
| 0026 | 2026-08-19 | Implementation | Setup Identity Surface Integration (BG-D1c) — Implementation Record | Final | `main` / `2da08b9` | [0026_2026-08-19_SETUP_IDENTITY_SURFACE_INTEGRATION.md](0026_2026-08-19_SETUP_IDENTITY_SURFACE_INTEGRATION.md) |
| 0027 | 2026-08-20 | Implementation | Setup Evidence (Milestone BR) — Implementation Record | Final | `main` / `2059ca7` | [0027_2026-08-20_SETUP_EVIDENCE_IMPLEMENTATION.md](0027_2026-08-20_SETUP_EVIDENCE_IMPLEMENTATION.md) |
| 0028 | 2026-08-20 | Implementation | Setup Evidence (Milestone BR) — Release-Gate Fixes | Final | `main` / `f2cacf5` | [0028_2026-08-20_BR_RELEASE_GATE_FIXES.md](0028_2026-08-20_BR_RELEASE_GATE_FIXES.md) |
| 0029 | 2026-08-20 | Implementation | Swing Decision Workspace v1 (Milestone BS) — `fmits workspace` | Final | `main` / `b6a456c` | [0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md](0029_2026-08-20_SWING_DECISION_WORKSPACE_IMPLEMENTATION.md) |
| 0031 | 2026-08-23 | Implementation | Macro & Cross-Asset Context Foundation (Milestone BU) — `fmits macro` | Final | `main` / `2b30e38` (base `7fbe611`) | [0031_2026-08-23_MACRO_AND_CROSS_ASSET_CONTEXT_IMPLEMENTATION.md](0031_2026-08-23_MACRO_AND_CROSS_ASSET_CONTEXT_IMPLEMENTATION.md) |
| 0030 | 2026-08-22 | Implementation | Global Market Pulse Foundation (Milestone BT) — `fmits pulse` | Final | `main` / uncommitted (base `8ecd822`) | [0030_2026-08-22_GLOBAL_MARKET_PULSE_IMPLEMENTATION.md](0030_2026-08-22_GLOBAL_MARKET_PULSE_IMPLEMENTATION.md) |
| 0032 | 2026-08-24 | Implementation | FMITS Operator Dashboard V0 (Milestone BV) — `fmits dashboard` | Final | `main` / `0f31293` (base `1a73cf8`) | [0032_2026-08-24_OPERATOR_DASHBOARD_V0_IMPLEMENTATION.md](0032_2026-08-24_OPERATOR_DASHBOARD_V0_IMPLEMENTATION.md) |
| 0033 | 2026-08-25 | Implementation + Research | Swing Strategy Laboratory & Historical Replay (Milestone BW) — `fmits research`, `/lab`; the 1W gate measured | Final | `main` / uncommitted (base `d8e1b9e`) | [0033_2026-08-25_SWING_STRATEGY_LABORATORY_IMPLEMENTATION.md](0033_2026-08-25_SWING_STRATEGY_LABORATORY_IMPLEMENTATION.md) |
| 0034 | 2026-08-25 | Implementation + Research | Swing Trade Geometry Research & Policy Candidates (Milestone BX) — `fmits research geometry`, `/geometry`; 13 geometries measured, **no candidate** | Final | `main` / uncommitted (base `f5d59df`) | [0034_2026-08-25_SWING_TRADE_GEOMETRY_RESEARCH.md](0034_2026-08-25_SWING_TRADE_GEOMETRY_RESEARCH.md) |
| 0035 | 2026-08-26 | Implementation + Research | Pre-Registered Swing Geometry Validation & Execution Mechanics (Milestone BY) — sealed pre-registration `a81b6ab8…`, `fmits research validation`, `/validation`; 11 hypotheses on development/validation/holdout, **hypothesis refuted, no candidate** | Final | `main` / uncommitted (base `3598b4c`) | [0035_2026-08-26_PREREGISTERED_SWING_GEOMETRY_VALIDATION.md](0035_2026-08-26_PREREGISTERED_SWING_GEOMETRY_VALIDATION.md) |
| 0036 | 2026-08-26 | Implementation + Research | Swing Thesis Persistence & Exit Mechanics (Milestone BZ) — sealed pre-registration `4d089ff4…`, `fmits research persistence`; post-entry thesis persistence measured and confirmed, 5 exit families on 2 geometries × 3 samples, **all REJECTED, no candidate** | Final | `main` / uncommitted (base `fd1270b`) | [0036_2026-08-26_SWING_THESIS_PERSISTENCE_RESEARCH.md](0036_2026-08-26_SWING_THESIS_PERSISTENCE_RESEARCH.md) |
| 0037 | 2026-08-27 | Implementation + Research | Swing Admission Edge vs Random-Entry Null (Milestone CA) — sealed pre-registration `910cad28…`, `fmits research admission`; 5 matched null families on development/validation/holdout, **NO_EDGE, no candidate**; independent review withdrew the draft's gate-ladder claim and established that the study is underpowered for its own sealed bar, so `NO_EDGE` means "no edge visible at 155 admissions" | Final | `main` / uncommitted (base `21dac05`) | [0037_2026-08-27_SWING_ADMISSION_NULL_MODEL_RESEARCH.md](0037_2026-08-27_SWING_ADMISSION_NULL_MODEL_RESEARCH.md) |
| 0038 | 2026-08-28 | Implementation + Research | Statistical Power & Research Design Foundation (Milestone CB) — `fmis.research_design`, `fmits research design`; prospective/post-hoc separated structurally, cluster-aware resolution, growth-path planning. CA's ~4,800 estimate **REPRODUCED** (4,827) and shown to hold only on the more-symbols path: with 15 symbols fixed the half-width has a floor of 0.33–0.53 ATR and **more years cannot resolve +0.10 ATR at any size**. Verdict `UNDERPOWERED`, binding dimension `cluster_count`; ~467 symbols required | Final | `main` / uncommitted (base `d1735bb`) | [0038_2026-08-28_STATISTICAL_POWER_AND_RESEARCH_DESIGN.md](0038_2026-08-28_STATISTICAL_POWER_AND_RESEARCH_DESIGN.md) |
| 0039 | 2026-08-28 | Implementation + Research | Universe Feasibility & Information Expansion (Milestone CC) — `fmis.universe`, `fmits research universe`, sealed pre-registration `ef6f3950…`; read-only `exchangeInfo` discovery added to the existing Binance adapter. 3,649 instruments → 660 economic assets → **38 eligible**, against CB's 467 required. Crypto co-moves heavily (mean pairwise r 0.604, market factor 62.5 % of variance) but the residual after removing that factor is **indistinguishable from independence**, so dependence was NOT the wall: **598 of 622 depth exclusions are FMITS's own 1,750-day weekly warm-up**, and zero instruments were lost to data quality or liquidity. A post-hoc ceiling over the provider's ENTIRE history reaches only 106 clusters / 1,089 admissions against 467 / 4,823. Verdict **`INFEASIBLE`**, binding constraint `cluster_count`; the feasible question today is ~0.3–0.5 ATR, not 0.10. Universe `PARTIALLY_SURVIVORSHIP_AWARE`. **Independent review performed** (3 reviewers, 16 findings, 2 rejected with evidence): it found the sealed residual scenario is structurally unable to measure residual dependence (demeaning pins it at −1/(K−1) for ANY true value), a latent path to inverting a design parameter from the protected holdout, an ordering control that could not detect an expectancy sort, and a claimed control that did not exist — all fixed, with 39 regressions and 10/10 rule mutants killed. A pre-commit release audit then found 5 more (chiefly that the 0.0023 sensitivity is MARGINAL — 5.9 % over break-even and flips under CB-6's own ±30 % scatter — so only the CONDITIONAL claim is asserted); all fixed. **No measured figure moved and the verdict is unchanged** | Final | `main` / uncommitted (base `c320525`) | [0039_2026-08-28_UNIVERSE_FEASIBILITY_AND_INFORMATION_EXPANSION.md](0039_2026-08-28_UNIVERSE_FEASIBILITY_AND_INFORMATION_EXPANSION.md) |
| 0040 | 2026-09-03 | Research (measurement) | Paired-Effect Dependence Measurement (Milestone CD) — `fmis.paired_dependence`, `fmits research dependence`, sealed pre-registration `28f8ebed…`. Answers the question Milestone CC's estimator structurally could not, and then has **two of its own central claims overturned by independent review**. **First persisted the Milestone BZ capture, which had never been written down** — the missing file behind CB-1, CB-2 and CC-1 — and with it **2,390 observation-level paired differences**. A fresh replay reproduced Milestone CA's counts **and its effects to four decimal places** (246/234 candidates; 155/91/234 matched; −0.2028/−0.3347/−0.5337). One-way random-effects ICC on two named axes: **`rho_w` = −0.0355 [−0.0774, −0.0064]**, bounded near zero, so clustering by symbol costs no information; **`r_b` = +0.1984 [−0.0491, +0.4181]**, positive in **all 15 panels** (+0.095…+0.549) and **all 16 sensitivity cells** (+0.122…+0.514). **CC's central assumption is wrong** — the paired difference does not remove the market factor — but **CD's own first explanation was wrong too and was withdrawn**: the matching radius is a *ceiling* (10–90 days, not 90–360), two families draw a *same-bar* control, and the real cause is that `control_forward` averages 200 draws carrying 2.8 % of the admission leg's variance, leaving `corr(D, admission) = +0.987`. Review also found the **effective-cluster arithmetic overstated ~3×** (arbitrated by simulation: true design effect 1.4266 vs the sealed formula's 3.7446); corrected, the design-relevant `q · r_b` is **+0.037**, still **17×** the `1/K*` = 0.002141 at which the requirement stops being finite, and CC's 38 eligible assets supply **8–23** effective clusters against 467. Verdict **`INCONCLUSIVE`** — the interval spans zero, so 15 assets cannot separate 'no penalty' from 'unreachable at any size'; 5 of 15 panels (all of validation) are **`UNREACHABLE`** outright. **43/43 mutation probes killed** over two campaigns. **Independent review performed and it changed the science**: 3 reviewers, **30 findings, 2 critical**, every one reproduced before acceptance; **9 defects fixed** including a weighted-ICC bug, an observer hook that could have mutated CA's published effect, and **two architecture guards CD had advertised as a strengthening that were circular**; **5 sealed findings disclosed rather than fixed**, each pinned by a test. CA's `NO_EDGE`, CB's `UNDERPOWERED` and CC's `INFEASIBLE` all stand; **CD removes the premise of CC's warm-up-sensitivity recommendation**, and withdrew its own first replacement for it | Final | `main` / one commit on top of `f47cd05` | [0040_2026-09-03_PAIRED_EFFECT_DEPENDENCE_MEASUREMENT.md](0040_2026-09-03_PAIRED_EFFECT_DEPENDENCE_MEASUREMENT.md) |
| 0013 | 2026-08-11 | Review | Research Harness Correction V1 — Hostile Review | Final | `main` / uncommitted (base `f9ddc54`) | [0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md](0013_2026-08-11_RESEARCH_HARNESS_CORRECTION_HOSTILE_REVIEW.md) |
| 0012 | 2026-08-11 | Implementation | Research Harness Correction V1 — Implementation Record | Final | `main` / uncommitted (base `f9ddc54`) | [0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md](0012_2026-08-11_RESEARCH_HARNESS_CORRECTION_IMPLEMENTATION.md) |
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
