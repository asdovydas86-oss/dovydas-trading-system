# ADR-0018 — Series identity: extracting what `CandleSeries` already knew, so derived facts can keep it

**Status:** Accepted
**Date:** 2026-07-30
**Decides:** what identifies one analytical market series, where that identity lives, how it propagates
through deterministic transformations, and how incompatible series are rejected (Milestone AB)
**Implemented by:** `Add Series Identity & Context Contract v1`
**Closes:** [the Trend Foundation review](../reviews/TREND_FOUNDATION_REVIEW_V1.md) P3-2
**Relates to:** [ADR-0017](ADR-0017-structural-trend-foundation.md);
[ADR-0016](ADR-0016-structural-sequence-state-history-foundation.md) (`index`/`timestamp` as projections —
the pattern `CandleSeries.identity` follows); [ADR-0012](ADR-0012-market-structure-foundation.md);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (identity strings are rejected, never normalized);
[ADR-0009](ADR-0009-trading-analysis-context-boundary.md) (a timeframe label is opaque);
[ADR-0005](ADR-0005-ingestion-boundary-strictness.md) (decode, never repair);
[the architecture review](../reviews/MARKET_STRUCTURE_ARCHITECTURE_REVIEW_V1.md) §16;
[the design](../design/SERIES_IDENTITY_CONTEXT_CONTRACT_V1.md)

---

## Context

### The inherited risk

The Trend Foundation review recorded P3-2: a `StructuralSequenceStateSnapshot` and a
`StructuralTrendSnapshot` carry no symbol and no timeframe — and neither does a `SwingPoint`,
`SwingComparison` or `StructuralSwing`. A caller can concatenate two instruments' histories, or two
timeframes of one instrument, and every deterministic function in the repository will accept the result
and return a confident, wrong answer.

**This is measured, not feared.** A BTCUSDT 4h series and an ETHUSDT 4h series built from identical OHLC
rows produce **byte-identical** trend histories. Nothing downstream could distinguish them, because there
was nothing to distinguish them with. A test now pins that fact permanently
(`test_the_measured_risk_this_contract_closes`).

Level-Crossing Foundation v1 will be the first layer to consume **both** candles and derived swings, and
must prove they describe the same series before comparing a price to a level. It needs a contract, not a
convention.

### The audit changed the answer

The instruction was to check for an existing primitive before assuming a new package. There were four, and
together they already settle almost every question this ADR was expected to decide:

- **`CandleSeries(symbol, timeframe, candles)`** — identity already exists one layer down, validated per
  candle by exact string equality, rejecting rather than regrouping.
- **`ingest.decode_candle_series`** — already calls that pair *"series identity"*, already raises on
  "mixed identity", and already handles the empty-payload case by requiring identity explicitly.
- **`evidence.descriptor._require_name`** — the authoritative policy on identity strings: reject, never
  normalize, because *"silently trimming or lower-casing would let `"Trend "` and `"trend"` be entered as
  two descriptors that collapse into one"*.
- **`trading_context`** — the authoritative policy on timeframe labels: `"4h"` and `"4H"` are two
  different labels, because the system has no canonical vocabulary.

**So the gap was never *definition*. It was *propagation*.** `detect_swings` receives a `CandleSeries` that
has `symbol` and `timeframe` and reads neither, and every stage after it is identity-free. This ADR
extracts the identity already in force and carries it upward; it invents no new semantics, because
inventing a second set would be the duplication ADR-0014 §5 and ADR-0016 §8 each refused.

## Decisions

### 1. Identity is `symbol` + `timeframe`, and nothing else

`SeriesIdentity(symbol, timeframe)`. The inclusion rule: **a field is included only if something in the
repository today would be wrong without it.**

| Excluded | Why |
|---|---|
| venue / exchange | zero occurrences outside three prose docstrings; nothing stores, validates or compares one. Including it would require inventing which venue a symbol belongs to — symbol mapping across exchanges is an explicit non-goal |
| data source / provider | the architecture review §16 already assigned this to *pipeline metadata*: it describes how data arrived, not what the series is. Including it would make two identical series from two providers incomparable, which is wrong |
| market type | nothing models it; futures resolution is an explicit non-goal |
| quote currency | already inside `symbol` (`BTCUSDT`); splitting needs exchange-specific parsing |
| price type | `Candle` has one set of OHLC fields and no variant concept |
| contract identifier | needs futures resolution |

Each is **deferred, not refused forever** — adding one later is a decision with its own record, and the
rule above is what that decision must satisfy.

### 2. Identity lives in `fmis.data`, and `CandleSeries` remains its owner

`SeriesIdentity` sits beside `CandleSeries`, and **`CandleSeries.identity` is a computed projection, not a
stored field** — following ADR-0016 §4 exactly: a stored copy of a value one attribute away is somewhere
for it to drift.

So a candle-derived pipeline's identity has exactly one source, and no synchronization problem can exist.
Placing `SeriesIdentity` in a new package while `CandleSeries` kept `symbol`/`timeframe` would have created
two definitions of one fact.

### 3. Equality is structural and exact; normalization is *none*

Two identities are equal iff both strings are equal by `==`. No case folding, no trimming, no Unicode
normalization, no alias translation. `"BTCUSDT"` ≠ `"btcusdt"` ≠ `" BTCUSDT"`; `"4h"` ≠ `"4H"` ≠ `"240m"`;
`"NASDAQ:AAPL"` ≠ `"AAPL"`.

Inherited, not invented (see Context). The repository has no canonicalization layer, so any alias table
here would be an unversioned, exchange-specific rule.

**The direction of the resulting error is deliberate and is the point.** Refusing to normalize makes this
contract **over-reject**: two spellings of one series will not combine. Over-rejection is safe;
under-rejection is the silent mixing being prevented. A caller wanting them unified normalizes *before*
building candles, where ingestion already owns the boundary.

A timeframe label stays **opaque**: `"banana"` is accepted, because validating the grammar needs the
canonical vocabulary ADR-0009 says does not exist.

### 4. Value validation is no stricter than `CandleSeries` — a compatibility constraint, not a preference

`CandleSeries` validates a label as `not value or not value.strip()`, so it **accepts `" BTCUSDT "`**
(verified). A stricter rule in `SeriesIdentity` would make `CandleSeries.identity` raise for a series that
is already valid, and a projection that can fail on a valid object is not a projection.

So blank and empty are rejected; surrounding and internal whitespace are accepted and preserved, and yield
a *different* identity. The type check is stricter (`TypeError` for a non-`str`) and safely so:
`CandleSeries` already rejects those, just via `AttributeError` from `.strip()`, so no valid series can
hold one.

**Tightening this is a breaking change and is deliberately out of scope**; it would need its own ADR and a
migration for any stored identity.

### 5. Context lives in an envelope, once per series — never per element

`ContextualSeries(identity, values)`, generic over its payload. Eight alternatives were compared against
sixteen criteria (design §3); the two that embed identity in every candle or every snapshot were rejected
for duplicating one fact across every element, changing every existing type and fixture, and — decisively —
**putting identity inside the value the analytical code reads**, which is how identity starts affecting
results.

The payload is *exactly* what the corresponding context-free function returned. Measured: a 22-element
history holds **one** identity object, and no element grew an identity, symbol or timeframe attribute.

A generic envelope is justified by the repository's own bar — it serves three payload types today: swings,
state history, trend history.

### 6. Identity never participates in a calculation

No analytical function receives an envelope; the wrappers unwrap, delegate, and re-wrap. So adding context
**cannot** change a result — proved, not asserted, by equivalence tests over ten fixture classes covering
every `StructuralSequenceStateType` member, every `StructuralTrendType` member, and outside-bar structure.
A further test derives the same rows under three different identities and asserts all three payloads are
identical.

### 7. Propagation is by object reference, and substitution is unrepresentable

Each wrapper carries the input envelope's identity **object** forward — never rebuilt from its fields,
never defaulted. A wrapper that reconstructed an equal identity would pass every `==` test while quietly
severing the link to the series the payload came from, so the tests assert `is`, not `==`. Mutation probe 5
does exactly that rebuild and is detected.

**No wrapper takes an identity parameter.** The only place identity can come from is the input, which makes
silent replacement unrepresentable rather than merely discouraged.

### 8. Mismatch is deterministic, named, and refused

`SeriesIdentityMismatchError(SeriesContextError, ValueError)`, matching
`SeriesDecodeError(IngestError, ValueError)` and `NotAlignedError(RelativeValueError, ValueError)` so
boundary code catching `ValueError` keeps working.

Message: `subjects[{i}] has identity {symbol!r}/{timeframe!r}, expected {symbol!r}/{timeframe!r}`. The
first subject is the reference and comparison is against it — not pairwise — so the reported position is
deterministic no matter how many subjects disagree.

**Raised, never warned, never repaired, never resolved by picking a side.** ADR-0005's rule applied to
identity.

### 9. `require_same_identity` is the single choke point, and it spans both sides

One function, accepting any mix of `CandleSeries` (through its projection) and `ContextualSeries` (through
its field). That uniformity is deliberate: **Level-Crossing must check candles against derived facts, and
should not need two different checks to do it.**

```python
identity = require_same_identity(candle_series, contextual_swings)
```

A single named function is either called or it is not, which is what makes the contract mutation-testable
— and probes 1, 2, 3 and 11 each attack it and are each detected.

### 10. Empty data keeps its identity

An empty payload is legal and fully identified. Missing analytical evidence is **not** missing series
identity: two empty series with different identities are unequal and still refuse to combine. Probe 12
makes empty data lose identity and is detected.

### 11. Two API categories, stated explicitly; nothing is deprecated

**Category 1 — context-free primitives** (`detect_swings`, `compare_swing_sequence`,
`label_swing_sequence`, `derive_structural_sequence_state_history`, `derive_structural_trend_history`,
and the rest) remain **public and unchanged**. They are not deprecated: they are the arithmetic, and
arithmetic does not need a passport. Their permitted scope is unit-level computation over values already
known to come from one series. What they never promised — and still do not — is to notice that they were
handed two.

**Category 2 — safe pipeline boundary**: `contextual_structural_swings`,
`contextual_structural_state_history`, `contextual_structural_trend_history`, `require_same_identity`.
These carry identity, preserve it exactly, and reject mismatches. **A future candle-derived module enters
here.**

Breaking Category 1 to force purity was rejected: the audit found no incompatibility that would justify it,
and the milestone's own instruction was not to. The change is **purely additive** — no existing type,
signature, exception message or export was modified.

### 12. Nothing analytical is re-implemented

Swing detection, comparison, labelling, sequence grouping, structural-state derivation, trend derivation,
ordering validation, outside-bar atomicity and prefix stability all keep their single implementation. The
wrappers unwrap, delegate, re-wrap. AST tests forbid this package from performing arithmetic, reading any
OHLC field, or naming any state or trend member. Probes 9 and 10 reimplement the two derivations locally
and are detected by 30 and 11 tests respectively.

Ordering errors surface from the delegate with the **exact** message the context-free function produces —
asserted by comparing the two strings.

### 13. No global state, ever

No registry, no cache, no ambient "current series", no thread-local. Identity is passed, not looked up.
Enforced by an AST guard and a runtime guard over module namespaces; probe 15 introduces a module-level
dict and is detected.

This also makes the contract trivially safe under concurrency: `SeriesIdentity` and `ContextualSeries` are
frozen, so one identity object can be shared across any number of readers.

### 14. Dependency direction, and no cycle

`fmis.data` gains **no import**. `fmis.series_context` imports `fmis.data`, `fmis.market_structure` and
`fmis.structural_trend` — public surfaces only, no private submodules — and **nothing imports
`fmis.series_context`**. A test spawns a fresh interpreter and asserts `import fmis.data` pulls in none of
its dependents.

`fmis.series_context.models` — which holds `ContextualSeries` and `require_same_identity` — imports
**neither** `market_structure` nor `structural_trend`, so a future Level-Crossing package can consume the
whole identity contract without depending on trend. That is asserted by test, because it is the property
that keeps the architecture review §15 ordering (BOS on levels → CHoCH on BOS → trend as a summary of both)
achievable.

## Alternatives considered

| | Rejected because |
|---|---|
| **A** identity in every candle *and* every snapshot | duplicates one fact per element, changes every type and fixture, and puts identity inside the value the maths reads |
| **B** identity in every snapshot, not candles | all of A's duplication with a hole underneath: Level-Crossing needs candle-side identity too |
| **D** a context object passed separately to every call | nothing forces the right one to be passed, so identity and payload can silently diverge — the exact failure mode being removed; also invites an ambient "current context" |
| **E** a generic wrapper around ordered values | **not rejected** — it is the mechanism the chosen design uses |
| **F** identity as function arguments | no object holds the pair, so every call site re-implements the check |
| **G** a single opaque series ID | cannot be inspected or explained in an error, and would require the canonicalization decision §3 refuses to make |
| **H** status quo, caller discipline | this is the defect |
| tightening whitespace validation now | would break `CandleSeries.identity` for already-valid series (§4) |
| deprecating the context-free APIs | no proven incompatibility; they are the arithmetic (§11) |
| normalizing aliases | no authoritative canonicalization layer exists (§3) |

## Consequences

- Derived histories can now be identified, and two of them can be refused. The measured risk — identical
  analytics under different identities — is closed at the pipeline boundary and pinned by test.
- **The unsafe path still exists and is now documented rather than assumed.** Category-1 primitives remain
  public and cannot tell whether their input came from one series. That is a deliberate compatibility
  choice, and the mitigation is that the safe path is now also the easy path.
- **The contract over-rejects.** `" BTCUSDT"` and `"BTCUSDT"` are different series and will not combine.
  Anything wanting them unified must normalize before building candles.
- Whitespace-bearing identities are accepted, inherited from `CandleSeries` (§4). Tightening is a breaking
  change needing its own ADR.
- `fmis.data` grew by one export — the first change to the most-depended-on module in several milestones.
  It is additive and the full suite was re-run.
- One existing architecture guard was updated, not weakened: `test_nothing_below_imports_this_package` in
  the trend suite now names `fmis.series_context` as the single permitted consumer *above* trend, and a
  companion test asserts that consumer touches no private submodule. A second consumer appearing anywhere
  fails the suite and must justify itself.
- **Still deliberately absent:** level crossing, protected levels, BOS, CHoCH, regime, signals, entries,
  exits, sizing, downloads, exchange integration, symbol mapping across exchanges, futures resolution,
  corporate actions, session/calendar logic, resampling, gap detection, portfolio identity, and any
  evidence descriptor — `EvidenceFamily.MARKET_STRUCTURE` remains empty.
