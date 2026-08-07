# Market Regime Time-Reference Fix — Independent Review

**Reviews:** the implemented fix for
[`REGIME_ROOT_CAUSE_ANALYSIS_V1.md`](../design/REGIME_ROOT_CAUSE_ANALYSIS_V1.md) (D-1/D-2), against
[ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md) §6 (amended by this change) and
[ADR-0024](../adr/ADR-0024-confirmation-delay-provenance.md)
**Date:** 2026-08-07
**Repository state reviewed:** branch `main`, base `HEAD = 2a9bdcc`, working tree at review time
**Verdict:** no P0, no P1, no P2. One P3 documented (residual API risk, already contained by every
live call site — see §11).

Every claim below was re-derived from production code and from fixtures built during this review, not
copied from the implementation's own account of itself. The RCA is trusted for its measurements (they
were independently reproduced in §2 of the implementation work); its recommendation (Option B) is not
trusted here — it is checked against the code that actually shipped.

---

## 1. What changed, read from the diff, not from a summary

```
docs/adr/ADR-0025-market-regime-engine-v1.md |  17 +-
src/fmis/market_regime/classify.py           |   4 +-
src/fmis/market_regime/models.py             |  51 +++--
src/fmis/pipeline/regime.py                  |   3 +-
tests/test_market_regime.py                  |  59 ++-
tests/test_pipeline_regime.py                | 329 ++++++++++++++++++++++-
tests/test_workspace_build.py                |   2 +-
7 files changed, 423 insertions(+), 42 deletions(-)
```

Three production files changed. `RegimeInput.last_index: int | None = None` became
`RegimeInput.closed_count: int` (required, no default) in `models.py`; the invariant became
`latest_change_index >= closed_count → RegimeInputError`; `classify.py`'s `bars_since` became
`closed_count - 1 - latest_change_index`; `pipeline/regime.py`'s adapter stopped reading
`structure.swings` at all and now reads `sheet.window.closed_count`. No other production file changed —
`swing_setup`, `workspace`, `daily`, `archive` have a zero-line diff, confirmed by `git diff --stat` over
each directory.

---

## 2. The twelve adversarial angles

### 2.1 Off-by-one error

The engine computes `bars_since = closed_count - 1 - latest_change_index`. Mutated to
`closed_count - latest_change_index` (dropping the `- 1`) during this review: 3 tests failed, including
one asserting a hand-computed value of `25` (got `26`) and one asserting `"2 bars ago"` (got `"3 bars
ago"`, from `test_structure_transitioning_on_a_recent_change_of_character`). Restored, byte-identical
(SHA-256 verified). **No off-by-one survives.**

### 2.2 `closed_count` vs. last-index confusion

Mutated the adapter back to `(structure.swings[-1].index + 1) if structure.swings else 0` — the exact
shape of the original defect, reading a swing position instead of the window's own count. 10 tests
failed immediately, including the two fixtures built specifically to reproduce D-1/D-2
(`test_a_change_of_character_on_the_confirmation_frontier_does_not_raise`,
`test_structural_age_is_measured_from_the_last_closed_candle_not_the_swing`) and the seed-58 regression.
Restored, byte-identical. **The regression this fix exists to prevent is caught if reintroduced.**

### 2.3 Forming-candle leakage

`regime_input_from_sheet` reads `sheet.window.closed_count`, which `_window_of` (`market_analysis.py:205`)
computes as `len(closed.candles)` from the *same* `closed = series.closed()` that
`_structure_of` analyses (`structural_facts.py:414, 437`) — traced by hand, not assumed. A dedicated test
(`test_a_forming_candle_cannot_change_the_regime_result`) builds two sheets differing only by one
forming candle with deliberately extreme OHLCV values and asserts the two `RegimeInput`s and the two
`MarketRegime`s are equal. Mutated the adapter to read `sheet.window.fetched_count` instead (the count
*including* the forming candle): this one test caught it immediately (120 vs 121). Restored,
byte-identical. **A forming candle cannot reach `closed_count`.**

### 2.4 Transition-boundary asymmetry

`test_the_transition_lookback_boundary_is_inclusive` asserts a change exactly `transition_lookback_bars`
old still transitions, and one bar further does not. Mutated `<=` to `<` in the boundary comparison: the
inclusive-side assertion failed. Restored, byte-identical. The boundary is unchanged by this fix — it
was already `<=` before Option B — but D-2 means the value being compared is now correct, so this
boundary is now checked against real ages for the first time.

### 2.5 A valid change of character rejected again

Three independent lines of evidence, not one: (a) the deterministic frontier fixture
(`_FRONTIER_LEGS`, change of character on the exact last closed candle) does not raise; (b) a property
test over `seeded_series` seeds `0..119` asserts `regime_input_from_sheet` never raises and, whenever a
change exists, `latest_change_index < closed_count`; (c) the live walk-forward sweep in §3 replayed 6,452
real historical states across 11 symbols × 4 intervals and recorded **zero** `RegimeInputError`s under
the fixed code, against 1,006 (15.59 %) that the pre-fix reference frame would have rejected. **No valid
state is rejected.**

### 2.6 An invalid future index accepted

`test_a_change_after_the_last_candle_is_rejected` (`latest_change_index == closed_count`) and the
`closed_count ∈ {0, 1}` boundary tests
(`test_a_closed_count_of_zero_cannot_carry_a_change_index`,
`test_a_closed_count_of_one_accepts_only_index_zero`) pin both sides of the boundary. Mutated the
invariant check out of `models.py` entirely during this review: 3 tests failed immediately (`DID NOT
RAISE`). Restored, byte-identical. **The guard that used to reject valid data zero times for the right
reason now rejects invalid data for the right reason, and nothing else.**

### 2.7 Incorrect Market Regime state

`test_structural_age_is_measured_from_the_last_closed_candle_not_the_swing` hand-computes (not via
`classify_regime`) `true_bars_since = closed_count - 1 - change_index = 25` on a fixture where the old
formula would answer `2`, then asserts the *engine's own* evidence string reads `"25 bars ago"` under a
30-bar lookback, and that the default 5-bar lookback correctly reports **not** transitioning (`25 > 5`).
The live sweep (§3) independently confirms the direction and scale: 837 states move from
wrongly-`TRANSITIONING` to correctly-not, zero move the other way.

### 2.8 Swing Setup workaround duplicating logic

`git diff --stat -- src/fmis/swing_setup/` is empty — literally zero lines changed. `swing_setup/policy.py`
already carried the correct pattern (`execution_closed_count - 1 - matching_break.index`,
`policy.py:347`) before this milestone; nothing needed to change there, and this review confirms nothing
did. The full `swing_setup` test suite passes unchanged as part of the 4,332-test run in §4.

### 2.9 Application-layer arithmetic violating ADR-0025

`test_the_composition_root_contains_no_arithmetic` (an AST walk over `pipeline/regime.py` rejecting any
`BinOp` with `+ - * / // ** %`) passes on the shipped code. Mutated the adapter to
`sheet.window.closed_count - 0` (a no-op arithmetically, but an `ast.BinOp` syntactically): the guard
caught it on the first assertion. Restored, byte-identical. **The "no arithmetic in `fmis.pipeline`"
guarantee ADR-0025 §6 states is upheld by the shipped code, not merely by convention.**

### 2.10 Historical-state behaviour changed beyond the intended defect

Only `_structure_dimension` in `classify.py` reads `closed_count`/`latest_change_index`; `_volatility_dimension`
and `_participation_dimension` (unmodified, confirmed by reading the full file) read only `atr_fast`,
`atr_slow` and `participation_ratio`, none of which this fix touches, and the adapter lines supplying
those three fields are byte-identical before and after (`git diff` shows only the `closed_count`/
`latest_change_index` lines changed in `pipeline/regime.py`). The sweep in §3 confirms this
empirically — every state's volatility and participation classification is a pure function of fields
this fix never wrote to, so no separate before/after measurement was needed to know they are unaffected.
**Nothing outside the structure dimension moved.**

### 2.11 Hidden assumptions in sparse-pivot markets

Two fixtures were built specifically because `seeded_series`'s random walk cannot produce them (RCA
§8.2): `_FRONTIER_LEGS` (a 200-candle monotonic climb off one early dip, ending in a plunge that closes
below the dip's level on its very first candle — landing the change of character on the last closed
candle) and `_UNDERSTATEMENT_LEGS` (the same climb, but the plunge and the pivot it creates land on
different bars, decoupling `closed_count`, `latest_change_index` and the last confirmed swing by 25
bars). Both are literal, hand-written price-delta lists — no `random` call anywhere in either — and both
were verified empirically once, then pinned as permanent fixtures with the exact resulting indices
asserted in the test (`built.structure.latest_change.index == 223`, etc.), so a future change to the
detection algorithm that shifts these numbers fails loudly rather than silently drifting.

### 2.12 Test fixtures that still overrepresent choppy random walks

`test_no_valid_series_is_ever_rejected_over_a_wide_seed_range` widens `seeded_series`'s exercised range
to `0..119`, specifically so seed 58 — the first seed at which the RCA's own `seed_sweep.py` reproduced
D-1 — sits inside the range the suite actually runs, documented as such in the test's docstring. That
alone does not fix the *representativeness* problem the RCA names in §8.2 (a random walk pivots on
almost every bar); §2.11's two hand-built trending fixtures are what actually closes it, plus the live
sweep in §3, which replays real market data rather than any synthetic generator.

---

## 3. Historical walk-forward sweep (independently run during this review)

Real Binance data, fetched live on 2026-08-07 — 500 klines per symbol/interval, 11 symbols × 4
intervals (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, DOTUSDT, LINKUSDT, AVAXUSDT,
SUIUSDT; 1w, 1d, 4h, 1h), replayed prefix-by-prefix every 3rd prefix from bar 30 onward — **6,452
independent historical states**, a different sample from the RCA's own (live data two commits later,
every-3rd-prefix stride vs. every prefix, 11 symbols vs. 30), so agreement between the two is
corroboration, not a repeated measurement.

| | RCA (30 symbols, all prefixes) | This review (11 symbols, 1-in-3 prefixes, later data) |
|---|---:|---:|
| States evaluated | 23,627 | 6,452 |
| D-1 rate (old code) | 16.07 % | 15.59 % |
| D-1 failures (fixed code) | — (not yet fixed) | **0** |
| Age reported correctly (old code) | 0.0 % | 0.0 % |
| Max understatement | 19 bars | 20 bars |

Classification flips under `DEFAULT_POLICY` (5-bar lookback), old formula vs. shipped formula:

```
old TRANSITIONING -> new NOT (corrected away):    837
old NOT -> new TRANSITIONING (corrected into):       0
both TRANSITIONING (unaffected):                  1694
both NOT TRANSITIONING (unaffected):              3757
```

Every flip runs in the direction the RCA predicted (§6: "direction of every flip: TRANSITIONING claimed
when the true age is stale"); zero run the other way. The 1,006 states that would have raised
`RegimeInputError` under the old reference frame now classify as: `transitioning` (967), `trending`
(19), `indeterminate` (17), `insufficient` (3) — no crash silently became a wrong answer of a kind the
RCA did not anticipate.

---

## 4. Regression suite, coverage, mutation

- Full suite: **4,332 passed**, up from the pre-fix baseline of 4,319 (11 references migrated per the
  RCA's own count; 13 net new tests added, none removed). Green under `-W error`.
- Coverage on the three modified production modules (`market_regime/models.py`, `market_regime/classify.py`,
  `pipeline/regime.py`): **100 % line, 100 % branch** (`coverage run --branch`, measured this review,
  not carried over from before the fix).
- Eight targeted mutations probed (off-by-one, swing-index regression, forming-candle count, boundary
  `<`/`<=`, guard bypass, arithmetic-in-pipeline, invariant removal, field-swap) — **all eight detected,
  zero survivors**. Every mutation's source restoration was verified byte-identical by SHA-256, not by
  visual diff.

---

## 5. Findings

No P0. No P1. No P2.

**P3-1 — the residual risk ADR-0025 §6 already names is real but currently unreachable.**
`build_structural_facts` accepts a caller-supplied `window` argument that changes what is *reported*,
not what is *computed* (`structural_facts.py:381-386`). If a caller ever passed a `window` inconsistent
with the `series` it also passed, `closed_count` would silently disagree with the series `_structure_of`
actually analysed, reintroducing a frame error of the same shape as D-1/D-2 by a different route. Traced
by hand: the **only** production call site that supplies `window` is `structural_facts_for_symbol`
(`structural_facts.py:496,507`), and it always derives `window` from the exact same `closed` series it
passes alongside it (`market_analysis.py:242`, `_fetch_closed`) — so the risk is not exploitable by any
code that ships today, and `test_the_window_closed_count_matches_the_closed_series_length` pins the
invariant for every sheet the test suite builds. Not blocking: fixing it would mean either removing a
parameter `ADR-0025` did not ask this milestone to touch, or adding a validation this milestone's brief
explicitly scoped out ("do not broaden into unrelated cleanup"). Recorded here as a watch item, matching
the RCA's own treatment of Option C.

---

## 6. What this review did not re-litigate

Per the milestone brief, this review did not re-derive the RCA's original measurements from scratch
(§2 of the implementation work already reproduced D-1 and D-2 independently before any code changed);
did not evaluate whether `transition_lookback_bars = 5` is the right policy value (explicitly out of
scope — correctness and calibration are different questions); and did not assess the `fmits daily`
partial-result question the RCA named as a separate, not-yet-decided defect (§8.5).
