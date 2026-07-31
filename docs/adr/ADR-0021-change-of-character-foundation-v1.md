# ADR-0021 — Change of Character Foundation v1: the first break opposing the last determinate one

**Status:** Accepted
**Milestone:** AE
**Date:** 2026-07-31
**Supersedes / amends:** supersedes **ADR-0020 §7's CHoCH sketch**. Extends ADR-0012, ADR-0013, ADR-0018,
ADR-0019, ADR-0020.
**Design:** [`docs/design/CHOCH_FOUNDATION_V1.md`](../design/CHOCH_FOUNDATION_V1.md)

---

## 1. Context

ADR-0020 built the break primitive and deliberately refused every reading over the break *sequence*: whether
a break "failed", whether character changed, whether a trend exists. It named change of character as the
next layer and sketched it in four lines.

This milestone makes exactly that reading and nothing else. Not trend. Not regime. Not bias.

---

## 2. The audit

### 2.1 BOS already contains every primitive CHoCH needs — none is missing, none is invented

Re-derived by inspecting `dataclasses.fields(StructureBreak)` and its property set directly rather than
reading ADR-0020: fields are exactly `{crossing, eligible_from}`, properties exactly
`{index, label, level, origin, side, timestamp}`.

The rule reads `index` and `side`. Both are present. Every other fact — the crossing, the level, its price,
provenance, label and the eligibility bar — is reachable through the break object, which is carried by
reference.

**This is the first milestone in the chain that adds no primitive and requests none.** That is the
strongest available evidence that the layering below is correct: BOS was designed to be consumed this way,
and it is.

ADR-0020 **D1** — the confirmation delay is recorded on no derived fact — remains open and is **not made
worse**. Eligibility was resolved one layer down and is already baked into which breaks exist, so
`derive_changes_of_character` takes **no `confirmation_bars` argument and no configuration of any kind**,
and consequently cannot be misconfigured.

### 2.2 No candle, no level and no crossing is consulted, and that is structural

`fmis.change_of_character` **does not import `fmis.data` at all**, so `Candle` is not a name it can reach.
It takes exactly one name from `fmis.level_crossing` — the type `LevelSide` — and an AST guard in *both*
test suites asserts that is the only one, so `CrossingKind`, `CrossingMechanism`, `PriceLevel`,
`LevelCrossingEvent`, `structural_levels` and `derive_level_crossings` are all unreachable by name. It does
not import `fmis.market_structure` or `fmis.structural_trend` at all.

### 2.3 The finding — ADR-0020 §7's sketch is wrong in exactly one representable case

> **The `zip(breaks, breaks[1:])` adjacency sketch infers a change of character from an ordering the layer
> below explicitly refuses to read as temporal.**

ADR-0020 §3.5 states that two breaks may share a bar — one `UPPER`, one `LOWER` — and that **their order is
the level ordering, not a claim about which happened first**, because OHLC data cannot prove an intrabar
path. Applied to such a pair, the sketch's adjacent pair *is* that pair.

Measured on a run produced by the shipped break layer (shipped as a test fixture):

```
breaks: upper@4 · upper@12 · lower@12

sketch        -> (upper@12 -> lower@12)   ← predecessor on the SAME BAR
this ADR      -> (upper@4  -> lower@12)   ← predecessor on a strictly earlier bar
```

Both agree **bar 12 is where character changed**. They disagree about what it changed *from*, and only one
can answer without fabricating an intrabar path.

Notably this is **not** a prefix-stability argument: both rules measure **0 violations over 6,400
prefixes**. The correction rests on correctness, and this ADR says so rather than borrowing a
stronger-sounding justification it did not earn.

The sketch was prose in a section titled "Future CHoCH"; **no shipped production logic depended on it**, and
`fmis.structure_break` is not modified by this milestone. It is superseded here and the disagreement is
pinned by a test so the correction cannot be quietly lost.

### 2.4 Is the case reachable?

**Representable and constructible; not observed in candle-derived data at the sizes measured** — 40 seeded
fixtures × 200 bars gave 174 breaks and **0 shared bars**; the real `btcusdt_4h` fixture gives 1 break. It
requires the reference low to sit above the reference high, exactly the configuration ADR-0020 §3.9
described.

Rarity is not a reason to get it wrong. It is a reason the wrong answer would never be noticed.

---

## 3. Decision

A new sibling package **`fmis.change_of_character`** with **five public names**.

> **A change of character is a break of structure whose side differs from the side broken at the most recent
> strictly earlier break-bearing bar, when that bar broke exactly one side.**

Four conjuncts, each decided separately:

| # | Conjunct | Decision |
|---|---|---|
| 1 | subject | a `StructureBreak`, so every break conjunct already holds |
| 2 | predecessor exists | a break-bearing bar **strictly earlier** than the subject's bar |
| 3 | predecessor is determinate | that bar broke **exactly one** side |
| 4 | opposition | the subject's side **differs** from it |

### 3.1 The predecessor is chosen by bar, not by adjacency

Because "the previous element" is only well defined through the level ordering, and ADR-0019 §2.6 and
ADR-0020 §3.5 both refuse to read that ordering as time (§2.3). Selecting by bar also makes the rule
**order-invariant on its input** for free, which the adjacency formulation is not.

### 3.2 The transition table

Character is the set of sides broken at the most recent break-bearing bar. Exhaustive over 4 × 3:

| prior character | sides at this bar | emits | next character |
|---|---|---|---|
| `NONE` | `{UPPER}` / `{LOWER}` / `{UPPER, LOWER}` | — | `UPPER` / `LOWER` / `INDETERMINATE` |
| `UPPER` | `{UPPER}` | — | `UPPER` |
| `UPPER` | `{LOWER}` | **CHoCH** | `LOWER` |
| `UPPER` | `{UPPER, LOWER}` | **CHoCH** (subject = the lower break) | `INDETERMINATE` |
| `LOWER` | `{LOWER}` | — | `LOWER` |
| `LOWER` | `{UPPER}` | **CHoCH** | `UPPER` |
| `LOWER` | `{UPPER, LOWER}` | **CHoCH** (subject = the upper break) | `INDETERMINATE` |
| `INDETERMINATE` | `{UPPER}` / `{LOWER}` / `{UPPER, LOWER}` | — | `UPPER` / `LOWER` / `INDETERMINATE` |

Four consequences, each pinned by a test: the next character never depends on whether a change was emitted;
`INDETERMINATE` **suppresses without persisting**; there is **at most one change per bar**; and there is
never a change at the first break-bearing bar.

**No state type is exported.** No `CharacterState` enum, no snapshot, no history function. The table
describes a fold; exporting its state would create a third vocabulary for structural condition beside
`StructuralSequenceState` and `StructuralTrendType`.

### 3.3 A two-sided bar leaves character indeterminate

Choosing one of that bar's two breaks to be "the" prior character is the intrabar claim reintroduced one
step later. Suppression is the honest answer: a market that broke both ways in one bar has no character to
have changed *from*. It does not thereby lose the ability to have one again — the next single-sided break
bar restores a determinate character. **This is the milestone's principal limitation (E1)**, and resolving
it needs sub-bar data this repository does not ingest.

### 3.4 Character is the last break bar only

Never an accumulated run. Three consecutive upper breaks give the same character as one. Accumulation is
trend's job and `MINIMUM_DIRECTIONAL_SHIFTS` already owns that idea one package over (**E4**).

### 3.5 Ordering

Output is ordered by **`subject.index` alone**, ascending — **total and strictly increasing**, because at
most one change exists per bar. The output is built by walking sorted bar indices and is **never sorted
afterwards**: the guarantee is a property of the construction, not a step that could silently be removed. A
test asserts exactly one `sorted` call exists in the module and no `.sort` at all.

**Consequence, deliberate and load-bearing: no side ordering exists anywhere in this package.**
`fmis.structure_break`'s private `_SIDE_RANK` is neither imported nor restated, and a guard asserts no
side-ranking construct exists. The one ordering rule this layer could plausibly have duplicated is
structurally absent.

### 3.6 Duplicates, conflicts and input order

| Input | Verdict |
|---|---|
| two **equal** breaks at one `(bar, side)` | **collapsed** — duplicated facts are one fact (ADR-0020 §3.8 inherited) |
| two **distinct** breaks at one `(bar, side)` | **`ChangeOfCharacterInputError`** — the predecessor there would be ambiguous, and picking one would change every later character without saying so |
| any input order | **invariant** — the sequence is rebuilt by bar, never assumed |
| empty | `()` |

**Input ordering is not validated.** `derive_structure_breaks` owns the break ordering contract and its key
is private for exactly that reason. Order-*invariance* is strictly stronger than validation and borrows no
rule.

### 3.7 The model

```python
@dataclass(frozen=True, slots=True)
class ChangeOfCharacter:
    subject: StructureBreak     # the break that changed character
    previous: StructureBreak    # the break it changed from
    # index · timestamp · side -> projections
```

Two stored fields, both load-bearing. `previous` is stored rather than derived because it is what makes the
claim auditable from the object alone; without it, "character changed" would be an assertion whose
justification lived only in the derivation.

**Three projections only** — the three join keys every layer in this chain exposes. Everything else is one
attribute away on `subject` or `previous`. `previous_side` is deliberately absent: validation guarantees the
sides differ and there are two, so it is fully determined by `side`, and a stored copy is somewhere for one
fact to disagree with itself.

**The model validates itself**: the sides must differ, and `previous.index` must be **strictly** less than
`subject.index`. A `ChangeOfCharacter` claiming a same-side change, or a change from a break at the same bar
or a later one, **cannot be constructed**. The strict inequality is the intrabar refusal made
unrepresentable rather than merely undocumented.

**No direction enum.** `side` projects the subject break's side — ADR-0019 §D unchanged through three
layers. `UPPER` is not "bullish", and it is not "a reversal".

### 3.8 Prefix stability and context

**Exact**, in the pipeline-wide form: breaks derived from a candle prefix give exactly the full run's
changes whose index falls inside that prefix, in the same order. Proved in two steps (design §3.9): breaks
are exactly prefix-stable, and the rule at bar `i` reads only breaks at bars `≤ i`. Measured at **0
violations** across seeded fixtures, three confirmation delays, handcrafted edge cases and the real fixture.

Context follows ADR-0018 unchanged, in the **single-input** shape already established by
`contextual_structural_state_history`: envelope validated, payload delegated verbatim, identity re-wrapped
**by reference**, no identity argument anywhere, empty input retaining identity.

**`require_same_identity` is deliberately not called.** It is the rule for reconciling two or more subjects,
and there is one. A one-subject "check" would return that subject's identity while implying a guarantee that
is not happening, and a false guarantee is worse than none.

---

## 4. Public API and dependencies

`ChangeOfCharacter` · `ChangeOfCharacterError` · `ChangeOfCharacterInputError` ·
`derive_changes_of_character(breaks)` · `contextual_changes_of_character(breaks)`

```
fmis.series_context ─► fmis.level_crossing ─► fmis.structure_break ─► fmis.change_of_character
```

Imports `fmis.structure_break`, `fmis.series_context`, and `fmis.level_crossing` for the single type name
`LevelSide`. **Not `fmis.data`.** Not `fmis.market_structure`. Not the structural-trend package. Nothing
imports it. No runtime dependency added — `itertools` is standard library.

Three upstream guards were **narrowed**, each anticipated rather than discovered:

| Guard | Change |
|---|---|
| `fmis.structure_break`'s "nothing imports this package" | now names `change_of_character` as its single permitted consumer, plus a new private-internals guard on it |
| `fmis.level_crossing`'s permitted-consumer list | gains `change_of_character`, plus a new guard asserting `LevelSide` is the **only** name it takes |
| `fmis.series_context`'s permitted-consumer list | gains `change_of_character` |

Every exemption is **named, not pattern-matched**, so a further consumer fails the test and must justify
itself in an ADR. The direction each guard protects — nothing below imports upward — is unchanged, and no
guard was weakened.

### 4.1 Exact exception messages (a shipped contract, asserted with `==`)

| Message |
|---|
| `previous break is on the same side (upper); character did not change` |
| `previous break index (12) does not precede the subject's (12); two breaks at one bar carry no order in time` |
| `subject must be a StructureBreak, got str` · `previous must be a StructureBreak, got int` |
| `breaks must be a sequence of StructureBreak, got str` |
| `breaks[1] must be a StructureBreak, got str` |
| `breaks[1] shares bar index 4 and side upper with a different break; the previous break at that bar would be ambiguous` |
| `breaks must be a ContextualSeries, got tuple` |

No existing message was changed.

---

## 5. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **ADR-0020 §7's `zip` adjacency sketch** | infers a change from an ordering the layer below refuses to read as temporal; differs on a constructible case (§2.3). **Superseded** |
| element adjacency with same-bar pairs skipped | closes the intrabar claim but loses a genuine change: `upper@4 · upper@12 · lower@12` would yield nothing |
| picking one side of a two-sided prior bar | the intrabar claim, reintroduced one step later |
| `INDETERMINATE` persisting until a reset | invents a lifecycle nothing in the inputs supports |
| skipping back past a two-sided bar | claims that bar did not change character — an interpretation, and it reads arbitrarily far back |
| CHoCH re-deriving from levels and crossings | duplicates BOS wholesale and gives the reference rule a second implementation |
| CHoCH consulting trend | trend is a *summary of* BOS and CHoCH and defines neither (review §15) |
| CHoCH reading candles | the mission; and confirmation was decided one and two layers down |
| a `CharacterState` enum or history function | a third vocabulary for structural condition; the fold's state is an implementation detail |
| `bullish` / `bearish` / `direction` field | `side` carries the sense — ADR-0019 §D |
| `previous_side` stored | fully determined by `side`; a second place for one fact to disagree |
| `bars_since` / `duration` | arithmetic a consumer already has, and naming it invites a threshold |
| `confirmed` / `strength` / `confidence` | interpretation; no such notion exists in this repository |
| an `invalidated` flag or "failed CHoCH" | a later reading over the change sequence; ADR-0020 §3.7 inherited |
| a configurable minimum break count or spacing | makes historical results non-reproducible without the setting (ADR-0019 §2.2) |
| a `confirmation_bars` argument, for symmetry | cannot change the answer, so it can only be passed wrongly |
| validating the input break ordering | a second implementation of a rule `fmis.structure_break` owns |
| requiring sorted input for `O(n)` | buys a constant factor and costs order-invariance |
| resolving a conflicting break pair by picking one | changes every later character without saying so |
| rejecting duplicated equal breaks | duplicated facts are one fact |
| ordering by `(index, side)` like BOS | the side column is constant, and importing a side rank would create the one duplication this package can otherwise avoid entirely |
| ordering by timestamp | equal for two facts at one bar; index is exact |
| `require_same_identity(breaks)` in the wrapper | a one-subject check that checks nothing while implying it does |
| editing `fmis.structure_break`'s docstring sketch | production source, and the sketch is prose in a "future" section, not logic. Superseded here and pinned by a test instead |

---

## 6. Consequences

**Gained.** A non-repainting, exactly prefix-stable change-of-character primitive that adds no primitive,
takes no configuration, duplicates no rule, and reads no candle, level or crossing. The predecessor is
carried on the result, so every claim is auditable from the object alone. The deterministic chain
`CandleSeries → Swings → … → BOS → CHoCH` is now complete.

**Costs, accepted deliberately.**

- **A two-sided break bar leaves character indeterminate** (E1), so no change is claimed at the next break
  bar. The alternative is an intrabar claim.
- **No lifecycle** (E2) — a consumer wanting "failed CHoCH" builds it over the sequence.
- **No trend interaction** (E3) — reconciling CHoCH with `StructuralTrendType` belongs *above* both, in a
  later milestone.
- **Character is the last break bar only** (E4), not an accumulated run.

**Limitations.**

| | Question | Status |
|---|---|---|
| **E1** | two-sided break bar leaves character indeterminate | principal limitation; needs sub-bar data |
| **E2** | no invalidation, no "failed CHoCH" | deliberate — a later reading |
| **E3** | no trend interaction | deliberate — trend is a summary of both, and reconciliation sits above |
| **E4** | character is the last break bar, not an accumulated run | deliberate — that is trend's idea |
| **E5** | ADR-0020 D1 (confirmation delay on no derived fact) | inherited, **not made worse** — no argument to mismatch |
| **E6** | ADR-0019 D2 (first swing of each type has no level) | inherited, unchanged |
| **E7** | exact float comparison (ADR-0013 §4) | inherited through the break; CHoCH compares **no prices at all** |
| **E8** | no minimum spacing between changes | deliberate — a threshold would be unreproducible without its setting |

**Still deliberately absent:** trend reconciliation, regime, bias, protected levels, inducement, liquidity
sweeps, support, resistance, signals, entries, exits, stops, targets, sizing, confidence, AI interpretation,
persistence and multi-timeframe aggregation.

---

## 7. What sits above this

The deterministic structural chain is complete. The next reading — reconciling `StructuralTrendType` with
the BOS and CHoCH sequences — sits **above both** and defines neither, which is the market-structure
architecture review §15 ordering satisfied end to end:

> **BOS is defined purely on levels, CHoCH over the BOS sequence, and trend is a summary of both, defining
> neither.**

A test in this milestone pins the last clause from the CHoCH side: `fmis.structural_trend` imports neither
`fmis.structure_break` nor `fmis.change_of_character`, and cannot.

---

## 8. Validation

3221 tests pass (3033 baseline + 184 new + 4 from narrowed guards), identically with `-W error`.
**59/59 mutation probes detected, 0 no-ops, 0 survivors, all sources restored byte-for-byte with SHA-256
verification.** 136 public exports, 0 collisions. `pyproject.toml` and `uv.lock` unchanged; `itertools` is
standard library, so no runtime dependency was added.

Two probes survived the first mutation round and both were **test-suite gaps, not equivalent mutants**:
overwriting an earlier equal break with a later one (the suite compared duplicates with `==`, never `is`),
and emptying a submodule's `__all__` (nothing asserted a submodule's public surface). Both were closed by
new tests and the contract they pin is now stated in the source.

**Performance.** Growth is measured, not argued: doubling the break count doubles the time at every size
from 500 to 100,000 — 20,000 breaks in **0.0113 s**, 100,000 in **0.103 s**, and a realistic 5,000-candle
chain (110 breaks) in **91 µs**. The adversarial case where *every* bar is two-sided — maximum grouping
work, zero output — derives 20,000 breaks in 0.0028 s. The `O(n log n)` bound is real but the log factor is
invisible at every size measured. No optimisation is recommended; there is nothing to optimise.

The independent review
([`docs/reviews/CHOCH_FOUNDATION_V1_REVIEW.md`](../reviews/CHOCH_FOUNDATION_V1_REVIEW.md)) found **no P0 and
no P1**.
