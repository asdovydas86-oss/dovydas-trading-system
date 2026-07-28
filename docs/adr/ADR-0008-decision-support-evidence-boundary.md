# ADR-0008 — Decision-support evidence boundary

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** where evidence organisation lives, and the line it must not cross (Milestone R)
**Implemented by:** `feat(decision_support): add Decision Support Evidence v1`
**Relates to:** [ADR-0007](ADR-0007-application-layer-boundary.md) (the layer it consumes);
[ADR-0004](ADR-0004-rve-v1a-return-and-result-policy.md) (RVE results are restated, never recomputed);
`PROJECT_SPECIFICATION_V1.md` §4 (deterministic facts before AI interpretation)

---

## Context

`AnalysisSnapshot` answers "what are the numbers". A human — or, later, an interpretation layer — then
has to do the same tedious work every time: find the EMAs, compare them to price, decide whether MACD
agrees, notice that a value is missing rather than zero. That work is mechanical, and doing it ad hoc is
where undisciplined reasoning creeps in.

The risk in building this layer is obvious: a component that groups evidence and emits a summary word is
one small step from emitting a trading opinion. The decisions below exist mostly to make that step
structurally impossible rather than merely discouraged.

## Decisions

### 1. `fmis.decision_support` sits above `fmis.pipeline`, consuming snapshots only
It reads an `AnalysisSnapshot` and nothing else — no provider, no engine call, no candle access. Nothing
below imports it, including the pipeline; a test walks every lower package and asserts this. It imports
`fmis.pipeline` as a whole, not its submodules, so it depends on published result types rather than
internals.

### 2. Classification, not calculation
Exactly one new number is derived — ATR as a percentage of price — and it lives alone in `derived.py`.
Everything else classifies values an engine already produced. A test asserts that no module in the
package except `derived.py` contains a subtraction, multiplication, division, power, or modulo, and that
`derived.py` contains exactly one division. (`Add` is exempted: this layer concatenates many tuples, and
no meaningful market calculation can be built from addition alone.)

### 3. Every classification rule is a written-out, individually testable function
`classify_comparison`, `classify_rsi_zone`, `classify_sign` are pure functions over plain floats with no
knowledge of snapshots. No rule engine, no configuration, no strategy system — a rule you cannot read in
one screen is a rule nobody audits. Comparisons are exact: no epsilon is invented, because a tolerance is
an undocumented judgement about what counts as "the same price".

### 4. An oscillator band is not a direction
An RSI zone is classified as `NOT_DIRECTIONAL` and is structurally excluded from directional grouping.
"Oversold" describes where a bounded value sits; it is not evidence that price will rise, and the
oversold-equals-buy reflex is precisely the reasoning this project exists to avoid. The band is still
reported — the reader gets the fact, not a conclusion drawn from it. ATR percent is excluded for the same
reason: magnitude says nothing about sign.

### 5. Agreement is counted, and a tie stays a tie
The dominant alignment is whichever of upward/downward has more observations; supporting observations are
those matching it, conflicting are the rest. **On a tie there is no dominant alignment**: every
directional observation is reported as conflicting and none as supporting. Breaking a deadlock with a
tiebreak rule would manufacture agreement that the data does not contain. `NEUTRAL` observations (an exact
equality) support nothing and conflict with nothing.

### 6. Scenarios restate observations; they never forecast
A scenario's conditions are generated mechanically from the grouped observations — `X remains above`,
`X becomes below` — using each observation's recorded inverse. There is no price level, no timing, no
likelihood, and no authored prose. A test asserts no scenario condition contains a digit.

### 7. `OverallState` is undirectional, and has exactly three values
`WATCH` (enough directional evidence, and it does not disagree with itself), `WAIT` (mixed, conflicting,
or entirely neutral), `INSUFFICIENT_DATA` (fewer than three of the five directional observations
available). `WATCH` deliberately does not say which way anything leans — the dominant alignment is
reported separately as a fact, and the state answers only "is this coherent enough to follow".

All-neutral evidence is `WAIT`, not `WATCH`: it is coherent but says nothing, and a state that cannot
distinguish "everything agrees" from "nothing is happening" would be useless.

### 8. No trading vocabulary, enforced by test
No direction to trade, price target, stop, position size, confidence number, or ranking — not in a value,
a field name, an enum member, or metadata. Two tests scan the public surface and the field names of every
exported dataclass against a banned-word list.

### 9. A missing value is reported, never inferred
An absent feature and a warming-up feature both yield an `UNAVAILABLE` observation; the distinction is
preserved in `metadata` as `missing_features` and `warming_up_features`. An UNDEFINED RVE metric carries
the RVE's own reason. Nothing is defaulted to zero or quietly dropped.

## Prerequisite change

`DataWindow` gained `last_close`. Indicator values alone cannot be related back to price, so "price
relative to EMA" and "ATR as a percent of price" were not expressible from a snapshot. It is a recorded
fact about the analysed window — the close of the last closed candle — not a calculation, and the window
is where the other facts about that candle already live. The alternative, re-reading candles downstream,
would have meant a second data path for something the snapshot had already consumed.

## Alternatives considered

- **Map RSI bands to a direction** (oversold → upward). Rejected: it is the classic error, and encoding it
  once would propagate into every consumer of this layer.
- **Break alignment ties by weighting** trend above momentum, or by recency. Rejected: any weighting is a
  strategy hypothesis, which this milestone explicitly does not have and cannot test.
- **A single directional summary** (e.g. `state = WATCH_UPWARD`). Rejected: it collapses "the evidence is
  coherent" and "the evidence points up" into one word, which is exactly the conflation that turns
  evidence into advice. The two are reported separately.
- **A configurable rule engine / thresholds file.** Rejected as speculative: there is one rule set, no
  second consumer, and configurable thresholds invite tuning against remembered outcomes.
- **Emitting scenario probabilities or a confidence score.** Rejected outright: nothing in the system
  estimates likelihood, and a number with no basis is worse than no number.
- **Putting this inside `fmis.pipeline`.** Rejected: the pipeline orchestrates engines; classification is
  a different job, and keeping it separate means the pipeline stays usable without it.

## Consequences

- The facts arrive organised, with gaps visible, which is what an interpretation layer needs to reason
  honestly — and what a human needs to not fool themselves.
- The report is bound to `default_features()` names (`ema_20`, `ema_50`, `rsi_close_14`, `atr_14`,
  `macd_close_12_26_9`). A snapshot built from a different feature selection yields `UNAVAILABLE`
  observations rather than an error. Making the names configurable is future work, and should wait for a
  second real feature set.
- Thresholds (RSI bands, the three-observation floor) are constants in code, deliberately not
  configuration. Changing one is a code change with a test, which is the point.
- The layer is additive: `fmis.pipeline` and every engine remain fully usable without it.
