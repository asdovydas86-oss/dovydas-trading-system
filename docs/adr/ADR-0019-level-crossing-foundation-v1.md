# ADR-0019 — Level-Crossing Foundation v1: a crossing is a fact, a break is a reading

**Status:** Accepted
**Milestone:** AC
**Date:** 2026-07-31
**Supersedes / amends:** nothing. Extends ADR-0012, ADR-0013, ADR-0018.
**Design:** [`docs/design/LEVEL_CROSSING_FOUNDATION_V1.md`](../design/LEVEL_CROSSING_FOUNDATION_V1.md)

---

## 1. Context

The market-structure architecture review §15 stated the gap precisely. After `detect_swings`, **no layer
reads a candle**, so no fact of the form *"price traded above level L at bar i"* exists anywhere.
`SwingPoint` stores only the extreme, so *close vs wick* is not derivable from swings. And a swing carries
the **pivot's** timestamp, while a crossing happens at a **different** bar that nothing currently records.

This milestone supplies those facts and stops there.

### 1.1 Why crossing is separated from BOS

A crossing is a **geometric fact about two numbers and one candle**. Break of Structure is an
*interpretation* that additionally requires deciding **which** level was protected, **when** it stops being
protected, and whether an `EQUAL_HIGH`-derived level breaks anything. None of those decisions has an
answer that follows from the data; each needs its own record.

Separating them buys a specific property: **a BOS layer that disagrees with any particular protected-level
policy can still use these events unchanged.** Had v1 baked in "first crossing only" or "skip candles
before the level's origin", it would have shipped an unrecorded BOS policy disguised as a primitive.

### 1.2 Why crossing is separated from CHoCH

Review §15 fixed the ordering and it stands: **BOS is defined purely on levels, CHoCH over the BOS
sequence, and trend is a summary of both, defining neither.** CHoCH is therefore two layers up and never
sees a crossing or a candle. Any definition in which trend is an input to a break is rejected on sight —
which is why `fmis.level_crossing` imports the structural-trend package nowhere, enforced by a test.

---

## 2. Decision

A new sibling package **`fmis.level_crossing`**, depending on `fmis.data`, `fmis.market_structure` and
`fmis.series_context`, with **13 public names**.

Review §15 recommended a sibling explicitly, so `market_structure` keeps its property that **only its
first stage touches candles**. Putting crossing inside `market_structure` would have reintroduced a
`CandleSeries` dependency *below* `detect_swings`, and was rejected for that reason alone.

### 2.1 The level model

```python
@dataclass(frozen=True, slots=True)
class LevelOrigin:
    index: int; timestamp: datetime; label: StructuralSwingLabel

@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: float; side: LevelSide; origin: LevelOrigin | None = None
```

- **`origin` is optional**, and that is the substance. A hand-written test level, or a future level from a
  source that is not a swing, must be representable without fabricating a pivot.
- **`origin` is provenance, never policy.** Nothing marks a level protected, active, spent or
  BOS-relevant. Nothing in the package reads an origin except the ordering key.
- **A swing is never renamed.** `EQUAL_HIGH` stays `EQUAL_HIGH`, not "double top", "resistance" or
  "protected high".
- **`side` is intrinsic and validated against `origin.label`.** A level contradicting its own provenance
  cannot be constructed.
- **Equality is structural and exact.** Same price, different origin → two levels, never collapsed.

Rejected: a raw price (no provenance, duplicates indistinguishable), separate `HighLevel`/`LowLevel`
(doubles every signature), and a level tied directly to a `Swing` (makes a hand-made level impossible and
forces the dependency).

### 2.2 The crossing policy — one canonical rule, not a setting

For an `UPPER` level at price `L`:

| | |
|---|---|
| `high < L` | nothing |
| `high == L` | `TOUCH` |
| `high > L` and `close <= L` | `WICK_BREACH` |
| `high > L` and `close > L` | `CLOSE_BREACH` |

Mirrored on `low` for a `LOWER` level. Mutually exclusive and exhaustive over "an interaction occurred".
`CLOSE_BREACH` implies the extreme was beyond too, since `high >= close`.

**A configurable policy was rejected.** It would make every historical event non-reproducible without its
setting — the identical argument review §9 uses to keep tolerance out of comparison. The distinctions a
caller would configure are already *facts on the event*, so a consumer that only trusts closes filters on
`CLOSE_BREACH` and gets a stronger guarantee than a setting would have given it.

### 2.3 Touch versus breach, and the equality policy

**Exact equality is a `TOUCH`, never a breach.** A breach requires strict `>` / `<`. A touch consumes
nothing: a level may be touched repeatedly and later breached, and every interaction is reported.

`EQUAL_HIGH` and `EQUAL_LOW` are **not** treated differently as levels — both yield a level at the swing's
price with the label carried through — because treating them differently *here* would be BOS policy
smuggled into a primitive.

**Comparison is exact on stored floats.** No epsilon, tick size, `isclose`, rounding or `Decimal`. Not a
new decision: ADR-0013 §4 and review §9 already record that tolerance is a claim about *instrument
precision*, needs metadata that exists nowhere in this repository, and belongs at ingestion. An AST test
scans this package for those tokens. The consequence is documented rather than smoothed: with `L = 0.3`, a
high of `0.1 + 0.2` (`0.30000000000000004`) is a strict breach.

### 2.4 Wick versus close

Both, as separate kinds, neither privileged. `WICK_BREACH` says the extreme went beyond and the close did
not; `CLOSE_BREACH` says the close did. `open` is **never** consulted anywhere in the package.

### 2.5 Gap policy

An orthogonal `CrossingMechanism`:

| Member | Definition | Meaning |
|---|---|---|
| `WITHIN_RANGE` | `low <= L <= high` | price demonstrably reached the level in this candle |
| `GAPPED_BEYOND` | this candle wholly beyond, previous not | arrived on the far side without trading at the level |
| `ALREADY_BEYOND` | the **first** candle is wholly beyond | a state observation — no predecessor, so no arrival is claimed |

- `GAPPED_BEYOND` and `ALREADY_BEYOND` always carry `CLOSE_BREACH`; enforced, not incidental.
- **A candle wholly beyond whose predecessor was also wholly beyond emits nothing.** Without it, one
  breach would re-emit on every later candle.
- **`open` is not the test.** "Previous close below, next open above" is a *description* of a gap, not a
  definition: an open above the level whose low came back through it *did* trade at the level. The
  `low`/`high` test is the one that is actually true.
- **No time gap is inferred.** Nothing in the repository detects a missing bar; a gap here is a gap in
  price coverage between adjacent candles, whatever their spacing.
- `ALREADY_BEYOND` is kept separate from `GAPPED_BEYOND` because collapsing them would claim an arrival
  the data cannot support.

### 2.6 Outside-bar policy and intrabar honesty

A candle breaching an upper and a lower level produces **two events sharing one index and one timestamp**.
Their relative order in the output is the *level* ordering and is **explicitly not a claim about time**.

**There is deliberately no path field and no "intrabar order unknown" flag.** Intrabar order is *never*
known, for *every* event, so a flag that never varies carries no information — and would imply that its
absence means "known". The honest encoding is a model that cannot express a path at all, which a test
pins by asserting the event's field set.

`market_structure`'s outside-bar convention (two swing points at one index, HIGH before LOW) is **not**
reused. The subjects differ — levels, not points, any number at any prices — and the ordering rule here is
the level key. The two rules are separately tested.

### 2.7 Repeated-crossing policy and lifecycle

**All interactions are emitted; there is no lifecycle.** No level is active, spent, protected or
invalidated. First-crossing-only was rejected as alternative #3: it encodes "a level is spent once
crossed", which is a protected-level decision belonging to BOS, and it destroys re-tests that CHoCH may
need. A consumer derives first-cross in one pass.

**Activation is deliberately absent and is the sharpest edge.** Derivation evaluates *every* candle
against *every* level, including candles **before** a level's origin. Filtering would require deciding
whether a level exists at its pivot bar or only once that pivot is *confirmed* — a policy with no
data-derived answer, and unrepresentable for origin-less levels. A BOS consumer applies it by filtering
`event.index >= event.level.origin.index` on fields it already holds, without re-reading a candle.
Deferred question **D1**.

### 2.8 Event-ordering contract

```
(crossing candle index, level side, level price, level origin, level origin label)
```

`UPPER` before `LOWER`, from **explicit rank mappings** — never enum definition order, `.value` string
order, set order or hash order. A level without an origin sorts before one with an origin. Timestamp is
absent from the key because `CandleSeries` guarantees timestamps increase strictly with index; kind and
mechanism are absent because at most one event exists per (candle, level) pair.

**Input level order is not part of the contract** — all 24 permutations of a 4-level set give
byte-identical output. **Input candle order is** `CandleSeries`'s own guarantee. The derived run is
**validated against the key after derivation**, so a refactor that reorders the loops fails the suite
rather than silently shipping a different contract.

**Exact duplicate levels are rejected** (`DuplicateLevelError`), not deduplicated — validate, never repair.
An exact duplicate cannot come out of `structural_levels`, so it is always caller error. Levels differing
in *any* field, including provenance at one price, are distinct and both report.

### 2.9 Prefix-stability contract

**Exact, with no exceptions:**

```
derive_level_crossings(P, levels)
    == tuple(e for e in derive_level_crossings(P + E, levels) if e.index < len(P.closed().candles))
```

An event at candle `i` is a function of candle `i`, candle `i-1` and the level set. Nothing reads forward;
there is **no confirmation delay**, so unlike `detect_swings` this layer is complete at every prefix, and
unlike the state history there is no "complete-group extension" caveat.

Measured at **0 violations** over 121 prefixes × 22 levels on a seeded fixture with forced exact
equalities, outside bars, gaps and repeated crossings; 0 on the real `btcusdt_4h` fixture against
swing-derived levels; and 0 over an exhaustive two-candle × five-shape space.

### 2.10 Context contract integration

The safe pipeline calls exactly what ADR-0018 §6.1 designed:

```python
identity = require_same_identity(series, levels)
```

`CandleSeries` satisfies it through its projection, `ContextualSeries` through its field — one call, both
sides, no identity logic of this package's own, and no dependency on trend. Mismatched instruments and
timeframes raise before any arithmetic. Empty data retains a full identity. No API accepts an identity
argument, so substitution is unrepresentable. Identity propagates by reference and the tests assert `is`.

### 2.11 The immutable event model

```python
@dataclass(frozen=True, slots=True)
class LevelCrossingEvent:
    level: PriceLevel; candle: Candle; index: int
    kind: CrossingKind; mechanism: CrossingMechanism
    @property
    def timestamp(self) -> datetime: ...   # projects candle.timestamp
```

`timestamp` is a **projection, not a stored field**, per ADR-0016 §4. It is the *crossing* bar's time, not
the level origin's — review §15's fact #5, and the distinction a dedicated test pins with a provenanced
level whose origin timestamp differs.

**The event validates itself against its own fields.** `kind` must equal what the candle and level imply;
`mechanism` must agree with whether the candle lies wholly beyond. An event claiming `CLOSE_BREACH` for a
candle that closed inside cannot be constructed. `GAPPED_BEYOND` vs `ALREADY_BEYOND` is the one residue
that cannot self-check — it depends on the predecessor — and is documented rather than pretended away
(**D4**).

`index` matches `SwingPoint.index` exactly (a position in `series.closed().candles`), so BOS can join a
crossing to a swing without a translation table.

---

## 3. Dependency graph

```
fmis.data ──► fmis.market_structure ──► fmis.structural_trend
   │                   │                        │
   └───────────────────┴────────────────────────┴──► fmis.series_context
                                                            │
                                                            ▼
                                                   fmis.level_crossing
```

`fmis.level_crossing` imports `fmis.data`, `fmis.market_structure`, `fmis.series_context`. Nothing imports
it. No runtime dependency was added; stdlib only.

`fmis.series_context`'s "nothing below imports this package" guard was **narrowed** to exempt
`level_crossing` — the widening ADR-0018 §6.1 designed. The exemption is *named*, not pattern-matched, so
a second consumer must justify itself in an ADR. The direction the guard exists to protect is unchanged:
`fmis.data`, `fmis.market_structure` and `fmis.structural_trend` still cannot see it.

---

## 4. Public API

**Context-free primitives** — `crossing_kind`, `derive_level_crossings`, `structural_levels`.
**Safe pipeline** — `contextual_structural_levels`, `contextual_level_crossings`.
**Types** — `LevelSide`, `CrossingKind`, `CrossingMechanism`, `LevelOrigin`, `PriceLevel`,
`LevelCrossingEvent`. **Errors** — `LevelCrossingError`, `DuplicateLevelError`.

Identity mismatch reuses `SeriesIdentityMismatchError` rather than introducing a second identity error, so
this package's failure cannot be caught without catching the contract's.

### 4.1 Exact exception messages (a shipped contract, asserted with `==`)

| Message |
|---|
| `levels contains a duplicate level (upper 100.0); levels must be distinct` |
| `side 'upper' does not match the origin label (equal_low); expected 'lower'` |
| `kind 'touch' does not match the candle against the level (upper 100.0); expected 'close_breach'` |
| `candle does not reach the level (upper 100.0); no crossing to record` |
| `mechanism 'within_range' does not match the candle, which lies wholly beyond the level (upper 100.0)` |
| `mechanism 'gapped_beyond' does not match the candle, which reaches the level (upper 100.0) within its range; expected 'within_range'` |
| `series must be a CandleSeries, got str` · `levels must be a sequence of PriceLevel, got str` · `levels[1] must be a PriceLevel, got float` |
| `swings must be a sequence of StructuralSwing, got str` · `swings[0] must be a StructuralSwing, got int` |
| `swings must be a ContextualSeries, got tuple` · `levels must be a ContextualSeries, got tuple` |

No existing message was changed.

---

## 5. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| a `bool` for one candle and one price | loses when and how; every caller rebuilds the replay loop |
| batch returning **first** crossing per level | encodes a lifecycle policy belonging to BOS; destroys re-tests |
| **stateful level tracker** | makes the result a function of call order, which is exactly what prefix-stability testing then cannot prove; the repository has zero mutable module state and this is not the milestone to start |
| crossing embedded in future BOS | guarantees the duplication this milestone exists to prevent; untestable without a BOS policy that does not exist |
| methods on `Candle` / `CandleSeries` | drags structural vocabulary into `fmis.data`, which imports nothing internal |
| crossing inside `market_structure` | reintroduces `CandleSeries` below `detect_swings`, breaking the layering review §15 protects (the closest call) |
| a generic threshold utility outside market structure | abstraction over one caller; genericity strips provenance |
| event-sourced snapshot per candle | pays O(candles × levels) unconditionally for what the event list already carries |
| configurable crossing policy | makes historical events non-reproducible without their setting |
| an `intrabar_order_unknown` flag | always the same value, so it carries no information and implies its absence means "known" |
| silent deduplication of exact-duplicate levels | repairs instead of validating, and quietly changes the event count |

---

## 6. Consequences

**Gained.** A reusable, non-repainting, exactly prefix-stable crossing primitive; provenance carried from
swing to event; identity enforced at one choke point; a `kind`/`mechanism` vocabulary rich enough that BOS
needs no candle re-evaluation.

**Costs, accepted deliberately.**

- **O(candles × levels)** event volume. A 22-level grid straddling the price range produced 2036 events
  over 120 candles. Bounded, measured in the review, and the price of not baking in a lifecycle.
- **No activation** means a naive consumer can see a crossing of a level that did not yet exist (D1). Named
  loudly in the module docstring, the ADR and a dedicated test, rather than silently policy-fixed.
- **Exact float comparison** inherits ADR-0013 §4's limitation (D3).

**Limitations and deferred questions.**

| | Question | Status |
|---|---|---|
| **D1** | level activation — exclude candles before a level's origin or its confirmation? | deferred to BOS |
| **D2** | the **first swing of each type** has no `StructuralSwing` and therefore no level (2 of 5 points on the real fixture) | documented and tested; needs an `origin.label`-optional decision |
| **D3** | price tolerance / tick size | belongs at ingestion, behind a model that does not exist |
| **D4** | `GAPPED_BEYOND` vs `ALREADY_BEYOND` is not self-validating on the event | documented; both self-check as far as the fields allow |
| **D5** | time gaps are not detected — a gap here is in price coverage | no repository-wide gap contract exists |
| **D6** | multi-timeframe: indices are per-series, `timestamp` is the only cross-timeframe key | inherited from review §16 |
| **D7** | serialization: `pickle`-round-trippable like every sibling; no JSON schema anywhere | out of scope, consistent with precedent |

**Still deliberately absent:** BOS, CHoCH, protected levels, inducement, liquidity sweeps, support,
resistance, regime, bias, signals, entries, exits, stops, targets, sizing, confidence, AI interpretation,
persistence, multi-timeframe aggregation and every evidence descriptor for market structure.

---

## 7. Future integration

**BOS** consumes `ContextualSeries[LevelCrossingEvent]` and needs **no candle OHLC re-evaluation**: every
event carries level, provenance, label, index, timestamp, kind and mechanism. BOS adds — in its own
package — which level is protected, when protection ends, whether a `TOUCH` or `WICK_BREACH` counts, and
whether an `EQUAL_HIGH`-derived level breaks anything. Each reads a field already present.

**CHoCH** then consumes the **BOS sequence** and never sees a crossing or a candle, per review §15.

---

## 8. Validation

2849 tests pass (2609 baseline + 239 new + 1 added guard), identically with `-W error`.
**35/35 mutation probes detected, 0 no-ops, 0 survivors, all sources restored byte-for-byte with SHA-256
verification.** 0 export collisions. `pyproject.toml` and `uv.lock` unchanged.
