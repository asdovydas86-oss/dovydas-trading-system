# Market Scanner v1 — design

**Milestone:** AT
**Status:** Implemented
**Date:** 2026-08-07
**Contracts:** none new — reuses [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md)
**Repository state at start:** `9977274` (Milestone AS, plus its documentation reconciliation)

## 1. What this milestone builds

The first market scanner: one command, `fmits scan`, that runs the existing Swing Setup Engine
(Milestone AR) across a small, hardcoded watchlist of major crypto pairs and prints a compact table —
one row per symbol, every `SetupAssessment` the engine already produces, nothing more. The product
acceptance test, verbatim from the task brief: *"scan approximately twenty major crypto pairs, return
every swing setup already produced by the existing engine."*

**Not built, and named here so the gap is not silent:** ranking, scoring, probability, AI
interpretation, position sizing, symbol discovery from an exchange endpoint. Each is explicitly out of
scope per the task brief; the backlog's own note under Milestone AN already states a scanner "must rank
on an explicit, deterministic, testable and backtested policy... never as a side effect of a workflow"
— this milestone avoids that hazard by **not ranking at all**. When ranking is built, it is its own
future milestone with its own policy, evidence and backtest.

## 2. Where it sits

`fmis.swing_setup.scan` — a new module **inside** the existing `fmis.swing_setup` package, not a new
top-level package. This is the one architectural choice this milestone makes, and it follows directly
from [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md) §2: directional vocabulary
(`SIDE: LONG`/`SHORT`) may appear only inside `fmis.swing_setup`'s own modules and in
`pipeline/cli.py`. A scan table has to print the side of any candidate or confirmed setup, so a new
top-level `fmis.scanner` package would either duplicate the ADR's permitted-location list (a real
architecture change the brief asks to avoid) or violate it. Placing the scanner inside the already-
permitted package needs no ADR change at all — the guard test
(`tests/test_directional_vocabulary_boundary.py`) already exempts every file whose parent directory is
`fmis/swing_setup/`, and `scan.py` is a direct child of it.

```
run_market_scan(symbols=SCAN_UNIVERSE)   ──►  run_setup_for_symbols (fmis.swing_setup.compose, AR)
                                                        │  one setup_for_symbol call per symbol,
                                                        │  in list order, per-symbol isolation
                                                        ▼
                                          tuple[SetupRunResult, ...]
                                                        │
                                                        ▼
                                          render_scan(results)  ──►  compact terminal table
```

**Zero new engine logic.** `run_market_scan` is `run_setup_for_symbols` — the exact function
`fmits setup` already uses for its own multi-symbol mode — called with a default watchlist instead of
a caller-supplied one. No policy, no composition root, no adapter is duplicated or reimplemented.
`render_scan` reads fields that already exist on `SetupAssessment` (`state`, `direction`, `risk_reward`,
`stop`, `targets`) and formats them; it computes nothing.

## 3. Symbol list

A twenty-symbol, hardcoded tuple, `SCAN_UNIVERSE`, matching the task brief exactly: BTCUSDT, ETHUSDT,
BNBUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, DOTUSDT, TRXUSDT, ATOMUSDT, NEARUSDT,
SUIUSDT, APTUSDT, ARBUSDT, OPUSDT, UNIUSDT, LTCUSDT, HBARUSDT. Not fetched from any exchange endpoint,
per the brief's explicit instruction. `run_market_scan` accepts an optional `symbols` override (default
`SCAN_UNIVERSE`) purely so the function stays unit-testable against small or empty lists without
depending on the hardcoded constant; the CLI command never exposes this override — `fmits scan` always
scans the fixed watchlist, which is the whole point of the command as distinct from `fmits setup`
(caller-supplied symbols) and `fmits daily` (caller-supplied universe).

## 4. Failure isolation

Inherited unchanged from `run_setup_for_symbols` (Milestone AR, itself following the Deterministic
Daily Workflow's contract, Milestone AN): each symbol is fetched and assessed independently; only
`PipelineError` (insufficient data) and `BinanceError` (provider failures) are converted into a
`SetupRunResult.failure`, and everything else propagates, because a defect in this repository must
never be rendered as an ordinary market outcome. One symbol's failure never stops the scan — the
remaining nineteen still run, and the failed one's row shows `ERROR` with the underlying exception's
message beneath it.

## 5. Output

One table, one row per symbol, in scan-list order — never reordered:

```
 SYMBOL     STATUS     SIDE   RR     STOP          TARGET
──────────────────────────────────────────────────────────────────────────────
 BTCUSDT    CONFIRMED  LONG   3.00   90            130
 ETHUSDT    WAIT       —      —      —             —
 DOTUSDT    CANDIDATE  SHORT  0.43   0.825         0.815
 BADUSDT    ERROR      —      —      —             —
     BinanceTransportError: connection refused
```

`STATUS` is `SetupAssessment.state` (`WAIT`/`CANDIDATE`/`CONFIRMED`) or the literal `ERROR` when
`SetupRunResult.assessment is None`. `WAIT` is counted and displayed identically to `CANDIDATE`/
`CONFIRMED` — it is a successful result, never merged with or mistaken for `ERROR`. `SIDE`, `RR`,
`STOP`, `TARGET` are read directly from the assessment's `direction`, `risk_reward.ratio`, `stop.price`
and `targets[0].price` and are the em dash `—` exactly when the underlying field is `None` — the same
"absence is stated, never fabricated" discipline every renderer in this repository already follows.
`targets` is a tuple because a future policy version may populate more than one; v1 (Milestone AR) never
does, so showing `targets[0]` loses nothing today and needs no shape change later.

**Summary line**, after the table: `N scanned · N WAIT · N CANDIDATE · N CONFIRMED · N ERROR` — the
literal counts the task brief asked for, in one line rather than five, so the page stays short.

**`TOP OPPORTUNITIES`**, only when at least one `CANDIDATE` or `CONFIRMED` exists: the same table,
filtered to those rows, in the same scan-list order. Never sorted by direction, risk/reward or any
other property — sorting here would be exactly the ranking-by-a-back-door the task brief forbids.
Omitted entirely, not printed empty, when nothing qualifies.

## 6. CLI

`fmits scan` — no positional arguments; the watchlist is fixed. Every other flag `fmits setup` accepts
(`--limit`, `--left-bars`, `--right-bars`, the three timeframe-role flags, `--band`,
`--transition-lookback`) is available identically, applied to every symbol in the scan — refactored out
of `_configure_setup` into a shared `_add_setup_style_arguments` helper so the two commands cannot drift
apart on an option one of them forgets to add. Exit code follows `fmits setup`'s own "at least one true
report" contract, factored into a shared `_exit_code_for` helper: `0` unless every symbol errored, in
which case `1`.

## 7. Reuse — nothing recomputed

No indicator, no swing detection, no BOS/CHoCH, no regime, no evidence grouping, no decision-context
verdict, no directional policy decision is recomputed. `run_market_scan` calls
`run_setup_for_symbols` — the same function, not a copy of its logic — which in turn calls
`setup_for_symbol` exactly as `fmits setup` does. A scan row and a `fmits setup SYMBOL` page for the
same symbol, at the same instant, are produced by identical underlying code and cannot disagree.

## 8. Testing strategy

Two files. `tests/test_swing_setup_scan.py` covers `SCAN_UNIVERSE` (count, no duplicates), `
run_market_scan` (default universe, custom list, empty-list rejection, one-symbol-fails-scan-continues,
all-fail, a genuine defect still propagates) and `render_scan` (type/shape guards, all-WAIT, all-ERROR,
mixed results, input-order preservation regardless of state, CANDIDATE output, CONFIRMED output,
summary counts, `TOP OPPORTUNITIES` present/absent, page-width guard, determinism). `
tests/test_pipeline_cli_scan.py` covers CLI parsing, wiring to the real composition root, per-symbol
failure isolation at the command level, exit codes, and the command registry entry — mirroring
`tests/test_pipeline_cli_setup.py`'s own split between policy tests and CLI tests.

## 9. What this milestone deliberately does not touch

`fmis.swing_setup.compose.run_setup_for_symbols`, `fmis.swing_setup.policy`,
`fmis.swing_setup.models` and `fmis.swing_setup.render` are unmodified — a zero-line diff. No ADR is
added or amended. No engine, application layer or CLI command outside `fmis.swing_setup` and
`pipeline/cli.py` changed behaviour.
