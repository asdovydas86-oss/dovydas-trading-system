# ADR-0020 — Break of Structure Foundation v1: the first close beyond a level that was already knowable

**Status:** Accepted
**Milestone:** AD
**Date:** 2026-07-31
**Supersedes / amends:** nothing. Extends ADR-0012, ADR-0013, ADR-0018, ADR-0019.
**Design:** [`docs/design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md`](../design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md)

---

## 1. Context

ADR-0019 built the crossing primitive and deliberately refused every lifecycle decision, recording them as
BOS's to make: which level is protected, when protection ends, whether a `TOUCH` or a `WICK_BREACH` counts,
whether an `EQUAL_HIGH`-derived level breaks anything, and activation (deferred question D1).

This milestone makes exactly those decisions and nothing else. Not trend. Not change of character.

---

## 2. The audit, and the one missing primitive

### 2.1 BOS needs levels *and* crossings — both already exist

Crossings alone are insufficient, because BOS is not "a level was crossed" but "**the reference level** was
crossed". Identifying the reference at bar *i* requires the whole level set, including levels that were
never crossed and so produced no event. Concretely: swing highs at 105 (bar 10) and 110 (bar 20); a close
of 107 at bar 25 crosses the 105 level, which from crossings alone looks like a break and plainly is not.

### 2.2 No candle is consulted, and that is structural

Every fact a break needs is on the two inputs — the kind, the mechanism, the bar index and timestamp, the
level, its price, side, origin index and label. `fmis.structure_break` therefore **does not import
`fmis.data` at all**, so `Candle` is not a name it can reach. Two AST guards pin it: no `fmis.data` import,
and no attribute access named `open`/`high`/`low`/`close`/`volume`.

### 2.3 The missing primitive — documented, not invented

> **The confirmation delay (`right_bars`) is recorded on no derived fact.**

Verified by inspecting every dataclass: `SwingPoint`, `SwingComparison`, `StructuralSwing`, `LevelOrigin`,
`PriceLevel` and `LevelCrossingEvent` all carry only the **pivot** index.

BOS needs it because a swing at bar `o` is knowable only at `o + right_bars`. With pivot-bar eligibility,
BOS is **prefix-unstable** — measured at **30 violating prefixes across 40 seeded fixtures**, with this
minimal reproduction (shipped as a test fixture):

```
levels: lower 98.5 @6 · upper 103.8 @9 · lower 97.1 @11 · upper 103.0 @12
bar 12 closes at 98.4

13-bar prefix : swing low @11 not yet confirmed → reference low is 98.5@6 → 98.4 < 98.5 → BOS
full 15 bars  : swing low @11 exists            → reference low is 97.1@11 → 98.4 > 97.1 → no BOS
```

Confirmation-based eligibility gives **0 violations**, and gives the *correct* answer: at bar 12 nobody
could know the swing at 11 existed. This is the non-repainting requirement, not a stability patch.

**Decision:** `confirmation_bars` is a **required keyword argument with no default**. A default would
silently bind BOS to `DEFAULT_RIGHT_BARS` and be wrong for any caller who chose otherwise — the failure a
default is meant to prevent. Carrying the delay on `LevelOrigin` changes a shipped model and is deferred
(**D1**).

### 2.4 A proven property that makes this safe

**No breach can occur inside a level's own confirmation window.** Detection requires every bar in
`(o, o+right]` to stay at or inside the pivot's extreme, and `close <= high`, so only a `TOUCH` is
possible. Measured across 900 series × 3 values of `right_bars`: **11,608 in-window crossings, 0 breaches.**

So confirmation-based eligibility never discards a reachable break. It only fixes which level is the
reference — exactly the repainting hazard it exists to close.

---

## 3. Decision

A new sibling package **`fmis.structure_break`** with **five public names**.

> **A break of structure is the first close beyond the reference structural level for its side, at a bar
> where that level was already knowable.**

Five conjuncts, each decided separately:

| # | Conjunct | Decision |
|---|---|---|
| 1 | qualifying kind | `CrossingKind.CLOSE_BREACH` **only** |
| 2 | mechanism | not `ALREADY_BEYOND` |
| 3 | eligibility | level has provenance and `index >= origin.index + confirmation_bars` |
| 4 | reference | the level **is** the most recent eligible level on its side |
| 5 | lifecycle | it is the **first** such crossing for that level |

### 3.1 Which crossings qualify

| Kind | Qualifies | Why |
|---|---|---|
| `TOUCH` | **No** | price reached the level and did not pass it; equality is not a breach (ADR-0019 §2.3) |
| `WICK_BREACH` | **No** | the extreme passed, the **close** did not — a rejection, not a break. A wick rule also cannot be non-repainting on a forming bar, which review §15 named as the deciding property |
| `CLOSE_BREACH` | **Yes, required** | the bar settled beyond the level; on closed candles this is final |

Exactly one policy, **not configurable** — a setting would make every historical break non-reproducible
without it. A consumer wanting wick breaks reads the crossing history, where `WICK_BREACH` is already
first-class.

### 3.2 `EQUAL_HIGH` and `EQUAL_LOW`

**The label decides nothing. All six labels can produce a reference level.**

Not a claim that an equal high equals a higher high — a claim about what the break test *measures*: a close
against a **price**. The label is carried unchanged on `StructureBreak.label`, so a consumer that wants to
weigh them differently can, in its own layer. Filtering here would silently discard breaks.

### 3.3 The reference level

The level on that side with the greatest `eligible_from <= index`, where
`eligible_from = origin.index + confirmation_bars`.

**Most recent, not most extreme** — "most extreme unbroken" is protected-level and liquidity logic, out of
scope (**D5**). Two levels on one side sharing an origin index make the reference ambiguous and are
**rejected**; a level with no origin cannot be ranked and is **rejected**. `structural_levels` can produce
neither, so both mean a hand-built set where guessing would be inventing behaviour.

### 3.4 Cardinality

| Question | Answer |
|---|---|
| one crossing → several breaks? | **No** — a crossing names one level, a break names one crossing |
| several crossings → one break? | **Yes** — a bar may close beyond many levels; only the reference one counts |
| one bar → several breaks? | **Yes, at most one per side** |
| twice on one level? | **No — structure breaks once**, ever, at the earliest qualifying crossing |
| can a break be invalidated? | **No** — a fact about a closed bar; "it failed" is a later reading over the break *sequence*, and change-of-character adjacent (**D3**) |

Once the reference breaks with no newer level on that side, **there is no further break on that side until
a new swing forms.**

### 3.5 Outside bars and gaps

Two breaks may share a bar — one upper, one lower — reachable when the reference low sits above the
reference high. Their order is `UPPER` then `LOWER`, from an explicit rank, and **is not a claim about
which happened first**; ADR-0019 §2.6's refusal to fabricate an intrabar path is inherited, and
`StructureBreak` has no field that could express one.

`GAPPED_BEYOND` **qualifies** — the close is beyond the level, and how price arrived is carried on
`crossing.mechanism` rather than used to filter. `ALREADY_BEYOND` is **excluded**, because ADR-0019 defines
it as a state observation with no arrival, and claiming a break requires an arrival. It is **doubly
excluded** — it can only occur at bar 0, where no structural level is eligible — and both exclusions are
tested, since relying on the second alone would make the rule invisible to a reader and to a mutant.

### 3.6 Reference lookup

`_reference` uses `bisect_right` over the side's list, not a scan. The list is sorted by `eligible_from` and
those values are **strictly increasing within a side** — two levels sharing an origin index are rejected —
which is what makes the binary search return the *same element* a scan would, exactly.

The scan shipped first and the independent review measured what it cost: **125,000,000 inner iterations**
for 5,000 levels against 50,000 crossings, because a crossing's index is usually beyond every level's
eligibility so the loop's early exit almost never fired. The replacement cut that case from ~1.3 s to
0.026 s and made runtime independent of the level count. Equivalence is proved against a naive linear
implementation over an exhaustive small space, not argued.

### 3.7 Ordering and input invariance

Output order is `(breaking bar index, level side)` from an explicit rank mapping — total, because at most
one break exists per (bar, side). **The full level ordering key is deliberately not restated**; it is
private to `fmis.level_crossing` precisely so a second implementation cannot drift from it.

BOS is **invariant to the order of both inputs** and to **duplicated crossing events**, because it selects
the earliest qualifying crossing per level rather than assuming one. Re-validating the crossing run's
canonical order would be that forbidden second implementation.

### 3.8 The model

```python
@dataclass(frozen=True, slots=True)
class StructureBreak:
    crossing: LevelCrossingEvent
    eligible_from: int
    # index · timestamp · level · side · origin · label -> projections
```

Two stored fields. `eligible_from` is stored rather than projected because `confirmation_bars` is
caller-supplied and lives nowhere on the inputs, so a consumer holding only this object could not otherwise
recover it — and recovering it is what makes the break auditable.

**The break validates itself against its own crossing**: a `StructureBreak` claiming a touch, a wick, an
`ALREADY_BEYOND` crossing, an unprovenanced level, or a bar before eligibility **cannot be constructed**.

**No direction enum.** `side` projects the level's side, which already carries the only sense this layer
knows — ADR-0019 §D unchanged. `UPPER` is not "bullish".

### 3.9 Prefix stability and context

**Exact**, in the pipeline-wide form: levels and crossings derived from a candle prefix give exactly the
full run's breaks whose index falls inside that prefix, in the same order. Measured at **0 violations**
across seeded fixtures, handcrafted edge cases, three confirmation delays and the real fixture.

Context follows ADR-0018 unchanged: one `require_same_identity(levels, crossings)` call, mismatches
rejected before any derivation, empty inputs retaining identity, no identity argument anywhere, propagation
by reference.

---

## 4. Public API and dependencies

`StructureBreak` · `StructureBreakError` · `StructureBreakInputError` ·
`derive_structure_breaks(levels, crossings, *, confirmation_bars)` ·
`contextual_structure_breaks(levels, crossings, *, confirmation_bars)`

```
fmis.series_context ─► fmis.level_crossing ─► fmis.structure_break
```

Imports `fmis.level_crossing`, `fmis.series_context`, and `fmis.market_structure` for one label type.
**Not `fmis.data`.** Not the structural-trend package. Nothing imports it. No runtime dependency added.

`fmis.level_crossing`'s "nothing imports this package" guard was **narrowed** to name `structure_break` as
its single permitted consumer, and `fmis.series_context`'s to name both — the widening ADR-0019 and
ADR-0018 respectively anticipated. Both exemptions are *named*, not pattern-matched, so a second consumer
must justify itself in an ADR. The direction each guard protects is unchanged.

### 4.1 Exact exception messages (a shipped contract, asserted with `==`)

| Message |
|---|
| `crossing kind 'touch' does not break structure; expected 'close_breach'` |
| `crossing mechanism 'already_beyond' does not break structure; the series began beyond the level, so no arrival can be claimed` |
| `crossing level carries no origin; a break needs provenance to place the level in time` |
| `crossing index (6) precedes eligible_from (7); the level was not yet knowable` |
| `eligible_from (4) cannot precede the level origin index (5)` |
| `levels[1] carries no origin (upper 105.0); a break needs provenance to place the level in time` |
| `levels[1] shares origin index 5 with another upper level; the reference level at that point would be ambiguous` |
| `crossings[0] references a level absent from levels (upper 200.0)` |
| `confirmation_bars must be an int, got str` · `confirmation_bars cannot be negative, got -1` |
| `levels must be a ContextualSeries, got tuple` · `crossings must be a ContextualSeries, got tuple` |

No existing message was changed.

---

## 5. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| BOS from crossings alone | cannot identify the reference; reports breaks of superseded levels |
| BOS re-reading `CandleSeries` | duplicates the crossing rule and reintroduces the dependency `level_crossing` removed |
| eligibility at the pivot bar | prefix-unstable — 30 violations measured, with a minimal reproduction |
| `confirmation_bars` defaulted | silently wrong for any caller who chose a different `right_bars` |
| most *extreme* unbroken level as reference | protected-level / liquidity logic, out of scope |
| `WICK_BREACH` or `TOUCH` qualifying | not non-repainting on a forming bar; equality is not a breach |
| configurable qualifying kind | historical breaks non-reproducible without their setting |
| filtering `EQUAL_HIGH`-derived levels | a consumer policy in the wrong layer; silently discards breaks |
| repeated breaks on one level | structure breaks once |
| a `BreakDirection` / bullish-bearish enum | `side` already carries it; "bullish" is trading semantics |
| an `invalidated` flag | a later reading over the break sequence, CHoCH-adjacent |
| re-validating the crossing run's order | a second implementation of a rule `level_crossing` owns |
| silently ignoring unrankable levels or unknown-level crossings | repairs instead of validating, and changes every later reference |
| a redundant eligibility check beside the reference test | **removed during mutation validation** — provably unreachable, an equivalent mutant by construction |
| a linear scan for reference lookup | **replaced during review** — O(crossings x levels-per-side), measured at 125M inner iterations |
| a `confirmation_bars` default, or a partial mismatch check | a default is silently wrong for a different `right_bars`; the check is only possible in one direction and would reject valid hand-built level sets |

---

## 6. Consequences

**Gained.** A non-repainting, exactly prefix-stable break primitive; provenance and label carried from
swing to break; identity enforced at one choke point; a break sequence sufficient for CHoCH with no
re-derivation.

**Costs, accepted deliberately.**

- **`confirmation_bars` must be supplied and matched to detection by the caller, and a mismatch is
  undetectable** (D1). The milestone's principal limitation, named loudly rather than defaulted away.
- **No break invalidation** (D3) — a consumer wanting "failed break" builds it over the sequence.
- **Most-recent, not most-extreme** reference (D5): a run of lower highs makes each successive lower high
  the reference.

**Limitations.**

| | Question | Status |
|---|---|---|
| **D1** | confirmation delay not carried on any derived fact | principal limitation; own milestone |
| **D2** | first swing of each type has no level (ADR-0019 D2) | inherited, unchanged |
| **D3** | no invalidation, no "failed break" | deliberate — a later reading |
| **D4** | exact float comparison (ADR-0013 §4), inherited via the crossing kind | inherited |
| **D5** | reference is most recent, not most extreme | deliberate |
| **D6** | breaks are derived per side independently; no sequence reading | deliberate — that is CHoCH's job |

**Still deliberately absent:** CHoCH, trend, regime, bias, protected levels, inducement, liquidity sweeps,
support, resistance, signals, entries, exits, stops, targets, sizing, confidence, AI interpretation,
persistence and multi-timeframe aggregation.

---

## 7. Future CHoCH

```python
tuple(b for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)
```

Computed from the break sequence alone — no level, no crossing, no candle. That is review §15's ordering
satisfied exactly: **BOS on levels, CHoCH over the BOS sequence, trend a summary of both, defining
neither.**

---

## 8. Validation

3033 tests pass (2856 baseline + 175 new + 2 narrowed guards), identically with `-W error`.
**42/42 mutation probes detected, 0 no-ops, 0 survivors, all sources restored byte-for-byte with SHA-256
verification.** 0 export collisions. `pyproject.toml` and `uv.lock` unchanged; `bisect` is standard library,
so no runtime dependency was added.

The independent review
([`docs/reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md`](../reviews/BREAK_OF_STRUCTURE_FOUNDATION_V1_REVIEW.md))
found **no P0 and no P1**, one **P2** — the linear reference lookup described in §3.6 — and three P3, one
fixed and two documented. 48/48 adversarial cases pass. After the fix, 20,000 levels against 200,000
crossings derive in 0.089 s.
