# Current State

**Snapshot document.** This file records the repository as it is **today**. It is the one document that
should be updated at the end of every milestone. If it disagrees with the code, the code is correct —
update this file.

**Last updated for:** Milestone U — Evidence Taxonomy v1 (2026-07-28).
**Latest commit at time of writing:** `50e9a43` — `Merge Volume Foundation v1a`
(the Milestone U commit is created by this milestone; update this line to its hash after commit).

---

## Current milestone

- **U — Evidence Taxonomy v1** (implementation): new `fmis.evidence` package — a shared vocabulary for
  *what evidence is about*. `EvidenceFamily` (ten subject areas), the frozen slotted `EvidenceDescriptor`
  (`family`, `name`, `description`), and an immutable canonically ordered catalog. Definitions only: no
  observation, no value, no score, no behaviour. Contracts fixed in
  [ADR-0011](../adr/ADR-0011-evidence-taxonomy.md).

  **The governing rule: a calculated indicator is not automatically evidence.** A descriptor exists only
  for a concept the system genuinely *classifies* today. An architecture audit found exactly six —
  TREND (`price_vs_ema_fast`, `price_vs_ema_slow`, `ema_fast_vs_ema_slow`) and MOMENTUM (`rsi_zone`,
  `macd_vs_signal`, `macd_histogram`) — and **five families are deliberately empty**: volume and
  volatility are measured but not classified, and the relative-value metrics are restated unchanged, so
  no "relative-value alignment" exists to describe.

  **No combined evidence-type enum was created.** Supporting/conflicting is owned by `EvidenceGroups`,
  neutral/unavailable by `Alignment`, insufficient-data by `OverallState` and feature metadata — three
  existing owners across two different dimensions.

  `decision_support` integration is **deferred**: neither package imports the other, both directions
  test-enforced.

- **Previous:** T — Volume Foundation v1a (`fmis.features.volume`), merged into `main` via `50e9a43`.

## Completed milestones

Reconstructed from git history (`git log --oneline`):

| Milestone (theme) | Commit | Summary |
|---|---|---|
| Environment | `d875344` | uv-managed Python 3.12, reproducible env |
| Data contract (B) | `9465c64` | `Candle` / `CandleSeries` + fixture |
| Feature Engine scaffold (C) | `619dd5c` | deterministic technical Feature Engine architecture |
| EMA + engine (D) | `b745dca` | EMA indicator + minimal FeatureEngine orchestration |
| ATR (E) | `23baea3` | Wilder ATR |
| RSI (F) | `8c01f21` | Wilder RSI + shared OHLC source vocabulary |
| MACD (G) | `e0ba4c1` | MACD + shared `ema_series` helper |
| Architecture (H) | `2fbe662` | architecture & roadmap document |
| Documentation foundation (H.5) | `7aefc8c` | permanent documentation set |
| Observation series (I-A) | `7a5db80` | canonical non-OHLC `ObservationSeries` |
| Alignment (I-B) | `a110427` | strict-intersection alignment + report |
| Canonical UTC (I-C) | `5e7e3d5` | permanent-zero-offset timestamp contract — see [ADR-0001](../adr/ADR-0001-canonical-utc-timestamps.md) |
| Documentation finalization (I-D) | `16ef0dd` | architecture review, ADR-0001/0002/0003, RVE design |
| Observation reduction & alignment boundary (I-E) | `f1a0d58` | `fmis.alignment` package + `candle_series_to_observations` + mixed-calendar test |
| RVE v1a metrics (J v1a) | `6700e92`, reviewed in `23e4bd5`, merged `fb90014` | `fmis.relative_value` — 5 scalar metrics + result model; see [ADR-0004](../adr/ADR-0004-rve-v1a-return-and-result-policy.md) |
| Ingestion boundary (O) | `b2ab82a`, merged `37f0dea` | `fmis.ingest` — strict record → canonical decoding; see [ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md) |
| Binance adapter (P) | `4f7017c`, merged `26f4c0f` | `fmis.providers.binance` — public klines → canonical series; see [ADR-0006](../adr/ADR-0006-provider-adapter-contract.md) |
| Market Analysis Pipeline v1 (Q) | `742e832` + `bfb4edf`, merged `fb57d62` | `fmis.pipeline` — end-to-end orchestration → `AnalysisSnapshot`; see [ADR-0007](../adr/ADR-0007-application-layer-boundary.md) |
| Decision Support Evidence v1 (R) | `8dcd551`, merged `b29d833` | `fmis.decision_support` — snapshot → structured `EvidenceReport`; see [ADR-0008](../adr/ADR-0008-decision-support-evidence-boundary.md) |
| Trading Analysis Context v1 (S) | `0e0cd44`, merged `423ebaa` | `fmis.trading_context` — explicit trading objective + timeframes; see [ADR-0009](../adr/ADR-0009-trading-analysis-context-boundary.md) |
| Volume Foundation v1a (T) | `6f9ecd9`, merged `50e9a43` | `fmis.features.volume` — average + relative volume measurements; see [ADR-0010](../adr/ADR-0010-volume-foundation.md) |
| Evidence Taxonomy v1 (U) | _this commit_ | `fmis.evidence` — evidence families + descriptor catalog; see [ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) |

(Earlier commits cover the initial audit and documentation of the pre-code repository state.)

## Test count

**838 passing** (`uv run pytest`, ~0.32 s). Per module:

| Module | Tests |
|---|---|
| `tests/test_evidence_taxonomy.py` | 69 |
| `tests/test_features_volume.py` | 81 |
| `tests/test_decision_support_evidence.py` | 93 |
| `tests/test_providers_binance.py` | 98 |
| `tests/test_pipeline_market_analysis.py` | 52 |
| `tests/test_ingest_candles.py` | 72 |
| `tests/test_data_models.py` | 50 |
| `tests/test_relative_value_metrics.py` | 49 |
| `tests/test_observation.py` | 39 |
| `tests/test_reduction.py` | 27 |
| `tests/test_ema.py` | 27 |
| `tests/test_macd.py` | 24 |
| `tests/test_alignment.py` | 24 |
| `tests/test_rsi.py` | 22 |
| `tests/test_relative_value_models.py` | 19 |
| `tests/test_atr.py` | 15 |
| `tests/test_features_architecture.py` | 19 |
| `tests/test_ema_math.py` | 5 |
| `tests/test_trading_context.py` | 51 |
| `tests/test_smoke.py` | 2 |
| **Total** | **838** |

## Implemented indicators (Tier-1)

| Indicator | Class | Warm-up (closed candles) | Value |
|---|---|---|---|
| EMA | `ExponentialMovingAverage` | `period` | scalar float |
| ATR | `AverageTrueRange` | `period + 1` | scalar float |
| RSI | `RelativeStrengthIndex` | `period + 1` | scalar float |
| MACD | `MovingAverageConvergenceDivergence` | `slow + signal − 1` (34 for 12/26/9) | immutable mapping `{macd_line, signal_line, histogram}` |

All: closed-candles-only, deterministic, no third-party TA library, explicit insufficient-data state,
provenance in metadata. Each returns **only the latest value**, not the full series (see review finding
R5 — relevant to future backtesting).

## Implemented architecture

- **Pipeline stages present:** *deterministic calculations* (single-instrument, single-timeframe) and
  *canonical series alignment* (multi-series, strict intersection), **now connected** by the
  `candle_series_to_observations` reduction (a candle field → `ObservationSeries`).
- **Canonical models:** `Candle`, `CandleSeries`, `ObservationSeries` (`src/fmis/data/`).
- **Trading context (`fmis.trading_context`):** `TradingObjective` (SWING_TRADE, DAY_TRADE) +
  `TradingAnalysisContext` — descriptive value objects, no behaviour, importing nothing from `fmis`.
  **Long-term investing is not a trading objective** and gets its own future module. No
  objective-dependent branching, no timeframe inference or presets, no strategy/risk/direction fields
  ([ADR-0009](../adr/ADR-0009-trading-analysis-context-boundary.md)).
- **Evidence taxonomy (`fmis.evidence`):** `EvidenceFamily` + `EvidenceDescriptor` + an immutable
  catalog of the six concepts the system genuinely classifies today. Definitions only — no value, score,
  direction, or availability state; supporting/conflicting and availability are **not** redefined.
  Imports nothing from `fmis`; not wired to `decision_support` in either direction
  ([ADR-0011](../adr/ADR-0011-evidence-taxonomy.md)).
- **Decision support (`fmis.decision_support`):** `build_evidence_report` — turns a snapshot into
  structured evidence: explicit classifications, supporting/conflicting/unavailable grouping, mechanical
  scenario conditions, and an undirectional `OverallState`. Consumes snapshots only; classifies rather
  than calculates (one isolated derived value); no trading vocabulary anywhere, test-enforced
  ([ADR-0008](../adr/ADR-0008-decision-support-evidence-boundary.md)).
- **Application layer (`fmis.pipeline`):** `analyze_symbol` — the end-to-end workflow. Closed candles
  unconditionally (`DataWindow` reports fetched/closed/excluded); warm-up is a result, insufficient data
  raises `InsufficientDataError`; a failed benchmark fails the whole call; downstream errors propagate
  unwrapped. Orchestration only — no formula is defined there
  ([ADR-0007](../adr/ADR-0007-application-layer-boundary.md)).
- **Provider adapter (`fmis.providers.binance`):** `fetch_klines` — public Binance spot klines, no API
  key, `urllib` only. Parses provider string prices, maps to `CANDLE_FIELDS`, decodes via `fmis.ingest`.
  Injected transport and clock; explicit `BinanceError` hierarchy; a provider error never becomes an
  empty series; forming candles are flagged (not dropped) via the clock
  ([ADR-0006](../adr/ADR-0006-provider-adapter-contract.md)).
- **Ingestion boundary (`fmis.ingest`, v1):** `decode_candle` / `decode_candle_series` /
  `decode_candle_series_from_json` turn untrusted records into canonical candles. Strict: no coercion,
  repair, sorting, dedup, or filtering; missing **and** unexpected fields raise; errors carry the record
  index. Domain invariants stay in `Candle`/`CandleSeries`. A decoder, **not** a provider adapter — no
  transport, network, or credentials ([ADR-0005](../adr/ADR-0005-ingestion-boundary-strictness.md)).
- **Canonical time contract:** every canonical model timestamp must use a *permanent* zero-offset
  timezone; validated, never converted ([ADR-0001](../adr/ADR-0001-canonical-utc-timestamps.md)).
- **Observation reduction:** `candle_series_to_observations(series, field, *, series_id=None)` +
  `CandleField` enum — pure, closed-candles-only, explicit field (no default), no policy.
- **Alignment (policy layer, `fmis.alignment`):** `align_intersection` — strict timestamp intersection
  only, with an immutable `AlignmentResult` / `AlignmentReport` / `SeriesAlignmentStats`. No interpolation,
  forward-fill, resampling, or timezone conversion anywhere. Separate from `fmis.data`
  ([ADR-0002](../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)).
- **Relative Value Engine (`fmis.relative_value`, v1a):** five scalar, deterministic, fact-only metrics —
  `period_return`, `relative_return`, `realized_volatility`, `volatility_ratio`, `pearson_correlation` —
  over **simple** returns, **unannualized**, no rolling windows. Each returns a `RelativeValueResult`
  (`status` OK/UNDEFINED + `reason` + immutable provenance metadata). Consumes `ObservationSeries` only;
  requires inputs already aligned (never aligns itself). Contracts:
  [ADR-0004](../adr/ADR-0004-rve-v1a-return-and-result-policy.md).
- **Volume measurements (`fmis.features.volume`, v1a):** `AverageVolume` and `RelativeVolume` —
  `relative_volume = current_volume / average_volume`, where the baseline is the `lookback` candles
  **preceding** the latest one (warm-up `lookback + 1`, default lookback 20). Zero baseline is undefined,
  never infinity. Measurements only — no labels or thresholds. **Shared calculation does not mean
  identical interpretation across markets** ([ADR-0010](../adr/ADR-0010-volume-foundation.md)).
- **Feature Engine:** `FeatureEngine` orchestration; registry-based discovery; topological dependency
  ordering; closed-candle enforcement; immutable `FeatureResult`/`FeatureSet`.
- **Dependency graph:** clean, acyclic, one-directional; `fmis.data` imports nothing from outside
  `fmis.data` (and no longer re-exports alignment, so `fmis.features` no longer pulls it in transitively —
  review finding R12); `fmis.alignment` imports only `fmis.data`; `fmis.relative_value` imports only
  `fmis.data` (never `fmis.features`, never `fmis.alignment`); `fmis.ingest` imports only `fmis.data`
  (never anything downstream, and never the private `_timeutils`); `fmis.providers` imports only
  `fmis.ingest` + `fmis.data` and never constructs `Candle` directly; `fmis.pipeline` sits on top and
  **no engine imports it**; `fmis.decision_support` sits above the pipeline and **nothing below imports
  it**, the pipeline included; `fmis.trading_context` and `fmis.evidence` are leaves importing nothing from
  `fmis`, and no other package references either (all test-enforced); shared kernels (`sources.py`,
  `ema_math.py`, `_timeutils.py`) import nothing internal.
- **Zero runtime dependencies.**

## Existing modules

```
src/fmis/
├── __init__.py                     package metadata (__version__)
├── data/
│   ├── _timeutils.py               validate_utc_timestamp — canonical time contract (private)
│   ├── models.py                   Candle, CandleSeries
│   ├── observation.py              ObservationSeries (non-OHLC numeric series)
│   └── reduction.py                CandleField, candle_series_to_observations
├── alignment/
│   ├── __init__.py                 policy-layer surface (re-exports intersection)
│   └── intersection.py             align_intersection, AlignmentResult/Report, SeriesAlignmentStats
├── evidence/
│   ├── __init__.py                 taxonomy rules + public surface
│   ├── families.py                 EvidenceFamily
│   ├── descriptor.py               EvidenceDescriptor
│   └── catalog.py                  descriptors(), descriptors_for(), find()
├── trading_context/
│   ├── __init__.py                 layer rules + public surface
│   └── context.py                  TradingObjective, TradingAnalysisContext
├── decision_support/
│   ├── __init__.py                 layer rules + public surface
│   ├── classification.py           classify_comparison/rsi_zone/sign, Alignment
│   ├── derived.py                  atr_percent_of_close (the only calculation)
│   └── report.py                   build_evidence_report + EvidenceReport types
├── pipeline/
│   ├── __init__.py                 application-layer rules + public surface
│   └── market_analysis.py          analyze_symbol, AnalysisSnapshot, DataWindow,
│                                   RelativeValueSection, default_features
├── providers/
│   ├── __init__.py                 adapter-layer rules (no re-exports)
│   └── binance.py                  fetch_klines, map_kline, build_klines_url,
│                                   urlopen_transport, BinanceError hierarchy
├── ingest/
│   ├── __init__.py                 public surface (decoders + error hierarchy)
│   └── candles.py                  decode_candle, decode_candle_series,
│                                   decode_candle_series_from_json, CANDLE_FIELDS
├── relative_value/
│   ├── __init__.py                 public surface (5 metrics + result model)
│   ├── models.py                   RelativeValueResult, MetricStatus, UndefinedReason, errors
│   └── metrics.py                  period_return, relative_return, realized_volatility,
│                                   volatility_ratio, pearson_correlation
└── features/
    ├── types.py                    FeatureValue, FeatureCategory, regime enums,
    │                               FeatureResult, FeatureContext, FeatureSet,
    │                               Feature (Protocol), BaseFeature
    ├── registry.py                 FeatureRegistry
    ├── feature_engine/engine.py    FeatureEngine
    └── indicators/                 ema, atr, rsi, macd + sources, ema_math
```

## Placeholder modules (no calculation code)

Under `src/fmis/features/`: `trend/`, `momentum/`, `volatility/`, `market_structure/`,
`support_resistance/`, `pattern_detection/` — each is a docstring + planned-features `TODO` list +
`__all__ = []`. These are the intended homes for the **Planned** Composite Feature Layer.

`volume/` is **no longer a placeholder**: it holds the deterministic volume measurements added in
Milestone T ([ADR-0010](../adr/ADR-0010-volume-foundation.md)).

## Known open items from the architecture review

Full detail in [../ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md).

| # | Item | Status / action |
|---|---|---|
| **R1** | `CandleSeries → ObservationSeries` reduction | **Done (I-E)** — `candle_series_to_observations` connects the two pipelines |
| **R2** | Alignment was inside `fmis.data`; D4 places it in a separate module | **Done (I-E)** — moved to `fmis.alignment` ([ADR-0002](../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)) |
| R9 | Stale `alignment.py` timezone docstring | **Done (I-E)** — rewritten for the canonical-UTC contract |
| R12 | `fmis.features` transitively imported alignment via `fmis.data` | **Done (I-E)** — resolved by removing the `fmis.data` re-export |
| — | Mixed-calendar (7-day vs 5-day) alignment test | **Done (I-E)** — `tests/test_alignment.py` |
| **R3** | No knowledge/availability-time dimension, so the documented look-ahead guarantee is not currently provided | **Decided (deferred)** — macro/vintage data gated until an availability-time model is designed and accepted ([ADR-0003](../adr/ADR-0003-availability-time-boundary.md)); that model is a required precursor milestone |
| R5 | Features return only the latest value → backtesting would be O(N²) | No action now; the additive `compute_series()` path is the recorded intent, to be addressed before serious backtesting performance work |
| R11 | The `float` numeric choice was scoped to market data only | Money/portfolio/risk types require their **own ADR** before those modules are built — not inherited by default |

## Immediate next milestone

Not yet chosen. Natural follow-ons:

- **Evidence taxonomy integration** — decide how a `decision_support.Observation` refers to an
  `EvidenceDescriptor`. Deliberately deferred from Milestone U; it is a real design question
  ([ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) §8).
- **Volume Evidence v1b** — classify relative volume, which would earn the VOLUME family its first
  descriptor. The hard part remains that a ratio means different things per market
  ([ADR-0010](../adr/ADR-0010-volume-foundation.md) §6).
- **Trading reasoning v1** — the first consumer of `TradingAnalysisContext`, taking it with an
  `EvidenceReport`.
- **A thin CLI / entry point** (§2.9(8)) — still the last structural gap.

**Known follow-ups from Milestone U** (each small, none blocking): nothing consumes the taxonomy yet;
`EvidenceFamily` overlaps `FeatureCategory` on five names by design (different axes — see
[ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) §2) and both must be kept distinct.

**Required precursor milestone (not near-term):** an **availability-time model** must be designed and
accepted before any macroeconomic, fundamental-release, revised, or vintage-data backtesting
([ADR-0003](../adr/ADR-0003-availability-time-boundary.md)).

## Current branch expectations

- Work on `main` (single-developer flow to date).
- Each milestone is one implementation → audit → commit → push cycle; the working tree is expected to be
  clean between milestones and `main` in sync with `origin/main`.

## Repository status

- Working tree clean; `main` in sync with `origin/main` at the last completed (pushed) milestone.
- TradingView MCP workflow is external to the Python package — **zero coupling to `src/`**.

## Latest architecture commit

`2fbe662` — `docs(architecture): define FMITS architecture and development roadmap`
([../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md)), as amended by the review record
[../ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md) §5.

## Known future roadmap (from the architecture document)

**Planned / near-term:** J v1b (deferred RVE metrics — ratio/spread/beta, then rolling/annualized, each
gated per [ADR-0004](../adr/ADR-0004-rve-v1a-return-and-result-policy.md) §5) → M (Composite Feature
foundation) → N (Market Regime foundation). *Note: the architecture doc's original J/K/L split
(indexed/ratio → correlation → z-score) is superseded by the v1a/v1b scoping in ADR-0004.*

**Deferred:** provider adapters (incl. TradingView ingestion), macro/news/on-chain/derivatives
intelligence, ETF-flow / insider / China / IPO engines, Daily Brief & Opportunity Scanner, persistence,
APIs, dashboards, paper trading, shadow mode, execution, ML, graph/network analysis, cointegration,
causal inference.

See [../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) §10–§11 for full detail.

---

### How to update this file
After a milestone that changes repository state: update *Current milestone*, add the row to *Completed
milestones*, refresh the *Test count* table, adjust *Implemented indicators/architecture/modules*, set
the new *Immediate next milestone*, and update *Latest architecture commit* / *Repository status*.
