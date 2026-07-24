# Relative Value Engine — Technical Design V1

**Status:** Design proposal — **not authorization to implement**
**Date:** 2026-07-24
**Baseline:** `5e7e3d5`, 218 passing tests
**Scope of this document:** the first implementable version of the RVE (Milestones J / K / L), designed in
full so that J can be built without re-deciding K and L, and so that the extension points to v2 are chosen
deliberately rather than discovered.
**Governed by:** [ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) §7 (RVE specification)
and decisions D1–D10. This document refines that specification into concrete contracts; where it makes a
new choice, the choice is numbered `RV-n` and justified in §12.
**Prerequisites:** both are now **satisfied by Milestone I-E** — **R1** (the
`candle_series_to_observations` reduction in `fmis.data`, the RVE's price input) and **R2** (alignment now
lives in `fmis.alignment`, [ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md), so
the RVE imports `fmis.alignment.align_intersection` from its permanent home). The RVE (Milestone J) is
therefore unblocked.

---

# 1. Purpose

The Relative Value Engine answers one class of question that no existing layer can express:

> **How does series A relate to series B?**

The Feature Engine cannot answer it, and the reason is structural rather than incidental:
`FeatureContext.primary` is a single `CandleSeries`, and a `FeatureSet` is identified by
`(symbol, timeframe, as_of)`. A relationship has **no single symbol**. Recording "BTC vs Global M2" inside
a BTC `FeatureSet` would assert that it is a property of BTC alone, which is false — the same number moves
when M2 moves.

The RVE therefore exists to produce **deterministic, reproducible, auditable measurements of relationships
between two or more series**, each accompanied by the data-quality facts needed to judge whether the
measurement means anything.

**The RVE is explicitly not:**

- a signal generator — no `LONG`, `SHORT`, `BUY`, `SELL`, "bullish", "bearish", "overbought", "extreme";
- a scorer — no confidence values, no rankings framed as preference;
- a causal claim — it measures association and says so; mechanism is a hypothesis belonging to human or AI
  interpretation;
- a threshold evaluator — "z-score above 2" is a *strategy condition*, defined in a versioned strategy, not
  a fact the RVE emits.

It reports **what the relationship measures**, never **what to do about it**. This is the property that
keeps it testable.

---

# 2. Position in the architecture

```
        fmis.data  (Candle · CandleSeries · ObservationSeries · alignment)
              │                                    │
              ▼                                    ▼
     fmis.features                        fmis.relative_value
   (single instrument)                   (two or more series)
              │                                    │
              └──────────────┬─────────────────────┘
                             ▼
              Market Regime · Strategy · Portfolio · AI
```

**The Feature Engine and the RVE are siblings, not neighbours in a chain. Neither imports the other.**
Both depend only on the canonical data layer. They are joined one level up, by the layers that legitimately
hold both kinds of fact at once. This is the single most important structural property of the design, and
§9 explains why.

**Proposed location:** `src/fmis/relative_value/` — a top-level sibling of `fmis.data` and `fmis.features`,
mirroring the internal shape that `fmis.features` already proved:

```
src/fmis/relative_value/
├── __init__.py       public surface + scope-boundary docstring
├── definition.py     RelationshipDefinition, Transform  (what to measure)
├── types.py          RelativeValueMetric, DataQuality, RelativeValueResult  (what comes out)
├── metrics.py        pure math on aligned float sequences  (no models, no policy)
└── engine.py         RelativeValueEngine — align → compute → assemble
```

The `metrics.py` / `engine.py` split is the same separation that `ema_math.py` (pure arithmetic) and
`ema.py` (validation, context, result assembly) already demonstrate, and it is what makes D4 ("RVE math
consumes aligned series only") concrete: the functions in `metrics.py` cannot align anything, because they
never see a series object at all.

---

# 3. Inputs

## 3.1 What the engine accepts

| Input | Type | Notes |
|---|---|---|
| Series to relate | `tuple[ObservationSeries, ...]` (v1: exactly 2) | **Never** `CandleSeries` — see RV-1 |
| What to measure | `RelationshipDefinition` (frozen) | Declares base/quote, transform, windows |
| Evaluation instant | `as_of: datetime` (canonical UTC), **injected** | Never read from the wall clock — see RV-4 |

## 3.2 Price series enter as observations, not candles

A price series reaches the RVE by being reduced first: `CandleSeries` + a chosen source (`close`) →
`ObservationSeries` with a `series_id` such as `BTCUSDT.close.4H`. That reduction is the missing helper
identified as review finding R1 and belongs in `fmis.data`, beside the models.

The consequence is deliberate: **the RVE never knows what OHLCV is.** A price series, a macro print, an
on-chain metric, and a derivatives metric are all the same shape by the time they arrive, so every metric
is written once and works on all of them. It also removes any temptation to reach into candle internals
(highs, lows, volume) from a layer whose job is relationships.

## 3.3 Metadata the RVE relies on

`ObservationSeries` already carries `series_id`, `unit`, and `frequency`. The RVE uses `unit` and
`frequency` for **reporting and guarding**, not for conversion:

- it records them in provenance so a stored result stays interpretable;
- it **refuses** a raw (non-log, non-indexed) ratio of two series whose `unit` values differ, because a
  ratio of USD to an index level is a number without meaning. Explicit refusal beats a plausible-looking
  wrong number.

The RVE performs **no unit conversion and no currency conversion**. Those are adapter responsibilities.

---

# 4. Responsibilities

**Owns:**

1. Interpreting a `RelationshipDefinition` into an ordered set of metric computations.
2. Invoking the alignment service and carrying its report forward — never re-implementing alignment.
3. Computing deterministic relationship metrics via pure functions.
4. Deriving and enforcing each metric's warm-up, and emitting an explicit insufficient-data state below it.
5. Assembling an immutable result with metrics, data quality, and provenance.
6. Reporting staleness relative to the **injected** `as_of` (review finding R6 assigns it here).

**Does not own:**

- alignment policy (the alignment service owns it) or the definition of "same instant" (ADR-0001 owns it);
- data ingestion, unit conversion, currency conversion (adapters);
- interpretation, labels, thresholds, direction, confidence (AI and Strategy);
- persistence or serialization (a later layer);
- anything single-instrument (the Feature Engine).

---

# 5. Data contracts

All types are frozen slotted dataclasses with tuple-normalized state and `MappingProxyType` mappings,
following the established `FeatureResult` pattern exactly.

## 5.1 `RelationshipDefinition` — what to measure

```python
class Transform(str, Enum):
    RAW     = "raw"      # A / B on levels
    LOG     = "log"      # ln(A / B)          — requires strictly positive values
    INDEXED = "indexed"  # 100 * P_t / P_base — both series rebased to a common start

@dataclass(frozen=True, slots=True)
class RelationshipDefinition:
    relationship_id: str          # stable identity, e.g. "ETH_BTC"
    base_series_id: str           # NUMERATOR  — explicit, never positional
    quote_series_id: str          # DENOMINATOR
    transform: Transform
    windows: tuple[int, ...] = () # observation counts for windowed metrics
    version: int = 1              # bump on any semantic change
```

Explicit `base`/`quote` **by series id, not by argument position**, is not ceremony: `ETH/BTC` and `BTC/ETH`
are different measurements that a positional API silently confuses. The engine matches ids against the
supplied series and raises if either is absent, so a reordered input tuple cannot change the answer.

`version` exists because a definition change makes historical outputs incomparable. Versioning the
definition keeps old results interpretable instead of quietly wrong (architecture principle 7).

## 5.2 `RelativeValueMetric` — one measurement

```python
@dataclass(frozen=True, slots=True)
class RelativeValueMetric:
    name: str                      # deterministic: "log_ratio", "rolling_correlation_90"
    value: float | None            # None == explicit insufficient-data / undefined state
    window: int | None             # observations the metric spans; None if not windowed
    metadata: Mapping[str, Any]    # MappingProxyType: formula, warm-up, flags, limitations
```

Deliberate mirror of `FeatureResult`: same immutability, same explicit `None`, same provenance discipline —
so that a reader who understands one understands the other. It is *not* a `FeatureResult`, per decision D8:
reuse the patterns, not the class, because a `FeatureResult` belongs to a `FeatureSet` that names a symbol.

**An unavailable metric is present with `value=None`, never omitted.** Absence from a mapping is ambiguous —
was it not requested, or not computable? An explicit `None` plus a reason in metadata is not.

## 5.3 `DataQuality` — first-class, never optional

```python
@dataclass(frozen=True, slots=True)
class DataQuality:
    aligned_observations: int
    dropped_per_series: Mapping[str, int]   # series_id -> observations discarded by alignment
    staleness: Mapping[str, timedelta]      # series_id -> as_of minus last observation
    common_start: datetime | None
    common_end: datetime | None
    vintage: str                            # "revised" | "point_in_time" | "unknown"
```

`staleness` lives here rather than in the alignment report because it is only definable against an
evaluation instant, and alignment has none (review finding R6). `vintage` is `"unknown"` in v1 and defaults
to being **recorded rather than assumed** — a backtest built on revised macro data is optimistic, and the
honest minimum is to say so in the output (decision D5).

## 5.4 `RelativeValueResult` — the engine's output

```python
@dataclass(frozen=True, slots=True)
class RelativeValueResult:
    relationship_id: str
    definition_version: int
    series_ids: tuple[str, ...]           # input order: (base, quote)
    as_of: datetime                       # the injected evaluation instant
    transform: Transform
    metrics: Mapping[str, RelativeValueMetric]
    data_quality: DataQuality
    provenance: Mapping[str, Any]         # module, parameters, alignment policy, return convention
```

Metric insertion order is the definition's declared order, so repeated runs produce byte-identical output
including key order — a testable property, and a precondition for the regression tests §11 requires.

---

# 6. Public API

Four entry points, and nothing else exported:

```python
# fmis.relative_value.engine
class RelativeValueEngine:
    def __init__(self, *, return_convention: ReturnConvention = ReturnConvention.LOG) -> None: ...

    def compute(
        self,
        definition: RelationshipDefinition,
        series: tuple[ObservationSeries, ...],
        *,
        as_of: datetime,
    ) -> RelativeValueResult: ...
```

`compute` performs exactly five steps, in order:

1. **Validate** — the definition's `base_series_id` and `quote_series_id` are both present in `series`;
   ids are unique; `as_of` is a canonical UTC timestamp; `as_of` is not earlier than the last observation
   used.
2. **Align** — call `align_intersection(...)` and keep its `AlignmentReport`. The engine never inspects
   timestamps itself beyond this.
3. **Compute** — for each metric in the definition's declared order, call a pure function from
   `metrics.py` with plain float sequences and the window.
4. **Assess quality** — derive `DataQuality` from the alignment report plus `as_of`.
5. **Assemble** — build the immutable result. No mutation is possible after this point.

The pure layer is separately importable and independently testable:

```python
# fmis.relative_value.metrics — plain sequences in, plain floats out. No models, no policy, no I/O.
def ratio(a: Sequence[float], b: Sequence[float]) -> list[float]: ...
def log_ratio(a: Sequence[float], b: Sequence[float]) -> list[float]: ...
def indexed(values: Sequence[float], base_index: int = 0) -> list[float]: ...
```

Because these functions cannot see an `ObservationSeries`, they cannot align, cannot forward-fill, and
cannot invent a timestamp. The prohibition is structural, not documentary.

---

# 7. Staged scope

## Milestone J — v1a (first implementation)

`RelationshipDefinition`, `Transform`, the three result types, the engine skeleton, and three metrics:
**indexed performance**, **simple ratio**, **log ratio**. Deliberately no windows and no statistics — this
milestone proves the *contract*, alignment reuse, and the data-quality block on the simplest possible math.

## Milestone K — v1b

Relative return, rolling relative return, **rolling correlation of returns**, rolling volatility ratio.
Introduces windows and the return convention.

## Milestone L — v1c

Rolling mean/σ, z-score of the ratio or spread, relative momentum.

## Explicitly deferred to v2+

Beta and rolling beta; lead-lag scanning; cross-correlation; residual and spread analysis; cointegration;
baskets and weights; ranking and percentile position; regime-conditional relationships; divergence
detection. Each carries statistical hazards (multiple-testing bias in lag scanning, out-of-sample
instability in cointegration) that deserve their own design, not an incremental commit.

## Metrics with a known limitation, recorded now

Every metric ships with its interpretation trap in `metadata["limitations"]`, because the trap travels
with the number to whoever reads it — including the AI layer:

- **Indexed performance** — entirely determined by the base date; a different base tells a different story.
- **Raw ratio** — meaningless across differing units or scales; unstable as the denominator approaches zero.
- **Log ratio** — undefined for non-positive values; symmetric and additive, which is why it is preferred.
- **Relative return** — the window choice dominates the answer; not risk-adjusted.
- **Rolling metrics** — overlapping windows are autocorrelated; successive values are **not** independent
  observations.
- **Correlation** — computed on returns only (correlation of *levels* is spurious: any two trending series
  correlate); symmetric, non-causal, regime-dependent, unstable.
- **Z-score** — **assumes mean reversion that may not exist.** A trending ratio sits at an extreme z-score
  for long stretches while continuing to trend. It is a position measure, not a signal.

---

# 8. Numerical and edge-case policy

Every edge case gets an explicit named outcome. None produces `NaN`, `inf`, or an exception escaping to
the caller as the answer.

| Situation | Policy |
|---|---|
| Denominator is exactly zero (raw ratio) | `value=None`, `metadata["undefined_reason"]="zero_denominator"` |
| Non-positive value under `LOG` | `value=None`, `metadata["undefined_reason"]="non_positive_input"`; the *whole* metric is refused, not silently skipped for some observations |
| Zero variance in a z-score window | `value=None`, `metadata["zero_variance"]=True` — never a division |
| Zero variance in a correlation window | `value=None`, `metadata["undefined_reason"]="zero_variance"` (correlation with a constant series is undefined, not zero) |
| Fewer observations than the mathematical minimum | `value=None`, `metadata["insufficient_data"]=True` plus `required` — exactly the indicator convention |
| Enough for the math, few for the statistics | value **is** computed, plus `metadata["low_sample"]=True` and the threshold used |
| Mismatched `unit` under `RAW` | the engine raises — this is a definition error, not a data condition |
| Empty intersection after alignment | every metric `None`; `DataQuality.aligned_observations == 0`; no exception |

The `low_sample` distinction resolves architecture-doc open question §13.6. A rolling correlation over 20
observations is mathematically defined and statistically close to meaningless. Refusing it would hide
information; returning it bare would overstate it. Computing it and **flagging it** keeps the RVE
fact-only while still telling the truth — and leaves the judgement to the layer that is allowed to judge.

---

# 9. Interaction with the Feature Engine

**No import in either direction.** Not now, and not later.

- The RVE must not import `fmis.features`: it would couple a multi-series engine to a single-instrument
  contract that it cannot satisfy, and a `FeatureSet` cannot name a relationship.
- The Feature Engine must not import the RVE: a cross-asset value inside a single-symbol `FeatureSet`
  misattributes a two-sided measurement to one instrument, and it would create the first cycle in a graph
  that is currently clean.

The two engines meet **one level up**, in the Market Regime Engine and above, where holding both a
`FeatureSet` and a `RelativeValueResult` at once is exactly the point.

**One shared-kernel question must be settled before Milestone K.** "Relative trend" is defined as the EMA of
a ratio, and EMA math already exists as `ema_series` — a genuinely dependency-free pure function that
§5.1 permits anything to import. But it currently lives at
`fmis.features.indicators.ema_math`, *inside* one of the two engines. Having the RVE import it would put a
`fmis.features.*` import into `fmis.relative_value`, which reads as exactly the coupling this section
forbids even though it is technically legal.

**Recommendation: when the second consumer appears, promote the shared kernels to a neutral home** (e.g.
`fmis/kernels/` holding `ema_math.py`, and later the time contract from review finding R4) — the same
extraction that produced `sources.py` and `ema_math.py` in the first place. Until then, keep "relative
trend" out of v1a so the question is answered deliberately rather than under implementation pressure.

---

# 10. Interaction with the other layers

## 10.1 AI Interpretation Layer

Strictly one-directional: the AI layer **consumes** `RelativeValueResult` objects and never produces one.

The RVE hands the AI layer three things, and the third is the one that matters: the metrics, the data
quality, and **the limitations metadata**. An AI asked to interpret a z-score of 2.4 will reach for
"stretched" unless it is simultaneously told that this z-score assumes a mean reversion that may not exist
and is computed over an overlapping, autocorrelated window. Shipping the caveat *with* the number, rather
than in a document the model may never see, is a deliberate design choice.

What the RVE must never do — because the AI layer would then be interpreting an interpretation — is emit a
label, a direction, a score, or a threshold verdict. A suggested guard test, mirroring the existing
`test_feature_category_is_technical_only`: assert that the module's public surface contains no directional
vocabulary. The scope boundary is then enforced, not merely asserted in prose.

## 10.2 Strategy Engine

The Strategy Engine consumes RVE metrics as *evidence* and applies **versioned, explicit** conditions to
them. The division is absolute:

| Belongs to the RVE | Belongs to Strategy |
|---|---|
| `z_score_180 = 1.83` | `z_score_180 > 2.0` as an entry condition |
| `rolling_correlation_90 = 0.42` | "correlation below 0.3 means the hedge is broken" |
| `log_ratio = -0.4213` | any action, including `WAIT` and `NO TRADE` |

Thresholds are strategy parameters, versioned with the strategy — never literals inside the RVE. This is
the direct lesson of the v2→v3 analyzer post-mortem in `docs/analysis-notes.md`, where a judgement embedded
where it did not belong produced systematic directional bias that no test could catch.

## 10.3 Portfolio and Exposure Engine

The Portfolio Engine is the RVE's most demanding consumer, because concentration and correlation-cluster
analysis need the relationship between **every pair of held positions**, not one pair.

Two consequences for this design:

1. **Correlation must be computed in exactly one place.** If the Portfolio Engine grows its own correlation
   routine, the system will eventually report two different correlations for the same pair — the failure
   mode that `ema_math` was extracted to prevent, at a level where it would be far harder to notice.
2. **Pairwise-first, N-series-capable.** Decision D2 is already honoured by the substrate:
   `align_intersection` accepts N series today. v1 exposes a pairwise *definition*, so the N×N step is a
   new definition type plus an orchestration loop over an unchanged aligned container and unchanged pure
   metrics — not a rewrite. That is the specific reason the aligned container was not narrowed to two.

## 10.4 Market Regime Engine

The first consumer that holds both kinds of fact: per-instrument `FeatureSet`s and cross-asset
`RelativeValueResult`s. Correlation regime and risk-on/risk-off classification are impossible without the
RVE, which is why the roadmap places Regime (N) after RVE v1 rather than before — retrofitting cross-asset
evidence into an existing regime engine would be the expensive path.

---

# 11. Testing strategy

Following the established precedent — expected values are **independently derived**, never produced by the
code under test.

- **Exact arithmetic** with `fractions.Fraction` for ratios, indexed performance, returns, and z-scores.
- **Hand-calculated examples** over 3–5 observations where every intermediate step is checkable by eye.
- **Warm-up boundaries on both sides** — exactly-enough versus one-short, for every windowed metric,
  matching the ATR (`period+1`) and MACD (`slow+signal−1`) precedent.
- **Known-answer correlation** — two synthetic series constructed to have an exact analytic correlation
  (perfect ±1, and a hand-computable intermediate value).
- **Alignment reuse** — asserts the engine calls the alignment service and reports its counts rather than
  computing its own intersection.
- **Mixed-calendar** — a 7-day crypto series against a 5-day equity series; dropped observations must be
  *counted*, never absorbed. (Also the missing Milestone I test noted in the architecture review.)
- **No-look-ahead** — a value that becomes knowable after `as_of` must not influence the result at `as_of`.
  Currently expressible only via `as_of` truncation; the stronger release-date form is blocked on review
  finding R3, and that limitation must be stated in the test module rather than left implicit.
- **Edge-case matrix** — every row of §8, asserted individually.
- **Determinism** — repeated runs produce identical output including metric key order.
- **No-signal guard** — the module surface contains no directional vocabulary (§10.1).
- **Regression fixtures** — locked known-answer outputs over a small committed dataset.

---

# 12. Design decisions made in this document

| # | Decision | Alternatives rejected | Why |
|---|---|---|---|
| RV-1 | The RVE consumes **only** `ObservationSeries`; price is reduced to observations before it arrives | Accept `CandleSeries` directly; accept either | One code path for price, macro, on-chain, and derivatives. The RVE never learns what OHLCV is, so it cannot reach for a high or a volume — and every metric is written once. |
| RV-2 | Pure metric functions take **plain float sequences**; only the engine touches models and alignment | Metrics take `ObservationSeries` | Makes D4 structural: a function that never sees a series *cannot* align, fill, or invent a timestamp. Mirrors `ema_math` vs `ema.py`. |
| RV-3 | The engine calls the alignment service itself | Require callers to pre-align | One correct sequence, once. A caller that forgets to align would produce a plausible, wrong number with no trace. |
| RV-4 | `as_of` is **injected**, never read from the clock | Default to `datetime.now(UTC)` | Reproducibility is the project's core property: the same inputs must always give the same output. A wall-clock default would make every result non-reproducible and every backtest non-repeatable. |
| RV-5 | Staleness is reported by the RVE, not by alignment | Put it in `AlignmentReport` | Staleness needs an evaluation instant; alignment has none and must not acquire one. (Review finding R6.) |
| RV-6 | **Log returns** are the default convention for correlation and volatility; simple returns are an explicit override | Simple returns as default; no default | Resolves open question §13.2. Log returns are additive across time and symmetric, and they compose with the log-ratio algebra the RVE is built on: `ln(A/B) = ln A − ln B`. Both remain available; one is documented as the default. |
| RV-7 | **No annualization** in v1 | Annualize with 365 (crypto) or 252 (equity) | Resolves open question §13.3 for v1: the volatility *ratio* `σ_A/σ_B` is scale-free, so a common annualization factor cancels exactly. Annualization only becomes necessary if absolute volatility is ever reported — and then the crypto-vs-equity day-count conflict must be settled explicitly, not inherited. |
| RV-8 | Metrics below the statistical floor are **computed and flagged** (`low_sample`), not refused | Refuse below a minimum; ignore the issue | Resolves open question §13.6. Refusing hides information; returning bare overstates it. Flagging keeps the RVE fact-only and hands the judgement to the layer allowed to judge. |
| RV-9 | Relationship definitions are **frozen dataclasses in code** for v1; the declarative file format is deferred | Build the TOML/JSON loader now (open question §13.1) | A configuration loader with zero users freezes a format before its requirements are known. The frozen object is the contract; a loader is a thin future addition that constructs it. Defer the format choice to the first real definition file. |
| RV-10 | Unavailable metrics are present with `value=None` and a reason | Omit them from the mapping | Absence is ambiguous — not requested, or not computable? An explicit `None` is not. Matches the indicator convention exactly. |
| RV-11 | Shared pure kernels move to a neutral location when a second engine needs them | RVE imports `fmis.features.indicators.ema_math` | Technically legal under §5.1, but it puts a `fmis.features` import inside `fmis.relative_value` and reads as coupling between sibling engines. The extraction precedent already exists. (Also review finding R4.) |

---

# 13. What remains open

1. **`RelationshipDefinition` field naming** — `base`/`quote` is unambiguous for FX and crypto pairs, but
   reads oddly for `BTC vs Global M2`, which is not a pair in the trading sense. `numerator`/`denominator`
   is clearer and less evocative of a tradable instrument. Decide when the first definition is written.
2. **Whether `relationship_id` is caller-supplied or derived** from the definition, as feature names are
   derived from their parameters. Derivation guarantees uniqueness and consistency; supplied ids read
   better in output. Leaning derived-with-optional-override.
3. **The declarative configuration format** (architecture doc open question §13.1) — deferred by RV-9,
   still leaning TOML via stdlib `tomllib`.
4. **Mixed-frequency policy** (open question §13.5) — downsample-to-coarsest versus as-of join on release
   date. Blocked on review finding R3 and genuinely undecidable before macro data exists. Strict
   intersection is the v1 answer, and daily-versus-monthly will simply yield very few common instants — a
   visible, honest result rather than a hidden one.
5. **Whether `RelativeValueResult` should carry the full metric series** or only the latest value. v1a
   returns scalars; backtesting will want series — the same tension as review finding R5, and it should be
   resolved once, for both engines, rather than twice.

---

# 14. Implementation readiness

**The design is complete enough to implement Milestone J, and both prerequisites are now met by Milestone
I-E:**

1. **R1** — `candle_series_to_observations` exists in `fmis.data` (the RVE's price input). ✅
2. **R2** — the alignment service is now `fmis.alignment.align_intersection`
   ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)). ✅

Milestone J may now begin against the contracts above. Separately, the release-date form of the
no-look-ahead guarantee is gated on the availability-time model
([ADR-0003](adr/ADR-0003-availability-time-boundary.md)); v1 supports only the injected-`as_of`
truncation form (§11).
