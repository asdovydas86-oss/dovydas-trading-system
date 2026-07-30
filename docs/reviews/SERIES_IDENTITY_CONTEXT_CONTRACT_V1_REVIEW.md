# Series Identity & Context Contract v1 — Independent Review (Milestone AB)

**Date:** 2026-07-30
**Reviewing:** `Add Series Identity & Context Contract v1 design` (`5281b03`) and
`Add Series Identity & Context Contract v1` (`5e549d1`)
**Scope:** `SeriesIdentity` and `CandleSeries.identity` in `fmis.data`; the new `fmis.series_context`
package; [ADR-0018](../adr/ADR-0018-series-identity-and-context-contract.md);
[the design](../design/SERIES_IDENTITY_CONTEXT_CONTRACT_V1.md); the documentation the milestone touched
**Method:** every count, export, mutation result and behavioural claim **re-derived from production code**.
Nothing from the design, the implementation's comments, its test counts, or its mutation report was taken
on trust.

---

## 1. Verdict

**Accept, after one P2 fix applied during this review.**

The milestone did the thing that mattered most: it audited before designing, found that identity already
existed in `CandleSeries`, and **extracted** it rather than inventing a parallel definition. That single
decision is what keeps the contract free of the duplication every ADR since 0013 has refused.

The core claims hold under independent measurement. Identity propagates by object reference, mismatches
are refused deterministically, empty data keeps full identity, and — the claim most worth distrusting —
**adding context provably changes no analytical value**, verified across all ten fixture classes.

**No P0. No P1.** One P2 was found and fixed; two P3s are recorded.

## 2. Re-derived claims

| Claim | Stated | Re-derived | Verdict |
|---|---|---|---|
| full suite | 2607 | **2609** after the review fix (2607 before) | ✅ |
| full suite, `-W error` | 2607 | **2609** | ✅ |
| series-context module | 181 | **183** after the review fix | ✅ |
| market_structure suite | 1227 | **1227** | ✅ unchanged from baseline |
| structural_trend suite | 353 | **353** (352 + 1 new layering guard) | ✅ |
| state-history / ordering suites | 267 / 33 | **267 / 33** | ✅ unchanged |
| data suite | 50 | **50** | ✅ unchanged |
| baseline before milestone | 2425 | **2425** | ✅ |
| total package exports | 113 | **113** across 22 packages | ✅ |
| export collisions | none | **none** | ✅ |
| `fmis.data` exports | 6 (was 5) | **6** | ✅ +1 = `SeriesIdentity` |
| `fmis.series_context` exports | 7 | **7** | ✅ |
| `fmis.market_structure` / `structural_trend` | 19 / 5 | **19 / 5** | ✅ unchanged |
| runtime dependencies added | none | **none** — `pyproject.toml` and `uv.lock` byte-identical to baseline `238691b` | ✅ |
| mutation probes | 15/15, 0 no-ops | **15/15 detected, 0 no-ops, 0 survivors**, re-run independently; every source restored byte-exactly and SHA-256 verified; post-restore suite green | ✅ |
| design's export arithmetic | "+6 → 112" | **+7 → 113** | ⚠️ already self-corrected during implementation, verified |

**Methodological note.** The design's eleven experiments were run against a *prototype*, not the shipped
code. This review re-ran all twenty adversarial cases against the real `fmis.series_context`, which is
what surfaced the P2 below — a property the prototype never had, because the prototype never defined
`__len__`.

## 3. Adversarial cases — all twenty, against production

| # | Case | Result |
|---|---|---|
| 1 | BTCUSDT 4h + ETHUSDT 4h | **rejected at all three stages** |
| 2 | BTCUSDT 1h + BTCUSDT 4h | **rejected at all three stages** |
| 3 | same identity reconstructed in a separate object | accepted; `is not` yet `==` |
| 4 | empty BTCUSDT 4h series | identity intact through all three stages, same object throughout |
| 5 | two empty series, different identities | payloads equal, envelopes unequal, combination rejected |
| 6 | valid state history wrapped with the wrong identity | rejected on combination |
| 7 | valid trend history wrapped with the wrong identity | rejected on combination |
| 8 | identity through every transformation | preserved **by object reference** (`is`), not rebuilt |
| 9 | attempted mutation of identity/envelope | 3/3 refused |
| 10 | attempted substitution mid-pipeline | 2/2 refused — no wrapper accepts an identity argument |
| 11 | context-free vs context-aware | **0 mismatches across all 10 fixture classes** |
| 12 | outside-bar fixture | 5 outside bars, payload unchanged, identity carried |
| 13 | alternating fixture | unchanged; trends `{INDETERMINATE, NEUTRAL}` |
| 14 | insufficient-structure fixture | unchanged and fully identified |
| 15 | Unicode / whitespace | 4 whitespace variants and 3 Unicode variants all distinct |
| 16 | case differences | distinct identities, rejected on combination |
| 17 | serialization reconstruction | pickle preserves identity, payload **and rejection behaviour** |
| 18 | concurrent reuse of one immutable identity | 200 tasks / 16 threads, single consistent result |
| 19 | type-valid but unintended API orders | 4/4 refused |
| 20 | Level-Crossing without importing trend | **confirmed** — `models.py` imports only `__future__`, `collections.abc`, `dataclasses`, `fmis.data`, `typing` |

Case 20 is the structurally important one: `ContextualSeries` and `require_same_identity` live in a module
that imports **neither** `market_structure` nor `structural_trend`, so the next milestone can consume the
whole identity contract without inheriting a dependency on trend. That keeps the architecture review §15
ordering (BOS on levels → CHoCH on BOS → trend as a summary of both) achievable rather than merely
intended.

## 4. Audit against the required checks

### Identity semantics and ownership — **clean, and the best decision in the milestone**
`SeriesIdentity` lives in `fmis.data` beside `CandleSeries`, and `CandleSeries.identity` is a **projection,
not a stored field**. Verified: `identity` is absent from `fields(CandleSeries)`, and the stored field set
is still exactly `{symbol, timeframe, candles}`.

Putting the type anywhere else would have created two definitions of one fact. The milestone was
explicitly told not to assume a new package was the answer, and the audit correctly concluded that half of
the answer already existed.

### Equality, hashing, normalization — **clean**
Structural and exact. Verified: separately constructed equal identities compare `==`, hash equal, collapse
in a set, and key a dict; ten distinct near-miss spellings all compare unequal. No case folding, no
trimming, no NFC/NFKC folding, no alias translation.

The **over-rejection** direction is correct and correctly documented: `" BTCUSDT"` will not combine with
`"BTCUSDT"`. Under-rejection is the failure being prevented; over-rejection is merely inconvenient.

### The compatibility constraint — **verified, and correctly reasoned**
`CandleSeries` accepts `" BTCUSDT "`, so `SeriesIdentity`'s **value** validation must be no stricter or
the projection would raise for an already-valid series. Confirmed by a test that builds series across five
symbol spellings and four timeframe spellings and asserts `identity` never raises.

The type check *is* stricter (`TypeError` for non-`str`) and that is safe: `CandleSeries` already rejects
those via `AttributeError` from `.strip()`, so no valid series can hold one. Correct.

### Immutability, hidden state, thread safety — **clean**
Frozen and slotted throughout. No `global`, no module-level mutable object, no registry, no cache, no
thread-local — enforced by both an AST guard and a runtime scan of module namespaces. Case 18 exercised one
shared identity across 200 concurrent tasks with a single consistent result. Probe 15 introduces a
module-level dict and is detected.

### Context propagation — **clean, and asserted the hard way**
Identity is carried by **object reference**. The tests assert `is`, not `==`, which is the only assertion
that catches a rebuild — and probe 5 performs exactly that rebuild and is detected by 2 tests. No wrapper
takes an identity parameter, so substitution is unrepresentable rather than discouraged (case 10).

### Analytical equivalence — **clean; the claim most worth distrusting, and it holds**
0 mismatches across all ten fixture classes at all three stages. A separate test derives the same rows
under three different identities and asserts the payloads are identical, which is the converse property.

The fixture set is itself verified rather than assumed: `test_every_required_fixture_class_is_actually_
exercised` asserts the sweep really reaches every `StructuralSequenceStateType` member, every
`StructuralTrendType` member, and outside-bar structure. Without that, an equivalence sweep over empty
payloads would pass vacuously — a real risk, since the first draft of the fixtures produced **no pivots at
all** at the default 2-bar confirmation window.

### No duplicated logic — **clean**
The wrappers unwrap, delegate, re-wrap. AST guards forbid arithmetic (`BinOp`), any OHLC/price attribute
read, and naming any state or trend member. Probes 9 and 10 reimplement the two derivations locally and are
detected by 30 and 11 tests respectively. Ordering errors surface from the delegate with the **exact**
original message, asserted by string comparison against the context-free call.

### Import direction and cycles — **clean**
`fmis.data` gained **no import** (verified by AST: still `{__future__, dataclasses, datetime,
fmis.data._timeutils}`). `fmis.series_context` imports only the three permitted public surfaces, reaches
into no private submodule, and nothing imports it. A test spawns a fresh interpreter and asserts
`import fmis.data` pulls in none of its dependents.

### Compatibility — **clean, purely additive**
No existing type, signature, exception message or export was modified. The only production file touched
outside the new package is `fmis/data/models.py`, additively.

One existing guard was **updated rather than weakened**: the trend suite's
`test_nothing_below_imports_this_package` now names `fmis.series_context` as the single permitted consumer
*above* trend, with a companion test asserting that consumer touches no private submodule. The exemption is
named, not pattern-matched, so a second consumer fails the suite. I checked this specifically for the
weaken-the-test-to-pass antipattern and it is not one — the guard's real intent was "nothing *below* depends
on trend", and a legitimate consumer above it was always going to require this.

### Documentation accuracy — **accurate**, one arithmetic slip already self-corrected
Every figure re-derived correctly. The design's original "+6 exports → 112" was wrong (three types plus
four functions is seven) and was corrected during implementation with the correction recorded inline
rather than silently overwritten. Verified: 113.

## 5. Findings

### P0 — none. P1 — none.

I specifically hunted for silent identity loss, false equality, missed mismatches, analytical-result
changes, compatibility breaks and import cycles. Probes 1, 2, 3, 5, 6, 11 and 12 attack exactly those
invariants and are all detected; cases 1–14 and 20 exercise them from the outside. None survived.

### P2-1 — an empty-but-valid contextual series was falsy *(fixed during this review)*

`ContextualSeries` defined `__len__`, so `bool(envelope)` was `False` whenever the payload was empty:

```python
empty = ContextualSeries(identity=SeriesIdentity("BTCUSDT", "4h"), values=())
bool(empty)   # False — despite a complete, valid identity
```

`if not envelope:` reads as *"no envelope"* but meant *"no values"*. That is in direct tension with the
contract's own principle 8 — **empty data may still possess a valid identity** — and with ADR-0018 §10.
It is a quiet trap rather than a wrong answer, hence P2 rather than P1, but it is exactly the kind of
idiom a future consumer writes without thinking.

It is also **inconsistent with the sibling type**: `CandleSeries` implements no container protocol at all;
callers write `len(series.candles)`.

**Fixed** by removing `__len__` entirely. Callers write `len(envelope.values)`, which cannot be misread, and
the API surface shrinks. Two tests were updated and **two regression tests added**:
`test_an_empty_envelope_is_never_falsy` (asserts `bool(empty) is True` and that no container protocol
exists) and `test_the_envelope_matches_candle_series_container_conventions` (asserts the envelope and
`CandleSeries` agree on `__len__`, `__iter__`, `__getitem__`, `__contains__`), so the protocol cannot be
reintroduced without a deliberate decision.

Mutation validation was re-run in full after the fix: **15/15 still detected, 0 no-ops, 0 survivors.**

### P3-1 — a payload can be paired with a foreign identity *(inherent; documented, no code change)*

`ContextualSeries(identity=BTC, values=eth_trend_history)` is constructible, and nothing detects it.

This is **inherent to the chosen architecture, not a defect of the implementation.** Derived elements carry
no identity — that is the entire point of storing it beside the values rather than inside them (ADR-0018
§5), and the alternatives that would make this detectable are precisely the ones rejected for duplicating
identity per element and letting it reach the arithmetic.

The mitigations are real and were verified: the wrappers never produce such an envelope (identity always
comes from the input, and there is no parameter to override it), and combining a forged envelope with an
honest one is still refused — `test_a_deliberately_mislabelled_envelope_is_still_rejected_downstream` and
adversarial cases 6 and 7 pin that. Hand-constructing a lie remains possible in Python, as it does for
every value type in the repository.

### P3-2 — the private carry helper is typed at `object` *(cosmetic, no code change)*

`_carry(source: ContextualSeries[object], values: Sequence[object])` loses the payload type across the
re-wrap, so the public wrappers' precise return annotations rest on their own signatures rather than on
inference through the helper. A `TypeVar` would thread it properly.

Not fixed: it is a private single-expression helper, the public signatures are exact, no runtime behaviour
depends on it, and the milestone's instruction was to avoid speculative generic machinery. Recorded so it
is a choice rather than an oversight.

### Accepted, not defects

- **Context-free primitives remain public and unsafe.** Deliberate (ADR-0018 §11), documented, and the
  right call: they are the arithmetic, and the milestone explicitly forbade breaking existing APIs without
  proven incompatibility. The mitigation is that the safe path is now also the easy path.
- **`_identity_of` uses `getattr`.** Duck typing is what lets one check span `CandleSeries` and
  `ContextualSeries`, which is the property Level-Crossing needs (§9 of the ADR). A non-`SeriesIdentity`
  attribute is still rejected with a positional `TypeError` — verified.
- **`ContextualSeries` is generic with `slots=True`.** Verified working: subscripting, pickling, equality
  and hashing all behave.
- **Whitespace-bearing identities are accepted.** Forced by the compatibility constraint (§4 of the ADR);
  over-rejection is the safe direction; tightening is correctly deferred to its own ADR.

## 6. Mutation review

Re-run independently after the P2 fix. Each probe: verified as a real byte change before the suite ran (a
probe that changes nothing is rejected by the harness), suite run, source restored, restoration verified by
**SHA-256**, and the post-restore suite confirmed green.

| # | Probe | Detecting tests |
|---|---|---|
| 1 | ignore instrument mismatch | 11 |
| 2 | ignore timeframe mismatch | 2 |
| 3 | force all identities equal | 13 |
| 4 | make identity mutable | 5 |
| 5 | drop identity during transformation (rebuild, not carry) | 2 |
| 6 | replace output identity with a default | 9 |
| 7 | permit empty required identity fields | 7 |
| 8 | normalize case contrary to the contract | 8 |
| 9 | duplicate structural-state logic instead of delegating | 30 |
| 10 | duplicate structural-trend logic instead of delegating | 11 |
| 11 | accept mixed contextual histories | 1 |
| 12 | make empty contextual data lose its identity | 2 |
| 13 | bypass ordering validation | 1 |
| 14 | break outside-bar compatibility | 4 |
| 15 | introduce global mutable context | 2 |

**15/15 detected, 0 no-ops, 0 survivors.** All fifteen probes required by the milestone were applicable to
the chosen architecture, so no substitution was needed.

Probes 11 and 13 are detected by a single test each. That is narrow but correct rather than weak — each is
the narrowest possible behaviour change, and the detecting test is precisely the one that owns the
invariant. The harness leaves no temporary files in the repository; it lives entirely outside it and was
deleted after use.

## 7. Validation

| Check | Result |
|---|---|
| full suite | **2609 passed** |
| `python -W error -m pytest -q` | **2609 passed** |
| targeted identity/context suite | **183 passed** |
| market_structure suite | **1227 passed** (unchanged) |
| structural_trend suite | **353 passed** |
| state-history / ordering suites | **267 / 33 passed** (unchanged) |
| data suite | **50 passed** (unchanged) |
| exports / collisions | **113 / none**; data 6, series_context 7, market_structure 19, structural_trend 5 |
| architecture guards | pass — no arithmetic, no price read, no state/trend member named, no global state |
| dependency direction | pass — three permitted imports, no private submodule, nothing imports the package |
| import cycle | none — fresh interpreter confirms `fmis.data` pulls in no dependent |
| `pyproject.toml` / `uv.lock` | **byte-identical to baseline `238691b`** |
| analytical results changed by context | **none**, 10/10 fixture classes |
| cross-instrument rejection | **rejected**, all three stages |
| cross-timeframe rejection | **rejected**, all three stages |
| empty-series identity | **retained**, all three stages |
| global mutable identity state | **none** |
| mutation probes | **15/15 detected, 0 no-ops**, SHA-256 restoration verified |
| `git diff --check` | clean |

## 8. Recommended next milestone

**Level-Crossing Foundation v1** — recommended, and the contract is sufficient for it.

The sufficiency check was performed rather than assumed (adversarial case 20 plus
`test_a_future_candle_consuming_module_can_join_the_contract`):

- it needs candles **and** derived swings proven to be one series →
  `require_same_identity(candle_series, contextual_swings)` covers both sides in one call, because the
  check spans a `CandleSeries` projection and a `ContextualSeries` field;
- it must not depend on trend → `fmis.series_context.models` imports neither `market_structure` nor
  `structural_trend`, verified by AST;
- it must be a sibling package, since it is the first layer since `detect_swings` to need a `CandleSeries`,
  keeping `market_structure`'s property that only its first stage touches a candle (architecture review
  §15).

**Its ADR must still decide, before any code:** close-versus-wick crossing; which level is protected and
when it stops being; whether an `EQUAL_HIGH` crosses anything; how an outside bar crossing both sides is
grouped and ordered; whether a crossing is reported at the crossing bar or at the next confirmed swing; and
what happens when a level is crossed inside a later swing's confirmation window.

**And the ordering stands:** BOS on levels, CHoCH over the BOS sequence, **trend an input to neither**.
