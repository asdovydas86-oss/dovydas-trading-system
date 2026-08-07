# Market Scanner Intelligence Report v1 — implementation record

| Field | Value |
|---|---|
| **Report number** | 0010 |
| **Title** | Market Scanner Intelligence Report v1 — Implementation Record |
| **Date** | 2026-08-07 |
| **Report type** | Implementation |
| **Model** | Claude Sonnet 5 |
| **Repository branch** | `main` |
| **Base commit** | `81a6202` (Milestone AT, plus its documentation reconciliation) |
| **Status** | Final — **not yet committed**; see §10 |

## 1. What was asked

An implementation milestone — explicitly not architecture, not investigation, not another design
document — to transform the Market Scanner's (Milestone AT) raw table into something a trader would
actually read every morning: a summary, a market overview, actionable CONFIRMED/CANDIDATE setups with
their reasons, and WAIT results grouped by reason, plus deterministic (never AI, never inferred) reason
text. No new engine logic, no ranking, no score, no probability. The brief also specified its own
adversarial review checklist verbatim: prove the report lies, counts disagree, summary disagrees, reason
disagrees, duplicate logic exists, orchestration leaks, or presentation leaks.

## 2. Required reading, and what it established before any code changed

`CLAUDE.md`, the AT design record and review, `fmis.swing_setup.scan`/`compose`/`policy`/`models` were
read in full before any code was written. Two facts shaped every decision below:

- **`SetupAssessment` already carries every fact the brief's example report wants** —
  `thesis`/`confirmation`/`invalidation` are complete, deterministic, human-readable sentences produced
  by `policy.py` at the exact point each decision is made. The correct "human-readable explanation
  generation" this milestone asked for is printing those sentences verbatim, not writing a second,
  shorter paraphrase in a presentation layer that could drift from the first.
- **The one structured, per-symbol "is the market trending" fact `fmis.market_regime.StructureState`
  would supply is never stored on `SetupAssessment`** — only folded into one formatted prose sentence
  (`regime_context`). Recovering it would mean parsing rendered text, which is itself a way to fabricate
  meaning from a string never meant to be machine-read. This ruled out the most literal reading of the
  brief's own "Trending:"/"Transitioning:" example and led to `MARKET OVERVIEW` reading the `Lean`
  vocabulary the engine's own directional-factor logic already assigns instead — see the design record
  §3 for the full argument, including the two defects that design choice's *first draft* had and how
  they were closed.

## 3. What was built

One new module, `src/fmis/swing_setup/scan_report.py`:

- `render_scan_report(results)` — four sections (`SCAN SUMMARY`, `MARKET OVERVIEW`, `ACTIONABLE SETUPS`,
  `WAIT REASONS`) plus a conditional `SCAN ERRORS` section, over the identical
  `tuple[SetupRunResult, ...]` `render_scan` already renders as a table. ASCII-only in every line this
  module writes itself; verbatim, unedited engine text (which can include `—`) is the one deliberate
  exception, argued in the design record §5.

One promotion in `src/fmis/swing_setup/scan.py`: private `_status` → public `result_status`, identical
body, so both renderers share one status classifier instead of risking two copies drifting apart.

Wiring, in `src/fmis/pipeline/cli.py`:

- `fmits scan` now prints `render_scan_report` by default; a new `--table` flag prints the unchanged
  Milestone AT table.
- Every other flag (`--limit`, timeframe roles, `--band`, `--transition-lookback`) is unaffected.

`src/fmis/swing_setup/__init__.py` gained two new exports: `render_scan_report`, `result_status`.

**Zero-line diff** on `fmis.swing_setup.compose`, `fmis.swing_setup.policy`, `fmis.swing_setup.models`,
and every engine package. No ADR added or amended.

## 4. Review-driven changes (not shipped as first drafted)

An independent adversarial review — run as a genuinely separate agent, per the brief's own checklist —
found two real, reproducible defects in the first draft, both already visible in this milestone's own
first live scan against real Binance data, not only in the reviewer's hand-built fixtures:

1. **`MARKET OVERVIEW`'s `TRENDING` label could sit beside a `WAIT` reason literally stating "not
   trending" for the same symbol** in the same report (`BNBUSDT`/`NEARUSDT`/`UNIUSDT`, live — see §8a).
   Root cause: the bucket read one directional factor (`context_structural_trend`) while the WAIT
   reason's "not trending" gate reads an independent fact (`context_regime_structure`); the two can
   disagree. Fixed by renaming the bucket `DIRECTIONAL` (the word "trending" no longer appears anywhere
   in this module's own text) and, for any `CANDIDATE`/`CONFIRMED` result, reading the policy's own
   final `direction` first rather than one family's factor in isolation — which also closed a related
   defect where a live confirmed trade could be bucketed `NO DATA`/`CONFLICTED` if the *other* two
   families had won the tally.
2. **`ACTIONABLE SETUPS` silently dropped RR and target for `CANDIDATE` rows even when both were already
   computed** — the brief explicitly asked for "CONFIRMED/CANDIDATE with reasons, RR, targets, stops."
   Also visible live: `ATOMUSDT CANDIDATE` printed only a stop, no RR, no target — even though the
   fixed version of the same live data shows `RR 8.00`, `target 1.212`. Fixed by sharing one header
   builder between the two states so neither can special-case away a number the other prints.

Both fixes are pinned by regression tests built directly from the review's reproduction steps, and both
were confirmed against a second live scan (§8a). Full review, including the "not broken" claims verified
independently and the one disclosed-not-fixed limitation:
[MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md](../docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md).

## 5. Test results

| Metric | Before | After | Delta |
|---|---|---|---|
| Tests passing | 4,423 | **4,426** | **+3** net (45 new in the report's own file, offset against zero regressions elsewhere; two AT-era CLI tests were renamed/split rather than added, see below) |
| New test files | — | `tests/test_swing_setup_scan_report.py` (45 tests) | |
| Modified test files | — | `tests/test_pipeline_cli_scan.py` — `--table`/default split (4 renamed tests, 4 new: `--table` argument parsing, default-report assertions) | |

Every category the brief and its own review required is covered: type/shape guards, determinism,
page-width discipline (including a live-shaped 20-symbol worst case and a monkeypatched-width failure
guard), `SCAN SUMMARY` counts cross-checked against `render_scan` for four result mixes, `MARKET
OVERVIEW` bucketing for every `Lean` value plus both review-driven regression cases, `ACTIONABLE SETUPS`
reason/needs/invalidation verbatim-fidelity (parsed back out of wrapped output and compared
character-for-character against the source tuple), the CANDIDATE RR/target regression, `WAIT REASONS`
grouping/counting/sort-order/tie-break, `SCAN ERRORS` presence/absence and failure isolation, and one
golden full-page exact-string test.

Full suite: `4426 passed`, zero failures, zero skips.

## 6. Coverage

No coverage tool (`coverage`/`pytest-cov`) is installed in this environment and none could be installed
offline (`pip` itself is unavailable in the project's `.venv`) — stated plainly rather than a number
invented to fill this section. In its place: a manual review of every function in `scan_report.py`
against the test file confirms every branch is exercised except two explicitly defensive ones —
`_context_trend_factor` returning `None` and `_reason_lines` receiving an empty tuple — neither of which
`evaluate_setup` can produce today (every assessment it builds carries the `context_structural_trend`
factor and a non-empty thesis for `CANDIDATE`/`CONFIRMED`). Both are exercised anyway, via hand-built
`SetupAssessment` objects constructed directly (bypassing `evaluate_setup`) —
`wait_with_no_directional_factors`/`candidate_with_no_thesis_or_confirmation` — so the defensive code
itself is proven correct even though production code cannot reach it.

## 7. Mutation analysis

Seven manual mutation probes against `scan_report.py`, substituting for the unavailable `coverage`
tool's own branch report, chosen to hit the sections a line-coverage number could not distinguish (a
bucket-condition swap, a sort-direction inversion, a formatting-precision corruption, an RR-presence
condition inversion, a verbatim-text substitution, a CONFIRMED/CANDIDATE filter swap, and a revert of
the review's own direction-first fix) — run against the full relevant test surface
(`test_swing_setup_scan_report.py`, `test_pipeline_cli_scan.py`):

| # | Mutation | Result |
|---|---|---|
| 1 | Swap the `CONFLICTED`/`NO DATA` branch condition | Detected |
| 2 | Invert `WAIT REASONS`' descending sort to ascending | Detected |
| 3 | Corrupt price precision (`.6g` → `.2g`) | Detected |
| 4 | Invert the RR-present guard (crash on `None.ratio` when RR is absent) | Detected |
| 5 | Replace verbatim WAIT thesis text with a constant string | Detected |
| 6 | Swap the `CONFIRMED`/`CANDIDATE` state filter assignment | Detected |
| 7 | Revert the review's direction-first `MARKET OVERVIEW` fix | Detected |

**7/7 detected, 0 survivors.** Source restored byte-identical after every probe (`diff` against a
pre-mutation copy, confirmed clean).

## 8. Performance

Not separately measured: `render_scan_report` adds pure string formatting over an already-computed
`tuple[SetupRunResult, ...]` — no network, no additional provider call, no new computation. The scan
itself (`run_market_scan`) is unchanged from Milestone AT, already measured there as network-bound.

## 8a. Live verification

`fmits scan` was run against real Binance data twice, both captured verbatim.

**First run — pre-review draft.** 20/20 symbols returned a result, 0 `ERROR`, 15 `WAIT`, 2 `CANDIDATE`,
3 `CONFIRMED`. This transcript is what surfaced both fixed findings independently of the reviewer's own
hand-built reproductions:

```
MARKET OVERVIEW  (source: each symbol's own context_structural_trend factor)
   TRENDING (12)
     ...
     BNBUSDT (short)
     ...
     NEARUSDT (long)
     ...
     UNIUSDT (short)
     ...
...
 CANDIDATE  ATOMUSDT  SHORT
   reason: ...
   needs: ...
   risk: stop 1.365
...
 WAIT REASONS
   3 symbols:
     BNBUSDT, NEARUSDT, UNIUSDT
     Context-role (1w) regime structure is transitioning, not trending. ...
```

`BNBUSDT`/`NEARUSDT`/`UNIUSDT` appear in `TRENDING (12)` and, in the same report, are described as
"not trending." `ATOMUSDT CANDIDATE` shows a stop with no RR and no target.

**Second run — after both fixes.** Same live scan, same real data. `"TRENDING" in text` is `False`
(checked programmatically, not by eye). Both `CANDIDATE` rows now show RR/target:

```
MARKET OVERVIEW  (direction when set, else context_structural_trend lean)
   DIRECTIONAL (12)
     ...
...
 CANDIDATE  ATOMUSDT  SHORT   RR 8.00
   target 1.212   stop 1.365
...
 CANDIDATE  APTUSDT  LONG   RR 11.00
   target 0.628   stop 0.58
```

Every line in both transcripts fits the 78-column page (`max(len(line) for line in text.splitlines())
== 78` in both), including the worst-case wrapped 8-symbol WAIT-reason group. Counts in both transcripts
are internally consistent: `WAIT(15) = 8+3+2+2`, `CANDIDATE(2)+CONFIRMED(3)` match `ACTIONABLE SETUPS`'
own row count, `DIRECTIONAL(12)+CONFLICTED(8) = 20` with `ERROR=0`.

## 9. Review findings

One P0 (a label collision that could contradict a WAIT reason for the same symbol) and two P1s (a
related overview-bucketing gap, and CANDIDATE rows silently dropping already-computed RR/target) — all
three found, fixed, and confirmed against a second live scan. One P2 (WAIT-reason grouping can merge
symbols reaching the same branch through different families) is disclosed in the module docstring rather
than fixed, for a stated reason. One P3 (duplicated pure-formatting helper, matching an existing
repository pattern) requires no action. Every "report lies"/"counts disagree"/"duplicate logic"/
"orchestration leak"/"presentation leak" claim in the brief's own checklist was independently checked and
did not hold against the fixed version. Full record:
[MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md](../docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md).

## 10. Git status

```
$ git status --porcelain
 M src/fmis/pipeline/cli.py
 M src/fmis/swing_setup/__init__.py
 M src/fmis/swing_setup/scan.py
 M tests/test_pipeline_cli_scan.py
?? docs/design/MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md
?? docs/reviews/MARKET_SCANNER_INTELLIGENCE_REPORT_V1_REVIEW.md
?? reports/0010_2026-08-07_MARKET_SCANNER_INTELLIGENCE_REPORT_V1_IMPLEMENTATION.md
?? src/fmis/swing_setup/scan_report.py
?? tests/test_swing_setup_scan_report.py
```

(Plus five pre-existing untracked files from before this milestone began — `docs/design/ADR_IMPLEMENTATION_GATE.md`,
`docs/design/AP_ADR_DISCOVERY.md`, `docs/design/AP_D1_D2_INVESTIGATION.md`,
`docs/design/IMPLEMENTATION_ROADMAP_V1.md`, `docs/reviews/AP_D1_D2_INVESTIGATION_REVIEW.md` — not
touched by this milestone and not listed above.)

**Commit SHA: none yet.** Per `CLAUDE.md`'s git safety rule and this milestone's own explicit
instruction ("Commit locally only. DO NOT PUSH."), nothing is committed until the owner authorizes it in
this conversation. The working tree above is the complete, tested, reviewed state of Milestone AU.

## 11. Remaining limitations

Carried from the design record and review, stated plainly rather than left implicit:

- **`WAIT REASONS` groups by exact thesis text, not by which families produced it** — two symbols
  reaching the "factors do not agree" branch through different families can render identical text and
  group together. Documented as an accepted trade-off (fixing it would duplicate `policy.py`'s own
  tally logic).
- **No ranking, by design** — `ACTIONABLE SETUPS` lists `CONFIRMED` then `CANDIDATE`, in scan order
  within each group; never sorted by RR, direction or any other property.
- **The watchlist is still fixed and not configurable at the CLI**, unchanged from Milestone AT.
- **`_price` formatting is duplicated across three modules** (pure formatting, not logic) — a P3,
  matching an existing repository pattern rather than introducing a new one.
- **No coverage tooling available in this environment** — substituted with a manual per-function audit
  plus 7/7-detected mutation testing (§6–7), not a claim that this is equivalent to a measured number.

## 12. Recommended next milestone

Per the brief, this task does not select the next one. Two items this milestone's own output makes more
concrete, named without recommending either: making `WAIT REASONS`' grouping family-aware (would need a
small, explicit extension to `policy.py`'s own tally output — e.g. naming which families voted, not just
counting them — so this presentation layer would still not have to duplicate logic to read it); and a
Telegram delivery surface for `render_scan_report`'s output, since this milestone was explicitly built
ASCII-only and width-guarded with that destination in mind.
