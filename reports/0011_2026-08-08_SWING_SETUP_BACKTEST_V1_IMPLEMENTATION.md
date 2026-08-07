# Swing Setup Historical Backtest Harness v1 — implementation record

| Field | Value |
|---|---|
| **Report number** | 0011 |
| **Title** | Swing Setup Historical Backtest Harness V1 — Implementation Record |
| **Date** | 2026-08-08 |
| **Report type** | Implementation |
| **Model** | Claude Sonnet 5 |
| **Repository branch** | `main` |
| **Base commit** | `35bce7a` (Milestone AU's docs, committed and pushed) |
| **Status** | Final — **not yet committed**; see §35–37 |

## 1. What was asked

An implementation milestone (Milestone AV) to build the first deterministic historical backtest
harness for the existing Swing Setup Engine (AR/AT/AU): answer exactly one question — *"what would the
CURRENT Swing Setup v1 policy have produced historically?"* — with no lookahead, no strategy changes,
no fabricated PnL, honest outcome discipline (report bad results as bad), and a real live demonstration
on public Binance data. Explicitly not a strategy redesign, not an optimization milestone, not
parameter tuning.

## 2. Starting Git state

`HEAD` = `origin/main` = `35bce7a` (`docs(product): record Market Scanner Intelligence Report v1
commit`), itself on top of `fd8a781` (Milestone AU's production code + tests). Working tree clean
relative to `35bce7a` except five pre-existing, unrelated untracked docs (`ADR_IMPLEMENTATION_GATE.md`
and siblings under `docs/design/`/`docs/reviews/`, predating this milestone and left untouched by it).
Full test suite green (4,426 tests) before any change in this milestone was made.

## 3. Required reading, and what it established before any code changed

`CLAUDE.md`, `FMITS_PRODUCT_BACKLOG.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`, ADR-0028, the Swing Setup
Engine design/review, the Market Regime design, the Market Scanner design/review, existing provider and
closed-candle contracts (`fmis.providers.binance`, `fmis.pipeline.market_analysis._fetch_closed`,
`CandleSeries.closed()`) and the existing structural-chain prefix-stability tests were read before any
code was written. Three facts from that reading decided the whole architecture:

- **Every composition root already accepts injectable `transport`/`clock` parameters**
  (`fetch_klines`, `structural_facts_for_symbol`, `multi_timeframe_facts_for_symbol`,
  `setup_for_symbol`) — the exact seam this repository's entire test suite already uses to run
  network-free. A backtest harness could therefore reuse the production composition path exactly, by
  supplying a historical replay transport instead of writing a second implementation.
- **`is_closed` is derived, not stored, from `close_time_ms < now_ms`** (`map_kline`), and
  `CandleSeries.closed()` filters on it. A replay transport only has to answer with the right raw rows
  for a given simulated `now`; the closed/forming decision itself needed no new logic.
- **ADR-0028 §5's guard test exempts files by directory** (`path.parent == fmis/swing_setup/`), not by
  package prefix — confirmed by reading `tests/test_directional_vocabulary_boundary.py` directly rather
  than trusting the design record's restatement. This fixed the new code's location: flat files
  directly inside `fmis/swing_setup/`, matching `scan.py`/`scan_report.py`'s own precedent, not a new
  subpackage (which the guard would not exempt).

## 4. What was built

Seven new flat modules, all direct children of `fmis/swing_setup/`:

- **`backtest_models.py`** — `DataBoundary`, `HistoricalObservation`, `FamilyLean`, `OutcomeStatus`,
  `SetupOutcome`, `BacktestRun`. Value types only, every invariant validated in `__post_init__`
  following every existing model's own discipline.
- **`backtest_replay.py`** — `fetch_raw_klines` (pages the real endpoint via `fetch_klines`'s own
  `build_klines_url`/`Transport`, keeping the raw undecoded shape so close-time survives),
  `fetch_historical_dataset` (fetches every requested `(symbol, interval)` once and records a
  `DataBoundary`), and `build_replay_transport` — a `Transport` bound to one simulated `now` that
  filters cached raw rows to `close_time < now` before a single byte reaches `fetch_klines`.
- **`backtest_identity.py`** — `setup_identity` (a deterministic key from symbol, direction and the
  confirming/watched structural level's own origin) and `IdentityTracker` (a small per-symbol state
  machine reporting `is_new_setup`/`is_first_confirmation`).
- **`backtest_outcomes.py`** — `evaluate_outcome`: walks the full historical execution series forward
  from the bar after confirmation, classifying `TARGET_FIRST`/`STOP_FIRST`/`AMBIGUOUS_SAME_BAR`/
  `NEITHER_WITHIN_WINDOW` by touch (high/low), never by close or candle colour.
- **`backtest_harness.py`** — `run_backtest`: the orchestrating loop. For each symbol and each
  execution-role candle close, builds a replay transport bound to that instant and calls the
  **unmodified** `multi_timeframe_facts_for_symbol` → `setup_inputs_and_assessment_for_sheet` →
  `evaluate_setup` chain, records a `HistoricalObservation`, applies identity, and evaluates outcomes on
  first confirmation.
- **`backtest_metrics.py`** — `compute_metrics`: pure arithmetic over one `BacktestRun` — counts, rates
  (`None`/`INSUFFICIENT SAMPLE` below `MIN_SAMPLE_FOR_RATE = 5`), nearest-rank percentiles, by-symbol/
  by-side/by-month cohorts, the evidence-family independence audit, and the regime-behaviour audit.
- **`backtest_render.py`** — `render_backtest_report`: the terminal report, limitations always printed.

Plus one small, additive, backward-compatible refactor to **`compose.py`**:
`setup_inputs_and_assessment_for_sheet` now does what `setup_assessment_for_sheet` always did
internally, returning `(SetupInputs, SetupAssessment)`; the existing function became a two-line wrapper.
Zero behaviour change — the full pre-existing `test_swing_setup_compose.py` suite passes unmodified.

Wiring, in `pipeline/cli.py`: `BACKTEST_COMMAND` (`fmits backtest [SYMBOL...] [--start] [--end]
[--window] ...`), reusing the existing `_add_setup_style_arguments`/`_policy_from`/`_detection_from`
helpers `setup`/`scan` already share, so the three commands cannot drift apart on a policy flag.

`fmis/swing_setup/__init__.py` gained 17 new exported names (34 → 51), matching the package's existing
convention of re-exporting every public surface at the top level (`scan`/`scan_report` already do this).

## 5. Architecture: no lookahead, no duplicated signal logic

Full design in [`docs/design/SWING_SETUP_BACKTEST_V1.md`](../docs/design/SWING_SETUP_BACKTEST_V1.md).
Summary of the load-bearing decision:

```
fetch_historical_dataset(symbols, intervals, start_time, end_time)   [real network, once, up front]
        │
        ▼
RawKlineCache: {(symbol, interval) -> raw kline rows, undecoded}
        │
        │  per symbol, per execution-role candle close T:
        ▼
build_replay_transport(cache, now=T)  ──►  Transport bound to T
        │
        ▼ (fed into the UNCHANGED production composition path)
multi_timeframe_facts_for_symbol(symbol, transport=replay, clock=lambda: T, ...)
setup_inputs_and_assessment_for_sheet(sheet)  ──►  (SetupInputs, SetupAssessment)
```

The no-lookahead guarantee rests on **two independent checks over the same boundary**: the replay
transport's own `close_time < now` filter, and `fetch_klines`'s unmodified `is_closed` re-derivation
from the same clock. A bug in either alone cannot leak a forming or future candle into a historical
decision. Outcome evaluation (`evaluate_outcome`) is architecturally separate and runs only from the
harness's top-level loop, after an observation is already recorded — never consulted while building one.

## 6. Historical dataset used

Real public Binance spot data, fetched via `fetch_klines`'s own URL builder, paged by the provider's
own close time (no interval-duration table needed or kept).

## 7. Symbols

`DEFAULT_BACKTEST_SYMBOLS` — the task brief's own suggested ten: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT,
XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT.

## 8. Period

`start_time = 2025-07-04`, `end_time = 2026-08-07` — 400 days, `DEFAULT_BACKTEST_DAYS`. Not 180 (the
first value written): the context-role (1w) regime structure dimension needs `fmis.market_regime`'s
moving-average family, which needs EMA(50) on 50 closed weekly candles — roughly 350 days — before it
can classify anything at all. A 180-day synthetic test produced **zero** `CONFIRMED` results, traced to
exactly this cause, and the default was corrected before any live run — a structural fix, not a
result-driven one. Exact per-symbol data boundaries (identical across all ten symbols in this run):

| Interval | First candle | Last candle | Candle count |
|---|---|---|---|
| 1w | 2025-07-07 | 2026-08-03 | 57 |
| 1d | 2025-07-04 | 2026-08-07 | 400 |
| 4h | 2025-07-04 | 2026-08-07 | 2,400 |

## 9. Total historical observations

**21,730**

## 10. WAIT

**21,147**

## 11. CANDIDATE

**401**

## 12. CONFIRMED

**182**

## 13. Unique setups

**580** (deduplicated occurrences — see design record §5 for the identity rule)

## 14. Unique confirmed setups

**182** — of which **151** had valid stop-and-target geometry and were outcome-evaluated; **31** reached
`CONFIRMED` without both (not evaluated, per the task brief's own instruction to evaluate only setups
with valid geometry). `182 = 151 + 31`, reconciled exactly.

## 15. TARGET_FIRST

**64**

## 16. STOP_FIRST

**71**

## 17. AMBIGUOUS_SAME_BAR

**5**

## 18. NEITHER_WITHIN_WINDOW

**11** (`64 + 71 + 5 + 11 = 151`, reconciled exactly against §13)

## 19. Target-first rate

**47.4%** (excludes ambiguous/unresolved: `64 / (64 + 71) = 47.4%`). Stop-first rate **52.6%**. Reported
as measured — close to a coin flip, not reinterpreted positively. This is a target-first rate, never
called a win rate: no fees, slippage, spread, or fill quality are modelled.

## 20. RR distribution

Measured over 532 setup **formations** (occurrence formation bars with full stop/target geometry,
`CANDIDATE` or `CONFIRMED` — a larger set than the 151 evaluated outcomes, since geometry exists before
confirmation too): mean **277.89**, median **1.36**, percentiles p10=0.20 · p25=1.00 · p50=3.09 ·
p75=7.80 · p90=20.00 · **max=41,282.00**. The tail is genuinely pathological — flagged, not smoothed
over, exactly per the brief's instruction not to auto-correct with an ATR buffer or RR floor. This is
evidence for, not against, the hostile audit's original concern about unbounded stop/target geometry
from nearest-detected-level selection.

## 21. Results by symbol

Symbols with at least one evaluated outcome in this window:

| Symbol | N | Target first | Stop first | Ambiguous | Neither |
|---|---|---|---|---|---|
| BTCUSDT | 19 | 3 | 13 | 3 | 0 |
| ETHUSDT | 34 | 20 | 6 | 0 | 8 |
| ADAUSDT | 24 | 8 | 15 | 1 | 0 |
| LINKUSDT | 16 | 9 | 7 | 0 | 0 |
| DOTUSDT | 58 | 24 | 30 | 1 | 3 |

SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT and AVAXUSDT produced no `CONFIRMED` setup with evaluable geometry
in this 400-day window — a real, honest result of this specific window and this specific policy, not
withheld or padded to look complete.

## 22. Results by side

| Side | N | Target first | Stop first | Ambiguous | Neither |
|---|---|---|---|---|---|
| long | 69 | 32 | 26 | 3 | 8 |
| short | 82 | 32 | 45 | 2 | 3 |

## 23. Evidence-family cohorts

Pairwise agreement across **all** 21,730 observations (not only confirmed ones — this measures how
correlated the three families are in general, per the brief's double-counting audit):

| Pair | Both directional | Agree | Rate |
|---|---|---|---|
| context trend ↔ setup evidence alignment | 3,133 | 2,472 | 78.9% |
| context trend ↔ setup trend | 6,171 | 3,427 | 55.5% |
| setup evidence alignment ↔ setup trend | 6,571 | 4,939 | 75.2% |
| all three at once | 2,316 | 1,236 | 53.4% |

Two of the three pairs agree roughly 75–79% of the time when both are directional — real evidence that
these families are **not** fully independent, exactly the correlation the hostile audit's original
concern named. `context trend ↔ setup trend` is closer to independent (55.5%). Outcomes split by how
many families agreed at confirmation: `exactly_2_of_3` — 146 outcomes (63 target-first, 67 stop-first, 5
ambiguous, 11 neither); `all_agree` — only 5 outcomes (1 target-first, 4 stop-first) — too small a
sample for any rate (`MIN_SAMPLE_FOR_RATE = 5` is the floor, not comfortably above it).

## 24. Regime behavior

| State | Count | Share |
|---|---|---|
| INSUFFICIENT | 16,632 | 76.5% |
| TRANSITIONING | 3,559 | 16.4% |
| TRENDING | 785 | 3.6% |
| INDETERMINATE | 754 | 3.5% |

Bar-to-bar regime change rate: **0.1%** (regime is sticky, as expected for a weekly-role dimension).
`WAIT` observations blocked *only* by the regime-not-trending gate (decision context already
sufficient/limited): **20,945** of 21,147 total `WAIT` — the overwhelming majority of `WAIT` results in
this window trace to the context-role regime never reaching `TRENDING`, itself substantially explained
by §23's `INSUFFICIENT` share (early in the window, EMA(50) on the weekly role is still warming up).

## 25. Stop-distance distribution

Measured over the same 532 formation bars as §19, as a fraction of reference price: risk fraction
p10=0.00 · p25=0.00 · p50=0.01 · p75=0.01 · p90=0.03 · max=0.07; reward fraction p10=0.00 · p25=0.01 ·
p50=0.02 · p75=0.04 · p90=0.05 · max=0.10. Most stops sit within 1–3% of price; the RR tail in §19 comes
from the rare cases where the paired target is comparatively far while the stop is extremely close
(risk near the p10/p25 floor), not from an extreme reward figure alone.

## 26. Lookahead protections

Design record §4; proven by `test_no_lookahead_a_changed_future_candle_does_not_alter_an_earlier_decision`
and `test_no_lookahead_a_changed_future_candle_does_not_alter_an_already_frozen_outcome`
(`tests/test_swing_setup_backtest.py`), plus a targeted mutation probe against the replay transport's
own boundary (caught).

## 27. Duplicate-setup rule

Design record §5 (`backtest_identity.py`). Proven by
`test_repeated_confirmed_bars_count_as_one_unique_setup` and
`test_confirmation_is_flagged_exactly_once_across_repeated_confirmed_bars`, plus a mutation probe
against both the identity key (dropping direction) and the confirmed-once dedup flag (both caught).

## 28. Tests

62 new tests in `tests/test_swing_setup_backtest.py`, organized by module: `TestSetupIdentity`,
`TestIdentityTracker`, `TestEvaluateOutcome`, `TestReplayNoLookahead`, `TestFetchRawKlines`,
`TestFetchHistoricalDataset`, `TestBacktestModels`, `TestComputeMetrics`, `TestRenderBacktestReport`,
`TestRunBacktestIntegration`. Covers: no-lookahead (both at the transport boundary and end-to-end
through the harness), same-bar ambiguity, exact boundary touch semantics, the confirming bar itself
never checked, target-first/stop-first/neither classification, LONG/SHORT symmetry (both at the
`evaluate_outcome` level and an end-to-end mirrored-fixture harness run), setup identity and its two
named fallbacks, deduplication (repeated `CONFIRMED` bars, an intervening `WAIT`), deterministic rerun
(byte-identical `BacktestRun` equality), symbol isolation, insufficient warmup, empty dataset, missing
stop/target/RR (confirmed-without-geometry), counts reconciliation, page-width rendering (including the
real 10-symbol default set — the exact case that caught the P1 in §29), and model-level validation for
every new dataclass. No test derives its expected value by calling the same production function under
test — every expectation is reasoned by hand from the fixture's own construction, per the brief's own
instruction.

## 29. Coverage

`coverage`/`pytest-cov` unavailable offline in this environment (the same constraint recorded in report
0010's own review); mutation testing was used in their place, per that precedent.

## 30. Mutations

8 targeted probes against the highest-risk correctness code: the lookahead boundary
(`close_time < now` → `<=`), same-bar ambiguity (the `target_hit and stop_hit` branch removed), the
window slice excluding the confirming bar (`[i+1:...]` → `[i:...]`), the identity key dropping direction,
the confirmed-once dedup flag, the target-first-rate denominator (including ambiguous/unresolved), the
`risk_reward_mean` divisor, and the regime-block marker match. **8/8 detected** (7/8 on the first pass;
one survivor — the RR-mean divisor — closed with a new test,
`test_risk_reward_mean_and_median_are_computed_correctly`, and reconfirmed caught on the second pass).
Byte-identical source restoration verified by SHA-256 comparison after every probe.

## 31. Hostile-review findings

Full record in [`docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md`](../docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md).
Summary:

- **P1, found and fixed.** `render_backtest_report`'s `SYMBOLS`/`TIMEFRAME ROLES` header lines were not
  wrapped; every unit fixture used at most two short symbol names, so nothing exercised a line long
  enough to overflow. The **first live run against the real ten-symbol default universe crashed** with
  `BacktestError: rendered line of 119 exceeds the 78-column page` before printing anything. Fixed with
  `textwrap.wrap`; a regression test (`test_renders_within_page_width_for_the_full_default_symbol_set`)
  builds a `BacktestRun` over the real `DEFAULT_BACKTEST_SYMBOLS` and asserts every line fits. The live
  demonstration was re-run in full against the fix (§8–§24 above are from that second, successful run).
- **P2, found and fixed during implementation.** `DEFAULT_BACKTEST_DAYS = 180` (first value written)
  produced zero `CONFIRMED` results on a synthetic fixture; traced to the regime engine's EMA(50)
  requirement and fixed by raising the default to 400 days before any live run (§7).
- **P3, found and fixed.** One mutation survivor (§29), closed with a new test.
- **P3, informational, not fixed.** The regime-block marker (`_REGIME_ONLY_BLOCK_MARKER`) is a literal
  substring match against `policy.py`'s current wording — stable for this milestone (which changes no
  policy wording) but would silently undercount, not error, if a future milestone changes that text.
  Documented inline and in the review record.
- No P0.

## 32. Performance

Live run: 10 symbols, 400 days, ~2,400 execution-role (4H) candles per symbol → 21,730 total simulated
instants (after warmup skipping), wall time **5 minutes 4 seconds** including network fetch, structural
recomputation, and regime/evidence/decision-context composition at every instant. Roughly 14ms per
observation, dominated by the repeated structural chain recomputation (`derive_level_crossings` is
documented elsewhere as O(candles × levels)) rather than by network I/O, which happens once per
(symbol, interval) up front.

## 33. Exact limitations

Printed verbatim on every report (`BACKTEST_LIMITATIONS`, `AV-1` through `AV-9`); see design record §10
for the full list. Restated briefly: not a portfolio backtest (no fees/slippage/spread/execution delay,
no position sizing); printed R:R is not realized PnL; same-bar ambiguity is never guessed; entry
reference is the confirming bar's close, no wick fill or next-bar-open assumption; setup identity has
two named, disclosed fallbacks; `NEITHER_WITHIN_WINDOW` does not distinguish "never resolved" from "the
dataset ended first"; the evaluation window is a stated measurement policy, not a tuned value; every
`fmis.swing_setup` limitation applies unchanged; the geometry/RR distributions measure formation-bar
values only, not a later bar's refined stop/target within the same occurrence.

## 34. Files changed

New: `src/fmis/swing_setup/backtest_{models,replay,identity,outcomes,harness,metrics,render}.py`,
`tests/test_swing_setup_backtest.py`, `docs/design/SWING_SETUP_BACKTEST_V1.md`,
`docs/reviews/SWING_SETUP_BACKTEST_V1_REVIEW.md`, this report, this report's index row.
Modified: `src/fmis/swing_setup/compose.py` (additive refactor, §3), `src/fmis/swing_setup/__init__.py`
(new exports), `src/fmis/pipeline/cli.py` (`BACKTEST_COMMAND` + import consolidation),
`tests/test_multi_timeframe.py`, `tests/test_pipeline_cli.py`, `tests/test_pipeline_regime.py`,
`tests/test_workspace_render.py` (four registry-count guard tests widened to include `"backtest"`, each
following the existing repository precedent for widening such tests when a command is added),
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`.

**No strategy-policy file was changed.** `fmis/swing_setup/policy.py`, `fmis/market_regime/*`,
`fmis/decision_context/*` all have a zero-line diff. No runtime dependency was added; `pyproject.toml`
and `uv.lock` are unchanged. Import cycles: 0. Export collisions: 0 (+17 new names on
`fmis.swing_setup`, 34 → 51).

## 35. Commit SHA(s)

None yet at the time of writing. Commit(s) will be created after this report is finalized, per the
milestone's own commit-authorization gate, and this report will
**not** be revised to add them afterward (this repository's own point-in-time report convention — see
report 0009/`AT`, never revised after its own later commit).

## 36. Final Git state

At the time of writing: `HEAD` = `origin/main` = `35bce7a`. All Milestone AV changes are uncommitted in
the working tree.

## 37. Explicit confirmation: NOTHING PUSHED

Confirmed. No `git push` was run at any point during this milestone. `origin/main` is unchanged from
`35bce7a`, verified via `git rev-parse origin/main` immediately before this report was written.

## 38. One recommended next product task

**A second, independently-scoped strategy-decision milestone reading this run's own §22 finding**: two
of the three "independent" evidence families agree 75–79% of the time — evidence the 2-of-3 threshold
may be granting less real corroboration than its name implies. That decision explicitly belongs to the
owner, not to this milestone or to AI interpretation of the number — this backtest harness exists to
produce exactly the evidence such a decision would need, and now it has.
