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
├── tests/                  pytest suite (247 tests) + fixtures
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
  - `trend/`, `momentum/`, `volatility/`, `volume/`, `market_structure/`, `support_resistance/`,
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

- **Purpose:** the correctness contract. **247 tests** across 11 modules, plus `tests/fixtures/` (a small
  committed OHLCV dataset).
- **Responsibilities:** verify every deterministic calculation against independently derived expected
  values; test warm-up boundaries on both sides; test immutability and validation.
- **Allowed dependencies:** `pytest` (the only dev dependency), the `fmis` package, standard library.
- **Forbidden dependencies:** network access; nondeterministic inputs; deriving expected values by
  calling the implementation under test.

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
| **Relative Value Engine** | `src/fmis/relative_value/` — a top-level sibling of `data` and `features`; **neither engine imports the other** (design: [RVE_DESIGN_V1.md](RVE_DESIGN_V1.md)) | measures relationships between *two or more* series; has no single symbol, so it cannot fit `FeatureSet`'s identity |
| ~~**Alignment service**~~ | **Done** — now `src/fmis/alignment/` ([ADR-0002](adr/ADR-0002-alignment-as-temporal-comparison-policy-layer.md)) | alignment is a temporal-comparison policy/service, not a model |
| **Composite Feature Layer** | the existing Tier-2 placeholder packages under `features/` | single-instrument; fits the Feature Engine — stays inside it |
| **Market Regime Engine** | new module | consumes facts; must not embed strategy decisions |
| Strategy / Risk / Portfolio / AI / Execution | separate modules, downstream | see architecture doc §4 — most are Deferred |

Full boundaries, inputs/outputs, and status for every module are in
[ARCHITECTURE_AND_ROADMAP_V1.md §4](ARCHITECTURE_AND_ROADMAP_V1.md).
