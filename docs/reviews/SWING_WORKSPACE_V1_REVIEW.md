# Swing Trading Workspace v1 — Independent Review

**Milestone:** AK
**Reviews:** [design](../design/SWING_WORKSPACE_V1.md)
**Date:** 2026-08-04
**Verdict:** no P0, no P1, **five P2 found and fixed**, three P3 documented

Every claim was re-derived from production code. Counts, coverage and mutation
results were measured in this review, not copied from the design.

---

## 1. Scope

Five questions:

1. Does the workspace **compute** anything it should have composed?
2. Is an unbuilt section genuinely impossible to mistake for an answered one?
3. Does conflict detection stay on the reporting side of the line?
4. Are `decision_support` and `evidence` **used**, or re-implemented?
5. Does anything on the page assert more than the facts support?

---

## 2. Composition, not computation — verified

`sections.py` contains **no** subtraction, multiplication, division, power or
modulo, asserted by AST. `builder.py` calls no engine function — not
`detect_swings`, `structural_levels`, `derive_structure_breaks`,
`derive_level_crossings` or `classify_regime` — it calls composition roots only.
`render.py` imports `fmis.workspace.models` and nothing else.

The one join that could have been a recomputation is the evidence snapshot.
`snapshot_from_sheet` copies five fields off a `StructuralFactSheet` and is
asserted to share the *same objects* (`window`, `features`) rather than rebuild
them. Calling `analyze_symbol` instead would have fetched the same candles a
second time and could have produced two different `as_of` values on one page.

## 3. Reachability — the milestone's real product value

Before AK, three accepted packages had **zero production importers**:
`fmis.decision_support` (674 statements), `fmis.evidence` (291),
`fmis.trading_context` (166). All three now have one.

The join between the first two turned out to be free and is worth recording:
**`Observation.key` is already the `EvidenceDescriptor` name**, so placing an
observation in its family is `find(key)` — a lookup, not a heuristic. A test
asserts every observation the report produces resolves to a catalogued
descriptor, so a rename breaks loudly instead of silently binning observations.

## 4. Findings

### P2-1 — conflict output depended on the order its inputs arrived in *(found and fixed)*

`detect_conflicts` paired roles in input order, so reversing the input produced
`"execution · 4h … while setup · 1d …"` where the same facts had produced
`"setup · 1d … while execution · 4h …"`. Two runs over identical data disagreed
about their own output.

**Found by a test written for the design's claim** that the order is
"content-only, so permuting the inputs cannot change the output" — the claim was
false when written.

**Fixed** by sorting roles into canonical order before any pair is described,
using an explicit `_ROLE_RANK` declared locally rather than reaching into
`fmis.pipeline.multi_timeframe`'s private ordering.

### P2-2 — the levels section could print a heading from one view over another view's numbers *(found and fixed)*

The section's label came from `primary_label` while its numbers came from
`view`. A mutation pointing `view` at `views[0]` produced a section headed
**execution · 4h** carrying **context · 1w** prices, and **every existing
assertion accepted it**, because each checked only the label.

This is the most dangerous defect class the milestone could ship: a correctly
formatted page stating the wrong instrument's numbers under the right heading.

**Fixed** by asserting the rendered values against the primary view's own sheet,
not against the label.

### P2-3 — the page overran its own width contract in four places *(found and fixed)*

The structure table (81 columns), the evidence table (88), the conflicts table
(116) and every limitation row (up to 221) exceeded the 78-column page. A
terminal wrapping a table row mid-value produces something a reader parses as a
different value.

**Fixed** three ways, each at the right layer: `RowBlock` rendering now wraps a
row that will not fit; the structure and evidence tables dropped a column each,
with the removed counts moved into notes; and `TableBlock` rendering now
**raises** if a table is wider than the page, so a future provider cannot
reintroduce the defect silently.

### P2-4 — the evidence table said "no engine" where the truth was "no descriptor" *(found and fixed)*

Eight of ten families showed `no engine`. That is **factually wrong** for four of
them: volume, volatility, market structure and relative strength all have engines
in this repository — what they lack is a *descriptor*, because ADR-0011 §1 earns
one by being **classified**, not merely calculated.

**Fixed**: the column now reads `no descriptor`, the note distinguishes the two
cases explicitly, and coverage is asked of the catalogue (`descriptors_for`)
rather than inferred from whether observations happened to land in a bucket.

### P2-5 — the CLI imported `fmis.trading_context`, violating ADR-0009 *(found and fixed)*

`fmis.pipeline.cli` imported `TradingObjective` to name the objective. ADR-0009's
guard lists `pipeline` among the layers that may not import that package, and the
guard failed.

**Fixed by removing the import, not by widening the guard.** The `swing` command
does not need to name its objective — the builder's default already is
`SWING_TRADE`, and the command's name says the same thing.

### P3-1 — evidence covers the primary timeframe only

Structure and regime are reported for all three roles; evidence and levels for
the primary role alone. `decision_support` consumes one `AnalysisSnapshot`, so
per-view evidence would mean three reports and a much longer page. Recorded as
limitation `AK-4` and printed on every run.

### P3-2 — `dominant_alignment` is directional, and is shown

The evidence note prints `Dominant alignment: downward`. That word is
`Alignment`'s own vocabulary and ADR-0008 §7 reports it as a **fact** separate
from the undirectional `OverallState`. It is shown with a caveat naming it *the
grouping key the evidence layer used, not a view about price*. Recorded rather
than removed, because suppressing a fact the evidence layer publishes would
misrepresent that layer.

### P3-3 — a `Workspace` cannot be pickled

`MappingProxyType` metadata, the repository-wide convention. `StructuralFactSheet`
and `MarketRegime` share it. Persistence is open decision **D-01**; the answer
belongs to every metadata-carrying model at once.

## 5. Mutation results

**49 probes · 49 detected · 0 survivors · 0 no-ops**, byte-identical source
restoration verified by SHA-256 across all six touched modules.

**Twelve probes survived their first run, and one was a no-op.** Every one of the
twelve was a real assertion gap in a suite that already had **100 % line
coverage** — which is the clearest demonstration this repository has produced of
why coverage and mutation measure different things:

| Probe | What the gap was |
|---|---|
| a section may appear twice | the fixture also broke the *order* check, so the duplicate guard never ran |
| insufficient becomes an opposite | no test paired `TRENDING` with `INSUFFICIENT` |
| regime conflict order | order independence was asserted for trends only |
| conflict kind ranking | the two statements happened to sort the same way alphabetically |
| evidence disagreement never reported | the assertion was conditional and passed vacuously |
| a dimension's reason is dropped | same — conditional on a fixture that did not trigger it |
| structural trend hard-coded | presence was asserted, never the value |
| levels read the first view | → **P2-2** |
| consistent counted as conflicting | nothing tied the table's columns to the evidence groups |
| every family claims a descriptor | coverage was described in a note, never asserted |
| incomplete coverage reports available | the `PARTIAL` status was never checked |
| conflict branches swapped | both branches carry the same caveat, so only the body distinguishes them |

The no-op was a harness anchor that did not match the source; corrected and
re-run, the probe was detected.

## 6. Measured results

**3,702 tests pass**, identically under `-W error` (3,582 before AK; **+120**).

| Module | Coverage |
|---|---|
| `workspace/models.py` | **100 %** |
| `workspace/sections.py` | **100 %** |
| `workspace/conflicts.py` | **100 %** |
| `workspace/builder.py` | **100 %** |
| `workspace/render.py` | **100 %** |
| `workspace/__init__.py` | **100 %** |
| `pipeline/cli.py` | **100 %** |

Public exports **212**, zero collisions. Import cycles **0**. Runtime
dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

## 7. Adversarial inputs

| Input | Result |
|---|---|
| A section missing from the page | `WorkspaceError` naming it |
| Sections out of canonical order | `WorkspaceError` citing `SECTION_ORDER` |
| A section repeated in place | `WorkspaceError` |
| A `Section` claiming `UNAVAILABLE` | rejected — the two are different types |
| A `FAILED` section with no reason | rejected |
| An `Unavailable` with a blank owner or prohibition | rejected |
| A table record shorter than its columns | rejected, never padded |
| A table wider than the page | rejected at render |
| An unregistered block type | `TypeError`, never silent |
| A 40-candle view | `PARTIAL`, warm-up named, page still true |
| A 12-candle view | both nearest levels absent with reasons |
| A window with no closed candle | evidence `FAILED` with a reason; every other section still available |
| An unknown `primary_role` | `ValueError` naming the available roles |
| An uncatalogued observation key | counted in no family, and said so |
| Conflicts supplied in reverse order | identical output |
| A very long source name | page still within 78 columns |

## 8. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 5 | Order-dependent conflicts · mislabelled levels · four width overruns · "no engine" vs "no descriptor" · an ADR-0009 import violation — **all fixed** |
| **P3** | 3 | Evidence is primary-timeframe only · `dominant_alignment` is shown · not picklable (D-01) |

The milestone does what it claimed: one page, one object, every section present,
the unbuilt ones naming their owner and the inference they forbid, and three
shipped packages reachable for the first time.

**The thing this review would not let pass** is the phrase "full coverage" as
evidence of a tested suite. Twelve mutations survived against 100 % line
coverage, and two of them — the mislabelled levels section and the
order-dependent conflicts — would have shipped a page that was confidently and
quietly wrong.
