# ADR-0017 — Structural trend: summarising a sequence, and naming the policy that does it

**Status:** Accepted
**Date:** 2026-07-29
**Decides:** what "structural trend" means in this repository, the policy that derives it, how ambiguity
is reported rather than resolved, and what the result is forbidden from claiming (Milestone AA)
**Implemented by:** `Add Trend Foundation v1`
**Depends on:** [ADR-0016](ADR-0016-structural-sequence-state-history-foundation.md) (the history this
consumes — Milestone Z1)
**Relates to:** [ADR-0015](ADR-0015-structural-sequence-state-foundation.md) (the states being
summarised, and the outward/inward/static axis that makes only two of them directional);
[ADR-0014](ADR-0014-structural-swing-label-foundation.md) (naming a fact is not reading it);
[ADR-0013](ADR-0013-swing-relationship-foundation.md) (exact comparison; order validated, never repaired);
[ADR-0012](ADR-0012-market-structure-foundation.md) (non-repainting detection; a package rather than a
Feature); [ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence);
[the architecture review](../reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) §13 row C and §15;
[the state-history review](../reviews/STRUCTURAL_SEQUENCE_STATE_HISTORY_REVIEW_V1.md) §8, which
recommended this milestone; [the design](../design/TREND_FOUNDATION_DESIGN_V1.md)

---

## Context

ADR-0016 produced a prefix-stable record of how structure changed over time, and closed with §12: having
the history makes trend *expressible*; it does not answer it, and a reader must not infer that a run of
`SHIFTED_HIGHER` snapshots is a small answer to the question.

This ADR answers it — and the hazard is different from every ADR before it. ADR-0014's risk was that a
*name* would drag a market view along; ADR-0015's was that a *state* would imply persistence; ADR-0016's
was that a *transition flag* would pre-empt three later layers. Here the risk is more direct: **there is
no objective answer.** The architecture review §13 flagged this milestone as "high risk of embedding
interpretation too early" and said plainly that *"how many swings make a trend" has no objective answer;
it is a policy, and it must be stated as one.*

So this ADR does not claim to have discovered what a trend is. It records a policy, names the number the
policy turns on, measures what that number does, and states what the result may not be read as.

## Decisions

### 1. The definition
> A **structural trend** is a *sustained same-direction structural shift*: at least
> `MINIMUM_DIRECTIONAL_SHIFTS` snapshots whose state is the same directional member, with no opposing
> directional snapshot between them.

### 2. Only `SHIFTED_HIGHER` and `SHIFTED_LOWER` are directional evidence
Of the six `StructuralSequenceStateType` members, exactly two say that *both* structural sides moved the
same way in price. That is not a convenience: it falls directly out of the outward/inward/static axis
ADR-0015 §2 built the enum on. `EXPANDED` is outward with nothing inward, `CONTRACTED` is inward with
nothing outward, `UNCHANGED` is nothing moved, and `INSUFFICIENT_STRUCTURE` is a side that does not exist
yet.

Reading a direction out of any of those four would invent one where ADR-0015 §5 says none is present. The
mapping from a directional state to its sustained member is `models._TREND_BY_DIRECTIONAL_STATE` — private,
a `MappingProxyType`, written cell by cell, following ADR-0015 §10 exactly, and it is the single authority
for what "directional" means so the predicate and the mapping can never disagree.

### 3. The other four states are transparent
They neither advance nor invalidate a run.

This is the decision most likely to be questioned, so the reasoning is recorded in full. None of the four
is evidence *against* a direction. Deciding that expansion *ends* a trend is a market claim of exactly the
kind ADR-0015 §5 forbids — and it was measured: candidate policy C, which resets on any non-directional
state, turns `SUSTAINED_HIGHER` into `INDETERMINATE` on the sequence `H H E H`, losing an established trend
to a snapshot that says nothing about direction. In real candle-derived histories, where non-directional
states are common, C's answer is dominated by its reset rule rather than by structure.

### 4. The threshold is 2, and it is a policy, not a measurement
`MINIMUM_DIRECTIONAL_SHIFTS = 2`.

No number here can be derived from anything. Two is chosen as the smallest integer that expresses
*repetition*: one shift is a single already-settled fact about one candle, and calling that a trend renames
a fact rather than reads a sequence — the move ADR-0014 and ADR-0015 each refused. Any larger value is a
strictly more arbitrary choice.

It is exposed as a **public module constant** so the policy is legible in code and in tests, and it is
deliberately **not a function parameter**: a parameter invites per-call tuning, and §7 makes the
prefix-stability guarantee per-threshold, so two results derived under different thresholds are not
comparable. Changing it changes the meaning of every result and requires its own decision record.

Measured over 1,627 non-empty state sequences: `minimum=1` yields a direction in 79% of them, `minimum=2`
in 22%, `minimum=3` in 5%. The threshold materially changes the answer, which is precisely why it is
stated in the open rather than buried in a conditional.

### 5. `NEUTRAL` and `INDETERMINATE` are different, and both exist
Four members, partitioning every case with no catch-all (ADR-0015 §2's reasoning):

| Condition | Member |
|---|---|
| run length ≥ minimum, higher | `SUSTAINED_HIGHER` |
| run length ≥ minimum, lower | `SUSTAINED_LOWER` |
| run length < minimum, history contested | `NEUTRAL` |
| run length < minimum, never contested | `INDETERMINATE` |

`NEUTRAL` means **evidence exists on both sides and conflicts**. `INDETERMINATE` means **evidence is
absent** — empty input, non-directional-only, insufficient-structure-only, or exactly one shift.

Folding them together was rejected as the central ambiguity-hiding failure available here: one says the
structure has moved both ways, the other says it has barely moved at all, and a consumer that cannot tell
them apart cannot tell a choppy market from a quiet one. Three of the four candidate policies could not
express both, and that is what disqualified them as much as any behavioural difference.

`contested` is **monotone** — once a history has contained an opposition, `INDETERMINATE` never returns,
because "not enough evidence yet" becomes permanently false the moment conflicting evidence exists.

### 6. Ambiguity is reported, never resolved
On a strictly alternating history no run ever reaches the minimum, so the answer is `NEUTRAL` — not the
latest direction. Candidate policy A reports a flipping direction at every position on exactly this input,
and was rejected for it.

### 7. Persistence is unconditional, and invalidation is exactly one opposing shift
A sustained trend survives any number of non-directional snapshots (§3). It is invalidated by **one**
opposing directional shift, immediately: the run restarts at length 1 in the new direction, and because the
history is now contested the result is `NEUTRAL`, not the opposite sustained trend.

Requiring *two* opposing shifts before releasing the old trend was rejected: it would report
`SUSTAINED_HIGHER` while the most recent structural fact says both sides moved lower, which is hiding
ambiguity.

**The limitation this leaves, stated plainly:** a trend established once and followed by five hundred
contracting snapshots still reads as sustained. That is real. It is preferred to the alternative because
every decay or timeout rule needs an arbitrary constant this layer has no basis for, and a wrong constant
would be invisible — whereas this limitation is documented, tested, and visible. A consumer needing recency
has every snapshot's `index` and `timestamp`.

### 8. The prefix-stability guarantee, stated exactly
> For any snapshot history `h` and any `k`:
> `derive_structural_trend_history(h[:k]) == derive_structural_trend_history(h)[:k]`.

The derivation is a left fold whose step reads only the accumulator and the current snapshot's state, and
whose classification is a pure function of the accumulator, so output element *j* depends on `h[0..j]` and
on nothing after it. ∎

Composed with ADR-0016 §6, the trend history is therefore prefix-stable under **candle-series extension**
and under **complete structural-group extension**. Measured: **0 violations** across 2,000 candle-series
prefixes and 739 complete-group prefixes.

### 9. The limitations of that guarantee, stated just as exactly
1. **An arbitrary cut inside a same-candle HIGH/LOW group** is outside it — inherited verbatim from
   ADR-0016 §7, neither weakened nor repaired. It cannot arise from candle growth and is not detectable.
   Measured at 133 divergences over 891 split groups, and **a test asserts the divergence still exists**,
   so the limitation cannot be quietly "fixed" into a false guarantee.
2. **Nothing is claimed across two `detect_swings` parameterisations.** Different `left_bars`/`right_bars`
   produce a different history entirely.
3. **Nothing is claimed across two values of `MINIMUM_DIRECTIONAL_SHIFTS`** (§4).
4. **The guarantee is that an already-emitted reading never changes — not that the trend keeps its value.**
   A later opposing shift may invalidate a sustained trend; that is §7 working, not instability. A test
   pins the distinction.
5. **Nothing about a forming candle**, inherited from ADR-0012; the history never contains one.

### 10. A sibling package, not `market_structure` and not `features.trend`
`fmis.structural_trend`, importing only `fmis.market_structure`'s public surface.

| Placement | Verdict |
|---|---|
| inside `fmis.market_structure` | rejected. ADR-0016 §12 states trend is not that package's job, and its own architecture test forbids the token `trend` anywhere in its code — a guard that exists to hold exactly this line. Adding trend there would require weakening it |
| `fmis.features.trend` (Tier-2) | rejected. A tuple of `StructuralTrendSnapshot` dataclasses is not a `FeatureValue`, so it cannot be a `FeatureResult.value` without being flattened into dictionaries and losing its type — the reasoning ADR-0012 used to make `market_structure` a package. That placeholder remains for indicator-derived trend features |
| a new sibling package | **chosen**, matching the architecture review §15 recommendation. It keeps `market_structure`'s property that only its first stage ever touches a candle, and that it holds no interpretation |

A test asserts that `market_structure` still contains no trend vocabulary, so the reason this package is a
sibling remains enforced rather than remembered.

### 11. Two API shapes, one rule
`derive_structural_trend` returns the trend now; `derive_structural_trend_history` returns one reading per
snapshot. The scalar is **not** `history[-1]`, for ADR-0016 §10's reason: making the cheap "what is it now"
query allocate an entire history is a real cost for the most common call.

The risk of two paths is that they disagree, so both fold with the same private `_advance` and classify with
the same private `_classify` — one rule, not two implementations — and an equivalence contract is tested.
An AST test asserts both public functions call both private helpers, so the shapes cannot drift apart.
Empty input is the one place they correctly differ in shape: `()` versus `INDETERMINATE`, because one
describes a sequence and the other a current condition.

### 12. Totality: every snapshot gets a reading
Exactly one `StructuralTrendSnapshot` per input snapshot, including those whose trend is `INDETERMINATE`.
Suppressing them would make the history start at an arbitrary point and would lose the distinction between
"nothing conclusive yet" and "no snapshot here" — ADR-0016 §5's reasoning, applied one layer up.

### 13. The accumulator is private, and there is no score
`direction`, `length` and `contested` live in a private frozen `_Run` and appear on no public type. A run
length exposed publicly is a confidence score by another name, and it would invite threshold-shopping over
a policy already stated once. There is no confidence, strength, rank, probability, magnitude or duration
anywhere in this package.

### 14. What `StructuralTrendSnapshot` deliberately cannot validate
`StructuralSwing.label` and `StructuralSequenceState.state` are each checked against the object's own other
fields. `trend` **cannot be**: a trend is a property of the whole *prefix*, not of one snapshot, so the very
same state snapshot legitimately carries a different trend depending on what preceded it.

So the type validates types only, and the correctness of `trend` is a property of the derivation, tested
there. Recording that honestly is better than claiming a validation that cannot exist — and it is why the
derivation's tests carry an independent oracle rather than relying on model self-checks.

### 15. Ordering: a genuinely different rule, not a second copy of one
The rule is `index` and `timestamp` **strictly** increasing, validated and never repaired.

`market_structure.models._validate_key_order` is deliberately not reused. It permits a *non-decreasing*
index because one outside bar yields two swings at one index, with strictness only within a `SwingType`. A
snapshot history has already collapsed those groups (ADR-0016 §1–§2), so it has exactly one entry per index
and strictness is global — and there is no `SwingType` to be strict within. Reusing the looser rule would
accept a two-snapshots-at-one-index history that no valid history contains.

This is a different rule over a different element type, not the duplication ADR-0013 §6, ADR-0014 §6,
ADR-0015 §9 and ADR-0016 §8 each refused. The distinction is recorded because "reuse the shared rule" is
the right instinct and would be wrong here.

### 16. Everything below is delegated; nothing is re-derived
Detection, comparison, labelling and state classification each keep their single authority in
`fmis.market_structure`, and none is re-implemented. This package reads `snapshot.state.state` and nothing
else from a snapshot — enforced by AST tests that reject any read of `latest_high`, `latest_low`, `label`,
`triggers`, `comparison`, or any candle field, and any call to `detect_swings`, `compare_swings`,
`compare_swing_sequence`, `label_swing`, `label_swing_sequence`,
`derive_structural_sequence_state`, `derive_structural_sequence_state_history`, `_sequence_state_for`,
`sorted` or `reversed`.

### 17. Still not evidence, and still not a signal
Nothing here classifies in ADR-0011 §1's sense, so no `EvidenceDescriptor` was added,
`EvidenceFamily.MARKET_STRUCTURE` remains empty, the catalog remains at six, and the
`EvidenceFamily` enum is unchanged — all four pinned by test.

`SUSTAINED_HIGHER` is **not** an uptrend, bullish, strong, momentum, a breakout, a continuation, a reason to
buy, or a prediction, and `SUSTAINED_LOWER` is not a short signal. `NEUTRAL` is not a range and not
indecision.

### 18. Trend is never an input to a break
The architecture review §15 fixed the ordering and it stands: BOS is defined purely on levels, CHoCH over
the BOS sequence, and any definition making trend an input to either is rejected on sight. This package
consumes the state history and defines nothing directional for a lower layer to depend on. Nothing below it
imports it — enforced by test.

## Alternatives considered

Four candidate policies were implemented as scratch experiments and measured over 1,629 state sequences
(13 named history classes, 1,555 exhaustive sequences of length 0–4, 61 candle-derived runs including
outside bars). All four are prefix-stable, so that property alone did not discriminate.

| Candidate | Rejected because |
|---|---|
| **A — latest directional state wins** (`minimum = 1`) | **forces direction.** Reports a flipping direction at every position of a strictly alternating history, and cannot express `NEUTRAL`, so contested ambiguity is indistinguishable from a clean run. It reduces trend to a rename of `snapshot.state.state` |
| **B — majority vote** | **double-counts evidence and hides ambiguity.** A shift from 300 snapshots ago is weighted like the newest, so `H H L` still reports `HIGHER`; and it cannot express `INDETERMINATE`, reading an empty history as `NEUTRAL`. Any fix (window, decay, recency weight) adds a second arbitrary parameter |
| **C — strict adjacency** | **treats a neutral fact as counter-evidence, so it cannot persist** (§3) |
| **D — sustained run** | **chosen** |
| **E — derive trend from the structural labels directly** | duplicates `_sequence_state_for` and the outside-bar grouping policy inside the trend layer; ADR-0016 exists so this is unnecessary |
| **F — require a candle or close confirmation** | reintroduces a `CandleSeries` dependency above `detect_swings` (architecture review §15) and would repaint on a forming bar (ADR-0012) |
| **G — define trend via break of structure** | requires BOS, which cannot exist at this layer, and is the circularity §15 says to reject on sight |
| **H — a `MIXED` / `AMBIGUOUS` catch-all beside `NEUTRAL`** | the four members already partition every case; a fifth would be where ambiguity accumulates (ADR-0015 §2) |
| **I — a decay or timeout rule** | invents a second arbitrary constant with no basis in any fact this layer holds; §7 documents the limitation instead |
| **J — expose the run length or a strength score** | a confidence score in all but name (§13) |
| **K — reuse `_validate_key_order` for ordering** | its rule is looser in a way that matters here (§15) |
| **L — suppress `INDETERMINATE` readings** | makes the history non-total (§12) |
| **M — make the threshold a parameter** | invites per-call tuning of a stated policy, and the stability guarantee is per-threshold (§4) |
| **N — claim unconditional prefix stability** | false (§9) |

## Consequences

- The package now has its first deterministic *summary* of the state history, and it is a summary rather
  than a reading: every conclusion is traceable to a run of already-settled facts.
- **A policy now exists in the repository that no amount of testing can validate as correct** — only as
  correctly implemented and honestly stated. `MINIMUM_DIRECTIONAL_SHIFTS` is that policy. Any future
  disagreement with it is a disagreement about the number, and should be argued as such rather than by
  changing what the four members mean.
- The unconditional-persistence limitation (§7) is now a documented property of the system. Anything built
  on top must not assume a sustained trend is recent.
- Two API shapes coexist under a tested equivalence contract, as in ADR-0016 §10.
- Readings are rebuilt on every call, so they compare `==` across calls but are not identical. Tests assert
  `==`, never `is`, and consumers must do the same.
- The `EQUAL_*` and exact-comparison limitations from ADR-0013 §4 are inherited unchanged, as is the
  event-indexed nature of the history from ADR-0016: a consumer wanting a value at every bar must join on
  `index` or `timestamp` itself.
- **Still postponed, and unblocked by nothing here:** BOS, CHoCH, support/resistance, protected levels,
  liquidity, sweep, double top/bottom, regime, bias, multi-timeframe merging, tolerance/tick-size handling,
  incremental derivation, and every evidence descriptor for market structure.
