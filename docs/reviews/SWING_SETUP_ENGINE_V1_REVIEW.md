# Swing Setup Engine v1 — Independent Review

**Milestone:** AR
**Reviews:** [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md),
[design](../design/SWING_SETUP_ENGINE_V1.md)
**Date:** 2026-08-07
**Verdict:** no P0, **three P1 found and fixed**, one P3 found and fixed

This review was performed by a separate agent instance with no memory of the implementation session,
briefed only on the architecture and the adversarial checklist below, and instructed not to trust the
implementer's own claims. It read the source fresh, ran the existing test suite, and independently
picked and ran three of its own mutations (not drawn from the implementer's mutation list) before
reporting. All findings below were then fixed and re-verified in a second pass.

---

## 1. What was checked

Hidden `LONG`/`SHORT` bias; correlated evidence double-counting; a path producing direction from one
indicator; a path bypassing the Decision Context gate; fake precision; stop/target geometry bugs;
R/R computation bugs; look-ahead or forming-candle influence; direction vocabulary leaking into a
forbidden package; overly eager `CANDIDATE`/`CONFIRMED` classification; a `WAIT` case silently
promoted; unnecessary duplication in `compose.py`; and a spot-check of the implementer's own claimed
17/17 mutation-detection result using different, independently-chosen mutations.

## 2. Findings — all fixed

### P1 — Same-bar dual break always resolved toward the LOWER side

`fmis.structure_break` can emit an upper and a lower break on **one** bar (documented in its own
module), ordered upper-before-lower. `StructuralFactSheet.structure.latest_break` is `breaks[-1]`, so
on a tied bar it is **always** the lower one. The original implementation read this single positional
value directly (`execution_latest_break_level`), so a `SHORT` candidate confirmed by a same-bar tie and
a `LONG` candidate did not — a real, provable, deterministic directional asymmetry, independent of how
rare the trigger (a single execution candle sweeping both a swing high and swing low) is in practice.
This is precisely the class of bug ADR-0028 exists to prevent.

**Fix:** `SetupInputs` now carries `execution_breaks`, the **full** ordered break history, as
`ExecutionBreakEvent(level, index)` pairs rather than one precomputed "latest". `policy._latest_matching_break`
searches it backward for the most recent break whose **side** matches the candidate's confirming side,
never trusting positional order to mean what it does not.

**Regression tests:** `test_a_same_bar_dual_break_confirms_long_from_the_upper_side`,
`test_a_same_bar_dual_break_confirms_short_from_the_lower_side`,
`test_the_most_recent_matching_break_is_used_not_the_earliest`.

### P1 — No recency bound on a confirming break

Confirmation checked only that the single latest break matched the confirming side and that the
execution trend did not currently oppose it — nothing bounded *how old* that break could be. With a
typical 500-candle fetch, a break could legitimately be tens or hundreds of bars old and still report
`CONFIRMED` for a directional candidate that only just formed from fresh CONTEXT/SETUP/evidence
signals, with the rendered thesis reading as a current, actionable claim.

**Fix:** `CONFIRMATION_LOOKBACK_BARS = 10`, a stated module constant beside
`MINIMUM_AGREEING_FAMILIES` (the same "chosen and labelled as chosen" discipline `RegimePolicy`
already uses for its own thresholds). A confirming break outside this window leaves the result at
`CANDIDATE`, with the break's age in bars stated in the rendered confirmation text.

**Regression tests:** `test_a_stale_break_beyond_the_lookback_window_does_not_confirm`,
`test_a_break_exactly_at_the_lookback_edge_still_confirms`,
`test_one_bar_past_the_lookback_edge_does_not_confirm`.

### P1 — A one-flag misconfiguration defeated the "≥2 independent families" guarantee

Nothing validated that the CONTEXT and SETUP roles were fetched at distinct intervals.
`fmits setup BTCUSDT --context 1d --setup 1d` — a single, freely-offered CLI flag combination — makes
`context_structural_trend` and `setup_structural_trend` read from the same underlying candles, so one
fact is tallied as two "independent" votes. This collapses the exact guarantee `MINIMUM_AGREEING_FAMILIES`
exists to enforce, silently and without a test to catch it.

**Fix:** `build_setup_inputs` now requires the three role intervals to be pairwise distinct, raising
`ValueError` before the policy is ever reached.

**Regression test:** `test_build_setup_inputs_rejects_a_context_setup_interval_collision`.

### P3 — the R/R reference price was labelled `entry`

`render.py` printed the execution close as `entry` beside `stop`/`target`/`R:R`, in tension with the
design's own explicit "no exact entry price is fabricated" claim (design record §7) — the number was
real, not invented, but the label read as more actionable than intended.

**Fix:** relabelled `reference ... (not an order price)`.

**Regression test:** `test_the_reference_price_is_not_labelled_as_an_order_price`.

## 3. What was checked and found sound

- No hidden `LONG` bias beyond the P1 above: every `LONG` branch has a `SHORT` mirror, verified by a
  test suite that flips every directional fixture field and asserts structural symmetry (equal risk,
  equal reward, equal ratio, mirrored sides).
- No path produces a direction from fewer than `MINIMUM_AGREEING_FAMILIES` (2) families; the family
  tally requires zero opposition, not merely a plurality.
- The Decision Context `INSUFFICIENT` gate is checked first, unconditionally, before the family tally
  is even reached — traced through every code path.
- No fake precision: probability is always `NOT_CALIBRATED`; stop/target are real, already-detected
  `PriceLevel` objects or absent, never fabricated.
- Stop/target geometry cannot select a level on the wrong side of price or equal to it — `_nearest`'s
  strict inequality against the reference close makes zero risk/reward unrepresentable, and
  `SetupAssessment.__post_init__` independently re-validates every side.
- No look-ahead: nothing here reads a candle at all: it consumes already-computed, closed-candle-only
  facts.
- Direction vocabulary does not leak into a forbidden package — verified both by the widened
  "nothing below imports this package" guards across seven engine packages and by
  `tests/test_directional_vocabulary_boundary.py`'s repository-wide AST scan.
- `compose.py`'s duplication of two small adapters from `fmis.workspace.builder`'s pattern
  (`snapshot_from_sheet`, the `ContextInput` adapter) is deliberate and recorded (ADR-0028 §3), not
  accidental drift.

## 4. Mutation testing

**Implementer's original pass:** 17 hand-picked mutations across `policy.py`/`models.py`/`compose.py`
(LONG/SHORT swaps, threshold changes, gate bypasses, side-mapping flips, R/R denominator flip,
`_nearest` inequality weakening, role swap) — 17/17 detected on the first pass after one test gap
(a missing `SHORT`-side mirror of an opposition-check test) was closed.

**Independent spot-check (this review, 3 mutations of its own choosing):**

1. `_tally`'s `short_votes == 0` → `short_votes <= 1` in the `LONG` branch — **detected**.
2. `_nearest`'s strict `>`/`<` → `>=`/`<=` against the reference close — **detected**, via a
   `ZeroDivisionError` the weakened check allowed through.
3. The regime `TRENDING` gate prefixed with `False and` (bypassed entirely) — **detected decisively**,
   6 tests failed.

**Second pass, after the three P1 fixes (7 mutations targeting the new logic):** forward-vs-reversed
search order in `_latest_matching_break`, the lookback boundary (`>` vs `>=`), the staleness check
being dropped from `break_confirms`, an off-by-one in the age computation, the `ExecutionBreakEvent`
range guard inverted, the interval-distinctness check weakened, and `execution_breaks` sourced from
the wrong role. First run: 2 survivors (the forward/reversed search and the wrong-role break source),
because no existing test distinguished "most recent break" from "any matching break" or asserted
`execution_breaks` came specifically from the execution view. Both closed with new regression tests
(`test_the_most_recent_matching_break_is_used_not_the_earliest`, an extended
`test_build_setup_inputs_reads_the_right_role_for_each_field`); re-run: **7/7 detected**.

Every probe's file was restored and verified byte-identical by SHA-256 before the next probe.

## 5. Quality, measured after all fixes

- **4317 tests**, full repository suite, passing identically under `-W error`.
- **100 % line coverage** on every file in `fmis.swing_setup` and on the modified `pipeline/cli.py`.
- **24 mutation probes across two passes and one independent spot-check, 24 detected, 0 survivors**,
  byte-identical source restoration verified by SHA-256 before and after every probe.
- Zero import cycles; the widened "nothing below imports `fmis.swing_setup`" guards cover
  `fmis.decision_context`, `fmis.market_regime`, `fmis.pipeline.multi_timeframe`,
  `fmis.pipeline.structural_facts`, `fmis.structural_trend`, `fmis.structure_break`,
  `fmis.level_crossing` — seven packages, each individually asserted.
- Zero new runtime dependencies.

## 6. Verdict

Safe to ship as "a technically valid setup according to policy v1." The architecture, invariants and
test discipline were sound from the first pass; the three P1s the review found were each a genuine,
reachable gap in exactly the guarantee this milestone exists to provide, and each is now closed with
its own named regression test and confirmed caught by mutation testing rather than merely patched.
