# ADR-0032: Market technical context — a sibling of strategy input, never a wider strategy input

**Status:** Accepted
**Date:** 2026-09-17
**Milestone:** TA Slice 5A — Recover Technical Context & Feature Series

## Context

`build_setup_inputs` in `src/fmis/swing_setup/compose.py` receives three complete
`StructuralFactSheet`s — every swing, label, sequence-state snapshot, structural trend, price level,
level crossing, structure break, change of character, nearest-level pair, `FeatureSet`, warm-up list
and data window, for the context, setup and execution roles — and emits **twenty-two scalars and two
level tuples**.

Everything else stops there. [Report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md)
§7 traced each item to the exact line; [`CAPABILITY_REGISTRY.md`](../AI_HANDOFF/CAPABILITY_REGISTRY.md)
§2.2 re-verified every row against live code on 2026-09-16 and classifies them
`PRODUCT_UNREACHABLE` — *computed correctly and thrown away one layer before the operator*. The
registry calls it the cheapest class of gap in the repository, and it is: nothing is missing, only
the carriage.

**`build_setup_inputs` is not a badly written function.** `SetupInputs`' own docstring states that
it is a deliberately narrow policy boundary, and it was correct when the policy read three things.
The product then grew past it and nothing widened the seam.

The obvious repair — add the missing facts to `SetupInputs` — is the one that must not be made.
`SetupInputs` is *what the strategy policy reads*. Every field on it is, by construction, something
`evaluate_setup` may branch on. Putting the whole technical picture there would:

* make the strategy's own input surface the general warehouse for all technical analysis, so that
  "what may the policy see" stops being answerable by reading one dataclass;
* invite a later milestone to gate on a recovered fact **because it was in scope**, which is exactly
  the correlated-vote inflation [`CAPABILITY_REGISTRY.md`](../AI_HANDOFF/CAPABILITY_REGISTRY.md) §3
  measures and forbids;
* change `SetupInputs`' `repr()`, and with it the artifacts the 81-fixture policy non-regression
  digest pins.

Report 0047 identified the **seam**; it did not decide the **ownership**, and the
[review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) did not ratify its implementation
plan verbatim. This ADR decides ownership.

There is already a precedent in the same file. Slice 1 needed the per-role reading instants and the
context-role regime dimensions above the policy, and it did **not** add them to `SetupInputs`: it
added `SetupReadings`, assembled *after* the assessment from values already computed, carried beside
it on `SetupRunResult.readings`. `SetupReadings`' docstring states the rule outright — *"It is not a
policy input and the policy never reads it."* This decision generalises that precedent rather than
inventing a shape.

## Decision

### 1. Recovered technical facts are a sibling object, not a strategy input

```
MultiTimeframeFactSheet ─┬─► build_setup_inputs      ──► SetupInputs ──► evaluate_setup ──► SetupAssessment
                         └─► technical_context_for_sheet ──► MarketTechnicalContext
                                                                       │
                       Swing Workspace / SymbolDecision  ◄─────────────┘  (carried, never read by policy)
```

`SetupInputs` gains **no field**. `evaluate_setup` is untouched, byte for byte.
`MarketTechnicalContext` is assembled *after* the regimes, the evidence report, the decision context
and the assessment already exist, from the objects those stages already built.

### 2. `fmis.pipeline` owns it

`fmis.pipeline.technical_context` is a new module in the package that already owns
`StructuralFactSheet` (ADR-0022) and `MultiTimeframeFactSheet` (ADR-0023). It is a **projection over
a sheet**, and the sheet's owner is the right owner of a view of it.

No new top-level package is created. A `fmis.technical_analysis` collecting everything was
considered and rejected: it would import `fmis.pipeline` and therefore be a composition root of its
own, duplicating the tier `fmis.pipeline` already occupies, and it would exist to hold one 400-line
projection.

Ownership carries the composition-root discipline unchanged (ADR-0007 §2): **no calculation is
defined in this module.** It selects, references and groups. It performs no arithmetic — a test
asserts the module contains no arithmetic operator at all, the same guard `structural_facts` and
`multi_timeframe` hold.

### 3. Timeframe roles are preserved and never blended

The context is a tuple of per-role views in the sheet's own canonical order — context, setup,
execution — each carrying its own role, interval, `as_of`, closed count, warm-up list, structural
trend, `MarketRegime`, levels, nearest levels, crossings, breaks and changes of character.

Nothing is merged across roles. No agreement flag, no alignment count, no "two of three" anything —
the refusal `MultiTimeframeFactSheet`'s own docstring calls its load-bearing decision, inherited
verbatim. This is what recovers the **setup- and execution-role `MarketRegime`s** (previously one
integer) and the **context-role levels** and **setup-role breaks** (previously nothing).

### 4. Canonical objects are carried by reference

`PriceLevel`, `LevelCrossingEvent`, `StructureBreak`, `ChangeOfCharacter`, `MarketRegime` and
`FeatureSet` are carried **as themselves**, by reference, not converted to strings, counts or
dictionaries. All six are frozen; none is copied; the tuples already exist on the sheet and the
projection holds the same objects.

This is what "lossless" means here, and it is the requirement later deterministic engines actually
have: an engine needing the ATR at a zone's establishment point, or the classification and timing of
the crossing that established a level, cannot recover either from an integer count. A projection
that reduced a rich event sequence to `len()` would have to be undone by the first engine that used
it.

It is also the cheapest option. Carrying references adds one tuple header per role per collection;
it does **not** duplicate the events, and immutability makes sharing safe.

### 5. Bounded, truthful summaries are computed here, never in a renderer

Crossing histories run to hundreds of events at production window sizes, and the product must not
render a raw event flood. The **selection** of what a surface shows — the latest crossing, the
latest close breach, the latest break, the latest change of character — is made **in this module**,
beside the full history it selects from, and it introduces no vocabulary: each is the last element
of a sequence the deterministic layer already ordered, or the last element matching a
classification that layer already assigned.

No presentation layer may derive one. The full history stays reachable for later engines; the
summary is what a page prints.

### 6. Carriage is not interpretation

A recovered fact keeps exactly the meaning its owning engine gave it.

* A `LevelCrossingEvent` with `CrossingKind.CLOSE_BREACH` is a close beyond a number at a bar. It is
  **not** a breakout, a confirmation, a signal or a reason.
* A `ChangeOfCharacter` is two breaks on opposite sides in a stated order. It is **not** a reversal,
  a prediction, directional evidence or a vote.
* A `PriceLevel` above the last close is the **nearest structural level above**. It is **not**
  resistance, and the one below is **not** support — the derivation *below price = support* is
  forbidden by the [0047 disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §E and by
  ADR-0019 §I, and three existing guards forbid those words in output.
* A `FeatureSet` value is a measurement. It is **not** *bullish EMA*, *momentum improving* or a
  *golden cross forming*.

Nothing in this object is an opportunity, a score, a probability, a confidence, a ranking or a
recommendation, and there is no field one could be stored in.

### 7. Nothing above may consult it to decide anything

`MarketTechnicalContext` reaches `SetupRunResult.technical`, then `SymbolDecision.technical`, then
the dashboard — each as an **additive, defaulted** field, so every existing construction stays valid
and a result assembled without it states the absence rather than inventing a context.

It is carried on `SymbolDecision` as `Any`, for the identical reason `developing`, `blocker` and
`plan` are: `fmis.swing_workspace`'s import allowlist does not include `fmis.pipeline`, and
importing an engine vocabulary into a projection layer would put that vocabulary in a second place.

No decision, group, ordering, summary or evidence field changes because a technical context exists.
It reaches **`fmis.scan_memory` not at all** — the Slice 3 comparison dimensions are deliberate, and
an EMA value or a crossing count that moved every refresh would turn *what changed* into noise.

## Consequences

* The operator can, for the first time, see per role: the regime in three dimensions, the structural
  trend, the nearest structural level above and below, how many levels exist each side, the level
  crossing history's size and its latest events, the latest structure break, whether a change of
  character has occurred and when, the indicator values, and what is still warming up.
* Later deterministic engines — zones, phases, opportunity, indicator context, divergence — consume
  a boundary that already carries what they need, instead of re-fetching or re-deriving it.
* `fmis.swing_setup` grows two composition functions and keeps every existing signature: the
  existing ones become thin wrappers that drop the new element, the arrangement `compose.py` already
  used when `setup_inputs_and_assessment_for_sheet` was introduced.
* The workspace holds more objects per symbol. Measured rather than assumed — see report 0049 §17.
* **`SetupInputs` is now explicitly closed to general technical facts.** A future milestone that
  wants the policy to read one must say so, and justify it against the independence constraint.

## Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Add the fields to `SetupInputs` | It is the strategy's input surface. Widening it makes every recovered fact a candidate gate, destroys the ability to answer *what may the policy see* by reading one type, and moves the policy non-regression digest. |
| A new top-level `fmis.technical_analysis` package | It would import `fmis.pipeline` and so occupy the tier `fmis.pipeline` already occupies, for one projection. §24 of the milestone brief and the repository's own ownership rule both say use the existing owner. |
| Carry the whole `MultiTimeframeFactSheet` above the seam | Simplest, and wrong in two ways: it hands every consumer the raw candles (so a renderer *could* compute), and it gives the workspace no stated contract about what it may rely on. |
| Reduce crossings to a count and drop the history | Exactly the loss this milestone exists to stop. A count cannot answer *which level, when, how far, how it arrived* — the four things a later interaction engine needs. |
| Convert levels and events to formatted strings at the seam | Seam 5 of report 0047 is the repository already having done this once, and `fmis.swing_setup.decision_summary` exists specifically because a later layer had been reduced to string-matching sentences a policy wrote. |
| Extend `SetupReadings` instead of adding a new type | `SetupReadings` answers *when was each role read and what did the policy read from it*; it lives in `fmis.swing_setup` and holds policy-adjacent enums. The technical context is a view of the fact sheet and belongs beside the fact sheet. Merging them would put `fmis.level_crossing` and `fmis.features` vocabularies inside the strategy package. |
| Let the dashboard pick the latest crossing itself | Selection over a market event sequence is a market fact, and the dashboard is guarded against producing one. §5 puts it where it belongs. |

## How it is enforced

* `tests/test_technical_context.py` — the projection: role isolation, no recomputation, identity
  preservation, reference equality against the sheet's own objects, no arithmetic in the module,
  bounded-summary correctness, and directional symmetry.
* `tests/test_technical_context_carriage.py` — the seam matrix: each role's facts survive
  `run_setup_for_symbols` → `SetupRunResult` → `SymbolDecision` → `SymbolDecisionRow` with identity
  and classification intact, an unavailable fact stays explicitly unavailable, and roles cannot be
  swapped.
* `tests/test_swing_setup_policy_non_regression.py` — unchanged, and unchanged in result.
* `tests/test_scan_memory_*` plus a new regression asserting the recovered context reaches no
  comparison dimension.
* `tests/test_operator_dashboard_architecture.py` — unchanged, and still passing: the dashboard
  names no indicator identifier and performs no arithmetic over the new rows.
