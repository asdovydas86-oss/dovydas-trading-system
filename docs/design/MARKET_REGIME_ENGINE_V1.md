# Market Regime Engine v1 — Design

**Milestone:** AI
**Status:** Implemented by [ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md)
**Date:** 2026-08-03
**Executes:** `ARCH` §9 — the contract, followed without redesign

---

## 1. The problem, measured

The regime call exists today. It lives in the v3 TradingView prompt's STEP 1, where it cannot be
versioned, diffed, replayed or tested. `ARCH` §9 calls this the highest-leverage unbuilt module in the
system, because regime is the assumption nearly every downstream rule conditions on.

`docs/analysis-notes.md` is the post-mortem of what an unexamined regime call did to v2, and it is the
specification for what this engine must make impossible:

| v2 failure | What it cost | The structural answer here |
|---|---|---|
| Trend gate counted twice (weekly + daily) | LONG began with **two free confirmations** | Evidence votes by **family**; each family votes once; no family feeds two dimensions |
| "Bullish" common, "bearish" a deep-bear condition | Branches were not mirror images | A band is **one** number; its edges are multiplicative mirrors; asymmetry is unrepresentable |
| Tools defined in one direction only | Evidence could only ever support LONG | The engine **never learns direction**; swapping the trend changes nothing |
| No NO-TRADE outcome | Ambiguity resolved to a default | `INSUFFICIENT` and `INDETERMINATE` are first-class, and distinct |
| Order anchoring (LONG evaluated first) | The first framework read wins | Dimensions have a fixed order; no dimension is a verdict |

## 2. Scope

**In:** a regime engine below the application layer · a narrow input model · three inspectable
dimensions · evidence with status · an immutable, versioned policy · an adapter in the composition
root · a renderer · a CLI command · tests · this design · an ADR · an independent review.

**Out, and asserted:** direction of any kind · trade signals · LONG/SHORT scoring · setup detection ·
entry, stop or target · sizing · portfolio risk · scanner · watchlists · persistence · scheduling ·
Telegram · AI interpretation · macro, news, on-chain, derivatives · support/resistance scoring ·
Market Regime v2's non-technical dimensions · the Swing Trading Workspace.

## 3. The design questions, resolved from the repository

### 3.1 What may a regime say?

`ARCH` §9 lists possible outputs: trending/ranging · volatility expansion/contraction · risk-on/risk-off
· liquidity · correlation · crisis. The last four need L6 intelligence that does not exist, so v1 is
**technical regime only**, which the milestone brief also fixes.

That leaves three dimensions the repository can already evidence, and all three are **non-directional**
— which is the property that keeps regime separable from signal.

### 3.2 Where does it live?

`reports/0003` places Market Regime at **L5 · Deterministic Context**, below `fmis.decision_support` at
L7. So it is an engine package, not an application module and not part of decision support — which in
any case consumes an `AnalysisSnapshot` and would have to grow a structural dependency it does not have.

### 3.3 What does it consume?

Evaluated in order of narrowness:

| Candidate input | Verdict |
|---|---|
| `StructuralFactSheet` | **Rejected** — an engine importing an application type inverts ADR-0007 |
| `MultiTimeframeFactSheet` | Rejected for the same reason, and it is three sheets |
| `FeatureSet` + structural runs | Better, but binds the engine to feature *names* |
| **A narrow `RegimeInput`** | **Chosen** — one enum, two indices, six optional floats, one identity |

The narrow model is what makes the engine testable without building a sheet, and it means
`fmis.market_regime` imports exactly one name from the repository: `StructuralTrendType`.

### 3.4 How is double-counting prevented?

By making the **family** the unit of evidence, not the measurement.

Structural trend and change of character are both swing structure. Close-vs-fast-EMA and
close-vs-slow-EMA are both moving averages. Each family produces one reading; the dimension counts
readings, not numbers. And the four families partition across the three dimensions, so no measurement
can push two dimensions and look like independent corroboration.

Structure requires **two agreeing families**. One readable family is `INSUFFICIENT` — refusing the free
confirmation costs only honesty during warm-up.

### 3.5 Why position, not ordering, for the moving averages?

Ordering (fast above slow) is almost always true one way or the other, so it would vote on nearly every
bar — and the direction it votes is the direction of the market. That is the v2 gate's shape exactly.

Position — is the close beyond *both* averages, or between them — is informative about whether price is
extended or contained, and asking "beyond both" rather than "above both" makes it directionless.

### 3.6 Why a ratio for volatility?

A ratio is self-normalising, so the same threshold means the same thing on any instrument, which is
what principle 9 (asset-agnostic) requires. An absolute ATR-percent threshold would encode a
crypto-shaped number.

The slow baseline is a second `AverageTrueRange`, added in `regime_features()` — the same move AG made
when it added `ExponentialMovingAverage(200)` to `swing_features()`. `default_features()` and
`swing_features()` are both untouched, so `facts` and `mtf` compute and print exactly what they did.

### 3.7 What stops a threshold becoming a biased gate?

The type. A band is one number; the edges are `1 + band` and `1 / (1 + band)`. There is no field to
set them independently, and the CLI exposes one `--band`.

This is deliberately stronger than validation. A validator that checked two numbers were "close enough
to symmetric" would be a warning in the place a guarantee belongs, and v2's checklists passed exactly
that kind of eyeball check — nine mirrored items each.

### 3.8 What surface does the owner get?

A new command, `fmits regime SYMBOL [--multi]`. Adding regime to `facts` would have changed a shipped
command's feature set and output, or shipped a volatility dimension that reported `INSUFFICIENT`
forever because `facts` computes no slow baseline.

## 4. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | Swapping `SUSTAINED_HIGHER`/`SUSTAINED_LOWER` changes nothing | both regimes compared whole |
| I2 | No directional word in any state, or any reachable evidence string | whole-word scan over a sweep of inputs |
| I3 | Each family appears in exactly one dimension | partition asserted over the result |
| I4 | Structure needs two readable families | both single-family cases asserted `INSUFFICIENT` |
| I5 | Unavailable is never conflicting | all-`None` input yields no conflicting evidence |
| I6 | Band edges are exact multiplicative mirrors | product of edges is 1.0 |
| I7 | A ratio and its reciprocal classify as mirrors | swept over three bands and four factors |
| I8 | The engine imports one repository name | AST over the package |
| I9 | The engine reads no clock and no network | docstring-stripped source scan |
| I10 | The composition root contains no arithmetic | AST, matching `structural_facts`' predicate |
| I11 | `facts` and `mtf` print no regime vocabulary | rendered output scanned |
| I12 | Dimension order is fixed | asserted, and a reordered construction is rejected |

## 5. Measured results

**Correctness.** 3,582 tests pass, identically under `-W error` (3,449 before AI; **+133**). Coverage
is **100 %** on every module AI touched — `market_regime/{classify,models,policy,__init__}.py`,
`pipeline/regime.py`, `pipeline/render.py`, `pipeline/cli.py`. Public exports **183** (**+29**: 19 new names in
`fmis.market_regime`, 10 re-exported from `fmis.pipeline`), zero collisions. Import cycles **0**. Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

**Mutation.** 45 probes across six modules: **45 detected, 0 survivors, 0 no-ops**, with byte-identical
source restoration verified by SHA-256.

Seven probes survived their first run and **every one was a real test gap** — a boundary asserted on
one dimension but not its twin, an evidence *status* never checked, a guard never exercised, and an
adapter field whose fixture happened to be empty. All seven are closed; see
[the review](../reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md) §6.

**Performance.** Classification is free relative to the data it reads.

| candles | fact sheet | adapt | classify | classify share |
|---:|---:|---:|---:|---:|
| 100 | 1.21 ms | 0.0023 ms | 0.0059 ms | 0.49 % |
| 260 | 5.98 ms | 0.0024 ms | 0.0059 ms | 0.10 % |
| 500 | 21.54 ms | 0.0023 ms | 0.0061 ms | 0.03 % |

Live end to end at 300 candles including network: **~1.4 s**, essentially all fetch.

**Determinism.** Output is identical under `PYTHONHASHSEED` 0, 1, 42 and 12345 in fresh processes.

**Review.** No P0, no P1, **four P2 found and fixed** — a direction printed in the evidence, a
provenance field typed `Any`, a validation order producing the wrong exception, and an assertion that
could never fail — and three P3 recorded.

## 6. What it does not claim

Not a direction. Not a signal. Not a setup. Not a forecast. Not a probability. `TRENDING` says
structure is sustained, not that price is rising; `ELEVATED` participation says volume is above its own
average, not that the move is real. The regime is an environment a later layer may condition on, and
the sheet says so on every run.
