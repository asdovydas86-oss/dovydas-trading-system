# ADR-0025 — Market Regime Engine v1: the environment in three dimensions, never a direction

**Status:** Accepted
**Date:** 2026-08-03
**Decides:** where regime classification lives, what it may and may not say, how evidence is counted,
and how its thresholds are prevented from becoming an asymmetric gate (Milestone AI)
**Implemented by:** *(uncommitted at the time of writing)*
**Relates to:** [ADR-0007](ADR-0007-application-layer-boundary.md) (the boundary the root reuses);
[ADR-0016](ADR-0016-structural-sequence-state-history-foundation.md) §4 (projections, not stored copies);
[ADR-0017](ADR-0017-structural-trend-foundation.md) (a stated policy is not a measurement);
[ADR-0021](ADR-0021-change-of-character-foundation-v1.md) (the event `TRANSITIONING` restates);
[ADR-0023](ADR-0023-multi-timeframe-composition.md) (nothing derived from the combination of views);
[ADR-0024](ADR-0024-confirmation-delay-provenance.md) (the hazard that had to close before a second
consumer of the structural chain could exist);
`ARCH` §9 (the contract this executes); `docs/analysis-notes.md` (the failure it must not repeat)

---

## Context

`ARCH` §9 names the Market Regime Engine the highest-leverage unbuilt module in the system:

> regime is the assumption nearly every downstream rule is conditioned on, so an unexamined regime
> call silently biases everything

and requires that its output carry **evidence and uncertainty** rather than a bare word, and be
reproducible on historical data so its usefulness can be tested rather than assumed.

The regime call currently lives in the v3 TradingView prompt's STEP 1, where it is not versioned, not
diffable and not testable. `docs/analysis-notes.md` records what that cost in v2, in detail:

* the trend gate was **double-counted** — weekly and daily trend were two separate confirmations of
  the same thing, so a LONG began with two free points;
* the two branches were **not mirror images** — "weekly bullish" held most of the time while "weekly
  bearish" required a deep bear market;
* tools were defined in **one direction only**;
* there was **no NO-TRADE outcome**, so ambiguity resolved to a default.

Milestone AH closed the last correctness blocker (ADR-0024): the regime engine is the second consumer
of `derive_structure_breaks`, and until the confirmation delay travelled with its origin, a second
consumer could silently disagree with the first about which breaks existed.

---

## Decision

A new engine package **`fmis.market_regime`** at L5, with a **narrow input model** as its only
boundary, classifying **three dimensions** that are never collapsed.

### 1. The regime is the environment, not the direction

The result contains no direction and cannot compute one. `SUSTAINED_HIGHER` and `SUSTAINED_LOWER` are
read as the same fact — *structure is sustained* — and a test asserts that swapping them changes no
state and no evidence string.

**This diverges from the v3 prompt**, which classifies regime as BULLISH / BEARISH / RANGE per
timeframe. The divergence is deliberate. A directional regime is exactly the object whose two branches
drifted apart in v2, and the brief for this milestone forbids direction in regime output. Which way
structure points is already a fact on the fact sheet, one layer down, where it is a measurement rather
than a classification. A consumer that wants both reads both.

`TRENDING` therefore does not mean rising. The engine's own limitation `AI-1` says so on every run.

### 2. Three dimensions, inspectable, never collapsed

| Dimension | States |
|---|---|
| **structure** | `TRENDING` · `RANGING` · `TRANSITIONING` · `INDETERMINATE` · `INSUFFICIENT` |
| **volatility** | `EXPANDING` · `CONTRACTING` · `STEADY` · `INSUFFICIENT` |
| **participation** | `ELEVATED` · `SUBDUED` · `TYPICAL` · `INSUFFICIENT` |

**There is no overall state and no score.** A fourth composite member would be the bare word `ARCH` §9
argues against: a consumer would read it and skip the three values carrying the information. A number
would imply a calibration this repository has never performed, which `SPEC` §4.1 rejects.

`INSUFFICIENT` (evidence absent) and `INDETERMINATE` (evidence present and disagreeing) are different
facts and are never merged. Both are first-class outcomes, which is the structural answer to v2's
missing NO-TRADE.

### 3. Evidence votes by **family**, and each family votes once

Two measurements that express the same thing are one piece of evidence:

| Family | Members | Feeds |
|---|---|---|
| swing structure | structural trend, change of character | structure |
| moving averages | close against a fast and a slow EMA | structure |
| true range | fast ATR against slow ATR | volatility |
| volume | volume against its own average | participation |

**No family appears in two dimensions**, so no number can corroborate itself, and a test asserts the
partition. This is the direct answer to the v2 double count.

Structure requires **both** its families to be readable and to agree. One readable family yields
`INSUFFICIENT`, not a classification — a single-family call is precisely the free confirmation the
post-mortem identified.

The moving-average family reads **position, never ordering**: close beyond *both* averages, or between
them. Ordering (fast above slow) is almost always true one way or the other, so it would vote on nearly
every bar while carrying direction — the shape of the gate that produced the bias.

### 4. A threshold band is one number with two mirrored edges

`RegimePolicy` carries `volatility_band` and `participation_band` as **single** numbers. The upper edge
is `1 + band`; the lower edge is `1 / (1 + band)` — the multiplicative mirror, which is the correct
symmetry for a ratio.

There is **no way through the API to express an asymmetric gate.** That is stronger than validating two
independently-settable thresholds for approximate symmetry, and it is the lesson of v2 encoded as a
type rather than as a warning. The CLI exposes one `--band` flag for the same reason.

The defaults are **stated policy, not measurement**, following ADR-0017's precedent with
`MINIMUM_DIRECTIONAL_SHIFTS`. No backtest justifies them because no backtester exists; when one does,
the policy object is what it sweeps. The policy travels on every result, so a classification can always
be reproduced.

### 5. Uncertainty and unavailability are modelled, not scored

`EvidenceStatus` has four members: `CONSISTENT`, `CONFLICTING`, `CONTEXT`, `UNAVAILABLE`.

`UNAVAILABLE` is **never** negative evidence — a warming-up indicator says nothing, and counting
silence as disagreement is how an engine manufactures confidence.

`CONTEXT` marks a fact reported but counted neither way, following the precedent
`fmis.decision_support` set with `Alignment.NOT_DIRECTIONAL`. A change of character from long ago is
the case it exists for: worth showing, but it neither agrees nor disagrees with "trending", and
labelling it either would be an invention.

`CONSISTENT` rather than "supporting": evidence is consistent with a description, it does not support a
decision, and the fact-only vocabulary guard forbids the substring `support` because a level may never
be called support (ADR-0019 §I).

### 6. The engine's boundary is a narrow model, not a fact sheet

`RegimeInput` carries an identity, an `as_of`, one enum, two indices and six optional floats.
`fmis.market_regime` imports exactly **one** name from the rest of the repository —
`StructuralTrendType` — and cannot see `fmis.pipeline`, `fmis.features`, `fmis.data` or a provider.

The application root `fmis.pipeline.regime` adapts a `StructuralFactSheet` into that model. An engine
that imported a fact sheet to read six numbers would invert ADR-0007's dependency direction for no
gain, and would be unreachable from a test without building a whole sheet.

The root contains **no arithmetic**, the rule `structural_facts` already follows. That is why the input
carries `last_index` and `latest_change_index` rather than a pre-computed distance: the subtraction is
the engine's to do.

### 7. Volatility is a ratio of two ATRs, not a level

A second `AverageTrueRange` at a longer period, added in `regime_features()` exactly as AG added
`ExponentialMovingAverage(200)` in `swing_features()` — a second instance of a shipped indicator, never
a new one invented to enrich the model.

A ratio is **self-normalising**: no currency, no tick size, no asset class, which is what keeps the
engine asset-agnostic. Classifying an *absolute* ATR-percent against a threshold would bake in a value
that differs between crypto and equities, and principle 9 forbids exactly that.

`fmis.features.VolatilityRegime` (LOW / NORMAL / HIGH / EXTREME) was **not** reused. It is a *level*
vocabulary reserved for a volatility feature that has not been built — "how volatile is this market" —
while this dimension answers "is volatility changing relative to its own baseline". One enum for both
would force a meaning to bend, so the states here are `VolatilityState`.

### 8. Multi-timeframe regime is per view, and nothing is derived from the set

`MultiTimeframeRegime` classifies each role independently and reports them side by side. It carries no
agreement, alignment, consensus, dominance or overall view — ADR-0023 fixed that rule for the
multi-timeframe fact sheet, and a regime that reconciled three timeframes would be exactly the
synthesis it forbids, made silently.

### 9. A new command rather than a changed one

`fmits regime SYMBOL`, with `--multi` for the three roles. `facts` and `mtf` are **untouched**: their
feature sets, their output and their contracts are byte-identical, and tests assert that neither prints
regime vocabulary.

Bolting regime onto `facts` would have forced one of two bad outcomes — changing that command's feature
set and printed output, or shipping a volatility dimension permanently reporting `INSUFFICIENT` because
`facts` computes no slow ATR baseline.

---

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **A directional regime (BULLISH / BEARISH / RANGE), as v3 does** | The exact object whose branches drifted apart in v2; forbidden by the milestone brief; direction is already a fact one layer down |
| **A single composite regime label** | The bare word `ARCH` §9 argues against; discards the disagreement a reader most needs |
| **A confidence score or probability** | Never calibrated, so it would decorate rather than inform; `SPEC` §4.1 rejects false precision |
| **Two independent thresholds per dimension** | Reproduces the asymmetric gate; a validator checking "close enough to symmetric" is a warning where a guarantee belongs |
| **Reusing `fmis.features.VolatilityRegime`** | A *level* vocabulary for an unbuilt feature; a different question from expansion against a baseline |
| **Putting the engine in `fmis.decision_support`** | That package sits **above** `fmis.pipeline` and consumes an `AnalysisSnapshot`; regime is L5, below it, and needs structural facts it does not carry |
| **Letting the engine consume `StructuralFactSheet`** | Inverts ADR-0007's direction so an engine can read six numbers; the narrow model costs one adapter and keeps the graph honest |
| **EMA ordering as trend evidence** | Almost always true one way or the other, and it carries direction |
| **Classifying an absolute ATR-percent** | Bakes in an asset-specific threshold; not asset-agnostic |
| **Extending `fmits facts`** | Changes a shipped command's feature set and output, or ships a permanently-insufficient dimension |

---

## Consequences

**The owner gains a versioned, diffable regime call** with the evidence behind it, the evidence against
it, what was unavailable, and the exact thresholds used — replacing a judgement made inside a prompt.

**Four evidence families, one vote each, no overlap.** Correlated evidence cannot inflate a state.

**An asymmetric gate is unrepresentable**, not merely discouraged.

**`facts` and `mtf` are unchanged.** New public names appear only in `fmis.market_regime` (19) and
`fmis.pipeline` (10 more); no existing export was renamed or removed.

**Limitations, printed on every run:** `AI-1` regime is not direction · `AI-2` volatility and
participation each rest on a single family, so neither can be corroborated within its dimension ·
`AI-3` the thresholds are stated policy, not measurements · `AI-4` each timeframe is classified alone.

**Still deliberately absent:** trade signals, LONG/SHORT scoring, setup detection, entry, stop, target,
sizing, portfolio risk, scanner, watchlists, persistence, scheduling, AI interpretation, macro, news,
on-chain, derivatives, support/resistance scoring, and Market Regime v2's non-technical dimensions
(risk-on/risk-off, liquidity, correlation, crisis) — which `ARCH` §9 assigns to L6 intelligence this
repository has not built.
