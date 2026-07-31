# Change of Character (CHoCH) Foundation v1 — Design

**Status:** accepted — implemented by ADR-0021
**Baseline:** `5aac1a3f652ea44e4523e2609e140c18a0b9f121` — *Merge Break of Structure Foundation v1 Review*
**Baseline metrics (re-derived, not trusted):** 3033 tests, 3033 with `-W error`, `structure_break` 175,
`level_crossing` 247, `series_context` 185, `structural_trend` 353, 131 public exports, 0 collisions,
`pyproject.toml` and `uv.lock` untouched since the previous milestone.

---

## 1. Scope

Build **only** the deterministic Change of Character layer that consumes the existing break-of-structure
sequence.

Not trend. Not regime. Not bias. Not entries, exits, protected levels, inducement, liquidity or confidence.

**CHoCH must never inspect a candle, a level, or a crossing.** This design achieves that structurally
rather than by discipline: `fmis.change_of_character` does not import `fmis.data` at all, so `Candle` is not
a name it can reach; and its only use of `fmis.level_crossing` is the **type name `LevelSide`**, pinned by
an AST guard that permits that single name and nothing else.

---

## 2. Targeted audit

Only `fmis.structure_break`, `fmis.series_context`, ADR-0019 and ADR-0020 were re-derived. Nothing was
assumed from the previous milestone's prose; every claim below was re-checked against the shipped source
or measured by prototype.

### 2.1 What exists

| Fact | Stored fields | Projections |
|---|---|---|
| `StructureBreak` | `crossing`, `eligible_from` | `index`, `timestamp`, `level`, `side`, `origin`, `label` |
| `LevelSide` | `UPPER`, `LOWER` | — |
| `derive_structure_breaks(levels, crossings, *, confirmation_bars)` | → `tuple[StructureBreak, ...]` ordered by `(index, side rank)` | — |
| `contextual_structure_breaks(...)` | → `ContextualSeries[StructureBreak]` | — |

Re-derived by inspecting `dataclasses.fields(StructureBreak)` and its property set directly, not by reading
ADR-0020: fields are exactly `{crossing, eligible_from}`, properties exactly
`{index, label, level, origin, side, timestamp}`.

### 2.2 Question 1 — does BOS already contain every primitive CHoCH requires?

**Yes. No primitive is missing, and none is invented here.**

| CHoCH needs | Supplied by | Verified |
|---|---|---|
| which way a break went | `StructureBreak.side` (`LevelSide`) | property, re-derived |
| when it happened, as a join key | `StructureBreak.index` | property, re-derived |
| when it happened, as a time | `StructureBreak.timestamp` | property, re-derived |
| the full audit trail of each break | `StructureBreak.crossing`, `.level`, `.origin`, `.label`, `.eligible_from` | fields + properties |
| a deterministic total order over breaks | `derive_structure_breaks` returns `(index, side)`-ordered | ADR-0020 §3.7, re-measured |
| identity | `ContextualSeries.identity` | ADR-0018 |

This is the **first milestone in the chain that adds no primitive and requests none.** That is the
strongest available evidence that the layering below it is correct: BOS was designed to be consumed
this way, and it is.

**What is still missing repository-wide, and is *not* needed here.** ADR-0020 D1 — the confirmation delay
is recorded on no derived fact — remains open. CHoCH does not need it: eligibility was decided one layer
down and is already baked into which breaks exist. `derive_changes_of_character` therefore takes **no
`confirmation_bars` argument and no configuration of any kind**, and consequently cannot be misconfigured.

### 2.3 Question 2 — is ADR-0020 §7's CHoCH sketch correct?

**No. It is correct for every sequence in which no two breaks share a bar, and wrong in exactly one
representable case.** This is the audit's principal finding, and it is the reason this milestone is not a
four-line function.

ADR-0020 §7 and the `fmis.structure_break` package docstring both sketch:

```python
tuple(b for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)
```

ADR-0020 §3.5 simultaneously states that two breaks may share a bar — one `UPPER`, one `LOWER` — and that
**their order is the level ordering, not a claim about which happened first**, because OHLC data cannot
prove an intrabar path.

The two statements are incompatible. Applied to a same-bar pair, the sketch's adjacent pair `(a, b)` *is*
that pair, so it reports a change of character **derived entirely from an ordering that the layer below
explicitly refuses to interpret as temporal**. Measured directly:

```
breaks: upper@4 · upper@12 · lower@12          (bar 12 closes above the upper reference
                                                and below the lower reference)
sketch          -> (upper@12 -> lower@12)   ← the predecessor is the SAME BAR
shipped rule    -> (upper@4  -> lower@12)   ← the predecessor is a strictly earlier bar
```

Both agree that **bar 12 is a change-of-character bar**. They disagree about *what changed from*, and only
one of them can answer without fabricating an intrabar path.

The sketch is therefore **superseded, not implemented**. It was a sketch in prose, in a section titled
"Future CHoCH"; no shipped production logic depends on it, and `fmis.structure_break` is not modified by
this milestone. A test in this milestone's suite pins the disagreement so the correction cannot be quietly
lost.

### 2.4 Question 3 — is the same-bar case reachable, or theoretical?

**Representable and constructible; not observed in candle-derived data at the sizes measured.**

- 40 seeded fixtures × 200 bars: **174 breaks, 0 shared bars.**
- The real `btcusdt_4h` fixture: 1 break.
- Constructed directly from levels and crossings: reachable, and shipped as a fixture. It requires the
  reference low to sit **above** the reference high — exactly the configuration ADR-0020 §3.9 described.

Rarity is not a reason to get it wrong. It is a reason the wrong answer would never be noticed, which is
the failure mode this repository treats as the most serious.

### 2.5 Question 4 — does prefix stability distinguish the two rules?

**No, and saying so is more useful than claiming it does.** Measured over 40 seeded fixtures × every
prefix — **6,400 prefixes** — both the sketch and the shipped rule record **0 violations**.

The choice between them rests entirely on §2.3: whether a change of character may be inferred from an
ordering the layer below refuses to call temporal. It rests on **correctness, not stability**, and the
design says so rather than borrowing a stronger-sounding justification it did not earn.

---

## 3. Design decisions

### 3.1 What is a change of character?

> **A change of character is a break of structure whose side differs from the side broken at the most
> recent strictly earlier break-bearing bar, when that bar broke exactly one side.**

Four conjuncts, each independently decided below, each testable, none interpretive:

1. the subject is a `StructureBreak` (so every BOS conjunct already holds of it);
2. a **prior break-bearing bar** exists, strictly earlier than the subject's bar;
3. that bar broke **exactly one** side — the prior character is determinate;
4. the subject's side **differs** from that side.

The predecessor is stored on the result, so the claim is auditable from the object alone.

### 3.2 Why "the most recent strictly earlier bar" and not "the previous element"

Because "the previous element" is only well defined through the level ordering, and ADR-0019 §2.6 and
ADR-0020 §3.5 both refuse to read that ordering as time. Selecting the predecessor **by bar** rather than
by position in a tuple is what makes the rule independent of a convention its own inputs disclaim.

It also makes the rule **order-invariant on its input** for free (§3.7), which the element-adjacency
formulation is not.

### 3.3 The character state, as a transition table

Let *character* be the set of sides broken at the most recent break-bearing bar. It takes four values, one
of which — `INDETERMINATE` — exists precisely because a bar can break both sides.

| prior character | sides broken at this bar | emits | next character |
|---|---|---|---|
| `NONE` (no earlier break bar) | `{UPPER}` | — | `UPPER` |
| `NONE` | `{LOWER}` | — | `LOWER` |
| `NONE` | `{UPPER, LOWER}` | — | `INDETERMINATE` |
| `UPPER` | `{UPPER}` | — | `UPPER` |
| `UPPER` | `{LOWER}` | **CHoCH** (`previous` = the upper break) | `LOWER` |
| `UPPER` | `{UPPER, LOWER}` | **CHoCH** (subject = the lower break) | `INDETERMINATE` |
| `LOWER` | `{LOWER}` | — | `LOWER` |
| `LOWER` | `{UPPER}` | **CHoCH** (`previous` = the lower break) | `UPPER` |
| `LOWER` | `{UPPER, LOWER}` | **CHoCH** (subject = the upper break) | `INDETERMINATE` |
| `INDETERMINATE` | `{UPPER}` | — | `UPPER` |
| `INDETERMINATE` | `{LOWER}` | — | `LOWER` |
| `INDETERMINATE` | `{UPPER, LOWER}` | — | `INDETERMINATE` |

Twelve rows, exhaustive over 4 × 3. Four properties fall out of it and are each pinned by a test:

- **The next character never depends on whether a CHoCH was emitted.** It is a function of the current
  bar's side set alone. The rule is a fold with no feedback.
- **`INDETERMINATE` suppresses, it does not persist.** The very next single-sided break bar restores a
  determinate character. A market that broke both ways in one bar has no character to have changed *from*;
  it does not thereby lose the ability to have one again.
- **At most one CHoCH per bar.** Both breaks at a two-sided bar are tested against the *same* prior side,
  and they are each other's opposite, so at most one can differ from it.
- **No CHoCH at the first break-bearing bar, ever.** There is nothing for character to have changed from.

**This state is not stored anywhere and no state type is exported.** There is no `CharacterState` enum, no
snapshot type, and no history function. The table describes the fold; the output is the CHoCH sequence.
Exporting the state would create a second vocabulary for structural condition alongside
`StructuralSequenceState` and `StructuralTrendType`, which is the duplication this milestone must not add.

### 3.4 Is a CHoCH itself a break?

**Yes, and it is not re-derived.** `ChangeOfCharacter.subject` **is** the `StructureBreak` object supplied,
by reference — not an equal copy, not a reconstruction, and not a re-derivation from levels and crossings.
Every fact about the break is reached through it. There is no duplicated field.

Consequently a CHoCH inherits, without restating any of them: only a close breaks structure; the reference
is the most recent eligible level; eligibility begins at the confirmation bar; structure breaks once;
nothing is invalidated; the label decides nothing.

### 3.5 What the model stores, and what it refuses to store

```python
@dataclass(frozen=True, slots=True)
class ChangeOfCharacter:
    subject: StructureBreak    # the break that changed character
    previous: StructureBreak   # the break it changed from — a strictly earlier bar, opposite side
```

**Exactly two stored fields**, and both are needed: `subject` is the fact, and `previous` is what makes the
claim checkable from the object alone. Without `previous`, "character changed" would be an assertion whose
justification lived only in the derivation that produced it.

**Three projections only** — `index`, `timestamp`, `side` — the three join keys every layer in this chain
exposes (`SwingPoint`, `LevelCrossingEvent`, `StructureBreak`). Everything else is reached through
`.subject.` or `.previous.`, which is one attribute away and cannot drift.

Deliberately absent, each for a stated reason:

| Absent | Why |
|---|---|
| `previous_side` | fully determined by `side` — validation guarantees they are opposite, and there are two sides. A stored copy is somewhere for one fact to disagree with itself (ADR-0016 §4). |
| `direction`, `bullish`, `bearish` | `side` already carries the only sense this layer knows. ADR-0019 §D, unchanged. `UPPER` is not bullish. |
| `bars_since`, `duration` | arithmetic over two indices a consumer already has, and naming it invites a threshold. |
| `confirmed`, `strength`, `confidence`, `valid` | interpretation. There is no confidence in this repository and this layer does not introduce one. |
| `invalidated`, `failed` | a CHoCH is a fact about closed bars; ADR-0020 §3.7's refusal, inherited. |
| `trend`, `regime`, `bias` | trend is a **summary of** BOS and CHoCH and defines neither — market-structure review §15, load-bearing here. |
| any character-state enum | §3.3. |

**The model validates itself.** `previous.side is not subject.side`, and `previous.index < subject.index`
strictly. A `ChangeOfCharacter` claiming a same-side change, or a change from a break at the same bar or a
later one, **cannot be constructed**. That is `SwingComparison`'s and `StructureBreak`'s rule applied here.

### 3.6 What the derivation rejects, and what it collapses

Reject, never repair — ADR-0005's rule, inherited through three layers:

| Input | Verdict | Why |
|---|---|---|
| not a sequence, or a `str`/`bytes` | `TypeError` | as every layer below |
| an element that is not a `StructureBreak` | `TypeError` | a hand-built element cannot be trusted to satisfy the BOS conjuncts |
| two **distinct** breaks at one `(index, side)` | `ChangeOfCharacterInputError` | the predecessor at that bar would be ambiguous, exactly as ADR-0020 §3.4 rejects two levels sharing an origin index. `derive_structure_breaks` cannot produce it; a hand-built run can |
| two **equal** breaks at one `(index, side)` | **collapsed** | duplicated facts are one fact. ADR-0020 §3.8's duplicate-crossing invariance, inherited deliberately |
| empty | `()` | "character did not change" is a true answer to a well-formed question |

Note the pairing in rows three and four: duplicates collapse **only** when they are equal. A conflicting
pair is never resolved by picking one, because picking would change every later character without saying so.

**Input ordering is not validated.** `derive_structure_breaks` owns the break ordering contract and its key
is private for exactly that reason (ADR-0020 §3.7). Re-validating it here would be the second implementation
this repository keeps refusing to create. Instead the derivation is **invariant** to input order, which is
strictly stronger than validating it and requires no borrowed rule.

### 3.7 Ordering guarantees

Output is ordered by **`subject.index` alone**, ascending.

That key is **total and strictly increasing**, because at most one CHoCH exists per bar (§3.3). This is a
genuine simplification over the layer below, not an omission: BOS needs `(index, side rank)` because two
breaks can share a bar; CHoCH cannot have two at one bar, so the side rank would be a constant column.

**Consequence, and it is the point:** `fmis.change_of_character` needs **no side ordering at all**. It does
not restate `_SIDE_RANK`, does not import it, and does not define an equivalent. The one ordering rule it
could plausibly have duplicated is structurally absent, and a guard test asserts no side-ranking construct
exists anywhere in the package.

Ordering is by index rather than timestamp for the reason ADR-0019 fixed: index is the sequence position
and is exact; timestamps are equal for two facts at one bar. A test asserts the two orders agree.

### 3.8 Invariants

Each is pinned by at least one test, and each is a property of the output, not of the implementation.

| # | Invariant |
|---|---|
| I1 | every `ChangeOfCharacter.subject` is an object present in the input, by identity |
| I2 | every `previous` is an object present in the input, by identity |
| I3 | `previous.side is not subject.side` |
| I4 | `previous.index < subject.index` — strictly |
| I5 | `previous` is the break at the greatest bar index strictly below `subject.index` that carries any break |
| I6 | that bar carries exactly one break |
| I7 | output indices are strictly increasing — at most one CHoCH per bar |
| I8 | output is a `tuple`, immutable, possibly empty |
| I9 | the result is a pure function of the input as a **multiset of breaks** — permutation-invariant |
| I10 | duplicated equal breaks change nothing |
| I11 | no CHoCH is emitted at the earliest break-bearing bar |
| I12 | for every emitted CHoCH, no bar strictly between `previous.index` and `subject.index` carries a break |

### 3.9 Prefix stability proof

**Contract.** For a candle prefix `P` of series `S`, with swings, levels, crossings and breaks each derived
from `P`:

```
choch(breaks(P)) == tuple(c for c in choch(breaks(S)) if c.subject.index < len(P.closed().candles))
```

**Proof.** In two steps, neither of which is asserted.

*Step 1 — breaks are exactly prefix-stable.* ADR-0020 §3.9, re-measured in this milestone at 0 violations
over 6,400 prefixes. So `breaks(P) = {b ∈ breaks(S) : b.index < |P|}`, order preserved.

*Step 2 — the rule at bar `i` reads only breaks at bars `≤ i`.* Directly from §3.1: the subject is at bar
`i`; the predecessor bar is the greatest break-bearing bar `< i`; the side set at that bar is read; nothing
else is consulted. There is no lookahead, no windowing, no aggregate over the whole run, and no dependence
on the count of breaks. Formally, the fold's state after bar `i` is a function of `{b ∈ breaks : b.index ≤ i}`,
and emission at bar `i` is a function of that state and bar `i`'s side set.

*Combining.* Truncating `S` to `P` removes exactly the breaks at bars `≥ |P|`, and by step 2 no decision at
a bar `< |P|` reads any of them. Every emission and every suppression at bars `< |P|` is therefore
unchanged, and no new one can appear. ∎

**Corollary — non-repainting.** A CHoCH reported for a closed bar is never withdrawn, never re-attributed to
a different predecessor, and never re-dated by any later candle. The corollary is what the property is
*for*; stability is how it is measured.

**Measured:** 0 violations across 40 seeded fixtures × every prefix (6,400 prefixes), three confirmation
delays, handcrafted edge cases, and the real fixture.

### 3.10 Replay determinism

Pure function. No state, no cache, no clock, no randomness, no environment, no global registry, no
mutable module-level object, no memoisation — each pinned by an AST guard copied from the BOS suite.

The result depends on the input **multiset** only. Repeated derivation is identical; a permuted input is
identical; a duplicated input is identical; a rebuilt-but-equal input gives an equal result. Object identity
of `subject` and `previous` is preserved from the input, so a replay that supplies the same objects returns
results holding those same objects.

### 3.11 Context propagation

One input, so — unlike BOS — there is nothing to reconcile:

```python
def contextual_changes_of_character(breaks): ...
```

The wrapper validates the envelope type, delegates the payload verbatim, and re-wraps under the input's
**own identity object, by reference**. It takes no identity argument, so substitution is unrepresentable
rather than merely discouraged. Empty input retains a full identity.

`require_same_identity` is deliberately **not** called: it is the rule for reconciling *two or more*
subjects, and there is one. Calling it with a single subject would return that subject's identity while
implying a check that is not happening. The single-input shape already established by
`contextual_structural_state_history` and `contextual_structural_trend_history` is followed exactly.

### 3.12 Computational complexity

Let `n` be the number of breaks and `k ≤ n` the number of distinct break-bearing bars.

| Stage | Time | Space |
|---|---|---|
| validate elements, group by bar, collapse/reject duplicates | `O(n)` expected (dict) | `O(n)` |
| sort the distinct bar indices | `O(k log k)` | `O(k)` |
| single scan over sorted bars, emitting at most one CHoCH each | `O(k)` | `O(k)` output worst case |
| **total** | **`O(n log n)`** worst case, `O(n)` when `k` is small | **`O(n)`** |

`O(n log n)` is the price of §3.6's order-invariance: a sort is required precisely because the input order
is not trusted. Requiring sorted input would give `O(n)` and would mean importing an ordering rule
`fmis.structure_break` owns — the trade is deliberate, and at realistic sizes it is not close (§6, probe 12:
385 breaks in 0.084 ms).

No quadratic path exists. There is no nested scan, no repeated search, and no per-crossing lookup — the
defect class the BOS review found and fixed one layer down cannot occur here, and a scaling test pins the
growth as sub-quadratic.

**Allocations:** one dict of bars, one list of sorted keys, one output list, one output tuple. No
intermediate copy of the input, no per-element tuple, no comprehension over the full input inside the scan.
`itertools.pairwise` is used over the sorted bar list rather than a `[1:]` slice, so no second copy of the
key list is made.

**Measured** (alternating breaks, best of 3–5 runs):

| breaks | seconds | µs/break | ratio for ×2 input |
|---:|---:|---:|---:|
| 500 | 0.00025 | 0.50 | — |
| 1,000 | 0.00053 | 0.53 | ×2.10 |
| 2,000 | 0.00102 | 0.51 | ×1.93 |
| 10,000 | 0.00566 | 0.57 | ×2.07 |
| 20,000 | 0.01129 | 0.57 | ×2.00 |
| 100,000 | 0.10324 | 1.03 | ×2.01 |

Doubling the input doubles the time at every size. The `O(n log n)` bound is real but the log factor is
invisible in this range. A realistic 5,000-candle chain (110 breaks, 53 changes) derives in **91 µs**, and
the adversarial maximum-grouping case — 20,000 breaks on 10,000 two-sided bars, zero output — in
**0.0028 s**. **No optimisation is recommended**; recommending one would be optimising a cost that does not
exist.

### 3.13 Package ownership and dependency graph

New sibling package **`fmis.change_of_character`**, owning three modules and nothing else:

| Module | Owns |
|---|---|
| `models.py` | `ChangeOfCharacter`, the two errors, and the model's self-validation |
| `changes.py` | `derive_changes_of_character` — grouping, duplicate policy, the fold, the ordering |
| `pipeline.py` | `contextual_changes_of_character` — the identity boundary, and nothing analytical |

```
fmis.data ─► fmis.market_structure ─► fmis.structural_trend
   │               │                          │
   └───────────────┴──────────────────────────┴─► fmis.series_context
                                                      │
                                                      ▼
                                              fmis.level_crossing
                                                      │
                                                      ▼
                                              fmis.structure_break
                                                      │
                                                      ▼
                                          fmis.change_of_character     ← this milestone
```

Imports **`fmis.structure_break`**, **`fmis.series_context`**, and **`fmis.level_crossing` for the single
type name `LevelSide`**. Notably **not `fmis.data`** — a candle is not a name this package can reach — and
not `fmis.market_structure`, not `fmis.structural_trend`. Nothing imports it. No runtime dependency is
added; the package uses no third-party import and no standard-library import beyond `dataclasses`,
`datetime`, `collections.abc`, `itertools` and `__future__`.

**The `LevelSide` import is a type name, not logic**, and is guarded to stay that way: an AST test asserts
that `LevelSide` is the *only* name imported from `fmis.level_crossing` anywhere in the package, so
`CrossingKind`, `CrossingMechanism`, `PriceLevel`, `LevelCrossingEvent`, `structural_levels` and
`derive_level_crossings` are all unreachable by name. The alternative — an unannotated public property — was
rejected: this repository annotates every public return type, and dropping one to keep an import list
shorter trades a real guarantee for a cosmetic one.

Two upstream guards are **narrowed**, both anticipated rather than discovered:

- `fmis.structure_break`'s "nothing imports this package" guard now names `change_of_character` as its
  single permitted consumer — the widening ADR-0020 §7 explicitly designed for.
- `fmis.level_crossing`'s and `fmis.series_context`'s permitted-consumer lists gain the same name.

Every exemption is **named, not pattern-matched**, so a second consumer fails the test and must justify
itself in an ADR. The direction each guard protects — nothing below imports upward — is unchanged, and each
guard's private-submodule clause is unchanged.

### 3.14 Worked example

```
ContextualSeries[StructureBreak]
        │
        ▼  contextual_changes_of_character(breaks)
ContextualSeries[ChangeOfCharacter]
```

Full chain, with the two candle-reading stages marked:

```
CandleSeries ─►(candles) contextual_structural_swings ─► ContextualSeries[StructuralSwing]
                              └─► contextual_structural_levels ─► ContextualSeries[PriceLevel] ─┐
CandleSeries ─►(candles) contextual_level_crossings(series, levels) ────────────────────────────┤
                                                                                                ▼
                        contextual_structure_breaks(levels, crossings, confirmation_bars=R)
                                                                                                │
                                                                                                ▼
                        contextual_changes_of_character(breaks) ─► ContextualSeries[ChangeOfCharacter]
```

After the crossing stage no candle is read again — and after the break stage, no level and no crossing.

---

## 4. Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| **ADR-0020 §7's `zip(breaks, breaks[1:])` sketch** | infers a change of character from an ordering that ADR-0019 §2.6 and ADR-0020 §3.5 both refuse to read as temporal; measured to differ on a constructible case (§2.3). **Superseded here.** |
| **element adjacency, with same-bar pairs skipped** | closes the intrabar claim but loses a genuine change: with breaks `upper@4 · upper@12 · lower@12`, skipping the same-bar pair yields nothing, though `lower@12` plainly opposes `upper@4` across nine bars |
| **emitting a CHoCH at a two-sided prior bar by picking one side** | picking is exactly the intrabar claim, reintroduced one step later |
| **treating `INDETERMINATE` as sticky until a "reset"** | invents a lifecycle; nothing in the inputs says a two-sided bar poisons later structure |
| **skipping back past a two-sided bar to the last single-sided one** | claims the two-sided bar did not change character — an interpretation, and it makes the rule read arbitrarily far back |
| **CHoCH re-deriving from levels and crossings** | duplicates BOS wholesale, reintroduces the crossing dependency BOS exists to remove, and gives the reference rule a second implementation |
| **CHoCH consulting trend** | trend is a *summary of* BOS and CHoCH and defines neither (market-structure review §15). Any definition with trend as an input to CHoCH is rejected on sight |
| **CHoCH reading candles for confirmation** | the mission; and confirmation was already decided one and two layers down |
| **a `CharacterState` enum or a character history function** | a third vocabulary for structural condition beside `StructuralSequenceState` and `StructuralTrendType`; the fold's state is an implementation detail |
| **a `bullish`/`bearish`/`direction` field** | `side` carries the sense; ADR-0019 §D unchanged |
| **`previous_side` as a stored field** | fully determined by `side`; a second place for one fact to disagree |
| **a `bars_since` / `duration` field** | arithmetic a consumer already has, and naming it invites a threshold this layer must not own |
| **`confirmed` / `strength` / `confidence`** | interpretation; no such notion exists in this repository |
| **an `invalidated` flag or "failed CHoCH"** | a later reading over the CHoCH sequence; ADR-0020 §3.7 inherited |
| **a configurable minimum number of breaks before a CHoCH may be claimed** | makes historical results non-reproducible without the setting — ADR-0019 §2.2's rule; and a consumer can filter the sequence itself |
| **a `confirmation_bars` argument, for symmetry with BOS** | CHoCH consumes breaks, in which eligibility is already resolved. An argument that cannot change the answer is an argument that can be passed wrongly |
| **validating the input break ordering** | a second implementation of a rule `fmis.structure_break` owns; order-invariance is stronger and borrows nothing |
| **requiring sorted input for `O(n)`** | buys a constant factor at realistic sizes and costs the order-invariance above (§3.12) |
| **resolving two conflicting breaks at one `(index, side)` by picking one** | changes every later character without saying so — the hardest failure mode to notice |
| **rejecting duplicated equal breaks instead of collapsing** | duplicated facts are one fact; ADR-0020 §3.8 inherited, and rejecting would make the layer order- and multiplicity-sensitive |
| **ordering output by `(index, side)` like BOS** | the side column is constant — at most one CHoCH per bar — and importing a side rank would create the one duplication this package can otherwise avoid entirely |
| **ordering by timestamp** | equal for two facts at one bar; index is the exact sequence position (ADR-0019) |
| **`require_same_identity(breaks)` in the wrapper** | a one-subject "check" that checks nothing while implying it does |
| **modifying `fmis.structure_break`'s docstring sketch** | production source, and the sketch is prose in a "future" section, not logic. Superseded in ADR-0021 and pinned by a test instead |

---

## 5. Public API

```python
@dataclass(frozen=True, slots=True)
class ChangeOfCharacter:
    subject: StructureBreak
    previous: StructureBreak
    # index, timestamp, side -> projections, not stored fields
```

| Name | Kind |
|---|---|
| `ChangeOfCharacter` | model |
| `ChangeOfCharacterError` | error base |
| `ChangeOfCharacterInputError` | `(ChangeOfCharacterError, ValueError)` |
| `derive_changes_of_character(breaks)` | context-free primitive |
| `contextual_changes_of_character(breaks)` | safe pipeline API |

**Five public names**, matching the shape of every foundation milestone since ADR-0018. No constant is
exported, no enum is added, and no existing public name changes.

---

## 6. Experiment results — 17/17 PASS

Prototyped outside production against the real repository types; scratch files deleted before committing.

| # | Demonstration | Result |
|---|---|---|
| 1 | `StructureBreak` exposes `index` and `side` — **no primitive missing** | **PASS** — fields `{crossing, eligible_from}`, properties `{index, label, level, origin, side, timestamp}` |
| 2 | CHoCH derivable from the break sequence alone, no candle/level/crossing | **PASS** — 9 breaks → 4 changes |
| 3 | two breaks can share one bar | **PASS** — `upper` and `lower` at bar 12 |
| 3b | **ADR-0020 §7's sketch claims an intrabar order** | **PASS (finding)** — sketch pairs `upper@12 → lower@12` |
| 3c | the shipped rule makes no intrabar claim | **PASS** — pairs `upper@4 → lower@12` |
| 4 | frequency of same-bar breaks in candle-derived data | **PASS** — 0 shared bars over 174 breaks, 40 fixtures |
| 5 | prefix stability, shipped rule | **PASS** — **0 violations / 6,400 prefixes** |
| 5b | prefix stability, sketch rule | **PASS** — 0 violations; **stability does not distinguish them** (§2.5) |
| 6 | invariant to input order | **PASS** — 10 random shuffles |
| 6b | invariant to duplicated breaks | **PASS** |
| 6c | replay determinism | **PASS** |
| 7 | a two-sided prior bar suppresses the claim | **PASS** — no CHoCH at bar 20 after a two-sided bar 12 |
| 8 | alternating and repeated BOS both exercised | **PASS** — 6 breaks, 4 changes |
| 9 | real `btcusdt_4h` fixture | **PASS** — 1 break, 0 changes |
| 10 | at most one CHoCH per bar | **PASS** — 20 fixtures |
| 11 | empty input | **PASS** — `()` |
| 12 | benchmark | **PASS** — 385 breaks in **0.084 ms** |

Named fixtures carried into the test suite: the intrabar-claim counterexample (3/3b/3c); the two-sided
prior bar (7); the real fixture (9).

---

## 7. Limitations and deferred questions

| | Question | Status |
|---|---|---|
| **E1** | **A two-sided break bar leaves character indeterminate**, so a change of character cannot be claimed at the next break bar. Deliberate — the alternative is an intrabar claim. Rare (0 occurrences in 40 candle-derived fixtures) but representable. | **The milestone's principal limitation.** Resolving it needs sub-bar data, which this repository does not ingest. |
| **E2** | **No lifecycle.** No invalidation, no "failed CHoCH", no re-arming. | Deliberate — a later reading over the CHoCH sequence. |
| **E3** | **No trend interaction.** CHoCH is not compared against, filtered by, or reconciled with `StructuralTrendType`. | Deliberate — review §15's ordering: trend is a summary of both, defining neither. That reconciliation is a **later milestone's** job, and it belongs above both. |
| **E4** | Character is defined by the **most recent break bar only**, not by an accumulated run. Three consecutive upper breaks give the same character as one. | Deliberate — accumulation is trend's job, and `MINIMUM_DIRECTIONAL_SHIFTS` already owns that idea one package over. |
| **E5** | ADR-0020 **D1** (the confirmation delay is on no derived fact) is inherited. CHoCH does not need it and takes no such argument, so it cannot be misconfigured here. | Inherited, unchanged, and **not made worse**. |
| **E6** | ADR-0019 **D2** (the first swing of each type has no level) is inherited, so the earliest breaks — and therefore the earliest possible change — are missing. | Inherited, unchanged. |
| **E7** | Exact float comparison (ADR-0013 §4) is inherited through the break. CHoCH itself compares **no prices at all** — only sides and indices — so it introduces no new float sensitivity. | Inherited; strictly reduced. |
| **E8** | CHoCH is emitted per bar with no minimum spacing. Two breaks one bar apart on opposite sides produce a change. | Deliberate — spacing is a consumer policy, and a threshold here would be unreproducible without its setting. |

**No P0 or P1 design question remains unresolved.**
