# ADR-0012 — Market structure foundation: deterministic swing detection

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** the first market-structure primitive, its comparison rules, and why structural
interpretation is postponed (Milestone V)
**Implemented by:** `feat(market_structure): add deterministic swing detection`
**Relates to:** [ADR-0001](ADR-0001-canonical-utc-timestamps.md) (canonical timestamps);
[ADR-0010](ADR-0010-volume-foundation.md) (measurement before interpretation);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (a calculation is not automatically evidence)

---

## Context

Every structural concept the system will eventually want — higher highs, break of structure, change of
character, consolidation, support and resistance, liquidity pools — is defined by *comparing swing points
to each other*. None of them can be built, or even honestly discussed, until swing points themselves
exist and are trustworthy.

"Trustworthy" is the hard part. Swing detection is where indicator libraries most often quietly repaint:
a pivot appears, then vanishes or moves as new candles arrive, and every downstream conclusion silently
changes with it. A backtest built on a repainting pivot is worthless in a way that is very hard to notice.

## Decisions

### 1. `fmis.market_structure` is a package, not a Feature
Swing detection returns a *sequence of structured objects*. `FeatureValue` covers floats, ints, bools,
strings, `None`, mappings and sequences **of those** — a tuple of `SwingPoint` dataclasses is none of
them. Making swings a `FeatureResult` would mean flattening each point into a dictionary and losing its
type, so they are domain objects in their own package instead.

The Tier-2 placeholder `fmis.features.market_structure` previously claimed "swing high / swing low
detection". That claim has been removed and now points here, so there is exactly one home for detection.
That package keeps its remaining purpose: structural *features* that interpret these points and can be
expressed as a `FeatureValue`. This differs from Milestone T, where relative volume was a plain float and
therefore belonged in `fmis.features.volume` — the deciding factor is the shape of the output, not the
subject.

### 2. Detection is deterministic and non-repainting
`detect_swings` is a pure function of the closed candles and two integers. The same inputs always give
the same output, and — the property that matters — **extending the series never revises a point already
returned**. A swing at index `i` depends only on `[i - left_bars, i + right_bars]`, all of which had
already closed when the point was emitted, so later candles cannot reach back and change it.

This is asserted directly rather than argued: a property test detects on every prefix of a random series
and requires the result to equal exactly the full run's swings that were confirmable at that prefix
length.

### 3. Confirmation delay is the mechanism, not a shortcoming
A swing at index `i` cannot be known until `right_bars` further candles have closed. **In any finite
series snapshot the newest `right_bars` closed candles cannot yet be classified; they become eligible
once additional closed candles arrive.** Being unconfirmed is a property of the snapshot, not a permanent
property of those candles — the confirmation frontier advances as data arrives.

The right-side candles are "future" only relative to the *candidate*; they are already closed and known
at the moment of evaluation, which is precisely why the result is stable. This is not latency to be
optimised away — it *is* what makes the result non-repainting. Any scheme that reports a pivot sooner is
either guessing or will revise itself, and both are worse than waiting.

So "non-repainting" means two things together, and both are tested: **confirmed historical output is
stable**, and **the confirmation frontier advances**.

### 4. No future candle is ever inspected
The candidate range is exactly `range(left_bars, n - right_bars)`, so every comparison window lies wholly
inside the supplied closed series. Nothing is extrapolated, and no candle beyond the window affects the
result.

### 5. Closed candles only
Detection runs on `series.closed()`. A forming bar's high and low can still move, so a swing that
depended on one could change on the next tick — which is exactly the repainting §2 forbids.

**Consequence, stated plainly:** `SwingPoint.index` is a position in the *closed* candle sequence, not in
the raw series. A raw index would mean something different depending on whether the last bar had closed,
which is precisely the kind of silent ambiguity this project keeps eliminating.

### 6. Comparison rule: strictly greater on the left, greater-or-equal on the right
```
swing high at i  <=>  high[i] >  high[j]  for j in [i-left, i-1]
                 and  high[i] >= high[j]  for j in [i+1, i+right]
```
mirrored for lows. The asymmetry exists to resolve **plateaus** — runs of equal extremes — to exactly one
point:

| rule | `[1, 5, 5, 1]`, left=right=1 | verdict |
|---|---|---|
| strict both sides | **no swing at all** | silently discards a real level |
| `>=` both sides | swing at index 1 **and** 2 | duplicates one structure |
| **strict left, `>=` right** | one swing, at index 1 | chosen |

Repeated prices are ordinary, not exotic — exchanges quote discrete ticks and levels get retested — so a
rule that drops plateaus would lose real structure regularly.

**The first bar of a plateau wins**, which also confirms as early as the information allows: in the table
above index 1 is settled at index 2 rather than at the end of the run. Deciding it is the *last* bar
would be equally consistent but would delay confirmation for no gain.

**This is a deterministic representation policy, not a claim about markets.** Three things follow, and
they are stated here so no later layer has to guess:

  * It deliberately introduces a **time-direction asymmetry** — the left side is strict, the right side
    is not — so the rule is not symmetric under reversing the series. That asymmetry is the price of
    collapsing a plateau to exactly one point, and it is chosen, not accidental.
  * It is **not claimed to be the only valid market interpretation.** Treating the last bar of a plateau,
    or its midpoint, or every bar, as the swing are all defensible readings; this one is fixed so results
    are reproducible and comparable.
  * **Downstream structure logic must not silently redefine it.** A later layer that wants a different
    plateau convention must say so explicitly and carry its own decision record, rather than
    re-deriving swings with different rules and presenting them as the same thing.

### 7. Equal extremes that are separated are distinct swings
`[1, 5, 1, 5, 1]` with left=right=1 yields **two** swing highs, at indices 1 and 3. They are two local
maxima that happen to share a price — a double top — and merging them would destroy exactly the structure
a later layer is going to look for. A plateau is one extreme spread over adjacent bars; equal highs are
two extremes at the same level. The rule distinguishes them without needing a special case.

### 8. A candle may be both a swing high and a swing low
An outside bar whose high tops its neighbours and whose low undercuts them produces two points at the
same index. Results are sorted by `(index, type)` with HIGH before LOW, so ordering stays total and
deterministic.

### 9. Insufficient history is an empty result, not an error
Fewer than `left_bars + 1 + right_bars` closed candles yields `()`, as does an empty series. "No swing
could be confirmed" is a true answer to a well-formed question, unlike the feature layer's warm-up case
where a *scalar* had to be reported as absent. A collection has a natural empty value; using it avoids
inventing an error for a normal state.

### 10. Parameters are explicit; defaults encode no opinion
`left_bars` and `right_bars` are independent positive integers, defaulting to 2 each. Two is deliberately
unremarkable — it is not a tuned value, and any lookback is available by passing it. Asymmetric settings
are supported because the two sides answer different questions: how much history must be exceeded, and
how long to wait before committing.

### 11. Nothing is interpreted
No BOS, CHoCH, higher-high/lower-low classification, trend, consolidation state, support, resistance, or
liquidity. `SwingPoint` carries no direction, strength, confidence, rank, or reference to another swing.
A test scans the package for that vocabulary. Every one of those concepts is a *comparison between*
swings, and each deserves its own decision about what it means — questions that are much easier to answer
well once the primitive underneath is known to be sound.

## Alternatives considered

- **Strict comparison on both sides** (the most common textbook form). Rejected: silently reports nothing
  for plateaus, which are common (§6).
- **`>=` on both sides.** Rejected: reports every bar of a plateau, so a single structure appears as
  several and any downstream count is inflated.
- **Last bar of a plateau wins.** Rejected as equally correct but strictly later to confirm (§6).
- **Emit provisional swings and revise them.** Rejected outright: that is repainting, and it makes every
  historical result depend on when it was computed.
- **Detect on all candles including the forming one.** Rejected: the newest swing could change intrabar
  (§5).
- **Merge equal highs into one point.** Rejected: destroys double-top structure (§7).
- **Put swing detection in `fmis.features.market_structure`.** Rejected on output shape: `SwingPoint`
  tuples are not `FeatureValue`s (§1).
- **Raise on insufficient history.** Rejected: an empty collection already says it (§9).

## Consequences

- The primitive every later structural milestone needs now exists and is provably non-repainting.
- `SwingPoint.index` is meaningful only alongside the closed series it came from. Points carry their
  timestamp so they remain interpretable once separated, but an index must not be applied to a raw series.
- At any moment the newest `right_bars` closed candles are not yet classifiable, and become eligible as
  further candles close. Any consumer showing "current structure" must state that lag rather than hide
  it — but must not present it as a permanent gap.
- Detection is `O(n · (left + right))` with no caching. At the series lengths in use this is irrelevant;
  it would need revisiting only for large-scale backtesting.
- Swing points are **not evidence** in the ADR-0011 sense: nothing classifies them yet, so no
  `EvidenceDescriptor` was added and the MARKET_STRUCTURE family stays empty. It earns a descriptor when
  something interprets these points, not when something computes them.
