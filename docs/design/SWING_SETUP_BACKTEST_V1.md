# Swing Setup Historical Backtest Harness v1 — design

**Milestone:** AV
**Status:** Implemented
**Date:** 2026-08-08
**Contracts:** none new — reuses [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md)
**Repository state at start:** `35bce7a` (Milestone AU's docs, committed and pushed)

## 1. What this milestone builds

The first deterministic historical backtest harness for the existing Swing Setup Engine (Milestone
AR/AT/AU). It answers exactly one question: **"What would the current Swing Setup v1 policy have
produced historically?"** It is a measurement, not a strategy redesign, not a tuning exercise, and not
a portfolio backtest with fees, slippage, or realized PnL.

**Not built, and named here so the gap is not silent:** any change to the 2-of-3 family rule, regime
thresholds, transition window, confirmation age, stop rule, target rule, or RR policy; any realized-PnL,
Sharpe, CAGR, or expected-value computation; any probability or confidence number; any position sizing.

## 2. Where it sits

Seven new flat modules, all direct children of `fmis/swing_setup/` — the one location ADR-0028 §5
already exempts from the repository-wide directional-vocabulary guard
(`tests/test_directional_vocabulary_boundary.py`, which checks `path.parent == fmis/swing_setup/`, not
a package prefix). No new top-level package, no ADR amendment, following exactly the precedent Milestone
AT/AU already set for `scan.py`/`scan_report.py`:

- `backtest_models.py` — `DataBoundary`, `HistoricalObservation`, `OutcomeStatus`, `SetupOutcome`,
  `BacktestRun`. Value types only; every field is a fact copied from a `SetupAssessment`/`SetupInputs`
  pair or from the outcome walk, nothing computed.
- `backtest_replay.py` — the historical data acquisition and the no-lookahead replay `Transport`.
- `backtest_identity.py` — the setup identity/freshness rule.
- `backtest_outcomes.py` — post-confirmation outcome classification.
- `backtest_harness.py` — `run_backtest`, the orchestrating loop.
- `backtest_metrics.py` — deterministic aggregate metrics over one `BacktestRun`.
- `backtest_render.py` — the terminal report.

Plus one small, additive, backward-compatible refactor to `fmis/swing_setup/compose.py`:
`setup_assessment_for_sheet` is now a thin wrapper over a new `setup_inputs_and_assessment_for_sheet`,
which returns the `SetupInputs` alongside the `SetupAssessment` it produced. Zero behaviour change for
any existing caller (proven by the existing `test_swing_setup_compose.py` suite passing unmodified) —
it exists so the harness can read the regime/evidence facts an assessment was reasoned from without
recomputing them or parsing them back out of rendered text. `compose.py` is composition-layer plumbing,
not a policy file; the milestone's "no strategy changes" rule is about `policy.py` and the market-regime/
decision-context policy objects, none of which changed.

## 3. Core principle: reuse, not reimplementation

The task brief's non-negotiable rule: *"Backtesting must use the SAME deterministic production logic as
live analysis."* This harness adds no backtest-only setup logic, no simplified policy, no alternate
signal implementation, and no duplicate regime/swing logic. Every historical observation is produced by
calling, unmodified:

```
fmis.pipeline.multi_timeframe.multi_timeframe_facts_for_symbol   (network edge, AG)
fmis.swing_setup.compose.setup_inputs_and_assessment_for_sheet   (composition root, AR)
fmis.swing_setup.policy.evaluate_setup                            (the policy itself, AR)
```

What makes this possible without a second implementation is that every one of those functions already
accepts injectable `transport`/`clock` parameters — the exact seam every existing test in this
repository already uses to run network-free. The harness's only genuinely new code is what stands in
for the network: a real historical data cache, and a `Transport` that serves it correctly bounded to one
simulated instant.

## 4. No lookahead — the architecture, not just a promise

```
fetch_historical_dataset(symbols, intervals, start_time, end_time)
        │  pages fetch_klines' own URL builder + injectable Transport, once, up front
        ▼
RawKlineCache: {(symbol, interval) -> raw Binance kline rows, undecoded}
        │
        │  for each symbol, for each execution-role candle close time T in the cache:
        ▼
build_replay_transport(cache, now=T)  ──►  Transport bound to T
        │
        ▼ (fed into the UNCHANGED production composition path)
multi_timeframe_facts_for_symbol(symbol, transport=replay, clock=lambda: T, limit=250, ...)
        │
        ▼
setup_inputs_and_assessment_for_sheet(sheet)  ──►  (SetupInputs, SetupAssessment)
```

For a given simulated instant `T`, the replay transport filters the raw cache to
`close_time_ms < to_epoch_ms(T)` **before a single byte reaches `fetch_klines`**, and returns the most
recent `limit` (or 500, Binance's own documented default) rows — exactly what the real endpoint would
answer had the query been made at `T`. `fetch_klines` then independently re-derives `is_closed` from
the same clock (`map_kline`'s `close_time_ms < now_ms`), and `CandleSeries.closed()` drops anything not
marked closed. **Two independent checks over the same boundary, using the identical inequality**: a bug
in either one alone still cannot leak a forming or future candle into a historical decision.

An unknown `(symbol, interval)` is answered with Binance's own real error shape (`code -1121`,
`"Invalid symbol."`), so a caller mistake surfaces through `fetch_klines`'s existing, unmodified
`BinanceAPIError` path rather than a new one invented here.

**Outcome evaluation is the one place look-forward is correct, and it is architecturally separate.**
`fmis.swing_setup.backtest_outcomes.evaluate_outcome` reads the *full* historical execution series —
deliberately, because judging what happened after a confirmed setup requires seeing after it. It is
never consulted while building an observation, only afterward, from the harness's own top-level loop.

Proven by tests, not just argued: `test_no_lookahead_a_changed_future_candle_does_not_alter_an_earlier_decision`
corrupts every candle after an analysis cutoff and asserts observations up to that cutoff are
byte-identical; `test_no_lookahead_a_changed_future_candle_does_not_alter_an_already_frozen_outcome`
corrupts the tail of the dataset, far beyond a resolved outcome's window, and asserts that outcome is
unchanged.

## 5. Setup identity — telling one persisting setup from a new one

A `CANDIDATE`/`CONFIRMED` result can repeat, unchanged in substance, across many consecutive bars: the
policy re-reads the same structural level every time it is asked. The identity rule
(`fmis.swing_setup.backtest_identity.setup_identity`) is the smallest one the existing facts already
support: two observations for one symbol are the *same* setup when they agree on **direction** and on
the **structural level** being watched or that confirmed them, read from `Trigger.level.origin` — the
same swing-point provenance (`LevelOrigin.index`, `.label`) `fmis.level_crossing` already carries. A
different level, a direction flip, or an intervening `WAIT` all start a new identity.

Two named fallbacks, both stated in the harness's own limitations: a level with no `origin` (the
earliest, unlabelled swing — ADR-0019 D2) falls back to its price; a candidate with no watched level at
all falls back to direction only. Neither is a new structural concept — both reuse fields the model
already carries.

`IdentityTracker` walks one symbol's observations in chronological order and reports `is_new_setup`
(a fresh occurrence started) and `is_first_confirmation` (the first bar this occurrence reached
`CONFIRMED` — the only bar that triggers an outcome evaluation). Repeated `CONFIRMED` bars for the same
occurrence report `is_first_confirmation=False`, which is what prevents one confirmed setup from being
outcome-evaluated more than once.

## 6. Outcome evaluation

For each occurrence's first `CONFIRMED` bar with a valid stop **and** target (i.e. `risk_reward` is not
`None`), the harness locates the confirming candle in the full historical execution series (matched by
`execution_last_timestamp`, the exact instant the confirmation's `reference_price` was read from) and
walks forward from the **next** candle — never the confirming candle itself, whose own high/low occurred
before the close the reference price is stated as. The window is `DEFAULT_EVALUATION_WINDOW_BARS = 60`
execution-role bars — ten days at the default 4H execution role, six times
`fmis.swing_setup.policy.CONFIRMATION_LOOKBACK_BARS` (10) — a stated v1 measurement policy, fixed before
any run's results were seen, never tuned to a result.

Each candle in the window is checked by touch (high/low, not close — a wick counts):

- Both target and stop touched on the same candle → `AMBIGUOUS_SAME_BAR`. This follows the identical
  refusal `fmis.change_of_character`'s design record already states for two structural events sharing
  one candle: OHLC data cannot establish an intrabar path, so none is guessed — not from candle colour,
  not from a coin flip.
- Only the target touched (first, scanning forward) → `TARGET_FIRST`.
- Only the stop touched → `STOP_FIRST`.
- Neither touched by the end of the window (including when the historical dataset itself ends first) →
  `NEITHER_WITHIN_WINDOW`.

Entry reference is the execution-timeframe close at the confirming bar — the exact number
`fmits setup`/`fmits scan` already print as `reference_price`, never a fabricated fill, never a
next-bar-open assumption.

## 7. Metrics and independence audit

`fmis.swing_setup.backtest_metrics.compute_metrics` is pure arithmetic over `BacktestRun.observations`/
`.outcomes` — counts, rates, and nearest-rank percentiles, nothing invented. A rate computed from fewer
than `MIN_SAMPLE_FOR_RATE = 5` resolved outcomes reports `None` (rendered `INSUFFICIENT SAMPLE`) rather
than a number presented with false precision.

The evidence-family independence audit reads `SetupAssessment.directional_factors` — already present on
**every** observation, `WAIT` included — and reports, for every pair of the three families
(context-role structural trend, setup-role structural trend, setup-role evidence alignment): how often
both are directional and how often they agree; and for all three at once. Outcomes are then split by
"exactly 2 of 3 agreed" vs. "all 3 agreed" by joining each `SetupOutcome` back to the exact triggering
observation via `(symbol, execution_last_timestamp)` — a collision-free key, since one symbol can have at
most one active directional candidate at any simulated instant.

The regime-behaviour audit reads `context_regime_structure` off every observation (percentage
TRENDING/RANGING/TRANSITIONING/INDETERMINATE/INSUFFICIENT, bar-to-bar change frequency per symbol) and
counts `WAIT` observations whose recorded `thesis` matches the exact, stable substring
`evaluate_setup` emits only when a candidate is blocked purely because context-role regime structure is
not `TRENDING` — reading an already-produced, deterministic reason string, not recomputing the gate.

## 8. Historical data

`fmis.swing_setup.backtest_replay.fetch_historical_dataset` pages the real public
`GET /api/v3/klines` endpoint (via `fetch_klines`'s own `build_klines_url`/`Transport`/`urlopen_transport`,
reused, not reimplemented) from `start_time` to `end_time`, advancing the cursor by the **provider's own
close time** of the last row returned plus one millisecond — no interval-duration table is needed or
kept. Raw arrays are cached, not decoded, so close-time — needed to reproduce the closed-candle boundary
at replay time — survives; decoding happens later, once per simulated instant, through the unmodified
`map_kline`/`decode_candle_series` path.

Every `(symbol, interval)` pair's exact window is recorded on a `DataBoundary`: first candle, last
candle, candle count, source, and the caller-supplied `fetched_at` stamp (this module reads no wall
clock of its own — only `pipeline/cli.py` does, per this repository's existing convention).

`DEFAULT_BACKTEST_DAYS = 400`, not a rounder or shorter number: the context-role (1w) regime structure
dimension needs `fmis.market_regime`'s moving-average family, which needs EMA(50) on 50 closed weekly
candles — roughly 350 days — before it can classify anything at all. A shorter default would spend most
of the window unable to produce a directional candidate for a reason that has nothing to do with the
market, which would misrepresent the policy's own historical behaviour. This was discovered empirically
during implementation (a synthetic fixture at 180 days produced zero `CONFIRMED` results, traced to
`_moving_average_evidence` never having both readings available) and fixed by lengthening the window,
never by loosening the regime engine's own requirement.

## 9. First-version scope

Crypto only, `DEFAULT_BACKTEST_SYMBOLS` — the task brief's own suggested ten: BTCUSDT, ETHUSDT, SOLUSDT,
BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT — distinct from (and smaller than)
`fmis.swing_setup.scan.SCAN_UNIVERSE`, since this is a measurement run, not a scan, and the two lists
drifting together silently was judged worse than a second explicit constant. The production timeframe
roles (`DEFAULT_TIMEFRAMES`: 1w/1d/4h) are reused unchanged — no second timeframe scheme.

`fmits backtest [SYMBOL...] [--start] [--end] [--window] [-n/--limit] [--left-bars] [--right-bars]
[--context] [--setup] [--execution] [--band] [--transition-lookback]` — a default run
(`fmits backtest`, no arguments) is possible, reusing the existing `_add_setup_style_arguments` helper
`setup`/`scan` already share so the three commands cannot drift apart on policy flags.

## 10. What is deliberately not claimed

Printed verbatim from `BACKTEST_LIMITATIONS`, always rendered on the report itself, not left in this
document alone:

- Not a portfolio backtest: no fees, slippage, spread, or execution delay; no position sizing.
- `target_first`/`stop_first` describe which level touched first by wick, not realized PnL, and are
  never called a win rate.
- `AMBIGUOUS_SAME_BAR` is a refusal to guess intrabar order, not a resolved outcome folded into either
  side.
- Entry reference is the confirming bar's close — no wick fill, no next-bar-open assumption.
- Setup identity can under- or over-count distinct setups that share a price or lack a watched level.
- `NEITHER_WITHIN_WINDOW` does not distinguish "price never got there" from "the dataset ended first".
- The evaluation window is a stated measurement policy, not a backtested or optimised value.
- Every limitation `fmis.swing_setup` itself already carries (uncalibrated probability, no position
  sizing, nearest-detected-level stops/targets, the 10-bar confirmation lookback) applies unchanged.
