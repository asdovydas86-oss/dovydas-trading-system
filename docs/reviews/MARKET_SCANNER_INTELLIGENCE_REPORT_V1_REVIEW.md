# Market Scanner Intelligence Report v1 — independent review

**Milestone:** AU
**Reviewed:** 2026-08-07
**Design:** [MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md](../design/MARKET_SCANNER_INTELLIGENCE_REPORT_V1.md)
**Scope:** `src/fmis/swing_setup/scan_report.py` (new), `result_status` promotion in
`src/fmis/swing_setup/scan.py`, the `--table`/`SCAN_COMMAND` wiring in `src/fmis/pipeline/cli.py`,
`src/fmis/swing_setup/__init__.py`'s new exports, `tests/test_swing_setup_scan_report.py` (new) and the
`tests/test_pipeline_cli_scan.py` update.

## Method

The task brief named the exact adversarial brief to run: *"Reviewer must try to prove: report lies;
counts disagree; summary disagrees; reason disagrees; duplicate logic exists; orchestration leak;
presentation leak."* This was run as a genuinely independent pass — a separate agent, with no memory of
implementing the feature, was briefed on the brief above and told explicitly not to accept a docstring's
claim about itself as proof, and to reproduce any finding through the real `evaluate_setup` path rather
than only hand-built adversarial objects. It read `models.py`/`policy.py` independently to verify every
provenance claim in `scan_report.py`'s own docstring, ran the full test suite, and constructed its own
`SetupInputs` fixtures to probe the two sections that make an interpretive choice (`MARKET OVERVIEW`'s
bucketing, `ACTIONABLE SETUPS`' CONFIRMED/CANDIDATE symmetry) rather than trusting the ones already in
the test file.

## Findings

### P0 — found, fixed, and confirmed live

**MARKET OVERVIEW's `TRENDING` bucket could directly contradict a `WAIT` reason for the same symbol in
the same report.** `context_regime_structure` (from `fmis.market_regime`, gates `evaluate_setup`'s
"not trending → WAIT" branch) and `context_structural_trend` (from `fmis.structural_trend`, fed the
first draft's bucket) are two independently computed facts that can disagree — `evaluate_setup` computes
`directional_factors` *before* checking the regime-structure gate, so a symbol can fail the gate ("regime
structure is ranging/transitioning, not trending") while its `context_structural_trend` factor still
reads `SUSTAINED_HIGHER`/`LOWER`. The reviewer reproduced this through real `evaluate_setup`, not a
contrived object.

**This was not only a hand-built reproduction — it was already present in this milestone's own first
live scan against real Binance data**, run before the review, saved verbatim: `BNBUSDT`, `NEARUSDT` and
`UNIUSDT` appeared in `TRENDING (12)` in the `MARKET OVERVIEW` section while `WAIT REASONS` — twelve
lines later, same report, same run — read *"3 symbols: BNBUSDT, NEARUSDT, UNIUSDT / Context-role (1w)
regime structure is transitioning, **not trending**."* A trader reading top-to-bottom would see the same
three symbols called trending and then, moments later, explicitly not trending.

**Fix:** the bucket label was renamed `DIRECTIONAL` — the word "trending" no longer appears anywhere in
this module's own text, so no rendering of this section can collide with a `WAIT` reason's wording
regardless of which underlying fact produced either line. Pinned by
`test_market_overview_never_uses_the_word_trending`. Confirmed live on a second scan: the same
underlying data (`BNBUSDT`/`NEARUSDT`/`UNIUSDT` still transitioning, still WAIT) now renders with no
lexical collision anywhere in the page.

### P1 — found, fixed, and confirmed live

**ACTIONABLE SETUPS silently dropped RR and target for `CANDIDATE` rows even when both were already
computed.** The brief explicitly asked for "CONFIRMED/CANDIDATE with reasons, RR, targets, stops."
`_candidate_block`'s first draft printed only `reason`, `needs`, and a bespoke `risk: stop {price}` line
— it never read `assessment.risk_reward` or `assessment.targets`. `risk_reward` is computed by
`policy.py` whenever both a stop and a target exist, **independent of `state`** — a `CANDIDATE` with a
qualifying level on each side routinely carries a full `RiskReward`. Reproduced against the milestone's
own fixture (`candidate_short_with_watched_level`: target `0.815`, RR `0.43`) and, again, already present
in the first live scan: `ATOMUSDT CANDIDATE` printed only `risk: stop 1.365`, with no RR and no target
line at all, even though the second (fixed) live scan shows the same symbol, same data, actually carries
`RR 8.00` and `target 1.212`.

**Fix:** `_confirmed_block` and `_candidate_block` now share one header builder, `_setup_header`, that
reads and prints `risk_reward`/`stop`/`targets` identically for both states — no special-casing left to
silently drop a number one branch happens to compute and the other doesn't check for. Pinned by
`test_candidate_shows_rr_and_target_when_already_computed`. Confirmed live: both `CANDIDATE` rows in the
second scan (`ATOMUSDT`, `APTUSDT`) now show `RR`/`target` alongside `stop`.

### P1 — related, same root cause, fixed as a side effect of the P0 fix

**A `CONFIRMED`/`CANDIDATE` result could land in `MARKET OVERVIEW`'s `NO DATA`/`CONFLICTED` bucket even
though it is a live, directional trade**, because the first draft's bucket read only the
`context_structural_trend` factor, while the tally that actually decides `direction` can be won by the
*other* two families while that one factor is `UNAVAILABLE`/`CONFLICTING`. Reproduced by the reviewer
through real `evaluate_setup` (`context_structural_trend=INDETERMINATE`, the other two families LONG,
execution confirms → `CONFIRMED LONG RR 3.00` bucketed `NO DATA`). Not independently observed live (the
scan universe's own data did not happen to produce this combination on the day tested), but reachable
and real. **Fix:** `_overview_lean` now reads `SetupAssessment.direction` — the policy's own final,
all-families-considered verdict — first, and only falls back to the `context_structural_trend` factor's
own lean for a `WAIT` result, which has no `direction` of its own to read. A `CONFIRMED`/`CANDIDATE`
result can no longer be bucketed from one family in isolation. Pinned by
`test_market_overview_buckets_a_confirmed_trade_as_directional_even_when_its_own_context_trend_factor_disagrees`.

### P2 — informational, not fixed, disclosed instead

1. **`WAIT REASONS`' exact-text grouping can merge two symbols reaching the "factors do not agree"
   branch through different families**, since that branch's thesis is templated only from vote *counts*
   (`1 long, 1 short, ...`), not from which families cast which vote. Fixing this would require
   `scan_report.py` to re-derive which-family-voted from `directional_factors` — duplicating a piece of
   `policy.py`'s own tally logic this module exists specifically not to duplicate. Judged: grouping by
   the engine's own exact wording, warts included, is the lesser fabrication versus this presentation
   layer inventing its own independent classification of *why* a symbol waited. Disclosed directly in
   the module docstring rather than silently accepted.

### P3 — informational, no action

1. **`_price` price-formatting is duplicated across three modules** (`scan.py`, `scan_report.py`,
   `render.py`'s `_number`) rather than shared from one place. Pure formatting, not business/domain
   logic, so it does not violate the brief's "no duplicated business logic" rule — each copy already
   documents the others as its source of truth, matching the existing repository pattern
   (`fmis.daily.render` and `fmis.swing_setup.render` already duplicate the identical one-liner). Low
   drift risk given the format string is a single, rarely-touched constant.

### Claims independently verified, not broken

- **Report lying via fabricated text**: every `reason`/`needs`/`invalidation`/WAIT-reason line traces
  exactly to `SetupAssessment.thesis`/`.confirmation`/`.invalidation`, verified both by the reviewer
  reading `models.py`/`policy.py` directly and by dedicated tests
  (`test_confirmed_setup_reason_is_verbatim_thesis_and_confirmation`,
  `test_candidate_setup_reason_is_verbatim_thesis`, `test_wait_reason_text_is_verbatim_thesis`, and
  others) that parse the wrapped output back out and compare it, character-for-character (modulo
  whitespace reflow), against the source tuple. No fabricated sentence found anywhere.
- **Counts disagreeing between `render_scan` and `render_scan_report`**: both call the identical, single
  `scan.result_status` — confirmed by test (`test_scan_summary_counts_agree_with_render_scan`,
  parametrized across four result mixes including the full 20-symbol universe) and by code reading; the
  two summaries cannot drift by construction, not merely by coincidence.
- **Orchestration/presentation leak**: `scan_report.py` imports only the `SetupRunResult` *type* from
  `compose.py`, calls no engine function, performs no I/O, and computes no new number — pure formatting
  over already-computed fields. `scan.py`/`compose.py`/`policy.py`/`models.py` gained no new formatting
  logic (`scan.py`'s only change is the `_status` → `result_status` rename, identical body). CLI wiring
  is a single boolean branch between two renderers with no duplicated logic.
- **Duplicate business logic**: none found. The one place a duplication might have crept in — the
  `_setup_header` refactor that now shares CONFIRMED/CANDIDATE formatting — is presentation, not policy;
  it reads fields `policy.py` already computed rather than re-deciding anything.

## Test results

Before this milestone: 4,423 passing (post-AT baseline plus this milestone's `result_status` rename).
After this milestone including both review-driven fixes: **4,426 passing**, zero failures, zero skips.
`tests/test_swing_setup_scan_report.py`: 45 tests (grew by 5 during the review pass: two P0/P1
regression tests, one `_setup_header`-symmetry regression test, and two updated assertions for the
renamed bucket label).

## Live verification

`fmits scan` was run against real Binance data twice, both captured verbatim (no mocking, no fixture):

- **First run, against the pre-review draft**: 20/20 symbols returned a result, 0 `ERROR`, 15 `WAIT`,
  2 `CANDIDATE`, 3 `CONFIRMED` — the exact live transcript that surfaced both fixed findings above,
  independent of the reviewer's own hand-built reproductions.
- **Second run, after both fixes**: same live scan, same real data. `TRENDING` does not appear anywhere
  in the page (`"TRENDING" in text` is `False`, checked directly). Both `CANDIDATE` rows (`ATOMUSDT`,
  `APTUSDT`) now print `RR`/`target` alongside `stop`. Every line still fits the 78-column page under
  real, unselected data (`max(len(line) for line in text.splitlines()) == 78`).

## Verdict

**Ship with the fixes applied.** The review found the module well-built and faithful for the majority of
its surface on the first pass — reason/needs/invalidation text was already genuinely verbatim, counts
could not drift, and there was no orchestration or presentation-layer leak. But the brief's central
question — "can the report contradict itself, or silently drop a number, for the same symbol" — had two
real, reproducible yes answers, both reachable through the actual production `evaluate_setup` path with
realistic inputs, and both already present in this milestone's own first live scan rather than only in
contrived fixtures. Both are fixed, both fixes are pinned by regression tests built directly from the
review's own reproduction steps, and both fixes are confirmed against a second live scan. One
P2 (WAIT-reason grouping coarseness) is disclosed rather than fixed, for a stated reason — fixing it
would require duplicating policy logic this module exists specifically to avoid duplicating. No P0 or
P1 remains open.
