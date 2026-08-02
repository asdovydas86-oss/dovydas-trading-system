# ADR-0023 — Multi-timeframe composition: three facts side by side, nothing derived from their combination

**Status:** Accepted
**Date:** 2026-08-02
**Decides:** how several timeframes are composed, how their roles are assigned, and what may *not* be
said about them together (Milestone AG)
**Implemented by:** `feat(pipeline): add Multi-Timeframe Fact Sheet v1`
**Relates to:** [ADR-0007](ADR-0007-application-layer-boundary.md) (the boundary reused);
[ADR-0009](ADR-0009-trading-analysis-context-boundary.md) (never infer what the caller states);
[ADR-0020](ADR-0020-break-of-structure-foundation-v1.md) (D1, still contained);
[ADR-0022](ADR-0022-structural-fact-sheet-composition-root.md) (the root composed per view);
`reports/0006` §5 (the implementation contract this executes)

---

## Context

Milestone AF shipped a fact sheet for **one instrument on one timeframe**, and the architecture gate
that followed found it could actively mislead. Measured live on BTCUSDT the same day: 1W read
`sustained_higher`, 1D `neutral`, 4H `sustained_lower`.

`PROJECT_SPECIFICATION_V1.md` §5 names exactly that case:

> Weekly: bullish structural trend. Daily: correction. 4H: early momentum reversal.
> **That combination is different from simply calling the asset "bullish."**
>
> The system must avoid mixing timeframe signals without explaining their role.

A user running `fmits facts BTCUSDT` saw `sustained_lower` and nothing else. Multi-timeframe is
therefore not a convenience — it is the difference between a fact and a misleading fact.

## Decisions

### 1. A third composition root in `fmis.pipeline`, composing AF rather than extending it

`fmis.pipeline.multi_timeframe` calls `structural_facts_for_symbol` once per timeframe and reaches no
engine of its own. ADR-0007 §1 already grants this package the right to import every engine and
forbids any engine importing it, so no new architectural decision was needed — the same reasoning
ADR-0022 §1 used.

`structural_facts.py` was **not modified**. A test asserts it contains no reference to
`multi_timeframe` or `TimeframeRole`, so the direction of the dependency cannot invert later.

### 2. **No cross-timeframe synthesis.** This is the load-bearing decision

The sheet reports each view's facts side by side and derives **nothing** from their combination: no
"aligned", no "conflicting", no agreement flag, no consensus, no count of matching trends, no score.

*Rejected alternative:* a `TrendAgreement` field with values `ALL_EQUAL` / `MIXED`. It is
deterministic, cheap, and obviously useful — and it is still **a classification of market state**,
which is the Market Regime Engine's job. Emitting it here would put the first interpretation into the
application layer and pre-empt a layer that does not exist yet. The same error the architecture gate
rejected a workspace for.

The reader sees `1W sustained_higher · 1D neutral · 4H sustained_lower` and draws the conclusion. The
system does not draw it for them.

Enforced three ways: the dataclass field set is asserted exactly; no public attribute may contain a
synthesis word; and the rendered output is scanned for ten synthesis terms outside the limitations
block — with a second test proving the limitations that *disclaim* synthesis are still rendered, so
the exclusion cannot hide their removal.

### 3. Roles are stated, never inferred from the interval

`TimeframeRole` is `CONTEXT` / `SETUP` / `EXECUTION` — `SPEC` §5's framework, which is explicit that
1W/1D/4H "is not a permanent universal rule". A view carries its role *and* its interval as two
fields, and a caller may map any interval to any role.

This follows ADR-0009's rule about trading objectives: inferring would silently decide the very thing
the caller is stating. The CLI names roles explicitly (`--context`, `--setup`, `--execution`).

Role **order** comes from an explicit `_ROLE_ORDER` mapping, not from enum definition order, following
`_SIDE_RANK` in `fmis.level_crossing.models`: an ordering contract resting on definition order changes
silently when a member is moved.

### 4. Views are **not aligned in time**, and each keeps its own `as_of`

Views are fetched independently and have different timestamps by nature. Measured live: the 1W view's
newest closed bar was **13 days old** because the week had not closed, while the 4H view's was hours
old.

`fmis.alignment` is deliberately **not** used. It exists to make series comparable for *arithmetic*,
and nothing here computes across timeframes; forcing intersection would discard data for no gain. A
test asserts no import of it — checked against imports rather than raw text, because the module
docstring names it to record why it is unused.

`newest_as_of` is the maximum across views, named to prevent it reading as a shared observation
instant. A field called `as_of` was rejected for exactly that reason. The renderer labels it
"not a shared instant" and prints each view's own timestamp.

### 5. Nothing partial

If any requested timeframe cannot be analysed, the error propagates and no sheet is returned. A sheet
missing its context view would look complete while answering a different question.

### 6. Zero arithmetic, no clock

The module contains **no arithmetic operator at all** — AST-asserted, matching `structural_facts`.
The one candidate, a set difference validating symbols, was rewritten as a comprehension: set
subtraction is `ast.Sub`, and an invariant that admits no exceptions is easier to trust.

No clock is read beneath the CLI, so a sheet is a pure function of its views. Cross-process
determinism verified: identical output hash under four `PYTHONHASHSEED` values.

### 7. `swing_features()`, and `default_features()` left untouched

The swing workflow's headline trend reference is EMA(200), which `default_features()` does not ship.
Adding it there would break `tests/test_pipeline_market_analysis.py:128`, which asserts every default
feature has a value over a **60-candle** fixture — EMA(200) needs 200 — and would silently change
`analyze_symbol` for every existing caller.

`swing_features()` is `default_features()` plus EMA(200). Two *named* sets with stated purposes are
clearer than one set meaning "whatever the last milestone needed". A regression test pins
`default_features()`.

### 8. The confirmation delay still has exactly one source

One `DetectionSettings` is built or accepted once and passed to every view, so ADR-0020 D1's
containment extends across the sheet unchanged. Asserted twice: an AST check that
`DetectionSettings()` is constructed once and `detection=` appears once, and a behavioural spy proving
all three views receive the *same object*.

D1 itself is still **not fixed**. AG adds no second caller of `derive_structure_breaks` — it reuses
AF's root — so the hazard remains contained and remains owed to its own milestone.

### 9. Commands are declared in a registry, not dispatched by hand

`Command` records name, help, argument configuration and runner together; `COMMANDS` is the single
tuple `build_parser` and `main` both read. Introduced now rather than later because the third command
is where a hand-written `if/elif` chain starts drifting from the parser.

## Consequences

**Gained.** The daily swing workflow's deterministic step is complete: one command, three
role-labelled timeframes, computed facts. The single-timeframe misreading that AF shipped with is
addressed.

**Costs, accepted deliberately.**

- **Three sequential fetches.** Wall time ~1.9 s live for three views at 260 candles. No concurrency
  was added; it would be premature and the composition overhead itself is 0.004 ms — effectively free.
- **A compact per-view block.** Three exhaustive sheets on one page is unreadable, so the view block
  shows fewer fields than `fmits facts`. Nothing is computed differently; `fmits facts` remains the
  place to read one timeframe exhaustively.
- **`TimeframeView` carries both `role` and `interval`** where `sheet.interval` already exists. The
  duplication is deliberate — it records what the *caller requested* against what the provider
  returned, and a test pins that they agree today so a divergence would be visible.

**Limitations.**

| | Question | Status |
|---|---|---|
| **AG-1** | Views are fetched at different instants and are not aligned | deliberate; each view reports its own as-of |
| **AG-2** | No cross-timeframe synthesis is performed | deliberate; the Regime Engine's job |
| **AG-3** | `ema_200` on a weekly view needs ~4 years of history | reports as warming up where unavailable |
| **F1** | ADR-0020 D1 contained, not fixed | inherited from AF; own milestone |
| **F2–F6** | One provider · single symbol · no persistence · text only · quadratic in candles | inherited from ADR-0022 unchanged |

**Still deliberately absent:** regime, alignment, agreement, scanning, watchlists, persistence,
scheduling, alerts, AI, portfolio, risk, strategy, execution, JSON output, a second provider,
non-crypto assets, and any interface beyond the CLI.
