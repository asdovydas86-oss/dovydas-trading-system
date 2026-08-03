# ADR-0024 — Confirmation-delay provenance: the delay travels with the origin that earned it

**Status:** Accepted
**Date:** 2026-08-03
**Decides:** where the swing confirmation delay lives, how eligibility is derived from it, and why the
mismatch class is removed rather than validated (Milestone AH)
**Implemented by:** *(uncommitted at the time of writing)*
**Relates to:** [ADR-0012](ADR-0012-market-structure-foundation.md) (detection, which owns the window);
[ADR-0016](ADR-0016-structural-sequence-state-history-foundation.md) §4 (projections, not stored copies);
[ADR-0019](ADR-0019-level-crossing-foundation-v1.md) (`LevelOrigin`, the model this changes);
[ADR-0020](ADR-0020-break-of-structure-foundation-v1.md) (**D1, which this closes**);
[ADR-0022](ADR-0022-structural-fact-sheet-composition-root.md) (the containment this replaces);
[ADR-0023](ADR-0023-multi-timeframe-composition.md) (the second root that inherited the containment)

---

## Context

`derive_structure_breaks` needed to know when a level became knowable. A pivot at bar `o` detected
with `right_bars = R` is knowable only at `o + R`; treating it as the reference earlier makes break
derivation **prefix-unstable**, measured at 30 violating prefixes across 40 seeded fixtures
(ADR-0020 §2.4).

The number was not on any input. ADR-0020 therefore made `confirmation_bars` a **required keyword
argument with no default** and recorded the consequence as deferred question **D1**:

> the confirmation delay is carried on no derived fact — a mismatch is undetectable

"Undetectable" is the whole problem. Passing a wrong `R` does not raise, does not warn, and does not
produce obviously broken output. It silently changes which level is the reference at every bar, and
therefore which breaks exist, which changes of character exist, and every fact derived from them.
Measured across 300 seeded series against five wrong delays: **36.1 % produced materially different
breaks**, 155 of those also changed the change-of-character count, and **zero raised an error**.

Two milestones contained it without fixing it. ADR-0022 had `build_structural_facts` read
`DetectionSettings.right_bars` once and hand the same value to both consumers; ADR-0023 passed one
`DetectionSettings` to all three views. Both were real, and both were local: the guarantee held for
callers who went through those roots and for nobody else. The Market Regime Engine is the second
consumer of `derive_structure_breaks`, and containment does not survive a second caller.

---

## Decision

**The confirmation window is stamped where it is known — at detection — and travels with the facts
derived from it. `derive_structure_breaks` no longer takes it as an argument.**

```
detect_swings(series, right_bars=R)
        │  stamps R on every point
        ▼
SwingPoint(index, timestamp, price, type, confirmation_bars=R)
        │  carried through comparison and labelling unchanged
        ▼
structural_levels(labelled)          ← takes no delay parameter
        │  copies it off the swing
        ▼
PriceLevel(origin=LevelOrigin(index, timestamp, label, confirmation_bars=R))
        │
        ▼
derive_structure_breaks(levels, crossings)   ← reads origin.knowable_from
```

### 1. `SwingPoint` carries the window, and `LevelOrigin` copies it

Both gain one required field, `confirmation_bars`, and one property, `knowable_from`
(`index + confirmation_bars`).

`left_bars` is deliberately **not** carried. It decides *whether* a pivot is a pivot — settled by the
time the object exists. Only `right_bars` decides *when the pivot became knowable*, which is the one
question a later layer asks. A field no consumer reads would be provenance theatre; adding it later
is purely additive.

### 2. The field is required, with no default

A default would bind every hand-built point to `DEFAULT_RIGHT_BARS` and be wrong for anyone who
detected with another window — the exact failure the field exists to prevent, reintroduced at the
constructor. It costs 80 test construction sites, and each now states the window it means.

### 3. `knowable_from`, not `eligible_from`

The property says **when the pivot became knowable**, which is a fact about detection.

It deliberately does not say what may be *done* at that bar. `fmis.structure_break` decides that
eligibility to break structure begins there, and that decision stays in that package. Naming the
property `eligible_from` would have moved a break-of-structure semantic into the level layer, which
does not own it.

The name also respects `fmis.market_structure`'s own vocabulary guard, which bans `confirmed` as an
interpretation word. `knowable` is the word that package's docstrings already use for this concept.

### 4. `StructureBreak.eligible_from` becomes a projection

It was a stored field only because the number lived nowhere on the inputs. It now lives on
`crossing.level.origin`, which makes a stored copy exactly what ADR-0016 §4 forbids — a duplicate of
a value one attribute away, with somewhere to drift.

Worse, as a constructor argument it was a **second source of truth**: a break could be built claiming
an eligibility its own level contradicted. Removing the argument removes that possibility instead of
validating against it. Two validations disappear with it — `eligible_from` cannot precede the origin
index, and cannot be negative — because `index + window` over a non-negative index and a window of at
least 1 makes both arithmetic guarantees.

### 5. One level set must agree on one window

`_levels_by_side` rejects a set whose origins disagree, as `StructureBreakInputError`.

This is not fastidiousness. `eligible_from` must be **strictly increasing within a side** for
`_reference`'s binary search to find what a linear scan would, and for the reference test to imply
eligibility without restating it (ADR-0020 §3.3). With one shared window that follows from strictly
increasing origin indices, which the existing duplicate check already forces. With mixed windows it
does not: a later pivot detected under a shorter window can become knowable *before* an earlier one,
and "the most recent eligible level" stops being well defined. Mixing windows also means mixing
detection runs over one index space, which no producer in this repository can do.

### 6. A window of at least 1, so bar 0 is unbreakable

`SwingPoint` and `LevelOrigin` both require `confirmation_bars >= 1`, matching
`fmis.market_structure`'s bar-count rule, whose validator moved into `models.py` so detection and
provenance apply one rule in one wording. `detect_swings` — the only producer — already rejects a
smaller window, so a recorded 0 would record a confirmation that never happened.

Zero was previously *permitted* by the break layer, meaning "eligible at its own pivot bar". A
consequence, recorded because it changes a testable behaviour: **a break at bar 0 is no longer
representable at all**. It never was reachable from real detection; only a hand-built fixture could
express it.

### 7. Two points from different windows cannot be compared

`SwingComparison` rejects a pair whose `confirmation_bars` disagree, following its existing rule that
a model may not contradict its own fields. A comparison spanning two detection runs is not a
comparable pair.

---

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **A `confirmation_bars` parameter on `structural_levels`** | The hazard relocated one layer up, and made worse: a wrong value would then look like *recorded provenance*. Named as a fake fix in ADR-0022 and on the backlog before this milestone began. |
| **Keep the argument, warn on mismatch** | Nothing to compare against — the level set did not know its window. A warning also leaves two sources of truth, which the milestone brief explicitly forbids. |
| **Store `eligible_from` on `LevelOrigin` instead of the window** | Bakes a break-of-structure semantic into the level layer, and loses the window itself, which is the auditable fact. Storing both duplicates a derivable value. |
| **Carry `left_bars` as well** | No consumer reads it. |
| **A default of `DEFAULT_RIGHT_BARS`** | Reintroduces the silent-wrong-value failure at the constructor. |
| **Allow mixed windows and sort by `knowable_from`** | Breaks the strictly-increasing property the binary search and the single-test eligibility rule both rest on, silently weakening a proven property. |

---

## Consequences

**The mismatch class is gone, not guarded.** No public entry point — `derive_structure_breaks`,
`contextual_structure_breaks` or `structural_levels` — accepts a confirmation delay. A caller cannot
express the mistake.

**Both composition roots lose their duplicated delay configuration.** `structural_facts` reads
`right_bars` once and passes it to `detect_swings` alone. The AF-era AST guard that policed one read
feeding two consumers is replaced by one asserting no `confirmation_bars=` argument exists anywhere in
the module.

**One limitation leaves the product.** `ADR-0020 D1` is removed from `LIMITATIONS`, so both the
single-timeframe and multi-timeframe sheets print six limitations rather than seven. A limitation kept
past its fix teaches a reader to discount the list.

**Public API changes** — the migration is documented in the design record:

| Name | Change |
|---|---|
| `SwingPoint` | new required field `confirmation_bars`; new property `knowable_from` |
| `LevelOrigin` | new required field `confirmation_bars`; new property `knowable_from` |
| `SwingComparison` | rejects a pair disagreeing about the window |
| `StructureBreak` | `eligible_from` is now a **property**; the constructor takes `crossing` only |
| `derive_structure_breaks` | `confirmation_bars` **removed** |
| `contextual_structure_breaks` | `confirmation_bars` **removed** |
| `structural_levels` | unchanged signature, now copies the window |

**No name was added or removed from any package's `__all__`.** The change is in fields and
signatures, not in the exported surface: `fmis.level_crossing` 13, `fmis.market_structure` 19,
`fmis.structure_break` 5, all unchanged.

**Equality is stricter.** Two origins identical but for the window are two provenances, because they
became knowable at two different bars. Collapsing them would be the original hazard re-expressed as
an equality rule.

**Behaviour is otherwise unchanged**, and that is proved rather than asserted: a reimplementation of
the pre-AH algorithm is compared against the new derivation across 40 seeded series at four detection
windows, and every break matches exactly.

---

## Limitations

| # | Limitation | Disposition |
|---|---|---|
| **G1** | One derivation cannot span two detection windows | Deliberate; rejected loudly. No producer can create such a set |
| **G2** | `left_bars` is not carried, so a point cannot fully describe its detection | Deliberate; no consumer reads it. Additive if one appears |
| **G3** | A hand-built `PriceLevel` may still carry `origin=None` and is rejected by the break layer, not at construction | Unchanged from ADR-0019; `origin` is optional on purpose |

**Still deliberately absent:** regime, alignment, agreement, signals, persistence, scanning,
scheduling, AI, portfolio, risk, strategy, execution, BOS invalidation, failed CHoCH, and any
sub-bar reconstruction.
