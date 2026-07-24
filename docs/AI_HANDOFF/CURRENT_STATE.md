# Current State

**Snapshot document.** This file records the repository as it is **today**. It is the one document that
should be updated at the end of every milestone. If it disagrees with the code, the code is correct —
update this file.

**Last updated for:** Milestone I-D — Documentation Finalization (2026-07-24).
**Latest commit at time of writing:** `5e7e3d5` — `feat(data): enforce canonical UTC timestamps`.

---

## Current milestone

- **I-D — Documentation Finalization** (documentation only; no production code, tests, or
  `pyproject.toml` changes): records the architecture review, the canonical-UTC decision, and the accepted
  R2/R3 decisions, and designs the Relative Value Engine.
  Deliverables: [../ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md),
  [../adr/ADR-0001-canonical-utc-timestamps.md](../adr/ADR-0001-canonical-utc-timestamps.md),
  [../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md](../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md),
  [../adr/ADR-0003-availability-time-boundary.md](../adr/ADR-0003-availability-time-boundary.md),
  [../RVE_DESIGN_V1.md](../RVE_DESIGN_V1.md).

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

(Earlier commits cover the initial audit and documentation of the pre-code repository state.)

## Test count

**218 passing** (`uv run pytest`, ~0.07 s). Per module:

| Module | Tests |
|---|---|
| `tests/test_data_models.py` | 50 |
| `tests/test_observation.py` | 39 |
| `tests/test_ema.py` | 27 |
| `tests/test_macd.py` | 24 |
| `tests/test_rsi.py` | 22 |
| `tests/test_alignment.py` | 22 |
| `tests/test_atr.py` | 15 |
| `tests/test_features_architecture.py` | 12 |
| `tests/test_ema_math.py` | 5 |
| `tests/test_smoke.py` | 2 |
| **Total** | **218** |

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
  *canonical series alignment* (multi-series, strict intersection). The two are **not yet connected** —
  see review finding R1.
- **Canonical models:** `Candle`, `CandleSeries`, `ObservationSeries` (`src/fmis/data/`).
- **Canonical time contract:** every canonical model timestamp must use a *permanent* zero-offset
  timezone; validated, never converted ([ADR-0001](../adr/ADR-0001-canonical-utc-timestamps.md)).
- **Alignment:** `align_intersection` — strict timestamp intersection only, with an immutable
  `AlignmentResult` / `AlignmentReport` / `SeriesAlignmentStats`. No interpolation, forward-fill,
  resampling, or timezone conversion anywhere.
- **Feature Engine:** `FeatureEngine` orchestration; registry-based discovery; topological dependency
  ordering; closed-candle enforcement; immutable `FeatureResult`/`FeatureSet`.
- **Dependency graph:** clean, acyclic, one-directional; `fmis.data` imports nothing from outside
  `fmis.data`; shared kernels (`sources.py`, `ema_math.py`, `_timeutils.py`) import nothing internal.
- **Zero runtime dependencies.**

## Existing modules

```
src/fmis/
├── __init__.py                     package metadata (__version__)
├── data/
│   ├── _timeutils.py               validate_utc_timestamp — canonical time contract (private)
│   ├── models.py                   Candle, CandleSeries
│   ├── observation.py              ObservationSeries (non-OHLC numeric series)
│   └── alignment.py                align_intersection, AlignmentResult/Report, SeriesAlignmentStats
└── features/
    ├── types.py                    FeatureValue, FeatureCategory, regime enums,
    │                               FeatureResult, FeatureContext, FeatureSet,
    │                               Feature (Protocol), BaseFeature
    ├── registry.py                 FeatureRegistry
    ├── feature_engine/engine.py    FeatureEngine
    └── indicators/                 ema, atr, rsi, macd + sources, ema_math
```

## Placeholder modules (no calculation code)

Under `src/fmis/features/`: `trend/`, `momentum/`, `volatility/`, `volume/`, `market_structure/`,
`support_resistance/`, `pattern_detection/` — each is a docstring + planned-features `TODO` list +
`__all__ = []`. These are the intended homes for the **Planned** Composite Feature Layer.

## Known open items from the architecture review

Full detail in [../ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md).

| # | Item | Status / action |
|---|---|---|
| **R1** | No `CandleSeries → ObservationSeries` reduction — the candle and observation pipelines are disconnected | **Blocks Milestone J.** Implement in Milestone I-E |
| **R2** | Alignment lives in `fmis.data`; decision D4 places it in a separate module | **Decided** — move to `fmis.alignment` ([ADR-0002](../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)); code move is Milestone I-E |
| **R3** | No knowledge/availability-time dimension, so the documented look-ahead guarantee is not currently provided | **Decided** — macro/vintage data gated until an availability-time model is designed and accepted ([ADR-0003](../adr/ADR-0003-availability-time-boundary.md)); that model is a required precursor milestone |
| R5 | Features return only the latest value → backtesting would be O(N²) | No action now; the additive `compute_series()` path is the recorded intent, to be addressed before serious backtesting performance work |
| R11 | The `float` numeric choice was scoped to market data only | Money/portfolio/risk types require their **own ADR** before those modules are built — not inherited by default |
| — | Mixed-calendar (7-day vs 5-day) alignment test missing from Milestone I acceptance | Add in Milestone I-E; writable today |
| R9 | `alignment.py` module docstring describes a timezone policy the UTC contract made unreachable | Correct in Milestone I-E |

## Immediate next milestone

**Milestone I-E — Observation Reduction & Alignment Boundary** (Planned; implementation under a separate
prompt — **not** authorized yet). Scope, per [ADR-0002](../adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)
and review findings R1/R9:
- create the dedicated `fmis.alignment` package boundary and move the strict-intersection implementation
  into it (public path becomes `fmis.alignment.align_intersection`); update imports and tests;
- add a pure `CandleSeries → ObservationSeries` reduction helper in `src/fmis/data/`, with explicit
  supported price-field selection and a deterministic `series_id`;
- add the missing mixed-calendar alignment test (crypto 7-day vs equity 5-day; dropped observations
  counted, never absorbed);
- correct the stale `alignment.py` module docstring (R9).
- **No** relative-value mathematics, **no** forward-fill, **no** providers, **no** persistence.

**Then Milestone J — RVE v1a** (indexed performance, simple ratio, log ratio), designed in full in
[../RVE_DESIGN_V1.md](../RVE_DESIGN_V1.md). Blocked on Milestone I-E.

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

**Planned / near-term:** I-E (alignment boundary + candle→observation reduction) → J/K/L (Relative Value Engine v1: indexed
performance & ratio → relative returns & rolling correlation → z-score & relative momentum) → M
(Composite Feature foundation) → N (Market Regime foundation).

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
