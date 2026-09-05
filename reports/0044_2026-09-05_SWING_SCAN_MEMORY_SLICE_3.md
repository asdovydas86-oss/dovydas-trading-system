| Field | Value |
|---|---|
| **Report number** | 0044 |
| **Title** | Swing Product Slice 3 — Scan Memory and "What Changed" |
| **Date** | 2026-09-05 |
| **Report type** | Implementation (product) |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `77b956d` (baseline) |
| **Status** | Final |

---

# Swing Product Slice 3 — Scan Memory and "What Changed"

## 1. The Product First problem

Slice 1 made every scanned symbol's evidence reachable. Slice 2 put the trading question
above the audit question and named the condition holding each symbol. After both, FMITS
could answer:

> **What is happening with this symbol now, and why?**

It could not answer:

> **What changed since the last time I looked?**

That gap was not cosmetic. The Swing workspace scans twenty symbols and the great majority
of them sit at `WAIT` for days at a time. A `WAIT` symbol whose **reason** for waiting moved
from *the higher-timeframe regime gate rejected it* to *the directional families disagree*
is in a materially different operational situation — the gate it could not pass is now
passed — and on the Slice 2 page those two states render identically apart from one cell
the operator would have to have memorised.

So the workflow was: open the dashboard, read twenty rows, and compare them against a
recollection of yesterday's twenty rows. In practice that comparison did not happen.

**What Dovydas had to remember manually before Slice 3:** every symbol's decision, policy
direction, developing-evidence state, named blocker, decision-context sufficiency, and three
per-role structural trends — twenty symbols × eight states, held in his head between
sessions, with no record anywhere in the product to check against.

## 2. Baseline

| | |
|---|---|
| `HEAD` / local `main` / `origin/main` / `git ls-remote` | `77b956d432582fe35f10467211201d19807367bc` — all four identical |
| ahead / behind | `0 / 0` |
| tracked tree | clean |
| untracked | exactly 16 pre-existing research documents, none modified |
| stash | empty |
| active git operation | none |
| operator dashboard | PID **49813**, `.venv/bin/fmits dashboard`, listening on `127.0.0.1:8787`, started 2026-09-04 14:36:35 |

The dashboard process was identified by `lsof -nP -iTCP:8787 -sTCP:LISTEN` and its full
command line read from `ps`, never by assuming the reported PID and never by `pkill -f`.
It was not stopped at any point during development; all manual verification used a
separate port and a separate history root.

## 3. Existing persistence, inspected before anything was designed

Four candidates already exist in the repository, and each was read before a fifth was
considered:

| Mechanism | What it is | Why it is not this |
|---|---|---|
| `fmis.persistence.RecordStore` | The trade domain's journalled store — hash-chained write journal, rebuildable index, frozen records, lineage | Its journal is a legal-grade audit trail of money movements. A market observation that will be discarded in eight refreshes does not belong in it, and **it never prunes**. |
| `fmis.archive.ArchiveStore` (ADR-0027) | The permanent, content-addressed record of what the system decided — manifest, content digests | An archive is *permanent by definition*. Scan memory must prune, must tolerate corruption, and must define comparability rather than lineage. Adding a record type would also have meant widening the archive's import guard to a fifth package. |
| `fmis.snapshotting` | Frozen readings at a decision instant | No producer, and it freezes one decision rather than one scan. |
| `fmis.archive.atomic.atomic_write` | Build bytes in memory → temp file in the same directory → flush → fsync → `os.replace` | **Reused.** `fmis.persistence.store` already reuses exactly this primitive for exactly this reason. |

**Decision:** a small dedicated store in a new `fmis.scan_memory` package, built on the
existing atomic-publish primitive and the existing runtime-root convention
(`~/.fmits/<name>`, beside `~/.fmits/archive` and `~/.fmits/store`). The semantics differ
from both existing stores on every axis that matters — bounded retention, tolerated
corruption, comparability rather than lineage — and that is documented in the store's own
module docstring rather than only here.

## 4. Architecture

```
run_swing_workspace()            ← the scan the dashboard already performs, once
        │
        ▼
scan_record_from(workspace)      ← fmis.scan_memory.projection   (pure)
        │
        ▼
compare_and_record(record)       ← fmis.scan_memory.recorder     (the one writer)
   ├── store.latest_complete()   ← read the previous comparable completed scan
   ├── compare_scans(prev, cur)  ← fmis.scan_memory.comparison   (pure)
   └── store.append(cur)         ← atomic publish, then prune
        │
        ▼
scan_change_view(comparison)     ← fmis.operator_dashboard.sections (pure mapping)
        │
        ▼
OperatorDashboardSnapshot.scan_change  →  /swing and /swing/{symbol}
```

The arrow never runs backwards. **No previous snapshot reaches trading policy**, and the
import direction is asserted for twenty-six packages by
`test_nothing_that_decides_can_reach_scan_memory`.

**Where the write lives, and why not in the dashboard.** `fmis.operator_dashboard` writes
nothing, anywhere, by any means, and three guard tests assert it — no store verb, no `open`,
no filesystem call. So the seam that persists a scan is placed one layer up, in
`fmis/pipeline/scan_memory.py`: the refresh is performed through `refresh`'s **existing**
`workspace_runner` injection seam, the workspace it produced is captured, the scan is
recorded, and the comparison is handed to the snapshot as an already-computed view. That is
the same discipline `--lab-artifact`, `--geometry-artifact` and `--validation-artifact`
already follow — decoded by the caller, handed to the dashboard already parsed — applied to
the one input produced per refresh rather than once at startup.

**No extra engine read.** The scan the dashboard renders and the scan that is remembered are
one call, so a page and its history cannot disagree about what the market did.

## 5. Scan identity

`ScanIdentity(schema_version, universe, timeframes, reference_time, analysis_as_of)`.

`scan_id` is `sha256` over those five fields, truncated to 32 hex characters.

**The identity digest deliberately excludes the scan's results.** A digest over the states
would give two scans that observed identical market state one id, so the second could never
be recorded — and *nothing changed* would become indistinguishable from *nothing ran*.
Asserted by `test_the_scan_id_does_not_depend_on_what_the_scan_found`.

**Completeness is coverage, not success.** A scan is complete when every symbol its universe
asked for produced an assessment. A scan that lost a symbol to a provider outage is recorded
— honestly, with the symbol named — but is never chosen as a baseline.

## 6. Comparable-scan semantics

`incomparable_reason(previous, current)` returns the reason, or `""`. Five conditions, all
structural:

1. **schema version** differs;
2. **universe** differs — a different watchlist is a different question, not a changed market;
3. **timeframe roles** differ — different structural states answer a different question;
4. the previous scan is **not complete** — a partial scan is never a baseline;
5. the "previous" record **is this same scan** — which is what makes a duplicated observation
   an idempotent no-op instead of a fake `A → A`.

**§33's universe question, decided:** a universe change makes two scans **non-comparable**,
and the product says so rather than presenting a delta. Within one universe, a symbol
appearing or disappearing is a `PRESENCE` transition, labelled *produced no assessment* —
never bearish, broken or failed. A test asserts that vocabulary directly.

## 7. What is persisted

Per scan: the identity, `recorded_at`, one `SymbolState` per assessed symbol, and the names
of the symbols that produced nothing.

Per symbol — the narrowest projection that answers the operator's change questions:

| Field | Compared? | Why |
|---|---|---|
| `state`, `direction`, `sufficiency`, `classification` | ✅ | the policy's own conclusions |
| `developing_state`, `developing_lean` | ✅ (as one dimension) | so a side can never be shown without the state beside it |
| `blocker_kind` | ✅ | the **category**, never the sentence |
| `structural_trends` (context / setup / execution) | ✅ (one dimension each) | the engine's own `structural_trend` values |
| `independence_established`, `evidence_available` | ✅ | |
| `supporting` / `conflicting` / `missing` / `unavailable` counts | ✅ (as one dimension) | |
| `as_of` | ❌ provenance | so a surface can print what the previous scan saw |
| `blocker_observed` | ❌ provenance | §30: the value that failed the condition is not the category |

**Not persisted at all:** thesis lines, regime prose, blocker statements, confirmation and
invalidation text, evidence items, directional factors, per-role reading instants, ages,
closed-bar counts, provider payloads, candles, and rendered HTML.

That last group is the structural guarantee behind §12: **the comparator cannot report a
routine observation update as a change, because it cannot see one.** Two tests assert the
absence of those fields on the model, and a third asserts `dimension_values` is unchanged by
moving `as_of` a year.

## 8. Schema version, storage location, retention, atomicity

| | |
|---|---|
| **Schema version** | `SCAN_MEMORY_SCHEMA_VERSION = 1`, written into every record and checked on every read. An unsupported version is refused with the number in the message, never reinterpreted. |
| **Location** | `~/.fmits/scan_memory/scans/<recorded_at compact UTC>-<scan_id[:12]>.json` — **outside the git checkout**, beside `~/.fmits/archive` and `~/.fmits/store`. No ignore rule was needed or added, because runtime history is not inside the repository at all. Overridable with `fmits dashboard --scan-history-root PATH`. |
| **Retention** | `DEFAULT_RETAINED_SCANS = 8`, deterministic (newest 8 by name), pruned after every publish. The product needs *current and previous*; the extra six are slack so a run of incomplete scans cannot push the last complete baseline out of the window. **Not** an analytics history — nothing reads further back than the first complete record. |
| **Atomicity** | every file published through `fmis.archive.atomic.atomic_write`. An interrupted write leaves a dot-prefixed `.tmp` that the `*.json` glob never sees. A reader gets no file or a complete file; there is no third outcome. |
| **Filename ordering** | lexicographic order **is** chronological order, so finding the previous scan is a directory listing and one decode — not a walk of every record. |

## 9. Failure semantics

| What failed | Current analysis | Change surface |
|---|---|---|
| the scan itself | not produced — the swing section says so | not rendered; **nothing recorded** |
| reading history (corrupt / unsupported schema) | unaffected | *history unavailable*, with the reason |
| the two scans are not comparable | unaffected | *no previous comparable scan*, with the reason |
| publishing this scan | unaffected | still compared; **states that this scan was not recorded** |
| the current scan is incomplete | shown as it is | compared; **states it is not used as a baseline** |

**A corrupt newest record makes history unavailable rather than wrong.** Skipping it to reach
an older one would silently redefine *the previous scan* as *some earlier scan*, over a gap
nobody was told about.

**Not one of those paths reports *nothing changed*.** That is a claim about the market and is
only ever made when two comparable scans really were compared — enforced on the type:
`ScanComparison` refuses to hold per-symbol results under any status but `COMPARED`.

## 10. Concurrency and idempotence

* **A page `GET` never records anything.** `SnapshotHolder` calls its refresher on warm-up, on
  `?refresh=1`, and on the first request of an unwarmed server; every other request returns the
  held snapshot. Rendering does not refresh, so it does not record. Asserted by rendering three
  routes four times and watching the record count stay at 1.
* **The record path is a pure function of the scan's identity**, so recording the same completed
  scan twice targets the same file rather than appending a second row.
* **A scan is never compared with a stored copy of itself** — `latest_complete(exclude=…)`.
* **Within a process** refreshes are already serialised by `SnapshotHolder`'s lock. **Across
  processes** names are unique per scan identity, so two writers cannot collide on one file and
  neither can produce a half record; that is stated in the store's docstring rather than
  defended against, because this is a single-operator local product.
* **The renderer is read-only** and stays so: `fmis.operator_dashboard` gained no write verb,
  no `open`, and no filesystem call, and its three existing guards still pass.

## 11. Material change semantics

`ChangeDimension` — twelve members, declaration order is display order and **not** an
importance order:

`presence` · `decision` · `policy_direction` · `decision_context` · `developing_evidence` ·
`blocker` · `context_structure` · `setup_structure` · `execution_structure` ·
`evidence_independence` · `evidence_availability` · `evidence_composition`

`CHANGE_DIMENSIONS` **is the whole comparison surface**, and a test asserts that
`dimension_values()` reads exactly it — so a dimension added to the enum and not read would
fail rather than silently never fire.

**Explicitly ignored as routine:** the scan instant, the per-symbol assessment instant, every
per-role reading instant, every age, every closed-bar count, and the blocker's observed value.
None of them is a dimension; most are not even persisted.

**No score, no rank, no importance.** There is no field in the package that could hold one, and
a guard asserts no field name matches a sixteen-word ranking vocabulary. Attention is provided
by a **partition** — changed symbols separated from unchanged ones, each group in the scan's own
universe order — which is asserted as an ordering test, not left as an intention.

## 12. The transitions, proved over the live engine

Every controlled transition below is produced by the **real** composition root
(`setup_assessment_for_sheet` over seeded synthetic candles) through the **real** workspace
builder, the **real** projection and the **real** renderer:

| Transition | Fixture | What the page shows |
|---|---|---|
| **Blocker moved, decision held** (§30, §44A — the BTC-shaped case) | `GATE_REJECTED → FAMILIES_SPLIT` | `WAIT` on both scans; `Blocker: HTF regime not eligible → timeframes disagree`, and `HTF context structure: neutral → sustained lower` |
| **Decision transition** (§28, §44B) | `GATE_REJECTED → CANDIDATE` | `Decision: wait → candidate`, `Policy direction: not stated → …`. Never called a buy signal. |
| **Decision transition, the other way** | `CANDIDATE → GATE_REJECTED` | `Decision: candidate → wait`. Never called a failed trade — nothing was ever taken. |
| **Developing evidence** (§29, §44C) | `GATE_REJECTED → GATE_LEANING` | `Developing evidence: divided → leaning · …`, with the decision unchanged at `WAIT` |
| **Structural state** (§32) | live `structural_trend` values | separate dimensions for context, setup and execution roles |
| **No change** (§44D) | `GATE_REJECTED → GATE_REJECTED` | one sentence, once |
| **First scan** (§44E) | empty store | *Baseline scan recorded. Changes appear after the next comparable refresh.* |

A non-vacuity test asserts the three fixtures reach three genuinely different exits of
`evaluate_setup`, so a transition between them is one the live product can produce.

## 13. The surfaces

**`/swing`** — a new panel, *Since the previous comparable scan*, rendered **above** the
existing workspace. The question it answers — *is there anything here I have not already
seen?* — decides whether the twenty rows below need reading at all. It never replaces them.

```
SINCE THE PREVIOUS COMPARABLE SCAN

  Previous comparable scan   This scan          Changed   No material change
  2026-08-24 12:00Z          2026-08-24 16:00Z  1         0

  AAAUSDT — CANDIDATE   previously wait

  Changed                  From                        To
  Decision                 wait                        candidate
  Policy direction         not stated                  …
  Developing evidence      divided                     direction stated · …
  Blocker                  HTF regime not eligible     awaiting confirmation
  HTF context structure    neutral                     sustained higher
  Execution structure      sustained lower             neutral
  Evidence composition     supporting 2 · conflicting 1 · …   supporting 4 · …

  1 of 1 symbols changed on at least one dimension, in the scan's own order.
  This is not an ordering by importance.
```

With zero changes: one sentence — *No material Swing state change since the previous
comparable scan.* — and a collapsed `<details>` naming the unchanged symbols. **Not** twenty
rows of `UNCHANGED`; the workspace below already states every symbol's current state.

**`/swing/{symbol}`** — a compact block, rendered **after** the operator summary and before the
evidence audit, so the current decision stays first. It states only the dimensions that moved;
unchanged dimensions are omitted. With no change: *No material Swing state change for this
symbol since the previous comparable scan.* With no baseline: the baseline sentence.

**Vocabulary.** `CHANGED` / `FROM` / `TO` / `CURRENT` / `PREVIOUS` / `SINCE PREVIOUS
COMPARABLE SCAN`. No `NEW`, `IMPROVED`, `WORSE`, `STRONGER`, `WEAKER`. A parametrized test
asserts sixteen forbidden words are absent from the panel's own markup, with the panel's
stated limitations excluded from the scan — the disclaimer is allowed to name what it refuses.

**No freshness verdict.** Slice 2 found no validated per-role staleness bound and Slice 3
invents none; a test asserts `fresh`, `stale` and `expired` never appear in the panel.

## 14. Policy non-regression

Slice 3 changes no policy file. `fmis/swing_setup/policy.py`, `compose.py`, `models.py`,
`decision_summary.py`, the regime engines, the evidence projection and the decision-context
verdict are **byte-for-byte unmodified**.

The Slice 1/2 canonical mechanism was re-run unchanged:
`tests/test_swing_setup_policy_non_regression.py` — 81 assessments and 81 evidence reports
across 27 seed triples × 3 symbols, each canonicalised as its complete recursive `repr()` and
digested. **Every digest matches**, including the aggregate `096a575a…` that Slice 1 and
Slice 2 both recorded.

Beyond that, a functional end-to-end test renders the **same** workspace three times against
three different store states — empty, a matching baseline, and a contradicting one — and
asserts the decision, direction, blocker kind and developing-evidence state are identical in
all three. History cannot reach the decision that is rendered.

## 15. Tests

| File | Tests | What it defends |
|---|---|---|
| `tests/test_scan_memory_models.py` | 26 | identity, completeness, comparability, the projection's field list |
| `tests/test_scan_memory_comparison.py` | 43 | every named transition over the live engine; the invariant/property half |
| `tests/test_scan_memory_store.py` | 33 | codec round trip, corruption, schema refusal, atomicity, retention, **restart continuity** |
| `tests/test_scan_memory_architecture.py` | 212 | the import direction, no prose, no ranking, no arithmetic, no clock, no alerts, no model |
| `tests/test_swing_scan_change_surface.py` | 46 | the rendered product, the refresh boundary, `GET` records nothing |
| `tests/test_swing_scan_change_non_vacuity.py` | 15 | every claim checked against the pre-Slice-3 product |
| **Total new** | **375** | |

All offline. No live Binance, FRED or provider access in any of them.

**Invariant / property tests** (§40), asserted over generated pairs rather than one example:
`compare(A, A)` reports nothing · comparison mutates neither argument · no unchanged dimension
is ever reported as changed · every reported transition has two different ends · storage order
cannot change a per-symbol result · changed symbols come out in universe order · transitions
come out in enum order · the full Cartesian product of variants never invents a dimension ·
history absence never fabricates a previous state.

**Non-vacuity** (§41). Six claims, each checked against a reconstruction of the product
without the feature: the Slice 2 page has no temporal section at all; a Slice 2 refresh writes
to no directory; an in-memory-only history is empty after the object is recreated while the
Slice 3 store is not; the blocker transition renders identically on two Slice 2 pages; the
time-only invariant is paired with a real change to prove the empty result is a decision and
not an inability to detect anything; and three type-level guards are each fired on a planted
violation.

Three existing guards were touched, each deliberately:

* `tests/architecture_tiers.py` — `scan_memory` classified **PRODUCTION**, which is what the
  partition requires of a new package and what makes the boundary guards apply to it.
* `tests/test_operator_dashboard_architecture.py` — the read-model method allowlist gained
  `compared` and `change_for`: one predicate over a stored status and one lookup by symbol
  name, neither of which derives a value.
* No guard was weakened, and no test was modified to make the suite green.

## 16. Full regression

Baseline (Slice 2): **14,155** passing under `-W error`.

Slice 3 run, `-W error`, whole suite: **14,529 passed, 2 failed, in 12:21**. Zero skips, zero new
warnings, no guard weakened, and no test modified to make the suite pass.

**14,155 → 14,531 collected — the delta is exactly the 376 tests added** (375 in the six new files
plus one startup smoke test).

### 16.1 The two failures, and why they are not this milestone's

```
FAILED tests/test_operator_dashboard_startup_smoke.py::test_the_operators_command_starts_serves_the_dashboard_and_stops
FAILED tests/test_operator_dashboard_startup_smoke.py::test_a_dashboard_whose_main_route_is_broken_is_caught
```

Both fail identically, at `_Dashboard.interrupt()`: after `SIGINT`, the dashboard subprocess does not
exit within the 30 s `EXIT_TIMEOUT`. They are the **only two smoke tests that call `interrupt()`**;
the other five make the same HTTP requests and let the fixture kill the process, and all five pass.

**They are pre-existing and reproduce at the baseline commit.** A clean `git worktree` at
`77b956d` — Slice 3 not present in any form — was run over the identical 67-file prefix:

```
this tree at 77b956d + Slice 3   2 failed, 4658 passed in 90.65s   ← the same two tests
baseline worktree at 77b956d     2 failed, 4657 passed in 92.46s   ← the same two tests
```

**They depend on position in the session, not on the code.** The same file passes every time it runs
early or alone — seven passes in a row standalone, and 4,660 passed when the smoke file is placed
*first* in the same 67-file set. It fails when preceded by ~4,650 other tests. That is a property of
the pytest process the child is spawned from, not of `fmits dashboard`: two dashboards were started
and stopped by hand during this milestone's live verification and both exited immediately.

**No fix was attempted, deliberately.** It is not a Slice 3 regression, it is outside this
milestone's scope, and the code it would touch is `serve()`'s shutdown path — the exact path report
0041 repaired and the one this smoke test exists to protect. Changing it on the way past, inside a
milestone about scan memory, is how that repair gets undone.

**Recommended as the next dashboard task**, ahead of EP-21: characterise why a child process that
served at least one request stops responding to `SIGINT` when spawned late in a large pytest session,
and either fix it or make the test's teardown honest about what it is measuring.

Two genuine regressions were found **by the full suite** and fixed at the architecture rather than
by exemption:

1. **`UNSTATED` collided with `fmis.swing_workspace.UNSTATED`.** A repository-wide guard, asserted
   from twelve different test files, requires every public name to belong to exactly one package.
   The guard was right — two packages exporting one name is exactly the ambiguity it exists to
   prevent — so scan memory's constant was renamed `NOT_STATED`, with the reason recorded beside it.

2. **`fmis/pipeline/scan_memory.py` imported `fmis.swing_workspace`**, which
   `test_only_the_cli_imports_this_package_from_the_pipeline` permits from `cli.py` alone. The guard
   was right again, and the fix improved the design: `fmis.operator_dashboard.compose` now names its
   own default — `DEFAULT_WORKSPACE_RUNNER` — and the wrapper takes **that** rather than naming the
   engine a second time. The scan that is remembered is now *by construction* the scan the dashboard
   renders, and two names for one default can no longer drift.

Three smoke-test failures were the same defect in one place: the smoke driver replaces
`SnapshotHolder`'s refresher to stay offline, and the command now supplies one too. The driver was
changed to **keep** the command's wiring and bind only the three networked runners into it —
discarding it would have taken the recording seam out of the very startup path that test exists to
exercise. The driver also now requires `--scan-history-root`, so a smoke run can never reach the
owner's real history, and a **seventh smoke test** was added: the real command records exactly one
scan, and six page loads across three routes record none.

## 17. Live verification

Performed on **port 8799** with `--scan-history-root` pointed at a scratch directory. **The
operator's dashboard on 8787 (PID 49813) was never stopped and never touched** — verified before and
after by `lsof`.

| Step | Observed |
|---|---|
| First refresh, real providers | 20 symbols, complete; `reference_time 2026-09-05T08:38:55Z`, `analysis_as_of 2026-09-05T04:00Z`, `scan_id 10d7bfa5638777b575b477b9d92b5784` |
| Baseline persisted | one file, `20260905T083855216326-10d7bfa56387.json`, 11,080 bytes |
| Read back by a **new store object** over the same directory | 20 symbols, `complete=True`, `unreadable=()` — the record decodes without the process that wrote it |
| `/swing` says | *Baseline scan recorded. Changes appear after the next comparable refresh.* — not *unchanged*, not an error |
| 7 page loads across 4 routes | all `200`; history still **1 record** |
| Process killed, a **new process** started over the same history root | baseline survives the process ending |

The live states reproduce the shapes Slices 1 and 2 recorded, now as structured memory:
**BTCUSDT** `wait` · blocker `context_regime_not_eligible` · developing `leaning/long` · context
`neutral`, setup `sustained_higher`; **BNBUSDT** `wait` · blocker `directional_families_disagree` ·
developing `divided` · context `sustained_lower` against setup `sustained_higher`; **SOLUSDT**
`wait` · `none_readable`.

## 18. Controlled product verification

Rendered through the real projection → real store → real section mapping → real renderer. The live
market did not materially change in the 83 s between the two live scans, and **no live change was
fabricated to compensate**; these are deterministic fixtures, clearly labelled as such.

**A · the blocker moves while the decision holds at `WAIT`** *(the BTC-shaped case)*

```
AAAUSDT — WAIT   previously wait

Changed                  From                       To
Blocker                  HTF regime not eligible    timeframes disagree
HTF context structure    neutral                    sustained lower
Evidence composition     supporting 2 · conflicting 1 · …   supporting 3 · conflicting 0 · …
```

**B · `WAIT → CANDIDATE`** — `Decision wait → candidate`, `Policy direction not stated → …`,
`Developing evidence divided → direction stated · …`, `Blocker HTF regime not eligible → awaiting
confirmation`, plus two structural dimensions. **B′ · `CANDIDATE → WAIT`** — the same six
dimensions, reversed, and described in exactly the same neutral vocabulary.

**C · developing evidence** — `Developing evidence divided → leaning · …`, with the decision
unchanged at `wait` and the row heading reading `AAAUSDT — WAIT previously wait`.

**D · no change** — `Changed 0 · No material change 1`, one sentence, and a collapsed list.

**E · first scan** — *Baseline scan recorded. Changes appear after the next comparable refresh.* on
both pages.

## 19. Security boundary

The persisted record holds market-analysis state and nothing else. No API key, token, auth header,
credential, private key or wallet datum can be in it, because **no field of the model could hold
one** — asserted over the encoded payload by a test that scans the JSON for seven such words. No
permission was broadened, no trading write path was created, and the dashboard remains `GET`/`HEAD`
only on loopback.

## 20. Research boundary

Unchanged and uncontradicted. **CA `NO_EDGE`**, **CB `UNDERPOWERED`**, **CC `INFEASIBLE`** and CD's
dependence conclusions are named in the package's own docstring, where somebody adding to it will
read them, and a test asserts they are there. Nothing in scan memory implies a validated strategy, a
calibrated probability, independent confirmation, predictive edge, expected return or execution
readiness. *What changed* is observational product state; it is not evidence of profitability, and
the page says so in those words.

## 21. Product First — before and after

**Before Slice 3.** Dovydas opened `/swing`, read twenty rows of current state, and compared them
against his recollection of the previous session's twenty rows. Eight states per symbol —
decision, policy direction, developing evidence, blocker, decision-context sufficiency and three
structural trends — held in his head between sessions, with nothing in the product to check against.
A `WAIT` symbol whose blocking condition had moved looked exactly like a `WAIT` symbol where nothing
had happened. Restarting the dashboard lost even the possibility of the comparison.

**After Slice 3.** FMITS remembers each completed comparable scan and states, on `/swing`, whether
anything decision-relevant changed since the previous comparable completed one — which symbols
changed, and exactly which deterministic dimensions moved, from what to what. `/swing/{symbol}` adds
the same, per symbol, beneath the current decision. When nothing changed it says so in one sentence.
When there is no baseline, or the scans are not comparable, or history could not be read, it says
which — and never *unchanged*. It survives restarts, and opening pages does not disturb it.

**What Dovydas can do now that he could not before:** open FMITS after a new Swing scan and
immediately see whether any decision-relevant state changed since the previous comparable completed
scan, which symbols changed, exactly which deterministic dimensions changed — and then drill into the
current decision and evidence — **without manually remembering the previous dashboard.**

## 22. Deferred — Slice 4 and beyond, not begun

Risk Engine product integration · position sizing · portfolio risk · trade execution · paper trading
· alerts and notifications of any kind (Telegram, email, push, Discord, daemon, background polling,
alert rules) · AI/LLM interpretation of changes · long-term scan-history analytics · historical
charts · opportunity ranking · a validated freshness policy · terminal renderer parity for the
temporal section (`fmits workspace` shows neither panel; the models carry both) · new strategy
logic · new indicators · backtest changes.

Slice 3 creates the deterministic **event substrate** an alert layer could later consume. It builds
none of that layer, and a guard test asserts no module in the package names a notification channel.

## 23. What was deliberately *not* written

**No ADR was added.** ADR-0027 governs the memory-and-decision *archive*, and scan memory is
deliberately not that: it is a bounded, prunable, corruption-tolerant rolling buffer with different
semantics on every axis. Recording that as an accepted architecture decision is the owner's call, not
this milestone's — the same position Slices 1 and 2 took. The reasoning is written where somebody
will meet it: in `fmis/scan_memory/store.py`'s own module docstring, which states which existing
mechanism was considered, and why each was not it.

**No terminal renderer.** `fmits workspace`, `fmits scan` and `fmits setup` show neither the
overview panel nor the per-symbol block. The models carry both; wiring them is a later, deliberate
edit rather than a drift.

**No `docs/AI_HANDOFF/CURRENT_STATE.md` update**, on the same footing as Slices 1 and 2 — the
milestone history there is maintained separately from a milestone's own closure.
