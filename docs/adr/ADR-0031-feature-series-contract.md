# ADR-0031: The additive feature-series contract — `compute_series()`, alignment, warm-up and provenance

**Status:** Accepted
**Date:** 2026-09-17
**Milestone:** TA Slice 5A — Recover Technical Context & Feature Series

## Context

`Feature.compute(context) -> FeatureResult` returns **one value: the latest**. Every Tier-1
indicator in the repository computes its whole history internally and then throws all but the last
element away — `fmis.features.indicators.ema.ExponentialMovingAverage.compute` is the clearest
case, calling the shared `ema_series(prices, period)` and keeping `[-1]`.

The consequence is not a missing convenience. It is that **slope, rate of change, acceleration,
crossover recency, divergence and volatility compression are not derivable in principle** from what
the Feature Engine publishes. `PROJECT_SPECIFICATION_V1.md` §4.1 requires direction, momentum,
acceleration or deceleration, slope and divergences; none of them can be expressed against a scalar.

This has been recorded as review item **R5 since 2026-07-24**
([`../ARCHITECTURE_REVIEW_2026-07-24.md`](../ARCHITECTURE_REVIEW_2026-07-24.md)), referenced by
reports 0002, 0003 and 0004 as the `compute_series()` extension, re-measured by
[report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §8 seam 1 and
§10.1, and approved **as additive** by the
[0047 review disposition](../reviews/REPORT_0047_REVIEW_DISPOSITION.md) §C and D4:

> `compute()` unchanged, every existing feature name, seeding convention and metadata unchanged.

It is also a **prerequisite with a deadline**: disposition §C fixes that historical series access
must exist **before** any production zone engine depends on the ATR at a zone's establishment point.

Report 0047 §8 noted that `FeatureValue` already permits `Sequence`, so "no contract change is
needed". **That observation is true and is not sufficient**, which is the decision this ADR exists
to take. A bare list inside `FeatureResult.value` answers none of the questions a historical series
raises: which candle does element 0 describe; where does warm-up end; is a `None` an absent value or
an undefined one; what were the parameters; which symbol and timeframe is this. A caller would have
to reconstruct the alignment by arithmetic over a period it had to know independently, which is the
class of off-by-one this repository's `LevelOrigin.knowable_from` and `StructureBreak.eligible_from`
projections exist to make impossible.

## Decision

### 1. `compute_series()` is additive, and `compute()` does not change

`Feature` — the existing `runtime_checkable` Protocol — is **untouched**. A second Protocol is
added beside it:

```python
@runtime_checkable
class SeriesFeature(Protocol):
    name / category / dependencies / compute(context) -> FeatureResult
    compute_series(context) -> FeatureSeries
```

`BaseFeature` is untouched and declares no abstract `compute_series`, so a feature that has no
meaningful history — or has not been converted — remains a valid `Feature`. `supports_series(obj)`
is the one published way to ask.

No existing feature's `name`, seeding convention, warm-up rule, value or `metadata` changes.
`FeatureResult`, `FeatureSet`, `FeatureContext`, `FeatureRegistry` and `FeatureEngine.compute` are
unchanged. The policy non-regression digest depends on the `repr()` of what those produce and must
stay byte-identical; this decision is what makes that achievable rather than hoped for.

### 2. The result is an explicit type, not a list in `FeatureValue`

```python
FeatureSeriesPoint:  index · timestamp · value · undefined_reason
FeatureSeries:       name · category · identity · as_of · closed_candles
                     · warmup_candles · points · metadata
```

* **`index`** is the point's position in the **closed-candle sequence** the context carried — the
  same index space `SwingPoint.index`, `LevelOrigin.index` and `LevelCrossingEvent.index` already
  use, so a feature value and a structural event at the same bar carry the same number.
* **`timestamp`** is that candle's own timestamp, carried so a consumer never needs the candles to
  place a value in time.
* **`identity`** is the `SeriesIdentity` of the series the points came from, stored **once for the
  whole series** — the `ContextualSeries` convention (ADR-0018), for the reason ADR-0018 gives.
* **`as_of`** is the last **closed candle's** timestamp, matching `FeatureSet.as_of`. It is `None`
  only for an empty series, and it is deliberately *not* the last point's timestamp: those differ
  exactly while a feature is warming up, and collapsing them would make a warming-up series look
  like a stale one.

### 3. Warm-up is stated, never backfilled

A point exists for a closed-candle index **iff** the feature is defined there. Positions before
warm-up produce **no point at all** — they are not padded with `None`, not zero-filled and not
seeded. `warmup_candles` states how many closed candles the feature needs, and `first_index` is a
**projection over `points`** rather than a stored field (ADR-0016 §4), so the two can never disagree.

`points` is empty exactly when the feature has not warmed up. An empty `points` tuple beside a
positive `closed_candles` is the series form of `FeatureResult(value=None, insufficient_data=True)`.

### 4. Defined-but-undefined is a third state, and it is distinguishable

`RelativeVolume` already has a position that is *past warm-up and still has no value*: a baseline
window of entirely zero volume, reported as `undefined_reason="zero_average_volume"` and never
repaired with an epsilon or an infinity. A point therefore carries `value` **and**
`undefined_reason`, with an enforced invariant:

> `value is None` **iff** `undefined_reason is not None`.

So *not warmed up* (no point), *undefined here* (a point with a reason) and *computed* (a point with
a value) are three different facts and cannot be confused. Dropping the undefined position instead
would silently shorten the series and shift nothing else — the worst available failure.

### 5. Structured values are first-class

`value` is a `FeatureValue`, so MACD emits the same immutable
`{"macd_line", "signal_line", "histogram"}` mapping per point that its `FeatureResult` emits for the
latest bar. The protocol assumes no scalar anywhere, and MACD is the test case that proves it.

### 6. One mathematical implementation, and the parity is tested

`compute()` and `compute_series()` must not implement one formula twice. Each converted indicator
has its arithmetic in exactly one pure helper module producing the **whole** series in one pass, and
`compute()` takes the last element of what `compute_series()` publishes — the arrangement
`ema_math.ema_series` already had, extended to ATR, RSI, MACD and the volume baseline.

The contract is asserted, not assumed:

> for the same closed input and the same parameters,
> `compute(context).value` **equals** the value of the final point of `compute_series(context)`
> — and both are `None` under the same conditions.

Equality is exact, not approximate: both paths execute the same operations in the same order over
the same floats, so bit-identical results are a property of the design rather than a tolerance.

### 7. Prefix stability and no lookahead are contract, not convenience

For a closed prefix of the candles, every point knowable at that prefix is **equal** to the
corresponding point of the full series. No future candle may change an earlier value. This is the
same guarantee every L4/L5 engine in this repository already holds, restated at the feature
boundary, and it is what makes an eventual replay or backtest able to use a series at all.

### 8. No engine-level `compute_series`, deliberately

`FeatureEngine.compute` threads each feature's **latest** `FeatureResult` into the next feature's
`FeatureContext.computed`, so a dependent feature reads its dependency's latest value. Threading
*latest* values into a *historical* computation would inject the newest bar's reading into every
past bar — lookahead, produced by the orchestration rather than by any feature. Until a dependent
series feature exists and a correct per-index dependency contract is designed, the engine gets no
series method. No feature in the repository declares a dependency today, so nothing is blocked.

## Consequences

* Slope, ROC, crossover recency, RSI dynamics, MACD histogram direction, volatility
  compression/expansion, divergence and establishment-time ATR all become **derivable**. None of
  them is derived here — that is the explicit non-goal of TA Slice 5A.
* Every consumer of the latest value is unaffected, by construction.
* Six features gain series support: EMA, ATR, RSI, MACD, `RelativeVolume` and `AverageVolume`.
  `AverageVolume` stays **DORMANT** — it is not promoted into `default_features()`, and its series
  support exists only because it shares `volume_math` with `RelativeVolume` and excluding it would
  have left one class in one module series-capable and its sibling not.
* Series computation is **O(n)** in closed candles for the recursive indicators and O(n · lookback)
  for the fixed-window volume baseline, where lookback is a parameter and not a function of n.
* A feature added later is **not** required to support series. `supports_series` is a question with
  two honest answers.

## Alternatives rejected

| Alternative | Why rejected |
|---|---|
| A list in `FeatureResult.value`, since `FeatureValue` permits `Sequence` | It is representable, not specified. Alignment, warm-up boundary, undefined-versus-absent, and the identity of the series are all left for the caller to reconstruct — and each reconstruction is a place to be off by one. That a type permits a shape is not evidence the shape is correct. |
| Reuse `ObservationSeries` | It is `tuple[float]` with parallel timestamps: no candle index, no structured value (MACD cannot be expressed), no warm-up field, no undefined reason, and a `series_id` string rather than a `SeriesIdentity`. |
| Reuse `ContextualSeries[T]` | Closest fit, and it supplies identity correctly — but it is deliberately *exactly two fields* and holds no alignment, warm-up or provenance. Widening it would change a contract three structural engines depend on, to serve one new consumer. `FeatureSeries` carries a `SeriesIdentity` for the same reason and leaves `ContextualSeries` alone. |
| Parallel `tuple[int]` / `tuple[datetime]` / `tuple[value]` | Three tuples that must stay the same length is an invariant to enforce rather than a shape that cannot be wrong. |
| Pad the warm-up region with `None` so index 0 is candle 0 | Makes *not enough history yet* and *no value at this bar* the same token, which is precisely the distinction `StructuralFactSheet.warming_up` exists to keep — and it invites a consumer to backfill. |
| Change `compute()` to return the series and have callers take `[-1]` | Breaks every existing caller and, worse, changes `FeatureResult.repr()` and therefore the policy non-regression digest. The disposition approved this extension **as additive** for exactly this reason. |
| Add `compute_series` to `BaseFeature` as abstract | Makes every future feature owe a history it may not have. A pattern detector's output is not a series. |
| An engine-level `compute_series` now | See §8: it would have to decide a per-index dependency semantics that no feature needs yet, and the naive version injects lookahead. |

## How it is enforced

* `tests/test_feature_series.py` — the correctness matrix: latest-value parity per feature, warm-up
  boundary at `w−1` / `w` / `w+1`, prefix stability, no-lookahead, identity and provenance,
  parameter variation, empty and short input, structured MACD values, repeat determinism,
  closed-candle semantics, alignment against the candle timeline, and the undefined-versus-absent
  distinction.
* `tests/test_feature_series_performance.py` — measured scaling at 200 / 500 / 1,000 / 2,000 closed
  candles, asserting the growth is not quadratic.
* `tests/test_swing_setup_policy_non_regression.py` — the 81-fixture digest table, unchanged, proves
  `compute()` did not move when its arithmetic was relocated into shared helpers.
