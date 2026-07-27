# ADR-0004 — RVE v1a: return convention and result policy

**Status:** Accepted
**Date:** 2026-07-24
**Decides:** the concrete contracts for the first Relative Value Engine implementation (Milestone J v1a)
**Implemented by:** `feat(relative_value): implement RVE v1a deterministic metrics`
**Relates to / refines:** [RVE_DESIGN_V1.md](../RVE_DESIGN_V1.md) (RV-6, §5.2, §7), which this ADR
supersedes **for v1a** where they differ; [ADR-0002](ADR-0002-alignment-as-temporal-comparison-policy-layer.md)
(alignment is a separate upstream policy); [ADR-0003](ADR-0003-availability-time-boundary.md)
(availability-time gate for macro/vintage data)

---

## Context

Milestone J implements the first RVE metrics. The design doc `RVE_DESIGN_V1.md` left several choices open
or leaning a different way than the J-0 review concluded, so the binding decisions are recorded here
before code, because they fix public formulas, return types, and error behaviour that later milestones
build on.

## Decisions

### 1. Simple returns only; log returns deferred
The return convention for every v1a metric is the **simple** return

```
r_t = P_t / P_{t-1} - 1
```

Log returns are **not** implemented and not silently supported. This overrides the *lean* toward log
returns in `RVE_DESIGN_V1.md` RV-6. Rationale: simple returns are the intuitive default, and v1a has no
log-ratio algebra to benefit from log additivity (price ratio is deferred, §5). A log-return variant is a
deliberate future addition, not a hidden option.

### 2. Unannualized sample volatility (Bessel)
`realized_volatility` is the **sample** standard deviation of simple returns with **Bessel correction**
(divide by `m − 1`, `m` = number of returns). There is **no annualization**: `ObservationSeries.frequency`
is a free-text label, not canonical periods-per-year metadata, so annualizing would require inventing or
inferring a frequency. Every result carries `annualized = False` and `standard_deviation = "sample_bessel"`.
Frequency is never inferred from `series_id` or `frequency` strings.

### 3. Alignment is explicit and upstream; the RVE never aligns
Pairwise metrics require their inputs to already be aligned: identical length **and** identical
`timestamps` tuples (guaranteed by `fmis.alignment.align_intersection`, which canonicalizes common
instants to the first series' objects). The RVE never aligns, intersects, fills, resamples, or drops
observations. A mismatch raises `NotAlignedError`. The RVE does **not** import or call `fmis.alignment`.

### 4. Hybrid result policy: raise structural errors, return structured undefined
- **Structural / caller-contract failures raise** — wrong input type (`TypeError`), too few observations
  (`InsufficientObservationsError`), unaligned inputs (`NotAlignedError`). These are ill-formed requests
  and must surface loudly.
- **Mathematically undefined results do not crash** — a valid, aligned, long-enough series whose metric is
  simply undefined returns a `RelativeValueResult` with `status = UNDEFINED`, `value = None`, and a
  `reason` (`ZERO_DENOMINATOR`, `ZERO_VARIANCE`, `ZERO_REFERENCE_VOLATILITY`, `NON_FINITE_RESULT`), so an
  analytics pipeline records and continues.

This refines `RVE_DESIGN_V1.md` §5.2's plain `value = None` convention by adding an explicit `status`/
`reason`, and it deliberately differs from the indicator layer's bare `value=None` warm-up state — RVE
inputs are caller-controlled aligned windows, so degeneracy carries a reason.

`RelativeValueResult` invariants: `OK` ⇒ finite `float` value and `reason is None`; `UNDEFINED` ⇒
`value is None` and a `reason`; violations raise `ValueError`; `metadata` is a defensively-copied
`MappingProxyType`.

### 5. Scalar-only v1a scope; ratio/spread/beta deferred
v1a implements exactly five **scalar** metrics: `period_return`, `relative_return`,
`realized_volatility`, `volatility_ratio`, `pearson_correlation` (correlation over simple returns).

Deferred: **price ratio** and **arithmetic spread** (series-valued; spread additionally blocked on unit
fidelity — the reduction stamps all OHLC as `unit="price"`, which cannot distinguish USD from index
points); **beta** (collinear with `correlation × volatility_ratio`, and requires explicit
denominator/return-convention/zero-variance/ordering decisions per RVE_DESIGN D-considerations); and all
rolling, annualized, z-score, regression, ranking, composite-score, and signal variants.

### 6. Fact-only, deterministic, stdlib-only
No LONG/SHORT/BUY/SELL, scores, rankings, confidence values, labels, recommendations, or AI narratives —
not in values and not in metadata. Pure arithmetic, reproducible, `math`-and-stdlib only; no pandas,
numpy, scipy, or new dependencies.

## Alternatives considered

- **Log returns as default (RVE_DESIGN RV-6).** Rejected for v1a: less intuitive, and its additivity
  advantage only pays off with the deferred log-ratio algebra.
- **Raise on every undefined result.** Rejected: zero variance / zero denominator on otherwise-valid data
  is a normal analytical outcome across many pairs; crashing a batch on one degenerate pair is hostile to
  the intended pipeline use.
- **Bare `value=None` (no status/reason).** Rejected: ambiguous — an auditor cannot tell *why* a value is
  absent. `status` + `reason` is self-describing.
- **Population standard deviation.** Rejected: realized volatility from a finite sample is an estimate;
  the Bessel-corrected sample stdev is the standard unbiased-variance choice.
- **Include price ratio in v1a.** Rejected (borderline): it is series-valued and would break the uniform
  scalar result shape; deferred to a series-transform milestone.

## Consequences

- Public v1a API is five pure functions returning `RelativeValueResult`; alignment stays a caller
  responsibility; undefined results are inspectable, not exceptional.
- `RVE_DESIGN_V1.md` is annotated (not rewritten) to point at this ADR where it previously leaned toward
  log returns / `value=None` / a heavier engine design.
- Later milestones inherit these contracts: a log-return variant, price ratio/spread (post unit-fidelity),
  beta, and rolling/annualized metrics are additive future work, each its own decision.
