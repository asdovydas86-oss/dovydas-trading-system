# Market Scanner v1 — implementation record

| Field | Value |
|---|---|
| **Report number** | 0009 |
| **Title** | Market Scanner v1 — Implementation Record |
| **Date** | 2026-08-07 |
| **Report type** | Implementation |
| **Model** | Claude Sonnet 5 |
| **Repository branch** | `main` |
| **Base commit** | `9977274` (Milestone AS, plus its documentation reconciliation) |
| **Status** | Final — **not yet committed**; see §8 |

## 1. What was asked

An implementation milestone — explicitly not architecture, not investigation, not an ADR — to build
the first working market scanner on top of the existing Swing Setup Engine (Milestone AR): one
command, a hardcoded list of roughly twenty major crypto pairs, every symbol's already-computed
`SetupAssessment` returned in a compact table, one broken symbol never aborting the scan, no ranking,
no scoring, no probability, no AI.

## 2. Required reading, and what it established before any code changed

`CLAUDE.md`, `FMITS_PRODUCT_BACKLOG.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`, ADR-0028, the Swing Setup
Engine design and review, `fmis.pipeline.cli` and the `fmis.swing_setup`/`fmis.daily` composition
roots were read in full before any code was written. Two facts from that reading shaped every decision
below:

- **ADR-0028 confines directional vocabulary (`LONG`/`SHORT`) to `fmis.swing_setup`'s own modules plus
  `pipeline/cli.py`**, enforced by a repository-wide AST guard
  (`tests/test_directional_vocabulary_boundary.py`) that exempts files by directory — any file whose
  parent is `fmis/swing_setup/` is automatically covered. A scan table has to print a `SIDE` column, so
  this fact decided where the new code could live without touching the ADR at all.
- **`fmis.swing_setup.compose.run_setup_for_symbols` already implements everything the brief asked
  for as "failure isolation"** — per-symbol try/except, only expected exception types converted to a
  result, a defect still propagates — because `fmits setup SYMBOL...` already needed the identical
  guarantee for its own multi-symbol mode. This made the correct scope of this milestone unusually
  small: a default watchlist plus a table renderer, not a new isolation mechanism.

## 3. What was built

One new module, `src/fmis/swing_setup/scan.py`:

- `SCAN_UNIVERSE` — the twenty-symbol hardcoded tuple from the brief, verbatim.
- `run_market_scan(symbols=SCAN_UNIVERSE, ...)` — a nine-line pass-through to
  `run_setup_for_symbols`. No new engine call, no new adapter, no new policy.
- `render_scan(results)` — a compact plain-text table (`SYMBOL`/`STATUS`/`SIDE`/`RR`/`STOP`/`TARGET`),
  a one-line summary of counts, and a `TOP OPPORTUNITIES` section (present only when at least one
  `CANDIDATE`/`CONFIRMED` exists, filtered — never sorted — from the same scan order).

Wiring, in `src/fmis/pipeline/cli.py`:

- `_configure_setup`'s argument block was factored into a new `_add_setup_style_arguments` helper,
  shared by `setup` and the new `scan` command, so the two cannot silently drift apart on an option.
- `_exit_code_for` factors out the "zero unless every symbol failed" contract `setup` already had,
  reused by `scan`.
- `SCAN_COMMAND` registers `fmits scan` — no positional symbol argument; every other flag `setup`
  accepts is available identically.

`src/fmis/swing_setup/__init__.py` gained three new exports: `SCAN_UNIVERSE`, `run_market_scan`,
`render_scan`.

**Zero-line diff** on `fmis.swing_setup.compose`, `fmis.swing_setup.policy`, `fmis.swing_setup.models`,
`fmis.swing_setup.render`, and every engine package. No ADR added or amended.

## 4. Architectural decision reused, none introduced

The one real design choice this milestone made — put the scanner inside `fmis.swing_setup` rather than
in a new top-level `fmis.scanner` package — is a placement decision under an existing ADR, not a new
one. Full reasoning in [`MARKET_SCANNER_V1.md`](../docs/design/MARKET_SCANNER_V1.md) §2. No new
boundary, no new permitted-vocabulary location, no widened import guard anywhere in the repository.

## 5. Test results

| Metric | Before | After | Delta |
|---|---|---|---|
| Tests passing (`-W error`) | 4,332 | **4,375** | **+43** |
| New test files | — | `tests/test_swing_setup_scan.py` (32 tests), `tests/test_pipeline_cli_scan.py` (11 tests) | |
| Modified test files | — | `tests/test_pipeline_cli.py`, `tests/test_pipeline_regime.py`, `tests/test_multi_timeframe.py`, `tests/test_workspace_render.py` — each updates a pinned command-registry list/count to include `scan` | |

Every category the brief required is covered: all-`WAIT`, all-`ERROR`, mixed results, an empty symbol
list (rejected, matching `run_setup_for_symbols`'s own contract), one symbol throwing while the scan
continues, `CANDIDATE` output, `CONFIRMED` output, summary counts, and CLI rendering — split between a
policy-independent scan-and-render test file and a CLI-wiring test file, mirroring the existing
`test_swing_setup_policy.py` / `test_pipeline_cli_setup.py` split.

Full suite: `4375 passed` under `-W error`, zero failures, zero skips.

## 6. Coverage

100 % line and branch coverage on both new/modified production files, measured with
`coverage run --branch` under the full suite:

```
Name                           Stmts   Miss Branch BrPart  Cover
--------------------------------------------------------------------
src/fmis/pipeline/cli.py         226      0     36      0   100%
src/fmis/swing_setup/scan.py     100      0     32      0   100%
```

## 7. Mutation analysis

Seven targeted probes against `scan.py` and the `cli.py` scan wiring — a filter-condition inversion, a
status mislabel, a stop/target column swap, a silent page-width widening, a corrupted watchlist symbol,
an inverted exit-code polarity, and a dropped computed value — run against the full relevant test
surface. **7/7 detected, 0 survivors**, source restored byte-identical after each probe (verified by
`diff` against a pre-mutation copy). Full method and results in
[the review](../docs/reviews/MARKET_SCANNER_V1_REVIEW.md).

## 8. Performance

Not separately measured: `run_market_scan` adds no computation beyond `run_setup_for_symbols`, which
Milestone AR already measured at 0.4 ms per symbol (0.03 % of wall time, entirely network-bound). A
twenty-symbol scan issues the same three provider calls per symbol as `fmits setup` run twenty times —
sixty sequential requests — the same network-bound profile `fmis.daily` (Milestone AN) already
documented and accepted for a comparable request count.

## 8a. Live verification

`fmits scan` was run against real Binance data: 20/20 symbols returned a result, 0 `ERROR`, 15 `WAIT`,
2 `CANDIDATE`, 3 `CONFIRMED` — a genuine, naturally-occurring result. `TOP OPPORTUNITIES` correctly
listed exactly the five non-`WAIT` rows, in scan order. A second run with a deliberately invalid
symbol spliced between two valid ones (`["BTCUSDT", "NOTAREALSYMBOLXYZ", "ETHUSDT"]`) confirmed
failure isolation live — the invalid symbol produced an `ERROR` row with the real
`BinanceAPIError` message, and both surrounding symbols completed normally, proving the scan neither
aborts nor reorders around a mid-list failure.

## 9. Review findings

No P0, P1 or P2. Two issues were found and fixed during implementation — both caught by running the
full existing suite, not only the new tests. One further P3 (an untested `_clip` overflow branch) was
found and closed with a dedicated test during the same review pass, verified live against real
Binance data; two P3s remain, recorded as informational and inherited
from existing patterns rather than introduced here. Full record:
[MARKET_SCANNER_V1_REVIEW.md](../docs/reviews/MARKET_SCANNER_V1_REVIEW.md).

## 10. Git status

```
$ git status --porcelain
 M src/fmis/pipeline/cli.py
 M src/fmis/swing_setup/__init__.py
 M tests/test_multi_timeframe.py
 M tests/test_pipeline_cli.py
 M tests/test_pipeline_regime.py
 M tests/test_workspace_render.py
?? docs/design/MARKET_SCANNER_V1.md
?? docs/reviews/MARKET_SCANNER_V1_REVIEW.md
?? reports/0009_2026-08-07_MARKET_SCANNER_V1_IMPLEMENTATION.md
?? src/fmis/swing_setup/scan.py
?? tests/test_pipeline_cli_scan.py
?? tests/test_swing_setup_scan.py
```

(Plus five pre-existing untracked files from before this milestone began — `docs/design/ADR_IMPLEMENTATION_GATE.md`,
`docs/design/AP_ADR_DISCOVERY.md`, `docs/design/AP_D1_D2_INVESTIGATION.md`,
`docs/design/IMPLEMENTATION_ROADMAP_V1.md`, `docs/reviews/AP_D1_D2_INVESTIGATION_REVIEW.md` — not
touched by this milestone and not listed above.)

**Commit SHA: none.** Per `CLAUDE.md`'s git safety rule, nothing is committed without the owner's
explicit authorization, and none was given for this task. The working tree above is the complete,
tested, reviewed state of Milestone AT, ready to commit on request.

## 11. Remaining limitations

Carried from the design record, stated plainly rather than left implicit:

- **No ranking, by design, not by omission.** The task brief forbade it and the backlog's own note
  under Milestone AN already named the hazard a scanner must avoid (ranking as a side effect of a
  workflow rather than an explicit, backtested policy). This milestone ships the "return what the
  engine already knows" half only.
- **The watchlist is fixed and not configurable at the CLI**, by design — `fmits scan` always scans
  `SCAN_UNIVERSE`; a caller-chosen universe is `fmits setup SYMBOL...` or `fmits daily SYMBOL...`,
  both already shipped.
- **No archiving.** `--archive` exists on `swing` and `daily`; it was not added to `scan`, since the
  brief did not ask for it and adding it would be scope beyond what was requested.
- **Sequential, twenty symbols, three provider calls each** — the same network-bound profile every
  other multi-symbol command in this repository already carries and accepts.

## 12. Recommended next milestone

Per the brief, this task does not select the next one. The backlog's own outstanding action — naming
the next `NOW` item — remains open (`FMITS_PRODUCT_BACKLOG.md` §5) and is unaffected by this milestone.
Two directly relevant, unsequenced items already on the backlog that this milestone's own output makes
easier to scope, named without recommending either: `EP-02`/`EP-03`'s deferred **candidate ranking**
(now has a real `TOP OPPORTUNITIES` surface to rank, once a backtested policy exists) and archiving a
`MarketScan` result (would need its own model and ADR-0027-style capture contract, deliberately not
built here).
