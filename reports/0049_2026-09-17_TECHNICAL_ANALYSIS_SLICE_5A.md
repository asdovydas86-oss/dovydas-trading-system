# Report 0049 — Technical Analysis Slice 5A: Recover Technical Context & Feature Series

| Field | Value |
|---|---|
| **Report number** | 0049 |
| **Title** | Technical Analysis Slice 5A — Recover Technical Context & Feature Series |
| **Date** | 2026-09-17 |
| **Report type** | Implementation record (production milestone) |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Baseline commit** | `4d77e4df20d1c97e146dff3d335a243371e8c4d8` (Project Memory & Documentation Gate) |
| **Delivered at commit** | see §24 |
| **Status** | Final |

---

## The milestone in one sentence

**FMITS stopped forgetting what it already knows**, and the Feature Engine can now be asked what a
measurement *has been* rather than only what it *is*.

---

## 1. Verified starting baseline

Every line below was read from the live repository before anything was changed.

| Claim in the brief | Verified? | Evidence |
|---|---|---|
| `HEAD` = `main` = `origin/main` = `4d77e4d` | **Yes** | all three resolve to `4d77e4df20d1c97e146dff3d335a243371e8c4d8` |
| Branch `main`, `0/0` ahead/behind | **Yes** | `git rev-list --left-right --count origin/main...HEAD` → `0 0` |
| Stash empty, no active Git operation | **Yes** | `git stash list` empty |
| 16 untracked research documents, untouched | **Yes** | 15 under `docs/design/`, 1 under `docs/reviews/`. **None was read-modified, and all 16 are still untracked at close** |
| Policy baseline 81 fixtures, 72 `WAIT`, 9 `CANDIDATE` | **Yes** | recomputed independently of the test suite, §12 |
| Aggregate `sha256 8b22e6c9…` | **Yes** | recomputed with report 0045 §11.6's committed formula, §12 |
| Operator instance PID 46403 on `127.0.0.1:8787` | **Yes** | confirmed `LISTEN` by `lsof`. **Never stopped, signalled or requested.** `pkill` was not used at any point |
| `~/.fmits/risk_policy.json` absent | **Yes** | `~/.fmits/` holds only `scan_memory/`. **Not created** |
| Test baseline 14,699 under `-W error` | **Carried, then superseded** | that figure was last *actually run* on 2026-09-07. This milestone changed `src/`, so it was re-established rather than quoted — §18 |

**Discrepancies found: none.** The brief's expected baseline matched the live repository exactly.

---

## 2. Authoritative sources read, in the repository's own order

1. `docs/AI_HANDOFF/START_HERE_FOR_AI.md`
2. `docs/AI_HANDOFF/CURRENT_STATE.md` §0
3. `docs/AI_HANDOFF/CAPABILITY_REGISTRY.md` (all 8 sections)
4. `docs/AI_HANDOFF/daily/2026-09-16.md`
5. `docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md` — **the twelve binding modifications**
6. `reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md` §§2, 7, 8, 9, 10
7. `reports/0048_2026-09-16_PROJECT_MEMORY_AND_DOCUMENTATION_GATE.md`
8. ADRs 0007, 0013, 0016, 0018, 0019, 0020, 0021, 0022, 0023, 0024, 0025, 0028, 0029, 0030
9. `FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`, `reports/README.md`

Then the live code: the Feature Engine and all six features, `pipeline/structural_facts.py`,
`pipeline/multi_timeframe.py`, `swing_setup/compose.py`, `swing_workspace/{models,sections,builder}.py`,
`operator_dashboard/{models,sections,render,server}.py`, `scan_memory/{models,comparison,projection}.py`,
`level_crossing/models.py`, `structure_break/models.py`, `change_of_character/models.py`,
`market_regime/models.py`, `series_context/models.py`, `data/models.py`, and the architecture guards
in `tests/`.

**No conflict between the brief and the live repository was found.** Where report 0047 and the
disposition differ, the disposition was followed (§5, §6).

---

## 3. Live seam audit — re-derived, not copied

The brief required the loss seam to be re-audited in live code rather than taken from report 0047.
The data-flow map, as it stood at `4d77e4d`:

```
fetch_klines ─► CandleSeries.closed()
                     │
                     ├─► FeatureEngine.compute()        ─► FeatureSet          (latest values only)
                     └─► detect_swings ─► label ─► state_history ─► trend
                                       └─► structural_levels ─► derive_level_crossings
                                                              ─► derive_structure_breaks
                                                              ─► derive_changes_of_character
                     ▼
              StructuralFactSheet   (× 3 roles)
                     ▼
              MultiTimeframeFactSheet
                     ├─► regime_for_sheet  (× 3 roles)
                     ├─► build_evidence_report  (SETUP role only)
                     ▼
              build_setup_inputs  ──────►  SetupInputs  ──►  evaluate_setup  ──►  SetupAssessment
                     ▼                                              ▼
              [everything else discarded]                    SetupRunResult
                                                                    ▼
                                                             SymbolDecision  ──►  SymbolDecisionRow  ──►  HTML
```

**Confirmed: `build_setup_inputs` emits twenty-two scalars and two level tuples** from three complete
fact sheets. Report 0047 §7's table reproduced exactly. Nothing had moved since 2026-09-16.

Per candidate fact, the brief's required determination:

| Fact | Computed at | Type | Immutable? | Identity/provenance? | Already consumed? | Dropped at | Does the workspace need it? | Render now? |
|---|---|---|---|---|---|---|---|---|
| `FeatureSet` × 3 | `structural_facts` | `FeatureSet` | yes (frozen + `MappingProxyType`) | symbol, timeframe, `as_of`, per-result metadata | SETUP role only, inside `build_evidence_report` | `build_setup_inputs` | **yes** — it is the indicator layer, absent from every surface | **yes** |
| `structure.crossings` × 3 | `level_crossing` | `tuple[LevelCrossingEvent, …]` | yes, hashable | level + origin + candle + index + kind + mechanism | one integer on `fmits facts` | `build_setup_inputs` | **yes** — the later interaction engine's whole input | **bounded summary only** |
| `structure.changes` × 3 | `change_of_character` | `tuple[ChangeOfCharacter, …]` | yes, hashable | two `StructureBreak`s by reference | a `TRANSITIONING` regime state | `build_setup_inputs` | **yes** | **latest only** |
| `structure.breaks` × 3 | `structure_break` | `tuple[StructureBreak, …]` | yes, hashable | crossing by reference; `eligible_from` projected | execution role only | `build_setup_inputs` | **yes** | **latest only** |
| `structure.levels` (context role) | `structural_facts` | `tuple[PriceLevel, …]` | yes, hashable | `LevelOrigin` with index, timestamp, label, confirmation window | **nothing** | `build_setup_inputs` | **yes** | count + nearest pair |
| `nearest_levels` × 3 | `structural_facts` | `NearestLevels` | yes | the `PriceLevel`s themselves | two rows on `fmits facts` | `build_setup_inputs` | **yes** | **yes** |
| `MarketRegime` (setup, execution) | `swing_setup/compose` | `MarketRegime` | yes | symbol, timeframe, `as_of`, policy, per-dimension evidence | one integer | `build_setup_inputs` | **yes** | three dimensions per role |
| `warming_up` × 3 | `structural_facts` | `tuple[str, …]` | yes | feature names | one integer | `build_setup_inputs` | **yes** | **yes** |
| `window.last_close` × 3 | `structural_facts` | `float \| None` | yes | — | `closed_count` only | `build_setup_inputs` | yes | yes |
| `swings` / `labelled` / `state_history` × 3 | `structural_facts` | tuples of pivots/labels/snapshots | yes | full provenance | counts on `fmits facts` | `build_setup_inputs` | **no — not yet** | **no** |

**The last row is the only one deliberately left behind**, and §21 states why.

---

## 4. Architecture decision for recovered context ownership

**[ADR-0032](../docs/adr/ADR-0032-market-technical-context-carriage.md) — Accepted.**

Report 0047 identified the **seam**. It did not decide the **ownership**, and the review disposition
did not ratify its implementation plan verbatim. This milestone decided ownership before writing any
carriage code.

**The obvious repair was refused.** Adding the recovered facts to `SetupInputs` would have made the
strategy's own input surface the warehouse for all technical analysis — so *what may the policy see*
would stop being answerable by reading one dataclass — and it would have invited a later milestone to
gate on a recovered fact **because it was in scope**, which is precisely the correlated-vote inflation
`CAPABILITY_REGISTRY.md` §3 measures and forbids.

**What was built instead**, generalising the precedent `SetupReadings` set in Slice 1:

```
MultiTimeframeFactSheet ─┬─► build_setup_inputs        ─► SetupInputs ─► evaluate_setup ─► SetupAssessment
                         └─► technical_context_for_sheet ─► MarketTechnicalContext
                                                                   │
                            SymbolDecision  ◄──────────────────────┘   carried, never read by policy
```

* `SetupInputs` gained **no field**. `evaluate_setup` is untouched byte for byte.
* Owner: **`fmis.pipeline`**, which already owns both fact-sheet types (ADR-0022, ADR-0023). No new
  top-level package; a `fmis.technical_analysis` was considered and rejected as a second composition
  root holding one projection.
* The module inherits the composition-root discipline: **a test asserts it contains no arithmetic
  operator at all**, the same guard `structural_facts` and `multi_timeframe` hold.
* Canonical objects are carried **by reference**, not converted. That is what *lossless* has to mean
  here: an integer count cannot answer *which level, when, how far, how it arrived*, which is exactly
  what a later interaction engine needs.
* **Roles are never blended.** No agreement flag, no alignment count — `MultiTimeframeFactSheet`'s
  load-bearing refusal, inherited verbatim.

---

## 5. Feature-series protocol decision

**[ADR-0031](../docs/adr/ADR-0031-feature-series-contract.md) — Accepted.** Closes review item **R5,
open since 2026-07-24**, on the footing the [0047 disposition](../docs/reviews/REPORT_0047_REVIEW_DISPOSITION.md)
§C and D4 approved: **additive**, with `compute()`, every feature name, every seeding convention and
every metadata key unchanged.

Report 0047 §8 observed that `FeatureValue` already permits `Sequence`, so *"no contract change is
needed"*. **That observation is true and it is not sufficient**, and saying so is the substance of
the ADR. A bare list answers none of: which candle is element 0; where warm-up ends; whether a `None`
means *not yet* or *not defined here*; which symbol and timeframe this is. Each reconstruction is a
place for a caller to be off by one — the class of defect `LevelOrigin.knowable_from` and
`StructureBreak.eligible_from` exist to make impossible.

The shape, and the nine properties it holds, are in ADR-0031 §§2–7. The three that most earned their
place:

* **Warm-up is never backfilled.** A position before the first defined one carries **no point at
  all** — not `None`, not zero, not the seed.
* **A point carries a value *or* an `undefined_reason`, never both and never neither.** So *not
  warmed up* / *undefined here* / *computed* stay three distinguishable facts. `RelativeVolume` over
  an all-zero baseline is the live case, and dropping that position would have shortened the history
  and shifted nothing else — the worst available failure, because every later index would still look
  plausible.
* **One mathematical implementation.** Each indicator's arithmetic lives in exactly one pure helper
  producing the whole series in one pass, and `compute()` takes its last element. Parity is therefore
  **bit-identical by construction** and is asserted per feature with no tolerance.

**Deliberately not built: an engine-level `compute_series`.** `FeatureEngine.compute` threads each
feature's *latest* result into the next feature's context; threading latest values into a historical
computation injects lookahead produced by the orchestration rather than by any feature. No feature
declares a dependency today, so nothing is blocked. A test asserts the method's absence, so adding
one is a deliberate act with a dependency semantics attached.

---

## 6. The twelve required modifications — compliance

| # | Requirement | This milestone |
|---|---|---|
| **A** | Opportunity ≠ Strategy | No opportunity state exists. None was created |
| **B** | `MissingConfirmation` ≠ policy `Blocker` | Neither was touched; no new state was introduced |
| **C** | `compute_series()` **precedes** ATR-based zone width | **Satisfied.** It landed here, before any zone engine exists |
| **D** | Zone evidence independence NOT established | No zone, and no independence claim, anywhere |
| **E** | Support/resistance from interaction history, never position | **Enforced in code and in a rendered-output scan.** The page says *nearest structural level above/below*, and a test refuses the words with one denial sentence carved out and asserted separately |
| **F** | Do not freeze phase segmentation | No phase exists |
| **G** | Do not freeze the trendline anchor rule | No trendline exists |
| **H** | Divergence alignment not frozen | No divergence exists. The panel states that none is computed |
| **I** | Fibonacci: research first, no implementation | 0 occurrences under `src/` |
| **J** | Elliott: deferred, no implementation | 0 occurrences under `src/` |
| **K** | Correlated indicators ≠ independent confirmation | **The sharpest test of this milestone.** Six indicator readings per role now reach the page; **none is an evidence family, a vote or a lean**, and the page says so |
| **L** | Primitives before patterns | No pattern exists |

---

## 7. Files and packages changed

**New production modules (6):**

| File | Lines | What it is |
|---|---|---|
| `src/fmis/features/series.py` | 274 | `FeatureSeries`, `FeatureSeriesPoint`, `SeriesFeature`, `supports_series` |
| `src/fmis/features/indicators/wilder_math.py` | 43 | Wilder smoothing — the single source, shared by ATR and RSI |
| `src/fmis/features/indicators/atr_math.py` | 71 | true ranges + the ATR series |
| `src/fmis/features/indicators/rsi_math.py` | 81 | gains/losses, the zero policy, the RSI series |
| `src/fmis/features/indicators/macd_math.py` | 51 | the MACD line and the signal over it |
| `src/fmis/pipeline/technical_context.py` | 432 | `MarketTechnicalContext`, `TechnicalContextView`, `CrossingHistory` |

**Modified production modules (17):** the four indicators and both volume features (each gains
`compute_series`, with `compute` re-pointed at the shared helper and its output unchanged);
`volume_math` (one arithmetic site, plus the series form); `swing_setup/compose.py` (+159/−25 — two
new composition functions, three existing ones become thin wrappers, `SetupRunResult.technical`);
`swing_workspace/{models,sections}.py` (+28); `operator_dashboard/{models,sections,render}.py`
(+642); and five `__init__.py` export lists.

**New tests (7 files, 2,825 lines):** `test_feature_series.py`, `test_feature_series_performance.py`,
`test_technical_context.py`, `test_technical_context_carriage.py`,
`test_swing_technical_context_surface.py`, `test_scan_memory_technical_context_isolation.py`, and
`feature_series_helpers.py`.

**Modified tests (2):** `test_features_volume.py` (the volume package's import allowlist, widened
downward with the reason stated — §9) and `test_swing_operator_summary.py` (one positional panel
assertion converted to the relation its own docstring already said it should be — §9).

---

## 8. Public contracts added and changed

**Added — `fmis.features`:** `FeatureSeries`, `FeatureSeriesPoint`, `SeriesFeature`,
`supports_series`. Six features gained `compute_series`.

**Added — `fmis.pipeline`:** `MarketTechnicalContext`, `TechnicalContextView`, `CrossingHistory`,
`technical_context_for_sheet`, `TECHNICAL_CONTEXT_LIMITATIONS`.

**Added — `fmis.swing_setup`:** `setup_composition_for_sheet`, `setup_analysis_for_symbol`;
`SetupRunResult.technical`.

**Added — `fmis.swing_workspace`:** `SymbolDecision.technical` (typed `Any`).

**Added — `fmis.operator_dashboard`:** `TechnicalContextRow`, `StructuralLevelRow`,
`CrossingEventRow`, `StructureEventRow`, `FeatureReadingRow`, `technical_context_rows`;
`SymbolDecisionRow.technical`.

**Changed:** nothing. No existing name, signature, return type or field was altered or removed.

---

## 9. Backward compatibility

* **Every existing entry point keeps its exact signature and result.**
  `setup_assessment_for_sheet`, `setup_inputs_and_assessment_for_sheet`,
  `setup_reading_and_assessment_for_symbol`, `setup_for_symbol` and `run_setup_for_symbols` are
  unchanged to every caller; the first four are now thin wrappers that drop the new element, the
  arrangement `compose.py` itself introduced in Slice 1. A test asserts the wrapped results are equal
  to the composed ones.
* **`Feature.compute()` is byte-identical in output** — value and metadata — for all six features,
  proven by the unchanged policy digest and by the pre-existing hand-calculated tests in
  `test_{ema,atr,rsi,macd}.py` and `test_features_volume.py`, none of which was modified.
* **Every new field is additive and defaulted**, so every hand-built `SetupRunResult`,
  `SymbolDecision` and `SymbolDecisionRow` in the suite stays valid unchanged.
* **`BaseFeature` gained nothing**, so a feature with no meaningful history stays a valid `Feature`.

**Two existing tests were changed, both deliberately and both narrowly.**

1. `test_features_volume.py::test_volume_package_imports_only_feature_types_and_its_own_kernel` —
   the allowlist gained `fmis.features.series` (the sibling vocabulary module, same tier as
   `fmis.features.types`) and `fmis.data` (`Candle`, `SeriesIdentity` — **not a new dependency in
   substance**: `fmis.features.types` already imports `CandleSeries` from there, so the package
   always depended on it transitively). **Both entries are at or below this package's own tier**, and
   the assertions that carry the layering — no `fmis.pipeline`, no `fmis.decision_support`, no
   sibling engine — are untouched and still pass.
2. `test_swing_operator_summary.py::test_the_symbol_page_puts_the_summary_above_the_audit` — one
   positional assertion (`panels[2] == "… directional families"`) became an ordering relation. **That
   test's own docstring already said it should be**: it records that pinning a fixed list failed once
   before, when Slice 4 inserted the risk panel, and that the invariant is *decision first, audit
   last*. The relation now asserted is the whole hierarchy.

**Four architecture guards fired and were obeyed rather than widened.**
`test_{change_of_character,level_crossing,market_regime,structural_trend}` each scan every module
outside their permitted consumers for the **text** of their package name. They fired on *docstrings*
in `operator_dashboard/models.py` and `swing_workspace/models.py` that credited the producing engines
by module path. The dashboard and the workspace import none of those packages and must not; the
guards were right and the prose was wrong. The attributions were reworded to name the engines without
spelling their module paths — the restraint `render.py`'s `_state_cell` already documents. **No guard
was relaxed.**

---

## 10. Product surface change

One new panel on `/swing/SYMBOL`, placed **after** the decision layer and **before** the evidence
audit: `{SYMBOL} — technical context`.

**Scannable first, deep second**, because the owner's own report is that dense technical text is hard
to scan:

* **One table row per timeframe role** — role, interval, structural trend, regime in three
  dimensions, nearest structural level above, nearest structural level below. Six facts an operator
  reads in seconds, for 1W, 1D and 4H at once.
* **One `<details>` disclosure per role**, folded shut, holding the last closed price, the level
  counts each side, the crossing count, the latest crossing, the latest close beyond a level, the
  latest break of structure, the latest change of character **with the break it changed from**, the
  bar count, what is still warming up, and every indicator reading under the engine's own name.
* **A closing note that states the refusals in the operator's own words** rather than leaving them
  implied.

**The scanner page `/swing` is unchanged.** Nothing was added to it; its concise role is preserved.

**No raw event flood.** A role carries thousands of crossings and the page renders two of them plus a
truthful count. A test asserts the whole panel holds fewer than 60 table rows while the underlying
runs hold more than 100 events.

---

## 11. Examples of recovered context — the acceptance cases

**Fixture-backed and stated as such.** These are deterministic synthetic candles from
`tests/archive_helpers.multi`, not live market data, and no claim is made about any real market.

**`BTCUSDT`, seeds (1, 5, 9) — policy decision `WAIT`:**

| Role | Interval | Structural trend | Regime | Levels | Crossings | Breaks | CHoCH |
|---|---|---|---|---|---|---|---|
| context | 1w | `neutral` | `indeterminate` / `steady` / `subdued` | 97 (47↑/50↓) | 4,015 | 6 | 2 |
| setup | 1d | `sustained_higher` | `transitioning` / `steady` / `subdued` | 93 (48↑/45↓) | 3,793 | 4 | 3 |
| execution | 4h | `sustained_lower` | `trending` / `steady` / `typical` | 100 (51↑/49↓) | 4,214 | 3 | 2 |

Context role, in full: nearest level above `103.5607…`, nearest below `98.0361…`; latest close beyond
a level at `98.0361…` on 2026-02-13 00:00Z (`within_range`); latest break of structure `lower` at
`96.0025…` on 2026-02-11 08:00Z; **latest change of character `upper` → `lower` on 2026-02-05
08:00Z**; readings `ema_20=99.7951 · ema_50=99.9457 · ema_200=100.0263 · rsi_close_14=53.1642 ·
atr_14=7.4290 · atr_50=7.4579 · macd_close_12_26_9=[line −0.2193, signal −0.2001, hist −0.0192] ·
relative_volume_20=0.5989`; nothing warming up.

**`ETHUSDT`, seeds (3, 4, 7) — policy decision `WAIT`:** carries a change of character in the
**opposite** direction on its setup role (`lower` → `upper`, 2026-02-07 04:00Z) beside `upper` →
`lower` ones on the other two, which is the symmetry evidence §14 relies on.

**Every item the brief's §19 acceptance list names is present**: a symbol with a CHoCH (both, on
every role), structural levels, crossing history, all three timeframe roles, and current `FeatureSet`
values with availability. §20 records the same panel rendering against **live** market data.

---

## 12. Policy non-regression — the hard gate

Recomputed **outside** the test suite, using the formula report 0045 §11.6 committed:

```python
sha256(b"".join(repr(setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol))).encode()
                for key, seeds, symbol in _matrix()))
```

| | Before (`4d77e4d`) | After |
|---|---|---|
| **Fixtures** | 81 | **81** |
| **States** | 72 `WAIT` · 9 `CANDIDATE` | **72 `WAIT` · 9 `CANDIDATE`** |
| **Aggregate** | `8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c` | **`8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c`** |

**Identical.** Run three times across the milestone — before any change, after the feature-series
refactor, and after the carriage — and again on cleared bytecode. The per-fixture table in
`tests/test_swing_setup_policy_non_regression.py` (162 digests) is **unchanged and passes**; that
file was not edited.

`evaluate_setup` was not modified. `SetupInputs` gained no field. **A probe that made the composition
consult a recovered crossing count was killed by this gate** (§19, probe 16).

---

## 13. Series correctness matrix

`tests/test_feature_series.py` — **234 tests**, every row of the brief's §21 matrix, across all six
series-capable features.

| # | Property | How it is asserted |
|---|---|---|
| 1 | latest-value parity | `compute(ctx).value` **equals** the final point, exactly, no tolerance, per feature — and both report an absence under the same conditions |
| 2 | warm-up boundary | `w−1` → zero points; `w` → exactly one point, at index `w−1`; `w+1` → exactly two |
| 3 | prefix stability | a prefix of the same candle objects yields equal values at every shared index |
| 4 | no lookahead | appending a candle only **appends** points; the existing prefix is equal object for object |
| 5 | identity and provenance | `SeriesIdentity` carried; two symbols give unequal series; parameters and producer survive in metadata; metadata is read-only |
| 6 | parameter variation | five pairs of differing parameters give different names, warm-ups and points; a non-default `source` changes the values, not only the name |
| 7 | empty and short input | an absence with `as_of=None`; 1/2/3 candles raise nothing and guess nothing |
| 8 | malformed input | a non-finite price is refused by `Candle` and can never reach a series; every emitted value is finite |
| 9 | structured values | MACD emits its three-component mapping at **every** point, in order, immutably |
| 10 | determinism | two calls equal; two equal inputs equal |
| 11 | closed-candle semantics | appending a forming bar changes nothing at all |
| 12 | alignment | every point's timestamp **is** its own candle's; points are contiguous from `first_index` |
| + | three states | no point / point with a value / point with an `undefined_reason`, all distinguishable |
| + | additive compatibility | every feature still satisfies `Feature`; `BaseFeature` demands no history; the engine grew no series method; `default_features()` did not grow |

**Alignment is also pinned independently of the pairing expression** — and that test exists because a
probe found the hole (§19).

---

## 14. Symmetry and bias checks

* **Structural**: every field naming one side of the market has an exact mirror naming the other
  (`nearest_above`/`nearest_below`, `upper_level_count`/`lower_level_count`), asserted as a set
  equality so a field with no partner fails.
* **Vocabulary**: `TechnicalContextView` is asserted to hold no `direction`, `lean`, `bias`, `score`,
  `rank`, `opportunity`, `confidence` or `signal` field. The repository-wide directional guard covers
  both new packages and passes.
* **Data**: the acceptance fixtures carry changes of character in **both** directions (`upper`→`lower`
  and `lower`→`upper`), and a test asserts the two markets produce the same shape — neither run gets
  a field or a populated collection the other does not.
* **Presentation**: the panel applies **no colour, accent or emphasis** to any directional value.
  Trend, regime and side all render as the engine's own text. No new colour class was added to the
  theme.
* **Language**: `upper` and `lower` are used throughout; no phrasing treats one side as interesting
  and the other as a warning.

---

## 15. Scan Memory compatibility

`tests/test_scan_memory_technical_context_isolation.py` — **9 tests**. The recovered context reaches
Scan Memory **not at all**, asserted four independent ways:

* the projected `SymbolState` is **equal field for field** with and without a context;
* the compared dimension values are equal, and `transitions_between` reports **zero** transitions in
  both directions;
* `CHANGE_DIMENSIONS` is still exactly the twelve Slice 3 named, and `SymbolState` holds no field a
  recovered fact could arrive in;
* `scan_memory/projection.py` never reads the attribute at all, asserted at source level;
* **the whole persisted `ScanRecord` is equal** with and without a context.

**Existing history stays readable.** A record projected from results that predate the field is written
to an isolated `tmp_path` store and read back equal; a record from a context-bearing workspace
round-trips through the same codec.

**`~/.fmits/scan_memory` was never opened, written or reset.** Every store in the suite is a
`tmp_path`, and the live directory was inspected read-only at the start and confirmed unchanged at the
end.

---

## 16. Import and DAG validation

* **`fmis.pipeline.technical_context` imports** `fmis.change_of_character`, `fmis.features`,
  `fmis.level_crossing`, `fmis.market_regime`, `fmis.pipeline.multi_timeframe`,
  `fmis.structural_trend`, `fmis.structure_break` — all strictly below it, none above.
* **It is imported by exactly two modules**: `fmis.pipeline` (its own `__init__`) and
  `fmis.swing_setup.compose`.
* **No engine imports a composition root.** `fmis.swing_workspace` gained no import (the context is
  `Any`); `fmis.operator_dashboard` gained no import (rows are built from attributes).
* **Module-level cycles across the whole tree, excluding the one declared outermost edge
  (`pipeline/cli.py`): exactly one**, `paired_dependence.estimator ↔ paired_dependence.uncertainty`
  — **pre-existing since Milestone CD (`1a133b1`)** and in a file this milestone did not touch.
* **The tier partition is intact**: no top-level package was added, so
  `assert_tier_partition_is_complete` needed no edit and passes.
* **`fmis.features` gained five submodules**, none of which collides with a name in `__all__` — the
  repository-wide collision guard passes.

---

## 17. Performance and memory, measured

**Feature series** (`tests/test_feature_series_performance.py`, best of seven per point):

| Closed candles | 7 series-capable features |
|---|---|
| 200 | 0.69 ms |
| 500 | **1.94 ms** ← the production window |
| 1,000 | 4.20 ms |
| 2,000 | 8.47 ms |

**Linear.** Doubling the input doubles the time. Asserted as *cost per emitted point stays flat* —
which a quadratic cannot satisfy — measured over the sizes where each feature is warmed up enough for
the ratio to describe the algorithm rather than the warm-up. (EMA(200) emits **one** point at 200
candles, so a ratio taken there measures the fixed cost; the test names that and excludes it.)

**Carriage**, per symbol over a three-role 260-bar sheet:

| Quantity | Measured |
|---|---|
| Objects referenced per symbol | 12,356 (290 levels · 12,022 crossings · 13 breaks · 7 changes · 24 feature results) |
| Referenced or duplicated? | **Referenced** — asserted with `is`, not `==`. Nothing is copied |
| Projection memory | **0.9 KiB per symbol** → ~19 KiB across a 20-symbol watchlist |
| Building the three-view sheet | 20.6 ms |
| The projection on top of it | **0.208 ms — about 1 %** |
| Row translation (1 symbol) | 0.166 ms |
| Technical panel render | 0.093 ms, **9,652 bytes** |

Across the 20-symbol watchlist the projection adds roughly **4 ms of compute and 19 KiB of memory**,
against a provider fetch report 0047 measured at ~38 s. `derive_level_crossings` was **not** touched;
report 0047 §10.3's finding stands unchanged and un-acted-on, as the brief required.

---

## 18. Full suite

Run on **cleared bytecode**, with no other pytest process alive and the operator instance untouched:

```
.venv/bin/python -m pytest -q -W error -p no:cacheprovider
```

```
15092 passed in 708.10s (0:11:48)
EXIT=0
```

**15,092 passed · 0 failed · 0 skipped · 0 warnings.** Baseline moves from **14,699** at `66bab74`
to **15,092** — **+393**, every one of them new. **Reliability Gate: 9/9**
(`tests/test_operator_dashboard_startup_smoke.py`, unchanged).

One operational note, recorded because report 0047 §2.1 recorded the same class of thing: this
repository has **no bare `python` on `PATH`**, and `.venv/bin/python` is the only correct interpreter.

An earlier run of the same suite reported **5 failures**, all four import-boundary guards plus the
panel-ordering assertion. All five are recorded in §9 with what was done about each: four guards were
**obeyed** and the prose corrected; one test's positional assertion became the relation its own
docstring specified.

---

## 19. Targeted adversarial testing — and the bug it found in the campaign itself

Seventeen surgical probes, each expressing one dangerous mistake this milestone could make. A probe
that no test kills is a hole in the test suite.

**Result: 17/17 killed. Source restored byte-identically** (`sha256` over every `.py` under `src/fmis`
equal before and after).

| Probe | Killed by |
|---|---|
| EMA points shifted one bar later | series matrix (alignment) |
| ATR points shifted one bar earlier | series matrix (alignment) |
| RSI claims one candle less warm-up than it needs | series matrix (warm-up boundary) |
| **MACD signal paired one position off** | **the alignment test this probe caused to be written** |
| ATR `compute` diverges from the series | series matrix (parity) + `test_atr.py` |
| Volume baseline window includes the bar it describes | series matrix (no lookahead) |
| The zero-baseline point is dropped instead of reported | series matrix (three states) |
| A seed point emitted before the first valid bar | series matrix (warm-up) |
| The context reads one role's regime for another | technical-context + carriage matrices |
| Every view gets the first view's levels | technical-context + carriage matrices |
| Only the last ten crossings are carried | carriage matrix (event identity) |
| The latest close breach becomes the first one | technical-context matrix (selection) |
| A warming-up reading reports zero | carriage + surface matrices |
| A close breach is rendered as a breakout | surface vocabulary scan |
| The nearest level below is rendered as *Support* | surface vocabulary scan |
| **The composition consults a recovered crossing count** | **the policy non-regression digest** |
| The context leaks into a Scan Memory dimension | scan-memory isolation |

**The first run reported 16/17, and the survivor was real.** The MACD pairing probe survived because
`compute` and `compute_series` **share** the expression that pairs a line element with a signal
element — which is the design, and is what makes them one arithmetic — so a shift moves both together
and latest-value parity, prefix stability and the histogram's internal consistency all keep passing
while every point describes the wrong bar. Two tests were added that derive the expected value **from
the prices at that bar**, through the shared EMA helper and none of the pairing logic, and the probe
is now killed.

### 19.1 A stale-bytecode hazard, recorded because it nearly produced a false report

Investigating that survivor turned up something worth writing down.

A probe that replaces a substring with one of the **same length** leaves the restored file the same
size. CPython invalidates `.pyc` on **`(mtime, size)` at one-second resolution** — so a
mutate → test → restore cycle completing inside one second leaves a **stale mutated `.pyc` behind a
correct source file**. `inspect.getsource` reads the *source* and cheerfully showed the restored code
while the interpreter executed the mutation.

Consequences, all real and all caught:

* the MACD probe's "survival" was partly an artefact — the mutation was still live in bytecode while
  the follow-up investigation ran;
* **every probe after it ran against a silently mutated MACD**, so their kills were not trustworthy;
* a `sha256` over `src/**/*.py` said `RESTORED EXACTLY` and was **true and insufficient**.

The campaign was rewritten to run every subprocess with `PYTHONDONTWRITEBYTECODE=1` and to clear every
`__pycache__` before each probe, and was re-run from scratch — **17/17, digest identical**. The full
suite was then re-run on cleared bytecode, and the policy digest recomputed on cleared bytecode.

**The rule this establishes**, recorded in `CURRENT_STATE.md` §0.1 so it is not relearned: *never run
a mutation campaign that writes bytecode, and never let a digest of `src/` alone stand as proof that a
campaign is over.*

---

## 20. Live dashboard verification

Performed on the **development port 8799**, in a process this session started and stopped by its own
handle. **The operator's instance was never stopped, signalled or requested**, and `pkill` was not
used at any point.

```
8787 before:  PID 46403  127.0.0.1:8787 (LISTEN)     ← the owner's, untouched
8799 before:  nothing listening
8799 during:  PID 96932  127.0.0.1:8799 (LISTEN)     ← this session's
8799 after:   nothing listening
8787 after:   PID 46403  127.0.0.1:8787 (LISTEN)     ← unchanged
```

**Eleven routes, real sockets, real Binance data.** The first request pays the refresh, as designed;
the rest are served from the held snapshot.

| Route | Status | Bytes | Time |
|---|---|---|---|
| `/` | 200 | 27,137 | 32.35 s *(the refresh)* |
| `/markets` | 200 | 31,133 | 0.00 s |
| `/swing` | 200 | 37,260 | 0.00 s |
| **`/swing/BTCUSDT`** | 200 | **49,434** | 0.00 s |
| **`/swing/ETHUSDT`** | 200 | **50,040** | 0.00 s |
| **`/swing/SOLUSDT`** | 200 | **49,283** | 0.00 s |
| `/portfolio` | 200 | 12,154 | 0.00 s |
| `/paper` | 200 | 12,067 | 0.00 s |
| `/performance` | 200 | 12,024 | 0.00 s |
| `/system` | 200 | 25,600 | 0.00 s |
| `/swing/NOTONTHELIST` | 200 | 12,005 | 0.00 s |

**Eleven requests, one refresh.** `holder.refresh_count == 1` — the shared-snapshot guarantee is
intact, so every panel on every page describes the same instant.

**Confirmed on all three live symbols:**

* the **technical context panel is present**, with all three roles and all three intervals;
* the panel order is **decision → timeframe context → technical context → evidence audit**, so the
  operator decision layer still comes first and the audit still comes last;
* **the refused vocabulary does not appear in the panel** — `support`, `resistance`, `breakout`,
  `retest`, `reclaim`, `rejection`, `acceptance`, `divergence`, `trendline`, `fibonacci`, `elliott`,
  `bullish`, `bearish`, `watch`, `score`, `confidence`, `probability`: **none**;
* the panel's **denial sentence is present** on the live page;
* an unknown symbol still renders *"produced no assessment on this refresh"*;
* **no `WATCH` state anywhere**, no policy outcome change, no risk configuration dependency.

**A recorded honesty note about that scan.** Run over the *whole* page, `confidence`, `probability`
and `score` do appear — in **denial prose written by Slices 1–4**: *"Nothing here is a probability, a
confidence or an expected return"*, *"Counts of evidence items are counts, not a score"*. Those
sentences pre-date this milestone, are asserted by that milestone's own tests, and the first run of
this verification flagged them because it scanned the whole page rather than the section under test.
The scan was corrected to scope the assertion to the panel and to **report** the rest rather than
silence it. Nothing was widened to make a check pass.

**Live technical context, `BTCUSDT`, read from the rendered page** (real market, 2026-09-17):

```
Role        Interval  Structural trend  Regime                          Nearest above                Nearest below
HTF context 1w        neutral           transitioning/steady/subdued    80600.0  (lower low,          76606.0  (lower low,
                                                                          2025-11-17)                   2025-03-10)
setup       1d        sustained_lower   transitioning/steady/typical    76264.0  (lower low,          76051.0  (lower low,
                                                                          2026-09-02)                   2026-05-18)
execution   4h        sustained_lower   trending/steady/subdued         76500.0  (higher low,         76464.0  (lower low,
                                                                          2026-08-22 04:00Z)            2026-09-10)
```

`ETHUSDT` and `SOLUSDT` render the same shape with their own values — including a **weekly
`sustained_higher` on ETH against a weekly `neutral` on BTC and SOL**, which is the multi-timeframe
disagreement `SPEC` §5 says must be visible rather than collapsed.

**Repeated GET does not mutate Scan Memory.**

```
history before:  8 records, digest f91f68c86a181631…
  11 page loads
history after:   8 records, digest f91f68c86a181631…     ← identical
```

**`~/.fmits/risk_policy.json` still absent.** No capital was declared, inferred or written.

**The dashboard performs no market calculation.** Asserted at source by the pre-existing architecture
guards (487 of them, all passing), and structurally by
`tests/test_technical_context_carriage.py::test_the_renderer_needs_no_recomputation_to_show_any_of_it`,
which walks every field of every technical row and fails if any of them is an engine object rather
than a primitive.

---

## 21. Known limitations

1. **`swings` / `labelled` / `state_history` are still not carried.** They are the *inputs* to facts
   that are: levels derive from the labelled swings, the structural trend from the state history.
   Carrying them would have widened the contract for no current or named consumer. Revisit when a
   deterministic engine needs pivot-level detail — Price Phases plausibly will.
2. **The evidence report is still built for the SETUP role only.** Report 0047's seam 2 is untouched.
   The 1W and 4H `FeatureSet`s are now *visible*, and they are still never *classified*. Closing that
   is an evidence-family decision, not a carriage one, and §3 of the registry constrains it.
3. **Indicator readings are the latest closed-candle values.** `compute_series()` exists; nothing on
   any surface consumes it yet. That is deliberate — it is infrastructure here.
4. **The technical context is not persisted and not archived.** It is recomputed per refresh, which
   is correct while it is a pure projection and would need an ADR if it ever were not.
5. **Crossing counts are large and are presented as counts.** A count is a size, never a strength. A
   level touched many times is not thereby a strong level; that reading needs interaction semantics
   this repository does not have.
6. **`derive_level_crossings` is still effectively quadratic in candles** (report 0047 §10.3). Not
   touched, as the brief required. Invisible at the 500-bar production window; real under replay.
7. **The fixture views all use 4-hour candles** with the requested intervals labelled `1w`/`1d`/`4h`.
   That is the pre-existing shape of `tests/archive_helpers`, not something this milestone introduced,
   and the live verification in §20 uses real per-interval data.
8. **No warning is issued when a role's data is old.** Per-role instants and ages are stated and no
   threshold is applied — the Slice 1 refusal, unchanged: no validated staleness bound exists.

---

## 22. Explicit non-goals — what FMITS still cannot claim

**After TA Slice 5A, FMITS still cannot truthfully claim to detect:**

* support or resistance **zones** — no zone, clustering, width policy, tolerance, touch count or
  lifecycle exists anywhere;
* **breakout** — a close beyond a level is a close beyond a level; `close > level` is explicitly not
  an acceptable definition of anything;
* **acceptance** · **rejection** · **retest** · **reclaim** · **false breakout** — no interaction
  vocabulary exists;
* **consolidation** · **impulse** · **retracement** · **range** — no phase primitive exists;
* **bull flag** · **bear flag** · double top/bottom · head & shoulders · triangles · wedges — no
  pattern engine exists;
* **divergence** — no price/oscillator divergence engine exists;
* **trendlines** · **channels** — 0 files;
* **Fibonacci** · **Elliott** — 0 occurrences under `src/`;
* **`WATCH LONG` / `WATCH SHORT`** — no opportunity state exists, and naming a side outside
  `fmis.swing_setup` remains an ADR-0028 decision nobody has taken;
* **EMA slope** · **MACD histogram acceleration** · **RSI recovery** · **volume contraction** ·
  **ATR compression** — every one is now *derivable* and **none is derived**.

**This is not failure.** 5A builds the trustworthy data boundary those capabilities will consume, and
the last bullet is the point: the data arriving is not authorisation for the vocabulary. A rendered
output scan enforces that, across three markets, with the page's single denial sentence carved out and
asserted separately so deleting it fails a test.

---

## 23. Capability registry changes

| Capability | Was | Now |
|---|---|---|
| `compute_series()` | **`MISSING`** — the prerequisite blocking four capabilities | **`IMPLEMENTED`** (ADR-0031), six features |
| Level crossings (nine-way) | **`PRODUCT_UNREACHABLE`** | **`IMPLEMENTED`** — full run per role, bounded summary rendered |
| Change of character | **`PRODUCT_UNREACHABLE`** | **`IMPLEMENTED`** — full run per role, latest rendered with its predecessor |
| Break of structure | `IMPLEMENTED` (execution role only above `facts`) | **`IMPLEMENTED`** — all three roles |
| Market regime | `IMPLEMENTED` (context role; setup/execution `PRODUCT_UNREACHABLE`) | **`IMPLEMENTED`** — all three roles |
| `FeatureSet` × 3 roles | **`PRODUCT_UNREACHABLE`** | **`IMPLEMENTED`** — per role, with warm-up stated |
| Context-role levels · setup-role breaks · nearest levels · `warming_up` | **`PRODUCT_UNREACHABLE`** | **`IMPLEMENTED`** |
| `swings`/`labelled`/`state_history` | `PRODUCT_UNREACHABLE` | **`PRODUCT_UNREACHABLE`** — deliberately, with a revisit trigger |
| `AverageVolume` | `DORMANT` | **`DORMANT`** — gained a history, **not** promoted into `default_features()` |
| Zones · phases · patterns · divergence · trendlines · opportunity | `MISSING` / `DEFERRED` | **unchanged**, with their `compute_series()` prerequisite now satisfied |
| Fibonacci | `CANDIDATE` / research first | **unchanged** |
| Elliott | `DEFERRED` / hypothesis-only | **unchanged** |

Registry §2.2 — *"the most important section in the file"* — is now a record of a **closed** gap.

---

## 24. Git, commit and push state

<<GIT>>

---

## 25. Exact next recommended milestone

> ### TA Slice 5B — Price Zones & Interactions

**It is blocked, and the blocker is an owner decision, not engineering.**

| Prerequisite | State |
|---|---|
| **0047 D1** — zone-width tolerance policy, a scoped weakening of ADR-0013 §4's no-tolerance rule | **OPEN. Blocking.** Only the owner can take it |
| **0047 D2** — may a zone carry a role, and what may it be called | **Partly settled.** The *derivation* rule is fixed (interaction history, never position); the *naming* is open |
| Historical ATR at a zone's establishment point | **Satisfied** by this milestone. Note that the prerequisite existing is not a recommendation to use it |
| Deterministic interaction semantics · non-repainting design · a product consumer | Design work for that slice |

**Do not start 5B without D1.** A zone engine written against an un-decided width policy would bake
an invented threshold into deterministic market truth, which is the one thing this repository has
consistently refused.

---

## 26. Unresolved decisions for Slice 5B and beyond

| ID | Decision | Blocks | State |
|---|---|---|---|
| **0047 D1** | Zone-width tolerance policy | **TA Slice 5B** | **Open — owner** |
| **0047 D2** | May a zone carry a role, and what may it be called | TA Slice 5B | Derivation fixed; naming open |
| **0047 D3** | Where opportunity state lives; may it name a side (ADR-0028) | Market Opportunity | Open |
| **0047 D5** | Do the three evidence-status vocabularies converge | — | Open; 0047 recommends **no** |
| **AP-D2** | Capture contract and migration guarantee | **before the first irreplaceable trading record** | Open |
| **D-03** | Availability-time model (ADR-0003) | all macro/news/fundamental/vintage backtesting | Open |
| **New (5A)** | Should the evidence report be built for all three roles? The 1W and 4H `FeatureSet`s are now visible and still never classified. **Constrained by registry §3** — more indicators add no independence | Indicator Context | **Open — raised by this milestone** |
| **New (5A)** | Should `swings`/`labelled`/`state_history` be carried? Not needed by any current or named consumer | Price Phases, possibly | **Open — raised by this milestone** |
| — | **The owner's capital declaration** | risk sizing as a product capability | Open |

---

## WHAT THE OPERATOR CAN DO NOW THAT THEY COULD NOT DO BEFORE

Open `/swing/BTCUSDT` and, **for the first time, see what this system already knows about that
market** — per timeframe role, without opening a chart and without the system recomputing anything:

* **the weekly, daily and four-hour structural trend and market regime side by side** — the setup and
  execution regimes existed on every scan and reached the operator as a single integer;
* **the nearest structural level above and below the last close, on every role**, each with the
  confirmed swing it came from and when that swing occurred — the weekly levels reached **nothing at
  all** before today;
* **whether a change of character has occurred, when, and from which break** — CHoCH had been
  computed on every scan since Milestone AH and had never been visible as an event;
* **the latest level crossing and the latest close beyond a level**, in the engine's own nine-way
  classification, out of a history of thousands that is kept and not rendered;
* **the latest break of structure on all three roles**, not just execution;
* **every indicator value the system computes, on every timeframe** — EMA 20/50/200, RSI, ATR, MACD's
  three components, relative volume — which reached **no operator surface whatsoever** before this
  milestone;
* and **which readings are still warming up**, stated as such rather than shown as a blank.

The decision layer above it is unchanged, and so is the decision. A `WAIT` is still a `WAIT` — but it
is now a `WAIT` an operator can *read the market behind*.

Underneath, the system can now be asked **what a measurement has been**, not only what it is. Nothing
uses that yet, and that is the correct state for it to be in today.

## WHAT FMITS STILL CANNOT CLAIM

Everything in §22. Most sharply: **the data becoming visible is not authorisation for the
vocabulary.** FMITS can now show you the close that went beyond a level. It still cannot tell you that
was a breakout, and it will not pretend otherwise until an engine exists that has earned the word.
