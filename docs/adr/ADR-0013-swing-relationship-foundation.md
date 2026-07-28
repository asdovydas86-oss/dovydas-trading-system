# ADR-0013 — Swing relationship foundation: comparison without naming

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** how consecutive swings are compared, and why the familiar HH/HL/LH/LL names are withheld
(Milestone W)
**Implemented by:** `Add swing relationship foundation`
**Relates to:** [ADR-0012](ADR-0012-market-structure-foundation.md) (the swing points this compares);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence);
[ADR-0008](ADR-0008-decision-support-evidence-boundary.md) (`Comparison`, the similar-looking enum in a
different layer)

---

## Context

`detect_swings` locates extremes. Every structural concept above it — break of structure, change of
character, trend, consolidation — is defined by *comparing* those extremes. The comparison itself is
arithmetic on two numbers; almost all of the difficulty is in not saying more than the arithmetic
supports.

The specific trap: the moment a swing high that exceeds the previous swing high is called a "higher
high", the phrase carries a reading of the market that the two numbers do not contain. That reading may
well be reasonable, but it should be a decision someone made, not a side effect of naming a variable.

## Decisions

### 1. Comparisons are same-type only
A swing high is compared to the previous swing **high**; a low to the previous **low**. Comparing a high
to a low would relate two different measurements — where price stopped rising versus where it stopped
falling — and the resulting number would mean nothing. `SwingComparison` enforces it, and
`compare_swing_sequence` tracks the latest point of each type independently, so interleaving in any
pattern produces the same pairs.

### 2. `SwingRelation` is numeric, not directional
`HIGHER`, `LOWER`, `EQUAL` — three members, describing which of two prices is the larger number.

`HIGHER` on a swing low says the low sits at a higher price than the low before it. It does **not** say
"uptrend", and the enum has no vocabulary to say so: no BULLISH, BEARISH, LONG, SHORT, BUY, SELL, BREAK,
REVERSAL, CONTINUATION, CONFIDENCE, or STRENGTH. A test asserts their absence.

There is also no `UNAVAILABLE` member. Both swings always exist and always carry a finite price, so every
comparison resolves.

**Not a duplicate of `decision_support.Comparison`** (ABOVE/BELOW/EQUAL/UNAVAILABLE), despite the shape.
That enum lives in a higher layer this package may not import, models possibly-missing values, and
describes spatial position of one value against another rather than movement between two points in a
sequence. Reusing it would have inverted the dependency direction for a three-member enum.

### 3. HH / HL / LH / LL naming is deliberately withheld
`SwingType.HIGH` + `SwingRelation.HIGHER` is what a chartist calls a "higher high". This milestone keeps
the two facts **separate** rather than fusing them into one word.

The reason is not pedantry. A single label makes it easy to write `if higher_high: trend = "up"` without
ever deciding what a higher high means in the presence of an equal low, a longer timeframe, or a gap. Two
orthogonal facts force the naming layer to state its own rule and own it. The composite vocabulary is a
later milestone, and it will need a decision record about exactly those cases.

### 4. Exact price comparison, no tolerance
```
current.price > previous.price  -> HIGHER
current.price < previous.price  -> LOWER
otherwise                       -> EQUAL
```
Applied to the stored `float` values with **no epsilon, tolerance, percentage band, ATR scaling, or
volatility adjustment**.

This follows an audit rather than a preference. `Candle` stores OHLCV as plain `float` and its own
docstring records that `Decimal` is deferred; there is **no tick-size, instrument-precision, or
price-normalization abstraction anywhere in the repository**. Any tolerance would therefore be a number
invented locally, in one module, with nothing to calibrate it against — and it would silently make two
genuinely different prices "equal" at a threshold nobody chose. The same reasoning is already recorded in
`decision_support.classify_comparison`, which compares exactly for the same reason.

**This is a storage-level determinism policy, not an exchange-level tick-equivalence policy.** It says
two stored `float` values are equal, which is not the same claim as "these two prices are the same price"
at the instrument's tick size. Two prices that differ only by floating-point representation error compare
as `HIGHER` or `LOWER` rather than `EQUAL`. In practice swing prices are
exchange-reported values that round-trip through `float` unchanged, so exact equality does occur and is
reported. But the system cannot currently express "equal to within one tick", because it does not know
what a tick is for any instrument. When a tick-size or price-precision abstraction is introduced, this is
one of the first places that should consult it — and that will be an explicit change, not a quiet one.

### 5. Order is validated, never repaired
Unsorted input raises. Silently sorting would hide a caller's bug *and* produce comparisons between the
wrong pairs, which is worse than failing: the output would look plausible. `compare_swings` likewise
rejects reversed arguments rather than swapping them, because "previous" and "current" are the caller's
claim about the direction of time.

The ordering contract is **global non-decreasing index, strict within each type**:

  * indices non-decreasing across the whole input;
  * within a `SwingType`, index and timestamp strictly increasing;
  * points sharing an index must share a timestamp.

**Global strictness is deliberately not required**, and this was found by testing rather than assumed: a
single outside candle legitimately yields two points at one index — one HIGH and one LOW — so a global
"reject duplicate index" rule would reject valid `detect_swings` output and make these two layers unable
to compose, which is the entire point of the milestone. Per-type strictness is what actually matters,
because it is what guarantees each comparison links two distinct candles.

### 6. The price rule is private; `compare_swings` is the only public pair operation
The comparison rule lives in one place, `models._relation_for`, used by both
`SwingComparison.__post_init__` and `compare_swings`. It is **private on purpose**: it compares prices
and checks nothing else, so a public version would accept mixed swing types and reversed ordering — the
exact invariants `SwingComparison` exists to enforce — while looking like the obvious thing to call. One
authoritative rule, one validated entry point.

### 7. Equal `current.index` ties break on input order
Two comparisons can share a `current.index`, because one candle may produce both a HIGH and a LOW. Their
relative order is **the order those points appeared in the input**: the walk emits as it encounters, so
the tie-break is neither enum declaration order nor dictionary iteration order, and does not depend on
any implementation detail that could shift. For `detect_swings` output this means HIGH before LOW,
because that is the order the detector emits. Documented and tested in both directions.

### 8. Prefix stability
A comparison depends only on two points that were already present when it was produced, so appending
later swing points can add comparisons but never change one already emitted. This inherits directly from
`detect_swings` being non-repainting (ADR-0012 §2-3): if the points are stable, comparisons between them
are stable.

It matters for the same reason it mattered one layer down. Anything built on top — a structure break, a
backtest, a recorded observation — is only reproducible if the facts underneath do not silently change as
data arrives. A property test walks every prefix of randomized runs and asserts no emitted comparison ever
differs.

### 9. This layer consumes swing points and nothing else
No candles, no `detect_swings` call, no state, no side effects. A test asserts the module never references
a candle field or the detector. Keeping detection and comparison separable means either can be tested,
replaced, or reasoned about without the other.

### 10. Nothing is interpreted
No BOS, CHoCH, trend, regime, support, resistance, liquidity, strength, confidence, evidence descriptor,
or observation. `EvidenceFamily.MARKET_STRUCTURE` stays empty: comparisons are computed, not classified,
and ADR-0011 §1 is explicit that a calculation is not automatically evidence.

## Alternatives considered

- **A single `SwingLabel` enum** with HIGHER_HIGH, LOWER_HIGH, HIGHER_LOW, LOWER_LOW. Rejected: it fuses
  two orthogonal facts and smuggles interpretation into a data type (§3). It is also lossy for the equal
  case, which would need four more members.
- **Reuse `decision_support.Comparison`.** Rejected: wrong layer, wrong direction of dependency, and it
  carries an `UNAVAILABLE` state that cannot occur here (§2).
- **Compare each swing to the immediately preceding swing of either type.** Rejected: relates
  incommensurable measurements (§1).
- **A relative tolerance** (e.g. 0.01%) for `EQUAL`. Rejected: no repository-wide price-normalization or
  tick-size mechanism exists to justify a number, so it would be locally invented (§4).
- **Sort the input silently.** Rejected: hides a caller bug and produces plausible-looking wrong pairs
  (§5).
- **Require globally strict indices.** Rejected after testing showed it breaks composition with
  `detect_swings` on outside bars (§5).
- **Emit a comparison for the first point of each type**, against itself or a sentinel. Rejected: there is
  no previous swing, and inventing one would report a relation that no two observations support.

## Consequences

- The last primitive needed before structural naming exists: type and relation are available separately,
  so the layer that names them can be written deliberately.
- `compare_swing_sequence(detect_swings(series))` is a supported composition, including for outside bars.
- Exact comparison means `EQUAL` is reported only for bit-identical prices. Until a tick-size abstraction
  exists, "equal within a tick" cannot be expressed, and any consumer needing it must say so rather than
  assume this layer provides it.
- Comparisons are **not evidence**. Nothing classifies them, so no `EvidenceDescriptor` was added and the
  MARKET_STRUCTURE family remains empty.
- The comparison count is `max(highs − 1, 0) + max(lows − 1, 0)`, so a run with fewer than two points of
  a type contributes nothing from it — an ordinary result, not an error.
