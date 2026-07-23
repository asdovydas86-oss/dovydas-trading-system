# Current State

**Snapshot document.** This file records the repository as it is **today**. It is the one document that
should be updated at the end of every milestone. If it disagrees with the code, the code is correct —
update this file.

**Last updated for:** Milestone H.5 (documentation foundation).
**Latest commit at time of writing:** `2fbe662` — `docs(architecture): define FMITS architecture and development roadmap`.

---

## Current milestone

- **H.5 — Documentation Foundation** (in progress): adding the permanent documentation set
  (`docs/README.md`, `docs/REPOSITORY_MAP.md`, `docs/AI_HANDOFF/START_HERE_FOR_AI.md`, this file).
  Documentation only — no production code, tests, or `pyproject.toml` changes.

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

(Earlier commits cover the initial audit and documentation of the pre-code repository state.)

## Test count

**147 passing** (`uv run pytest`). Per module:

| Module | Tests |
|---|---|
| `tests/test_data_models.py` | 40 |
| `tests/test_ema.py` | 27 |
| `tests/test_macd.py` | 24 |
| `tests/test_rsi.py` | 22 |
| `tests/test_atr.py` | 15 |
| `tests/test_features_architecture.py` | 12 |
| `tests/test_ema_math.py` | 5 |
| `tests/test_smoke.py` | 2 |
| **Total** | **147** |

## Implemented indicators (Tier-1)

| Indicator | Class | Warm-up (closed candles) | Value |
|---|---|---|---|
| EMA | `ExponentialMovingAverage` | `period` | scalar float |
| ATR | `AverageTrueRange` | `period + 1` | scalar float |
| RSI | `RelativeStrengthIndex` | `period + 1` | scalar float |
| MACD | `MovingAverageConvergenceDivergence` | `slow + signal − 1` (34 for 12/26/9) | immutable mapping `{macd_line, signal_line, histogram}` |

All: closed-candles-only, deterministic, no third-party TA library, explicit insufficient-data state,
provenance in metadata.

## Implemented architecture

- **Pipeline stage present:** *deterministic calculations* (single-instrument, single-timeframe).
- **Canonical models:** `Candle`, `CandleSeries` (`src/fmis/data/`).
- **Feature Engine:** `FeatureEngine` orchestration; registry-based discovery; topological dependency
  ordering; closed-candle enforcement; immutable `FeatureResult`/`FeatureSet`.
- **Dependency graph:** clean, acyclic, one-directional; `fmis.data` imports nothing internal; shared
  kernels (`sources.py`, `ema_math.py`) import nothing.
- **Zero runtime dependencies.**

## Existing modules

```
src/fmis/
├── __init__.py                     package metadata (__version__)
├── data/                           Candle, CandleSeries
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

## Immediate next milestone

**Milestone I — canonical `ObservationSeries` + strict-intersection alignment foundation** (Planned).
- Add an immutable non-OHLC `ObservationSeries` *additively* in `src/fmis/data/`, plus a
  `CandleSeries → ObservationSeries` helper.
- Add a separate alignment service (e.g. `src/fmis/alignment/`) implementing **strict timestamp
  intersection only**, plus an immutable `AlignmentReport` (retained observations, alignment loss,
  missing count, staleness).
- **No** relative-value mathematics, **no** forward-fill, **no** providers, **no** persistence, and no
  change to existing `Candle`/`CandleSeries` behaviour or to `fmis.features`.
- Rationale and acceptance criteria: architecture doc §10 (Milestone I) and §14.

## Current branch expectations

- Work on `main` (single-developer flow to date).
- Each milestone is one implementation → audit → commit → push cycle; the working tree is expected to be
  clean between milestones and `main` in sync with `origin/main`.

## Repository status

- Working tree clean; `main` in sync with `origin/main` at the last completed (pushed) milestone.
- TradingView MCP workflow is external to the Python package — **zero coupling to `src/`**.

## Latest architecture commit

`2fbe662` — `docs(architecture): define FMITS architecture and development roadmap`
([../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md)).

## Known future roadmap (from the architecture document)

**Planned / near-term:** Milestone I (observation series + alignment) → J/K/L (Relative Value Engine v1:
indexed performance & ratio → relative returns & rolling correlation → z-score & relative momentum) → M
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
