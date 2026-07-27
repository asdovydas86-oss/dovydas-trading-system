# Start Here — For AI Coding Agents

You are working in **FMITS** (Financial Market Intelligence & Trading System). Read this document fully
before modifying anything. It encodes the non-negotiable engineering rules of this repository. If a task
instruction ever conflicts with a safety/scope rule here, stop and surface the conflict rather than
guessing.

---

## What FMITS is

A modular, AI-assisted market decision-support system built as a deterministic pipeline:

```
Data → deterministic calculations → structured features → AI interpretation → decision support
```

It is **not** a signal bot and **not** an automated trading system. `WAIT` and `NO TRADE` are valid
outcomes. Capital preservation and testability outrank impressive output. Long-term investing and
short-term trading are separate domains.

---

## What has already been implemented (as of this document)

- **Canonical data models:** `Candle`, `CandleSeries` (frozen, validated, closed-candle aware) and
  `ObservationSeries` (non-OHLC timestamped numeric series).
- **Canonical time contract:** every canonical timestamp must use a *permanent* zero-offset timezone —
  validated, never converted. Read [../adr/ADR-0001-canonical-utc-timestamps.md](../adr/ADR-0001-canonical-utc-timestamps.md)
  before touching anything that handles a timestamp.
- **Observation reduction:** `candle_series_to_observations(series, field, *, series_id=None)` +
  `CandleField` enum (`fmis.data`) — a pure, closed-candles-only bridge from a candle field to an
  `ObservationSeries`. The field is **required** (no default); pass a `CandleField`, never a raw string.
- **Alignment (`fmis.alignment`):** `align_intersection` — **strict timestamp intersection only**, with an
  immutable `AlignmentReport`. It is a **policy layer, separate from `fmis.data`** (ADR-0002). No
  interpolation, forward-fill, resampling, or timezone conversion exists anywhere, and none may be added
  without an explicit, named, documented policy (a new module in `fmis.alignment`, never in `fmis.data`).
- **Deterministic Feature Engine:** `FeatureEngine`, `FeatureRegistry`, `FeatureResult`,
  `FeatureContext`, `FeatureSet`, `Feature` protocol, `BaseFeature`.
- **Tier-1 indicators:** EMA, ATR, RSI, MACD, plus shared kernels `sources.py` (OHLC vocabulary) and
  `ema_math.py` (EMA math).
- **Tier-2 packages** (`trend`, `momentum`, `volatility`, `volume`, `market_structure`,
  `support_resistance`, `pattern_detection`): **placeholders only — no calculation code.**
- **Relative Value Engine (`fmis.relative_value`, v1a):** five scalar, fact-only metrics —
  `period_return`, `relative_return`, `realized_volatility`, `volatility_ratio`, `pearson_correlation` —
  over **simple** returns, **unannualized**, no rolling windows. Returns a `RelativeValueResult`
  (OK/UNDEFINED + reason + provenance). Consumes `ObservationSeries`; **requires inputs already aligned**
  and never aligns itself. Rules in [../adr/ADR-0004-rve-v1a-return-and-result-policy.md](../adr/ADR-0004-rve-v1a-return-and-result-policy.md).
  It must **not** import `fmis.features` and must **not** call `fmis.alignment`.
- **Tests:** 315 passing.

For the precise, always-current snapshot (test count, latest commit, next milestone) read
[CURRENT_STATE.md](CURRENT_STATE.md). Do not trust your memory of these numbers — read the file.

Everything not listed above is **Planned** or **Deferred**. Never write code that assumes an unbuilt
module exists.

---

## Authoritative documents

- **Architecture & boundaries:** [../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md)
  — authoritative for module boundaries, dependency direction, the Relative Value Engine spec, the
  roadmap, and the decision records (D1–D11).
- **Architecture review:** [../ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md)
  — amends the above where code and document diverged (§5). Read its findings **R1–R14** before starting
  any new milestone; two of them (R1, R2) block the Relative Value Engine.
- **Decisions:** [../adr/](../adr/README.md) — one decision per file, with the alternatives that were
  rejected and why.
- **Vision & principles:** [../../PROJECT_SPECIFICATION_V1.md](../../PROJECT_SPECIFICATION_V1.md) and
  [../../PROJECT_VISION_ADDENDUM_V1.md](../../PROJECT_VISION_ADDENDUM_V1.md).
- **Current snapshot:** [CURRENT_STATE.md](CURRENT_STATE.md).
- **Directory rules:** [../REPOSITORY_MAP.md](../REPOSITORY_MAP.md).

If two documents ever disagree, the architecture document wins on architecture; the vision specs win on
principles; and if the *code* disagrees with a doc about current state, the code is the truth — fix the
doc (see "Review-first workflow").

---

## Always read before modifying code

1. [CURRENT_STATE.md](CURRENT_STATE.md) — what exists and what the next milestone is.
2. [../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) — the boundary you must stay
   inside.
3. [../REPOSITORY_MAP.md](../REPOSITORY_MAP.md) — allowed/forbidden dependencies for the directory you
   are touching.
4. The nearest existing sibling. New indicator? Read `ema.py`/`atr.py`/`rsi.py`/`macd.py` and their
   tests first, and match their structure.

---

## The most important engineering rules

### Deterministic calculations
- If a value can be computed objectively, **code computes it** — never AI, never a visual guess.
- **Closed candles only.** Operate on `series.closed()`; a forming bar must never change an output.
- **Explicit warm-up.** Derive the exact minimum observation count; below it return an explicit
  insufficient-data state (`value=None` + metadata), never a guessed number.
- **Reproducible & pure.** No wall-clock, no randomness, no ambient state. Same input → same output.
- **Immutable results.** Results are frozen; metadata (and any structured value) is a read-only,
  defensively-copied mapping.
- **Provenance.** Record parameters, observation counts, and the producing module in metadata.
- **No hidden signals.** A low-level feature returns a number or a small structured fact — never
  "bullish", a score, or a trade.

### AI interpretation
- The AI layer is **Planned**, not built. When it exists, it will *interpret* deterministic facts —
  conflicts, scenarios, the strongest opposing case, uncertainty. It will **never** compute what code
  can compute, and **never** override a deterministic fact. Its outputs are non-deterministic and are
  therefore not stored as `FeatureResult`s.
- Until then: do not put interpretation, directional labels, or scoring anywhere in the deterministic
  layers.

### Dependency direction
- **Dependencies point toward the deterministic core; nothing depends on a later pipeline stage.**
- `fmis.data` is the kernel and imports nothing internal — keep it that way.
- The Feature Engine must never import a concrete feature (discovery is via the registry); indicators
  must never import sibling indicators (use the shared kernels); nothing deterministic may import AI,
  strategy, or execution code; provider/TradingView types must never become canonical models.
- Full permitted/forbidden lists: architecture doc §5.

### Testing
- Verify against **independently derived** expected values (hand calculations, arithmetic means, exact
  `fractions`) — **never** by calling the implementation under test.
- Test warm-up boundaries on **both** sides (exactly-enough vs one-short).
- The full suite must be green before and after your change.

### Small milestones
- Do one small thing per milestone: one implementation → audit → commit → push cycle. Do not bundle
  unrelated changes. Do not refactor opportunistically outside the stated scope.
- Respect the stated development order: research → explicit rules → tests → backtesting → robustness →
  paper trading → shadow mode → controlled live testing. Live execution is **not** a near-term priority.

### Review-first workflow
- Inspect before you write; verify claims against the live repository rather than assuming.
- After a change: run the full suite, run `git diff --check`, and reconcile documentation with reality
  (update [CURRENT_STATE.md](CURRENT_STATE.md) when the state changes).
- Do not stage, commit, or push unless the task explicitly asks for it. When it does, stage only the
  intended files and use a precise commit message.

---

## What must never be violated

1. Never break the dependency direction (no upward/downstream imports; kernel stays import-free).
2. Never put a signal, score, directional label, threshold-as-decision, or cross-asset logic inside the
   Feature Engine.
3. Never let a provider-specific type become a canonical domain model.
4. Never introduce look-ahead bias or silently forward-fill data (critical for the Planned Relative
   Value Engine).
5. Never derive test expectations from the code under test.
6. Never document a Planned/Deferred module as if it exists.
7. Never add a runtime dependency or plan premature databases, APIs, ML, graph analysis, or live
   execution.
8. Never modify production code, tests, or `pyproject.toml` during a documentation-only milestone.

When in doubt, prefer the smaller, more reversible, better-tested change — and ask.
