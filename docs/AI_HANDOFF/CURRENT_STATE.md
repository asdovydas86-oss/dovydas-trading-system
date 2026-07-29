# Current State

**Snapshot document.** This file records the repository as it is **today**. It is the one document that
should be updated at the end of every milestone. If it disagrees with the code, the code is correct —
update this file.

**Last updated for:** Milestones Z0-Z1 — ordering unification + Structural Sequence State History v1 (2026-07-29).
**Latest commit at time of writing:** `8535a98` — `Merge Market Structure Architecture Review v1`
(the Z0/Z1 commits are created by these milestones).

---

## Current milestone

- **Z0 — Structural Sequence Ordering Unification** (implementation): the sequence-ordering contract had
  two independent implementations (architecture review P2-1). Both now project onto normalised
  `(index, timestamp, type)` keys and delegate to one private core, `models._validate_key_order`, with
  adapters carrying only each layer's message nouns. All ten messages byte-identical, verified by
  differential against both originals over 12,889 generated cases. No public API change.

- **Z1 — Structural Sequence State History Foundation v1** (implementation): `fmis.market_structure`
  gains `StructuralSequenceStateSnapshot` (`state`, `triggers`, plus `index`/`timestamp` as computed
  **projections**) and `derive_structural_sequence_state_history`. Contracts fixed in
  [ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md); design in
  [the design document](../design/STRUCTURAL_SEQUENCE_STATE_HISTORY_DESIGN_V1.md).

  **One snapshot per candle that changed structure**, event-indexed rather than bar-indexed. Outside-bar
  HIGH/LOW pairs apply **atomically**, so no half-applied state is ever emitted.
  `INSUFFICIENT_STRUCTURE` snapshots are recorded, never suppressed.

  **Prefix-stable under candle-series extension and complete structural-group extension** — and
  explicitly **not** under an arbitrary cut inside a same-candle HIGH/LOW group, which cannot arise from
  candle growth and is not detectable. The limitation is tested, not just documented.

  **Recording is not interpreting.** No transition type, no "changed" flag, no direction or magnitude.
  Every classification rule is delegated; the module performs no arithmetic and names no state member.

  Both APIs remain, under a tested equivalence contract:
  `history[-1].state == derive_structural_sequence_state(...)`.

- **Y — Structural Sequence State Foundation v1** (merged `1154622`): `fmis.market_structure` gains
  `StructuralSequenceStateType` (six members), the frozen/slotted/hashable `StructuralSequenceState`
  (`latest_high`, `latest_low`, `state`), and the pure function `derive_structural_sequence_state`.
  Contracts fixed in [ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md).

  **A complete nine-cell matrix**, classified by whether each side moved outward from its own previous
  swing, inward, or not at all: `SHIFTED_HIGHER`, `SHIFTED_LOWER`, `EXPANDED`, `CONTRACTED`, `UNCHANGED`,
  plus `INSUFFICIENT_STRUCTURE` when either side has no labelled swing. The partition is exhaustive and
  disjoint, so there is **no catch-all member**. `ADVANCING_*` and `BALANCED` were rejected as
  interpretive.

  **The grouping is lossy on purpose, so both source facts are retained.** Five states over nine
  combinations cannot distinguish `HIGHER_HIGH` + `LOWER_LOW` from `HIGHER_HIGH` + `EQUAL_LOW`; the two
  `StructuralSwing` objects stay on the result, so a consumer recovers the exact cell.

  **Aggregate state evolves, and that is not repainting.** Swings, comparisons and labels remain
  prefix-stable; the aggregate is by construction a statement about the *latest* pair and is superseded
  when a newer swing is confirmed on either side. Prefix stability is explicitly **not** claimed for it.

  **Outside bars resolve atomically** — the whole run is evaluated and one final state derived, so no
  intermediate half-applied state is exposed. One shared ordering rule
  (`models._validate_current_point_order`) now serves both this layer and labelling. State history is
  postponed ([ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md) §11).

- **X — Structural Swing Label Foundation v1** (merged `b5f8723`): `fmis.market_structure` gained
  `StructuralSwingLabel` (six members), the frozen/slotted/hashable `StructuralSwing`
  (`comparison`, `label`), and the pure functions `label_swing` / `label_swing_sequence`. Contracts fixed
  in [ADR-0014](../adr/ADR-0014-structural-swing-label-foundation.md).

  **One authoritative mapping** of `SwingType` x `SwingRelation`, exhaustive over both enums, kept
  private — a public `label_for(type, relation)` would name a pairing no validated comparison produced.
  The label is derived from `current.type` only; the previous point's type is never consulted, because
  `SwingComparison` already guarantees they match.

  **Naming is not interpreting.** `HIGHER_HIGH` says a high's price is above the previous high and stops
  there — not uptrend, breakout, BOS, CHoCH or a reason to trade, and `LOWER_LOW` is not a short signal.

  **Full names are canonical.** `HH`/`HL`/`LH`/`LL` are prose shorthand only: `LH` and `HL` differ by one
  transposition and mean opposite things, which is a poor property for an identifier used in conditionals.

  **`EQUAL_HIGH` and `EQUAL_LOW` stay first-class** — never folded into HIGHER/LOWER, never renamed
  "double top", "support" or "liquidity". Exact equality is inherited from ADR-0013 §4 unchanged; this
  layer never touches a price.

  Input order is preserved, never sorted; outside-bar comparisons sharing a `current.index` are accepted,
  and the **secondary order at an equal index is inherited from the input, never imposed** — labelling
  does not independently order HIGH before LOW.
  Labels are still **not evidence** — nothing classifies them, so `EvidenceFamily.MARKET_STRUCTURE`
  remains empty.

- **Previous:** W — Swing Relationship Foundation v1 (comparison), merged into `main` via `153f930`.

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
| Evidence Taxonomy v1 (U) | `96bad56`, merged `21a4bb0` | `fmis.evidence` — evidence families + descriptor catalog; see [ADR-0011](../adr/ADR-0011-evidence-taxonomy.md) |
| Evidence namespace hygiene fix | `6e098cf`, merged `352bf45` | `descriptors.py` -> `descriptor.py`; no API or taxonomy change |
| Market Structure Foundation v1 (V) | `b91c3d1`, merged `e7dbbb9` | `fmis.market_structure` — deterministic swing detection; see [ADR-0012](../adr/ADR-0012-market-structure-foundation.md) |
| Swing Relationship Foundation v1 (W) | `90ae358`, merged `153f930` | `SwingRelation`, `SwingComparison`, `compare_swings`, `compare_swing_sequence`; see [ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md) |
| Structural Swing Label Foundation v1 (X) | `5a25f39`, merged `b5f8723` | `StructuralSwingLabel`, `StructuralSwing`, `label_swing`, `label_swing_sequence`; see [ADR-0014](../adr/ADR-0014-structural-swing-label-foundation.md) |
| Structural Sequence State Foundation v1 (Y) | `6047e65`, merged `1154622` | `StructuralSequenceStateType`, `StructuralSequenceState`, `derive_structural_sequence_state`; see [ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md) |

(Earlier commits cover the initial audit and documentation of the pre-code repository state.)

## Test count

**2073 passing** (`uv run pytest`, ~1.4 s). Per module:

| Module | Tests |
|---|---|
| `tests/test_market_structure_sequence_state.py` | 312 |
| `tests/test_market_structure_state_history.py` | 267 |
| `tests/test_market_structure_ordering.py` | 33 |
| `tests/test_market_structure_relationships.py` | 228 |
| `tests/test_market_structure_swings.py` | 194 |
| `tests/test_market_structure_labels.py` | 193 |
| `tests/test_evidence_taxonomy.py` | 77 |
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
| **Total** | **2073** |

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
- **Market structure (`fmis.market_structure`):** `detect_swings` — deterministic, non-repainting swing
  highs and lows over closed candles; plus `compare_swings` / `compare_swing_sequence`, which compare
  each swing against the previous swing **of the same type** into a numeric `SwingRelation`
  (HIGHER/LOWER/EQUAL); and `label_swing` / `label_swing_sequence`, which name the pairing as one of six
  `StructuralSwingLabel` members. Exact price comparison, validated/preserved order, full names canonical,
  EQUAL first-class, and naming that stops short of interpretation
  ([ADR-0013](../adr/ADR-0013-swing-relationship-foundation.md),
  [ADR-0014](../adr/ADR-0014-structural-swing-label-foundation.md)); and
  `derive_structural_sequence_state`, which reads the latest HIGH-side label beside the latest LOW-side
  label as one of five states over a complete nine-cell matrix — or `INSUFFICIENT_STRUCTURE` when a side
  is missing — while retaining both source facts. Its aggregate output is **expected to evolve** as newer
  swings are confirmed, which is not repainting and is the one thing in this package that is not
  prefix-stable ([ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md)). Strict-left / `>=`-right comparison; plateaus collapse to one
  point, separated equal highs stay distinct; insufficient history returns `()`. Located facts only, no
  structural interpretation ([ADR-0012](../adr/ADR-0012-market-structure-foundation.md)).
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
├── market_structure/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   SwingType, SwingPoint, SwingRelation,
│   │                               SwingComparison, StructuralSwingLabel,
│   │                               StructuralSwing, StructuralSequenceStateType,
│   │                               StructuralSequenceState
│   ├── swings.py                   detect_swings, required_candles
│   ├── relationships.py            compare_swings, compare_swing_sequence
│   ├── labels.py                   label_swing, label_swing_sequence
│   └── sequence_state.py           derive_structural_sequence_state
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

Not yet chosen. With named structural facts available, the natural next steps are:

- **Break of structure / change of character** — the first rule *over a sequence* of labels. It needs an
  explicit definition of what counts as a break, including whether an `EQUAL_HIGH` breaks anything, before
  any code ([ADR-0014](../adr/ADR-0014-structural-swing-label-foundation.md) §11).
- **Structural sequence state history** — deliberately postponed from Milestone Y. It needs one decision
  first: whether an outside bar updating both sides at one index emits one transition or two
  ([ADR-0015](../adr/ADR-0015-structural-sequence-state-foundation.md) §11).
- **Trend classification** — how many swings constitute a trend, and what an interleaved
  `HIGHER_HIGH` / `LOWER_LOW` run means. Its own decision record.
- **Support / resistance candidates** — `fmis.features.support_resistance` already names swing points as
  its input, and `EQUAL_HIGH`/`EQUAL_LOW` are the obvious seed.
- **Volume Evidence v1b** — still the deferred half of Milestone T.
- **Trading reasoning v1** — first consumer of `TradingAnalysisContext`.

**Known follow-ups from Milestone Y** (each small, none blocking): the package now has two kinds of
output with different stability guarantees, so any interface built on top must not describe the aggregate
state as non-repainting; and the five states are deliberately coarser than their inputs, so a consumer
needing more detail reads `latest_high.label` / `latest_low.label` rather than growing the enum.

**Known follow-ups from Milestone X** (each small, none blocking): `StructuralSwing` is a thin wrapper, so
a consumer reaching through `swing.comparison.current.price` repeatedly wants a projection rather than
more fields on this type; the exact-equality limitation from ADR-0013 §4 is inherited verbatim, so
`EQUAL_HIGH` fires only for bit-identical stored prices.

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
