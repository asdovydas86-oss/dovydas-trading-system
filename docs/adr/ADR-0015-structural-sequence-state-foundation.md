# ADR-0015 — Structural sequence state: two sides read together, still not interpreted

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** how the latest HIGH-side and latest LOW-side structural labels combine into a single
state, and what that state is forbidden from claiming (Milestone Y)
**Implemented by:** `Add structural sequence state foundation`
**Relates to:** [ADR-0014](ADR-0014-structural-swing-label-foundation.md) (the labels this consumes);
[ADR-0013](ADR-0013-swing-relationship-foundation.md) (exact comparison, order validated not repaired);
[ADR-0012](ADR-0012-market-structure-foundation.md) (the swing points underneath);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence)

---

## Context

ADR-0014 produced six labels, each describing one side of structure in isolation. Every conventional
reading of market structure — trend, break of structure, change of character, range behaviour — starts
by putting the two sides *next to each other*. That juxtaposition is the smallest honest step beyond
labelling, and it is worth taking on its own, because the step after it is where interpretation begins
and the two should not be taken in one commit.

The hazard here is different from ADR-0014's. There the risk was that a *name* would drag a market view
along with it. Here the risk is that a *state* implies persistence: "the market is contracting" sounds
like a condition that holds and will continue, when all this layer knows is how two already-settled
comparisons stand against each other.

## Decisions

### 1. The latest HIGH and the latest LOW are selected independently
Highs and lows are confirmed on their own schedules. Requiring the two selected sides to share a candle,
an index, or a timestamp would discard nearly every real pair, since the latest swing high and the latest
swing low are almost always from different bars. So each side is simply the last `StructuralSwing` of
that `SwingType` in the supplied run.

"Latest" means **position in the supplied run**, not the largest index. The run is validated as ordered
first, so the two agree; using position keeps the input's own order authoritative rather than
re-deriving one, which is the same reasoning as ADR-0013 §5.

### 2. The complete nine-case matrix, and the axis it is built on
Every complete combination, classified by whether each side moved **outward** from its own previous
swing, **inward**, or not at all:

| | `HIGHER_LOW` (in) | `LOWER_LOW` (out) | `EQUAL_LOW` (static) |
|---|---|---|---|
| **`HIGHER_HIGH`** (out) | `SHIFTED_HIGHER` | `EXPANDED` | `EXPANDED` |
| **`LOWER_HIGH`** (in) | `CONTRACTED` | `SHIFTED_LOWER` | `CONTRACTED` |
| **`EQUAL_HIGH`** (static) | `CONTRACTED` | `EXPANDED` | `UNCHANGED` |

The rule in one sentence: one side out and the other in means both sides moved the same way in price,
which is a shift; otherwise it is expansion if anything went out, contraction if anything went in, and
`UNCHANGED` if nothing moved.

That partition is **exhaustive and disjoint over all nine cells**, which is why the enum has no `MIXED`,
`OTHER` or `UNKNOWN` member. A catch-all would mean the classification was incomplete, and it would
become the place ambiguous cases quietly accumulate.

### 3. The grouping is lossy, so both source facts are retained
Five states over nine combinations loses information on purpose: `HIGHER_HIGH` + `LOWER_LOW` and
`HIGHER_HIGH` + `EQUAL_LOW` are both `EXPANDED`, and a later layer may well need to tell them apart.

`StructuralSequenceState` therefore holds the two `StructuralSwing` objects themselves. A consumer reads
`latest_high.label` and `latest_low.label` and recovers the exact cell — and through the comparison,
every underlying point, index, timestamp and price. Nothing is copied onto the state, so there is no
second place for any of it to disagree (ADR-0014 §5, one layer up).

### 4. `EQUAL_HIGH` and `EQUAL_LOW` are not collapsed
The five equality-containing combinations resolve to three different states, not one. An equal high with
a higher low genuinely contracted; an equal high with a lower low genuinely expanded; equal on both sides
moved nothing at all. Folding them together would throw away a distinction the labels were kept
first-class (ADR-0014 §4) precisely to preserve.

`UNCHANGED` is emphatically not "double top", "double bottom", "support", "resistance" or "liquidity" —
those readings each need conditions this layer does not state.

### 5. Naming: what each state must not be read as
- `SHIFTED_HIGHER` / `SHIFTED_LOWER` — both sides sit at higher (lower) prices than the swings they were
  each compared against. Not uptrend, downtrend, bullish, bearish, strength, or continuation.
- `EXPANDED` / `CONTRACTED` — outward with nothing inward, inward with nothing outward. Not breakout, not
  volatility, not consolidation, not compression.
- `UNCHANGED` — neither side moved.

`ADVANCING_UP` and `ADVANCING_DOWN` were the candidate names and were rejected: "advancing" is a
near-synonym for progressing or trending, and it would smuggle in exactly the reading `SHIFTED_` avoids.
`BALANCED` was rejected for `UNCHANGED` for the same reason — balance implies equilibrium between forces,
which is a market claim, whereas "unchanged" is an observation about two numbers.

"Expanded" and "contracted" describe the two sides' **movement**, not a measured width. Each side is
compared to its own previous swing, and those two baselines are independent and generally from different
candles, so no range size is ever computed — this layer reads no price at all.

### 6. One `INSUFFICIENT_STRUCTURE` state, and no missing-side variants
No labelled HIGH, no labelled LOW, or neither: all give `INSUFFICIENT_STRUCTURE`. Deriving a two-sided
statement from one side would be fabricating the half that is not there.

Separate `HIGH_SIDE_ONLY` / `LOW_SIDE_ONLY` members were considered and rejected as redundant: the state
object still carries whichever side exists, so `latest_high is None` already answers the question with no
extra vocabulary, and every consumer that does not care would have to handle two members instead of one.
This follows `decision_support.OverallState.INSUFFICIENT_DATA` in spirit; the name differs because what is
missing here is a *labelled swing*, not data — the candles may be plentiful.

### 7. Outside bars resolve atomically
One candle can produce both a HIGH-side and a LOW-side `StructuralSwing` at the same index. The whole
supplied run is evaluated and one final state derived from both latest sides, so no intermediate state is
ever exposed in which only half of that candle had been applied.

Exposing one would give artificial meaning to an ordering that is an artefact of emission order, not of
the market: with a falling outside bar, applying the high half alone reads `CONTRACTED` and the complete
pair reads `SHIFTED_LOWER`, and only the second is a fact about that candle. Either order of the pair is
accepted and produces the same state, which is what makes the ordering an artefact rather than a signal.

### 8. Aggregate state evolves, and that is not repainting
This is the first type in the package whose output is *expected to change*, so the distinction has to be
stated plainly rather than left to inference.

A `SwingPoint`, `SwingComparison` and `StructuralSwing` are settled once emitted: they depend only on
closed candles inside their own confirmation window, and appending later data never revises one
(ADR-0012). Those objects remain prefix-stable, and this layer never touches them.

A `StructuralSequenceState` is by construction a statement about *the latest pair*. When a newer swing is
confirmed on either side, a later call returns a different state — a new fact about newer data, not a
revision of an old one. Nothing that was previously reported becomes false; what it described is simply
no longer the latest. The object itself is immutable; it is superseded, never mutated.

**Prefix stability is therefore claimed for the underlying facts and explicitly not claimed for the
aggregate.** Pretending otherwise would be the more dangerous error, because a consumer that cached one
state as permanent would be wrong in a way nothing here would catch.

### 9. One ordering rule, shared rather than re-implemented
The contract of ADR-0014 §7–9 is inherited verbatim: non-decreasing index and timestamp globally, shared
index requires shared timestamp, strictly increasing within each `SwingType`, equal-index order inherited
from the input and never imposed, order validated but never repaired.

It is inherited by **calling the same code**. The check moved into
`models._validate_current_point_order`, parameterised only by the caller's parameter name for error
messages, and both `label_swing_sequence` and `derive_structural_sequence_state` call it. Copying the rule
would have been the obvious alternative and is exactly how two layers end up with contracts that agree
today and diverge in a year.

### 10. The state mapping is private
`models._STATE_BY_LABEL_PAIR` and `models._sequence_state_for` follow `_relation_for` (ADR-0013 §6) and
`_label_for` (ADR-0014 §6). A public `state_for(high_label, low_label)` would let a caller classify a
pairing that no validated pair of `StructuralSwing` objects ever produced. The mapping is a
`MappingProxyType`, written cell by cell rather than derived, so reading it is the same as reading §2's
matrix.

### 11. No state history yet
A `derive_structural_sequence_state_history` was considered and deliberately postponed. It needs one
decision this milestone does not have to make: whether an outside bar that updates both sides at one index
emits one transition or two, and if one, what it is anchored to. §7 answers that question for a single
final state only, and the answer does not automatically generalise. Adding a history now would either
guess or expose the intermediate state §7 exists to suppress.

### 12. Still not evidence, and still not trend
Nothing classifies these states, so no `EvidenceDescriptor` was added and `EvidenceFamily.MARKET_STRUCTURE`
remains empty (ADR-0011 §1).

Trend, BOS and CHoCH are each defined over a *run* of states plus a rule about what counts as a break —
how many swings make a trend, whether an equal high breaks structure, how timeframes combine. Having the
state makes those questions expressible. It does not answer any of them, and a reader must not infer that
`SHIFTED_HIGHER` is a small answer to the first.

## Alternatives considered

- **`ADVANCING_UP` / `ADVANCING_DOWN`.** Rejected: "advancing" implies progress and continuation (§5).
- **A `MIXED` or `OTHER` member.** Rejected: the five states already partition all nine cells, so a
  catch-all could only be a place for ambiguity to hide (§2).
- **`BALANCED` for the both-equal case.** Rejected: equilibrium is a market claim; `UNCHANGED` is an
  observation (§5).
- **Separate missing-side states.** Rejected as redundant given the retained sides (§6).
- **Returning only the enum**, without the two swings. Rejected: the grouping is lossy and the discarded
  detail is exactly what a later layer needs (§3).
- **Requiring the two latest sides to share a candle.** Rejected: it would discard nearly every real pair
  (§1).
- **Sorting the input**, or accepting an unordered run. Rejected: ADR-0013 §5, unchanged.
- **Copying the ordering check** into the new module. Rejected: two copies of one contract (§9).
- **Emitting a state per entry** so an outside bar produces two. Rejected: artificial intermediate meaning
  (§7); a history API would have to decide this properly (§11).

## Consequences

- The two structural sides can now be read together, and a later trend or structure-break layer has a
  state to be written against rather than two loose labels.
- This package now has two kinds of output with different stability guarantees. That distinction is real
  and must be carried into any documentation or interface built on top: "non-repainting" describes the
  swings, comparisons and labels, and does not describe the aggregate state.
- The state is deliberately coarser than its inputs. Any consumer that finds five states insufficient
  should read `latest_high.label` and `latest_low.label` rather than argue for more members.
- The exact-equality limitation from ADR-0013 §4 is inherited unchanged: `UNCHANGED` requires
  bit-identical stored prices on both sides, and "equal within a tick" remains inexpressible.
