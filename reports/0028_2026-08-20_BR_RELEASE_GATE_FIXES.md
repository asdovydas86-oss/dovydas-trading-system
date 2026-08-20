# Report 0028 — Setup Evidence (Milestone BR) — Release-Gate Fixes

| | |
|---|---|
| **Report number** | 0028 |
| **Title** | Setup Evidence (Milestone BR) — release-gate defects and their fixes |
| **Date** | 2026-08-20 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `main` / `f2cacf5` (production code + tests), on top of `c1a91e7` |
| **Status** | Final |

---

## 1. Why this report exists

An independent release gate was run over Milestone BR **after** its two commits
(`2059ca7`, `c1a91e7`) were already in `origin/main`. The gate found two defects that the
8,693-test suite did not: one of them crashed `fmits evidence` on live market data.

This report records both, their root causes, the fixes, and the verification. It supersedes
nothing in report 0027 — that record remains accurate about what BR built. It corrects two
things BR got wrong.

**The gate's most important finding is not either defect. It is that a full green suite,
94% statement coverage and 15 killed mutation probes did not catch a crash on the first
live symbol outside the fixture set.** Both defects were found by running the product, not
by running the tests.

---

## 2. Defect 1 — the confluence invariant rejected a legitimate report

### Symptom

```
$ fmits evidence SOLUSDT
Traceback (most recent call last):
  ...
  File "src/fmis/setup_evidence/models.py", line 264, in __post_init__
    raise SetupEvidenceError(
fmis.setup_evidence.models.SetupEvidenceError: independent_agreeing_families cannot
exceed agreeing_item_count; distinct families are counted over the agreeing items themselves
$ echo $?
1
```

One of twenty live symbols surveyed hit this. It is market-state dependent, so any symbol
can enter the state.

### Root cause

Two deliberate design decisions inside the same package contradicted each other.

`EvidenceItem.families` is a **tuple** on purpose. `correlation.FACTOR_FAMILIES` maps
`setup_evidence_alignment` onto **two** families:

```python
"setup_evidence_alignment": (EvidenceFamily.TREND, EvidenceFamily.MOMENTUM),
```

because `fmis.decision_support` reduces three TREND observations and two MOMENTUM
observations to a single `dominant_alignment` and does not report which drove it. Assigning
it to one family would be a fabricated attribution — `models.py` says so explicitly.

But `ConfluenceSummary.__post_init__` asserted:

```python
if self.independent_agreeing_families > self.agreeing_item_count:
    raise SetupEvidenceError(...)
```

`agreeing_item_count` counts **items**; `independent_agreeing_families` counts **distinct
families over those items**. When the alignment was the *only* agreeing item, `_confluence`
computed 1 item and 2 families — and the value type rejected its own producer's output.

The comparison encoded an assumption ("families ≤ items") that the multi-family mapping was
designed to violate. Minimal reproduction:

```python
EvidenceItem(families=(TREND, MOMENTUM), status=SUPPORTING, inputs={"lean": "long"})
→ _confluence((item,), (), {...})  →  SetupEvidenceError
```

### Why the suite passed

No test constructed a one-agreeing-item-with-two-families report. Worse,
`tests/test_setup_evidence.py` **actively pinned the wrong invariant** — a test asserted that
1 item / 2 families *must* raise. The defect was not merely untested; it was protected.

### The fix

`src/fmis/setup_evidence/models.py`. The count is bounded by the families actually listed:

```python
if self.independent_agreeing_families > len(self.agreeing_families):
    raise SetupEvidenceError(
        "independent_agreeing_families cannot exceed the number of "
        "agreeing_families; it counts those families and inventing one "
        "that is not listed would overstate the agreement"
    )
if self.agreeing_item_count == 0 and (
    self.agreeing_families or self.independent_agreeing_families
):
    raise SetupEvidenceError(
        "agreeing families were reported with no agreeing items; a "
        "family is only present because some item carried it"
    )
```

Family multiplicity is allowed. Counts stay internally consistent: a family cannot be
claimed that is not listed, and families cannot be reported with no items behind them.
Confluence still counts families rather than items, the independence caveats are untouched,
and no score, weight or ordinal is introduced.

### What did *not* change

`independent_pairs_exist`, `KNOWN_CORRELATIONS`, `FACTOR_FAMILIES` and every caveat string
are byte-identical. The SOLUSDT page still reports `independent corroboration: NOT
established` with the upstream double-count caveat — the fix let the honest page print; it
did not make the page more generous.

---

## 3. Defect 2 — one projection failure suppressed every symbol behind it

### Symptom

```
$ fmits evidence BTCUSDT SOLUSDT ETHUSDT
── SETUP EVIDENCE — BTCUSDT ──────────────────────────────────
  ... (full page)
Traceback (most recent call last): ...
$ echo $?
1
```

Only BTCUSDT rendered. A valid **CONFIRMED / LONG** ETHUSDT page was lost.

### Root cause

`_run_evidence`'s own docstring promised isolation:

> A symbol whose analysis failed prints a failure block and does not stop the remaining
> symbols, matching `fmits setup`'s own isolation contract.

That contract covered `result.assessment is None` — analysis failure — only.
`project_setup_evidence` was called unguarded, so a symbol that *did* produce an assessment
but could not be projected escaped the loop entirely. The documented contract and the code
disagreed, and the docstring was the more accurate description of the intent.

### The fix

`src/fmis/pipeline/cli.py`. Projection **and** render sit inside a per-symbol guard:

```python
try:
    report = project_setup_evidence(
        result.assessment, setup_identity=_identity_ref_for(result)
    )
    page = render_setup_evidence(report)
except SetupEvidenceError as failure:
    print(
        f"fmits evidence: {result.requested_symbol}: "
        f"evidence could not be projected: {failure}",
        file=sys.stderr,
    )
    continue
print(page)
rendered += 1
```

Four properties, each pinned by a test:

- **Narrow.** Only `SetupEvidenceError` — the error this package raises for a report it
  refuses to build. A `TypeError`, an `AttributeError` or a bug in `cli.py` still
  propagates. A surface that swallows programmer errors reports a clean page over broken
  code.
- **Render is inside the guard.** A half-written page never precedes the error explaining
  that it could not be built.
- **stderr, not stdout.** A refusal never looks like a page.
- **Honest exit code.** `EXIT_OK if rendered else EXIT_FAILURE` counts pages actually
  rendered, so isolation cannot turn a total failure into a clean exit.

---

## 4. Regressions added

Eleven, all of which **fail against the unfixed code** — verified by running the new suite
against `c1a91e7`:

| Test | Pins |
|---|---|
| `test_confluence_cannot_claim_a_family_it_does_not_list` | corrected upper bound |
| `test_confluence_cannot_report_families_with_no_agreeing_items` | zero-item consistency |
| `test_one_agreeing_item_may_carry_two_families` | the exact live shape, at the value type |
| `test_confluence_builds_when_the_alignment_is_the_only_agreeing_item` | the same shape through the real producer |
| `test_a_projection_failure_does_not_suppress_the_symbols_behind_it` | BTCUSDT / SOLUSDT / ETHUSDT isolation |
| `test_a_projection_failure_reports_that_symbol_on_stderr_not_stdout` | no partial page, no fake page |
| `test_every_symbol_failing_to_project_is_a_non_zero_exit` | exit code under total projection failure |
| `test_a_programmer_error_is_not_swallowed_by_the_isolation_guard` | `AttributeError` still propagates |
| `test_a_render_failure_is_isolated_the_same_way` | guard covers render |
| `test_an_analysis_failure_is_isolated_alongside_a_projection_failure` | the other failure mode on the loop |
| `test_every_symbol_failing_analysis_is_a_non_zero_exit` | exit code under total analysis failure |

The producer-level test builds its item from `FACTOR_FAMILIES` rather than a hand-written
family tuple, and asserts the mapping is genuinely multi-family first — so a future change
to that mapping fails the test rather than leaving it passing vacuously.

One test was **removed**: `test_confluence_cannot_claim_more_families_than_items`, which
pinned the invalid invariant.

---

## 5. Verification

| Gate | Result |
|---|---|
| Focused BR suite | 173 passed (was 163; −1 removed, +11 added) |
| Full repository | **8,703 passed**, identically under `-W error` |
| swing_setup / setup-identity / observation | 574 passed, unchanged |
| pipeline / CLI / workspace / today / decision_support / proposal | 1,228 passed |
| Package branch coverage | 92% branch, 94% statement (unchanged) |
| `_run_evidence` coverage | 18/18 statements, by the BR suite alone |
| Mutation probes (both fixes) | **9/9 killed** |
| Import cycles | none across 241 modules |
| Export collisions | 0 across 1,176 exported names |
| `git diff --check` | clean |
| `pyproject.toml` / `uv.lock` | SHA-256 unchanged |
| `src/fmis/swing_setup/` | byte-identical |

### Mutation probes

Each reverts or weakens one part of a fix; all nine were killed:

```
killed  DEFECT 1 reverted: bound families by item count again
killed  DEFECT 1: invariant removed entirely (families unbounded)
killed  DEFECT 1: invariant loosened by one
killed  DEFECT 1: zero-item consistency guard removed
killed  DEFECT 2 reverted: no isolation guard around the projection
killed  DEFECT 2: guard widened to bare Exception (swallows bugs)
killed  DEFECT 2: failure aborts the loop instead of isolating
killed  DEFECT 2: exit code always OK even when every symbol fails
killed  DEFECT 2: render moved outside the guard (partial page possible)
```

> **Harness note, recorded because it nearly corrupted this work.** The first probe run
> restored each mutated file with `git checkout --`, which reverts to `HEAD` — and `HEAD`
> did not yet contain the uncommitted fixes. The run silently destroyed both fixes and then
> reported the tree "clean", which was true and entirely misleading. Mutation harnesses
> operating on uncommitted work must restore from an in-memory snapshot of the file, never
> from git. The rerun above uses a snapshot and re-runs the suite after restoring.

### Live demonstration — the previously failing case

```
$ fmits evidence SOLUSDT ; echo $?
── FAMILY CONFLUENCE ─────────────────────────────────────────
  agreeing families:    trend, momentum
  conflicting families: trend
  agreeing items: 1   distinct families: 2
  independent corroboration: NOT established — see the caveats below
  ! Internally double-counted upstream. Within `fmis.decision_support`,
    `macd_vs_signal` and `macd_histogram` are the same fact ...
0
```

One agreeing item, two families — the exact shape that crashed — now renders, and still
reports that corroboration is not independent.

### Live demonstration — batch isolation

Real market data, with a projection failure injected for the middle symbol only:

```
$ fmits evidence BTCUSDT SOLUSDT ETHUSDT
fmits evidence: SOLUSDT: evidence could not be projected: injected: simulated unprojectable report
── SETUP EVIDENCE — BTCUSDT ──────────────────────────────────   (full WAIT page)
── SETUP EVIDENCE — ETHUSDT ──────────────────────────────────   (full CONFIRMED / LONG page)
>>> exit code: 0
```

The failure goes to stderr; the symbol behind it renders in full. Without the injection all
three symbols render and stderr is empty.

---

## 6. Scope discipline

- **`MINIMUM_AGREEING_FAMILIES` was not changed.** It remains `2`, and
  `src/fmis/swing_setup/` is byte-identical to `c1a91e7`.
- **No strategy policy changed.** These are a value-type invariant and a CLI exception
  boundary.
- **No new capability.** `fmits evidence` gained no flag, no field and no output section.
- **No redesign.** `project.py`, `correlation.py`, `render.py` and `fmis/evidence/` are
  untouched.
- The **regime-gate / context-trend dependency remains an open strategy decision**,
  disclosed as a caveat and recorded in the backlog — not silently fixed.

---

## 7. Outstanding

Two items found by the gate and **not** addressed here, because neither is a defect and
both are test-coverage observations:

1. `family_order` returning a constant survives the BR suite. Shipped behaviour is
   unaffected — the real sort key is total, and reports were verified byte-identical across
   four `PYTHONHASHSEED` values — but no test pins the function's return values.
2. Re-keying the MACD correlation rule survives the suite. The mechanism is proven against
   live code and the caveat prints correctly, but no test asserts that *this* caveat is
   attached to *that* item.

Neither blocks release. Both are cheap to close when the package is next opened.
