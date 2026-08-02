# Structural Fact Sheet v1 — Design

**Milestone:** AF — First Light
**Status:** Implemented by [ADR-0022](../adr/ADR-0022-structural-fact-sheet-composition-root.md)
**Date:** 2026-08-02
**Executes:** `reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md` §11

---

## 1. The problem, measured

The repository holds 11,128 lines of production Python, 3,221 passing tests, 96 % line coverage, zero
circular dependencies and 21 ADRs. Before this milestone it delivered **no user-visible capability at
all**.

Report 0003 established why, from the executable import graph rather than from documentation:

```
Island A — MEASUREMENT      4,862 LOC   43.7 %   has provider, application layer, output
  data · ingest · providers · features · alignment · relative_value · pipeline · decision_support

Island B — STRUCTURE        5,695 LOC   51.2 %   no provider path, no application layer, no consumer
  market_structure · structural_trend · series_context · level_crossing · structure_break
  · change_of_character

Unwired                       559 LOC    5.0 %
  evidence · trading_context
```

**Zero executable import edges connect A and B.** `fmis.pipeline` imports `alignment`, `data`,
`features`, `providers` and `relative_value` — and none of the six structural packages.
`structure_break/__init__.py` and `change_of_character/__init__.py` each state in their own docstrings
that *nothing imports this package*.

The chain is complete and unreachable. This design connects it.

## 2. Scope

**In:** one composition root; one fact-sheet model; a plain-text renderer; a CLI; the reuse of the
existing Binance path.

**Out, explicitly:** any new indicator, any new structural mathematics, AI, regime, support/resistance
naming, portfolio, risk, strategy, backtesting, execution, scheduling, persistence, alerts, dashboard,
JSON output, a second provider.

The milestone's value comes entirely from *composition*. If it needs a new engine, it is the wrong
milestone.

## 3. Where it lives

Two candidate homes were considered.

| Option | Assessment |
|---|---|
| A new `fmis.factsheet` package | Requires deciding what a *second* application layer is, and what its relationship to `fmis.pipeline` should be. Buys nothing the milestone needs |
| **A second module inside `fmis.pipeline`** | **Chosen.** ADR-0007 §1 already defines this package as the application layer — permitted to import every engine, imported by none. A structural composition root is precisely that |

The existing guard tests in `test_pipeline_market_analysis.py` are scoped to
`market_analysis.__file__`, so adding a sibling module leaves them intact, and equivalent guards were
written for the new module.

## 4. The composition

```
                     structural_facts_for_symbol(symbol, interval, ...)
                                    │  network edge — the only I/O
                     _fetch_closed  │  reused from market_analysis, so the
                                    │  closed-candle policy has one implementation
                                    ▼
                     build_structural_facts(series, *, detection, features, ...)
                                    │  pure — no clock, no network, no state
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   FeatureEngine            detect_swings(L, R)          series.closed()
   EMA·RSI·MACD·ATR                 │                    (unconditional)
   ·RelativeVolume         compare_swing_sequence
        │                           │
        │                  label_swing_sequence
        │                           │
        │             derive_structural_sequence_state_history
        │                    │              │
        │       derive_structural_trend    structural_levels
        │                                   │
        │                          derive_level_crossings(series, levels)
        │                                   │
        │                    derive_structure_breaks(..., confirmation_bars=R)
        │                                   │
        │                        derive_changes_of_character(breaks)
        └───────────────────────────┬───────┘
                                    ▼
                          StructuralFactSheet
```

Every arrow is a delegation. Nothing in the root computes a market quantity.

## 5. The confirmation-delay problem

### 5.1 What ADR-0020 D1 actually says

`derive_structure_breaks` takes a required `confirmation_bars` with no default, and it must equal the
`right_bars` used for detection. ADR-0020 records the consequence in its own limitations table:

> **D1** — confirmation delay not carried on any derived fact — *principal limitation; own milestone*

and in its costs section:

> `confirmation_bars` must be supplied and matched to detection by the caller, and **a mismatch is
> undetectable**.

Undetectable is the operative word. A mismatch produces plausible output: it silently changes which
level is the reference at every bar, and therefore which breaks and which changes of character exist.

### 5.2 Why the real fix is a separate milestone

To populate the delay truthfully it must flow from where it is chosen to where it is needed:

```
detect_swings(right_bars=R)   ← R chosen here
  → SwingPoint        fields: index, timestamp, price, type      ← no R
  → SwingComparison                                              ← no R
  → StructuralSwing                                              ← no R
  → structural_levels → LevelOrigin                              ← no R
  → derive_structure_breaks(confirmation_bars=?)                 ← R needed here
```

`SwingPoint`'s docstring reads *"Fields, and nothing else"*, followed by a list of what is
*"deliberately absent"*. Adding a field to it touches five shipped models across three packages, and
the models are constructed at **69 sites in 8 test files** (`SwingPoint`), **77 sites** (`PriceLevel`)
and **10 sites** (`LevelOrigin`). `SwingPoint` also participates in the `(index, timestamp, type)`
ordering key, equality and hashing, and in the contracts of ADR-0012 through ADR-0016.

Both `CURRENT_STATE.md` and ADR-0020 already classified this as its own milestone. This design agrees.

### 5.3 The rejected shortcut

Adding `right_bars` to `structural_levels` looks like a fix and is not. It relocates the hand-matching
from `detect_swings ↔ derive_structure_breaks` to `detect_swings ↔ structural_levels`, where it stays
equally undetectable — and it is **worse than the current gap**, because a stored value that claims to
be provenance, while accepting any number the caller types, is a lie the honest gap does not tell.

### 5.4 The containment that was chosen

```python
@dataclass(frozen=True, slots=True)
class DetectionSettings:
    left_bars: int = DEFAULT_LEFT_BARS
    right_bars: int = DEFAULT_RIGHT_BARS
```

Read once, bound to one local name, handed to both consumers:

```python
confirmation_bars = detection.right_bars
swings = detect_swings(series, left_bars=detection.left_bars, right_bars=confirmation_bars)
...
breaks = derive_structure_breaks(levels, crossings, confirmation_bars=confirmation_bars)
```

Two different values are **unrepresentable through this root**. Enforced by a test that parses
`_structure_of`, strips its docstring, and asserts exactly one read of `detection.right_bars` feeding
both call sites — parsed rather than asserted behaviourally, because the hazard is precisely that a
mismatch produces *plausible* output.

**This is containment, not a fix.** Every other caller of `derive_structure_breaks` remains exposed.
The sheet prints that limitation on every run.

## 6. What the sheet reports

| Section | Content | Source |
|---|---|---|
| Header | asset, exchange/source, timeframe, as-of, freshness, window, detection settings, last close | provider + `DataWindow` |
| Indicators | EMA(20), EMA(50), RSI(14), ATR(14), MACD(12,26,9) expanded to its three components, RelativeVolume(20) | `fmis.features` |
| Market structure | swing count, labelled/unlabelled split, structural trend, latest label, latest break, break count, latest change of character, change count | the L4 chain |
| Structural levels | level count by side, **nearest above** and **nearest below** the last close with side and origin label, crossing-event count | `fmis.level_crossing` |
| Warm-up | which features lack history, out of how many | `FeatureResult.value is None` |
| Limitations | six inherited limitations, each with its ADR code | `LIMITATIONS` |

### 6.1 Why not "support" and "resistance"

The milestone brief listed both. ADR-0019 §I reserves that naming for a later layer, and
`structural_levels`' docstring refuses it explicitly. Reporting them under those names would have put
the first interpretation into a deterministic layer and contradicted a shipped ADR.

The live output demonstrates the point. On real BTCUSDT 4H data the nearest level *below* the close is
an **UPPER** level — a former swing high that price has traded through. "Support" would assert
something the data does not say; "nearest below, upper side, higher_high @ bar 28" says exactly what
is true.

## 7. Determinism

| Property | How |
|---|---|
| No clock beneath the CLI | Tested: the module source contains no `datetime.now`, `utcnow`, `time.time`, `time.monotonic` |
| No arithmetic | Tested: zero `BinOp` of any arithmetic kind — one stricter than ADR-0007 §2 allows `market_analysis` |
| No maths imports | Tested: no `math`, `statistics`, `decimal`, `fractions`, `random` |
| Closed candles only | `series.closed()` unconditionally; exclusion reported in `DataWindow` |
| Equal inputs, equal sheets | Tested directly on the committed fixture |
| Total ordering on ties | Two levels at one price resolve identically in any input order |

Nearest-level selection uses **comparison only** — smallest price above the close, largest below —
because sorting by distance would have required a subtraction.

## 8. Test strategy

79 tests across twelve groups: end-to-end composition · closed-candle policy · determinism and purity
· **ADR-0020 D1 containment** · nearest levels · warm-up · insufficient data · immutability ·
limitations · network edge · architectural guards · fact-only vocabulary · renderer · CLI.

Expected values are hand-derived or read from the committed fixture. One test proves reuse rather than
assuming it: the root's swings, labels, levels and crossings must equal the engines called directly.

## 9. Measured results

**Correctness.** 3,300 tests pass, identically under `-W error`. Coverage of the new modules:
`cli.py` 100 %, `structural_facts.py` 100 %, `render.py` 95 %.

**Mutation.** 35 probes across the three new modules — D1 containment, closed-candle policy,
nearest-level selection, warm-up reporting, chain wiring, provenance, renderer, CLI. **35/35 detected,
zero survivors, zero no-ops.** Six survived the first round; all six were **test-suite gaps, not
equivalent mutants**, and each was closed:

| Probe | Why it survived | Fix |
|---|---|---|
| `left_bars` replaced by the delay | Every test used a symmetric pair (L2 R2, L4 R4, L3 R3), so swapping was invisible | A test with an asymmetric pair (L3 R5) over a committed irregular walk |
| Tie-break loses the origin index | The two tied levels had *different labels*, so the label alone decided | Same label on both, making the index the deciding field |
| Per-row warm-up note removed | The section header also contains "warming up" | Assert the note on the `ema_50` row specifically |
| Break presence inverted | The test asserted only that the label appeared | Assert the rendered side and bar; plus a no-break case |
| Nearest above/below swapped | The fixture has `above=None`, so the swap was invisible | A series where both exist and differ, asserting values per line |
| `--no-age` ignored | The test never asserted the line was absent | Assert absent with the flag, present without |

**Performance.** Scaling measured over synthetic series, five runs each, median:

| candles | median | levels | crossings | growth |
|---:|---:|---:|---:|---:|
| 100 | 1.5 ms | 46 | 668 | — |
| 500 | 18.2 ms | 246 | 4,068 | ×4.37 |
| 1,000 | 61.4 ms | 496 | 8,318 | ×3.37 |
| 2,000 | 223.1 ms | 996 | 16,818 | ×3.64 |
| 5,000 | 1,318.9 ms | 2,496 | 42,318 | ×5.91 |

Quadratic. Attributed by stage:

| candles | crossings share of total |
|---:|---:|
| 1,000 | **90.6 %** |
| 2,000 | **94.9 %** |
| 4,000 | **97.2 %** |

`derive_level_crossings` is the entire quadratic term. This is ADR-0019's documented
`O(candles × levels)` with levels growing linearly in candles — **inherited, not introduced**. Every
other stage is linear and the composition root's own overhead is negligible.

Practical effect: a 5,000-candle sheet takes ~1.3 s, acceptable for a CLI. A scanner over many symbols
would need a level-selection policy first — which is Phase 3's support/resistance work, not this
milestone's.

## 10. Verified live

```
fmits facts BTCUSDT --interval 4h --limit 200
```

returned a complete sheet from real Binance data: 199 closed candles (1 forming excluded), all six
features ready, 50 swings (48 labelled), `sustained_lower` trend, 18 breaks, 8 changes of character,
48 levels, 1,355 crossing events, nearest level each side of the close, and the six limitations.

This is the first time the structural chain has been reached from real market data.

## 11. What this unlocks

Value Level 0 → 1 on Report 0004's ladder. Maturity M1 → M2 on Report 0003's scale. The chain now has
a caller, so its ergonomics can be judged; and the next structural milestone has somewhere to be seen.

## 12. What it does not claim

It produces **facts, not analysis**. The human — assisted for now by the v3 TradingView prompt — still
analyzes. That boundary is what makes the sheet safe to ship at Level 1, and the renderer's closing
line states it on every run.
