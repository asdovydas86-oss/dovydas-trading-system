# Confirmation-Delay Provenance v1 — Independent Review

**Milestone:** AH
**Reviews:** [ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md),
[design](../design/CONFIRMATION_DELAY_PROVENANCE_V1.md)
**Date:** 2026-08-03
**Verdict:** no P0, no P1, **two P2 found and fixed**, three P3 documented

Every claim was re-derived from production code. Counts, coverage and mutation results were measured
in this review, not copied from the design.

---

## 1. Scope

Four questions:

1. Is the mismatch class actually **removed**, or relocated somewhere new?
2. Does correct behaviour survive unchanged?
3. Does anything ship untested?
4. Did the layering hold — did provenance leak break-of-structure semantics downward?

---

## 2. Is the hazard removed? — verified

Re-derived from the live signatures rather than the docstrings:

```
derive_structure_breaks      (levels, crossings)
contextual_structure_breaks  (levels, crossings)
structural_levels            (swings)
```

No public entry point accepts a confirmation delay. The number reaches the break layer on
`level.origin.confirmation_bars` and nowhere else.

**This is not "relocated".** The obvious wrong fix — a `confirmation_bars` parameter on
`structural_levels` — was the one ADR-0022 already named as fake, because it lets a caller record a
window the swings were not detected under, dressed as provenance. A test asserts that function's
parameter set is exactly `{"swings"}`.

The chain was walked end to end on real detection output: at `right_bars` of 1, 2 and 4, every level
produced by `structural_levels` carries the window `detect_swings` was called with, and every break's
`eligible_from` equals its own `origin.knowable_from`.

## 3. Does correct behaviour survive? — verified against a reimplementation

The strongest test in the milestone reimplements the **pre-AH algorithm** — eligibility as
`origin.index + confirmation_bars`, linear reference scan, close-breach only, one break per level —
and compares it against the new derivation across **40 seeded series at four detection windows**,
calling the old implementation with the delay a correct caller would have passed.

**Every break matches exactly**, at all four windows, on at least 35 series per window.

The same reference implementation then measures the hazard on the same data: with a wrong delay it
produces different breaks on **more than a third** of the series. That is the defect, reproduced and
pinned, on the very fixtures that prove the fix changed nothing else.

## 4. Did the layering hold? — verified, after a naming correction

`fmis.level_crossing` gained no import edge: `models.py` still imports `fmis.data` and
`fmis.market_structure` and nothing else, asserted by AST.

The property is named `knowable_from`, not `eligible_from`, and that distinction is load-bearing.
*Knowable* is a fact about detection; *eligible* is a break-of-structure decision. Naming it the
latter would have moved a semantic into a package that does not own it.

The first implementation called it `confirmed_at` and `fmis.market_structure`'s vocabulary guard
rejected it — `confirmed` is on the banned interpretation list. **The guard was right and the name
changed.** Weakening a scope boundary to fit a new field would have been the wrong repair, and it is
worth recording that the guard caught something real rather than being an obstacle.

## 5. Findings

### P2-1 — the rendered detection row could not distinguish `left_bars` from `right_bars` *(found and fixed)*

`render_fact_sheet` prints `confirmation_bars={...}` on the detection row. A mutation changing it to
read `sheet.detection.left_bars` **survived the full suite**.

The cause is a fixture, not the renderer: every render test used the default `DetectionSettings()`,
which is `L2 R2`. With left equal to right, a renderer printing the wrong one is indistinguishable
from a correct one.

**Fixed** by `test_render_reports_the_right_bars_window_not_the_left_one`, which renders with
`DetectionSettings(3, 5)` and asserts the row shows `L3 R5` and `confirmation_bars=5`, and explicitly
that `confirmation_bars=3` does not appear. Verified to fail against the mutant and pass against the
original.

This gap predates AH — the row has read `right_bars` since AF — but AH is what made the value
meaningful enough to test properly.

### P2-2 — the cross-window rejection message was asserted only by substring *(found and fixed)*

`SwingComparison` rejects a pair whose confirmation windows disagree, and names both values. A
mutation swapping the two in the message survived, because the test matched only
`"must share a confirmation window"`.

A message that reports the windows the wrong way round misdirects every reader debugging it.
**Fixed** with a full exact-string assertion.

### P3-1 — one probe is a proven equivalent mutant, and stays one

`structural_levels` reads `swing.comparison.current.confirmation_bars`. A mutation reading
`previous` instead survives, and **must**: `SwingComparison` now rejects a pair whose windows
disagree, so the two values are always equal and no input can distinguish the spellings.

This is a consequence of an invariant AH added, not a test gap. It is recorded rather than papered
over, and the invariant that makes it equivalent is now asserted directly by
`test_a_comparison_can_never_straddle_two_windows` — so the equivalence is enforced, not argued.
`current` remains the correct spelling because the level sits at the current pivot; its correctness is
a matter of meaning, not of observable behaviour.

### P3-2 — two import-direction guards were widened to ignore docstrings

`test_only_change_of_character_imports_structure_break` and the new purity test scan raw source text
for a package name, which catches a dynamic `importlib.import_module(...)` that an AST check would
miss. AH gave `SwingPoint` and `LevelOrigin` docstrings that name the layer above, to explain which
layer owns eligibility — the very boundary those guards defend.

Both now blank docstrings before scanning. Comments and non-docstring literals are still scanned, so
the crude scan keeps its teeth. The alternative — forbidding the code from naming the rule it enforces
— would have pushed the explanation out of the codebase.

### P3-3 — a break at bar 0 became unrepresentable

`confirmation_bars >= 1` means the earliest knowable bar is 1. Fixtures that built break runs from
bar 0 now start at bar 1, and one test asserts the impossibility directly.

No detection run could ever produce a bar-0 break — `detect_swings` rejects a window below 1 — so
this removes a fixture-only capability, not a real behaviour. Recorded because it changed test data
visibly.

## 6. Mutation results

**42 probes · 41 detected · 1 proven-equivalent survivor · 0 no-ops**, with byte-identical source
restoration verified by SHA-256 before and after across all seven touched modules.

Probes cover: the stamp at detection, both `knowable_from` projections, window validation on both
models, silent defaults, the copy from swing to level, eligibility ranking and ordering, the
mixed-window rejection and its message, duplicate and unprovenanced origins, all five break
conjuncts, the reference binary search, the `eligible_from` projection, the composition root's single
delay path, the rendered detection row, the contextual wrapper, and the removed limitation code.

Three probes did not detect on their first run. **One was equivalent; two were real gaps:**

| Probe | Cause | Resolution |
|---|---|---|
| detection row reports `left_bars` | Every render fixture used `L2 R2`, so the two are indistinguishable | Asymmetric-settings test → P2-1 |
| mismatch message swaps the two windows | Assertion matched a substring, not the message | Exact-string assertion → P2-2 |
| level copies the window from `previous` | Provably equivalent under `SwingComparison`'s new invariant | Equivalence asserted directly → P3-1 |

The harness purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE=1` before every probe, and runs
the **full suite** per probe — both corrections carried forward from the AG review §6, where a
same-size mutation was shown to be masked by a stale `.pyc`.

## 7. Measured results

**3,449 tests pass**, identically under `-W error` (3,404 before AH; **+45**).

| Module | Coverage |
|---|---|
| `level_crossing/levels.py` | **100 %** |
| `level_crossing/models.py` | **100 %** |
| `market_structure/swings.py` | **100 %** |
| `structure_break/breaks.py` | **100 %** |
| `structure_break/models.py` | **100 %** |
| `pipeline/render.py` | **100 %** |
| `market_structure/models.py` | 99 % — the one uncovered line predates AH (`d1c0b3b0`) |
| `pipeline/structural_facts.py` | 99 % — the one uncovered line predates AH (`1505dd8a`) |

Public exports **154**, zero collisions — **unchanged by AH**, which adds fields and properties, not
names. Import cycles **0**. Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

**Suites:** AH 50 · BOS 170 · CHoCH 184 · AF 86 · AG 98 · level crossing 249 · swings 194.

## 8. Adversarial inputs

| Input | Result |
|---|---|
| `confirmation_bars` of 0, −1, −99 on a swing or an origin | `ValueError`, "must be at least 1" |
| `confirmation_bars` of `"2"`, `2.0`, `None`, `True` | `TypeError` |
| Omitting `confirmation_bars` entirely | `TypeError` — no default exists |
| Two levels disagreeing about the window | `StructureBreakInputError` naming both positions |
| Three levels where the third disagrees | Same error, naming the first disagreeing pair, stable over five runs |
| Two levels on one side sharing an origin index | `StructureBreakInputError`, unchanged from ADR-0020 |
| A level with `origin=None` | `StructureBreakInputError`, unchanged |
| Comparing two points from different windows | `ValueError` at construction |
| A break at bar 0 | Unrepresentable |
| `derive_structure_breaks(..., confirmation_bars=2)` | `TypeError` — the argument is gone |
| A series too short to detect anything | Empty levels, empty breaks, no error |
| Detection at `L1 R1`, `L2 R2`, `L3 R5`, `L4 R3` | Provenance matches `right_bars` in every case |

## 9. Determinism and stability

Break output hashes identically under `PYTHONHASHSEED` 0, 1, 42 and 12345 in fresh subprocesses.

**Prefix stability re-verified**, since it is the property the eligibility rule exists to protect: 20
seeded series, every 10-bar prefix from bar 30, **0 violations** — a break reported over a prefix is
always reported over the full run.

The deterministic layer reads no clock and reaches no provider, asserted over
`market_structure`, `level_crossing` and `structure_break` with docstrings excluded.

## 10. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 2 | Render row indistinguishable at `L=R` — **fixed** · rejection message asserted by substring — **fixed** |
| **P3** | 3 | One proven equivalent mutant · two guards made docstring-aware · bar-0 break unrepresentable |

The milestone does what it claimed: the confirmation delay travels with the origin that earned it, no
public entry point accepts one, and the 36.1 % silent-divergence class is gone rather than guarded.
ADR-0020 D1 is closed, and the limitation has left the product's printed output.

**The thing this review would not let pass** is the phrase "zero survivors". One probe survives and
always will, because an invariant this milestone added makes it equivalent. Calling that zero would
be a more comfortable number and a less true one; it is reported as 41 detected, 1 proven equivalent,
with the proof asserted in a test rather than argued in prose.
