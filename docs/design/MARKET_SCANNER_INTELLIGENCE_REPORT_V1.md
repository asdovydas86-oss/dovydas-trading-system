# Market Scanner Intelligence Report v1 — design

**Milestone:** AU
**Status:** Implemented
**Date:** 2026-08-07
**Contracts:** none new — reuses [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md)
**Repository state at start:** `81a6202` (Milestone AT, plus its documentation reconciliation)

## 1. What this milestone builds

Milestone AT (`fmits scan`) prints one compact table: a row per symbol, five columns. It answers "what
did every symbol get?" but not "what should I actually read this morning?" — a trader still has to scan
twenty rows to find the two or three that matter, and a `WAIT` row gives no reason. This milestone adds
a second renderer, `fmis.swing_setup.scan_report.render_scan_report`, over the exact same scan result —
a market intelligence report with four sections: a summary, a market overview, actionable setups with
their stated reasons, and WAIT results grouped by reason. `fmits scan` now prints this report by
default; `--table` prints the original AT table unchanged.

**Not built, and named here so the gap is not silent:** no new engine logic, no ranking, no score, no
probability, no AI/LLM interpretation. Every fact printed by the new report already existed on a
`SetupAssessment` before this milestone started — this is a presentation-only milestone, verified in
§6 and independently in the review.

## 2. Where it sits

A second module beside `scan.py`, not inside it: `fmis.swing_setup.scan_report`. Same package as
`scan.py` (ADR-0028 §2 already permits directional vocabulary here — see the AT design record §2 for
the full argument, unchanged), same input type (`tuple[SetupRunResult, ...]`), same
`fmis.swing_setup.compose.run_setup_for_symbols` underneath. `scan.py` keeps owning orchestration
(`run_market_scan`) and its own table (`render_scan`); `scan_report.py` owns only presentation.

```
run_market_scan(symbols=SCAN_UNIVERSE)  ──►  tuple[SetupRunResult, ...]
                                                        │
                                       ┌────────────────┴────────────────┐
                                       ▼                                 ▼
                         render_scan(results)                render_scan_report(results)
                         (Milestone AT, unchanged)            (this milestone, new)
                         compact table, `--table`             market intelligence report, default
```

One shared classifier, not two: `scan._status` was promoted to a public `scan.result_status`, and both
renderers call it. The two summaries cannot disagree by construction — proven by a cross-checking test
(`test_scan_summary_counts_agree_with_render_scan`), not merely by inspection.

## 3. The four sections, and exactly which field backs each one

### SCAN SUMMARY

Identical counts to `render_scan`'s own summary line, computed once with `result_status` and printed as
a dot-leader block (`WAIT ................ 15`) instead of one dense line — the only thing this section
changes from AT is layout.

### MARKET OVERVIEW

Every scanned symbol bucketed `DIRECTIONAL`, `CONFLICTED`, `NO DATA` or `NOT SCANNED`. The rule, in
`_overview_lean`:

1. A `CANDIDATE`/`CONFIRMED` result (`direction is not None`) is bucketed from `SetupAssessment.direction`
   itself — the policy's own final directional verdict, reached from all three families plus execution
   confirmation.
2. A `WAIT` result (`direction is None`, no final verdict exists) falls back to the `lean` of its own
   `context_structural_trend` directional factor (`DirectionalFactor.lean`,
   `policy._directional_factors`'s first entry) — the same factor `ACTIONABLE SETUPS`' own reason lines
   already cite by name.
3. A failed symbol (`assessment is None`) is `NOT SCANNED`.

**This is not `fmis.market_regime.StructureState`** (`TRENDING`/`RANGING`/`TRANSITIONING`/...). That
value is never stored on `SetupAssessment` — only folded into one formatted sentence inside
`regime_context` — and this module does not parse rendered prose to recover a fact it would otherwise
have to fabricate the meaning of. Reusing the `Lean` vocabulary the engine itself already assigned
(`LONG`/`SHORT` → `DIRECTIONAL`, `CONFLICTING` → `CONFLICTED`, `UNAVAILABLE` → `NO DATA`) is the only
bucketing that adds no interpretation beyond what `evaluate_setup` already decided.

**This design is the second draft.** The first draft bucketed every result — including `CANDIDATE`/
`CONFIRMED` — from the `context_structural_trend` factor alone, and labelled the `LONG`/`SHORT` bucket
`TRENDING`. An adversarial review (§7) found this reachable through the real `evaluate_setup` path,
not a contrived object:

- A `CONFIRMED` trade can be won by the *other* two families while `context_structural_trend` itself
  reads `UNAVAILABLE`/`CONFLICTING` — the old rule would bucket a live trade under `NO DATA` or
  `CONFLICTED`.
- `context_regime_structure` (which gates the "not trending" `WAIT` branch in `policy.py`) and
  `context_structural_trend` (which fed the old bucket) are two independently computed facts that can
  disagree. The old rule could print `TRENDING` for a symbol whose own `WAIT` reason, elsewhere in the
  same report, says "regime structure is ranging, **not trending**" — a literal contradiction between
  two sections about the same symbol.

Reading `direction` first when one exists removes the first defect outright — a final directional
verdict cannot itself be wrong about which family it came from. Renaming the label to `DIRECTIONAL`
(the word "trending" never appears in this module's own text) removes the second regardless of which
underlying fact produced the bucket. Both are pinned by regression tests:
`test_market_overview_buckets_a_confirmed_trade_as_directional_even_when_its_own_context_trend_factor_disagrees`
and `test_market_overview_never_uses_the_word_trending`.

### ACTIONABLE SETUPS

Every `CONFIRMED` result, then every `CANDIDATE` result, in scan order within each group — a filter,
never a reorder, the same discipline `render_scan`'s own `TOP OPPORTUNITIES` applies. Both states share
one header builder, `_setup_header`: `SYMBOL  SIDE  RR x.xx` plus a `target`/`stop` line, reading
`SetupAssessment.risk_reward`/`.stop`/`.targets` directly and printing them identically regardless of
state. `policy.py` computes `risk_reward` whenever a stop and a target both exist — never conditioned on
`state` — so a `CANDIDATE` with a known level on each side already carries a real RR exactly as a
`CONFIRMED` result does.

**This, too, is a second draft.** The first draft printed RR/target for `CONFIRMED` only; `CANDIDATE`
printed a bespoke `risk: stop X` line and silently dropped RR/target even when both were already
computed — reachable through the milestone's own `candidate_short_with_watched_level` test fixture (RR
0.43, target 0.815), not a corner case. The adversarial review named this directly against the task
brief's own wording ("ACTIONABLE SETUPS ... CONFIRMED/CANDIDATE with reasons, RR, targets, stops").
Fixed by sharing `_setup_header` between both blocks; pinned by
`test_candidate_shows_rr_and_target_when_already_computed`.

The "reason"/"needs"/"invalidation" lines are `SetupAssessment.thesis`/`.confirmation`/`.invalidation`,
printed verbatim — not summarised, not paraphrased. Every reason line in the report is checked in tests
against the exact source tuple it was copied from (`_extract_block` + `_dewrap`/`_normalize` helpers in
`tests/test_swing_setup_scan_report.py`), not merely "looks plausible".

### WAIT REASONS

Every `WAIT` result grouped by its own `thesis[0]` string, compared for exact equality, counted, and
sorted by descending count (ties keep scan order — the order each reason was first seen). Two symbols
reaching `WAIT` by the same policy branch produce byte-identical thesis text, because every `_wait` call
site in `policy.py` templates its sentence from `SetupInputs` values with no symbol name embedded — so
exact-string grouping is a real category, not a coincidence that happens to work on today's fixtures.

**Known, accepted limitation**, disclosed in the module docstring rather than fixed: the "factors do not
agree" branch's thesis is templated only from vote *counts* (`1 long, 1 short, 1 conflicting, ...`), not
from *which* families voted which way. Two symbols reaching that branch through different families can
render identical text and group together. Fixing this would require this module re-deriving
which-family-voted from `directional_factors` — duplicating a piece of `policy.py`'s own tally logic
that this module exists specifically not to duplicate. Grouping by the engine's own exact wording, warts
included, was judged the lesser fabrication; the alternative (this module inventing its own,
independent classification of *why* a symbol waited) is exactly the kind of interpretation the milestone
brief forbids.

### SCAN ERRORS

Present only when at least one symbol failed: the symbol and its `SetupRunResult.failure` string,
verbatim, wrapped. Not part of the brief's four named sections, but necessary for the same reason
`render_scan` prints a failure block under an `ERROR` row — a failure that's counted in `SCAN SUMMARY`
but never explained anywhere would be a completeness gap the "no invented facts, but no missing ones
either" discipline this repository already follows elsewhere would not accept.

## 4. Human-readable explanation generation — how "no inference" was actually enforced

The brief's own example (`WAIT` → "Higher timeframe not trending. Execution confirmation missing. No
structural target.") reads as a paraphrase. This implementation deliberately does not paraphrase:
`policy.py` already produces one complete, deterministic, human-readable sentence per outcome (`_wait`'s
`thesis`, the confirmed/candidate branch's `thesis`/`confirmation`/`invalidation`) — templated from
`SetupInputs`, with no symbol name and no free text, at the exact point the decision is made. Printing
that sentence verbatim *is* the "pure deterministic template" the brief asks for; writing a second,
shorter version of the same sentence in this presentation layer would be a second place the same
decision could be described, and the two could drift. Every "reason"/"needs"/"invalidation"/WAIT-reason
line in the report is one of these sentences, unedited, and the tests check for exact provenance, not
resemblance.

## 5. ASCII-only, deliberately, and why the exception exists

Every rule, section title, dot-leader and label this module writes itself uses `-` and `=`, never a
box-drawing character or an em dash — unlike `render_scan`/`render_setup` (Milestones AT/AR), which
both use `—`/`─`/`═` and predate this requirement. The brief names "no Unicode dependency" directly
("readable in terminal... Telegram... logs"), and this module is new, so it follows it from the start.

The one exception is content this module does not write: a `thesis`/`confirmation`/`invalidation`
sentence is printed exactly as `policy.py` composed it, including whichever punctuation that sentence
already uses — a small number use `—`. Editing an inherited sentence to enforce this module's own
character set would itself be an invented change to text this milestone promises never to touch.

## 6. What this milestone deliberately does not touch

`fmis.swing_setup.compose`, `fmis.swing_setup.policy` and `fmis.swing_setup.models` are unmodified — a
zero-line diff, confirmed by the review's independent read. `fmis.swing_setup.scan` gained exactly one
change: `_status` renamed to public `result_status` (same body, same three lines) so both renderers
share one classifier instead of two copies. No ADR added or amended — no new boundary, no new
permitted-vocabulary location; `scan_report.py` sits in the same ADR-0028-exempt directory `scan.py`
already does.

## 7. CLI

`fmits scan` prints `render_scan_report` by default (Milestone AU). `--table` prints the unchanged
Milestone AT table. Every other flag (`--limit`, timeframe roles, `--band`, `--transition-lookback`)
applies identically to both, unchanged from AT. Exit code is unaffected by which renderer runs — both
share `_exit_code_for` over the same `results`.

## 8. Testing strategy

`tests/test_swing_setup_scan_report.py` (45 tests): type/shape guards, determinism, page-width
discipline (including a live-shaped 20-symbol worst case and a monkeypatched-width failure guard),
SCAN SUMMARY counts cross-checked against `render_scan`, MARKET OVERVIEW bucketing for every `Lean`
value plus the two regression cases from the review, ACTIONABLE SETUPS reason/needs/invalidation
verbatim-fidelity checks (parsed back out of the wrapped output and compared against the exact source
tuple), the RR/target CANDIDATE regression, WAIT REASONS grouping/counting/sort-order/tie-break, SCAN
ERRORS presence/absence and failure isolation, and one golden full-page exact-string test.
`tests/test_pipeline_cli_scan.py` gained the default/`--table` split; `tests/test_swing_setup_scan.py`
is otherwise unaffected by the `_status` → `result_status` rename (no external test referenced the
private name).

## 9. Live verification

`fmits scan` was run against real Binance data twice — once against the first draft (which reproduced
the `TRENDING`-label collision and the dropped-CANDIDATE-RR gap live, on real symbols, not only in the
review's hand-built fixtures), and once against the fixed version, confirming both defects are gone and
every line still fits the 78-column page under real, unselected data. Full transcript in the
implementation report, §8a.
