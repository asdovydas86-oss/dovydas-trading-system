# Market Scanner v1 — independent review

**Milestone:** AT
**Reviewed:** 2026-08-07
**Design:** [MARKET_SCANNER_V1.md](../design/MARKET_SCANNER_V1.md)
**Scope:** `src/fmis/swing_setup/scan.py`, the `_add_setup_style_arguments`/`SCAN_COMMAND` wiring in
`src/fmis/pipeline/cli.py`, `src/fmis/swing_setup/__init__.py`'s new exports, and
`tests/test_swing_setup_scan.py` / `tests/test_pipeline_cli_scan.py`.

## Method

A fresh adversarial pass against the implementation and its own design claims, not a re-statement of
intent: re-derived the ADR-0028 boundary argument from the guard test's actual exemption logic rather
than trusting the design doc's prose; ran the full existing suite before and after every change;
measured line and branch coverage on both touched files; ran targeted mutation probes against
`scan.py` and the new `cli.py` wiring with byte-identical source restoration verified after each.

## Findings

### Found and fixed during implementation (not shipped as defects)

1. **A docstring reference tripped `fmis.daily`'s own raw-text import guard.**
   `tests/test_daily_runner.py::test_no_engine_imports_this_package` scans the full source text of
   every file outside a short allow-list for the literal substring `"fmis.daily"` — not an AST-based
   check, so it flags a *mention* of the module path exactly as it would flag a real import. An early
   draft of `scan.py`'s `_clip` docstring referenced `fmis.daily.render._clip` by dotted path for
   context. Caught by running the full suite (not just the new tests) before considering the change
   complete; fixed by describing the behaviour without writing the dotted path. No import was ever
   added — `scan.py` does not and must not import `fmis.daily` (a Market Scanner sits at the same tier
   as `fmis.swing_setup`, not above `fmis.daily`, and needs nothing from it).

2. **`pipeline/cli.py` reached into `fmis.swing_setup.compose` for a name already re-exported at the
   package's own top level.** The first draft imported `SetupRunResult` from
   `fmis.swing_setup.compose` for a type hint on the new `_exit_code_for` helper, while every other
   name `cli.py` uses from this package is imported from `fmis.swing_setup` itself. No test forbids the
   submodule import — no such guard exists for this package — so this would have shipped as a working
   but locally inconsistent import. Fixed by importing `SetupRunResult` from `fmis.swing_setup`
   alongside everything else `cli.py` already takes from it.

Both are recorded here rather than silently folded into the diff, per this repository's own
"corrected during review" convention (see Milestone AR's three P1s, AI's four P2s, etc.) — the
difference here is severity: both were caught before any commit, in the same working session, and
neither reached a state a reader would call "shipped."

### P0 / P1 / P2

**None found.** No correctness defect, no directional-vocabulary leak, no boundary violation, no
silent data loss.

### P3 — informational, not fixed, and not blocking

1. **`render_scan`'s per-symbol duplicate rejection is inherited, not independent.**
   `run_setup_for_symbols` (Milestone AR) does not reject a duplicate symbol the way
   `fmis.daily.require_symbols` does — `run_market_scan`/`render_scan` would happily process
   `["BTCUSDT", "BTCUSDT"]` as two identical rows. Unreachable through `fmits scan` today, because the
   CLI command takes no symbol argument at all and always scans the duplicate-free `SCAN_UNIVERSE`
   (verified by `test_scan_universe_has_no_duplicates`). Worth a note only because `run_market_scan`'s
   `symbols` override is public API, used directly by the test suite; a future caller of that override
   should not assume rejection.

2. **The page-width guard (`SwingSetupError` on a line over 78 columns) is unreachable through normal
   data**, because every variable-width table cell is passed through `_clip` before the row is
   assembled — the guard exists only to catch a genuine defect in this module (e.g. a future edit that
   widens a column constant without updating another). Verified this is not a new gap:
   `fmis.daily.render_daily_run`'s own `DailyRunError` width guard is equally unreachable from
   ordinary data and is, in the existing codebase, called *outside* `_run_daily_command`'s
   `try/except DailyRunError` block — so a real trigger there already propagates as an unhandled
   exception exactly as a real trigger in `render_scan` would here. `scan.py` matches established
   precedent rather than introducing a new one.

3. **Closed during this review.** `_clip`'s ellipsis branch was untested — no fixture constructed a
   symbol long enough to force it. A live run against real Binance data with a deliberately invalid,
   over-length symbol (`NOTAREALSYMBOLXYZ`) confirmed the clip behaves correctly
   (`NOTAREALS…`); `test_render_scan_clips_a_symbol_wider_than_its_column` now pins that exact shape.
   `fmis.daily.render`'s own `_clip` has the identical gap and was left alone, since fixing a
   pre-existing pattern in another package is out of this milestone's scope.

## Mutation testing

Seven targeted probes against `scan.py` and the `cli.py` scan wiring — chosen to hit the branches a
line-coverage number cannot distinguish (a filter condition, a status label, a column swap, a width
constant, a data constant, an exit-code polarity, a computed value silently dropped) — run against the
full relevant test surface (`test_swing_setup_scan.py`, `test_pipeline_cli_scan.py`,
`test_pipeline_cli.py`, `test_pipeline_cli_setup.py`, `test_pipeline_regime.py`,
`test_multi_timeframe.py`, `test_workspace_render.py`):

| # | Mutation | Result |
|---|---|---|
| 1 | Invert the `TOP OPPORTUNITIES` filter condition | Detected |
| 2 | Mislabel `ERROR` status as `"OK"` | Detected |
| 3 | Swap `_stop`/`_target` in the row builder | Detected |
| 4 | Widen `_WIDTH` from 78 to 79 (silently loosen the page-width contract) | Detected |
| 5 | Corrupt the first `SCAN_UNIVERSE` symbol (`BTCUSDT` → `XTCUSDT`) | Detected |
| 6 | Invert the `scan`/`setup` shared exit-code polarity | Detected |
| 7 | Drop the computed R/R ratio from the row (render `—` unconditionally) | Detected |

**7/7 detected, 0 survivors.** Source restored byte-identical after every probe (`diff` against a
pre-mutation copy, confirmed clean).

## Coverage

100 % line and branch coverage on both `src/fmis/swing_setup/scan.py` (100 statements, 32 branches)
and `src/fmis/pipeline/cli.py` (226 statements, 36 branches) under the full suite, measured with
`coverage run --branch`.

## Architecture conformance

- **ADR-0028 boundary.** `scan.py` is a direct child of `fmis/swing_setup/`, which
  `tests/test_directional_vocabulary_boundary.py` already exempts by directory — no ADR amendment
  needed, and the full suite (including that guard test) is green with the new file in place.
- **No new engine, no recomputation.** `run_market_scan` is a nine-line pass-through to
  `run_setup_for_symbols` (Milestone AR); `render_scan` reads fields that already exist on
  `SetupAssessment` and formats them. Confirmed by reading `scan.py` end to end: it imports no engine
  package directly and calls no function that was not already exported by `fmis.swing_setup.compose`.
- **No ranking.** `render_scan` never sorts `results`; the `TOP OPPORTUNITIES` section is a filter
  over the same order, pinned by `test_render_scan_top_opportunities_preserves_scan_order_not_desirability`,
  which deliberately places a `CANDIDATE` before a `CONFIRMED` result to rule out an implicit
  "readiness" sort.
- **Failure isolation.** Exercised at both layers: `run_market_scan` isolates a failing symbol without
  a network dependency (`test_run_market_scan_isolates_one_failing_symbol_and_continues`), and the CLI
  command does the same through the real composition root
  (`test_a_failed_symbol_does_not_stop_the_scan`). A genuine defect (`KeyError`, standing in for any
  exception outside the two named expected classes) still propagates rather than being absorbed as a
  market outcome (`test_run_market_scan_a_defect_propagates_rather_than_becoming_a_result`).

## Live verification

`fmits scan` was run against real Binance data (no mocking, no fixture): 20/20 symbols returned a
result, 0 `ERROR`, 15 `WAIT`, 2 `CANDIDATE`, 3 `CONFIRMED` — a naturally-occurring result, not
manufactured or selected to look good. `TOP OPPORTUNITIES` correctly listed exactly the five
non-`WAIT` rows, in scan order. A second run, `run_market_scan(["BTCUSDT", "NOTAREALSYMBOLXYZ",
"ETHUSDT"])`, confirmed failure isolation live: the invalid symbol returned
`BinanceAPIError: Binance error (HTTP 400, code -1121): Invalid symbol.` as an `ERROR` row, and both
real symbols on either side of it completed normally — proving the scan does not abort or reorder
around a mid-list failure.

## Verdict

**Ready to ship as designed.** No P0, P1 or P2. Two issues were found and fixed during implementation,
both caught by running the full existing suite rather than only the new tests — the strongest
available evidence that the full-suite-before-considering-done discipline this repository already
practices is doing real work. Three P3s are informational, inherited from existing patterns
(`fmis.daily`) rather than introduced by this milestone, and are recorded rather than silently
absorbed.
