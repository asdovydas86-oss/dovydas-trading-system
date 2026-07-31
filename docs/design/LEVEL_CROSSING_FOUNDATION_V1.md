# Level-Crossing Foundation v1 — Design

**Status:** accepted — implemented by ADR-0019
**Baseline:** `c71d79e612db9b509b1393b92b5c1b06f5780d5a` — *Merge Series Identity & Context Contract v1 Review*
**Baseline metrics (re-derived, not trusted):** 2609 tests, 2609 with `-W error`, `market_structure` 1227,
`structural_trend` 353, `series_context` 183, state-history 267, ordering 33, export collisions 0.

---

## 1. The question this milestone answers

> Did price cross a specific structural price level, when did it happen, how did it happen, and under
> which explicit policy?

Nothing in the repository can answer it today. The market-structure architecture review §15 established
the gap precisely: **after `detect_swings`, no layer reads a candle**, so there is no fact of the form
*"price traded above level L at bar i"*. `SwingPoint` stores only the extreme, so *close vs wick* is not
derivable from swings alone. And a swing carries the **pivot's** timestamp, while a crossing happens at a
**different** bar that no existing fact carries.

This milestone supplies exactly those missing facts and stops there.

### 1.1 Why crossing is separated from BOS and CHoCH

A level crossing is a **geometric fact about two numbers and one candle**. Break of Structure is an
*interpretation* built from a crossing plus a decision about *which* level was protected, *when* it stopped
being protected, and whether an `EQUAL_HIGH` breaks anything. Change of Character is a further
interpretation over the *sequence* of those interpretations.

The review §15 fixed the ordering and it stands: **BOS is defined purely on levels, CHoCH over the BOS
sequence, trend as a summary of both.** Any definition in which trend is an input to BOS is rejected on
sight. This package therefore sits **below** all three and imports none of them.

The practical consequence: a crossing event must be usable by a BOS layer that *disagrees* with any
particular protected-level policy. That rules out baking activation, invalidation or protection into v1.

---

## 2. Audit — what the live repository already decides (Phases 1–2)

Every row below was read from source, not assumed. **No crossing-like logic exists anywhere**; the only
occurrences of "level"/"crossing" in `src/` are prohibitions and forward references.

| # | Question | Established answer | Source |
|---|---|---|---|
| 1 | Candle ordering | `CandleSeries` enforces **strictly increasing** UTC timestamps; no duplicates, no backwards steps | `data/models.py:CandleSeries.__post_init__` |
| 2 | Index ownership | A candle carries **no** index. Index is a *position in `series.closed().candles`*, assigned by the consumer | `market_structure/models.py` module docstring |
| 3 | Timestamp uniqueness | Guaranteed unique and increasing by `CandleSeries`; `Candle` alone validates only UTC-ness | `data/_timeutils.validate_utc_timestamp` |
| 4 | Numeric type | **`float`**, deliberately. `Decimal` explicitly deferred to money/execution | `data/models.py` module docstring; review §9 |
| 5 | Equal prices | Compared **exactly**, no epsilon. `EQUAL` is first-class and never folded away. An AST scan pins the absence of `isclose`/`tolerance`/`round`/`tick` | `models._relation_for`; ADR-0013 §4; review §9 |
| 6 | Outside bars | One candle yields **two** `SwingPoint`s at the **same index**, HIGH before LOW | `swings.detect_swings` final sort |
| 7 | Gaps | **No existing treatment anywhere.** `CandleSeries` permits arbitrary timestamp spacing; nothing detects or annotates a gap | verified by search |
| 8 | Swing time | The **pivot candle's** timestamp — not confirmation, not emission | `SwingPoint.timestamp` docstring |
| 9 | Level origin | Nothing marks any swing as a level. Review §15 fact #3: *"nothing marks any swing as 'the' level"* | review §15 |
| 10 | Legal dependencies | `market_structure` → `fmis.data` only. `structural_trend` → `market_structure` only. `series_context` → all three. **Nothing imports `series_context`** | `test_series_context.py:881,908` |

### 2.1 Conventions this package must obey

- **Frozen + slotted dataclasses**, hashable, validated in `__post_init__`; a model claiming a
  classification its own fields contradict **cannot be constructed** (`SwingComparison`, `StructuralSwing`).
- **Derived values are projections, not stored fields** — ADR-0016 §4: *"a stored copy of a value one
  attribute away is somewhere for it to drift."* (`CandleSeries.identity`,
  `StructuralSequenceStateSnapshot.index`).
- **`str`-valued `Enum`s**, exhaustive, with the deliberately-absent members named in the docstring.
- **One authoritative rule, kept private** — `_relation_for`, `_label_for`, `_validate_key_order`. A public
  variant would offer a shortcut past the invariants.
- **Validate order, never repair it.** Unsorted input is a caller bug.
- **Exact exception messages are a shipped contract**, asserted with `==`, not `match=`
  (`test_market_structure_ordering.py` module docstring).
- **Package error base + `ValueError` mixin** — `SeriesContextError` / `SeriesIdentityMismatchError`,
  matching `IngestError`, `RelativeValueError`.
- **The repository already names this package.** `series_context/pipeline.py:36`: *"A future
  candle-consuming sibling (Level-Crossing) joins the same contract through `require_same_identity`, and
  needs to import nothing from this module."* Review §15: *"**Recommendation: a sibling package**, so
  `market_structure` keeps its property that only its first stage touches candles."*

---

## 3. Architecture alternatives (Phase 4)

Twelve alternatives, scored against the required criteria. `+` good, `~` partial, `−` bad.

| # | Alternative | Determinism | Prefix-stable | Replay | Mutation-testable | Context integrity | Layering | BOS fit | CHoCH fit | Memory | API clarity | Speculative-abstraction risk | Duplication risk | Provenance | Multi-level | Outside-bar | Gaps | Type fit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `bool` for one candle + one price | + | + | + | ~ | − none | + | − loses when/how | − | + | + | + | − caller rebuilds the loop | − | − | − | − | ~ |
| 2 | rich event for one candle + one level | + | + | + | + | − none | + | ~ | ~ | + | + | + | ~ | + | − | ~ | ~ | + |
| 3 | batch, **first** crossing per level | + | + | + | + | + | + | ~ | − loses re-tests | + | ~ | − bakes a lifecycle policy | + | + | + | ~ | ~ | + |
| 4 | batch, **all** crossings | + | + | + | + | + | + | + | + | ~ O(n·m) | + | + | + | + | + | + | + | + |
| 5 | stateful level tracker | ~ | − order-dependent | − | − | ~ | ~ | + | + | + | − | − | + | + | + | ~ | + | ~ |
| 6 | immutable replay over candles+levels | + | + | + | + | + | + | + | + | ~ | + | + | + | + | + | + | + | + |
| 7 | crossing embedded in future BOS | + | + | + | − untestable alone | ~ | − inverted | n/a | − | + | − | + | − guarantees duplication | ~ | ~ | ~ | ~ | ~ |
| 8 | methods on `Candle`/`CandleSeries` | + | + | + | ~ | − | − drags structure into `fmis.data` | ~ | ~ | + | ~ | − | ~ | − | − | − | − | − |
| 9 | **dedicated sibling package** | + | + | + | + | + | + | + | + | + | + | + | + | + | + | + | + | + |
| 10 | inside `market_structure` | + | + | + | + | + | − reintroduces `CandleSeries` below `detect_swings` | + | + | + | ~ | + | + | + | + | + | + | + |
| 11 | generic threshold utility outside market structure | + | + | + | ~ | − no identity | ~ | − no provenance | − | + | ~ | − generalises with one caller | + | − | ~ | − | − | − |
| 12 | event-sourced snapshots (one per candle) | + | + | + | + | + | + | + | + | − O(n·m) always | ~ | − | + | + | + | + | + | + |

**Selected: 4 + 6 + 9 — an immutable batch replay over candles and levels, in a dedicated sibling package.**

Rejections worth recording:

- **#3 (first crossing only)** encodes a *lifecycle policy* — "a level is spent once crossed" — that
  belongs to BOS's protected-level decision, not to a geometric primitive. It also destroys re-tests,
  which CHoCH may need. Rejected on §1.1's grounds.
- **#5 (stateful tracker)** makes the result a function of *call order*, which is precisely what
  prefix-stability testing cannot then prove. The repository has zero mutable module state today
  (review §16) and this milestone will not be the first.
- **#7** guarantees the duplication the milestone exists to prevent, and makes the crossing rule
  untestable independently of a BOS policy that does not exist.
- **#10** is the only close call. It is rejected because `market_structure`'s stated property is that
  **only its first stage touches candles** (review §15, explicit recommendation). Reintroducing a
  `CandleSeries` dependency *below* `detect_swings` would break the layering the review protects.
- **#11** would abstract over one caller. `Candle`'s `high`/`low`/`close` triple and `LevelSide` are not
  a general threshold problem, and genericity would strip provenance.
- **#12** materialises one snapshot per candle even when nothing happens, paying O(n·m) unconditionally
  for information that #4 already carries.

---

## 4. Design decisions (Phases 3 & 6)

### 4.A What is a level?

Alternatives A1–A8 evaluated:

| | Reuse | Type safety | Serializable | Equality | Provenance | Duplicate prices | Equal H/L | Hand-made test levels | Dependency direction | BOS fit | Premature interpretation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 raw price | + | − | + | − collides | − | − indistinguishable | − | + | + | − | + |
| A2 price + direction | + | ~ | + | ~ | − | − | − | + | + | ~ | ~ conflates side with direction |
| A3 price + origin index/ts | + | ~ | + | + | ~ partial | + | + | ~ forces a fake origin | + | + | + |
| A4 price + swing provenance | ~ | + | + | + | + | + | + | − impossible without a swing | + | + | + |
| A5 generic `PriceLevel` | + | + | + | + | ~ | + | + | + | + | + | + |
| A6 separate `HighLevel`/`LowLevel` | − | + | + | + | ~ | + | + | + | + | ~ doubles every signature | + |
| A7 generic + explicit side | + | + | + | + | ~ | + | + | + | + | + | + |
| A8 level tied to a `Swing` | − | + | + | + | + | + | + | − | − forces the dependency | + | ~ |

**Selected: A5 + A7 + A4 combined — a generic `PriceLevel` with an explicit `side` and an *optional*
`origin`.**

```python
@dataclass(frozen=True, slots=True)
class LevelOrigin:
    index: int                    # closed-candle position of the pivot
    timestamp: datetime           # the pivot candle's timestamp
    label: StructuralSwingLabel   # the swing's own name, carried unchanged

@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: float
    side: LevelSide               # UPPER | LOWER
    origin: LevelOrigin | None = None
```

Why this shape:

- **`origin` is optional, and that is the whole point of A5 over A4.** A hand-written level in a test, or
  a future level from a source that is not a swing (a session high, a range boundary), must be
  representable without fabricating a pivot. A4 alone would make every test level a lie.
- **`origin` is *provenance*, never a policy.** It records where the level came from. It does not mark the
  level protected, active, or BOS-relevant, and nothing in this package reads `origin` except the
  ordering key.
- **`label` is carried, not reinterpreted.** An `EQUAL_HIGH`-derived level stays an `EQUAL_HIGH`-derived
  level. This package never renames a swing.
- **Equality is structural and exact**, inherited from every other model here. Two levels at the same
  price with different origins are **two levels**. Deduplicating them is a mutation probe (#14).
- **`side` is intrinsic.** A swing high yields an `UPPER` level. Evaluating a level "both ways" would
  require a caller decision this package must not make.

### 4.B What counts as a crossing?

B1–B8 all describe *one* rule each; the repository's own style (`EQUAL` is first-class, never folded)
says the answer is not to pick one and discard the rest, nor to make it configurable.

**Selected: B8 — one canonical v1 rule — combined with B7's distinctions expressed as *facts on the
event*, not as policies.**

For an **UPPER** level at price `L`, against one candle:

| Condition | Result |
|---|---|
| `high < L` | **no event** |
| `high == L` | `TOUCH` |
| `high > L` and `close <= L` | `WICK_BREACH` |
| `high > L` and `close > L` | `CLOSE_BREACH` |

For a **LOWER** level, mirrored on `low` and `close`:

| Condition | Result |
|---|---|
| `low > L` | **no event** |
| `low == L` | `TOUCH` |
| `low < L` and `close >= L` | `WICK_BREACH` |
| `low < L` and `close < L` | `CLOSE_BREACH` |

The three kinds are **mutually exclusive and exhaustive** over "an interaction occurred", by construction.
`CLOSE_BREACH` implies `high > L` because `high >= close`, so the kinds nest correctly and no candle can
close beyond a level it never reached.

Rejected: **B6 (configurable policy)**. A configurable crossing rule makes every historical event
non-reproducible without its setting — the identical argument review §9 uses to keep tolerance out of
`market_structure`. The distinctions callers would configure are already on the event as facts, so a BOS
layer that only trusts closes filters on `kind is CLOSE_BREACH` and gets a *stronger* guarantee than a
setting would have given it.

Vocabulary, fixed and never used interchangeably:

- **touch** — the extreme reached the level *exactly*. Not a breach.
- **strict breach** — the extreme went *strictly* beyond. `WICK_BREACH` or `CLOSE_BREACH`.
- **close-confirmed breach** — `CLOSE_BREACH` only.
- **gap beyond** — mechanism `GAPPED_BEYOND` (§4.G).
- **trading through** — mechanism `WITHIN_RANGE`: `low <= L <= high`.
- **opening beyond** — not a separate concept. `open` is deliberately **not** consulted (§4.G).

### 4.C Equality policy

| Question | Decision |
|---|---|
| Does exact equality count as a touch? | **Yes** — `TOUCH`. |
| Does exact equality count as a crossing/breach? | **No.** A breach requires strict `>` / `<`. |
| Is `EQUAL_HIGH` treated differently from `HIGHER_HIGH`? | **No** — as *levels*. Both yield an `UPPER` level at the swing's price, and the label is carried through untouched so a later layer can decide. Treating them differently here would be BOS policy. |
| Is `EQUAL_LOW` treated differently from `LOWER_LOW`? | **No**, same reasoning. |
| Does equality require a later strict breach? | Not to be *reported* — a `TOUCH` is a fact in its own right. Whether a break requires more than a touch is BOS's decision, and the distinct `kind` is what lets BOS make it. |
| Can repeated touches occur before the first crossing? | **Yes**, and each is emitted. |
| Can a touched level remain active? | There is **no active/inactive state in v1** (§4.I). A touch consumes nothing. |

Comparison is **exact on stored floats**. No epsilon, no tick size, no `isclose`, no rounding, no
`Decimal`. This is not a new decision: ADR-0013 §4 and review §9 already forbid tolerance in structural
comparison and record that it belongs at ingestion, behind a tick-size model that does not exist. An
architecture test scans this package's source for those tokens.

Experiment 21 pins the consequence: with `L = 0.3`, a candle whose high is `0.1 + 0.2`
(`0.30000000000000004`) is a **strict breach**, not a touch. Deterministic, reproducible, and documented
rather than smoothed away.

### 4.D Direction

**Decision: there is no `direction` field.** `LevelSide` alone carries the sense, and "beyond" means
*above* for `UPPER` and *below* for `LOWER`.

The candidate meanings were each rejected for a specific reason:

| Candidate meaning of "direction" | Verdict |
|---|---|
| upward / downward crossing | redundant with `side` — an `UPPER` level is only ever breached upward |
| crossing of an upper / lower level | that *is* `side` |
| candle movement from one side to the other | not knowable — OHLC does not prove the path (§4.F) |
| resulting side after the close | already carried, exactly, by `CLOSE_BREACH` vs `WICK_BREACH` |
| trade / trend direction | forbidden — trading semantics |

A separate field would be a second place for the same fact to disagree, and its name would invite
conflation with candle direction (`close > open`), trade direction and trend direction. The four are named
in the module docstring as distinct, precisely so no one merges them later.

### 4.E Event time and index

A `LevelCrossingEvent` records:

| Field | Meaning |
|---|---|
| `level` | the `PriceLevel` object **by reference** — carries the origin index/timestamp |
| `candle` | the crossing `Candle` **by reference** |
| `index` | the crossing candle's position in `series.closed().candles` |
| `kind` | `TOUCH` / `WICK_BREACH` / `CLOSE_BREACH` |
| `mechanism` | `WITHIN_RANGE` / `GAPPED_BEYOND` / `ALREADY_BEYOND` |
| `timestamp` | **a property projecting `candle.timestamp`** — not a stored field |

Deliberately **not** recorded: first-touch index, first-breach index, close-confirmation index, detection
index, emission index. There is no confirmation delay and no detection step, so each of those would be
either a duplicate of `index` or a lifecycle concept v1 does not have (§4.I).

`timestamp` is a projection for ADR-0016 §4's reason. Storing it beside `candle` would create a second
copy of a value one attribute away.

**Index semantics match `SwingPoint.index` exactly** — a position in the *closed* candle sequence — so a
future BOS layer can join a crossing to a swing on index without a translation table. Derivation runs on
`series.closed()`, idempotently.

**No intrabar timing is claimed.** The event says *at this candle*, never *at this moment within it*.

### 4.F Outside bars

A candle whose high exceeds an upper level **and** whose low undercuts a lower level produces **two
events**, one per level, sharing one `index` and one `timestamp`.

**Their relative order in the output is the level ordering (§4.H), and it is explicitly not a claim about
time.** OHLC data does not record whether the high or the low came first, and the model refuses to
fabricate it. This is stated in the module docstring, in the ADR, and in the event type's own docstring,
because a consumer reading two same-index events *will* be tempted to read sequence into them.

Rejected: an `intrabar_order_unknown` boolean or an `INTRABAR_UNKNOWN` enum member. Intrabar order is
**never** known, for every event, so a flag that is always the same value carries no information and
would imply that its absence means "known". The honest encoding is that the model has no path field at
all, which is unrepresentable-by-construction rather than flagged.

**This is independent of `market_structure`'s outside-bar policy, deliberately.** That policy groups two
*swing points* at one index and orders HIGH before LOW. Here the subjects are *levels*, which may be any
number at any prices, and the ordering rule is the level key. Reusing the swing convention blindly would
be wrong — the semantics differ — and the two rules are separately tested.

A single candle can also breach **two upper levels and one lower level**, or any combination; each
(candle, level) pair is evaluated independently.

### 4.G Gap crossings

`mechanism` answers this, as an orthogonal fact:

| Mechanism | Definition | Meaning |
|---|---|---|
| `WITHIN_RANGE` | `low <= L <= high` | price demonstrably reached the level during this candle |
| `GAPPED_BEYOND` | this candle lies **wholly** beyond `L`, the previous candle did not | price arrived on the far side without trading at the level |
| `ALREADY_BEYOND` | the **first** candle of the series lies wholly beyond `L` | a state observation, not a crossing — there is no predecessor, so no arrival can be claimed |

"Wholly beyond" is `low > L` for `UPPER`, `high < L` for `LOWER`.

Consequences, all deliberate:

- `GAPPED_BEYOND` and `ALREADY_BEYOND` always carry `kind is CLOSE_BREACH`, because `low > L` forces
  `close > L`. This is an **enforced invariant** on the event, not a coincidence.
- **A candle wholly beyond a level whose predecessor was also wholly beyond emits nothing.** Nothing
  happened; price was already there. Without this rule a level breached once would re-emit on every
  subsequent candle, turning a 10,000-candle series into 10,000 meaningless events per level.
- The rule looks at candle `i-1` and `i` only, both inside any prefix containing `i`, so prefix stability
  is preserved exactly (§4.J).
- **`open` is never consulted.** "Previous close below, next open above" is a *description* of a gap, not
  a definition: an open above the level with a low back below it traded at the level, and is
  `WITHIN_RANGE`. Using `open` would misclassify exactly that case. The `low`/`high` test is the one that
  is actually true.
- **Missing candles are not inferred.** `CandleSeries` permits arbitrary timestamp spacing and nothing in
  the repository detects a gap in *time*; this package adds no such inference. A gap here is a gap in
  *price coverage between adjacent candles*, whatever their spacing.

`ALREADY_BEYOND` is separated from `GAPPED_BEYOND` because collapsing them would claim an arrival that
the data cannot support — the series simply starts there. Mutation probe #34 targets exactly this.

### 4.H Multiple levels and event ordering

Levels are canonically ordered by a **total key derived entirely from level content**:

```
(side_rank, price, origin_rank, origin_index, origin_timestamp, label_rank)
```

- `side_rank` — `UPPER` = 0, `LOWER` = 1, from an explicit `MappingProxyType`. **Never** enum definition
  order, `.value` string order, or hash order.
- `label_rank` — likewise explicit.
- `origin_rank` — a level without an origin sorts before one with an origin, so the key is total across
  the optional field without a sentinel that could collide with real data.

Events are emitted **candle-major, level-minor**: for each candle in index order, for each level in
canonical order. The full ordering contract is therefore:

```
(candle index, level side, level price, level origin, level label)
```

`timestamp` need not appear in the key: `CandleSeries` guarantees timestamps increase strictly with index,
so index order *is* timestamp order. `kind` and `mechanism` need not appear: at most one event exists per
(candle, level) pair, so the key is already total.

The order is **validated after derivation** by a private ordering check, so a future refactor that
reorders the loops fails the suite rather than silently changing a contract.

**Input level order is not part of the contract.** All 24 permutations of a 4-level set produce
byte-identical output (experiment 22), and this is asserted as a property. Input *candle* order **is**
part of the contract, and is `CandleSeries`'s own guarantee.

**Duplicate levels.** Two levels at the same price with different provenance are **two distinct levels**
producing **two events**. Two levels equal in *every* field are **rejected** with
`DuplicateLevelError`. Rejection rather than silent deduplication follows the repository's
validate-never-repair rule: an exact duplicate cannot arise from `structural_levels` (origins differ by
index), so it is always caller error, and silently collapsing it would hide the bug while quietly
changing the event count.

### 4.I Level lifecycle

**v1 has none, and that is the decision.**

| Feature | v1 | Why |
|---|---|---|
| repeated crossings | **yes, all emitted** | the primitive is per-candle interaction |
| first crossing only | no | a lifecycle policy (§3, alternative #3) belonging to BOS |
| active / inactive state | no | protected-level management, explicitly out of scope |
| invalidation | no | same |
| activation (ignore candles before `origin.index`) | **no** | see below |
| crossing history per candle | no | alternative #12, rejected |

**Activation is the sharp edge, so it is stated loudly.** `derive_level_crossings` evaluates *every*
candle against *every* level, including candles **before** the level's origin. It is a pure geometric
predicate over (candles, levels) with no notion of a level being born.

This is deliberate and it is a real footgun. The alternative — silently skipping candles before
`origin.index` — would be a policy decision (does a level exist at its pivot bar, or only once the pivot
is *confirmed* `right_bars` later?) that this package has no basis to make, and it would be
unrepresentable for origin-less levels. A BOS consumer that wants activation filters
`event.index >= event.level.origin.index` on the events it already has, without re-reading a candle.
Recorded as deferred question D1.

First-crossing-only is likewise derivable by the consumer, in one pass, from the full list.

### 4.J Prefix stability

**Contract: for any prefix `P` of a closed candle series and any extension `P + E`,**

```
derive_level_crossings(P, levels) == tuple(e for e in derive_level_crossings(P + E, levels)
                                           if e.index < len(P.closed().candles))
```

**exactly, with no exceptions.** Events attributable to candles inside `P` do not change; nor does their
order, kind, mechanism, level identity, index or timestamp; and no earlier crossing appears only because
later candles arrived.

This holds structurally, not by luck: an event at candle `i` is a function of candle `i`, candle `i-1`,
and the level set. Nothing reads forward. There is **no confirmation delay and no delayed confirmation**,
so unlike `detect_swings` (which cannot classify the newest `right_bars` candles yet) this layer is
complete at every prefix.

Measured: **0 violations** over 121 prefixes × 22 levels on a seeded fixture with forced exact equalities,
outside bars, gaps and repeated crossings (experiment 19, 2036 events), and 0 violations on the real
`btcusdt_4h` fixture against swing-derived levels.

### 4.K Context integrity

Identity is validated through **Series Identity & Context Contract v1**, using its public API only:

```python
identity = require_same_identity(candle_series, contextual_levels)
```

This is exactly the shape ADR-0018 §6.1 designed for: `CandleSeries` satisfies the check through its
`identity` projection, a `ContextualSeries` through its field, so **one call covers both sides** and this
package needs no identity logic of its own — and no dependency on `fmis.structural_trend`.

- Different instruments → `SeriesIdentityMismatchError` (experiment 17).
- Different timeframes → `SeriesIdentityMismatchError` (experiment 18).
- Empty contextual inputs **retain identity**: an empty level set or an empty candle series yields
  `ContextualSeries(identity=<same object>, values=())`.
- **Identity never reaches the arithmetic.** No context-free function accepts an envelope; the wrappers
  unwrap, delegate and re-wrap. Proved by the equivalence tests, not asserted.
- **No API accepts an identity argument**, so substitution is unrepresentable rather than discouraged.
- Identity is carried **by reference** — the object `require_same_identity` returned — and tests assert
  `is`, not `==`.

**One test change is required and it is a guard, not semantics.** `test_series_context.py`'s
`test_nothing_below_imports_series_context` asserts that *nothing in `fmis`* imports `fmis.series_context`.
That was true when `series_context` was the top layer. `fmis.level_crossing` sits **above** it, exactly as
ADR-0018 §6.1 prescribes, so the guard is narrowed to "nothing below it" — every package except
`level_crossing`. No production behaviour changes; the replacement is stricter about the rest.

### 4.L Low-level and safe APIs

**Category 1 — context-free deterministic primitives** (raw candles and levels; no identity):

| Function | Signature |
|---|---|
| `crossing_kind` | `(candle: Candle, level: PriceLevel) -> CrossingKind \| None` |
| `derive_level_crossings` | `(series: CandleSeries, levels: Sequence[PriceLevel]) -> tuple[LevelCrossingEvent, ...]` |
| `structural_levels` | `(swings: Sequence[StructuralSwing]) -> tuple[PriceLevel, ...]` |

**Category 2 — safe context-aware pipeline APIs** (require/return `ContextualSeries`):

| Function | Signature |
|---|---|
| `contextual_structural_levels` | `(swings: ContextualSeries[StructuralSwing]) -> ContextualSeries[PriceLevel]` |
| `contextual_level_crossings` | `(series: CandleSeries, levels: ContextualSeries[PriceLevel]) -> ContextualSeries[LevelCrossingEvent]` |

Raw primitives **stay public**, matching ADR-0018's classification of `detect_swings` et al: they are
useful, testable, and their context-freeness is the property that makes the equivalence proof possible.

`crossing_kind` is the **one authoritative predicate**; the batch function calls it rather than
re-deriving, enforced by an AST test. Note the deliberate seam: `crossing_kind` answers *"how does this
candle stand against this level"* for **any** candle, while the batch adds the §4.G suppression rule for
a candle whose predecessor was already wholly beyond. Both halves are separately tested.

Level construction from swings **does** belong here: it is the join between two existing vocabularies and
has no home in either — `market_structure` must not learn the word "level", and `series_context` must not
learn arithmetic. It **delegates entirely**: it reads `swing.comparison.current` and `swing.label` and
reinterprets nothing.

**Known limitation, tested and documented (D2).** `structural_levels` derives from `StructuralSwing`,
whose `comparison.current` covers every confirmed swing **except the first of each type** — those are
only ever a `previous`, so they carry no label and have no `StructuralSwing`. On the `btcusdt_4h` fixture
this omits exactly 2 of 5 swing points. A caller needing them constructs a `PriceLevel` from the
`SwingPoint` directly, with `origin=None`. Widening this needs an `origin.label`-optional decision that
v1 declines to make speculatively.

---

## 5. Dependency graph

```
                       fmis.data
                  (Candle, CandleSeries, SeriesIdentity)
                    │                       │
                    ▼                       │
           fmis.market_structure             │
        (SwingPoint … StructuralSwing)       │
            │            │                   │
            │            ▼                   │
            │   fmis.structural_trend        │
            │            │                   │
            ▼            ▼                   ▼
              fmis.series_context
        (ContextualSeries, require_same_identity)
                         │
                         ▼
                 fmis.level_crossing          ← this milestone
```

`fmis.level_crossing` imports **`fmis.data`, `fmis.market_structure` and `fmis.series_context`**.

**Prohibited imports, each guarded by a test:** `fmis.structural_trend` (§1.1 — trend must never be an
input to a level fact), `fmis.decision_support`, `fmis.evidence`, `fmis.providers`, `fmis.pipeline`,
`fmis.ingest`, `fmis.trading_context`, `fmis.relative_value`, `fmis.features`, `fmis.alignment`, and any
private submodule of a dependency (`fmis.series_context.models`, `fmis.market_structure.models`, …).
Nothing imports `fmis.level_crossing`. Stdlib only; **no runtime dependency is added**.

### 5.1 Worked example

```
CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=(...))
    │
    ▼  contextual_structural_swings(series)              [series_context]
ContextualSeries[StructuralSwing]        identity = BTCUSDT/4h
    │
    ▼  contextual_structural_levels(swings)              [level_crossing]
ContextualSeries[PriceLevel]             identity carried by reference
    │
    ▼  contextual_level_crossings(series, levels)        [level_crossing]
    │      └─ require_same_identity(series, levels)  → BTCUSDT/4h  or raise
ContextualSeries[LevelCrossingEvent]     identity carried by reference
```

`fmis.structural_trend` appears **nowhere** in this chain. The audit found no factual reason for it: a
crossing is a comparison of a price to a number, and trend is a summary of structure that would make the
dependency circular under review §15's ordering.

### 5.2 Future BOS / CHoCH integration shape

A BOS layer consumes `ContextualSeries[LevelCrossingEvent]` and needs **no candle OHLC re-evaluation**:
every event carries its level (with provenance and label), its index, its timestamp, its kind and its
mechanism. BOS adds, on top and in its own package: which level is protected, when protection ends,
whether a `TOUCH` or a `WICK_BREACH` counts, and whether an `EQUAL_HIGH`-derived level breaks anything.
Every one of those reads a field that is already on the event.

CHoCH then consumes the **BOS sequence** and never sees a crossing or a candle, per review §15.

The event carries `candle` by reference so that a consumer *may* look, and so the model can validate
itself (§6); the guarantee is that BOS does not *need* to.

---

## 6. Models, validation and exceptions

| Type | Fields | Enforced on construction |
|---|---|---|
| `LevelSide` | `UPPER`, `LOWER` | — |
| `CrossingKind` | `TOUCH`, `WICK_BREACH`, `CLOSE_BREACH` | — |
| `CrossingMechanism` | `WITHIN_RANGE`, `GAPPED_BEYOND`, `ALREADY_BEYOND` | — |
| `LevelOrigin` | `index`, `timestamp`, `label` | int (not `bool`), non-negative; `datetime`; `StructuralSwingLabel` |
| `PriceLevel` | `price`, `side`, `origin` | finite number (not `bool`); `LevelSide`; `LevelOrigin` or `None`; **`side` must agree with `origin.label`'s own side** |
| `LevelCrossingEvent` | `level`, `candle`, `index`, `kind`, `mechanism` | types; non-negative index; **`kind` must equal `crossing_kind(candle, level)`**; **`mechanism` must be consistent with the candle's range** |

The event's self-validation is the strongest invariant in the design: an event claiming `CLOSE_BREACH`
for a candle that closed inside, or `WITHIN_RANGE` for a candle wholly beyond, **cannot be constructed**.
This is `SwingComparison`'s rule applied here.

`GAPPED_BEYOND` vs `ALREADY_BEYOND` is the one distinction the event **cannot** self-check — it depends on
the predecessor, which the event does not carry. Both are validated as far as they can be (both require
the candle to be wholly beyond), and the residue is documented rather than pretended away.

`PriceLevel`'s side/label agreement (`EQUAL_HIGH` → `UPPER`, `HIGHER_LOW` → `LOWER`, …) makes a level
that contradicts its own provenance unconstructable, via one authoritative private mapping.

**Exceptions**, following the package-error + `ValueError` mixin convention:

```python
class LevelCrossingError(Exception): ...
class DuplicateLevelError(LevelCrossingError, ValueError): ...
```

Identity mismatch reuses `SeriesIdentityMismatchError` — no second identity error type is introduced,
because `require_same_identity` is the single choke point and a wrapper type would let this package's
error be caught without catching the contract's.

Every message is exact, tested with `==`, and listed in the ADR.

---

## 7. Test and mutation strategy

- **Context-free / context-aware equivalence** across empty candles, empty levels, single upper, single
  lower, equal touch, wick breach, close breach, gap breach, outside bar, multiple levels, duplicate
  prices and repeated interactions: the envelope's `values` must equal the bare function's return.
- **Prefix stability** over handcrafted edge cases, equal prices, outside bars, gaps, repeated crossings,
  many and duplicate levels, seeded deterministic fixtures, and the real `btcusdt_4h` fixture.
- **Property/combinatorial tests**, deterministic and dependency-free: raising a high cannot remove a
  strict upper breach; lowering a low cannot remove a lower breach; changing only identity cannot change
  a payload; appending candles cannot modify earlier events; permuting levels cannot change the output;
  no event references a candle or level outside the input; every event satisfies `crossing_kind`; the
  ordering key is monotonic; repeated execution is identical; empty input yields an immutable empty
  result; provenance survives wrapping.
- **Architecture guards** (AST): no forbidden import, no tolerance token, no `global`, no module-level
  mutable object, no wall-clock (`datetime.now`, `time.`), no `random`, no re-implementation of swing,
  state or trend logic, single call-site for the authoritative predicate.
- **Mutation validation**: 35 probes, each verified to change the source SHA, be detected by at least one
  named test, and restore byte-for-byte with SHA-256 verification. Harness lives outside the repository
  and is deleted before committing.

---

## 8. Experiment results (Phase 5) — 25/25 PASS

Prototyped outside production against the real repository types; scratch files deleted before committing.

| # | Demonstration | Result |
|---|---|---|
| 1 | strict wick crossing, upper | **PASS** — `high>L, close<L` → `WICK_BREACH` |
| 2 | inclusive wick touch | **PASS** — `high == L` → `TOUCH` |
| 3 | strict close crossing | **PASS** — `close > L` → `CLOSE_BREACH` |
| 4 | inclusive close touch | **PASS** — `close == L` is **not** a close breach → `WICK_BREACH` |
| 5 | same candle touching but not strictly breaching | **PASS** — `high < L` → no event |
| 6 | gap above an upper level | **PASS** — 1 event, `GAPPED_BEYOND` + `CLOSE_BREACH` |
| 7 | gap below a lower level | **PASS** — 1 event, `GAPPED_BEYOND` + `CLOSE_BREACH` |
| 8 | candle crossing 3 upper levels | **PASS** — 3 events, prices ascending `[100, 101, 102]` |
| 9 | candle crossing 3 lower levels | **PASS** — 3 events, `[90, 91, 92]` |
| 10 | outside bar crossing one upper and one lower | **PASS** — 2 events, one index, UPPER then LOWER |
| 11 | duplicate price, different provenance | **PASS** — 2 distinct events, neither collapsed |
| 12 | two exactly identical levels | **PASS** — rejected |
| 13 | empty candles | **PASS** — `()` |
| 14 | empty levels | **PASS** — `()` |
| 15 | first candle already beyond | **PASS** — 1 event at index 0, `ALREADY_BEYOND` |
| 16 | level whose origin postdates the crossing | **PASS** — reported; no activation policy (D1) |
| 17 | BTCUSDT levels + ETHUSDT candles | **PASS** — `subjects[1] has identity 'BTCUSDT'/'4h', expected 'ETHUSDT'/'4h'` |
| 18 | BTCUSDT 1h candles + BTCUSDT 4h levels | **PASS** — `subjects[1] has identity 'BTCUSDT'/'4h', expected 'BTCUSDT'/'1h'` |
| 19 | prefix-extension stability | **PASS** — **0 violations**, 121 prefixes × 22 levels, 2036 events |
| 20 | repeated crossing behaviour | **PASS** — cross, retreat, re-cross → 3 events at indices 0,1,2 |
| 21 | equality at a binary float boundary | **PASS** — `0.1+0.2 = 0.30000000000000004` vs `0.3` → strict `WICK_BREACH`, not `TOUCH` |
| 22 | deterministic event ordering | **PASS** — all **24** permutations of a 4-level set byte-identical |
| 23 | same payload under different identities | **PASS** — identity never enters the arithmetic |
| 24 | one immutable level reused across derivations | **PASS** — 100 events, `level is` the shared object |
| 25 | replay determinism | **PASS** — structurally equal |

Additional measurements carried into the design:

- On the real `btcusdt_4h` fixture: 20 candles → 3 structural swings → 3 levels → **15 events**, **0**
  prefix-stability violations, and exactly **2** swing points omitted by the first-of-type limitation (D2).
- Event density is the cost of alternative #4: a 22-level grid straddling the price range produced 2036
  events over 120 candles. Bounded by O(candles × levels) and measured in the review.

---

## 9. Limitations and deferred questions

| | Question | Status |
|---|---|---|
| **D1** | **Level activation** — should candles before `origin.index` (or before the pivot's *confirmation* bar) be excluded? | Deferred to BOS. v1 reports all; the consumer filters on fields it already has. |
| **D2** | **First swing of each type** has no `StructuralSwing` and therefore no level. | Documented and tested. Needs an `origin.label`-optional decision. |
| **D3** | **Price tolerance / tick size.** Exact float comparison inherits ADR-0013 §4's limitation. | Belongs at ingestion, behind a tick-size model that does not exist. |
| **D4** | **`GAPPED_BEYOND` vs `ALREADY_BEYOND` is not self-validating** on the event. | Documented; both self-check as far as the fields allow. |
| **D5** | **Time gaps are not detected.** A gap here is a gap in price coverage, not in the clock. | No repository-wide gap contract exists yet. |
| **D6** | **Multi-timeframe.** Indices are per-series; `timestamp` is the only cross-timeframe key. | Inherited from review §16; unchanged. |
| **D7** | **Serialization.** Types are `pickle`-round-trippable like every sibling model; no JSON schema exists anywhere in the repository. | Out of scope, consistent with precedent. |

**No P0 or P1 design question remains unresolved.**
