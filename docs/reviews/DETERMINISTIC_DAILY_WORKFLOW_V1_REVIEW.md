# Deterministic Daily Workflow v1 — Independent Review

**Milestone:** AN
**Reviews:** [design](../design/DETERMINISTIC_DAILY_WORKFLOW_V1.md)
**Date:** 2026-08-04
**Verdict:** no P0, no P1, **two P2 found and fixed**, one P3 fixed, three P3 documented

Every claim below was re-derived from production code or measured in this review.
Nothing was copied from the design.

---

## 1. Scope

Five questions:

1. Does a symbol's failure ever cost the run, or another symbol?
2. Is a **defect** distinguishable from a **market failure** — in the model, in
   the code path, and on the page?
3. Does anything rank, score, or order by an analysis property?
4. Does the daily layer re-decide anything AL or AK already decided?
5. Does the page ever show a value that is not the value?

Question 5 is where both P2s were found.

## 2. Composition, not computation — verified

`runner.py` calls exactly one composition root, `workspace_for_symbol`, and none
of `detect_swings`, `structural_levels`, `derive_structure_breaks`,
`derive_level_crossings`, `classify_regime`, `evaluate_context`,
`build_workspace`, `analyze_symbol` or `build_structural_facts` — asserted by AST
over call names. Its only arithmetic is `timer() - started`, twice.

`models.py` imports **nothing from `fmis`**. It is a pure value layer, which is
why `workspace` and `context` are typed `Any`: carrying the real types would
invert the dependency for no gain, since the model never reads them.

`render.py` imports `fmis.daily.models` and nothing else. Its only arithmetic is
header padding and the ellipsis position.

## 3. Reachability and layering

`fmis.daily` is a second application-layer root above `fmis.workspace`. Four
pre-existing import guards (`decision_context`, `market_regime`,
`multi_timeframe`, `structural_facts`) were **widened to name it**, in the same
direction and for the same reason AK widened two of them for the workspace. No
engine gained a permission, and each widening carries the reason in its
docstring.

A directory scan asserts only `fmis/pipeline/cli.py` imports `fmis.daily`, and a
subprocess asserts `import fmis.pipeline` still does not load it — so the new
edge cannot become a cycle silently. Measured: **0 import cycles.**

## 4. Findings

### P2-1 — the page printed a timestamp cut mid-value *(found and fixed)*

The first live run of `fmits daily` produced this row:

```
 ✓ BTCUSDT      sufficient    trending · contracting · typical 2026-08-04T08:0
```

`trending · contracting · typical` is **32 characters in a 30-column field**.
Python's `:<30` pads but never truncates, so the regime pushed the `AS OF` column
two places right, and the row's final `[:78]` truncation removed the last two
characters — of a **different value**. The result reads `08:0`, which a reader
parses as a time it is not.

This is the AK P2-3 defect class recurring one layer up: a correctly formatted
page stating something other than the fact beneath it. It reached a live run
because every width test asserted `len(line) <= 78` — which was **true**. The
line fit; the value inside it did not.

**Fixed three ways.** Values are now `_clip`ped to their column with a visible
`…`, so at most one value is shortened and the mark says which. The `as_of` is
`strftime`-formatted rather than sliced, because `isoformat()[:16]` produces a
string whose completeness depends on the offset's length. Column widths are
declared once and used by both the header and the rows, so a widened column
cannot drift away from its heading — asserted by a test comparing the header's
column offsets against a rendered row's.

Four probes cover the fix; all four are detected.

### P2-2 — the run recorded intervals it had not used *(found and fixed)*

`run_daily` recorded `metadata["intervals"]` as
`tuple((timeframes or {}).get(role, "") for role in TimeframeRole)`. When the
caller supplied no timeframes — the documented default — every symbol was
analysed at `1w`/`1d`/`4h`, and the run recorded:

```
recorded intervals: ('', '', '')
actually used     : ('1w', '1d', '4h')
```

A provenance field that is silently empty is worse than an absent one: a consumer
reading it concludes no intervals were used, and there is nothing to signal the
discrepancy. It also meant each `analyse_symbol` call resolved its own defaults,
so the "one setting reaches every symbol" guarantee held only by coincidence of
those defaults being constant.

**Fixed** by resolving the interval mapping **once**, before the loop, and
passing that one object to every symbol. A test asserts the recorded intervals
equal the workspace's own, and another asserts every symbol received the *same
mapping object* — the `DetectionSettings` identity check AG established, applied
to intervals.

### P3-1 — a run could be published with no limitations *(found and fixed)*

`DailyRun.limitations` defaulted to `()` and was unvalidated. The runner always
supplies four, but a second consumer building a `DailyRun` directly could publish
a page of results under a bare `LIMITATIONS` heading with nothing beneath it.
Given that `Workspace` makes its limitations section mandatory, the asymmetry was
an oversight rather than a decision.

**Fixed:** a run must state at least one limitation, and the error says why.

### P3-2 — evidence, conflicts and structure are not on the index

The index shows readiness and regime. Everything else on a workspace stays on the
workspace. This is the compactness trade the milestone exists to make, and the
footer names the command that opens any symbol in full. Recorded rather than
changed.

### P3-3 — `regime_summary` is parsed out of a rendered summary line

`_regime_line` reads the regime section's summary and splits on `": "`. It reads
rather than recomputes — which is the right direction, since a row and a page
must not disagree — but it depends on that section's line format. A structured
accessor on `Workspace` would be sturdier and belongs to the workspace, not here.

### P3-4 — a `DailyRun` cannot be pickled

`MappingProxyType` metadata, the repository-wide convention shared with
`Workspace`, `StructuralFactSheet` and `MarketRegime`. Persistence is open
decision **D-01**; the answer belongs to every metadata-carrying model at once.

## 5. Mutation results

**81 probes · 81 detected · 0 survivors · 0 no-ops**, byte-identical source
restoration verified by SHA-256 across all four touched modules, with
`__pycache__` purged before and after every probe.

**Five probes survived their first run and three were no-ops**, against a suite
that already had **100 % line coverage** on every module. Each survivor was a
real assertion gap:

| Probe | What the gap was |
|---|---|
| `INSUFFICIENT` binned as `LIMITED` | the live fixture only ever produced `SUFFICIENT`, so no test saw the other two states — fixed by asserting value-identity across the **whole** mapping rather than through a fixture |
| the requested symbol overwritten by the resolved one | the provider answers about exactly what it is asked, so the two fields were equal in every test — fixed by staging a workspace naming a different instrument |
| the regime line reads a non-primary view | all three timeframes classified alike in the fixture, so reading the wrong one looked correct — fixed with three deliberately different per-role summaries |
| a non-datetime `reference_time` accepted | the model rejected it anyway, so the test passed either way; the runner's guard exists to fail **before 150 fetches** — fixed by asserting the transport was never called |
| the readiness word dropped, leaving only a glyph | the word also appears in the summary counts, so a page-wide search passed — fixed by asserting per row |

The three no-ops were harness defects, not passes: `cli.py` contains the same
argument-passing lines in five commands, so three anchors matched twice and were
rejected rather than counted. Disambiguated with surrounding context and re-run,
all three were detected. Two further probes went stale when the P2-1 fix changed
the row's source; refreshed and re-run, both were detected.

## 6. Measured results

**3,905 tests pass**, identically under `-W error` (3,766 before AN; **+139**).

| Module | Coverage |
|---|---|
| `daily/models.py` | **100 %** |
| `daily/runner.py` | **100 %** |
| `daily/render.py` | **100 %** |
| `daily/__init__.py` | **100 %** |
| `pipeline/cli.py` | **100 %** |

Coverage was measured with a `sys.settrace` line tracer rather than by installing
`coverage`, because the repository ships **zero** runtime and one test dependency
and `uv.lock` must not move for a measurement.

Public exports **242** (228 before AN; **+14**), zero collisions. Import cycles
**0**. Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

> **Counting convention.** 242 counts `__all__` entries across **subpackage**
> `__init__.py` files, the convention this repository has used since AG. Counting
> the root `src/fmis/__init__.py` as well — whose `__all__` is `["__version__"]` —
> gives 243.

**Performance.** Compute is **22 ms per symbol** and linear (measured offline at
1, 5, 10, 20 and 50 symbols). A live three-symbol run took **4.58 s wall**, of
which FMITS compute was **1.4 %**; the rest is nine HTTPS round trips. Fifty
symbols renders in **83 lines** against roughly 13,500 for fifty full pages.

## 7. Adversarial inputs

| Input | Result |
|---|---|
| A symbol the provider rejects | one row, `invalid_symbol`, run continues, exit 0 |
| A transport outage mid-universe | one row, `provider_failure`, later symbols still analysed |
| An undecodable response | `malformed_data`, distinct from a rejected symbol |
| A window too thin to analyse | `insufficient_data` — a failure, not an `INSUFFICIENT` analysis |
| A `KeyError` from inside FMITS | **propagates**; the run stops |
| `RuntimeError`, `AttributeError`, `ZeroDivisionError` | all propagate |
| A repeated symbol | rejected, before any request is made |
| A blank or empty universe | rejected with the position named |
| The bare string `"BTCUSDT"` | rejected — never seven single-character symbols |
| 51 symbols | rejected, naming the maximum; 50 accepted |
| A lowercase symbol | provider rejects it; the row still says what was typed |
| A non-datetime `reference_time` | rejected before the first fetch |
| A regime longer than its column | clipped with `…`; the timestamp stays whole |
| A 25-character symbol | clipped; later columns undisturbed |
| A 240-character failure message | wrapped; no line over 78 |
| A run with no limitations | rejected |
| A page line over 78 columns | **raises** rather than printing |
| A workspace naming a different symbol | both names reported, neither overwritten |

## 8. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 2 | A timestamp truncated mid-value · a run recording intervals it did not use — **both fixed** |
| **P3** | 4 | Limitations could be empty (**fixed**) · index omits evidence and conflicts · `regime_summary` is parsed from a rendered line · not picklable (D-01) |

The milestone does what it claimed: one command, one object, one row per
requested symbol in the order requested, a failure that reports itself and does
not take the run with it, and a page that fits on a screen.

**The thing this review would not let pass** is `len(line) <= 78` as evidence
that a page is correct. Every width test passed while the page was printing
`2026-08-04T08:0` — because the line fit and the value inside it did not. Width
is a property of the page; truth is a property of each value on it, and only the
second one matters.
