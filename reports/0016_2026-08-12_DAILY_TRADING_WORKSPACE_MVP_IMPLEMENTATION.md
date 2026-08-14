# 0016 — Daily Trading Workspace MVP (Milestone BJ) — implementation record

| Field | Value |
|---|---|
| **Report number** | 0016 |
| **Title** | Daily Trading Workspace MVP (Milestone BJ) — implementation record |
| **Date** | 2026-08-12 |
| **Report type** | Implementation record |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | Working tree on top of `dbc4765`. `origin/main` is at `f9ddc54`, five commits behind |
| **Status** | Implementation complete. **Not committed, not pushed.** Both require separate, explicit authorization (`CLAUDE.md`) |

---

## 0. What was built, in one paragraph

One new package, `fmis.today`, and one new command, `fmits today`. Eight modules
assembling a complete swing-trading cockpit from components that already existed:
the market half's scan (`fmis.swing_setup`), the owner half's durable store
(`fmis.persistence`), and the trading domain those records belong to. **2,603
lines of production code, 3,783 lines of tests, 247 new tests, 100 % statement
and 100 % branch coverage of the new package, 15 mutation probes with 15
detected and 0 survivors, zero new runtime dependencies, zero export collisions,
one existing production file modified (`pipeline/cli.py`, additively).** This is
the first milestone since `BH` that changes what the owner can do.

**It is the first package in this repository that reads both halves of FMITS**,
and that is the one architectural claim it makes. Everything else it does, it
does with facts and records that were already there.

---

## 1. What the owner can do after this that was impossible before

One command, run in the evening, answers seven questions on one page:

| # | Section | Answers | Built from |
|---|---|---|---|
| 1 | **Market overview** | What is the market doing | The scan `fmits scan` already runs |
| 2 | **Portfolio overview** | What do I hold, what is committed | The position fold, the risk budget, the latest snapshot |
| 3 | **Today's opportunities** | Is there anything at all | `WAIT` / `CANDIDATE` / `CONFIRMED`, grouped |
| 4 | **Priority queue** | What deserves attention, what to ignore | Readiness state + watchlist order + the rules |
| 5 | **Trade journal** | What have I decided and written | `JournalEntry`, closed positions, live proposals |
| 6 | **Recent analysis** | What has been durably recorded | The archive manifest, citations, market snapshots |
| 7 | **Workspace warnings** | What should I not trust | The deterministic rules, with their sources |

Before this milestone the answer to questions 2, 4, 5, 6 and 7 was *"run nothing,
because no surface exists"* — report 0015 §9 item 1 states it directly: *"the
store has no surface. Nothing in `fmits` reads or writes it."* That is no longer
true.

**A changelog entry is warranted and one was made.** This is a user-visible
capability, unlike `BH` and `BI`.

---

## 2. The three decisions that shaped the page, and the evidence behind each

### 2.1 There is no Bull / Bear / Neutral label, and the page says why

The brief asks for *"Current regime — Bull / Bear / Neutral"*. The brief also
says *"Do NOT redesign architecture. Follow existing ADRs."* Those two
instructions conflict, and ADR-0025 wins:

> A regime is the environment, never a direction. Three dimensions — structure,
> volatility, participation — each with its own evidence, never collapsed into
> one label and never scored.

Producing a single directional regime label would have required this package to
invent the exact object ADR-0025 exists to refuse, and `docs/analysis-notes.md`
records what a directional regime cost the v2 prompt: branches that looked
symmetric while one required a deep bear market, and a systematic long bias.

**What ships instead** is the distribution of what the engine actually
concluded, per symbol — a **breadth** table counting how many symbols the
policy placed on each side and how many on none. That is a count of already-final
verdicts, not a new judgement. `MarketOverview.regime_note` carries the refusal
onto the page in words, because a missing headline reads as an oversight and this
one is a contract.

**This is the one place the implementation does not do what the brief literally
asked.** It is recorded here rather than quietly substituted.

### 2.2 The priority queue orders by attention, and it is structurally incapable of ranking

The brief asks for a priority queue and says *"Do NOT sort by RR alone. Respect
existing research."* The research is unanimous and stronger than "not RR alone":

* `SWING_TRADING_READINESS_AUDIT_V1.md` §6.1 — *"let the owner rank by
  risk/reward… This attack requires no adversary; it happens by default."*
* `AX` §3.7 — displayed R:R in `[5, 20)` resolved target-first **7.7 %** of the
  time (n = 26) against **74.5 %** for R:R in `[0, 1)`. The big number is the
  bad one.
* Milestone `AN`'s own record — a scanner *"must rank on an explicit,
  deterministic, testable and backtested policy"*, and no such policy exists.

So the queue orders by exactly two things and nothing else: **the engine's own
readiness state** (`CONFIRMED` before `CANDIDATE` — the grouping
`fmis.swing_setup.scan_report` already applies to identical results), then
**watchlist order** within each group.

**It is not merely unsorted; the mechanism is absent.** A guard test parses
`attention.py` and asserts the module contains no `sorted`, `.sort`, `min`,
`max`, `key=` or `reverse=`. A behavioural test plants a `CANDIDATE` with
`R:R 49.00` — the value a live run actually printed — against a `CONFIRMED`
setup with `R:R 0.4`, and asserts the order does not move. A second test proves
a flagged entry does not sink below a clean one.

**Refusals leave the queue rather than sinking in it.** An entry the system will
not produce a number for is not a worse opportunity; it is a different statement.
`PriorityQueue` has two tuples, and the model refuses to put a `BLOCK` warning in
the `warnings` list or a blocked entry in `needs_attention`.

### 2.3 Every measured number prints with its `n` and what is wrong with its sample

`SWING_TRADING_MVP_BLUEPRINT_V1.md` §7.6 is explicit:

> Every soft warning drawn from that chain must therefore be rendered with its
> `n` and a note that the sample is superseded — **or the warning becomes the
> thing it exists to prevent: a confident number the owner acts on.**

`fmis.today.evidence` holds every number this package cites — two — as a
`MeasuredFigure` with `statement`, `sample`, `source` and `caveat`. `rendered()`
returns all three parts and **there is no short form**, so a renderer cannot drop
the caveat. The live run above prints, beside a real `R:R 8.25`:

```
   Sample superseded: BB proved the window was 41-43 usable days inside a
     period described as 400, and BC proved the setup identity changed
     every bar. Read as a direction of association, never as a probability.
```

A guard test asserts no other module in the package contains a numeric literal
beyond `0`, `1`, `CLUSTER_MINIMUM` and `RECENT_LIMIT` — so a threshold cannot be
typed into a rule without failing.

---

## 3. Architecture: the crossing, and how wide it is

`fmis.today` is a **fourth application-layer root**, above `fmis.workspace`,
`fmis.daily` and `fmis.swing_setup`, and the first package to read the owner half
as well as the market half. Every layer below belongs to exactly one half, and
neither may import the other — `AP` §5.6: *"or the analysis becomes a function of
the position, the oldest bias in trading."*

**The crossing is exactly one package wide, asserted in both directions:**

| Guard | What it asserts |
|---|---|
| `test_no_engine_or_domain_package_imports_the_workspace` | No engine, no domain package and no store module imports `fmis.today` |
| `test_only_the_cli_imports_the_workspace_from_the_pipeline` | The same exception `fmis.archive` already holds — `cli.py` is the outermost edge |
| `test_the_cli_does_not_import_the_store_directly` | `fmis.pipeline` remains a market-half package that cannot reach `fmis.persistence` |
| `test_no_market_half_package_imports_the_store` | Re-asserted here, so this widening is not mistaken for permission to widen again |
| `test_importing_the_pipeline_does_not_pull_in_the_workspace_layer` | A cold `import fmis.pipeline` in a subprocess loads none of it |

**`StoreUnreadableError` exists because of that last constraint.** The CLI must
report a corrupt store without importing the store, so `read_store` wraps
`PersistenceError` and `TradeDomainError` in one `TodayError` subclass, chaining
the original as `__cause__`.

### 3.1 The one existing production file modified

`src/fmis/pipeline/cli.py`: +100 lines, entirely additive — one import, one
`_configure_today`, one `_run_today_command`, one `Command` record, one registry
entry. No existing command's parsing, behaviour or output changed; every
pre-existing CLI test passes unmodified except the four that assert the registry's
own contents.

### 3.2 Eight existing guard tests widened, each with its own recorded justification

Following the precedent `AK` (seven widenings) and `AN` (four) set:

| Test | Why |
|---|---|
| `test_decision_context.py::test_no_engine_below_imports_this_package` | `fmis.today` passes a `ContextPolicy` through and reads the sufficiency state an assessment already carries. It re-decides nothing; ADR-0026 forbids adding a threshold and none was added |
| `test_market_regime.py::test_no_engine_below_imports_this_package` | Names `RegimePolicy` only to pass the caller's policy through. Classifies nothing, prints no regime vocabulary |
| `test_multi_timeframe.py::test_no_engine_imports_the_multi_timeframe_root` | Names `TimeframeRole` only to pass the role assignment through; fetches nothing itself |
| `test_structural_facts.py::test_no_engine_imports_the_fact_sheet_root` | Names `DetectionSettings` only to pass the detection window through |
| `test_multi_timeframe.py::test_registry_names_are_unique` | A tenth command |
| `test_pipeline_cli.py::test_the_registry_still_has_every_original_command` | A tenth command, additive |
| `test_pipeline_regime.py::test_the_registry_carries_nine_commands` | Ten, registered after `daily` |
| `test_workspace_render.py::test_the_registry_carries_nine_commands` | Same |

**One guard was deliberately *not* widened.** `fmis.today.warnings` originally
named `fmis.daily` in a warning's `evidence` string and tripped that package's
raw-text import guard — the identical trap `AT` hit with a docstring reference.
The **reference was reworded**, not the guard widened: widening a guard for a
mention would weaken it for an import. `fmis.today` does not import `fmis.daily`.

### 3.3 Two names renamed to preserve the repository's zero-collision invariant

`Unavailable` → `NotAvailable` (collided with `fmis.workspace.Unavailable`) and
`LIMITATIONS` → `TODAY_LIMITATIONS` (collided with `fmis.pipeline.LIMITATIONS`).
Both were caught by the repository's own existing collision guards, not by
inspection. 646 → **697** public exports, **0** collisions.

---

## 4. What the implementation enforces rather than documents

| Rule | Where it is enforced | What it would cost to lose |
|---|---|---|
| Nothing is ranked by desirability | No sort mechanism exists in `attention.py`, asserted by AST scan | The top row reads as the best idea whatever the header says |
| A refusal is never rendered as a warning | `QueueEntry` raises if either list holds the other's severity | Refusing to size a setup would read as disliking it |
| Absence carries the inference it forbids | `NotAvailable`'s three fields are all required | A blank capital section reads as "no exposure" |
| Indeterminate is never `WITHIN` | `LimitLine.status` is a different *type*, not a different spelling | A limit nobody measured would read as a limit that held |
| No figure prints without its `n` and caveat | `MeasuredFigure.rendered()` has no short form | The warning becomes the confident number it exists to prevent |
| No threshold is invented | AST scan: no numeric literal beyond 0, 1 and two named counts | The owner's policy becomes this package's judgement |
| This package writes nothing | AST scan: no `publish`, `create`, `update`, `replace`, `append_*` | A page that could change what it reports on |
| Nothing reads a clock | AST scan over every module | Two runs over the same inputs could differ |
| No directional vocabulary of its own | AST scan; ADR-0028 applies unchanged, with no exemption | A second place `LONG`/`SHORT` lives |
| A missing store is emptiness; a corrupt one is a failure | `read_store` wraps only the decode/persistence families | A detected corruption becoming a page saying "you hold nothing" |
| One symbol's failure never stops the page | Per-symbol isolation inherited, plus a blank-message guard | The isolation the scan already provides, defeated by whitespace |
| The page never exceeds 78 columns | `_require_fits`, its own function so the boundary is testable | A value cut at a position that depends on the reader's window |

---

## 5. Test and coverage evidence

Every figure below was executed against this working tree, not quoted.

| Measure | Value |
|---|---|
| **New tests** | **247**, in 7 files plus one shared builder module |
| **Test suite** | 5,629 → **5,876**, all passing under `pytest -q -W error` — zero warnings, 170 s |
| **New-package statement coverage** | **100 %** — 975 statements, 0 missed |
| **New-package branch coverage** | **100 %** — 340 branches, 0 partial |
| **Production lines added** | 2,603 across 8 modules, plus 100 in `pipeline/cli.py` |
| **Test lines added** | 3,783 |
| **New public exports** | 51; repository total 646 → **697** |
| **Export collisions** | **0**, verified repository-wide |
| **New runtime dependencies** | **0** (asserted by test: only stdlib `ast`, `textwrap`, `dataclasses`, `datetime`, `enum`, `pathlib`, `types`, `typing`, `collections.abc`) |
| **Import cycles** | **0**, with the seven-module layering order pinned by test |
| **Existing production files modified** | **1** (`pipeline/cli.py`, additive) |
| **Existing test files modified** | **8** (guard widenings, §3.2) |

`coverage` was run through `uv run --with` against the project interpreter; it is
not installed into `.venv` and not added to `pyproject.toml`.

---

## 6. Mutation testing

15 targeted probes across all six behavioural modules, each applied to the real
source, the bytecode cache cleared before and after, and byte-identical
restoration verified by SHA-256.

| Measure | Value |
|---|---|
| **Probes** | 15 |
| **Detected** | **15** |
| **Survived** | **0** (after closing two, below) |

### 6.1 The two survivors, and what each exposed

Both were real gaps in the tests, not in the code.

1. **`sorted(..., reverse=True)` → `reverse=False` in the wait-group ordering
   survived.** The test that claimed to cover it paired a `WAIT` result with a
   `CANDIDATE` one, producing a *single* group — so no ordering could be
   observed. Closed with a test using two genuine `WAIT` populations of
   different sizes, and the original test's comment now records the mistake.

2. **The page-width guard weakened to `> _WIDTH * 2` survived.** The only test
   exercising it monkeypatched `_WIDTH` to 10, which still tripped the doubled
   bound. Closed by extracting `_require_fits` as its own function and pinning
   the comparison at exactly `_WIDTH` and `_WIDTH + 1` — 79 columns is the
   failure that actually happens, and it was untested.

---

## 7. Three real defects the tests found before release

Each was found by a test failing, not by reading the code.

1. **A blank provider message took the whole page down.** `SetupRunResult`
   guarantees a failure string when there is no assessment; it does not
   guarantee the string says anything. A whitespace-only message passed every
   check upstream and then failed `FailedSymbol`'s non-empty validation — turning
   one symbol's unhelpful error text into a crash, defeating the per-symbol
   isolation this workspace inherits. Fixed and regression-tested against two
   blank shapes.

2. **A corrupt store escaped as an unhandled traceback.** `read_store` caught
   `PersistenceError`, but a hand-edited index row fails the *domain's* decoder
   (`PayloadDecodeError`, a `TradeDomainError`) long before any store-level check
   runs. The two families are separate hierarchies. Fixed by catching both; the
   comment records that the hierarchy was misread, not merely under-specified.

3. **Long identifiers and paths overflowed the 78-column page in four places** —
   a 69-character market-snapshot id, a 64-character store path, a budget note,
   and a position line. The first draft clipped them with an ellipsis; that was
   replaced with lossless wrapping, because a truncated record id is one a reader
   copies and cannot look up. The cost is a path that wraps mid-token, which is
   ugly and visible in §8's live run.

---

## 8. Live verification

Run against real Binance data on 2026-08-12 at 21:45 UTC, four symbols, exit
code 0.

**Empty store.** Complete page: 1 `CONFIRMED` (DOTUSDT `SHORT`, R:R 8.25), 3
`WAIT` (2 for an indeterminate context regime, 1 for disagreeing families), 0
errors. Capital, journal and analysis sections each rendered `not available`
with their reason, their owning slice and the inference their absence forbids.
The DOTUSDT R:R of 8.25 raised `R-RR-ELEVATED`, printing the 7.7 %/74.5 %
association, `n = 146`, and the superseded-sample caveat — beside the number, in
the queue, and again in the warnings section.

**Populated store** (one trade, one journal entry, one risk budget, written
through the real repositories): the capital section reported the folded position
(`binance:BTCUSDT:spot`, `long`, `0.5 BTC`, entry `30000 ÷ 0.5`), the budget in
force with its policy version, and its one configured limit with
`status: indeterminate — nothing measured against it`. The journal section
reported the entry. **Nothing was written**: the store's file listing was
byte-identical before and after, asserted by test as well as observed.

---

## 9. Known limitations, stated rather than implied

1. **No single directional regime label.** §2.1. This is the one deviation from
   the brief's literal wording.
2. **No freshness triple.** The page shows one analysis instant per symbol, not
   the age of each timeframe role, because `SetupAssessment` carries one `as_of`
   and this package does not fetch. The context role — which gates whether any
   direction may exist — was measured 8 d 16 h stale in `BE`'s own live run, and
   this page cannot show that. Raised on every run as `L-NO-FRESHNESS`.
3. **No position size, open risk or portfolio exposure is computed.** Open risk
   needs a mark for every holding and a recorded stop for every position; neither
   exists. Rendered as `NotAvailable`, never as a zero.
4. **No correlation is measured.** `R-CLUSTER` counts actionable setups sharing
   one side; it does not claim those markets move together, and says so.
5. **No change comparison.** *"What changed since yesterday"* would require
   decoding two archived payloads and defining what a difference is; neither
   exists. The section states what a comparison would need and performs none.
6. **The store is read whole on every run.** `search` is O(index rows), the same
   cost curve report 0015 §9 item 5 already accepted.
7. **Two budget or portfolio lineages resolve to `None`.** Picking one would make
   *which limits apply* depend on an id sort nobody wrote down. A store with two
   is not an error and is not guessed at.
8. **`--no-records` is distinguishable from an empty store**, but nothing
   distinguishes an empty store from one whose records live on another machine.
9. **A long store path wraps mid-token.** §7 item 3 — deliberate, and ugly.
10. **The backlog's exactly-one-NOW rule remains unsatisfied.** This was an
    explicitly scoped, owner-directed implementation task, like `BI`, `BH`, `AT`,
    `AU` and `AV` before it — not a NOW selection.

---

## 10. What a reviewer should attack first

1. **`CONFIRMED` before `CANDIDATE` in the queue.** It is the engine's own
   readiness state and the grouping `scan_report` already applies, but it *is*
   an ordering, and the top row is still the top row. §2.2 argues it is not a
   desirability claim; a reviewer should test that argument against a real
   morning.
2. **`CLUSTER_MINIMUM = 3`.** Justified as the count the motivating live run
   produced rather than as a chosen threshold. That justification is thinner
   than the two measured figures' and should be read sceptically.
3. **The breadth table.** It counts already-final verdicts, but a table of
   counts by side is one mental step from a market call, which is the object
   ADR-0025 refuses.
4. **`read_store` catching `TradeDomainError`.** Broad. It is the family a
   corrupt payload raises, but a domain validation bug inside this package's own
   adapters would be reported as a corrupt store.
5. **The store is read on every run, including when nothing has changed.** No
   caching, deliberately — but the first thing a large store will notice.
6. **`RECENT_LIMIT = 5`.** A layout decision that silently drops older records
   from three sections. The count of what was dropped is stated in the journal
   section's note and *not* in the analysis section's.

---

## 11. Documents updated

`FMITS_PRODUCT_CHANGELOG.md` (a user-visible capability),
`FMITS_PRODUCT_BACKLOG.md` §8, `docs/AI_HANDOFF/CURRENT_STATE.md`, and
`reports/README.md`. **No ADR was written and no accepted ADR was amended**: this
milestone creates no new contract. It occupies a boundary — the first package
reading both halves — which is asserted by test in both directions (§3) and
recorded here; whether that boundary deserves an ADR of its own is a decision
that belongs to the owner.

**No design document was written.** Implementation forced no design decision the
existing records did not already contain: `BE` designed the page, `BF` designed
the warning taxonomy, `BG` designed the domain and `BI` built the store. The one
place implementation departed from a brief is §2.1, and it is recorded here.
