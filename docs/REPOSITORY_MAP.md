# Repository Map

A directory-by-directory guide to the **current** repository, with the allowed and forbidden
dependencies for each area. This is a navigation and guardrail document; the authoritative rules on
dependency direction and module boundaries are in
[ARCHITECTURE_AND_ROADMAP_V1.md](ARCHITECTURE_AND_ROADMAP_V1.md) §4–§5.

Everything below describes what exists **today** unless explicitly marked **Planned** or
**Future milestone**.

---

## Top-level layout

```
.
├── src/fmis/               Python package (the system)
├── tests/                  pytest suite (1040 tests) + fixtures
├── docs/                   all documentation (this file lives here)
├── prompts/                AI prompt prototypes (not wired to Python)
├── scripts/                operational scripts (TradingView launcher)
├── config/                 non-secret config templates
├── pyproject.toml          packaging + pytest config; zero runtime dependencies
├── uv.lock / .python-version   reproducible uv-managed Python 3.12 environment
└── PROJECT_SPECIFICATION_V1.md, PROJECT_VISION_ADDENDUM_V1.md   authoritative vision
```

The dependency principle in one line: **dependencies point toward the deterministic core; nothing
depends on a later stage of the pipeline** (architecture doc §5.1).

---

## `src/fmis/`

- **Purpose:** the installable package. Root holds package metadata only (`__version__`).
- **Responsibilities:** house the domain models, the deterministic feature engine, and (Planned) the
  future analytical engines.
- **Allowed dependencies:** Python standard library only. The project has **zero runtime dependencies**.
- **Forbidden dependencies:** any third-party runtime package; any provider SDK; any network/O calls in
  the current layers.

## `src/fmis/data/` — canonical market-data models

- **Purpose:** the domain **kernel** — the canonical, validated, immutable representation of market data.
- **Responsibilities today:**
  - `models.py` — `Candle` and `CandleSeries` (frozen dataclasses; non-negative validated OHLCV;
    strictly increasing canonical-UTC timestamps; `closed()` to drop the forming bar).
  - `observation.py` — `ObservationSeries`, the canonical **non-OHLC** numeric series (macro, on-chain,
    derivatives, sentiment, breadth, benchmark levels). Parallel `timestamps`/`values` tuples; values may
    be negative but never `bool`; empty series are valid.
  - `_timeutils.py` — `validate_utc_timestamp`, the system-wide canonical time contract: a canonical
    timestamp must use a **permanent** zero-offset timezone, validated and **never converted**. See
    [ADR-0001](adr/ADR-0001-canonical-utc-timestamps.md).
  - `reduction.py` — `candle_series_to_observations(series, field, *, series_id=None)` plus the
    `CandleField` enum: a **pure** transform from one explicitly-chosen candle field to an
    `ObservationSeries`, over **closed candles only**. No default field (the enum is required); no
    alignment, fill, resampling, or unit/timezone conversion. This is the bridge from the candle pipeline
    into the observation/alignment pipeline (review finding R1).
- **Allowed dependencies:** standard library only, plus other modules **inside** `fmis.data`.
- **Forbidden dependencies:** **imports nothing from outside `fmis.data`** — this is verified and must
  stay true. (Intra-package imports are expected and fine; the invariant is about the package boundary.)
  It must never import `fmis.features`, `fmis.alignment`, provider adapters, or anything downstream.
  Provider-specific types (e.g. TradingView shapes) must never become canonical models here.
- **Boundary note:** alignment is **no longer here.** It moved to the sibling package `fmis.alignment`
  (see below and [ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)), and
  `fmis.data` deliberately does **not** re-export it — this keeps the package a pure canonical kernel and
  stops downstream layers importing alignment transitively.

## `src/fmis/trading_context/` — trading analysis context

- **Purpose:** record what a *trading* analysis is scoped to — its objective and timeframes — so a future
  trading reasoning layer receives that explicitly instead of inferring it. Descriptive value objects
  with **no behaviour**. Contracts: [ADR-0009](adr/ADR-0009-trading-analysis-context-boundary.md).
- **Responsibilities today:** `context.py` — `TradingObjective` (`SWING_TRADE`, `DAY_TRADE`) and the
  frozen `TradingAnalysisContext` (`objective`, `primary_timeframe`, `supporting_timeframes`,
  `benchmark_symbol`, `notes`).
- **Allowed dependencies:** **none from `fmis`** — standard library only. This is a leaf that higher
  layers depend on; the direction never reverses, and a test asserts no lower or sibling layer references
  it.
- **Forbidden dependencies:** every other `fmis` package, plus network, AI, persistence, execution,
  portfolio, and future investment modules.
- **Hard rules:** **long-term investing is not a trading objective** and has no enum member — it becomes
  its own module with its own context. No objective-dependent branching anywhere (test-enforced: no enum
  member is referenced outside its own definition). The objective is never inferred from a timeframe, and
  no timeframe is selected, defaulted, reordered, or recommended. No direction/entry/stop/target/size/
  leverage/risk/confidence/strategy fields — the field list is pinned by test. Timeframes are `str`
  because no canonical timeframe type exists (ADR-0006 §6); their syntax is deliberately unvalidated.
- **Not integrated with the pipeline**, deliberately: nothing there would read it, and a stored-but-unread
  field invites being mistaken for meaning. See [ADR-0009](adr/ADR-0009-trading-analysis-context-boundary.md) §9.

> **Shared calculations do not imply shared decision logic.** The deterministic engines are
> objective-agnostic and reused by everything; what their numbers *mean* stays module-specific.

## `src/fmis/market_structure/` — market structure primitives

- **Purpose:** deterministic swing detection — *located facts* about where local extremes occurred.
  Contracts: [ADR-0012](adr/ADR-0012-market-structure-foundation.md).
- **Responsibilities today:** `models.py` — `SwingType` (HIGH/LOW) and the frozen, slotted, hashable
  `SwingPoint` (`index`, `timestamp`, `price`, `type`); `swings.py` — `detect_swings`,
  `required_candles`, and the `DEFAULT_LEFT_BARS`/`DEFAULT_RIGHT_BARS` defaults.
- **Allowed dependencies:** `fmis.data` (the canonical `CandleSeries`); standard library only.
- **Forbidden dependencies:** `fmis.decision_support`, `fmis.evidence`, `fmis.providers`,
  `fmis.pipeline`, `fmis.features`, `fmis.trading_context`, and anything AI / execution / portfolio.
  Nothing below imports this package.
- **Hard rules:** **closed candles only**; never inspect a candle outside `[i-left, i+right]`; a point,
  once emitted, is never revised by later data (asserted by a prefix property test over random series).
  Comparison is **strictly greater on the left, greater-or-equal on the right**, so a plateau yields
  exactly one point (the first bar) while separated equal highs stay two distinct swings. Insufficient
  history returns `()`, not an error. **No interpretation** — no BOS, CHoCH, HH/HL/LH/LL, trend, support,
  resistance, or liquidity, and `SwingPoint` carries no direction, strength, or confidence.
- **Index semantics:** `SwingPoint.index` is a position in `series.closed().candles`, never in the raw
  series.
- **Where structural *interpretation* belongs:** `fmis.features.market_structure` (Tier-2), which
  consumes these points and expresses a result as a `FeatureValue`. Detection is here because a tuple of
  `SwingPoint` objects is not a `FeatureValue`.

## `src/fmis/evidence/` — evidence taxonomy

- **Purpose:** shared vocabulary for *what evidence is about*. Definitions only — no observation, no
  value, no behaviour. Contracts: [ADR-0011](adr/ADR-0011-evidence-taxonomy.md).
- **Responsibilities today:** `families.py` — `EvidenceFamily` (TREND, MOMENTUM, VOLUME, VOLATILITY,
  MARKET_STRUCTURE, RELATIVE_STRENGTH, LIQUIDITY, MACRO, NEWS, SENTIMENT); `descriptor.py` —
  the frozen, slotted `EvidenceDescriptor` (`family`, `name`, `description`); `catalog.py` — the
  immutable, canonically ordered catalog plus `descriptors()`, `descriptors_for()`, `find()`.
- **Allowed dependencies:** **none from `fmis`** outside this package; standard library only.
- **Forbidden dependencies:** every other `fmis` package — and **`decision_support` in particular**, in
  both directions: this package does not import it, and it was not modified to import this one. Both are
  test-enforced.
- **Hard rules:** a **calculated indicator is not automatically evidence** — a descriptor exists only for
  a concept the system genuinely *classifies* today, verified by a test that builds a real report and
  matches every catalogued name against an emitted, classified observation. No score, weight, confidence,
  direction, or availability field. **No combined evidence-type enum**: supporting/conflicting is owned by
  `EvidenceGroups`, neutral/unavailable by `Alignment`, insufficient-data by `OverallState` and feature
  metadata. Names must already be normalized (rejected, never rewritten). No mutable registry, no plugin
  mechanism, no arithmetic.
- **Current catalog:** six descriptors — TREND (`price_vs_ema_fast`, `price_vs_ema_slow`,
  `ema_fast_vs_ema_slow`) and MOMENTUM (`rsi_zone`, `macd_vs_signal`, `macd_histogram`). The other five
  populated-looking families are **empty on purpose**: volume and volatility are measured but not
  classified, and the relative-value metrics are restated unchanged.
- **Where a new descriptor belongs:** `catalog.py` — but only after the corresponding classification
  actually exists, which the cross-check test enforces.

> **A shared vocabulary is not shared interpretation.** Trading, investing, macro and news modules may
> each read the same family differently; the taxonomy names the subject and says nothing about the claim.

## `src/fmis/decision_support/` — Decision Support Evidence v1

- **Purpose:** organise an `AnalysisSnapshot` into structured, deterministic evidence so a human — or a
  later interpretation layer — reasons from structure rather than from a bag of numbers. Sits **above**
  `fmis.pipeline`. Contracts: [ADR-0008](adr/ADR-0008-decision-support-evidence-boundary.md).
- **Responsibilities today:** `classification.py` — the written-out rules (`classify_comparison`,
  `classify_rsi_zone`, `classify_sign`) and their vocabulary; `derived.py` — the single derived
  calculation `atr_percent_of_close`; `report.py` — `build_evidence_report` and the immutable result
  types (`EvidenceReport`, `MarketContext`, `TrendEvidence`, `MomentumEvidence`, `VolatilityEvidence`,
  `RelativeValueEvidence`, `EvidenceGroups`, `Observation`, `Scenario`, `OverallState`).
- **Allowed dependencies:** `fmis.pipeline` (its published result types); standard library.
- **Forbidden dependencies:** every engine — no provider, ingest, feature, alignment, or RVE import; no
  `fmis.pipeline` submodule. **Nothing below may import this**, the pipeline included (test-enforced).
- **Hard rules:** consumes snapshots only — no fetching, no indicator math, no metric recomputation
  (RVE values are restated from the snapshot). **Classification, not calculation:** only `derived.py` may
  compute, enforced by an AST test. No LLM, prompt, API, network, persistence, CLI, or dashboard; no rule
  engine or configurable strategy system. An RSI band is `NOT_DIRECTIONAL` by rule; an alignment tie stays
  a tie; scenarios restate observations and contain no number. **No trading vocabulary** in any value,
  field name, or metadata — test-enforced against a banned-word list.
- **Where a new rule belongs:** a new pure function in `classification.py` with its own boundary tests; a
  second derived number goes beside `atr_percent_of_close` in `derived.py`, or into an engine.

### Usage

```python
from fmis.pipeline import analyze_symbol
from fmis.decision_support import build_evidence_report

report = build_evidence_report(
    analyze_symbol("BTCUSDT", "4h", limit=200, benchmark_symbol="ETHUSDT")
)
report.state                       # OverallState.WATCH | WAIT | INSUFFICIENT_DATA
report.groups.dominant_alignment   # reported separately from the state
report.volatility.atr_percent_of_close
report.scenarios["deterioration"].conditions
```

## `src/fmis/pipeline/` — application layer (Market Analysis Pipeline v1)

- **Purpose:** the **top** of the dependency graph and the only layer allowed to know about more than one
  engine. It composes provider → ingestion → features → alignment → RVE into one structured answer.
  Contracts: [ADR-0007](adr/ADR-0007-application-layer-boundary.md).
- **Responsibilities today:** `market_analysis.py` — `analyze_symbol(...)` returning an immutable
  `AnalysisSnapshot` (`DataWindow`, `FeatureSet`, optional `RelativeValueSection`), `default_features()`,
  and the `PipelineError`/`InsufficientDataError` hierarchy.
- **Allowed dependencies:** every engine (`fmis.providers`, `fmis.ingest`, `fmis.data`, `fmis.features`,
  `fmis.alignment`, `fmis.relative_value`); standard library.
- **Forbidden dependencies:** **no engine may import `fmis.pipeline`** — a test walks all of `src/fmis`
  outside this package and asserts nothing references it. No private modules of any engine.
- **Hard rules:** **orchestration only** — no formula may be defined here; a test asserts the module
  contains exactly one arithmetic operator (an excluded-candle count) and imports no `math`/`statistics`,
  and another asserts its RVE outputs equal calling the RVE directly. Closed candles **unconditionally**.
  Warm-up is a result; insufficient data raises. Nothing partial: a failed benchmark fails the call.
  Downstream errors propagate unwrapped. Fact-only — no direction, score, confidence, or recommendation.
- **Where a new workflow belongs:** a new function (or module) here — never a generic stage/registry
  framework, and never a calculation. A new indicator goes in `fmis.features`; a new metric in
  `fmis.relative_value`.

### Usage

```python
from fmis.pipeline import analyze_symbol

# 1. BTCUSDT technical snapshot
snap = analyze_symbol("BTCUSDT", "4h", limit=200)
snap.as_of, snap.window.closed_count, snap.features.get("rsi_close_14").value

# 2. BTCUSDT compared with ETHUSDT
cmp = analyze_symbol("BTCUSDT", "1d", limit=90, benchmark_symbol="ETHUSDT")
cmp.relative_value.metrics["pearson_correlation"].value
cmp.relative_value.alignment.aligned_observation_count
```

## `src/fmis/providers/` — provider adapters

- **Purpose:** the only layer that knows an external API's shape. An adapter fetches from one concrete
  provider, parses its payload into the canonical `CANDLE_FIELDS` record shape, and hands it to
  `fmis.ingest`. Contracts: [ADR-0006](adr/ADR-0006-provider-adapter-contract.md).
- **Responsibilities today:** `binance.py` — public spot klines (`GET /api/v3/klines`, **no API key**):
  `fetch_klines`, `map_kline`, `build_klines_url`, `urlopen_transport`, the `HttpResponse`/`Transport`
  types, and the `BinanceError` hierarchy (`BinanceRequestError`, `BinanceTransportError`,
  `BinanceAPIError`, `BinanceResponseError`).
- **Allowed dependencies:** `fmis.ingest`, `fmis.data` (types only); standard library — `urllib`, so the
  zero-runtime-dependency invariant holds.
- **Forbidden dependencies:** `fmis.features`, `fmis.alignment`, `fmis.relative_value`; any third-party
  HTTP library. An adapter must **not** construct `Candle` directly — canonical validation is reached
  only through `fmis.ingest`, and a test enforces this.
- **Hard rules:** public market data only — no authentication, private/account/order endpoints,
  websockets, trading, caching, persistence, scheduling, or retries. Transport is an **injected
  callable** returning `(status, body)` and never raising on HTTP status, so tests never touch the
  network. Provider errors raise explicitly and are **never** turned into an empty series. Forming
  candles are flagged via an injectable clock, returned rather than dropped.
- **Where a new adapter belongs:** a new module here as a sibling of `binance.py`, following ADR-0006.
  There is deliberately **no** generic provider Protocol until a second adapter proves the shape.

## `src/fmis/ingest/` — ingestion boundary (v1: candles)

- **Purpose:** the one place where data FMITS did not construct itself becomes a canonical model.
  Upstream of it everything is untrusted; downstream of it everything is a validated `CandleSeries`.
  Contracts: [ADR-0005](adr/ADR-0005-ingestion-boundary-strictness.md).
- **Responsibilities today (v1):** `candles.py` — `decode_candle`, `decode_candle_series`,
  `decode_candle_series_from_json`, the `CANDLE_FIELDS` canonical record shape, and the
  `IngestError`/`RecordDecodeError`/`SeriesDecodeError` hierarchy. Validates **shape** (field presence and
  type) and delegates every domain invariant to `Candle`/`CandleSeries`.
- **Allowed dependencies:** `fmis.data` (the canonical models it builds); standard library only.
- **Forbidden dependencies:** `fmis.features`, `fmis.alignment`, `fmis.relative_value`, and
  `fmis.data._timeutils` (the UTC contract is enforced by `Candle`, never re-implemented here); no
  pandas/numpy; no new runtime dependencies.
- **Hard rules:** **decoder, not provider adapter** — no transport, network, credentials, retries,
  pagination, rate limits, or provider-specific field names. Never coerces (numeric strings and `0`/`1`
  booleans are rejected), never repairs, never sorts, deduplicates, filters, or forward-fills. Missing
  **and** unexpected fields are both errors. Every error carries the record index, and the field where
  attributable.
- **Where new ingestion belongs:** a new module here (e.g. `observations.py`) as a sibling of
  `candles.py`. `ObservationSeries` decoding is deliberately **not** implemented yet — its real sources
  are macro/revised/vintage series, gated by [ADR-0003](adr/ADR-0003-availability-time-boundary.md).
  A provider adapter (transport + renaming into `CANDLE_FIELDS`) belongs in its own future package, not
  here.

## `src/fmis/alignment/` — temporal-comparison policy layer

- **Purpose:** answer *how two or more canonical series are made comparable in time* — a **policy**
  concern, deliberately separate from the canonical models ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)).
- **Responsibilities today:** `intersection.py` — `align_intersection` plus `AlignmentResult` /
  `AlignmentReport` / `SeriesAlignmentStats`: **strict timestamp intersection only**. No interpolation,
  forward-fill, resampling, nearest-match, tolerance, or timezone conversion — ever. Public path:
  `fmis.alignment.align_intersection`.
- **Allowed dependencies:** `fmis.data` (the canonical models it aligns); standard library.
- **Forbidden dependencies:** anything downstream (`fmis.features`, strategy, RVE, execution). Canonical
  models never import alignment.
- **Where a new policy belongs:** a new module here (e.g. `asof.py`, `resample.py`) as a sibling of
  `intersection.py` — never inside `fmis.data`. Each future policy must be explicit, named, and reported,
  and must never silently invent data. Availability-aware/as-of policies additionally depend on the
  availability-time model gated by [ADR-0003](adr/ADR-0003-availability-time-boundary.md).

## `src/fmis/relative_value/` — Relative Value Engine (v1a)

- **Purpose:** deterministic, **fact-only** measurement of relationships between two or more already-aligned
  series (and per-series summaries) — the question the single-instrument Feature Engine cannot express.
- **Responsibilities today (v1a):** five scalar metrics in `metrics.py` — `period_return`,
  `relative_return`, `realized_volatility`, `volatility_ratio`, `pearson_correlation` — over **simple**
  returns, **unannualized**, **no rolling windows**; and `models.py` — `RelativeValueResult`
  (`status` OK/UNDEFINED + `reason` + immutable provenance metadata), `MetricStatus`, `UndefinedReason`,
  and the `RelativeValueError`/`NotAlignedError`/`InsufficientObservationsError` hierarchy. Contracts:
  [ADR-0004](adr/ADR-0004-rve-v1a-return-and-result-policy.md).
- **Allowed dependencies:** `fmis.data` (canonical `ObservationSeries`); standard library only.
- **Forbidden dependencies:** **must not import `fmis.features`**; **must not call `fmis.alignment`
  internally** (alignment is an explicit upstream policy the caller performs); no pandas/numpy/scipy; no
  provider/API/TradingView/AI/adapter code.
- **Hard rules:** never aligns/intersects/fills/resamples/drops (pairwise metrics require identical
  `timestamps` + equal length, else `NotAlignedError`); never infers frequency from `series_id`/`frequency`
  strings; never annualizes; emits **no** LONG/SHORT/score/ranking/confidence/label/recommendation, in
  values or metadata.
- **Where a new metric belongs:** a new pure function in `metrics.py` returning a `RelativeValueResult`,
  with hand-derived tests on both warm-up boundaries. Deferred (each its own milestone): price ratio,
  arithmetic spread, beta, rolling/annualized variants — see
  [ADR-0004](adr/ADR-0004-rve-v1a-return-and-result-policy.md) §5.

## `src/fmis/features/` — deterministic Feature Engine

- **Purpose:** compute single-instrument, single-timeframe deterministic technical features and assemble
  a `FeatureSet`.
- **Key modules today:**
  - `types.py` — `FeatureValue`, `FeatureCategory` (technical-only, test-enforced), regime enums,
    `FeatureResult` (frozen; metadata is an immutable `MappingProxyType`), `FeatureContext`,
    `FeatureSet`, the `Feature` protocol, and `BaseFeature`.
  - `registry.py` — `FeatureRegistry` (name → feature; duplicate names raise).
  - `feature_engine/` — see below.
  - `indicators/` — see below.
  - `trend/`, `momentum/`, `volatility/`, `market_structure/`, `support_resistance/`,
    `pattern_detection/` — **placeholder packages** (docstring + planned-features `TODO` list +
    `__all__ = []`; **no calculation code**). These are the intended homes for the **Planned** Tier-2
    Composite Feature Layer.
- **Allowed dependencies:** `fmis.data`; the shared kernels `indicators/sources.py` and
  `indicators/ema_math.py`; standard library.
- **Forbidden dependencies:** provider code; any AI/interpretation code; strategy, risk, backtesting, or
  execution code; anything downstream in the pipeline.
- **What must NEVER be placed into the Feature Engine:**
  - Trading signals, directional labels ("bullish"/"bearish"), scores, or confidence values.
  - Strategy conditions or thresholds framed as decisions.
  - Cross-asset / relationship logic — a feature is single-instrument by construction
    (`FeatureContext.primary` is one `CandleSeries`; `FeatureSet` identity is `(symbol, timeframe,
    as_of)`). Relationships belong in the **Relative Value Engine** (Planned), not here.
  - Non-technical domains (macro, news, on-chain, derivatives, sentiment) — `FeatureCategory` is
    technical-only and enforced by a test.
  - AI interpretation of any kind.

## `src/fmis/features/volume/` — Tier-2 volume measurements

- **Purpose:** deterministic volume **measurements** — the first Tier-2 category with calculation code.
  Contracts: [ADR-0010](adr/ADR-0010-volume-foundation.md).
- **Responsibilities today (v1a):** `volume_math.py` — `trailing_mean` / `required_values`, the **single
  source of truth** for the baseline window; `statistics.py` — `AverageVolume` and `RelativeVolume`
  features (`FeatureCategory.VOLUME`).
- **Window convention:** the baseline is the `lookback` candles **preceding** the latest closed one, which
  is excluded from its own comparison; warm-up is `lookback + 1`. Default lookback 20.
- **Allowed dependencies:** `fmis.features.types` and its own kernel; standard library. The kernel imports
  nothing internal at all.
- **Forbidden dependencies:** `fmis.pipeline`, `fmis.decision_support`, `fmis.providers`, `fmis.ingest`,
  `fmis.alignment`, `fmis.relative_value`, `fmis.trading_context`; anything provider- or market-specific.
- **Hard rules:** **measurements, not conclusions** — no label, threshold, direction, or judgement
  (test-enforced, including a scan for threshold constants). A zero baseline is reported as undefined,
  never as infinity and never with an epsilon. Volume validity is inherited from `Candle`, never
  re-validated. No other package may re-derive the baseline or the ratio (test-enforced across all seven
  lower/sibling packages, with a rename guard).
- **Where a new volume metric belongs:** a sibling of `statistics.py`, reusing `trailing_mean`. VWAP, OBV,
  accumulation/distribution, money-flow and volume profile are each their own future milestone.

> **Shared calculation does not mean identical interpretation.** The same relative-volume arithmetic
> serves crypto, HKEX, Shanghai/Shenzhen, mining equities and large-cap AI names — venues whose session
> structure, auction mechanics, price limits and venue fragmentation make the same number mean different
> things. The core measures; market-aware reasoning interprets.

## `src/fmis/features/feature_engine/`

- **Purpose:** orchestration only — resolve requested features into deterministic dependency order and
  assemble a `FeatureSet`.
- **Responsibilities today:** `FeatureEngine.compute(series, names, sources=...)` operates on
  `series.closed()`, topologically orders features by their declared `dependencies`, rejects unknown
  features and dependency cycles, threads results through `FeatureContext.computed`, and stamps the
  `FeatureSet` with the last closed candle's timestamp.
- **Allowed dependencies:** `fmis.data`, `fmis.features.registry`, `fmis.features.types`.
- **Forbidden dependencies:** **must never import a concrete feature** (discovery is via the registry);
  no math, no interpretation, no strategy.

## `src/fmis/features/indicators/` — Tier-1 primitives

- **Purpose:** raw, deterministic technical-analysis primitives. One class = one parameter set = one
  stable feature name.
- **Implemented today:**
  - `ema.py` — `ExponentialMovingAverage` (SMA seed, `k = 2/(period+1)`).
  - `atr.py` — `AverageTrueRange` (Wilder).
  - `rsi.py` — `RelativeStrengthIndex` (Wilder; explicit 100/0/50 zero policy).
  - `macd.py` — `MovingAverageConvergenceDivergence` (structured immutable
    `{macd_line, signal_line, histogram}` value).
  - `sources.py` — `VALID_SOURCES` shared OHLC vocabulary (dependency-free kernel).
  - `ema_math.py` — `ema_series()` shared EMA math used by EMA and MACD (dependency-free kernel).
- **Allowed dependencies:** `fmis.features.types`, and the two local kernels; standard library.
- **Forbidden dependencies:** **no sibling indicator may import another sibling** (the shared vocabulary
  and EMA math were extracted into `sources.py`/`ema_math.py` precisely to prevent this); no third-party
  TA library; no interpretation.
- **Where a new indicator belongs:** a new module here, exported from `indicators/__init__.py`,
  implementing the `Feature` protocol, closed-candles-only, with explicit warm-up and insufficient-data
  handling, provenance in metadata, and independently verified tests.

## `tests/`

- **Purpose:** the correctness contract. **1040 tests** across 21 modules, plus `tests/fixtures/` (a small
  committed OHLCV dataset) and `conftest.py`.
- **Responsibilities:** verify every deterministic calculation against independently derived expected
  values; test warm-up boundaries on both sides; test immutability and validation.
- **Import-boundary tests:** tests that assert what a *cold* `import fmis.<pkg>` pulls in must take the
  `fresh_fmis_imports` fixture (`conftest.py`) rather than clearing `sys.modules` inline. The fixture
  restores the original module objects afterwards; without that restore, later tests comparing class
  identity against a module-level import fail or pass purely according to alphabetical file ordering.
- **Allowed dependencies:** `pytest` (the only dev dependency), the `fmis` package, standard library.
- **Forbidden dependencies:** network access (provider adapters are tested with an injected transport,
  never a live endpoint); nondeterministic inputs (an injected clock, never wall-clock time); deriving
  expected values by calling the implementation under test.

## `docs/`

- **Purpose:** all project documentation. Two subdirectories: `AI_HANDOFF/` (agent-facing docs) and
  `adr/` (Architecture Decision Records); everything else is flat.
- **Responsibilities:** entry point, repository map, architecture, decision records, review records,
  current-state snapshot, historical audits, setup.
- **Convention:** authoritative documents use `UPPERCASE_SNAKE_V*.md` and are versioned rather than
  overwritten; navigation/reference docs use plain names; ADRs use `adr/ADR-NNNN-kebab-title.md` and are
  never renumbered or deleted (a superseded ADR is marked, not removed); review records are dated
  (`ARCHITECTURE_REVIEW_YYYY-MM-DD.md`).

## `prompts/`, `scripts/`, `config/`

- **`prompts/`** — AI prompt prototypes (e.g. the v3 swing analyzer). **Not** imported by Python; a
  prototype record, not production code.
- **`scripts/`** — operational shell scripts (`tradingview-launcher.sh` opens the CDP debug port for the
  TradingView MCP workflow). The TradingView MCP integration is entirely outside the Python package —
  **there is zero coupling between it and `src/`**, which must remain true.
- **`config/`** — non-secret config templates only (e.g. `mcp.json.example`); real secrets live in
  git-ignored files.

---

## Where future engines will live (Planned)

These do **not** exist yet. Locations are proposals from the architecture document, not current code.

| Future module | Planned location (proposal) | Belongs separate from Feature Engine because |
|---|---|---|
| ~~**Relative Value Engine**~~ | **Built (v1a)** — `src/fmis/relative_value/` (see its section above); neither engine imports the other | measures relationships between *two or more* series; has no single symbol, so it cannot fit `FeatureSet`'s identity |
| ~~**Alignment service**~~ | **Done** — now `src/fmis/alignment/` ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)) | alignment is a temporal-comparison policy/service, not a model |
| **Composite Feature Layer** | the existing Tier-2 placeholder packages under `features/` | single-instrument; fits the Feature Engine — stays inside it |
| **Market Regime Engine** | new module | consumes facts; must not embed strategy decisions |
| ~~**Provider adapters**~~ | **Built** — `src/fmis/providers/` (Binance public klines); see its section above | transport/provider quirks must never reach the canonical layer ([ADR-0006](adr/ADR-0006-provider-adapter-contract.md)) |
| Strategy / Risk / Portfolio / AI / Execution | separate modules, downstream | see architecture doc §4 — most are Deferred |

Full boundaries, inputs/outputs, and status for every module are in
[ARCHITECTURE_AND_ROADMAP_V1.md §4](ARCHITECTURE_AND_ROADMAP_V1.md).
