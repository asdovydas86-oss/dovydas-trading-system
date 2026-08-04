# Deterministic Daily Workflow v1 — Design

**Milestone:** AN
**Status:** Implemented
**Date:** 2026-08-04
**Reviewed by:** [DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md](../reviews/DETERMINISTIC_DAILY_WORKFLOW_V1_REVIEW.md)

---

## 1. The problem, measured

Every capability before AN answered about **one symbol**. `fmits swing BTCUSDT`
produces a complete page — and produces exactly one. An owner who watches eight
instruments ran eight commands, read eight ~270-line pages, and held the
comparison in their head.

That is not a workflow, it is a demo repeated eight times. Its three specific
failures:

| Failure | Consequence |
|---|---|
| No repeatable routine | what gets analysed depends on what the owner remembered to type |
| No shared settings | eight runs, eight chances for one to use different bars or limits |
| No failure record | a symbol whose fetch failed is a command that scrolled past; nothing says it was skipped |

The third is the dangerous one. A morning where BTC, ETH and SOL were analysed
and ADA silently was not looks exactly like a morning where ADA was analysed and
found unremarkable.

## 2. Scope

**In:** the `DailyRun` model · a sequential runner with per-symbol error
isolation · a compact terminal readiness index · `fmits daily` · tests · this
design · an independent review.

**Out, and deliberately so — each was named in the milestone brief as a
non-goal:** scanning, ranking, scoring, signal generation, recommendation,
portfolio state, a scheduler or daemon, notification delivery, persistence, AI
summarisation, execution.

## 3. The design questions, resolved

### 3.1 Is a daily run an object or a command?

**An object**, for the reason AK settled the same question: `DailyRun` is frozen,
schema-versioned, and holds real `Workspace` and decision-context objects by
reference. The terminal index is one consumer. A future Telegram digest, JSON
export or stored history reads the same instance and re-derives nothing.

### 3.2 Where does it sit?

A **second application-layer root**, `fmis.daily`, above `fmis.workspace`. It
imports the workspace, the decision context, the regime policy and the provider
errors; **nothing imports it except `fmis.pipeline.cli`**, the terminal boundary.
Four pre-existing import-direction guards were widened to name it — the same
widening AK performed for `fmis.workspace`, and in the same direction ADR-0007
permits. No engine gained a permission.

`fmis.pipeline.__init__` does not import `cli`, so importing the pipeline still
does not load this layer; a subprocess test asserts it.

### 3.3 What does a row say, and what must it never say?

A row says **whether the analysis rests on enough trustworthy data** — the
`ContextState` that Milestone AL computed, carried through verbatim. `ResultCategory`
mirrors `ContextState` exactly plus one member, and a test asserts the mapping
is value-identical, because AL owns that judgement and ADR-0026 forbids adding
thresholds around it.

The added member is `FAILED`, and the distinction it draws is the model's whole
point:

> **`INSUFFICIENT`** — an analysis happened, and it rests on too little. A fact
> about the market's data.
> **`FAILED`** — the analysis did not happen. A fact about the network.

Conflating them tells the owner they are having a thin-data morning when they are
in fact having an outage.

A row must never say, and no member, string or export in the package can express:
a rank, a score, a direction, an opportunity or a recommendation. Twenty-one
forbidden words are asserted over every public name, and an AST scan asserts the
package contains exactly **one** `sorted()` — which orders the duplicate symbol
names inside an error message.

### 3.4 Why is the run not sorted?

Because **a sorted list is a claim**. Ordering by readiness produces a page whose
top row reads as the best idea, whatever the header says. `SPEC` §7 names
excessive confidence from incomplete data as a bias to guard against, and it
applies to a list exactly as it applies to a page.

The rows therefore stay in the order the caller typed. The **summary counts** use
a fixed reporting order, which is not an ordering of instruments.

### 3.5 What happens when one symbol fails?

It becomes a row. `analyse_symbol` is the single place a `try` exists, so every
symbol is isolated identically and the run loop contains no error handling of its
own.

`_FAILURE_KINDS` is an **ordered tuple**, not a mapping, because
`BinanceRequestError` and `BinanceResponseError` are both `ValueError`s and the
first match must be the specific one. A test asserts no entry shadows a later one.

**What is not caught matters more than what is.** Only the six listed exception
types become results. A `KeyError` from a defect in this repository propagates
and stops the run, because a report that renders an internal bug as an ordinary
market failure teaches the owner to ignore both. Three separate probes confirm
an unexpected exception is neither swallowed nor re-labelled.

### 3.6 Why sequential, when concurrency is easy?

Measured, not assumed:

| Universe | FMITS compute | Wall clock (live) | Compute share |
|---:|---:|---:|---:|
| 3 symbols | 0.07 s | 4.58 s | **1.4 %** |
| 50 symbols (offline) | 1.10 s | — | — |

Compute is **22 ms per symbol** and linear. A daily run is entirely
network-bound, so concurrency buys wall-clock at the cost of provider rate-limit
exposure, non-deterministic failure interleaving and a much harder isolation
story — for a universe a human reads in one sitting. A test asserts no
concurrency primitive appears in the module, so the decision cannot erode
silently.

### 3.7 Why is `MAXIMUM_SYMBOLS` fifty?

**A stated policy, not a measurement** — the ADR-0017 precedent. Three timeframes
per symbol makes fifty symbols a hundred and fifty sequential requests. A run
large enough to be rate-limited halfway is a run whose failures are the tool's
fault rather than the market's. A caller with a larger universe splits it, which
is visible, instead of discovering the limit as a provider error.

### 3.8 Why are duplicates rejected rather than collapsed?

The `DuplicateLevelError` rule: **validate, never repair.** Collapsing
`BTCUSDT BTCUSDT ETHUSDT` to two rows changes the row count the caller expected
without saying so. The universe is validated **before the first request**, so an
invalid one costs zero provider calls — asserted by a test that checks the
transport was never called.

### 3.9 Where does `reference_time` come from?

**The outer boundary.** Nothing in the package reads a clock — asserted over the
source — so two runs over the same stored candles are identical. `fmits daily`
accepts `--reference-time` precisely so a page can be reproduced.

Limitation **AN-3** states the consequence plainly: each symbol is fetched at a
different instant, the run has **no shared as-of**, and rows are not comparable
in time.

### 3.10 Why a compact index rather than concatenated pages?

Twenty full workspaces is ~5,400 lines nobody reads — the alert fatigue
`reports/0005` Phase 4 names as this milestone's principal risk. Fifty symbols
render in **83 lines**, and the footer says exactly how to open any one page in
full. Every state carries a **glyph and a word**, so nothing depends on colour
surviving a pipe or a log file.

## 4. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | Exactly one result per requested symbol, in input order | model validation + renderer row count |
| I2 | A failed symbol carries its reason; a completed one carries its analysis | mutually exclusive, both directions rejected |
| I3 | `INSUFFICIENT` is never `FAILED` | asserted on `completed` |
| I4 | The category is the `ContextState` verbatim | value-identity over the whole mapping |
| I5 | Nothing ranks, scores or recommends | 21-word scan over public names; exactly one `sorted()` in the package |
| I6 | Counts are projections, never stored | no field name contains "count" |
| I7 | A defect is never a market failure | three probes; unlisted exceptions propagate |
| I8 | The universe is validated before any fetch | transport call list asserted empty |
| I9 | No clock is read inside the package | source scan for `datetime.now` / `time.time` |
| I10 | Execution is sequential | no concurrency primitive; fetch order asserted |
| I11 | The renderer imports only the model | AST over imports |
| I12 | No page line exceeds 78 columns | every line, plus a render-time guard that **raises** |
| I13 | No engine imports `fmis.daily` | directory scan; only `pipeline/cli.py` |

## 5. Measured results

**Correctness.** 3,898 tests pass, identically under `-W error` (3,766 before AN;
**+132**). Coverage **100 %** on all four `fmis.daily` modules and on
`pipeline/cli.py`. Public exports 242, zero collisions. Import cycles **0**.
Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

**Mutation.** 74 probes · 74 detected · 0 survivors · 0 no-ops. See the review §5.

**Capability.** One command now analyses a universe, records what failed and
why, and prints a page that fits on a screen.

## 6. What it does not claim

The index says which analyses are worth trusting. It says nothing about which
instruments are worth trading. No direction, no score, no ranking, no
recommendation is produced, and four limitations printed on every run say so —
the first of them denying, in the header, the exact reading the page most
invites.

## 7. Open decisions

| # | Question | Why deferred |
|---|---|---|
| **D-01** | Persisting a run across days | shared with `Workspace` (AK P3-3); the answer belongs to every metadata-carrying model at once |
| **D-02** | A watchlist file format | a universe is supplied by the shell today (`fmits daily $(cat list.txt)`); a stored watchlist is a persistence concern, not a run concern |
| **D-03** | Delivery outside the terminal | needs the model, which now exists; the renderer proves a second consumer costs nothing |
