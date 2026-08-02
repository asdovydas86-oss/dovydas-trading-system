# ADR-0022 — Structural Fact Sheet: a second composition root, and containing the confirmation delay

**Status:** Accepted
**Date:** 2026-08-02
**Decides:** where the first end-to-end consumer of the structural chain lives, what it may report, and how the ADR-0020 D1 hazard is handled before it is fixed (Milestone AF)
**Implemented by:** `feat(pipeline): add Structural Fact Sheet v1`
**Relates to:** [ADR-0007](ADR-0007-application-layer-boundary.md) (the boundary it reuses);
[ADR-0019](ADR-0019-level-crossing-foundation-v1.md) (level and crossing facts, and the naming rule);
[ADR-0020](ADR-0020-break-of-structure-foundation-v1.md) (D1, the confirmation delay);
[ADR-0021](ADR-0021-change-of-character-foundation-v1.md) (the chain's last layer);
`reports/0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md` §11 (the milestone this executes)

---

## Context

Thirty milestones produced a deterministic core of unusual quality and **no user-visible capability**.
Report 0001 measured it, Report 0003 diagnosed it structurally, and Report 0004 restated it as a
capability fact: the `fmis` package is two dependency islands sharing only the kernel, with **zero
executable import edges between them**.

- **Island A — measurement.** `data → ingest → providers → pipeline → decision_support`, plus
  `features`, `alignment`, `relative_value`. It has a live data path and an application layer.
- **Island B — structure.** `market_structure → structural_trend → series_context → level_crossing
  → structure_break → change_of_character`. **5,695 LOC, 51.2 % of the codebase, no provider path and
  no consumer.** Two of its packages state in their own docstrings that nothing imports them.

The structural chain is complete — ADR-0021 closed it — and unreachable. Every further structural
milestone would deepen a chain no application can call, and its contracts have never met a real
caller.

This milestone connects them. It adds **no engine, no indicator, no structural mathematics, no AI, no
persistence and no interface** — only composition.

## Decisions

### 1. The fact sheet is a second composition root **inside** `fmis.pipeline`, not a new package

ADR-0007 §1 already defines `fmis.pipeline` as the application layer: it may import every engine, and
no engine may import it. A structural composition root is exactly that kind of module. Creating a
sibling application package would have required deciding what a *second* application layer means, and
that decision buys nothing — the milestone's constraint was explicitly "no extra architecture".

So `structural_facts.py` sits beside `market_analysis.py`, under the boundary ADR-0007 already fixed,
and the tests that enforce it apply unchanged.

**Consequence:** six pre-existing import guards, each of which names its permitted consumers, were
widened to name `fmis.pipeline`. Every widening is documented in the guard's own docstring, and the
*direction* rule each guard exists for is unchanged: no engine may import upward. The guards behaved
exactly as designed — they forced this ADR to exist rather than allowing a silent new dependency.

### 2. Orchestration only, and **zero** arithmetic — one stricter than its sibling

ADR-0007 §2 allows `market_analysis` exactly one arithmetic operator, a bookkeeping subtraction.
`structural_facts` has **none**: it reuses `_window_of` rather than restating that subtraction, and
its nearest-level selection is written with comparison alone (smallest price above the close, largest
below) rather than by sorting on a distance, which would have required a subtraction.

A test parses the module's AST and asserts no `BinOp` of any arithmetic kind, and a second asserts it
imports no `math`, `statistics`, `decimal`, `fractions` or `random`.

### 3. The confirmation delay has exactly **one source**, which contains ADR-0020 D1 without fixing it

ADR-0020 D1 is the largest correctness hazard in the chain: `derive_structure_breaks` needs a
`confirmation_bars` equal to the `right_bars` used for detection, and **a mismatch raises no error**.
It silently changes which level is the reference at every bar, and therefore which breaks and which
changes of character exist.

Fixing it properly means carrying the delay from `detect_swings` through `SwingPoint` →
`SwingComparison` → `StructuralSwing` → `structural_levels` → `LevelOrigin`. `SwingPoint` has four
fields and a docstring reading *"Fields, and nothing else"*; the change touches five shipped models
across three packages and 69 test construction sites for `SwingPoint` alone. **That is a milestone,
which both `CURRENT_STATE.md` and ADR-0020's own limitations table already said.**

Giving `structural_levels` a `right_bars` parameter was rejected as a **fake fix**: it relocates the
hand-matching from `detect_swings ↔ derive_structure_breaks` to `detect_swings ↔ structural_levels`
and remains undetectable — and it is strictly worse than the current honest gap, because a *stored*
wrong value looks like provenance.

**Decision:** a frozen `DetectionSettings(left_bars, right_bars)` is the single source. `right_bars`
is read **once**, bound to one local name, and handed to both consumers, so two different values are
unrepresentable through this root. This is **containment, not a fix** — every other caller of
`derive_structure_breaks` remains exposed — and the sheet says so in its own limitations block.

Enforced two ways: a test parses `_structure_of`, strips its docstring, and asserts exactly one read
of `detection.right_bars` feeding both call sites; and a behavioural test proves the root's breaks
equal the engine called directly with the matching delay.

### 4. A sheet is a **pure function of its candles** — no clock anywhere beneath the CLI

`build_structural_facts` reads no time. Two sheets built from the same candles are equal, which is
what will make a stored sheet re-derivable when persistence arrives. Freshness is reported as the last
closed timestamp; turning that into an *age* needs a reference instant, and only the CLI — the
outermost edge — takes one, with `--reference-time` making even that injectable so rendered output can
be pinned in a test.

A test asserts the module's source contains no `datetime.now`, `utcnow`, `time.time` or
`time.monotonic`.

### 5. Levels are reported as **nearest above / nearest below**, never as support and resistance

ADR-0019 §I reserves that naming for a later layer, and `structural_levels`' own docstring refuses it:
an `EQUAL_HIGH` becomes an `UPPER` level carrying the `EQUAL_HIGH` label, *"not a 'double top',
'resistance', 'liquidity' or a 'protected high'"*.

Milestone AF's brief listed "Support" and "Resistance" as fact-sheet fields. Reporting them under
those names would have been the first interpretation to enter a deterministic layer, and would have
contradicted a shipped ADR. What the sheet reports instead is the *fact* such an interpretation would
rest on — the closest level each side of the last close, with its side and origin label intact.

The live output shows why this matters: on real BTCUSDT data the nearest level *below* the close is an
**UPPER** level (a former swing high price has traded through). Calling it "support" would assert
something the data does not say.

### 6. Fact-only vocabulary is enforced **through to the terminal**

A test scans rendered output for `buy`, `sell`, `long`, `short`, `bullish`, `bearish`, `support`,
`resistance`, `signal`, `recommend`, `entry`, `target`, `confidence`, `score`.

Two exemptions, each justified rather than convenient: `signal_line` is MACD's own component name for
a computed quantity, and the closing disclaimer contains "recommendation" precisely to deny making
one — asserted by a separate test, so removing it fails rather than passes.

### 7. Warm-up is named, never inferred from a null

An indicator without enough history carries `value=None` plus warm-up metadata. The sheet lists those
features in a first-class `warming_up` tuple and the renderer prints an em dash with the reason,
because *"not computed yet"* and *"computed to be nothing"* must never look alike.

Insufficient data to detect **any** swing is different: it raises `InsufficientDataError`, because the
question cannot be answered at all.

### 8. Inherited limitations are printed on the sheet

Six, each carrying the code of the ADR that owns it (ADR-0019 D1/D2, ADR-0020 D1/D3/D5, ADR-0021 E1).
A fact sheet that omitted what it cannot see would read as more complete than it is.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| A new `fmis.factsheet` package | Requires deciding what a second application layer is; ADR-0007 already covers this case |
| Fix ADR-0020 D1 inside this milestone | Five shipped models, three packages, 69 test sites — a milestone, as ADR-0020 and `CURRENT_STATE.md` both recorded. Doing it here would have tripled the scope and delayed all user value |
| Fix D1 first, as its own milestone, then build this | The hazard is untrippable with **no callers**; this milestone creates the first. Fixing it first delays every unit of user value to close a hazard nobody can currently hit |
| `structural_levels(swings, *, right_bars)` | A fake fix: relocates the hand-matching and stays undetectable, while making a wrong value look like recorded provenance |
| Report support/resistance as named | Contradicts ADR-0019 §I and would put the first interpretation into a deterministic layer |
| Let the renderer read the clock | Makes rendered output non-reproducible; the reference instant is injected at the edge instead |
| JSON output in v1 | Serialization is an open architectural question (`ARCH` §13.8); text needs no decision and the milestone forbade scope growth |

## Consequences

**Gained.** The first end-to-end path from a provider through **every** deterministic layer. 51.2 % of
the codebase becomes reachable. The first product surface (`fmits facts SYMBOL`). The first real
feedback the structural contracts have ever received — and they needed no change, which is the
strongest available evidence that the layering below is correct.

**Costs, accepted deliberately.**

- **ADR-0020 D1 is contained here, not fixed** — the principal limitation, named loudly and printed on
  every sheet. Milestone AG owes the real fix.
- **`derive_level_crossings` dominates runtime** — measured at 91 % of total at 1,000 candles rising to
  97 % at 4,000, growing quadratically. This is ADR-0019's documented `O(candles × levels)`, inherited
  rather than introduced; the composition root's own overhead is negligible. Practical effect: a
  single 5,000-candle sheet takes ~1.3 s, which is fine for a CLI and would not be for a scanner.
- **`build_structural_facts` gained a `window` parameter** so the fetching wrapper can report the
  forming candle the provider returned even though `_fetch_closed` already dropped it. It changes what
  is *reported*, never what is *computed* — the candles analysed are always `series.closed()`.
- **Six import guards widened**, each named and documented.

**Limitations.**

| | Question | Status |
|---|---|---|
| **F1** | Confirmation delay contained, not carried on a derived fact | principal limitation; Milestone AG |
| **F2** | One provider only (Binance spot); non-crypto assets need the calendar layer | inherited; Phase 6 |
| **F3** | No multi-timeframe composition — one sheet is one timeframe | inherited (`ARCH` D11); Phase 3 |
| **F4** | No persistence: a sheet is printed, not stored | deliberate; Phase 5 |
| **F5** | Text output only; no JSON, because serialization is undecided | deliberate |
| **F6** | Quadratic in candles via crossings | inherited from ADR-0019 |

**Still deliberately absent:** regime, support/resistance naming, composite features, scanning,
scheduling, AI interpretation, portfolio, risk, strategy, backtesting, execution, alerts, dashboards.
