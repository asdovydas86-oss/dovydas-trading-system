# Swing Setup Historical Backtest Harness v1 — independent hostile review

**Milestone:** AV
**Reviewed:** 2026-08-08
**Design:** [SWING_SETUP_BACKTEST_V1.md](../design/SWING_SETUP_BACKTEST_V1.md)
**Scope:** `src/fmis/swing_setup/backtest_*.py` (seven modules), the additive refactor to
`src/fmis/swing_setup/compose.py`, the `BACKTEST_COMMAND` wiring in `src/fmis/pipeline/cli.py`, and
`tests/test_swing_setup_backtest.py`.

## Method

The task brief names an explicit adversarial checklist for this milestone. Each item below was tried
directly — against the actual implementation, not the design document's claims — with the goal of
proving the harness wrong. Every claim is either a reproduced test result, a mutation probe with
before/after output, or a specific code path traced by hand and cited by file:line. Where the checklist
found something, the finding is recorded whether or not it changed the outcome.

## Checklist findings

1. **Lookahead exists.** Tried directly: `build_replay_transport`'s boundary was mutated from
   `close_time_ms < now_ms` to `<= now_ms` (a one-character, classically real off-by-one). Caught
   immediately — `test_a_candle_closing_after_now_is_never_served` failed, serving 10 rows instead of 9.
   Also tried at the harness level: `test_no_lookahead_a_changed_future_candle_does_not_alter_an_earlier_decision`
   corrupts every candle after bar 200 of a 300-bar series and asserts observations at or before bar 200
   are byte-identical — passes on the real implementation. **Not found in the shipped code.**

2. **Future data leaks.** The replay transport is checked twice for the same boundary by two
   independent mechanisms (transport-level filter, and `fetch_klines`'s own `is_closed` re-derivation
   from the same clock) — see design §4. Tried breaking each independently via mutation; both caught.
   **Not found.**

3. **Duplicate setups inflate sample size.** Tried directly: mutated `IdentityTracker.observe` so
   `is_first_confirmation` fires on every `CONFIRMED` bar rather than only the first for an active
   identity. Caught — `test_confirmation_is_flagged_exactly_once_across_repeated_confirmed_bars` failed
   (`(True, True, True)` instead of `(True, False, False)`). Also tried dropping `direction` from the
   identity key (would collapse a LONG and a SHORT occurrence at the same level into one identity) —
   caught by `test_direction_flip_is_a_different_identity_even_at_the_same_level`. **Not found in the
   shipped code**, though the identity rule's two named fallbacks (no-origin, no-level) remain a real,
   disclosed limitation (AV-5) rather than a defect: they can under- or over-count in the fallback cases,
   by construction, and the design record says so.

4. **Target-first rate denominator is dishonest.** Tried directly: mutated the denominator to include
   `AMBIGUOUS_SAME_BAR` and `NEITHER_WITHIN_WINDOW` counts. Caught —
   `test_target_first_rate_excludes_ambiguous_and_unresolved` failed (0.3 instead of 0.6 on a
   6/4/5/5 fixture). **Not found.**

5. **Ambiguous bars are silently guessed.** Tried directly: mutated `evaluate_outcome` to drop the
   `target_hit and stop_hit` branch entirely, falling through to `TARGET_FIRST` whenever the target was
   also touched. Caught — `test_ambiguous_same_bar_long` failed. Traced `_hits` and the render layer by
   hand: neither reads `Candle.open`/`.close` for ordering, and no candle-colour or wick-length heuristic
   exists anywhere in `backtest_outcomes.py`. **Not found.**

6. **LONG and SHORT differ.** `_hits` is a two-line mirror (`Direction.LONG`:
   `high >= target, low <= stop`; `Direction.SHORT`: `low <= target, high >= stop`) with no branch
   beyond that one `if`. `test_long_short_symmetry` constructs mirrored LONG/SHORT fixtures and asserts
   identical outcome classification. At the harness level,
   `test_long_short_symmetry_of_direction_counts` mirrors an entire multi-role synthetic price path
   (reflecting OHLC around the series' own maximum) and asserts the mirrored downtrend produces at least
   as many SHORT as LONG observations, and vice versa for the original uptrend — not a vacuous pass,
   since both counts are asserted positive first. **Not found.**

7. **Report claims profitability it did not measure.** Read `render_backtest_report` end to end: no
   occurrence of "profit", "win", "return", "expected value", "Sharpe", or "CAGR" anywhere in the module.
   The TARGET-FIRST RATE section carries its own inline disclaimer
   ("This is a target-first rate, not a win rate..."). **Not found.**

8. **Printed RR is confused with realized RR.** The RR DISTRIBUTION section header reads
   `"printed R:R at formation — not realized PnL"` verbatim, and `BACKTEST_LIMITATIONS` AV-2 restates it.
   **Not found.**

9. **Regime cohort statistics are wrong.** Tried directly: mutated `blocked_only_by_regime` to count
   every `WAIT` observation regardless of its recorded reason. Caught —
   `test_blocked_only_by_regime_matches_the_recorded_thesis` failed (2 instead of 1, the
   `INSUFFICIENT`-decision-context WAIT wrongly counted as regime-blocked). **Found and already
   detected by an existing test — no fix required beyond confirming the guard holds.** Separately: the
   regime-block marker is a literal substring match against `policy.py`'s exact wording (documented
   inline and in the design record §7) — a **P3**, recorded below.

10. **Summary counts fail to reconcile.** `test_confirmed_without_geometry_reconciles` proves
    `unique_confirmed_setups == evaluated_outcomes + confirmed_without_geometry` on a hand-built fixture
    with one of each. The rendered report prints all three numbers adjacent to each other
    (`BACKTEST SUMMARY`) rather than only the ones that look good. **Not found.**

11. **Results depend on run order.** Traced every collection literal in `backtest_metrics.py` and
    `backtest_harness.py`: every `set()` is immediately `sorted()` before use (`families`,
    `distinct_intervals`), so `PYTHONHASHSEED` cannot affect output order; every `dict` is either
    iterated only for its values (counts) or built from an already-ordered sequence. Confirmed
    empirically: `test_symbol_isolation_one_symbols_data_does_not_affect_another` runs the same symbol
    both alone and second-in-a-two-symbol run and asserts identical per-symbol output. **Not found.**

12. **Repeated run is not deterministic.** `test_deterministic_rerun_is_byte_identical` runs the full
    harness twice over an identical fixture and asserts `run_a == run_b` (frozen dataclass equality,
    field by field, including every nested `HistoricalObservation`/`SetupOutcome`). **Not found.**

## Found and fixed

1. **P1 — a real width-overflow defect, caught only by the live Binance demonstration.**
   `render_backtest_report`'s `SYMBOLS`/`TIMEFRAME ROLES` header lines were not wrapped; every unit
   fixture up to this point used at most two short symbol names (`BTCUSDT`, `ETHUSDT`), so no test
   exercised a line long enough to overflow. The first live run against the real ten-symbol default
   universe crashed with `BacktestError: rendered line of 119 exceeds the 78-column page` before
   printing anything — a shipped command that could not run with its own documented default arguments.
   Fixed by wrapping both lines with `textwrap.wrap`, matching every other long line in the renderer.
   Regression test added: `test_renders_within_page_width_for_the_full_default_symbol_set`, which
   builds a `BacktestRun` over the real `DEFAULT_BACKTEST_SYMBOLS` tuple and asserts every rendered line
   stays within the page width. The live demonstration was then re-run in full against the fixed code
   (§ implementation report).

2. **P2 (found during implementation, not after) — the default lookback window was too short for the
   regime engine to ever classify anything.** `DEFAULT_BACKTEST_DAYS = 180` (the first value written)
   produced **zero** `CONFIRMED` results on a real, deliberately trend-correlated synthetic fixture,
   traced to `fmis.market_regime.classify._moving_average_evidence` requiring both an EMA(50) reading
   and a swing-structure reading before context-role regime structure can be anything but `INSUFFICIENT`
   — EMA(50) on the weekly (context) role needs roughly 350 days of history, which 180 days cannot
   supply regardless of `--limit`. Fixed by raising the default to 400 days (§ design record §8), a
   structural correction discovered and fixed before any live run, not a result-driven adjustment.

3. **P3 (informational, not fixed) — one survivor on the first mutation pass.** Mutating
   `risk_reward_mean`'s divisor from `len(rr_values)` to `len(rr_values) + 1` produced no test failure:
   no existing test asserted the exact value of `risk_reward_mean`/`.median`. Closed by adding
   `test_risk_reward_mean_and_median_are_computed_correctly` (a hand-computed 3-value fixture,
   `(1+2+3)/3 = 2.0`), re-run against the same mutation, now caught.

## Mutation probes

Eight targeted probes against the highest-risk correctness code (lookahead boundary, same-bar
ambiguity, window slicing that excludes the confirming bar, duplicate-setup identity — both the
direction-key and the confirmed-once dedup — outcome denominator, RR aggregation, regime cohort
matching). **8/8 detected** on the second pass (7/8 on the first pass; the one survivor is finding 3
above, closed with a new test and reconfirmed caught). Byte-identical source restoration verified by
SHA-256 after every probe (`sha256sum` before and after each of the four mutated files matched exactly).
No mutation was left applied at any point between probes.

## Coverage

`coverage`/`pytest-cov` are unavailable offline in this environment (the same constraint Milestone AU's
review recorded); mutation testing was used in their place, per that precedent. All 61 tests in
`tests/test_swing_setup_backtest.py` were read and re-verified to reason about their expected values
independently — no test derives its assertion by calling the same production function the assertion is
checking (`tests/test_swing_setup_backtest.py`'s own module docstring states this discipline).

## Live demonstration

Run against real public Binance data — see the implementation report for exact figures, period, and
data boundaries. The first live run surfaced finding 1 above (a real defect); the second, on the fixed
code, completed and printed a full report within the process's own page-width and reconciliation
invariants, which are asserted, not merely displayed.

## Conclusion

One P1 (render width overflow, live-demonstration-only defect), one P2 (default lookback window too
short for the regime engine — a design correction made before any live run), one P3 survivor (closed
with a new test), one P3 informational note (a stable but string-coupled regime-block marker). No P0.
Every finding above was either not reproducible against the shipped code, or fixed with a regression
test that reproduces the original failure against the pre-fix code and passes against the fix.
