# Structural Sequence State History Foundation v1 — Design

**Type:** design and specification only — no production code, no repository change
**Date:** 2026-07-29
**Designed against:** `main` = `8535a98` (`Merge Market Structure Architecture Review v1`), tree clean
**Follows:** the recommendation in `docs/reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md` §18
**Would become:** ADR-0016, implemented across milestones Z0–Z2 (§11)

> **Status: proposal.** Nothing here is authorization to implement. Section 12 lists five questions that
> should be answered first; two of them can change the public shape of the API.

---

## 1. Purpose and scope

### 1.1 The gap this fills

`derive_structural_sequence_state` answers *"what is the structure now?"*. It deliberately does not
answer *"how did it get here?"*, and by design its output is superseded rather than accumulated
(ADR-0015 §8). The package therefore has no prefix-stable view of structural change over time.

Every plausible next layer — trend, break of structure, change of character — is defined over a
*sequence* of structural states. Without a history layer each of them would derive its own sequencing
from the label run, which is the duplication this repository has repeatedly refused (ADR-0013 §6,
ADR-0014 §6, ADR-0015 §9, and P2-1 in the architecture review).

### 1.2 What this layer is

A **fold** over an ordered `StructuralSwing` run that emits **one immutable snapshot per candle index at
which structure changed**, each snapshot carrying the state at that moment and the swings that caused it.

### 1.3 What this layer is not

Not a trend. Not a break of structure. Not a change of character. Not a regime, bias, direction,
strength, confidence or score. Not a signal. Not evidence. It **describes** a sequence of already-settled
facts; it does not read them.

The deterministic/interpretive boundary is unchanged and absolute:

```
  DETERMINISTIC (this layer and everything below it)
    candles → swing points → comparisons → labels → state → state history
    pure functions · exact comparison · no thresholds · no parameters beyond bar counts
  ─────────────────────────────────────────────────────────────────────────
  INTERPRETIVE (later, separate modules, each with its own ADR)
    trend · BOS · CHoCH · liquidity · evidence · scenarios · AI narrative
    policies · thresholds · judgement · confidence
```

Nothing in this layer may be parameterised by a threshold, a lookback, a tolerance or an option. If a
question needs a knob, it belongs above the line.

---

## 2. Repository audit

Verified at `8535a98`, working tree clean, 1773 tests passing.

### 2.1 What exists today

| Module | Public surface | Private rules |
|---|---|---|
| `models.py` (599 lines) | `SwingType`, `SwingPoint`, `SwingRelation`, `SwingComparison`, `StructuralSwingLabel`, `StructuralSwing`, `StructuralSequenceStateType`, `StructuralSequenceState` | `_relation_for`, `_label_for`, `_validate_current_point_order`, `_sequence_state_for`, `_LABEL_BY_TYPE_AND_RELATION`, `_STATE_BY_LABEL_PAIR` |
| `swings.py` | `detect_swings`, `required_candles`, `DEFAULT_LEFT_BARS/RIGHT_BARS` | `_require_bars`, `_is_swing_high`, `_is_swing_low` |
| `relationships.py` | `compare_swings`, `compare_swing_sequence` | — (ordering validated inline — see §7) |
| `labels.py` | `label_swing`, `label_swing_sequence` | — |
| `sequence_state.py` | `derive_structural_sequence_state` | — |

Dependency graph is acyclic; `models` imports nothing; only `swings` touches `fmis.data`.

### 2.2 Everything State History touches

| Area | Affected because |
|---|---|
| `models.py` | gains the snapshot type; may gain a private grouping helper |
| new `state_history.py` | the derivation itself |
| `__init__.py` | three new exports, pipeline docstring, package rules |
| 4 existing test files | API-set, submodule-set and import-boundary guards enumerate the package and **will fail by design** |
| ADR index + new ADR-0016 | the decision record |
| `CURRENT_STATE`, `REPOSITORY_MAP`, `START_HERE_FOR_AI` | pipeline description, counts, stability semantics |
| architecture review | its §18 recommendation becomes implemented; add a pointer, do not rewrite history |

**Not affected, and must stay that way:** `swings.py`, `relationships.py`, `labels.py`,
`sequence_state.py` (all four are complete for this purpose), `fmis.data`, `fmis.evidence`,
`fmis.decision_support`, `fmis.pipeline`, `fmis.providers`, `fmis.trading_context`.

### 2.3 Precedent checks performed

- `@property` on frozen dataclasses is **established precedent** — 21 uses across the repo, including
  `decision_support.report` and `features.volume.statistics`. It is not yet used in `market_structure`.
- No `global`, no module-level mutable state anywhere in the package.
- Both existing mappings are `MappingProxyType`.
- Every value type is `frozen=True, slots=True` and hashable.

---

## 3. Domain design

### 3.1 Purpose

Turn the *latest-state aggregate* into a *sequence of historical facts*, without changing what a state
means.

### 3.2 Responsibilities

**Owns:** grouping an ordered structural run by candle index; folding latest-side selection across those
groups; emitting one immutable snapshot per group; retaining each snapshot's triggering swings.

**Does not own** (delegates, never reimplements):

| Concern | Owner |
|---|---|
| ordering validation | `models._validate_current_point_order` |
| state classification | `models._sequence_state_for` / `_STATE_BY_LABEL_PAIR` |
| label derivation | `models._label_for` |
| price relation | `models._relation_for` |
| swing detection | `swings.detect_swings` |
| candle validation | `fmis.data.CandleSeries` |

If implementation ever needs a rule not in this table, that is the signal to stop and write an ADR.

### 3.3 Invariants

1. **I1 — one snapshot per group.** Exactly one snapshot per distinct `current.index` present in the
   input, in input order, no gaps for indices with no structural change.
2. **I2 — group atomicity.** Every swing sharing an index is applied *before* that index's snapshot is
   produced. No half-applied state is ever emitted (ADR-0015 §7).
3. **I3 — monotone index.** Snapshot indices are strictly increasing.
4. **I4 — cause retention.** Each snapshot holds exactly the swings from its own group: 1 normally, 2 for
   an outside bar, never 0, never 3, never two of one `SwingType`.
5. **I5 — trigger/state coherence.** For each trigger `t`, the state's side matching `t`'s `SwingType`
   **is** `t` (identity, not equality).
6. **I6 — carry-forward.** A side not present in a group is carried unchanged from the previous snapshot,
   by identity.
7. **I7 — no fabrication.** Until both sides exist, the state is `INSUFFICIENT_STRUCTURE`.
8. **I8 — immutability.** Snapshots and the history tuple are frozen; the input is never mutated or
   sorted.
9. **I9 — purity.** Same input → equal output, always. No clock, no I/O, no randomness, no global state.
10. **I10 — prefix stability under candle extension.** See §5.

### 3.4 Lifecycle

```
candles close
   → detect_swings confirms a pivot (right_bars late)
   → compare_swing_sequence relates it to the previous same-type pivot
   → label_swing_sequence names it
   → derive_structural_sequence_state_history folds it into a NEW snapshot appended to the history
   → every earlier snapshot is byte-identical to before
```

A snapshot, once emitted, is a historical fact and is never revised. This restores at the history level
the guarantee that ADR-0015 §8 explicitly declined to make for the single aggregate.

### 3.5 Boundaries

```
        fmis.data ──────► swings ──► relationships ──► labels ──► sequence_state
                                                            │            │
                                                            └──────┬─────┘
                                                                   ▼
                                                            state_history        ◄── THIS LAYER
                                                                   │
                                    ═══════════════════════════════╪═══════════════════
                                    interpretive layers (later)    ▼
                                          trend · BOS · CHoCH · liquidity · evidence
```

Inputs: `Iterable[StructuralSwing]` only — no candles, no series, no context, no options.
Outputs: `tuple[StructuralSequenceSnapshot, ...]`.

---

## 4. State model

Specification only — field tables and signatures, not implementations.

### 4.1 New type: `StructuralSequenceSnapshot`

| Field | Type | Meaning |
|---|---|---|
| `state` | `StructuralSequenceState` | the complete aggregate at this point — reused whole, never flattened |
| `triggers` | `tuple[StructuralSwing, ...]` | the 1–2 swings confirmed at this index that produced it |

Frozen, slotted, hashable. **Two fields only.**

**Why `state` is embedded rather than flattened.** `StructuralSequenceState` already validates that its
own three fields are mutually consistent (ADR-0015 §3). Copying `latest_high`/`latest_low`/`state` onto
the snapshot would create a second place for them to disagree — the exact hazard ADR-0014 §5 removed.

**Why `index` and `timestamp` are not fields.** Both are reachable as
`triggers[0].comparison.current.index` / `.timestamp`, and every trigger in a group shares them (I4).
Storing them would duplicate a derived fact.

Because reaching through four attributes is the ergonomic problem ADR-0014's consequences section
predicted, the design offers them as **computed properties**, not stored fields:

```
    snapshot.index      -> int        == triggers[0].comparison.current.index
    snapshot.timestamp  -> datetime   == triggers[0].comparison.current.timestamp
```

`@property` on a frozen dataclass is established repo precedent (§2.3). This is a projection, not state:
nothing is stored, so nothing can disagree. **See open question Q1** — the conservative alternative is to
omit them entirely.

**Validation (`__post_init__`), rejecting rather than normalising:**

| Check | Failure |
|---|---|
| `state` is a `StructuralSequenceState` | `TypeError` |
| `triggers` is a tuple of `StructuralSwing` | `TypeError` |
| `len(triggers)` in 1..2 | `ValueError` |
| all triggers share `current.index` | `ValueError` |
| all triggers share `current.timestamp` | `ValueError` |
| triggers have distinct `SwingType` | `ValueError` |
| **I5**: for each trigger, the state's matching side **is** that trigger | `ValueError` |

### 4.2 New function

```
derive_structural_sequence_state_history(
    structures: Iterable[StructuralSwing],
) -> tuple[StructuralSequenceSnapshot, ...]
```

- `TypeError` — not iterable, or an element is not a `StructuralSwing`
- `ValueError` — the run is not ordered, per `models._validate_current_point_order` with
  `subject="structures"` (identical rule, identical wording, only the parameter name substituted)
- Empty input → `()`

### 4.3 New enum

**None.** Deliberately. A transition type or a "changed/unchanged" flag would be the first place
interpretation could hide. A consumer comparing `history[i-1].state.state` with `history[i].state.state`
has everything, expressed in existing vocabulary.

### 4.4 Relationship to existing types

```
StructuralSequenceSnapshot
├── state: StructuralSequenceState        (reused whole)
│   ├── latest_high: StructuralSwing|None ─┐  may be shared with earlier snapshots
│   ├── latest_low:  StructuralSwing|None ─┘  by identity (carry-forward, I6)
│   └── state: StructuralSequenceStateType
└── triggers: tuple[StructuralSwing, ...]    always from THIS index
        └── comparison: SwingComparison
                ├── previous / current: SwingPoint
                └── relation: SwingRelation
```

Strict DAG. Objects are shared by identity across snapshots — never rebuilt, never copied. Since every
node is frozen, sharing is safe and makes carry-forward checkable with `is`.

### 4.5 Sequence evolution — worked example

Bars 0…9; `left_bars=right_bars=1`. Structural swings confirmed at indices 2, 4, 6 (outside bar), 8.

| # | index | triggers | latest_high | latest_low | state |
|---|---|---|---|---|---|
| 0 | 2 | `EQUAL_HIGH@2` | `@2` | — | `INSUFFICIENT_STRUCTURE` |
| 1 | 4 | `EQUAL_LOW@4` | `@2` *(carried)* | `@4` | `UNCHANGED` |
| 2 | 6 | `LOWER_HIGH@6`, `LOWER_LOW@6` | `@6` | `@6` | `SHIFTED_LOWER` |
| 3 | 8 | `HIGHER_LOW@8` | `@6` *(carried)* | `@8` | `CONTRACTED` |

Snapshot 2 is the outside bar: both sides update, one snapshot, and the intermediate `CONTRACTED` that a
per-swing design would emit never exists (measured in §5.4).

---

## 5. Prefix-stability proof

### 5.1 Assumptions

- **A1** The input is accepted by `models._validate_current_point_order`: `current.index` non-decreasing
  globally, equal index implies equal timestamp, strictly increasing within each `SwingType`.
- **A2** `StructuralSwing` objects are prefix-stable — proven for `detect_swings` (ADR-0012 §2, property
  test) and inherited by comparison and labelling.
- **A3** `_sequence_state_for` is a pure total function of the two latest sides.

### 5.2 The theorem

Let `S = (s₁…sₙ)` satisfy A1. Grouping by `current.index` yields contiguous groups `G₁…G_m` (contiguous
because indices are non-decreasing, A1). Let `H(S)` be the snapshot sequence.

**Claim.** Snapshot `j` is a pure function of `G₁…G_j` alone.

**Proof.** By construction `latest_high` and `latest_low` at snapshot `j` are the last HIGH-side and
LOW-side swings in `G₁…G_j`; nothing later is read. `state` is `_sequence_state_for` of those two (A3,
pure). `triggers` is exactly `G_j`. Therefore snapshot `j` depends on no element after `G_j`. ∎

**Corollary (I10).** For any prefix `S'` of `S` that ends **on a group boundary**,
`H(S') = H(S)[:len(H(S'))]` exactly.

### 5.3 The one edge case, stated honestly

If a prefix cuts **inside** a group — taking the HIGH of an outside bar without its LOW — the final
snapshot is computed from half the group and may differ. This is not a bug: both outputs are correct
functions of their respective inputs, and the two inputs are different.

**It cannot happen when data grows the way real data grows.** A candle either produces both swings of an
outside bar or neither; `detect_swings` emits them together. So a *candle* prefix never splits a group.

**It is not detectable, and not an error.** A HIGH at index 6 with no LOW at 6 is a perfectly legal run —
most bars are not outside bars. The layer cannot distinguish "you cut my group" from "there was no LOW".

**Consequence for the contract:** the guarantee must be stated as *prefix stability under candle
extension*, not *under arbitrary structural truncation*. Documenting the weaker true claim is better than
asserting the stronger false one.

### 5.4 Evidence

195 random series, 2,976 snapshots, 24 outside-bar groups:

| Extension mode | Violations |
|---|---|
| **candle prefixes** (how data actually arrives) | **0** |
| group-aligned structural cuts | **0** |
| arbitrary structural cuts (may split a group) | **12** — exactly the documented caveat |

Worked instance of mode 3 — full history `[(2, unchanged), (6, shifted_lower)]`; cut after 3 elements
`[(2, unchanged), (6, contracted)]`.

### 5.5 Edge cases

| Case | Behaviour |
|---|---|
| empty input | `()` |
| one swing | one snapshot, `INSUFFICIENT_STRUCTURE`, that side retained |
| only HIGHs, ever | every snapshot `INSUFFICIENT_STRUCTURE`, `latest_low is None` |
| equal highs / equal lows | `EQUAL_*` labels flow through unchanged; `UNCHANGED` only when both sides are equal |
| outside bar | one snapshot, both sides updated atomically, `len(triggers) == 2` |
| outside bar in either input order | identical snapshot; grouping is order-insensitive *within* a group |
| gap of many bars | no snapshots for bars with no structural change — the history is event-indexed, not bar-indexed |
| invalid sequence | `ValueError` from the shared rule; no partial history returned |
| non-iterable / wrong element | `TypeError` before any work |

**No partial results, ever.** Validation completes before the first snapshot is built — matching
`fmis.pipeline`'s "nothing partial" rule (ADR-0007).

---

## 6. Transition tables

### 6.1 Per-group side update

| Group contents | latest_high | latest_low |
|---|---|---|
| one HIGH-side swing | ← trigger | carried (I6) |
| one LOW-side swing | carried (I6) | ← trigger |
| one of each (outside bar) | ← HIGH trigger | ← LOW trigger |
| *(empty)* | impossible — groups come from input elements |

### 6.2 State derivation — unchanged, delegated

Reproduced for reference only; the authority is `models._STATE_BY_LABEL_PAIR`.

| | `HIGHER_LOW` | `LOWER_LOW` | `EQUAL_LOW` | *(none)* |
|---|---|---|---|---|
| **`HIGHER_HIGH`** | `SHIFTED_HIGHER` | `EXPANDED` | `EXPANDED` | `INSUFFICIENT_STRUCTURE` |
| **`LOWER_HIGH`** | `CONTRACTED` | `SHIFTED_LOWER` | `CONTRACTED` | `INSUFFICIENT_STRUCTURE` |
| **`EQUAL_HIGH`** | `CONTRACTED` | `EXPANDED` | `UNCHANGED` | `INSUFFICIENT_STRUCTURE` |
| *(none)* | `INSUFFICIENT_STRUCTURE` | `INSUFFICIENT_STRUCTURE` | `INSUFFICIENT_STRUCTURE` | `INSUFFICIENT_STRUCTURE` |

### 6.3 Snapshot-to-snapshot state transitions

All 36 ordered pairs are reachable and **all are legal**. This layer asserts nothing about which
transitions are meaningful — that is precisely the interpretation it withholds.

Two transitions are worth naming because later layers will care, and because naming them here prevents
someone inventing a flag for them:

- `INSUFFICIENT_STRUCTURE → anything` — occurs **at most once** per history (once both sides exist they
  never become unavailable again). A useful property; must be property-tested.
- `X → X` — a snapshot may repeat the previous state. It is still a distinct historical fact, because
  its triggers differ. **Never deduplicate.**

---

## 7. P2 architecture review

### P2-1 — two independent ordering implementations

`relationships.compare_swing_sequence` validates `SwingPoint` runs inline; `models._validate_current_point_order`
validates `SwingComparison` runs. Same four checks, near-identical message text, no shared code. They
agree today (composition verified: 6,535 accepted runs, 0 downstream rejections) but nothing enforces it.

**Recommended architecture — one core, two thin adapters.**

```
models._validate_key_order(
    keys:  Sequence[tuple[int, datetime, SwingType]],
    *,
    subject:      str,   # "points" | "comparisons" | "structures"
    index_noun:   str,   # "index"  | "current index"
    element_noun: str,   # "point"  | "comparison"
) -> None
        ▲                              ▲
        │ [(p.index, p.timestamp, p.type) for p in points]
        │                              │ [(c.current.index, …) for c in comparisons]
compare_swing_sequence      _validate_current_point_order
```

Rejected alternatives:

- **Leave both.** Rejected: it is the drift risk itself, and history would be the third consumer.
- **Make the comparison rule call the point rule.** Rejected: `compare_swing_sequence` interleaves
  validation with comparison construction, so it cannot delegate without an extra pass — and it would
  drag the message vocabulary of one layer into the other.
- **A shared generic over a protocol.** Rejected: three string parameters are simpler than a protocol,
  and the message text is the part that must be preserved byte-for-byte.

**Non-negotiable constraint.** All eight existing message strings must stay byte-identical. Milestone Y
proved a rewording slips past substring assertions; the extraction must be preceded by exact-equality
tests, not followed by them.

### P2-2 — missing equivalence tests

Nothing asserts the two rules agree; each is tested only against itself.

**Recommended:** a property-based **differential** over the shared domain — generate random
`(index, timestamp, type)` key sequences, drive both adapters, and assert:

1. accept/reject verdicts are identical;
2. on rejection, the two messages are identical after substituting the three nouns;
3. the rejection *reason* (which of the four checks fired) is identical.

Point 3 matters: verdict-only equivalence would pass even if the two rules rejected the same input for
different reasons, which is exactly how a divergence would begin.

**Sequencing.** P2 is *not* a prerequisite — history reuses the existing shared validator and adds no
third copy. But doing it first is cheap (~1 day), removes a known risk before a new consumer arrives, and
lets history's tests assert equivalence from day one. This refines the architecture review's "milestone
after next": on closer design the ordering is a free choice, and the cheaper-risk order is P2 first.

---

## 8. Test strategy

Target **≈ 260–320 collected cases** in a new `tests/test_market_structure_state_history.py`, from
**≈ 85–100 distinct functions**. (The suite convention counts collected cases; roughly a third will be
seed expansion — that ratio should be stated in the docs, not hidden.)

### 8.1 Unit — the snapshot model (~30)

Exact fields; frozen; slotted; `__slots__` contents; no `__dict__`; hashable; undeclared attribute
rejected (note the CPython frozen+slots `TypeError` quirk); every validation row of §4.1 individually;
`triggers` of length 0 and 3 rejected; two same-type triggers rejected; mismatched index or timestamp
rejected; **I5 violation rejected** (a trigger that is not the state's corresponding side).

### 8.2 Unit — the derivation (~45)

Empty → `()`; single swing; HIGH-only and LOW-only runs; carry-forward by identity on each side; outside
bar in both orders; snapshot count equals distinct index count; strictly increasing indices; a repeated
state emitted as its own snapshot; the worked example of §4.5 asserted end-to-end; generator input
consumed once; every `TypeError`/`ValueError` path.

### 8.3 Property tests — deterministic seeds (~120 cases from ~8 functions)

1. `len(history) == len({s.comparison.current.index for s in structures})`
2. indices strictly increasing
3. every snapshot's state equals an **independent oracle** — a fourth formulation, e.g. recomputing from
   raw prices, deliberately not the production mapping
4. concatenated triggers, in order, reconstruct the input exactly
5. each snapshot's sides are the last of their type at or before that group (identity)
6. `INSUFFICIENT_STRUCTURE → …` occurs at most once
7. input never mutated (value **and** identity)
8. output is deterministic across repeated calls

### 8.4 Prefix-stability tests (~35) — the milestone's core claim

- **Candle prefixes:** for random series, every candle prefix's history is an exact prefix of the full
  history. This is I10 and must be the strictest test in the suite.
- **Group-aligned structural cuts:** same guarantee.
- **Mid-group split:** assert the *documented* divergence, so the caveat is pinned rather than discovered
  later. A test that asserts a limitation is as valuable as one asserting a guarantee.
- **Snapshot identity:** earlier snapshots are `is`-identical? No — they are rebuilt per call. Assert
  `==` and explicitly document that identity is not promised across calls.

### 8.5 Deterministic replay (~15)

Bar-by-bar replay (append one candle, re-derive) must produce exactly the history of a single
whole-series derivation. This is the test that would catch a stateful or order-dependent implementation,
and it is the closest analogue to how a live consumer will use the layer.

### 8.6 Equivalence tests (~25) — P2-2

Per §7; lives with the P2 milestone, then guards all three consumers.

### 8.7 Regression and architecture guards (~30)

Extend, never weaken: public-API set (+3), submodule set (+1), import-boundary set (+1), stdlib-only,
vocabulary scan (add `transition`, `history` is fine, `trend`, `regime`, `momentum`, `strength`),
no-approximate-equality scan, `EvidenceFamily.MARKET_STRUCTURE` still empty, catalog still 6, mapping
still private and immutable, no arithmetic in the new module (AST: 0 `BinOp`).

Plus **exact-message contracts** for the new `ValueError` paths — the Milestone Y lesson applied from the
start.

### 8.8 Mutation probes (run individually, mutation confirmed live, byte-exact restore)

| Probe | Must be caught by |
|---|---|
| snapshot per swing instead of per group | outside-bar and replay tests |
| trigger group not applied before snapshot | atomicity test |
| carry-forward dropped (missing side → `None`) | carry-forward and insufficient tests |
| latest side taken as first rather than last | property test 5 |
| deduplicate repeated states | snapshot-count property |
| silently sort the input | ordering tests |
| snapshot emitted before validation completes | no-partial-result test |
| triggers stored from the wrong group | property test 4 |

### 8.9 Coverage estimate

100% line and branch coverage of the new module is achievable and should be required — it is ~60 lines of
pure logic with no I/O. The meaningful metric is **mutation kill rate**: all eight probes above must be
caught, each by a *named* test rather than incidentally.

---

## 9. Repository impact

### Production (4 files)

| File | Change | Size |
|---|---|---|
| `src/fmis/market_structure/state_history.py` | **new** — one public function | ~130 lines with docstrings |
| `src/fmis/market_structure/models.py` | `StructuralSequenceSnapshot` + `__all__` | ~120 lines |
| `src/fmis/market_structure/__init__.py` | 3 exports, pipeline diagram, package rules | ~35 lines |
| *(P2 milestone only)* `relationships.py` | adapt onto the unified rule | ~45 lines net removal |

### Tests (5 files)

| File | Change |
|---|---|
| `tests/test_market_structure_state_history.py` | **new**, ~260–320 cases |
| `tests/test_market_structure_{swings,relationships,labels,sequence_state}.py` | guard-set extension only — API set, submodule set, import set. **Additive; never weaken an assertion.** |

Expect roughly **7 pre-existing tests to fail on the first full run**, all correctly detecting intended
package growth. That is the guards working; extend precisely.

### Documentation (6 files)

`docs/adr/ADR-0016-structural-sequence-state-history-foundation.md` (new) · `docs/adr/README.md` (index
row) · `CURRENT_STATE.md` (milestone entry, counts, pipeline, stability section) · `REPOSITORY_MAP.md`
(package responsibilities, counts, new rules) · `START_HERE_FOR_AI.md` (pipeline, counts, **the stability
call-out must be revised** — the "one exception to non-repainting" becomes more nuanced once snapshots
are prefix-stable) · architecture review (pointer only; do not rewrite a merged audit).

### Complexity estimate

| Milestone | Complexity | Effort | Risk |
|---|---|---|---|
| Z0 — P2 unification | **Low** | ~1 day | Low — behaviour-preserving, guarded by exact-message tests |
| Z1 — State History | **Medium** | ~2 days | Medium — the design is settled; the risk is in the prefix-stability contract wording |
| Z2 — docs/counts reconciliation | **Trivial** | folded into Z1 | — |

Medium, not high: no new dependency, no new input type, no new enum, one new model, one new function, and
every classification rule delegated.

---

## 10. Risks, ranked

| # | Risk | Severity | Why | Mitigation |
|---|---|---|---|---|
| R1 | **Over-claiming prefix stability** — documenting the guarantee without the mid-group caveat | **High** | A consumer would cache snapshots believing them absolute; the failure is silent and the whole milestone's value rests on this claim | State the guarantee as *under candle extension*; pin the divergence with a test that asserts the limitation (§8.4) |
| R2 | **Re-deriving state instead of delegating** | **High** | A second source of truth for classification — the exact defect this repo has removed three times | AST test: 0 `BinOp`, no `StructuralSequenceStateType` member referenced by name in the new module; it must call `_sequence_state_for` |
| R3 | **Interpretation creeping in** via a transition type, a `changed` flag, or a `direction` field | **High** | Would silently make this an interpretive layer and pre-empt trend/BOS decisions | No new enum (§4.3); vocabulary scan extended; ADR-0016 states the exclusion explicitly |
| R4 | **P2 divergence** if the two ordering rules drift before unification | Medium | Adding a consumer raises the cost of a later divergence | Do Z0 first (§7); add the differential test |
| R5 | **Guard-test weakening** under first-run failures | Medium | The tempting fix for 7 red tests is to loosen them | Extend only; re-verify each narrowed guard still bites, as done in milestones X and Y |
| R6 | **Snapshot identity assumed across calls** | Medium | Snapshots are rebuilt per derivation; `is` comparison across calls fails while `==` succeeds | Document explicitly; assert `==` not `is` in tests (§8.4) |
| R7 | **Memory on long histories** — a snapshot per structural event, each holding references | Low | ~32k snapshots for 80k candles; objects are shared by identity, so the cost is pointers, not copies | Measure in Z1; do not optimise speculatively |
| R8 | **O(n) full rescan on every call** | Low | Fine today (100k structures → 0.05 s, measured); only walk-forward backtests re-deriving from bar 0 would feel it | The fold shape already admits an incremental adapter *above* the function; do not build it now |
| R9 | **`models.py` growth** past ~720 lines | Low | Cohesion cost only | Revisit splitting when a rule needs an external input; not before |

**Hidden coupling check.** Three couplings are real and all are intended: to `_sequence_state_for`
(classification), to `_validate_current_point_order` (ordering), and to the prefix stability of
`StructuralSwing` (A2). Each should be named in ADR-0016, because a change to any of them changes this
layer's guarantees. No coupling to candles, symbols, timeframes or clocks is introduced.

---

## 11. Implementation roadmap

Each milestone is independently testable, independently mergeable, and independently revertible.

### Z0 — Ordering Rule Unification (P2-1 + P2-2)

Extract one core ordering rule; adapt `compare_swing_sequence` and `_validate_current_point_order` onto
it; add the differential equivalence test.
**Exit:** all 8 message strings byte-identical to `8535a98` (proven by differential against the old
implementation, as in Milestone Y); equivalence test passing; test count unchanged except additions;
zero behaviour change.
**Independently valuable:** yes — closes both known P2 findings whether or not history follows.

### Z1 — Structural Sequence State History Foundation v1

`StructuralSequenceSnapshot` + `derive_structural_sequence_state_history` + ADR-0016 + full suite.
**Exit:** all §8 tests green; all 8 mutation probes caught; prefix stability proven for candle prefixes
**and** the mid-group caveat pinned; `EvidenceFamily.MARKET_STRUCTURE` still empty; docs consistent.

### Z2 — *(only if Q3 resolves toward it)* Snapshot Projection Helpers

Deferred by default. Add `index`/`timestamp` properties only if real consumers demonstrate the need.

### Then — and not before

Trend Foundation (needs its own ADR defining what constitutes a trend), then the level-crossing
prerequisite that BOS requires (a new input contract — see review §15), then BOS, then CHoCH over the BOS
sequence, then liquidity. Multi-timeframe is orthogonal. Evidence last.

**Explicitly not in Z0–Z2:** trend, BOS, CHoCH, break of structure, liquidity, sweep, support/resistance,
transitions as a type, evidence descriptors, signals, AI interpretation, multi-timeframe, tolerance,
incremental/streaming derivation, and any consumption of `CandleSeries` below `detect_swings`.

---

## 12. Open questions — resolve before implementing

**Q1 — Should the snapshot expose `index`/`timestamp` as properties?**
For: ergonomics; `@property` is repo precedent (21 uses). Against: `market_structure` has none, and
ADR-0014's consequences argue a consumer reaching through wants a *projection type*, not more surface.
*Recommendation:* include them — zero duplication, and the four-attribute reach is otherwise real.
**This changes the public API shape, so decide first.**

**Q2 — Emit `INSUFFICIENT_STRUCTURE` snapshots, or suppress until both sides exist?**
*Recommendation:* emit. "At bar 12 structure was not yet determinable" is a fact, and suppression makes
the function partial for no gain. Consumers can filter.

**Q3 — Is `derive_structural_sequence_state_history` too long a name?**
It is 40 characters. Alternatives: `derive_state_history` (loses the domain prefix),
`structural_sequence_state_history` (drops the verb). *Recommendation:* keep the long name — it matches
`derive_structural_sequence_state` exactly, and consistency beats brevity in a public API.

**Q4 — Should `derive_structural_sequence_state` be re-expressed as `history[-1].state`?**
Tempting (one derivation instead of two) but it would make the cheap single-state call allocate the whole
history. *Recommendation:* keep both, and add a test asserting they agree — an equivalence guard in the
same spirit as P2-2.

**Q5 — Does Z0 run before Z1?**
*Recommendation:* yes, on risk grounds, though the design confirms it is not a hard dependency. This
refines the architecture review's ordering; the user should confirm.
