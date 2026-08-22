# Global Market Pulse Foundation (Milestone BT) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0030 |
| **Title** | Global Market Pulse Foundation (Milestone BT) — `fmits pulse` |
| **Date** | 2026-08-22 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `1b56069` (production + tests), on base `8ecd822` |
| **Status** | Final |

---

## 1. What the owner can do now that was impossible before

```
fmits pulse
```

One command produces an honest deterministic orientation across the configured
market universe: each market's move over named horizons, those same moves
ordered by one stated quantity, measured volatility, co-movement against one
named reference, the age and provenance of every figure, and **every market that
could not be read together with the reason it could not**.

Before BT, every surface in this repository answered *"what about this asset?"*
— `fmits facts`, `mtf`, `regime`, `setup`, `evidence`, `swing`. `fmits scan`
answered *"which of my twenty symbols has a setup?"*, which is a search rather
than an orientation. Nothing answered the question that comes **first**: *what
is happening across the markets, and what can this system not tell me?*

The second half of that sentence is the milestone's real product. `fmits pulse`
reports five markets it cannot read — the S&P 500, the dollar index, gold, the
US 10-year yield and VIX — each naming the kind of adapter it would need. A page
that listed only what it can fetch would answer *"what is happening across the
markets"* with a crypto-shaped silence, and the reader would not know the
silence was there.

---

## 2. Starting state, verified

| Fact | Value |
|---|---|
| `HEAD` | `8ecd82283b8e990fb282c639411a6586f7fa409a` |
| `origin/main` | `8ecd82283b8e990fb282c639411a6586f7fa409a` (identical) |
| Working tree | Clean except 16 pre-existing untracked research documents |
| Stash | Empty |
| Milestone BS | Confirmed landed (`b6a456c` code, `8ecd822` docs) |

The reference SHA the task supplied was verified rather than assumed. The 16
untracked research documents under `docs/design/` and `docs/reviews/` were
present at the start and are **byte-for-byte unchanged**; none is staged.

---

## 3. Repository audit — what already owned each responsibility

The mandatory pre-work searched for every concept BT proposed. Four existing
owners were found and **reused rather than duplicated**; two concepts had no
owner and are the milestone's only genuinely new vocabulary.

| Responsibility | Existing owner | Decision |
|---|---|---|
| Return over a window | `fmis.relative_value.period_return` | **Reused.** `P_last / P_first − 1`, with `UNDEFINED` + reason for a zero denominator |
| Volatility | `fmis.relative_value.realized_volatility` | **Reused.** See §4 for why not `features.indicators.atr` |
| Correlation | `fmis.relative_value.pearson_correlation` | **Reused**, including its refusal to align |
| Candles → single series | `fmis.data.reduction.candle_series_to_observations` | **Reused.** Closed-only by construction |
| Price observation w/ provenance | `fmis.marks` | **Pattern reused, package not imported.** `fmis.marks` is a *price* snapshot for valuation; a pulse reading is a *set of derived moves*. Its `observed_at`-is-the-bar-open rule, its exactly-one-of-value-or-reason rule and its per-symbol failure isolation are all followed and cited in the source |
| Provider composition | `fmis.pipeline.prices`, `fmis.pipeline.candles` | **Pattern reused.** `fmis.pipeline.pulse` is a third sibling written to the same three rules |
| Staleness policy | `fmis.position_sizing.SizingPolicy` | **Reused as policy.** *An age judged against a number this build picked would be a threshold invented at exactly the point the specification says not to.* Age is always reported; `--max-age` is the owner's |
| Symbol universe | `fmis.swing_setup.SCAN_UNIVERSE` | **Deliberately not reused.** Twenty symbols is right for a scan (a search) and wrong for an orientation (a glance) |
| Market identity | `fmis.data.SeriesIdentity` | **Composed around, not extended.** Its docstring records that venue, asset class and quote currency were excluded because *"a field earns inclusion only if something in the repository today would be wrong without it."* BT is the first milestone where something would be — see §5 |

**Two concepts had no owner** and are new: a *benchmark registry* (a market with
its category, schedule, quote unit and provider mapping — or the reason it has
none) and a *trading schedule* vocabulary. `fmis.accounts.VenueId`/`MarketMode`
exist but are trading-domain types describing the owner's money, not the market.

---

## 4. Architecture

```
fmis.providers.binance          public klines            (adapter — the only place a URL exists)
    ↓
fmis.pipeline.pulse             composition root         (the only place a venue is named for a pulse)
    ↓
fmis.data.reduction             candles → observations   (closed bars only)
    ↓
fmis.relative_value             observations → numbers   (period_return, realized_volatility, pearson_correlation)
    ↓
fmis.market_pulse.measure       numbers → records
    ↓
fmis.market_pulse.pulse         records → one immutable page
    ↓
fmis.market_pulse.render        page → text
```

`fmis.market_pulse` is a **market-half deterministic package**. It imports
exactly three `fmis` packages — `fmis.data`, `fmis.relative_value` and itself —
and a guard test pins that set. No LLM, no prompt, no narrative, no hidden score.

### It is not a swing engine, and that is asserted by name

The milestone brief required the Pulse to be usable independently of swing
trading. Twenty forbidden dependencies are enumerated in
`test_market_pulse_architecture.py` and each is asserted individually:
`fmis.plan`, `fmis.position_sizing`, `fmis.paper`, `fmis.trade_lifecycle`,
`fmis.swing_setup`, `fmis.proposal`, `fmis.today`, `fmis.swing_workspace`,
`fmis.setup_evidence`, `fmis.decision_context`, `fmis.decision_support`,
`fmis.persistence`, `fmis.archive`, `fmis.providers`, `fmis.ingest`,
`fmis.marks`, `fmis.valuation`, `fmis.portfolio_risk`, `fmis.statistics`,
`fmis.market_regime`. The reverse direction is guarded too: **nothing below
imports it**, and only `fmis.pipeline.pulse` and `fmis/pipeline/cli.py` import
it from the pipeline.

### No second volatility engine

`fmis.features.indicators.atr` exists and is **deliberately not used**. ATR is an
absolute price range in a market's own quote currency, so BTC's and DOGE's are
not comparable — and comparability is the only reason this page prints
volatility beside other markets' at all. `realized_volatility` (sample standard
deviation of simple returns) is unitless and is the right primitive. No
volatility formula is written anywhere in the new package.

### It computes nothing

Three modules — `measure.py`, `pulse.py` and `fmis/pipeline/pulse.py` — hold
**zero arithmetic operators**, with no exception list, asserted after stripping
type annotations (`float | None` is a `BinOp`). `models.py` is permitted exactly
four operations, each pinned by source text: a count relationship (`bars + 1`),
a count (`len + len`), two durations (a reading's age, a window's span) and a set
difference. `render.py` is permitted exactly four, also pinned: the percent
scale, the page-width rule, and two string indents. The package holds **two float
literals in total**, both the `[-1, 1]` bound a Pearson correlation cannot leave.

---

## 5. Design decisions worth defending

### A horizon is a count of closed bars, never a duration

This is the decision that makes the page correct for markets that do not trade
continuously. *"The move over the last 24 closed 1h bars"* is well defined for a
market with any schedule; *"the move over the last 24 hours"* is only well
defined for one that never closes, and computing it by subtracting timestamps
would silently span a weekend for anything else.

`TradingSchedule` is the **minimum** session vocabulary and is deliberately not a
calendar: no holiday table, no exchange timezone, no open/closed computation.
`CONTINUOUS` may print a wall-clock equivalent; `SESSION_BOUND` and `UNKNOWN` may
not, and `UNKNOWN` answers exactly as `SESSION_BOUND` does — *a schedule nobody
established is not a schedule that happens to be 24/7*.

### The ordering is an ordering, not a score

> Markets are ordered by one measured quantity: their `period_return` over
> exactly one named horizon, among markets denominated in exactly one quote
> unit. Higher first. A tie is broken by `benchmark_id`, ascending.

Produced by **two stable sorts** rather than one composite key — ascending by id,
then descending by value — so there is no negation of a market quantity anywhere
in it. Seven quantities are named as excluded and printed under every ordering.
`RankedMove` has exactly three slots, and a guard forbids any field named
`score`, `weight`, `rank`, `confidence`, `probability`, `strength`, `grade`,
`rating`, `total` or `composite`.

This is deliberately *weaker* than `fmis.swing_workspace.ranking`'s
four-component key. That key exists because four engine states genuinely bear on
whether a setup is actionable; nothing comparable is true of *"which market moved
most"* — it is one number.

### An ordering refuses to mix quote units

A return on a market priced in EUR silently contains the EUR/USD move. So a
universe spanning two units produces **two orderings** per horizon, each printing
its unit, rather than one mixed ordering. Markets in another unit are not
*excluded* — they are outside the comparison and get their own.

### Five distinct absences, kept distinct

`unsupported` (no provider configured) · `unavailable` (a configured provider
failed) · `insufficient window` (fewer closed bars than the horizon names) ·
`mathematically undefined` (the engine's own `UndefinedReason`) · `not
comparable` (units or bars refuse it). **A zero move is none of those** — it
prints as `+0.00%`, and the constructor makes a value-and-a-reason, or neither,
unrepresentable.

### Correlation is measured against one reference, not as a matrix

A matrix over eleven markets is fifty-five numbers nobody reads, and every one
invites the causal reading `CO_MOVEMENT_CAVEAT` exists to refuse. The reference
is the first **read** market in universe order — a stated choice, printed on the
page. A pair whose bars do not line up exactly is reported unavailable rather
than intersected, because an intersection is a *different* window than the one
the page names.

---

## 6. Supported and unsupported markets — exactly

**Supported (6), all crypto spot on `binance-spot`, `1h` bars, quoted in USDT:**
`BTC` (BTCUSDT) · `ETH` (ETHUSDT) · `SOL` (SOLUSDT) · `BNB` (BNBUSDT) ·
`XRP` (XRPUSDT) · `DOGE` (DOGEUSDT)

**Unsupported (5), carried in the universe with their reasons:**

| Id | Market | Category | Schedule | Needs |
|---|---|---|---|---|
| `SPX` | S&P 500 | equity index | session-bound | a US equity index adapter |
| `DXY` | US Dollar Index | currency | session-bound | a currency index adapter |
| `XAU` | Gold (spot) | commodity | session-bound | a spot gold adapter |
| `US10Y` | US 10-year Treasury yield | rates | session-bound | a government bond yield adapter |
| `VIX` | CBOE Volatility Index | volatility index | session-bound | an options-derived volatility index adapter |

**Horizons:** `latest_bar` (1 bar) · `24_bars` (24 bars) · `168_bars` (168 bars).
Volatility and co-movement both use `168_bars` — two figures describing one week
are comparable with each other; two figures describing two different weeks are a
trap.

---

## 7. Provider limitations and behaviour

- **Only crypto spot is reachable.** `fmis.providers.binance` is the repository's
  only market-data adapter. No credential, no private endpoint, no order.
- **Per-market failure isolation** for five named families (`BinanceError`,
  `IngestError`, `NoObservationsError`, `ValueError`, `TypeError`). Anything else
  **propagates** — asserted with `KeyError`, `AttributeError` and `RuntimeError`.
- **An unsupported market is never fetched**, asserted by recording every URL the
  transport was asked for.
- **One request per market.** The observation series is reduced once and handed to
  both the reading and the co-movement step; `measure_from_observations` exists
  precisely so it is not reduced twice.
- **Freshness:** every reading carries source, interval, closed-bar count and the
  instant its last bar **opened**. Age is overstated by up to one interval and
  never understated. No reading is called stale without an owner-supplied
  `--max-age`.

---

## 8. Hostile review — 14 probes, one real defect

Every probe in §8 of the brief was run. Results:

| Probe | Outcome |
|---|---|
| Duplicate benchmark id / display name / instrument | Refused at construction, three distinct messages |
| Same symbol on two venues | Two markets — venue is part of the instrument |
| Zero prices inside the window | Move measured correctly (zeros were not denominators) |
| Zero price *at* a window start | `UNDEFINED` with `zero_denominator`, never `0.00%` |
| Negative price | Rejected by the canonical ingest boundary → one unavailable row |
| Extreme (1e-8) and huge (1e12) values | Measured, not clamped |
| All bars dated after `as_of` | `read=0`, one unavailable row with the reason |
| Forming bars present | Excluded by two independent mechanisms |
| 120 markets | Page renders, no line over 78 columns |
| Identical returns across every market | Deterministic id-ascending order |
| Mixed quote currencies | Two separate orderings, neither mixed |
| 5,000-character provider error | Wrapped, never truncated, no overlong line |
| Unknown-schedule market | Prints bars, claims no elapsed time |
| One observation only | Nothing measured, no `+0.00%` printed |
| All providers fail | Page renders and says so; exit 1 |
| Different `PYTHONHASHSEED` values | Byte-identical pages (subprocess test) |

### Finding H-1 — a bar count printed as a duration (**real defect, fixed**)

A `CandleSeries` permits **forward gaps**. A provider that omitted bars for
maintenance returns 168 hourly bars spanning **eleven days**, and the page
printed `168_bars (7 days)` over it — a statement the data does not support.
Reproduced directly:

```
nominal label says 7 days; actual span = 11 days, 4:00:00
row: '  168_bars (7 days): +128.24%'
```

**Fix.** `Horizon` now carries `wall_clock_span: timedelta` alongside the phrase,
and refuses to hold one without the other (*a phrase with nothing to check it
against is a claim nobody can falsify*). `HorizonMove.measured_span` is a new
projection. The renderer prints the phrase **only** when the market trades
continuously *and* the measured span equals the duration asserted; otherwise it
falls back to the bar count, which is true of every market under every schedule
with every gap. Three regressions were added, and two mutation probes covering
this rule are detected.

```
GAPPED: '  168_bars (168 bars): +128.24%'      # falls back
CLEAN : '  168_bars (7 days): +128.24%'        # normal case preserved
```

### Finding H-2 — a horizon shorter than a metric's own minimum (**real defect, fixed**)

Found by the test suite rather than by the probes, and worth recording as a
review finding because it escaped design. `realized_volatility` and
`pearson_correlation` require **3** observations; a 1-bar horizon supplies 2, so
the engine's `InsufficientObservationsError` reached the caller as an unhandled
traceback. The engine is right to raise — it is a caller mistake, not a fact
about a market — so the condition is now detected **before** the engine is called
and reported as *"a configuration fault rather than a missing reading — no market
could satisfy it"*. Catching the engine's exception instead would have turned a
misconfigured horizon into a row reading *"unavailable"* on every market forever,
which looks exactly like a data outage. A guard test asserts the restated minimums
still match the engine's own, so the two cannot drift.

### Finding H-3 — microseconds on every age line (cosmetic, fixed)

A default run takes `as_of` from the wall clock, so every row printed
`age 1:36:10.529724`. Ages are now truncated to whole seconds. The direction was
checked: truncation shortens a stated age by under a second, while the
bar-open timestamping already *lengthens* it by up to a full interval, so the
page's *never understated* claim still holds. `as_of` itself keeps full precision
— it is an exact instant, not a duration.

### Finding H-4 — an unread field (found by the release gate, see §9a)

`MarketCategory` was declared and validated but never read. Recorded here so the
findings list is complete; the analysis and fix are in §9a.

### Investigated and dismissed

A vocabulary scan flagged the word *"should"*. It occurs only inside the page's
own prohibitions (*"nothing on it should be read as one"*, *"none should be
inferred"*). Prose denying a word is not the word being used — the same carve-out
`test_directional_vocabulary_boundary.py` documents for engine docstrings.

A 120-market probe read only 68. Investigated: the fixture generated negative
prices, which the canonical ingest boundary correctly rejects. Not a defect —
and a useful incidental demonstration that a malformed payload becomes a
per-market row rather than taking the page down.

---

## 9. Verification

| Gate | Result |
|---|---|
| Focused BT suite | **366 passed** under `-W error` |
| Full repository | **9,320 passed** under `-W error` (BS baseline 8,954 + 366) |
| Statement coverage | **100 %** of all 7 new modules (857 statements) |
| Branch coverage | **100 %** of all 7 new modules (310 branches) |
| Mutation probes | **38 applied, 38 detected, 0 survivors** (development); **20 applied, 20 detected, 0 survivors** (independent release gate) |
| Import cycles | None — layering pinned `models → universe → measure → pulse → render` |
| Export collisions | None, checked against every package's `__all__` repository-wide |
| New runtime dependencies | **0** — `dependencies = []` unchanged, `uv.lock` untouched |
| `git diff --check` | Clean |
| Secret scan | No credential-like string; the package names no URL at all |

### Regression suites

| Milestone | Tests | Result |
|---|---|---|
| BS — Swing Decision Workspace | 251 | pass |
| BR — Setup Evidence | 173 | pass |
| BG-D1 — Setup Identity | 150 | pass |
| BP — Statistics | 539 | pass |
| BO — Paper / Lifecycle | 446 | pass |
| BN — Sizing / Approval | 368 | pass |
| BJ — Today | 327 | pass |
| CLI registry & architecture guards | 351 | pass |

### Mutation probes (38/38 detected)

Sign inversion · wrong baseline · short window measured anyway · undefined→zero ·
forming bar admitted · post-`as_of` bar admitted · boundary shifted to exclusive ·
ascending order · nondeterministic tie-break · unavailable move ranked · excluded
quantity in the sort key · cross-unit comparison · silent exclusion · hidden
unsupported market · volatility undefined→zero · volatility minimum bypassed ·
misaligned windows intersected · reference correlated with itself · co-movement
minimum bypassed · provenance dropped · value-and-reason permitted · neither
permitted · future-dated reading permitted · market vanished from page ·
duplicate id / instrument / display name permitted · **wall-clock claimed without
checking the span** · **wall-clock claimed for a session-bound market** ·
staleness ignored · newest reported as oldest · programming error swallowed ·
one failure aborts the page · unsupported markets fetched · percentage scaled
twice · unavailable hidden · unsupported hidden · width discipline dropped.

Sources were restored from **in-memory byte snapshots**; `git checkout --` was not
used, per the lesson the BR release gate recorded. `git status src/` after the run
showed only BT's own intended changes.

---

## 9a. Independent release gate (2026-08-22)

A release gate re-derived every claim above from the working tree rather than
accepting this report's own account. It re-ran the architecture audit by parsing
each module's real imports, re-measured coverage, wrote **fresh** adversarial
probes rather than reusing BT's tests, re-ran mutation probes, and reconciled the
live page against hand arithmetic on raw provider data.

**It found one defect this report had not.**

### Finding R-1 — `MarketCategory` was declared, validated, and never read

`Benchmark.category` was type-checked at construction and then read by nothing:
no surface printed it, no calculation branched on it, and no renderer grouped by
it. `fmis.data.SeriesIdentity`'s own docstring states this repository's rule —
*"a field earns inclusion only if something in the repository today would be
wrong without it"* — and by that standard a six-member enum carried purely as
metadata failed it. §2 of the gate asks specifically whether the two new concepts
are minimal abstractions rather than premature parallel domain models;
`TradingSchedule` passed (it gates `claims_wall_clock_horizons` and is printed),
`MarketCategory` did not.

**Fix.** The category now earns inclusion by being printed. Each read market's
row carries `market: crypto · continuous`, and each dark row carries its asset
class beside its name — `US Dollar Index [DXY] · currency`. That is the stronger
half: five dark rows naming five *different asset classes* say *"equities, the
dollar, gold, rates and volatility are all unreadable"*, which five bare names
cannot. Two regressions were added and **proved to fail against the unfixed
renderer**, and a mutation probe covering the rule is detected.

### What the gate confirmed independently

| Check | Method | Result |
|---|---|---|
| Engine reuse | AST import scan + grep for statistical formulas | Exactly 3 engine calls, 3 value assignments, **zero** statistical formulas anywhere |
| Provider boundary | grep for payload/transport concepts in the core | Core is provider-free; only `pipeline/pulse.py` names the adapter |
| Reverse dependency | repo-wide AST scan | Only `fmis/pipeline/cli.py` imports it |
| Domain / AI leak | AST scan against 24 domain packages + 6 AI libs | None |
| Persistence | grep for `RecordKind`/repository/write verbs | None; `fmis.persistence` has no notion of a pulse |
| Horizons | fresh probes: zero baseline, single obs, missing baseline, gaps, duplicate bars, future bar | All correct; duplicate bars refused upstream by `CandleSeries` |
| Ordering | permutation fuzz over ties, volatility fuzz across three regimes, extremes ±1e12 | Order invariant to every excluded quantity; one ordering per permutation |
| Provider failure | fail-between-two, several, all, empty response, owned timeout, 4 programmer-bug types | Isolated correctly; `KeyError`/`AttributeError`/`RuntimeError`/`ZeroDivisionError` all propagate |
| Rendering | 120 registry items, all-unsupported, 180-char symbol, 4,000-char error | Max width 78 in every case; nothing truncated |
| Live reconciliation | one frozen snapshot driving both the page and independent hand arithmetic | bars, last-bar-open, all three moves, volatility and correlation **match to 10 decimal places**; leader/laggard match |

### Investigated and dismissed

- *"because"* in a co-movement reason — explains **the system's own behaviour**
  (*"this build never intersects two windows … because the result would be
  labelled with a window it was not measured over"*), not a market cause.
- *"recommend"* on the page — occurs only in the page's own disclaimer,
  *"This page is orientation, not a recommendation."*
- *"no holiday table"* matching a schedule-logic grep — the denial sentence, not
  schedule logic. No open/closed computation exists.
- A one-bar disagreement between the live page and a first hand-check — the page
  derives `is_closed` from the **real wall clock** while that script used
  `as_of`. The page's rule is the conservative one: a future `--as-of` cannot
  conjure bars that have not closed, so the page can under-report and never
  over-report. Confirmed by re-running both sides against one frozen snapshot,
  where every figure matched exactly.

---

## 10. Architecture guards — one widened, one deliberately not

**Widened (1), with justification:**
`test_trade_capture_architecture.test_the_cli_reaches_neither_the_domain_nor_the_store`
gained `fmis.market_pulse` in its permitted-prefix list. This crossing is *smaller*
than any of the eight before it: `fmis.market_pulse` is a market-half package that
reads no store, imports no domain root and names no provider, so the rule the
guard actually protects — that `fmis.pipeline` never reaches `fmis.persistence` —
is not merely unaffected but unreachable from here.

**Deliberately not widened (1):**
`test_structural_facts.test_no_engine_imports_the_fact_sheet_root` is a raw-text
scan, and it failed because `universe.py`'s docstring *mentioned*
`fmis.pipeline.structural_facts` while documenting that the provider labels
match. `fmis.market_pulse` does not import it. The fix was to name the module in
prose rather than by path — exactly the note `fmis.pipeline.prices` already
carries for the identical situation — **not** to add an exemption. A guard that
has to be widened for a docstring is a guard that gets widened for a real
violation next.

**Roster tests updated (5):** the exact command lists in `test_pipeline_cli.py`,
`test_multi_timeframe.py`, `test_pipeline_regime.py`, `test_workspace_render.py`
and `test_pipeline_cli_trade.py`. Each is an additive edit recording *why* `pulse`
sits between `workspace` and `portfolio`: orientation across the markets is what
the owner reads before choosing an asset, and it reads no position, plan or
account at all.

---

## 11. Live demonstration (2026-08-22, real Binance public endpoint)

- `fmits pulse` — **6 markets read, 0 provider failures, 5 with no configured
  provider**, 199 closed 1h bars each.
- Real positive, negative and ordered moves across three horizons; `latest_bar`
  ordered BTC −1.39 % … XRP −8.11 %, while `168_bars` ordered XRP +52.13 % … BNB
  +14.39 % — the same six markets ordered differently by two different horizons,
  which is the ordering rule visible in one page.
- Real volatility, unclassified: BTC 0.0062 … XRP 0.0146, each with its window.
- Real co-movement against BTC: ETH 0.8002, SOL 0.6996, BNB 0.6934, DOGE 0.6077,
  XRP 0.6026, over a stated 169-bar window.
- All five unsupported markets printed with their reasons.
- **Deterministic rerun:** two separate processes with the same `--as-of`
  produced byte-identical pages (`sha256 e5b2e5f973a30d83`).
- **Subset in the owner's order:** `fmits pulse XRP BTC DXY` — XRP printed before
  BTC, DXY reported as unsupported.
- **Owner's staleness bound:** `--max-age 0.5` marked a 1-hour-old reading stale.
- **Live partial failure:** a universe of BTC / an invalid pair / ETH read both
  real markets, filed the invalid one as a provider failure with Binance's own
  words, kept it out of all three orderings while reporting it in each, and
  exited 0.
- **Total failure:** every market failing printed the page, said *"No market could
  be read"*, and exited 1.

No credential appears in any output or in this report.

---

## 12. Known follow-ups

1. **Swing Workspace integration was deliberately not built.** §17 of the brief
   permitted it only if clean. It is left unbuilt and the seam is documented: a
   guard test asserts neither `fmis.today` nor `fmis.swing_workspace` imports the
   pulse, so wiring it later is a deliberate edit rather than a drift. **No trading
   decision, and no `CONFIRMED`/`CANDIDATE`/`WAIT` state, is affected by BT.**
2. **A trading-calendar milestone is the real unlock** for session-bound markets.
   `TradingSchedule` is the seam; the calendar itself is out of scope.
3. **Non-crypto adapters.** Each dark benchmark names the adapter it needs, so the
   registry doubles as that milestone's specification.
4. **Volatility classification** stays impossible until a baseline distribution of
   a market's own past volatility is computed or stored.
5. **Correlation is one-reference and one-window.** A rolling or multi-window form
   is a later decision, not an omission.

---

## 13. Files

**New production (7):**
`src/fmis/market_pulse/__init__.py` · `models.py` · `universe.py` · `measure.py` ·
`pulse.py` · `render.py` · `src/fmis/pipeline/pulse.py`

**New tests (9):**
`tests/market_pulse_helpers.py` · `test_market_pulse_models.py` ·
`test_market_pulse_universe.py` · `test_market_pulse_measure.py` ·
`test_market_pulse_ranking.py` · `test_market_pulse_render.py` ·
`test_market_pulse_compose.py` · `test_market_pulse_edges.py` ·
`test_market_pulse_architecture.py` · `tests/test_pipeline_cli_pulse.py`

**Modified (7):** `src/fmis/pipeline/cli.py` (one command registered) ·
`tests/test_pipeline_cli.py` · `test_multi_timeframe.py` ·
`test_pipeline_regime.py` · `test_workspace_render.py` ·
`test_pipeline_cli_trade.py` · `test_trade_capture_architecture.py`

**0 record kinds · 0 repositories · 0 write paths · 0 ADRs · 0 domain types
changed · 0 new dependencies.**

Committed as `1b56069` (production code + tests), with this documentation commit
recorded directly on top of it.
