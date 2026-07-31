# Change of Character Foundation v1 — Independent Review

**Reviewed commit:** `9658003` — *Merge Change of Character Foundation v1*
**Baseline compared against:** `5aac1a3f652ea44e4523e2609e140c18a0b9f121` — *Merge Break of Structure
Foundation v1 Review*
**Verdict:** **accepted.** No P0. No P1. Three P3 observations, all documented rather than fixed, none
blocking.

---

## 1. Method

Every load-bearing claim was **re-derived from production source**, not read from ADR-0021 or the design
document, and not taken from the milestone's own test suite.

The central check does not reuse the shipped implementation in any form: the rule was **reimplemented from
ADR-0021 §3.1–§3.3's prose and transition table** as a deliberately naive `O(n²)` scan — for each break,
find the greatest strictly smaller break-bearing bar, read that bar's side set, apply the table — and the
two were cross-checked over every input class below. A reviewer that calls the implementation to check the
implementation proves nothing, so it does not.

Fixtures were constructed independently of `tests/test_change_of_character.py`.

**50 checks, 50 pass, 0 findings from the automated pass.** Three P3 observations below come from reading,
not from a failing check.

### 1.1 Three review-harness defects, disclosed

The first harness run reported four failures. **All four were defects in the review harness, and none was
a defect in the package.** They are recorded because a review that hides its own false positives cannot be
trusted about its true negatives.

| Reported | Actual cause | Resolution |
|---|---|---|
| 1,387 / 3,000 randomised equivalence mismatches | the harness's own reference rule emitted a change **once per duplicated break**, instead of collapsing equal duplicates as the contract specifies | reference rule corrected; 0 mismatches |
| `confirmation_bars` "duplicated" in `changes.py` | crude substring scan matched the **module docstring sentence stating the argument does not exist** | re-checked at AST identifier level: not a `Name`, `Attribute`, `arg`, `FunctionDef` or `ClassDef` anywhere |
| input payload "sliced / copied" | same crude scan matched `breaks[{position}]` inside an **error-message f-string** and `zip(breaks, breaks[1:])` inside the **docstring describing the superseded sketch** | re-checked at AST level: the only `Subscript` over a runtime name is `grouped[…]` / `at_bar[…]`; there is **no** `list(breaks)`, `tuple(breaks)`, `sorted(breaks)` or `breaks[…]` |
| `OverflowError` at bar index 10⁹ | the **harness's** fixture builder computes `BASE + timedelta(hours=4 * index)`, which overflows `datetime` past year 9999 | harness fixture reduced to 10⁶; production has no timestamp arithmetic at all |

---

## 2. Re-derived: the rule is what the ADR says it is

| Input class | Cases | Mismatches against the independent reimplementation |
|---|---|---|
| exhaustive, single-sided bars, up to 4 breaks over 7 bars | 939 | **0** |
| exhaustive, **including two-sided bars**, 3 bars × {U}/{L}/{U,L} | 540 | **0** |
| randomised, with injected duplicates and shuffles | 3,000 | **0** |
| candle-derived chains (220 bars each) | 60 | **0** |

The two-sided row is the one that matters: it is the input class where the rule differs from ADR-0020 §7's
sketch, and it is covered exhaustively rather than by example.

---

## 3. Re-derived: invariants, ordering, determinism

| Claim | Method | Result |
|---|---|---|
| output strictly increasing by bar; at most one change per bar | 43 runs incl. adversarial shapes | **holds** |
| I3 / I4 — opposite sides, strictly earlier predecessor | every emitted change | **holds** |
| I1 / I2 — subject and previous are supplied objects, **by identity** | `is` against the input list | **holds** |
| I12 — no break-bearing bar lies between a change and its predecessor | every emitted change | **holds** |
| permutation invariance | 20 runs × 8 shuffles | **holds** |
| duplicate invariance | input concatenated with itself | **holds** |
| the input sequence is not mutated | element-wise `is` before/after | **holds** |
| **replay determinism across processes** | 4 fresh interpreters, `PYTHONHASHSEED` ∈ {0, 1, 12345, random} | **1 distinct output** |

The hash-seed check is the one worth calling out. The package iterates a `dict` and sorts its integer keys;
it iterates **no set anywhere**, which is what makes the output independent of hash randomisation. That was
verified rather than assumed — a set iteration in the fold would have been a genuine, intermittent replay
defect invisible to a single-process test run.

---

## 4. Re-derived: prefix stability

| Measurement | Prefixes | Violations |
|---|---|---|
| candle-prefix, full chain re-derived per prefix (30 fixtures × 130 bars) | 3,900 | **0** |
| break-run truncation, formulated independently of the suite's version | all cuts over 15 runs | **0** |

The design's proof is in two steps — breaks are exactly prefix-stable, and the rule at bar `i` reads only
breaks at bars `≤ i`. The second step was checked by reading the fold: the predecessor bar is drawn from
`sorted(grouped)` strictly below the current bar, and nothing else is consulted. There is no lookahead, no
window, no aggregate over the run, and no dependence on the break count.

---

## 5. Re-derived: architecture

| Claim | Result |
|---|---|
| import set is exactly `{__future__, dataclasses, datetime, collections.abc, itertools}` + the three `fmis` packages + own submodules | **exact — no extras** |
| **only `LevelSide`** is taken from `fmis.level_crossing` | **exact** |
| `fmis.data` never imported — a candle is unreachable | **holds** |
| `fmis.market_structure` never imported | **holds** |
| `fmis.structural_trend` never imported | **holds** |
| no private submodule of any dependency imported | **holds** |
| no forbidden identifier reachable (`Candle`, `PriceLevel`, `LevelCrossingEvent`, `CrossingKind`, `CrossingMechanism`, `derive_structure_breaks`, `_SIDE_RANK`, `bisect_right`, `MappingProxyType`, `StructuralTrendType`, `MINIMUM_DIRECTIONAL_SHIFTS`, `require_same_identity`, …) | **none present** |
| no forbidden attribute read (`open`/`high`/`low`/`close`/`volume`/`symbol`/`timeframe`/`price`/`now`/`perf_counter`/…) | **none present** |
| no `global`, no module-level state besides `__all__`, no mutable default argument | **holds** |
| **no upstream private rule identifier exists anywhere in the package** | **holds** |
| nothing imports `fmis.change_of_character` | **holds** |
| `fmis.structural_trend` imports neither `structure_break` nor `change_of_character` | **holds** |
| no import cycle; a cold import of every lower package does not pull this one in | **holds** |

### 5.1 The narrowed guards were empirically proved still to bite

Narrowing a guard is where an architecture review earns its keep, because a guard that no longer fails is
indistinguishable from one that passes. Each was tested by **injecting a forbidden reference and confirming
the suite fails**, then restoring:

| Injection | Guard | Result |
|---|---|---|
| `fmis.structure_break` referenced from `fmis/data/models.py` | `test_only_change_of_character_imports_structure_break` | **1 failed** ✓ |
| `fmis.change_of_character` referenced from `fmis/market_structure/swings.py` | `test_nothing_imports_change_of_character` | **1 failed** ✓ |
| `fmis.level_crossing` referenced from `fmis/structural_trend/trend.py` | `test_nothing_below_imports_level_crossing` | **1 failed** ✓ |
| `fmis.series_context` referenced from `fmis/data/observation.py` | `test_nothing_below_imports_series_context` | **1 failed** ✓ |
| `CrossingKind` added to the `fmis.level_crossing` import in `changes.py` | the two `LevelSide`-only guards | **3 failed** ✓ |

The direction each guard protects is unchanged, every exemption is a **named path** rather than a pattern,
and the working tree was verified clean after each probe. **No guard was weakened.**

### 5.2 Upstream is byte-untouched

`git diff 5aac1a3..HEAD -- src/` lists **exactly four files**, all under
`src/fmis/change_of_character/`. No production source outside the new package changed by a single byte —
including `fmis/structure_break/__init__.py`, whose docstring still carries the superseded sketch. That was
the right call: the sketch is prose in a "future" section, no logic depends on it, and rewriting shipped
source to match a later ADR would have put a documentation edit inside a milestone that also had to prove
its sources restored byte-identically after mutation.

`pyproject.toml` and `uv.lock` are untouched; `project.dependencies` is still `[]`.
`git diff` under `tests/` lists exactly four files. 136 public exports, **0 collisions**.

---

## 6. Re-derived: performance

Measured on alternating breaks, best of 3 runs:

| breaks | seconds | ratio for ×2 input |
|---:|---:|---:|
| 1,000 | 0.00053 | — |
| 2,000 | 0.00103 | ×1.95 |
| 4,000 | 0.00218 | ×2.12 |
| 8,000 | 0.00447 | ×2.05 |
| 16,000 | 0.00922 | ×2.06 |
| 32,000 | 0.01885 | ×2.04 |

Doubling the input doubles the time, at every size. Quadratic behaviour would show ×4; the worst observed
ratio is **×2.12**. The `O(n log n)` bound from the sort is real and invisible in this range.

**Adversarial shape** — every bar two-sided, i.e. maximum grouping work and zero output: 40,000 breaks on
20,000 bars in **0.0049 s**.

**Allocations** were measured with `tracemalloc`, not argued: peak allocation for 2,000 / 4,000 / 8,000
breaks is 645 KB / 1.30 MB / 2.60 MB — ratios ×2.02 and ×2.00, i.e. **linear**, with no hidden quadratic
retention.

**No unnecessary allocation was found.** The AST confirms there is no `list(breaks)`, `tuple(breaks)`,
`sorted(breaks)` or subscript of the input anywhere; `itertools.pairwise` is used over the sorted key list
rather than a `[1:]` slice, avoiding a second copy of the keys; and the only allocations are one dict of
bars, one sorted key list, one output list and one output tuple.

**The defect class the BOS review found one layer down cannot occur here.** That review's P2 was an
`O(crossings × levels-per-side)` scan measured at 125 M inner iterations. This package has no nested scan
over the input: the inner loop runs over a mapping of **at most two** entries. That is a structural
property, not a tuning choice.

**No optimisation is recommended.** Recommending one would be optimising a cost that does not exist.

---

## 7. Re-derived: the audit's headline claims

**"BOS already contains every primitive CHoCH needs."** Re-derived by inspecting
`dataclasses.fields(StructureBreak)` and its property set directly: fields `{crossing, eligible_from}`,
properties `{index, label, level, origin, side, timestamp}`. The rule reads `index` and `side`. **Confirmed
— no primitive is missing and none was invented.**

**"ADR-0020 §7's sketch is wrong in one representable case."** Re-derived from scratch, building the levels
and crossings by hand and passing them through the **shipped** `derive_structure_breaks`:

```
breaks produced by the shipped break layer : upper@4 · upper@12 · lower@12
ADR-0020 §7 sketch                         -> (upper@12 -> lower@12)   predecessor on the SAME bar
fmis.change_of_character                   -> (upper@4  -> lower@12)   predecessor strictly earlier
both agree the changing bar is             -> 12
```

**Confirmed.** The finding is real, the fixture is genuinely produced by the break layer rather than
hand-assembled, and the correction preserves *which bar* changed character while fixing *what it changed
from*.

**"The case is not observed in candle-derived data."** Re-measured over **200** independent 200-bar chains:
**0** contained a two-sided break bar, and the sketch and the shipped rule therefore agreed on all 200.
Confirmed — and it is exactly why the correction matters: a wrong answer here would never have surfaced.

**"Prefix stability does not distinguish the two rules."** Confirmed; both measure 0 violations. The design
is right not to claim it does.

---

## 8. Contract surface, re-derived

| Check | Result |
|---|---|
| conflicting `(bar, side)` pair rejected with the documented message, no partial result | **holds** |
| equal duplicates collapse and the **first** object is kept, by reference | **holds** |
| a `ContextualSeries` passed to the bare function is rejected (it is not a `Sequence`) | **holds** |
| a same-bar predecessor is **unconstructible** at the model level | **holds** |
| the wrapper carries identity by reference and its payload equals the bare call's | **holds** |
| extreme bar indices (0 and 10⁶) | **holds** |
| hashable, and pickle round-trips to an equal object | **holds** |
| no caching: repeated calls return equal but **freshly built** objects | **holds** |

---

## 9. Findings

### P0 — none
### P1 — none
### P2 — none

### P3-1 — the bare primitive accepts breaks from different series

`derive_changes_of_character` will happily read a run mixing a BTCUSDT break and an ETHUSDT break, because
identity lives on the envelope and never on an element (ADR-0018). This is **by design, tested, and
consistent with every context-free primitive in the repository** — the same observation was already
recorded as a Milestone AB follow-up. Recorded rather than fixed: the mitigation is that the safe path
(`contextual_changes_of_character`) is also the easy path, and moving identity onto elements would undo
ADR-0018.

### P3-2 — the dependency list reads as three packages, and one of them is a type-only import

A reader scanning imports sees `fmis.level_crossing` and may infer that this layer can reach crossings. It
cannot: only the type name `LevelSide` is imported, and **two** AST guards — one in
`tests/test_change_of_character.py`, one in `tests/test_level_crossing.py` — assert that is the only name
taken, both empirically proved to fail when a second name is added (§5.1). The residual cost is a reader's
first impression, not a reachable capability. Recorded rather than fixed; the alternative — dropping the
annotation on a public property — trades a real guarantee for a cosmetic one.

### P3-3 — the two-sided-bar behaviour is exercised only by constructed fixtures

0 of 200 candle-derived chains produced a two-sided break bar, so the transition table's `INDETERMINATE`
rows, limitation E1, and the §2.3 correction are all covered by **constructed** levels and crossings rather
than by candle-derived data. The fixtures are legitimate — the outside-bar fixture is produced by passing
hand-built levels and crossings through the shipped `derive_structure_breaks`, not by assembling
`StructureBreak` objects directly — and the space is covered exhaustively (§2). Recorded so a future reader
knows the provenance: this behaviour is proved correct, but it has not been observed in market-shaped data,
and a fixture generator that reliably produces reference lows above reference highs would strengthen the
evidence.

---

## 10. Verdict

**Accepted.** The layer does what ADR-0021 says, adds no primitive, takes no configuration, duplicates no
rule, reads no candle, level or crossing, holds every stated invariant, is exactly prefix-stable, is
deterministic across processes and hash seeds, is linear in practice with linear allocation, and leaves
every upstream production source byte-identical. Its guards were proved to still reject what they claim to
reject, rather than assumed to.

The one substantive judgement call — superseding ADR-0020 §7 rather than implementing it — is **correct**,
is argued on the right grounds (a refusal to fabricate intrabar order, *not* prefix stability), and is
pinned by a test so it cannot be silently reverted.

The strongest signal in the milestone is negative space: the one ordering rule this layer could have
duplicated does not exist in it, the one configuration it could have accepted is absent, and the one
primitive it might have needed was already there.
