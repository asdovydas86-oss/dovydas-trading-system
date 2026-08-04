# Decision Context Engine v1 — Design

**Milestone:** AL
**Status:** Implemented by [ADR-0026](../adr/ADR-0026-decision-context-boundary.md)
**Date:** 2026-08-04

---

## 1. Phase 1 — was this the right milestone? The evidence

The board's NOW item was the daily workflow. This milestone was proposed instead, so the first work
was proving which is correct. Measured at `6ebf1e0`:

| Candles | What the page rendered | What was underneath |
|---:|---|---|
| 12 | 5 available · 2 partial | regime all three dimensions `insufficient`, 0 levels |
| 40 | 5 available · 2 partial | 2 dimensions `insufficient`, 3 features warming up |
| 260 | 6 available · 1 partial | everything classified |

**A 12-candle page and a 260-candle page produced nearly the same status profile.** A section's status
says whether it *produced output*, not whether the output can be *trusted*. `required_candles` existed
per indicator and `InsufficientDataError` fired only at zero closed candles; nothing judged the
analysis as a whole. That is the bias `SPEC` §7 names, live in the product.

**It also gates the boarded milestone.** `reports/0005` Phase 4 names *"alert fatigue from an
unfiltered brief"* as the daily workflow's principal risk. The filter is a sufficiency judgement.
Building the workflow first means building it inside and extracting it later — the rewrite this
milestone was asked to avoid.

**Alternatives weighed and rejected on evidence:** Memory is blocked on open decision D-01. Adding
volume and volatility descriptors would fill two empty evidence families but is incremental content,
not architectural reduction.

## 2. The one question

> Does the current analysis contain enough trustworthy information to continue toward a trading setup?

Nothing else. No direction, entry, exit, target, stop, size or risk — asserted over every public name
and every reachable statement.

## 3. The design questions, resolved

### 3.1 Does this contradict ADR-0025's refusal of a composite label?

**No.** ADR-0025 refused to collapse *market state*. This judges the *analysis*. `SPEC` §6 requires
missing data as a first-class output; a system that computes uncertainty per value and never aggregates
it has met the letter and not the intent.

### 3.2 Where do the thresholds come from?

**Nowhere — every rule is delegated.** Depth compares against the view's own `required_candles`,
warm-up against the feature engine's metadata, determinacy against `fmis.market_regime`, structure
against `fmis.level_crossing`, evidence against ADR-0008 §7's own verdict.

`ContextPolicy` therefore carries no numbers, uniquely among this repository's policies. A test asserts
no numeric literal beyond 0 and 1 exists in the evaluator.

### 3.3 What does the engine consume?

A narrow `ContextInput` — seven integers, two strings, a flag, a timestamp. **Not the `Workspace`:**
that model is presentation-shaped, its body values being formatted strings like
`('setup · 1d', 'insufficient', ...)`. An engine reading it would parse presentation back into data.

### 3.4 Do conflicts reduce sufficiency?

**No, and this is deliberate.** Sufficiency is about availability. Penalising disagreement rewards
pages that look tidy by being one-sided — the failure `docs/analysis-notes.md` records. The count is
carried into metadata and read by no rule; a test asserts varying it changes nothing.

### 3.5 Three states, not two

`SUFFICIENT` / `LIMITED` / `INSUFFICIENT`. The middle is the honest one: nothing blocking is missing,
but the analysis is degraded in named ways and continues *with the limitation attached*.

## 4. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | No forbidden word in any name or produced statement | whole-word sweep over every reachable combination |
| I2 | No threshold is invented | AST: no numeric literal beyond 0 and 1 in the evaluator |
| I3 | Every requirement names the layer owning its rule | `SOURCES` covers `Requirement` exactly |
| I4 | Conflicts move nothing | state and checks compared across conflict counts |
| I5 | Depth is judged against the caller's own requirement | same candle count passes and fails |
| I6 | Severity is fixed, not configurable | no override field exists |
| I7 | `may_continue` can never disagree with the state | swept across strictness and gaps |
| I8 | Every requirement is reported, met ones included | completeness and order validated |
| I9 | The engine imports nothing from `fmis` | AST over the package |
| I10 | The gate sits after conflicts and before risk | `SECTION_ORDER` asserted |

## 5. Measured results

**Correctness.** 3,766 tests pass, identically under `-W error` (3,702 before AL; **+64**). Coverage
**100 %** on all four `decision_context` modules and all six `workspace` modules. Public exports 228,
zero collisions. Import cycles 0. Runtime dependencies 0. `pyproject.toml` and `uv.lock` untouched.

**Mutation.** 43 probes: **43 detected, 0 survivors, 0 no-ops**, byte-identical restoration. Eleven
probes survived their first run and every one was a real assertion gap against 100 % line coverage —
see [the review](../reviews/DECISION_CONTEXT_V1_REVIEW.md) §5.

**Review.** No P0, no P1, **two P2 found and fixed** — `may_continue` contradicting its own state under
a strict policy, and a `DEFAULT_POLICY` export collision with `fmis.market_regime` — and three P3.

**Live.** `fmits swing BTCUSDT` renders the gate as a twelfth section between conflicts and risk.

## 6. What it does not claim

That the analysis is *correct* — only that the data each layer asked for is present. A `SUFFICIENT`
context over a wrong reading is still a wrong reading, and the page says so.
