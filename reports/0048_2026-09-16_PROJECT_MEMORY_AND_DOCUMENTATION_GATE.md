| Field | Value |
|---|---|
| **Report number** | 0048 |
| **Title** | FMITS Project Memory & Documentation Gate |
| **Date** | 2026-09-16 |
| **Report type** | Documentation / project-continuity milestone |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3` |
| **Status** | Final |

# FMITS Project Memory & Documentation Gate

**Documentation only. `src/` and `tests/` are byte-identical to `66bab74`. No engine was
implemented, no policy changed, no capital configured, no TA work begun.**

---

## 1. Verified baseline

Every value below was read from the live repository at the start of the session, not assumed from
report 0047.

| Check | Result |
|---|---|
| `pwd` | `/Users/dovydas/dovydas-trading-system` |
| `git branch --show-current` | `main` |
| `git rev-parse HEAD` | `66bab7414e8c9a255dfbdde9fa9d3e8ef3c1f6e3` |
| `git rev-parse main` | `66bab74` |
| `git rev-parse origin/main` | `66bab74` |
| `git ls-remote origin refs/heads/main` | `66bab74` |
| `git rev-list --left-right --count origin/main...HEAD` | `0  0` |
| `git stash list` | empty |
| Active Git operation | none — no `rebase-merge`, `rebase-apply`, `MERGE_HEAD`, `CHERRY_PICK_HEAD` or `BISECT_LOG` |
| `git diff -- src tests` | **empty, at start and at end** |
| Tracked modifications at start | `reports/README.md` only (the uncommitted 0047 index row) |
| Untracked at start | report 0047 + the **16 pre-existing research documents** under `docs/design/` and `docs/reviews/` |

**`HEAD` had not moved since report 0047.** The expected baseline was confirmed rather than assumed,
and nothing was reset, cleaned, checked out, stashed or overwritten to make it match.

### 1.1 Operator dashboard — protected

| Check | Result |
|---|---|
| Listener on `127.0.0.1:8787` | **PID 46403**, `LISTEN`, running since 2026-09-07 |
| Process | `.venv/bin/fmits dashboard` |
| Action taken | **none** — never stopped, signalled, killed or requested |
| Development dashboard | none started |
| `pkill` | **not used** |

### 1.2 Risk configuration — untouched

`~/.fmits/` holds **only** `scan_memory/`. **`~/.fmits/risk_policy.json` does not exist and was not
created.** Declaring capital remains the owner's decision.

---

## 2. Source set reviewed

`PROJECT_SPECIFICATION_V1.md` · `PROJECT_VISION_ADDENDUM_V1.md` · `CLAUDE.md` ·
`docs/AI_HANDOFF/START_HERE_FOR_AI.md` · `docs/AI_HANDOFF/CURRENT_STATE.md` · `docs/README.md` ·
`docs/adr/README.md` (30 ADRs) · `FMITS_PRODUCT_BACKLOG.md` · `FMITS_PRODUCT_CHANGELOG.md` ·
`reports/README.md` · report 0047 in full · the `docs/design/` and `docs/reviews/` indexes · and the
live `src/` tree.

---

## 3. Stale and conflicting documentation found

| # | Document | Claim | Reality | Severity |
|---|---|---|---|---|
| 1 | `CURRENT_STATE.md` `## Current milestone` | milestone **AV** (August 2026) | five milestones behind — Slice 4 is latest | **High** — the section a reader goes to for *"what's current"* |
| 2 | `CURRENT_STATE.md` `## Test count` | **10,671 passing** | **14,699** | **High** |
| 3 | `CURRENT_STATE.md` `## Repository status` | *"Milestone AP is committed locally and is NOT on the remote"* | false — `main` = `origin/main` = `66bab74` | **High** |
| 4 | `CURRENT_STATE.md` `## Immediate next milestone` | *awaiting the owner's decision*; discusses AN/AO/AP | TA Slice 5A | **High** |
| 5 | `CURRENT_STATE.md` `## Known future roadmap` | dashboards, paper trading, persistence, APIs *Deferred* | **all shipped** | **High** |
| 6 | `START_HERE_FOR_AI.md` | *"five CLI commands — `facts`, `mtf`, `regime`, `swing`, `daily`"*; *"27 ADRs"*; *"No AI interpretation layer exists yet"* | **25 commands**; **30 ADRs**; the third is still true | **High** |
| 7 | `FMITS_PRODUCT_BACKLOG.md` header | verified 2026-08-13 at `dbc4765` | five weeks stale | Medium |
| 8 | `FMITS_PRODUCT_BACKLOG.md` §5 | exactly-one-NOW rule *"not currently satisfied"* | true for six weeks; **now satisfied** | Medium |
| 9 | `FMITS_PRODUCT_CHANGELOG.md` §3 | *"As of Milestone `BS`"* | four Swing slices shipped since | Medium |
| 10 | `FMITS_PRODUCT_BACKLOG.md` §8 | **`DV` used twice** — Reliability Gate and Slice 4 | a genuine label collision | Low |

**The structural finding.** `CURRENT_STATE.md` was not merely stale — it was **self-contradicting**.
Its top banner was accurate to 2026-09-06 while five sections *below* it, including the one literally
titled *"Current milestone"*, described August. A fresh agent scrolling to the obviously-named section
would have been confidently misinformed. That is worse than a uniformly old document, because nothing
signalled the disagreement.

---

## 4. Authority reconciliation performed

The hierarchy in §3 of the rewritten `START_HERE_FOR_AI.md` was applied:

| Conflict | Kind | Resolution |
|---|---|---|
| `CURRENT_STATE.md` §§1–5 above vs the live repository | technical state | **Live repository wins.** New §0 block states verified truth; the stale sections keep their text and gain in-place banners |
| Backlog §4 *"Immediate next milestone: awaiting the owner's decision"* vs report 0047 + this gate | planning state | **Newer decision wins.** NOW is now TA Slice 5A; the six-week gap is preserved in a collapsed historical block |
| Report 0047's plan vs the Dovydas + ChatGPT review | decision about a report | **Review wins**, recorded in a **separate** record. Report 0047 itself is unmodified |
| Old roadmap *"dashboards, paper trading deferred"* vs shipped capability | historical planning vs technical state | **Live repository wins.** Marked historical, not deleted |
| Fibonacci/Elliott "discussed later" vs the approved specification | product intent | **Approved sources win** — both confirmed absent from them; recorded as not-original-scope |

**No historical report was rewritten. No milestone entry was revised to look as if it were written
today. Nothing was deleted.**

---

## 5. Documents created

| Path | Responsibility | Why it is not a duplicate |
|---|---|---|
| [`docs/AI_HANDOFF/CAPABILITY_REGISTRY.md`](../docs/AI_HANDOFF/CAPABILITY_REGISTRY.md) | *What capabilities exist, and what is their actual status?* | Searched first: **no existing document served this purpose.** The backlog answers *what next*; the changelog *what shipped*; neither answers *what is partial, dormant, unreachable, deferred and why* |
| [`docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md`](../docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md) | The review outcome for report 0047 | Reports are immutable; `docs/reviews/` is the **existing** home for review records of this repository's work |
| [`docs/AI_HANDOFF/CHATGPT_PROJECT_INSTRUCTIONS.md`](../docs/AI_HANDOFF/CHATGPT_PROJECT_INSTRUCTIONS.md) | Portable rules for a ChatGPT project | ChatGPT sessions often cannot read this repository, so the export must be self-contained. **No equivalent existed** |
| [`docs/AI_HANDOFF/daily/README.md`](../docs/AI_HANDOFF/daily/README.md) + [`2026-09-16.md`](../docs/AI_HANDOFF/daily/2026-09-16.md) | Session continuity | **No handoff mechanism existed** — session state lived only in chat, which is the failure being fixed |

**Four responsibilities, four documents.** Each was checked against the existing tree before creation.

## 6. Documents updated

| Path | Change |
|---|---|
| [`docs/AI_HANDOFF/START_HERE_FOR_AI.md`](../docs/AI_HANDOFF/START_HERE_FOR_AI.md) | **Rewritten** as a thin cold-start router: mission, non-negotiable principles, source-authority hierarchy, where-everything-is table, startup ritual, live-repo verification checklist, *never assume* list, shutdown ritual, validation proportionality, do-not-create-false-authority table. **It routes; it does not restate.** The next-step pointer deliberately lives in one place only (`CURRENT_STATE.md`) |
| [`docs/AI_HANDOFF/CURRENT_STATE.md`](../docs/AI_HANDOFF/CURRENT_STATE.md) | **Restructured, not truncated.** New maintained **§0 CURRENT STATE** (13 subsections); the ~3,200-line history explicitly headed `ARCHIVE`; **six** sections given in-place banners — five `HISTORICAL`, one `STILL TRUE — re-verified` |
| [`FMITS_PRODUCT_BACKLOG.md`](../FMITS_PRODUCT_BACKLOG.md) | Header re-verified; §4 given a current block above the historical table; **§5 NOW satisfied for the first time since `AP`** with the six-week gap preserved in a collapsed block; §6 gained the TA sequence as §6.1; §8 gained `DW` |
| [`FMITS_PRODUCT_CHANGELOG.md`](../FMITS_PRODUCT_CHANGELOG.md) | Header re-verified; §3 split into current (§3.1) and the `BS`-era snapshot (§3.2); an explicit note that **this gate has no changelog entry, deliberately** |
| [`reports/README.md`](README.md) | This report indexed; next number bumped to `0049` |

## 7. Documents deliberately NOT changed

| Document | Why |
|---|---|
| **Report 0047** | Immutable point-in-time evidence of Claude's proposal. Its disposition lives in a separate record |
| Reports 0001–0046 | Same convention |
| `PROJECT_SPECIFICATION_V1.md`, `PROJECT_VISION_ADDENDUM_V1.md` | Approved product intent. **Nothing in this gate changes scope** |
| All 30 ADRs | **No binding architecture decision was made.** Creating ADRs to restate a report is bureaucracy and was refused |
| `docs/adr/README.md` | Already current (indexes ADR-0029/0030) — routed to rather than duplicated |
| `docs/ARCHITECTURE_AND_ROADMAP_V1.md`, `ARCHITECTURE_REVIEW_2026-07-24.md`, `REPOSITORY_MAP.md` | Standing architecture documents outside this gate's scope; reconciling them is separate work |
| The **16 untracked research documents** | Explicitly out of scope. Untouched and still untracked |
| `src/`, `tests/` | **Byte-identical** |

---

## 8. Capability registry design

**One question: *what capabilities does FMITS know about, and what is their actual status?*** Not a
second backlog.

**Twelve states, never collapsed** — because the difference between them is the information that was
being lost: `IMPLEMENTED` · `PARTIAL` · `PRODUCT_UNREACHABLE` · `DORMANT` · `PLACEHOLDER` · `MISSING` ·
`PLANNED` · `DEFERRED` · `CANDIDATE` · `BLOCKED` · `REJECTED` · `UNKNOWN`.

Three distinctions do the real work:

- **`PRODUCT_UNREACHABLE` vs `MISSING`** — the difference between *we compute this and throw it away*
  and *we never computed it*. The first is the cheapest class of gap in the repository, and it was
  invisible in every prior document.
- **`DORMANT` vs `PRODUCT_UNREACHABLE`** — nothing constructs it at all, versus a producer exists and
  a consumer does not.
- **`CANDIDATE` vs `MISSING`** — absence of a `CANDIDATE` is **not a gap**; it was never promised.

**`DEFERRED` carries four mandatory fields**: why · whether still desired · what must exist first ·
what triggers reconsideration. This is the enforcement mechanism for **DEFERRED ≠ FORGOTTEN**.

The registry covers the TA/Swing capability set and every major future FMITS domain — long-term
investing, portfolio, risk, macro, news, on-chain, derivatives, flows, China, IPO, research,
backtesting, paper, shadow, execution, Daily Brief, Opportunity Scanner and alerts — so that narrowing
FMITS to swing trading would be visibly a change of scope rather than a drift.

---

## 9. Sample live verification of registry statuses

**Not a pretty table — every status below was re-derived from the live repository.**

| Status | Capability | Evidence | Matches 0047? |
|---|---|---|---|
| `IMPLEMENTED` | Market structure / swings | `src/fmis/market_structure/` — 7 modules, **1,775 lines**; ADR-0012/0013/0014 | ✓ |
| `IMPLEMENTED` | BOS | `src/fmis/structure_break/` — 4 modules, **832 lines**; ADR-0020 | ✓ |
| `IMPLEMENTED` | CHoCH *(computed)* | `src/fmis/change_of_character/` — 4 modules, **650 lines**; ADR-0021 | ✓ |
| **`PRODUCT_UNREACHABLE`** | All three `FeatureSet`s | Produced in `pipeline/structural_facts.py` and `pipeline/market_analysis.py`. **`grep FeatureSet` across `operator_dashboard`, `swing_workspace`, `swing_setup`, `setup_evidence` → no match** | ✓ |
| **`PRODUCT_UNREACHABLE`** | Context-role levels, all crossings, all CHoCH, nearest levels, setup-role breaks | `build_setup_inputs`, `src/fmis/swing_setup/compose.py:225` — read in full. It passes trend ×3, the context regime's 3 dimensions, evidence state + dominant alignment, decision-context state, `execution_close`/`closed_count`/`execution_levels`/`execution_breaks`, `setup_levels`. **Everything else in the three sheets stops there** | ✓ |
| **`DORMANT`** | `AverageVolume` | Defined `features/volume/statistics.py:69`, exported in `__all__`. **`grep "AverageVolume(" src/` returns exactly one line — its own `class` statement.** `market_analysis.py:189`: *"registerable on request"*; nothing requests it | ✓ |
| **`PLACEHOLDER`** | Six Tier-2 packages | Measured individually: `trend` 18 · `momentum` 17 · `volatility` 16 · `market_structure` 20 · `support_resistance` 16 · `pattern_detection` 23 = **110 lines**, `__all__ = []`, zero math | ✓ **exactly** |
| **`MISSING`** | Divergence | `grep -ri divergence src/` → 12 files, **every hit an unrelated sense**: `exit_divergence` on trade plans, *"a divergence would be visible"*, *"a divergence is a statement about the provider"*, and one `TODO` in the momentum placeholder. **No price/oscillator divergence engine** | ✓ |
| **`MISSING`** | Consolidation / phases | `grep -ri consolidation src/` → 5 files, all docstrings **denying** the sense (*"`CONTRACTED` is not consolidation"*) plus one `TODO` | ✓ |
| **`MISSING`** | Zones, trendlines | `grep -ri "price_zones\|PriceZone" src/` → **0 files**. `grep -ri trendline src/` → **0 files** | ✓ |
| **`CANDIDATE`** | Fibonacci | **0** occurrences in `PROJECT_SPECIFICATION_V1.md`, **0** in `PROJECT_VISION_ADDENDUM_V1.md`, **0 files** in `src/` | ✓ |
| **`DEFERRED`** | Elliott | **0 / 0 / 0**, identically | ✓ |

**Every sampled status reproduced report 0047's finding.** No contradiction was found, so no
divergence needed documenting. The six-package line counts matched to the line.

---

## 10. Report 0047 disposition

**APPROVED WITH REQUIRED ARCHITECTURAL MODIFICATIONS.**

Approved: the audit, its measurements, its findings and the general direction of its sequence.
**Not approved verbatim: the implementation plan.** Twelve binding modifications, recorded in
[`docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md`](../docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md):

| § | Modification |
|---|---|
| **A** | **Opportunity ≠ Strategy.** `WATCH LONG` + `WAIT` and `WATCH LONG` + `CANDIDATE` must both stay logically possible. Opportunity must **not** be defined as *"strategy gates are not satisfied"* |
| **B** | **`MissingConfirmation` ≠ policy `Blocker`.** *What market event has not happened yet* ≠ *why did the strategy stop* |
| **C** | **`compute_series()` precedes** production ATR-based zone clustering |
| **D** | **Zone evidence independence NOT established** — *"potentially more orthogonal"*, never *proven independent* |
| **E** | Support/resistance role from **interaction history, never position** |
| **F** | **Do not freeze** "one exhaustive non-overlapping phase per candle" |
| **G** | **Do not freeze** "anchors must lie inside exactly one phase" |
| **H** | Divergence: exact pivot indexing is a safe v1; a researched alignment policy is not ruled out; ±N-bar cherry-picking never |
| **I** | Fibonacci — `RESEARCH FIRST`, optional context, not original scope |
| **J** | Elliott — `DEFERRED`, hypothesis-level only. *"Elliott can never exist"* is **not** recorded |
| **K** | Correlated indicators: contextual usefulness ≠ independent evidence family — **and EMA/MACD/RSI context is still useful** |
| **L** | Patterns after primitives; rectangles are ranges; no generic framework before a second pattern |

**Report 0047 was not modified.** Its own status line still reads as written on 2026-09-07, and
`CURRENT_STATE.md` §0.12 plus the disposition record now supply the context it lacked.

---

## 11. Current implementation sequence

Recorded as **planning state, not authorization**:

```
MEMORY GATE (this report) → ChatGPT + Dovydas review
  → 0. TA Slice 5A — Recover Technical Context      ← NOW
  → 1. TA Slice 5B — Price Zones & Interactions
  → 2. Price Phases
  → 3. Market Opportunity
  → 4. Indicator Context
  → 5. Volume & volatility at events
  → 6. Divergence
  → 7. Trend Geometry
  ──────── re-evaluate here, with real usage ────────
  → 8. Simple Patterns
  → 9. later research-dependent capabilities
  ── Fibonacci: only if its research supports it
  ── Elliott: not scheduled
```

Homes: [`CAPABILITY_REGISTRY.md`](../docs/AI_HANDOFF/CAPABILITY_REGISTRY.md) §6 (capability view) and
[`FMITS_PRODUCT_BACKLOG.md`](../FMITS_PRODUCT_BACKLOG.md) §6.1 (board view).

---

## 12. Daily / session handoff protocol

`docs/AI_HANDOFF/daily/YYYY-MM-DD.md`, one per **meaningful** session — not per commit, not a
transcript. A template and an index live in [`daily/README.md`](../docs/AI_HANDOFF/daily/README.md);
the first handoff is [`2026-09-16.md`](../docs/AI_HANDOFF/daily/2026-09-16.md).

Every handoff ends with **EXACT NEXT STEP** and **MUST NOT FORGET**. A handoff is a *continuity
pointer* and is explicitly **not** authoritative over the repository or the ADRs.

## 13. AI startup / shutdown protocol

Both live in [`START_HERE_FOR_AI.md`](../docs/AI_HANDOFF/START_HERE_FOR_AI.md) §5–§9 — the document
read first, which is where a startup ritual belongs — and are exported for ChatGPT in
[`CHATGPT_PROJECT_INSTRUCTIONS.md`](../docs/AI_HANDOFF/CHATGPT_PROJECT_INSTRUCTIONS.md).

Startup: read the four memory documents → backlog if planning → the domain's ADR/spec/report →
**verify live Git** → **inspect the live implementation before claiming any capability status** → if
docs and code disagree, reconcile → only then propose.

Shutdown is **event-driven**: `CURRENT_STATE` when state changed · `CAPABILITY_REGISTRY` when a
**status** changed · changelog when **user-visible capability** changed · backlog when planning
changed · an ADR when a **binding** decision changed · a report when a gate warrants one · a handoff at
the end of a meaningful session. **No trivial edit is required to produce every document.**

## 14. Backlog / changelog reconciliation

**History preserved, pointers reconciled.** Nothing deleted, no milestone entry rewritten.

- Backlog header and §4 re-verified at `66bab74`, with the historical table explicitly labelled.
- **§5 NOW satisfied for the first time since `AP`**, with the honest six-week gap and every
  owner-directed task delivered during it preserved in a collapsed `<details>` block that states the
  paragraphs inside were true when written.
- §6 gained the TA sequence; the `AP` trading-domain sequence is retained as §6.2 on its own track.
- `DW` added to §8 with the Product-First justification stated as **blocker removal**, and the `DV`
  label collision recorded rather than silently renamed.
- Changelog: **no entry added**, deliberately, with a note saying why; §3 split into current and
  historical.
- **No product version assigned.** The changelog's own §2 warning that no scheme is approved stands.

## 15. Product-First justification

Documentation is not the product, and this gate is justified only because **continuity failure had
become a blocker to safe product development**. Under the backlog's own rule it is the second
permitted form — *removes a clearly identified blocker preventing measurable user value*.

**It unblocks safe continuation of TA Slice 5A, and prevents deferred capabilities and decisions from
disappearing across AI sessions.** It claims **no** market-analysis capability.

The gate was kept thin: **four new documents, each for a responsibility nothing else served**; two
rewrites; no ADR; no new directory beyond `daily/`; and a canonical home preferred over overlapping
ones in every case.

---

## 16. Validation performed

Proportional, per the brief and `START_HERE_FOR_AI.md` §9.

| Check | Result |
|---|---|
| **`git diff -- src tests`** | **empty** — proved first, and re-proved at the end |
| Full pytest suite | **NOT RUN.** No `src/`/`tests/` byte changed. **No "suite green" claim is made anywhere in this report** |
| Test baseline carried | 14,699 at `66bab74`, **labelled with the date it was last actually run** (2026-09-07, report 0047) |
| Registry statuses | sampled against live code — §9, twelve rows |
| Referenced files exist | checked for every new link |
| Duplicate canonical document | **none** — the tree was searched for a capability registry, a handoff mechanism and a ChatGPT-instructions document before any was created; all three were absent |
| Source hierarchy consistency | one hierarchy, stated once in `START_HERE_FOR_AI.md` §3 and referenced elsewhere |
| `CURRENT_STATE.md` vs verified repo | §0 matches §1 of this report |
| Backlog NOW/NEXT coherence | exactly one NOW |
| Report numbering | `0048` verified free against the index and the directory before use |
| Markdown structure | headings, tables and the one `<details>` block verified balanced |
| Secrets | none introduced |
| Risk config | **not created** — `~/.fmits/risk_policy.json` verified still absent |
| Operator dashboard | **PID 46403 untouched**, confirmed listening at start and end |

**What was NOT tested:** the Python test suite, the policy digest, and the Reliability Gate. All three
are carried forward from report 0047's run at the identical `src`/`tests` state.

## 17. Diff summary

| Path | Change |
|---|---|
| `docs/AI_HANDOFF/START_HERE_FOR_AI.md` | rewritten |
| `docs/AI_HANDOFF/CURRENT_STATE.md` | header replaced with §0; six in-place banners; **archive preserved** |
| `docs/AI_HANDOFF/CAPABILITY_REGISTRY.md` | **new** |
| `docs/AI_HANDOFF/CHATGPT_PROJECT_INSTRUCTIONS.md` | **new** |
| `docs/AI_HANDOFF/daily/README.md` | **new** |
| `docs/AI_HANDOFF/daily/2026-09-16.md` | **new** |
| `docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md` | **new** |
| `FMITS_PRODUCT_BACKLOG.md` | header, §4, §5, §6, §8 |
| `FMITS_PRODUCT_CHANGELOG.md` | header, §3 |
| `reports/0047_…ARCHITECTURE_GATE.md` | **unchanged** (previously untracked; committed as-is) |
| `reports/0048_…PROJECT_MEMORY_AND_DOCUMENTATION_GATE.md` | **new** — this report |
| `reports/README.md` | 0048 indexed; next number `0049` |
| **`src/`, `tests/`** | **zero bytes changed** |

## 18. Commit / push state

See §20 and the session handoff. Pre-commit verification: full diff inspected · only documentation and
project-memory files changed · `src/` and `tests/` unchanged · no secrets · no generated files · **the
16 untracked research documents deliberately not staged**.

---

## 19. Exact next recommended milestone

> ## TA Slice 5A — Recover Technical Context

**Purpose:** stop throwing away already-computed technical information, and establish the historical
series access later engines need.

**In scope:** widen the `build_setup_inputs` seam · preserve relevant per-role structured facts ·
carry crossings / CHoCH / levels / nearest levels / regimes / `FeatureSet`s where architecture permits ·
an **additive** `compute_series()` · a small **real product consumer**.

**Out of scope:** Swing policy change · zones · `WATCH` · invented thresholds · risk/capital change.

**GO:** Dovydas + ChatGPT have reviewed this gate, **and** the slice has its own implementation brief.
**STOP:** when recovered facts reach a real operator surface and `compute_series()` exists additively.
It does **not** continue into 5B.

## 20. Unresolved questions requiring Dovydas + ChatGPT

| # | Question | Blocks |
|---|---|---|
| 1 | **Is this Memory Gate accepted?** | TA Slice 5A |
| 2 | **0047 D1 — zone-width tolerance policy** (a scoped weakening of ADR-0013 §4) | Slice 5B |
| 3 | **0047 D2 — may a zone carry a role, and what may it be called?** The *derivation* rule is settled (interaction history); the *naming* is not, and three guards currently forbid the words in output | Slice 5B |
| 4 | **0047 D3 — where does opportunity state live, and may it name a side?** (ADR-0028) | Market Opportunity |
| 5 | **0047 D5 — do the three evidence-status vocabularies converge?** *(0047 recommends no)* | — |
| 6 | **AP-D2 — capture contract and migration guarantee** | the first irreplaceable trading record |
| 7 | **D-03 — availability-time model** (ADR-0003) | all macro/news/fundamental/vintage backtesting |
| 8 | **The owner's capital declaration** — deliberately not made on his behalf | risk sizing as a product capability |
| 9 | **Should `CURRENT_STATE.md`'s archive be split into its own file?** Not done here; it would be a second large edit with no continuity benefit this session | — |

---

# WHAT A NEW AI MUST KNOW IN 5 MINUTES

**FMITS is not a trading bot.** It is a personal Financial Market Intelligence operating environment.
The immediate priority is Swing Trading / Technical Market Intelligence — a priority, **not** the
boundary of the project.

**Read these four, in order:** `docs/AI_HANDOFF/START_HERE_FOR_AI.md` → `CURRENT_STATE.md` **§0**
(everything below §0 is a historical archive) → `CAPABILITY_REGISTRY.md` → the newest file in
`daily/`. Then **verify Git and inspect the live code** before claiming anything about capability.

**Where truth lives:** live repository + tests → accepted ADRs → the specification and vision addendum
→ newer reports (for their own baseline) → `CURRENT_STATE.md` → the registry → backlog/changelog →
old roadmaps (**historical planning only, never a command**).

**The product today:** 25 CLI commands and a 10-page operator dashboard. The deterministic structural
chain is complete from candles to a regime-classified, conflict-checked, multi-timeframe decision with
the blocking condition named. Risk sizing exists but is **unavailable until the owner declares
capital** — and an agent must **never** declare it for him.

**The one big gap:** FMITS has an excellent price-structure spine and almost no technical-analysis
body. Roughly **half of what it computes is thrown away** in one 75-line function,
`build_setup_inputs` at `src/fmis/swing_setup/compose.py:225`. **No zones, phases, trendlines,
divergence, breakout vocabulary or chart patterns exist.** Indicators return the latest scalar only,
so slope and divergence are not derivable *in principle*. The six Tier-2 feature packages are 110
lines of placeholder with zero math.

**The product problem driving all of it:** the operator sees too many undifferentiated `WAIT`s and
cannot tell *nothing interesting* from *something is developing*. **This does not authorize more
trades, weaker gates, or bullish bias.**

**Rules that are not negotiable:** deterministic first, AI second · no simplistic indicator rules · no
LONG or SHORT bias · **`WAIT` and `NO TRADE` are valid outcomes** · **more indicators add no
independence, a new *family* does** · **2 % per-trade risk is a hard ceiling, never a default** · Swing,
long-term and day-trading are **separate books and one must never size another** · never commit
secrets · no withdrawal permissions, ever.

**DEFERRED ≠ FORGOTTEN.** Fibonacci is `CANDIDATE`/research-first. Elliott is `DEFERRED`,
hypothesis-level only — **and "Elliott can never exist" is explicitly not the decision.** Never read a
deferral as a cancellation.

**Four things not to freeze**, because report 0047 stated them more confidently than the evidence
supports: the phase-segmentation model · the trendline-anchor rule · the divergence-alignment policy ·
and any claim that zone evidence is independent.

**Two separations to protect:** Opportunity ≠ Strategy, and `MissingConfirmation` ≠ policy `Blocker`.

**Operationally:** the owner's dashboard runs on **`127.0.0.1:8787`, PID 46403** — develop on 8799,
restart only at handoff by exact PID, **never `pkill`**. Never commit or push without explicit
authorization.

**The next milestone is TA Slice 5A — Recover Technical Context**, pending Dovydas + ChatGPT review of
this gate.
