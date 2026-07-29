# ADR-0016 — Structural sequence state history: recording a sequence, not reading it

**Status:** Accepted
**Date:** 2026-07-29
**Decides:** how the structural sequence state is recorded over time, what guarantee that record
carries, and what it is forbidden from concluding (Milestone Z1)
**Implemented by:** `Add structural sequence state history foundation`
**Depends on:** `Refactor structural sequence ordering validation` (Milestone Z0)
**Relates to:** [ADR-0015](ADR-0015-structural-sequence-state-foundation.md) (the state being recorded);
[ADR-0014](ADR-0014-structural-swing-label-foundation.md) (the labels beneath, and the equal-index order
rule); [ADR-0012](ADR-0012-market-structure-foundation.md) (non-repainting detection);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence);
[the market structure architecture review](../reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) §18,
which recommended this milestone; [the design](../design/STRUCTURAL_SEQUENCE_STATE_HISTORY_DESIGN_V1.md)

---

## Context

ADR-0015 made a deliberate and correct choice: `StructuralSequenceState` describes the *latest* pair and
is superseded when a newer swing confirms. §8 there states plainly that prefix stability is **not**
claimed for it.

That choice has a consequence the architecture review named as the package's largest gap: there was no
prefix-stable view of how structure changed over time. Every plausible next layer — trend, break of
structure, change of character — is defined over a *sequence* of states, so each would have had to derive
its own sequencing from the label run. That is the duplication ADR-0013 §6, ADR-0014 §6 and ADR-0015 §9
each refused, and P2-1 of the review showed how quickly two copies of one rule appear.

This ADR records the layer that closes the gap without taking a single interpretive step.

## Decisions

### 1. One snapshot per candle that changed structure
`derive_structural_sequence_state_history` folds an ordered `StructuralSwing` run into one
`StructuralSequenceStateSnapshot` per distinct `current.index`, in input order.

Candles at which nothing was confirmed produce no snapshot. The history is **event-indexed, not
bar-indexed**: it answers "what did structure look like each time it moved", not "what did it look like
at every bar". A bar-indexed view would require a candle count this layer deliberately does not receive.

### 2. Structural groups are applied atomically
Every swing sharing a `current.index` is applied *before* that index's snapshot is emitted. One outside
candle produces one snapshot holding both swings.

This carries ADR-0015 §7 forward, and it is not cosmetic. With a falling outside bar, applying the HIGH
half alone reads `CONTRACTED` while the complete candle reads `SHIFTED_LOWER`. Only the second describes
the candle. A per-swing design would emit the first, and the architecture review measured that artefact
appearing in 12 of 120 random series.

Either input order of the pair gives the same `state`, `index` and `timestamp`.

### 3. Two fields, and no duplicated facts
`StructuralSequenceStateSnapshot` holds a `StructuralSequenceState` and a tuple of `StructuralSwing`
triggers. Nothing else.

The state is embedded **whole** rather than flattened. It already validates that its own three fields
agree (ADR-0015 §3), so re-exposing `latest_high` / `latest_low` / `state` here would create a second
place for them to disagree — the hazard ADR-0014 §5 removed one layer down.

`triggers` are the swings confirmed *at this candle*, which is a different fact from the state's latest
sides: a side not confirmed here is carried forward from an earlier snapshot, by identity. Keeping both
means a consumer can always tell what changed from what merely persists.

The snapshot is validated against its triggers, not trusted: a snapshot whose trigger is not the state's
own latest side for that swing type cannot be constructed. That check is by **identity**, so a snapshot
cannot pair a state with a plausible-looking but unrelated cause.

### 4. `index` and `timestamp` are projections, not fields
Both are computed `@property` values over `triggers[0].comparison.current`. Every trigger shares them,
enforced on construction, so storing them would duplicate a derived fact — and a stored copy is somewhere
for it to drift.

The alternative was to store them and validate, which is what `StructuralSwing.label` and
`StructuralSequenceState.state` do. Those are different: a label and a state are *derived by a rule* that
could in principle be wrong, so validating them catches a real error class. An index copied from a field
one attribute away is not a rule, it is a copy.

`@property` on a frozen dataclass is established repository practice (`decision_support.report`,
`features.volume.statistics`), and it is the first use in this package.

### 5. Insufficient structure is recorded, never suppressed
Until both sides exist the state is `INSUFFICIENT_STRUCTURE`, and those snapshots are emitted like any
other. "At this candle structure was not yet determinable" is a fact about that candle.

Suppressing them would make the function silently non-total — the history would start at an arbitrary
point with no way to tell "nothing happened" from "not enough had happened" — and a consumer that wants
only complete states can filter in one expression. It also preserves a useful property, tested: the
insufficient snapshots form a contiguous prefix, because once both sides exist neither becomes
unavailable again.

### 6. The prefix-stability guarantee, stated exactly
> The history is prefix-stable under **candle-series extension** and under **complete structural-group
> extension**.

Appending later candles, or later whole same-candle groups, never alters a snapshot already produced.
This restores at the history level what ADR-0015 §8 explicitly declined to claim for the single
aggregate, and it is what makes snapshots historical facts rather than a value that keeps changing.

The proof is short: grouping by index yields contiguous groups, because indices are non-decreasing; a
snapshot's sides are the last HIGH-side and LOW-side swings in the groups up to and including its own;
nothing later is read; and the state is a pure function of those two sides. So snapshot *j* depends on no
element after group *j*. ∎

### 7. The limitation, stated just as exactly
The guarantee does **not** extend to an arbitrary cut *inside* a same-candle HIGH/LOW group.

Taking the HIGH of an outside bar without its LOW yields a different state for that candle. Both outputs
are correct functions of their respective inputs; the inputs differ.

It cannot arise from candle growth — a candle produces both swings of an outside bar or neither, and
`detect_swings` emits them together. It is also **not detectable**: a HIGH at an index with no LOW is a
perfectly legal run, since most candles are not outside bars, so this layer cannot distinguish "you split
my group" from "there was no low here".

The narrower true claim is documented in preference to the broader false one, and a test pins the
divergence so it cannot be rediscovered as a surprise. Documenting a limitation is worth as much as
documenting a guarantee: a consumer who cached snapshots believing the stronger claim would be wrong
silently.

### 8. Everything is delegated; nothing is re-derived
Ordering is validated by `models._validate_current_point_order`; classification is
`models._sequence_state_for`; labels, comparisons and detection are untouched. This module performs **no
arithmetic**, names **no** `StructuralSequenceStateType` member, and reads no candle field — all three
enforced by AST tests, so a future "small optimisation" that inlines a rule fails the suite rather than
quietly creating a second source of truth.

### 9. No transition type, no "changed" flag
There is deliberately no `StructuralSequenceTransition`, no `changed` boolean, no direction, magnitude or
duration.

Whether one snapshot following another is meaningful is a *reading*: it needs a rule about what counts as
a change worth naming, and that rule is the substance of trend, BOS and CHoCH. A flag would look
innocuous and would pre-empt all three. A consumer comparing `history[i - 1].state.state` with
`history[i].state.state` already has every fact such a layer would need, expressed in vocabulary that
already exists.

All 36 ordered state pairs are reachable and all are legal. This layer asserts nothing about which are
significant.

### 10. Both the single-state and history APIs remain
`derive_structural_sequence_state` was not reimplemented as `history[-1].state`. Doing so would make the
cheap "what is it now" call allocate an entire history, which is a real cost for the most common query.

The risk of two paths is that they disagree, so an **equivalence contract** is tested instead: for every
valid non-empty input, `history[-1].state == derive_structural_sequence_state(...)`. Empty input is
tested too, where the two correctly differ in shape — `()` versus an `INSUFFICIENT_STRUCTURE` state with
both sides `None` — because one describes a sequence of events and the other a current condition.

### 11. Relationship to Z0
Milestone Z0 unified the two independent sequence-ordering implementations (review findings P2-1, P2-2)
into one core, `models._validate_key_order`, with two adapters that differ only in the nouns their
messages use. All ten messages were preserved byte-for-byte, verified by differential against both
originals over 12,889 generated cases.

Z0 was not a prerequisite — this layer reuses the existing `_validate_current_point_order` adapter and
adds no third copy — but it was sequenced first so that a new consumer arrived after the drift risk was
closed rather than before, and so this milestone's tests could assert equivalence from the start.

### 12. Still not evidence, and still not trend
Nothing here classifies anything, so no `EvidenceDescriptor` was added and
`EvidenceFamily.MARKET_STRUCTURE` remains empty (ADR-0011 §1).

Trend, BOS and CHoCH each need decisions this milestone deliberately does not make. Having the history
makes those questions expressible; it does not answer them, and a reader must not infer that a run of
`SHIFTED_HIGHER` snapshots is a small answer to the first.

## Alternatives considered

- **Compare two `StructuralSequenceState` objects** into a transition type. Rejected: the API could not
  verify that two supplied states are adjacent or even from the same series — the
  shortcut-around-the-invariants hazard of ADR-0013 §6 — and it is subsumed by a snapshot sequence.
- **Emit one snapshot per individual `StructuralSwing`.** Rejected on measured evidence: it exposes the
  half-applied outside-bar state that ADR-0015 §7 exists to suppress, in 12 of 120 random series.
- **Derive transitions without the snapshots between them.** Rejected: discards the states themselves and
  still needs this milestone's grouping policy to know what a transition is at an outside bar.
- **Skip history and go straight to trend.** Rejected: trend defined directly over labels would re-derive
  sequencing inside the trend layer.
- **Suppress `INSUFFICIENT_STRUCTURE` snapshots** (§5), **store `index`/`timestamp`** (§4), **flatten the
  state onto the snapshot** (§3), **sort triggers into HIGH-before-LOW order** (would impose the
  convention ADR-0014 §8 forbids) — each rejected above.
- **Claim unconditional prefix stability.** Rejected as false (§7).

## Consequences

- The package now has a prefix-stable record of structural change, and a later trend or structure-break
  layer can be written against a sequence of facts rather than re-deriving one.
- Two stability classes still coexist, but the boundary moved: swings, comparisons, labels **and history
  snapshots** are settled once emitted; only `derive_structural_sequence_state`'s single answer is
  superseded. Documentation that described "the aggregate" as the sole exception needed updating, and was.
- Snapshots are rebuilt on every call, so they compare equal across calls but are not identical. Tests
  assert `==`, never `is`, and consumers must do the same.
- The history is event-indexed. A consumer wanting a value at every bar must join on `index` or
  `timestamp` itself; this layer will not grow a bar-indexed variant without its own decision record.
- The `EQUAL_*` and exact-comparison limitations from ADR-0013 §4 are inherited unchanged.
