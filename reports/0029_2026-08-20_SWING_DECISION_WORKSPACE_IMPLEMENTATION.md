# 0029 — Milestone BS: Swing Decision Workspace v1 — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0029 |
| **Title** | Milestone BS — Swing Decision Workspace v1 |
| **Date** | 2026-08-20 |
| **Report type** | Implementation record |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `cc4e748` (HEAD at start of milestone) |
| **Status** | Final — committed as `b6a456c` (production code + tests) on top of `cc4e748`, with the documentation commit directly on top of it. Verified by the milestone and again by an independent release gate on 2026-08-21 (§8a) |

---

## 1. What shipped, in one paragraph

One new application-layer package, **`fmis.swing_workspace`** (5 modules), and one new command,
**`fmits workspace`**. It is the second package in the repository that reads both halves of FMITS,
and the first that reads them *through* another such package rather than directly: its composition
root calls `fmis.today.assemble_today` — the exact sequence `fmits today` runs — and rearranges the
three artifacts that returns. **No engine was created, no deterministic computation was duplicated,
and no market, monetary or statistical quantity is computed anywhere in the package.** What the page
adds over `fmits today` is exactly one thing: a **decision order**, expressed as an explicit
lexicographic key over four named engine states, printed on every row it places.

## 2. The one architectural decision, and why the brief was adapted

**The brief asked for ranked opportunities. This repository has refused every ranking for five
milestones, and has a measurement behind the refusal.** `fmis.today.attention` states it: *"let the
owner rank by risk/reward… this attack requires no adversary; it happens by default"*, and
`fmis.today.evidence.RISK_REWARD_ASSOCIATION` records that higher displayed R:R was measured with a
**worse** outcome — R:R in `[5, 20)` resolved target-first 7.7 % of the time against 74.5 % for R:R
in `[0, 1)`.

The brief itself resolves the tension, in its own words: *"NOT probability. NOT AI score. NOT hidden
weighting… If two setups swap order the reason must be reconstructable."* So BS ranks, and pays the
full price:

- The order is a **lexicographic key over four components**, compared left to right:
  `readiness` (the Swing Setup Engine's `SetupState`) → `approval` (the Position Sizing Engine's
  `ApprovalStatus`) → `sufficiency` (the Decision Context Engine's `ContextState`) → `watchlist`
  (the position of the symbol in the requested universe).
- Every component is an **ordinal over a finite, written-out vocabulary** — a complete mapping over
  the upstream enum, never a lookup with a default. `ranking.py` contains no division, no
  multiplication, no subtraction and **no floating-point literal at all**; a guard test asserts it.
- Every component's `name`, `value`, integer `rank` and `source` is **printed on the row it placed**,
  so two adjacent rows can be compared component by component without reading any code.
- Nine quantities are named in `EXCLUDED_FROM_RANKING` and printed under the rule: risk/reward, stop
  distance, target distance, recommended size, open risk after entry, evidence item counts, agreeing
  family counts, direction, paper-trade result. Tests plant a 99:1 R:R candidate above a 0.5:1
  confirmed setup and assert the order does not move.
- The page prints, and the object carries, the sentence *"readiness is not desirability"*.

**`INDETERMINATE` sorts after `BLOCKED`, deliberately.** A blocked candidate was measured against the
owner's limits and failed one — a fact about the trade. An indeterminate one was not measured at all
— a fact about the engine's reach. The page orders by how *settled* a row is, and neither is a claim
about the market.

## 3. Section membership is the engine's own three states

No new policy decides what goes where. `SetupState`'s own documentation supplies the mapping:

| Engine state | Section | The engine's own words |
|---|---|---|
| `CONFIRMED` | **TOP OPPORTUNITIES** | *"the thesis has confirmed under this policy's stated rule"* |
| `CANDIDATE` | **WAIT LIST** | *"a directional thesis exists, but the execution-timeframe confirmation this policy requires has not occurred"* — exactly *close but not ready* |
| `WAIT` | **NO TRADE** | *"no directional candidate exists"* |
| no assessment | **COULD NOT BE READ** | never a market statement |

`NO TRADE` groups on the engine's verbatim `thesis[0]`, exactly as `fmis.swing_setup.scan_report` and
`fmis.today.sections` do, and sub-classifies each group as *read and declined* or *could not be
classified* on the sufficiency judgement `MarketOverview` already makes.

## 4. What each section reuses, with nothing recomputed

| Section | Source | Recomputed? |
|---|---|---|
| Global market summary | `fmis.today.MarketOverview` + counts of the sections below | no |
| Top opportunities / wait list | `fmis.today.OpportunityLine` — **the identical instances** | no |
| — evidence digest | `fmis.setup_evidence.project_setup_evidence`, `len()` of its own groups | no |
| — stable identity | `fmis.setup_observation.observe_setup_series`, the same call `fmits setup` makes | no |
| — paper status | the folded `TradeMonitor` states, matched by market | no |
| — held | `PortfolioOverview.open_positions`, matched by market | no |
| No trade | the assessments' own `thesis[0]` | no |
| Active paper trades | `fmis.paper`'s `TradeMonitor` — entry, risk, R, MFE, MAE, bars, state | no |
| Portfolio summary | `fmis.today.PortfolioOverview` — **the identical instance** | no |
| — books | `fmis.portfolio_risk`'s own `BOOK` exposure breakdown, one of the eight `build_state` folds | no |
| Statistics snapshot | `fmis.today.PerformanceSummary` — **the identical instance** | no |
| Warnings | `fmis.today`'s own warnings + `fmis.paper`'s per-trade warnings, deduplicated | no |

Three tests assert **object identity** (`is`, not `==`) between the page's market, portfolio and
statistics sections and the day's page's own, so a future refactor cannot silently substitute a
recomputation.

## 5. The seam in `fmis.today`, and why it is an addition rather than a rewrite

`run_today` built three things — the scan results, the store reading and the assembled page — and
returned only the last. A second composition root above it therefore had two bad options: re-run the
scan (twenty symbols, sixty timeframe fetches, and a second set of prices that could disagree with
the first), or re-implement `run_today`'s sequence and drift from it the first time a step is added.

So `fmis.today.builder` gained **`TodayRun`** (a three-field record) and **`assemble_today`** (the
whole of what `run_today` did). `run_today` is now one delegation over it and **keeps its exact
signature and its exact result**; a test drives both through a stubbed scan and asserts the two pages
render byte-identically. No behaviour changed, `fmits today` is unchanged, and `fmis.today` gained
two public names and lost none.

## 6. Deviations from the brief, each deliberate

1. **`fmits today` was not re-implemented on top of the workspace builders.** The brief allowed it
   ("*if appropriate*"). It is not appropriate: the day's page deliberately refuses to order by
   anything but scan order, and rebuilding it on a package whose reason for existing is an ordering
   would put the refusal downstream of the thing it refuses. The reuse runs the other way — the
   workspace is built from the day's page — which is the direction that preserves both contracts.
   `fmits today` is byte-identical and shares `_configure_today` with the new command, so the two can
   never drift on flags.
2. **`risk state` is a description, never a traffic light.** No layer in this repository measures a
   limit yet — `fmis.today` renders every one of them as indeterminate with its reason — so a
   green/amber/red headline would be invented, and invented at the top of the page.
3. **The engine policy types are typed `Any` in `run_swing_workspace`.** Four engine-layering guards
   scan for the *text* of a module name outside the composition roots they permit. Importing
   `RegimePolicy`, `ContextPolicy`, `DetectionSettings` and `TimeframeRole` to annotate five opaque
   pass-through parameters would have meant widening four guards to buy five annotations. The values
   are validated one layer down, where they are used. The same reasoning reworded three printed
   provenance strings to name engines rather than module paths.
4. **The per-row evidence digest reverses `BR`'s decision for `fmits today`, and states why.** `BR`
   declined a per-row evidence figure on the day's page because it would be provably constant and
   would read as a ranking. Here the digest sits in a per-setup **detail block**, not a sortable
   column, the ordering demonstrably ignores it (asserted), and the live page shows it is *not*
   constant — ETHUSDT reported 5 supporting / 1 conflicting while ARBUSDT reported 4 / 1 with a
   different family split.
5. **The correlation caveats are printed once, under `EVIDENCE INDEPENDENCE`, not per row.** They are
   properties of the policy rather than of a market; every actionable row reports the same ones, and
   printing thirty identical paragraphs is the fastest way to teach a reader to skip the section that
   most needs reading. The full set is still carried per row on the object, for consumers.

## 7. Defects found and how each was handled

All were found by this milestone's own gates and all are fixed in the delivered code.

| # | Found by | Defect | Resolution |
|---|---|---|---|
| 1 | Reading the first rendered page | A wrapped rank key repeated its **label** on every continuation line — `rank key` printed twice reads as two values, the exact misreading the page exists to prevent | `_token` now indents continuations with spaces; a test counts the label's occurrences |
| 2 | A width test with a 64-character symbol | Nothing bounds a symbol's length, and the row heading was laid out on one unwrapped line — 103 columns on a 78-column page | The heading wraps; the same class of defect `BR` recorded |
| 3 | **Attacking the surface** | `fmits workspace BTCUSDT BTCUSDT` **lost the entire page**: the duplicate guard rejected a symbol appearing twice in one section | The guard now rejects a symbol in two *different* sections — a contradiction — and permits repetition inside one, which is the honest answer to being asked twice |
| 4 | **Attacking the surface** | A row read `paper: none` beside a real open position — the wrong half of *"am I already in this?"* | `paper_status` now names the book it checked; a second field, `held`, names any recorded position in **any** book, per book, never totalled |
| 5 | The mutation harness (probe 29) | `books_from` filtered on the exposure axis, and every fixture had made that filter free because no two axes had ever shared a key. An owner whose *account* is named `paper` would have had the account's figure printed as the book's | The fixture now shares a key across two axes with different figures; the probe is killed |
| 6 | The mutation harness (probes 32, 20, 23, 24, 31, 38, 10) | Seven test gaps, not source defects: identity vs equality on an unmerged warning, a wait-list-only page's emptiness, caveats dropped on established independence, a paper trade on another market, a finished trade counted as running, a constant watchlist ordinal, and a refusal matched too loosely | Seven assertions strengthened; all seven probes now killed |
| 7 | Coverage | The evidence-absence row used the wide label column and misaligned against the rest of the block | Row width passed through |
| 8 | The release gate | Six repository guards and rosters needed the new command or the new consumer | All six updated **with written justification**; none weakened — see §9 |
| 9 | **The independent release gate** (§8a) | The *"this package writes nothing"* guard listed only the store's repository verbs, so a plain `pathlib.Path(...).write_text(...)` injected into the composition root **survived**. A guard that cannot see a raw filesystem write does not enforce what it claims | The guard now forbids `write_text`, `write_bytes`, `writelines`, `mkdir`, `makedirs`, `unlink`, `rmtree`, `remove`, `rename`, `touch` and `open` as well |
| 10 | **The independent release gate** | Risk/reward could still decide the order **in a tie**. A mutant pre-sorting the input by R:R survived every existing test, because the total key overrides a pre-sort — it changes the answer only where the fourth component ties, which is precisely where a quantity that orders nothing must be proven inert | Two regressions added: two symbols outside the watchlist, and a watchlist naming one symbol twice, each with R:R inverted between runs |
| 11 | **The independent release gate** | `TodayRun.results` could be emptied and `TodayRun.reading` replaced with an empty reading without any test failing — the page inside the run was still built from the real inputs, so the day's page stayed correct while everything the *workspace* derives from the run silently became an absence | Two regressions added asserting the seam hands back the very scan and the very reading the page was assembled from |
| 12 | **The independent release gate** | A wrapped continuation indented to column 0 passed the width contract (shorter lines always fit) while reading as a new top-level line | A regression asserts the continuation starts at the column of the value it continues |
| 13 | **The independent release gate** | The identity call site could take a literal gap tolerance instead of the named constant. Equivalent today — one invocation observes one bar — but not equivalent the moment a surface passes a series | An AST regression pins the call site to `ONE_READING_GAP_BARS` and the constant to `0` |

## 8. Verification

| Gate | Result |
|---|---|
| Focused BS suite | **251 passed** (8 new files) |
| Coverage — statement **and** branch | **100 %** of all 5 new modules (772 statements, 274 branches, 0 missed), of the modified `fmis/today/builder.py` (142 statements, 34 branches, 0 missed) and of `fmis/today/__init__.py`; **0 missed lines** in the new `fmits workspace` CLI region, measured by line map |
| Mutation probes — milestone harness | **45 / 45 detected, 0 survivors** |
| Mutation probes — independent release-gate harness | **45 / 45 detected, 0 survivors** across the twelve areas the gate names (ranking priority, tie handling, excluded quantities, section membership, duplicate symbols, paper/live, book/account, identity propagation, warning aggregation, `TodayRun` reuse, store-write prohibition, width protection). Seven probes survived the first pass; five were real assertion gaps and one a guard hole, all fixed with regressions (§7 rows 9–13), one was a proven equivalent now pinned, and one probe was malformed and replaced |
| Mutation restoration | in-memory byte snapshot, SHA-256 verified, `__pycache__` cleared both sides. `git checkout --` deliberately not used: report 0028 records why that can destroy uncommitted work, and this milestone was uncommitted throughout |
| **Full repository, `-W error`** | **8,954 passed, 0 failed** (~189 s), via `uv run python -W error -m pytest -q`. Baseline before this milestone: **8,703** |
| Regression groups (release gate, run separately) | BS focused 251 · BR setup-evidence 173 · BG-D1/b/c identity 189 · BP statistics 539 · BO paper 332 · BN sizing/approval 368 · BM/BL portfolio+marks+valuation 631 · BJ today 327 · pipeline/CLI 308 · architecture/boundary 635 · swing_setup+AK workspace 542 — **all green under `-W error`** |
| Import cycles | **0**, measured across 275 modules |
| Public exports / collisions | **1,220 public names, 0 collisions**. `fmis.swing_workspace` 42 new; `fmis.today` 60 → 62. Two names were renamed during the milestone *because* the zero-collision guard caught them: `PAGE_WIDTH` → `WORKSPACE_PAGE_WIDTH` (against `fmis.setup_evidence`) and `OBJECTIVE` withdrawn from the package root (against `fmis.today`) |
| Runtime dependencies | **0 added**; `pyproject.toml` and `uv.lock` unchanged (0 diff lines) |
| Record kinds / repositories / write paths | **0 added.** A guard asserts no store write verb appears anywhere in the package, and a live run left the store **byte-identical** (SHA-256 over every path and payload, before and after) |
| Architecture guards weakened | **none.** Six were *extended* with justification; the assertions they protect are unchanged |
| ADRs | **none required and none widened** — no new boundary. The package composes existing ones |
| Directional vocabulary | no exemption taken; `fmis.swing_workspace` is covered by ADR-0028's repository-wide guard with no edit, asserted by a test |

### Live demonstration (real Binance data, 2026-08-20)

| Case | Command | Result |
|---|---|---|
| CONFIRMED | `fmits workspace BTCUSDT ETHUSDT SOLUSDT DOTUSDT ARBUSDT --store-root …` | `#1 ETHUSDT long [confirmed · sufficient]`, rank key printed, 5 supporting / 1 conflicting, independence **NOT established** in 5 stated ways |
| WAIT | same run | `#1 ARBUSDT short [candidate · sufficient]` with the engine's verbatim *"Awaiting a confirmed close beyond the lower level at 0.0887 … 29 bar(s) old, beyond the 10-bar confirmation window"* |
| NO TRADE | same run | Two groups: three symbols, each with the engine's own reason, both classified *read and declined* |
| Empty | `fmits workspace … --no-records` | Complete page; every store-derived figure a stated absence naming what it forbids |
| Paper trade | same run | `BTCUSDT [pending]` with entry, risk, R, MFE and MAE all **absent with the simulator's own reason** — never a zero |
| Portfolio | same run | 0 open positions, exposure `0 USDT`, `risk remaining` refused with the reason |
| Statistics | same run | 3 trades recorded, 0 resolved, sample floor 30, every rate refused with its `n` |
| Warnings | same run | `M-NO-POSITIONS`, `R-NO-BUDGET`, and **`PT-W6` from `fmis.paper`** — a warning `fmits today` never surfaced |
| Read-only | store SHA-256 before / after | **identical** |
| Reproducible | two separate processes, one `--reference-time` | **byte-identical pages** |
| Page width | every line, by character | **0 over 78 columns** |

## 8a. Independent release gate (2026-08-21)

The milestone's own verification was **not** accepted on its own evidence. An independent gate
re-derived every claim from the source and the running system, and found five real assertion gaps
and one guard hole (§7 rows 9–13). All are fixed, each with a regression that fails against the
unfixed implementation. What the gate established that the milestone had asserted:

- **The seam is behaviour-preserving by construction.** `run_today` and `assemble_today` were
  compared at the AST level: identical 18-parameter signatures, identical defaults, all 18 forwarded,
  none rewired to a different local, and a single `return …​.workspace`.
- **`fmits today` is byte-identical across the seam, measured against the real pre-change code.** The
  old `builder.py` was loaded from `HEAD` into its own module namespace — the working tree untouched —
  and both were driven over one stubbed scan and one real store. Four flag combinations (`{}`,
  `--no-records`, `--no-marks`, a non-default timezone): **identical pages, byte for byte.**
- **Nothing is repeated.** One `fmits workspace` invocation was instrumented at every expensive
  boundary: market scan **1**, store read **1**, price fetch/valuation **1**, approval pass **1**,
  statistics computation **1**, portfolio computation **1**, `build_today` **1**. Per-row work is per
  row, not per section.
- **The ordering is lexicographic and total, exhaustively.** All 30 combinations of the declared state
  space produce an order exactly equal to `sorted(key)`, strictly increasing with no ties. Across
  16,000 adversarial pairs, **no later component ever compensated for a worse earlier one**.
- **Every excluded quantity is provably inert.** Nine fields — risk/reward, stop, target, size, open
  risk, direction, thesis, invalidation, confirmation — were fuzzed 300 times each over a fixed row
  set; the order never moved. A tenth attack, R:R deciding a *tie*, is what §7 row 10 records.
- **Conservation.** Over 400 randomized scans of 1–24 symbols, every requested symbol appeared in
  **exactly one** section, every time.
- **Paper and live are two questions.** Six store shapes (empty, open paper, closed paper, recorded
  position, both at once, store unread) produce six distinct pairs of answers; no case collapses to a
  bare `none`; two books on one market are named separately and never summed; and an account named
  `paper` cannot supply the book's figure in either breakdown ordering.
- **Statistics are projected, never computed.** No statistical function or method call exists in the
  package, `fmis.statistics` is not imported, and `workspace.statistics` **is** the day's own object.
- **Warnings survive the edges.** One code arriving by two paths → one warning with two subjects;
  fifty arrivals → one warning with fifty subjects; a 900-character statement with a 300-character
  subject and a 700-character detail renders inside the width contract.
- **Seventeen hostile surface cases** — empty watchlist, one symbol, duplicate symbol, 100 symbols,
  all-WAIT, all-CANDIDATE, multiple CONFIRMED, every symbol failed, blank failure text, missing
  store, missing paper data, a 64-character symbol, a 200-character store path, a 900-character
  thesis, insufficient context, and a mixed scan — every one renders with **no line over 78
  characters**; the empty watchlist is refused by the layer that owns the rule.

## 9. Guards and rosters extended, with the justification written into each

1. `tests/test_trade_capture_architecture.py` — `fmis.swing_workspace` admitted as the eighth
   application-layer prefix the CLI may name. The two assertions that matter — the CLI opens no store
   and names no domain root — are unaffected and still pass.
2. `tests/test_setup_evidence_architecture.py` — a third permitted consumer of the evidence
   projection, at the same tier as `fmis.today.sections`.
3. `tests/test_pipeline_cli.py`, `tests/test_multi_timeframe.py`, `tests/test_pipeline_regime.py`,
   `tests/test_workspace_render.py`, `tests/test_pipeline_cli_trade.py` — the command roster and the
   registration-order pin, with a note recording that `workspace` sits immediately after `today`
   because it is that page's successor rather than a later step in the day.

Four further guards — `decision_context`, `market_regime`, `multi_timeframe`, `structural_facts` —
initially failed and were **not** widened; the imports and the prose that tripped them were removed
instead (§6.3).

## 10. What the owner can do that was impossible before

Open one page and be told **what to look at first, and why that order and not another**. Previously
the day's page listed actionable setups in watchlist order with no ordering claim at all, and
answering *"which of these three first?"* meant reading three full blocks and deciding by eye. Now
the first row states its own placement — `readiness=confirmed(0) · approval=approved(0) ·
sufficiency=sufficient(0) · watchlist=#2(1)` — and the page states, beneath it, the nine quantities
that did **not** decide it.

Three questions are answerable on the row for the first time: *is this the same idea I saw
yesterday* (the stable identity), *what argues against it* (the evidence digest, with independence
reported rather than assumed), and *am I already in this* (the paper book and the recorded position,
separately).

## 11. Limits of this milestone

- **A pending paper trade on a symbol the engine now calls NO TRADE is not cross-referenced, and
  the condition is real.** The release gate reproduced it deliberately: on 2026-08-21, `BTCUSDT`
  appeared under **NO TRADE** (*"context-role (1w) regime structure is indeterminate, not trending"*)
  while a `pending` `BTCUSDT` activation appeared under **ACTIVE PAPER TRADES** and the header counted
  it as one paper position. Both facts are on the page, in different sections, and **BS deliberately
  draws no line between them** — the gate confirmed no such sentence is rendered anywhere. This is
  *lifecycle-versus-current-assessment* intelligence: it needs a rule about when a commitment made
  under one reading is stale under a later one, which is a policy decision and not a presentation
  one. It is recorded as unsequenced follow-up work on the backlog and is deliberately **not** patched
  into the workspace.
- **Nothing is measured against a risk limit**, so `risk state` is a description of what is recorded
  rather than of what is breached. That is `fmis.today`'s state, inherited.
- **The evidence digest is a count, not a strength**, and `BR`'s finding stands: the context regime
  gate and the context structural-trend factor are the same reading, so the effective agreement bar
  is the gate's own family plus one other.
- **The wait list is ordered by the same key as the opportunities**, which means an approval status
  can order a row the owner cannot act on yet. It is stated on the row and is the honest reading of
  *how settled* each candidate is.
- **No probability, no correlation, no liquidity, no macro.** Unchanged, and printed as `WS-5`,
  `WS-6` and `WS-8` at the foot of every page.

## 12. Exact changed-file scope

**New (10 files):**

```
src/fmis/swing_workspace/__init__.py          144
src/fmis/swing_workspace/models.py            648
src/fmis/swing_workspace/ranking.py           276
src/fmis/swing_workspace/sections.py          722
src/fmis/swing_workspace/render.py            697
src/fmis/swing_workspace/builder.py           283
tests/swing_workspace_helpers.py              206
tests/test_swing_workspace_ranking.py         371
tests/test_swing_workspace_models.py          375
tests/test_swing_workspace_builder.py         412
tests/test_swing_workspace_sections.py        980
tests/test_swing_workspace_render.py          419
tests/test_swing_workspace_store.py           360
tests/test_swing_workspace_architecture.py    420
tests/test_pipeline_cli_workspace.py          179
```

**Modified (10 files):**

```
src/fmis/pipeline/cli.py                   +85   the `workspace` command
src/fmis/today/builder.py                 +148/-36  TodayRun + assemble_today; run_today delegates
src/fmis/today/__init__.py                  +4   two new exports
tests/test_trade_capture_architecture.py   +10   CLI prefix allowlist
tests/test_setup_evidence_architecture.py   +9   third permitted consumer
tests/test_pipeline_cli.py                  +2   command roster
tests/test_pipeline_cli_trade.py            +9   registration-order pin
tests/test_pipeline_regime.py               +6   registration-order pin
tests/test_workspace_render.py              +6   registration-order pin
tests/test_multi_timeframe.py               +4   command roster
```

`pyproject.toml`, `uv.lock` and every ADR: **unchanged**.
