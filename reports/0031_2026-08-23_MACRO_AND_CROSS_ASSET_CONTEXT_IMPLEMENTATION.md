# Macro & Cross-Asset Context Foundation (Milestone BU) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0031 |
| **Title** | Macro & Cross-Asset Context Foundation (Milestone BU) — `fmits macro` |
| **Date** | 2026-08-23 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `2b30e38` (production + tests), on base `7fbe611` |
| **Status** | Final |

---

## 1. What the owner can do now that was impossible before

```
fmits macro
```

One command produces a deterministic macro and cross-asset context page: where US
equities, the dollar, two Treasury yields and the volatility index are, what each
did over named windows, what the yields did **in basis points**, how each moved
with Bitcoin over shared observation dates, how fresh each reading is against its
own source's publication schedule, and which markets this build still cannot see
and why.

Before BU the answer to *"what is the dollar doing"* was a dark row. Five of BT's
five dark markets are now measured from a real, public, no-key source; the two
that remain dark say precisely what is missing and why it is not an adapter that
would fix it.

`fmits pulse` gained the same five markets as measured rows.

---

## 2. Starting state, verified

| Item | Value |
|---|---|
| `HEAD` | `7fbe6110a4f4a01e6b7a962034b603f40e5bc231` |
| `origin/main` | `7fbe6110a4f4a01e6b7a962034b603f40e5bc231` |
| Ahead / behind | `0 / 0` |
| Stash | empty |
| Unresolved operation | none |
| Working tree | clean apart from 16 pre-existing untracked research documents under `docs/design/` and `docs/reviews/` |
| Baseline suite | **9320 passed** in 188 s |

The reference commit named in the BU brief was verified rather than assumed.

---

## 3. Repository audit

Read: `CLAUDE.md`, `PROJECT_SPECIFICATION_V1.md`, `PROJECT_VISION_ADDENDUM_V1.md`,
`docs/AI_HANDOFF/CURRENT_STATE.md`, `FMITS_PRODUCT_BACKLOG.md`,
`FMITS_PRODUCT_CHANGELOG.md`, report 0030 (BT), and the `market_pulse`,
`relative_value`, `alignment`, `data`, `providers` and `pipeline` packages in full.

Findings that shaped the design:

* **`fmis.market_pulse.measure_from_observations` already takes an
  `ObservationSeries`, not candles.** BT had split it out so the co-movement step
  could reuse a reduced series. That split is what let a non-candle source reuse
  BT's entire measurement stack with no duplication.
* **`fmis.alignment.align_intersection` already exists** and already returns
  per-series drop counts and a common window. No alignment was written for BU.
* **`fmis.data.ObservationSeries` is already the canonical non-OHLCV model** —
  UTC, strictly increasing, finite, negatives permitted. It is exactly the shape a
  macro series needs, and a yield needs the negatives.
* **The repository has zero runtime dependencies** and both existing adapters use
  `urllib` from the standard library. BU held that line.
* **`fmis.market_pulse` was the one benchmark registry**, and BT had already
  declared SPX/DXY/XAU/US10Y/VIX as dark members of it. Lighting them meant
  editing that registry, not creating a second one.

---

## 4. Provider strategy, and what was actually reachable

The brief's instruction was to determine what providers *actually* support rather
than assume. Endpoints were probed directly before any code was written.

**Chosen source: the Federal Reserve Bank of St. Louis (FRED) public CSV
download**, `GET https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>` —
the link the FRED site itself serves behind *"Download CSV"*. No API key, no
credential, no authentication, `content-type: application/csv`.

Probe results (2026-08-23):

| Series | HTTP | Latest observation | Outcome |
|---|---|---|---|
| `SP500` | 200 | 2026-08-21 · 7674.37 | **adopted** — S&P 500 |
| `DTWEXBGS` | 200 | 2026-08-14 · 118.9028 | **adopted** — Fed nominal broad dollar index |
| `DGS2` | 200 | 2026-08-20 · 4.19 | **adopted** — US 2-year yield |
| `DGS10` | 200 | 2026-08-20 · 4.69 | **adopted** — US 10-year yield |
| `VIXCLS` | 200 | 2026-08-20 · 16.01 | **adopted** — CBOE VIX |
| `GOLDPMGBD228NLBM` | **404** | — | discontinued; gold stays dark |
| `GOLDAMGBD228NLBM` | **404** | — | discontinued; gold stays dark |
| `NASDAQ100`, `DCOILWTICO`, `DTWEXAFEGS` | 200 | — | **declined** — the brief says not to add optional markets merely to lengthen the list |

**The TradingView MCP server was considered and rejected as a product data
source.** It drives a GUI desktop application over the Chrome DevTools Protocol.
It is available to the agent working on this repository; it is not available to a
Python process running `fmits macro`, and building the product's macro layer on a
running desktop app would make a CLI depend on a GUI session. It is not an
adapter and was not made one.

### The DXY decision — the milestone's most consequential judgement

`DTWEXBGS` is **not** DXY. ICE's US Dollar Index is a licensed index over six
currencies with weights fixed in 1973; the Federal Reserve's nominal broad index
covers 26 currencies with annually revised weights, based January 2006 = 100.
They are different numbers.

Printing the broad index under DXY's name would have been the single most
plausible-looking lie this page could tell — a real number, correctly computed,
under the wrong label, and undetectable by any downstream check. So:

* `USDBROAD` — **new benchmark**, carried under its own name and its own unit,
  `index points (Jan 2006 = 100)`.
* `DXY` — **stays unsupported**, with a reason naming the licence and explicitly
  saying it is *not* substituted by `USDBROAD`.

A test asserts the two never share a name or a unit, and that `DXY` appears on the
page exactly once, in the unavailable section.

---

## 5. Architecture

```
RAW SOURCE
  -> fmis.providers.fred          CSV        -> ObservationSeries      (new)
  -> fmis.pipeline.market_data    benchmark  -> observations           (new, shared)
  -> fmis.market_pulse.measure    observations -> MarketReading        (reused)
  -> fmis.macro.context           observations -> levels, rates, relations (new)
  -> fmis.macro.models            facts      -> MacroContextReport     (new)
  -> fmis.macro.render            report     -> a page                 (new)
  -> LATER INTERPRETATION                                              (not in this build)
```

### The interpretation boundary

**BU stops before interpretation and carries nothing to cross that line with.**
There is no AI call, no LLM client, no prompt, no prediction, no causal claim, no
regime label, no risk-on/risk-off state and no signal anywhere in `fmis.macro` or
in either composition root. A guard asserts the package imports nothing whose name
begins `anthropic`, `openai`, `llm` or `prompt`, and a second asserts no field is
named regime, signal, bias, score, weight or confidence. The page states that the
10-year moved +10 bp and that the S&P and Bitcoin correlated 0.31 over 21 shared
observations; it never states what either fact means. That reading belongs to a
later milestone, which will consume these facts rather than replace them.

### Documented deviations from the brief's implied shape

1. **The benchmark vocabulary stayed in `fmis.market_pulse`, not `fmis.macro`.**
   The brief said to reuse BT's registry and not create a second one. `Benchmark`,
   `MarketUniverse` and `Horizon` therefore stayed where they were, and BU
   *extended* them with `QuantityKind`, `FreshnessPolicy` and `FreshnessState`.
   Those belong there because `fmits pulse` itself needs them: the moment US10Y
   became readable, the pulse had to know a yield is not a price.

   The consequence is that `fmis.market_pulse` is now the shared cross-asset
   vocabulary as well as the pulse surface, and its name understates it. Renaming
   it (to `fmis.benchmarks`, say) touches a large number of tests and is recorded
   as a follow-up rather than done inside this milestone.

2. **A shared dispatch layer was added: `fmis.pipeline.market_data`.** With two
   adapters, either every composition root grows a chain of `if provider ==`
   branches or dispatch happens once. It happens once. Both `fmits pulse` and
   `fmits macro` read through it, so neither can fetch differently, and the
   architecture guard now asserts that only this module reaches two adapters.

3. **No ADR was written.** The durable decisions here — a second adapter, a
   quantity-kind distinction, a comparability rule — are recorded in module
   docstrings and pinned by guard tests, which is where this repository's
   equivalent decisions already live. Nothing in BU overturns an existing ADR.

---

## 6. Benchmark universe — exact

**Supported (11):**

| Id | Name | Source | Unit | Kind | Cadence |
|---|---|---|---|---|---|
| BTC, ETH, SOL, BNB, XRP, DOGE | crypto spot pairs | `binance-spot` | USDT | price | 1h |
| SPX | S&P 500 | `fred SP500` | index points | price | 1d |
| USDBROAD | US Dollar Index (Fed nominal broad) | `fred DTWEXBGS` | index points (Jan 2006 = 100) | price | 1d |
| US2Y | US 2-year Treasury yield | `fred DGS2` | percent per annum | **rate** | 1d |
| US10Y | US 10-year Treasury yield | `fred DGS10` | percent per annum | **rate** | 1d |
| VIX | CBOE Volatility Index | `fred VIXCLS` | volatility points (annualised implied %) | price | 1d |

**Unsupported (2), each naming why:**

| Id | Name | Why dark |
|---|---|---|
| DXY | ICE US Dollar Index (DXY) | licensed index; `USDBROAD` is a different measure and is not substituted for it |
| XAU | Gold (spot) | the LBMA benchmark series the macro source carried were discontinued and return not-found; no configured source publishes spot gold |

Five of the six market categories now have a live member. Commodities do not,
because the only commodity in the universe is spot gold.

---

## 7. Rate semantics

`fmis.macro.rates` is a new deterministic engine for a new quantity class. It is
deliberately **not** in `fmis.relative_value`, whose whole subject is ratios of
levels (ADR-0004, simple returns only); a yield difference is a level difference.

`rate_change(4.20, 4.30)` returns **three named quantities and no default one**:

| Field | Value | Meaning |
|---|---|---|
| `basis_points` | `+10.0` | the difference, in hundredths of a percentage point |
| `percentage_points` | `+0.10` | the same difference in whole points |
| `relative_change` | `+0.0238` | the *ratio* — a different fact, always labelled |

`RateChange` has no field called *the* change. A test asserts the field set
exactly, because a default-named field is how the wrong quantity reaches a page.

* Scale is `BASIS_POINTS_PER_PERCENTAGE_POINT = 100`, an exact integer, appearing
  in one module. A guard asserts no other module in `fmis.macro` holds `10000`.
* Sign convention: a yield that rose is positive. Pinned by test and by mutation.
* A zero starting level yields `relative_change=None` with a reason **and still
  reports the basis-point move** — 0.00% to 0.25% is +25 bp, and losing that to a
  division nobody needed would be a real loss.
* Negative yields are accepted. They are real.
* Floats, not `Decimal`, matching the whole repository; the error is ~1e-14 on a
  figure published to two decimals, and the renderer prints one decimal of a basis
  point. Stated in the module docstring rather than left to be discovered.

---

## 8. Session and calendar semantics

This build still holds **no trading calendar** — no holiday table, no exchange
timezone, no open/closed computation. BU did not build one and says so on every
page.

What BU added is the minimum needed to stop a dishonest comparison:

* **Macro markets get their own horizons.** `latest_observation`,
  `5_observations`, `21_observations` — distinct ids from BT's `latest_bar`,
  `24_bars`, `168_bars`. This is the milestone's central honesty decision: 168
  hourly bars is one week and 168 daily observations is eight months, and one
  label over both would have been indefensible.
* **No macro window is ever described in days or weeks.** Five completed
  observations span seven calendar days in an ordinary week and nine across a
  holiday weekend, and this build cannot tell which it is looking at.
* **`horizons_for(benchmark)` maps a cadence to its family** and raises for a
  cadence no family is defined for — a market measured over a window nobody chose
  for it would produce figures under a label that does not describe them.

**Boundary for a future Market Calendar milestone**, stated explicitly: session
open/close instants, holiday tables, half-days and exchange timezones are absent.
Their absence is paid for openly in the freshness tolerances (§9) rather than
hidden.

---

## 9. Freshness semantics

A single universal stale threshold is dangerous, and BU does not use one.

`FreshnessPolicy(publication_period, tolerance, basis)` states how often a source
publishes and how late it may be. `behind_schedule_after` is their sum, computed
rather than stored. Classification is `ON_SCHEDULE` / `BEHIND_SCHEDULE` /
`UNKNOWN` — deliberately **not** fresh/stale, because "stale" is a judgement about
usability and depends on what the reader is doing.

| Policy | Period | Tolerance | Bound | Basis |
|---|---|---|---|---|
| `CRYPTO_FRESHNESS` | 1 h | 2 h | 3 h | a continuous venue closes an hourly bar every hour; tolerance covers the forming bar and request latency |
| `FRED_DAILY_FRESHNESS` | 1 d | 4 d | 5 d | a business-day series with an overnight lag; tolerance covers a weekend, a holiday this build has no calendar for, and that lag |
| `FRED_LAGGED_WEEKLY_FRESHNESS` | 1 d | 13 d | 14 d | the Fed releases the broad dollar index about a week behind a market print |

Every policy must state its `basis`; a policy without one would be exactly the
invented threshold `fmis.market_pulse.render` declines to choose for the owner,
wearing a respectable name.

A negative age raises rather than classifying: an observation from the future is a
clock defect, and calling it on-schedule would hide it behind a reassuring word.

**`fmits pulse --max-age` interaction.** The owner's uniform bound still applies
and is never overridden, but a reading it marks overdue now also states its
source's own schedule — so a daily series flagged by an hourly bound reads *"older
than you asked for rather than later than its source is"* instead of looking like
broken data.

---

## 10. Comparability

An explicit refusal mechanism, not a renderer convention.

`ComparabilityKey(quantity_kind, quote_unit, observation_interval, horizon_id,
metric)`. `compare_keys` requires **all five** to match and returns a verdict
naming **every** component that differs, not the first — a reader told only about
units will fix the units and be refused again for the interval.

`compare_for_correlation` drops **the unit and only the unit**, because a Pearson
correlation of simple returns is scale-invariant by construction; requiring one
unit would refuse every genuine cross-asset comparison the page exists to make.
The quantity kind is explicitly *not* dropped: a yield's simple return is a ratio
of two rates, and correlating it against an equity index's return would put two
different constructions in one number.

Refusals actually produced on the live page:

* `US2Y` vs `BTC` — *not comparable: different quantity kind*
* `US10Y` vs `BTC` — *not comparable: different quantity kind*

A yield is never placed in a return ordering (`RATE_LIKE_EXCLUSION`), and an
ordering is emitted only when it places at least two markets
(`MINIMUM_ORDERED_MARKETS`) — see §14.

---

## 11. Correlation methodology

* **Metric**: `fmis.relative_value.pearson_correlation` over simple returns. No
  second correlation was written.
* **Alignment**: `fmis.alignment.align_intersection` — strict intersection on
  shared observation instants. No alignment was written for BU.
* **Window**: the last `21 + 1` shared observations, taken **after** aligning.
  Tailing first would take 22 from each series and then find few in common; a
  mutation probe confirms the order is load-bearing.
* **Reported**: the value, the exact `observation_count` used, the window dates,
  the total `aligned_count` of shared dates, and how many observations **each
  side** lost to alignment. The window count and the shared count are two
  different numbers and the type refuses to conflate them.
* **Minimum sample**: 3, restated from the engine so a horizon too short for it is
  reported as a configuration fault rather than as a market outage.
* **Reference**: `BTC`, a stated choice printed on the page, read at the macro
  cadence (daily) because an hourly bar and a daily observation share no instants.
* **No causation language, and no field one could enter through**: no p-value, no
  significance flag, no lead/lag, no direction of influence. A guard test asserts
  the field names.
* **Stated limitation**: two observations sharing a date are not simultaneous — a
  crypto daily bar covers the whole UTC day and a US session market's covers that
  day's session. The caveat says so.

Difference from BT deliberately: `measure_co_movement` *refuses* a misaligned
pair, because the pulse compares markets sharing one venue's calendar where a
mismatch means something is wrong. The macro page compares a seven-day market with
a five-day one, where a mismatch is the normal case; it intersects, and the
intersection is honest because it is **named**.

---

## 12. Exact file scope

**New production (9 files, 3 130 lines):**

```
src/fmis/macro/__init__.py
src/fmis/macro/rates.py
src/fmis/macro/comparability.py
src/fmis/macro/models.py
src/fmis/macro/context.py
src/fmis/macro/render.py
src/fmis/providers/fred.py
src/fmis/pipeline/market_data.py
src/fmis/pipeline/macro.py
```

**Modified production (8 files):**

```
src/fmis/market_pulse/models.py     QuantityKind, FreshnessState, FreshnessPolicy,
                                    Benchmark.quantity_kind / .freshness_policy,
                                    MarketReading.freshness_at
src/fmis/market_pulse/universe.py   5 markets lit, 2 restated as dark, macro
                                    horizons, freshness policies, horizons_for
src/fmis/market_pulse/measure.py    rate-like markets produce no percentage move
                                    and no realized volatility
src/fmis/market_pulse/pulse.py      RATE_LIKE_EXCLUSION, MINIMUM_ORDERED_MARKETS,
                                    co-movement scoped to one cadence
src/fmis/market_pulse/render.py     rows only for windows a market holds, one
                                    shared reason collapsed, schedule beside the bound
src/fmis/market_pulse/__init__.py   exports
src/fmis/pipeline/pulse.py          reads through the shared dispatch layer
src/fmis/pipeline/cli.py            `fmits macro`
```

**New tests (12 files, 5 615 lines, 496 tests):** `macro_helpers.py`, `test_macro_rates.py`,
`test_macro_comparability.py`, `test_macro_models.py`, `test_macro_context.py`,
`test_macro_freshness.py`, `test_macro_render.py`, `test_macro_compose.py`,
`test_macro_hostile.py`, `test_macro_architecture.py`, `test_providers_fred.py`,
`test_pipeline_cli_macro.py`.

**Modified tests (13 files)** — every change is a BT assertion BU deliberately
supersedes, each carrying its reasoning in the test itself. No guard was weakened
to make it pass; two were extended narrowly (§16) and one was **satisfied** rather
than exempted by making `_HORIZONS_BY_INTERVAL` a `MappingProxyType`.

Untouched, as required: the 16 pre-existing research documents, `pyproject.toml`,
`uv.lock`.

---

## 13. Test results

| Gate | Result |
|---|---|
| Baseline before BU | 9320 passed |
| Full suite after BU | **9824 passed**, 207 s |
| Full suite under `-W error` | **9824 passed** — no warning anywhere |
| BU focused suite | 496 passed, 2.3 s |
| BT / BS / BR / BG-D1 / BP / BO / BN / BJ regressions | all green |
| `relative_value`, `alignment`, `data` regressions | all green |
| Pipeline / CLI regressions | all green |

**Coverage over the BU scope** (statement + branch):

| Module | Cover |
|---|---|
| `fmis/macro/rates.py` | 100% |
| `fmis/macro/context.py` | 100% |
| `fmis/macro/models.py` | 100% |
| `fmis/macro/comparability.py` | 98% |
| `fmis/macro/render.py` | 100% |
| `fmis/providers/fred.py` | 99% |
| `fmis/pipeline/market_data.py` | 94% |
| `fmis/pipeline/macro.py` | 94% |
| `fmis/market_pulse/*` | 95–100% |
| **Total** | **99% statements** (9 of 1 802 missed), 650 branches |

The residue is seven defensive type-guard branches, the real-transport default in
the macro composition root, and one `urllib` `HTTPError` path that needs a live
HTTP error to reach. Every module in `fmis.macro` is at 100% except one
`TypeError` guard in `comparability.py`.

---

## 14. Behaviour changes to Milestone BT

BU changed three BT behaviours. Each is deliberate, each is documented in the
code, and each has its BT test updated with the reasoning rather than deleted.

1. **A yield produces no percentage move and no realized volatility.** See §17 —
   this was found by the live demonstration, not by a test.
2. **An ordering is emitted only when it places ≥2 markets.** BT's universe was
   six crypto markets in one unit on one cadence, so every ordering held six. BU's
   universe spans two cadences and five quote units: the full cross product is 30
   (horizon, unit) pairs of which 27 place nothing, and emitting them all buried
   the three real orderings under twelve sections reading *"no market in this unit
   could be ordered"* (measured: 478-line page). Nothing is hidden — a market
   absent from every ordering still carries its move on its own row, and an unread
   market is still reported with its reason.
3. **A market's rows are its own measurements.** Iterating every declared horizon
   printed three rows per market saying *"not measured on this run"* for the other
   cadence's family — asserting an attempt that was never made and never will be.

---

## 15. Hostile review

Every attack the brief names was run; each is now a permanent test in
`tests/test_macro_hostile.py` (32 tests).

| Attack | Outcome |
|---|---|
| DXY and gold sharing a display name | refused at universe construction |
| One source series mapped to two benchmarks | refused — *"one fact printed twice… a rigged tie"* |
| Quote/unit mismatch in a comparison | refused, naming every differing component |
| Yield accidentally treated as a price | **unrepresentable** — no percentage move is produced |
| 10Y shown as `+0.10%` instead of `+10 bp` | **found live and fixed** (§17) |
| VIX ranked against a price return | refused; each is alone in its unit and units differ |
| Different calendars falsely correlated | intersection only, with drop counts stated |
| Daily data marked stale by an hourly threshold | per-source policies; the bound now states the schedule beside it |
| Weekend equity data treated as missing | business-day fixtures; every price-like move measured |
| Unsupported benchmark silently omitted | both dark markets appear on both pages with reasons |
| Every source call failing | honest empty page, no zeros, exit code 1 |
| One failure hiding later successes | first-market failure leaves the other four read |
| Same timestamp with conflicting values | refused by `ObservationSeries` (strictly increasing) |
| Future observation | refused by the report; refused by `FreshnessPolicy.classify` |
| 1 000-digit Decimal | overflows to infinity and is refused, never printed |
| 200 benchmarks | page renders, every line ≤ 78 columns |
| 5 000-byte provider message | wrapped, never truncated, width held |
| Deterministic rerun under `PYTHONHASHSEED` 0/1/12345 | byte-identical pages |

---

## 16. Architecture and static results

* **Import cycles**: none. Layering pinned: `rates → comparability → models →
  context → render`.
* **Export collisions**: none, checked against every package's `__all__`
  repository-wide.
* **`fmis.macro` imports**: `fmis.data`, `fmis.alignment`, `fmis.relative_value`,
  `fmis.market_pulse` and itself. 23 forbidden dependencies asserted individually.
* **No provider, transport, store, AI, swing decision or persistence import.**
* **No provider-specific vocabulary in the core** — a guard asserts `DGS10`,
  `SP500`, `VIXCLS`, `DTWEXBGS`, `BTCUSDT` and `fredgraph` appear nowhere in
  `fmis.macro`.
* **No second registry** — a guard asserts `fmis.macro` never constructs a
  `Benchmark`, `MarketUniverse` or `ProviderInstrument`.
* **No second formula** — a guard asserts no `sqrt`, `stdev`, `variance`, `fsum`
  or `** 2` anywhere in `fmis.macro`, and no hand-rolled set intersection.
* **Writes nothing, reads no clock, holds no mutable module state, defines no
  repository and no schema version. No record kind added.**
* **No new runtime dependency.** `pyproject.toml` still declares
  `dependencies = []`; the FRED adapter is `urllib` + `csv`.
* **`git diff --check`**: clean. **Secret scan**: clean. **Artifact scan**: clean.

Two guards were extended narrowly, each with its justification written into the
test:

1. `test_only_the_composition_root_and_the_cli_import_it_from_the_pipeline` — now
   admits `fmis.pipeline.macro` and `fmis.pipeline.market_data`. Both are
   composition-layer modules of exactly the kind `fmis.pipeline.pulse` already
   was; the set stays closed and small.
2. `test_the_cli_reaches_neither_the_domain_nor_the_store` — now admits
   `fmis.macro`, on the same footing BT's widening for `fmis.market_pulse` used.
   The rule it protects (`fmis.pipeline` never reaches `fmis.persistence`) remains
   unreachable from there.

One BT guard's *permitted arithmetic* list gained `self.publication_period +
self.tolerance` — a sum of two durations, in the same category as the existing
permitted `self.bars + 1`. No market quantity is computed in that module.

---

## 17. The defect the live demonstration caught

The brief requires a live demonstration, and it earned its place.

With all 9 700 tests green, `fmits pulse` printed:

```
US 10-year Treasury yield  [US10Y]
  latest_observation (1 bar): +0.86%
```

That is the milestone's own headline prohibition — a yield's move shown as a
percentage. BU's first fix had excluded rate-like markets from the *orderings*,
which is where a comparison happens; it had not stopped the figure appearing on
the market's own row, unlabelled, where a reader takes it for the move. `+0.86%`
is the ratio 4.69 ÷ 4.65; the move was **+4 basis points**.

**Fix**: the number is no longer produced. `measure_from_observations` gives a
rate-like benchmark moves carrying `RATE_LIKE_MEASURE_REASON` instead of a value,
so no consumer of a `MarketReading` can print one by accident. Realized volatility
is refused with it, because it is the sample standard deviation of the identical
simple-return construction — the dispersion of ratios of rates is not the
dispersion of the yield. `fmits macro` states the move in basis points, from the
same observations.

Three regression tests now pin this at the model, the reading and the rendered
page. A mutation probe removing the guard is killed.

The lesson is recorded plainly: the test suite asserted the *comparison* rule and
not the *display* rule, and only running the real command against real data
surfaced the gap.

---

## 18. Performance and fetch discipline

Measured at the composition root with counting transports.

| Command | Markets | Provider calls | Series calls | Duplicate fetches |
|---|---|---|---|---|
| `fmits macro` | 5 macro + 1 reference | 6 | 6 | **0** |
| `fmits pulse` | 11 | 11 | 11 | **0** |

Each market is read once and the resulting `ObservationSeries` is handed to the
reading, the level, the rate fact and the relationship. Asserted by test:
`len(calls) == len(set(calls))` for both adapters on both commands.

The macro page costs one extra request for the cross-asset reference (BTC at the
daily cadence), which buys the only genuinely cross-asset section on the page.
`--no-relationships` omits both the section and the request.

FRED returns full history (`DGS10` is ~16 000 rows since 1962); the endpoint takes
no range parameter, so the whole body arrives and `OBSERVATION_LIMIT = 260` trims
it. That trim is a display decision as much as a memory one: reporting *"dropped
16 000 observations"* in an alignment diagnostic would be a true number that told
a reader nothing.

---

## 19. Live demonstration (2026-08-23, real data)

`fmits macro` — exit 0, 5 markets read, 0 source failures, 2 with no source.

| Market | Level | Observed | Source | Freshness |
|---|---|---|---|---|
| S&P 500 | 7674.3700 index points | 2026-08-21 | `fred SP500 1d` | on schedule (age 2 d) |
| US Dollar Index (Fed nominal broad) | 118.9028 index points (Jan 2006 = 100) | 2026-08-14 | `fred DTWEXBGS 1d` | on schedule (age 9 d) |
| US 2-year Treasury yield | 4.1900 percent per annum | 2026-08-20 | `fred DGS2 1d` | on schedule (age 3 d) |
| US 10-year Treasury yield | 4.6900 percent per annum | 2026-08-20 | `fred DGS10 1d` | on schedule (age 3 d) |
| CBOE Volatility Index | 16.0100 volatility points | 2026-08-20 | `fred VIXCLS 1d` | on schedule (age 3 d) |
| ICE US Dollar Index (DXY) | — | — | — | **no configured source** (licensed index) |
| Gold (spot) | — | — | — | **no configured source** (LBMA series discontinued) |

### Manual reconciliation against the raw CSV

| # | Figure | Page | Raw source | ✓ |
|---|---|---|---|---|
| 1 | SPX latest-observation return | `+0.4346%` | 7674.37 ÷ 7641.16 − 1, 08-20 → 08-21 | ✓ |
| 2 | US10Y latest-observation move | `+4.0 bp` (4.65% → 4.69%) | 08-19 = 4.65, 08-20 = 4.69 | ✓ |
| 2b | US10Y 5-observation move | `+6.0 bp` (4.63% → 4.69%) | 08-13 = 4.63 over 6 observations | ✓ |
| 2c | its relative change, **labelled** | `+0.86%` | 4.69 ÷ 4.65 − 1 — a different fact | ✓ |
| 3 | VIX level | `16.0100` | `VIXCLS` 2026-08-20 = 16.01 | ✓ |
| 4 | SPX vs BTC correlation | `−0.0199`, n = 22 (07-23 → 08-21), 137 shared dates, dropping 123/62 | recomputed from the aligned pair | ✓ |

`fmits pulse` — exit 0, 254 lines, 11 markets read. All five formerly dark rows
now measured. The two yields state the basis-point refusal rather than a
percentage. Three orderings, all USDT/hourly, six markets each.

---

## 20. Known limitations

1. **No trading calendar.** Session boundaries, holidays and half-days are not
   modelled. Paid for openly in the freshness tolerances and stated on every page.
2. **Observation dating.** A FRED observation carries a date, not an instant, and
   is timestamped at 00:00 UTC of that date. Ages are therefore **overstated by up
   to one period and never understated** — the safe direction. The cost is real for
   historical replay: an `as-of` inside an observation's own date keeps a value not
   published until later that day. Harmless for the live orientation this build
   uses; documented in `OBSERVATION_DATING_LIMITATION`.
3. **Same-date is not same-hour.** A crypto daily bar covers the UTC day; a US
   session market's observation covers that day's session. Stated in the caveat.
4. **No gold, no DXY.** Both need a data licence, not an adapter.
5. **Yield co-movement is not computed.** A yield's honest correlation measure is
   built on basis-point changes; the page refuses the pair and says so rather than
   answering with the ratio construction.
6. **`fmis.market_pulse` is under-named** for what it now holds (§5).
7. **Volatility is unclassified**, exactly as in BT — no baseline distribution
   exists to call a reading low or elevated.

---

## 21. Known follow-ups

* A **Market Calendar** milestone: exchange sessions, holidays, half-days. Would
  let tolerances shrink and windows carry honest durations.
* **Yield-change correlation** over basis-point differences — the measure the page
  currently refuses.
* A **rates curve** view: 2s10s and other spreads are now one subtraction away and
  were deliberately left out of BU.
* A **macro evidence domain** attached to a setup as a separate, non-decisional
  input. BU built the facts and deliberately left the seam unbuilt; a guard test
  asserts nothing consumes it, and wiring it is that milestone's deliberate edit.
* Consider renaming `fmis.market_pulse` to reflect its role as shared cross-asset
  vocabulary.
* Gold and DXY if a licensed source is ever configured.

---

## 22. Swing workspace — unchanged, and asserted

BU changed nothing about `CONFIRMED`, `CANDIDATE`, `WAIT`, setup ranking, position
sizing or approval. `fmis.swing_workspace`, `fmis.today` and `fmis.setup_evidence`
import neither `fmis.macro` nor `fmis.pipeline.macro`, asserted by test in both
directions. `fmits macro` reads no store and touches no trading decision, asserted
by an AST scan of its own CLI runner.

---

## 23. Git state

An independent release gate was run over the complete working tree on
**2026-08-24** before anything was committed: full state verification against the
remote, an architecture audit from source, benchmark/rate/session/freshness/
comparability/correlation attacks, provider-failure attacks, fetch measurement,
the focused suite, every named regression set, coverage, all 36 mutation probes,
static and safety checks, and a live demonstration reconciled against raw source.
It found no defect. It did raise coverage — four branches introduced by the
live-demo fix were reachable and untested, and five tests were added for them,
taking `fmis.macro.render` and `fmis.macro.models` to 100% and the suite from
9 819 to 9 824.

```
starting HEAD        7fbe6110a4f4a01e6b7a962034b603f40e5bc231
starting origin/main 7fbe6110a4f4a01e6b7a962034b603f40e5bc231 (confirmed by ls-remote)
ahead/behind         0 / 0
stash                empty
in-progress op       none
```

**Commit A** — `2b30e38` · `feat(macro): add deterministic Macro & Cross-Asset
Context` · 42 paths, production and tests only.

**Commit B** — `docs(product): record Macro & Cross-Asset Context milestone` ·
this report, `reports/README.md`, `CURRENT_STATE.md`, the backlog and the
changelog.

Both are plain commits on `main`, fast-forward from the starting `origin/main`.
No history was rewritten; nothing was forced, amended, rebased, squashed or
tagged, and no branch other than `main` was pushed. The 16 pre-existing research
documents remain untracked and untouched.
