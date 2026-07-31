# Break of Structure Foundation v1 — Design

**Status:** accepted — implemented by ADR-0020
**Baseline:** `2e6d8f9e2cc09ccd15c58f1432f20467fb9fb03a` — *Merge Level-Crossing Foundation v1 Review*
**Baseline metrics (re-derived, not trusted):** 2856 tests, 2856 with `-W error`, `level_crossing` 246,
`market_structure` 1227, `structural_trend` 353, `series_context` 184, state-history 267, ordering 33,
126 public exports, 0 collisions.

---

## 1. Scope

Build **only** the deterministic Break of Structure layer that consumes existing crossing events.

Not trend. Not CHoCH. Not entries, exits, protected levels, inducement, liquidity or regime.

**BOS must never inspect raw OHLC candles.** This design achieves that structurally rather than by
discipline: `fmis.structure_break` does not import `fmis.data` **at all**, so `Candle` is not a name it can
reach, and an AST guard pins it.

---

## 2. Targeted audit

Only `level_crossing`, `structural_levels`, structural labels/sequence/trend, `series_context` and the
crossing ADRs were inspected. Earlier repository-wide audits were not repeated.

### 2.1 What exists

| Fact | Fields |
|---|---|
| `PriceLevel` | `price`, `side`, `origin` |
| `LevelOrigin` | `index`, `timestamp`, `label` |
| `LevelCrossingEvent` | `level`, `candle`, `index`, `kind`, `mechanism`; `timestamp` as a projection |
| `CrossingKind` | `TOUCH`, `WICK_BREACH`, `CLOSE_BREACH` |
| `CrossingMechanism` | `WITHIN_RANGE`, `GAPPED_BEYOND`, `ALREADY_BEYOND` |

### 2.2 Question 1 — can BOS be expressed entirely from LevelCrossing events?

**No — it needs the *level set* as well, and both already exist.** Crossings alone are insufficient
because BOS is not "a level was crossed"; it is "**the reference level** was crossed". Determining which
level is the reference at bar *i* requires knowing every level on that side, including levels that were
never crossed and therefore produced no event.

The concrete failure: swing highs at 105 (bar 10) and 110 (bar 20). A close of 107 at bar 25 crosses the
105 level. From crossings alone that looks like a break; with the level set it plainly is not, because the
reference high is 110. Both inputs are required, and `ContextualSeries[PriceLevel]` is already a
first-class output of `contextual_structural_levels`.

### 2.3 Question 2 — must any candle information be consulted?

**No.** Everything BOS needs is already on the two inputs:

| BOS needs | Supplied by |
|---|---|
| did price close beyond the level? | `crossing.kind is CLOSE_BREACH` |
| did price actually arrive there? | `crossing.mechanism` |
| at which bar? | `crossing.index`, `crossing.timestamp` |
| which level, at what price, on which side? | `crossing.level` |
| when was that level established? | `crossing.level.origin.index` |
| what kind of swing was it? | `crossing.level.origin.label` |

Verified experimentally: the prototype derives BOS with no candle access, and the shipped package imports
no candle type.

### 2.4 Question 3 — is a primitive missing?

**Yes, one, and it is documented here rather than invented.**

> **The confirmation delay (`right_bars`) is not carried on any derived fact.**

`detect_swings(series, left_bars=…, right_bars=…)` takes it, but `SwingPoint`, `SwingComparison`,
`StructuralSwing`, `LevelOrigin`, `PriceLevel` and `LevelCrossingEvent` **all** record only the *pivot*
index. Verified by inspecting every dataclass's field list.

**Why BOS needs it.** A swing at bar `o` is only *knowable* at bar `o + right_bars`. If level eligibility
began at the pivot bar, BOS would be **prefix-unstable** — measured, not theorised: **30 violating prefixes
across 40 seeded fixtures**, with this minimal reproduction:

```
levels: lower 98.5 @6 (higher_low) · upper 103.8 @9 · lower 97.1 @11 (lower_low) · upper 103.0 @12
bar 12 closes at 98.4

prefix of 13 bars : the swing low at 11 is not yet confirmed, so the reference low is 98.5@6
                    -> 98.4 < 98.5  -> BOS reported
full 15-bar run   : the swing low at 11 exists, so the reference low is 97.1@11
                    -> 98.4 > 97.1  -> no BOS
```

The prefix reports a break the full run does not. With **confirmation-based** eligibility the level at
bar 11 becomes eligible only at bar 13, so at bar 12 the reference is 98.5@6 in **both** — and the answer
is also the *correct* one, because at bar 12 nobody could yet know the swing at 11 existed. This is the
non-repainting requirement, not a stability patch.

Measured: **0 violations across the same 40 fixtures** under confirmation-based eligibility.

**Resolution, chosen deliberately over inventing hidden behaviour.** `confirmation_bars` is a
**required keyword argument with no default**. The caller already chose `right_bars` when calling
`contextual_structural_swings`; BOS asks for the same number explicitly. A default would silently bind BOS
to `DEFAULT_RIGHT_BARS` and be wrong for anyone who passed anything else — the failure mode a default is
supposed to prevent. Carrying the delay on `LevelOrigin` is the correct long-term fix; it changes a
shipped model and belongs in its own milestone (**deferred question D1**).

### 2.5 A proven property that makes this safe

**No *breach* of a level can occur inside that level's own confirmation window.**

For a confirmed swing high at `o`, detection requires `high[j] <= high[o]` for every `j` in
`(o, o+right]`. Since `close <= high`, no bar in that window can close — or even wick — strictly beyond
the level. Only a `TOUCH` is possible. Mirrored for lows.

Measured across 900 series × 3 values of `right_bars`: **11,608 in-window crossings inspected, 0 were
breaches.** Every one was a `TOUCH`.

So confirmation-based eligibility never discards a break that could have existed. It changes only which
level is the *reference*, which is exactly the repainting hazard it exists to close.

---

## 3. Design decisions

### 3.1 What is a BOS?

> **A break of structure is the first close beyond the reference structural level for its side, at a bar
> where that level was already knowable.**

Five conjuncts, each independently decided below, each testable, none interpretive:

1. the crossing's `kind` is `CLOSE_BREACH`;
2. the crossing's `mechanism` is not `ALREADY_BEYOND`;
3. the level carries provenance, and the crossing bar is at or after `origin.index + confirmation_bars`;
4. the level **is the reference** for its side at that bar;
5. it is the **first** such crossing for that level.

### 3.2 Which crossing events qualify?

| Kind | Qualifies | Why |
|---|---|---|
| `TOUCH` | **No** | Price reached the level and did not pass it. Nothing was broken. Equality is not a breach — inherited verbatim from ADR-0019 §2.3. |
| `WICK_BREACH` | **No** | The extreme passed the level; the **close** did not. A wick beyond a level that the bar then closed back inside is a rejection, not a break — and, critically, a wick-based rule cannot be non-repainting on a forming bar, which the market-structure review §15 identified as the deciding property. |
| `CLOSE_BREACH` | **Yes — required** | The bar settled beyond the level. On closed candles this is final and never revised. |

**`CLOSE_BREACH` is required and is the only qualifying kind.** There is exactly one policy and it is not
configurable, for ADR-0019 §2.2's reason: a configurable rule makes every historical break
non-reproducible without its setting. A consumer wanting wick-based breaks reads the crossing history
directly, where `WICK_BREACH` is already a first-class fact.

### 3.3 Do `EQUAL_HIGH` / `EQUAL_LOW` break structure?

**The label is irrelevant to whether a break occurred. All six labels can produce a reference level.**

This is not a claim that an equal high is the same as a higher high. It is a claim about *what the break
test measures*: whether a close is beyond a **price**. An `EQUAL_HIGH`-derived level sits at a real price
that price either closed beyond or did not, and the label does not change that arithmetic.

The label is **carried through** on `break.level.origin.label`, unchanged, so a consumer that wants to
weight an `EQUAL_HIGH` break differently has the fact in hand. Filtering here would be that consumer's
policy executed in the wrong layer — and would silently discard breaks, which is the failure mode that is
hardest to notice.

Verified: an `EQUAL_HIGH`-derived level at 105 is broken by a close of 109, and the break carries
`label = equal_high`.

### 3.4 Which level becomes eligible, and when?

**The reference level for a side, at bar `i`, is the level on that side with the greatest
`eligible_from` that is `<= i`,** where

```
eligible_from = level.origin.index + confirmation_bars
```

- **Most recent, not most extreme.** "Most extreme unbroken level" is protected-level/liquidity logic and
  is explicitly out of scope.
- **Eligibility begins at the confirmation bar**, per §2.4 — the earliest bar at which the level was
  knowable. Not the pivot bar.
- If **two levels on one side share an origin index**, the reference is ambiguous and the input is
  **rejected**. `structural_levels` cannot produce that (`_validate_key_order` enforces per-type strictly
  increasing indices); a hand-built set can, and guessing would be inventing behaviour.
- A level with **no origin** cannot be ranked at all, so the input is **rejected** rather than the level
  silently ignored. Dropping it would change every later reference without saying so.

### 3.5 Can one crossing create several BOS? Can several crossings create one?

| Question | Answer |
|---|---|
| one crossing → several BOS? | **No.** A crossing names exactly one level; a BOS names exactly one crossing. |
| several crossings → one BOS? | **Yes.** One bar may close beyond many levels; only the reference one yields a BOS, so the rest are discarded. |
| one bar → several BOS? | **Yes, at most one per side** — an upper and a lower break can share a bar. Their order in the output is `UPPER` then `LOWER`, and **that is the level ordering, not a claim about which happened first** (ADR-0019 §2.6, inherited). |

### 3.6 Can BOS occur twice on the same level?

**No. At most one BOS per level, ever** — the earliest qualifying crossing.

This is the level lifecycle that ADR-0019 §2.7 deliberately refused to put in the primitive, and it
belongs here: *structure breaks once*. A second close beyond an already-broken level is not a second
break; the level stopped being structure when it broke.

Consequence, stated plainly: once the reference level is broken and no newer level exists on that side,
**there is no further BOS on that side until a new swing forms**. Verified: two close-breaches of one
level at bars 8 and 10 yield exactly one break, at bar 8.

### 3.7 Can a BOS be invalidated?

**No.** A BOS is a fact about a bar that has closed. Nothing later revises it.

"This break failed" is a *later reading* over the break sequence — and it is CHoCH-adjacent, which makes
it doubly out of scope. There is no `invalidated` field, no `active` flag and no lifecycle beyond §3.6.

### 3.8 Duplicate levels and duplicate crossings

- **Duplicate levels.** Exact duplicates are already rejected upstream by `derive_level_crossings`. Here,
  the relevant duplicate is *ambiguity of reference* — two same-side levels sharing an origin index —
  which is rejected (§3.4). Two levels at the **same price** with different origins are two levels, and the
  later one is the reference; the earlier one simply stops being the reference.
- **Duplicate crossings.** BOS is **invariant to duplicated crossing events**, because it selects the
  earliest qualifying crossing per level. Duplicates collapse, deterministically, with no dedup step.
- **Input order.** BOS is **invariant to the order of both inputs**. It indexes the level set and scans
  crossings, then sorts its own output by its own key. This is deliberate: re-validating the crossing run's
  canonical order would be a *second implementation* of a rule `fmis.level_crossing` already owns, and
  `_event_key` is private to that package for exactly that reason. Verified over 10 random shuffles of both
  inputs.
- **Unknown levels.** A crossing referencing a level absent from the level set is **rejected**, not
  skipped — silently skipping it would hide a caller error that changes the answer.

### 3.9 Outside bars

A bar may produce two crossings, and therefore up to two breaks — one per side. Both carry the same
`index` and `timestamp`.

Reachable, though it requires the reference low to sit **above** the reference high (a market that has run
far enough that the newest swing low is above the newest swing high), so that one close can be above the
upper reference and below the lower reference at once. It is representable, tested with directly
constructed levels and crossings, and **no intrabar path is claimed** — inherited from ADR-0019 §2.6,
where the honest encoding is a model that cannot express a path at all.

### 3.10 Gaps

**The mechanism does not decide whether a break occurred; the close does.**

- `WITHIN_RANGE` → qualifies.
- `GAPPED_BEYOND` → **qualifies.** Price closed beyond the level. That it arrived without trading at the
  level is a fact worth carrying — and it is carried, on `break.crossing.mechanism` — but it does not make
  the close any less beyond. Verified: a bar gapping from 100 to 152 over a level at 103 produces a break.
- `ALREADY_BEYOND` → **excluded.** ADR-0019 defines it as *"a state observation, not a crossing — no
  predecessor, so no arrival can be claimed"*. Claiming a break requires an arrival.

`ALREADY_BEYOND` is **doubly excluded**: it can only occur at bar 0, and no structural level is eligible at
bar 0 (`origin.index >= left_bars >= 1`, so `eligible_from >= 2`). Both exclusions are tested, because
relying on the second alone would make the rule invisible to a reader and to a mutant.

### 3.11 Prefix stability

**Contract:** for a candle prefix `P` of a series, with levels and crossings each derived from `P`,

```
derive_structure_breaks(levels(P), crossings(P), confirmation_bars=R)
    == tuple(b for b in derive_structure_breaks(levels(full), crossings(full), confirmation_bars=R)
             if b.index < len(P.closed().candles))
```

This is the strong, pipeline-wide form, not merely stability under a truncated crossing list. It holds
because every input to a decision at bar `i` is available from candles `0..i`: crossings are exactly
prefix-stable (ADR-0019 §2.9), and a level is *eligible* at `i` precisely when it is *detectable* from
`0..i`.

Measured: **0 violations** across 40 seeded fixtures × every prefix, plus handcrafted edge cases. The
origin-based alternative gives **30 violations** on the same data (§2.4).

### 3.12 Replay determinism and context propagation

Pure functions, no state, no cache, no clock, no randomness. Repeated derivation is identical; permuted
inputs are identical.

Context follows the established contract exactly:

```python
identity = require_same_identity(levels, crossings)
```

Both inputs are `ContextualSeries`, so one call covers both. Mixed instruments and mixed timeframes are
rejected before any work. Empty inputs retain a full identity. No API accepts an identity argument, so
substitution is unrepresentable. Identity propagates **by reference**.

---

## 4. Alternatives rejected

| Alternative | Why rejected |
|---|---|
| **BOS from crossings alone** | cannot identify the reference level; reports a break of a superseded level (§2.2) |
| **BOS re-reading `CandleSeries`** | duplicates the crossing rule, violates the mission, and re-introduces the dependency `level_crossing` exists to remove |
| **eligibility at the pivot bar** | prefix-unstable — 30 violations measured, with a minimal reproduction (§2.4) |
| **`confirmation_bars` defaulted to `DEFAULT_RIGHT_BARS`** | silently wrong for any caller who passed a different `right_bars`; a required argument makes the coupling visible |
| **most *extreme* unbroken level as reference** | protected-level / liquidity logic, explicitly out of scope |
| **`WICK_BREACH` qualifying** | not non-repainting on a forming bar (review §15); a wick beyond that closes back inside is a rejection, not a break |
| **`TOUCH` qualifying** | equality is not a breach (ADR-0019 §2.3) |
| **configurable qualifying kind** | makes historical breaks non-reproducible without their setting |
| **filtering out `EQUAL_HIGH`-derived levels** | a consumer policy executed in the wrong layer; silently discards breaks |
| **repeated BOS on one level** | structure breaks once; a second close beyond an already-broken level is not a second break |
| **a `BreakDirection` / bullish-bearish enum** | `level.side` already carries the sense; a second field is a second place to disagree, and "bullish" is trading semantics (ADR-0019 §2.4 §D) |
| **an `invalidated` flag** | a later reading over the break sequence, and CHoCH-adjacent |
| **re-validating the crossing run's canonical order** | a second implementation of a rule `fmis.level_crossing` owns; BOS is order-invariant instead |
| **silently ignoring unprovenanced levels or unknown-level crossings** | repairs instead of validating, and changes every later reference without saying so |

---

## 5. Public API and dependency graph

```python
@dataclass(frozen=True, slots=True)
class StructureBreak:
    crossing: LevelCrossingEvent
    eligible_from: int
    # index, timestamp, level, side, label -> projections, not stored fields
```

| Name | Kind |
|---|---|
| `StructureBreak` | model |
| `StructureBreakError` | error base |
| `StructureBreakInputError` | `(StructureBreakError, ValueError)` |
| `derive_structure_breaks(levels, crossings, *, confirmation_bars)` | context-free primitive |
| `contextual_structure_breaks(levels, crossings, *, confirmation_bars)` | safe pipeline API |

**Five public names.** Ordering: `(crossing index, level side)` — total, because there is at most one break
per (bar, side). The full level key is deliberately **not** restated here.

```
fmis.data ─► fmis.market_structure ─► fmis.structural_trend
   │               │                          │
   └───────────────┴──────────────────────────┴─► fmis.series_context
                                                      │
                                                      ▼
                                              fmis.level_crossing
                                                      │
                                                      ▼
                                              fmis.structure_break     ← this milestone
```

Imports **`fmis.level_crossing` and `fmis.series_context` only**. Notably **not `fmis.data`** — so a
candle is not a name this package can reach — and not `fmis.market_structure` or the structural-trend
package. Each is guarded by a test. No runtime dependency is added.

### 5.1 Worked example

```
CandleSeries
  ├─► contextual_structural_swings   ─► ContextualSeries[StructuralSwing]
  │        └─► contextual_structural_levels ─► ContextualSeries[PriceLevel] ──┐
  └─► contextual_level_crossings(series, levels) ─► ContextualSeries[LevelCrossingEvent] ─┤
                                                                                          ▼
                                    contextual_structure_breaks(levels, crossings, confirmation_bars=R)
                                                                                          │
                                                                                          ▼
                                                                    ContextualSeries[StructureBreak]
```

After the crossing stage, **no candle is read again**.

### 5.2 Future CHoCH

A change of character is *the first break opposing the direction of the previous break*, which is

```python
tuple(b for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)
```

— computed from the break sequence alone, touching no level, no crossing and no candle. That is review
§15's ordering satisfied exactly: BOS on levels, CHoCH over the BOS sequence, trend a summary of both.

---

## 6. Experiment results — 14/14 PASS

Prototyped outside production against the real repository types; scratch files deleted before committing.

| # | Demonstration | Result |
|---|---|---|
| 1 | BOS derivable from (levels, crossings) with no candle access | **PASS** |
| 2 | no breach can occur inside a level's own confirmation window | **PASS** — 11,608 in-window crossings, **0** breaches, all `TOUCH` |
| 3 | pivot-index eligibility is prefix-**unstable** | **PASS (finding)** — 30 violating prefixes across 40 fixtures |
| 4 | confirmation-index eligibility is prefix-**stable** | **PASS** — **0** violations, 23 breaks |
| 5 | replay determinism | **PASS** |
| 6 | invariant to level **and** crossing input order | **PASS** — 10 random shuffles of both |
| 7 | invariant to duplicated crossing events | **PASS** |
| 8 | at most one BOS per level | **PASS** |
| 9 | at most one BOS per (bar, side) | **PASS** |
| 10 | outside bar can break both sides at one bar | **PASS** |
| 11 | empty levels and crossings | **PASS** — `()` |
| 12 | levels but no crossings | **PASS** — `()` |
| 13 | `GAPPED_BEYOND` produces a break | **PASS** — gap 100→152 over a level at 103 breaks it |
| 14 | CHoCH definable over the break sequence alone | **PASS** |

Named fixtures carried into the test suite: the minimal prefix-instability counterexample (§2.4); an
`EQUAL_HIGH`-derived level at 105 broken by a close of 109; a gapped break; a level close-breached at bars
8 and 10 yielding exactly one break.

---

## 7. Limitations and deferred questions

| | Question | Status |
|---|---|---|
| **D1** | **The confirmation delay is not carried on any derived fact**, so `confirmation_bars` must be supplied and matched to detection by the caller. A mismatch is undetectable. | **The milestone's principal limitation.** Carrying it on `LevelOrigin` changes a shipped model and needs its own milestone. |
| **D2** | The **first swing of each type** has no `StructuralSwing` and therefore no level (ADR-0019 D2), so the earliest reference on each side is missing. | Inherited, unchanged. |
| **D3** | No break invalidation, no "failed break". | Deliberate — a later reading, CHoCH-adjacent. |
| **D4** | Exact float comparison inherited from ADR-0013 §4 via the crossing kind. | Inherited, unchanged. |
| **D5** | Reference selection is **most recent**, not most extreme. A run of lower highs makes each successive lower high the reference. | Deliberate; "most extreme unbroken" is protected-level logic. |
| **D6** | BOS is defined per side independently. No cross-side interaction, no sequence reading. | Deliberate — that is CHoCH's job. |

**No P0 or P1 design question remains unresolved.**
