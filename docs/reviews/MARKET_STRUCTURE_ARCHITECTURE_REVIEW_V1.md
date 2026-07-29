# Market Structure Architecture Review v1

**Type:** architecture audit — no production behaviour was added or changed
**Date:** 2026-07-29
**Reviewed at:** `main` = `1154622` (`Merge Structural Sequence State Foundation v1`)
**Covers:** ADR-0012 … ADR-0015, the whole of `src/fmis/market_structure/`
**Purpose:** audit the complete deterministic foundation *before* trend, BOS, CHoCH, liquidity,
evidence, signals or trading interpretation are introduced, and name the next milestone precisely.

---

## 1. Executive summary

The deterministic market-structure foundation is **sound and ready to build on**. Four milestones
(V, W, X, Y) produced a four-stage pipeline with no dependency cycles, no forbidden imports, no
interpretation vocabulary in production code, one authoritative implementation of every classification
rule, and 927 focused tests. **No P0 or P1 finding exists.** Nothing blocks the next milestone.

Five things are worth stating plainly because they shape what comes next:

1. **The package now has two stability classes**, and only one of them is non-repainting. Swing points,
   comparisons and labels are settled forever; `StructuralSequenceState` is a statement about the latest
   pair and is expected to be superseded. This is documented in six places and is correct — but it means
   the package currently offers **no prefix-stable view of how structure changed over time**.
2. **The single biggest gap is not a defect, it is an absence**: there is no historical record of state.
   Every later layer (trend, BOS, CHoCH) is defined over a *sequence*, and today the only sequence
   available is the label run, from which each consumer would re-derive its own sequencing. That is the
   duplication hazard this repository has repeatedly and correctly refused.
3. **BOS and CHoCH cannot be defined from the facts that currently exist.** Not because the primitives
   are weak, but because a break is a statement about *price crossing a level*, and after `detect_swings`
   no layer in this package ever reads a candle again. Implementing BOS requires a deliberate new input
   contract, not just a new rule. §15 sets out what must be decided first.
4. **The ordering rule exists twice** — once over `SwingPoint` runs in `relationships.py`, once over
   `SwingComparison` runs in `models.py`. They agree today and composition is proven safe over 6,535
   random runs, but they are two copies of one contract, which is precisely the drift risk the last
   milestone removed one layer up. P2, non-blocking, recommended for the milestone after next.
5. **Recommended next milestone: Structural Sequence State History Foundation v1** (Alternative D —
   one snapshot per unique candle index, outside-bar pairs applied atomically). It is the only
   alternative that both restores prefix stability and preserves the atomicity ADR-0015 §7 established.
   Measured: **0** snapshots changed under prefix extension across 120 random series, while the
   per-swing alternative exposed a spurious half-applied state in **12 of 120**.

---

## 2. Verified repository state

All 16 preconditions independently verified before any file was touched.

| # | Check | Result |
|---|---|---|
| 1 | branch | `main` |
| 2 | HEAD | `11546229dff55ed46316eae90907be005b974b0d` |
| 3 | subject | `Merge Structural Sequence State Foundation v1` |
| 4 | parent count | 2 |
| 5 | parent one | `b5f8723` |
| 6 | parent two | `6047e65` |
| 7 | `6047e65` ancestor of main | yes |
| 8 | working tree | clean |
| 9 | `git diff --check` | clean |
| 10 | pytest | 1773 passed |
| 11 | `-W error` | 1773 passed |
| 12 | `origin/main` | `f1a0d58` (unchanged) |
| 13 | ahead | 28 |
| 14 | pushed | nothing |
| 15 | unmerged branches | none — all 14 feature branches are ancestors of main |
| 16 | mutation artifacts | none tracked, none untracked |

---

## 3. Current architecture

Traced from code, not documentation.

```
CandleSeries                    (fmis.data — validated upstream)
    │  detect_swings(series, *, left_bars=2, right_bars=2)
    │    reads: candle.high, candle.low, series.closed()
    ▼
tuple[SwingPoint, ...]          index · timestamp · price · type
    │  compare_swing_sequence(points)
    │    reads: index, timestamp, price, type — never a candle
    ▼
tuple[SwingComparison, ...]     previous · current · relation
    │  label_swing_sequence(comparisons)
    │    reads: current.type, relation — never a price
    ▼
tuple[StructuralSwing, ...]     comparison · label
    │  derive_structural_sequence_state(structures)
    │    reads: current.type, label — no arithmetic, no comparison operators
    ▼
StructuralSequenceState         latest_high · latest_low · state
```

Per stage:

| | detect_swings | compare_swing_sequence | label_swing_sequence | derive_…_state |
|---|---|---|---|---|
| **input** | `CandleSeries` | `Iterable[SwingPoint]` | `Iterable[SwingComparison]` | `Iterable[StructuralSwing]` |
| **output** | `tuple[SwingPoint, …]` | `tuple[SwingComparison, …]` | `tuple[StructuralSwing, …]` | one `StructuralSequenceState` |
| **validation owner** | `CandleSeries` (upstream) + own bar-count checks | own point-order rule | `models._validate_current_point_order` | same shared rule |
| **ordering** | produces order | validates, never sorts | validates, never sorts | validates, never sorts |
| **immutability** | frozen+slotted, hashable | frozen+slotted, hashable | frozen+slotted, hashable | frozen+slotted, hashable |
| **prefix-stable** | yes (property-tested) | yes | yes | **no — by design** |
| **fact class** | historical | historical | historical | latest aggregate |
| **equal-index outside bars** | emits both | accepts both | accepts both | accepts both, resolves atomically |
| **object identity** | created | points reused whole | comparison reused whole | both swings reused whole |
| **owns which rule** | plateau + confirmation frontier | price relation | label mapping | state mapping + latest selection |

**No layer reimplements a lower layer's logic.** Verified by AST: `sequence_state.py` contains **0**
`BinOp` and **0** `Compare` nodes, so it cannot be re-deriving a relation or a label; `labels.py` calls
neither `detect_swings` nor any comparison function; no module below `swings.py` reads a candle field.

---

## 4. Public API inventory

`__all__` — 17 names, in dependency order:

```python
SwingType(str, Enum)                 HIGH · LOW
SwingPoint                           index · timestamp · price · type
SwingRelation(str, Enum)             HIGHER · LOWER · EQUAL
SwingComparison                      previous · current · relation
StructuralSwingLabel(str, Enum)      HIGHER_HIGH · LOWER_HIGH · EQUAL_HIGH ·
                                     HIGHER_LOW · LOWER_LOW · EQUAL_LOW
StructuralSwing                      comparison · label
StructuralSequenceStateType(str,Enum) SHIFTED_HIGHER · SHIFTED_LOWER · EXPANDED ·
                                     CONTRACTED · UNCHANGED · INSUFFICIENT_STRUCTURE
StructuralSequenceState              latest_high · latest_low · state

detect_swings(series: CandleSeries, *, left_bars: int = 2, right_bars: int = 2) -> tuple[SwingPoint, ...]
compare_swings(previous: SwingPoint, current: SwingPoint) -> SwingComparison
compare_swing_sequence(points: Iterable[SwingPoint]) -> tuple[SwingComparison, ...]
label_swing(comparison: SwingComparison) -> StructuralSwing
label_swing_sequence(comparisons: Iterable[SwingComparison]) -> tuple[StructuralSwing, ...]
derive_structural_sequence_state(structures: Iterable[StructuralSwing]) -> StructuralSequenceState
required_candles(left_bars: int, right_bars: int) -> int
DEFAULT_LEFT_BARS = 2 · DEFAULT_RIGHT_BARS = 2
```

Submodules: `labels`, `models`, `relationships`, `sequence_state`, `swings`.

- **Collisions:** none — `set(submodules) & set(__all__) == set()`.
- **Mutable exports:** none.
- **Accidental helper exports:** none — `_relation_for`, `_label_for`, `_validate_current_point_order`,
  `_sequence_state_for`, `_LABEL_BY_TYPE_AND_RELATION`, `_STATE_BY_LABEL_PAIR` are all unreachable from
  the package namespace.
- **Duplicated conceptual types:** none. `SwingRelation` and `decision_support.Comparison` are adjacent
  concepts but deliberately distinct (ADR-0013 documents why: the latter models possibly-missing values).
- **Backward compatibility:** every name from milestones V, W and X is still exported; the API has only
  ever grown (6 → 11 → 14 → 17).

**Assessment.** Minimal (nothing exported that is not used by a caller), coherent (one verb per stage,
one noun per fact), consistently named (`*_swing` / `*_swings` / `*_sequence` follow the arity), free of
trend or trading vocabulary, and extension-ready — a new stage can be added as a submodule plus exports
without touching any existing one, which is exactly how Y was added.

One naming observation, not a defect: `StructuralSequenceStateType` is the only `*Type` suffix on a
non-`SwingType` enum, forced by the model claiming the shorter name. It reads acceptably and the
alternative (renaming the model) would break a merged API for style. Left alone.

---

## 5. Contract-ownership map

| # | Contract | Authoritative owner | Single? | Reused not copied | Location apt | Runtime-enforced | Test-pinned | Documented |
|---|---|---|---|---|---|---|---|---|
| 1 | candle validation | `fmis.data.CandleSeries` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0012 |
| 2 | swing detection | `swings._is_swing_high/_low` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0012 §2 |
| 3 | confirmation frontier | `detect_swings` loop bounds | ✔ | ✔ | ✔ | ✔ | ✔ (prefix property) | ADR-0012 §2–3 |
| 4 | plateau policy | `_is_swing_high/_low` (strict left, `>=` right) | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0012 §6 |
| 5 | outside-bar emission order | `detect_swings` sort key | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0012 |
| 6 | comparison relation | `models._relation_for` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0013 §4, §6 |
| 7 | structural label | `models._label_for` / `_LABEL_BY_TYPE_AND_RELATION` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0014 §1, §6 |
| 8 | sequence ordering | **two implementations — see below** | ✘ | ✘ | ✔ | ✔ | ✔ | ADR-0013 §5, ADR-0014 §7–9, ADR-0015 §9 |
| 9 | latest-HIGH selection | `derive_structural_sequence_state` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0015 §1 |
| 10 | latest-LOW selection | same | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0015 §1 |
| 11 | aggregate state mapping | `models._sequence_state_for` / `_STATE_BY_LABEL_PAIR` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0015 §2, §10 |
| 12 | insufficient structure | `models._sequence_state_for` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0015 §6 |
| 13 | object consistency | each model's `__post_init__` | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0014 §5, ADR-0015 §3 |
| 14 | immutability | `@dataclass(frozen=True, slots=True)` | ✔ | ✔ | ✔ | ✔ | ✔ | all four ADRs |
| 15 | equality policy | `models._relation_for` (exact floats) | ✔ | ✔ | ✔ | ✔ | ✔ | ADR-0013 §4 |

### The one contract with two owners (#8)

`relationships.compare_swing_sequence` validates `SwingPoint` runs with an inline loop;
`models._validate_current_point_order` validates `SwingComparison` runs. Both implement the same four
checks — non-decreasing index, non-decreasing timestamp, equal index requires equal timestamp, strict
within each `SwingType` — and both carry near-identical message text (`"must be ordered by"`,
`"shares …"`, `"repeats or precedes"`).

- **Not a behavioural divergence.** A naive differential is meaningless because the two take different
  inputs (points vs the *current* points of comparisons). The property that matters is composition, and
  it holds: over 20,000 random point runs, **6,535** were accepted upstream and **0** were rejected
  downstream.
- **It is a drift risk.** A future change to per-type strictness applied in one place and not the other
  would leave `detect_swings` output and labelling input contracts silently disagreeing.
- Classified **P2**. The fix (a shared rule over `(index, timestamp, type)` triples, with the point and
  comparison layers both adapting onto it) is a small, self-contained refactor. It should not be bundled
  into the next feature milestone; recommended as its own narrow hygiene milestone afterwards.

---

## 6. Data-model classification

| Model | Represents | Responsibilities | Verdict |
|---|---|---|---|
| `SwingPoint` | **atomic fact** | one located extreme | single responsibility |
| `SwingComparison` | **relationship** | two points + their numeric relation | single responsibility |
| `StructuralSwing` | **classification** | a comparison + its conventional name | single responsibility |
| `StructuralSequenceState` | **latest-state aggregate** | two latest sides + their joint state | single responsibility |

Verified for all four: frozen, slotted, hashable, no `__dict__`, no duplicated derived field, no
constructible invalid state (an exhaustive sweep of all 6 states × 9 pairs found **0** holes), no circular
object graph (the graph is a strict DAG: state → swing → comparison → point), and no stored value that
can disagree with its source — every derived field is recomputed and compared in `__post_init__`.

`latest_high` / `latest_low` are the only optional fields and represent a genuinely missing fact ("no
labelled swing of this side yet"), not a null placeholder. Source objects are preserved by **identity**,
not rebuilt — confirmed in both outside-bar orders. The aggregate does not claim historical permanence:
its own docstring, the module docstring and ADR-0015 §8 all state the opposite.

**No model mixes more than one responsibility.** No refactor recommended.

---

## 7. Ordering and outside-bar semantics

All eight ordering properties verified end to end: non-decreasing global index and timestamp; equal index
requires equal timestamp; strict per-`SwingType` index and timestamp growth; input order preserved; no
silent sorting (unsorted input raises); no mutation (by value **and** by identity).

Both legal outside-bar orders were exercised at every stage. HIGH→LOW and LOW→HIGH are both accepted and
both yield `expanded` for the same pair; the two results are `==`; and `latest_high`/`latest_low` are the
identical objects in both orders. Atomicity is real, not vacuous: with a *falling* outside bar, applying
the HIGH half alone reads `CONTRACTED` while the complete pair reads `SHIFTED_LOWER`.

**Vocabulary: unified, with one implicit concept.** The package consistently distinguishes four ordering
notions — *source order* (input order, preserved), *chronological order* (index and timestamp,
non-decreasing), *per-type order* (strict), *equal-index order* (inherited from input, never imposed).
ADR-0014 §8 states the last of these explicitly and tests pin both directions.

The one **implicit** concept is the fifth: *emission order at an equal index*. `detect_swings` guarantees
HIGH before LOW, but implements it as `sorted(..., key=lambda point: (point.index, point.type.value))` —
which works only because the string `"high"` sorts before `"low"`. The guarantee is documented and tested
at the output, but the mechanism is alphabetical coincidence: renaming `SwingType.HIGH.value` to, say,
`"peak"` would silently invert it. **P3** — the tie-break should be expressed by an explicit ordering
rather than left to depend on enum string values.

Aggregate update order is unambiguous: the whole run is evaluated, then one state is derived.

---

## 8. Stability semantics

Two guarantee classes, and the package is precise about which is which.

| | `SwingPoint` · `SwingComparison` · `StructuralSwing` | `StructuralSequenceState` |
|---|---|---|
| immutable | yes | yes |
| prefix-stable | **yes** (0 revisions across 60 random series × every prefix) | **no — by design** |
| deterministically recomputable | yes | yes |
| superseded by newer data | no | yes |
| repainting | never | not applicable — supersession is not revision |
| historical revision | never | never (a new object; the old one is not altered) |

A scan of `src/fmis/market_structure/`, ADR-0012 through ADR-0015, both `AI_HANDOFF` documents and
`REPOSITORY_MAP.md` for `non-repainting`, `never revised`, `prefix-stab*`, `permanent` and `cache` found
**28 occurrences** once the sentences that already carry the aggregate caveat are excluded. (A looser
repository-wide search over the full term list — adding `stable`, `immutable`, `historical`, `latest`,
`superseded`, `recomputed` — touches 21 files, mostly unrelated prose.) Every one of the 28 is correctly
scoped: each `non-repainting` claim attaches to detection, comparison or labels,
never to the aggregate. Six places carry the explicit warning, including a call-out block in
`START_HERE_FOR_AI` and a consequence paragraph in ADR-0015.

**No statement was found that could lead a consumer to cache the latest aggregate as a permanent
historical fact.** The two older documents (`ARCHITECTURE_AND_ROADMAP_V1`, `ARCHITECTURE_REVIEW_2026-07-24`)
mention repainting only in the context of the closed-candle rule and predate this package.

The honest consequence: because the aggregate is deliberately not prefix-stable, **the package today
offers no stable historical view of structural change**. That is not a defect — it is the gap §14 fills.

---

## 9. Equality semantics

Equality is first-class at every stage and survives to the end:

```
prices equal → SwingRelation.EQUAL → EQUAL_HIGH / EQUAL_LOW → UNCHANGED (labels retained)
```

Verified: `EQUAL` is one of three relation members and is never folded into HIGHER/LOWER; both equality
labels are reachable from real detector output; the five equality-containing combinations resolve to
**three** distinct states, not one; and both source labels remain readable on the state, so the grouping
is information-preserving.

**No hidden tolerance.** An AST scan of every module found no `isclose`, `epsilon`, `tolerance`, `atol`,
`rtol`, `approx`, `round`, `decimal`, `tick`, `atr` or `percent` token. Comparison is exact on stored
floats, as ADR-0013 §4 records.

Observed float behaviour, deterministic and worth stating: `0.1 + 0.2` compares `LOWER` than `0.3`;
`-0.0` and `0.0` compare `EQUAL`; `Decimal` is **rejected** by `SwingPoint` (`price must be a number`);
`int` is accepted and stored as-is (`5`, not `5.0`) — harmless, since comparison is numeric, but worth
knowing.

### Where future tolerance should live — recommendation

**Before `SwingPoint` creation, as an explicit normalization policy owned outside this package.**

Reasoning. A tolerance is a claim about *instrument precision* — "these two prices are the same tick" —
and it needs tick-size or price-precision metadata that exists nowhere in this repository today. Placing
it in structural comparison would mean:

- `models._relation_for` would need instrument metadata it deliberately does not receive, which would
  drag symbol/venue context into an atomic layer (§16 argues against exactly that);
- equality would become configurable, so `EQUAL_HIGH` would stop being a property of the data and start
  being a property of a setting — and every historical fact would become non-reproducible without its
  setting;
- the plateau rule in `detect_swings` would still use exact comparison, so two layers would disagree
  about what "the same price" means.

Normalizing at ingestion instead (quantise prices to the instrument's tick before a `Candle` is built)
keeps every downstream layer exact, keeps facts reproducible, and makes the policy visible in one place.
It requires a tick-size model first, which is its own prerequisite milestone. **Do not implement
tolerance inside `market_structure` under any circumstances.**

---

## 10. Dependency graph

```
fmis.market_structure/__init__  →  labels, models, relationships, sequence_state, swings
labels                          →  models
relationships                   →  models
sequence_state                  →  models
swings                          →  models, fmis.data
models                          →  (nothing)
```

- **Cycles:** none.
- **External `fmis` dependencies:** `fmis.data` only, and only from `swings.py`.
- **Forbidden dependencies:** none of `decision_support`, `evidence`, `pipeline`, `providers`,
  `execution`, `portfolio`, `features`, `trading_context`, `relative_value`, `ingest`, `alignment`.
- **Reverse dependencies:** nothing in `src/fmis` imports this package. Four files mention the string
  "market_structure" — `evidence/families.py` (`EvidenceFamily.MARKET_STRUCTURE`), `features/__init__.py`,
  `features/types.py`, `features/support_resistance/__init__.py` — all textual, **no imports**.
- **Third-party:** none; stdlib only.

`models.py` is now 599 lines and holds every value type plus four private rules. Does concentrating the
rules there create undesirable coupling? **No.** All four are pure functions over this package's own
value types, `models` imports nothing, and the alternative — a separate `_rules.py` — would add a module
without removing an edge. The one thing that *would* justify moving is if a rule needed an external
input (tick size, candles); §9 and §15 both argue such a rule belongs outside the package entirely. Left
in place, as instructed.

---

## 11. Test-architecture assessment

| File | Collected | Functions | Parametrized | Property | Seeded RNGs |
|---|---|---|---|---|---|
| `test_market_structure_swings.py` | 194 | 62 | 9 | 5 | 5 |
| `test_market_structure_relationships.py` | 228 | 69 | 12 | 6 | 6 |
| `test_market_structure_labels.py` | 193 | 69 | 8 | 5 | 5 |
| `test_market_structure_sequence_state.py` | 312 | 93 | 14 | 7 | 7 |
| **total** | **927** | **293** | **43** | **23** | **23** |

Guards present in every file: public-API set, import-boundary set, stdlib-only, interpretation-vocabulary
scan (AST code tokens, docstrings excluded), approximate-equality scan. Submodule-collision guards in
three of four. Exact-message contracts in two.

**Independent oracles.** Each layer's oracle is written in a different formulation from production:
labels derive the name from the naming convention (`"{relation}_{type}"`) rather than the lookup table;
sequence state derives from outward/inward/static movement rather than the 9-cell table. This review
added a **third**, price-sign-based oracle for verification — 9/9 agreement.

**Findings.**

- *Test-count inflation:* real. 927 collected from 293 functions; 23 property functions contribute
  roughly 400 seeded cases. The counts in `CURRENT_STATE` are accurate as collection counts but should
  not be read as 927 independent scenarios.
- *Weak substring assertions:* **57** `pytest.raises(match=...)` sites remain, against just **2**
  exact-equality (`==`) message contracts — both added by the last milestone, expanding to 4 collected
  cases through parametrization. Per file, the substring counts are swings 9, relationships 18, labels 12,
  sequence_state 18. This is the
  class of weakness that let a reworded message through in Milestone Y. **P3** — worth converting the
  ordering-message assertions in `relationships.py` (the second copy of the rule, §5 finding) to exact
  matches, so the two copies can be proven to agree rather than assumed to.
- *Vacuous outside-bar tests:* none remaining. The one that existed was corrected during the Y review;
  the current atomicity test is discriminating (`CONTRACTED` vs `SHIFTED_LOWER`).
- *Missing integration seams:* `test_market_structure_relationships.py` and `..._swings.py` have **no
  full-chain test** (0 uses of a `chain()` helper); only labels (9) and sequence_state (4) exercise
  candles→state. The chain is covered, but only from the top two layers. **P3.**
- *Tests that might pass despite a broken architecture:* one class identified — nothing asserts that the
  **point-level** and **comparison-level** ordering rules agree. Each is tested against itself. A
  divergence introduced in one would be caught only if it happened to break a composition test.
  **P2**, same root cause as §5.
- *Duplicated or overspecified tests:* the three API/submodule/import guards are deliberately repeated
  across files (each file guards the package from its own perspective). This is redundancy, not
  duplication, and it is what caught the API growth in Milestone Y three times over. Keep.

No test should be weakened. Recommended additions are listed in §17 under P2/P3.

---

## 12. Performance assessment

Measured on synthetic random series (single run, wall clock):

| candles | `detect_swings` | `compare_swing_sequence` | `label_swing_sequence` | `derive_…_state` | points |
|---|---|---|---|---|---|
| 1,000 | 0.0010 s | 0.0002 s | 0.0002 s | 0.0001 s | 397 |
| 5,000 | 0.0048 s | 0.0013 s | 0.0009 s | 0.0002 s | 2,028 |
| 20,000 | 0.0193 s | 0.0043 s | 0.0038 s | 0.0010 s | 8,039 |
| 80,000 | 0.0885 s | 0.0181 s | 0.0265 s | 0.0040 s | 32,123 |

| Transformation | Time | Memory | Full rescan | Incremental later? |
|---|---|---|---|---|
| `detect_swings` | O(n · (left+right)) → linear at fixed bars | O(n) | yes | yes — confirmation frontier makes the window bounded |
| `compare_swing_sequence` | O(k) | O(k) | yes | yes — one pass, per-type running latest |
| `label_swing_sequence` | O(k) | O(k) | yes | yes — each label depends on one comparison |
| `derive_…_state` | O(k) | O(1) beyond input | yes | yes — a running fold |

Everything is linear and everything rescans. At 80,000 candles the whole chain is ~0.13 s, so a backtest
over 100 symbols × 5 timeframes × 80k candles is roughly 65 s of structure derivation — acceptable, and
dominated by data loading in any realistic pipeline.

**Verdict: acceptable current implementation, no correctness problem, no optimisation warranted now.**
The one thing worth recording for later: every stage is a *fold over an ordered sequence*, so all four
admit incremental derivation without changing their contracts. If repeated recomputation ever becomes hot
— most likely under walk-forward backtests that re-derive from bar 0 at every step — the fix is an
incremental adapter above these functions, not a rewrite of them. **Do not build it speculatively.**

---

## 13. Readiness for future layers

| | Milestone | Primitives sufficient? | Additional facts required | Consumes | Needs history? | Depends on |
|---|---|---|---|---|---|---|
| A | Structural State **Transition** | yes | none | `StructuralSequenceState` ×2 | — | — |
| B | Structural State **History** | **yes** | none | `StructuralSwing` | produces it | — |
| C | **Trend** Foundation | mostly | a swing-count/persistence policy | both | **yes** | B |
| D | **Break of Structure** | **no** | price-vs-level crossing; close-vs-wick policy; protected-level rule | both + `CandleSeries` | yes | B, plus a new level-crossing layer |
| E | **Change of Character** | **no** | everything D needs, plus prior-BOS direction | BOS sequence | yes | D |
| F | **Liquidity / Sweep** | **no** | level crossing **and** return; a "sweep" definition | both + candles | yes | D |
| G | **Multi-timeframe** | yes, structurally | an envelope carrying symbol/timeframe; an alignment policy | envelopes | no | orthogonal |
| H | **Evidence generation** | not yet | something that *classifies*, per ADR-0011 §1 | whatever C/D/E produce | yes | C or D |

Risk notes per layer:

- **A (transition)** — low technical risk, but the API cannot validate that two supplied states are
  adjacent or even from the same series. That is the "plausible-looking shortcut around the invariants"
  hazard ADR-0013 §6 and ADR-0014 §6 both removed. Subsumed by B (a transition is a pair of adjacent
  snapshots), so it should not be a separate milestone.
- **B (history)** — no new facts needed, restores prefix stability, no interpretation. Lowest risk of
  the eight.
- **C (trend)** — high risk of embedding interpretation too early. "How many swings make a trend" has no
  objective answer; it is a policy, and it must be stated as one. No repainting risk if built on B.
- **D (BOS)** — highest architectural risk, because it needs `CandleSeries` at a layer that currently
  never sees one. Also the highest repainting risk: a break detected on a forming candle is exactly the
  provisional output ADR-0012 forbids.
- **E (CHoCH)** — **circularity risk is real.** The conventional definition ("a break against the
  prevailing trend") makes CHoCH depend on trend, and trend is often defined by breaks. §15 sets out the
  way to break the cycle.
- **F (liquidity/sweep)** — needs a crossing *and* a return within some window; both the window and
  "return" are policies. Strong transient risk around outside bars.
- **G (multi-timeframe)** — structurally ready today; see §16.
- **H (evidence)** — premature by ADR-0011 §1: nothing here classifies anything yet, and naming or
  describing a fact is not classification.

**Dependency order:** B → C → (level-crossing prerequisite) → D → E → F, with G orthogonal and H last.

---

## 14. Transition/history alternative analysis

| | A: compare two states | B: transitions from swing run | C: snapshot per swing | D: snapshot per index group | E: skip to trend |
|---|---|---|---|---|---|
| deterministic definition | yes, but adjacency unverifiable | yes | yes | yes | n/a |
| outside-bar behaviour | invisible (already atomic) | needs an explicit policy | **exposes the transient** | atomic, matches ADR-0015 §7 | n/a |
| transient-state risk | none | policy-dependent | **high — measured** | none | n/a |
| retains cause | only by identity diffing | yes | yes | yes — the triggering swing group | n/a |
| prefix behaviour | inherits caller's | stable | stable | **stable — measured 0/120** | n/a |
| API complexity | one type, one function | one type, one function | one function | one type, one function | none |
| useful for BOS/CHoCH | partially | yes | yes | yes | insufficient |
| duplicates state derivation | no | **yes, unless it calls the same rule** | yes, same caveat | yes, same caveat | n/a |
| snapshots retain triggering facts | no | yes | yes | yes |  n/a |

Measured evidence (audit probe, 120 random series, not committed):

- **Alternative D:** snapshots that changed under prefix extension: **0**.
- **Alternative C:** series exposing a half-applied outside-bar state: **12 of 120**.

Worked example — a falling outside bar following an unchanged pair:

```
C: ['insufficient_structure', 'unchanged', 'contracted', 'shifted_lower']
D: ['unchanged', 'shifted_lower']
```

C reports `contracted` at a bar whose complete structural fact is `shifted_lower`. That state never
existed; it is an artefact of emission order. ADR-0015 §7 decided against exposing exactly this.

**Rejections.**

- **A** rejected: cannot validate adjacency or common provenance, and it is subsumed by D.
- **B** rejected: transitions without the snapshots between them discard the states themselves, and it
  still needs D's grouping policy to know what a transition is at an outside bar.
- **C** rejected on measured evidence: it contradicts a merged ADR and fabricates states in 10% of random
  series.
- **E** rejected: trend defined directly over labels would re-derive sequencing inside the trend layer —
  the duplication this repository has consistently refused, and the exact hazard §5 already flags once.

---

## 15. BOS / CHoCH prerequisite analysis

Deliberately no definitions are proposed here.

**Facts currently available:** confirmed swing highs and lows with index, timestamp, exact extreme price
and type; same-type numeric relations; the six structural labels; the latest HIGH/LOW pair and its joint
state; a guarantee that all of these are non-repainting.

**Facts not currently available:**

1. **Any candle after a swing.** After `detect_swings`, no layer reads a candle. There is therefore no
   fact of the form "price traded above level L at bar i".
2. **Close vs wick.** `SwingPoint` stores only the extreme (`candle.high` or `candle.low`). Whether a
   *close* crossed a level is not derivable from swings alone — it requires the candles back.
3. **A protected / reference level.** Nothing marks any swing as "the" level a break would be measured
   against.
4. **Directional context.** No trend, regime or bias exists — deliberately.
5. **Event time.** Swings carry the pivot's timestamp; a break happens at a *different* bar, and no fact
   currently carries that bar.

**Answers the audit can give now:**

- *Does a structural label alone prove a break?* **No.** `HIGHER_HIGH` says the next confirmed pivot high
  exceeded the previous one — a statement about two pivots, made `right_bars` late. A break, as normally
  meant, is a statement about price crossing a level at a specific bar. These are different facts and one
  does not imply the other.
- *Is a `SwingPoint` price crossing enough?* Only if "crossing" is defined pivot-to-pivot, which yields a
  lagging, coarse notion that most consumers would not recognise as BOS.
- *Is close confirmation required?* That is a **policy decision** requiring its own ADR. It is also the
  decision that determines whether the result can be non-repainting: a close-based break on a closed
  candle can be; a wick-based break on a forming candle cannot.

**Decisions requiring explicit future policy, before any code:**

1. wick crossing vs close crossing vs both as separate facts;
2. which level is protected, and when it stops being protected;
3. whether an `EQUAL_HIGH` breaks anything;
4. how an outside bar that crosses both sides is grouped and ordered;
5. whether a break is reported at the crossing bar or at the next confirmed swing;
6. what happens when a level is crossed inside the confirmation window of a later swing.

**Breaking the trend/CHoCH circularity.** Define BOS **purely on levels**, with no reference to trend or
regime. Then define CHoCH over the *BOS sequence* — the first break opposing the direction of the
previous break — so it depends on BOS and never on trend. Trend then becomes a *summary* of the BOS/state
history, consuming both and defining neither. Any definition in which trend is an input to BOS should be
rejected on sight.

**Must remain postponed:** BOS, CHoCH, trend, support/resistance, liquidity, sweep, double top/bottom,
regime, bias, and every evidence descriptor for market structure.

**Architectural consequence worth flagging now:** BOS needs a layer that reads *both* swing levels and
candles. That is a new input contract for this package, and it deserves its own ADR deciding whether such
a layer lives inside `fmis.market_structure` (reintroducing a `CandleSeries` dependency below
`detect_swings`) or in a new sibling package that consumes both. **Recommendation: a sibling package**,
so `market_structure` keeps its property that only its first stage touches candles.

---

## 16. Multi-timeframe readiness

Structurally ready.

- **No hidden global state:** zero `global` statements; no module-level mutable object; both mappings are
  `MappingProxyType`.
- **No shared-granularity assumption:** nothing compares two sequences; nothing merges.
- **No metadata leakage:** `SwingPoint`, `SwingComparison`, `StructuralSwing` and
  `StructuralSequenceState` carry **no** symbol, timeframe, venue, source or run identifier.
  `detect_swings` receives a `CandleSeries` that has `symbol` and `timeframe` but reads neither.
- **No premature merge logic:** none exists.

The one caution: `SwingPoint.index` is a position in `series.closed().candles`, so an index is only
meaningful relative to the series that produced it. Two timeframes' indices are not comparable —
`timestamp` is the only cross-timeframe key. Any future MTF layer must join on timestamps, never indices.
This is documented in `models.py` but is worth restating in whatever ADR introduces MTF.

**Where context belongs — recommendation.**

| Context | Belongs in | Why |
|---|---|---|
| symbol, timeframe, venue | an **envelope/snapshot** wrapping a derived structural run | keeps atomic facts small and universally reusable; one place to disagree instead of thousands |
| source / provider | **pipeline metadata**, alongside existing provenance | it describes how data arrived, not what the structure is |
| analysis run identifier | **pipeline metadata** | it is an execution concern with no structural meaning |
| objective / intent | `fmis.trading_context` (already exists) | ADR-0009 already owns this boundary |

Putting symbol or timeframe onto `SwingPoint` would multiply the same two strings across every point,
create a second source of truth against `CandleSeries`, and break the model's current property of being a
pure geometric fact. Recommended shape when MTF arrives: a frozen envelope holding *(context, points,
comparisons, structures, state)* — with the atomic types untouched.

---

## 17. Findings

### P0 — correctness or data corruption
**None.**

### P1 — architectural defect blocking the next milestone
**None.** The recommended next milestone requires no new facts and no correction first.

### P2 — real but non-blocking

**P2-1 — The sequence-ordering contract has two implementations.**
`relationships.compare_swing_sequence` (over `SwingPoint`) and `models._validate_current_point_order`
(over `SwingComparison`) implement the same four checks with near-identical message text. They agree
today — composition verified over 6,535 accepted runs with 0 downstream rejections — but nothing
*enforces* that they agree, and a change to one would silently diverge from the other.
*Recommendation:* a narrow hygiene milestone after the next feature milestone — one rule over
`(index, timestamp, type)` triples, both layers adapting onto it. Do not bundle it into feature work.

**P2-2 — Nothing tests that the two ordering rules agree.**
Each is tested against itself. A divergence would be caught only incidentally.
*Recommendation:* a differential test over the shared domain, added with P2-1's fix.

### P3 — optional improvement

**P3-1 — The equal-index tie-break depends on enum string values.**
`detect_swings` sorts by `(index, type.value)`, which puts HIGH first only because `"high" < "low"`.
The guarantee is documented and tested at the output; the mechanism is coincidental.

**P3-2 — 57 of the 59 error-message assertion sites are substring matches.**
This is the weakness that allowed a reworded message through in Milestone Y. The ordering messages in
`relationships.py` are the highest-value candidates for exact matching.

**P3-3 — No full-chain test in the swings and relationships suites.**
Both cover their own layer thoroughly but never run candles → state.

**P3-4 — `__init__.py` docstring says "two layers" while listing four stages.** Stale prose. *Corrected
in this review* (see §20).

**P3-5 — `CURRENT_STATE.md` header still names `b5f8723` as the latest commit** with a note to update it
after committing Milestone Y. *Corrected in this review* (see §20).

### P4 — stylistic
**P4-1** — `StructuralSequenceStateType` is the only `*Type`-suffixed non-`SwingType` enum. Renaming
would break a merged API for style; not recommended.
**P4-2** — `models.py` is 599 lines. Cohesive and dependency-free; splitting would add a module without
removing an edge. Not recommended.

---

## 18. Recommended next milestone

### **Structural Sequence State History Foundation v1** — Alternative D

Emit one `StructuralSequenceState` snapshot per **unique current candle index**, with an outside-bar
HIGH/LOW pair applied atomically before that index's snapshot is produced. Each snapshot retains the
`StructuralSwing` objects that triggered it.

**Why this one:**

1. **It requires no new facts.** Everything it needs exists and is proven.
2. **It restores the guarantee the package currently lacks.** Snapshots are prefix-stable — measured 0
   changes across 120 random series and every prefix — turning "the latest state" into a *history of
   historical facts*, which is what every later layer actually needs.
3. **It is the only alternative consistent with ADR-0015 §7.** Alternative C fabricates a state that never
   existed in 10% of random series.
4. **It subsumes transitions.** A transition is a pair of adjacent snapshots, so Alternative A becomes
   unnecessary rather than deferred.
5. **It unblocks trend, BOS and CHoCH simultaneously** without committing to any of their definitions.

**Constraints it must respect** (to be fixed in its own ADR):

- one authoritative state mapping — it must call `models._sequence_state_for`, never re-derive;
- one authoritative ordering rule — reuse, do not copy (and note P2-1 before adding a third copy);
- snapshots are historical facts and **must** be prefix-stable; this must be property-tested;
- the grouping key is the `current` index, and equal-index grouping must be tested in both orders;
- no transition *interpretation* — no "improving", "weakening", "breaking", direction or magnitude;
- `EvidenceFamily.MARKET_STRUCTURE` stays empty.

### Explicit non-goals for the next milestone

Trend, BOS, CHoCH, break of structure, continuation, reversal, breakout, support, resistance, liquidity,
sweep, double top/bottom, regime, bias, direction, confidence, score, signals, evidence descriptors,
multi-timeframe merging, tolerance/tick-size handling, incremental or streaming derivation, and any
consumption of `CandleSeries` below `detect_swings`.

---

## 19. Validation results

| Check | Result |
|---|---|
| market-structure suite | 927 passed |
| architecture tests | 19 passed |
| data-model tests | 50 passed |
| evidence taxonomy | 77 passed |
| full pytest | 1773 passed |
| `python -W error -m pytest -q` | 1773 passed |
| `git diff --check` | clean |
| public API probe | `__all__` = 17, backward compatible |
| namespace-collision probe | none |
| import-boundary probe | `fmis.data` only |
| dependency-cycle probe | none |
| nine-case sequence-state probe | 9/9 vs a third independent oracle |
| equality reachability probe | `EQUAL` → `EQUAL_HIGH`/`EQUAL_LOW` → `UNCHANGED`, labels retained |
| outside-bar probes (both orders) | identical state, identity preserved |
| prefix-stability probe (historical facts) | 0 revisions across 60 random series |
| aggregate-evolution probe | `shifted_higher` → `expanded`, sources unchanged |
| deterministic-repeatability probe | equal results |
| invalid-manual-construction probe | 0 of 45 wrong constructions accepted |
| scope-guard scan | 0 banned tokens in production code |

---

## 20. Files changed by this review

Documentation only. No production behaviour was added or changed.

| File | Change | Why |
|---|---|---|
| `docs/reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md` | new | this report |
| `docs/README.md` | one index line | make the review discoverable |
| `src/fmis/market_structure/__init__.py` | `"two layers"` → `"four stages"` | P3-4: prose contradicted the four-stage list directly beneath it |
| `docs/AI_HANDOFF/CURRENT_STATE.md` | header commit hash | P3-5: still named `b5f8723` with a note to update after committing Y |

Both code-adjacent edits are pure prose inside a docstring or a header line, cannot alter architecture or
behaviour, and are permitted by the review's own defect policy. `CURRENT_STATE` was **not** changed to
claim any new production feature.
