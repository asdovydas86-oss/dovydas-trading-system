# Decision Context Engine v1 — Independent Review

**Milestone:** AL
**Reviews:** [ADR-0026](../adr/ADR-0026-decision-context-boundary.md),
[design](../design/DECISION_CONTEXT_V1.md)
**Date:** 2026-08-04
**Verdict:** no P0, no P1, **two P2 found and fixed**, three P3 documented

Every claim was re-derived from production code. Counts, coverage and mutation results were measured
in this review.

---

## 1. Was the milestone itself justified? — verified

The review's first duty was to check Phase 1's claim rather than accept it. Reproduced independently:
a 12-candle page and a 260-candle page produced status profiles differing by one section, while the
12-candle page had zero levels and three unclassified regime dimensions. The gap was real, and it is
now closed: 12 → `INSUFFICIENT`, 40 → `LIMITED`, 260 → `SUFFICIENT`.

## 2. Does it stay inside its one question? — verified

No forbidden word — long, short, buy, sell, entry, exit, target, stop, position, size, risk, bullish,
bearish, signal, recommend, score, confidence, rank, trade — appears in any public name, any enum
value, or any of the statements reachable across the full sweep of gap combinations. The result carries
no score field and no direction field.

The naming was checked too: `may_continue` is a statement about information. `should_trade` and
`is_tradeable` do not exist and a test asserts they never will.

## 3. Does it invent a threshold? — verified

An AST scan finds no numeric literal beyond 0 and 1 in the evaluator, and `ContextPolicy` has exactly
two fields, neither numeric. `SOURCES` covers `Requirement` exactly, and every check's rendered source
begins `fmis.`. Depth was confirmed to be relative rather than absolute: 10 candles passes against a
requirement of 5 and fails against 50.

## 4. Findings

### P2-1 — `may_continue` contradicted its own state *(found and fixed)*

`may_continue` was `not self.blocking`, re-derived from the checks. Under a strict policy the *state*
becomes `INSUFFICIENT` while each check keeps its fixed severity, so a strict result reported
`INSUFFICIENT` **and** `may_continue is True` simultaneously — an object disagreeing with itself, and
the field a caller is most likely to branch on.

**Found by a test written for the strictness feature**, not by inspection.

**Fixed** by deriving it from `state`, the single source of truth — ADR-0016 §4 applied to a property.
A sweep across strictness × gap combinations now asserts the two can never diverge.

### P2-2 — `DEFAULT_POLICY` collided with `fmis.market_regime` *(found and fixed)*

The new package exported `DEFAULT_POLICY`, which `fmis.market_regime` already owns. The repository's
existing export-collision guard caught it on the first full run.

**Fixed** by renaming to `DEFAULT_CONTEXT_POLICY`. Worth recording as evidence that the collision guard
earns its keep: nothing else in the milestone would have noticed until an ambiguous import somewhere.

### P3-1 — the judgement is made about the primary view only

The other views contribute their adequacy to `ContextInput.views` and to metadata, but the five
requirements are evaluated against the primary timeframe. That is the timeframe a setup would be built
on, and judging three views jointly would require a weighting rule this engine must not hold.

### P3-2 — `SUFFICIENT` does not mean correct

It means the data each layer asked for is present. A sufficient context over a wrong reading is still
a wrong reading. The section states this as a caveat on every run.

### P3-3 — `strict` is coarse

One flag promotes every limiting gap. A caller wanting to tolerate warm-up but not an indeterminate
regime cannot express that. Deliberate: per-requirement overrides would let a caller switch off the one
check about to stop them, which is the gate shape `docs/analysis-notes.md` blames for the v2 bias.

## 5. Mutation results

**43 probes · 43 detected · 0 survivors · 0 no-ops**, byte-identical restoration verified by SHA-256.

**Eleven probes survived their first run**, every one a real assertion gap against **100 % line
coverage** — the second milestone running to show the two measure different things:

| Probe | The gap |
|---|---|
| a requirement checked twice | the fixture also broke completeness, so the duplicate guard never ran |
| requirement order changed | the test compared against `REQUIREMENT_ORDER`, which follows it when mutated |
| an input with no view | the primary-role check fired first and hid it |
| primary view always first | every fixture had exactly one view |
| blocking/limiting swapped | no case carried one of each |
| policy misreports strictness | `describe()` was rendered and never read back |
| warm-up count zeroed | the adapter's fields were never checked one by one |
| level count hard-coded | same |
| insufficient dimensions uncounted | same |
| adapter names first role primary | same |
| section status inverted | the status was never asserted against the state |

The adapter cluster is the instructive one: four separate fields were being copied and **nothing
asserted any of them**, because every test looked at the verdict rather than at the inputs the verdict
was computed from.

## 6. Measured results

**3,766 tests pass**, identically under `-W error` (3,702 before AL; **+64**).

Coverage **100 %** on all four `decision_context` modules and all six `workspace` modules. Public
exports **228**, zero collisions. Import cycles **0**. Runtime dependencies **0**. `pyproject.toml` and
`uv.lock` untouched.

`fmis.decision_context` imports **nothing** from the repository — asserted by AST — so it is reachable
from a test with seven integers.

## 7. Adversarial inputs

| Input | Result |
|---|---|
| Zero views | `ContextInputError` naming the view requirement |
| Repeated role | `ContextInputError` |
| `primary_role` absent from the views | `ContextInputError` naming the available roles |
| `required_candles` of 0 | rejected — depth could not be judged |
| Negative or float or boolean counts | rejected |
| Blank symbol, role or interval | rejected |
| Conflict counts 0, 1, 5, 99 | identical state and identical checks |
| Strict policy over a clean analysis | still `SUFFICIENT` — strictness invents no gap |
| Missing evidence report | treated as insufficiency, not as silence |
| Reordered or truncated check list | rejected at construction |

## 8. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 2 | `may_continue` contradicted its state · export collision — **both fixed** |
| **P3** | 3 | Primary-view scope · sufficient ≠ correct · coarse strictness |

The milestone does what it claimed, and it did it by adding a rule-free engine: five requirements, each
delegating to the layer that already owned it, and a policy that carries no numbers at all.

**The thing this review would not let pass** is the temptation to give the engine its own thresholds.
A minimum-candle constant here would have been one line and would have created a second definition of a
rule `fmis.market_structure` already owns — the kind of duplication that is invisible for a year and
then disagrees.
