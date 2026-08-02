# Multi-Timeframe Fact Sheet v1 — Independent Review

**Milestone:** AG
**Reviews:** [ADR-0023](../adr/ADR-0023-multi-timeframe-composition.md), [design](../design/MULTI_TIMEFRAME_FACT_SHEET_V1.md)
**Date:** 2026-08-02
**Verdict:** no P0, no P1, **two P2 found and fixed**, three P3 documented

Every claim was re-derived from production code. Counts, timings and mutation results were measured in
this review, not copied from the design.

---

## 1. Scope

Four questions:

1. Is "no cross-timeframe synthesis" **enforced**, or only documented?
2. Does composition genuinely delegate, or was logic duplicated?
3. Does the ADR-0020 D1 containment survive across three views?
4. Does anything ship untested?

---

## 2. Is "no synthesis" enforced? — verified

Re-derived from the live class, not from the docstring:

```
sheet fields:     ['limitations', 'metadata', 'newest_as_of', 'source', 'symbol', 'views']
public surface:   ['by_role', 'intervals']
members matching agree|align|conflict|consensus|confluence|score|verdict|overall:  NONE
```

There is no field, property or method from which a caller could read a combined judgement. The three
trends are reachable only individually, through `views[i].sheet.structure.trend`.

Four independent tests hold this: the field set is asserted exactly; no public attribute may contain a
synthesis word; rendered output is scanned for ten synthesis terms outside the limitations block; and
a fourth test proves the disclaiming limitations are still rendered, so that exclusion cannot mask
their removal.

**Verified on live data.** `fmits mtf BTCUSDT -n 260` produced `1W sustained_higher · 1D neutral ·
4H sustained_lower` — the `SPEC` §5 case — followed by *"Reported side by side. Nothing is derived from
the combination."* and no verdict of any kind.

## 3. Does composition delegate? — verified, after a fix

`build_multi_timeframe_facts` stores the **same object** the caller passed (`view.sheet is direct[role]`),
and `multi_timeframe_facts_for_symbol` reaches no engine. Imports outside `fmis.pipeline` are limited
to `fmis.features.indicators.ema`, `fmis.features.types` and `fmis.providers.binance` — all type or
construction only.

But the **renderer** did duplicate logic. See P2-1.

## 4. Does D1 containment hold across views? — verified two ways

**Structurally.** `multi_timeframe_facts_for_symbol` constructs `DetectionSettings()` exactly once and
passes `detection=` exactly once — AST-asserted.

**Behaviourally.** A spy over `structural_facts_for_symbol` captured the `detection` argument of all
three calls and asserted `s is settings` for each. Three views, one object.

AG adds **no second caller** of `derive_structure_breaks` — it reuses AF's root — so the hazard remains
contained and remains owed to its own milestone. The ADR says "contained, not fixed", and that is
accurate.

## 5. Findings

### P2-1 — the renderer carried two near-identical structure blocks *(found and fixed)*

`render_fact_sheet` (AF) and `_view_block` (AG) each rendered the latest label, latest break and latest
change of character, in blocks that were identical except that AF appends two count rows.

**How it surfaced.** Not by reading — by mutation. Two probes anchored on strings that exist in *both*
copies, and `str.replace(…, 1)` mutated **AF's** copy, which AG's suite correctly does not cover. The
probes reported as survivors. The duplication was the reason the anchors were ambiguous at all.

Measured before the fix: **26 identical lines** across the two blocks.

**Fixed** by extracting `_structure_rows(structure)`, used by both. The one genuine difference — AF's
two count rows — stays at the call site rather than becoming a flag on the helper. `render.py` shrank
from 397 to 384 lines, and both suites pass unchanged (182 tests across AF and AG), confirming the
extraction is behaviour-preserving.

This directly satisfies the milestone's own instruction to *avoid duplicate logic*.

### P2-2 — row order in the single-timeframe sheet was asserted by nothing *(found and fixed)*

Extracting the shared helper made the three rows swappable as a unit. A probe that swapped
`label_row` and `break_row` in `render_fact_sheet` **survived the full 3,403-test suite**.

The gap predates AG: nothing ever asserted row order, and while the code was inline no single mutation
could expose it. The refactor made it reachable.

**Fixed** by `test_render_emits_structure_rows_in_a_fixed_order`, which extracts the rendered row
labels and asserts the exact sequence. Verified to fail against the mutant and pass against the
original.

### P3-1 — the multi-timeframe view block is deliberately less complete than `fmits facts`

The per-view block omits break count, change count, crossing count, warm-up summary and detection
settings, all of which the single-timeframe sheet shows. Three exhaustive sheets on one page is not
readable, and `fmits facts` remains the place to read one timeframe fully. Recorded so the omission
reads as a decision, not an oversight.

### P3-2 — `TimeframeView` carries both `role`/`interval` and `sheet.interval`

Deliberate: `interval` records what the *caller requested*, `sheet.interval` what the provider
returned. A test pins that they agree today, so a future normalising provider would make the
divergence visible rather than silent. It is redundancy with a stated purpose.

### P3-3 — three sequential fetches, no concurrency

Live wall time is ~1.9 s for three views at 260 candles, essentially all of it network. Composition
overhead measured at **0.004–0.005 ms**, i.e. 0.01–0.12 % of total. Concurrency would be premature.

## 6. A methodological defect in the review's own tooling

**The mutation harness produced unreliable results until it was fixed, and this is worth recording.**

A mutation that changes no byte count — swapping two adjacent lines — leaves the file's size
identical. When the write lands inside the same mtime-granularity window, CPython reuses the cached
`.pyc` and runs the **unmutated** code. The probe then reports whatever the stale copy produces.

It surfaced as a contradiction: the source clearly appended `label_row` before `break_row`, while the
rendered output showed the reverse. Clearing `__pycache__` resolved it.

The harness now purges every `__pycache__` and sets `PYTHONDONTWRITEBYTECODE=1` before each probe.
**All results in §7 are from after that fix.** Any mutation harness in this repository should do the
same; without it, a "zero survivors" claim over same-size mutations is not trustworthy.

A second correction: the harness originally ran only `tests/test_multi_timeframe.py`. Probes touching
`render.py` reach code AF also renders, so a probe could be "survived" simply because the wrong suite
was asked. It now runs the **full suite** per probe.

## 7. Mutation results

**42 probes, 42 detected, 0 survivors, 0 no-ops**, with byte-identical source restoration verified by
checksum before and after.

Probes cover: role ordering and validation, default timeframes, `newest_as_of` selection, D1
containment, delegation, feature selection, symbol and type validation, interval overrides,
limitations, metadata, every renderer branch including the shared helper, and the CLI registry.

Six probes did not detect on their first run. **None was an equivalent mutant:**

| Probe | Cause | Resolution |
|---|---|---|
| empty-views check removed | The factory rejects an empty mapping first, so the model's own guard was unreachable through the public path — but the model is public | Test constructing `MultiTimeframeFactSheet` directly |
| role header removed | Anchor did not match the real source line | Anchor corrected; assertion strengthened to count header lines |
| MTF absent-label note removed | Ambiguous anchor mutated **AF's** copy → P2-1 | Duplication removed; probe retargeted at the shared helper |
| MTF absent-break note removed | Same | Same |
| AF row order swapped | Genuinely undetected by any test → P2-2 | New AF row-order test |
| *(same probe, earlier run)* | Stale bytecode → §6 | Harness hardened |

## 8. Adversarial inputs

| Input | Result |
|---|---|
| Empty view mapping | `ValueError` from the factory |
| `MultiTimeframeFactSheet` constructed directly with no views | `ValueError` from the model |
| Duplicate roles | `ValueError` |
| Views out of role order | `ValueError` |
| Views of different symbols | `ValueError` naming both |
| Non-`TimeframeRole` key | `TypeError` |
| Non-`StructuralFactSheet` value | `TypeError` |
| Single-view sheet | Valid |
| Two-view sheet | Valid, role order preserved |
| Roles mapped to unconventional intervals | Honoured verbatim, never re-inferred |
| One timeframe too short | Raises; **no partial sheet escapes** |
| A view with no labelled swing and no break | Renders both as absent with reasons |
| A view with a change of character | Renders side, bar and timestamp |

## 9. Determinism

Rendered output hashes identically under `PYTHONHASHSEED` 0, 1, 42 and 12345 in fresh processes. The
module reads no clock and contains no arithmetic operator — both AST-asserted.

## 10. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 2 | Renderer duplication — **fixed** · row order untested — **fixed** |
| **P3** | 3 | Compact view block · dual interval fields · sequential fetches |

**3,404 tests pass**, identically under `-W error`. Coverage: `multi_timeframe.py` **100 %**,
`cli.py` **100 %**, `render.py` **100 %**. Public exports **154**, zero collisions. Zero import cycles.
Zero runtime dependencies.

*Export count convention, stated so it is reproducible:* `__all__` entries across the subpackage
`__init__.py` files under `src/fmis`. That count was **145 before AG** and is **154 after**, because
`fmis.pipeline` raised its surface from 16 to 25. An earlier draft of this review and of the design
carried 145 as the post-AG figure — it was the pre-AG measurement, and it is corrected here.

The milestone does what it claimed: three role-labelled timeframes from one command, composed from
AF's root with no new engine, and with nothing derived from their combination.

**The thing this review would not let pass** is the word "contained" applied to ADR-0020 D1. AG reuses
AF's single caller and adds no second one, so containment genuinely holds — but it is containment, and
the next consumer of `derive_structure_breaks` reopens the hazard. That distinction must survive into
the milestone that fixes it.
