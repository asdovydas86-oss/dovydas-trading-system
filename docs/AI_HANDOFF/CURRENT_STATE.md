# Current State

**Snapshot document.** This file records the repository as it is **today**. It is the one document that
should be updated at the end of every milestone. If it disagrees with the code, the code is correct —
update this file.

**Last updated for:** Milestone AI — Market Regime Engine v1 (2026-08-03).
**Latest commit at time of writing:** `0775292` — `docs(product): record Milestone AH release`
(Milestones AF, AG and AH are committed; AH is **not yet pushed**, and the Milestone AI changes are
uncommitted at time of writing).

---

## Current milestone

- **AI — Market Regime Engine v1**: the first **interpretation-adjacent** layer in the repository, and
  `ARCH` §9's highest-leverage unbuilt module. Contracts in
  [ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md); design in
  [the design document](../design/MARKET_REGIME_ENGINE_V1.md); independent review in
  [the review record](../reviews/MARKET_REGIME_ENGINE_V1_REVIEW.md).

  **The problem it solved.** The regime call lived in the v3 TradingView prompt's STEP 1 — not
  versioned, not diffable, not testable. `docs/analysis-notes.md` records what that cost in v2: a trend
  gate counted twice so a LONG began with two free confirmations, branches that looked symmetric while
  one required a deep bear market, tools defined in one direction only, and no NO-TRADE outcome.

  **What shipped:** `fmis.market_regime`, an engine package at L5, plus a fourth composition root
  `fmis.pipeline.regime`, two renderers and the `fmits regime SYMBOL [--multi]` command.

  **A regime is the environment, never a direction.** Three dimensions — **structure**
  (trending/ranging/transitioning/indeterminate/insufficient), **volatility**
  (expanding/contracting/steady/insufficient) and **participation**
  (elevated/subdued/typical/insufficient) — each with its own evidence, never collapsed into one label
  and never scored. This **diverges from the v3 prompt**, which classifies BULLISH/BEARISH/RANGE: a
  directional regime is the object whose branches drifted apart in v2. Which way structure points is
  already a fact on the fact sheet.

  **The v2 failures are structurally unrepresentable.** The engine cannot tell `SUSTAINED_HIGHER` from
  `SUSTAINED_LOWER` — asserted by comparing two whole regimes. Evidence votes by **family**, and the
  four families partition across the three dimensions, so nothing corroborates itself. A threshold band
  is **one** number whose edges are `1 + band` and `1 / (1 + band)`, so an asymmetric gate cannot be
  written through the API or the CLI at all.

  **Uncertainty is first-class.** `INSUFFICIENT` (evidence absent) and `INDETERMINATE` (evidence present
  and disagreeing) are distinct states. Structure refuses to classify from one readable family, because
  a single-family call is the free confirmation v2 gave away. `UNAVAILABLE` evidence is never counted as
  conflicting, and a fourth status `CONTEXT` marks facts reported but counted neither way — following
  `decision_support`'s `NOT_DIRECTIONAL` precedent.

  **The boundary is a narrow model.** `fmis.market_regime` imports exactly **one** name from the
  repository, `StructuralTrendType`, and cannot see `fmis.pipeline`, `fmis.features`, `fmis.data` or a
  provider. The composition root adapts a `StructuralFactSheet` into `RegimeInput` and contains **no
  arithmetic**, which is why the input carries indices rather than a distance.

  **`facts` and `mtf` are untouched.** Their feature sets are byte-identical and their pages print no
  regime vocabulary, both asserted. `regime_features()` adds a slow ATR baseline for the volatility
  ratio, exactly as AG added EMA(200) — and `fmis.features.VolatilityRegime` was **not** reused, being
  a *level* vocabulary (LOW/HIGH/EXTREME) for an unbuilt feature rather than a statement about change.

  **Quality.** 3,449 → **3,582 tests** (+133), identically under `-W error`. Coverage **100 %** on every
  module AI touched. **45 mutation probes, 45 detected, 0 survivors, 0 no-ops**, byte-identical
  restoration. Exports 173 / 0 collisions. Classification costs 0.006 ms — 0.03 % of a 500-candle sheet.

  **The review found four P2s, all fixed.** The evidence line printed `sustained_lower`, putting a
  direction on a page whose own limitation denies restating one — found by reading live output, not by a
  test. `MarketRegime.policy` was typed `Any` and never validated, so a result could cite a policy that
  could not have produced it. Validation ran in the wrong order, raising `AttributeError` instead of a
  named `TypeError`. And one assertion ended in `or True` and could never fail.

- **AH — Confirmation-Delay Provenance v1**: the milestone that **closes ADR-0020 D1**, the largest
  remaining correctness hazard before the Market Regime Engine. Contracts in
  [ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md); design in
  [the design document](../design/CONFIRMATION_DELAY_PROVENANCE_V1.md); independent review in
  [the review record](../reviews/CONFIRMATION_DELAY_PROVENANCE_V1_REVIEW.md).

  **The problem it solved, measured.** `derive_structure_breaks` required a `confirmation_bars`
  argument that had to equal the `right_bars` used for detection, and the number lived on none of the
  inputs, so nothing could check it. A wrong value did not raise: it silently changed which level was
  the reference at every bar, and therefore which breaks and which changes of character existed.
  Across 300 seeded series against five wrong delays, **36.1 % produced materially different breaks
  and zero raised an error**.

  **What shipped:** the delay is stamped where it is known and travels with the facts derived from it.
  `detect_swings` records `right_bars` on every `SwingPoint`; `structural_levels` copies it onto every
  `LevelOrigin`; `derive_structure_breaks` reads `origin.knowable_from` and **no longer takes the
  argument at all**. Neither does `contextual_structure_breaks`, and `structural_levels` never did.

  **The mismatch is unrepresentable, not guarded.** The brief forbade a runtime warning over two
  independent sources of truth, and no compatibility path was kept: an optional override would have
  preserved the hazard exactly. `StructureBreak.eligible_from` became a **projection** of
  `crossing.level.origin.knowable_from`, so a break can no longer disagree with its own level.

  **`knowable_from`, not `eligible_from`.** *Knowable* is a fact about detection; *eligible* is a
  break-of-structure decision that stays in `fmis.structure_break`. A first attempt named it
  `confirmed_at` and `fmis.market_structure`'s vocabulary guard rejected it — `confirmed` is on the
  banned interpretation list. The guard was right; the name changed and the guard was not weakened.

  **One level set must agree on one window.** A mixed set is rejected as `StructureBreakInputError`,
  because `eligible_from` must be strictly increasing within a side for `_reference`'s binary search
  and for the single-test eligibility rule to hold. A window of at least 1 is required on both models,
  which also makes a break at bar 0 unrepresentable — reachable before only from a hand-built fixture.

  **AF and AG both lose their duplicated delay configuration.** `structural_facts` reads `right_bars`
  once and hands it to `detect_swings` alone; the AF-era guard asserting one read feeding two
  consumers is replaced by one asserting no `confirmation_bars=` argument exists in the module.
  **`ADR-0020 D1` is removed from `LIMITATIONS`**, so both sheets now print six limitations, not seven.

  **Public API changes.** `SwingPoint` and `LevelOrigin` each gain a required `confirmation_bars` field
  and a `knowable_from` property; `SwingComparison` rejects a pair whose windows disagree;
  `StructureBreak` keeps one field and projects `eligible_from`. **No package's `__all__` changed** —
  13 / 19 / 5 as before. 80 test construction sites were migrated by AST position, with no default
  added, so every site states the window it means.

  **Quality.** 3,404 → **3,449 tests** (+45), identically under `-W error`. Coverage 100 % on every
  module AH touched, except two at 99 % whose uncovered lines predate this milestone. **42 mutation
  probes, 41 detected, 1 proven-equivalent survivor, 0 no-ops**, byte-identical restoration verified.
  Public exports 154 / 0 collisions, import cycles 0, runtime dependencies 0.

  **Behaviour is otherwise unchanged, and that is proved.** A reimplementation of the pre-AH algorithm
  agrees with the new derivation on every break across 40 seeded series at four detection windows. On
  the same fixtures a wrong delay changes the answer on more than a third — the defect and the proof
  that removing it broke nothing, measured on one data set.

  **The review found two P2s, both fixed.** The rendered detection row could not distinguish
  `left_bars` from `right_bars` because every fixture used `L2 R2`; and the cross-window rejection
  message was asserted only by substring, so a probe swapping the two reported windows survived. It
  also recorded the one surviving probe as a **proven equivalent mutant** rather than rounding it to
  zero.

- **AG — Multi-Timeframe Fact Sheet v1**: the second milestone that adds **no engine**. Contracts in
  [ADR-0023](../adr/ADR-0023-multi-timeframe-composition.md); design in
  [the design document](../design/MULTI_TIMEFRAME_FACT_SHEET_V1.md); independent review in
  [the review record](../reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md).

  **The problem it solved, measured.** AF's single-timeframe sheet can mislead. Live on BTCUSDT the
  same day: 1W `sustained_higher`, 1D `neutral`, 4H `sustained_lower` — the exact combination
  `PROJECT_SPECIFICATION_V1.md` §5 says "is different from simply calling the asset bullish". A user
  running `fmits facts BTCUSDT` saw the 4H row alone.

  **What shipped:** `fmis.pipeline.multi_timeframe` — a third composition root calling
  `structural_facts_for_symbol` once per timeframe — plus `render_multi_timeframe_sheet`, the `fmits
  mtf SYMBOL` command, and a declared **command registry** replacing hand-written dispatch. Roles are
  `CONTEXT`/`SETUP`/`EXECUTION`, defaulting to 1W/1D/4H and settable per role.

  **No cross-timeframe synthesis, and that is the load-bearing decision.** No agreement, alignment,
  conflict, consensus or score. A `TrendAgreement` field was considered and rejected: classifying the
  *combination* is the Market Regime Engine's job, and emitting it here would put the first
  interpretation into the application layer. Four tests hold it, including a scan of rendered output.

  **Views are not aligned in time.** Each keeps its own `as_of` — the weekly view's newest bar
  measured **13 days old** live, because the week had not closed. `newest_as_of` is named to prevent
  it reading as a shared instant. `fmis.alignment` is deliberately unused: it serves arithmetic, and
  nothing here computes across timeframes.

  **ADR-0020 D1 stayed contained** — one `DetectionSettings` reaching every view, asserted by AST
  *and* by object identity across all three calls. **Superseded by Milestone AH**, which removed the
  argument entirely; the containment described here is history, not current behaviour.

  **`default_features()` unchanged.** `swing_features()` adds EMA(200) — the swing workflow's headline
  trend reference — without breaking `test_pipeline_market_analysis.py:128`, whose 60-candle fixture
  EMA(200)'s 200-bar warm-up would fail.

  **Quality.** 3,305 → **3,404 tests** (+99), identically under `-W error`. Coverage:
  `multi_timeframe.py` 100 %, `cli.py` 100 %, `render.py` 100 %. **42/42 mutation probes detected,
  zero survivors, zero no-ops**, with byte-identical restoration. Composition overhead 0.004 ms;
  live wall time ~1.9 s for three views including network. Determinism verified across four
  `PYTHONHASHSEED` values.

  **The review found two P2s, both fixed.** The renderer carried **26 identical lines** across
  `render_fact_sheet` and `_view_block` — surfaced because a mutation anchor matched both copies —
  now extracted into one `_structure_rows` helper. And row order in the single-timeframe sheet was
  **asserted by nothing**: a probe swapping two rows survived the full suite. Both closed. It also
  recorded a defect in the harness itself: same-size mutations were served **stale bytecode**, so the
  harness now purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE` before every probe.

### Previous milestone

- **AF — First Light / Structural Fact Sheet v1**: the first milestone that adds **no engine**. It
  connects what already existed. Contracts in
  [ADR-0022](../adr/ADR-0022-structural-fact-sheet-composition-root.md); design in
  [the design document](../design/STRUCTURAL_FACT_SHEET_V1.md); independent review in
  [the review record](../reviews/STRUCTURAL_FACT_SHEET_V1_REVIEW.md).

  **The problem it solved, measured.** `fmis` was **two dependency islands sharing only the kernel,
  with zero executable import edges between them**. Island A (measurement: data, ingest, providers,
  features, alignment, relative_value, pipeline, decision_support) had a provider and an application
  layer. Island B (structure: market_structure, structural_trend, series_context, level_crossing,
  structure_break, change_of_character) — **5,695 LOC, 51.2 % of the codebase** — had neither, and two
  of its packages stated in their own docstrings that nothing imported them. The chain ADR-0021
  completed was unreachable.

  **What shipped:** a second composition root **inside `fmis.pipeline`** (`structural_facts.py`), a
  plain-text renderer, a CLI (`fmits facts SYMBOL`, also `python -m fmis.pipeline`), and the repository's
  **first product surface**. `build_structural_facts` is pure — no clock, no network — and
  `structural_facts_for_symbol` is the network edge, reusing `_fetch_closed` so the closed-candle policy
  keeps one implementation.

  **Zero arithmetic**, one stricter than ADR-0007 §2 allows `market_analysis`: `_window_of` is reused
  rather than restated, and nearest-level selection uses comparison alone rather than a distance.

  **ADR-0020 D1 is contained, not fixed.** A frozen `DetectionSettings.right_bars` is read once and
  handed to both `detect_swings` and `derive_structure_breaks`, so a mismatch is unrepresentable through
  this root. The real fix carries the delay from detection through `SwingPoint` to `LevelOrigin` —
  five shipped models across three packages, 69 `SwingPoint` construction sites in tests — and remains
  its own milestone, as ADR-0020's limitations table and this document both already said. A
  `right_bars` parameter on `structural_levels` was **rejected as a fake fix**: it relocates the
  hand-matching and stays undetectable, while making a wrong value look like recorded provenance.

  **The hazard was quantified in review:** over 300 seeded series × 5 wrong delays, **36.1 % of
  mismatched calls produced materially different breaks** and 155 of those also changed the number of
  changes of character — with **zero errors raised**. Comparing break *counts* finds nothing; comparing
  break *identity* is required.

  **Levels are reported as nearest above / nearest below, never support and resistance** (ADR-0019 §I).
  The live BTCUSDT run shows why: the nearest level *below* the close is an **UPPER** level, a former
  swing high price has traded through.

  **Purely additive to the engines:** no engine's source was modified. Six pre-existing import guards
  were widened to name `fmis.pipeline`, each documented in its own docstring, with the direction rule
  unchanged. **39/39 mutation probes detected, zero survivors, zero no-ops** — six survived the first
  round and all six were test-suite gaps, closed rather than tolerated. The independent review found
  **no P0, no P1, one P2** (a render branch no fixture reached — fixed, coverage now 100 %) and four
  P3s. Runtime is quadratic and **inherited**: `derive_level_crossings` is 90.6 % of total at 1,000
  candles rising to 97.2 % at 4,000, exactly ADR-0019's documented `O(candles x levels)`.

  **Verified live** against real Binance data: 199 closed candles, 50 swings, `sustained_lower` trend,
  18 breaks, 8 changes of character, 48 levels, 1,355 crossings.

### Earlier milestone

- **AE — Change of Character Foundation v1**: the layer that completes the deterministic structural chain
  `CandleSeries → Swings → Relationships → Labels → Sequence State → Trend → Context → Level Crossing →
  Break of Structure → **Change of Character**`. Contracts in
  [ADR-0021](../adr/ADR-0021-change-of-character-foundation-v1.md); design in
  [the design document](../design/CHOCH_FOUNDATION_V1.md).

  **What a change of character is:** a **break of structure whose side differs from the side broken at the
  most recent strictly earlier break-bearing bar, when that bar broke exactly one side**. Four conjuncts,
  each decided separately: the subject is a `StructureBreak`; a break-bearing bar exists **strictly
  earlier**; that bar broke **exactly one** side; and the subject's side **differs** from it.

  **The audit's headline: this is the first milestone in the chain that adds no primitive and requests
  none.** `StructureBreak` already exposes `index` and `side`, which is everything the rule reads —
  re-derived by inspecting the dataclass directly rather than trusting ADR-0020. That is the strongest
  available evidence that the layering below is correct. ADR-0020's D1 (the confirmation delay is on no
  derived fact) is inherited and **not made worse**: eligibility was resolved one layer down, so this layer
  takes **no configuration of any kind** and cannot be misconfigured.

  **The audit's finding: ADR-0020 §7's CHoCH sketch is superseded.** The sketched
  `zip(breaks, breaks[1:])` adjacency rule infers a change of character from an ordering that ADR-0019 §2.6
  and ADR-0020 §3.5 both explicitly refuse to read as temporal — the order of two breaks sharing a bar is
  the *level* ordering, not a claim about which happened first. On a run the shipped break layer produces,
  `upper@4 · upper@12 · lower@12`, the sketch pairs `upper@12 → lower@12` (a predecessor on the **same
  bar**) where this milestone pairs `upper@4 → lower@12`. Both agree bar 12 changed character; only one can
  say what it changed *from* without fabricating an intrabar path. Notably this is **not** a
  prefix-stability argument — both rules measure 0 violations over 6,400 prefixes — and the design says so
  rather than borrowing a stronger-sounding justification. `fmis.structure_break` was **not modified**: the
  sketch was prose in a "future" section and no production logic depended on it; the disagreement is pinned
  by a test.

  **A two-sided break bar leaves character indeterminate**, so no change is claimed at the next break bar.
  Choosing one of that bar's two breaks to be "the" prior character is the intrabar claim reintroduced one
  step later. Indeterminacy **suppresses without persisting** — the next single-sided break bar restores a
  determinate character. This is the milestone's principal limitation (E1); resolving it needs sub-bar data
  the repository does not ingest.

  **At most one change per bar**, so output is ordered by the changing bar index **alone** — total and
  strictly increasing. The consequence is deliberate: **no side ordering exists anywhere in the package**,
  so `fmis.structure_break`'s private side rank is neither imported nor restated. The one ordering rule
  this layer could plausibly have duplicated is structurally absent.

  **No trend is consulted, in either direction**, and a test pins it from both sides:
  `fmis.structural_trend` imports neither `fmis.structure_break` nor `fmis.change_of_character`. Review §15
  is now satisfied end to end — BOS on levels, CHoCH over the BOS sequence, trend a summary of both,
  defining neither.

  **Purely additive to production:** no existing type, signature, exception message or export was modified,
  and no existing production source byte was changed. The only changes outside the new package are **three
  test guards**, each narrowed by design to name its permitted consumers, plus a new guard asserting that
  `LevelSide` is the **only** name this package takes from `fmis.level_crossing`. **59/59 mutation probes
  detected, zero survivors, zero no-ops.** Two probes survived the first round and both were **test-suite
  gaps, not equivalent mutants** — duplicate collapse was compared with `==` rather than `is`, and no test
  asserted a submodule's `__all__`; both are now closed. Growth is measured as effectively linear: 20,000
  breaks in 0.0113 s, 100,000 in 0.103 s, a realistic 5,000-candle chain in 91 µs. The independent review
  found **no P0, no P1 and no P2**, and three P3 observations, all documented rather than fixed; it
  re-derived the rule as an independent reimplementation (0 mismatches over 4,479 exhaustive + 3,000
  randomised + 60 candle-derived cases), proved every narrowed guard still rejects what it claims to by
  injecting forbidden imports, and confirmed replay determinism across four `PYTHONHASHSEED` values in
  fresh processes.

### Earlier still

- **AD — Break of Structure Foundation v1**: the first layer built **entirely on derived facts**. It
  consumes the structural level set and the crossing history and reads **no candle at all** — the package
  does not import `fmis.data`, so `Candle` is not a name it can reach. Contracts in
  [ADR-0020](../adr/ADR-0020-break-of-structure-foundation-v1.md); design in
  [the design document](../design/BREAK_OF_STRUCTURE_FOUNDATION_V1.md).

  **What a break is:** the **first close beyond the reference structural level for its side, at a bar where
  that level was already knowable**. Five conjuncts, each decided separately: the crossing is a
  `CLOSE_BREACH`; its mechanism is not `ALREADY_BEYOND`; the level has provenance and the bar is at or
  after its confirmation bar; the level **is** the reference for its side; and it is the **first** such
  crossing for that level.

  **The audit found one missing primitive and documented it rather than inventing behaviour.** The
  confirmation delay (`right_bars`) is recorded on **no derived fact** — every dataclass from `SwingPoint`
  to `LevelCrossingEvent` carries only the *pivot* index. Yet BOS needs it: with pivot-bar eligibility the
  result is **prefix-unstable**, measured at **30 violating prefixes across 40 seeded fixtures** with a
  minimal reproduction now shipped as a test fixture, against **0** for confirmation-bar eligibility. So
  `confirmation_bars` is a **required keyword argument with no default** — a default would silently bind
  this layer to `DEFAULT_RIGHT_BARS` and be wrong for anyone who chose otherwise. Carrying it on
  `LevelOrigin` changes a shipped model and is deferred to its own milestone (D1).

  A property that makes the rule safe rather than merely stable: **no breach can occur inside a level's own
  confirmation window** — 11,608 in-window crossings inspected, every one a `TOUCH` — so
  confirmation-based eligibility discards no reachable break.

  **Only a close breaks structure**, and the policy is **not configurable**. A `TOUCH` reached the level
  without passing it; a `WICK_BREACH` passed it and closed back inside — a rejection, and a wick rule
  cannot be non-repainting on a forming bar.

  **The label decides nothing.** All six labels can produce a reference level; `EQUAL_HIGH` is carried
  through on `StructureBreak.label` so a consumer can weigh it in its own layer rather than have breaks
  silently discarded here.

  **Structure breaks once** per level, and a break is **never invalidated** — that is a later reading over
  the break *sequence*, and change-of-character adjacent.

  **Purely additive to production:** no existing type, signature, exception message or export was modified.
  The only changes outside the new package are **two test guards**, each narrowed by design to name its
  single permitted consumer. 42/42 mutation probes detected with zero survivors. The independent review
  found **no P0 and no P1**, and one **P2**: the reference lookup was a linear scan per crossing, measured
  at **125,000,000 inner iterations** for 5,000 levels against 50,000 crossings. An exact binary search cut
  that case from ~1.3 s to 0.026 s and made runtime independent of the level count, with equivalence proved
  against a naive implementation over an exhaustive small space. 48/48 adversarial cases pass.

### Earlier still

- **AC — Level-Crossing Foundation v1**: the first layer to read **both** candles and derived structure,
  closing the gap the market-structure architecture review recorded as §15. Contracts in
  [ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md); design in
  [the design document](../design/LEVEL_CROSSING_FOUNDATION_V1.md).

  **The gap, as the review stated it:** after `detect_swings` **no layer reads a candle**, so no fact of
  the form *"price traded above level L at bar i"* existed anywhere. `SwingPoint` stores only the extreme,
  so close-versus-wick was not derivable from swings. And a swing carries the *pivot's* timestamp, while a
  crossing happens at a different bar that nothing recorded.

  **A crossing is a fact; a break is a reading.** Break of Structure additionally requires deciding which
  level is protected, when protection ends, and whether an `EQUAL_HIGH`-derived level breaks anything —
  none of which follows from the data. Separating them buys a specific property: a BOS layer that
  *disagrees* with any particular protected-level policy can still use these events unchanged.

  **What shipped:** a new sibling package `fmis.level_crossing` with thirteen public names — `LevelSide`,
  `CrossingKind`, `CrossingMechanism`, `LevelOrigin`, `PriceLevel`, `LevelCrossingEvent`,
  `LevelCrossingError`, `DuplicateLevelError`, `crossing_kind`, `derive_level_crossings`,
  `structural_levels`, `contextual_structural_levels`, `contextual_level_crossings`.

  **One canonical crossing policy, deliberately not configurable.** `high == L` is a `TOUCH`; only strict
  `>` / `<` is a breach; wick and close are two *facts on the event*, not two settings. A configurable rule
  would make every historical event non-reproducible without its setting. Comparison is **exact on floats**
  with no tolerance, inheriting ADR-0013 §4.

  **Gaps and outside bars are represented honestly.** `CrossingMechanism` separates price *reaching* a
  level from *arriving beyond* it and from a series that simply *starts* beyond it; `open` is never
  consulted, because an open beyond a level whose low came back through it did trade at the level. An
  outside bar yields two events sharing one index, and their order is the *level* ordering, not a time
  claim — there is **no path field and no "order unknown" flag**, because intrabar order is never known
  and a flag that never varies carries no information.

  **No lifecycle at all**, and that is the decision: no activation, no first-cross-only, no invalidation.
  Both are BOS policies, applied by a consumer filtering fields the event already carries.

  **Prefix stability is exact with no exceptions** — nothing reads forward and there is no confirmation
  delay — measured at 0 violations over 121 prefixes × 22 levels, the real fixture, and an exhaustive
  two-candle space.

  **Purely additive to production:** no existing type, signature, exception message or export was
  modified. The only change outside the new package is one **test guard**, narrowed by design
  (ADR-0018 §6.1) so `fmis.series_context` may be imported by `fmis.level_crossing` and nothing else.
  38/38 mutation probes detected with zero survivors. The independent review found **no P0**, one **P1**
  and two **P2**, all fixed: the level ordering key projected the origin timestamp with
  `datetime.timestamp()`, which reads the **host's local time zone** for a naive value and loses
  microsecond resolution beyond about the year 2900 — so the published order was environment-dependent and
  not total. `LevelOrigin` now requires a timezone-aware timestamp and the key carries the `datetime`
  itself, making both defects unrepresentable. 45/45 adversarial cases pass.

### Earlier milestone

- **AB — Series Identity & Context Contract v1**: closes the integrity risk the Trend Foundation review
  recorded as P3-2. Contracts in [ADR-0018](../adr/ADR-0018-series-identity-and-context-contract.md);
  design in [the design document](../design/SERIES_IDENTITY_CONTEXT_CONTRACT_V1.md).

  **The risk, measured:** a BTCUSDT 4h series and an ETHUSDT 4h series built from identical OHLC rows
  produce **byte-identical** trend histories. Derived facts carried no symbol or timeframe, so nothing
  downstream could tell them apart. A test pins that fact permanently.

  **The audit changed the answer.** Identity already existed: `CandleSeries` has always held `symbol` and
  `timeframe` and validated every candle against them, `fmis.ingest` already called that pair "series
  identity" and already rejected mixed identity, and the evidence-descriptor and trading-context layers
  already fixed the reject-never-normalize and opaque-timeframe policies. **The gap was propagation, not
  definition** — `detect_swings` receives a series with both and reads neither.

  **What shipped:** `SeriesIdentity` in `fmis.data` (where identity is owned), with
  `CandleSeries.identity` as a **projection, not a stored field**; and a new sibling package
  `fmis.series_context` holding the generic immutable `ContextualSeries` envelope, the
  `SeriesIdentityMismatchError` contract, the single choke point `require_same_identity`, and three
  identity-preserving wrappers that delegate entirely to the existing derivations.

  **Context sits beside the values, never inside them** — one identity per series, not one per element —
  so adding it provably changes no analytical result. Equivalence is tested across ten fixture classes
  covering every sequence-state member, every trend member, and outside-bar structure.

  **No normalization; the contract deliberately over-rejects.** `"BTCUSDT"` != `"btcusdt"` != `" BTCUSDT"`;
  `"4h"` != `"4H"`. Over-rejection is safe; under-rejection is the silent mixing being prevented.

  **Purely additive:** no existing type, signature, exception message or export was modified. `fmis.data`
  gained one export (`SeriesIdentity`), `fmis.series_context` adds seven. 15/15 mutation probes detected, and the independent
  review found and fixed one P2 (an empty-but-valid contextual series was falsy because the
  envelope defined `__len__`); no P0 or P1.

### Earlier milestone

- **AA — Trend Foundation v1** (implementation): a new sibling package `fmis.structural_trend`, the first
  deterministic **consumer** of the structural sequence state history, and the first layer in the
  repository whose output rests on a *stated policy* rather than on arithmetic alone. Contracts fixed in
  [ADR-0017](../adr/ADR-0017-structural-trend-foundation.md); design in
  [the design document](../design/TREND_FOUNDATION_DESIGN_V1.md).

  **The definition:** a structural trend is a *sustained same-direction structural shift* — at least
  `MINIMUM_DIRECTIONAL_SHIFTS` (2) snapshots of the same directional state, with no opposing directional
  snapshot between them.

  **Only two states are directional evidence:** `SHIFTED_HIGHER` and `SHIFTED_LOWER`, the two that say
  *both* structural sides moved the same way in price. `EXPANDED`, `CONTRACTED`, `UNCHANGED` and
  `INSUFFICIENT_STRUCTURE` are **transparent** — they neither advance nor invalidate a run, because none
  is evidence *against* a direction.

  **Persistence is unconditional; invalidation is exactly one opposing shift.** The cost is documented
  rather than patched: a trend followed by 500 contracting snapshots still reads as sustained, because
  every decay rule needs an arbitrary constant this layer has no basis for.

  **Ambiguity is reported, never resolved.** `NEUTRAL` (evidence exists on both sides and conflicts) and
  `INDETERMINATE` (evidence is absent) are never folded together. An alternating history is `NEUTRAL`, not
  the latest direction.

  **The threshold is a policy, not a measurement** — a module constant, deliberately not a parameter.
  Measured: `minimum=1` yields a direction in 79% of 1,627 sequences, `minimum=2` in 22%, `minimum=3` in
  5%.

  **Prefix-stable** under candle-series extension and complete structural-group extension, measured at 0
  violations over 2,000 + 739 prefixes. The arbitrary inside-group cut stays **outside** the guarantee
  (inherited from ADR-0016 §7, 133/891 divergences), pinned by a test asserting the divergence still
  exists.

  **Five new public names**, no collision, no dependency added, no existing export or exception message
  changed, `EvidenceFamily` and the evidence catalog untouched.

### Previous milestone

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
| Structural Sequence Ordering Unification (Z0) | `682ca31` | one `_validate_key_order` core; closes review P2-1/P2-2; no API change |
| Structural Sequence State History Foundation v1 (Z1) | `d1c0b3b` | `StructuralSequenceStateSnapshot`, `derive_structural_sequence_state_history`; see [ADR-0016](../adr/ADR-0016-structural-sequence-state-history-foundation.md) |
| Trend Foundation v1 (AA) | see final report | `fmis.structural_trend` — `StructuralTrendType`, `StructuralTrendSnapshot`, `MINIMUM_DIRECTIONAL_SHIFTS`, `derive_structural_trend`, `derive_structural_trend_history`; see [ADR-0017](../adr/ADR-0017-structural-trend-foundation.md) |
| Series Identity & Context Contract v1 (AB) | see final report | `SeriesIdentity` + `CandleSeries.identity` in `fmis.data`; `fmis.series_context` — `ContextualSeries`, `require_same_identity`, `SeriesIdentityMismatchError` and three identity-preserving wrappers; see [ADR-0018](../adr/ADR-0018-series-identity-and-context-contract.md) |

| Level-Crossing Foundation v1 (AC) | see final report | `fmis.level_crossing` — `LevelSide`, `CrossingKind`, `CrossingMechanism`, `LevelOrigin`, `PriceLevel`, `LevelCrossingEvent`, `LevelCrossingError`, `DuplicateLevelError`, `crossing_kind`, `derive_level_crossings`, `structural_levels`, `contextual_structural_levels`, `contextual_level_crossings`; see [ADR-0019](../adr/ADR-0019-level-crossing-foundation-v1.md) |

| Break of Structure Foundation v1 (AD) | see final report | `fmis.structure_break` — `StructureBreak`, `StructureBreakError`, `StructureBreakInputError`, `derive_structure_breaks`, `contextual_structure_breaks`; see [ADR-0020](../adr/ADR-0020-break-of-structure-foundation-v1.md) |

| Change of Character Foundation v1 (AE) | see final report | `fmis.change_of_character` — `ChangeOfCharacter`, `ChangeOfCharacterError`, `ChangeOfCharacterInputError`, `derive_changes_of_character`, `contextual_changes_of_character`; supersedes ADR-0020 §7's CHoCH sketch; see [ADR-0021](../adr/ADR-0021-change-of-character-foundation-v1.md) |

| First Light / Structural Fact Sheet v1 (AF) | see final report | `fmis.pipeline.structural_facts` — `build_structural_facts`, `structural_facts_for_symbol`, `StructuralFactSheet`, `StructureFacts`, `NearestLevels`, `DetectionSettings`, `Limitation`, `LIMITATIONS`; plus `fmis.pipeline.render.render_fact_sheet` and the `fmits` CLI. First consumer of the structural chain; ADR-0020 D1 contained, not fixed; see [ADR-0022](../adr/ADR-0022-structural-fact-sheet-composition-root.md) |

| Multi-Timeframe Fact Sheet v1 (AG) | uncommitted at time of writing | `fmis.pipeline.multi_timeframe` — `TimeframeRole`, `TimeframeView`, `MultiTimeframeFactSheet`, `DEFAULT_TIMEFRAMES`, `MULTI_TIMEFRAME_LIMITATIONS`, `swing_features`, `build_multi_timeframe_facts`, `multi_timeframe_facts_for_symbol`; plus `render_multi_timeframe_sheet`, the `fmits mtf` command and a declared CLI command registry. No engine added; no cross-timeframe synthesis; see [ADR-0023](../adr/ADR-0023-multi-timeframe-composition.md) |

(Earlier commits cover the initial audit and documentation of the pre-code repository state.)

## Test count

**3404 passing** (`uv run pytest`, ~4.9 s), identically with `-W error`. Per module:

| Module | Tests |
|---|---|
| `tests/test_change_of_character.py` | 184 |
| `tests/test_structure_break.py` | 176 |
| `tests/test_level_crossing.py` | 249 |
| `tests/test_market_structure_sequence_state.py` | 312 |
| `tests/test_structural_trend.py` | 353 |
| `tests/test_series_context.py` | 186 |
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
│   │                               StructuralSequenceState,
│   │                               StructuralSequenceStateSnapshot
│   ├── swings.py                   detect_swings, required_candles
│   ├── relationships.py            compare_swings, compare_swing_sequence
│   ├── labels.py                   label_swing, label_swing_sequence
│   ├── sequence_state.py           derive_structural_sequence_state
│   └── state_history.py            derive_structural_sequence_state_history
├── structural_trend/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   StructuralTrendType, StructuralTrendSnapshot,
│   │                               MINIMUM_DIRECTIONAL_SHIFTS
│   └── trend.py                    derive_structural_trend,
│                                   derive_structural_trend_history
├── series_context/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   ContextualSeries, SeriesContextError,
│   │                               SeriesIdentityMismatchError,
│   │                               require_same_identity
│   └── pipeline.py                 contextual_structural_swings,
│                                   contextual_structural_state_history,
│                                   contextual_structural_trend_history
├── level_crossing/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   LevelSide, CrossingKind, CrossingMechanism,
│   │                               LevelOrigin, PriceLevel, LevelCrossingEvent,
│   │                               LevelCrossingError, DuplicateLevelError
│   ├── crossing.py                 crossing_kind, derive_level_crossings
│   ├── levels.py                   structural_levels
│   └── pipeline.py                 contextual_structural_levels,
│                                   contextual_level_crossings
├── structure_break/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   StructureBreak, StructureBreakError,
│   │                               StructureBreakInputError
│   ├── breaks.py                   derive_structure_breaks
│   └── pipeline.py                 contextual_structure_breaks
├── change_of_character/
│   ├── __init__.py                 package rules + public surface
│   ├── models.py                   ChangeOfCharacter, ChangeOfCharacterError,
│   │                               ChangeOfCharacterInputError
│   ├── changes.py                  derive_changes_of_character
│   └── pipeline.py                 contextual_changes_of_character
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

The **deterministic structural chain is complete**:

    CandleSeries -> Swings -> Relationships -> Labels -> Sequence State -> Structural Trend
                 -> Series Context -> Level Crossing -> Break of Structure -> Change of Character

Every stage is pure, non-repainting, exactly prefix-stable, identity-carrying and single-implementation.
Nothing in the chain remains to be built before a consumer can read structure end to end.

**Recommended next: Milestone AH — carry the confirmation delay on `LevelOrigin` (ADR-0020 D1).**
*(Renumbered: AG became the Multi-Timeframe Fact Sheet, which reuses AF's single caller and therefore
kept the hazard contained rather than reopening it.)*
Still the single largest correctness hazard in the chain, and still the only one a caller can trip
without any error being raised — but the case is now **measured rather than argued**. Milestone AF's
review ran 300 seeded series x 5 wrong delays: **36.1 % of mismatched calls produced materially
different breaks**, 155 of those also changed the number of changes of character, and **not one raised
an error**. Comparing break *counts* finds nothing; only comparing break *identity* exposes it.

Milestones AF and AG **contain** the hazard for the only caller that exists — `DetectionSettings`
single-sources the delay, so a mismatch is unrepresentable through the fact sheet — but containment is
per-caller and does not generalise. The second consumer of `derive_structure_breaks` reopens it.

What AG must decide: whether the delay rides on `SwingPoint` (flowing to `LevelOrigin` through
`SwingComparison` and `StructuralSwing`) or is attached later; and what happens to the 69 `SwingPoint`
construction sites in tests. A `right_bars` parameter on `structural_levels` is **not** an option — AF
rejected it as a fake fix that relocates the hand-matching while making a wrong value look like
recorded provenance. Today `confirmation_bars` must be supplied to `derive_structure_breaks` and matched **by
hand** to the `right_bars` used for detection, and **a mismatch is undetectable** — it silently changes
which level is the reference at every bar, and therefore which breaks and which changes of character
exist. It changes a shipped model (`LevelOrigin` gains a field, and `structural_levels` must populate it),
so it needs its own milestone and ADR. Milestone AE did **not** make it worse — CHoCH takes no
configuration at all — but it also did not fix it, and every layer above will inherit it.

Then, in the order the market-structure architecture review §15 fixed:

- **Trend as a summary of the BOS and CHoCH histories**, consuming both and defining neither. This is the
  last clause of review §15 and is now fully unblocked: both inputs exist, and a test in Milestone AE pins
  that `fmis.structural_trend` currently imports neither, so the new dependency will be a deliberate,
  reviewable widening rather than a drift. What it must decide: whether trend reads changes of character,
  the break sequence, or both; how it reconciles a `StructuralTrendType` derived from swing labels with one
  derived from breaks; and what it reports when the two disagree.
- **Support / resistance candidates** — `PriceLevel`, break history and change-of-character history are now
  the natural vocabulary.
- **Volume Evidence v1b** — still the deferred half of Milestone T.
- **Trading reasoning v1** — first consumer of `TradingAnalysisContext`.

**Known follow-ups from Milestone AE** (each small, none blocking): a **two-sided break bar leaves
character indeterminate**, so no change is claimed at the next break bar — deliberate, since the
alternative is an intrabar claim, and resolving it needs sub-bar data the repository does not ingest (E1);
a change of character is **never invalidated**, so anything wanting "failed CHoCH" builds it over the
sequence (E2); **no trend interaction** exists in either direction, because reconciliation sits above both
(E3); character is the **last break bar only**, not an accumulated run, because accumulation is trend's
idea and `MINIMUM_DIRECTIONAL_SHIFTS` already owns it (E4); and there is **no minimum spacing** between
changes, because a threshold would make historical results unreproducible without its setting (E8).

**Known follow-ups from Milestone AD** (each small, none blocking): the reference level is the **most
recent**, not the most extreme, so a run of lower highs makes each successive lower high the reference
(D5); a break is **never invalidated**, so anything wanting "failed break" builds it over the sequence
(D3); breaks are derived **per side independently**, with no cross-side reading, because that is CHoCH's
job (D6); and the first swing of each type still yields no level (ADR-0019 D2), so the earliest reference
on each side is missing.

**Known follow-ups from Milestone AC** (each small, none blocking): `derive_level_crossings` has **no
activation policy**, so it will report a crossing of a level whose origin is later — deliberate, since
filtering is BOS's decision, but a naive consumer must apply it (D1); `structural_levels` omits the
**first swing of each type**, which has no `StructuralSwing` and therefore no label (2 of 5 points on the
real fixture, D2); event volume is **O(candles × levels)**, so a wide level set over a long series is
large by design; and `GAPPED_BEYOND` versus `ALREADY_BEYOND` is the one distinction an event cannot
self-validate, because it depends on the predecessor the event does not carry (D4).

**Known follow-ups from Milestone AB** (each small, none blocking): the context-free primitives remain
public and cannot tell whether their input came from one series — that is a deliberate compatibility
choice, and the mitigation is that the safe path is now also the easy path; the contract **over-rejects**,
so `" BTCUSDT"` and `"BTCUSDT"` will not combine and anything wanting them unified must normalize before
building candles; and `SeriesIdentity`'s value validation is deliberately no stricter than
`CandleSeries`', so tightening whitespace handling is a breaking change needing its own ADR.

**Known follow-ups from Milestone AA** (each small, none blocking): `MINIMUM_DIRECTIONAL_SHIFTS` is a
**policy no test can validate as correct**, only as correctly implemented — any disagreement with it is a
disagreement about the number and should be argued as such, not by redefining the four members;
persistence is unconditional, so nothing built on top may assume a sustained trend is *recent*; and
`NEUTRAL` and `INDETERMINATE` must never be collapsed by a consumer, because that erases the difference
between a choppy market and a quiet one.

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

- Working tree clean. **Milestone AE is merged locally and deliberately NOT pushed**, so `main` is ahead
  of `origin/main` by the six Milestone AE commits (design, implementation, review — three branches, three
  `--no-ff` merges). Nothing about the milestone is on the remote.
- TradingView MCP workflow is external to the Python package — **zero coupling to `src/`**.
- `pyproject.toml` and `uv.lock` unchanged since Milestone AD; still **zero runtime dependencies**.

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
