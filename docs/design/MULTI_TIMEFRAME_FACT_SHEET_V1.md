# Multi-Timeframe Fact Sheet v1 — Design

**Milestone:** AG
**Status:** Implemented by [ADR-0023](../adr/ADR-0023-multi-timeframe-composition.md)
**Date:** 2026-08-02
**Executes:** `reports/0006` §5 — the implementation contract, followed without redesign

---

## 1. The problem, measured

Milestone AF delivered a deterministic fact sheet for one instrument on **one timeframe**. The
architecture gate that followed measured what that costs, live on BTCUSDT:

| Timeframe | Structural trend | `as_of` |
|---|---|---|
| 1W | `sustained_higher` | 2026-07-20 |
| 1D | `neutral` | 2026-08-01 |
| 4H | `sustained_lower` | 2026-08-02 |

`fmits facts BTCUSDT` returns the 4H row alone. `PROJECT_SPECIFICATION_V1.md` §5 names this exact
combination and states that it *"is different from simply calling the asset bullish"*, and requires
the system to "avoid mixing timeframe signals without explaining their role".

So the gap is not a missing convenience. A single-timeframe sheet can lead a reader to the conclusion
the specification exists to prevent.

## 2. Scope

**In:** a composition root over N role-labelled timeframes · an immutable result · role mapping · a
renderer · a CLI command · tests · this design · an ADR · an independent review.

**Out, and asserted:** regime · alignment or agreement of any kind · signals · portfolio · risk · AI ·
news · scanner · persistence · scheduling · watchlists · database · strategy engine.

The milestone adds **no engine**. Its value comes entirely from composing what AF already built.

## 3. Design

### 3.1 Placement

`fmis.pipeline.multi_timeframe` — a third module in the existing application layer, beside
`market_analysis` and `structural_facts`. ADR-0007 §1 already fixes that boundary, so no new
architectural decision was required.

```
multi_timeframe_facts_for_symbol(symbol, timeframes={CONTEXT: "1w", SETUP: "1d", EXECUTION: "4h"})
        │  network edge — the only I/O
        │  one DetectionSettings, one feature set, reused for every view
        ▼
   structural_facts_for_symbol(symbol, "1w", …)   ─┐
   structural_facts_for_symbol(symbol, "1d", …)   ─┤ → three StructuralFactSheets
   structural_facts_for_symbol(symbol, "4h", …)   ─┘
        │
        ▼
build_multi_timeframe_facts(views)   pure — no clock, no network
        ▼
   MultiTimeframeFactSheet
```

Every arrow is a delegation. Nothing in this module computes a market quantity.

### 3.2 Models

| Type | Purpose |
|---|---|
| `TimeframeRole` | `CONTEXT` / `SETUP` / `EXECUTION` — `SPEC` §5's framework |
| `TimeframeView` | one role, the requested interval, and that timeframe's sheet |
| `MultiTimeframeFactSheet` | symbol, source, role-ordered views, `newest_as_of`, limitations, metadata |

`MultiTimeframeFactSheet` validates: at least one view · roles unique · views ordered by
`_ROLE_ORDER` · all views share the symbol · metadata copied into a `MappingProxyType`.

### 3.3 The decision that governs the milestone

**Nothing is derived from the combination of views.**

A `TrendAgreement` field (`ALL_EQUAL` / `MIXED`) was considered and rejected. It is deterministic and
cheap. It is also a classification of *market state*, which belongs to the Market Regime Engine — and
emitting it here would put the first interpretation into the application layer, pre-empting a layer
that does not exist.

The renderer prints the three trends beside their roles and one sentence: *"Reported side by side.
Nothing is derived from the combination."*

Enforced by three independent tests: the dataclass field set is asserted exactly; no public attribute
may contain a synthesis word; and the rendered output is scanned for ten synthesis terms outside the
limitations block — plus a fourth test proving the disclaiming limitations are still rendered, so the
exclusion cannot mask their removal.

### 3.4 Roles are stated, never inferred

A caller may map any interval to any role. The default `1w/1d/4h` is a default, not a rule — `SPEC` §5
says so explicitly. This follows ADR-0009's precedent: inferring would silently decide what the caller
is stating.

Role ordering uses an explicit `_ROLE_ORDER` mapping rather than enum definition order, so renaming or
moving a member cannot silently change the layout.

### 3.5 Time is not aligned, and each view says when it was

Views have different `as_of` values by nature — the weekly bar measured **13 days old** live, because
the week had not closed. Each view renders its own timestamp and age.

`fmis.alignment` is not used and a test asserts no import of it. Alignment makes series comparable for
*arithmetic*; nothing here computes across timeframes, and intersection would discard data for no gain.

`newest_as_of` is deliberately not called `as_of` — that would read as a property of the sheet. The
renderer labels it *"not a shared instant"*.

### 3.6 `swing_features()`

`default_features()` plus EMA(200), the swing workflow's headline trend reference.

`default_features()` is **unchanged**, for a measured reason:
`tests/test_pipeline_market_analysis.py:128` asserts every default feature has a value over a
60-candle fixture, and EMA(200) needs 200. Adding it there would force a larger fixture into a 4-second
suite and silently change `analyze_symbol` for every caller. Two named sets with stated purposes are
clearer than one that means "whatever the last milestone needed".

### 3.7 Command registry

`Command` records name, help, argument configuration and runner together; `COMMANDS` is the one tuple
both `build_parser` and `main` read. Introduced at the second command rather than the fourth, because
a hand-written dispatch is where the parser and the runner start disagreeing.

## 4. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | Zero arithmetic operators in the module | AST walk for any arithmetic `BinOp` |
| I2 | No clock | source scan for `datetime.now`, `utcnow`, `time.time`, `time.monotonic` |
| I3 | One `DetectionSettings` reaches every view | AST check **and** a behavioural spy on object identity |
| I4 | Each view delegates wholly to `structural_facts_for_symbol` | composed view is the same object as the direct call |
| I5 | Nothing outside `fmis.pipeline` references it | tree walk over `src/fmis` |
| I6 | A partial failure raises; no sheet escapes | short timeframe → raises, result stays `None` |

I1 required one change: a set difference validating symbols was rewritten as a comprehension, because
set subtraction is `ast.Sub` and an invariant with no exceptions is easier to trust.

## 5. Measured results

> **Measured at implementation, before the independent review.** The review re-ran every measurement
> after fixing two P2 findings, one of which added a test. Where the figures below differ from
> [the review](../reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md) §7, **the review's are current**:
> 3,404 tests (**+99**) and 42 mutation probes.

**Correctness.** 3,403 tests pass, identically under `-W error` (3,305 before AG; **+98**).
Coverage: `multi_timeframe.py` **100 %**, `cli.py` **100 %**, `render.py` **100 %**.
Public exports **154**, **zero collisions**. Import cycles **none**. Runtime dependencies **none**.

**Mutation.** 40 probes across all three touched modules. **40/40 detected, zero survivors, zero
no-ops**, with byte-identical source restoration verified by checksum.

Four probes did not detect on the first pass. **None was an equivalent mutant**:

| Probe | Why it survived | Fix |
|---|---|---|
| empty-views check removed | `build_multi_timeframe_facts` rejects an empty mapping first, so the dataclass guard was unreachable through the public path — but the model is public and directly constructible | A test constructing `MultiTimeframeFactSheet` directly |
| role header removed | Anchor did not match the real source line | Anchor corrected; assertion strengthened to count header lines, not just find substrings |
| MTF absent-label note removed | The identical string exists in AF's `render_fact_sheet`, and `replace(…, 1)` mutated **AF's copy**, which AG's suite correctly does not cover | Anchor extended with the preceding assignment line, making it unique to `_view_block` |
| MTF absent-break note removed | Same cause | Same fix |

The last two are worth recording as a method lesson: **a mutation anchor that is not unique tests a
different function than intended**, and reports a false survivor.

**Performance.** Composition overhead is negligible; cost is the three fetches.

| candles/view | three sheets | composition | overhead share |
|---:|---:|---:|---:|
| 100 | 4.6 ms | 0.005 ms | 0.117 % |
| 200 | 12.5 ms | 0.004 ms | 0.029 % |
| 400 | 37.5 ms | 0.004 ms | 0.011 % |

Live end to end, three views at 260 candles including network: **~1.9 s**.

**Determinism.** Rendered output hashes identically under `PYTHONHASHSEED` 0, 1, 42 and 12345 in fresh
processes.

## 6. Verified live

```
fmits mtf BTCUSDT -n 260
```

returned three role-labelled views from real Binance data, with per-view `as_of` and age, and the
trend summary:

```
── STRUCTURAL TREND BY ROLE ─────────────────────────────────
 context · 1w                  sustained_higher
 setup · 1d                           neutral
 execution · 4h                sustained_lower
 Reported side by side. Nothing is derived from the combination.
```

That is the `SPEC` §5 case, reproduced on live data and reported without a verdict — which is the
milestone's entire product value.

## 7. What it does not claim

Three facts, not one conclusion. The system does not say which timeframe wins, whether they agree, or
what to do. Reconciling them is the Market Regime Engine's job, and the sheet says so on every run.
