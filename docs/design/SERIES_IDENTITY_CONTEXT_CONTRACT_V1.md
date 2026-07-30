# Series Identity & Context Contract v1 — Design

**Status:** Accepted (design)
**Date:** 2026-07-30
**Milestone:** Series Identity & Context Contract v1 (Milestone AB)
**Closes:** [the Trend Foundation review](../reviews/TREND_FOUNDATION_REVIEW_V1.md) P3-2 — derived histories
carry no symbol or timeframe, so two instruments' histories can be concatenated without deterministic
rejection
**Relates to:** [ADR-0017](../adr/ADR-0017-structural-trend-foundation.md) §consequences;
[ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md);
[ADR-0012](../adr/ADR-0012-market-structure-foundation.md);
[ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) (identity strings are rejected, never normalized);
[ADR-0009](../adr/ADR-0009-trading-analysis-context-boundary.md) (a timeframe label is opaque);
[ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md) (decode, never repair);
[the architecture review](../reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) §16 (where context belongs)

---

## 1. Purpose

### 1.1 The risk, stated exactly

`StructuralSequenceStateSnapshot` and `StructuralTrendSnapshot` carry no symbol and no timeframe. Neither
does a `SwingPoint`, `SwingComparison` or `StructuralSwing`. So a caller can concatenate two instruments'
histories, or two timeframes' histories of one instrument, and every deterministic function in the
repository will accept the result and return a confident, wrong answer.

**Measured** (§7, experiment 1): a BTCUSDT 4h series and an ETHUSDT 4h series built from the same OHLC
rows produce **byte-identical** trend histories. Nothing downstream can tell them apart, because there is
nothing to tell apart with. That is not a hypothetical.

### 1.2 What this milestone does, and does not

It establishes a reusable, enforceable identity and context contract for candle-derived pipelines, so that
Level-Crossing Foundation v1 — which will consume **both** candles and swings, and therefore must prove
they describe the same series — has a contract to consume rather than a convention to remember.

It adds no trading logic, changes no analytical result, and answers no structural question.

## 2. The audit came first, and it changed the answer

The milestone instruction was explicit: *do not assume the correct solution is a new package; determine
whether the repository already contains a suitable primitive.* It does — four of them.

| Existing primitive | What it already establishes |
|---|---|
| `fmis.data.CandleSeries(symbol, timeframe, candles)` | **Identity already exists**, one layer down. It is `symbol` + `timeframe`, and every candle is validated against it by **exact string equality**, rejecting rather than regrouping |
| `fmis.ingest.decode_candle_series(..., symbol=, timeframe=)` | Already uses the term *"series identity"* for exactly that pair, and already raises `SeriesDecodeError` on "mixed identity". Already handles the empty-payload case by **requiring identity explicitly** |
| `fmis.evidence.descriptor._require_name` | The authoritative repository policy on identity strings: **reject, never normalize.** Its docstring gives the reason — *"silently trimming or lower-casing would let `"Trend "` and `"trend"` be entered as two descriptors that collapse into one"* |
| `fmis.trading_context` §docstring | The authoritative policy on timeframe labels: *"No normalization is applied, so `"4h"` and `"4H"` are two different labels — consistent with the rest of the system, which treats a timeframe label as opaque until a canonical vocabulary exists"* |

**Consequence: this milestone must not invent identity semantics. It must extract the ones already in
force and carry them upward.** Every question §5 asks — which fields, what equality, what normalization —
already has a repository answer, and inventing a second one would be the duplication ADR-0014 §5,
ADR-0015 §9 and ADR-0016 §8 each refused.

The gap is not *definition*. It is **propagation**: `detect_swings` receives a `CandleSeries` that has
`symbol` and `timeframe` and reads neither, and every stage after it is identity-free.

### 2.1 A hard compatibility constraint the audit discovered

`CandleSeries` validates a symbol as `if not value or not value.strip()`. It therefore **accepts
`" BTCUSDT "`** — verified in §7. Any identity type that is *stricter* than that would raise when derived
from an existing, valid `CandleSeries`.

So the new identity type's value validation must be **no stricter than `CandleSeries`'s**. Surrounding
whitespace is preserved and produces a *different* identity, never a normalized one. §5.4 records this and
why tightening it is deliberately out of scope.

## 3. Alternatives

Eight candidates, scored against the sixteen criteria the milestone requires. **`=`** means "same as
today, neither better nor worse".

| Criterion | A: identity in every candle **and** every snapshot | B: identity in every snapshot, not candles | **C: identity once in an immutable envelope** | D: separate context object passed to every call | E: generic contextual wrapper around ordered values | F: identity as function arguments | G: single opaque series ID | H: status quo, caller discipline |
|---|---|---|---|---|---|---|---|---|
| prevents cross-**instrument** mixing | yes | yes | **yes** | only if callers pass it | yes | only if callers pass it | yes | **no** |
| prevents cross-**timeframe** mixing | yes | yes | **yes** | only if callers pass it | yes | only if callers pass it | yes | **no** |
| compatible with current APIs | **no** — every snapshot type changes | **no** — snapshot types change | **yes** — additive only | yes | yes | yes | yes | yes |
| metadata duplication | **worst** — per candle *and* per element | **bad** — per element | **none** — one object per series | none | none | none | none | n/a |
| memory cost | O(n) identity refs ×2 | O(n) identity refs | **O(1)** per series | O(1) | O(1) | O(0) | O(1) | O(0) |
| deterministic equality | yes, but equality of *values* now includes identity | same | **yes, and separable** — envelope equality includes identity, payload equality does not | n/a | yes | n/a | yes | n/a |
| context propagation | automatic but invasive | automatic but invasive | **explicit, one hop per stage** | **caller-managed — the failure mode** | explicit | **caller-managed** | explicit | none |
| serialization | heavy | heavy | **light** | light | light | n/a | lightest | n/a |
| testing complexity | high — every existing fixture changes | high | **low** — existing fixtures untouched | medium | low | low | low | none |
| mutation-testability | good | good | **good** — mismatch check is a single named function | poor — no single choke point | good | poor | good | nothing to mutate |
| global/hidden state risk | none | none | **none** | **none, but invites a thread-local "current context"** | none | none | none | none |
| suits Level-Crossing / BOS / CHoCH | yes | **no** — Level-Crossing needs candle-side identity too | **yes** — both candles and derived series carry it | yes | yes | fragile | yes | no |
| identity leaking into calculations | **high risk** — identity sits inside the value the maths reads | **high risk** | **none** — payload is untouched and the envelope is never read by analysis | none | none | none | none | none |
| can invalid combinations still occur silently? | no | **yes** — candles stay identity-free at the swing boundary | **only via documented context-free primitives**, which stay explicitly labelled | **yes** — nothing forces the context to be passed | no | **yes** | no | **yes** |
| migration cost | **very high** | **high** | **very low** — nothing existing is modified except one additive projection | low | low | none | low | none |
| public API clarity | muddled — a candle is not a series | muddled | **clear** — envelope carries context, payload carries facts | two parallel arguments to keep in sync | clear | unclear | **poor** — an opaque ID cannot be inspected or explained |

### 3.1 Why each rejected candidate is rejected

- **A — identity in every candle and snapshot.** `Candle` *already* carries symbol and timeframe, so the
  candle half is done; extending it to every derived snapshot is the expensive half. It duplicates one fact
  across every element, changes every existing snapshot type and every existing fixture, and — decisively —
  **puts identity inside the value the analytical code reads**, which is exactly how identity starts
  affecting results. Rejected.
- **B — identity in every snapshot but not candles.** All of A's per-element duplication with a hole
  underneath: Level-Crossing must read candles *and* swings, so leaving the candle side identity-free at
  the boundary defeats the milestone's own purpose. Rejected.
- **D — a context object passed separately to every function.** Nothing forces a caller to pass the right
  one, so identity and payload can silently diverge — the failure mode this milestone exists to remove. It
  also invites the "ambient/thread-local current context" that principle 3 forbids. Rejected.
- **E — a generic wrapper around ordered values.** This is *not* rejected; it is the mechanism **C** uses.
  Listed separately by the milestone, but the two collapse: the envelope in C is generic over its payload.
  Adopted as part of C (§4.3).
- **F — identity as function arguments.** No object holds the pair, so nothing can be checked once and
  reused, and every future call site re-implements the check. Rejected.
- **G — a single opaque series ID.** Prevents mixing, but an opaque token cannot be inspected, explained in
  an error message, or reasoned about — and it would require a *new* canonicalization decision about how to
  build the token from symbol and timeframe, which is precisely the aliasing question §5.4 refuses to
  answer. Rejected.
- **H — status quo.** This is the defect. Rejected by the existence of the milestone.

### 3.2 Chosen: **C**, implemented with **E**'s generic envelope

> Identity is stored **once**, in an immutable envelope, generic over its payload. The payload is the exact
> tuple the existing context-free function already returns, unchanged and untouched.

It is the only candidate that prevents both mixing modes, requires no change to any existing type,
duplicates nothing, and structurally cannot let identity reach the arithmetic.

## 4. Identity semantics

### 4.1 The two dimensions, and why exactly two

`SeriesIdentity(symbol, timeframe)`.

**Included, each with a demonstrated *current* integrity purpose:**

| Field | Current purpose |
|---|---|
| `symbol` | `CandleSeries` already validates every candle against it; mixing two symbols is the P3-2 risk verbatim |
| `timeframe` | likewise; a 1h and a 4h history of one instrument are different analytical series, and `detect_swings` indices are only meaningful within one |

**Excluded, each deliberately deferred:**

| Field | Why excluded |
|---|---|
| venue / exchange | **Zero occurrences** in the repository outside three prose docstrings. Nothing stores, validates or compares one. Adding it would mean inventing which venue a symbol belongs to — a mapping this milestone's non-goals forbid |
| data source / provider | The architecture review §16 already assigned this to **pipeline metadata**: *"it describes how data arrived, not what the structure is"*. Including it would make two identical series from two providers incomparable, which is wrong |
| market type (spot/perp/futures) | No type models it; futures contract resolution is an explicit non-goal |
| quote currency | Already inside `symbol` for every symbol the repository handles (`BTCUSDT`). Splitting it would require exchange-specific parsing — an explicit non-goal |
| price type (last/mark/index) | Nothing models it; `Candle` has one set of OHLC fields and no variant concept |
| contract identifier | Requires futures resolution — an explicit non-goal |

The rule applied: **a field is included only if something in the repository today would be wrong without
it.** Symbol and timeframe both fail that test without inclusion; nothing else does.

### 4.2 Equality and hashing

Structural, exact, field-by-field — the dataclass default. `frozen=True, slots=True`, so identity is
hashable and immutable, matching every value type in `fmis.data` and `fmis.market_structure`.

Two identities are equal **iff** both strings are equal by `==`. No case folding, no trimming, no aliasing,
no length-normalizing, no Unicode normalization. Measured in §7 experiment 6: reconstruction of the same
identity in a separate object compares equal and hashes equal.

### 4.3 Normalization policy: **none**, and it is inherited rather than invented

`"BTCUSDT"` ≠ `"btcusdt"` ≠ `" BTCUSDT"`. `"4h"` ≠ `"4H"` ≠ `"240m"`. `"NASDAQ:AAPL"` ≠ `"AAPL"`.

This is not a new decision. `fmis.trading_context` already states it for timeframes verbatim, and
`fmis.evidence.descriptor` already states the reasoning for identity strings generally. The repository has
**no authoritative canonicalization layer**, so any alias table here would be an invented, unversioned,
exchange-specific rule — which the milestone forbids and which ADR-0005 forbids in general.

**The direction of the error matters and is stated deliberately.** Refusing to normalize means the contract
**over-rejects**: `" BTCUSDT"` and `"BTCUSDT"` are treated as different series and will not combine. That
is the safe direction. Under-rejecting — silently treating them as one — is the failure this milestone
exists to prevent. A caller wanting them unified must normalize *before* constructing candles, where
ingestion already owns the boundary.

### 4.4 Edge cases, decided

| Case | Decision | Reason |
|---|---|---|
| empty string | **rejected**, `ValueError` | matches `CandleSeries` and `Candle` exactly |
| whitespace-only | **rejected**, `ValueError` | matches `CandleSeries`' `not value.strip()` |
| leading/trailing whitespace | **accepted**, preserved, a *different* identity | forced by §2.1: `CandleSeries` accepts it, so rejecting would break the projection from a valid series. Recorded as a known limitation, not an endorsement |
| internal whitespace | accepted, preserved | same reason |
| case | **significant**, never folded | §4.3 |
| Unicode | accepted as-is; no NFC/NFKC normalization | normalizing is normalizing; two visually identical strings with different code points are different identities. Over-rejection, the safe direction |
| non-`str` type | **rejected**, `TypeError` | stricter than `CandleSeries` only in *type*, and safe: `CandleSeries` already crashes on a non-str symbol (`.strip()` raises `AttributeError`), so no valid series can hold one |
| malformed timeframe (`"banana"`, `"-4h"`) | **accepted** | a timeframe label is opaque (ADR-0009). Validating its grammar would require the canonical vocabulary that does not exist, and inventing one is a non-goal |
| optional fields | **none** — both are required | an optional identity dimension is an identity that sometimes does not identify |
| default identity | **none** — no default is provided | a default identity is the silent-mixing bug with extra steps |
| mutable metadata | **none** — no metadata mapping on the identity | ADR-0016 §3's reasoning: a second place for facts to disagree |
| serialization round trip | preserved (`pickle`, §7 experiment 7) | frozen slotted dataclass of two `str`s. The repository has no serializer of its own, so no format contract is claimed |

### 4.5 Where identity is *owned*

**`CandleSeries` remains the owner.** `SeriesIdentity` is the extraction of what it already holds, and
`CandleSeries.identity` is a **computed projection, not a stored field** — following ADR-0016 §4 exactly:
storing a copy of a value one attribute away is somewhere for it to drift.

So there is exactly one place a candle-derived series' identity comes from, and no synchronization problem
can exist.

## 5. The context contract

The fifteen required principles, and how each is enforced:

| # | Principle | Enforcement |
|---|---|---|
| 1 | identity is immutable | `frozen=True, slots=True`; test asserts assignment raises |
| 2 | identity is explicit | every envelope requires it positionally; no default |
| 3 | identity is not global state | no module-level mutable object, no registry, no cache, no thread-local; AST test |
| 4 | identity does not affect calculations | the payload is produced by the **existing** context-free function and passed through untouched; equivalence test on ten fixture classes |
| 5 | a context-bearing transformation preserves identity exactly | each wrapper copies the input envelope's identity **by identity (`is`)**, never rebuilds it; test |
| 6 | a transformation cannot silently replace identity | wrappers take no identity parameter — there is no argument through which to substitute one |
| 7 | two identities cannot be combined through a safe API | `require_same_identity` raises `SeriesIdentityMismatchError`; measured §7 |
| 8 | empty data may still possess a valid identity | an empty payload is legal; §7 experiment 5 |
| 9 | missing evidence ≠ missing identity | `INDETERMINATE`/`INSUFFICIENT_STRUCTURE` payloads keep full identity; tested |
| 10 | validation failures are deterministic | pure comparisons of frozen strings; no clock, no randomness |
| 11 | validation precedes derivation where practical | wrappers validate the envelope before calling the analytical function |
| 12 | outputs are type-safe and inspectable | generic envelope with a real payload type; `identity` and `values` are plain attributes |
| 13 | comparison is structural and exact | §4.2 |
| 14 | no API infers identity from price behaviour | wrappers read only `series.symbol` / `series.timeframe`; AST test forbids reading any OHLC field for identity |
| 15 | no API infers timeframe from timestamps | nothing computes an interval anywhere; AST test |

## 6. Low-level versus pipeline-boundary APIs

The milestone requires an explicit two-category classification. **No existing API is deprecated, changed,
or removed** — the audit found no incompatibility that would justify it.

### Category 1 — context-free deterministic primitives (unchanged, still public)

`detect_swings` · `compare_swings` · `compare_swing_sequence` · `label_swing` · `label_swing_sequence` ·
`derive_structural_sequence_state` · `derive_structural_sequence_state_history` ·
`derive_structural_trend` · `derive_structural_trend_history` · `required_candles`

**Permitted scope, documented:** unit-level computation over values already known to come from one series.
They remain the single implementation of every analytical rule, and the Category-2 APIs delegate to them
rather than reimplementing anything. They are *not* deprecated: they are the arithmetic, and arithmetic
does not need a passport.

**What they do not promise:** they cannot tell whether their input came from one series, and they never
could. That is now written down rather than assumed.

### Category 2 — safe pipeline-boundary APIs (new)

`contextual_structural_swings` · `contextual_structural_state_history` ·
`contextual_structural_trend_history` · `require_same_identity`

These carry identity, preserve it exactly, and reject mismatches. **A future candle-derived module enters
the pipeline here.**

### 6.1 How Level-Crossing Foundation must consume this

Level-Crossing needs *both* a `CandleSeries` and a derived swing series, and must prove they describe the
same series before comparing a price to a level. With this contract it does exactly:

```python
identity = require_same_identity(candle_series, contextual_swings)
```

`CandleSeries` satisfies the check through its `identity` projection, and the contextual swing series
through its envelope — so **one function covers both sides**, and Level-Crossing needs no identity logic of
its own.

Critically, it can do this **without importing `fmis.structural_trend`** (verified in the review's
adversarial case 20): the contract lives below trend, so a sibling package can consume candles + swings +
identity and never see a trend.

## 7. Design experiments — reproducible results

Prototyped outside production and run against the real pipeline. **11/11 passed.** Scratch files were
deleted before committing; the prototype is reproduced by the shipped implementation and its tests.

| # | Demonstration | Result |
|---|---|---|
| 1 | equal analytical histories with different identities remain distinguishable | **PASS** — BTCUSDT 4h and ETHUSDT 4h from identical rows gave `values` **equal** and envelopes **not equal**. This is the risk and the fix in one line |
| 2 | combining different identities is rejected by the safe API | **PASS** — 2/2 rejected |
| 3 | no per-element identity duplication | **PASS** — 22 payload elements, **1** identity object; no element grew an `identity` attribute |
| 4 | context propagation does not change structural-state or trend values | **PASS** — all three stages byte-identical to the context-free result |
| 5 | empty series retains identity | **PASS** — `values == ()`, identity intact through all three stages |
| 6 | identity equality and hashing deterministic | **PASS** — separately constructed equal identities compare `==`, hash equal, collapse in a `set`, and are not `is` |
| 7 | serialization preserves identity | **PASS** — `pickle` round trip equal and hash-equal |
| 8 | no global mutable registry required | **PASS** — no module-level mutable object |
| 9 | wraps candle input and derived output | **PASS** — `identity_of(candles) == swings.identity == trend.identity` |
| 10 | mixed BTCUSDT/ETHUSDT rejected | **PASS** — `subject[1] has identity 'ETHUSDT'/'4h', expected 'BTCUSDT'/'4h'` |
| 11 | mixed BTCUSDT 1h / BTCUSDT 4h rejected | **PASS** — `subject[1] has identity 'BTCUSDT'/'1h', expected 'BTCUSDT'/'4h'` |

Two further measurements taken during the experiments and carried into the design:

- **identity is immutable** — assignment raises.
- **`CandleSeries` accepts `" BTCUSDT "`** — the constraint that fixes §4.4's whitespace decision.

## 8. Decisions

| Question | Decision |
|---|---|
| package/module location | `SeriesIdentity` → **`fmis.data`** (with `CandleSeries.identity`), because identity is already `CandleSeries`'s. Envelope and wrappers → new sibling package **`fmis.series_context`** |
| public type names | `SeriesIdentity`, `ContextualSeries`, `SeriesContextError`, `SeriesIdentityMismatchError` |
| public function names | `require_same_identity`, `contextual_structural_swings`, `contextual_structural_state_history`, `contextual_structural_trend_history` |
| immutable model | every type `frozen=True, slots=True`; payload stored as a `tuple` |
| validation rules | §4.4 |
| symbol ownership | `CandleSeries` (projected, not copied) |
| timeframe ownership | `CandleSeries` (projected, not copied) |
| venue/source | **excluded** (§4.1) |
| equality / hashing | structural, exact, dataclass default (§4.2) |
| propagation | each wrapper carries the input envelope's identity forward **by object identity** |
| mismatch failure type | `SeriesIdentityMismatchError(SeriesContextError, ValueError)` — matching `NotAlignedError(RelativeValueError, ValueError)` and `SeriesDecodeError(IngestError, ValueError)` |
| mismatch message | `subjects[{i}] has identity {symbol!r}/{timeframe!r}, expected {symbol!r}/{timeframe!r}` — exact, positional, tested |
| empty-series behaviour | legal; identity retained |
| context-free API policy | unchanged, still public, scope documented (§6) |
| context-aware API policy | the safe boundary; delegates, never reimplements |
| compatibility strategy | **purely additive.** No existing type, signature, message or export is modified. One additive projection on `CandleSeries`; one new export in `fmis.data` |
| prohibited dependency directions | `fmis.data` imports nothing of ours; `fmis.series_context` imports `fmis.data`, `fmis.market_structure`, `fmis.structural_trend` and nothing else; **nothing imports `fmis.series_context`** |
| public export impact | +1 in `fmis.data` (105 → 106), +6 in `fmis.series_context` (→ 112), 0 collisions |

### 8.1 Dependency direction

```
        fmis.data  (Candle, CandleSeries, SeriesIdentity)
             │  identity is owned here
             ▼
    fmis.market_structure   ──────────┐   context-free primitives
             │                        │
             ▼                        │
    fmis.structural_trend             │
             │                        │
             └────────┬───────────────┘
                      ▼
            fmis.series_context        safe pipeline boundary
                      │
                      ▼
        (future) fmis.level_crossing — consumes candles + swings + identity,
                                       never imports structural_trend
```

No cycle: `fmis.data` gains no import, and nothing imports `fmis.series_context`.

### 8.2 Example transformation

```
CandleSeries("BTCUSDT", "4h", …)                 identity owned here
        │  contextual_structural_swings
        ▼
ContextualSeries[StructuralSwing]                identity carried, payload = label_swing_sequence(…)
        │  contextual_structural_state_history
        ▼
ContextualSeries[StructuralSequenceStateSnapshot] identity carried, payload untouched
        │  contextual_structural_trend_history
        ▼
ContextualSeries[StructuralTrendSnapshot]        identity carried, payload untouched
```

At every arrow the payload is exactly what the context-free function returns (§7 experiment 4), and the
identity is the same object throughout.

## 9. Test strategy

One new module, `tests/test_series_context.py`, covering the thirty required areas: identity construction,
immutability, exact equality, hash stability, empty/whitespace/case/Unicode policy, timeframe opacity,
empty contextual series, context preservation by object identity, replacement rejection, instrument and
timeframe mismatch rejection, same-identity acceptance, mixed state-history and trend-history rejection,
**context-free/context-aware equivalence across all ten required fixture classes**, unchanged structural /
trend / outside-bar / ordering / prefix behaviour, pickle round trip, exports, collisions, dependency
direction, no duplicated analytical logic (AST), no global mutable context (AST), and a representative
Level-Crossing consumption shape.

## 10. Mutation strategy

Fifteen probes, each verified as a real source change, detected, and restored byte-exactly with SHA-256
verification: ignore instrument mismatch · ignore timeframe mismatch · force all identities equal · make
identity mutable · drop identity during transformation · replace output identity with a default · permit
empty identity fields · normalize case · duplicate structural-state logic · duplicate trend logic · accept
mixed contextual histories · make empty data lose identity · bypass ordering validation · break outside-bar
compatibility · introduce global mutable context.

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | context-free APIs stay public, so the unsafe path remains reachable | classified and documented (§6); breaking them was rejected as unjustified. The safe path is now the *easy* path |
| 2 | whitespace-bearing identities are accepted | forced by §2.1 compatibility; over-rejection is the safe direction; recorded as a deferred limitation |
| 3 | a generic envelope is over-abstraction | it serves three payload types today (swings, state history, trend history) — the milestone's own stated bar |
| 4 | identity could later drift into calculations | payload is never touched; AST guard forbids the wrappers reading any OHLC field |
| 5 | someone adds venue "just in case" | §4.1 records the inclusion rule and every exclusion |
| 6 | `fmis.data` is the most-depended-on module | the change is additive only: one new type, one projection, one export; full suite re-run |

## 12. Future extension boundaries

**May later be added, each with its own decision record:** a canonicalization layer (which would then make
alias handling legitimate); venue/source once a type models one; a timeframe vocabulary once one exists;
serialization format contracts.

**Must never be added here:** level crossing, protected levels, BOS, CHoCH, regime, signals, entries,
exits, sizing, downloads, exchange integration, symbol mapping across exchanges, futures resolution,
corporate actions, session/calendar logic, resampling, gap detection, portfolio identity, or any global
mutable context.
