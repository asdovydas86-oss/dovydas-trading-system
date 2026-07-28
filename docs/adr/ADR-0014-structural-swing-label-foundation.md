# ADR-0014 — Structural swing labels: naming a fact, not reading it

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** the composite name for a `SwingType` + `SwingRelation` pairing, and the boundary that name
must not cross (Milestone X)
**Implemented by:** `Add structural swing label foundation`
**Relates to:** [ADR-0013](ADR-0013-swing-relationship-foundation.md) (which deliberately withheld this
naming); [ADR-0012](ADR-0012-market-structure-foundation.md) (the swing points underneath);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence)

---

## Context

ADR-0013 kept `SwingType` and `SwingRelation` as two separate facts and said the composite vocabulary
would be its own milestone, needing its own decision record. This is that record.

The thing being added is small — six names for six combinations — and the risk is entirely in what those
names drag along with them. "Higher high" is a phrase most traders already have opinions attached to, so
introducing it as an identifier is the moment a codebase quietly acquires a market view it never decided
to hold.

## Decisions

### 1. The label is derived from `current.type` and `relation`, nothing else
One authoritative mapping, exhaustive over both source enums:

| `SwingType` | `SwingRelation` | `StructuralSwingLabel` |
|---|---|---|
| HIGH | HIGHER | `HIGHER_HIGH` |
| HIGH | LOWER | `LOWER_HIGH` |
| HIGH | EQUAL | `EQUAL_HIGH` |
| LOW | HIGHER | `HIGHER_LOW` |
| LOW | LOWER | `LOWER_LOW` |
| LOW | EQUAL | `EQUAL_LOW` |

The **previous** point's type is deliberately not consulted. `SwingComparison` already guarantees both
points share a type, so reading both would create two sources for one fact and invite them disagreeing.

Note this makes one mutation untestable at runtime: swapping `current.type` for `previous.type` produces
identical output for every valid comparison, precisely *because* of that invariant. The rule is therefore
pinned by a static check on the source instead — the honest place to enforce something that cannot be
observed from outside.

### 2. Naming is not interpreting
`HIGHER_HIGH` means: the current swing is a high, and its price is numerically above the previous high.
It does **not** mean uptrend, breakout, break of structure, change of character, continuation, strength,
or a reason to buy. `LOWER_LOW` is not a short signal.

The enum has no vocabulary for any of that — no BULLISH, BEARISH, CONTINUATION, REVERSAL, BREAK, BOS,
CHOCH, LONG, SHORT, BUY, SELL, STRONG, WEAK, CONFIRMED, INVALID — and a test scans for it. The underlying
`type` and `relation` remain available on the comparison, so naming the pair loses nothing and forecloses
nothing.

### 3. Full names are canonical; abbreviations are prose only
`HIGHER_HIGH`, not `HH`. The shorthand is fine in a sentence and appears in this document, but it must not
be the API.

The reason is concrete rather than stylistic: `LH` and `HL` differ by a single transposition and mean
opposite things — a lower high versus a higher low. That is a poor property for an identifier destined to
appear inside conditionals, and the failure mode is a silent inversion rather than an error. `EH` and `EL`
are worse still, being near-invisible in a list. Six full names cost nothing to read.

### 4. `EQUAL_HIGH` and `EQUAL_LOW` are first-class
Never folded into HIGHER or LOWER, never dropped, and never renamed. A retest at exactly the previous
level is its own structural fact.

It is also where interpretation pressure is strongest: an equal high is what people go on to call a
double top, resistance, a liquidity pool, or consolidation. Every one of those is a *reading*, each with
its own conditions, and each belongs to a later layer that can state them. Collapsing EQUAL into a
neighbouring label would destroy the fact before that layer ever sees it.

Equality is **inherited, not redefined**. The relation was already fixed by `SwingComparison` using exact
stored-float comparison (ADR-0013 §4); this layer never touches a price, so no epsilon, tick-size
equivalence, rounding, ATR tolerance, or percentage band appears here — and the storage-level limitation
recorded there carries forward unchanged.

### 5. Two fields, and no duplicated facts
`StructuralSwing` holds a `SwingComparison` and a `StructuralSwingLabel`. It does **not** re-expose
`previous`, `current`, `relation`, `price`, `index`, `timestamp`, or `type` as its own fields: they are
all reachable through the comparison, and a copy is somewhere for them to disagree.

The label is **validated against the comparison** rather than trusted, so an object claiming
`HIGHER_HIGH` for a low that fell cannot be constructed. Frozen, slotted and hashable, matching every
other value type in this package.

### 6. The mapping is private, and `label_swing` is the only public derivation
`models._LABEL_BY_TYPE_AND_RELATION` and `models._label_for` are internal, for the same reason
`_relation_for` is (ADR-0013 §6). A public `label_for(type, relation)` would let a caller name a pairing
that no validated `SwingComparison` ever produced — a plausible-looking shortcut around the invariants.
The mapping is an immutable `MappingProxyType` so the vocabulary cannot be re-pointed at runtime.

### 7. Sequence order is preserved, never repaired
Input order is output order, one label per comparison — including at equal indices (§8). Sorting silently
would hide a caller's bug while presenting the result as sequential — the same reasoning as ADR-0013 §5,
one layer up.

The ordering contract is checked on each comparison's `current` point: globally non-decreasing index and
timestamp, shared index requires shared timestamp, and **strictly** increasing within each `SwingType`.
Per-type strictness is also what rejects a duplicated comparison object.

### 8. Equal-index secondary order is inherited, never imposed
Two comparisons can share a `current.index` when one candle produced both a HIGH and a LOW. Their
relative order in the output is **whatever order the input had** — this layer labels, it does not reorder,
and it does not independently impose HIGH-before-LOW.

That distinction matters because HIGH-before-LOW is a property of `detect_swings`, not a rule of the
relationship or labelling layers. `compare_swing_sequence` accepts a valid run in either order and
preserves it, so a LOW-before-HIGH equal-index run is legitimate upstream input and comes back labelled
in that same order. Both directions are tested.

Had labelling imposed a canonical type order instead, it would silently disagree with its own input for
any caller who legitimately supplied the other order — a reordering layer masquerading as a naming one.

### 9. Outside-bar equal indices must be accepted
`compare_swing_sequence` legitimately emits two comparisons sharing a `current.index` when one candle
produced both a HIGH and a LOW. Global strictness would reject that and break the composition this layer
exists for — the same trap ADR-0013 §5 documents, and it was re-verified against real detector output
before the rule was written rather than assumed.

### 10. Labels are still not evidence
Nothing classifies them, so no `EvidenceDescriptor` was added and `EvidenceFamily.MARKET_STRUCTURE`
remains empty. Per ADR-0011 §1 a computed value earns a descriptor by being *classified*, and giving a
fact a conventional name is not classification.

### 11. BOS, CHoCH and trend remain later milestones
Each is defined over a *sequence* of labels plus a rule about what counts as a break, which requires
decisions this milestone deliberately does not make: how many swings form a trend, whether an equal high
breaks structure, what happens across timeframes. Having the labels makes those questions expressible;
it does not answer them.

## Alternatives considered

- **Abbreviated members** (`HH`, `LH`, …). Rejected: transposition-adjacent identifiers meaning opposite
  things (§3).
- **Fold EQUAL into the nearest directional label**, or drop it. Rejected: destroys a real structural fact
  and pre-empts the double-top / resistance / liquidity readings that belong to later layers (§4).
- **Put the label on `SwingComparison`** instead of a wrapper. Rejected: it would make ADR-0013's
  deliberate separation of type and relation pointless, and every consumer of a comparison would carry a
  name it may not want.
- **Duplicate `current`, `price` or `index` onto `StructuralSwing`** for convenience. Rejected: two places
  for one fact (§5).
- **A public `label_for(type, relation)`.** Rejected: names pairings no validated comparison produced (§6).
- **Interpret while naming** — e.g. a `bias` field alongside the label. Rejected outright: that is the
  entire boundary this milestone holds.

## Consequences

- The conventional vocabulary now exists, and a later trend or structure-break layer can be written
  against names rather than tuples.
- Those later layers must supply their own definitions; nothing here says what a run of `HIGHER_HIGH`
  means, and a reader must not infer that it does.
- `StructuralSwing` is a thin wrapper. If a consumer finds itself reaching through
  `swing.comparison.current.price` constantly, that is a signal the *consumer* wants a projection — not
  that this type should grow fields.
- The exact-equality limitation from ADR-0013 §4 is inherited verbatim: `EQUAL_HIGH` fires only for
  bit-identical stored prices, and "equal within a tick" remains inexpressible until a tick-size
  abstraction exists.
